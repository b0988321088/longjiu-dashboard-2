#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""book_vs_market_card.py — 日報第 1 章「帳面 vs 大盤拆解」卡（淺色版）

2026-11-05 使用者核准：把「帳面今天看起來在跌、相對大盤其實沒有輸」的拆解固定進日報，
每天自動附上，不用再自己對照新聞。

本卡只做顯示與口徑揭露，不產生任何交易指令、不改 G1/G2/G3。
所有數字即時讀取，任一來源缺值一律顯示「—」，絕不以常數頂替。

資料來源（單一真值，不另存副本）：
  帳面與分項 → asset_diff_history.json（與差異分析同一份）
  美元資產   → snapshot.usd_exposure_monitor.current.金額明細
  大盤漲跌   → daily_analysis.json（market.twii / market.sox）
  匯率       → Yahoo chart API（TWD=X）；失敗才退回 macro_regime_YYYY-MM-DD.json 的輔助因子
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]


# ── 讀檔與抓價 ────────────────────────────────────────────────────────────
def _load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def _yahoo_closes(symbol: str, rng: str = "5d") -> list[tuple[str, float]]:
    """回 [(YYYY-MM-DD, close)]，以台北時間切日。失敗回空 list（呼叫端自行 fallback）。"""
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
               f"{urllib.parse.quote(symbol, safe='')}?range={rng}&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        res = data["chart"]["result"][0]
        ts = res["timestamp"]
        closes = res["indicators"]["quote"][0]["close"]
        out = []
        for t, c in zip(ts, closes):
            if c is None:
                continue
            out.append((datetime.utcfromtimestamp(t + 8 * 3600).strftime("%Y-%m-%d"), float(c)))
        return out
    except Exception:
        return []


def _pct_from_text(s) -> float | None:
    """從 '41,574.72 (-3.20%)' 取 -3.20；抓不到回 None。"""
    if not isinstance(s, str):
        return None
    m = re.search(r"\(\s*([+-]?\d+(?:\.\d+)?)\s*%\s*\)", s)
    return float(m.group(1)) if m else None


def _fx_map(today: str) -> tuple[dict, str]:
    """回 ({date: usdtwd}, 來源說明)。優先 Yahoo，缺才退回 macro_regime 檔。"""
    series = _yahoo_closes("TWD=X", "1mo")
    if len(series) >= 2:
        return {d: v for d, v in series}, "Yahoo TWD=X"
    # fallback：macro_regime_YYYY-MM-DD.json 的輔助因子（近 10 天）
    out = {}
    try:
        d0 = datetime.strptime(today, "%Y-%m-%d").date()
    except Exception:
        d0 = datetime.now().date()
    for i in range(0, 12):
        day = (d0 - timedelta(days=i)).isoformat()
        d = _load_json(BASE / f"macro_regime_{day}.json")
        v = ((d.get("輔助因子") or {}).get("USD/TWD"))
        if isinstance(v, (int, float)) and v > 0:
            out[day] = float(v)
    return out, "macro_regime 輔助因子"


# ── 小工具 ──────────────────────────────────────────────────────────────
def _money(v):
    return "—" if v is None else f"{v:+,.0f}"


def _pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def _pp(v):
    return "—" if v is None else f"{v:+.2f}pp"


