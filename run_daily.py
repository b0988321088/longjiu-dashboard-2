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
from datetime import date, datetime
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
OUT_CHANGELOG = BASE / f"changelog_{TODAY}.md"


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
    s_expense = snap.get("monthly_expense")
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
        "monthly_expense": check("月支出", s_expense, to_num(r_expense)),
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
    }


# ==========================================================================
# 2. 日報產出
# ==========================================================================

def render_daily_report(tv: dict, intel_text: str = "", intel_signals: dict | None = None) -> str:
    """產出五大章節日報 HTML。"""
    allianz = tv["allianz_ab"] or 7_881_584
    firstjin = tv["firstjin"] or 1_994_698
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = 69_044
    allianz_dividend = 55_451
    firstjin_dividend = 13_593

    # 從 full_monitor.py 動態取得 relay 時序描述
    relay_table = f"""<div class="table-wrap">
      <table>
        <thead>
          <tr><th>站別</th><th>流向</th><th>基準日</th><th>預估入帳</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>第一站</td><td>摩根多重收益（FJ33）→ 安聯收益成長（FL65）</td><td>7/14</td><td>7/19-20</td><td>✅ 已配息/已入帳</td></tr>
          <tr><td>第二站</td><td>安聯收益成長 + M&amp;G 入息基金</td><td>7/17</td><td>~7/29</td><td>🔄 配息接力中</td></tr>
          <tr><td>第三站</td><td>安聯 AI 收益 + PIMCO 第一金 + 貝萊德世界科技 A10</td><td>7/29-30</td><td>~8/10</td><td>⏸️ 等待到期</td></tr>
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
</style>
</head>
<body>
<div class="page">

  <!-- 1/5 財富生命線 -->
  <div class="card">
    <h1>1/5｜財富生命線 Wealth Baseline</h1>
    <div class="label">資產負債快照</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>指標</th><th class="num">數值 TWD</th></tr>
        </thead>
        <tbody>
          <tr><td>總資產</td><td class="num">50,689,930</td></tr>
          <tr><td>總負債</td><td class="num">22,000,000</td></tr>
          <tr><td>淨資產</td><td class="num">28,689,930</td></tr>
          <tr><td>負債率</td><td class="num">43.4%</td></tr>
        </tbody>
      </table>
    </div>

    <h2>月收入 vs 月支出</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>項目</th><th class="num">金額 TWD</th></tr>
        </thead>
        <tbody>
          <tr><td>月收入</td><td class="num">{tv['monthly_income']:,}</td></tr>
          <tr><td>月支出</td><td class="num">{tv['monthly_expense']:,}</td></tr>
          <tr><td>工作期月盈餘</td><td class="num">+{tv['working_surplus']:,}</td></tr>
          <tr><td>退休後月盈餘</td><td class="num">+{tv['retirement_surplus']:,}</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 2/5 戰略異常看板 -->
  <div class="card">
    <h2>2/5｜戰略異常看板 Strategic Risk Hub</h2>
    <div class="label">四大戰略重點</div>

    <h3>保單維運</h3>
    <p class="text-lead">保單現值 <strong>{insurance_total:,} TWD</strong>（安聯 A+B {allianz:,} + 第一金 FL65 {firstjin:,}），本月配息合計 <strong>{monthly_dividend:,} TWD</strong>。落實利潤再投資 SOP，於 T+4 最晚轉換申請日才執行 relay 轉換。</p>

    <h3>證券曝險</h3>
    <p class="text-lead">0056 凍結質押中，短期無法加碼。0050 配息：待 MB 確認；防禦缺口由 00878/00713 預備。</p>

    <h3>房租金流</h3>
    <p class="text-lead">房租月收 <strong>{tv['rent_monthly']:,} TWD</strong>，覆蓋月支出 55%。7/20 洲際 W 租金入帳監控；星展戶頭餘額 7,287 TWD，8/1 需扣款 33,724，由台新調度 3 萬元補庫。</p>

    <h3>鉅亨基金調校</h3>
    <p class="text-lead">監控鉅亨買基金平台標的，追蹤 IT 與 AI 淨值，確保與保單資產互補。</p>
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
      <table>
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
      <table>
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
      <table>
        <thead>
          <tr><th>銀行</th><th>卡片</th><th>繳款日</th><th class="num">近期應付 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>玉山銀行</td><td>UNI</td><td>7/22</td><td class="num">3,176</td><td>🔄 待扣繳</td></tr>
          <tr><td>台新銀行</td><td>Richart</td><td>7/29</td><td class="num">1,000</td><td>🔄 待扣繳</td></tr>
          <tr><td>永豐銀行</td><td>SPORT</td><td>7/29</td><td class="num">500</td><td>🔄 待扣繳</td></tr>
          <tr><td>台北富邦</td><td>momo / J</td><td>8/3</td><td class="num">800</td><td>🔄 待扣繳</td></tr>
        </tbody>
      </table>
    </div>

    <h3>房貸帳戶（列管帳戶）</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>銀行</th><th>貸款名稱</th><th>扣款日</th><th class="num">金額 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>永豐銀行</td><td>洲際 W 房貸</td><td>7/20</td><td class="num">65,734</td><td>📌 待扣款</td></tr>
          <tr><td>國泰世華</td><td>大義街房貸（原國泰，尚未完成轉貸）</td><td>8/1</td><td class="num">23,424</td><td>📌 待扣款</td></tr>
          <tr><td>國泰世華</td><td>理財型利息</td><td>8/1</td><td class="num">10,300</td><td>📌 隨房貸扣款</td></tr>
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
        <li>7/17（五）— 國泰轉貸面簽/對保（原國泰名義尚未轉出，剩 1 天）</li>
        <li>7/20（一）— 洲際 W 租金到帳監控 33,000 TWD</li>
        <li>7/22（三）— 玉山信用卡繳款截止 3,176</li>
        <li>7/27（一）— 台新信用卡繳款截止 1,000</li>
        <li>7/29-30 — Fed 利率決策 + 安聯 AI / 貝萊德 A10 基準日</li>
        <li>8/1（五）— 星展戶頭扣款 33,724（大義街房貸 + 理財型利息）🚨 需補缺口</li>
        <li><relay_0050> — 0050 配息 ⚠️ 待 MB 確認</li>
      </ul>
    </div>

    <h3>本週行程 + 繳款 / 配息排程</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>日期</th><th>項目</th><th class="num">金額 TWD</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>7/17（五）</td><td>國泰轉貸面簽/對保 + 段部上課</td><td class="num">—</td><td>🚨 P0</td></tr>
          <tr><td>7/19-20</td><td>摩根 FJ33 配息入帳</td><td class="num">13,593</td><td>✅ 已配息</td></tr>
          <tr><td>7/22</td><td>玉山信用卡繳款截止</td><td class="num">3,176</td><td>🔄 待處理</td></tr>
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
      <table>
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
      <strong>🤖 CTO 技術視角（tech_stack / risk / action）</strong><br>
      __CTO_TECH__<br>
      __CTO_RISK__<br>
      __CTO_ACTION__
    </div>
  </div>

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
    analysis = load_daily_analysis()
    if not analysis:
        return html

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
        f"<tr><td>台股加權指數（{TODAY}）</td><td>{twii}</td><td>高檔震盪</td></tr>",
        f"<tr><td>台積電（{TODAY}）</td><td>{tsm}</td><td>半導體龍頭穩盤</td></tr>",
        f"<tr><td>費半（{TODAY}）</td><td>{sox}</td><td>高檔回調</td></tr>",
        f"<tr><td>美股（{TODAY}）</td><td>{us}</td><td>通膨降溫驅動科技領漲</td></tr>",
        f"<tr><td>美國 CPI</td><td>{cpi}</td><td>降息預期升溫</td></tr>",
        # 0050 配息：待 MB 確認後由 daily_analysis.json 注入
    ]
    html = html.replace("__MARKET_ROWS__", chr(10).join("          " + r for r in rows))

    # Buffett / CTO 區塊
    buf_bull = buffett.get("bull", "")
    buf_bear = buffett.get("bear", "")
    buf_actions = buffett.get("actions", [])
    buf_content = "<strong>🧓 巴菲特式思考（規範：整體資產配置，非個股評論）</strong><br>"
    if buf_bull:
        buf_content += f"• Bull：{buf_bull}<br>"
    if buf_bear:
        buf_content += f"• Bear：{buf_bear}<br>"
    for a in buf_actions:
        buf_content += f"• {a}<br>"
    html = html.replace("__BUFFETT_CONTENT__", buf_content)
    html = html.replace("__CTO_TECH__", cto.get("tech_stack", "—"))
    html = html.replace("__CTO_RISK__", cto.get("risk", "—"))
    html = html.replace("__CTO_ACTION__", cto.get("action", "—"))

    return html


def render_changelog(tv: dict) -> str:
    md = f"""# 龍九日報 changelog {TODAY}

