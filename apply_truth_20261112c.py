#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-12 10:21 台股盤中真值套用（使用者 Telegram 兩張截圖）

表頭：總市值 2,762,260｜當日 +18,270（+0.67%）｜未實現 +292,750（+11.85%）｜已實現 +23,460（+27.34%）
⚠️ 逐檔「市值」欄合計 2,762,430（與表頭差 170）、成本×股數推得未實現 292,960（與表頭差 210），
   差額來自 009816／0056／00918 三行報價時點與表頭不同步 → 以**逐檔**為準存檔（維持「逐檔＝總值」），
   表頭值寫入 note；13:30 官方收盤覆蓋時一併歸零。
⚠️ 盤中價非官方收盤 → provisional=True，13:30 後須以 TWSE 收盤覆蓋並重跑 check_securities_integrity。
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

# ticker: (股價, 券商市值欄)
PX = {
    "0050": (104.10, 208200), "006208": (238.80, 477600), "009816": (15.47, 247360),
    "00646": (78.70, 78700), "00713": (63.30, 126600), "00878": (33.61, 504150),
    "0056": (53.85, 53800), "00981A": (25.46, 203680), "00984A": (14.10, 141000),
    "00919": (31.34, 219380), "00918": (33.29, 33280), "00888": (30.20, 181200),
    "00983D": (10.00, 200000), "00927": (32.14, 64280), "2610": (23.20, 23200),
}
HEADER_TOTAL, HEADER_UNREAL, HEADER_DAY_CHG = 2762260, 292750, 18270
REALIZED, REALIZED_PCT = 23460, 27.34

old = snap["securities"]["holdings"]
holdings, sec_bd, tot, unr, day_chg = [], {}, 0, 0, 0
for h in old:
    t = h["ticker"]
    px, mv = PX[t]
    sh, avg = h["shares"], h["cost_avg"]
    cost = round(avg * sh)
    pnl = round(mv - cost)
    tot += mv
    unr += pnl
    day_chg += round(sh * (px - float(h.get("price") or px)))
    sec_bd[t] = mv
    holdings.append({**h, "price": px, "value": mv, "market_value": mv, "cost": cost,
                     "pnl": pnl, "pnl_pct": round(pnl / cost * 100, 2),
                     "price_date": "2026-11-12", "price_type": "盤中10:21",
                     "price_source": "券商持股即時報價截圖（10:21 盤中）"})
assert len(holdings) == 15, len(holdings)
assert tot == sum(v for _, v in PX.values()), tot

for k in ("securities_total_market_value", "securities_total", "securities_market",
          "securities_current_value", "securities_market_value", "securities_current",
          "total_stock_value"):
    snap[k] = tot
snap["securities_unrealized_pnl"] = unr
snap["securities"] = {
    "total_market_value": tot, "unrealized_pnl": unr,
    "unrealized_pnl_pct": round(unr / (tot - unr) * 100, 2),
    "realized_pnl": REALIZED, "realized_pnl_pct": REALIZED_PCT,
    "holdings": holdings, "as_of": "2026-11-12", "price_date": "2026-11-12",
    "price_type": "盤中（10:21 即時報價）", "provisional": True,
    "source": "券商持股即時報價截圖 10:21（盤中，非官方收盤）",
    "note": (f"2026-11-12 10:21 盤中截圖：15 檔逐檔市值合計 {tot:,}、未實現 +{unr:,}"
             f"（+{round(unr/(tot-unr)*100,2)}%）、已實現 +{REALIZED:,}（+{REALIZED_PCT}%）。"
             f"券商表頭 總市值 {HEADER_TOTAL:,}／未實現 +{HEADER_UNREAL:,}／當日 +{HEADER_DAY_CHG:,}，"
             f"與逐檔差 {HEADER_TOTAL-tot:,}／{HEADER_UNREAL-unr:,}（009816/0056/00918 報價時點差）→ 以逐檔為準。"
             "⚠️ 盤中價非官方收盤，13:30 後須以 TWSE 收盤覆蓋並重跑 check_securities_integrity。"),
}
snap["holdings"] = holdings
snap["securities_breakdown"] = sec_bd
snap["securities_unrealized_pnl_pct"] = snap["securities"]["unrealized_pnl_pct"]

from asset_sync import sync_snapshot_keys, rebuild_liabilities  # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
snap["generated_at"] = "2026-11-12T10:25:00"
P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("--- 2026-11-12 台股 10:21 盤中真值套用完成 ---")
print(f"  台股市值: {tot:,}（表頭 {HEADER_TOTAL:,}，差 {HEADER_TOTAL-tot:+}）")
print(f"  未實現: +{unr:,}（+{snap['securities']['unrealized_pnl_pct']}%）｜表頭 +{HEADER_UNREAL:,}")
print(f"  總資產: {snap['total_assets']:,}")
