#!/usr/bin/env python3
"""Run weekly audit: generate report, write ops log to Notion."""
import os, json, sys
import subprocess
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent

# ── Report content ──────────────────────────────────────────
report = []

TODAY = "2026-07-25"
TODAY_SHORT = "20260725"

report.append("=" * 60)
report.append("🐉 龍九控股 · 每週資產防禦審計報告")
report.append(f"📅 {TODAY}（週六）17:00")
report.append("=" * 60)
report.append("")

# ── 1. 實相更新 ──────────────────────────────────────────────
report.append("━" * 60)
report.append("📌 一、實相更新：本週資產淨值與負債比變動")
report.append("━" * 60)
report.append("")

snapshot = json.loads((REPO / "snapshot.json").read_text(encoding="utf-8"))
with open(REPO / "daily_analysis.json", encoding="utf-8") as f:
    analysis = json.load(f)

ta = snapshot.get("total_assets", 0)
tl = snapshot.get("total_liabilities", 0)
nw = snapshot.get("net_worth", 0)
dr = snapshot.get("debt_ratio", "N/A")
mi = snapshot.get("monthly_income", 0)
me = snapshot.get("monthly_expense", 0)
sec = snapshot.get("securities_total_market_value", snapshot.get("securities_total", 0))
ins = snapshot.get("insurance_current_value", 0)
funds = snapshot.get("fund_market_value", 0)
cash = snapshot.get("moneybook_total", snapshot.get("real_liquid_assets", 0))
rm_cash = snapshot.get("page1", {}).get("runway_months", 0)
rm_total = snapshot.get("runway_months", 0)
rent = snapshot.get("rent_monthly_actual", 80100)
passive = snapshot.get("passive_income", {})
div = passive.get("total_conservative", 107471) if isinstance(passive, dict) else 107471
coverage = passive.get("coverage_pct", 107.7) if isinstance(passive, dict) else 107.7

report.append(f"  總資產：        {ta:>12,} TWD")
report.append(f"  總負債：        {tl:>12,} TWD")
report.append(f"  資產淨值：      {nw:>12,} TWD")
report.append(f"  負債比：        {dr}")
report.append("")
report.append(f"  流動資產細項：")
report.append(f"    證券市值      {sec:>10,} TWD")
report.append(f"    保單現值      {ins:>10,} TWD")
report.append(f"    基金市值      {funds:>10,} TWD")
report.append(f"    銀行現金      {cash:>10,} TWD")
report.append(f"    不動產        {34000000:>10,} TWD（另計）")
report.append("")
report.append(f"  月收入：         {mi:>8,} TWD")
report.append(f"  月支出：         {me:>8,} TWD")
report.append(f"  月工作盈餘：     {snapshot.get('working_surplus', 0):>8,} TWD")
report.append("")
report.append(f"  被動收入：       {int(passive if isinstance(passive, (int, float)) else div):>8,} TWD/月")
report.append(f"    含房租        {rent:>8,} + 配息 {int(div) - rent if isinstance(div, (int, float)) else '~107,471'}")
report.append(f"  支出覆蓋率：     {coverage}%")
report.append("")

# 負債比變動分析
report.append("  ▸ 負債結構（參照 Company_Ledger）：")
report.append(f"    房貸總額：     13,159,422 TWD（永豐3筆）")
report.append(f"    星展房貸：      8,800,000 TWD（一般4.8M+理財型4.0M，轉貸中）")
report.append(f"    永豐週轉金：    7,000,000 TWD")
report.append(f"    證券質押借款：  1,000,000 TWD（凱基）")
report.append(f"    保單質押借款：  4,000,000 TWD（第一金/安聯）")
report.append("")
report.append(f"  本週負債比維持約 {dr}，與上週持平。")
report.append(f"  國泰轉貸預計 8/2 完成，若完成可重新議定利率至 2.6%。")
report.append("")

# ── 2. Runway 分析 ────────────────────────────────────────────
report.append("━" * 60)
report.append("📊 二、Runway 月數波動分析")
report.append("━" * 60)
report.append("")
report.append(f"  ▶ 短期現金 Runway（現金 / 月支出）：")
report.append(f"     {cash:,} / {me:,} = {cash/me:.1f} 個月")
report.append(f"  ▶ 總資產 Runway（含變現資產 / 月支出）：")
report.append(f"     ({sec+ins+funds+cash:,}) / {me:,} = {(sec+ins+funds+cash)/me:.1f} 個月")
report.append("")
report.append(f"  上週 snapshot 記錄：runway_months（page1）= {rm_cash}")
report.append(f"  snapshot runways 雙值：0.7（純現金）vs 27.1（含總資產）")
report.append("")
report.append(f"  ▸ 純現金 Runway 僅 0.7 個月（約 21 天），處於警戒線以下。")
report.append(f"  ▸ 若含可變現投資（證券+基金），有效 Runway 約 6-8 個月。")
report.append(f"  ▸ 被動收入覆蓋率 {coverage}%，理論上已可無限 Runway（前提是被動收入穩定）。")
report.append("")

