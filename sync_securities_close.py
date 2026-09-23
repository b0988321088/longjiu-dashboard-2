#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_securities_close.py — 台股收盤價覆蓋（2026-09-23 建立）

為什麼要有這支：
    使用者常在「盤中」傳凱基持股截圖（例：2026-09-23 11:2x 盤中 3,006,770）。盤中價不是收盤價，
    若就此停在 snapshot，日報/差異分析/儀表板的證券口徑會混兩個交易日。本腳本在收盤後（13:40+）
    用 market_price 單一入口重抓「最後成交/日線收盤」覆蓋，並改標「收盤」。

用法：
    python sync_securities_close.py --dry-run    # 只印比對表，不寫任何檔
    python sync_securities_close.py              # 寫 snapshot.securities + 呼叫 update_data.py 同步

行為：
    ① 讀 snapshot.securities.holdings 逐檔 ticker（含 0 股者跳過）
    ② market_price.fetch_snapshot(f"{ticker}.TW") → price
    ③ value = shares × price；total = Σvalue；unrealized = total − Σcost
    ④ 寫回 snapshot.securities（逐檔 price/value/total/unrealized/price_date/note）
    ⑤ python update_data.py --securities=<total>（同義欄位＋DB assets＋穿透重算）
    fail-closed：任一檔抓不到價格 → 不寫入任何檔，exit 1（寧可留盤中價也不寫半套）
    寫入前備份 snapshot.json → snapshot.backup.json（沿用 update_data.py 慣例）
"""
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
DRY = "--dry-run" in sys.argv

sys.path.insert(0, str(BASE))
from market_price import fetch_snapshot  # noqa: E402


def main() -> int:
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    sec = snap.get("securities") or {}
    holdings = sec.get("holdings") or []
    if not holdings:
        print("❌ snapshot.securities.holdings 為空 → 不動作")
        return 1

    rows, failed = [], []
    for h in holdings:
        tk = str(h.get("ticker") or "").strip()
        shares = float(h.get("shares") or 0)
        if not tk or shares <= 0:
            continue
        # 上市 .TW 優先，404/空值退上櫃 .TWO（2026-09-23 實測：00888、009823 為上櫃，.TW 回 404）
        s = fetch_snapshot(f"{tk}.TW") or {}
        if not s.get("price"):
            s = fetch_snapshot(f"{tk}.TWO") or {}
        px = s.get("price")
        if not px:
            failed.append(tk)
            continue
        px = float(px)
        val = int(round(shares * px))
        old_val = h.get("value")
        rows.append({
            "ticker": tk,
            "shares": shares,
            "old_price": h.get("price"),
            "new_price": px,
            "old_value": old_val,
            "new_value": val,
            "as_of": s.get("as_of"),
            "intraday": s.get("used_intraday"),
            "stale": s.get("stale"),
        })

    if failed:
        print(f"❌ 取價失敗 {len(failed)} 檔：{', '.join(failed)} → 不寫入（維持原值）")
        return 1

    total = sum(r["new_value"] for r in rows)
    cost_sum = int(round(sum(float(h.get("cost") or 0) for h in holdings)))
    unrl = total - cost_sum
    unrl_pct = round(unrl / cost_sum * 100, 2) if cost_sum else 0.0
    old_total = int(sec.get("total_market_value") or 0)

    print(f"{'代號':8}{'股數':>9}{'原價':>9}{'新價':>9}{'原值':>11}{'新值':>11}")
    for r in rows:
        print(f"{r['ticker']:8}{int(r['shares']):>9}{str(r['old_price']):>9}{r['new_price']:>9}"
              f"{str(r['old_value']):>11}{r['new_value']:>11}")
    print(f"\n合計 {old_total:,} → {total:,}（{total - old_total:+,}）｜未實現 {unrl:,}（{unrl_pct}%）")

    if DRY:
        print("\n--dry-run：未寫入任何檔案")
        return 0

    shutil.copy2(SNAP, BASE / "snapshot.backup.json")
    for h in holdings:
        r = next((x for x in rows if x["ticker"] == str(h.get("ticker") or "").strip()), None)
        if not r:
            continue
        h["price"] = r["new_price"]
        h["value"] = r["new_value"]
        # 2026-09-23 INC-242b v2（CIO F3）：只寫 price/value 會讓兄弟鍵停在舊值——
        # build_penetration_report.py:231-235 與 etf_holding_report.py:41,140-148 讀 h['pnl']／h['pnl_pct']，
        # value 用新價、pnl 卻用舊價 → 同一張表自相矛盾（與 INC-242 同型的子樹版本）。
        # market_value 是無讀者的鏡像鍵，一併對齊避免下一個陷阱。
        h["market_value"] = r["new_value"]
        _cost = float(h.get("cost") or 0)
        if _cost:
            h["pnl"] = int(r["new_value"] - round(_cost))
            h["pnl_pct"] = round(h["pnl"] / _cost * 100, 2)
    sec["total_market_value"] = total
    sec["unrealized_pnl"] = unrl
    sec["unrealized_pnl_pct"] = unrl_pct
    sec["price_date"] = date.today().isoformat()
    sec["note"] = (f"{date.today().isoformat()} 收盤（sync_securities_close.py 由 Yahoo 日線/最後成交覆蓋；"
                   f"來源截圖為同日盤中）")
    snap["securities"] = sec
    sid = snap.get("source_import_dates")
    if isinstance(sid, dict):
        for k in list(sid):
            if "證券" in k or "securities" in k.lower():
                sid[k] = date.today().isoformat()
    # 2026-09-23 INC-242b v3：snapshot canonical indent=1（INC-184／閉環稽核第 10 類）。
    # 原 indent=2 會讓每次收盤覆蓋都把整個 snapshot.json 換格式（實測 5,000 行全檔 churn），
    # 掩蓋真正的差異；update_data 隨後雖會寫回 1，但中間產出與備份已被污染。
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✅ snapshot.securities 已覆蓋為收盤價")

    r = subprocess.run([sys.executable, str(BASE / "update_data.py"), f"--securities={total}"],
                       cwd=str(BASE), capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip()[-800:])
    if r.returncode != 0:
        print(f"❌ update_data.py rc={r.returncode}；stderr={r.stderr.strip()[-400:]}")
        return r.returncode
    print("✅ 同義欄位／DB／穿透已同步（下一步：跑日報與差異分析）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
