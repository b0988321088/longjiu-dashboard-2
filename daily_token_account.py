#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_token_account.py — 每日 AI 費用與餘額帳（no_agent，零 LLM）

一次回答兩個問題：**今天花多少**、**還剩多少餘額**（DeepSeek / Gemini 各一行）。

資料來源（本機、零 API，除 DS 餘額與 Gemini 探測）：
  1. logs/agent.log(.1/.2/.3) 的 `API call #N: model=… provider=… in=… out=… cache=c/in`
     → 每模型 in/cached/out token，套官方現行價（PRICE 表）
  2. DeepSeek 餘額：GET /user/balance（真值 API）；失敗才退回 cost_log.csv 尾筆
  3. Gemini 餘額：預付制**無餘額 API** → 「最近一次儲值金額 − 儲值後 log 口徑用量」推定，
     再用 8-token 探測驗證（200=可用 / 429 depleted=用盡）。真值仍在 Google 帳單頁。
  4. cron/usage_audit.jsonl 今日 fire 記錄 → cron 佔多少

費率（PRICE 表為唯一來源，官方定價頁查證）：
  DS V4 Flash 離峰 0.15/0.60、cache-hit 0.003；尖峰（台灣週一~五 09-12、14-18）×2
  Gemini 2.5 Flash 0.30/2.50、cache-hit 0.03（2026-09-20 官網實查，取代舊 0.15/0.60 快照）
  ⚠️ Hermes state.db 的 estimated_cost_usd 用的是 2026-07-28 快照（2.5-flash 記為 0.15/0.60/0.015）
     → 約低估 2 倍，故本檔一律自算，不讀 state.db。
  USD→NT$ 31.7、CNY→NT$ 4.73（2026-09-14）
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERMES = Path.home() / "AppData" / "Local" / "hermes"
CRON_DIR = HERMES / "cron"
LJ = Path.home() / "Desktop" / "longjiu_system"
ENV_FILE = HERMES / ".env"
GEMINI_LOG = LJ / "data" / "gemini_cost_log.json"
PIPELINE_USAGE = LJ / "logs" / "pipeline_llm_usage.jsonl"  # 管線端（llm_analysis）用量落地檔
USD_TWD = 31.7  # 2026-09-14 Yahoo USDTWD 31.705（原 31.5）
CNY_TWD = 4.73  # 2026-09-14 使用者確認（200 CNY≈944 TWD）；Yahoo CNYTWD 4.734

# cache 欄位為選配：provider 沒回快取資訊時整行沒有 cache=，舊 regex 會把整筆呼叫漏掉
# （2026-09-20 實測：當日 53 行 Gemini 呼叫因缺 cache= 全數漏算 → 日帳低估 2.4 倍）。
API_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\d{2}.*API call #\d+: model=(\S+) provider=(\S+) "
    r"in=(\d+) out=(\d+) total=\d+ latency=\S+(?: cache=(\d+)/(\d+))?")
PRICE = {  # model: (in, out, cache_hit, is_deepseek)
    # ── DeepSeek（2026-09-14 查官方定價頁；此為 off-peak 價，尖峰由 cost_usd 的 peak 係數 ×2 處理）──
    # 官方頁：deepseek-flash cache hit $0.003 / miss $0.15 / out $0.60；pro $0.022 / $0.66 / $1.98
    "deepseek-flash": (0.15, 0.60, 0.003, True),
    "deepseek-v4-flash": (0.15, 0.60, 0.003, True),          # 舊名（已退役，由 V4.1-Flash 服務、同價）
    "deepseek-chat": (0.15, 0.60, 0.003, True),              # llm_analysis.py 實際送出的模型名
    "deepseek-v4-flash-vision-exp": (0.15, 0.60, 0.003, True),
    "deepseek-v4-pro": (0.66, 1.98, 0.022, True),
    # ── Gemini（2026-09-20 官網 ai.google.dev/gemini-api/docs/pricing 實查）──
    "gemini-2.5-flash": (0.30, 2.50, 0.03, False),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01, False),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03, False),
    "gemini-3.1-flash-lite": (0.25, 1.50, 0.025, False),
    "gemini-3.6-flash": (0.75, 3.75, 0.075, False),
}
LOG_FILES = ("agent.log", "agent.log.1", "agent.log.2", "agent.log.3")


