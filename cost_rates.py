#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_rates.py — 日耗（¥/NT$ per day）口徑的單一真值。

為什麼要有這支（2026-09-22 使用者核准統一）：
  三支費用腳本過去各算各的，同一時刻給出三個不同日耗 ——
    daily_token_account：log 估價中位數 ¥8.3 → 11.4 天
    wallet_status      ：cost_log.csv 中位數 ¥9.1 → 10.4 天
    ai_cost_watch      ：餘額真值均值   ¥11.6 → 8.0 天
  剩餘天數跟著差 1.2 倍，同一顆錢包會有兩種結論（一個 ⚠️、一個 ⛔）。本檔是唯一實作，
  三支腳本一律呼叫這裡。

口徑（2026-09-22 定案）：
  · DS：`cost_log.csv` 的**餘額真值**。相鄰**連續日曆日**的餘額差、只取正差（儲值跳升不算耗用），
    視窗＝最近 7 個日曆日，取**平均**（非中位數：中位數會把 CER 尖峰日當雜訊丟掉）。
    近 7 日完全沒有可用樣本 → 退回最近 7 筆可用樣本，並在 window 欄誠實標示。
    為何不用 log 估價：本機 log 系統性偏低（2026-09-22 實測 log NT$320 vs 餘額真值 NT$395）。
  · Gemini：預付制、無餘額 API → log 口徑，取最近 7 個**完整日**（不含今日，今日未過完）的**平均**。
    為何平均不用中位數：多數日子為 0、少數日子爆量時，中位數會嚴重低估續航。

回傳值一律附口徑說明，讓下游可以直接顯示（不許自己再算一次）。
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
COST_CSV = LJ / "cost_log.csv"
CNY_TWD = 4.73          # 2026-09-14 使用者確認（與 daily_token_account 同值）
USD_TWD = 31.7
DS_WINDOW_DAYS = 7      # DS：最近 N 個日曆日
GEMINI_WINDOW_DAYS = 7  # Gemini：最近 N 個完整日


def balance_history() -> dict[str, float]:
    """cost_log.csv → {date: balance_cny}（同日多筆取最後一筆；儲值日會有跳升）。"""
    hist: dict[str, float] = {}
    if not COST_CSV.exists():
        return hist
    with COST_CSV.open(encoding="utf-8-sig") as fh:
        for row in csv.reader(fh):
            if len(row) < 2 or row[0].strip() in ("", "date"):
                continue
            try:
                hist[row[0].strip()] = float(row[1])
            except ValueError:
                continue
    return hist


def ds_burn(window_days: int = DS_WINDOW_DAYS) -> dict:
    """DS 真值日耗（CNY）。回傳 {rate_cny, rate_twd, samples, window, ok}。"""
    hist = balance_history()
    dates = sorted(hist)
    drops: list[tuple[str, float]] = []
    for i in range(1, len(dates)):
        try:
            d0, d1 = dt.date.fromisoformat(dates[i - 1]), dt.date.fromisoformat(dates[i])
        except ValueError:
            continue
        if (d1 - d0).days != 1:      # 缺日 → 差額是好幾天的耗用，歸單日會高估
            continue
        diff = hist[dates[i - 1]] - hist[dates[i]]
        if diff <= 0:                # 儲值或持平 → 不是耗用
            continue
        drops.append((dates[i], diff))
    if not drops:
        return {"rate_cny": None, "rate_twd": None, "samples": 0,
                "window": "無連續日樣本", "ok": False}
    cut = (dt.date.today() - dt.timedelta(days=window_days)).isoformat()
    recent = [x for x in drops if x[0] >= cut]
    window = f"最近 {window_days} 個日曆日"
    if not recent:                   # 近 N 日沒樣本 → 退回最近 N 筆並誠實標示
        recent, window = drops[-window_days:], f"最近 {window_days} 筆可用樣本（非連續日，退化口徑）"
    rate = sum(x[1] for x in recent) / len(recent)
    return {"rate_cny": rate, "rate_twd": rate * CNY_TWD, "samples": len(recent),
            "window": window, "ok": True}


def _log_scan(days: set[str]) -> dict:
    """延遲載入 daily_token_account 取用它的 log 掃描與定價（避免循環匯入）。"""
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("daily_token_account", LJ / "daily_token_account.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.scan_agent_log_range(days)


def gemini_burn(window_days: int = GEMINI_WINDOW_DAYS, scan=None) -> dict:
    """Gemini 日耗（NT$）：最近 N 個完整日（不含今日）的 log 口徑平均。

    回傳 {rate_twd, samples, window, series, ok}。scan 可注入（測試用），預設自己掃 log。
    """
    today = dt.date.today()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(window_days, 0, -1)]
    try:
        per_range = scan(set(days)) if scan else _log_scan(set(days))
    except Exception as exc:  # noqa: BLE001
        return {"rate_twd": None, "samples": 0, "window": f"log 掃描失敗（{type(exc).__name__}）",
                "series": [], "ok": False}
    # daily_token_account 的每日分桶：Σ gemini 模型成本 × 匯率
    import importlib.util  # noqa: PLC0415

    spec = importlib.util.spec_from_file_location("daily_token_account", LJ / "daily_token_account.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    series: list[float] = []
    for d in days:
        models = (per_range or {}).get(d, {})
        gem = sum(mod.cost_usd(m, tok) for m, tok in models.items() if m.startswith("gemini"))
        series.append(gem * USD_TWD)
    if not series:
        return {"rate_twd": None, "samples": 0, "window": "無 log 樣本", "series": [], "ok": False}
    return {"rate_twd": sum(series) / len(series), "samples": len(series),
            "window": f"最近 {window_days} 個完整日（{days[0][5:]}~{days[-1][5:]}）",
            "series": series, "ok": True}


if __name__ == "__main__":
    import json

    print(json.dumps({"ds": ds_burn(), "gemini": gemini_burn()}, ensure_ascii=False, indent=1))
