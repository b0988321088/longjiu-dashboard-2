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
import re
import time
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

# ── 送審包裝常數（2026-10-16 使用者裁決「修掉切片造成的假拒絕」）──
# 單段目標上限 12,000 → 32,000 字元。實測依據（d28b889d，晨間資料 commit）：
#   640,240 字元 / 12,000 ＝ 54 段 → 每日 54 次模型呼叫（約 22 分鐘），且字元切點
#   會落在**檔案中間與超長行中間**（cost.html 的 `<script id="seed">` JSON 被切半）
#   → 審查者看到半截 JSON 判「truncated and malformed」→ 假 REJECT → 07:00 產線全停。
# 32,000 為**目標**上限：實際模型能否完整吃下該長度由 provider 上下文決定（見 tests 的
#   實測項）；分段後仍須 100% 涵蓋，任何長度都不得靜默截斷（_coverage_note 守門不變）。
DEFAULT_DIFF_CAP = 32000
# 技術性失敗重試（僅「全層不可用／無可解析的有效結果」；**有效 REJECT 不重試**，
#   不得為了拿 APPROVE 換層或重抽＝不投票、不洗結果）。
_RETRY_TECHNICAL = 2
_RETRY_BACKOFF = 2.0            # 秒；第 n 次重試前等待 n * backoff

# ── Gemini 候選層（RC-GEMINI-01，2026-10-14 使用者核准「受控接入、先驗證再啟用」）──
# 預設**關閉**：未設／設 0 時，既有審查鏈行為完全不變。
#   LONGJIU_REVIEW_GEMINI=1    → 追加為最後的備援層
#   LONGJIU_REVIEW_GEMINI=only → 只走此層（用於「必須由 CIO 的模型審查」的場合）
# 憑證讀 Hermes .env（repo 外）；**永不寫入 repo、測試輸出或審查紀錄**。
GEMINI_ENV = "LONGJIU_REVIEW_GEMINI"
GEMINI_MODEL = "gemini-2.5-flash"
_HERMES_ENV_PATH = Path.home() / "AppData" / "Local" / "hermes" / ".env"


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
            # 2026-10-15 B1（R1）：0.1 → 0。降低取樣隨機性；**不代表結果保證一致**
            # （同一輸入仍可能因上游實作變動給出不同判定 → 由 stability_check 標記 UNSTABLE）。
            "temperature": 0,
        }
        if extra:
            body.update(extra)
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        text, last_finish = _post(url, headers, body, timeout)
        if len(text.strip()) >= _MIN_CONTENT:
            return text
    raise RuntimeError(f"空輸出（finish_reason={last_finish or '?'}，cap={max_tokens}）")


def _read_hermes_env(name: str) -> str:
    """讀 Hermes .env 的單一變數（repo 外的憑證來源）。

    刻意不做快取：憑證可被外部輪替，每次取用即時讀。任何例外一律回空字串
    （憑證不可讀＝該層不可用，不得讓它炸掉整條鏈），且**永不輸出值**。
    """
    try:
        for line in _HERMES_ENV_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == name:
                return v.strip().strip('"').strip("'")
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _gemini_credentials() -> tuple[str, str] | None:
    """回傳 (base_url, api_key)；任一缺失 → None（該層不可用）。"""
    base = _read_hermes_env("GEMINI_BASE_URL").rstrip("/")
    key = _read_hermes_env("GEMINI_API_KEY")
    if not base or not key:
        return None
    return base, key


class _LayerBlocked(RuntimeError):
    """該層回覆被結構／安全因素擋下（無候選、空內容、SAFETY…）→ 視為**該層失敗**，續下一層。

    注意：這不是「拒審」——拒審（REJECT）是有效判定，必須原樣採用、不得降層。
    """


