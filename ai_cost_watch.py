#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai_cost_watch.py — AI 費用日/週流量監控 + 儲值追蹤 + 異常偵測（單一入口）

與既有分工的關係（本檔不重複造輪子，數值一律復用 daily_token_account 的解析器）：
  · daily_token_account.py … 每日成本帳（當日 + 近 7 日兩條序列）
  · wallet_status.py ……… 錢包餘額一鍵查（DS balance API + Gemini 探測）
  · fallback_cost_guard.py … 21:10 熔斷（非 DS 當日超標才發）
  · **ai_cost_watch.py（本檔）** … 把上面散落的數字收斂成「可稽核的日序列 + 週平均 + 儲值事件 + 異常判定」

為什麼要有自己的帳本（ledger）：
  agent.log 只保留 4 個檔（agent.log / .1 / .2 / .3），滾動後就算不回舊帳；
  errors.log 同理。所以「週平均」「異常回看」不能每次重掃 log —— 必須落地成日序列。
  → data/ai_cost_daily.jsonl 為本檔的真值帳本（每日一行，upsert，永不刪）。

異常規則（全部集中在 THRESHOLDS，要調只調這裡）：
  A1 單日總花費 ≥ 週中位數 × 3 且 ≥ NT$150（絕對下限，避免小額日誤報）
  A2 DS 內容風控（CER）當日 ≥ 20 次 → 錢正被導去備援
  A3 Gemini 429 當日 ≥ 10 次
  A4 近 7 日總額 ≥ 前 7 日 × 1.5（惡化）
  A5 CER ≥ 5 次卻沒走免費入口（備援全落付費）→ 風控的代價被付費模型吸收
  A6 DS 剩餘天數 < 7（⛔）／< 14（⚠️）
  A7 Gemini 剩餘天數 < 7（⛔）／< 14（⚠️）；探測「確定失效」才 ⛔，暫時性失敗只 ⚠️
  A8 DS 餘額單日上升 ≥ ¥50 → 判定為儲值事件（記入帳本，不當成花費）
  A9 CER 未收斂：連續 ≥ 3 天 或 近 7 日出現 ≥ 5 天 → 風控已常態化，要回頭查 prompt

用法：
  python ai_cost_watch.py                 # 完整報告（近 14 天）
  python ai_cost_watch.py --days 30
  python ai_cost_watch.py --json          # 機器可讀（cron / 其他腳本取用）
  python ai_cost_watch.py --quiet-ok      # watchdog：全正常時完全不輸出（cron 靜默）
  python ai_cost_watch.py --no-probe      # 不打 Gemini 探測（離線 / 省一次呼叫）
  python ai_cost_watch.py --strict-exit   # 有異常時 exit 1（預設 0，見下）
退出碼：預設 0（cron no_agent 以「有沒有輸出」判定要不要送，非 0 會被當執行失敗）；
        加了 --strict-exit 才在 A1~A8 命中時回 1。
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import statistics
import sys
from pathlib import Path

LJ = Path(__file__).resolve().parent
sys.path.insert(0, str(LJ))

LEDGER = LJ / "data" / "ai_cost_daily.jsonl"
COST_CSV = LJ / "cost_log.csv"

THRESHOLDS = {
    "day_spike_ratio": 3.0,      # A1：單日 / 週中位數
    "day_spike_floor_twd": 150,  # A1：絕對下限
    "cer_warn": 20,              # A2
    "cer_streak_warn": 3,        # A9：CER 連續未收斂天數
    "cer_days_warn": 5,          # A9：近 7 日出現 CER 的天數門檻
    "q429_warn": 10,             # A3
    "wow_ratio": 1.5,            # A4
    "cer_min_for_free_check": 5,  # A5：CER 達此數且免費入口 0 次 → 備援全走付費
    "days_critical": 7,          # A6/A7 ⛔
    "days_warn": 14,             # A6/A7 ⚠️
    "topup_jump_cny": 50,        # A8
    "min_days_for_stats": 3,     # 帳本不足時不報週平均/異常（避免假訊號）
}
# 已知限制誠實揭露（避免讀者把推定值當真值）：
#  · Gemini 無餘額 API → 剩餘天數為「儲值 − 逐筆 log 用量」推定值，只用於抓「快見底」的趨勢。
#  · DS 餘額為 API 真值，但日耗是「餘額差」口徑；儲值當日差額為負，已由 A8 排除。
PROBE_CRITICAL = {"depleted", "unauthorized", "no_key"}   # 確定失效，要立刻處理
PROBE_WARN = {"rate_limit", "error", "skipped"}            # 可能只是暫時性，不當阻斷


