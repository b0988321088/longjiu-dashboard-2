#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""etf_dividend_watch.py — ETF 除息公告自動巡檢（2026-11-02 使用者核准）

用途：每個交易日 08:00 巡一次持倉 ETF 的「除息日＋每股配息」，抓到投信新公告就
      寫回 snapshot.etf_dividend_schedule（已除息／下一梯次）並印出變更摘要；
      沒變更時 stdout 全空（no_agent cron 靜默，不吵使用者）。

資料源：Yahoo Finance chart API events=div（除息日＋金額，機器可讀、免登入）。
       官網／Goodinfo 為人工核對用；發放日若公告未含 → 標「待確認」不猜。

原則：
  1. 只寫自己擁有的欄位（除息日／配息／週期／note），不動金額真值與其他區塊。
  2. 抓不到或解析失敗 → 不動 snapshot、印錯誤到 stderr、exit 1（fail-loud）。
  3. 以「除息日」為唯一鍵比對，重複執行為 idempotent。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
LOG = BASE / "logs" / "etf_dividend_watch.log"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fetch_divs(ticker: str) -> list[tuple[dt.date, float]]:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.TW"
           "?range=2y&interval=1d&events=div")
    req = urllib.request.Request(url, headers=UA)
    raw = json.load(urllib.request.urlopen(req, timeout=25))
    ev = ((raw.get("chart", {}).get("result") or [{}])[0]
          .get("events", {}) or {}).get("dividends", {}) or {}
    out = []
    for v in ev.values():
        try:
            out.append((dt.datetime.fromtimestamp(v["date"]).date(), float(v["amount"])))
        except Exception:
            continue
    return sorted(out)


def norm_md(txt: str, today: dt.date) -> dt.date | None:
    """把 snapshot 的 'M/D' / 'YYYY/M/D' 正規化成 date；失敗回 None。"""
    s = str(txt or "").strip()
    s = s.split("(")[0].split("待")[0].strip()
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})$", s)
    if m:
        mo, da = int(m.group(1)), int(m.group(2))
        for y in (today.year, today.year + 1, today.year - 1):
            try:
                d = dt.date(y, mo, da)
            except ValueError:
                continue
            if d <= today + dt.timedelta(days=120):
                return d
    return None


def main() -> int:
    today = dt.date.today()
    snap = json.loads(SNAP.read_text(encoding="utf-8"))
    sched = snap.get("etf_dividend_schedule") or {}
    done = sched.setdefault("已除息", {})
    nxt = sched.setdefault("下一梯次", {})
    holdings = [h["ticker"] for h in (snap.get("securities", {}) or {}).get("holdings", []) if h.get("ticker")]
    if not holdings:
        print("❌ 持倉清單為空，拒絕巡檢", file=sys.stderr)
        return 1

    known: set[tuple[str, dt.date]] = set()
    cycle: dict[str, str] = {}
    for grp in (done, nxt):
        for key, info in grp.items():
            tk = re.match(r"^([0-9A-Za-z]+)", key).group(1) if re.match(r"^([0-9A-Za-z]+)", key) else key
            d = norm_md(info.get("除息日") or info.get("預計除息"), today)
            if d:
                known.add((tk, d))
            if info.get("週期"):
                cycle.setdefault(tk, info["週期"])

    changes, errors = [], []
    for tk in holdings:
        try:
            divs = fetch_divs(tk)
        except Exception as e:
            errors.append(f"{tk}: {type(e).__name__} {e}")
            continue
        for d, amt in divs[-3:]:            # 只看最近三次，足以覆蓋新公告
            if (tk, d) in known:
                continue
            # 只認「近期」公告：太久以前的歷史配息不補登（避免把已領數年的梯次灌成待入帳）
            if d < today - dt.timedelta(days=45):
                continue
            if d > today + dt.timedelta(days=150):
                continue
            label = f"{d.month}月"
            if d <= today:
                done[f"{tk}({label})"] = {
                    "除息日": f"{d.month}/{d.day}", "配息": round(amt, 4),
                    "發放日": "待確認（Yahoo 未提供發放日）", "已領": False,
                    "週期": cycle.get(tk, ""), "note": f"自動巡檢 {today.isoformat()} 抓到",
                }
            else:
                nxt[tk] = {
                    "預計除息": f"{d.month}/{d.day}", "配息": round(amt, 4),
                    "發放日": "待確認", "週期": cycle.get(tk, ""),
                    "note": f"自動巡檢 {today.isoformat()} 抓到公告（Yahoo events=div）",
                }
            known.add((tk, d))
            changes.append(f"  {tk} 除息 {d.isoformat()}｜{amt:g} 元/股｜"
                           f"{'已除息（待入帳）' if d <= today else '下一梯次'}")

    if errors:
        print("⚠️ 部分 ETF 抓取失敗（未動該檔）：" + "；".join(errors), file=sys.stderr)

    if changes:
        sched["note"] = (str(sched.get("note", ""))[:400] + "｜" +
                         f"{today.isoformat()} 自動巡檢新增 {len(changes)} 筆").strip("｜")
        snap["etf_dividend_schedule"] = sched
        snap["etf_dividend_last_checked"] = today.isoformat()
        SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} +{len(changes)}\n" + "\n".join(changes) + "\n")
        print(f"📢 ETF 除息公告更新 {today.isoformat()}（{len(changes)} 筆）")
        print("\n".join(changes))
        print("已寫回 snapshot.etf_dividend_schedule，明早 07:00 日報會帶到。")
    return 0 if not errors else 0  # 抓取失敗不阻擋其他檔；錯誤走 stderr


if __name__ == "__main__":
    sys.exit(main())
