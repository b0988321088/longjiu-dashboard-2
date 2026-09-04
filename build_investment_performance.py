# -*- coding: utf-8 -*-
"""build_investment_performance.py — 投資績效月報 v2（2026-09-04 定版）

核心：每月投資績效細分為 股票/基金/保單 三類，貸款資金單獨標示。

  每類損益 = 真實市值變化（帳面 − 當類新增投入）＋ 當類配息 − 當類費用
  總績效   = 三類損益合計 − 投資利息（房貸利息+保單借貸利息）− 申購手續費

口徑鐵則：
  · 借貸不創造淨值：轉貸撥款 = 負債同步增加。貸款投入的金額列「新增投入」，
    顯示於帳面但不計績效 → 貸款買的資產若漲跌，只有「漲跌部分」進績效
  · 配息自動分類：安聯/第一金 → 保單；ETF配息/台灣特品 → 股票；其餘基金名 → 基金
  · 校正檔帶入每月新增投入（分三類 + 資金來源），db 有月初基準後可全自動算市值

用法：
  python build_investment_performance.py            # 最近完整月
  python build_investment_performance.py 2026-08
"""
import json, sys, sqlite3, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADJ_FILE = BASE / "investment_performance_adjust.json"

CLASS_KEYS = ["股票", "基金", "保單"]


def classify_dividend(name):
    """配息 key → 類別：安聯/第一金→保單；ETF/台灣特品→股票；其他基金→基金"""
    if "安聯" in name or "第一金" in name:
        return "保單"
    if name.startswith("ETF") or "台灣特品" in name:
        return "股票"
    return "基金"


def load_adjust():
    if ADJ_FILE.exists():
        return json.loads(ADJ_FILE.read_text(encoding="utf-8"))
    return {}


