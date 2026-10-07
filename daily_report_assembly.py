# -*- coding: utf-8 -*-
"""日報組裝單一實作（INC-289，2026-10-07）。

為什麼存在
----------
同一份 `daily_report_v2_<date>.html` 有兩個 producer：
  - `regenerate_report.py`  ← 07:00（scripts/morning_deploy.py）與 22:00 cron 的產線路徑
  - `run_daily.py::main()`  ← 手動／legacy 路徑
兩邊各自實作了同一組「組裝邏輯」，於是同一份輸入產出不同 HTML：

  ① 「📋 執行中決策追蹤」章只有 regenerate_report.py 會加 → run_daily 路徑整章消失
  ② 穿透 `__DR_*_GAP__` 缺口欄：regenerate = `pp`，run_daily = TWD 金額
  ③ 本週行程／P0 任務：run_daily 另做優先度排序＋4000 字截斷，regenerate 維持檔案順序

本模組＝**唯一實作**。canonical 行為刻意等於 `regenerate_report.py` 的現行已上線行為
（使用者每天看到的就是這一份），因此收斂後**對外可見內容零變化**，只是讓另一個
producer 不再能產出不同版本。

兩個 producer 一律呼叫本模組；任一 producer 自行重寫這些邏輯＝閘門 FAIL
（`tools/verify_daily_report_single_producer.py`）。

相關：error_register INC-289／PEND-20261007-02。
"""
from __future__ import annotations

import json
from datetime import date as _date, timedelta as _td
from pathlib import Path

# P0 任務要顯示的狀態關鍵字（與 regenerate_report.py 原實作相同）
IMPORTANT_STATUS = ("🔴", "🔄", "⚠️", "⏸️", "📋 重要")


# ---------------------------------------------------------------- 載入
def load_events(base) -> list:
    """讀 schedule_events.json（缺檔／壞檔 → 空清單，行為與原實作一致）。"""
    try:
        return json.loads((Path(base) / "schedule_events.json").read_text(encoding="utf-8"))
    except Exception:
        return []


def load_pending(base) -> list:
    """讀 pending_decisions.json（缺檔／壞檔 → 空清單）。"""
    try:
        return json.loads((Path(base) / "pending_decisions.json").read_text(encoding="utf-8"))
    except Exception:
        return []


# ---------------------------------------------------------------- 本週行程
def build_schedule_rows(events, today: str | None = None, days: int = 7) -> str:
    """本週行程表（今天 ~ +days 天 ＋ 待處理）。維持檔案順序，最多 20 列。"""
    _t = today or _date.today().isoformat()
    _end = (_date.fromisoformat(_t) + _td(days=days)).isoformat()
    rows = [
        f'<tr><td>{e.get("date","")}</td><td>{e.get("item","")}</td>'
        f'<td class="num">{e.get("amount","")}</td><td>{e.get("status","")}</td></tr>'
        for e in events
        if e.get("date", "") == "待處理" or _t <= e.get("date", "") <= _end
    ]
    return "\n".join(rows[:20])


# ---------------------------------------------------------------- P0 / 決策追蹤
def build_decision_rows(pending, snapshot) -> str:
    """「執行中決策追蹤」逐卡一列（含決策卡連結）。

    INC-289：原實作把整段包在 `except: pass` 裡，任何例外都只留一行 WARN，
    然後 `_decision_rows` 為空 → 整章靜默消失（10/07 實例）。本版改為
    **fail-closed**：pending 非空卻產出 0 列＝直接拋錯，不允許靜默減章。
    """
    rows = ""
    for _d in pending:
        _card = str(_d.get("card", "") or "").strip()
        _card_td = (f'<td><a href="{_card}" target="_blank" '
                    f'style="color:#2563eb;text-decoration:underline">📑 決策卡</a></td>'
                    if _card else "<td>—</td>")
        try:
            from sot_targets import refresh_stale_amounts as _refresh
            _title_ok = _refresh(str(_d.get("title", "") or ""), snapshot)
            _status_ok = _refresh(str(_d.get("status", "") or ""), snapshot)
        except Exception:
            # 舊值覆蓋失敗時，寧可原樣輸出也不要吞掉整章
            _title_ok = str(_d.get("title", "") or "")
            _status_ok = str(_d.get("status", "") or "")
        rows += (f'<tr><td>{_d.get("date","")}</td><td>{_title_ok}</td>'
                 f'<td>{_status_ok}</td>{_card_td}</tr>')
    if pending and not rows:
        raise RuntimeError("執行中決策追蹤產出 0 列（pending_decisions 非空）→ fail-closed")
    _n_expect = len([x for x in pending])
    _n_got = rows.count("<tr>")
    if _n_expect != _n_got:
        raise RuntimeError(f"執行中決策追蹤列數不符：pending {_n_expect} vs 產出 {_n_got}")
    return rows


