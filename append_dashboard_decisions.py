#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_dashboard_decisions.py — dashboard_decisions.json 的唯一寫入入口（核准／決策事件）。

為什麼要有這支（CIO 2026-09-23 ②）：
  CIO Part A（每週一/三 18:30 戰略審計）直接讀 dashboard_decisions.json。過去核准靠
  「晚一點人工補」，CIO 跑的時候看到的是殘缺清單——9/23 就是 3 筆真核准只有 1 筆在檔內。
  這支把「核准事件 → 入庫」變成單一、必經、欄位固定的入口。

設計約束（使用者 2026-10-02 指裁）：
  - 唯一入口：所有 source=user 的決策一律經此寫入（其他寫方不得再直接 append）。
  - 欄位固定產生：id / timestamp（台北 +08:00）/ agent / status / source=user 不由呼叫端自由發揮。
  - 不收尾其他資料流：只碰 dashboard_decisions.json 的 decisions 陣列 + 收據檔。
  - 文字手術寫入（不整檔重排，避免 INC-268 型假 diff）＋寫入前三重驗證。
  - 每次寫入留收據 data/decision_intake_receipts.jsonl，供 reconcile_decision_intake.py 對帳。

用法：
  python append_dashboard_decisions.py --task "標題" --summary "摘要" [--status completed]
                                      [--source user] [--agent Hermes] [--dry-run] [--quiet]
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEC_FILE = REPO / "dashboard_decisions.json"
RECEIPT_FILE = REPO / "data" / "decision_intake_receipts.jsonl"
TPE = timezone(timedelta(hours=8))
MARKER = b'  ],\r\n  "meta"'  # decisions 陣列收尾（後接 "meta" 鍵）


def _now():
    return datetime.now(TPE)


def _next_id(decisions, ts):
    """id 格式沿用管線既有樣式：mem-<YYYYmmddHHMMSS>-<累計筆數>。"""
    return f"mem-{ts.strftime('%Y%m%d%H%M%S')}-{len(decisions)}"


def build_entry(task, summary, status="completed", source="user", agent="Hermes", ts=None):
    dec = json.loads(DEC_FILE.read_text(encoding="utf-8"))
    ts = ts or _now()
    return {
        "id": _next_id(dec["decisions"], ts),
        "timestamp": ts.isoformat(),
        "agent": agent,
        "task": task,
        "summary": summary,
        "status": status,
        "source": source,
    }


def append_entry(entry, dry_run=False):
    """文字手術插入 decisions 陣列尾；回傳 (ok, msg)。"""
    raw = DEC_FILE.read_bytes()
    before = json.loads(raw.decode("utf-8"))
    if raw.count(MARKER) != 1:
        return False, f"decisions 收尾標記命中 {raw.count(MARKER)} 處（預期 1）→ 中止，未寫入"
    i = raw.index(MARKER)
    body = json.dumps(entry, ensure_ascii=False, indent=2).replace("\n", "\r\n  ")
    new = raw[:i] + b"," + b"\r\n  " + body.encode("utf-8") + b"\r\n" + raw[i:]

    # 三重驗證（寫入前）
    try:
        after = json.loads(new.decode("utf-8"))
    except Exception as e:
        return False, f"插入後 JSON 解析失敗：{e}"
    if len(after["decisions"]) != len(before["decisions"]) + 1:
        return False, "decisions 筆數未 +1 → 中止"
    if after["decisions"][-1].get("id") != entry["id"]:
        return False, "新筆不在 decisions 陣列尾 → 中止"
    for k in before:
        if k == "decisions":
            continue
        if k not in after or after[k] != before[k]:
            return False, f"其他頂層鍵被動到（{k}）→ 中止"

    if dry_run:
        return True, f"[dry-run] 將寫入 id={entry['id']}｜{entry['task'][:40]}（{len(before['decisions'])} → {len(after['decisions'])}）"

    backup = DEC_FILE.with_suffix(f".json.bak-append-{_now().strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(DEC_FILE, backup)
    tmp = DEC_FILE.with_suffix(".json.tmp")
    tmp.write_bytes(new)
    os.replace(tmp, DEC_FILE)
    return True, (f"✅ 已入庫 id={entry['id']}｜{entry['task'][:40]}"
                  f"（decisions {len(before['decisions'])} → {len(after['decisions'])}；備份 {backup.name}）")


def write_receipt(entry, ok, msg):
    RECEIPT_FILE.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": entry.get("timestamp"),
        "id": entry.get("id"),
        "task": entry.get("task"),
        "source": entry.get("source"),
        "ok": bool(ok),
        "note": msg,
    }
    with RECEIPT_FILE.open("a", encoding="utf-8", newline="") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\r\n")


def main():
    ap = argparse.ArgumentParser(description="dashboard_decisions.json 唯一寫入入口（核准/決策事件）")
    ap.add_argument("--task", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--status", default="completed")
    ap.add_argument("--source", default="user")
    ap.add_argument("--agent", default="Hermes")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    entry = build_entry(a.task, a.summary, a.status, a.source, a.agent)
    ok, msg = append_entry(entry, dry_run=a.dry_run)
    if not a.dry_run:
        write_receipt(entry, ok, msg)
    print(msg)
    if not ok:
        return 1
    if not a.quiet and not a.dry_run:
        import subprocess
        r = subprocess.run([sys.executable, str(REPO / "reconcile_decision_intake.py"), "--quiet"],
                           capture_output=True, text=True)
        out = (r.stdout or "").strip()
        if r.returncode == 1:
            print("❌ 入庫後對帳未通過（缺口）→ 明細：")
            print(out or (r.stderr or "").strip())
        elif r.returncode == 2:
            print("⚠️ 對帳有來源未查核：")
            print(out or (r.stderr or "").strip())
        elif out:
            print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
