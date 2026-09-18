#!/usr/bin/env python
"""wallet_status.py — 一句話查兩個錢包（DeepSeek / Gemini）＋儲值連結。

設計：no_agent 純腳本（零 LLM、零逾時風險），供 cron 一鍵呼叫。
  DS    ：GET /user/balance（真值 API）
  Gemini：預付制無餘額 API → 用小額 generateContent 探測（8 tok，便宜），
          依錯誤碼判：200 = 可用 / 429 depleted = 用盡 / 401 = key 失效
輸出：固定短格式（餘額、日耗、剩餘天數、儲值連結）。
"""
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
# 日耗參考（2026-09-18 以真實帳單反推：9/5-9/17 非儲值日平均 ¥15.49/天，含 9/11 異常日 ¥42）
DS_DAILY_CNY = 15.5
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


def main():
    today = date.today()
    ds_state, ds_val = ds_status()
    gm_state, gm_note = gemini_status()
    lines = [f"💰 錢包狀態 {today.month}/{today.day} {datetime.now().strftime('%H:%M')}"]

    if ds_state == "ok":
        try:
            cny = float(ds_val)
            days = cny / DS_DAILY_CNY
            flag = "⛔" if days < 7 else ("⚠️" if days < 14 else "✅")
            lines.append(f"- DeepSeek  ¥{cny:.2f}（≈NT${cny * CNY_TWD:,.0f}）｜日耗 ¥{DS_DAILY_CNY:.1f} → 約 {days:.1f} 天 {flag}")
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