def build_p0_tasks_html(events, pending, snapshot, today: str | None = None, days: int = 30) -> str:
    """P0 任務清單 ＋（附掛）「📋 執行中決策追蹤」表。維持檔案順序。"""
    _t = today or _date.today().isoformat()
    _end = (_date.fromisoformat(_t) + _td(days=days)).isoformat()
    _dynamic = [
        f'<li>{e.get("date","")} — {e.get("item","")} {e.get("amount","")} '
        f'{e.get("status","") or ""}</li>'
        for e in events
        if any(s in (e.get("status", "") or "") for s in IMPORTANT_STATUS)
        and (e.get("date", "") == "待處理" or _t <= e.get("date", "") <= _end)
    ]
    out = "\n".join(_dynamic)
    _rows = build_decision_rows(pending, snapshot)
    if _rows:
        out += '\n<p style="margin-top:12px;font-weight:700;color:#3b82f6">📋 執行中決策追蹤</p>'
        out += ('\n<table style="width:100%;font-size:13px;border-collapse:collapse">'
                '<thead><tr style="background:#f0f0f5"><th>日期</th><th>決策</th>'
                '<th>狀態</th><th>決策卡</th></tr></thead><tbody>')
        out += _rows
        out += "\n</tbody></table>"
    return out


# ---------------------------------------------------------------- 穿透 __DR_*
def substitute_dr_tokens(html: str, penetration) -> str:
    """取代日報模板內全部 `__DR_*__`。

    缺口欄口徑＝**pp**（實際% − 目標%），與現行線上版一致（INC-289 收斂點②）。
    """
    _pen = penetration or {}
    _atwd = _pen.get("actual_twd", {}) or {}
    _apct = _pen.get("actual_pct", {}) or {}
    _tgt = _pen.get("targets", {}) or {}
    for _tk in ("美股市值型成長_科技", "美股市值型成長_非科技"):
        if _tk in _apct and not _atwd.get(_tk):
            print(f"  ⚠️ 穿透缺 {_tk} 金額（actual_twd）→ 日報該列會顯示 0 TWD；"
                  f"請先跑 update_data.py 重建穿透")
    for _k, _v in [
        ("__DR_TW_V__", f"{_atwd.get('台股市值型成長',0):,.0f}"),
        ("__DR_US_V__", f"{_atwd.get('美股市值型成長',0):,.0f}"),
        ("__DR_DEF_V__", f"{_atwd.get('防守型配息',0):,.0f}"),
        ("__DR_BOND_V__", f"{_atwd.get('債券',0):,.0f}"),
        ("__DR_CASH_V__", f"{_atwd.get('現金/安全網',0):,.0f}"),
    ]:
        html = html.replace(_k, _v)
    for _k, _v in [
        ("__DR_TW_PCT__", f"{_apct.get('台股市值型成長',0):.1f}%"),
        ("__DR_US_PCT__", f"{_apct.get('美股市值型成長',0):.1f}%"),
        ("__DR_DEF_PCT__", f"{_apct.get('防守型配息',0):.1f}%"),
        ("__DR_BOND_PCT__", f"{_apct.get('債券',0):.1f}%"),
        ("__DR_CASH_PCT__", f"{_apct.get('現金/安全網',0):.1f}%"),
    ]:
        html = html.replace(_k, _v)
    for _k, _v in [
        ("__DR_US_TECH_V__", f"{_atwd.get('美股市值型成長_科技',0):,.0f}"),
        ("__DR_US_TECH_PCT__", f"{_apct.get('美股市值型成長_科技',0):.1f}%"),
        ("__DR_US_NT_V__", f"{_atwd.get('美股市值型成長_非科技',0):,.0f}"),
        ("__DR_US_NT_PCT__", f"{_apct.get('美股市值型成長_非科技',0):.1f}%"),
        ("__DR_US_TECH_TGT__", f"{_tgt.get('科技曝險目標',15):.0f}%"),
        ("__DR_US_TECH_GAP__",
         f"{_apct.get('美股市值型成長_科技',0) - _tgt.get('科技曝險目標',15):+.1f}pp"),
    ]:
        html = html.replace(_k, _v)
    for _k, _v in [
        ("__DR_TW_TGT__", f"{_tgt.get('台股市值型目標',20):.0f}%"),
        ("__DR_US_TGT__", f"{_tgt.get('美股市值型目標',30):.0f}%"),
        ("__DR_DEF_TGT__", f"{_tgt.get('配息型目標',20):.0f}%"),
        ("__DR_BOND_TGT__", f"{_tgt.get('債券型目標',15):.0f}%"),
        ("__DR_CASH_TGT__", f"{_tgt.get('現金目標',15):.0f}%"),
    ]:
        html = html.replace(_k, _v)
    for _k, _t, _g in [
        ("__DR_TW_GAP__", _apct.get('台股市值型成長', 0), _tgt.get('台股市值型目標', 20)),
        ("__DR_US_GAP__", _apct.get('美股市值型成長', 0), _tgt.get('美股市值型目標', 30)),
        ("__DR_DEF_GAP__", _apct.get('防守型配息', 0), _tgt.get('配息型目標', 20)),
        ("__DR_BOND_GAP__", _apct.get('債券', 0), _tgt.get('債券型目標', 15)),
        ("__DR_CASH_GAP__", _apct.get('現金/安全網', 0), _tgt.get('現金目標', 15)),
    ]:
        html = html.replace(_k, f"{_t - _g:+.1f}pp")
    return html
