#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_utils.py — 日報輔助函數庫（從 run_daily.py 拆分）"""
from datetime import date, datetime, timedelta

def _fmt_rent_status(tv: dict) -> str:
    """房租金流：應收固定 80,100 + 動態追蹤已收/待收"""
    rb = tv.get("rent_breakdown", {}) or {}
    received = tv.get("rent_received_records", {}) or {}
    _m = date.today().strftime("%Y-%m")
    _got = sum(v for d, items in received.items() if str(d).startswith(_m) for v in items.values())
    label_map = {"大義街店面": "大義街1樓", "大義街二三樓": "大義街23樓"}
    # 完整應收明細
    detail = []
    for k, v in rb.items():
        label = label_map.get(k, k)
        detail.append(f"{label}{v:,}")
    if not detail:
        return "大義街1樓24,000+洲際W33,000+大義街23樓23,100+管理費2,100"
    base = "應收 80,100 = " + "+".join(detail)
    if _got > 0:
        got_parts = []
        for d, items in sorted(received.items()):
            if str(d).startswith(_m):
                for k, v in items.items():
                    label = label_map.get(k, k)
                    got_parts.append(f"{label}{v:,}")
        pending = 80_100 - _got
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