def db_asset_on(db, date):
    r = db.execute(
        "SELECT date, securities, funds, insurance FROM assets "
        "WHERE date <= ? ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    return r



# ── 資金成本儀表板（2026-09-04 使用者核准加入）──
# 利率對照（負債結構穩定；變動時改 investment_performance_adjust.json 的 "資金成本")
DEFAULT_LOANS = [
    # balance_keys: 多 key = 加總（永豐 3 筆分帳號，勿用 mortgage=含國泰 25,082,544）
    {"name": "永豐房貸（洲際W 3筆 2.5%）", "balance_keys": ["mortgage_yy", "mortgage_yydu", "mortgage_xz"], "rate": 0.025},
    {"name": "國泰轉貸（大義街 2.6%）", "balance_keys": ["mortgage_cathay"], "rate": 0.026},
    {"name": "保單借貸（4%）", "balance_keys": ["policy_pledge_loan"], "rate": 0.040},
    {"name": "元大質押（3.92%）", "balance_keys": ["pledge_loan"], "rate": 0.0392},
]


def load_loans(snap, adj_costs=None):
    """讀 snapshot 負債餘額 + 利率 → [(name, balance, rate, monthly_interest)]"""
    adj_costs = adj_costs or {}
    loans = []
    for dl in DEFAULT_LOANS:
        bal = sum(snap.get(k, 0) or 0 for k in dl["balance_keys"])
        if bal <= 0:
            continue
        rate = adj_costs.get(dl["name"], dl["rate"])
        monthly = bal * rate / 12
        loans.append({"name": dl["name"], "balance": bal, "rate": rate, "monthly": monthly})
    return loans


def funding_cost_report(snap, adj_costs=None):
    """輸出資金成本儀表板文字：負債表 + 加權成本 + 配息殖利率 + 淨利差燈號"""
    loans = load_loans(snap, adj_costs)
    total_bal = sum(l["balance"] for l in loans)
    total_m = sum(l["monthly"] for l in loans)
    wacc = total_m * 12 / total_bal if total_bal else 0

    # 投資市值（股票+基金+保單）
    inv = (snap.get("securities_total_market_value") or snap.get("securities_total") or 0) \
        + (snap.get("fund_market_value") or snap.get("funds_total") or 0) \
        + (snap.get("insurance_total") or 0)
    div_m = snap.get("dividend_month_expected") or 100000   # 保守常態月配息
    div_yield = div_m * 12 / inv if inv else 0

    spread = div_yield - wacc
    if spread >= 0.012:
        light = "🟢 利差充足（≥1.2%）→ 現金流安全、套利空間存在"
    elif spread >= 0:
        light = "🟡 利差偏薄（0~1.2%）→ 付息可、擴槓桿謹慎"
    else:
        light = "🔴 利差為負 → 配息不足以 cover 利息，停止加槓桿"
    pay_ok = "✅ 配息可 cover 利息" if div_m >= total_m else "⚠️ 月配息 < 月利息"

    L = ["\n⚖️ 資金成本儀表板（借貸總成本 vs 投資現金流）", "-" * 58]
    for l in loans:
        L.append(f"  {l['name']:26s} {l['balance']/10000:>7.0f}萬 @{l['rate']*100:>4.2f}% → {l['monthly']:>8,.0f}/月")
    L.append(f"  {'有息負債合計':26s} {total_bal/10000:>7.0f}萬            {total_m:>8,.0f}/月")
    L.append(f"  加權平均資金成本 = {wacc*100:.2f}%/年")
    L.append(f"  投資市值（股票+基金+保單） {inv/10000:,.0f}萬")
    L.append(f"  保守月配息 {div_m:,.0f} → 配息殖利率 {div_yield*100:.2f}%/年")
    L.append(f"  淨利差 = {div_yield*100:.2f}% − {wacc*100:.2f}% = {spread*100:+.2f}pp")
    L.append(f"  判斷：{light}")
    L.append(f"  現金流：{pay_ok}（月配息 {div_m:,.0f} vs 月息 {total_m:,.0f}）")
    L.append(f"  註：房貸利息為居住成本；純投資槓桿 = 國泰+保單+元大（若看套利）")
    return "\n".join(L)


def main():
    today = datetime.date.today()
    if len(sys.argv) > 1:
        ym = sys.argv[1]
        y, m = int(ym[:4]), int(ym[5:7])
    else:
        prev = today.replace(day=1) - datetime.timedelta(days=1)
        y, m = prev.year, prev.month

    month_start = datetime.date(y, m, 1)
    month_end = (datetime.date(y, m + 1, 1) - datetime.timedelta(days=1))
    prev_end = month_start - datetime.timedelta(days=1)
    mk = f"{y:04d}-{m:02d}"

    adj = load_adjust()
    a = adj.get(mk, {}) or {}
    adj_invest = a.get("新增投入", {}) or {}       # {類: 金額}
    adj_src = a.get("資金來源", {}) or {}          # {類: "國泰轉貸 1,200萬"}
    adj_mv = a.get("市值變化", {}) or {}           # {類: 真實市值變化(已剔投入)} 校正優先
    adj_div = a.get("配息", {}) or {}              # {類: 金額} 校正優先，否則自動分類
    adj_interest = a.get("利息", {}) or {}         # {"房貸":x,"保單借貸":y}
    adj_fees = a.get("手續費", {}) or {}           # {類: 金額}
    project = a.get("專案收入", 0)
    adj_costs = a.get("資金成本", {})   # {"永豐房貸（洲際W 3筆）": 0.025, ...} 利率覆蓋

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    end_row = db_asset_on(db, month_end.isoformat())
    start_row = db_asset_on(db, prev_end.isoformat())
    db.close()

    mv_reliable = a.get("市值可靠", True)   # false=月初基準不足/投入時點未知，只列現金型報酬

    # ── 各類帳面市值起訖（db 自動） ──
    mv0 = mv1 = None
    db_start_note = ""
    if end_row:
        mv1 = {"股票": end_row[1], "基金": end_row[2], "保單": end_row[3]}
        if start_row:
            mv0 = {"股票": start_row[1], "基金": start_row[2], "保單": start_row[3]}
            db_start_note = start_row[0]
        else:
            db_start_note = f"（db 自 {end_row[0]} 起，無月初基準）"

    # ── 配息自動分類（若校正未帶） ──
    auto_div = {"股票": 0, "基金": 0, "保單": 0}
    dr = (snap.get("dividend_records") or {}).get(mk, {}) or {}
    for k, v in dr.items():
        if isinstance(v, (int, float)):
            auto_div[classify_dividend(k)] += v

    # ── 利息（校正帶入，fallback 月報慣例） ──
    interest_total = sum(adj_interest.values()) if adj_interest else 0

    print(f"\n📊 投資績效月報 {y:04d}-{m:02d}（細分版：股票/基金/保單）")
    print(f"基準：{db_start_note or '校正檔'} → {end_row[0] if end_row else '校正檔'}")
    print("=" * 58)

    grand = 0
    for c in CLASS_KEYS:
        inv = adj_invest.get(c, 0)
        src = adj_src.get(c, "")
        div = adj_div.get(c, auto_div[c])
        fee = adj_fees.get(c, 0)
        print(f"\n■ {c}")
        if mv_reliable:
            # 真實市值變化：校正優先，其次 帳面−投入
            if c in adj_mv:
                real_mv = adj_mv[c]
                gross_mv = real_mv + inv
            elif mv0 and mv1:
                gross_mv = mv1[c] - mv0[c]
                real_mv = gross_mv - inv
            else:
                print(f"  ⚠️ 無基準 → 市值變化需校正檔，先以 0 計")
                real_mv = 0; gross_mv = 0
            print(f"  市值：帳面 {gross_mv:+,.0f}")
            if inv:
                print(f"     − 新增投入 {inv:,.0f}" + (f"（{src}）" if src else "（自有資金）"))
            print(f"     ＝ 真實市值變化 {real_mv:+,.0f}")
        else:
            real_mv = 0
            print(f"  市值：本月基準不足/投入時點未知 → 不計（見備註）")
        print(f"  ＋ 配息實收 {div:+,.0f}")
        if fee:
            print(f"  − 手續費 {-fee:,.0f}")
        sub = real_mv + div - fee
        grand += sub
        print(f"  ＝ {c}損益 {sub:+,.0f}" + ("（含市值）" if real_mv else "（現金型：不含市值）"))

    print("\n" + "-" * 58)
    print(f"三類損益合計        {grand:+,.0f}")
    if interest_total:
        print(f"− 投資利息(合計)    {-interest_total:,.0f}" + (f"（{json.dumps(adj_interest, ensure_ascii=False)}）" if adj_interest else ""))
    print("=" * 58)
    perf = grand - interest_total
    print(f"🎯 投資績效（月）= {perf:+,.0f} ＝ {(perf/10000):+.1f} 萬")
    print("=" * 58)
    if project:
        print(f"📦 專案收入(非常態) {project:+,.0f}（另計不混入）")
    print(funding_cost_report(snap, adj_costs))
    print("口徑：借貸不計績效（投入列帳面、漲跌才計）；配息當月實收；市值含未實現")


if __name__ == "__main__":
    main()
