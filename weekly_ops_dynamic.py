#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本週操作執行紀錄／閉環待追蹤 — 由 schedule_events 動態推導（2026-09-30）。

問題（使用者 9/30 反映）：日報與 Buffett/CTO 推播長期顯示「本週操作執行紀錄（2026-09-08 ~ 09-13）」
與已完成的閉環待追蹤（⏳ 9/16 保單轉換、⏳ 質押撥款 540萬 估10/5）。
根因：該區塊讀 snapshot.weekly_ops_closure_* 最新一筆（字串排序 = 0913），
而 9/14 之後沒有人再寫新的一筆 —— 資料源停住，產生器再動態也救不了。

修法：改由 schedule_events.json（唯一有人在維護的操作來源）推導：
  · 執行清單 ＝ 期間內 status 含 ✅ 的項目（近窗 7 天）
  · 閉環待追蹤 ＝ 未完成狀態（⏳／📌／🔴／🔄）且日期 ≥ 今日；日期已過仍未完者標 ⚠️ 逾期
snapshot.weekly_ops_closure_* 只當退路（schedule_events 取不到資料時）。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent
DONE = "✅"
PENDING = ("⏳", "📌", "🔴", "🔄", "⛔")
WINDOW_DAYS = 7
MAX_DONE = 8
MAX_PENDING = 6


def _events(base: Path | None = None) -> list[dict]:
    p = (base or REPO) / "schedule_events.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else data.get("events", [])
    return [x for x in items if isinstance(x, dict) and str(x.get("date", "")).strip()]


def _d(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def build(base: Path | None = None, today: str | None = None, window_days: int = WINDOW_DAYS) -> dict:
    """回傳 {期間, 狀態, 執行清單, 閉環:{決策紀錄, 待追蹤}, 來源}。取不到資料回傳 {}。"""
    items = _events(base)
    if not items:
        return {}
    t = date.fromisoformat(today) if today else date.today()
    d0 = t - timedelta(days=window_days)
    done, pend, overdue = [], [], []
    for x in items:
        d = _d(x.get("date"))
        if d is None:
            continue
        st = str(x.get("status", ""))
        title = str(x.get("item", "")).strip()
        if DONE in st:
            if d0 <= d <= t:
                done.append((d, {"項目": title, "狀態": st, "金額": str(x.get("amount") or "—")}))
        elif d >= t and (any(m in st for m in PENDING) or not st):
            pend.append((d, f"{title}（{d.isoformat()}）"))
        elif d < t and "⏳" in st:
            # 只有明確標「待入帳／待完成」的過去項目才列逾期，避免把歷史註記（除息/T+4 截止）全部掃成逾期
            pend.append((d, f"⚠️ 逾期未完成：{title}（原定 {d.isoformat()}）"))
    done.sort(key=lambda z: z[0])
    list_done = [v for _, v in done][-MAX_DONE:]
    for _it in list_done:
        _t = str(_it.get("項目", ""))
        if len(_t) > 72:
            _it["項目"] = _t[:72] + "…"
    tail = ["⏳ " + v for _, v in sorted(pend, key=lambda z: z[0]) if not v.startswith("⚠️")]
    tail += [v for _, v in sorted(pend, key=lambda z: z[0]) if v.startswith("⚠️")]
    if not list_done and not tail:
        return {}
    return {
        "期間": f"{d0.isoformat()} ~ {t.isoformat()}",
        "狀態": f"✅ 近期操作 {len(list_done)} 項完成" + (f"、待追蹤 {min(len(tail), MAX_PENDING)} 項" if tail else ""),
        "執行清單": list_done,
        "閉環": {"決策紀錄": "✅ 由 schedule_events 動態推導（單一來源）", "待追蹤": tail[:MAX_PENDING]},
        "來源": "schedule_events（動態推導）",
    }


def fallback(base: Path | None = None) -> dict:
    """退路：snapshot.weekly_ops_closure_* 最新一筆（人工維護版）。"""
    p = (base or REPO) / "snapshot.json"
    if not p.exists():
        return {}
    snap = json.loads(p.read_text(encoding="utf-8"))
    keys = sorted([k for k in snap.keys() if str(k).startswith("weekly_ops_closure_")])
    return snap.get(keys[-1], {}) if keys else {}


def build_or_fallback(base: Path | None = None, today: str | None = None) -> dict:
    d = build(base, today)
    return d if (d and d.get("執行清單")) else fallback(base)


if __name__ == "__main__":
    print(json.dumps(build_or_fallback(), ensure_ascii=False, indent=2))
