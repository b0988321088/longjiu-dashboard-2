#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_chain.py — 真 CIO 審查的「單一實作 ＋ 異質備援鏈」（2026-10-13）

TD-20261013-05 根因修復：
    402 不是單一故障，是**審查能力被設計成單一供應商依賴**。實證（2026-10-13）：
      - `.git/cio_reviews/wo_*.json` 的 reviewer 欄寫著「備援鏈(Pollinations402→DeepSeek)」
        → 402 早已在發生，而當時的「備援」是 DeepSeek＝產出者自己審自己（假異質）。
      - 三個審查入口行為不一致：`cio_lane.py`／`regenerate_report.py` 直接呼叫
        `_lrc._call(POLLI_URL)` → 完全無備援（402 即全停）；`llm_review_client.generate()`
        → 有備援但第二層是 DeepSeek（未經有效異質審查卻能落 RECORD 的縫）。
      - Pollinations `openai-fast` 實測已 HTTP 402（模型級收費牆）；`openai` 為間歇 402。

本檔把「哪一家審、幾層、失敗怎麼辦」收斂成唯一真值，三入口共用：
    llm_review_client.generate() / cio_lane.py / regenerate_report.py

鏈（**全部非 DeepSeek、非 Google**；異質性＝不同模型家族，非同一家自我複核）：
    1. Pollinations  openai                        （keyless，現行）
    2. nous          meituan/longcat-2.5-preview:free（中文母語，實測可用）
    3. nous          poolside/laguna-s-2.1:free     （第三家，實測可用）

fail-closed 語意（不變，且**不降級**）：
    全鏈失敗（含憑證失效）→ 丟 RuntimeError；呼叫端一律 fail-closed，不得退回未審查推送。
    絕不 fallback 到產出者同家模型 —— 那等於沒有閘門。

已知界線（誠實記錄，勿誤讀為保證）：
    - 免費層會下架（同日實測 meituan/longcat-2.0:free 已 404）→ 三層是提高可用機率，不是保證。
    - nous agent_key 有到期時間（實測約 1 小時週期）。本檔讀 auth.json 並檢查
      `agent_key_expires_at`，剩餘壽命低於 _NOUS_MIN_TTL 即**跳過該層**（不用失效憑證硬打，
      避免「送到一半才失效」被誤判成模型故障）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

POLLI_URL = "https://text.pollinations.ai/openai"
POLLI_MODEL = "openai"          # GPT-OSS 20B reasoning（keyless）
UA = "HermesAgent/longjiu-review"   # 免費層要求有辨識度的 UA

AUTH_PATH = Path.home() / "AppData" / "Local" / "hermes" / "auth.json"
NOUS_MODELS = (
    "meituan/longcat-2.5-preview:free",
    "poolside/laguna-s-2.1:free",
)
_NOUS_MIN_TTL = 120             # 秒：agent_key 剩餘壽命低於此 → 不使用該層
_MIN_CONTENT = 2                # 少於 2 字元的 content 視為空輸出（推理模型燒 token 的症狀）


def _nous_credentials() -> tuple[str, str] | None:
    """回傳 (inference_base_url, agent_key)；憑證缺失／已過期／即將過期 → None。"""
    try:
        d = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        n = (d.get("providers") or {}).get("nous") or {}
        key = n.get("agent_key") or ""
        base = (n.get("inference_base_url") or "").rstrip("/")
        if not key or not base:
            return None
        exp = n.get("agent_key_expires_at")
        if exp:
            t = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if (t - datetime.now(timezone.utc)).total_seconds() < _NOUS_MIN_TTL:
                return None
        return base, key
    except Exception:  # noqa: BLE001  憑證不可讀＝該層不可用，不得讓它炸掉整條鏈
        return None


