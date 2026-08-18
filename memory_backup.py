#!/usr/bin/env python3
"""memory_backup.py — 每日記憶備份（06:50 cron + 19:00 記憶同步前）
Phase 1 本地：MEMORY.md / USER.md / memory_store.db → memories/backups/
         命名：<檔名>.bak-YYYYMMDD ｜ 留存：30 天 ｜ 校驗：md5 比對 + 執行日誌
Phase 2 Notion：MEMORY.md → 「MEMORY_AlwaysOn 自動備份庫」頁面（龍九分析記錄 DB）
         固定頁面覆蓋（清空 children → 重寫 heading + code block），md5 往返驗證
         歷史版本由 Notion 內建版本紀錄保存（Plus 方案 30 天）
成功靜默（stdout 空 → cron 不發訊）；失敗 stderr + exit 1 → cron 發錯誤警示。
"""
import hashlib
import json
import os
import shutil
import sys
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # AppData/Local/hermes
MEM_DIR = BASE / "memories"
BACKUP_DIR = MEM_DIR / "backups"
LOG_FILE = BACKUP_DIR / "backup_log.txt"
KEEP_DAYS = 30

# Notion 目標頁（龍九分析記錄資料庫內專屬列）
NOTION_PAGE_ID = "3b1fc735-d433-8188-b5dd-fa2b0be2c774"
NOTION_API = "https://api.notion.com/v1/"

SOURCES = [
    (MEM_DIR / "MEMORY.md", "MEMORY.md"),
    (MEM_DIR / "USER.md", "USER.md"),
    (BASE / "memory_store.db", "memory_store.db"),
]


# ---------- helpers ----------

def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log(msg: str) -> None:
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def notion_token() -> str:
    env = os.environ.get("NOTION_TOKEN", "")
    if env:
        return env
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("NOTION_TOKEN="):
                return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def notion(method: str, path: str, body: dict = None):
    token = notion_token()
    if not token:
        raise RuntimeError("NOTION_TOKEN 不存在")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        NOTION_API + path, data=data,
        headers={"Authorization": f"Bearer {token}",
                 "Notion-Version": "2025-09-03",
                 "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise RuntimeError(f"Notion {method} {path} -> HTTP {e.code}: {detail}")


# ---------- Phase 1: 本地備份 ----------

def phase1_local() -> list:
    errors = []
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    for src, tag in SOURCES:
        if not src.exists():
            errors.append(f"來源不存在: {src.name}")
            continue
        dst = BACKUP_DIR / f"{tag}.bak-{stamp}"
        shutil.copy2(src, dst)
        if md5(src) == md5(dst):
            log(f"OK  {tag} -> {dst.name} ({src.stat().st_size} bytes, md5 相符)")
        else:
            errors.append(f"md5 不符: {tag}")
            log(f"FAIL {tag} -> {dst.name} md5 不符")
    # 30 天留存清理
    cutoff = (date.today() - timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    for tag in ("MEMORY.md", "USER.md", "memory_store.db"):
        for old in BACKUP_DIR.glob(f"{tag}.bak-*"):
            try:
                d = old.name.rsplit(".bak-", 1)[1]
                if d < cutoff:
                    old.unlink()
                    log(f"CLEAN 移除過期備份 {old.name} (> {KEEP_DAYS} 天)")
            except (ValueError, OSError):
                pass
    return errors


# ---------- Phase 2: Notion 頁面覆蓋 ----------

def _chunk_text(text: str, limit: int = 1900) -> list:
    """切成 ≤limit 字元的 rich_text 片段（Notion 單項上限 2000 字元）"""
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def phase2_notion() -> None:
    src = MEM_DIR / "MEMORY.md"
    if not src.exists():
        raise RuntimeError("MEMORY.md 不存在")
    content = src.read_text(encoding="utf-8")
    src_md5 = hashlib.md5(content.encode("utf-8")).hexdigest()  # 對送出文字算 md5（read_text 已做 \r\n→\n 正規化）

    # 1) 清空既有 children（固定頁面覆蓋）
    _, r = notion("GET", f"blocks/{NOTION_PAGE_ID}/children")
    for b in r.get("results", []):
        notion("DELETE", f"blocks/{b['id']}")

    # 2) 重寫：日期標題 + code block（位元組保真）
    heading = f"MEMORY_AlwaysOn 備份 {date.today().isoformat()}"
    children = [
        {"object": "block", "type": "heading_1",
         "heading_1": {"rich_text": [{"text": {"content": heading}}]}},
        {"object": "block", "type": "code",
         "code": {"rich_text": [{"text": {"content": c}} for c in _chunk_text(content)],
                  "language": "markdown"}},
    ]
    notion("PATCH", f"blocks/{NOTION_PAGE_ID}/children", {"children": children})

    # 3) md5 往返驗證：讀回 code block 全文比對
    _, r = notion("GET", f"blocks/{NOTION_PAGE_ID}/children")
    back = ""
    for b in r.get("results", []):
        if b.get("type") == "code":
            back = "".join(t.get("plain_text", "") for t in b["code"]["rich_text"])
    if hashlib.md5(back.encode()).hexdigest() != src_md5:
        raise RuntimeError("Notion 往返 md5 不符")
    log(f"OK  NOTION MEMORY.md -> page {NOTION_PAGE_ID} ({len(back)} bytes, md5 相符)")


# ---------- main ----------

def main() -> int:
    errors = []
    try:
        errors += phase1_local()
    except Exception as e:
        errors.append(f"本地備份例外: {e}")
    try:
        phase2_notion()
    except Exception as e:
        errors.append(f"Notion 同步失敗: {e}")

    if errors:
        msg = "記憶備份失敗：" + "；".join(errors)
        log("FAIL " + msg)
        print(msg, file=sys.stderr)
        return 1
    return 0  # 成功 → 靜默（僅寫日誌）


if __name__ == "__main__":
    sys.exit(main())