def _gemini_once(base: str, key: str, model: str, prompt: str, cap: int,
                 timeout: float, json_mode: bool) -> tuple[str, str]:
    """單次呼叫，回傳 (text, finishReason)。結構／安全異常一律 raise（見 `_LayerBlocked`）。"""
    # 2026-10-16 實測（seg5，prompt 36,261 字元）：開思考 cap=8192 → MAX_TOKENS、空輸出、
    #   44.6s；cap=32768 → 成功但 138.6s。關思考（thinkingBudget=0）→ STOP、合法 JSON、1.9s。
    #   2.5 系列思考 token 計入 maxOutputTokens → 低上限必失敗；本層為「判定 JSON」用途，
    #   不需長思考，故關閉思考（僅 Gemini 層；OpenAI 相容層與 nous 層不受影響）。
    gcfg: dict = {"temperature": 0, "maxOutputTokens": cap,
                  "thinkingConfig": {"thinkingBudget": 0}}   # 2026-10-15 B1（R1）：0.1 → 0
    if json_mode:
        gcfg["responseMimeType"] = "application/json"
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": gcfg}
    req = urllib.request.Request(
        f"{base}/models/{model}:generateContent?key={key}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Gemini 回應非 JSON 物件")
    cands = data.get("candidates") or []
    if not cands:
        _fb = (data.get("promptFeedback") or {}).get("blockReason")
        raise _LayerBlocked(f"無候選（blockReason={_fb or '?'}）")
    c0 = cands[0] or {}
    fr = str(c0.get("finishReason") or "").upper()
    if fr in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"):
        raise _LayerBlocked(f"finishReason={fr}")
    parts = (c0.get("content") or {}).get("parts") or []
    text = "".join(str(p.get("text") or "") for p in parts)
    return text, fr


def _call_gemini(base: str, key: str, model: str, prompt: str, max_tokens: int,
                 timeout: float, json_mode: bool = False) -> str:
    """Gemini 原生 generateContent（錯誤語意與 OpenAI 相容層 `_call` 對齊）。

    - 空輸出 → 放大上限重試一次（推理型模型把 token 燒在 reasoning 的症狀）。
    - **finishReason=MAX_TOKENS（截斷）一律視為失敗**：不完整的 JSON 不得進入審查，
      放大上限重試後仍截斷 → raise → 由 `review()` 續下一層或 fail-closed。
    - HTTP 層錯誤由 `urlopen` 拋出；無候選／安全阻擋／空 parts → `_LayerBlocked`。
    三者皆由 `review()` 統一視為「該層失敗」。URL 帶 key 屬 Gemini 原生設計；
    本函式不回傳、不記錄任何憑證。
    """
    last_finish = ""
    for cap in (max_tokens, max(max_tokens, 8192) * 2):
        text, last_finish = _gemini_once(base, key, model, prompt, cap, timeout, json_mode)
        if last_finish == "MAX_TOKENS":
            continue                      # 截斷 → 放大上限重試
        if len(text.strip()) >= _MIN_CONTENT:
            return text
    raise RuntimeError(f"空輸出或截斷（finishReason={last_finish or '?'}，cap={max_tokens}）")


def _mk_gemini(base: str, key: str):
    def _fn(prompt: str, max_tokens: int, timeout: float, json_mode: bool) -> str:
        return _call_gemini(base, key, GEMINI_MODEL, prompt, max_tokens, timeout, json_mode)
    return _fn


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

    # Gemini 候選層（預設關閉；語意見檔頭 GEMINI_ENV）。憑證不可用 → 不列入（only 模式則空鏈）。
    _mode = (_read_hermes_env(GEMINI_ENV) or os.environ.get(GEMINI_ENV) or "").strip().lower()
    if _mode in ("1", "true", "yes", "on", "only"):
        _gc = _gemini_credentials()
        _label = f"CIO-Gemini({GEMINI_MODEL})"
        if _mode == "only":
            return [(_label, _mk_gemini(*_gc))] if _gc else []
        if _gc:
            out.append((_label, _mk_gemini(*_gc)))
    return out


