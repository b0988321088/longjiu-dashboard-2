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
import sys
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
# 日耗：2026-09-22 起改為「單一口徑」—— 一律呼叫 cost_rates.ds_burn()（餘額真值法：
# cost_log.csv 相鄰連續日餘額差、只取正差、近 7 個日曆日平均）。本檔不再自己算：
# 舊版本檔用「近 7 筆非儲值日中位數」（¥9.1 → 10.4 天），與 ai_cost_watch 的餘額真值均值
# （¥11.5 → 8.0 天）差 1.2 倍，同一顆錢包兩個結論；三支腳本統一後只剩一種數字。
DS_BURN_FALLBACK_CNY = 10.0  # cost_rates 不可用時的保守值（僅顯示用，不再當真值）
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
    """DS 日耗（CNY）＝ cost_rates 單一口徑（2026-09-22 統一定案）。

    本檔不再自己算：以前用 cost_log.csv 的「近 7 筆非儲值日中位數」，與 ai_cost_watch 的
    「餘額真值均值」差 1.2 倍（9.1 vs 11.5 CNY），同一顆錢包會得出 10.4 天與 8.0 天兩種結論。
    現在三支腳本一律呼叫 cost_rates.ds_burn()（連續日、只取正差、近 7 個日曆日平均）。
    """
    try:
        sys.path.insert(0, str(LJ))
        from cost_rates import ds_burn  # noqa: PLC0415
        b = ds_burn()
        if b.get("ok") and b.get("rate_cny"):
            return float(b["rate_cny"]), str(b["window"])
        return DS_BURN_FALLBACK_CNY, f"fallback（{b.get('window') or '無樣本'}）"
    except Exception as exc:  # noqa: BLE001 — 口徑模組壞掉不該讓錢包查詢整個失敗
        return DS_BURN_FALLBACK_CNY, f"fallback（{type(exc).__name__}）"


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
