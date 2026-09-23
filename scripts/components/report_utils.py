#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_utils.py — 日報輔助函數庫（從 run_daily.py 拆分）"""
from datetime import date, datetime, timedelta

def _fmt_rent_status(tv: dict) -> str:
    """房租金流：**當月應收**（含一次性調整）＋ 動態追蹤已收/待收。

    2026-09-23 INC-241b：原以常態 80,100 為分母相減（`pending = 80_100 - _got`）→ 一次性折讓
    （2026-09 洲際W 維修費 3,000）會變成幽靈待收（日報顯示待收 26,100，真值 23,100）；
    且 fallback 字串把「大義街23樓23,100＋管理費2,100」重複計。改讀
    `tv["rent_receivable_by_month"][本月]`（缺 → fallback `rent_breakdown`），不再寫死數字。
    """
    _m = date.today().strftime("%Y-%m")
    _rb_all = tv.get("rent_receivable_by_month", {}) or {}
    rb = _rb_all.get(_m) or tv.get("rent_breakdown", {}) or {}
    received = tv.get("rent_received_records", {}) or {}
    _got = sum(v for d, items in received.items() if str(d).startswith(_m) for v in items.values())
    label_map = {"大義街店面": "大義街1樓", "大義街二三樓": "大義街23樓"}
    detail = [f"{label_map.get(k, k)}{v:,}" for k, v in rb.items()]
    if not detail:
        return "（snapshot 缺 rent_receivable_by_month / rent_breakdown，無法列出租金明細）"
    _due = sum(rb.values())
    base = f"當月應收 {_due:,} = " + "+".join(detail)
    if _got > 0:
        got_parts = [f"{label_map.get(k, k)}{v:,}"
                     for d, items in sorted(received.items())
                     if str(d).startswith(_m) for k, v in items.items()]
        pending = max(0, _due - _got)
        return f"{base}｜已收 {'+'.join(got_parts)}（{_got:,}）｜待收 {pending:,}"
    return f"{base}｜尚未入帳"

def _generate_schedule_html(events: list) -> str:
    """從 calendar_sync 事件生成排程 HTML 表格行"""
    from datetime import date
    today = date.today().isoformat()
    rows = []
    for ev in events:
        start = ev.get("start", "")
        if start < today:
            continue
        summary = ev.get("summary", "")
        amount = ev.get("amount", "")
        status = ev.get("status", "")
        rows.append(f'<tr><td>{start}</td><td>{summary}</td><td class="num">{amount}</td><td>{status}</td></tr>')
    return "\n".join(rows[:12])
