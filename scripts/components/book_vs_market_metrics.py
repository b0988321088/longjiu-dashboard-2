#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book_vs_market_metrics.py — 績效次要指標（今日／本週相對大盤、匯兌貢獻）

2026-11-05 使用者規格：績效不得當判斷依據，只留在「資產防護與行動卡」卡尾一行。
本模組只回字串摘要，不參與任何結論計算；資料缺漏回空字串（呼叫端顯示「—」）。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
TPE = timezone(timedelta(hours=8))


def _load(p):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def _pp(v):
    return "—" if v is None else f"{v:+.2f}pp"


def _pct_from_text(s):
    if not s:
        return None
    m = re.search(r"\(([+-]?\d+(?:\.\d+)?)%\)", str(s))
    return float(m.group(1)) if m else None


def _yahoo(symbol: str, rng: str = "1mo", timeout: int = 8):
    """回 [(date, close)]；失敗回 []（呼叫端視為缺值，不編造）。"""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(symbol) + f"?range={rng}&interval=1d")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        res = d["chart"]["result"][0]
        ts = res.get("timestamp") or []
        cl = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        out = []
        for t, c in zip(ts, cl):
            if c is None:
                continue
            out.append((datetime.fromtimestamp(t, TPE).strftime("%Y-%m-%d"), float(c)))
        return out
    except Exception:
        return []


def etf_check(tickers: list[str], days: int = 5) -> dict:
    """高股息 ETF 實測跌幅（規格要求：防守效果必須用實際跌幅驗證，不看配置比例）。

    回 {ticker: '-5.11%（自 2026-10-30）'}；取不到資料的標的不列（不編造）。
    """
    out = {}
    for t in tickers:
        s = _yahoo(t, rng="1mo")
        if len(s) < days:
            continue
        base_day, base = s[-days]
        chg = (s[-1][1] / base - 1) * 100
        out[t] = f"{chg:+.2f}%（自 {base_day}）"
    return out


def secondary(snap: dict | None = None) -> dict:
    hist = _load("asset_diff_history.json")
    dates = sorted(hist)
    if len(dates) < 2:
        return {}
    today, prev = dates[-1], dates[-2]
    t_tot = hist[today].get("total_assets")
    p_tot = hist[prev].get("total_assets")
    today_pct = ((t_tot - p_tot) / p_tot * 100) if (t_tot and p_tot) else None

    da = _load("daily_analysis.json").get("market") or {}
    tw_today = _pct_from_text(da.get("twii"))
    out = {}
    if today_pct is not None and tw_today is not None:
        out["today"] = f"帳面 {_pct(today_pct)} vs 台股 {_pct(tw_today)}（{_pp(today_pct - tw_today)}）"

    tws = _yahoo("^TWII")
    if len(tws) >= 5:
        tw_week = (tws[-1][1] / tws[-5][1] - 1) * 100
        base_day = tws[-5][0]
        cands = [d for d in dates if d <= base_day]
        if cands:
            b = hist[cands[-1]].get("total_assets")
            if b:
                wk = (t_tot - b) / b * 100
                out["week"] = f"{_pct(wk)} vs 台股 {_pct(tw_week)}（{_pp(wk - tw_week)}）"

    fx = _yahoo("TWD=X", rng="5d")
    if len(fx) >= 2 and snap:
        usd = (((((snap.get("usd_exposure_monitor") or {}).get("current") or {})
                 .get("金額明細")) or {}))
        amt = sum(float(v or 0) for k, v in usd.items() if k != "分母_總資產")
        chg = (fx[-1][1] / fx[-2][1] - 1) * 100
        if amt:
            out["fx"] = (f"{amt * chg / 100:+,.0f}（美元資產 {amt:,.0f} × 台幣 {chg:+.2f}%）")
    return out


if __name__ == "__main__":
    print(json.dumps(secondary(_load("snapshot.json")), ensure_ascii=False, indent=1))
