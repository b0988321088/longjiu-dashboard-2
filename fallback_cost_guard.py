#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""備援花費熔斷（每日 21:10，no_agent）

為什麼存在：9/5 儲值 NT$1,000 在 11 天內被 CER 的洞燒光（gemini 端實測 27k-58k 輸入
token/次）。遮蔽閘已上線，但**花錢這件事要有熔斷**：超標就推 TG，未超標完全靜默。

2026-09-20 改版（口徑修正）：
  舊版讀 state.db `session_model_usage.estimated_cost_usd` 做差分，但那份價目快照
  （agent/usage_pricing.py，google-pricing-2026-07-28）把 gemini-2.5-flash 記成
  0.15 / 0.60 / 0.015，而官方現行 standard 是 0.30 / 2.50 / 0.03 → **警報值低估 2.07 倍**
  （9/20 實例：舊法說過去一天 US$1.385，log 口徑真值 US$2.87＝NT$91）。
  新版直接從 logs/agent.log* 算「非 DeepSeek 模型」的當日與昨日花費（同 daily_token_account
  的 PRICE 表＝唯一價目來源），門檻 US$0.30/天 才是真的 US$0.30。

語意：今日（00:00→現在）與昨日各自結算，任一超過門檻即告警；同一日期只告警一次
（狀態存 data/fallback_cost_state.json），避免同日重複推播。
門檻可用 env FALLBACK_COST_ALERT_USD 覆寫。
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import sys
from pathlib import Path

HERMES = Path.home() / "AppData" / "Local" / "hermes"
REPO = Path.home() / "Desktop" / "longjiu_system"
STATE = HERMES / "data" / "fallback_cost_state.json"
THRESHOLD = float(os.environ.get("FALLBACK_COST_ALERT_USD", "0.30"))
USD_TWD = 31.7


def _load_core():
    """從 repo 載入唯一價目/解析來源（cron 是從 HERMES_HOME/scripts 執行，該目錄的同名檔
    是薄轉發器、沒有 PRICE，故用檔案路徑載入，避免被影子檔蓋掉）。"""
    path = REPO / "daily_token_account.py"
    spec = importlib.util.spec_from_file_location("dta_core", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    dta = _load_core()
    now = dt.datetime.now()
    today = now.date()
    yesterday = today - dt.timedelta(days=1)
    per = dta.scan_agent_log_range({today.isoformat(), yesterday.isoformat()})

    totals = {}
    models = {}
    for d in (today.isoformat(), yesterday.isoformat()):
        ds_usd, fb_usd = dta.day_split(per.get(d, {}))
        totals[d] = fb_usd
        models[d] = {m: dta.cost_usd(m, t) for m, t in per.get(d, {}).items()
                     if not m.startswith("deepseek") and dta.cost_usd(m, t) > 0}

    worst_day = max(totals, key=lambda k: totals[k])
    worst = totals[worst_day]
    if worst <= THRESHOLD:
        return  # 靜默

    prev = {}
    if STATE.exists():
        try:
            prev = json.loads(STATE.read_text(encoding="utf-8"))
        except ValueError:
            prev = {}
    # 同日去重：除非又累積了「一個門檻」以上的新花費，否則不重複推播
    # （門檻 0.30 → 同日約在 0.30 / 0.60 / 0.90… 各推一次，不會每筆呼叫都吵）
    if prev.get("last_alert_date") == worst_day and worst - float(prev.get("last_amount", -1)) < THRESHOLD:
        return

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "last_alert_date": worst_day,
        "last_amount": round(worst, 4),
        "checked_at": now.isoformat(timespec="seconds"),
        "today_usd": round(totals[today.isoformat()], 4),
        "yesterday_usd": round(totals[yesterday.isoformat()], 4),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    detail = "\n".join(f"   - {m}: US${c:,.3f}" for m, c in
                       sorted(models[worst_day].items(), key=lambda x: -x[1])[:6])
    cer, q429, _ = dta.scan_failures(worst_day)
    lines = [
        f"🔥 備援花費超標：{worst_day} US${worst:.3f}（門檻 US${THRESHOLD:.2f}／天）"
        f" ≈ NT${worst*USD_TWD:,.0f}",
        f"• 今日（至 {now.strftime('%H:%M')}）US${totals[today.isoformat()]:.3f}"
        f" ｜ 昨日全天 US${totals[yesterday.isoformat()]:.3f}",
    ]
    if detail:
        lines.append("• 當日明細（非 DeepSeek 模型）：")
        lines.append(detail)
    lines.append(f"• 當日 DS 內容風控(CER) {cer} 次、Gemini 429 {q429} 次"
                 + ("（CER 換手＝成本外溢主因，檢查 pii-gate/CER 筆數）" if cer else ""))
    lines.append("• 口徑：logs/agent.log 官方現行價自算（非 state.db 快照，該快照低估約 2 倍）")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
