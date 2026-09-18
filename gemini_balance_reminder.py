"""Gemini 餘額提醒（每3天）— no_agent 版。

2026-09-16 改版：不再只讀本地 log 推算（log 停在 9/5 儲值 1,000，會誤報「還很多」）。
改成每次執行**實測 API**，回報真實狀態：
  200 → 可用（印出本次回應確認）
  429 `prepayment credits are depleted` → 已用盡（附儲值連結）
  401 → key 失效
儲值頁：https://aistudio.google.com/billing （Prepay 加值，最低 US$5）
餘額/用量頁：https://aistudio.google.com/usage
"""
import json
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
LOG = LJ / "data" / "gemini_cost_log.json"
ENV = Path.home() / "AppData" / "Local" / "hermes" / ".env"
PROBE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
TOPUP_URL = "https://aistudio.google.com/billing"


def _api_key() -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _flat(text: str) -> str:
    """錯誤訊息壓成一行（f-string 內不能放反斜線，故獨立成函式）。"""
    return re.sub(r"\s+", " ", text).strip()


def probe() -> tuple[str, str]:
    """實測 API → (狀態碼, 說明)。狀態碼：ok / depleted / unauthorized / error / no_key。"""
    key = _api_key()
    if not key:
        return "no_key", "GEMINI_API_KEY 未設定"
    body = json.dumps({
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }).encode("utf-8")
    req = urllib.request.Request(
        PROBE_URL, data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return "ok", f"API 可用（HTTP {resp.status}）"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        if "prepayment credits are depleted" in detail:
            return "depleted", "預付金已用盡（429 RESOURCE_EXHAUSTED）"
        if exc.code == 401:
            return "unauthorized", "憑證失效（401）"
        return "error", f"HTTP {exc.code}：{_flat(detail)[:120]}"
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


def log_balance_twd() -> float | None:
    """log 內最近一次記錄的餘額（僅供對照，不再用來推算剩餘天數）。"""
    if not LOG.exists():
        return None
    try:
        data = json.loads(LOG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    for key in sorted([k for k in data if isinstance(k, str) and len(k) == 7], reverse=True):
        entry = data.get(key)
        if isinstance(entry, dict):
            for bk in ("credit_balance_twd", "balance_twd"):
                if entry.get(bk) is not None:
                    return float(entry[bk])
    return None


def main():
    today = date.today()
    state, note = probe()
    log_bal = log_balance_twd()

    lines = [f"💰 Gemini 狀態（{today.month}/{today.day}，實測 API）："]

    if state == "ok":
        lines.append(f"- ✅ {note}")
        if log_bal is not None:
            lines.append(f"- log 最後記錄餘額 NT${log_bal:.0f}（對照用）")
        lines.append("- fallback 鏈（9/18 定案）：DS-pro → Gemini 2.5 Flash；Gemini 僅最後一道，且無快取全價的 3.6-flash 已移出鏈")
    elif state == "depleted":
        lines.append(f"- ⛔ {note}")
        lines.append("- fallback 鏈（9/18 定案）：DS-pro → Gemini 2.5 Flash；免費層 opencode-free 因 403 已移除")
        lines.append(f"- 要恢復 Gemini：儲值 {TOPUP_URL}（Prepay 最低 US$5）")
        lines.append("- 未儲值前這則提醒可停用（`hermes cron`）")
    elif state == "unauthorized":
        lines.append(f"- ⛔ {note} → 這把 key 已失效，需在 AI Studio 重新產生")
        lines.append(f"- {TOPUP_URL}")
    elif state == "no_key":
        lines.append(f"- ⚠️ {note}（.env 無 GEMINI_API_KEY）")
    else:
        lines.append(f"- ⚠️ 無法判定：{note}（可能是網路或服務中斷，非額度問題）")

    if state != "ok":
        print("\n".join(lines))
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