def is_ds_peak(day: dt.date, hour: int) -> bool:
    """DS 尖峰（台灣）：週一~五 09:00-12:00 與 14:00-18:00。"""
    if day.weekday() >= 5:
        return False
    return (9 <= hour < 12) or (14 <= hour < 18)


def scan_agent_log_range(days: set[str]) -> dict[str, dict[str, collections.Counter]]:
    """掃 logs/agent.log*，回傳 {日期: {模型: Counter}}，只取 days 內的行。"""
    per: dict[str, dict[str, collections.Counter]] = collections.defaultdict(
        lambda: collections.defaultdict(collections.Counter))
    for name in LOG_FILES:
        p = HERMES / "logs" / name
        if not p.exists():
            continue
        try:
            with p.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line[:10] in days:
                        continue
                    m = API_RE.match(line)
                    if not m:
                        continue
                    date, hour = m.group(1), int(m.group(2))
                    model, pin, pout = m.group(3), int(m.group(5)), int(m.group(6))
                    cached = int(m.group(7) or 0)  # 缺 cache 欄位（無快取資訊）→ 視為 0（全價）
                    c = per[date][model]
                    c["calls"] += 1
                    c["in"] += pin
                    c["cached"] += cached
                    c["out"] += pout
                    if is_ds_peak(dt.date.fromisoformat(date), hour):
                        c["peak_calls"] += 1
        except Exception as e:
            print(f"⚠️ 讀 agent.log 失敗（{name}）：{e}", file=sys.stderr)
    return {d: dict(models) for d, models in per.items()}


def scan_agent_log(today: str) -> dict[str, collections.Counter]:
    """單日（維持舊介面，供其他腳本沿用）。"""
    return scan_agent_log_range({today}).get(today, {})


def scan_pipeline_usage(today: str) -> dict:
    """管線端（程式呼叫、非對話）用量：讀 llm_analysis 落地的 jsonl。

    回傳 {model: Counter(calls/in/cached/out/fail)}，另含 "_meta": {HH:MM: 次數} 供判斷跑了幾輪。
    背景（2026-09-21）：agent.log 只記 Hermes 端 → 帳面 NT$5 與實帳 NT$36 對不起來。
    """
    per: dict = collections.defaultdict(collections.Counter)
    if not PIPELINE_USAGE.exists():
        return {}
    try:
        with PIPELINE_USAGE.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ts = str(rec.get("ts") or "")
                if ts[:10] != today:
                    continue
                c = per[rec.get("model") or "unknown"]
                c["calls"] += 1
                c["in"] += int(rec.get("in") or 0)
                c["cached"] += int(rec.get("cached") or 0)
                c["out"] += int(rec.get("out") or 0)
                if not rec.get("ok", True):
                    c["fail"] += 1
                per["_meta"][ts[11:16]] += 1
    except Exception:
        return {}
    return dict(per)


def cost_usd(model: str, tok: collections.Counter) -> float:
    # 免費層（`:free` 尾綴）一律 0：它們的 pricing 在 provider 端是 0，不可套缺價表的保守估價，
    # 否則會在帳上憑空長出成本（2026-09-20 實測 longcat-2.0:free 被估成 US$0.003）。
    if ":free" in model:
        return 0.0
    # 未知模型用 DS 價保守估；DS/Gemini 一律看模型名稱（缺價表的 Gemini 模型才不會被誤當 DS）
    pin, pout, pcache, _ = PRICE.get(model, (0.15, 0.60, 0.003, True))
    is_ds = model.startswith("deepseek")
    miss = max(0, tok["in"] - tok["cached"])
    usd = miss / 1e6 * pin + tok["cached"] / 1e6 * pcache + tok["out"] / 1e6 * pout
    if is_ds and tok.get("peak_calls"):
        share = tok["peak_calls"] / max(1, tok["calls"])
        usd *= (1 + share)  # 尖峰段輸入/輸出都 ×2 → 平均約 (1+share)
    return usd


