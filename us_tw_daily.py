#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""美股收盤 + 台指期漲跌 每日監控（2026-11-24 使用者要求）

用途：每天早上（台北 08:35）把「昨夜美股四大指數收盤」與「台指期日盤漲跌」一起推播。
資料源：
  美股／加權指數 = Yahoo Finance chart API（^GSPC ^IXIC ^DJI ^SOX ^TWII）
  台指期         = 期交所 futDataDown CSV（Big5，取近月 TX「一般交易時段」＝日盤收盤）

用法：
  python us_tw_daily.py            # 抓取並推播
  python us_tw_daily.py --dry-run  # 只印不推
  python us_tw_daily.py --date 2026/11/24   # 指定台指期交易日

歷史紀錄：data/us_tw_daily.json（逐日 append，同一日期覆寫）
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT_JSON = BASE / "data" / "us_tw_daily.json"
UA = {"User-Agent": "Mozilla/5.0"}

INDEXES = [
    ("^GSPC", "S&P 500"),
    ("^IXIC", "那斯達克"),
    ("^DJI", "道瓊"),
    ("^SOX", "費城半導體"),
]


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _load_env():
    """讀 Hermes .env（腳本可能在 cron 下執行、沒有匯出環境變數）。"""
    cands = [
        BASE / ".env",
        Path.home() / "AppData/Local/hermes/.env",
        Path.home() / ".hermes/.env",
    ]
    for p in cands:
        try:
            if not p.exists():
                continue
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass


def _tg_send(text):
    tok = os.environ.get("TG_TOKEN", "")
    chat = os.environ.get("TG_CHAT_ID", "")
    if os.environ.get("LJ_NO_TELEGRAM") == "1" or not tok or not chat:
        print(text)
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{tok}/sendMessage",
            json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
            timeout=15,
        )
        return r.ok
    except Exception as e:
        print(f"⚠️ TG 失敗: {e}\n{text}")
        return False


def yahoo_index(sym):
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(sym)
        + "?range=5d&interval=1d"
    )
    req = urllib.request.Request(url, headers=UA)
    d = json.loads(urllib.request.urlopen(req, timeout=12, context=_ctx()).read())
    m = d["chart"]["result"][0]["meta"]
    return {
        "px": m.get("regularMarketPrice"),
        "pct": round(m.get("regularMarketChangePercent") or 0.0, 2),
        "ts": m.get("regularMarketTime"),
    }


def taifex_tx(day: dt.date):
    """回傳近月 TX 的一般交易時段（日盤）與盤後時段（夜盤）。"""
    q = (
        "https://www.taifex.com.tw/cht/3/futDataDown?down_type=1"
        f"&queryStartDate={day:%Y/%m/%d}&queryEndDate={day:%Y/%m/%d}"
        "&commodity_id=TX"
    )
    req = urllib.request.Request(q, headers=UA)
    raw = urllib.request.urlopen(req, timeout=20, context=_ctx()).read()
    txt = raw.decode("big5", errors="replace")
    rows = list(csv.reader(io.StringIO(txt)))
    if len(rows) < 2:
        return None
    head = [h.strip() for h in rows[0]]
    try:
        i_date = head.index("交易日期")
        i_cid = head.index("契約")
        i_mon = 0
        for i, h in enumerate(head):
            if h.startswith("到期月份"):
                i_mon = i
                break
        i_open = head.index("開盤價")
        i_high = head.index("最高價")
        i_low = head.index("最低價")
        i_close = head.index("收盤價")
        i_chg = head.index("漲跌價")
        i_pct = head.index("漲跌%")
    except ValueError:
        return None
    i_sess = head.index("交易時段") if "交易時段" in head else None
    i_vol = next((i for i, h in enumerate(head) if "成交量" in h and "買賣" not in h), None)

    def num(s):
        s = (s or "").replace(",", "").strip()
        try:
            return float(s)
        except Exception:
            return None

    recs = []
    for r in rows[1:]:
        if len(r) <= i_close:
            continue
        if r[i_cid].strip() != "TX":
            continue
        recs.append(
            {
                "date": r[i_date].strip(),
                "month": r[i_mon].strip(),
                "session": (r[i_sess].strip() if i_sess is not None and len(r) > i_sess else ""),
                "open": num(r[i_open]),
                "high": num(r[i_high]),
                "low": num(r[i_low]),
                "close": num(r[i_close]),
                "chg": num(r[i_chg]),
                "pct": (r[i_pct] or "").strip(),
                "vol": (num(r[i_vol]) if i_vol is not None and len(r) > i_vol else None),
            }
        )
    if not recs:
        return None
    # 近月＝到期月份最小者（排除價差/週別合約）
    months = sorted({x["month"] for x in recs if x["month"]})
    near = months[0] if months else None
    recs = [x for x in recs if x["month"] == near]
    day_sess = next((x for x in recs if "一般" in x["session"]), None)
    night_sess = next((x for x in recs if "盤後" in x["session"]), None)
    if day_sess is None and recs:
        day_sess = recs[0]
    return {"month": near, "day": day_sess, "night": night_sess}


