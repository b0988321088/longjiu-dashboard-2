# -*- coding: utf-8 -*-
"""2026-11-05 證券持股明細校正（券商 App 截圖為真值）

證據來源：券商 App 2026-11-05 20:26 截圖
  總市值 2,566,480／當日變動 -61,040 (-2.32%)／未實現 +178,640 (+7.48%)
  14 檔股數與價格逐一核對，並與 TWSE／TPEx 官方收盤價一致

本次只做三件事：
  1. holdings 逐檔 price 改官方收盤、market_value = ROUND_HALF_UP(shares*price)、重算 pnl
  2. securities 內值同步（total_market_value／unrealized_pnl／price_date／source）
  3. 6 個同義欄位與 securities_unrealized_pnl 一律由權威值派生

不動：total_assets（已用 2,566,480）、官方桶位、任何投資策略欄位。
"""
import json, shutil, sys
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent
SNAP = BASE / "snapshot.json"

# 券商 App 2026-11-05 逐檔（代號: 股數, 收盤價, 平均成本）
APP = {
    "0050":   (2000,  97.15, 84.90),
    "006208": (2000,  222.55, 196.90),
    "009816": (16000, 14.53, 12.49),
    "00646":  (1000,  79.55, 71.60),
    "00713":  (2000,  63.80, 54.80),
    "00878":  (15000, 33.03, 27.17),
    "0056":   (1000,  51.55, 37.15),
    "00981A": (8000,  23.05, 26.32),
    "00984A": (10000, 13.36, 14.56),
    "00919":  (6000,  31.19, 29.55),
    "00918":  (1000,  32.76, 28.55),
    "00888":  (5000,  28.37, 31.73),
    "00983D": (20000, 10.05, 10.10),
    "00927":  (2000,  29.85, 37.90),
}
TOTAL_APP = 2_566_480
PNL_APP = 178_640
PRICE_DATE = "2026-11-05"
SOURCE = "券商 App 持股明細截圖 2026-11-05 20:26（14 檔逐檔核對；價格＝11/05 收盤，與 TWSE／TPEx 官方一致）"


def r0(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def main() -> int:
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    bk = BASE / ".backup"
    bk.mkdir(exist_ok=True)
    shutil.copy2(SNAP, bk / f"snapshot_before_securities_{PRICE_DATE}.json")

    before_total = snap.get("securities_total_market_value")
    before_hold = sum(h["market_value"] for h in snap["holdings"])

    # ── 1. 逐檔校正 ─────────────────────────────
    print(f"{'代號':8s}{'股數':>7s}{'舊價':>8s}{'新價':>8s}{'舊市值':>11s}{'新市值':>11s}{'差額':>9s}")
    changed = []
    for h in snap["holdings"]:
        t = h["ticker"]
        if t not in APP:
            print(f"⚠️ {t} 不在券商清單，保留原值並標異常")
            h["price_date"] = None
            continue
        sh, px, avg = APP[t]
        if int(h["shares"]) != sh:
            print(f"❌ {t} 股數不符 snapshot={h['shares']} App={sh} → 中止")
            return 2
        mv = r0(sh * px)
        cost = h.get("cost") or r0(sh * avg)
        pnl = mv - cost
        old_mv = h["market_value"]
        changed.append((t, old_mv, mv))
        h.update({"price": px, "market_value": mv, "value": mv, "cost": cost,
                  "cost_avg": round(cost / sh, 4), "pnl": pnl,
                  "pnl_pct": round(pnl / cost * 100, 2) if cost else None,
                  "price_date": PRICE_DATE, "price_source": "TWSE/TPEx 官方收盤"})
        print(f"{t:8s}{sh:>7d}{'':>2s}{old_mv/sh:>8.2f}{px:>8.2f}{old_mv:>11,}{mv:>11,}{mv-old_mv:>9,}")

    hold_sum = sum(h["market_value"] for h in snap["holdings"])
    cost_sum = sum(h["cost"] for h in snap["holdings"])
    pnl_sum = hold_sum - cost_sum

    # ── 2. securities 內值 ──────────────────────
    sec = snap.setdefault("securities", {})
    sec.update({
        "total_market_value": hold_sum,
        "unrealized_pnl": PNL_APP,          # 券商 App 真值（成本均價僅 2dp，逐檔回推為 pnl_sum）
        "realized_pnl": 23_460,
        "price_date": f"{PRICE_DATE}（收盤）",
        "as_of": PRICE_DATE,
        "source": SOURCE,
        "note": (f"2026-11-05 券商 App：市值 {TOTAL_APP:,}／當日變動 -61,040 (-2.32%)／"
                 f"未實現 +{PNL_APP:,} (+7.48%)／已實現 +23,460 (+27.34%)；"
                 f"逐檔成本由 App 平均成本×股數，pnl 逐檔合計 {pnl_sum:,}（與 App 差 {pnl_sum - PNL_APP:,}＝成本均價顯示精度）"),
    })

    # ── 3. 同義欄位全部派生 ─────────────────────
    for k in ("securities_total", "securities_total_market_value", "securities_market",
              "securities_market_value", "securities_current", "securities_current_value"):
        snap[k] = hold_sum
    snap["securities_unrealized_pnl"] = PNL_APP
    snap["securities_market_value"] = hold_sum
    snap["securities_current"] = hold_sum

    # ── 驗證 ───────────────────────────────────
    errs = []
    if hold_sum != TOTAL_APP:
        errs.append(f"逐檔合計 {hold_sum:,} ≠ App 總市值 {TOTAL_APP:,}")
    for k in ("securities_total", "securities_total_market_value", "securities_market",
              "securities_market_value", "securities_current", "securities_current_value"):
        if snap[k] != TOTAL_APP:
            errs.append(f"{k}={snap[k]:,} ≠ {TOTAL_APP:,}")
    if sec["total_market_value"] != TOTAL_APP:
        errs.append("securities.total_market_value 未同步")
    for h in snap["holdings"]:
        if h.get("price_date") and r0(h["shares"] * h["price"]) != h["market_value"]:
            errs.append(f"{h['ticker']} shares×price ≠ market_value")
    if snap.get("total_assets") and (
        (snap.get("insurance_total", 0) + hold_sum + snap.get("fund_market", 0) + snap.get("cash_total", 0))
        != snap["total_assets"]
    ):
        errs.append("四項加總 ≠ total_assets（未授權改 total_assets，僅告警）")

    print("\n=== 校正結果 ===")
    print(f"  明細合計　{before_hold:,} → {hold_sum:,}（差 {hold_sum - before_hold:,}）")
    print(f"  權威總額　{before_total:,} → {snap['securities_total_market_value']:,}")
    print(f"  成本合計　{cost_sum:,}／逐檔 pnl {pnl_sum:,}／App pnl {PNL_APP:,}（差 {pnl_sum - PNL_APP:,}）")
    print(f"  price_date 全部＝{PRICE_DATE}：{all(h.get('price_date') == PRICE_DATE for h in snap['holdings'])}")
    if errs:
        print("  ❌ 驗證失敗：")
        for e in errs:
            print("    -", e)
        return 3
    print("  ✅ 全部驗證通過")

    snap["securities_closeout_20261105"] = {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "evidence": "券商 App 截圖 2026-11-05 20:26",
        "before_mv": before_hold, "after_mv": hold_sum,
        "delta": hold_sum - before_hold,
        "note": "修正明細價格由盤中價改官方收盤；total_assets 未變動（原本已用權威總額）",
    }
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  ✅ snapshot.json 已寫入（備份 .backup/）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