def day_split(per_day: dict[str, collections.Counter]) -> tuple[float, float]:
    """回傳（DS USD, 備援/Gemini USD）。"""
    ds = fb = 0.0
    for model, tok in per_day.items():
        usd = cost_usd(model, tok)
        if model.startswith("deepseek"):
            ds += usd
        else:
            fb += usd
    return ds, fb


def scan_cron_audit(today: str):
    p = CRON_DIR / "usage_audit.jsonl"
    total = collections.Counter()
    per_job = collections.Counter()
    fires = 0
    if not p.exists():
        return fires, total, per_job
    try:
        for line in p.open(encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            ts = str(r.get("ts") or "")
            # usage_audit 的 ts 是 UTC → 換算台北日期再比對
            try:
                d = dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) + dt.timedelta(hours=8)
            except Exception:
                continue
            if d.date().isoformat() != today:
                continue
            fires += 1
            total["in"] += int(r.get("prompt_tokens") or 0)
            total["out"] += int(r.get("completion_tokens") or 0)
            per_job[str(r.get("job_id"))] += int(r.get("total_tokens") or 0)
    except Exception as e:
        print(f"⚠️ 讀 usage_audit 失敗：{e}", file=sys.stderr)
    return fires, total, per_job


def scan_failures(today: str) -> tuple[int, int, list[str]]:
    """今日 DS 內容風控（CER）與 Gemini 429 次數（去重：session+秒+attempt），
    用於追蹤「DS 被擋 → Gemini 代答」造成的成本外溢（INC-172/174）。"""
    pat = re.compile(
        r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),\d+ WARNING \[([^\]]+)\] "
        r"agent\.conversation_loop: API call failed \(attempt (\d)/\d\) error_type=\S+ .*?"
        r"provider=(\S+) .*?model=(\S+) summary=(.*)$")
    seen = set()
    cer = q429 = 0
    errors = []
    for name in ("errors.log", "errors.log.1", "errors.log.2", "agent.log", "agent.log.1", "agent.log.2"):
        p = HERMES / "logs" / name
        if not p.exists():
            continue
        try:
            for line in p.open(encoding="utf-8", errors="ignore"):
                # 格式假設（Hermes log 固定格式）：行首即 YYYY-MM-DD 時間戳；格式變更需同步調整
                if not line.startswith(today) or "API call failed" not in line:
                    continue
                m = pat.match(line)
                if not m:
                    continue
                s = m.group(7)
                # 去重鍵要含 summary：同一秒同 attempt 可能是 CER 與 429 兩筆不同事件
                key = (m.group(3), m.group(2), m.group(4), m.group(5), m.group(6), s[:120])
                if key in seen:
                    continue
                seen.add(key)
                if "Content Exists Risk" in s:
                    cer += 1
                elif "429" in s or "RESOURCE_EXHAUSTED" in s:
                    q429 += 1
        except Exception as e:
            # 不靜默吞錯，回報讓帳面可稽核（僅型別與訊息前段，不含路徑細節）
            errors.append(f"{name}: {type(e).__name__} {str(e)[:60]}")
    return cer, q429, errors


def job_names() -> dict:
    p = CRON_DIR / "jobs.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            raw = d.get("jobs") or d
            js = list(raw.values()) if isinstance(raw, dict) else list(raw)
        else:
            js = list(d)
        return {str(j.get("id")): j.get("name") for j in js if isinstance(j, dict)}
    except Exception:
        return {}


