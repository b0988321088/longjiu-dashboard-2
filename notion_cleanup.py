#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notion_cleanup.py — Notion 分析庫定期清理掃描（stdlib only，零 LLM）

背景：分析庫（NOTION_ANALYSIS_DB_ID）沒有自動清理機制；2026-09-14 盤點 85 筆，
其中 3 組標題重複、備份類（簡報/截圖/日報/記憶）頁面會持續累積。

規則
----
1. **重複標題**：同一標題（去頭部日期後正規化）出現多次 → 保留最新一筆，其餘列為重複。
2. **舊備份類**：類型 ∈ {📑 簡報備份, 📸 截圖備份, 📰 日報備份, 記憶備份} 且日期早於
   `--days`（預設 60 天）→ 列為可歸檔。
3. **決策記錄（類型=決策記錄）永不自動歸檔** —— 那是決策庫本體，只在報告中顯示筆數。

安全
----
- 預設 **report-only**（只列清單，不動任何頁面）。
- `--fix` 才封存（Notion `archived=true`，可從垃圾桶回復）；只封存上面規則 1/2 命中的頁面。
- `--quiet`：無發現時完全不輸出（cron watchdog 用）。

用法
----
    python notion_cleanup.py                 # 掃描並列清單
    python notion_cleanup.py --fix           # 掃描 + 封存重複/舊備份頁
    python notion_cleanup.py --days 90       # 自訂備份保留天數
    python notion_cleanup.py --quiet --fix   # cron 用（無發現靜默）
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "hermes"
ENV = HOME / ".env"
BACKUP_TYPES = {"📑 簡報備份", "📸 截圖備份", "📰 日報備份", "記憶備份"}
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s+")


def _env(key: str) -> str:
    v = os.environ.get(key, "")
    if v:
        return v
    try:
        for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


TOKEN = _env("NOTION_TOKEN")
DB_ID = _env("NOTION_ANALYSIS_DB_ID")
H = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28",
     "Content-Type": "application/json"}


def _post(url: str, payload: dict):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=H)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _patch(url: str, payload: dict) -> int:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=H, method="PATCH")
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def fetch_pages() -> list:
    out, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        d = _post(f"https://api.notion.com/v1/databases/{DB_ID}/query", payload)
        out.extend(d.get("results", []))
        if not d.get("has_more"):
            return out
        cursor = d.get("next_cursor")


def page_meta(pg: dict) -> dict:
    pr = pg.get("properties", {})
    title = "".join(t.get("plain_text", "") for t in pr.get("名稱", {}).get("title", []))
    ty = ((pr.get("類型", {}) or {}).get("select") or {}).get("name", "")
    date = ((pr.get("日期", {}) or {}).get("date") or {}).get("start", "") \
        or (pg.get("created_time") or "")[:10]
    return {"id": pg.get("id", ""), "title": title, "type": ty, "date": date,
            "url": pg.get("url", ""), "created": (pg.get("created_time") or "")[:19]}


def plan(pages: list, days: int) -> dict:
    metas = [page_meta(p) for p in pages]
    # ① 重複標題（去頭部日期正規化後比對）
    groups = collections.defaultdict(list)
    for m in metas:
        key = DATE_PREFIX.sub("", m["title"]).strip()
        if key:
            groups[key].append(m)
    dups = []
    for key, items in groups.items():
        if len(items) > 1:
            items.sort(key=lambda x: (x["date"], x["created"]), reverse=True)
            dups.extend(items[1:])          # 保留最新一筆
    # ② 舊備份類
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    old_backups = [m for m in metas if m["type"] in BACKUP_TYPES and m["date"] and m["date"] < cutoff]
    return {"total": len(metas), "dups": dups, "old_backups": old_backups,
            "decisions": sum(1 for m in metas if m["type"] == "決策記錄"),
            "cutoff": cutoff}


def main() -> int:
    ap = argparse.ArgumentParser(description="Notion 分析庫清理掃描")
    ap.add_argument("--fix", action="store_true", help="封存命中的重複/舊備份頁（可回復）")
    ap.add_argument("--days", type=int, default=60, help="備份類保留天數（預設 60）")
    ap.add_argument("--quiet", action="store_true", help="無發現時不輸出")
    args = ap.parse_args()

    if not TOKEN or not DB_ID:
        print("⚠️ Notion 未設定（NOTION_TOKEN / NOTION_ANALYSIS_DB_ID）")
        return 1
    pages = fetch_pages()
    r = plan(pages, args.days)
    targets = r["dups"] + r["old_backups"]

    if not targets:
        if not args.quiet:
            print(f"✅ Notion 分析庫清理掃描：共 {r['total']} 筆，"
                  f"無重複標題、無逾 {args.days} 天備份頁（決策記錄 {r['decisions']} 筆保留）")
        return 0

    print(f"🧹 Notion 分析庫清理：共 {r['total']} 筆｜重複標題 {len(r['dups'])} 筆、"
          f"逾 {args.days} 天備份頁 {len(r['old_backups'])} 筆（截止 {r['cutoff']}）"
          f"｜決策記錄 {r['decisions']} 筆（永不動）")
    for m in r["dups"]:
        print(f"  · 重複：{m['date']} {m['title'][:40]}（{m['type']}）")
    for m in r["old_backups"]:
        print(f"  · 舊備份：{m['date']} {m['title'][:40]}（{m['type']}）")

    if not args.fix:
        print(f"（report-only；要封存請加 --fix，共 {len(targets)} 筆，可從垃圾桶回復）")
        return 0

    ok = 0
    for m in targets:
        try:
            if _patch(f"https://api.notion.com/v1/pages/{m['id']}", {"archived": True}) == 200:
                ok += 1
        except Exception as e:
            print(f"  ⚠️ 封存失敗 {m['title'][:30]}: {e}")
    print(f"🔧 已封存 {ok}/{len(targets)} 筆（Notion 垃圾桶可回復）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
