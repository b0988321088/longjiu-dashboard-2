#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""到期與待辦行動提醒（2026-11-25 使用者核准 08:10 版）

設計原則（使用者裁決）：
1. **有期限才有提醒**：T-3 起每天出現、當天標「今天最後一天」、逾期標 OVERDUE 每天出現。
2. **四要素**：是什麼／要你做什麼／金額或影響／不做的後果。缺一項就不算合格提醒。
3. **零噪音**：當日無 T-window 內項目 → 完全不輸出（cron 靜默）。
4. **單一真值**：只讀 data/weekly_open_items.json、pending_decisions.json、
   schedule_events.json、snapshot.policy_conversion_plan_*，不自行生成待辦。

用法：
    python action_reminder.py --dry-run            # 看今天會推什麼
    python action_reminder.py --today 2026-12-01   # 模擬某天
    python action_reminder.py                      # 給 cron 用（無事項則無輸出）
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
OEI = BASE / "data" / "weekly_open_items.json"
PD = BASE / "pending_decisions.json"
EV = BASE / "schedule_events.json"
SNAP = BASE / "snapshot.json"

_WEEK = "一二三四五六日"
_DATE_PATTERNS = [
    (re.compile(r"(\d{4})-(\d{2})-(\d{2})"), "ymd"),
    (re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})"), "ymd"),
    (re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)"), "md"),
]


def _today() -> date:
    return datetime.now().date()


def _parse_dates(text: str, ref: date) -> list[date]:
    """從任意字串抓日期。'12/08' 這種省略年份的，一律落在 ref 當年，
    若已明顯過期（>180 天前）則視為明年。"""
    out: list[date] = []
    s = str(text or "")
    for pat, kind in _DATE_PATTERNS:
        for m in pat.finditer(s):
            try:
                if kind == "ymd":
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                else:
                    mo, dd = int(m.group(1)), int(m.group(2))
                    d = date(ref.year, mo, dd)
                    if (ref - d).days > 180:
                        d = date(ref.year + 1, mo, dd)
                out.append(d)
            except ValueError:
                continue
    return sorted(set(out))


def _nearest_due(texts: list[str], ref: date) -> date | None:
    """取「最近且尚未超過 60 天」的到期日：優先未來，其次最近過期。"""
    ds = _parse_dates(" ".join(str(t or "") for t in texts), ref)
    if not ds:
        return None
    future = [d for d in ds if d >= ref - timedelta(days=60)]
    return future[0] if future else ds[-1]


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _items_open_items(ref: date) -> list[dict]:
    d = _load(OEI, {}) or {}
    rows = []
    for it in d.get("items") or []:
        if str(it.get("status", "")).upper() not in ("OPEN", "WAIT", "WATCH", "PENDING"):
            continue
        due_txt = it.get("due")
        due = _nearest_due([due_txt], ref) if due_txt and due_txt != "—" else None
        rows.append({
            "key": it.get("id"),
            "what": f"{it.get('id')} {it.get('title')}",
            "todo": it.get("action") or "",
            "impact": "｜".join(f"{k}：{v}" for k, v in (it.get("metric") or {}).items()),
            "no_due_ok": isinstance(due_txt, str) and due_txt.startswith("解凍日"),
            "due": due,
            "close_cond": it.get("close_cond") or "",
            "owner": it.get("owner") or "",
            "src": "weekly_open_items",
        })
    return rows


def _items_pending(ref: date) -> list[dict]:
    d = _load(PD, [])
    arr = d if isinstance(d, list) else (d.get("items") or [])
    rows = []
    for i, it in enumerate(arr):
        if "待處理" not in str(it.get("status", "")):
            continue
        # 2026-11-25 修正：pending_decisions 的 date 是「立案日」不是到期日。
        # 只接受**未來**日期（如『12/05 複核』），過去日期一律不當到期 → 避免 OVERDUE 假警報。
        _raw = it.get("due") or _nearest_due(
            [it.get("status_raw"), it.get("detail"), it.get("title")], ref)
        _cands = _parse_dates(str(it.get("status_raw") or "") + " " + str(it.get("detail") or ""), ref)
        _fut = [d for d in _cands if d >= ref]
        due = _fut[0] if _fut else None
        rows.append({
            "key": f"PD-{i + 1}",
            "what": _clean(str(it.get("title") or ""), 70),
            "todo": _clean(str(it.get("status_raw") or ""), 100) or "依 detail 執行",
            "impact": _clean(str(it.get("detail") or ""), 100),
            "no_due_ok": False,
            "due": due if isinstance(due, date) else None,
            "close_cond": "",
            "owner": "使用者（裁決）",
            "src": "pending_decisions",
        })
    return rows


def _items_events(ref: date) -> list[dict]:
    d = _load(EV, [])
    arr = d if isinstance(d, list) else (d.get("events") or [])
    rows = []
    for it in arr:
        if "需動作" not in str(it.get("status", "")):
            continue
        due = _nearest_due([it.get("date")], ref)
        if not due:
            continue
        rows.append({
            "key": f"EV {due.isoformat()}",
            "what": str(it.get("title") or it.get("item") or ""),
            "todo": str(it.get("status") or ""),
            "impact": str(it.get("note") or "")[:160],
            "no_due_ok": False,
            "due": due,
            "close_cond": "",
            "owner": "使用者",
            "src": "schedule_events",
        })
    return rows


