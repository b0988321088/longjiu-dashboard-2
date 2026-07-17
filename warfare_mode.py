"""
 warfare_mode.py
 戰略錄入模式：連續記錄戰爭室決策，最終同步到 LongJiu_Holdings_OS/Investment_SOP.md。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# === 預留擴充：可以接 LLM、語音轉寫、截圖 OCR 結果 ===
_llm_client = None
_vision_client = None


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_root() -> Path:
    return Path(__file__).resolve().parent


def sop_path() -> Path:
    return Path("C:/Users/bot/Desktop/LongJiu_Holdings_OS/Investment_SOP.md")


def warfare_log_path() -> Path:
    return _log_root() / "warfare_log.json"


# ---------- warfare_log.json ----------

def _load_log() -> Dict[str, Any]:
    p = warfare_log_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {"entries": []}
    return {"entries": []}


def _save_log(data: Dict[str, Any]) -> None:
    warfare_log_path().write_text(
        json.dumps(data,ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def append_to_log(entry: Dict[str, Any]) -> Dict[str, Any]:
    """寫入 intermediate warfare_log.json（交易中繼紀錄）。"""
    data = _load_log()
    entry.setdefault("logged_at", _ts())
    data["entries"].append(entry)
    _save_log(data)
    return data


# ---------- SOP 寫入 ----------

def _ensure_sop_section() -> None:
    """
    若 SOP 尚無「## 實戰紀錄」章節，於檔案尾部追加之。
    使用粗魯但保險的方式，只會重複檢查一次。
    """
    p = sop_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("# 龍九控股 — 投資紀律與決策引擎 V2.0\n\n## 實戰紀錄\n\n", encoding="utf-8")
        return

    text = p.read_text(encoding="utf-8")
    if "## 實戰紀錄" in text:
        return
    # 尾端新增
    p.write_text(text.rstrip() + "\n\n---\n\n## 實戰紀錄\n\n", encoding="utf-8")


def append_to_sop(record_type: str, content: str, extra: Optional[Dict[str, Any]] = None) -> Path:
    """
    將一筆戰略/戰術紀錄寫入 SOP 的「實戰紀錄」章節。
    record_type: 例如 "Screenshot" / "VoiceNote" / "Decision" / "AutoAction"。
    content: Markdown 內容。
    extra:   可選 key-value 用於中繼 log。
    """
    _ensure_sop_section()

    tag_map = {
        "Screenshot": "📷 截圖分析",
        "VoiceNote": "🎙️ 語音筆記",
        "Decision": "🧠 戰略決策",
        "AutoAction": "🤖 自動化執行",
    }
    label = tag_map.get(record_type, f"🔹 {record_type}")

    block = f"### {label} | {_ts()}\n\n{content}\n\n"

    p = sop_path()
    text = p.read_text(encoding="utf-8")
    marker = "## 實戰紀錄"
    head, tail = text.split(marker, 1)
    new_text = head + marker + "\n\n" + block + tail
    p.write_text(new_text, encoding="utf-8")

    log_entry = {
        "type": record_type,
        "label": label,
        "content": content,
    }
    if extra:
        log_entry.update(extra)
    append_to_log(log_entry)

    return p


# ---------- warfare mode 狀態機 ----------

_MODE_STATE_KEY = "_wf_mode_active"


def _state_file() -> Path:
    return _log_root() / ".warfare_mode_state.json"


def _read_state() -> Dict[str, Any]:
    p = _state_file()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_state(state: Dict[str, Any]) -> None:
    _state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def start_warfare_mode() -> Dict[str, Any]:
    state = _read_state()
    if state.get(_MODE_STATE_KEY):
        return {"already_active": True, "started_at": state.get("started_at")}

    now = _ts()
    entry = {
        "event": "start_warfare_mode",
        "started_at": now,
        "sop_path": str(sop_path()),
        "warfare_log": str(warfare_log_path()),
        "records": 0,
    }
    append_to_log(entry)

    state[_MODE_STATE_KEY] = True
    state["started_at"] = now
    _write_state(state)

    append_to_sop(
        "Decision",
        f"進入戰略錄入模式（warfare_mode）於 `{now}`。\n\n"
        f"- 目標：完整記錄 7/10 轉貸全程決策\n"
        f"- SOP：`{sop_path()}`\n"
        f"- 日誌：`{warfare_log_path()}`",
    )
    return {"started": True, "started_at": now}


def stop_warfare_mode() -> Dict[str, Any]:
    state = _read_state()
    if not state.get(_MODE_STATE_KEY):
        return {"already_inactive": True}

    now = _ts()
    entry = {
        "event": "stop_warfare_mode",
        "stopped_at": now,
    }
    append_to_log(entry)

    append_to_sop(
        "Decision",
        f"結束戰略錄入模式於 `{now}`。\n\n"
        f"- record_count（上傳總量）：{len(_load_log().get('entries', []))}",
    )

    state[_MODE_STATE_KEY] = False
    state["stopped_at"] = now
    _write_state(state)

    return {"stopped": True, "stopped_at": now}


# ---------- 範例執行（單獨執行：python warfare_mode.py） ----------

if __name__ == "__main__":
    print("Warfare Mode CLI")
    print("1) start_warfare_mode()")
    print("2) append_to_sop('Decision', '...')")
    print("3) stop_warfare_mode()")