def _load_dta():
    """以檔案路徑載入 daily_token_account（cron 從別的工作目錄執行也吃 repo 版）。"""
    p = LJ / "daily_token_account.py"
    spec = importlib.util.spec_from_file_location("daily_token_account", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


dta = _load_dta()
USD_TWD = dta.USD_TWD
CNY_TWD = dta.CNY_TWD
to_twd = lambda usd: round(usd * USD_TWD)  # noqa: E731


# ── 帳本 ─────────────────────────────────────────────────────────────
def read_ledger() -> tuple[dict[str, dict], list[str]]:
    """回傳（{date: rec}, 無法解析的原始行）。

    壞行**不丟棄**：原樣保留在回傳值裡，寫回時附在檔尾（2026-09-22 審查指出
    「靜默 continue 會永久丟失歷史」→ 改為保留證據，讓問題現形而不是消失）。
    """
    out: dict[str, dict] = {}
    bad: list[str] = []
    if not LEDGER.exists():
        return out, bad
    for line in LEDGER.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            bad.append(line)
            continue
        if isinstance(rec, dict) and rec.get("date"):
            out[str(rec["date"])] = rec
        else:
            bad.append(line)
    return out, bad


def write_ledger(rows: dict[str, dict], bad: list[str] | None = None) -> None:
    """原子寫（temp + os.replace）：cron 無人環境下中斷不會留下半截檔。"""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(rows[k], ensure_ascii=False, sort_keys=True) for k in sorted(rows)]
    lines += (bad or [])
    tmp = LEDGER.with_name(LEDGER.name + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, LEDGER)


def ds_balance_history() -> dict[str, float]:
    """cost_log.csv → {date: balance_cny}（同日多筆取最後一筆；儲值日會有跳升）。"""
    hist: dict[str, float] = {}
    if not COST_CSV.exists():
        return hist
    import csv as _csv
    for row in _csv.reader(COST_CSV.open(encoding="utf-8")):
        if len(row) < 2 or row[0].strip() == "date":
            continue
        try:
            hist[row[0].strip()] = float(row[1])
        except Exception:
            continue
    return hist


def daily_totals(days: list[str]) -> dict[str, dict]:
    """從 agent.log* 算每日三桶費用（NT$）＋呼叫數。免費層（:free）一律 0。"""
    per_range = dta.scan_agent_log_range(set(days))
    out: dict[str, dict] = {}
    for date, models in per_range.items():
        ds = gem = free = 0.0
        ds_calls = gem_calls = free_calls = 0
        for model, tok in models.items():
            usd = dta.cost_usd(model, tok)
            if model.startswith("deepseek"):
                ds += usd
                ds_calls += tok["calls"]
            elif model.startswith("gemini"):
                gem += usd
                gem_calls += tok["calls"]
            else:
                free += usd
                free_calls += tok["calls"]
        out[date] = {"ds_twd": to_twd(ds), "gemini_twd": to_twd(gem), "free_twd": to_twd(free),
                     "calls": ds_calls + gem_calls + free_calls,
                     "ds_calls": ds_calls, "gemini_calls": gem_calls, "free_calls": free_calls}
    return out


def ds_drain_from_csv(hist: dict[str, float]) -> tuple[float | None, int, str]:
    """DS 真值日耗（CNY）：cost_log.csv 餘額差，只在**連續日曆日**上算。

    為什麼不用 log 估價：本機 log 估價系統性偏低（9/22 實測 log 320 NT$ vs 餘額真值 395 NT$）。
    為什麼只取連續日：中間缺日時，兩筆餘額差是好幾天的耗用，歸給單日會高估；
    且與儲值跳升混在一起會算錯金額（2026-09-22 審查 blocking #3）。
    回傳（平均日耗 CNY, 樣本天數, 視窗說明）。
    """
    dates = sorted(hist)
    drops: list[tuple[str, float]] = []
    for i in range(1, len(dates)):
        try:
            d0 = dt.date.fromisoformat(dates[i - 1])
            d1 = dt.date.fromisoformat(dates[i])
        except Exception:
            continue
        if (d1 - d0).days != 1:      # 缺日 → 無法歸因到單日，不計
            continue
        diff = hist[dates[i - 1]] - hist[dates[i]]
        if diff <= 0:                # 儲值或持平 → 不是耗用
            continue
        drops.append((dates[i], diff))
    if not drops:
        return None, 0, "無連續日樣本"
    cut = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    recent = [x for x in drops if x[0] >= cut]
    window = "最近 7 個日曆日"
    if not recent:                   # 近 7 日內完全沒有可用樣本 → 退回最近 7 筆並誠實標示
        recent, window = drops[-7:], "最近 7 筆可用樣本（非連續 7 日）"
    return sum(x[1] for x in recent) / len(recent), len(recent), window


def scan_cer_day(date: str) -> tuple[int, int]:
    """單日 DS 內容風控（CER）與 Gemini 429 次數。

    刻意**不自己寫一份解析器**：直接呼叫 daily_token_account.scan_failures，
    讓「什麼算一次 CER」的定義只有一處（避免兩份 regex 走鐘）。
    實測單日 0.06s，14 天回填 < 1s，成本可忽略。
    """
    try:
        cer, q429, _errs = dta.scan_failures(date)
        return int(cer), int(q429)
    except Exception:
        return 0, 0