def env_value(name: str) -> str:
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip().startswith(name + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


# ── 餘額 ──────────────────────────────────────────────────────────────────────────────
def ds_balance_live() -> tuple[float | None, str]:
    """真值 API：回傳（CNY 餘額, 備註）。"""
    key = env_value("DEEPSEEK_API_KEY")
    if not key:
        return None, "DEEPSEEK_API_KEY 未設定"
    req = urllib.request.Request("https://api.deepseek.com/user/balance",
                                 headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode())
        cny = next((b for b in d.get("balance_infos", []) if b.get("currency") == "CNY"), None)
        if not cny:
            return None, "回應無 CNY 餘額"
        return float(cny.get("total_balance", 0)), "API"
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def ds_balance_csv() -> tuple[float | None, str]:
    """退路：cost_log.csv 尾筆（可能落後一天）。"""
    p = LJ / "cost_log.csv"
    if not p.exists():
        return None, "無 cost_log.csv"
    last = None
    try:
        for r in csv.reader(p.open(encoding="utf-8")):
            if len(r) >= 2:
                try:
                    last = (r[0].strip(), float(r[1]))
                except Exception:
                    pass
    except Exception:
        return None, "cost_log.csv 讀取失敗"
    if not last:
        return None, "cost_log.csv 無資料"
    return last[1], f"cost_log.csv（{last[0]}，可能落後）"


def gemini_topup() -> tuple[str, float, str]:
    """回傳（儲值日期, 金額 TWD, 時分 HH:MM 或 ""）。取 log 內最新一筆有金額的儲值。"""
    if not GEMINI_LOG.exists():
        return "", 0.0, ""
    try:
        d = json.loads(GEMINI_LOG.read_text(encoding="utf-8"))
    except Exception:
        return "", 0.0, ""
    best: tuple[str, float, str] = ("", 0.0, "")
    for k, v in d.items():
        if not isinstance(v, dict):
            continue
        if isinstance(v.get("topup_twd"), (int, float)) and v.get("date"):
            cand = (str(v["date"])[:10], float(v["topup_twd"]), "")
            if cand[0] > best[0]:
                best = cand
        for kk, vv in v.items():
            if isinstance(vv, dict) and str(kk).startswith("topup") and isinstance(vv.get("amount_twd"), (int, float)):
                date = str(vv.get("date") or kk).replace("topup_", "").replace("_", "-")[:10]
                hhmm = ""
                probe = str(vv.get("confirmed_by_probe") or "")
                m = re.search(r"T(\d{2}:\d{2})", probe)
                if m:
                    hhmm = m.group(1)
                if date > best[0]:
                    best = (date, float(vv["amount_twd"]), hhmm)
    return best


def gemini_used_since(topup_date: str, topup_hhmm: str, per_range: dict[str, dict]) -> float:
    """儲值後累計 Gemini（備援）花費 USD，從 topup_date 起算。

    已知限制：per_range 是「日」彙總，故儲值當日無法切到儲值時刻之前 → 整日計入（略高估）。
    9/18 的情形是 08:29 儲值前處於歸零狀態，該時段幾乎沒有成功呼叫，誤差可忽略。
    """
    total = 0.0
    for date, models in per_range.items():
        if date < topup_date:
            continue
        for model, tok in models.items():
            if model.startswith("deepseek"):
                continue
            total += cost_usd(model, tok)
    return total


def gemini_probe() -> tuple[str, str]:
    """8-token 探測：ok / depleted / unauthorized / rate_limit / error / no_key。"""
    key = env_value("GEMINI_API_KEY")
    if not key:
        return "no_key", "GEMINI_API_KEY 未設定"
    body = json.dumps({"contents": [{"parts": [{"text": "ping"}]}],
                       "generationConfig": {"maxOutputTokens": 1}}).encode()
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        data=body, headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return "ok", f"HTTP {r.status}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")
        if "prepayment credits are depleted" in detail:
            return "depleted", "預付金用盡（429）"
        if exc.code == 401:
            return "unauthorized", "憑證失效（401）"
        if "429" in detail:
            return "rate_limit", "速率上限（非餘額問題）"
        return "error", f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return "error", f"{type(exc).__name__}: {exc}"


