#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reconcile_decision_intake.py — 「今日核准」vs「今日入庫」ID 集合對帳（CIO 復盤前必跑）。

CIO 2026-09-23 ② 的缺口本質是「時序不可靠」：核准有留下、程式有留下，但 dashboard_decisions
在 CIO 18:30 跑的時候是殘缺的，靠晚上人工補。這支把「有沒有漏」變成可判定的檢查：

  今日收據（decision_intake_receipts.jsonl，由 append_dashboard_decisions.py 產生）
        ↓
  今日 dashboard_decisions（source=user）
        ↓
  ID 集合比對
        ↓
  一致 → PASS ／ 不一致 → 印出缺口筆數與明細（exit 1）

另可加 --notion：向 Notion 分析 DB 查「今日建立的決策頁」數，與檔案今日 user 筆數對照
（獨立第二來源；Notion 不可達時明確標示「未查核」，不靜默通過）。

用法：
  python reconcile_decision_intake.py [--date 2026-10-02] [--notion] [--quiet]
退出碼：0 = PASS；1 = 有缺口（fail-loud，供閘門/復盤前置使用）；2 = 有來源未查核
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
DEC_FILE = REPO / "dashboard_decisions.json"
RECEIPT_FILE = REPO / "data" / "decision_intake_receipts.jsonl"
TPE = timezone(timedelta(hours=8))


def _today(arg=None):
    if arg:
        return arg
    return datetime.now(TPE).strftime("%Y-%m-%d")


def load_receipts(day):
    if not RECEIPT_FILE.exists():
        return []
    out = []
    for ln in RECEIPT_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if str(r.get("ts", "")).startswith(day):
            out.append(r)
    return out


def load_intake(day):
    d = json.loads(DEC_FILE.read_text(encoding="utf-8"))
    return [x for x in d.get("decisions", [])
            if str(x.get("timestamp", "")).startswith(day) and str(x.get("source")) == "user"]


def notion_today_count(day):
    """獨立第二來源：Notion 分析 DB 今日建立的頁數。回傳 (count, note)。"""
    try:
        sys.path.insert(0, str(REPO))
        from notion_bridge import notion_post  # noqa
        import os
        db = ""
        for p in (Path.home() / "AppData/Local/hermes/.env", REPO / ".env"):
            if p.exists():
                for ln in p.read_text(encoding="utf-8").splitlines():
                    if ln.startswith("NOTION_ANALYSIS_DB_ID="):
                        db = ln.split("=", 1)[1].strip()
        if not db:
            return None, "找不到 NOTION_ANALYSIS_DB_ID（未查核）"
        payload = {"filter": {"timestamp": "created_time", "created_time": {"on_or_after": day}},
                   "page_size": 100}
        r = notion_post(f"/databases/{db}/query", payload)
        res = r.get("results")
        if res is None:
            return None, f"Notion 回應無 results（未查核）: {str(r)[:120]}"
        return len(res), f"Notion 今日建立 {len(res)} 頁"
    except Exception as e:
        return None, f"Notion 查核失敗（未查核）: {e}"


def main():
    ap = argparse.ArgumentParser(description="今日核准 vs 今日入庫 對帳")
    ap.add_argument("--date")
    ap.add_argument("--notion", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    day = _today(a.date)

    rec = load_receipts(day)
    intake = load_intake(day)
    rec_ok = [r for r in rec if r.get("ok")]
    rec_ids = {r.get("id") for r in rec_ok}
    file_ids = {x.get("id") for x in intake}

    missing = sorted(rec_ids - file_ids)          # 收了收據但沒進檔 → 真缺口
    unregistered = sorted(file_ids - rec_ids)     # 進檔但沒有收據 → 未經單一入口（人工/舊路徑）

    if not a.quiet:
        print(f"=== 決策入庫對帳（{day}）===")
        print(f"  收據（單一入口）：{len(rec)} 筆（成功 {len(rec_ok)}）")
        print(f"  檔案（source=user）：{len(intake)} 筆")
        print(f"  收據 ∩ 檔案：{len(rec_ids & file_ids)} 筆")

    rc = 0
    if missing:
        print(f"  ❌ 缺口 {len(missing)} 筆：核準已留收據但未入庫 →")
        for i in missing:
            t = next((r.get("task") for r in rec_ok if r.get("id") == i), "")
            print(f"     - {i}｜{str(t)[:44]}")
        rc = 1
    if unregistered:
        print(f"  ⚠️ {len(unregistered)} 筆入庫沒有收據（未經 append_dashboard_decisions.py，可能是舊路徑或人工補）：")
        for i in unregistered:
            t = next((x.get("task") for x in intake if x.get("id") == i), "")
            print(f"     - {i}｜{str(t)[:44]}")
    if not missing and not unregistered:
        print(f"  ✅ 一致（{len(file_ids)} 筆；今日無缺口）")

    if a.notion:
        cnt, note = notion_today_count(day)
        print(f"  （第二來源）{note}")
        if cnt is None:
            rc = rc or 2
        elif cnt != len(intake):
            print(f"  ⚠️ Notion 今日 {cnt} 筆 ≠ 檔案今日 user {len(intake)} 筆 → 有一邊漏記，需人工確認")
            rc = rc or 2
    return rc


if __name__ == "__main__":
    sys.exit(main())
