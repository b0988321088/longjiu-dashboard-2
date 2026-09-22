#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_baseline.py — 「治理後累計」的起算點（單一真值模組）。

為何需要（2026-09-22 使用者指示「從修改完再開始統計比較準確」）：
  9/13、9/16、9/17、9/20 的 CER 風暴把累計數字污染（累計 517 次 CER、Gemini 9 月
  NT$1,045 裡大半來自當時「CER → 備援全價代答」），與治理後的常態不同量級。
  把兩段混在同一個「累計」裡會誤導判斷 → 分開算，不刪歷史。

規則：
  · 基準日＝完成修改當天（`data/cost_baseline.json` 的 `baseline_date`）。
  · 累計從基準日的**隔日 00:00** 起算。基準日本身仍含當天修改前的部分，整日剔除最乾淨
    （避免半天混算成「治理後」）。
  · 每日帳本 `data/ai_cost_daily.jsonl`（由 ai_cost_watch.py 維護、永不刪）是唯一來源；
    今日尚未入帳本 → 用呼叫端傳入的即時值。
  · 基準日之前的數字不刪，只是不併入「治理後累計」。

用法：
    from cost_baseline import since_baseline
    acc = since_baseline(live_today)   # live_today 可省略
    if acc and acc["pending"]: ...     # 還在基準日，尚未開始累計
    elif acc: ...                      # acc["days"]/["ds_twd"]/["gem_twd"]/["free_calls"]/["cer"]
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
BASELINE = LJ / "data" / "cost_baseline.json"
LEDGER = LJ / "data" / "ai_cost_daily.jsonl"
DS_LOG = LJ / "cost_log.csv"


def load() -> dict | None:
    """讀基準日檔；不存在或壞掉回 None（呼叫端據此完全不顯示累計行）。"""
    try:
        d = json.loads(BASELINE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and d.get("baseline_date") else None
    except Exception:  # noqa: BLE001
        return None


def start_date(base: dict) -> str:
    """累計起始日＝基準日隔天（ISO 字串）。"""
    d = dt.date.fromisoformat(str(base["baseline_date"]))
    return (d + dt.timedelta(days=1)).isoformat()


def _ledger_rows() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not LEDGER.exists():
        return out
    try:
        for line in LEDGER.open(encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(r, dict) and r.get("date"):
                out[str(r["date"])] = r
    except Exception:  # noqa: BLE001
        return out
    return out


def since_baseline(live_today: dict | None = None) -> dict | None:
    """回傳「治理後累計」。無基準日檔 → None；還在基準日 → pending=True。

    live_today 鍵（可缺，缺視為 0）：date / ds_twd / gem_twd / free_twd / free_calls / cer / calls
    """
    base = load()
    if not base:
        return None
    s_date = start_date(base)
    today = str((live_today or {}).get("date") or dt.date.today().isoformat())

    rows = _ledger_rows()
    acc = {"baseline_date": base["baseline_date"], "start_date": s_date,
           "days": 0, "ds_twd": 0.0, "gem_twd": 0.0, "free_twd": 0.0,
           "free_calls": 0, "calls": 0, "cer": 0, "pending": True}
    if today < s_date:
        acc["days_until_start"] = (dt.date.fromisoformat(s_date) - dt.date.fromisoformat(today)).days
        return acc

    seen: set[str] = set()
    for date, r in rows.items():
        # 今日：呼叫端有給即時值 → 用即時值（避免同日重複計）；沒給 → 用帳本今日那筆
        if date < s_date or (date == today and live_today is not None):
            continue
        seen.add(date)
        acc["ds_twd"] += float(r.get("ds_twd") or 0)
        acc["gem_twd"] += float(r.get("gemini_twd") or 0)
        acc["free_twd"] += float(r.get("free_twd") or 0)
        acc["free_calls"] += int(r.get("free_calls") or 0)
        acc["calls"] += int(r.get("calls") or 0)
        acc["cer"] += int(r.get("cer") or 0)

    if live_today:
        seen.add(today)
        acc["ds_twd"] += float(live_today.get("ds_twd") or 0)
        acc["gem_twd"] += float(live_today.get("gem_twd") or 0)
        acc["free_twd"] += float(live_today.get("free_twd") or 0)
        acc["free_calls"] += int(live_today.get("free_calls") or 0)
        acc["calls"] += int(live_today.get("calls") or 0)
        acc["cer"] += int(live_today.get("cer") or 0)

    acc["days"] = len(seen)
    acc["pending"] = False
    acc["total_twd"] = acc["ds_twd"] + acc["gem_twd"] + acc["free_twd"]
    return acc


def ds_true_spend_since_baseline(balance_cny: float | None = None) -> dict | None:
    """DeepSeek 真值花費（基準日餘額 − 現餘額，CNY）。餘額 API 失敗回 None。"""
    base = load()
    if not base or base.get("ds_balance_cny") is None or balance_cny is None:
        return None
    try:
        b0 = float(base["ds_balance_cny"])
        spent = b0 - float(balance_cny)
    except (TypeError, ValueError):
        return None
    return {"baseline_cny": b0, "now_cny": float(balance_cny), "spent_cny": spent,
            "note": "含儲值；若期間已儲值則為負或失真，改看帳本欄位"}


def prior_totals(baseline_date: str | None = None) -> dict:
    """基準日（含）之前的歷史（僅供說明「為何剔除」，不參與累計）。

    baseline_date 可顯式傳入 —— 建立基準日當下檔案還不存在/還是舊值，靠檔案讀不到當次日期。
    """
    base = load() or {}
    b = str(baseline_date or base.get("baseline_date") or "")
    days = _ledger_rows()
    kept = {d: r for d, r in days.items() if b and d <= b}
    return {"days": len(kept), "cer": sum(int(r.get("cer") or 0) for r in kept.values()),
            "ds_twd": sum(float(r.get("ds_twd") or 0) for r in kept.values()),
            "gem_twd": sum(float(r.get("gemini_twd") or 0) for r in kept.values())}


def ds_topup_history() -> list[dict]:
    """cost_log.csv 的餘額跳升＝儲值事件（供基準日快照記錄）。"""
    out: list[dict] = []
    try:
        rows = [r for r in csv.reader(DS_LOG.open(encoding="utf-8-sig")) if r and r[0].strip()]
    except Exception:  # noqa: BLE001
        return out
    prev = None
    for r in rows[1:]:
        if len(r) < 2:
            continue
        try:
            bal = float(r[1])
        except ValueError:
            continue
        if prev is not None and bal > prev + 0.5:
            out.append({"date": r[0], "added_cny": round(bal - prev, 2), "to_cny": bal})
        prev = bal
    return out


if __name__ == "__main__":
    b = load()
    if not b:
        print("尚未設定基準日（跑 set_cost_baseline.py 建立）")
    else:
        print(json.dumps({"baseline": b, "since_baseline": since_baseline(),
                          "excluded_history": prior_totals(),
                          "ds_topups": ds_topup_history()},
                         ensure_ascii=False, indent=2))