def main() -> None:
    now = dt.datetime.now()
    today = now.date()
    today_s = today.isoformat()
    week_days = {(today - dt.timedelta(days=i)).isoformat() for i in range(0, 8)}
    per_range = scan_agent_log_range(week_days | {(today - dt.timedelta(days=i)).isoformat() for i in range(8, 15)})
    per_today = per_range.get(today_s, {})
    if not per_range:
        print(f"💰 AI 費用 {today_s}：agent.log 找不到任何 API call 記錄（可能剛輪替或尚未使用）")
        return

    ds_usd, gem_usd = day_split(per_today)
    free_usd = sum(cost_usd(m, t) for m, t in per_today.items()
                   if not m.startswith("deepseek") and not m.startswith("gemini"))
    total_usd = ds_usd + gem_usd + free_usd
    free_calls = sum(t["calls"] for m, t in per_today.items() if not m.startswith("deepseek")
                     and not m.startswith("gemini"))

    # 近 7 日（不含今天）
    hist_days = [(today - dt.timedelta(days=i)).isoformat() for i in range(7, 0, -1)]
    hist = []
    for d in hist_days:
        a, b = day_split(per_range.get(d, {}))
        hist.append((d, a * USD_TWD, b * USD_TWD))

    def median(vals: list[float]) -> float:
        v = sorted(x for x in vals if x > 0)
        if not v:
            return 0.0
        n = len(v)
        return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2

    ds_hist = [a for _d, a, _b in hist]
    gm_hist = [b for _d, _a, b in hist]
    peak_note = ""
    if gm_hist and max(gm_hist) > 4 * max(1.0, median(gm_hist)):
        peak_note = "（含 CER 風暴日，免費入口上線後應下降）"

    lines = [f"💰 AI 費用與餘額 {today.month}/{today.day} {now.strftime('%H:%M')}（"
             f"{'尖峰' if is_ds_peak(today, now.hour) else '離峰'}）"]
    lines.append(f"◆ 今日花費 NT${total_usd*USD_TWD:,.0f}｜DeepSeek NT${ds_usd*USD_TWD:,.0f}／"
                 f"Gemini NT${gem_usd*USD_TWD:,.0f}／免費模型 NT${free_usd*USD_TWD:,.1f}（{free_calls} 次）")
    # ── 管線端（程式呼叫、非對話）用量：讓「每次更新花多少」可歸因（2026-09-21 新增）──
    _pu = scan_pipeline_usage(today_s)
    _prod = {m: c for m, c in _pu.items() if m != "_meta"}
    if _prod:
        _pc = sum(c["calls"] for c in _prod.values())
        _pin = sum(c["in"] for c in _prod.values())
        _pca = sum(c["cached"] for c in _prod.values())
        _po = sum(c["out"] for c in _prod.values())
        _pusd = sum(cost_usd(m, c) for m, c in _prod.items())
        _pfail = sum(c["fail"] for c in _prod.values())
        lines.append(f"　· 管線 LLM（程式呼叫）{_pc} 次／in {_pin:,}（cache {_pca:,}）out {_po:,}"
                     f" ≈ NT${_pusd*USD_TWD:,.1f}｜{len(_pu.get('_meta') or {})} 個時段"
                     + (f"｜失敗 {_pfail} 次" if _pfail else ""))
    else:
        lines.append("　· 管線 LLM（程式呼叫）：今日無紀錄（llm_analysis 落地檔為空）")
    lines.append(f"　· 近 7 日（{hist_days[0][5:]}→{hist_days[-1][5:]}）DS "
                 + " ".join(f"{a:.0f}" for a in ds_hist)
                 + " ｜ Gemini " + " ".join(f"{b:.0f}" for b in gm_hist) + "（NT$）")

    # ── DeepSeek 餘額 ──
    bal, src = ds_balance_live()
    if bal is None:
        bal, src = ds_balance_csv()
    if bal is not None:
        rate_cny = median(ds_hist) / CNY_TWD   # 日耗換算成 ¥（DS 以人民幣計價）；用中位數避開單日尖峰
        tail = "" if rate_cny <= 0 else f"｜日耗中位數 ¥{rate_cny:.1f} → 約 {bal/rate_cny:.1f} 天"
        flag = ""
        if rate_cny > 0:
            days = bal / rate_cny
            flag = " ⛔" if days < 7 else (" ⚠️" if days < 14 else " ✅")
        lines.append(f"　· DeepSeek ¥{bal:.2f}（≈NT${bal*CNY_TWD:,.0f}）{tail}{flag}（{src}）")
    else:
        lines.append(f"　· DeepSeek ⚠️ 餘額查詢失敗：{src}")

    # ── Gemini 餘額（推定 + 探測）──
    gm_state, gm_note = gemini_probe()
    up_date, up_amt, up_hhmm = gemini_topup()
    if gm_state == "depleted":
        lines.append("　· Gemini ⛔ 預付金已用盡（探測 429）→ 需儲值")
    elif up_amt > 0:
        used = gemini_used_since(up_date, up_hhmm, per_range)
        left = up_amt - used * USD_TWD
        rate_g = median(gm_hist)
        days_txt = "" if rate_g <= 0 else f"｜日耗中位數 NT${rate_g:,.0f} → 約 {left/rate_g:.1f} 天"
        flag_g = ""
        if rate_g > 0:
            d_left = left / rate_g
            flag_g = " ⛔" if d_left < 7 else (" ⚠️" if d_left < 14 else " ✅")
        probe = {"ok": "✅ 可用", "rate_limit": "⚠️ 速率上限", "unauthorized": "⛔ 憑證失效",
                 "no_key": "⛔ 未設 key", "error": "⚠️ 探測失敗"}.get(gm_state, gm_state)
        note = f"（{up_date} 儲 NT${up_amt:,.0f} − 儲值後已用 ≈NT${used*USD_TWD:,.0f}）"
        if left <= 0 and gm_state == "ok":
            lines.append(f"　· Gemini 推定已歸零但探測 {probe} → 儲值紀錄未更新，請補登 gemini_cost_log.json")
        else:
            lines.append(f"　· Gemini 推定 NT${max(0, left):,.0f}{note}{days_txt}{flag_g}｜探測 {probe}")
    else:
        lines.append(f"　· Gemini 無儲值紀錄可推定｜探測 {gm_note}")
    if peak_note:
        lines.append(f"　· 註：Gemini 日耗{peak_note}")

    # ── 異常與成本外溢 ──
    cer, q429, _failerr = scan_failures(today_s)
    err_note = f"（讀取失敗：{_failerr}）" if _failerr else ""
    lines.append(f"◆ 異常：DS 內容風控(CER) {cer} 次、Gemini 429 {q429} 次{err_note}"
                 + ("（CER → 備援代答＝成本外溢主因）" if cer else ""))
    fires, cron_tok, per_job = scan_cron_audit(today_s)
    if fires:
        names = job_names()

        def short(jid: str) -> str:
            return str(names.get(jid, jid)).split("（")[0].strip()[:16]

        def tok_fmt(v: int) -> str:
            v = int(v or 0)
            return f"{v/1e6:.1f}M" if v >= 100_000 else f"{v/1000:.0f}K"

        top = sorted(per_job.items(), key=lambda kv: -kv[1])[:3]
        lines.append(f"　· cron {fires} 次 fire｜最多：" + "、".join(f"{short(k)} {tok_fmt(v)}" for k, v in top))
    lines.append("◆ 儲值：DS https://platform.deepseek.com/top_up ｜ Gemini https://aistudio.google.com/billing")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