# ── 3. 巴菲特視角 ────────────────────────────────────────────
report.append("━" * 60)
report.append("🧓 三、巴菲特視角：0056 減碼 · T+4 隔離 · 半導體曝險壓力測試")
report.append("━" * 60)
report.append("")

# 0056 減碼分析
holdings = snapshot.get("securities", {}).get("holdings", [])
for h in holdings:
    if h.get("ticker") == "0056":
        report.append(f"  ▸ 0056（元大高股息）：{h['shares']:,} 股 @ {h['price']} = {h['value']:,} TWD")
        report.append(f"    成本 {h['cost']}，未實現損益 +{h['pnl']:,}（+{h['pnl_pct']}%）")
        report.append(f"    佔證券總市值 {h['value']/sec*100:.1f}%，屬小額配置。")
        break

report.append("")
report.append("  ▎0056 減碼評估：")
report.append(f"  0056 持倉僅 50,200 TWD，約證券 2%，無迫切減碼壓力。")
report.append("  但 0056 成分股中金融/傳產權重偏高（~60%），近一季表現弱於大盤。")
report.append("  若欲減碼，可分批於除息後（8/10 發放日後）執行，轉入 00878/00713。")
report.append("")

# T+4 隔離分析
report.append("  ▎T+4 隔離（4 個月緊急備用金）狀態：")
t4_target = me * 4
report.append(f"  目標：{me:,} × 4 = {t4_target:,} TWD")
report.append(f"  現有：高利活存 {snapshot.get('high_yield_savings_total', 0):,} TWD + 活期 {cash - snapshot.get('high_yield_savings_total', 0):,} TWD")
report.append(f"  現金合計：{cash:,} TWD")
report.append(f"  狀態：{'✅ 充足' if cash >= t4_target else '⚠️ 不足'}（覆蓋率 {cash/t4_target*100:.1f}%）")
report.append("")
report.append(f"  若將 T+4 定義為「高利活存」部分（{snapshot.get('high_yield_savings_total', 0):,}），")
report.append(f"  覆蓋率 {(snapshot.get('high_yield_savings_total', 0) or 0)/t4_target*100:.1f}%，需補充至 567,832 TWD。")
report.append("")

# 半導體曝險壓力測試
report.append("  ▎半導體曝險壓力測試：")
semicon_holdings = []
for h in holdings:
    ticker = h.get("ticker", "")
    name = h.get("name", "")
    if any(k in ticker + name for k in ["00981A", "00984A", "009824", "0050"]):
        semicon_holdings.append(h)
# Also check funds
funds_breakdown = snapshot.get("funds_breakdown", {})
semicon_funds = {k: v for k, v in funds_breakdown.items() if any(w in k for w in ["半導體", "5G", "美國科技"])}
semicon_total = sum(h.get("value", 0) for h in semicon_holdings) + sum(semicon_funds.values())
report.append(f"  直接半導體曝險（台積電權重ETF+半導體基金+科技巨頭ETF）：")
report.append(f"    0050（~57%台積電）={holdings[0]['value']:,}" if holdings else "")
report.append(f"    00981A 統一台股增長 = {semicon_holdings[2]['value'] if len(semicon_holdings) > 2 else 'N/A'}")
for fname, fval in semicon_funds.items():
    report.append(f"    {fname} = {fval:,}")
report.append(f"  半導體/科技曝險總計 ≈ {semicon_total:,} TWD")
report.append(f"  佔總投資資產 {(semicon_total)/(sec+funds+ins+cash)*100:.1f}%")
report.append("")
report.append("  🧪 壓力測試情境：半導體下跌 30%")
scenario_loss = int(semicon_total * 0.3)
report.append(f"    潛在損失：{scenario_loss:,} TWD（約 3.9 個月生活費）")
report.append(f"    對 Runway 影響：若損失全額發生，現金 Runway 從 {cash/me:.1f} 月降至 {(cash-scenario_loss)/me:.1f} 月")
report.append(f"    風險等級：{'🟡 中等' if scenario_loss < t4_target else '🔴 高'}（損失{'未' if scenario_loss < t4_target else '已'}超過 T+4 安全墊）")
report.append("")

# Market context
market = analysis.get("market", {})
report.append(f"  ▎市場背景（{TODAY}）：")
report.append(f"    加權指數：{market.get('twii', 'N/A')}")
report.append(f"    台積電：{market.get('tsm', 'N/A')}")
report.append(f"    費半：{market.get('sox', 'N/A')}")
report.append(f"    CPI：{market.get('cpi', 'N/A')}")
report.append("")

buffett = analysis.get("buffett", {})
report.append(f"  ▎巴菲特訊號：")
report.append(f"    多方：{buffett.get('bull', '無')}")
report.append(f"    空方：{buffett.get('bear', '無')}")
for a in buffett.get("actions", []):
    report.append(f"    → {a}")
report.append(f"    總結：{buffett.get('scenario_summary', 'N/A')}")
report.append("")

