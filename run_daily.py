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
from logging_config import get_logger
logger = get_logger("run_daily")
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
    s_insurance = snap.get("allianz_combined", 0) + snap.get("firstjin_fl65_current_value", 0)
    s_allianz = snap.get("allianz_ab_current_value") or snap.get("allianz_ab")
    s_firstjin = snap.get("firstjin_current_value") or snap.get("firstjin")
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
    # 真值錨定：本月保單配息（從 snapshot allianz_ab_monthly + firstjin_monthly 動態計算）
    monthly_dividend = snap.get("monthly_dividend")
    if monthly_dividend is None:
        monthly_dividend = (snap.get("allianz_ab_monthly", 0) or 0) + (snap.get("firstjin_monthly", 0) or 0)

    # 從 monthly_dividend_breakdown 取得證券、基金配息及下次除息資訊
    dividend_breakdown = snap.get("monthly_dividend_breakdown", {})
    sec_dividend_monthly = dividend_breakdown.get("etf", 0)
    fund_dividend_monthly = dividend_breakdown.get("fund", 0)
    
    # ETF 除息時程表（HTML）
    _etf_div = snap.get("etf_dividend_schedule", {})
    _etf_table = "<table style='width:100%;font-size:14px;border-collapse:collapse;margin-top:8px'><thead><tr style='background:#f0f0f5'><th>ETF</th><th>狀態</th><th>除息日</th><th>配息</th><th>發放日</th></tr></thead><tbody>"
    for status_label, status_key in [("✅ 已除息","已除息"), ("🔜 下一梯次","下一梯次")]:
        items = _etf_div.get(status_key, {})
        for ticker, info in items.items():
            _ex = info.get("除息日") or info.get("預計除息", "")
            # 自動加星期
            try:
                _ex_dt = datetime.strptime(f"2026/{_ex.replace('月初','')}", "%Y/%m/%d") if '/' in _ex else None
                _ex = f"{_ex}({['一','二','三','四','五','六','日'][_ex_dt.weekday()]})" if _ex_dt else _ex
            except: pass
            _dv = f"{info.get('配息','')}元" if info.get('配息') else "-"
            _pay = info.get("發放日", "")
            try:
                _pay_dt = datetime.strptime(f"2026/{_pay}", "%Y/%m/%d") if '/' in _pay else None
                _pay = f"{_pay}({['一','二','三','四','五','六','日'][_pay_dt.weekday()]})" if _pay_dt else _pay
            except: pass
            _etf_table += f"<tr><td>{ticker}</td><td>{status_label}</td><td>{_ex}</td><td>{_dv}</td><td>{_pay}</td></tr>"
    _etf_table += "</tbody></table>"
    
    # 下次除息資訊（從 relay_calendar 讀取）
    try:
        _rc = open(BASE / "relay_calendar.md", encoding="utf-8").read()
        _matches = re.findall(r'\|\s*([^|]+?)\s*\|\s*(\d+/\d+)\(', _rc)
        _filtered = [(n.strip(), d) for n, d in _matches if n.strip() not in ('基金', '基金名稱')]
        if _filtered:
            next_ex_dividend_list = "、".join([f"{n}（{d}）" for n, d in _filtered[:5]])
    except:
        pass


    total_assets = snap.get("total_assets")
    total_liabilities = snap.get("total_liabilities")
    net_worth = snap.get("net_worth")
    if net_worth is None and total_assets is not None and total_liabilities is not None:
        net_worth = total_assets - total_liabilities
    return {
        "date": TODAY,
        "sec_dividend_monthly": sec_dividend_monthly,
        "fund_dividend_monthly": fund_dividend_monthly,
        "next_ex_dividend_list": next_ex_dividend_list,
        "etf_div_table": _etf_table,
        "monthly_income": s_income,
        "monthly_expense": s_expense,
        "working_surplus": s_work_surplus,
        "retirement_surplus": s_retire_surplus,
        "insurance_total": s_insurance,
        "allianz_ab": s_allianz,
        "firstjin": s_firstjin,
        "firstjin_label": snap.get("insurance_label_b", "第一金FL65"),
        "rent_monthly": s_rent,
        "securities_total": s_securities,
        "monthly_dividend": monthly_dividend,
        "insurance_dividend": dividend_breakdown.get("allianz", 0) + dividend_breakdown.get("firstjin", 0),
        "allianz_dividend": snap.get("allianz_ab_monthly", 73_167),
        "firstjin_dividend": snap.get("firstjin_monthly", 22_949),
        "relay_stations": snap.get("relay_stations", {}),
        "cc_4cards": ["玉山UNI", "台新Richart", "永豐SPORT", "台北富邦momo/J"],
        "loans_2mortgage": ["洲際W房貸", "理財型利息（房貸已清償）"],
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "bonds_cash": snap.get("penetration", {}).get("actual_twd", {}).get("債券及安全現金", 9_697_196),
        "insurance_current_value": s_insurance,
        "funds": snap.get("fund_market_value", snap.get("funds_total", 0)) or 0,
        "cash_total": snap.get("cash_total", 3_614_169),
        "rent_breakdown": snap.get("rent_breakdown", {}),
        # Liabilities from snapshot.json
        "mortgage_yy": snap.get("mortgage_yy", 0),
        "mortgage_yydu": snap.get("mortgage_yydu", 0),
        "mortgage_xz": snap.get("mortgage_xz", 0),
        "mortgage_balance": snap.get("mortgage_balance", 0),
        "financial_mortgage": snap.get("financial_mortgage", 0),
        "policy_loan": snap.get("policy_loan", 0),
        "pledge_loan": snap.get("pledge_loan", 0),
        "cc_liability": snap.get("cc_liability", 0),
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


def _fmt_rent_status(tv):
    """動態產生房租金流文字"""
    rb = tv.get("rent_breakdown", {})
    if not rb:
        return "大義街1樓24,000+洲際W33,000+大義街23樓21,000+管理費2,100 ✅"
    parts = []
    label_map = {"大義街店面":"大義街1樓", "大義街二三樓":"大義街23樓"}
    for k, v in rb.items():
        label = label_map.get(k, k)
        parts.append(f"{label}{v:,}")
    return "已全數實收 " + "+".join(parts) + " ✅ "


def _generate_schedule_html(events: list) -> str:
    """從 calendar_sync 事件生成排程 HTML 表格行"""
    from datetime import date
    today = date.today().isoformat()
    rows = []
    for ev in events:
        start = ev.get("start", "")
        if start < today:
            continue
        summary = ev.get("summary", "")
        amount = ev.get("amount", "")
        status = ev.get("status", "")
        rows.append(f'<tr><td>{start}</td><td>{summary}</td><td class="num">{amount}</td><td>{status}</td></tr>')
    return "\n".join(rows[:12])


def render_daily_report(tv: dict, intel_text: str = "", intel_signals: dict | None = None, market_intel_text: str = "", mb_cc_rows: str = "", llm_emergency_analysis: str = "", schedule_rows_html: str = "", p0_tasks_html: str = "", cio_content_html: str = "") -> str:
    _dbs_note_ph = "{_dbs_note}"  # placeholder for dynamic DBS note
    """產出五大章節日報 HTML。"""
    allianz = tv["allianz_ab"] or 7_634_046
    firstjin = tv["firstjin"] or 1_952_366
    firstjin_label = tv.get("firstjin_label", "第一金FL65")
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = tv.get("monthly_dividend", 107_116)
    allianz_dividend = tv.get("allianz_dividend", 73_167)
    firstjin_dividend = tv.get("firstjin_dividend", 22_949)
    # 總資產（含不動產）動態計算 — 不再硬編碼
    try:
        _re_val = float(json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("real_estate_value", 34_017_063))
    except Exception:
        _re_val = 34_017_063
    _total_with_re = int(tv.get("total_assets", 0) or 0) + int(_re_val)
    _total_liab = int(tv.get("total_liabilities", 0) or 0)
    _net_with_re = _total_with_re - _total_liab
    _liab_ratio = (_total_liab / _total_with_re * 100) if _total_with_re else 0

    loans_rows_html = ""
    if tv['mortgage_yy'] > 0:
        loans_rows_html += f"""          <tr><td>永豐銀行</td><td>永豐房貸 (YY)</td><td>—</td><td class="num">{tv['mortgage_yy']:,}</td><td>—</td></tr>\n"""
    if tv['mortgage_yydu'] > 0:
        loans_rows_html += f"""          <tr><td>永豐銀行</td><td>永豐房貸 (YYDU)</td><td>—</td><td class="num">{tv['mortgage_yydu']:,}</td><td>—</td></tr>\n"""
    if tv['mortgage_xz'] > 0:
        loans_rows_html += f"""          <tr><td>永豐銀行</td><td>永豐房貸 (XZ)</td><td>—</td><td class="num">{tv['mortgage_xz']:,}</td><td>—</td></tr>\n"""
    if tv['financial_mortgage'] > 0:
        loans_rows_html += f"""          <tr><td>星展銀行</td><td>理財型房貸</td><td>—</td><td class="num">{tv['financial_mortgage']:,}</td><td>—</td></tr>\n"""
    if tv['policy_loan'] > 0:
        loans_rows_html += f"""          <tr><td>—</td><td>保單借貸</td><td>—</td><td class="num">{tv['policy_loan']:,}</td><td>—</td></tr>\n"""
    if tv['pledge_loan'] > 0:
        loans_rows_html += f"""          <tr><td>—</td><td>證券質押</td><td>—</td><td class="num">{tv['pledge_loan']:,}</td><td>—</td></tr>\n"""

    # 從 relay_calendar.md 取得 T+4 轉換截止日 & 完整行事曆
    _rc_text = ""
    _rc_data = {}  # {月份: {基金: {除息日, T+4}}}
    try:
        _rc_text = open(BASE / "relay_calendar.md", encoding="utf-8").read()
        # 解析行事曆
        _cur_month = None
        for _line in _rc_text.splitlines():
            _mh = re.match(r'##\s*(\d+)月', _line)
            if _mh:
                _cur_month = _mh.group(1)
                _rc_data[_cur_month] = {}
                continue
            if _cur_month and '|' in _line and not _line.startswith('| 基金') and not _line.startswith('|---'):
                _cells = [c.strip() for c in _line.split('|') if c.strip()]
                if len(_cells) >= 3:
                    _name = _cells[0].strip()
                    _ex = re.sub(r'\([^)]*\)', '', _cells[1]).strip()
                    _t4 = re.sub(r'\([^)]*\)', '', _cells[2]).strip()
                    _rc_data[_cur_month][_name] = {'除息日': _ex, 'T+4': _t4}
    except:
        pass
    # 基金順序
    _rc_funds = ['摩根JPM', '安聯收益成長', 'M&G入息', '安聯AI收益', '貝萊德A10']
    _rc_months = ['8', '9', '10', '11', '12']
    # 動態生成行事曆表格
    _rc_rows = ""
    for _f in _rc_funds:
        _rc_rows += f"          <tr><td>{_f}</td>"
        for _m in _rc_months:
            _d = _rc_data.get(_m, {}).get(_f, {})
            _ex = _d.get('除息日', '')
            _t4 = _d.get('T+4', '')
            if _ex and _t4:
                _rc_rows += f"<td>{_ex}→<strong>{_t4}</strong></td>"
            else:
                _rc_rows += "<td>—</td>"
        _rc_rows += "</tr>"
    _relay_calendar_html = f"""    <h3>2026 保單基金配息接力行事曆</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead><tr><th>基金</th><th>8月</th><th>9月</th><th>10月</th><th>11月</th><th>12月</th></tr></thead>
        <tbody>
{_rc_rows}
        </tbody>
      </table>
    </div>
    <p class="text-sm" style="color:#6e6e73;margin-top:6px">除息日→<strong>T+4轉換截止</strong>。T+4 = 除息日前4工作日。</p>"""
    _rc_rows = ""
    # 從 snapshot relay_stations 動態生成接力站表
    _stations = tv.get("relay_stations", {})
    _station_icons = {'已配息': '✅', '轉換完成': '✅', '轉換中': '🔄', '待執行': '⏳', '等待': '⏸️'}
    _station_rows = ""
    for _sn, _sd in _stations.items():
        _st = _sd.get("狀態", "")
        _icon = ""
        for _k, _v in _station_icons.items():
            if _k in _st:
                _icon = _v
                break
        _t4 = _sd.get("轉換截止", "—")
        _deadline = f"⚠️ {_t4}" if "⚠️" in str(_t4) or any(x in str(_t4) for x in ["7/23","7/24"]) else _t4
        _station_rows += f"""          <tr><td>{_sn}</td><td>{_sd.get("流向","")}</td><td>{_sd.get("基準日","")}</td><td>{_deadline}</td><td>{_sd.get("預估入帳","")}</td><td>{_icon} {_st}</td></tr>"""
    relay_table = f"""<div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>站別</th><th>流向</th><th>基準日</th><th>轉換截止</th><th>預估入帳</th><th>狀態</th></tr>
        </thead>
        <tbody>
{_station_rows}
        </tbody>
      </table>
    </div>"""

    # CIO 觀點（外部傳入或靜態備援）
    cio_content = []
    cio_content.append(f'<p><strong>🧑‍💻 CIO 觀點</strong></p>')
    if cio_content_html:
        cio_content.append(cio_content_html)
    else:
        # 靜態備援：從 daily_analysis.json 取市場訊號做基本判斷
        try:
            _cio_da = json.loads((BASE / "daily_analysis.json").read_text(encoding="utf-8"))
            _cio_mkt = _cio_da.get("market", {})
            _cio_sig = _cio_da.get("signals", {})
            _cio_twii = _cio_mkt.get("twii", "")
            _cio_tsm = _cio_mkt.get("tsm", "")
            _cio_buy = _cio_sig.get("buy_signals", [])
            _cio_sell = _cio_sig.get("sell_signals", [])
            _cio_sentiment = "⚠️ 謹慎" if len(_cio_sell) > len(_cio_buy) else "✅ 中性偏多" if len(_cio_buy) > 0 else "➡️ 中性"
            cio_content.append(f'<span style="display:block">• 市場情緒：{_cio_sentiment}（買訊{len(_cio_buy)} / 賣訊{len(_cio_sell)}）</span>')
            if _cio_twii:
                cio_content.append(f'<span style="display:block">• 加權指數：{_cio_twii}</span>')
            if _cio_tsm:
                cio_content.append(f'<span style="display:block">• 台積電：{_cio_tsm}</span>')
            _cio_pen_tw = tv.get("penetration", {}).get("actual_pct", {}).get("台股市值型成長", 0)
            _cio_pen_us = tv.get("penetration", {}).get("actual_pct", {}).get("美股市值型成長", 0)
            _cio_pen_def = tv.get("penetration", {}).get("actual_pct", {}).get("防守型配息", 0)
            cio_content.append(f'<span style="display:block">• 配置：台股{_cio_pen_tw:.1f}% / 美股{_cio_pen_us:.1f}% / 防守{_cio_pen_def:.1f}%</span>')
            if _cio_sell:
                _cio_warn_str = "、".join(_cio_sell[:2])
                cio_content.append(f'<span style="display:block">• ⚠️ 警訊：{_cio_warn_str}</span>')
        except Exception:
            cio_content.append(f'<span style="display:block">• 本日市場無重大異常。</span>')
            cio_content.append(f'<span style="display:block">• 資產配置持續檢視，注意防禦型補碼時機。</span>')
        cio_content.append(f'<span style="display:block">• 流動性管理穩定，補庫警示已處理。</span>')
    cio_content_html = '\n'.join(cio_content)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>龍九控股日報 {TODAY}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans TC', sans-serif;
    color: #1d1d1f;
    background: #f5f5f7;
    margin: 0;
    padding: 16px;
    line-height: 1.8;
    font-size: 17px;
    -webkit-text-size-adjust: 100%;
  }}
  .page {{ max-width: 900px; margin: 0 auto; }}
  .card {{
    background: #fff;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  h1 {{ font-size: 22px; font-weight: 900; margin: 0 0 6px; }}
  h2 {{ font-size: 18px; font-weight: 800; margin: 14px 0 8px; }}
  h3 {{ font-size: 16px; font-weight: 800; margin: 10px 0 6px; }}
  .label {{ font-size: 12px; color: #6e6e73; margin-bottom: 6px; }}
  .text-lead {{ color: #3a3a3c; margin: 6px 0; }}
  .table-wrap {{ overflow-x: auto; margin: 8px 0; -webkit-overflow-scrolling: touch; }}
  table {{
    width: 100%;
    min-width: 360px;
    border-collapse: collapse;
    background: #fff;
    border: 1px solid #e5e5ea;
    border-radius: 10px;
    overflow: hidden;
    font-size: 16px;
  }}
  thead th {{
    background: #f2f2f7;
    font-weight: 800;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid #e5e5ea;
    font-size: 15px;
  }}
  tbody td {{
    padding: 10px 12px;
    border-bottom: 1px solid #f2f2f7;
    vertical-align: top;
  }}
  tbody tr:nth-child(even) td {{ background: #fafafa; }}
  tbody tr:hover td {{ background: #f0f8ff; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .callout {{
    border-radius: 10px;
    padding: 12px 14px;
    margin: 14px 0; /* Adjusted margin */
    border-left: 4px solid;
    font-size: 16px; /* Added font-size */
    line-height: 1.8; /* Added line-height */
  }}
  .callout h3 {{ text-decoration: underline; }} /* Added underline for h3 inside callout */
  .callout strong {{ color:#c2410c; text-decoration: underline; }} /* Added orange color and underline for strong inside callout */
  .callout-bull {{ background:#f0fff4; border-color:#22c55e; }}
  .callout-bear {{ background:#fff5f5; border-color:#ef4444; }}
  .callout-warn {{ background:#fffbeb; border-color:#f59e0b; }}
  .callout-warn span {{ display:block; margin:3px 0; padding-left:4px; border-left:2px solid rgba(245,158,11,0.2); }}
  .callout-info {{ background:#eff6ff; border-color:#3b82f6; }}

  /* Mobile table style: bordered with background fill */
  @media (max-width: 640px) {{
    body {{ font-size: 15px; padding: 10px; }}
    table {{ font-size: 13px; }}
    th, td {{ padding: 6px 6px !important; }}
    th:nth-child(2), td:nth-child(2) {{ max-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    #market-intel-block table th:nth-child(2),
    #market-intel-block table td:nth-child(2) {{
      display: none !important;
    }}
  }}
  table.mobile-bordered {{
    border: 1px solid #d1d5db;
    border-radius: 8px;
    overflow: hidden;
  }}
  table.mobile-bordered th {{
    background: #f2f2f7 !important;
    border: 1px solid #e5e5ea;
    color: #1d1d1f;
  }}
  table.mobile-bordered td {{
    background: #ffffff !important;
    border: 1px solid #f2f2f7;
  }}
  table.mobile-bordered tr:nth-child(even) td {{ background: #f9fafb !important; }}
  table.mobile-bordered .num {{ background: transparent !important; }}
</style>
</head>
<body>
<div class="page">

  <!-- 1/5 財富生命線 -->
  <div class="card">
    <h1>1/5｜財富生命線 Wealth Baseline</h1>
    <div class="label">資產負債快照</div>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>項目</th><th>內容</th><th>影響</th></tr>
        </thead>
        <tbody>
          <tr><td>總資產</td><td>{_total_with_re:,} TWD</td><td>淨資產 {_net_with_re:,}；負債率 {_liab_ratio:.1f}%</td></tr>
          <tr><td>總負債</td><td>{tv['total_liabilities']:,} TWD</td><td>總負債合計（含房貸、保單借貸、質押）</td></tr>
          <tr><td>本月領息</td><td>{monthly_dividend:,} TWD</td><td>保單 {tv['insurance_dividend']:,} + ETF {tv['sec_dividend_monthly']:,} + 基金 {tv['fund_dividend_monthly']:,}</td></tr>
          <tr><td>被動月收</td><td>{monthly_dividend + tv['rent_monthly']:,} TWD</td><td>配息 {monthly_dividend:,} + 房租 {tv['rent_monthly']:,}</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 2/5 戰略異常看板 -->
  <div class="card">

  <div class="card">
    <h2>2/5｜資產結構 Asset Penetration</h2>
    <div class="label">對照家族辦公室戰略目標模型（不動產不計入）</div>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead><tr><th>戰略類別</th><th class="num">金額 TWD</th><th class="num">佔比</th><th class="num">目標</th><th>缺口</th></tr></thead>
        <tbody>
          <tr><td>🇹🇼 台股市值型</td><td class="num">__DR_TW_V__ TWD</td><td class="num">__DR_TW_PCT__</td><td class="num">__DR_TW_TGT__</td><td>__DR_TW_GAP__</td></tr>
          <tr><td>🇺🇸 美股市值型</td><td class="num">__DR_US_V__ TWD</td><td class="num">__DR_US_PCT__</td><td class="num">__DR_US_TGT__</td><td>__DR_US_GAP__</td></tr>
          <tr><td>🛡️ 防守型配息</td><td class="num">__DR_DEF_V__ TWD</td><td class="num">__DR_DEF_PCT__</td><td class="num">__DR_DEF_TGT__</td><td>__DR_DEF_GAP__</td></tr>
          <tr><td>💵 債券</td><td class="num">__DR_BOND_V__ TWD</td><td class="num">__DR_BOND_PCT__</td><td class="num">__DR_BOND_TGT__</td><td>__DR_BOND_GAP__</td></tr>
          <tr><td>💵 安全現金</td><td class="num">__DR_CASH_V__ TWD</td><td class="num">__DR_CASH_PCT__</td><td class="num">__DR_CASH_TGT__</td><td>__DR_CASH_GAP__</td></tr>
        </tbody>
      </table>
    </div>
    <p class="text-sm" style="color:#6e6e73;margin-top:8px">穿透分母：台股+美股+防守+債券（不計入不動產）；管理費~1.5%，偏高於配息收益率。</p>
  </div>

  <div class="card" style="margin-top:4px;padding:10px 14px;background:#f0f4ff;">
  </div>

  <!-- 市場情報 -->
  <div class="card">
    <h2>2/5｜市場情報 Market Intel</h2>
    <div class="label">獵人情報 + 市場搜尋 + 持倉關聯</div>
    <div id="market-intel-block">{market_intel_text}</div>
  </div>

  <!-- 戰略異常看板 -->
  <div class="card">
    <h2>3/5｜戰略異常看板 Strategic Risk Hub</h2>
    <div class="label">四大戰略重點</div>

    <h3>保單維運</h3>
    <p class="text-lead">保單現值 <strong>{insurance_total:,} TWD</strong>（安聯 A+B {allianz:,} + {firstjin_label} {firstjin:,}），本月配息合計 <strong>{monthly_dividend:,} TWD</strong>。落實利潤再投資 SOP，於 T+4 最晚轉換申請日才執行 relay 轉換。</p>

    <h3>證券曝險</h3>
    <p class="text-lead">證券總市值 <strong>{tv['securities_total']:,} TWD</strong>（{tv['holdings_count']}檔）。本月已收配息：{tv['sec_dividend_monthly']:,} TWD。前三大：{tv['holdings_top3'][0][0]} {tv['holdings_top3'][0][1]:.1f}%、{tv['holdings_top3'][1][0]} {tv['holdings_top3'][1][1]:.1f}%、{tv['holdings_top3'][2][0]} {tv['holdings_top3'][2][1]:.1f}%。0056 凍結質押中，短期無法加碼。</p>
    {tv['etf_div_table']}

    <h3>房租金流</h3>
    <p class="text-lead">房租月收 <strong>{tv['rent_monthly']:,} TWD</strong>，覆蓋月支出 55%。{_fmt_rent_status(tv)}{_dbs_note_ph}</p>

    <h3>鉅亨基金部位</h3>
    <p class="text-lead">基金總市值 <strong>{tv.get('funds',0):,} TWD</strong>。本月已收配息：{tv['fund_dividend_monthly']:,} TWD。路博邁5G累積 238,955 / 0050不配息 108,047 / 統一奔騰 86,931 / 台新半導體(JPY) 177,662 / 台中銀優息 47,699 / 路博邁5G月配 88,939 / 0050B配息 46,924。淨值反彈 +29,166（+3.81%），今日鉅亨帳戶總覽 {tv.get('funds',0):,}。</p>
  </div>

  <!-- 3/5 保單接力引擎 -->
  <div class="card">
    <h2>3/5｜保單接力引擎 Insurance Relay Engine</h2>
    <div class="label">三站轉換時序監控</div>
    <p class="text-lead"><strong>本月配息合計：{monthly_dividend:,} TWD</strong></p>
    {relay_table}
    {_relay_calendar_html}

    <h3>保單成分穿透</h3>
    <h3>安聯 A+B 合併帳戶（成本 8,000,000 / 現值 {allianz:,}）</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>指標</th><th class="num">數值 TWD</th><th>備註</th></tr>
        </thead>
        <tbody>
          <tr><td>現值</td><td class="num">{allianz:,}</td><td>最新 market value</td></tr>
          <tr><td>本月配息</td><td class="num">{allianz_dividend:,}</td><td>當月配息</td></tr>
        </tbody>
      </table>
    </div>

    <h3>{firstjin_label}（成本 2,000,000 / 現值 {firstjin:,}）</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>指標</th><th class="num">數值 TWD</th><th>備註</th></tr>
        </thead>
        <tbody>
          <tr><td>現值</td><td class="num">{firstjin:,}</td><td>配息前</td></tr>
          <tr><td>本月配息</td><td class="num">{firstjin_dividend:,}</td><td>上月底配息</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 4/5 流動性調度站 -->
  <div class="card">
    <h2>4/5｜流動性調度站 Liquidity Hub</h2>
    <div class="label">5,000 元過濾器 + 補庫預警</div>

    <h3>信用卡四大主力（列管帳戶）</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>銀行</th><th>卡片</th><th>繳款日</th><th class="num">近期應付 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
{mb_cc_rows}
        </tbody>
      </table>
    </div>

    <h3>房貸帳戶（列管帳戶）</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>銀行</th><th>貸款名稱</th><th>扣款日</th><th class="num">金額 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
{loans_rows_html}
        </tbody>
      </table>
    </div>

    <div class="callout callout-ok">
      <strong>✅ 星展資金充足</strong><br>
      星展戶頭餘額 17,000 TWD，8/1 扣理財型利息 ~10,000，餘裕充足。一般房貸已清償 ✅
    </div>
  </div>

  <!-- 5/5 龍九決戰日檢核 -->
  <div class="card">
    <h2>5/5｜龍九決戰日檢核 Tactical Ops Checklist</h2>
    <div class="label">P0 任務置頂 + 行事曆維度聚合</div>

    <h3>🚨 P0 任務</h3>
    <div class="callout callout-warn">
      <ul>
        {p0_tasks_html}
      </ul>
    </div>

    <h3>本週行程 + 繳款 / 配息排程</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>日期</th><th>項目</th><th class="num">金額 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
{schedule_rows_html}
        </tbody>
      </table>
    </div>
  </div>

  <!-- 投資決策框架 -->
  <div class="card">
    <h2>5/5｜投資決策框架 Investment Decision Framework</h2>
    <div class="label">決策核心 + 緊急應變分析</div>

    <div id="emergency-llm-analysis" style="background:#fffbeb;border-radius:8px;padding:12px;margin-top:8px;font-size:13px;line-height:1.6;white-space:pre-wrap;overflow-x:auto;color:#1d1d1f;">
      <!-- LLM 緊急應變分析區塊 -->
            {llm_emergency_analysis}
    </div>

    <!-- 巴菲特視角建議 (Fallback 或輔助) -->
    <div class="callout callout-bull">
      <h3>巴菲特視角建議</h3>
      __BUFFETT_CONTENT__
    </div>

    <!-- CTO 技術視角 (Fallback 或輔助) -->
    <div class="callout callout-bear">
      <h3>CTO 技術視角</h3>
      __CTO_TECH__
    </div>

    <!-- CIO 審查 / 觀點 -->
        <div class="callout callout-info">
          {cio_content_html}
        </div>
        <!-- END CIO -->
  </div>

</div>
<div class="card">
  <h2>📊 資產差異分析 Asset Diff</h2>
  <p class="text-lead">
    <a href="https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html" target="_blank">
      開啟今日差異分析 → asset_diff_{TODAY}.html
    </a>
  </p>
  <div class="text-sm">包含：6/5 資產變化對照、趨勢圖表、巴菲特分析、Gemini 風控意見</div>
</div>
</body>
</html>"""

    # 動態 DBS note
    _dbs_cash = tv.get("cash_total", 0)
    _dbs_str = f"星展餘額 {_dbs_cash:,} TWD，扣理財型利息 ~10,000，{'餘裕充足 ✅' if _dbs_cash > 30000 else '⚠️ 需補資金'}"
    html = html.replace("{_dbs_note}", _dbs_str)
    return html
    return html


# ==========================================================================
# 3. 差異說明
# ==========================================================================



def _build_market_rows(signals: dict, tv: dict) -> str:
    sell = signals.get("sell_signals", [])
    rows = [
        f"<tr><td>台股加權指數（{TODAY}）</td><td>待補齊；外資單日賣超 —</td><td>高檔震盪</td></tr>",
        f"<tr><td>台積電（{TODAY}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>費半（{TODAY}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>美股（{TODAY}）</td><td>待補齊</td><td>觀察</td></tr>",
        f"<tr><td>美國 CPI</td><td>待補齊</td><td>待補齊</td></tr>",
        # 0050 配息：待 MB 確認後由 daily_analysis.json 注入
    ]
    return "\n          ".join(rows)


def _format_line_with_numbers(line: str) -> str:
    import re as _nm
    _b = _nm.sub(r'([0-9,]{1,}\\.?[0-9]*|[+-]?[0-9.]+%|[+-]?[0-9,]+億)', r'<strong style="color:#c2410c">\1</strong>', line)
    return _b

def _inject_market_intel(html: str, tv: dict, signals: dict, llm_emergency: str = "") -> str:

    """以 daily_analysis.json + hunter intel 注入 market + Buffett + CTO 區塊。"""
    # Moved from end of function for Buffett advice generation.
    import sqlite3
    _ac2 = {}
    try:
        _db2 = sqlite3.connect(str(BASE / "dragon_assets.db"))
        for r in _db2.execute("SELECT category, source, SUM(weight) as w FROM asset_class GROUP BY category, source"):
            _ac2[(r[1], r[0])] = r[2]
        _db2.close()
    except Exception:
        pass
    _sec2 = float(tv.get("securities_total", 0) or 0)
    _fund2 = float(tv.get("fund_market_value", 0) or tv.get("funds", 0) or 0)
    _ins2 = float(tv.get("insurance_current_value", 0) or 0)
    _cash_old2 = float(tv.get("bonds_cash", 0) or 0)
    _cash2 = max(_cash_old2 - 5_812_576, 0) + 33_000
    _bond2 = 2_097_467
    def _src2(src):
        return {"securities": _sec2, "fund": _fund2, "insurance_fund": _ins2, "cash": _cash2, "bond": _bond2}.get(src, 0)
    def _cat2(cat):
        t = 0
        for (s, c), w in _ac2.items():
            if c == cat:
                sw = sum(w2 for (s2, c2), w2 in _ac2.items() if s2 == s)
                t += _src2(s) * w / max(sw, 1)
        return t
    _tw_v = _cat2("tw_equity")
    _us_v = _cat2("us_equity")
    _def_v = _cat2("defensive")
    _bond_v = _cat2("bond")
    _cash_v = tv.get('cash', tv.get('cash_total', 4_483_408))

    _tgt_tw, _tgt_us, _tgt_def, _tgt_bond, _tgt_cash = 35.0, 30.0, 25.0, 5.0, 5.0
    _tot = max(_tw_v + _us_v + _def_v + _bond_v + _cash_v, 1) # This needs to be calculated before _fmt_pct and _fmt_gap
    def _fmt_pct(v): return f"{v/_tot*100:.1f}%"
    def _fmt_gap(v, t): return f"{v/_tot*100 - t:+.1f}pp"

    # 先從 market_intel 表補入 hunter 情報
    try:
        import sqlite3
        _db = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _r = _db.execute("SELECT buy_count,sell_count,summary,signals FROM market_intel WHERE date=? ORDER BY timestamp DESC LIMIT 1", (TODAY,)).fetchone()
        _db.close()
        if _r and _r[0] is not None and (_r[0] > 0 or _r[1] > 0):
            _mr = [f"<tr><td>Hunter 情報訊號</td><td>買{_r[0]}/賣{_r[1]}筆</td><td>{(_r[2] or '')[:60]}</td></tr>"]
            try:
                _j = json.loads(_r[3]) if _r[3] else {}
                for _s in (_j.get("buy",[])or[])[:2]:
                    _mr.append(f"<tr><td>購 買進訊號</td><td colspan='2'>{_s[:60]}</td></tr>")
                for _s in (_j.get("sell",[])or[])[:2]:
                    _mr.append(f"<tr><td>網 賣出訊號</td><td colspan='2'>{_s[:60]}</td></tr>")
            except: pass
            _hunter_rows = chr(10).join("          "+r for r in _mr)
    except: pass
    analysis = load_daily_analysis()
    if not analysis:
        return html

    scenario = analysis.get("scenario", {})
    buffett = analysis.get("buffett", {})
    cto = analysis.get("cto", {})

    # Bull / Bear
    html = html.replace("__BULL_TEXT__", buffett.get("bull", "—"))
    html = html.replace("__BEAR_TEXT__", buffett.get("bear", "—"))

    # Market rows from analysis
    market = analysis.get("market", {})
    twii = market.get("twii", "待補齊")
    tsm = market.get("tsm", "待補齊")
    sox = market.get("sox", "待補齊")
    us = market.get("us", "待補齊")
    cpi = market.get("cpi", "待補齊")

    rows = [
        f"<tr><td>台股加權指數（{TODAY}）</td><td>{twii}</td><td>{scenario.get('market_assessment', market.get('twii', '待補齊'))}</td></tr>",
        f"<tr><td>台積電（{TODAY}）</td><td>{tsm}</td><td>半導體龍頭穩盤</td></tr>",
        f"<tr><td>費半（{TODAY}）</td><td>{sox}</td><td>高檔回調</td></tr>",
        f"<tr><td>美股（{TODAY}）</td><td>{us}</td><td>通膨降溫驅動科技領漲</td></tr>",
        f"<tr><td>美國 CPI</td><td>{cpi}</td><td>降息預期升溫</td></tr>",
        # 0050 配息：待 MB 確認後由 daily_analysis.json 注入
    ]
    # 合併 Hunter 訊號 + 標準市場數據
    _all_rows = rows[:]
    try:
        if _hunter_rows:
            _all_rows = [_hunter_rows] + rows
    except: pass
    html = html.replace("__MARKET_ROWS__", chr(10).join("          " + r for r in _all_rows))

    # Buffett / CTO 區塊
    buf_bull = buffett.get("bull", "")
    buf_bear = buffett.get("bear", "")
    buf_actions = buffett.get("actions", [])
    scenario_event = scenario.get("event", "—")
    buf_scenario = scenario.get("scenario_summary") or buffett.get("scenario_summary")
    net_worth = tv.get("net_worth", 0)
    snap_dir = BASE / "snapshots"
    yesterday_snap = {}
    candidates = sorted(snap_dir.glob("snapshot_*.json"), reverse=True)
    if candidates:
        try:
            yesterday_snap = json.loads(candidates[0].read_text(encoding="utf-8"))
        except Exception:
            yesterday_snap = {}
    # Buffett/CTO: 優先從 buffett_cto_report_{TODAY}.md 讀取，不手動維護
    report_md = BASE / f"buffett_cto_report_{TODAY}.md"
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
        buf_content = []
        def _format_line_with_numbers(line):
            import re as _nm
            _b = _nm.sub(r'([0-9,]{3,}\\.?[0-9]*|[+-]?[0-9.]+%|[+-]?[0-9,]+億)', r'<strong style="color:#c2410c;">\\\1</strong>', line)
            return _b

        buf_content.append(f'<p><strong>🧓 巴菲特式思考</strong></p>')
        buf_content = []
        def _format_line_with_numbers(line):
            import re as _nm
            _b = _nm.sub(r'([0-9,]{3,}\\.?[0-9]*|[+-]?[0-9.]+%|[+-]?[0-9,]+億)', r'<strong style="color:#c2410c">\1</strong>', line)
            return _b
        if not buf_content:
            buf_content_lines = []
            buf_content_lines.append(f'<p><strong>🧓 巴菲特式思考</strong></p>')
            buf_content_lines.append(f'<span style="display:block">• 場景判定：{_format_line_with_numbers(buf_scenario or scenario_event)}</span>')
            if buf_bull:
                buf_content_lines.append(f'<span style="display:block">• Bull：{_format_line_with_numbers(buf_bull)}</span>')
            if buf_bear:
                buf_content_lines.append(f'<span style="display:block">• Bear：{_format_line_with_numbers(buf_bear)}</span>')
            for a in buf_actions:
                buf_content_lines.append(f'<span style="display:block">• {_format_line_with_numbers(a)}</span>')

            diff_bullets = _diff_to_buffett_bullets(tv, yesterday_snap)
            if diff_bullets:
                buf_content_lines.append(f'<p><strong>📋 昨日差異帶來的行動啟示</strong></p>')
                for b in diff_bullets:
                    buf_content_lines.append(f'<span style="display:block">• {_format_line_with_numbers(b)}</span>')

            buf_content_lines.append(f'<p><strong>🤝 Buffett 派操作建議</strong></p>')
            buf_content_lines.append(f'<span style="display:block">• 淨資產：{_format_line_with_numbers(f"{net_worth:,.0f} TWD")}</span>')
            _us_pct = _us_v / _tot * 100
            _tw_pct = _tw_v / _tot * 100
            _def_pct = _def_v / _tot * 100
            _bond_pct = _bond_v / _tot * 100
            _cash_pct = _cash_v / _tot * 100
            buf_content_lines.append(f'<span style="display:block">• 建議部位：美股 {_format_line_with_numbers(f"{_us_pct:.0f}%")}（目標 {_format_line_with_numbers(f"{_tgt_us:.0f}%")}）、台股 {_format_line_with_numbers(f"{_tw_pct:.0f}%")}（目標 {_format_line_with_numbers(f"{_tgt_tw:.0f}%")}）、防守 {_format_line_with_numbers(f"{_def_pct:.0f}%")}（目標 {_format_line_with_numbers(f"{_tgt_def:.0f}%")}）、債券 {_format_line_with_numbers(f"{_bond_pct:.0f}%")}（目標 {_format_line_with_numbers(f"{_tgt_bond:.0f}%")}）、現金 {_format_line_with_numbers(f"{_cash_pct:.0f}%")}（目標 {_format_line_with_numbers(f"{_tgt_cash:.0f}%")}）</span>')

            today_action = []
            if (_tw_v / _tot * 100 - _tgt_tw) < -5:
                today_action.append("台股偏低，逢低補碼")
            if (_us_v / _tot * 100 - _tgt_us) > 5:
                today_action.append("美股超標，優先減碼")
            if (_def_v / _tot * 100 - _tgt_def) < -5:
                today_action.append("防守不足，補 00878/00713")
            if (_cash_v / _tot * 100 - _tgt_cash) > 5:
                today_action.append("現金過多，可轉投入")
            if not today_action:
                today_action.append("持股觀望，等待機會")
            buf_content_lines.append(f'<span style="display:block">• 今日動作：{_format_line_with_numbers("、".join(today_action))}</span>')
            buf_content_lines.append(f'<span style="display:block">• 觸發條件：{_format_line_with_numbers("外資賣超 > 150 億 / 大盤跌 1.5% / 費半跌 2% / 跌破季線+量增 → 啟動減碼；外資買超 > 100 億 + 大盤漲 1% + 費半 +3% → 回補。")}</span>')
            buf_content = '\n'.join(buf_content_lines)

    cto_tech = cto.get("tech_stack", "—")
    cto_risk = cto.get("risk", "—")
    cto_action = cto.get("action", "—")
    cto_signal = scenario.get("cto_signal", "")
    if cto_signal:
        cto_risk = f"今日觸發：{cto_signal}；{cto_risk}"

    if not cto_content:
        cto_content_lines = []
        cto_content_lines.append(f'<p><strong>🤖 CTO 技術視角</strong></p>')
        cto_content_lines.append(f'<span style="display:block"><strong>tech_stack</strong>：{_format_line_with_numbers(cto_tech)}</span>')
        cto_content_lines.append(f'<span style="display:block"><strong>今日最大風險</strong>：{_format_line_with_numbers(cto_risk)}</span>')
        cto_content_lines.append(f'<span style="display:block"><strong>建議動作</strong>：{_format_line_with_numbers(cto_action)}</span>')
        cto_content = '\n'.join(cto_content_lines)

    # 緊急應變 LLM 分析
    if llm_emergency:
        # 清理 ASCII 排版，轉換為 HTML
        _em = llm_emergency
        _em = _em.replace("╔", "").replace("╗", "").replace("╚", "").replace("╝", "").replace("║", "").replace("═", "")
        _em = _em.replace("━━━", "").replace("━━", "").replace("━", "")
        _em = _em.replace("───", "").replace("──", "").replace("─", "")
        # 分隔線改為 HTML hr
        import re
        _em = re.sub(r'[━═─]{5,}', '<hr style="border:0;border-top:1px dashed #475569;margin:10px 0">', _em)
        # 標題關鍵字加粗
        for kw in ["【壹】", "【貳】", "【參】", "【肆】", "【伍】", "【陸】"]:
            _em = _em.replace(kw, f"<strong style='color:#f59e0b'>{kw}</strong>")
        # 分析/建議字樣加粗
        _em = _em.replace("分析：", "<strong>分析：</strong>")
        _em = _em.replace("建議：", "<strong>建議：</strong>")
        _em = _em.replace("警訊：", "<strong style='color:#ef4444'>警訊：</strong>")
        llm_emergency = _em

    html = html.replace("{llm_emergency_analysis}", llm_emergency)
    html = html.replace("__BUFFETT_CONTENT__", buf_content)
    html = html.replace("__CTO_TECH__", cto_content)

    return html



def _format_content_to_html(text, content_type="market_intel"):
    _formatted_lines = []
    if content_type == "market_intel":
        _known_headers = {"【台股/大盤】", "【美股/外資】", "【CPI/利率】", "【情報訊號】", "【最新市場消息】", "【持倉關聯分析】", "【買進訊號】", "【賣出訊號】"}
        for _l in text.split("\n"):
            _l = _l.strip()
            if not _l:
                continue
            _header = _l[:_l.find("】")+1] if "】" in _l else ""
            if _header in _known_headers:
                _rest = _l[len(_header):].strip()
                _formatted_lines.append(f"<p><strong>{_header}</strong>{' '+_rest if _rest else ''}</p>")
            elif _l.startswith("•"):
                _formatted_lines.append(f"<p style=\"margin-left:12px\">{_l}</p>")
            else:
                _formatted_lines.append(f"<p>{_l}</p>")
    elif content_type == "emergency_analysis":
        import re as _nm # This import needs to be handled carefully if it's not global
        for _analysis_line in text.split('\n'):
            _trimmed_line = _analysis_line.strip()
            if not _trimmed_line:
                _formatted_lines.append('<p></p>')
            elif _trimmed_line.startswith('━'):
                _formatted_lines.append('<hr>')
            elif _trimmed_line.startswith('•') or _trimmed_line.startswith('🔥'):
                _formatted_lines.append(f'<span style=\"display:block\">{_trimmed_line}</span>')
            elif _trimmed_line.startswith('【') and _trimmed_line.endswith('】'):
                _formatted_lines.append(f'<strong>{_trimmed_line}</strong>')
            else:
                _b = _nm.sub(r'([0-9,]{3,}\\.?[0-9]*|[+-]?[0-9.]+%)', r'<strong style=\"color:#c2410c\">\1</strong>', _trimmed_line)
                _formatted_lines.append(f'<span>{_b}</span>')
    return "\n".join(_formatted_lines)

def main():
    print(f"[RUN_DAILY] 日期：{TODAY}")

    # 校準
    tv = calibrate_sources()
    print(f"[RUN_DAILY] 真值：月收 {tv['monthly_income']:,} / 月支 {tv['monthly_expense']:,} / 盈餘 +{tv['working_surplus']:,}")

    # 情報：refresh today's hunter intel
    intel_result = mi_mod.ensure_today_intel(force_refresh=True)
    # 彙整所有情報源到 market_intel 表
    try:
        from compile_intel import compile_intel
        compile_intel(force_refresh=True)
    except Exception:
        pass
    # 從 Notion 同步決策（寫入策略檔）
    try:
        from notion_bridge import sync_notion_to_local
        _nr = sync_notion_to_local()
        if _nr["decisions_imported"] > 0:
            print(f"[NOTION BRIDGE] 匯入 {_nr['decisions_imported']} 筆決策")
    except Exception as _e:
        pass
    
    # 確保策略檔有內容（從 Notion 頁面直接讀取 blocks）
    try:
        from notion_bridge import read_page_blocks, parse_blocks_to_text
        _blocks = read_page_blocks("3a4fc735d43381d18a4bfe63e1bd6b2a")
        _block_text = parse_blocks_to_text(_blocks)
        if _block_text.strip():
            _raw_dir = BASE / "notion_bridge"
            _raw_dir.mkdir(exist_ok=True)
            (_raw_dir / f"{TODAY}_strategy_handbook.md").write_text(
                f"# 今日決策摘要\n來源頁面：3a4fc735...\n讀取時間：{__import__('datetime').datetime.now().isoformat()}\n\n{_block_text}",
                encoding="utf-8"
            )
    except: pass
    
    # 載入統一市場情報
    daily_analysis_path = BASE / "daily_analysis.json"
    market_intel_text = ""
    if daily_analysis_path.exists():
        try:
            daily_analysis_data = json.loads(daily_analysis_path.read_text(encoding='utf-8'))
            market_intel_text = daily_analysis_data.get("briefing", "")
        except Exception as _exc:
            print(f"[WARN] load daily_analysis.json for market briefing failed: {_exc}")

    # Fallback to legacy hunter text if LLM analysis is not available
    if not market_intel_text:
        intel_result = mi_mod.ensure_today_intel(force_refresh=True)
        intel_text = intel_result.get("briefing_text", "") # Get briefing text from daily_intel.py
        intel_signals = mi_mod.parse_hunter_signals(intel_text)
    else:
        # If LLM analysis is present, we still need signals for other parts of the report
        # For now, we'll try to extract them from the LLM text or use a placeholder.
        # A more robust solution would involve the LLM also outputting structured signals.
        intel_text = ""
        intel_signals = {"sell_signals": [], "buy_signals": []}


    # 巴菲特/CTO 動態分析（產出報告，供 render_daily_report 讀取）
    try:
        from buffett_cto_analyzer import main as buffett_main
        buffett_main(send=False)  # 產出報告，Telegram 統一由 deploy 發送
        print("[RUN_DAILY] buffett_cto_analyzer 報告產出完成")
    except Exception as exc:
        print(f"[WARN] buffett_cto_analyzer 失敗：{exc}")

    # 證券前三大佔比
    try:
        import sqlite3
        _sdb = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _sh = _sdb.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC LIMIT 3").fetchall()
        _cnt = _sdb.execute("SELECT COUNT(*) FROM holdings WHERE shares > 0").fetchone()
        _sdb.close()
        _stotal = sum(v for _, v in _sh) or 1
        _hpct = [round(v / _stotal * 100, 1) for _, v in _sh]
        tv['holdings_top3'] = [(f'{r[0]}', _hpct[i]) for i, r in enumerate(_sh)]
        tv['holdings_count'] = _cnt[0] if _cnt else len(_sh)
    except:
        tv['holdings_top3'] = [('00878', 15.0), ('009816', 16.6), ('00984A', 10.4)]
        tv['holdings_count'] = 15
    # 從 MB 最新帳單 CSV 讀取信用卡資料（只取每卡最新一筆）
    _mb_cc_rows = ""
    try:
        _mb_dir = BASE / "moneybook"
        _mb_bill = sorted(_mb_dir.glob("*帳單*.csv"), reverse=True)
        if _mb_bill:
            import csv
            _cc_map = {"玉山銀行": "UNI", "台新銀行": "Richart", "永豐銀行": "SPORT", "台北富邦": "momo / J"}
            _latest = {}
            with open(_mb_bill[0], "r", encoding="utf-8-sig") as _f:
                for _r in csv.DictReader(_f):
                    _bank = _r.get("金融機構","")
                    if _bank in _cc_map:
                        _due = _r.get("繳費截止日","")
                        _amt = float(_r.get("帳單金額",0))
                        # 只保留每卡繳費截止日最新的那筆
                        if _bank not in _latest or _due > _latest[_bank][0]:
                            _latest[_bank] = (_due, _amt)
            _cc_rows = []
            for _bank, (_due, _amt) in _latest.items():
                if _amt > 0:
                    _due_md = "/".join(_due.split("/")[1:]) if "/" in _due else _due
                    _cc_rows.append(f'          <tr><td>{_bank}</td><td>{_cc_map[_bank]}</td><td>{_due_md}</td><td class="num">{int(_amt):,}</td><td>🔄 待扣繳</td></tr>')
            if _cc_rows:
                _mb_cc_rows = "\n".join(_cc_rows)
    except: pass

    market_intel_text = _format_content_to_html(market_intel_text, content_type="market_intel")

    # 從 schedule_events.json 統一讀取排程（P0 + 本週行程）
    _schedule_rows = ""
    _p0_html = ""
    try:
        _events = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
        _schedule_rows = "\n".join(
            f'<tr><td>{e.get("date","")}</td><td>{e.get("item","")}</td><td class="num">{e.get("amount","")}</td><td>{e.get("status","")}</td></tr>'
            for e in _events
            if e.get("date","") == "待處理" or ("2026-07-26" <= e.get("date","") <= "2026-08-31")
        )[:4000]
        _p0_core = [
            '<li>7/17（五）— 國泰轉貸面簽/對保（✅ 已執行，8/2 完成低息轉貸）</li>',
            '<li>8/2（日）— 國泰 2.6% 轉貸完成 — 清償保單借貸</li>',
        ]
        _important = ['🔴','🔄','⚠️','⏸️','📋 重要']
        _p0_dynamic = [
            f'<li>{e.get("date","")} — {e.get("item","")} {e.get("amount","")} {e.get("status","")}</li>'
            for e in _events
            if any(s in (e.get("status","") or "") for s in _important)
            and (e.get("date","") == "待處理" or "2026-07" <= e.get("date","") <= "2026-08")
        ]
        _p0_html = "\n".join(_p0_core + _p0_dynamic)
    except Exception as _pe:
        print(f"[WARN] schedule_events.json: {_pe}")

    # 日報
    # LLM 緊急應變分析
    emergency_json_path = BASE / "data" / "emergency_llm_analysis.json"
    llm_emergency_analysis_html = ""
    if emergency_json_path.exists():
        try:
            emergency_data = json.loads(emergency_json_path.read_text(encoding='utf-8'))
            analysis_content = emergency_data.get("full_report", emergency_data.get("analysis", ""))
            _report_html = _format_content_to_html(analysis_content, content_type="emergency_analysis")
            # 從現有檔案找最新緊急應變報告（glob，不寫死日期，避免 404）
            _er_files = sorted(BASE.glob("emergency_report_2*.html"), reverse=True)
            _er_link = ""
            if _er_files:
                _er_link = f"https://b0988321088.github.io/longjiu-dashboard-2/{_er_files[0].name}"
            llm_emergency_analysis_html = f"""<div class="callout callout-warn">
            {_report_html}"""
            if _er_link:
                llm_emergency_analysis_html += f"""
            <p style="margin-top:8px;text-align:right;font-size:13px">
              <a href="{_er_link}" target="_blank" style="color:#2563eb">📄 查看完整緊急應變報告 →</a>
            </p>"""
            llm_emergency_analysis_html += """
            </div>"""
        except Exception as _exc:
            print(f"[WARN] load emergency_llm_analysis.json failed: {_exc}")

    daily_html = render_daily_report(tv, intel_text=intel_text, intel_signals=intel_signals, market_intel_text=market_intel_text, mb_cc_rows=_mb_cc_rows, llm_emergency_analysis=llm_emergency_analysis_html, schedule_rows_html=_schedule_rows, p0_tasks_html=_p0_html)
    daily_html = _inject_market_intel(daily_html, tv, intel_signals, llm_emergency_analysis_html)

    # 注入戰略穿透值到日報
    _snap = json.loads(Path(SNAPSHOT).read_text(encoding="utf-8")) if Path(SNAPSHOT).exists() else {}
    _pen = _snap.get("penetration", {})
    _atwd = _pen.get("actual_twd", {})
    _apct = _pen.get("actual_pct", {})
    _tgt = _pen.get("targets", {})
    _tw_v = _atwd.get("台股市值型成長", 0)
    _us_v = _atwd.get("美股市值型成長", 0)
    _def_v = _atwd.get("防守型配息", 0)
    _bond_v = _atwd.get("債券", 0)
    _cash_v = _atwd.get("現金/安全網", 0)
    for k, v in [("__DR_TW_V__",f"{_tw_v:,.0f}"),("__DR_US_V__",f"{_us_v:,.0f}"),("__DR_DEF_V__",f"{_def_v:,.0f}"),("__DR_BOND_V__",f"{_bond_v:,.0f}"),("__DR_CASH_V__",f"{_cash_v:,.0f}")]: daily_html = daily_html.replace(k, v)
    for k, v in [("__DR_TW_PCT__",f"{_apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{_apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{_apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{_apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{_apct.get('現金/安全網',0):.1f}%")]: daily_html = daily_html.replace(k, v)
    for k, v in [("__DR_TW_TGT__",f"{_tgt.get('台股市值型目標',35):.0f}%"),("__DR_US_TGT__",f"{_tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{_tgt.get('配息型目標',25):.0f}%"),("__DR_BOND_TGT__",f"{_tgt.get('債券型目標',5):.0f}%"),("__DR_CASH_TGT__",f"{_tgt.get('現金目標',5):.0f}%")]: daily_html = daily_html.replace(k, v)
    _pen_total = _tw_v + _us_v + _def_v + _bond_v + _cash_v or 1
    for k, t, g in [("__DR_TW_GAP__",_tw_v,_tgt.get('台股市值型目標',35)),("__DR_US_GAP__",_us_v,_tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",_def_v,_tgt.get('配息型目標',25)),("__DR_BOND_GAP__",_bond_v,_tgt.get('債券型目標',5)),("__DR_CASH_GAP__",_cash_v,_tgt.get('現金目標',5))]:
        _gap = t - _pen_total * g / 100; daily_html = daily_html.replace(k, f"{'+'if _gap>0 else ''}{_gap:,.0f}")

    # 證券明細注入
    try:
        _sdb = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _srows = _sdb.execute("SELECT ticker, shares, cost_price FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
        _sdb.close()
        _stop3 = "、".join(f"{r[0]} {int(r[1]):,}股" for r in _srows[:3])
        daily_html = daily_html.replace("__SEC_TOTAL__", f"{tv.get('securities_total', tv.get('securities', 0)):,} TWD ({len(_srows)}檔)")
        daily_html = daily_html.replace("__SEC_TOP3__", _stop3)
    except Exception as _se:
        print(f"  [WARN] 證券注入失敗: {_se}")
        daily_html = daily_html.replace("__SEC_TOTAL__", "---")
        daily_html = daily_html.replace("__SEC_TOP3__", "---")

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
        # 動態取代模板 placeholder
        _cash_val = tv.get("cash_total", tv.get("cash", 3614169))
        _mortgage_total = tv.get("mortgage_monthly_total", tv.get("mortgage_balance", 0))
        _salary_val = tv.get("salary", 43144)
        index_html = index_html.replace("__DBS_BALANCE__", f"{_cash_val:,.0f}")
        index_html = index_html.replace("__SINOPAC_BALANCE__", f"{_cash_val:,.0f}")
        index_html = index_html.replace("__SINOPAC_MORTGAGE__", f"{_mortgage_total:,.0f}")
        index_html = index_html.replace("__RESERVE_POOL__", f"{tv.get('financial_mortgage',2000000):,.0f}")
        index_html = index_html.replace("__SALARY__", f"{_salary_val:,.0f}")
        OUT_INDEX.write_text(index_html, encoding="utf-8")
        print(f"[RUN_DAILY] 儀表板產出：{OUT_INDEX}")

    # === 寫入記憶 ===
    try:
        from memory_helper import add_memory
        _pen = _snap.get("penetration", {}).get("actual_twd", {})
        add_memory("Hermes", f"日報{TODAY}", f"證券{_snap.get('securities_total_market_value',0):,} 保單{_snap.get('insurance_current_value',0):,} 配息{tv.get('monthly_dividend',0):,}")
        add_memory("Hermes", f"資產穿透{TODAY}", f"台股{_pen.get('台股市值型成長',0):,} 美股{_pen.get('美股市值型成長',0):,} 防守{_pen.get('防守型配息',0):,} 債券{_pen.get('債券',0):,} 現金{_pen.get('現金/安全網',0):,}")
    except Exception as _me:
        print(f"  ⚠️ 記憶寫入失敗: {_me}")



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
    _retire_income = tv.get("monthly_dividend", 107_116) + tv.get("rent_monthly", 80_100)
    _retire_expense = tv.get("monthly_expense", 141_958)
    html = html.replace("__RETIREMENT_INCOME__", fmt(_retire_income))
    html = html.replace("__RETIREMENT_SURPLUS__", f"+{fmt(_retire_income - _retire_expense)}")
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

    dividend = tv.get("monthly_dividend", 0) or 0
    rent = tv.get("rent_monthly", 0) or 0
    html = html.replace("__PASSIVE_INCOME__", f"配息 {dividend:,} + 房租 {rent:,} = {dividend + rent:,} TWD {passive_trend}")
    html = html.replace("__MONTHLY_INCOME_TREND__", income_trend)
    html = html.replace("__MONTHLY_EXPENSE_TREND__", expense_trend)
    html = html.replace("__INSURANCE_TREND__", insurance_trend)
    _cash_runway = int(tv.get("real_liquid_assets", tv.get("bonds_cash", 4_483_408)) - 5_812_576 + 33_000) if tv.get("bonds_cash") else int(tv.get("real_liquid_assets", 4_483_408))
    html = html.replace("__RUNWAY_MONTHS__", fmt(int(_cash_runway / max(tv.get("monthly_expense", 141_958), 1))))
    html = html.replace("__CASH_TOTAL__", fmt(_cash_runway))

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

    # 從 db 動態計算穿透值
    _sec = float(tv.get("securities_total", 0) or 0)
    _funds = float(tv.get("fund_market_value", 0) or tv.get("funds", 0) or 0)
    _insurance = float(tv.get("insurance_current_value", 0) or 0)
    _cash_old = float(tv.get("bonds_cash", 0) or 0)
    # bonds_cash = old_bonds(5,812,576) + old_cash, 減去舊債券得實際現金
    _cash = max(_cash_old - 5_812_576, 0) + 33_000  # 補今天洲際W租金
    _bonds_pen = 2_097_467  # 穿透校準後債券

    # 從 asset_class 表讀取權重係數
    _ac = {}
    try:
        import sqlite3
        _ac_db = sqlite3.connect(str(BASE / "dragon_assets.db"))
        for r in _ac_db.execute("SELECT category, source, SUM(weight) as w FROM asset_class GROUP BY category, source"):
            _ac[(r[1], r[0])] = r[2]
        _ac_db.close()
    except Exception:
        pass

    def _src_total(source):
        if source == "securities": return _sec
        if source == "fund": return _funds
        if source == "insurance_fund": return _insurance
        if source == "cash": return _cash
        if source == "bond": return _bonds_pen
        return 0

    def _cat_value(category):
        total = 0
        for (src, cat), weight in _ac.items():
            if cat == category:
                src_total = _src_total(src)
                # 計算該 source 的總權重
                total_weight = sum(w for (s, c), w in _ac.items() if s == src)
                total += src_total * weight / max(total_weight, 1)
        return total

    # 穿透值：優先讀 snapshot.penetration 真值（唯一真值），fallback 到 asset_class 權重計算
    _pen_vals = None
    try:
        import json as _json_io
        _snap_pen = _json_io.loads((BASE / "snapshot.json").read_text(encoding="utf-8")).get("penetration", {}).get("actual_twd", {})
        if _snap_pen and _snap_pen.get("台股市值型成長"):
            _pen_vals = {
                "tw": float(_snap_pen["台股市值型成長"]),
                "us": float(_snap_pen["美股市值型成長"]),
                "def": float(_snap_pen["防守型配息"]),
                "bond": float(_snap_pen["債券"]),
                "cash": float(_snap_pen["現金/安全網"]),
            }
    except Exception:
        _pen_vals = None

    if _pen_vals:
        _tw_value, _us_value, _def_value = _pen_vals["tw"], _pen_vals["us"], _pen_vals["def"]
        _bond_value, _cash_value = _pen_vals["bond"], _pen_vals["cash"]
    else:
        _tw_value = _cat_value("tw_equity")
        _us_value = _cat_value("us_equity")
        _def_value = _cat_value("defensive")
        _bond_value = _cat_value("bond")
        _cash_value = _cat_value("cash")

    _inv_total = max(_tw_value + _us_value + _def_value + _bond_value + _cash_value, 1)

    tw_eq = _tw_value / _inv_total * 100
    us_eq = _us_value / _inv_total * 100
    def_ = _def_value / _inv_total * 100
    bond = _bond_value / _inv_total * 100
    cash = _cash_value / _inv_total * 100

    tw_target = target.get("tw_equity_pct", 35.0)
    us_target = target.get("us_equity_pct", 30.0)
    def_target = target.get("defensive_pct", 25.0)
    bond_target = target.get("bond_pct", 5.0)
    cash_target = target.get("cash_pct", 5.0)

    tw_gap = tw_eq - tw_target
    us_gap = us_eq - us_target
    def_gap = def_ - def_target
    bond_gap = bond - bond_target
    cash_gap = cash - cash_target

    html = html.replace("__TW_EQ_PCT__", fmt(tw_eq))
    html = html.replace("__TW_EQ_TARGET__", fmt(tw_target))
    html = html.replace("__TW_EQ_GAP__", f"{tw_gap:+.1f}")
    html = html.replace("__TW_EQ_VALUE__", fmt(_tw_value))
    html = html.replace("__US_EQ_PCT__", fmt(us_eq))
    html = html.replace("__US_EQ_TARGET__", fmt(us_target))
    html = html.replace("__US_EQ_GAP__", f"{us_gap:+.1f}")
    html = html.replace("__US_EQ_VALUE__", fmt(_us_value))
    html = html.replace("__DEF_PCT__", fmt(def_))
    html = html.replace("__DEF_TARGET__", fmt(def_target))
    html = html.replace("__DEF_GAP__", f"{def_gap:+.1f}")
    html = html.replace("__DEF_VALUE__", fmt(_def_value))
    html = html.replace("__BOND_PCT__", fmt(bond))
    html = html.replace("__BOND_TARGET__", fmt(bond_target))
    html = html.replace("__BOND_GAP__", f"{bond_gap:+.1f}")
    html = html.replace("__BOND_VALUE__", fmt(_bond_value))
    html = html.replace("__CASH_PCT__", fmt(cash))
    html = html.replace("__CASH_TARGET__", fmt(cash_target))
    html = html.replace("__CASH_GAP__", f"{cash_gap:+.1f}")
    html = html.replace("__CASH_VALUE__", fmt(_cash_value))

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

    # 動態巴菲特：從 buffett_cto_analyzer 即時注入
    try:
        import json as _j
        from pathlib import Path as _P
        _snap = _j.loads((_P(r"C:/Users/bot/Desktop/longjiu_system/snapshot.json")).read_text("utf-8"))
        from buffett_cto_analyzer import penetration_analysis as _pa, generate_buffett_report as _gr
        _p = _pa(_snap)
        _bl = _gr(_p)
        _cd = {"tw_equity":("🇹🇼","台股",35),"us_equity":("🇺🇸","美股",30),"defensive":("🛡️","防守",25),"bond":("💵","債券",5),"cash":("💰","現金",5)}
        _h = '<div class="grid grid-cols-1 md:grid-cols-2 gap-4"><div class="bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2"><span class="text-xs font-bold text-blue-400">💡 穿透現況</span><ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4">'
        for _k,(_e,_l,_t) in _cd.items():
            _v = _p["actual"].get(_k,0)
            _g = _p["gaps"].get(_k,0)
            _c = "text-emerald-400" if _g >= 0 else "text-red-400"
            _s = f"+{_g:.0f}pp" if _g > 0 else f"{_g:.0f}pp"
            _h += f"<li>{_e} <strong>{_l}</strong>：{_v:.0f}%（目標 {_t}%，<span class=\"{_c}\">{_s}</span>）</li>"
        _h += '</ul></div><div class="bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2"><span class="text-xs font-bold text-teal-400">🎯 策略建議</span><ul class="text-xs text-slate-300 space-y-1.5 leading-relaxed">'
        for _ln in _bl:
            if "補碼" in _ln or "減碼" in _ln or "合理" in _ln:
                _h += f"<li>{_ln.replace('  ✅ ','').replace('  ⚠️ ','')}</li>"
        _h += "</ul>"
        # 加入巴菲特敘述
        _h += '<div class="mt-3 pt-3 border-t border-slate-700"><span class="text-xs font-bold text-amber-400">📝 巴菲特視角</span><ul class="text-xs text-slate-300 space-y-1.5 list-disc pl-4 mt-2">'
        _tw_g = _p["gaps"].get("tw_equity",0)
        _us_g = _p["gaps"].get("us_equity",0)
        _def_g = _p["gaps"].get("defensive",0)
        _bond_g = _p["gaps"].get("bond",0)
        _cash_g = _p["gaps"].get("cash",0)
        if _tw_g < -10:
            _h += "<li><strong>能力圈：</strong>台股嚴重不足，逢低補碼至目標水準，聚焦0050/009816</li>"
        if _us_g > 5:
            _h += "<li><strong>安全邊際：</strong>美股超標，優先減碼，保留現金等待機會</li>"
        if _bond_g > 5:
            _h += "<li><strong>分散配置：</strong>債券現金過多，可轉投入台股防守型配息</li>"
        if _def_g < -10:
            _h += "<li><strong>護城河：</strong>防守型配息不足，補00878/00713建立穩定現金流</li>"
        _h += "<li><strong>現金子彈：</strong>安全邊際充足，等待台股恐慌時加碼</li>"
        _h += "</ul></div>"
        _h += "</div></div>"
        html = html.replace("__BUFFETT_DYNAMIC__", _h)
    except Exception as _e:
        print(f"[WARN] Buffett dynamic inject fail: {_e}")
        html = html.replace("__BUFFETT_DYNAMIC__", '<div class="text-xs text-slate-400">📊 分析中</div>')

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
            "allianz_return": tv.get("allianz_a_performance", 16.41),
            "allianz_monthly": tv.get("allianz_ab_monthly", 95_347),
            "allianz_cum": tv.get("allianz_cum_dividend", 1_631_962),
            "allianz_cost": tv.get("allianz_cost", 8_000_000),
            "firstjin_monthly": tv.get("firstjin_monthly", 22_949),
            "firstjin_cum": tv.get("firstjin_cum_dividend", 73_341),
            "firstjin_cost": tv.get("firstjin_cost", 2_000_000),
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
    html = html.replace("__ALLIANZ_MONTHLY__", fmt(funds2.get("allianz_monthly", tv.get("allianz_ab_monthly", 95_347))))
    html = html.replace("__ALLIANZ_CUM__", fmt(funds2.get("allianz_cum", tv.get("allianz_cum_dividend", 1_630_962))))
    html = html.replace("__ALLIANZ_COST__", fmt(funds2.get("allianz_cost", tv.get("allianz_cost", 8_000_000))))
    html = html.replace("__POLICY_A_VAL__", fmt(tv.get("allianz_a_current_value", tv.get("allianz_a", tv.get("allianz_policy_a_value", 4_983_244)))))
    html = html.replace("__POLICY_B_VAL__", fmt(tv.get("allianz_b_current_value", tv.get("allianz_b", tv.get("allianz_policy_b_value", 2_650_802)))))
    html = html.replace("__FIRSTJIN_MONTHLY__", fmt(funds2.get("firstjin_monthly", tv.get("firstjin_monthly", 22_949))))
    html = html.replace("__FIRSTJIN_CUM__", fmt(funds2.get("firstjin_cum", 73_341)))
    html = html.replace("__FIRSTJIN_COST__", fmt(funds2.get("firstjin_cost", 2_000_000)))

    # Fund breakdown: prefer daily_analysis.json, fallback to known true values
    funds = da.get("funds", {})
    if not funds:
        funds = {
            "allianz_return": 16.41,
            "allianz_monthly": 73_167,
            "allianz_cum": 1_631_962,
            "allianz_cost": 8_000_000,
            "firstjin_monthly": 22_949,
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
    html = html.replace("__ALLIANZ_COST__", fmt(funds.get("allianz_cost", 7_808_297)))
    html = html.replace("__FIRSTJIN_MONTHLY__", fmt(funds.get("firstjin_monthly", 0)))
    html = html.replace("__FIRSTJIN_CUM__", fmt(funds.get("firstjin_cum", 0)))
    html = html.replace("__FIRSTJIN_COST__", fmt(funds.get("firstjin_cost", 2_000_000)))
    # firstjin value uses same as firstjin current value
    html = html.replace("__FIRSTJIN_VALUE__", fmt(tv.get("firstjin", 0) or funds.get("firstjin_value", 1_952_366)))
    # allianz value uses snapshot
    html = html.replace("__ALLIANZ_AB__", fmt(tv.get("allianz_ab", 0) or funds.get("allianz_value", 7_634_046)))
    # total monthly = sum of fund monthly + snapshot fallback
    calc_total = (funds.get("allianz_monthly", 0) or 0) + (funds.get("firstjin_monthly", 0) or 0)
    html = html.replace("__TOTAL_MONTHLY__", fmt(calc_total or tv.get("monthly_dividend", 107_116)))

    # 房租動態注入
    _rent_1f = 24_000
    _rent_zjw = 33_000
    _rent_23f = 21_000
    html = html.replace("__POLICY_A_VAL__", fmt(tv.get("allianz_a_current_value", tv.get("allianz_a", tv.get("allianz_policy_a_value", 4_983_244)))))
    html = html.replace("__POLICY_B_VAL__", fmt(tv.get("allianz_b_current_value", tv.get("allianz_b", tv.get("allianz_policy_b_value", 2_650_802)))))
    _rent_mgmt = 2_100
    _expense = int(tv.get("monthly_expense", 141_958))
    _mortgage_pmt = 33_724
    _rent_total = _rent_1f + _rent_zjw + _rent_23f + _rent_mgmt
    _rent_received = _rent_1f + _rent_zjw + _rent_23f + _rent_mgmt  # 80,100 全數實收
    _rent_pending = 0  # 已全數收齊
    _rent_breakdown = f"大義街1樓{_rent_1f:,}+洲際W{_rent_zjw:,}+大義街23樓{_rent_23f:,}+管理費{_rent_mgmt:,}"
    _rent_status = f"全數實收 {_rent_received:,}（大義街1樓{_rent_1f:,}+洲際W{_rent_zjw:,}+大義街23樓{_rent_23f:,}+管理費{_rent_mgmt:,} ✅）"

    html = html.replace("__RENT_TOTAL__", f"{_rent_total:,}")
    html = html.replace("__RENT_BREAKDOWN__", _rent_breakdown)
    html = html.replace("__RENT_STATUS__", _rent_status)
    # 房租收入明細列（動態）
    _rent_rows = (
        f'<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        f'<div class="flex items-center gap-2 text-xs">'
        f'<span class="text-emerald-400">✅ 已入帳</span>'
        f'<span class="text-slate-300">大義街1樓房租</span></div>'
        f'<span class="text-xs font-mono font-bold text-white">{_rent_1f:,} TWD</span></div>'
        f'<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        f'<div class="flex items-center gap-2 text-xs">'
        f'<span class="text-emerald-400">✅ 已入帳</span>'
        f'<span class="text-slate-300">洲際W房租</span></div>'
        f'<span class="text-xs font-mono font-bold text-white">{_rent_zjw:,} TWD</span></div>'
        f'<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        f'<div class="flex items-center gap-2 text-xs">'
        f'<span class="text-emerald-400">✅ 已入帳</span>'
        f'<span class="text-slate-300">大義街23樓房租</span></div>'
        f'<span class="text-xs font-mono font-bold text-white">{_rent_23f:,} TWD</span></div>'
        f'<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        f'<div class="flex items-center gap-2 text-xs">'
        f'<span class="text-emerald-400">✅ 已入帳</span>'
        f'<span class="text-slate-300">管理費</span></div>'
        f'<span class="text-xs font-mono font-bold text-white">{_rent_mgmt:,} TWD</span></div>'
    )
    html = html.replace("__RENT_ROWS__", _rent_rows)

    # template 殘留硬編碼注入
    html = html.replace("__CATHAT_SETTLEMENT__", f'{tv.get("mortgage_yy",0):,.0f}')
    html = html.replace("__CATHAY_DEPOSIT__", f'{tv.get("mortgage_yydu",0):,.0f}')
    html = html.replace("__DBS_BALANCE__", f'{tv.get("cash",0):,.0f}')
        # 動態 DBS note
    _dbs_cash = tv.get("cash_total", 0)
    _dbs_str = f"星展餘額 {_dbs_cash:,} TWD，扣理財型利息 ~10,000，{'餘裕充足 ✅' if _dbs_cash > 30000 else '⚠️ 需補資金'}"
    html = html.replace("{_dbs_note}", _dbs_str)
    html = html.replace("__SINOPAC_BALANCE__", f'{tv.get("cash",0):,.0f}')
    html = html.replace("__SINOPAC_MORTGAGE__", f'{tv.get("mortgage_monthly_total",0):,.0f}')
    html = html.replace("__RESERVE_POOL__", f'{tv.get("financial_mortgage",0):,.0f}+')
    html = html.replace("__SALARY__", f'{tv.get("salary",43144):,.0f}')
    # 新增動態注入
    html = html.replace("__MONTHLY_EXPENSE_PASSIVE__", f"{_expense:,}")
    html = html.replace("__MONTHLY_EXPENSE_DISPLAY__", f"{_expense:,}")
    html = html.replace("__MONTHLY_EXPENSE_COVER__", f"{_expense:,}")
    html = html.replace("__RENT_NOTE__", f"{tv.get('rent_monthly', 80_100):,}")
    html = html.replace("__MORTGAGE_PAYMENT__", f"{_mortgage_pmt:,}")
    html = html.replace("__DEF_TARGET_DISPLAY__", fmt(def_target))
    html = html.replace("__BOND_TARGET_DISPLAY__", fmt(bond_target))
    # 動態日期與提醒
    from datetime import date as _dt
    html = html.replace("__MARKET_DATE__", _dt.today().strftime("%m/%d"))
    # 今日提醒：從 Company_Ledger 或 dashboard_decisions 抓取
    _alert = ""
    try:
        _ledger = Path(BASE / "Company_Ledger.md").read_text("utf-8")
        import re as _re
        for _line in _ledger.splitlines():
            if _dt.today().isoformat() in _line or f"{_dt.today().month}/{_dt.today().day}" in _line:
                _alert = _line.strip().lstrip("|").strip()
                break
    except Exception:
        pass
    if not _alert:
        _alert = "✅ 無緊急事項"
    html = html.replace("__TODAY_ALERT__", _alert)

    # 本週完成清單（從 dashboard_decisions.json 動態生成）
    try:
        import json as _j
        _dec_file = BASE / "dashboard_decisions.json"
        if _dec_file.exists():
            _d = _j.loads(_dec_file.read_text("utf-8"))
            _decs = _d.get("decisions", [])
            # 取本週（近7天）已核准決策
            from datetime import timedelta
            _week_ago = (date.today() - timedelta(days=7)).isoformat()
            _weekly = [dec for dec in _decs if dec.get("timestamp", dec.get("approved_at", ""))[:10] >= _week_ago]
            _items = []
            for _dec in _weekly[-6:]:  # 最多顯示6項
                _name = _dec.get("action", _dec.get("text", _dec.get("name", "")))[:40]
                _items.append(f'<div class="flex items-center gap-1"><span class="text-emerald-400">•</span><span class="text-slate-300">{_name} ✅</span></div>')
            if _items:
                # 分兩欄
                _mid = (len(_items) + 1) // 2
                _left = "".join(_items[:_mid])
                _right = "".join(_items[_mid:])
                # reverse order so newest first
                _html = _left + _right
            else:
                _html = '<div class="col-span-2 text-slate-400 text-center">本週尚無核准決策</div>'
            html = html.replace("__WEEKLY_CHECKLIST__", _html)
    except Exception:
        html = html.replace("__WEEKLY_CHECKLIST__", '<div class="col-span-2 text-slate-400">載入失敗</div>')

    return html


    print("\n[DONE] 產出完成。")
    print(f"  日報：{OUT_DAILY}")


if __name__ == "__main__":
    main()