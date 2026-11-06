"""artifact_manifest.py — 產物留痕（B 案，INC-20261106-01）

**背景**：`wrappers/cost_watch_digest.py` 原本「跑完就地 commit → auto_push」。
2026-11-06 13:30 因此產生 `f83b2d2d`，讓人工核對窗口內的 HEAD 漂移；且因推送範圍含
一顆缺 CIO RECORD 的 `9dd6e960`，`auto_push` 以 rc=3 擋下，留下一顆推不出去的 commit。

**B 案（使用者 2026-11-06 裁決③ 批准）**：
    產生 → 驗證 → 寫入 artifact_manifest.json → **停止**
排程**不再** commit、**不再** push。commit 統一交每日單一窗口（22:38 收尾）。

**不可違反**：前一顆 commit 沒有 CIO RECORD 時，後續排程不得繞過審查、重排發布順序
或自行補授權。本模組不具備任何發布能力（刻意）。
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

BASE = Path(os.environ.get("LONGJIU_BASE", Path(__file__).resolve().parent))
MANIFEST_PATH = BASE / "data" / "artifact_manifest.json"


def sha256_of(path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_entry(producer: str, artifacts, report_base_date=None, source_dates=None, note=None) -> dict:
    arts = []
    for a in artifacts or []:
        p = Path(a)
        if not p.is_absolute():
            p = BASE / a
        arts.append({
            "artifact": str(a).replace("\\", "/"),
            "sha256": sha256_of(p),
            "exists": p.exists(),
            "bytes": p.stat().st_size if p.exists() else 0,
        })
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "producer": producer,
        "report_base_date": report_base_date,
        "source_dates": source_dates or {},
        "artifacts": arts,
        "note": note,
    }


def write_manifest(producer: str, artifacts, report_base_date=None, source_dates=None, note=None) -> dict:
    """append-only 寫入；回傳本筆 entry。不 commit、不 push、不觸發任何外部系統。"""
    entry = build_entry(producer, artifacts, report_base_date, source_dates, note)
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    data = []
    if MANIFEST_PATH.exists():
        try:
            raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            data = raw if isinstance(raw, list) else raw.get("entries", [])
        except Exception:
            data = []
    data.append(entry)
    MANIFEST_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    bad = [a["artifact"] for a in entry["artifacts"] if not a["sha256"]]
    if bad:
        print(f"⚠️ manifest：以下產物不存在或無法計算 SHA256 → {bad}")
    print(f"📝 artifact_manifest：{producer} 留痕 {len(entry['artifacts'])} 檔"
          f"（不 commit／不 push，依 INC-20261106-01 B 案）")
    return entry


if __name__ == "__main__":
    import sys
    print(json.dumps(build_entry("artifact_manifest.py", sys.argv[1:]), ensure_ascii=False, indent=1))