def fmt(n, dp=2):
    if n is None:
        return "—"
    return f"{n:,.{dp}f}"


def fmt_pct(p):
    if p is None:
        return "—"
    return f"{p:+.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--date", help="台指期交易日 YYYY/MM/DD（預設：最近有資料的營業日）")
    args = ap.parse_args()
    _load_env()
    today = dt.date.today()

    idx = {}
    for sym, name in INDEXES:
        try:
            idx[sym] = yahoo_index(sym)
        except Exception as e:
            idx[sym] = {"err": str(e)[:70]}

    twii = None
    try:
        twii = yahoo_index("^TWII")
    except Exception:
        pass

    # 台指期：從指定日往回找最多 6 天
    tx = None
    day_used = None
    if args.date:
        d0 = dt.datetime.strptime(args.date, "%Y/%m/%d").date()
    else:
        d0 = today
    for back in range(0, 7):
        d = d0 - dt.timedelta(days=back)
        if d.weekday() >= 5:
            continue
        try:
            got = taifex_tx(d)
        except Exception:
            got = None
        if got and got.get("day") and got["day"].get("close") is not None:
            tx, day_used = got, d
            break

    # 美股報價時間（台北）
    ts = None
    for k in ("^GSPC", "^IXIC"):
        if isinstance(idx.get(k), dict) and idx[k].get("ts"):
            ts = idx[k]["ts"]
            break
    us_time = ""
    if ts:
        us_time = dt.datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")

    lines = []
    lines.append(f"🇺🇸 美股收盤（台北 {us_time}）" if us_time else "🇺🇸 美股收盤")
    for sym, name in INDEXES:
        v = idx.get(sym) or {}
        if v.get("err"):
            lines.append(f"　{name}：抓取失敗")
            continue
        mark = " ⚠️" if abs(v.get("pct") or 0) >= 3 else ""
        lines.append(f"　{name:<6} {fmt(v.get('px'), 2):>12}　{fmt_pct(v.get('pct'))}{mark}")
    lines.append("")
    if tx and day_used:
        d = tx["day"]
        lines.append(f"🇹🇼 台指期（{day_used:%m/%d} 日盤・近月 {tx['month']}）")
        lines.append(
            f"　收盤 {fmt(d.get('close'), 0)}　漲跌 {d.get('chg') or 0:+,.0f} 點（{d.get('pct') or '—'}）"
        )
        if d.get("vol"):
            lines.append(f"　成交量 {d['vol']:,.0f} 口")
        if tx.get("night"):
            n = tx["night"]
            lines.append(
                f"　夜盤收 {fmt(n.get('close'), 0)}　{n.get('chg') or 0:+,.0f} 點（{n.get('pct') or '—'}）"
            )
        if twii:
            lines.append(f"　加權指數 {fmt(twii.get('px'), 2)}（{fmt_pct(twii.get('pct'))}）")
    else:
        lines.append("🇹🇼 台指期：查無資料（期交所尚未更新或休市）")

    msg = "\n".join(lines)

    # 歷史紀錄
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    hist = {}
    if OUT_JSON.exists():
        try:
            hist = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except Exception:
            hist = {}
    key = (day_used or today).isoformat()
    hist[key] = {
        "captured_at": dt.datetime.now().isoformat(timespec="seconds"),
        "us": {k: idx.get(k) for k, _ in INDEXES},
        "twii": twii,
        "tx": tx,
    }
    if len(hist) > 400:
        for k in sorted(hist)[:-400]:
            hist.pop(k, None)
    OUT_JSON.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")

    if args.dry_run:
        print(msg)
        return 0
    ok = _tg_send(msg)
    print("TG:", "已送出" if ok else "未送出（乾跑或無憑證）")
    print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