def _items_conversion(ref: date) -> list[dict]:
    """保單轉換／配置類：從 policy card 推出「最遲送件日」。
    2026-11-25 使用者指出的缺口：「系統都不提醒我去做轉換跟配置」——
    轉換案的截止不是行事曆事件，而是 T+4 回推出來的送件日，必須自己算。"""
    snap = _load(SNAP, {}) or {}
    rows = []
    for k, card in snap.items():
        if not str(k).startswith("policy_conversion_plan") or not isinstance(card, dict):
            continue
        tgt = card.get("轉入") or {}
        ex_txt = str(tgt.get("除息日") or "")
        ex = _parse_dates(ex_txt, ref)
        ex = [d for d in ex if d >= ref][:1]
        if not ex:
            continue
        # T+4 生效 + 2 個工作日緩衝 → 送件最遲 = 除息日 - 6 日曆日（估算，報告須標「估」）
        send_by = ex[0] - timedelta(days=6)
        rows.append({
            "key": f"CV-{str(k)[-8:]}",
            "what": f"保單轉換送件（{card.get('版本', '')}）：{tgt.get('摩根 USDEQ5440') and '摩根 USDEQ5440' or '轉入標的'}"
                    f"｜除息 {ex[0].month}/{ex[0].day:02d}",
            "todo": "定案單一案＋金額＋送件日；未定案不得送件",
            "impact": f"最遲送件日（估）{send_by.month}/{send_by.day:02d}＝除息前 6 天（T+4＋工作日緩衝）",
            "no_due_ok": False,
            "due": send_by,
            "close_cond": "",
            "owner": "使用者（裁決）／龍九（跟催）",
            "src": "policy_conversion_plan",
        })
    return rows


def _win_for(r: dict, default: int) -> int:
    """轉換／送件類要提前看到（準備需要時間）；行事曆事件用預設 3 天。"""
    return 7 if r.get("src") == "policy_conversion_plan" else default


def _clean(t: str, n: int) -> str:
    """去掉裁決出處括號等雜訊後截斷，避免提醒變成一坨內文。"""
    t = re.sub(r"（CIO[^）]*）|（使用者裁決[^）]*）|（[0-9]{4}-[0-9]{2}-[0-9]{2}[^）]*）", "", str(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return (t[:n] + "…") if len(t) > n else t


def _fmt_row(r: dict, ref: date, is_monday: bool, window: int = 3) -> str | None:
    due = r.get("due")
    if due is None:
        if not (is_monday and r.get("no_due_ok") is False):
            return None
        head = "🟦 無固定期限（每週一提示一次）"
    else:
        delta = (due - ref).days
        if delta < 0:
            head = f"⛔ OVERDUE {abs(delta)} 天｜原定 {due.month}/{due.day:02d}"
        elif delta == 0:
            head = f"🔴 今天是最後一天（{due.month}/{due.day:02d}）"
        elif delta <= _win_for(r, window):
            head = f"🟡 T-{delta}｜{due.month}/{due.day:02d}（週{_WEEK[due.weekday()]}）"
        else:
            return None
    lines = [f"{head}｜{r['what']}"]
    if r.get("todo"):
        lines.append(f"　· 做什麼：{r['todo']}")
    if r.get("impact"):
        lines.append(f"　· 影響／金額：{r['impact']}")
    if r.get("close_cond"):
        lines.append(f"　· 收法：{r['close_cond']}")
    lines.append(f"　· 不做：狀態維持待處理，逾期後每天出現直到你回覆或作廢（owner：{r.get('owner') or '—'}）")
    return "\n".join(lines)


def build(ref: date, window: int = 3) -> str:
    rows = (_items_open_items(ref) + _items_pending(ref)
            + _items_events(ref) + _items_conversion(ref))
    is_monday = ref.weekday() == 0
    blocks, keys = [], []
    for r in rows:
        txt = _fmt_row(r, ref, is_monday, window)
        if txt:
            blocks.append(txt)
            keys.append(str(r.get("key")))
    if not blocks:
        return ""
    title = f"🗓️ 龍九行動提醒（{ref.month}/{ref.day:02d} 週{_WEEK[ref.weekday()]}）"
    tail = [
        "",
        "回覆方式（回一個就好，我會落庫並關卡）：",
        "　✅ <編號> 已處理　｜　延後 <編號> 7天　｜　作廢 <編號>",
        f"　本則涵蓋：{'、'.join(keys)}",
    ]
    return "\n".join([title, ""] + blocks + tail)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None, help="YYYY-MM-DD（預設系統日）")
    ap.add_argument("--window", type=int, default=3, help="提前幾天開始提醒（預設 3）")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    ref = date.fromisoformat(a.today) if a.today else _today()
    out = build(ref, a.window)
    if not out:
        if a.dry_run:
            print(f"[{ref}] 無 T-{a.window} 內到期項目 → 靜默（不推播）")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
