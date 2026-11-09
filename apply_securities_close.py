#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_securities_close.py — 用官方收盤價更新證券持股明細（可重複執行）

用途：收盤後把 snapshot.holdings 的價格換成當日官方收盤，並同步
      securities 內值、6 個同義欄位、total_assets／net_worth。

為何要這支：2026-11-05 那支 apply_securities_close_1105.py 是硬編碼一次性腳本。
盤中價不得當收盤（date_integrity L1 明文），所以每日收盤後需要一個「按日期抓官方價」的入口。

價格來源（雙來源交叉，任一可得即可）：
  1. TWSE exchangeReport/STOCK_DAY（上市；回傳整月，取目標日收盤）
  2. Yahoo chart API（range=1mo，取目標日或之前最後一個交易日 close）
兩個來源都取不到 → 該檔保留原價並標 price_date=None（不冒充）。

用法：
  python apply_securities_close.py --date 2026-11-09 --dry-run
  python apply_securities_close.py --date 2026-11-09            # 寫入 snapshot
  python apply_securities_close.py --date 2026-11-09 --sync     # 寫入後跑四源同步＋重產日報
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

UA = {"User-Agent": "Mozilla/5.0 (longjiu-securities-close)"}
# TWSE MIS 需要 Referer，否則批次查詢會回空成交價（z='-'）→ 全部誤判「前收」
_UA_MIS = {**UA, "Referer": "https://mis.twse.com.tw/stock/", "Accept": "application/json"}

MIRROR_KEYS = ("securities_total", "securities_total_market_value", "securities_market",
               "securities_market_value", "securities_current", "securities_current_value")