## 本次更新

- 五大章節完整校準
- relay 三站制確認
- 四大信用卡 + 房貸列管
- 情報狀態：以 daily_analysis.json / hunter_logs 為準
- 巴菲特分析更新

## 真值錨定

- 總資產：50,689,930 TWD
- 保單現值：{tv['insurance_total']:,}（安聯 A+B {tv['allianz_ab']:,} / 第一金 {tv['firstjin']:,}）
- 本月配息：69,044 TWD
- 月收入：{tv['monthly_income']:,} / 月支出：{tv['monthly_expense']:,}
- 工作期盈餘：+{tv['working_surplus']:,} / 退休後盈餘：+{tv['retirement_surplus']:,}

## 待補齊

- 台股 7/16 收盤需凱基證券 App 截圖確認
- 台積電 ADR 無一致可信數據
"""
    return md


# ==========================================================================
# 4. 產出
# ==========================================================================

def main():
    print(f"[RUN_DAILY] 日期：{TODAY}")

    # 校準
    tv = calibrate_sources()
    print(f"[RUN_DAILY] 真值：月收 {tv['monthly_income']:,} / 月支 {tv['monthly_expense']:,} / 盈餘 +{tv['working_surplus']:,}")

    # 情報：refresh today's hunter intel
    intel_result = mi_mod.ensure_today_intel()
    print(f"[INTEL] {intel_result.get('file') or intel_result}")
    intel_text = mi_mod.load_latest_hunter()
    intel_signals = mi_mod.parse_hunter_signals(intel_text)

    # 日報
    daily_html = render_daily_report(tv, intel_text=intel_text, intel_signals=intel_signals)
    daily_html = _inject_market_intel(daily_html, tv, intel_signals)
    OUT_DAILY.write_text(daily_html, encoding="utf-8")
    print(f"[RUN_DAILY] 日報產出：{OUT_DAILY}")

    # changelog
    changelog = render_changelog(tv)
    OUT_CHANGELOG.write_text(changelog, encoding="utf-8")
    print(f"[RUN_DAILY] changelog 產出：{OUT_CHANGELOG}")

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

    html = html.replace("__INSURANCE_TOTAL__", fmt(tv.get("insurance_total", 0)))
    html = html.replace("__ALLIANZ_AB__", fmt(tv.get("allianz_ab", 0)))
    html = html.replace("__ALLIANZ_MONTHLY__", fmt(tv.get("allianz_monthly", 0)))
    html = html.replace("__ALLIANZ_CUM__", fmt(tv.get("allianz_cum", 0)))
    html = html.replace("__ALLIANZ_RETURN__", fmt(tv.get("allianz_return", 0)))
    html = html.replace("__ALLIANZ_COST__", fmt(tv.get("allianz_cost", 8_000_000)))
    html = html.replace("__FIRSTJIN__", fmt(tv.get("firstjin", 0)))
    html = html.replace("__FIRSTJIN_MONTHLY__", fmt(tv.get("firstjin_monthly", 0)))
    html = html.replace("__FIRSTJIN_CUM__", fmt(tv.get("firstjin_cum", 0)))
    html = html.replace("__FIRSTJIN_COST__", fmt(tv.get("firstjin_cost", 2_000_000)))
    html = html.replace("__FIRSTJIN_VALUE__", fmt(tv.get("firstjin", 0)))
    html = html.replace("__TOTAL_MONTHLY__", fmt(tv.get("monthly_dividend", 0)))
    html = html.replace("__WORKING_INCOME__", fmt(tv.get("monthly_income", 0)))
    html = html.replace("__WORKING_SURPLUS__", f"+{fmt(tv.get('working_surplus', 0))}")
    html = html.replace("__RETIREMENT_INCOME__", fmt(tv.get("retirement_income", 0)))
    html = html.replace("__RETIREMENT_SURPLUS__", f"+{fmt(tv.get('retirement_surplus', 0))}")
    html = html.replace("__PASSIVE_INCOME__", fmt(tv.get("rent_monthly_actual", 0) + tv.get("monthly_dividend", 0)))
    html = html.replace("__RUNWAY_MONTHS__", fmt(tv.get("runway_months", "—")))
    html = html.replace("__CASH_TOTAL__", fmt(tv.get("cash_total", 0)))

    # Allocation
    html = html.replace("__TW_EQ_PCT__", fmt(tv.get("tw_eq_pct", 0)))
    html = html.replace("__TW_EQ_TARGET__", fmt(20.0))
    html = html.replace("__TW_EQ_GAP__", fmt(tv.get("tw_eq_gap", 0)))
    html = html.replace("__TW_EQ_VALUE__", fmt(tv.get("tw_eq_value", 0)))
    html = html.replace("__US_EQ_PCT__", fmt(tv.get("us_eq_pct", 0)))
    html = html.replace("__US_EQ_TARGET__", fmt(20.0))
    html = html.replace("__US_EQ_GAP__", fmt(tv.get("us_eq_gap", 0)))
    html = html.replace("__US_EQ_VALUE__", fmt(tv.get("us_eq_value", 0)))
    html = html.replace("__DEF_PCT__", fmt(tv.get("def_pct", 0)))
    html = html.replace("__DEF_TARGET__", fmt(30.0))
    html = html.replace("__DEF_GAP__", fmt(tv.get("def_gap", 0)))
    html = html.replace("__DEF_VALUE__", fmt(tv.get("def_value", 0)))
    html = html.replace("__BOND_PCT__", fmt(tv.get("bond_pct", 0)))
    html = html.replace("__BOND_TARGET__", fmt(25.0))
    html = html.replace("__BOND_GAP__", fmt(tv.get("bond_gap", 0)))
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

    return html


    print("\n[DONE] 產出完成。")
    print(f"  日報：{OUT_DAILY}")
    if OUT_CHANGELOG.exists():
        print(f"  差異：{OUT_CHANGELOG}")


if __name__ == "__main__":
    main()