def chain_labels() -> list[str]:
    """回傳目前可用層的標籤（供健康檢查／測試斷言，不呼叫模型）。"""
    return [label for label, _ in _layers()]


# ── 送審 prompt 的單一真值（2026-10-13 P1）────────────────────────────────────
# 兩個真 CIO 送審入口（cio_lane.py／regenerate_report.py）原本各有一份內嵌 prompt
# 複本，實測已漂移：cio_lane 走 12 碼 tree 綁定，regenerate_report 仍走 40 碼
# （會踩「免費層抄寫長字串掉字元」的坑），且兩份都缺 canonical 契約。
# 統一收斂到本模組；兩入口只負責取資料，不再自建 prompt。
REVIEW_CONTRACT = (
    "輸出契約（必遵守；違反者判決無效）：\n"
    "1. `blocking` 只能列**具體、可指名**的阻塞缺陷（檔案＋問題）。沒有這類缺陷時一律 `[]`。\n"
    "2. **`blocking=[]` ⇒ verdict 必須是 `APPROVE`**（release boundary）。不得以「範圍大」"
    "「無法完整驗證」「缺乏進一步說明」等非指名理由，在 blocking 為空時給 `REJECT`。\n"
    "3. 只有在你能指名 blocking 級缺陷時才可 `REJECT`，且該缺陷必須逐條出現在 `blocking` 陣列。\n"
    "4. `required_fixes`／`required_changes` 屬後續 hardening，可非空，但**不得改變 verdict**。\n"
    "5. `reviewed_commits` 原樣抄寫下方的 12 碼 commit 與 12 碼 tree，"
    "不得自行補齊、截短或改寫任何字元。\n"
)


def _coverage_note(total: int, shown: int) -> str:
    """diff 覆蓋率提示（2026-10-15 B1／R1）：不得靜默截斷。

    完整提供（shown >= total）→ 空字串；否則明示涵蓋率並禁止 APPROVE。
    """
    if total <= 0 or shown >= total:
        return ""
    pct = shown * 100.0 / total
    return (f"\n⚠️ diff 未完整：本次僅提供 {shown}/{total} 字元（涵蓋率 {pct:.1f}%）。"
            f"涵蓋率不足 100% 時**不得給 APPROVE**，只能 REJECT 並指名截斷事實。\n")