def _get(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _num(s) -> float:
    return float(str(s).replace(",", "").strip())


def _roc(d: date) -> str:
    return f"{d.year - 1911:03d}/{d.month:02d}/{d.day:02d}"


def twse_close(code: str, target: date):
    """TWSE 官方收盤；非交易日或抓不到 → None。"""
    url = (f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json"
           f"&date={target:%Y%m}01&stockNo={code}")
    try:
        js = json.loads(_get(url).decode("utf-8"))
    except Exception:
        return None
    if js.get("stat") != "OK":
        return None
    want = _roc(target)
    for row in js.get("data") or []:
        if str(row[0]).strip() == want:
            try:
                return _num(row[6]), "TWSE"
            except Exception:
                return None
    return None


def tpex_close(code: str, target: date):
    """TPEx 官方收盤（上櫃 ETF，例：00888 永豐台灣ESG）。"""
    url = (f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
           f"?code={code}&date={target:%Y/%m/%d}&response=json")
    try:
        js = json.loads(_get(url).decode("utf-8"))
        rows = js["tables"][0]["data"]
    except Exception:
        return None
    want = _roc(target)
    for row in rows or []:
        if str(row[0]).strip() == want:
            try:
                return _num(row[6]), "TPEx"
            except Exception:
                return None
    return None


def yahoo_close(code: str, target: date):
    """Yahoo 備援：取目標日（含）之前最後一個交易日 close（上市 .TW／上櫃 .TWO 都試）。"""
    for suffix in ("TW", "TWO"):
        got = _yahoo_one(f"{code}.{suffix}", target)
        if got:
            return got
    return None


def _yahoo_one(sym: str, target: date):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
           f"?interval=1d&range=1mo")
    try:
        js = json.loads(_get(url).decode("utf-8"))
        res = js["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
    except Exception:
        return None
    best = None
    for t, c in zip(ts, closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(t).date()
        if d <= target:
            best = (d, float(c))
    if not best:
        return None
    return best[1], f"Yahoo({best[0]})"


def r0(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def mis_quotes(codes, chunk: int = 5):
    """盤中即時報價。主源 Yahoo chart meta（實測 00878/0056/00919/0050 都有值），
    TWSE MIS 為備援（實測批次回 z='-'，不可靠）。

    2026-11-09 使用者指示：可用盤中價估現值以保持資料新鮮度。
    契約：盤中價只用來「估算現值」，估值日仍記最後收盤日，並在 securities.intraday_estimate
    留時間戳與來源——不得把盤中價寫成收盤價（date_integrity L1 明文）。
    """
    out = {}
    for code in codes:
        for suffix in ("TW", "TWO"):
            url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{code}.{suffix}"
                   f"?interval=1m&range=1d")
            try:
                js = json.loads(_get(url))
                meta = js["chart"]["result"][0]["meta"]
                px = meta.get("regularMarketPrice")
                ts = meta.get("regularMarketTime")
                if px:
                    at = (datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                          if ts else datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    out[code] = (float(px), at, True)
                    break
            except Exception:
                continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--intraday", action="store_true",
                    help="用 TWSE MIS 盤中價估算現值（估值日仍記最近收盤，另存 intraday_estimate）")
    ap.add_argument("--sync", action="store_true", help="寫入後跑 check_securities_integrity＋four_source_sync＋regenerate_report")
    a = ap.parse_args()
    target = datetime.strptime(a.date, "%Y-%m-%d").date()

    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    holds = snap.get("holdings") or []
    if not holds:
        print("❌ snapshot.holdings 為空 → 中止")
        return 2

    before_total = snap.get("securities", {}).get("total_market_value")
    last_close_date = str(snap.get("securities", {}).get("price_date") or "")[:10] or target.isoformat()
    quotes_at = ""
    live_map = {}
    if a.intraday:
        live_map = mis_quotes([str(h.get("ticker") or "").strip() for h in holds])
        quotes_at = max((v[1] for v in live_map.values()), default="")
        print(f"📡 盤中估價：TWSE MIS {len(live_map)}/{len(holds)} 檔取得，時間 {quotes_at}")
        print(f"{'代號':8s}{'股數':>8s}{'前價':>9s}{'盤中':>9s}{'差':>9s}  來源")
    else:
        print(f"{'代號':8s}{'股數':>8s}{'舊價':>9s}{'新價':>9s}{'差':>9s}  來源")
    misses, changed = [], 0
    for h in holds:
        code = str(h.get("ticker") or "").strip()
        if a.intraday:
            q = live_map.get(code)
            if not q:
                misses.append(code)
                print(f"{code:8s}{int(h['shares']):>8d}{h['price']:>9.2f}{'—':>9s}{'':>9s}  ✗ 取不到")
                continue
            px, at, live = q
            src = f"MIS盤中{f'@{at[9:]}' if at else ''}{'' if live else '(前收)'}"
        else:
            got = twse_close(code, target) or tpex_close(code, target) or yahoo_close(code, target)
            if not got:
                misses.append(code)
                print(f"{code:8s}{int(h['shares']):>8d}{h['price']:>9.2f}{'—':>9s}{'':>9s}  ✗ 取不到")
                continue
            px, src = got
        mv = r0(h["shares"] * px)
        old_mv = h.get("market_value") or 0
        cost = h.get("cost") or 0
        if a.intraday:
            # 盤中：price 必須等於 market_value 的計算基礎（閘門 ① shares×price==market_value），
            # 因此 price 也寫盤中價；估值日仍記最後收盤，另存 prev_close 與 intraday_at 供追溯。
            h.update({"price": px, "price_intraday": px, "intraday_at": at,
                      "market_value_intraday": mv, "value": mv, "market_value": mv,
                      "price_prev_close": old_mv / max(int(h["shares"]), 1) if h["shares"] else None,
                      "price_date": last_close_date, "price_source": src})
        else:
            h.update({"price": px, "market_value": mv, "value": mv,
                      "price_date": target.isoformat(), "price_source": src})
        if cost:
            pnl = mv - cost
            h["pnl"] = pnl
            h["pnl_pct"] = round(pnl / cost * 100, 2)
        print(f"{code:8s}{int(h['shares']):>8d}{old_mv / max(int(h['shares']), 1):>9.2f}{px:>9.2f}"
              f"{mv - old_mv:>9,}  {src}")
        changed += 1

    hold_sum = sum(h.get("market_value") or 0 for h in holds)
    cost_sum = sum(h.get("cost") or 0 for h in holds)
    sec = snap.setdefault("securities", {})
    if a.intraday:
        sec.update({"total_market_value": hold_sum,
                    "price_date": f"{last_close_date}（收盤）",
                    "as_of": last_close_date,
                    "source": f"盤中估算 TWSE MIS {quotes_at}（{changed} 檔成功、{len(misses)} 檔失敗）；估值日仍為 {last_close_date} 收盤",
                    "unrealized_pnl": hold_sum - cost_sum if cost_sum else sec.get("unrealized_pnl"),
                    "intraday_estimate": {"at": quotes_at, "total": hold_sum,
                                          "delta_vs_close": hold_sum - (before_total or 0),
                                          "note": "市值＝股數×盤中價估算，非收盤真值；收盤後由 apply_securities_close.py --date 覆寫"}})
    else:
        sec.pop("intraday_estimate", None)
        sec.update({"total_market_value": hold_sum,
                    "price_date": f"{target}（收盤）",
                    "as_of": target.isoformat(),
                    "source": f"TWSE／Yahoo 官方收盤抓取 {target}（{changed} 檔成功、{len(misses)} 檔失敗）",
                    "unrealized_pnl": hold_sum - cost_sum if cost_sum else sec.get("unrealized_pnl")})
    # 2026-11-09（券商 App 對帳抓到）：unrealized_pnl_pct 是派生值，舊版只寫金額不寫比率，
    # 導致收盤後金額更新、比率停在舊值（實例：金額 170,820／成本 2,408,940 應為 7.09%，欄位卻是 3.07）。
    # 一律由「未實現 ÷ 成本」現算，成本不可得時留 None 而不是沿用舊值。
    if cost_sum:
        sec["unrealized_pnl_pct"] = round((hold_sum - cost_sum) / cost_sum * 100, 2)
    else:
        sec["unrealized_pnl_pct"] = None
    for k in MIRROR_KEYS:
        snap[k] = hold_sum
    snap["securities_unrealized_pnl"] = sec.get("unrealized_pnl")

    ins = snap.get("insurance_total") or 0
    fund = snap.get("fund_market") or 0
    cash = snap.get("cash_total") or 0
    old_assets = snap.get("total_assets") or 0
    snap["total_assets"] = ins + hold_sum + fund + cash
    snap["net_worth"] = snap["total_assets"] - (snap.get("total_liabilities") or 0)
    if snap.get("net_worth_incl_re"):
        snap["net_worth_incl_re"] = snap["net_worth_incl_re"] + (snap["total_assets"] - old_assets)

    print(f"\n證券合計 {before_total:,} → {hold_sum:,}（差 {hold_sum - (before_total or 0):,}）")
    print(f"總資產 {old_assets:,} → {snap['total_assets']:,}｜淨值 {snap['net_worth']:,}")
    if misses:
        print(f"⚠️ 取不到收盤價：{', '.join(misses)}（保留原價，不冒充）")

    if a.dry_run:
        print("（dry-run：未寫入）")
        return 0

    bk = BASE / ".backup"
    bk.mkdir(exist_ok=True)
    shutil.copy2(SNAP, bk / f"snapshot_before_securities_{target}.json")
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✅ snapshot.json 已寫入")

    if a.sync:
        chain = [["scripts/check_securities_integrity.py"], ["four_source_sync.py"]]
        for cmd in chain:
            print(f"→ {' '.join(cmd)}")
            r = subprocess.run([sys.executable, *cmd], cwd=str(BASE))
            if r.returncode != 0:
                print(f"⛔ {cmd[0]} rc={r.returncode} → 停止（不發布）")
                return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