def _post(url: str, headers: dict, payload: dict, timeout: float) -> tuple[str, str]:
    """單次 HTTP。回傳 (content, finish_reason)。

    HTTP 200 也可能帶 error body（無 `choices`）→ 必須拋錯，不可當成功。
    """
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict) or not data.get("choices"):
        raise RuntimeError(f"回應無 choices：{json.dumps(data, ensure_ascii=False)[:200]}")
    choice = data["choices"][0]
    msg = choice.get("message") or {}
    return (msg.get("content") or ""), (choice.get("finish_reason") or "")


def _call(url: str, headers: dict, model: str, prompt: str, max_tokens: int,
          timeout: float, json_mode: bool = False, extra: dict | None = None) -> str:
    """呼叫一個 OpenAI 相容端點；空輸出（推理吃光 token）時放大上限重試一次。

    2026-09-18 實測：推理型模型在長 prompt 加檢查清單時會把整個 max_tokens 燒在
    reasoning、content 回空字串，而放大上限救不回來（cap 32768 燒 24,742 reasoning
    tokens 才吐內容，成本 9 倍）。正解是從源頭壓推理（本檔一律帶 reasoning_effort=low）。
    """
    last_finish = ""
    for cap in (max_tokens, max(max_tokens, 8192) * 2):
        body: dict = {
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
        if len(text.strip()) >= _MIN_CONTENT:
            return text
    raise RuntimeError(f"空輸出（finish_reason={last_finish or '?'}，cap={max_tokens}）")


def _layers():
    """回傳可用層清單 [(label, callable)]；順序即優先序。憑證不可用者直接不列入。"""
    out = []

    def _polli(prompt: str, max_tokens: int, timeout: float, json_mode: bool) -> str:
        return _call(
            POLLI_URL,
            {"HTTP-Referer": "https://hermes-agent.nousresearch.com",
             "X-Title": "Hermes Agent", "User-Agent": UA},
            POLLI_MODEL, prompt, max_tokens, timeout, json_mode,
            extra={"reasoning_effort": "low"},
        )

    out.append((f"CIO-Pollinations({POLLI_MODEL})", _polli))

    creds = _nous_credentials()
    if creds:
        base, key = creds
        for model in NOUS_MODELS:
            def _mk(m: str):
                def _nous(prompt: str, max_tokens: int, timeout: float, json_mode: bool) -> str:
                    return _call(f"{base}/chat/completions", {"Authorization": f"Bearer {key}"},
                                 m, prompt, max_tokens, timeout, json_mode,
                                 extra={"reasoning_effort": "low"})
                return _nous
            out.append((f"CIO-nous({model})", _mk(model)))
    return out


def chain_labels() -> list[str]:
    """回傳目前可用層的標籤（供健康檢查／測試斷言，不呼叫模型）。"""
    return [label for label, _ in _layers()]


def review(prompt: str, *, max_tokens: int = 8192, timeout: float = 300,
           json_mode: bool = False) -> tuple[str, str]:
    """依序嘗試異質鏈，回傳 (模型輸出文字, 實際使用的審查者標籤)。

    全鏈失敗 → RuntimeError（呼叫端 fail-closed，不得降級）。
    """
    errors: list[str] = []
    layers = _layers()
    if not layers:
        raise RuntimeError("審查鏈無任何可用層（憑證缺失）→ fail-closed")
    for label, fn in layers:
        try:
            text = fn(prompt, max_tokens, timeout, json_mode)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        if len(text.strip()) >= _MIN_CONTENT:
            return text, label
        errors.append(f"{label}: 空輸出")
    raise RuntimeError("；".join(errors) if errors else "審查鏈全數失敗 → fail-closed")


if __name__ == "__main__":
    import sys

    _p = sys.argv[1] if len(sys.argv) > 1 else "只回兩個字：可用"
    print("可用層：", chain_labels())
    try:
        _t, _l = review(_p, max_tokens=128, timeout=90)
        print(f"✅ 由 {_l} 回應：{_t[:120]}")
    except Exception as e:  # noqa: BLE001
        print(f"❌ {e}")
        raise SystemExit(1)
