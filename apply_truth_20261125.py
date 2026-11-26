#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_truth_20261125.py — 2026-11-25 真值日批次寫入（一次性工具，不進版控）

來源：
  1. 安聯 App「我的投資」11/25 13:31 查詢（A 4,796,376／B 2,340,418，逐檔 3+5 檔加總一致）
  2. 國泰基金投資頁 11/25 截圖（參考現值 11,418,728，淨值日 2026/11/24）
  3. Moneybook ZIP 2026/10/26–11/25（帳戶 CSV）
  4. 凱基 App 自選報價 11/25 13:34 截圖（10 檔）＋ Yahoo 收盤補 5 檔

規則：截圖為真值；TWSE 官方收盤公布後由 apply_securities_close.py 冪等覆核。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

# ── 1. 安聯 A/B ────────────────────────────────────────────────
A_FUNDS = {
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 2556377,
    "USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)": 676416,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 1563583,
}
B_FUNDS = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 236561,
    "NTDET0010 元大台灣卓越50": 886376,
    "USDEQ3490 安聯收益成長基金-AM月收類股(美元)": 470713,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 617734,
    "USDEQ6730 貝萊德世界黃金基金A10美元(總報酬穩定配息)": 129034,
}
A_TOTAL = sum(A_FUNDS.values())      # 4,796,376
B_TOTAL = sum(B_FUNDS.values())      # 2,340,418

# ── 2. 國泰直購基金（淨值日 2026/11/24）────────────────────────
CATHAY = {
    "富達全球動能多元B股C月配息美元": 5502929,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 4954902,
    "聯博全球多元收益AD美元月配": 960897,
}
CATHAY_TOTAL = sum(CATHAY.values())  # 11,418,728
CATHAY_NAV_DATE = "2026-11-24"

# ── 3. 現金（Moneybook 帳戶 CSV 台幣活存；國泰 20,776 誤列排除）──
CASH_DETAIL = {
    "北台中活儲存款-優質薪轉儲蓄存款": 100.0,
    "民權活儲存款-證券": 1210.0,
    "文心綜活儲存款-薪轉": 182678.0,
    "敦南Richart數位一般帳戶": 104988.0,
    "敦南數位二類異業帳戶": 13.0,
    "敦南Richart子帳戶": 509467.0,
    "臺幣綜存": 59044.0,
    "市政分行活期儲蓄存款": 20.0,
    "營業部DAWHO活期儲蓄存款": 369606.0,
    "數位活儲": 40609.0,
    "Digital Savings Account": 739.0,
    "我的儲蓄口袋": 0.0,
    "金如意": 4.13,
    "iLEO帳戶": 716.0,
    "活期儲蓄存款": 844329.0,
    "數位存款帳戶２類": 2.0,
    "證券活期儲蓄存款": 0.0,
}

# ── 4. 證券收盤 2026-11-25 ─────────────────────────────────────
# 前 10 檔＝凱基 App 13:34 截圖（收盤）；後 5 檔截圖未涵蓋＝Yahoo 收盤
PRICES = {
    "0050": (90.20, "Yahoo"),
    "006208": (202.95, "Yahoo"),
    "009816": (13.35, "Yahoo"),
    "00646": (74.35, "Yahoo"),
    "00713": (59.00, "Yahoo"),
    "00878": (28.60, "凱基截圖"),
    "0056": (45.66, "凱基截圖"),
    "00981A": (20.53, "凱基截圖"),
    "00984A": (11.29, "凱基截圖"),
    "00919": (27.87, "凱基截圖"),
    "00918": (29.43, "凱基截圖"),
    "00888": (25.62, "凱基截圖"),
    "00983D": (9.86, "凱基截圖"),
    "00927": (27.39, "凱基截圖"),
    "2610": (22.00, "凱基截圖"),
}
PRICE_DATE = "2026-11-25"
TODAY = "2026-11-25"


