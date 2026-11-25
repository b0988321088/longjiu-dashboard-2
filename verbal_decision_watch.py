#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""口頭裁決偵測（2026-11-25 使用者核准 P2-①，22:35 執行）

問題實例：11/24 21:01 使用者在對話說「暫緩」，但沒有任何寫方把它落進
dashboard_decisions → 隔天 18:30 的 CIO 審查仍把 304,572 的減碼單當成
「已核准未執行」。CIO 只能讀 dashboard_decisions，看不到對話。

本支做的事（只偵測、不改任何狀態）：
1. 撈今日（台北日）role=user 的訊息，排除 cron 會話事件與系統通知。
2. 用裁決語彙比對（核准／同意／暫緩／不補／作廢／取消／延後／暫停／照做；
   單字「改／好」僅在極短訊息時算）。
3. 比對 dashboard_decisions 今日 source=user 的筆數。
4. 有裁決語句但決策庫 0 筆（或明顯少於語句數）→ 出聲；一致 → 靜默。

刻意不做的事：不自動寫入決策（避免把「我覺得像裁決」變成假裁決）。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TPE = timezone(timedelta(hours=8))
BASE = Path(__file__).resolve().parent
DEC = BASE / "dashboard_decisions.json"
STATE_DB = Path.home() / "AppData" / "Local" / "hermes" / "state.db"

CUE = re.compile(r"核准|同意|暫緩|不補|作廢|取消|延後|暫停|照做|不要|停用")
SHORT_CUE = {"改", "好", "做", "停"}
NOISE = re.compile(r"^\[(ASYNC DELEGATION|IMPORTANT|PRIOR CONTEXT)|^# Cron Job:|^\[OUT-OF-BAND")


def _decisions_today(ref: date) -> int:
    try:
        d = json.loads(DEC.read_text(encoding="utf-8"))
    except Exception:
        return -1
    arr = d if isinstance(d, list) else (d.get("decisions") or [])
    n = 0
    for r in arr:
        ts = str(r.get("timestamp") or "")
        if not ts.startswith(ref.isoformat()):
            continue
        if str(r.get("source")) != "user":
            continue
        n += 1
    return n


def _user_messages(ref: date) -> list[str]:
    if not STATE_DB.exists():
        return []
    a = datetime(ref.year, ref.month, ref.day, tzinfo=TPE).timestamp()
    b = a + 86400
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("""
            select m.content
              from messages m left join sessions s on s.session_key = m.session_id
             where m.role='user' and m.timestamp >= ? and m.timestamp < ?
               and coalesce(s.source,'') != 'cron'
             order by m.timestamp""", (a, b))
        out, seen = [], set()
        for r in cur.fetchall():
            t = (r["content"] or "").strip()
            if not t or NOISE.search(t) or t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out
    finally:
        con.close()


def _is_decision(t: str) -> bool:
    if len(t) > 400:          # 長貼文多半是轉貼或截圖 OCR
        return False
    if t.strip() in SHORT_CUE:
        return True
    return bool(CUE.search(t))


def build(ref: date) -> str:
    msgs = [m for m in _user_messages(ref) if _is_decision(m)]
    n_dec = _decisions_today(ref)
    if n_dec < 0:
        return f"🧩 口頭裁決偵測：dashboard_decisions.json 讀不到 → 無法對帳（fail-loud）"
    if not msgs:
        return ""
    if n_dec >= len(msgs):
        return ""
    lines = [f"🧩 口頭裁決未落庫（{ref.month}/{ref.day:02d}）",
             f"今日對話有 {len(msgs)} 句裁決性回覆，但 dashboard_decisions 今日 source=user 只有 {n_dec} 筆。",
             "偵測到的句子："]
    for m in msgs[:6]:
        lines.append("　·「" + m.replace("\n", " ")[:60] + "」")
    if len(msgs) > 6:
        lines.append(f"　· …另有 {len(msgs) - 6} 句")
    lines += ["", "處理：回「補登」我會用唯一入口寫入（含時間戳與來源）；回「免補」代表這些不是裁決。"]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ref = date.fromisoformat(a.today) if a.today else datetime.now(TPE).date()
    out = build(ref)
    if not out:
        if a.dry_run:
            print(f"[{ref}] 對話與決策庫一致 → 靜默")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
