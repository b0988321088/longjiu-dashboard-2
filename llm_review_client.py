#!/usr/bin/env python3
"""CIO 審查類腳本的 LLM 文字生成（2026-09-16 建立，2026-09-18 換審查者）。

審查者必須「非 DeepSeek、非 Google」—— 用同一個模型審自己會失去獨立性，
用 GEMINI_API_KEY 則專案預付金曾於 2026-09-16 15:15 用盡（429 prepayment credits
are depleted），舊 GOOGLE_API_KEY 早已 401。改走兩層、皆為 OpenAI 相容
`/chat/completions`：

  1. Pollinations（keyless 免註冊、非 DS 非 Google → 異質性審查）openai
  2. DeepSeek（付費但便宜，僅在第三方失敗時接手）deepseek-v4-flash

2026-09-18 移除 opencode-free：實測恆回
`403 FreeTierError: OpenCode's free tier can only be used from within OpenCode`，
三顆模型全數無法從外部呼叫，等於每則審查都退到 DeepSeek 自審（異質性假象）。

踩過的坑（全部會讓呼叫端拿到空字串而誤判成功）：
  - 免費層通常必須帶有辨識度的 User-Agent，否則被 Cloudflare 擋（403）
  - **HTTP 200 也可能帶 error body（無 `choices`）** → 必須拋錯
  - **推理型模型會把 max_tokens 燒在 reasoning**，finish_reason=length 且
    content 為空 → 必須放大上限重試，不可當成功
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

POLLI_URL = "https://text.pollinations.ai/openai"
POLLI_MODEL = "openai"  # GPT-OSS 20B reasoning（keyless）
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
          timeout: float, json_mode: bool = False, extra: dict | None = None) -> str:
    """呼叫一個 OpenAI 相容端點；空輸出（reasoning 吃光 token）時放大上限重試。

    2026-09-18 實測：推理模型（deepseek-v4-*、pollinations 的 GPT-OSS）在長 prompt 加
    檢查清單時，會把整個 max_tokens 燒在 reasoning、content 回空字串，而**放大上限救不
    回來**（cap 32768 燒掉 24,742 reasoning tokens 才吐出內容，成本 9 倍）。正解是從源頭
    壓推理：pollinations 用 `reasoning_effort: low`、DeepSeek 用
    `thinking: {"type": "disabled"}`（completion 2,853 vs 25,386）。見 `generate()`。
    """
    last_finish = ""
    for cap in (max_tokens, max(max_tokens, 8192) * 2):
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cap,
            "temperature": 0.1,
        }
        if extra:
            body.update(extra)
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
            POLLI_URL,
            {
                "HTTP-Referer": "https://hermes-agent.nousresearch.com",
                "X-Title": "Hermes Agent",
                "User-Agent": UA,
            },
            POLLI_MODEL, prompt, max_tokens, timeout,
            extra={"reasoning_effort": "low"},
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"pollinations/{POLLI_MODEL}: {exc}")

    key = _env("DEEPSEEK_API_KEY")
    if key:
        try:
            return _call(DEEPSEEK_URL, {"Authorization": f"Bearer {key}"},
                         DEEPSEEK_MODEL, prompt, max_tokens, timeout, json_mode,
                         extra={"thinking": {"type": "disabled"}})
        except Exception as exc:  # noqa: BLE001
            errors.append(f"deepseek/{DEEPSEEK_MODEL}: {exc}")
    else:
        errors.append("deepseek: DEEPSEEK_API_KEY 未設定")

    raise RuntimeError("；".join(errors))


if __name__ == "__main__":
    import sys

    print(generate(sys.argv[1] if len(sys.argv) > 1 else "只回兩個字：可用")[:400])