def refresh_ledger(days: list[str], bal_hist: dict[str, float], probe: bool) -> tuple[dict[str, dict], list[str], list[dict]]:
    """把可見日補進帳本。回傳（帳本, 新增日, 被壓下的下修）。

    覆寫規則（2026-09-22 審查 blocking #2）：**單調遞增，只補不減**。
    agent.log / errors.log 只保留 4 個滾動檔，log 滾走後重算值會變 0 或偏低；
    若照抄重算值，歷史會被「今天的視野」污染 → 週平均與 A4 失真。
    故每個計數欄位取 max(原值, 重算值)：log 只會變少、不會變多，取大等於保住真值。

    但「取大」會讓真正的下修（重複計數被修正、解析器修正）永遠進不來（審查第二輪 blocking #2）。
    對策（可稽核，不靠靜默）：
      ① 帳本某日可標 `"pinned": true` → 該日所有值凍結，本腳本不再動它（人工裁決用）。
      ② 非 pinned 且重算值明顯低於已存值時，記入 `corrections` 回報（A10），
         由人類決定要不要 pin 或改帳 —— 分歧一律現形，不靜默吞掉。
    """
    led, bad = read_ledger()
    computed = daily_totals(days)
    today = dt.date.today().isoformat()
    added: list[str] = []
    corrections: list[dict] = []
    COUNTERS = ("ds_twd", "gemini_twd", "free_twd", "calls", "ds_calls", "gemini_calls", "free_calls")
    for date in days:
        c = computed.get(date)
        prev = led.get(date)
        if not c and not prev:
            continue
        base = prev or {"date": date}
        if base.get("pinned"):
            # 人工凍結：只更新最後檢視時間，不動任何數值
            base["last_write"] = today
            led[date] = base
            continue
        if c:
            for k in COUNTERS:
                old = int(base.get(k, 0) or 0)
                new = int(c.get(k, 0) or 0)
                if new < old and (old - new) > max(2, old * 0.1):
                    corrections.append({"date": date, "field": k, "stored": old, "recomputed": new,
                                        "note": "重算值明顯較低（log 滾動或解析修正）；已保留較大值，"
                                                "若確認應下修請把該日標 pinned 或在帳本改值"})
                base[k] = max(old, new)
        if date in bal_hist:
            base.setdefault("ds_balance_cny", bal_hist[date])
        base["log_visible"] = bool(c)          # 該日是否還在 log 視窗內（false = 已滾出，值只能靠帳本）
        base["last_write"] = today
        # CER / 429 逐日（同取大不取小）：全窗口回填，不只今日 —— 使用者要看的正是「這幾天被擋幾次」
        cer, q429 = scan_cer_day(date)
        for k, v in (("cer", cer), ("q429", q429)):
            old = int(base.get(k, 0) or 0)
            if v < old and (old - v) > 5:
                corrections.append({"date": date, "field": k, "stored": old, "recomputed": v,
                                    "note": "風控計數重算值較低（可能原本重複計數）；已保留較大值"})
            base[k] = max(old, v)
        if not prev and c:
            added.append(date)
        led[date] = base
    write_ledger(led, bad)
    return led, added, corrections