def build_review_prompt(commit: str, tree: str, subject: str, files: str, stat: str,
                        diff_cap: int = DEFAULT_DIFF_CAP, patch: str | None = None,
                        segment: tuple[int, int] | None = None,
                        seg_note: str = "") -> str:
    """組出真 CIO 送審 prompt（兩個入口共用的單一真值）。

    綁定一律採 **12 碼前綴**：2026-10-13 實測免費層模型抄寫 40 碼 sha 會掉字元
    （c3b3a143 那輪 tree 40 碼被抄成 39 碼，造成產線連續 6 次 fail-closed 誤擋）。
    commit 本來就取 12 碼，tree 拉齊為同一慣例，比對端同樣只比 12 碼前綴。

    2026-10-14 W1（使用者核准 A+C）：新增 `patch`／`segment`。
    原版只送 `--name-only` 檔名＋`--stat` 統計（實測 662 字元），**完全不含程式碼**，
    使 APPROVE 的效力僅及於「通道類型判斷」而不及內容。呼叫端現須傳入實際 patch；
    `segment=(i, n)` 用於超量分段時標示段落。兩者皆為可選 → 既有呼叫端不受影響。
    """
    c12, t12 = commit[:12], tree[:12]
    _seg_txt = ""
    if segment and segment[1] > 1:
        _seg_txt = f"（第 {segment[0]}/{segment[1]} 段；本段需獨立判定，全部段落皆 APPROVE 才算通過）"
    # 2026-10-16：分段以**檔案邊界**為優先；本段若含被切斷的檔案，`seg_note` 明示檔名／
    #   該檔總長／第幾段。理由：舊版純字元切片會把超長行（HTML／JSON）切半，審查者看到
    #   半截內容後「合理地」判截斷 → 2026-10-16 07:00 假 REJECT 導致整條產線停擺。
    _note_txt = f"\n{seg_note}\n" if seg_note else ""
    _content_txt = ""
    if patch is not None:
        _content_txt = (f"\n變更內容（實際 patch{_seg_txt}）：\n"
                        f"{_note_txt}"
                        f"```diff\n{patch[:diff_cap]}\n```\n"
                        f"{_coverage_note(len(patch), min(len(patch), diff_cap))}")
    # 分段送審專屬的判準說明（只在真的有分段切點時出現；單段送審時 prompt 與舊版逐字相同）
    _focus_seg_txt = ""
    if seg_note:
        _focus_seg_txt = ("⑥**分段切點不是缺陷**：本段若在檔案或超長單行（HTML／JSON 行）中間中斷，"
                          "那是刻意分段（整批 patch 100% 已送審、無省略），**不得**以「截斷／不完整／"
                          "malformed／無法解析」為由列入 blocking；只有能指名「與切點無關的具體缺陷」"
                          "（例如數值矛盾、邏輯錯誤、fail-open）才算 blocking。\n")
    return (
        "你是龍九控股的獨立 CIO 審查者（異質審查，不得預設放行）。只回傳 JSON，不要任何其他文字。\n"
        f"待推送 commit：{c12}\n待推送 tree：{t12}\n主旨：{subject}\n\n"
        f"變更檔案清單：\n{files[:diff_cap]}\n\n變更統計：\n{stat[:diff_cap]}\n"
        + _content_txt +
        "\n審查重點：①是否含程式／治理紀錄／憑證類變更而走資料通道 ②資料是否自相矛盾或截斷"
        "（分段切點造成的顯示中斷除外，見⑥）"
        "③是否與使用者既定裁決衝突（例如公開首頁必經真 CIO、不可放寬審查）④是否有 blocking 級缺陷 "
        "⑤**變更內容本身是否有具體缺陷**（邏輯錯誤、fail-open／靜默失敗、資料誤用、未處理缺失值）"
        "—— 有則必須**指名檔案與問題**列入 blocking；無具體缺陷時不得以泛泛理由填入。\n"
        + _focus_seg_txt + "\n"
        + REVIEW_CONTRACT
        + "\n輸出格式（原樣抄寫下方 12 碼 commit 與 12 碼 tree，不得自行補齊或改寫字元）：\n"
        '{"verdict":"APPROVE 或 REJECT","reviewed_commits":[{"commit":"' + c12 + '","tree":"' + t12 + '"}],'
        '"blocking":[],"required_fixes":[],"note":"理由（160 字內）"}'
    )


def parse_review(text: str) -> dict | None:
    """從模型輸出取出審查 JSON 物件（容忍前後雜訊）；取不到回 None。"""
    if not text:
        return None
    try:
        j = json.loads(text)
        if isinstance(j, dict):
            return j
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
        return j if isinstance(j, dict) else None
    except Exception:  # noqa: BLE001
        return None


# 可定位依據：檔名（含副檔名）／行號（`行`、`L123`、`line 12`）
_LOCATABLE_RE = re.compile(
    r"[A-Za-z0-9_\-./]+\.(?:py|json|md|html|db|csv|txt|yml|yaml|sh|js|toml)"
    r"|行|L\d{1,5}|line\s*\d+")


