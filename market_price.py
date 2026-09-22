# -*- coding: utf-8 -*-
"""Yahoo chart API 取價「單一入口」（2026-09-22 建，INC-239）

為什麼要有這支（兩個實踩缺陷）：

1) 前收不可信任 meta.previousClose / meta.chartPreviousClose
   - INC-171（2026-09-13）：range=5d/1mo 的 chartPreviousClose 是「區間起點前」的收盤
     （約 5 日 / 1 月前）→ 漲跌% 被算成「一週漲跌」。
   - 2026-09-22 實證：^TWII 的 meta.previousClose 回 47,180.80（＝9/18 收盤），
     比真正的 9/21 收盤 47,718.84 落後「一整個交易日」
     → 台股當日漲跌從 +0.17% 誤成 +1.31%（誤差 1.14pp，方向偏樂觀，
       並會誤觸 ±1.0% 動能門檻、寫進日報第 3/4 章與 CIO prompt）。
   - 正解：用「日線 timestamp 對齊」推前收 —— 取最後一根日線的日期，
     前收＝日期在它之前的那一根收盤（天然跳過休市日，且不受 null 過濾影響）。

2) 收盤後 Yahoo 當日日線尚未 roll → 當日值會退回前一日（9/22 15:09 實證：
   ^TWII 日線仍只到 9/21，regularMarketPrice 為空 → 舊碼退回 closes[-1] = 9/21，
   於是「9/21 的 47,718.80 (+1.14%)」被標成「今日」，
   同一輪 2330.TW 已是 9/22 的 2,460 (-0.81%) → 同一區塊混兩個交易日）。
   台股收盤後（台北 13:40 起）若日線未 roll，改抓 interval=1m&range=1d 補當日最後成交。

美股不套用 (2)：日報對美股一律採「最新可得日線收盤」（昨收口徑），
且美股跨台北日期線（ET 16:00 = 台北隔日 04:00/05:00）不適合用同一套日界判斷。

用法：
    from market_price import fetch_snapshot, fmt
    s = fetch_snapshot("^TWII")     # → {"price","prev","change_pct","as_of","used_intraday","stale"}
    fmt(s)                          # → "47,800.17 (+0.17%)"
    fetch_snapshot 回 {} 代表抓取失敗（呼叫端要顯性標「—」，不可靜默給舊值）。
"""
from __future__ import annotations

import json
import urllib.request
from datetime import date, datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))
_UA = {"User-Agent": "Mozilla/5.0"}
_HOSTS = ("query1", "query2")  # query2 為 query1 的備援主機（INC-141）
# 台股收盤 13:30（台北）；Yahoo 日線 roll 需要緩衝，13:40 之後才期待有當日 K 棒
_TW_CLOSE_HHMM = 1340


def _is_tw(symbol: str) -> bool:
    s = (symbol or "").upper()
    return s.startswith("^TW") or s.endswith(".TW") or s.endswith(".TWO")


def _get_result(tail: str, timeout: int = 10) -> dict:
    """抓 chart API，回 result dict；query1 失敗退 query2，全失敗回 {}。"""
    last_err = None
    for host in _HOSTS:
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{tail}"
        try:
            req = urllib.request.Request(url, headers=_UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))["chart"]["result"][0]
        except Exception as e:  # noqa: BLE001
            last_err = e
    print(f"[WARN] market_price 抓取失敗 {tail}: {last_err}")
    return {}


def _bars(res: dict) -> list[tuple[date, float]]:
    """日線 → [(交易日(UTC 日界), 收盤)]，過濾 null，按時間排序。"""
    ts = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
    out: list[tuple[date, float]] = []
    for t, c in zip(ts, closes):
        if c is None:
            continue
        try:
            out.append((datetime.fromtimestamp(int(t), timezone.utc).date(), float(c)))
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda x: x[0])
    return out


def _tw_should_have_today_bar(now_tw: datetime) -> bool:
    return now_tw.weekday() < 5 and (now_tw.hour * 100 + now_tw.minute) >= _TW_CLOSE_HHMM


def _last_intraday(symbol: str, timeout: int = 10) -> tuple[date, float] | None:
    """interval=1m&range=1d 的最後一筆成交（含其台北日期）；取不到回 None。"""
    res = _get_result(f"{symbol}?interval=1m&range=1d", timeout)
    if not res:
        return None
    ts = res.get("timestamp") or []
    closes = (res.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
    for t, c in reversed(list(zip(ts, closes))):
        if c is None:
            continue
        return (datetime.fromtimestamp(int(t), TW_TZ).date(), float(c))
    return None


def fetch_snapshot(symbol: str, timeout: int = 10) -> dict:
    """回 {"price","prev","change_pct","as_of","used_intraday","stale"}；失敗回 {}。"""
    res = _get_result(f"{symbol}?interval=1d&range=5d", timeout)  # range=5d 保證 ≥2 點（INC-141）
    if not res:
        return {}
    bars = _bars(res)
    if not bars:
        return {}

    last_date, last_close = bars[-1]
    price, as_of = last_close, last_date
    used_intraday, stale = False, False

    if _is_tw(symbol):
        now_tw = datetime.now(TW_TZ)
        if last_date != now_tw.date() and _tw_should_have_today_bar(now_tw):
            intra = _last_intraday(symbol, timeout)
            if intra and intra[0] == now_tw.date():
                price, as_of, used_intraday = intra[1], intra[0], True
            else:
                stale = True  # 應有當日價卻拿不到 → 呼叫端應標「資料延遲」，不要當今日

    if used_intraday:
        prev = last_close            # 日線最後一根＝前一日
    elif len(bars) >= 2:
        prev = bars[-2][1]
    else:
        prev = None

    pct = ((price - prev) / prev * 100) if prev else None
    return {
        "price": price,
        "prev": prev,
        "change_pct": pct,
        "as_of": as_of.isoformat(),
        "used_intraday": used_intraday,
        "stale": stale,
    }


def fmt(s: dict) -> str:
    """→ "47,800.17 (+0.17%)"；缺值回 "—"。"""
    if not s or s.get("price") is None or s.get("change_pct") is None:
        return "—"
    return f"{s['price']:,.2f} ({s['change_pct']:+.2f}%)"


if __name__ == "__main__":
    for sym in ("^TWII", "2330.TW", "^SOX", "^GSPC", "^DJI"):
        s = fetch_snapshot(sym)
        print(f"{sym:10s} {fmt(s):>22s}  as_of={s.get('as_of')} "
              f"prev={s.get('prev')} 補盤中={s.get('used_intraday')} 遲={s.get('stale')}")
