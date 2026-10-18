#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""state_store.py — 執行期狀態與歸檔的單一位置（repo 外）。

背景（2026-10-19 使用者裁決）：
    週清與收工登錄寫出的狀態快取（data/*_state.json）與歸檔報告（.archive/…）原本落在
    repo 內，每週製造 dirty；要讓它們上線就得逐次真 CIO 審查，等於用授權換畫面全綠。
    這些是可重建的執行期狀態與審計副本 → 移到 repo 外，不進版控、也不擴大白名單。

位置：<home>/AppData/Local/longjiu_state/
    archive/                       歸檔報告與淘汰腳本（沿用 365 天輪替政策）
    calendar_overdue_state.json
    cache_audit_state.json

遷移安全契約（使用者 2026-10-19 明定三項）：
 1. 不得默認空狀態：讀不到／解析失敗 → 先把壞檔備份成 .corrupt-<ts>，再試 legacy；
    兩者都不可用 → raise StateUnreadable，由呼叫端明確處理（跳過本輪），絕不回 []。
 2. 不得覆蓋有效狀態：新位置存在且可解析 → 以它為權威；legacy 內容不同時只記警告，
    不動 legacy（它可能在版控中，改名會變成 deletion）。
 3. 遷移可驗證：copy → sha256 逐位元比對 → atomic replace 才視為完成；legacy 保持原樣。
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


class StateUnreadable(RuntimeError):
    """狀態檔存在但無法解析，且沒有可用的 legacy 來源 → 呼叫端必須明確處理。"""


_MISSING = object()


def _state_root() -> Path:
    """狀態根目錄。

    以家目錄固定推導，不依賴 LOCALAPPDATA 變數 —— 不同啟動來源（cron／互動 shell／
    服務）若環境變數不一致，會各自建立一份狀態，造成「新舊不同步」。
    """
    home = Path.home()
    cand = home / "AppData" / "Local" / "longjiu_state"
    if not cand.parent.exists():
        env = os.environ.get("LOCALAPPDATA")
        if env:
            return Path(env) / "longjiu_state"
    return cand


STATE_DIR = _state_root()
ARCHIVE_DIR = STATE_DIR / "archive"


def _path(name: str) -> Path:
    return STATE_DIR / name


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _MISSING
    except Exception as e:  # noqa: BLE001
        return e


def _quarantine(path: Path, tag: str) -> None:
    """把壞檔／過期檔改名保留（不刪），避免無聲覆蓋。"""
    try:
        if path.exists():
            path.replace(path.with_suffix(path.suffix + f".{tag}-{time.strftime('%Y%m%d%H%M%S')}"))
    except Exception:  # noqa: BLE001
        pass


def migrate_legacy(name: str, legacy: Path) -> Path:
    """legacy → STATE_DIR 的逐位元複製（sha256 驗證後 atomic replace）。legacy 不動。"""
    raw = legacy.read_bytes()
    dest = _path(name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(raw)
    if _sha256(tmp.read_bytes()) != _sha256(raw):
        tmp.unlink(missing_ok=True)
        raise StateUnreadable(f"遷移驗證失敗（sha256 不一致）：{legacy} → {dest}")
    os.replace(tmp, dest)
    return dest


def read_json(name: str, legacy: Path | None = None, default=None):
    """回傳 (資料, 來源標記)。

    來源標記：'state' / 'legacy-migrated' / 'default'。
    新位置損壞且 legacy 也不可用 → StateUnreadable（不回 default）。
    """
    p = _path(name)
    cur = _load(p)

    if cur is not _MISSING and not isinstance(cur, Exception):
        if legacy is not None and Path(legacy).exists():
            old = _load(Path(legacy))
            if old is not _MISSING and not isinstance(old, Exception) and old != cur:
                # 不動 legacy（可能在版控中，改名會變 deletion）；只留痕跡供稽核。
                try:
                    with (STATE_DIR / "migration_warnings.log").open("a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\tSTALE-LEGACY\t{name}\t"
                                f"legacy 與 state 不同步，已以 state 為權威（legacy 未動）\n")
                except Exception:  # noqa: BLE001
                    pass
        return cur, "state"

    # 新位置不存在 → 首次啟動或尚未遷移
    if cur is _MISSING:
        if legacy is not None and Path(legacy).exists():
            old = _load(Path(legacy))
            if isinstance(old, Exception):
                _quarantine(Path(legacy), "corrupt")
                raise StateUnreadable(f"legacy 狀態檔損壞且無其他來源：{legacy}（{old}）")
            if old is not _MISSING:
                migrate_legacy(name, Path(legacy))
                return old, "legacy-migrated"
        return default, "default"

    # 新位置存在但損壞
    _quarantine(p, "corrupt")
    if legacy is not None and Path(legacy).exists():
        old = _load(Path(legacy))
        if old is not _MISSING and not isinstance(old, Exception):
            migrate_legacy(name, Path(legacy))
            return old, "legacy-migrated"
        if isinstance(old, Exception):
            _quarantine(Path(legacy), "corrupt")
    raise StateUnreadable(f"狀態檔損壞且無可用 legacy：{p}（{cur}）")


def write_json(name: str, data) -> Path:
    """atomic 寫入（tmp + os.replace），父目錄自建。"""
    p = _path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def archive_path(name: str) -> Path:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    return ARCHIVE_DIR / name
