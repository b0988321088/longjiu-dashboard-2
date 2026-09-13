#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notion_cleanup.py — Notion 分析庫定期清理掃描（stdlib only，零 LLM）

背景：分析庫（NOTION_ANALYSIS_DB_ID）原本沒有自動清理機制；2026-09-14 盤點 85 筆，
其中 3 組標題重複、備份類（簡報/截圖/日報/記憶）頁面會持續累積。

規則
----
1. **重複標題**：同一標題（去頭部日期後正規化）出現多次 → 保留最新一筆，其餘列為重複。
   **決策記錄（類型=決策記錄）一律不列入此規則** —— 決策庫本體永不自動歸檔
   （CIO 審查 2026-09-14 建議 #1：同名決策頁曾被誤判為可封存）。
2. **舊備份類**：類型 ∈ {📑 簡報備份, 📸 截圖備份, 📰 日報備份, 記憶備份} 且日期早於
   `--days`（預設 60 天）→ 列為可歸檔。

安全
----
- 預設 **report-only**（只列清單，不動任何頁面）。
- `--fix` 才封存（Notion `archived=true`，可從垃圾桶回復）；只封存上面規則 1/2 命中的頁面。
- 目標以 page id 去重（避免同一頁被重複封存／計數失真）。
- `--fix` 若有任何封存失敗 → exit 1（cron watchdog 才看得到）。
- `--quiet`：無發現時完全不輸出（cron watchdog 用）。

用法
----
    python notion_cleanup.py                 # 掃描並列清單
    python notion_cleanup.py --fix           # 掃描 + 封存重複/舊備份頁
    python notion_cleanup.py --days 90       # 自訂備份保留天數
    python notion_cleanup.py --fix --quiet   # cron 用（無發現靜默）
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

BACKUP_TYPES = {"📑 簡報備份", "📸 截圖備份", "📰 日報備份", "記憶備份"}
DECISION_TYPE = "決策記錄"
DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}\s+")
MAX_PAGES = 50          # 每頁 100 筆 → 上限 5000 筆，防 API 異常時無限迴圈


def hermes_home() -> Path:
    """HERMES_HOME > LOCALAPPDATA/hermes（Windows）> ~/.hermes（可攜、非 Windows）。"""
    h = os.environ.get("HERMES_HOME")
    if h:
        return Path(h)
    la = os.environ.get("LOCALAPPDATA")
    if la:
        p = Path(la) / "hermes"
        if p.exists():
            return p
    return Path.home() / ".hermes"


ENV = hermes_home() / ".env"


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
    out, cursor, pages = [], None, 0
    while pages < MAX_PAGES:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        d = _post(f"https://api.notion.com/v1/databases/{DB_ID}/query", payload)
        out.extend(d.get("results", []))
        pages += 1
        if not d.get("has_more"):
            break
        cursor = d.get("next_cursor")
    return out


def page_meta(pg: dict) -> dict:
    pr = pg.get("properties", {})
    title = "".join(t.get("plain_text", "") for t in pr.get("名稱", {}).get("title", []))
    ty = ((pr.get("類型", {}) or {}).get("select") or {}).get("name", "")
    date = ((pr.get("日期", {}) or {}).get("date") or {}).get("start", "") \
        or (pg.get("created_time") or "")[:10]
    return {"id": pg.get("id", ""), "title": title, "type": ty, "date": date,
            "created": (pg.get("created_time") or "")[:19]}


def plan(pages: list, days: int) -> dict:
    metas = [page_meta(p) for p in pages]
    # ① 重複標題（決策記錄一律排除：決策庫本體永不歸檔）
    groups = collections.defaultdict(list)
    for m in metas:
        if m["type"] == DECISION_TYPE:
            continue
        key = DATE_PREFIX.sub("", m["title"]).strip()
        if key:
            groups[key].append(m)
    dups = []
    for _key, items in groups.items():
        if len(items) > 1:
            items.sort(key=lambda x: (x["date"], x["created"]), reverse=True)
            dups.extend(items[1:])          # 保留最新一筆
    # ② 舊備份類
    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    old_backups = [m for m in metas
                   if m["type"] in BACKUP_TYPES and m["date"] and m["date"] < cutoff]
    # ③ 目標依 page id 去重（同一頁可能同時命中兩條規則）
    uniq = {m["id"]: m for m in (dups + old_backups)}
    return {"total": len(metas), "dups": dups, "old_backups": old_backups,
            "targets": list(uniq.values()),
            "decisions": sum(1 for m in metas if m["type"] == DECISION_TYPE),
            "cutoff": cutoff}


def main() -> int:
    ap = argparse.ArgumentParser(description="Notion 分析庫清理掃描")
    ap.add_argument("--fix", action="store_true", help="封存命中的重複/舊備份頁（可回復）")
    ap.add_argument("--days", type=int, default=60, help="備份類保留天數（預設 60）")
    ap.add_argument("--quiet", action="store_true", help="無發現時不輸出")
    args = ap.parse_args()
    if args.days < 1:
        ap.error("--days 必須 >= 1")

    if not TOKEN or not DB_ID:
        print("⚠️ Notion 未設定（NOTION_TOKEN / NOTION_ANALYSIS_DB_ID）")
        return 1
    try:
        pages = fetch_pages()
    except Exception as e:
        print(f"⚠️ Notion 查詢失敗：{type(e).__name__}: {e}")
        return 1
    r = plan(pages, args.days)
    targets = r["targets"]

    if not targets:
        if not args.quiet:
            print(f"✅ Notion 分析庫清理掃描：共 {r['total']} 筆，"
                  f"無重複標題、無逾 {args.days} 天備份頁（決策記錄 {r['decisions']} 筆保留）")
        return 0

    print(f"🧹 Notion 分析庫清理：共 {r['total']} 筆｜重複標題 {len(r['dups'])} 筆、"
          f"逾 {args.days} 天備份頁 {len(r['old_backups'])} 筆"
          f"（去重後目標 {len(targets)} 筆、截止 {r['cutoff']}）｜決策記錄 {r['decisions']} 筆（永不動）")
    for m in r["dups"]:
        print(f"  · 重複：{m['date']} {m['title'][:40]}（{m['type']}）")
    for m in r["old_backups"]:
        print(f"  · 舊備份：{m['date']} {m['title'][:40]}（{m['type']}）")

    if not args.fix:
        print(f"（report-only；要封存請加 --fix，共 {len(targets)} 筆，可從垃圾桶回復）")
        return 0

    ok, failed = 0, []
    for m in targets:
        try:
            if _patch(f"https://api.notion.com/v1/pages/{m['id']}", {"archived": True}) == 200:
                ok += 1
            else:
                failed.append(m["title"])
        except Exception as e:
            failed.append(f"{m['title']}（{type(e).__name__}）")
    print(f"🔧 已封存 {ok}/{len(targets)} 筆（Notion 垃圾桶可回復）")
    if failed:
        print(f"  ⚠️ 失敗 {len(failed)} 筆：{failed[:5]}")
        return 1                     # 讓 cron watchdog 看到失敗
    return 0


if __name__ == "__main__":
    sys.exit(main())