# ── 儲值事件 ─────────────────────────────────────────────────────────
def topup_events(led: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """A8：DS 餘額單日上升 ≥ 門檻 = 儲值；Gemini 儲值取自 gemini_cost_log.json。

    只在**連續日曆日**上判定（審查 blocking #3）：帳本缺日時，兩筆餘額差是好幾天的
    合併結果，算出來的儲值金額會錯。但「跳過」不能等於「靜默漏掉」——
    凡跨缺日且餘額是上升的，一律回報成 `待人工確認`（審查第二輪 blocking #1：
    docstring 說會記錄、程式碼沒做）。回傳（(已確認儲值, 待人工確認)）。
    """
    evs: list[dict] = []
    unresolved: list[dict] = []
    dates = sorted(led)
    for i in range(1, len(dates)):
        a, b = led[dates[i - 1]], led[dates[i]]
        ba, bb = a.get("ds_balance_cny"), b.get("ds_balance_cny")
        if not (isinstance(ba, (int, float)) and isinstance(bb, (int, float))):
            continue
        try:
            gap = (dt.date.fromisoformat(dates[i]) - dt.date.fromisoformat(dates[i - 1])).days
        except Exception:
            continue
        if gap != 1:
            # 缺日：無法歸因到單日。若期間餘額是上升的，代表中間有儲值 → 必須現形，不可吞掉
            if bb - ba >= THRESHOLDS["topup_jump_cny"]:
                unresolved.append({"date": dates[i], "wallet": "DeepSeek",
                                   "from": dates[i - 1], "gap_days": gap,
                                   "amount": round(bb - ba, 2), "unit": "CNY",
                                   "twd": round((bb - ba) * CNY_TWD),
                                   "reason": f"{dates[i-1]}→{dates[i]} 中間有 {gap - 1} 天無帳本紀錄，"
                                             f"餘額上升無法歸因到單日，金額僅供參考"})
            continue
        if bb - ba >= THRESHOLDS["topup_jump_cny"]:
            evs.append({"date": dates[i], "wallet": "DeepSeek",
                        "amount": round(bb - ba, 2), "unit": "CNY",
                        "twd": round((bb - ba) * CNY_TWD), "evidence": "cost_log.csv 餘額跳升（連續日）"})
    try:
        gdate, gamt, _h = dta.gemini_topup()
        if gdate and gamt:
            evs.append({"date": gdate, "wallet": "Gemini", "amount": gamt, "unit": "TWD",
                        "twd": gamt, "evidence": "data/gemini_cost_log.json"})
    except Exception:
        pass
    return sorted(evs, key=lambda e: e["date"]), sorted(unresolved, key=lambda e: e["date"])


# ── 主流程 ───────────────────────────────────────────────────────────
def build(days_n: int, probe: bool) -> dict:
    today = dt.date.today()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(days_n)]
    days.reverse()
    bal_hist = ds_balance_history()
    led, added, corrections = refresh_ledger(days, bal_hist, probe)

    series = [led[d] for d in sorted(led) if d in set(days)]
    totals = [int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0)) for r in series]
    complete = [r for r in series if r.get("date") != today.isoformat()]  # 今日未過完，不進統計
    comp_tot = [int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0)) for r in complete]

    last7 = complete[-7:]
    prev7 = complete[-14:-7]
    s7 = sum(int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0)) for r in last7)
    s7p = sum(int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0)) for r in prev7)
    med7 = statistics.median(comp_tot[-7:]) if len(comp_tot) >= THRESHOLDS["min_days_for_stats"] else 0
    ds7 = sum(int(r.get("ds_twd", 0)) for r in last7)
    gem7 = sum(int(r.get("gemini_twd", 0)) for r in last7)
    free7 = sum(int(r.get("free_twd", 0)) for r in last7)

    # ── CER 專區（使用者指定要盯的指標）──────────────────────────────
    cer_series = [{"date": r.get("date"), "cer": int(r.get("cer", 0)), "q429": int(r.get("q429", 0)),
                   "calls": int(r.get("calls", 0)), "gemini_calls": int(r.get("gemini_calls", 0)),
                   "free_calls": int(r.get("free_calls", 0)), "gemini_twd": int(r.get("gemini_twd", 0)),
                   "ds_twd": int(r.get("ds_twd", 0))} for r in complete[-7:]]
    _prior = [{"date": r.get("date"), "cer": int(r.get("cer", 0))} for r in complete[-14:-7]]
    cer7 = sum(x["cer"] for x in cer_series)
    cer7p = sum(x["cer"] for x in _prior)
    # 連續未收斂天數：**在整本帳上算**（帳本只增不刪，故不受 --days 視窗限制）。
    # 並明確標示「是否已回溯到帳本最早一天」——若已到頂，代表真實連續天數可能更長（沒資料可查），
    # 不讓讀者把「≥N」誤讀成「恰好 N」（審查第三輪 blocking #1）。
    streak = 0
    _all_dates = [d for d in sorted(led) if d < today.isoformat()]   # 今日未過完，不列入連續判定
    for i in range(len(_all_dates) - 1, -1, -1):
        rec_i = led[_all_dates[i]]
        if int(rec_i.get("cer", 0) or 0) <= 0:
            break
        if streak > 0:   # 必須是日曆上連續的一天，否則斷開
            try:
                gap = (dt.date.fromisoformat(_all_dates[i + 1]) - dt.date.fromisoformat(_all_dates[i])).days
            except Exception:
                gap = 99
            if gap != 1:
                break
        streak += 1
    streak_capped = bool(_all_dates) and streak == len(_all_dates)
    streak_since = _all_dates[-streak] if streak else None
    cer_days = sum(1 for x in cer_series if x["cer"] > 0)      # 近 7 日有風控的天數
    q429_days = sum(1 for x in cer_series if x["q429"] > 0)
    q429_7 = sum(x["q429"] for x in cer_series)
    # 兩個口徑都給，名稱不騙人（審查第二輪 #4、第三輪 #3）：
    #   · paid_backup_on_cer_days_upper_twd：CER 當日**全部** Gemini 花費 → 是**上限**，不是外溢成本
    #     （無法逐筆歸因：同一天可能有與 CER 無關的正常付費任務）
    #   · spillover_strict_twd：只算「CER ≥ 門檻且免費入口完全沒接手」的日子 → 最接近「風控逼出來的錢」
    gemini_on_cer_days = sum(x["gemini_twd"] for x in cer_series if x["cer"] > 0)
    spillover_strict = sum(x["gemini_twd"] for x in cer_series
                           if x["cer"] >= THRESHOLDS["cer_min_for_free_check"] and x["free_calls"] == 0)

    # 餘額 / 剩餘天數
    ds_bal_cny, ds_src = dta.ds_balance_live()
    if ds_bal_cny is None:
        ds_bal_cny, ds_src = dta.ds_balance_csv()
    ds_days = None
    ds_daily = None
    # 日耗優先用「餘額真值」；樣本不足才退回 log 估價（且標記來源，讀者才知道可信度）
    _ds_drain_cny, _ds_samples, _ds_window = ds_drain_from_csv(bal_hist)
    if _ds_drain_cny:
        ds_daily = round(_ds_drain_cny * CNY_TWD)
        ds_daily_src = f"餘額真值（{_ds_window}，{_ds_samples} 個樣本）"
    elif complete:
        ds_daily = round(sum(int(r.get("ds_twd", 0)) for r in complete[-7:]) / max(1, len(complete[-7:])))
        ds_daily_src = "log 估價（樣本不足，偏低）"
    else:
        ds_daily_src = "無資料"
    if ds_bal_cny is not None and ds_daily:
        ds_days = round(ds_bal_cny * CNY_TWD / ds_daily, 1)

    g_top_date, g_top_amt, _g_hhmm = dta.gemini_topup()
    g_used = g_daily = g_bal = g_days = None
    g_state, g_detail = ("skipped", "未探測") if not probe else dta.gemini_probe()
    try:
        per_all = dta.scan_agent_log_range(set(led))
        if g_top_date:
            g_used = to_twd(dta.gemini_used_since(g_top_date, _g_hhmm, per_all))
            g_bal = max(0, round(g_top_amt - g_used))
            _gseries = [int(r.get("gemini_twd", 0)) for r in complete[-7:]]
            # 用平均而非中位數：中位數在「多數日子為 0、少數日子爆量」時會嚴重低估續航
            g_daily = round(sum(_gseries) / len(_gseries)) if _gseries else 0
            g_days = round(g_bal / g_daily, 1) if g_daily else None
    except Exception:
        pass

    alerts: list[dict] = []
    if len(comp_tot) >= THRESHOLDS["min_days_for_stats"]:
        for r in complete[-7:]:
            t = int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0))
            if med7 and t >= med7 * THRESHOLDS["day_spike_ratio"] and t >= THRESHOLDS["day_spike_floor_twd"]:
                alerts.append({"code": "A1", "level": "warn",
                               "msg": f"{r['date']} 單日 NT${t} ≥ 週中位數 NT${med7:.0f} × {THRESHOLDS['day_spike_ratio']}"})
        if s7p and s7 >= s7p * THRESHOLDS["wow_ratio"]:
            alerts.append({"code": "A4", "level": "warn",
                           "msg": f"近 7 日 NT${s7} ≥ 前 7 日 NT${s7p} × {THRESHOLDS['wow_ratio']}"})
        # A5：CER 發生的日子若備援全走付費（免費入口 0 次）→ 免費層沒接手，花費會被放大
        #     （2026-09-20 修正：舊規則用「免費佔比」判斷，但備援平常根本不啟動 → 佔比本來就接近 0，會天天誤報）
        for r in complete[-7:]:
            if int(r.get("cer", 0)) >= THRESHOLDS["cer_min_for_free_check"] and \
               int(r.get("free_calls", 0)) == 0 and int(r.get("gemini_calls", 0)) > 0:
                alerts.append({"code": "A5", "level": "warn",
                               "msg": f"{r['date']} CER {r.get('cer')} 次但備援全走付費（免費入口 0 次、Gemini {r.get('gemini_calls')} 次）"})
    t_rec = led.get(today.isoformat(), {})
    if int(t_rec.get("cer", 0)) >= THRESHOLDS["cer_warn"]:
        alerts.append({"code": "A2", "level": "warn", "msg": f"今日 DS 內容風控（CER）{t_rec.get('cer')} 次 ≥ {THRESHOLDS['cer_warn']}"})
    if int(t_rec.get("q429", 0)) >= THRESHOLDS["q429_warn"]:
        alerts.append({"code": "A3", "level": "warn", "msg": f"今日 Gemini 429 {t_rec.get('q429')} 次 ≥ {THRESHOLDS['q429_warn']}"})
    if streak >= THRESHOLDS["cer_streak_warn"] or cer_days >= THRESHOLDS["cer_days_warn"]:
        _cap_a9 = "（已回溯到帳本起點，實際可能更長）" if streak_capped else ""
        alerts.append({"code": "A9", "level": "warn",
                       "msg": (f"DS 內容風控（CER）未收斂：連續 {streak} 天{_cap_a9}、近 7 日有 {cer_days}/7 天出現"
                               f"（合計 {cer7} 次）→ 檢查近期 prompt／日報內文是否踩到關鍵詞")})
    _topups, _topup_unresolved = topup_events(led)
    for u in _topup_unresolved:
        alerts.append({"code": "A8", "level": "warn",
                       "msg": (f"儲值無法歸因：{u['from']}→{u['date']} 中間有 {u['gap_days'] - 1} 天無帳本紀錄，"
                               f"餘額上升 {u['amount']} {u['unit']}（≈NT${u['twd']:,}）→ 請人工確認儲值日")})
    if corrections:
        _shown = corrections[:3]
        _more = f"，共 {len(corrections)} 筆" if len(corrections) > len(_shown) else ""
        alerts.append({"code": "A10", "level": "warn",
                       "msg": (f"帳本有『重算值低於已存值』被保留（不靜默下修）："
                               + "、".join(f"{c['date']} {c['field']} {c['stored']}→{c['recomputed']}" for c in _shown)
                               + _more
                               + "｜若確認應下修，用 --pin 凍結該日或直接改帳本值")})
    if ds_days is not None:
        if ds_days < THRESHOLDS["days_critical"]:
            alerts.append({"code": "A6", "level": "critical", "msg": f"DeepSeek 剩餘 {ds_days} 天 < {THRESHOLDS['days_critical']} 天，需立即儲值"})
        elif ds_days < THRESHOLDS["days_warn"]:
            alerts.append({"code": "A6", "level": "warn", "msg": f"DeepSeek 剩餘 {ds_days} 天 < {THRESHOLDS['days_warn']} 天"})
    if g_days is not None:
        if g_days < THRESHOLDS["days_critical"]:
            alerts.append({"code": "A7", "level": "critical", "msg": f"Gemini 推定剩餘 {g_days} 天 < {THRESHOLDS['days_critical']} 天"})
        elif g_days < THRESHOLDS["days_warn"]:
            alerts.append({"code": "A7", "level": "warn", "msg": f"Gemini 推定剩餘 {g_days} 天 < {THRESHOLDS['days_warn']} 天"})
    if probe:
        # 探測失敗要分級（審查 blocking #4）：depleted / unauthorized / no_key 是「確定失效」，
        # rate_limit / error 可能只是暫時性 → 一律列 critical 會天天誤報。
        if g_state in PROBE_CRITICAL:
            alerts.append({"code": "A7", "level": "critical", "msg": f"Gemini 確定失效：{g_state}（{g_detail}）"})
        elif g_state in PROBE_WARN:
            alerts.append({"code": "A7", "level": "warn", "msg": f"Gemini 探測未通過（可能為暫時性）：{g_state}（{g_detail}）"})

    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "days": len(days),
        "ledger_rows": len(led),
        "backfilled": added,
        "series": [{"date": r.get("date"), "ds_twd": int(r.get("ds_twd", 0)),
                    "gemini_twd": int(r.get("gemini_twd", 0)), "free_twd": int(r.get("free_twd", 0)),
                    "total_twd": int(r.get("ds_twd", 0)) + int(r.get("gemini_twd", 0)) + int(r.get("free_twd", 0)),
                    "calls": int(r.get("calls", 0)), "cer": int(r.get("cer", 0)),
                    "q429": int(r.get("q429", 0))} for r in series],
        "today": {"total_twd": totals[-1] if totals else 0,
                  "cer": int(t_rec.get("cer", 0)), "q429": int(t_rec.get("q429", 0))},
        "week": {"last7_total": s7, "last7_daily_avg": round(s7 / max(1, len(last7))),
                 "prev7_total": s7p, "prev7_daily_avg": round(s7p / max(1, len(prev7))),
                 "wow_pct": (round((s7 / s7p - 1) * 100) if s7p else None),
                 "median_day": round(med7), "ds": ds7, "gemini": gem7, "free": free7},
        "wallets": {"ds_balance_cny": ds_bal_cny, "ds_balance_twd": (round(ds_bal_cny * CNY_TWD) if ds_bal_cny is not None else None),
                    "ds_source": ds_src, "ds_daily_twd": ds_daily, "ds_daily_src": ds_daily_src,
                    "ds_days_left": ds_days,
                    "gemini_balance_twd": g_bal, "gemini_daily_twd": g_daily, "gemini_days_left": g_days,
                    "gemini_probe": g_state, "gemini_probe_detail": g_detail,
                    "gemini_topup": {"date": g_top_date, "amount_twd": g_top_amt}},
        "topups": _topups,
        "topups_unresolved": _topup_unresolved,
        "ledger_corrections": corrections,
        "cer": {"today": int(t_rec.get("cer", 0)), "last7_total": cer7, "prev7_total": cer7p,
                "streak_days": streak, "streak_since": streak_since, "streak_capped": streak_capped,
                "days_with_cer": cer_days, "q429_last7": q429_7,
                "days_with_q429": q429_days,
                "spillover_strict_twd": spillover_strict,
                "paid_backup_on_cer_days_upper_twd": gemini_on_cer_days,
                "series": cer_series,
                "note": ("CER＝DeepSeek 內容風控擋下的呼叫數。spillover_strict_twd＝只算「CER ≥ 門檻且免費入口 0 次」的日子"
                         "（推定值，最接近風控逼出來的付費）。paid_backup_on_cer_days_upper_twd＝CER 當日的全部 Gemini 花費"
                         "（僅為上限，含非 CER 任務，不可當成外溢成本）。streak_capped=true 表示已回溯到帳本最早一天，"
                         "真實連續天數可能更長。")},
        "alerts": alerts,
        "governance": _gov_snapshot(),
    }