def contract_violation(j: dict | None, *, require_evidence: bool = True) -> str | None:
    """審查契約違規偵測 → 回傳原因（None＝合規）。

    使用者 2026-10-15 B1／R1 裁決：
      - `blocking` 非空 ⇔ `REJECT`；`blocking` 空 ⇔ `APPROVE`。不一致者判**無效審查**，不得核准。
      - 每個 blocking 必須含可定位依據（檔名／行號）；否則同樣無效。
    """
    if not isinstance(j, dict):
        return "回覆非 JSON 物件"
    v = str(j.get("verdict") or "").strip().upper()
    if v not in ("APPROVE", "REJECT"):
        return f"verdict 不可判定（{v or '空'}）"
    bl = j.get("blocking")
    if bl is None:
        bl = []
    if not isinstance(bl, list):
        return "blocking 非陣列"
    named = [b for b in bl
             if (b if isinstance(b, str) else json.dumps(b, ensure_ascii=False)).strip()]
    if v == "APPROVE" and named:
        return f"契約違規：verdict=APPROVE 但 blocking 非空（{len(named)} 條）"
    if v == "REJECT" and not named:
        return "契約違規：verdict=REJECT 但 blocking 為空（未指名缺陷）"
    if v == "REJECT" and require_evidence:
        bad = [b for b in named
               if not _LOCATABLE_RE.search(b if isinstance(b, str) else json.dumps(b, ensure_ascii=False))]
        if bad:
            return f"契約違規：blocking 缺可定位依據（檔名／行號）（{len(bad)} 條）"
    return None


_FILE_HDR_RE = re.compile(r"(?m)^diff --git a/(\S+)")
_PATCH_BLOCK_RE = re.compile(r"(?m)^(?=diff --git )")


def _chunk_lines(text: str, cap: int) -> list[str]:
    """把一段文字切成 ≤cap 的片段：優先於**行邊界**切；單行本身超限時才在行內切。

    行內切是必要之惡（真實案例：344KB 的單行 HTML），此時輸出仍是完整覆蓋，
    由 `split_patch` 回報切點、prompt 明示「切點不是缺陷」。
    """
    if cap <= 0 or len(text) <= cap:
        return [text]
    out: list[str] = []
    cur = ""
    for ln in text.splitlines(keepends=True):
        while len(ln) > cap:
            room = cap - len(cur)
            cur += ln[:room]
            ln = ln[room:]
            out.append(cur)
            cur = ""
        if len(cur) + len(ln) > cap:
            out.append(cur)
            cur = ""
        cur += ln
    if cur:
        out.append(cur)
    return out or [""]


def split_patch(patch: str, diff_cap: int = DEFAULT_DIFF_CAP) -> list[dict]:
    """把 patch 切成送審段（**單一真值**；cio_lane 與 regenerate_report 共用）。

    規則（2026-10-16 使用者裁決）：
      ① 以**檔案邊界**為優先：段內只放完整的檔案區塊（`diff --git` 區塊），
         **禁止**為了湊長度而切穿檔案 —— 這正是 2026-10-16 07:00 假 REJECT 的來源。
      ② 單一檔案區塊本身 > cap 時才切成多段，並在回傳值標示該檔的段序（第 j/m 段）。
      ③ 覆蓋率恆為 100%：`"".join(text) == patch`（自我檢查，不變量）。

    回傳 `[{"text":..., "files":[...該段涵蓋的檔名...], "split": {檔名: (段序, 段數)}}]`
    """
    if not patch:
        return [{"text": "", "files": [], "split": {}}]
    blocks = [b for b in _PATCH_BLOCK_RE.split(patch) if b]
    segs: list[dict] = []
    cur, cur_files = "", []
    for blk in blocks:
        m = _FILE_HDR_RE.match(blk)
        name = m.group(1) if m else ""
        if len(blk) > diff_cap:
            if cur:
                segs.append({"text": cur, "files": cur_files, "split": {}})
                cur, cur_files = "", []
            pieces = _chunk_lines(blk, diff_cap)
            for j, pc in enumerate(pieces, 1):
                segs.append({"text": pc, "files": [name],
                             "split": {name: (j, len(pieces))} if len(pieces) > 1 else {}})
            continue
        if len(cur) + len(blk) > diff_cap:
            segs.append({"text": cur, "files": cur_files, "split": {}})
            cur, cur_files = "", []
        cur += blk
        cur_files.append(name)
    if cur:
        segs.append({"text": cur, "files": cur_files, "split": {}})
    if not segs:
        segs = [{"text": "", "files": [], "split": {}}]
    if "".join(s["text"] for s in segs) != patch:
        raise ValueError("分段覆蓋不完整（split_patch 自我檢查失敗）")
    return segs