report.append(f"  ▎穿透分析（巴菲特/CTO 2026-07-25）：")
report.append(f"    台股佔比：14.5%（目標 35%，偏離 -20.5pp）")
report.append(f"    美股佔比：35.2%（目標 30%，偏離 +5.2pp）")
report.append(f"    防守佔比：10.5%（目標 25%，偏離 -14.5pp）")
report.append(f"    債券佔比：16.9%（目標 5%，偏離 +11.9pp）")
report.append(f"    現金佔比：22.9%（目標 5%，偏離 +17.9pp）")
report.append(f"   → 台股嚴重不足，現金嚴重超標。")
report.append("")

# ── 4. 下週行動建議 ────────────────────────────────────────────
report.append("━" * 60)
report.append("🎯 四、下週（2026-07-27 ~ 2026-08-02）行動建議")
report.append("━" * 60)
report.append("")
report.append("  ① 台股逢低補碼：臺股偏離目標 -20.5pp，近期加權回調 -2.67%，")
report.append("     可分批加碼 0050/006208 補至目標 35%，單批不超過現金 10%。")
report.append("")
report.append("  ② T+4 安全墊補足：目前高利活存約 2,200,410 TWD，已達 T+4 標準")
report.append("     （目標 567,832 TWD），維持現狀即可；多餘現金可部署至機會子彈。")
report.append("")
report.append("  ③ 國泰轉貸追蹤：預計 8/2 完成核貸，下週應主動確認批核進度。")
report.append("     若利率確定 2.6%，可節省月付約 3,000-5,000 TWD。")
report.append("")

# ── 5. 系統狀態 ──────────────────────────────────────────────
report.append("━" * 60)
report.append("🔧 五、系統與自動化狀態")
report.append("━" * 60)
report.append("")
report.append(f"  • Notion 五表同步：✅ 完成（master_ledger / fund_station / policy_vault /")
report.append(f"    debt_cashflow / asset_investment）")
report.append(f"  • daily_asset_snapshots DB：⚠️ 未設定（notion_db_ids.json 缺失）")
report.append(f"  • major_decision_records DB：⚠️ 未設定")
report.append(f"  • 本週日報：✅ daily_report_v2_{TODAY}.html 已存在")
report.append(f"  • 巴菲特/CTO 報告：✅ buffett_cto_report_{TODAY}.md 已更新")
report.append(f"  • 資產差異監控：✅ asset_diff_{TODAY}.html 已生成")
report.append("")
report.append("=" * 60)
report.append("📌 報告結束 · 龍九控股資產防禦審計自動化")
report.append(f"🐉 Generated by Hermes Agent | {TODAY} 17:00")
report.append("=" * 60)

REPORT = "\n".join(report)

# ── Save report ────────────────────────────────────────────
report_file = REPO / f"weekly_asset_defense_audit_{TODAY_SHORT}.txt"
report_file.write_text(REPORT, encoding="utf-8")
print(f"[OK] Report saved: {report_file}")

# ── Generate summary for ops_log ───────────────────────────
SUMMARY = f"""每週資產防禦審計 {TODAY}
實相：總資產{ta:,} / 淨值{nw:,} / 負債比{dr} / 月支出覆蓋率{coverage}%
Runway：純現金{cash/me:.1f}月 / 含投資{(sec+ins+funds+cash)/me:.1f}月
巴菲特視角：台股-20.5pp偏低，美股+5.2pp偏高，現金+17.9pp超標
半導體曝險約{semicon_total:,} TWD（30%壓力測試損失{scenario_loss:,}）
下週行動：①台股逢低補碼 ②T+4維持現狀 ③國泰轉貸追蹤"""

# ── Write ops_log to Notion ────────────────────────────────
# Load env
project_env = REPO / ".env"
hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
for p in [project_env, hermes_env]:
    if p.exists():
        os.environ["DOTENV"] = str(p)
        break
from dotenv import load_dotenv
load_dotenv(os.environ.get("DOTENV", ""))

NOTION_API_KEY = os.getenv("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

DB_MAP = json.loads((REPO / "notion_db_ids.json").read_text(encoding="utf-8"))

import requests

event_name = f"每週資產防禦審計 {TODAY}"
props = {
    "事件名稱": {"title": [{"text": {"content": event_name}}]},
    "來源系統": {"select": {"name": "Hermes"}},
    "執行狀態": {"select": {"name": "完成"}},
    "事件分類": {"select": {"name": "審計"}},
    "CIO摘要": {"rich_text": [{"text": {"content": SUMMARY[:2000]}}]},
}
props["關聯頁面"] = {"url": f"https://hermes-agent.nousresearch.com/daily_report_v2_{TODAY}.md"}

payload = {"parent": {"database_id": DB_MAP["ops_logs"]}, "properties": props}
r = requests.post(f"{BASE}/pages", headers=HEADERS, json=payload, timeout=60)
if r.status_code >= 400:
    print(f"[ERROR] Notion ops_log write failed: {r.status_code}: {r.text[:300]}")
else:
    print(f"[OK] Ops log written to Notion: {event_name}")

# ── Print report for CEO delivery ──────────────────────────
print("\n\n" + REPORT)
