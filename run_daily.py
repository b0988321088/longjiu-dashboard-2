#!/usr/bin/env python3
"""
龍九控股日報 + 靜態儀表板 產出入口
功能：一鍵產出三件套
  1. daily_report_v2_{date}.html
  2. index.html（靜態儀表板，懶更新）
  3. changelog_{date}.md（差異說明）
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
import daily_intel as mi_mod
from daily_intel import load_daily_analysis

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
SNAPSHOT = BASE / "snapshot.json"
RULES = BASE / "DAILY_REPORT_PIPELINE_RULE.md"
LEDGER = BASE / "Company_Ledger.md"
INDEX_TEMPLATE = BASE / "index_template.html"  # 靜態儀表板模板（預留）
OUT_DAILY = BASE / f"daily_report_v2_{TODAY}.html"
OUT_INDEX = BASE / "index.html"


# ==========================================================================
# 1. 三源真值校準
# ==========================================================================

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_markdown_value(text: str, pattern: str) -> str | None:
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def calibrate_sources() -> dict:
    """讀取三源並回傳校準後的真值 dict；不一致就 raise。"""
    snap = load_json(SNAPSHOT) if SNAPSHOT.exists() else {}
    rules = load_text(RULES) if RULES.exists() else ""
    ledger = load_text(LEDGER) if LEDGER.exists() else ""

    # snapshot 真值
    s_income = snap.get("monthly_income")
    # Prefer MB-calibrated expense if available
    s_expense = snap.get("monthly_expense_mb_override") or snap.get("monthly_expense")
    s_work_surplus = snap.get("working_surplus")
    s_retire_surplus = snap.get("retirement_surplus")
    s_insurance = snap.get("insurance_current_value")
    s_allianz = snap.get("allianz_ab_current_value")
    s_firstjin = snap.get("firstjin_current_value")
    s_rent = snap.get("rent_monthly_actual")
    s_securities = snap.get("securities_total_market_value")

    # rules 真值（文字檔，用 regex 抓）
    r_income = extract_markdown_value(rules, r"月收入 \*\*([0-9,]+)\*\*")
    r_expense = extract_markdown_value(rules, r"月支出 \*\*([0-9,]+)\*\*")
    r_work_surplus = extract_markdown_value(rules, r"工作期盈餘 \*\*([+-]?[0-9,]+)\*\*")
    r_retire_surplus = extract_markdown_value(rules, r"退休後盈余 \*\*([+-]?[0-9,]+)\*\*")
    r_allianz = extract_markdown_value(rules, r"安聯 A \+ 安聯 B = .*?現值 ([0-9,]+)")
    r_firstjin = extract_markdown_value(rules, r"第一金 = .*?現值 ([0-9,]+)")

    def to_num(s: str | None) -> int | None:
        if s is None:
            return None
        return int(s.replace(",", ""))

    def check(label, a, b):
        if a is None or b is None:
            return None
        return a == b

    checks = {
        "monthly_income": check("月收入", s_income, to_num(r_income)),
        # monthly_expense 以 MB override 為唯一真值，不跟旧文字檔比對
        "working_surplus": check("工作期盈餘", s_work_surplus, to_num(r_work_surplus)),
        "retirement_surplus": check("退休後盈餘", s_retire_surplus, to_num(r_retire_surplus)),
        "allianz_value": check("安聯A+B現值", s_allianz, to_num(r_allianz)),
        "firstjin_value": check("第一金現值", s_firstjin, to_num(r_firstjin)),
    }

    conflicts = {k: v for k, v in checks.items() if v is False}
    if conflicts:
        print(f"[CALIBRATE] 三源校準失敗：{conflicts}")
        sys.exit(2)

    print(f"[CALIBRATE] 三源校準通過")
    # 真值錨定：本月保單配息（缺 snapshot 欄位時由真值計算）
    monthly_dividend = snap.get("monthly_dividend")
    if monthly_dividend is None:
        # 保守回退：安聯 A+B + 第一金月配
        monthly_dividend = (snap.get("allianz_ab_monthly", 55_451) or 55_451) + (snap.get("firstjin_monthly", 13_593) or 13_593)

    total_assets = snap.get("total_assets")
    total_liabilities = snap.get("total_liabilities")
    net_worth = snap.get("net_worth")
    if net_worth is None and total_assets is not None and total_liabilities is not None:
        net_worth = total_assets - total_liabilities
    return {
        "date": TODAY,
        "monthly_income": s_income,
        "monthly_expense": s_expense,
        "working_surplus": s_work_surplus,
        "retirement_surplus": s_retire_surplus,
        "insurance_total": s_insurance,
        "allianz_ab": s_allianz,
        "firstjin": s_firstjin,
        "rent_monthly": s_rent,
        "securities_total": s_securities,
        "monthly_dividend": monthly_dividend,
        "relay_stations": 3,
        "cc_4cards": ["玉山UNI", "台新Richart", "永豐SPORT", "台北富邦momo/J"],
        "loans_2mortgage": ["洲際W房貸", "大義街房貸+理財型利息"],
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "insurance_current_value": s_insurance,
        # 穿透分析數據
        "penetration": snap.get("penetration_canonical", {}),
        # 穿透扁平化（供模板直接引用）
        "tw_stock": 2_065_675,
        "tw_stock_pct": 7.2,
        "us_stock": 13_226_058,
        "us_stock_pct": 46.1,
        "defensive": 5_307_637,
        "defensive_pct": 18.5,
        "bond": 9_697_196,
        "bond_pct": 33.8,
        "cash": 2_200_410,
        "cash_pct": 7.7,
        "investment_total": 28_496_976,
        "market_change": -6.0,
        "rebalance_suggestion": "台股低標補碼、美股超標減碼",
    }


# ==========================================================================
# 2. 日報產出
# ==========================================================================


def _diff_to_buffett_bullets(tv: dict, y: dict) -> list[str]:
    bullets = []
    pairs = [
        ("monthly_expense", "月支出", "支出上升時優先檢視信用卡/房貸是否異常"),
        ("monthly_income", "月收入", "收入變動確認是否為實質調整或一次性"),
        ("net_worth", "淨資產", "淨資產下滑需檢視資產配置是否有過度曝險"),
        ("insurance_current_value", "保單現值", "保單現值下降應評估是否調整基金標的"),
        ("monthly_dividend", "本月配息", "配息縮水時補位防禦型配息基金"),
        ("working_surplus", "工作期盈餘", "盈餘下滑應壓縮非必要支出"),
        ("retirement_surplus", "退休後盈餘", "退休金流下降需提前建立現金緩衝"),
    ]
    for key, label, hint in pairs:
        t = tv.get(key)
        prev = y.get(key)
        if t is None or prev is None:
            continue
        if isinstance(t, (int, float)) and isinstance(prev, (int, float)) and t != prev:
            direction = "上升" if t > prev else "下降"
            bullets.append(f"{label}{direction}（{t:,} vs 昨日 {prev:,}）：{hint}")
    return bullets




# ==========================================================================
# 3. 差異說明
# ==========================================================================



def _build_market_rows(signals: dict, tv: dict) -> str:
    sell = signals.get("sell_signals", [])
    rows = [
        f"<tr><td>台股加權指數（{{TODAY}}）</td><td>待補齊；外資單日賣超 —</td><td>高檔震盪</td></tr>",
        f"<tr><td>台積電（{{TODAY}}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>費半（{{TODAY}}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>美股（{{TODAY}}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>美國 CPI</td><td>待補齊</td><td>待補齊</td></tr>",
        # 0050 配息：待 MB 確認後由 daily_analysis.json 注入
    ]
    return "\n          ".join(rows)


def _inject_market_intel(html: str, tv: dict, signals: dict) -> str:
    """以 daily_analysis.json + hunter intel 注入 market + Buffett + CTO 區塊。"""
    analysis = load_daily_analysis()
    if not analysis:
        return html

    scenario = analysis.get("scenario", {{}})
    buffett = analysis.get("buffett", {{}})
    cto = analysis.get("cto", {{}})

    # Bull / Bear
    html = html.replace("__BULL_TEXT__", buffett.get("bull", "—"))
    html = html.replace("__BEAR_TEXT__", buffett.get("bear", "—"))

    # Market rows from analysis
    market = analysis.get("market", {{}})
    twii = market.get("twii", "待補齊")
    tsm = market.get("tsm", "待補齊")
    sox = market.get("sox", "待補齊")
    us = market.get("us", "待補齊")
    cpi = market.get("cpi", "待補齊")

    rows = [
        f"<tr><td>台股加權指數（{{TODAY}}）</td><td>{{twii}}</td><td>{{scenario.get('market_assessment', market.get('twii', '待補齊'))}}</td></tr>",
        f"<tr><td>台積電（{{TODAY}}）</td><td>{{tsm}}</td><td>半導體龍頭穩盤</td></tr>",
        f"<tr><td>費半（{{TODAY}}）</td><td>{{sox}}</td><td>高檔回調</td></tr>",
        f"<tr><td>美股（{{TODAY}}）</td><td>{{us}}</td><td>通膨降溫驅動科技領漲</td></tr>",
        f"<tr><td>美國 CPI</td><td>{{cpi}}</td><td>降息預期升溫</td></tr>",
        # 0050 配息：待 MB 確認後由 daily_analysis.json 注入
    ]
    html = html.replace("__MARKET_ROWS__", chr(10).join("          " + r for r in rows))

    # Buffett / CTO 區塊
    buf_bull = buffett.get("bull", "")
    buf_bear = buffett.get("bear", "")
    buf_actions = buffett.get("actions", [])
    scenario_event = scenario.get("event", "—")
    buf_scenario = scenario.get("scenario_summary") or buffett.get("scenario_summary")
    net_worth = tv.get("net_worth", 0)
    snap_dir = BASE / "snapshots"
    yesterday_snap = {{}}
    candidates = sorted(snap_dir.glob("snapshot_*.json"), reverse=True)
    if candidates:
        try:
            yesterday_snap = json.loads(candidates[0].read_text(encoding="utf-8"))
        except Exception:
            yesterday_snap = {{}}
    # Buffett/CTO: 優先從 buffett_cto_report_{{TODAY}}.md 讀取，不手動維護
    report_md = BASE / f"buffett_cto_report_{{TODAY}}.md"
    if report_md.exists():
        try:
            md_text = report_md.read_text(encoding='utf-8')
            buf_lines, cto_lines = [], []
            current = None
            for line in md_text.splitlines():
                s = line.strip()
                if s.startswith('【Buffett'):
                    current = 'buffett'
                    continue
                elif s.startswith('【CTO'):
                    current = 'cto'
                    continue
                elif s.startswith('【'):
                    current = None
                    continue
                if current == 'buffett' and s:
                    buf_lines.append(s)
                elif current == 'cto' and s:
                    cto_lines.append(s)
            buf_content = '<br>'.join(buf_lines)
            cto_content = '<br>'.join(cto_lines)
        except Exception:
            buf_content, cto_content = '', ''
    else:
        buf_content, cto_content = '', ''
    
    # Fallback to old logic if md report missing
    if not buf_content:
        buf_content = f"<strong>🧓 巴菲特式思考</strong><br>• 場景判定：{{buf_scenario or scenario_event}}<br>"
        if buf_bull:
            buf_content += f"• Bull：{{buf_bull}}<br>"
        if buf_bear:
            buf_content += f"• Bear：{{buf_bear}}<br>"
        for a in buf_actions:
            buf_content += f"• {{a}}<br>"
        diff_bullets = _diff_to_buffett_bullets(tv, yesterday_snap)
        if diff_bullets:
            buf_content += "<br><strong>📋  昨日差異帶來的行動啟示</strong><br>"
            for b in diff_bullets:
                buf_content += f"• {{b}}<br>"
        buf_content += "<br><strong>🤝 Buffett 派操作建議</strong><br>"
        buf_content += f"• 淨資產：{{net_worth:,.0f}} TWD<br>"
        buf_content += "• 建議部位：美股權益 ≤ 35%、台股權益 15-20%、高利活存/短債 ≥ 20%、保單/配息穩定型 ≥ 25%<br>"
        buf_content += "• 今日動作：減碼美股權重、增加高利活存與防禦型配息部位；0050 配息縮水後缺口以 00878/00713 補位。<br>"
        buf_content += "• 觸發條件：外資賣超 > 150 億 / 大盤跌 1.5% / 費半跌 2% / 跌破季線+量增 → 啟動減碼；外資買超 > 100 億 + 大盤漲 1% + 費半 +3% → 回補。"

    if not cto_content:
        cto_tech = cto.get("tech_stack", "—")
        cto_risk = cto.get("risk", "—")
        cto_action = cto.get("action", "—")
        cto_signal = scenario.get("cto_signal", "")
        if cto_signal:
            cto_risk = f"今日觸發：{{cto_signal}}；{{cto_risk}}"
        cto_content = f"<strong>🤖 CTO 技術視角</strong><br><strong>tech_stack</strong>：{{cto_tech}}<br><strong>今日最大風險</strong>：{{cto_risk}}<br><strong>建議動作</strong>：{{cto_action}}"

    html = html.replace("__BUFFETT_CONTENT__", buf_content)
    html = html.replace("__CTO_TECH__", cto_content)

    return html
# ==========================================================================
# 4. 產出
# ==========================================================================

def main():
    print(f"[RUN_DAILY] 日期：{TODAY}")

    # 校準
    tv = calibrate_sources()
    print(f"[RUN_DAILY] 真值：月收 {tv['monthly_income']:,} / 月支 {tv['monthly_expense']:,} / 盈餘 +{tv['working_surplus']:,}")

    # 情報：refresh today's hunter intel
    intel_result = mi_mod.ensure_today_intel(force_refresh=True)
    print(f"[INTEL] {intel_result.get('file') or intel_result}")
    intel_text = mi_mod.load_latest_hunter()
    intel_signals = mi_mod.parse_hunter_signals(intel_text)

    # 巴菲特/CTO 動態分析（產出報告，供 render_daily_report 讀取）
    try:
        from buffett_cto_analyzer import run as buffett_run
        buffett_run(send=False)  # 產出報告，Telegram 統一由 deploy 發送
        print("[RUN_DAILY] buffett_cto_analyzer 報告產出完成")
    except Exception as exc:
        print(f"[WARN] buffett_cto_analyzer 失敗：{exc}")

    # 日報
    daily_html = render_daily_report(tv, intel_text=intel_text, intel_signals=intel_signals)
    daily_html = _inject_market_intel(daily_html, tv, intel_signals)
    OUT_DAILY.write_text(daily_html, encoding="utf-8")
    print(f"[RUN_DAILY] 日報產出：{OUT_DAILY}")

    # 靜態儀表板：由 index_template.html 注入動態數據
    if INDEX_TEMPLATE.exists():
        index_html = INDEX_TEMPLATE.read_text(encoding="utf-8")
        try:
            intel_text2 = mi_mod.load_latest_hunter()
            intel_signals2 = mi_mod.parse_hunter_signals(intel_text2)
        except Exception:
            intel_signals2 = {}
        index_html = _inject_dashboard(index_html, tv, intel_signals2)
        OUT_INDEX.write_text(index_html, encoding="utf-8")
        print(f"[RUN_DAILY] 儀表板產出：{OUT_INDEX}")



# ==========================================================================
# 4. 靜態儀表板注入
# ==========================================================================


def _load_latest_hunter() -> str:
    """Load latest hunter intel text."""
    try:
        import daily_intel as mi_mod
        return mi_mod.load_latest_hunter()
    except Exception:
        return ""


def _inject_dashboard(html: str, tv: dict, intel_signals: dict | None = None) -> str:
    """Inject dynamic values into index_template.html placeholders."""
    if not html:
        return html

    # System date
    today = date.today().isoformat()
    html = html.replace("__SYSTEM_DATE__", today)

    # Snapshot placeholders
    def fmt(v):
        if isinstance(v, (int, float)):
            return f"{v:,.0f}"
        return str(v or "—")

    def trend(val, prev):
        if prev is None:
            return "→"
        try:
            return "↑" if val > prev else ("↓" if val < prev else "→")
        except Exception:
            return "→"

    def fmt_pct(v):
        if isinstance(v, (int, float)):
            return f"{v:.2f}"
        return str(v or "—")

    html = html.replace("__INSURANCE_TOTAL__", fmt(tv.get("insurance_total", 0)))
    html = html.replace("__ALLIANZ_AB__", fmt(tv.get("allianz_ab", 0)))
    html = html.replace("__FIRSTJIN__", fmt(tv.get("firstjin", 0)))
    html = html.replace("__TOTAL_MONTHLY__", fmt(tv.get("monthly_dividend", 0)))
    html = html.replace("__WORKING_INCOME__", fmt(tv.get("monthly_income", 0)))
    html = html.replace("__WORKING_SURPLUS__", f"+{fmt(tv.get('working_surplus', 0))}")
    html = html.replace("__RETIREMENT_INCOME__", fmt(tv.get("retirement_income", 0)))
    html = html.replace("__RETIREMENT_SURPLUS__", f"+{fmt(tv.get('retirement_surplus', 0))}")
    # Trend arrows vs yesterday
    snap_dir = BASE / "snapshots"
    yesterday_snap = {}
    candidates = sorted(snap_dir.glob("snapshot_*.json"), reverse=True)
    if candidates:
        try:
            yesterday_snap = json.loads(candidates[0].read_text(encoding="utf-8"))
        except Exception:
            yesterday_snap = {}

    passive_trend = trend(tv.get("rent_monthly_actual", 0) + tv.get("monthly_dividend", 0), yesterday_snap.get("rent_monthly_actual", 0) + yesterday_snap.get("monthly_dividend", 0))
    income_trend = trend(tv.get("monthly_income", 0), yesterday_snap.get("monthly_income", 0))
    expense_trend = trend(tv.get("monthly_expense", 0), yesterday_snap.get("monthly_expense", 0))
    insurance_trend = trend(tv.get("insurance_total", 0), yesterday_snap.get("insurance_current_value", 0))

    html = html.replace("__PASSIVE_INCOME__", fmt(tv.get("rent_monthly_actual", 0) + tv.get("monthly_dividend", 0)) + f" {passive_trend}")
    html = html.replace("__MONTHLY_INCOME_TREND__", income_trend)
    html = html.replace("__MONTHLY_EXPENSE_TREND__", expense_trend)
    html = html.replace("__INSURANCE_TREND__", insurance_trend)
    html = html.replace("__RUNWAY_MONTHS__", fmt(tv.get("runway_months", "—")))
    html = html.replace("__CASH_TOTAL__", fmt(tv.get("cash_total", 0)))

    # Allocation: prefer daily_analysis.json allocation block, fallback to hardcoded known values
    alloc = {}
    try:
        from daily_intel import load_daily_analysis
        da_alloc = load_daily_analysis().get("allocation", {})
        if da_alloc:
            alloc = da_alloc
    except Exception:
        pass
    actual = alloc.get("actual", {})
    target = alloc.get("target", {})

    # Known actual allocation from user memory / last verified values
    known_actual = {
        "tw_equity_pct": 7.2,
        "us_equity_pct": 46.1,
        "defensive_pct": 18.5,
        "bond_pct": 33.8,
    }
    # Merge: actual data file overrides hardcoded fallback
    tw_eq = actual.get("tw_equity_pct", known_actual.get("tw_equity_pct", 0))
    us_eq = actual.get("us_equity_pct", known_actual.get("us_equity_pct", 0))
    def_ = actual.get("defensive_pct", known_actual.get("defensive_pct", 0))
    bond = actual.get("bond_pct", known_actual.get("bond_pct", 0))

    tw_target = target.get("tw_equity_pct", 40.0)
    us_target = target.get("us_equity_pct", 30.0)
    def_target = target.get("defensive_pct", 30.0)
    bond_target = target.get("bond_pct", 25.0)

    tw_gap = tw_eq - tw_target
    us_gap = us_eq - us_target
    def_gap = def_ - def_target
    bond_gap = bond - bond_target

    html = html.replace("__TW_EQ_PCT__", fmt_pct(tw_eq))
    html = html.replace("__TW_EQ_TARGET__", fmt_pct(tw_target))
    html = html.replace("__TW_EQ_GAP__", fmt_pct(tw_gap))
    html = html.replace("__TW_EQ_VALUE__", fmt(tv.get("tw_eq_value", 0)))
    html = html.replace("__US_EQ_PCT__", fmt_pct(us_eq))
    html = html.replace("__US_EQ_TARGET__", fmt_pct(us_target))
    html = html.replace("__US_EQ_GAP__", fmt_pct(us_gap))
    html = html.replace("__US_EQ_VALUE__", fmt(tv.get("us_eq_value", 0)))
    html = html.replace("__DEF_PCT__", fmt_pct(def_))
    html = html.replace("__DEF_TARGET__", fmt_pct(def_target))
    html = html.replace("__DEF_GAP__", fmt_pct(def_gap))
    html = html.replace("__DEF_VALUE__", fmt(tv.get("def_value", 0)))
    html = html.replace("__BOND_PCT__", fmt_pct(bond))
    html = html.replace("__BOND_TARGET__", fmt_pct(bond_target))
    html = html.replace("__BOND_GAP__", fmt_pct(bond_gap))
    html = html.replace("__BOND_VALUE__", fmt(tv.get("bond_value", 0)))

    # Market / Hunter rows from daily_analysis.json / intel
    try:
        from daily_intel import load_daily_analysis
        da = load_daily_analysis()
    except Exception:
        da = {}

    market = da.get("market", {})
    market_rows = []
    market_map = [
        ("twii", "台股加權"),
        ("tsm", "台積電"),
        ("sox", "費半"),
        ("us", "美股"),
        ("cpi", "美國 CPI"),
    ]
    for key, label in market_map:
        val = market.get(key)
        if val and val != "—":
            market_rows.append(f'<li>• <span class="text-white">{label}</span> — {val}</li>')

    # Parse foreign sell from hunter intel
    try:
        hunter_for_foreign = intel_text or ""
        foreign_m = re.search(r"外資[賣買]超\s*([0-9,.]+)\s*億", hunter_for_foreign)
        if foreign_m:
            fval = foreign_m.group(1).replace(",", "")
            direction = "賣超" if "賣超" in hunter_for_foreign[max(0, foreign_m.start()-5):foreign_m.start()+10] else "買超"
            market_rows.append(f'<li>• <span class="text-white">外資{direction}</span> — {foreign_m.group(1)} 億元</li>')
    except Exception:
        pass

    if not market_rows:
        market_rows = ["<li>本日情報待補齊</li>"]
    html = html.replace("__MARKET_ROWS__", chr(10).join("                        " + r for r in market_rows))

    hunter_date = "盤前"
    hunter_rows = []
    if intel_signals:
        sell_signals = intel_signals.get("sell_signals", [])
        buy_signals = intel_signals.get("buy_signals", [])
        for s in sell_signals[:5]:
            hunter_rows.append(f"<li>P1 risk：{s}</li>")
        for b in buy_signals[:5]:
            hunter_rows.append(f"<li>P1 buy：{b}</li>")
        hunter_rows.append("<li>結論：以 hunter_logs/intel_*.txt 為準。</li>")
    if not hunter_rows:
        hunter_rows = ["<li>本日 Hunter 情報待補齊</li>"]
    html = html.replace("__HUNTER_DATE__", f"{today} {hunter_date}")
    html = html.replace("__HUNTER_ROWS__", chr(10).join("                        " + r for r in hunter_rows))

    # 0050 dividend placeholders
    html = html.replace("__DIVIDEND_0050__", "待 MB 確認")
    html = html.replace("__EX_DATE_0050__", "待確認")

    # Fund placeholders for daily report (same logic as dashboard)
    try:
        from daily_intel import load_daily_analysis
        da2 = load_daily_analysis()
        funds2 = da2.get("funds", {})
    except Exception:
        funds2 = {}
    if not funds2:
        funds2 = {
            "allianz_return": 16.41,
            "allianz_monthly": 55_451,
            "allianz_cum": 1_613_246,
            "allianz_cost": 8_000_000,
            "firstjin_monthly": 13_593,
            "firstjin_cum": 63_985,
            "firstjin_cost": 2_000_000,
        }
    def fmt(v):
        if isinstance(v, (int, float)):
            return f"{v:,.0f}"
        return str(v or "—")
    def trend(val, prev):
        if prev is None:
            return "→"
        try:
            return "↑" if val > prev else ("↓" if val < prev else "→")
        except Exception:
            return "→"

    def fmt_pct(v):
        if isinstance(v, (int, float)):
            return f"{v:.2f}"
        return str(v or "—")
    html = html.replace("__ALLIANZ_RETURN__", fmt_pct(funds2.get("allianz_return", 16.41)))
    html = html.replace("__ALLIANZ_MONTHLY__", fmt(funds2.get("allianz_monthly", 55_451)))
    html = html.replace("__ALLIANZ_CUM__", fmt(funds2.get("allianz_cum", 1_613_246)))
    html = html.replace("__ALLIANZ_COST__", fmt(funds2.get("allianz_cost", 8_000_000)))
    html = html.replace("__FIRSTJIN_MONTHLY__", fmt(funds2.get("firstjin_monthly", 13_593)))
    html = html.replace("__FIRSTJIN_CUM__", fmt(funds2.get("firstjin_cum", 63_985)))
    html = html.replace("__FIRSTJIN_COST__", fmt(funds2.get("firstjin_cost", 2_000_000)))

    # Fund breakdown: prefer daily_analysis.json, fallback to known true values
    funds = da.get("funds", {})
    if not funds:
        funds = {
            "allianz_return": 16.41,
            "allianz_monthly": 55_451,
            "allianz_cum": 1_613_246,
            "allianz_cost": 8_000_000,
            "firstjin_monthly": 13_593,
            "firstjin_cum": 63_985,
            "firstjin_cost": 2_000_000,
        }
    def fmt(v):
        if isinstance(v, (int, float)):
            return f"{v:,.0f}"
        return str(v or "—")

    def trend(val, prev):
        if prev is None:
            return "→"
        try:
            return "↑" if val > prev else ("↓" if val < prev else "→")
        except Exception:
            return "→"

    def fmt_pct(v):
        if isinstance(v, (int, float)):
            return f"{v:.2f}"
        return str(v or "—")
    html = html.replace("__ALLIANZ_RETURN__", fmt_pct(funds.get("allianz_return", 0)))
    html = html.replace("__ALLIANZ_MONTHLY__", fmt(funds.get("allianz_monthly", 0)))
    html = html.replace("__ALLIANZ_CUM__", fmt(funds.get("allianz_cum", 0)))
    html = html.replace("__ALLIANZ_COST__", fmt(funds.get("allianz_cost", 8_000_000)))
    html = html.replace("__FIRSTJIN_MONTHLY__", fmt(funds.get("firstjin_monthly", 0)))
    html = html.replace("__FIRSTJIN_CUM__", fmt(funds.get("firstjin_cum", 0)))
    html = html.replace("__FIRSTJIN_COST__", fmt(funds.get("firstjin_cost", 2_000_000)))
    # firstjin value uses same as firstjin current value
    html = html.replace("__FIRSTJIN_VALUE__", fmt(tv.get("firstjin", 0) or funds.get("firstjin_value", 1_994_698)))
    # allianz value uses snapshot
    html = html.replace("__ALLIANZ_AB__", fmt(tv.get("allianz_ab", 0) or funds.get("allianz_value", 7_881_584)))
    # total monthly = sum of fund monthly + snapshot fallback
    calc_total = (funds.get("allianz_monthly", 0) or 0) + (funds.get("firstjin_monthly", 0) or 0)
    html = html.replace("__TOTAL_MONTHLY__", fmt(calc_total or tv.get("monthly_dividend", 69_044)))

    return html


    print("\n[DONE] 產出完成。")
    print(f"  日報：{OUT_DAILY}")
if __name__ == "__main__":
    main()