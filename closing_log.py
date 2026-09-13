#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""closing_log.py — 龍九每日收工登錄（no_agent，零 LLM）

取代原 agent cron「龍九每日收工登錄 21:40」（2a44a680bec1，13 天 NT$15.8 ≈ 每月 NT$36）。
工作內容是純資料操作：把今天的已完成事項 append 進 work_log.json（供儀表板
🛠️ 系統工作日誌使用），重複者跳過。規則沿用原 job prompt：
  1. 來源 dashboard_decisions.json["decisions"]（status 為完成類）＋ pending_decisions（待辦類）
  2. 以 item 前 25 字元去重
  3. append {"date": 今天, "category": "完成"/"應辦", "item": …, "detail": …}
  4. 只改 work_log.json，結構必須維持合法 JSON 陣列
安全機制：寫入前先備份 work_log.json.bak-<ts>；寫入後重新 load 驗證筆數與結構，
驗證失敗即還原備份並以非零碼結束（cron 會發錯誤警報）。
輸出：N>0 → 摘要訊息；N=0 → 無輸出（no_agent 靜默＝不推送）。
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
DECISIONS = BASE / "dashboard_decisions.json"
WORKLOG = BASE / "work_log.json"
PENDING = BASE / "pending_decisions.json"
DONE_MARKERS = ("完成", "completed", "✅", "done")
TODO_MARKERS = ("待辦",)
DEDUP_CHARS = 25


def norm_status(s) -> str:
    return str(s or "").strip().lower()


def is_done(status) -> bool:
    s = str(status or "")
    return any(m.lower() in s.lower() for m in DONE_MARKERS)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def collect_today() -> list[dict]:
    today = dt.date.today().isoformat()
    out: list[dict] = []
    dec = load_json(DECISIONS, {})
    items = dec.get("decisions", dec) if isinstance(dec, dict) else dec
    for d in (items or []):
        if not isinstance(d, dict) or not is_done(d.get("status")):
            continue
        ts = str(d.get("timestamp") or d.get("date") or "")
        if not ts.startswith(today):
            continue
        title = (d.get("task") or d.get("decision") or d.get("title") or "").strip()
        summary = (d.get("summary") or d.get("detail") or "").strip()
        if not title and not summary:
            continue
        item = f"{title}（{summary}）" if (title and summary) else (title or summary)
        out.append({"date": today, "category": "完成",
                    "item": item[:180], "detail": (summary or title)[:120]})
    pend = load_json(PENDING, {})
    plist = pend.get("pending_decisions", pend) if isinstance(pend, dict) else pend
    for p in (plist or []):
        if not isinstance(p, dict):
            continue
        st = str(p.get("status") or "")
        if not any(m in st for m in TODO_MARKERS):
            continue
        ts = str(p.get("timestamp") or p.get("date") or "")
        if ts and not ts.startswith(today):
            continue
        title = (p.get("task") or p.get("title") or p.get("decision") or "").strip()
        if not title:
            continue
        out.append({"date": today, "category": "應辦",
                    "item": title[:180], "detail": (p.get("summary") or "")[:120]})
    return out


def main() -> None:
    if not WORKLOG.exists():
        print("⚠️ 收工登錄失敗：找不到 work_log.json")
        sys.exit(2)
    log = load_json(WORKLOG, None)
    if not isinstance(log, list):
        print("⚠️ 收工登錄失敗：work_log.json 不是 JSON 陣列（不動它）")
        sys.exit(3)

    existing_keys = [str(x.get("item", ""))[:DEDUP_CHARS] for x in log
                     if isinstance(x, dict)]

    def is_dup(item: str) -> bool:
        k = item[:DEDUP_CHARS]
        if k in existing_keys:
            return True
        # v2：候選條目以既有條目為前綴（或反之）也算重複 — 防「同事項多寫了摘要尾巴」
        return any(e and (item.startswith(e) or k.startswith(e))
                   for e in existing_keys)

    cand = collect_today()
    new = [c for c in cand if not is_dup(c["item"])]
    # 同批內也去重
    seen = set()
    deduped = []
    for c in new:
        k = c["item"][:DEDUP_CHARS]
        if k in seen:
            continue
        seen.add(k)
        deduped.append(c)
    new = deduped

    if not new:
        return  # 靜默（no_agent：無輸出＝不推送）

    bak = WORKLOG.with_name(f"work_log.json.bak-{dt.datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(WORKLOG, bak)
    merged = log + new
    try:
        WORKLOG.write_text(json.dumps(merged, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        check = json.loads(WORKLOG.read_text(encoding="utf-8"))
        if not isinstance(check, list) or len(check) != len(merged):
            raise ValueError(f"驗證失敗（{len(check)} != {len(merged)}）")
    except Exception as e:
        shutil.copy2(bak, WORKLOG)
        print(f"⚠️ 收工登錄失敗已還原 work_log.json：{e}")
        sys.exit(4)

    n_done = sum(1 for x in new if x["category"] == "完成")
    n_todo = len(new) - n_done
    lines = [f"✅ 已登錄 {len(new)} 筆（完成 {n_done} / 應辦 {n_todo}）："]
    for x in new:
        lines.append(f"- {x['category']}｜{x['item'][:110]}")
    lines.append(f"（work_log {len(log)}→{len(merged)} 筆；備份 {bak.name}）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
