# -*- coding: utf-8 -*-
"""llm_analysis.py — 龍九 LLM 真實分析模組（2026-08-22 升級）
讀 hermes .env 的 DEEPSEEK_API_KEY，呼叫 DeepSeek API 產出真實質化分析。
用於：巴菲特視角 / CTO 技術視角 / CIO 觀點（取代模板格式化）。
失敗回傳 None → 呼叫端 fallback 模板（graceful degradation）。
"""
import json, os, urllib.request
from pathlib import Path

HERMES_ENV = Path(os.path.expanduser("~/AppData/Local/hermes/.env"))


def _read_env_key(name: str) -> str:
    if HERMES_ENV.exists():
        try:
            for line in HERMES_ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return os.environ.get(name, "")


def ask_deepseek(prompt: str, system: str = "你是龍九控股的投資分析師。輸出繁體中文、精簡專業、有具體觀點，不重複數據表。",
                 max_tokens: int = 700, temperature: float = 0.4, timeout: int = 90) -> str | None:
    """呼叫 DeepSeek chat API。失敗回傳 None（呼叫端自行 fallback）。"""
    key = _read_env_key("DEEPSEEK_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
        return r["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def ask_llm(prompt: str, system: str = "你是龍九控股的投資分析師。輸出繁體中文、精簡專業、有具體觀點，不重複數據表。",
            max_tokens: int = 700, temperature: float = 0.4) -> str | None:
    """統一入口：DeepSeek 優先。失敗回 None（不拋例外）。"""
    return ask_deepseek(prompt, system, max_tokens, temperature)