def _seg_note(seg: dict, k: int, n: int) -> str:
    """分段脈絡提示（只在需要時產生；單段送審回空字串 → prompt 與舊版逐字相同）。"""
    if n <= 1:
        return ""
    lines = [f"ⓘ 分段送審：本段為完整 patch 的第 {k}/{n} 段（每段獨立判定，全部段落皆 APPROVE 才算通過）。"]
    if seg.get("split"):
        lines.append("ⓘ 下列檔案在本段被切成多段（**刻意分段，不是資料截斷或檔案缺漏**）：")
        for fname, (j, m) in seg["split"].items():
            lines.append(f"   - {fname}：本段為該檔第 {j}/{m} 段（僅含該檔的一部分，"
                         f"其餘段落為同一檔案的其他段）")
        lines.append("ⓘ 段尾若出現被切斷的內容（含超長 HTML／JSON 行），那是段落切點。")
    else:
        lines.append("ⓘ 本段未包含被切斷的檔案（段界落在檔案之間；段內每個 `diff --git` 區塊都是完整的）。")
    return "\n".join(lines)


def build_review_prompts(commit: str, tree: str, subject: str, files: str, stat: str,
                         diff_cap: int = DEFAULT_DIFF_CAP,
                         patch: str | None = None) -> tuple[list[str], dict]:
    """組送審 prompt（超量 diff 改為**檔案邊界分段**的完整涵蓋，不再靜默截斷）→ (prompts, coverage)。

    coverage：`total_chars`／`provided_chars`／`pct`／`segments`／`file_aligned`／`split_files`。
    分段時所有字元都被涵蓋（pct 恆 100）；每段獨立判定，未完整涵蓋時不得 APPROVE。
    段落切點由 `split_patch` 決定（**不切穿檔案**，僅超限單檔才續切成多段）。
    """
    total = len(patch or "")
    if patch is None:
        return ([build_review_prompt(commit, tree, subject, files, stat, diff_cap, patch)],
                {"total_chars": 0, "provided_chars": 0, "pct": 100.0, "segments": 1,
                 "file_aligned": True, "split_files": {}})
    segs = split_patch(patch, diff_cap)
    n = len(segs)
    prompts = [build_review_prompt(commit, tree, subject, files, stat, diff_cap, s["text"],
                                   segment=(k + 1, n), seg_note=_seg_note(s, k + 1, n))
               for k, s in enumerate(segs)]
    split_map = {str(k + 1): s["split"] for k, s in enumerate(segs) if s.get("split")}
    return prompts, {"total_chars": total, "provided_chars": total, "pct": 100.0,
                     "segments": n, "file_aligned": True, "split_files": split_map}


