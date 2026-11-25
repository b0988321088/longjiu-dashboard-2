#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提醒回覆自動落庫（2026-11-25 使用者核准：閉環最後一段）

原本：使用者回「✅ OI-07 已處理」→ 要我人在線、手動跑 apply_action_reply.py。
現在：這支每 10 分鐘掃一次對話，抓到「編號＋動作」就自動落地，並回一張收據。

設計邊界（刻意保守，寧可漏接不要誤關）：
- 只讀 telegram 來源的 user 訊息，排除 cron 會話與系統通知。
- 訊息含問號／疑問詞（嗎、呢、？）→ 不動作（那是提問不是裁決）。
- 訊息含否定前提（還沒、未、不要、不用、先不）→ 只認「作廢」，不認「已完成」。
- 冪等：目標已是 CLOSED／WAIVED 就不重複寫，也不重複推收據。
- checkpoint 存在 data/reminder_autoreply_state.json；首跑從「現在」開始，不回放歷史。
- 實際落地一律呼叫 apply_action_reply.py（單一寫入入口），本支不自己改 JSON。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

TPE = timezone(timedelta(hours=8))
BASE = Path(__file__).resolve().parent
OEI = BASE / "data" / "weekly_open_items.json"
STATE = BASE / "data" / "reminder_autoreply_state.json"
APPLY = BASE / "apply_action_reply.py"
DB = Path.home() / "AppData" / "Local" / "hermes" / "state.db"

KEY = re.compile(r"\b(OI-\d{2}|PD-\d|CV-[0-9A-Za-z\-]+|EV-[0-9\-]+)\b")
QUESTION = re.compile(r"[？?]|嗎|呢|是否|要不要")
NEGATE = re.compile(r"還沒|尚未|未完成|沒有|不要|不用|先不|別")
VOID = re.compile(r"作廢|取消|不用了|不理|算了|別管")
SNOOZE = re.compile(r"延後|延期|晚點|再等等|過幾天|下週再|明天再")
DONE = re.compile(r"已處理|處理好|處理完|完成了|完成|辦好|好了|送件了|已送件|已申請|已補|搞定|結案|done", re.I)
NOISE = re.compile(r"^\[(ASYNC DELEGATION|IMPORTANT|PRIOR CONTEXT)|^# Cron Job:|^\[OUT-OF-BAND")


def _state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_ts": datetime.now(TPE).timestamp(), "done": []}


def _save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    s["done"] = s.get("done", [])[-400:]
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def _messages(after: float) -> list[tuple[float, str]]:
    if not DB.exists():
        return []
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        cur = con.cursor()
        cur.execute("""
            select m.content, m.timestamp
              from messages m left join sessions s on s.session_key = m.session_id
             where m.role='user' and m.timestamp > ?
               and coalesce(s.source,'') != 'cron'
             order by m.timestamp""", (after,))
        out, seen = [], set()
        for r in cur.fetchall():
            t = (r["content"] or "").strip()
            if not t or NOISE.search(t):
                continue
            h = hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]
            if h in seen:
                continue
            seen.add(h)
            out.append((float(r["timestamp"]), t))
        return out
    finally:
        con.close()


def _status_of(key: str) -> str:
    try:
        d = json.loads(OEI.read_text(encoding="utf-8"))
    except Exception:
        return ""
    it = next((i for i in d.get("items", []) if i.get("id") == key), None)
    return str((it or {}).get("status") or "").upper()


def _parse(text: str) -> list[tuple[str, str, int]]:
    """回傳 [(key, action, days)]；action ∈ done/snooze/void

    兩道防誤判（2026-11-25 實測踩到）：使用者把我的整篇報告貼回來時，
    裡面同時有「OI-07」與「建議作廢」，若只看全文會把提醒關掉。
    → ①長訊息（>200 字）一律不解析（真回覆都很短）②動作詞必須落在編號
      前後 16 字內才算，杜絕「文章裡剛好提到」。
    """
    if QUESTION.search(text) or len(text) > 200:
        return []
    keys = list(dict.fromkeys(KEY.findall(text)))
    if not keys or len(keys) > 2:
        return []
    days = 7
    m = re.search(r"(\d+)\s*天", text)
    if m:
        days = max(1, min(int(m.group(1)), 90))
    elif "下週" in text:
        days = 7
    elif "明天" in text:
        days = 1

    # 子句切分：動作詞只在「與編號同一個短子句」內才算（避免引用整段文章誤關提醒）
    clauses = [c for c in re.split(r"[，。；;！!、｜|…\.]+", text) if c.strip()]
    out: list[tuple[str, str, int]] = []
    for k in keys:
        win = next((c for c in clauses if k in c and len(c) <= 40), "")
        if not win:
            continue
        if VOID.search(win):
            act = "void"
        elif SNOOZE.search(win):
            act = "snooze"
        elif DONE.search(win) and not NEGATE.search(win):
            act = "done"
        elif "✅" in win and not NEGATE.search(win):
            act = "done"     # 我們自己的提醒格式：✅ <編號> 已處理
        else:
            continue         # 只有編號、沒有動作語 → 不動（可能只是提到）
        out.append((k, act, days))
    return out


def _apply(key: str, action: str, days: int, note: str, dry: bool) -> str:
    cmd = [sys.executable, str(APPLY)]
    if action == "done":
        cmd += ["--done", key, "--note", note]
    elif action == "snooze":
        cmd += ["--snooze", key, "--days", str(days), "--note", note]
    else:
        cmd += ["--void", key, "--note", note]
    if dry:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=str(BASE), timeout=180)
    tail = ((r.stdout or "").strip().splitlines() or ["無輸出"])[-1]
    return tail if r.returncode == 0 else f"⚠️ {key} 落地失敗 rc={r.returncode}｜{tail}"


def run(dry: bool = False) -> str:
    st = _state()
    after = float(st.get("last_ts") or 0)
    msgs = _messages(after)
    if not msgs:
        return ""
    done_set = set(st.get("done") or [])
    receipts: list[str] = []
    for ts, text in msgs:
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
        if h in done_set:
            continue
        for key, action, days in _parse(text):
            if len(text) > 60:
                # 長訊息常是引用或轉貼（實測：把報告貼回來會誤關提醒）→ 只報告、不落地
                receipts.append(f"⏸️ 「{text[:28]}…」含 {key}，訊息太長未自動落庫；"
                                f"確定要處理請回短句「{key} 已處理」")
                if not dry:
                    done_set.add(h)
                continue
            cur = _status_of(key)
            if action in ("done", "void") and cur in ("CLOSED", "WAIVED"):
                continue                     # 冪等：已經結案就不重寫
            note = f"自動落庫（對話原句：{text[:40]}）"
            receipts.append(_apply(key, action, days, note, dry))
            if not dry:
                done_set.add(h)
        if not dry:
            st["last_ts"] = max(float(st.get("last_ts") or 0), ts)
            st["done"] = list(done_set)
    if not dry:
        _save_state(st)
    if not receipts:
        return ""
    head = "🤖 自動落庫（偵測到你回覆的處理動作）"
    return "\n".join([head] + [f"· {r}" for r in receipts])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="把 checkpoint 拉回現在，不回放歷史")
    a = ap.parse_args()
    if a.reset:
        _save_state({"last_ts": datetime.now(TPE).timestamp(), "done": []})
        print("checkpoint 已重設為現在")
        return 0
    out = run(a.dry_run)
    if out:
        print(out)
    elif a.dry_run:
        print("[dry-run] 無可落庫的回覆（未動作）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
