#!/usr/bin/env python3
"""CIO 審查類腳本的 LLM 文字生成（2026-09-16 建立）。

為什麼不用 Gemini 了：GEMINI_API_KEY 專案預付金曾於 2026-09-16 15:15 用盡
（`429 RESOURCE_EXHAUSTED: prepayment credits are depleted`），舊 GOOGLE_API_KEY 早已 401。
改走兩層、皆為 OpenAI 相容 `/chat/completions`（Gemini 恢復後仍保持此設定＝CER 代答不再燒錢）：

  1. opencode-free（keyless 免費、與主模型異家 → 保留審查的異質性）nemotron-3-ultra-free
  2. DeepSeek（付費但便宜）deepseek-v4-flash

踩過的坑（全部會讓呼叫端拿到空字串而誤判成功，2026-09-16 實測）：
  - 免費層必須帶 User-Agent，否則 Cloudflare 回 403 `error code: 1010`
  - 免費層必須帶 `x-opencode-session`，否則回 `MissingSessionID`
  - 免費層不可帶 Authorization（任意 bearer 一律 401）
  - **HTTP 200 也可能帶 error body（無 `choices`）** → 必須拋錯
  - **推理型模型（nemotron / deepseek-v4-*）會把 max_tokens 燒在 reasoning**，
    finish_reason=length 且 content 為空 → 必須放大上限重試，不可當成功
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

OPENCODE_URL = "https://opencode.ai/zen/v1/chat/completions"
OPENCODE_MODEL = "nemotron-3-ultra-free"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-v4-flash"
ENV_PATH = Path.home() / "AppData" / "Local" / "hermes" / ".env"
UA = "HermesAgent/longjiu-review"  # 免費層要求有辨識度的 UA


def _env(key: str) -> str:
    val = os.getenv(key, "")
    if val:
        return val
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _post(url: str, headers: dict, payload: dict, timeout: float) -> tuple[str, str]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not data.get("choices"):
        raise RuntimeError(f"回應無 choices：{json.dumps(data, ensure_ascii=False)[:200]}")
    choice = data["choices"][0]
    return (choice.get("message", {}).get("content") or ""), (choice.get("finish_reason") or "")


def _call(url: str, headers: dict, model: str, prompt: str, max_tokens: int,
          timeout: float, json_mode: bool = False) -> str:
    """呼叫一個 OpenAI 相容端點；空輸出（reasoning 吃光 token）時放大上限重試。"""
    last_finish = ""
    for cap in (max_tokens, max(max_tokens, 4096) * 2):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cap,
            "temperature": 0.1,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        text, last_finish = _post(url, headers, body, timeout)
        if text.strip():
            return text
    raise RuntimeError(f"空輸出（finish_reason={last_finish or '?'}，cap={max_tokens}）")


def generate(prompt: str, *, max_tokens: int = 8192, timeout: float = 180,
             session_id: str = "cioreview", json_mode: bool = False) -> str:
    """回傳模型輸出的文字。免費層失敗才動用 DeepSeek；兩層都失敗則丟例外。"""
    errors: list[str] = []

    try:
        return _call(
            OPENCODE_URL,
            {
                "Authorization": "",
                "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                "X-Title": "Hermes Agent",
                "User-Agent": UA,
                "x-opencode-session": session_id,
            },
            OPENCODE_MODEL, prompt, max_tokens, timeout,
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"opencode-free/{OPENCODE_MODEL}: {exc}")

    key = _env("DEEPSEEK_API_KEY")
    if key:
        try:
            return _call(DEEPSEEK_URL, {"Authorization": f"Bearer {key}"},
                         DEEPSEEK_MODEL, prompt, max_tokens, timeout, json_mode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"deepseek/{DEEPSEEK_MODEL}: {exc}")
    else:
        errors.append("deepseek: DEEPSEEK_API_KEY 未設定")

    raise RuntimeError("；".join(errors))


if __name__ == "__main__":
    import sys

    print(generate(sys.argv[1] if len(sys.argv) > 1 else "只回兩個字：可用")[:400])
