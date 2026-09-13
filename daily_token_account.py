#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_token_account.py — 每日 AI 成本帳（no_agent，零 LLM）

省錢分流方案 E 項：每天一行帳，讓「Gemini 佔比 < 30%」這個目標可被追蹤。

資料來源（本機、零 API）：
  1. logs/agent.log（+ agent.log.1）今日的 `API call #N: model=… provider=…
     in=… out=… cache=cached/in` 行 → 每個模型的 in/cached/out token 與估價
  2. cron/usage_audit.jsonl 今日的 fire 記錄（job_id / tokens / model）→
     「其中 cron 佔多少」與耗最多的 job（無快取資訊 → 估為上界）
  3. longjiu_system/cost_log.csv 尾筆 → DS 餘額與近期日耗（剩餘天數）

費率（來源：ai-api-cost-monitoring 技能，2026-08-27 查證官方定價頁；USD/1M）：
  DS V4 Flash 離峰 0.22/0.66、cache-hit 0.007；尖峰 ×2（台灣 09-12、14-18，週一~五）
  Gemini 2.5 Flash / 3.5 Flash-Lite 0.30/2.50、cache-hit 0.075（無尖離峰）
  USD→NT$ 以 31.5 換算（與技能一致）
"""
from __future__ import annotations

import collections
import csv
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERMES = Path.home() / "AppData" / "Local" / "hermes"
CRON_DIR = HERMES / "cron"
LJ = Path.home() / "Desktop" / "longjiu_system"
USD_TWD = 31.5

API_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}) (\d{2}):\d{2}:\d{2}.*API call #\d+: model=(\S+) provider=(\S+) "
    r"in=(\d+) out=(\d+) total=\d+ latency=\S+ cache=(\d+)/(\d+)")
PRICE = {  # model: (in, out, cache_hit, is_deepseek)
    # ── DeepSeek（2026-09-14 查官方定價頁；此為 off-peak 價，尖峰由 cost_usd 的 peak 係數 ×2 處理）──
    # 官方頁：deepseek-flash cache hit $0.003 / miss $0.15 / out $0.60；pro $0.022 / $0.66 / $1.98
    "deepseek-flash": (0.15, 0.60, 0.003, True),
    "deepseek-v4-flash": (0.15, 0.60, 0.003, True),          # 舊名（已退役，由 V4.1-Flash 服務、同價）
    "deepseek-v4-flash-vision-exp": (0.15, 0.60, 0.003, True),
    "deepseek-v4-pro": (0.66, 1.98, 0.022, True),
    # ── Gemini（2026-09-14 查官方定價頁 ai.google.dev/gemini-api/docs/pricing）──
    "gemini-3.6-flash": (0.75, 3.75, 0.075, False),
    "gemini-3.5-flash-lite": (0.30, 2.50, 0.03, False),
    "gemini-3.1-flash-lite": (0.25, 1.50, 0.025, False),
    "gemini-2.5-flash": (0.30, 2.50, 0.03, False),
    "gemini-2.5-flash-lite": (0.10, 0.40, 0.01, False),
}


def is_ds_peak(day: dt.date, hour: int) -> bool:
    """DS 尖峰（台灣）：週一~五 09:00-12:00 與 14:00-18:00。"""
    if day.weekday() >= 5:
        return False
    return (9 <= hour < 12) or (14 <= hour < 18)


def scan_agent_log(today: str):
    per = collections.defaultdict(lambda: collections.Counter())
    for name in ("agent.log", "agent.log.1"):
        p = HERMES / "logs" / name
        if not p.exists():
            continue
        try:
            with p.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    if today not in line[:12]:
                        continue
                    m = API_RE.match(line)
                    if not m:
                        continue
                    model, pin, pout = m.group(3), int(m.group(5)), int(m.group(6))
                    cached = int(m.group(7))
                    hour = int(m.group(2))
                    peak = is_ds_peak(dt.date.fromisoformat(m.group(1)), hour)
                    c = per[model]
                    c["calls"] += 1
                    c["in"] += pin
                    c["cached"] += cached
                    c["out"] += pout
                    if peak:
                        c["peak_calls"] += 1
        except Exception as e:
            print(f"⚠️ 讀 agent.log 失敗（{name}）：{e}", file=sys.stderr)
    return per


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


def scan_failures(today: str):
    """今日 DS 內容風控（CER）與 Gemini 429 次數（去重：session+秒+attempt），
    用於追蹤「DS 被擋 → Gemini 代答」造成的成本外溢（INC-172/174）。"""
    import re
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


def cost_usd(model: str, tok: collections.Counter) -> float:
    # 未知模型用 DS 價保守估；DS/Gemini 一律看模型名稱（缺價表的 Gemini 模型才不會被誤當 DS）
    pin, pout, pcache, _ = PRICE.get(model, (0.15, 0.60, 0.003, True))
    is_ds = model.startswith("deepseek")
    miss = max(0, tok["in"] - tok["cached"])
    usd = miss / 1e6 * pin + tok["cached"] / 1e6 * pcache + tok["out"] / 1e6 * pout
    if is_ds and tok.get("peak_calls"):
        share = tok["peak_calls"] / max(1, tok["calls"])
        usd *= (1 + share)  # 尖峰段輸入/輸出都 ×2 → 平均約 (1+share)
    return usd


def ds_balance_line() -> str:
    p = LJ / "cost_log.csv"
    if not p.exists():
        return ""
    rows = []
    try:
        for r in csv.reader(p.open(encoding="utf-8")):
            if len(r) >= 2:
                try:
                    rows.append((r[0].strip(), float(r[1])))
                except Exception:
                    pass
    except Exception:
        return ""
    if not rows:
        return ""
    bal = rows[-1][1]
    rate = 0.0
    if len(rows) >= 2:
        tail = rows[-4:]
        try:
            d0 = dt.date.fromisoformat(tail[0][0]); d1 = dt.date.fromisoformat(tail[-1][0])
            span = max(1, (d1 - d0).days)
            rate = max(0.0, tail[0][1] - tail[-1][1]) / span
        except Exception:
            rate = 0.0
    days = f"，依近期日耗 {rate:.1f} 約剩 {bal/rate:.1f} 天" if rate > 0 else ""
    return f"DS 餘額 {bal:.2f} CNY（≈NT${bal*4.2:.0f}）{days}"


def main() -> None:
    today = dt.date.today().isoformat()
    per = scan_agent_log(today)
    if not per:
        print(f"💰 今日 AI 成本 {today}：agent.log 找不到任何 API call 記錄（可能剛輪替或尚未使用）")
        return
    usd_total = 0.0
    by_model = []
    ds_usd = gem_usd = 0.0
    for model, tok in sorted(per.items(), key=lambda kv: -cost_usd(kv[0], kv[1])):
        usd = cost_usd(model, tok)
        usd_total += usd
        if model.startswith("deepseek"):
            ds_usd += usd
        else:
            gem_usd += usd
        cache_pct = (tok["cached"] / tok["in"] * 100) if tok["in"] else 0
        by_model.append(f"{model} NT${usd*USD_TWD:.1f}｜{tok['calls']} 次、in {tok['in']/1e6:.1f}M"
                        f"（快取 {cache_pct:.0f}%）、out {tok['out']/1e6:.3f}M"
                        + (f"、尖峰 {tok['peak_calls']} 次" if tok.get("peak_calls") else ""))
    fires, cron_tok, per_job = scan_cron_audit(today)
    cron_usd = 0.0
    if cron_tok["in"] or cron_tok["out"]:
        cron_usd = cost_usd("deepseek-v4-flash", collections.Counter({
            "in": cron_tok["in"], "cached": 0, "out": cron_tok["out"], "calls": 1}))

    lines = [f"💰 今日 AI 成本 {today}（{'離峰' if not is_ds_peak(dt.date.today(), dt.datetime.now().hour) else '尖峰'}）"]
    for b in by_model:
        lines.append(f"・{b}")
    lines.append(f"・合計 NT${usd_total*USD_TWD:.1f}｜DS NT${ds_usd*USD_TWD:.1f}／"
                 f"Gemini NT${gem_usd*USD_TWD:.1f}（Gemini 佔 "
                 f"{gem_usd/usd_total*100 if usd_total else 0:.0f}%，目標 <30%）")
    if fires:
        top = sorted(per_job.items(), key=lambda kv: -kv[1])[:3]
        names = job_names()

        def short(jid: str) -> str:
            n = str(names.get(jid, jid))
            return n.split("（")[0].strip()[:16]

        def tok_fmt(v: int) -> str:
            v = int(v or 0)
            return f"{v/1e6:.1f}M" if v >= 100_000 else f"{v/1000:.0f}K"

        t = "、".join(f"{short(k)} {tok_fmt(v)}" for k, v in top)
        lines.append(f"・其中 cron {fires} 次 fire ≈ NT${cron_usd*USD_TWD:.1f}（估上界，未計快取）｜最多：{t}")
    cer, q429, _failerr = scan_failures(today)
    _err_note = f"（讀取失敗：{_failerr}）" if _failerr else ""
    lines.append(f"・失敗：DS 內容風控(CER) {cer} 次、Gemini 429 {q429} 次{_err_note}"
                 + ("（CER → Gemini 代答＝成本外溢主因）" if cer else ""))
    bal = ds_balance_line()
    if bal:
        lines.append("・" + bal)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