def review_segmented(prompts: list[str], coverage: dict, *, max_tokens: int = 8192,
                     timeout: float = 300, json_mode: bool = True,
                     expect_pair: tuple[str, str] | None = None,
                     retry_technical: int = _RETRY_TECHNICAL) -> tuple[str, str, dict]:
    """逐段審查＋彙總（涵蓋率 <100% 直接拒絕核准，不呼叫模型）。

    回傳 (JSON 文字, 審查者標籤, meta)。任一段有 blocking → 整體 REJECT（blocking 取聯集）。
    `expect_pair=(commit12, tree12)` 時，每段都必須原樣回報該綁定；任一
    段綁定不符 → 整體 REJECT（不得以未綁定的審查放行）。

    2026-10-16 使用者裁決（一次到位）：
      ① **技術性失敗**（`review()` 丟例外＝全層不可用／全層無有效結果）每段最多重試
         `retry_technical` 次（預設 2）；重試用盡仍失敗 → 丟 RuntimeError（呼叫端
         fail-closed），**不得**當成通過。
      ② **有效 REJECT 一律不重試**（不換層、不重抽＝不投票、不洗結果）。
      ③ 段級完整性：任一段若無可解析的有效結果（verdict 不可判定／契約違規）→
         列入 blocking（不通過），避免「缺段／漏審」被靜默吞掉。
    """
    pct = float(coverage.get("pct", 0.0) or 0.0)
    if pct < 100.0:
        _block = [f"diff 涵蓋率 {pct:.1f}% < 100%，未完成分段審查 → 不得核准（review_chain coverage guard）"]
        out = {"verdict": "REJECT", "blocking": _block, "note": "coverage guard",
               "required_fixes": [], "coverage": coverage}
        return (json.dumps(out, ensure_ascii=False), "coverage-guard",
                {"verdict": "REJECT", "coverage": coverage, "labels": [], "segments": 0})
    if not prompts:
        out = {"verdict": "REJECT", "blocking": ["無任何送審段（缺段／漏審）→ 不得核准"],
               "note": "no segments", "required_fixes": [], "coverage": coverage}
        return (json.dumps(out, ensure_ascii=False), "no-segments",
                {"verdict": "REJECT", "coverage": coverage, "labels": [], "segments": 0})
    labels: list[str] = []
    blockers: list = []
    notes: list[str] = []
    pairs: set[tuple[str, str]] = set()
    binding_bad: list[str] = []
    retried: list[str] = []
    invalid_segs: list[str] = []
    for k, p in enumerate(prompts, 1):
        text, label, attempts = None, "", 0
        _err = ""
        for attempt in range(1, max(0, int(retry_technical)) + 2):
            attempts = attempt
            try:
                text, label = review(p, max_tokens=max_tokens, timeout=timeout, json_mode=json_mode)
                break
            except Exception as exc:  # noqa: BLE001  技術性失敗（唯一可重試的情形）
                text = None
                _err = f"{type(exc).__name__}: {str(exc)[:160]}"
                if attempt <= max(0, int(retry_technical)):
                    time.sleep(_RETRY_BACKOFF * attempt)
        if text is None:
            # 重試用盡仍無有效結果 → 不得視為通過（缺段／漏審），fail-closed 上拋
            raise RuntimeError(f"第 {k}/{len(prompts)} 段技術性失敗"
                               f"（重試 {max(0, int(retry_technical))} 次後仍失敗）：{_err}")
        if attempts > 1:
            retried.append(f"seg{k}:{attempts}")
        labels.append(label)
        j = parse_review(text) or {}
        _v_seg = str(j.get("verdict") or "").strip().upper()
        _cv_seg = contract_violation(j)
        if _v_seg not in ("APPROVE", "REJECT") or _cv_seg:
            # 有效 REJECT 不會走到這裡（`review()` 已先驗過契約）；此處是「無效結果」防線。
            # 2026-10-16：無效段仍要**保留它指名的缺陷**（模型可能回 APPROVE 卻列了 blocking／
            #   缺可定位依據等），否則診斷訊息會失去關鍵線索（既有的 test_05 就是這條路徑）。
            invalid_segs.append(f"seg{k}:{_cv_seg or 'verdict 不可判定'}")
            for _b in (j.get("blocking") or []):
                if str(_b).strip():
                    blockers.append(f"seg{k}（無效審查，僅供診斷）: {_b}")
            notes.append(f"seg{k}:INVALID@{label}")
            continue
        blockers += [b for b in (j.get("blocking") or []) if str(b).strip()]
        notes.append(f"seg{k}:{_v_seg}@{label}")
        _seg_pairs = {(str(x.get("commit", ""))[:12], str(x.get("tree", ""))[:12])
                      for x in (j.get("reviewed_commits") or []) if isinstance(x, dict)}
        pairs |= _seg_pairs
        if expect_pair and tuple(expect_pair) not in _seg_pairs:
            binding_bad.append(f"第 {k}/{len(prompts)} 段未回報綁定 {expect_pair[0]}/{expect_pair[1]}")
    if binding_bad:
        blockers += binding_bad
    if invalid_segs:
        blockers += [f"無效審查結果（不得視為通過）：{s}" for s in invalid_segs]
    verdict = "REJECT" if blockers else "APPROVE"
    out = {"verdict": verdict, "blocking": blockers, "required_fixes": [],
           "reviewed_commits": [{"commit": c, "tree": t} for c, t in sorted(pairs)],
           "note": ("；".join(notes))[:300], "coverage": coverage}
    return (json.dumps(out, ensure_ascii=False), ",".join(sorted(set(labels))),
            {"verdict": verdict, "coverage": coverage, "labels": labels,
             "segments": len(prompts), "binding_bad": binding_bad,
             "invalid_segments": invalid_segs, "retried": retried})


