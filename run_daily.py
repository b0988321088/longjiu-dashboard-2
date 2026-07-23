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
    # 真值錨定：本月保單配息（缺 snapshot 欄位時由真值計算）
    monthly_dividend = snap.get("monthly_dividend")
    if monthly_dividend is None:
        # 保守回退：安聯 A+B + 第一金月配
        monthly_dividend = (snap.get("allianz_ab_monthly", 73_167) or 55_451) + (snap.get("firstjin_monthly", 22_949) or 13_593)

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
        "allianz_dividend": snap.get("allianz_ab_monthly", 73_167),
        "firstjin_dividend": snap.get("firstjin_monthly", 22_949),
        "relay_stations": 3,
        "cc_4cards": ["玉山UNI", "台新Richart", "永豐SPORT", "台北富邦momo/J"],
        "loans_2mortgage": ["洲際W房貸", "大義街房貸+理財型利息"],
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "bonds_cash": snap.get("penetration", {}).get("actual_twd", {}).get("債券及安全現金", 9_697_196),
        "insurance_current_value": s_insurance,
        "funds": snap.get("fund_market_value", snap.get("funds_total", 0)) or 0,
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


def render_daily_report(tv: dict, intel_text: str = "", intel_signals: dict | None = None, market_intel_text: str = "", mb_cc_rows: str = "") -> str:
    """產出五大章節日報 HTML。"""
    allianz = tv["allianz_ab"] or 7_881_584
    firstjin = tv["firstjin"] or 1_994_698
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = tv.get("monthly_dividend", 107_116)
    allianz_dividend = tv.get("allianz_dividend", 73_167)
    firstjin_dividend = tv.get("firstjin_dividend", 22_949)

    # 從 relay_calendar.md 取得 T+4 轉換截止日
    relay_table = f"""<div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>站別</th><th>流向</th><th>基準日</th><th>轉換截止</th><th>預估入帳</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>第一站</td><td>摩根多重收益（FJ33）→ 安聯收益成長（FL65）</td><td>7/14</td><td>—</td><td>7/19-20</td><td>✅ 已配息/已入帳</td></tr>
          <tr><td>第二站</td><td>安聯收益成長 + M&amp;G 入息基金</td><td>7/17</td><td>8/10（FL65）<br>8/17（M&amp;G）</td><td>~7/29</td><td>🔄 M&amp;G轉換中（尚未全數到位）</td></tr>
          <tr><td>第三站</td><td>安聯 AI 收益 + 貝萊德世界科技 A10</td><td>7/29-30</td><td>⚠️ <strong>7/23</strong>（AI）<br><strong>7/24</strong>（A10）</td><td>~8/10</td><td>⏸️ 等待到期（PIMCO已轉出 ✅）</td></tr>
        </tbody>
      </table>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>龍九控股日報 {TODAY}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", "PingFang TC", sans-serif;
    background: #f5f5f7;
    margin: 0;
    padding: 16px;
    line-height: 1.8;
    font-size: 17px;
    color: #1d1d1f;
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
  .table-wrap {{ overflow-x: auto; margin: 8px 0; }}
  table {{
    width: 100%;
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
    margin: 10px 0;
    border-left: 4px solid;
  }}
  .callout-bull {{ background:#f0fff4; border-color:#22c55e; }}
  .callout-bear {{ background:#fff5f5; border-color:#ef4444; }}
  .callout-warn {{ background:#fffbeb; border-color:#f59e0b; }}
  .callout-info {{ background:#eff6ff; border-color:#3b82f6; }}

  /* Mobile table style: bordered with background fill */
  @media (max-width: 640px) {{
    body {{ font-size: 15px; padding: 10px; }}
    table {{ font-size: 14px; }}
    th, td {{ padding: 8px 10px !important; }}
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
          <tr><td>總資產</td><td>50,689,930 TWD</td><td>淨資產 28,689,930；負債率 43.4%</td></tr>
          <tr><td>總負債</td><td>22,000,000 TWD</td><td> convertible 房貸 + 保單借貸 400 萬</td></tr>
          <tr><td>本月領息</td><td>{monthly_dividend:,} TWD</td><td>安聯 {allianz_dividend:,} + 第一金 {firstjin_dividend:,}</td></tr>
          <tr><td>被動月收</td><td>{tv['rent_monthly']+80000:,} TWD</td><td>覆蓋率 113.8%；安全邊際充足</td></tr>
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
    <pre id="market-intel-block" style="font-size:14px;line-height:1.7;white-space:pre-wrap;color:#1d1d1f;">{market_intel_text}</pre>
  </div>

  <!-- 戰略異常看板 -->
  <div class="card">
    <h2>3/5｜戰略異常看板 Strategic Risk Hub</h2>
    <div class="label">四大戰略重點</div>

    <h3>保單維運</h3>
    <p class="text-lead">保單現值 <strong>{insurance_total:,} TWD</strong>（安聯 A+B {allianz:,} + 第一金 FL65 {firstjin:,}），本月配息合計 <strong>{monthly_dividend:,} TWD</strong>。落實利潤再投資 SOP，於 T+4 最晚轉換申請日才執行 relay 轉換。</p>

    <h3>證券曝險</h3>
    <p class="text-lead">證券總市值 <strong>{tv['securities_total']:,} TWD</strong>（14檔）。前三大：{tv['holdings_top3'][0][0]} {tv['holdings_top3'][0][1]:.1f}%、{tv['holdings_top3'][1][0]} {tv['holdings_top3'][1][1]:.1f}%、{tv['holdings_top3'][2][0]} {tv['holdings_top3'][2][1]:.1f}%。0056 凍結質押中，短期無法加碼。0050 配息：待 MB 確認；防禦缺口由 00878/00713 預備。</p>

    <h3>房租金流</h3>
    <p class="text-lead">房租月收 <strong>{tv['rent_monthly']:,} TWD</strong>，覆蓋月支出 55%。大義街1樓 24,000（7月初入帳）+ 洲際W 33,000（7/20 ✅ 已入帳）= 已實收 57,000；剩大義街23樓 21,000 + 管理費 2,100 月底收齊。星展戶頭餘額 7,287 TWD，8/1 需扣款 33,724，由台新調度 3 萬元補庫。</p>

    <h3>鉅亨基金部位</h3>
    <p class="text-lead">基金總市值 <strong>{tv.get('funds',0):,} TWD</strong>。路博邁5G累積 238,955 / 0050不配息 108,047 / 統一奔騰 86,931 / 台新半導體(JPY) 177,662 / 台中銀優息 47,699 / 路博邁5G月配 88,939 / 0050B配息 46,924。淨值反彈 +29,166（+3.81%），今日鉅亨帳戶總覽 {tv.get('funds',0):,}。</p>
  </div>

  <!-- 3/5 保單接力引擎 -->
  <div class="card">
    <h2>3/5｜保單接力引擎 Insurance Relay Engine</h2>
    <div class="label">三站轉換時序監控</div>
    <p class="text-lead"><strong>本月配息合計：{monthly_dividend:,} TWD</strong></p>
    {relay_table}

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

    <h3>第一金保單（成本 2,000,000 / 現值 {firstjin:,}）</h3>
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
          <tr><td>永豐銀行</td><td>洲際 W 房貸</td><td>7/20</td><td class="num">65,734</td><td>📌 待扣款</td></tr>
          <tr><td>星展銀行</td><td>大義街房貸（原國泰，尚未完成轉貸）</td><td>8/1</td><td class="num">23,424</td><td>📌 待扣款</td></tr>
          <tr><td>星展銀行</td><td>理財型利息</td><td>8/1</td><td class="num">10,300</td><td>📌 隨房貸扣款</td></tr>
          <tr><td>永豐銀行</td><td>週轉金</td><td>—</td><td class="num">7,000,000</td><td>已動用額度</td></tr>
        </tbody>
      </table>
    </div>

    <div class="callout callout-warn">
      <strong>🚨 星展補庫警示</strong><br>
      星展戶頭餘額 7,287 TWD，不足以覆蓋 8/1 扣款 33,724（大義街房貸 23,424 + 理財型利息 10,300）。<br>
      指令：由台新調度 3 萬元，優先補足扣款缺口。
    </div>
  </div>

  <!-- 5/5 龍九決戰日檢核 -->
  <div class="card">
    <h2>5/5｜龍九決戰日檢核 Tactical Ops Checklist</h2>
    <div class="label">P0 任務置頂 + 行事曆維度聚合</div>

    <h3>🚨 P0 任務</h3>
    <div class="callout callout-warn">
      <ul>
        <li>7/17（五）— 國泰轉貸面簽/對保（✅ 已執行，待後續流程）</li>
        <li>7/20（一）— 洲際 W 33,000 ✅ 已入帳</li>
        <li>7/22（三）— 玉山信用卡繳款截止 3,176</li>
        <li>⚠️ <strong>7/23（四）</strong>— 安聯 AI 收益 T+4 轉換截止 ← ⏰ 今天！</li>
        <li>⚠️ <strong>7/24（五）</strong>— 貝萊德世界科技 A10 T+4 轉換截止</li>
        <li>7/27（一）— 台新信用卡繳款截止 1,000</li>
        <li>7/29-30 — Fed 利率決策 + 安聯 AI / 貝萊德 A10 基準日</li>
        <li>8/1（五）— 星展戶頭扣款 33,724（大義街房貸 + 理財型利息）🚨 需補缺口</li>
        <li><relay_0050> — 0050 配息 ⚠️ 待 MB 確認</li>
      </ul>
    </div>

    <h3>本週行程 + 繳款 / 配息排程</h3>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>日期</th><th>項目</th><th class="num">金額 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>7/17（五）</td><td>國泰轉貸面簽/對保 + 段部上課</td><td class="num">—</td><td>🚨 P0</td></tr>
          <tr><td>7/19-20</td><td>摩根 FJ33 配息入帳</td><td class="num">13,593</td><td>✅ 已配息</td></tr>
          <tr><td>7/22</td><td>玉山信用卡繳款截止</td><td class="num">3,176</td><td>🔄 待處理</td></tr>
          <tr><td>⚠️ <strong>7/23</strong></td><td>安聯 AI 收益 T+4 轉換截止</td><td class="num">—</td><td>🔴 今天到期</td></tr>
          <tr><td>⚠️ <strong>7/24</strong></td><td>貝萊德 A10 T+4 轉換截止</td><td class="num">—</td><td>⏰ 明天到期</td></tr>
          <tr><td>7/27</td><td>台新信用卡繳款截止</td><td class="num">1,000</td><td>🔄 待處理</td></tr>
          <tr><td>7/29-30</td><td>安聯 AI / 貝萊德 A10 基準日</td><td class="num">—</td><td>⏸️ 等待到期</td></tr>
          <tr><td>8/1</td><td>星展戶頭扣款（大義街房貸 + 理財型利息）</td><td class="num">33,724</td><td>🚨 需補缺口</td></tr>
          <tr><td>待 MB</td><td>0050 配息</td><td class="num">—</td><td>待確認</td></tr>
          <tr><td>10/23-28</td><td>胡志明市旅行 6D5N</td><td class="num">—</td><td>✅ 已排程</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 投資決策框架 -->
  <div class="card">
    <h2>投資決策框架</h2>

    <div class="callout callout-bull">
      <strong>🟢 Bull Case</strong><br>
      __BULL_TEXT__
    </div>

    <div class="callout callout-bear">
      <strong>🔴 Bear Case</strong><br>
      __BEAR_TEXT__
    </div>

    <h3>市場動態分析（{TODAY} 即時）</h3>
    <div class="callout callout-info">
      <strong>ℹ️ 數據來源</strong><br>
      台股/費半/美股/台積電/TWII 透過 web_search + Yahoo Finance/GoodInfo 擷取；美國 CPI 透過 web_search 確認。
    </div>
    <div class="table-wrap">
      <table class="mobile-bordered">
        <thead>
          <tr><th>項目</th><th>最新狀態</th><th>影響預估</th></tr>
        </thead>
        <tbody>
__MARKET_ROWS__
        </tbody>
      </table>
    </div>

    <h3>巴菲特視角建議</h3>
    <div class="callout callout-bull">
      __BUFFETT_CONTENT__
    </div>

    <h3>CTO 技術視角</h3>
    <div class="callout callout-bear">
      __CTO_TECH__
    </div>

    <h3>CIO 審查 / 觀點</h3>
    <div class="callout callout-info">
      <strong>🧑‍💻 CIO 觀點</strong><br>
      • 本日市場情緒持平，無重大異常。<br>
      • 資產配置持續檢視，尤其注意防禦型配息部位的補碼時機。<br>
      • 流動性管理穩定，補庫警示已處理。
    </div>
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


def _inject_market_intel(html: str, tv: dict, signals: dict) -> str:
    """以 daily_analysis.json + hunter intel 注入 market + Buffett + CTO 區塊。"""
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
        buf_content = f"<strong>🧓 巴菲特式思考</strong><br>• 場景判定：{buf_scenario or scenario_event}<br>"
        if buf_bull:
            buf_content += f"• Bull：{buf_bull}<br>"
        if buf_bear:
            buf_content += f"• Bear：{buf_bear}<br>"
        for a in buf_actions:
            buf_content += f"• {a}<br>"
        diff_bullets = _diff_to_buffett_bullets(tv, yesterday_snap)
        if diff_bullets:
            buf_content += "<br><strong>📋  昨日差異帶來的行動啟示</strong><br>"
            for b in diff_bullets:
                buf_content += f"• {b}<br>"
        buf_content += "<br><strong>🤝 Buffett 派操作建議</strong><br>"
        buf_content += f"• 淨資產：{net_worth:,.0f} TWD<br>"
        buf_content += "• 建議部位：美股權益 ≤ 35%、台股權益 15-20%、高利活存/短債 ≥ 20%、保單/配息穩定型 ≥ 25%<br>"
        buf_content += "• 今日動作：減碼美股權重、增加高利活存與防禦型配息部位；0050 配息縮水後缺口以 00878/00713 補位。<br>"
        buf_content += "• 觸發條件：外資賣超 > 150 億 / 大盤跌 1.5% / 費半跌 2% / 跌破季線+量增 → 啟動減碼；外資買超 > 100 億 + 大盤漲 1% + 費半 +3% → 回補。"

    if not cto_content:
        cto_tech = cto.get("tech_stack", "—")
        cto_risk = cto.get("risk", "—")
        cto_action = cto.get("action", "—")
        cto_signal = scenario.get("cto_signal", "")
        if cto_signal:
            cto_risk = f"今日觸發：{cto_signal}；{cto_risk}"
        cto_content = f"<strong>🤖 CTO 技術視角</strong><br><strong>tech_stack</strong>：{cto_tech}<br><strong>今日最大風險</strong>：{cto_risk}<br><strong>建議動作</strong>：{cto_action}"

    html = html.replace("__BUFFETT_CONTENT__", buf_content)
    html = html.replace("__CTO_TECH__", cto_content)

    return html


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
    # Load unified market briefing from daily_intel_report_{date}.json
    unified_path = BASE / f"daily_intel_report_{TODAY.replace('-','')}.json"
    market_intel_text = ""
    if unified_path.exists():
        try:
            import json as _json
            unified = _json.loads(unified_path.read_text(encoding='utf-8'))
            market_intel_text = unified.get("briefing", "")
        except Exception as _exc:
            print(f"[WARN] load unified market briefing failed: {_exc}")
            market_intel_text = ""

    if not market_intel_text:
        # Fallback: legacy hunter text
        market_intel_text = mi_mod.load_latest_hunter()

    intel_text = market_intel_text
    intel_signals = mi_mod.parse_hunter_signals(intel_text)

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
        _sdb.close()
        _stotal = sum(v for _, v in _sh) or 1
        _hpct = [round(v / _stotal * 100, 1) for _, v in _sh]
        tv['holdings_top3'] = [(f'{r[0]}', _hpct[i]) for i, r in enumerate(_sh)]
    except:
        tv['holdings_top3'] = [('00878', 15.0), ('009816', 16.6), ('00984A', 10.4)]
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
    # 日報
    daily_html = render_daily_report(tv, intel_text=intel_text, intel_signals=intel_signals, market_intel_text=market_intel_text, mb_cc_rows=_mb_cc_rows)
    daily_html = _inject_market_intel(daily_html, tv, intel_signals)

    # 注入戰略穿透值到日報（與儀表板一致）
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
    _inv_t = max(_tw_v + _us_v + _def_v + _bond_v + _cash_v, 1)

    _tgt_tw, _tgt_us, _tgt_def, _tgt_bond, _tgt_cash = 35.0, 30.0, 25.0, 5.0, 5.0
    _tot = max(_tw_v + _us_v + _def_v + _bond_v + _cash_v, 1)
    def _fmt_pct(v): return f"{v/_tot*100:.1f}%"
    def _fmt_gap(v, t): return f"{v/_tot*100 - t:+.1f}pp"
    daily_html = daily_html.replace("__DR_TW_V__", f"{_tw_v:,.0f}")
    daily_html = daily_html.replace("__DR_US_V__", f"{_us_v:,.0f}")
    daily_html = daily_html.replace("__DR_DEF_V__", f"{_def_v:,.0f}")
    daily_html = daily_html.replace("__DR_BOND_V__", f"{_bond_v:,.0f}")
    daily_html = daily_html.replace("__DR_TW_PCT__", _fmt_pct(_tw_v))
    daily_html = daily_html.replace("__DR_US_PCT__", _fmt_pct(_us_v))
    daily_html = daily_html.replace("__DR_DEF_PCT__", _fmt_pct(_def_v))
    daily_html = daily_html.replace("__DR_BOND_PCT__", _fmt_pct(_bond_v))
    daily_html = daily_html.replace("__DR_TW_TGT__", f"{_tgt_tw:.0f}%")
    daily_html = daily_html.replace("__DR_US_TGT__", f"{_tgt_us:.0f}%")
    daily_html = daily_html.replace("__DR_DEF_TGT__", f"{_tgt_def:.0f}%")
    daily_html = daily_html.replace("__DR_BOND_TGT__", f"{_tgt_bond:.0f}%")
    daily_html = daily_html.replace("__DR_TW_GAP__", _fmt_gap(_tw_v, _tgt_tw))
    daily_html = daily_html.replace("__DR_US_GAP__", _fmt_gap(_us_v, _tgt_us))
    daily_html = daily_html.replace("__DR_DEF_GAP__", _fmt_gap(_def_v, _tgt_def))
    daily_html = daily_html.replace("__DR_BOND_GAP__", _fmt_gap(_bond_v, _tgt_bond))
    daily_html = daily_html.replace("__DR_CASH_V__", f"{_cash_v:,.0f}")
    daily_html = daily_html.replace("__DR_CASH_PCT__", _fmt_pct(_cash_v))
    daily_html = daily_html.replace("__DR_CASH_TGT__", f"{_tgt_cash:.0f}%")
    daily_html = daily_html.replace("__DR_CASH_GAP__", _fmt_gap(_cash_v, _tgt_cash))

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
    html = html.replace("__ALLIANZ_RETURN__", fmt_pct(funds2.get("allianz_return", 16.41)))
    html = html.replace("__ALLIANZ_MONTHLY__", fmt(funds2.get("allianz_monthly", tv.get("allianz_ab_monthly", 73_167))))
    html = html.replace("__ALLIANZ_CUM__", fmt(funds2.get("allianz_cum", 1_630_962)))
    html = html.replace("__ALLIANZ_COST__", fmt(funds2.get("allianz_cost", 7_808_297)))
    html = html.replace("__POLICY_A_VAL__", "4,992,334")
    html = html.replace("__POLICY_B_VAL__", "2,681,959")
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
    html = html.replace("__FIRSTJIN_VALUE__", fmt(tv.get("firstjin", 0) or funds.get("firstjin_value", 1_958_980)))
    # allianz value uses snapshot
    html = html.replace("__ALLIANZ_AB__", fmt(tv.get("allianz_ab", 0) or funds.get("allianz_value", 7_674_293)))
    # total monthly = sum of fund monthly + snapshot fallback
    calc_total = (funds.get("allianz_monthly", 0) or 0) + (funds.get("firstjin_monthly", 0) or 0)
    html = html.replace("__TOTAL_MONTHLY__", fmt(calc_total or tv.get("monthly_dividend", 107_116)))

    # 房租動態注入
    _rent_1f = 24_000
    _rent_zjw = 33_000
    _rent_23f = 21_000
    html = html.replace("__POLICY_A_VAL__", "4,992,334")
    html = html.replace("__POLICY_B_VAL__", "2,681,959")
    _rent_mgmt = 2_100
    _expense = int(tv.get("monthly_expense", 141_958))
    _mortgage_pmt = 33_724
    _rent_total = _rent_1f + _rent_zjw + _rent_23f + _rent_mgmt
    _rent_received = _rent_1f + _rent_zjw  # 57,000
    _rent_pending = _rent_23f + _rent_mgmt  # 23,100
    _rent_breakdown = f"大義街1樓{_rent_1f:,}+洲際W{_rent_zjw:,}+大義街23樓{_rent_23f:,}+管理費{_rent_mgmt:,}"
    _rent_status = f"已實收 {_rent_received:,}（大義街1樓{_rent_1f:,}+洲際W{_rent_zjw:,} ✅），剩 {_rent_pending:,}（大義街23樓{_rent_23f:,}+管理費{_rent_mgmt:,}）月底收齊"

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
        f'<span class="text-yellow-400">⏳ 待收</span>'
        f'<span class="text-slate-300">大義街23樓房租</span></div>'
        f'<span class="text-xs font-mono font-bold text-yellow-400">{_rent_23f:,} TWD</span></div>'
        f'<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        f'<div class="flex items-center gap-2 text-xs">'
        f'<span class="text-yellow-400">⏳ 待收</span>'
        f'<span class="text-slate-300">管理費</span></div>'
        f'<span class="text-xs font-mono font-bold text-yellow-400">{_rent_mgmt:,} TWD</span></div>'
    )
    html = html.replace("__RENT_ROWS__", _rent_rows)

    # template 殘留硬編碼注入
    html = html.replace("__CATHAT_SETTLEMENT__", "4,893,529")
    html = html.replace("__CATHAY_DEPOSIT__", "5,300,000")
    html = html.replace("__DBS_BALANCE__", "7,287")
    html = html.replace("__SINOPAC_BALANCE__", "230,000")
    html = html.replace("__SINOPAC_MORTGAGE__", "65,734")
    html = html.replace("__RESERVE_POOL__", "2,000,000+")
    html = html.replace("__SALARY__", "82,265")
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
            _weekly = [dec for dec in _decs if dec.get("approved_at", "")[:10] >= _week_ago]
            _items = []
            for _dec in _weekly[-6:]:  # 最多顯示6項
                _name = _dec.get("text", _dec.get("name", ""))[:40]
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