def main() -> int:
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    chg = []

    from asset_sync import SYNONYM_GROUPS as G

    def setg(g, v):
        for k in G[g]:
            snap[k] = v

    # ① 安聯（同義群組全寫，否則 --check 自癒會用舊 master 蓋回）
    setg("allianz_policy_a", A_TOTAL)
    setg("allianz_policy_b", B_TOTAL)
    setg("allianz_combined", A_TOTAL + B_TOTAL)
    ib = snap.setdefault("insurance_breakdown", {})
    ib["policy_a_total"] = float(A_TOTAL)
    ib["policy_b_total"] = float(B_TOTAL)
    ib["allianz_ab_total"] = A_TOTAL + B_TOTAL
    ib["policy_a_funds"] = A_FUNDS
    ib["policy_b_funds"] = B_FUNDS
    fj = snap.get("firstjin_fl65_current_value") or snap.get("firstjin_current_value") or 0
    snap["insurance"] = A_TOTAL + B_TOTAL + fj
    setg("insurance_total", snap["insurance"])
    chg.append(f"安聯 A {A_TOTAL:,}／B {B_TOTAL:,}／保險總 {snap['insurance']:,}")

    # ② 國泰直購
    fb = snap.setdefault("funds_breakdown", {})
    fb["國泰直購"] = CATHAY
    fb["國泰直購_小計"] = CATHAY_TOTAL
    for key in ("funds_cathay_breakdown", "fund_breakdown_cathay"):
        snap[key] = dict(CATHAY)
    setg("funds_cathay", CATHAY_TOTAL)
    ju = fb.get("鉅亨平台合計") or fb.get("平台小計") or 0
    funds_total = CATHAY_TOTAL + ju
    setg("funds_total", funds_total)
    chg.append(f"國泰直購 {CATHAY_TOTAL:,}／基金總 {funds_total:,}（鉅亨 {ju:,}）")

    # ③ 現金
    snap["cash_detail"] = CASH_DETAIL
    excl = ("外幣", "信用卡", "房貸", "卡", "房屋貸款", "貸款", "透支", "質押")
    cash = sum(v for k, v in CASH_DETAIL.items() if v > 0 and not any(x in k for x in excl))
    setg("cash_total", cash)
    snap["moneybook_total"] = cash
    snap["cash_source"] = {"date": TODAY, "note": "Moneybook 帳戶 CSV 匯入（cash_detail）"}
    chg.append(f"現金 {cash:,.2f}")

    # ④ 證券
    sec = snap["securities"]
    old_total = float(sec.get("total_market_value") or 0)
    new_total = 0.0
    cost_sum = 0.0
    for h in sec["holdings"]:
        t = h["ticker"]
        px, src = PRICES[t]
        h["price"] = px
        h["value"] = h["market_value"] = round(h["shares"] * px, 2)
        h["cost"] = h.get("cost", 0) or 0
        cost_sum += h["cost"]
        h["pnl"] = round(h["value"] - h["cost"], 2)
        h["pnl_pct"] = round(h["pnl"] / h["cost"] * 100, 2) if h["cost"] else 0.0
        h["price_date"] = PRICE_DATE
        h["price_type"] = "收盤"
        h["price_source"] = f"{src} 2026-11-25 收盤"
        new_total += h["value"]
    new_total = round(new_total, 2)
    sec["total_market_value"] = new_total
    sec["unrealized_pnl"] = round(new_total - cost_sum, 2)
    sec["unrealized_pnl_pct"] = round(sec["unrealized_pnl"] / cost_sum * 100, 2) if cost_sum else 0.0
    sec["today_pnl"] = round(new_total - old_total, 2)
    sec["today_pnl_pct"] = round(sec["today_pnl"] / old_total * 100, 2) if old_total else 0.0
    sec["as_of"] = f"{PRICE_DATE} 13:30"
    sec["price_date"] = PRICE_DATE
    sec["price_type"] = "收盤（凱基截圖 10 檔＋Yahoo 補 5 檔）"
    sec["source"] = "凱基證券 App 自選報價 13:34 截圖（使用者提供 2026-11-25）＋ Yahoo 收盤補 5 檔"
    sec["provisional"] = True
    sec["note"] = (
        f"2026-11-25 收盤：10 檔取自凱基 App 13:34 截圖、0050/006208/009816/00646/00713 截圖未涵蓋改取 Yahoo 收盤。"
        f"表頭 {new_total:,.0f}；成本合計 {cost_sum:,.0f}；未實現 {sec['unrealized_pnl']:,.0f}（{sec['unrealized_pnl_pct']:.2f}%）。"
        f"TWSE 官方收盤公布後以 apply_securities_close.py --date 2026-11-25 冪等覆核（差異預期 ≤ 數百元）。"
    )
    setg("securities_total", new_total)
    chg.append(f"證券 {old_total:,.0f} → {new_total:,.0f}（{sec['today_pnl']:+,.0f}）")

    # ⑤ 淨值日／匯入日
    snap.setdefault("fund_nav_dates", {})["國泰直購（富達/聯博/B11）"] = CATHAY_NAV_DATE
    snap["policy_valuation_dates"] = {
        "allianz": CATHAY_NAV_DATE,
        "note": "2026-11-25 13:31 安聯 App 截圖（畫面未顯示淨值日；依 T+1 與國泰基金同批推定 2026-11-24）",
    }
    sid = snap.setdefault("source_import_dates", {})
    for k in ("現金／銀行（Moneybook）", "證券部位", "保單 安聯 A/B（App）",
              "基金 國泰直購（富達/聯博/B11）", "Moneybook 明細"):
        sid[k] = TODAY

    # ⑥ 總資產
    ta = snap["insurance"] + new_total + funds_total + cash
    snap["total_assets"] = round(ta, 2)
    snap["net_worth"] = round(ta - (snap.get("total_liabilities") or 0), 2)

    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    for c in chg:
        print("✅", c)
    print(f"✅ 總資產 {ta:,.2f}／淨值 {snap['net_worth']:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
