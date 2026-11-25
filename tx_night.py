#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""台指期夜盤每日推播（2026-11-25 使用者要求）

用途：每天夜盤時段（15:00–次日 05:00）取近月台指期（TX）盤後報價，推 Telegram。
資料源：期交所 MIS 即時報價 API
  POST https://mis.taifex.com.tw/futures/api/getQuoteList
  MarketType=0 → 一般交易時段（日盤），SymbolID 尾碼 -F
  MarketType=1 → 盤後交易時段（夜盤），SymbolID 尾碼 -M

用法：
  python tx_night.py            # 印出訊息（不自行發 TG；cron 由 stdout 推播）
  python tx_night.py --dry-run  # 同上，語意標記

歷史紀錄：data/tx_night.json（逐次 append，同日覆寫）
"""
import argparse
import datetime as dt
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "data" / "tx_night.json"
API = "https://mis.taifex.com.tw/futures/api/getQuoteList"
UA = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

MONTH_LETTER = {c: i + 1 for i, c in enumerate("ABCDEFGHIJKL")}  # A=1 … L=12
_SYM_RE = re.compile(r"^TXF([A-L])(\d)-([FM])$")


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _quote_list(market_type):
    body = json.dumps(
        {
            "MarketType": str(market_type),
            "SymbolType": "F",
            "KindID": "1",
            "CID": "TXF",
            "ExpireMonth": "",
            "RowIndices": "1,2,3,4,5,6,7",
        }
    ).encode()
    req = urllib.request.Request(API, data=body, headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=15, context=_ctx()).read().decode("utf-8", "replace"))
    return (d.get("RtData") or {}).get("QuoteList") or []


def _num(s):
    s = (s or "").replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _parse(q):
    """把 MIS 單筆報價轉成 dict；解析不到近月契約代碼時回 None。"""
    m = _SYM_RE.match(q.get("SymbolID") or "")
    if not m:
        return None
    mon = MONTH_LETTER[m.group(1)]
    yr = 2020 + int(m.group(2))
    return {
        "sym": q.get("SymbolID"),
        "contract": f"{yr}/{mon:02d}",
        "sort_key": (yr, mon),
        "last": _num(q.get("CLastPrice")),
        "ref": _num(q.get("CRefPrice")),
        "diff": _num(q.get("CDiff")),
        "pct": _num(q.get("CDiffRate")),
        "open": _num(q.get("COpenPrice")),
        "high": _num(q.get("CHighPrice")),
        "low": _num(q.get("CLowPrice")),
        "vol": _num(q.get("CTotalVolume")),
        "oi": _num(q.get("OpenInterest")),
        "date": (q.get("CDate") or "").strip(),
        "time": (q.get("CTime") or "").strip(),
    }


def _near(rows):
    """近月＝(年, 月) 最小者；排除現貨 TXF-S/-P 與無成交價者。"""
    rows = [r for r in rows if r and r.get("last") is not None]
    if not rows:
        return None
    return sorted(rows, key=lambda r: r["sort_key"])[0]


def _fmt(n, dp=0):
    return "—" if n is None else f"{n:,.{dp}f}"


def _fmt_pct(p):
    return "—" if p is None else f"{p:+.2f}%"


def _fmt_diff(d):
    return "—" if d is None else f"{d:+,.0f}"


def _hhmm(t):
    if not t or len(t) < 4:
        return "—"
    return f"{t[0:2]}:{t[2:4]}:{t[4:6]}" if len(t) >= 6 else f"{t[0:2]}:{t[2:4]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只印不記檔（cron wrapper 用）")
    args = ap.parse_args()

    now = dt.datetime.now()
    night = day = None
    err = ""
    try:
        night = _near([_parse(q) for q in _quote_list(1)])
    except Exception as e:
        err = f"夜盤報價抓取失敗：{str(e)[:60]}"
    try:
        day = _near([_parse(q) for q in _quote_list(0)])
    except Exception:
        pass

    if not night and not day:
        print(f"⛔ 台指期夜盤：{err or '期交所無回應'}（{now:%m/%d %H:%M}）")
        return 1

    lines = []
    if night:
        nd = night["date"]
        nd_disp = f"{nd[4:6]}/{nd[6:8]}" if len(nd) == 8 else "—"
        stale = len(nd) == 8 and nd != f"{now:%Y%m%d}"
        tag = "夜盤（上一場，已收盤）" if stale else "夜盤（進行中）"
        lines.append(f"TW 台指期{tag}｜近月 {night['contract']}｜{nd_disp} {_hhmm(night['time'])}")
        lines.append(
            f"　現價 {_fmt(night['last'])}　{_fmt_diff(night['diff'])} 點（{_fmt_pct(night['pct'])}）"
        )
        lines.append(
            f"　高 {_fmt(night['high'])}／低 {_fmt(night['low'])}　量 {_fmt(night['vol'])} 口"
        )
        if day and day.get("last") is not None:
            gap = night["last"] - day["last"]
            gp = gap / day["last"] * 100 if day["last"] else None
            # 日盤尚未收盤時（09:00–13:45）不能寫「日盤收」，否則口徑錯
            day_live = (
                day.get("date") == f"{now:%Y%m%d}"
                and dt.time(9, 0) <= now.time() <= dt.time(13, 45)
            )
            base_tag = "今日日盤現價" if day_live else "日盤收"
            lines.append(f"　對{base_tag} {_fmt(day['last'])}：{_fmt_diff(gap)} 點（{_fmt_pct(gp)}）")
        if night["oi"] is not None:
            lines.append(f"　未平倉 {_fmt(night['oi'])} 口")
    else:
        lines.append("TW 台指期夜盤：查無報價")
        if day:
            lines.append(
                f"　（最近日盤 {day['contract']} 收 {_fmt(day['last'])}，{_fmt_diff(day['diff'])} 點／{_fmt_pct(day['pct'])}）"
            )
    if err:
        lines.append(f"　⚠️ {err}")

    msg = "\n".join(lines)

    if not args.dry_run:
        try:
            OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
            hist = {}
            if OUT_JSON.exists():
                try:
                    hist = json.loads(OUT_JSON.read_text(encoding="utf-8"))
                except Exception:
                    hist = {}
            hist[f"{now:%Y-%m-%d}"] = {
                "captured_at": now.isoformat(timespec="seconds"),
                "night": night,
                "day": day,
            }
            if len(hist) > 400:
                for k in sorted(hist)[:-400]:
                    hist.pop(k, None)
            OUT_JSON.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f"（歷史寫入失敗：{str(e)[:50]}）")

    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