def stability_check(verdicts: list[str]) -> dict:
    """同一輸入重複送審的一致性判定（純函式，可離線測試）。

    結論不一致 → `status="UNSTABLE"`：**不得作為核准依據**（維持 HOLD）。
    """
    vs = [str(v).strip().upper() for v in verdicts if str(v).strip()]
    stable = len(vs) >= 2 and len(set(vs)) == 1
    return {"stable": bool(stable), "verdicts": vs,
            "status": "STABLE" if stable else "UNSTABLE",
            "note": "" if stable else "同一輸入重複送審結論不一致 → UNSTABLE，不得作為核准依據"}


def review_stable(prompt: str, *, n: int = 3, max_tokens: int = 8192, timeout: float = 300,
                  json_mode: bool = True) -> tuple[dict, str]:
    """重複送審同一輸入並做一致性判定（生產／診斷用）。

    注意：此函式會實際呼叫模型 n 次（成本）。單元測試請改用 `stability_check`。
    """
    samples: list[str] = []
    labels: list[str] = []
    for _ in range(max(2, int(n))):
        text, label = review(prompt, max_tokens=max_tokens, timeout=timeout, json_mode=json_mode)
        labels.append(label)
        samples.append(str((parse_review(text) or {}).get("verdict") or "UNKNOWN"))
    st = stability_check(samples)
    st["labels"] = labels
    return st, ",".join(sorted(set(labels)))


def _valid_review(text: str) -> bool:
    """回覆是否含**可判定**的 verdict（APPROVE／REJECT）。

    2026-10-14：`_MIN_CONTENT = 2` 使得 `{}`（長度 2）恰被視為「有內容」→ 鏈直接採用
    → verdict 空 → 車道 fail-closed。實測第一層 Pollinations 會**間歇**回 `{}`，
    造成 3 段送審常態性卡住（與大小、內容無關）。

    語意邊界：**REJECT 是有效判定、原樣採用**（「拒審不換層」契約不變）；
    只有「無可判定 verdict」才視為該層失敗、續下一層（與逾時／空輸出同類）。
    """
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return False
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return False
    return str((obj or {}).get("verdict") or "").strip().upper() in ("APPROVE", "REJECT")


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
            if _valid_review(text):
                # 2026-10-15 B1（R1）：契約違規（verdict 與 blocking 不一致／缺可定位依據）
                # → 該層判**無效審查**，續試下一層；全層無效 → fail-closed 中止。
                _cv = contract_violation(parse_review(text))
                if _cv is None:
                    return text, label
                errors.append(f"{label}: {_cv}")
                continue
            errors.append(f"{label}: 回覆無可判定 verdict（{text.strip()[:60]}）")
            continue
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