def render(snap: dict | None = None, theme: str = "light", asof: str | None = None) -> str:
    if snap is None:
        snap = _load_json(BASE / "snapshot.json")
    hist = _load_json(BASE / "asset_diff_history.json")
    daily = _load_json(BASE / "daily_analysis.json")

    # ── 帳面：今日 vs 前一估值日 ──
    dates = sorted(k for k in hist if isinstance(hist.get(k), dict) and hist[k].get("total_assets"))
    if asof in dates:
        idx = dates.index(asof)
    else:
        idx = len(dates) - 1 if dates else -1
    today = dates[idx] if idx >= 0 else None
    prev = dates[idx - 1] if idx >= 1 else None
    cur = hist.get(today, {}) if today else {}
    prv = hist.get(prev, {}) if prev else {}

    total = cur.get("total_assets")
    total_prev = prv.get("total_assets")
    chg = (total - total_prev) if (total is not None and total_prev) else None
    chg_pct = (chg / total_prev * 100) if (chg is not None and total_prev) else None

    # ── 分項貢獻（四股力量）──
    def _delta(key):
        a, b = cur.get(key), prv.get(key)
        if a is None or b is None:
            return None
        return a - b

    parts = [("台股／證券", _delta("securities_market")),
             ("基金", _delta("fund_market")),
             ("保單", _delta("insurance_current")),
             ("現金", _delta("cash"))]
    parts_txt = "｜".join(f"{k} {_money(v)}" for k, v in parts)

    # ── 大盤對照 ──
    mk = (daily.get("market") or {})
    twii_txt, sox_txt = mk.get("twii"), mk.get("sox")
    twii_pct = _pct_from_text(twii_txt)
    sox_pct = _pct_from_text(sox_txt)
    rel_pp = (chg_pct - twii_pct) if (chg_pct is not None and twii_pct is not None) else None

    # ── 匯兌（粗估）：美元資產 × 台幣變動 ──
    usd_amt = None
    try:
        usd_amt = float(((snap.get("usd_exposure_monitor") or {}).get("current") or {})
                        .get("金額明細", {})
                        .get("美股桶", 0)
                        + ((snap.get("usd_exposure_monitor") or {}).get("current") or {})
                        .get("金額明細", {})
                        .get("美元計價基金", 0)
                        + ((snap.get("usd_exposure_monitor") or {}).get("current") or {})
                        .get("金額明細", {})
                        .get("保單美元債券", 0))
    except Exception:
        usd_amt = None
    usd_pct = ((snap.get("usd_exposure_monitor") or {}).get("current") or {}).get("合計")

    fx_map, fx_src = _fx_map(today or datetime.now().strftime("%Y-%m-%d"))
    fx_dates = sorted(fx_map)
    fx_now = fx_map.get(fx_dates[-1]) if fx_dates else None
    fx_prev = fx_map.get(fx_dates[-2]) if len(fx_dates) >= 2 else None
    fx_chg_pct = ((fx_now / fx_prev - 1) * 100) if (fx_now and fx_prev) else None
    fx_contrib = (usd_amt * fx_chg_pct / 100) if (usd_amt and fx_chg_pct is not None) else None
    orig_chg = (chg - fx_contrib) if (chg is not None and fx_contrib is not None) else None
    fx_note = (f"1 USD = {fx_now:.3f} TWD（{fx_dates[-1]}）" if fx_now else "匯率未取得")

    # ── 本週對照：以台股交易日為基準日，組合取「<= 該日」的最後一筆，兩邊期間對齊 ──
    tw_series = _yahoo_closes("^TWII", "1mo")
    tw_week_pct = None
    wk_base = None
    if len(tw_series) >= 5:
        tw_base_day = tw_series[-5][0]                 # 5 個交易日前的基準日
        tw_week_pct = (tw_series[-1][1] / tw_series[-5][1] - 1) * 100
        cands = [d for d in dates if d <= tw_base_day]
        if cands:
            wk_base = hist.get(cands[-1], {}).get("total_assets")
    if wk_base is None:                                 # 台股資料缺 → 退回組合自身 5 個估值日
        wk_base = hist.get(dates[max(0, idx - 4)], {}).get("total_assets") if dates else None
    wk_chg = (total - wk_base) if (total is not None and wk_base) else None
    wk_pct = (wk_chg / wk_base * 100) if (wk_chg is not None and wk_base) else None
    wk_rel = (wk_pct - tw_week_pct) if (wk_pct is not None and tw_week_pct is not None) else None

    # ── 穿透現況（只用既有口徑，不自行合併）──
    ap = ((snap.get("penetration") or {}).get("actual_pct") or {})
    tw_pct = ap.get("台股市值型成長")
    def_pct = ap.get("防守型配息")
    tech_pct = ap.get("美股市值型成長_科技")

    tone = "#0f766e" if (rel_pp or 0) >= 0 else "#b91c1c"
    bg = "#f0fdfa" if (rel_pp or 0) >= 0 else "#fef2f2"

    return f'''<div class="card" style="border-left:6px solid {tone};background:{bg}">
<h2>📉 帳面 vs 大盤拆解（{today or "—"}｜相對口徑）</h2>
<table>
<tr><th style="width:28%">今日帳面</th><td><b style="color:{tone};font-size:16px">{_money(chg)}</b> TWD（{_pct(chg_pct)}）
　<span style="color:#6e6e73;font-size:12px">總資產 {f"{total:,.0f}" if total else "—"}</span></td></tr>
<tr><th>台股加權（當日）</th><td>{twii_txt or "—"}　→ 組合 vs 大盤 <b style="color:{tone}">{_pp(rel_pp)}</b></td></tr>
<tr><th>費半（前一交易日）</th><td>{sox_txt or "—"}</td></tr>
<tr><th>分項貢獻</th><td>{parts_txt}</td></tr>
<tr><th>匯兌貢獻（粗估）</th><td>{_money(fx_contrib)} TWD
　<span style="color:#6e6e73;font-size:12px">美元資產 {f"{usd_amt:,.0f}" if usd_amt else "—"}（{f"{usd_pct:.1f}%" if isinstance(usd_pct, (int, float)) else "—"}）× 台幣 {_pct(-fx_chg_pct) if fx_chg_pct is not None else "—"}{"（貶）" if (fx_chg_pct or 0) > 0 else ("（升）" if (fx_chg_pct or 0) < 0 else "")}；{fx_note}</span></td></tr>
<tr><th>剝掉匯率後的原幣基礎</th><td><b>{_money(orig_chg)}</b> TWD <span style="color:#6e6e73;font-size:12px">（粗估：帳面 − 匯兌）</span></td></tr>
<tr><th>本週對照</th><td>組合 {_pct(wk_pct)} vs 台股 {_pct(tw_week_pct)}　→ <b>{_pp(wk_rel)}</b></td></tr>
<tr><th>結構現況（穿透）</th><td>台股市值型 {f"{tw_pct:.1f}%" if isinstance(tw_pct, (int, float)) else "—"}｜防守型配息 {f"{def_pct:.1f}%" if isinstance(def_pct, (int, float)) else "—"}｜科技 {f"{tech_pct:.1f}%" if isinstance(tech_pct, (int, float)) else "—"}</td></tr>
</table>
<p style="color:#6e6e73;font-size:12px;line-height:1.65;margin-top:8px">口徑：帳面＝總資產（含現金與配息入帳）；相對差＝組合報酬率 − 同期大盤。匯兌為換算效果、非現金入袋，
台幣回升時同額回吐。防守型配息主要為台股高股息 ETF，回檔時與台股同向，不視為避險資產。
本卡只顯示，不觸發任何加減碼。</p>
</div>'''


if __name__ == "__main__":
    print(render()[:3000])