def _gov_snapshot() -> dict | None:
    """治理後累計（基準日規則見 cost_baseline.py）。讀帳本即可，今日那筆帳本已有。"""
    try:
        from cost_baseline import since_baseline  # noqa: PLC0415
        return since_baseline()
    except Exception:  # noqa: BLE001
        return None


def _gov_line(g: dict | None) -> str:
    if not g:
        return "◆ 治理後累計：未設基準日（跑 set_cost_baseline.py 建立）"
    if g.get("pending"):
        return (f"◆ 治理後累計：基準日 {g['baseline_date'][5:]}（治理修改日）"
                f"→ 自 {g['start_date'][5:]} 00:00 起算（今日不併入）")
    return (f"◆ 治理後累計（自 {g['start_date'][5:]} 起，{g['days']} 天）NT${g['total_twd']:,.0f}"
            f"｜DS NT${g['ds_twd']:,.0f}／Gemini NT${g['gem_twd']:,.0f}"
            f"／免費 {g['free_calls']} 次｜CER {g['cer']} 次｜{g['calls']:,} 次呼叫"
            f"｜基準日前不併入（見 data/cost_baseline.json）")


def render(d: dict) -> str:
    L: list[str] = []
    L.append(f"📡 AI 費用監控　{d['generated_at'][:16].replace('T', ' ')}")
    L.append("─" * 52)
    L.append(f"◆ 今日　NT${d['today']['total_twd']}（進行中）｜CER {d['today']['cer']} ｜429 {d['today']['q429']}")
    L.append(_gov_line(d.get("governance")))
    w = d["week"]
    if w["last7_total"]:
        wow = f"（較前 7 日 {w['wow_pct']:+d}%）" if w["wow_pct"] is not None else ""
        L.append(f"◆ 近 7 日　NT${w['last7_total']}｜日均 NT${w['last7_daily_avg']}{wow}")
        L.append(f"　　DS {w['ds']}／Gemini {w['gemini']}／免費 {w['free']}　週中位數日 NT${w['median_day']}")
        L.append(f"◆ 前 7 日　NT${w['prev7_total']}｜日均 NT${w['prev7_daily_avg']}")
    L.append("")
    L.append("◆ 日序列（NT$）")
    for r in d["series"]:
        bar = "█" * min(30, int(r["total_twd"] / 10))
        flag = " ⚠️" if r["cer"] >= THRESHOLDS["cer_warn"] else ""
        L.append(f"　{r['date'][5:]} {r['total_twd']:>5}  {bar}{flag}")
    L.append("")
    L.append("◆ 錢包")
    wal = d["wallets"]
    ds_bal = f"¥{wal['ds_balance_cny']:.2f} ≈ NT${wal['ds_balance_twd']}" if wal["ds_balance_cny"] is not None else "讀取失敗"
    ds_left = f"{wal['ds_days_left']} 天" if wal["ds_days_left"] is not None else "—"
    mark_ds = "⛔" if (wal["ds_days_left"] or 99) < THRESHOLDS["days_critical"] else ("⚠️" if (wal["ds_days_left"] or 99) < THRESHOLDS["days_warn"] else "✅")
    L.append(f"　DeepSeek　{ds_bal}｜日耗 NT${wal['ds_daily_twd'] or 0}｜剩 {ds_left} {mark_ds}")
    L.append(f"　　日耗來源：{wal.get('ds_daily_src', '')}{'' if '餘額真值' in (wal.get('ds_daily_src') or '') else ' ⚠️推定，續航僅供趨勢參考'}｜餘額來源：{wal['ds_source']}")
    g_left = f"{wal['gemini_days_left']} 天" if wal["gemini_days_left"] is not None else "—"
    mark_g = "⛔" if (wal["gemini_days_left"] or 99) < THRESHOLDS["days_critical"] else ("⚠️" if (wal["gemini_days_left"] or 99) < THRESHOLDS["days_warn"] else "✅")
    L.append(f"　Gemini　　NT${wal['gemini_balance_twd'] or 0}（推定）｜日耗 NT${wal['gemini_daily_twd'] or 0}｜剩 {g_left} {mark_g}｜探測 {wal['gemini_probe']}")
    L.append("")
    L.append("◆ DS 內容風控（CER）")
    c = d["cer"]
    trend = ""
    if c["prev7_total"]:
        trend = f"（前 7 日 {c['prev7_total']}）"
    else:
        trend = "（前 7 日無紀錄）"
    _cap = "（可能更長，已回溯到帳本起點）" if c.get("streak_capped") else ""
    L.append(f"　今日 {c['today']} 次｜近 7 日 {c['last7_total']} 次{trend}｜出現 {c['days_with_cer']}/7 天｜連續未收斂 {c['streak_days']} 天{_cap}")
    L.append(f"　風控外溢成本（推定）NT${c['spillover_strict_twd']}（只算 CER≥{THRESHOLDS['cer_min_for_free_check']} 且免費入口 0 次的日子）")
    L.append(f"　上限值 NT${c['paid_backup_on_cer_days_upper_twd']}（CER 當日 Gemini 全部花費，含非 CER 任務，非外溢）")
    if c["series"]:
        parts = "｜".join(f"{x['date'][5:]} {x['cer']}" for x in c["series"])
        L.append(f"　CER 逐日：{parts}")
    if c["q429_last7"]:
        parts = "｜".join(f"{x['date'][5:]} {x['q429']}" for x in c["series"] if x["q429"])
        L.append(f"　429 逐日：{parts}（合計 {c['q429_last7']}）")
    L.append("")
    L.append("◆ 儲值事件（近 14 日）")
    if d["topups"]:
        for e in d["topups"]:
            unit = f"{e['amount']:,.0f} {e['unit']}"
            L.append(f"　{e['date']}　{e['wallet']}　+{unit}（≈NT${e['twd']:,}）｜{e['evidence']}")
    else:
        L.append("　（無）")
    for u in d.get("topups_unresolved", []):
        L.append(f"　🟡 待人工確認：{u['from']}→{u['date']} 中間缺 {u['gap_days'] - 1} 天帳本，餘額升 {u['amount']} {u['unit']}（≈NT${u['twd']:,}）")
    L.append("")
    if d["alerts"]:
        L.append(f"◆ 異常 {len(d['alerts'])} 項")
        for a in d["alerts"]:
            icon = "⛔" if a["level"] == "critical" else "⚠️"
            L.append(f"　{icon} [{a['code']}] {a['msg']}")
    else:
        L.append("◆ 異常：無 ✅")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="AI 費用日/週流量監控 + 儲值追蹤 + 異常偵測")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet-ok", action="store_true", help="無異常時完全不輸出（cron watchdog）")
    ap.add_argument("--no-probe", action="store_true", help="不打 Gemini 探測呼叫")
    ap.add_argument("--strict-exit", action="store_true", help="有異常時回傳 1（預設永遠 0）")
    ap.add_argument("--pin", metavar="DATE", help="把某日帳本標為人工凍結（YYYY-MM-DD）：數值不再被本腳本改動")
    ap.add_argument("--unpin", metavar="DATE", help="解除某日的人工凍結")
    a = ap.parse_args()

    if a.pin or a.unpin:
        # 讓「下修／凍結」有支援的入口，不必手改 JSON（審查第三輪 blocking #2）
        date = a.pin or a.unpin
        try:  # 先驗格式，避免把 typo 當成一個新日期寫進帳本（審查第四輪建議）
            _d = dt.date.fromisoformat(date)
            if _d.isoformat() != date:
                raise ValueError("需為 YYYY-MM-DD")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ 日期格式錯誤：{date!r}（{exc}）→ 請用 YYYY-MM-DD")
            return 1
        led, bad = read_ledger()
        if date not in led:
            print(f"❌ 帳本沒有 {date}（現有 {len(led)} 天：{min(led, default='-')} ~ {max(led, default='-')}）")
            return 1
        led[date]["pinned"] = bool(a.pin)
        led[date]["last_write"] = dt.date.today().isoformat()
        write_ledger(led, bad)
        print(f"{'🔒 已凍結' if a.pin else '🔓 已解除凍結'} {date}｜值："
              f"DS {led[date].get('ds_twd')}／Gemini {led[date].get('gemini_twd')}／CER {led[date].get('cer')}")
        return 0

    d = build(a.days, probe=not a.no_probe)
    if a.json:
        print(json.dumps(d, ensure_ascii=False, indent=2))
    elif not (a.quiet_ok and not d["alerts"]):
        print(render(d))
    return 1 if (a.strict_exit and d["alerts"]) else 0


if __name__ == "__main__":
    sys.exit(main())
