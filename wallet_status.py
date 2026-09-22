#!/usr/bin/env python
"""wallet_status.py — 一句話查兩個錢包（DeepSeek / Gemini）＋儲值連結。

設計：no_agent 純腳本（零 LLM、零逾時風險），供 cron 一鍵呼叫。
  DS    ：GET /user/balance（真值 API）
  Gemini：預付制無餘額 API → 用小額 generateContent 探測（8 tok，便宜），
          依錯誤碼判：200 = 可用 / 429 depleted = 用盡 / 401 = key 失效
輸出：固定短格式（餘額、日耗、剩餘天數、儲值連結）。
"""
import csv
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
ENV = Path.home() / "AppData" / "Local" / "hermes" / ".env"
GEMINI_LOG = LJ / "data" / "gemini_cost_log.json"
DS_LOG = LJ / "cost_log.csv"
DS_URL = "https://api.deepseek.com/user/balance"
DS_TOPUP = "https://platform.deepseek.com/top_up"
GM_TOPUP = "https://aistudio.google.com/billing"
GM_PROBE = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
# 日耗：2026-09-22 起改為動態 —— 從 cost_log.csv（餘額扣款真值）取近 N 筆非儲值日
# 的中位數。舊版寫死 ¥15.5（9/5-9/17 含 CER 風暴日的平均）會把剩餘天數低估近一半
# （9/22 實例：寫死 15.5 → 6.1 天 ⛔；實際近 7 日中位數 9.07 → 10.4 天 ⚠️）。
DS_BURN_WINDOW = 7          # 取近幾筆有效日
DS_BURN_FLOOR_CNY = 5.0     # 下限保護：中位數低於此值時以 FLOOR 計，避免單日極低把天數吹大
DS_BURN_FALLBACK_CNY = 10.0  # cost_log.csv 不可讀時的保守值
CNY_TWD = 4.73
USD_TWD = 31.7


def env_value(name: str) -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def ds_status() -> tuple[str, str]:
    key = env_value("DEEPSEEK_API_KEY")
    if not key:
        return "no_key", "DEEPSEEK_API_KEY 未設定"
    req = urllib.request.Request(DS_URL, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        cny = next((b for b in d.get("balance_infos", []) if b.get("currency") == "CNY"), None)
        if not cny:
            return "error", "回應無 CNY 餘額"
        return "ok", cny.get("total_balance", "?")
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


def gemini_status() -> tuple[str, str]:
    key = env_value("GEMINI_API_KEY")
    if not key:
        return "no_key", "GEMINI_API_KEY 未設定"
    body = json.dumps({
        "contents": [{"parts": [{"text": "ping"}]}],
        "generationConfig": {"maxOutputTokens": 1},
    }).encode()
    req = urllib.request.Request(GM_PROBE, data=body,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return "ok", f"HTTP {r.status}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        if "prepayment credits are depleted" in detail:
            return "depleted", "預付金用盡（429）"
        if exc.code == 401:
            return "unauthorized", "憑證失效（401）"
        if "input_token_count" in detail or "rate" in detail.lower():
            return "rate_limit", f"速率上限（429，非餘額問題）"
        return "error", f"HTTP {exc.code}：{re.sub(chr(92) + 's+', ' ', detail)[:110]}"
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


def gemini_log_balance() -> str:
    if not GEMINI_LOG.exists():
        return "無記錄"
    try:
        d = json.loads(GEMINI_LOG.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return "讀取失敗"
    for k in sorted([k for k in d if isinstance(k, str) and len(k) == 7], reverse=True):
        e = d.get(k)
        if isinstance(e, dict) and e.get("credit_balance_twd") is not None:
            return f"NT${float(e['credit_balance_twd']):,.0f}"
    return "無記錄"


def ds_daily_burn() -> tuple[float, str]:
    """DeepSeek 日耗（CNY）：cost_log.csv 近 N 筆非儲值日的中位數。

    為何不用平均、不用 log 估價：① 中位數避開 CER 風暴日（9/11 ¥42）把日耗拉高；
    ② cost_log.csv 是「餘額扣款」真值，本機 log 估價系統性低估 1.8x（2026-09-18 實證）。
    """
    vals: list[float] = []
    try:
        with DS_LOG.open(encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if r and r[0].strip()]
    except Exception:  # noqa: BLE001
        return DS_BURN_FALLBACK_CNY, "fallback（cost_log 不可讀）"
    for r in reversed(rows[1:]):
        if len(r) < 3:
            continue
        try:
            v = float(r[2])
        except ValueError:
            continue
        if v <= 0:  # 儲值列與無用量日不計入分母
            continue
        vals.append(v)
        if len(vals) >= DS_BURN_WINDOW:
            break
    if not vals:
        return DS_BURN_FALLBACK_CNY, "fallback（無有效日）"
    vals.sort()
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    if med < DS_BURN_FLOOR_CNY:
        return DS_BURN_FLOOR_CNY, f"下限 ¥{DS_BURN_FLOOR_CNY:.1f}（近{n}日中位數 ¥{med:.1f}）"
    return med, f"近{n}日中位數"


def main():
    today = date.today()
    ds_state, ds_val = ds_status()
    gm_state, gm_note = gemini_status()
    lines = [f"💰 錢包狀態 {today.month}/{today.day} {datetime.now().strftime('%H:%M')}"]

    if ds_state == "ok":
        try:
            cny = float(ds_val)
            rate, basis = ds_daily_burn()
            days = cny / rate
            flag = "⛔" if days < 7 else ("⚠️" if days < 14 else "✅")
            lines.append(f"- DeepSeek  ¥{cny:.2f}（≈NT${cny * CNY_TWD:,.0f}）"
                         f"｜日耗 ¥{rate:.1f}（{basis}）→ 約 {days:.1f} 天 {flag}")
        except ValueError:
            lines.append(f"- DeepSeek  ¥{ds_val}")
    else:
        lines.append(f"- DeepSeek  ⚠️ {ds_val}")

    if gm_state == "ok":
        lines.append(f"- Gemini    {gemini_log_balance()}（對照值）｜探測 {gm_note} ✅")
    elif gm_state == "depleted":
        lines.append(f"- Gemini    ⛔ {gm_note} → 需儲值")
    elif gm_state == "rate_limit":
        lines.append(f"- Gemini    ⚠️ {gm_note}")
    else:
        lines.append(f"- Gemini    ⚠️ {gm_note}")

    lines.append(f"- 儲值：DS {DS_TOPUP}")
    lines.append(f"        Gemini {GM_TOPUP}")

    if ds_state == "ok":
        try:
            if float(ds_val) < 50:
                lines.append("- ⛔ DS <¥50，建議立刻儲值")
        except ValueError:
            pass
    print("\n".join(lines))


if __name__ == "__main__":
    main()
