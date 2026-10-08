# -*- coding: utf-8 -*-
"""日報組裝單一實作（INC-289，2026-10-07）。

為什麼存在
----------
同一份 `daily_report_v2_<date>.html` 有兩個 producer：
  - `regenerate_report.py`  ← 07:00（`morning_deploy.py`）與 22:00 cron 的產線路徑
  - `run_daily.py::main()`  ← 手動／legacy 路徑
兩邊各自實作了同一組「組裝邏輯」，於是同一份輸入產出不同 HTML：

  ① 「📋 執行中決策追蹤」章只有 regenerate_report.py 會加 → run_daily 路徑整章消失
  ② 穿透 `__DR_*_GAP__` 缺口欄：regenerate = `pp`，run_daily = TWD 金額
  ③ 本週行程／P0 任務：run_daily 另做優先度排序＋4000 字截斷，regenerate 維持檔案順序

本模組＝上述**這 3 項**＋「緊急應變（美股／台股）」LLM 區塊（第 4 項，INC-291）的唯一實作。
canonical 行為刻意等於 `regenerate_report.py` 的現行已上線行為（使用者每天看到的就是這一份），
因此收斂後**對外可見內容零變化**，只是讓另一個 producer 不再能產出不同版本。兩個 producer
一律呼叫本模組；任一 producer 自行重寫這些邏輯＝閘門 FAIL
（`tools/verify_daily_report_single_producer.py`）。

收斂範圍邊界（重要）
--------------------
「唯一 producer」的宣告目前涵蓋上述 4 項，仍不等於「日報產出一致性已全數關閉」：

① `today` 參數值仍有來源差異（**已知殘留**）：`regenerate_report.py` 的 `TODAY` 是牆鐘日
   （`dt.today()`），`run_daily.py` 的 `TODAY` 是 `snapshot.date`。日報內容對 `today` 的**值**
   敏感（決定要不要上 as_of 歷史內文標示）。管線不變量＝`regenerate_report.py` 開頭先執行
   `_roll_day_to_today(TODAY)`，使 `snapshot.date == TODAY`，故兩者於產線實務上同值；
   閘門以 S5.9／S5.10 斷言此不變量存在（消失即 FAIL）。未經裁決不得改任一邊的 TODAY 定義。
② 另有**第三條**緊急應變組裝路徑 `build_rebalance_dashboard.py`，輸出的是
   `rebalance_dashboard_<date>.html`（**不同產物**，且其連結無 `.html.html` 缺陷），
   不在本模組職責內、亦不受本閘門偵測（它不 emit 日報用的標記）→ 口徑若需統一須另立卡片。
③ `producer 之間`尚有非本模組職責的差異（例：`_inject_market_intel` 第 3 參數 regenerate 傳
   `daily_analysis`、run_daily 傳 `intel_signals`）——未經裁決不得順手收斂。

緊急應變區塊另有**已知缺陷、本卡刻意保留**（不得順手改）：連結多綴一個 `.html`
（產出 `…2026-10-08.html.html` → 404）。修正須另立卡片經使用者裁決。

相關：error_register INC-289／INC-291、PEND-20261007-02／04。
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


# ---------------------------------------------------------------- 緊急應變（美股／台股）
# 私有組裝偵測標記：**只有本模組可以持有**（tools/verify_daily_report_single_producer.py S1 掃描）。
EM_EMIT = "📅 緊急應變資料："
PAGES_BASE = "https://b0988321088.github.io/longjiu-dashboard-2"


def build_emergency_block(base, snapshot, today: str | None = None) -> str:
    """「緊急應變（美股／台股）」LLM 區塊的唯一實作（INC-291／PEND-20261007-04）。

    canonical 行為＝`regenerate_report.py` 2026-10-09 前的**已上線**實作（07:00
    `scripts/morning_deploy.py` 與 22:00 cron 的產線路徑，使用者每天看到的那一份）：
    `refresh_stale_amounts` 舊值覆蓋 ＋ as_of 歷史內文標示 ＋ `<br>` 換行 ＋ 2 條連結。

    `run_daily.py::main()` 原走 `_format_content_to_html(content_type="emergency_analysis")`
    （無舊值覆蓋、無 as_of 標示、僅 1 條連結、包裝縮排不同）→ 同一份輸入兩條路徑曾產出
    不同內容。現在兩個 producer 都呼叫本函式。

    回傳 `""` ＝ 沒有可用的緊急應變分析。**語意差異（已揭露）**：JSON「存在但格式壞」時，舊
    `regenerate_report.py` 是**直接拋 `JSONDecodeError`（整條產線中斷）**、舊 `run_daily.py` 是
    吞掉並留空；本函式採後者（容忍 ＋ WARN）→ 對 regenerate 路徑屬**放寬**（不再因壞檔停產），
    故**並非**「與原行為完全一致」。若日後要求 fail-closed，須另立卡片（本卡驗收＝對外可見內容零變化）。

    ⚠️ 已知缺陷（**刻意保留、另案處理**）：連結多綴一個 `.html` → `…2026-10-08.html.html`
    （404）。本卡職責＝收斂雙 producer、維持對外可見內容零變化；修正須另立卡片經裁決。
    """
    _base = Path(base)
    _today = str(today or _date.today().isoformat())
    _ej = _base / "data" / "emergency_llm_analysis.json"
    if not _ej.exists():
        return ""
    try:
        _d = json.loads(_ej.read_text(encoding="utf-8"))
    except Exception as _e:
        print(f"[WARN] load emergency_llm_analysis.json failed: {_e}")
        return ""
    _r = _d.get("full_report", _d.get("analysis", ""))
    # P0-1（2026-09-30）：歷史內文中的清償前舊金額（現金／總資產／總負債／月支出…）
    # 一律以當日 snapshot 真值覆蓋，不讓前一日數字偽裝成當日現況。
    try:
        from sot_targets import refresh_stale_amounts as _refresh
        _r = _refresh(_r, snapshot or {})
    except Exception as _e_r:
        print(f"[WARN] P0-1 緊急應變內文舊值覆蓋失敗：{_e_r}")
    _gen = _d.get("generated_at", "") or ""
    _hour = int(_gen[11:13]) if len(_gen) >= 13 and _gen[11:13].isdigit() else 0
    _src = str(_d.get("source", "") or "")
    _is_us = (("美股" in _src) if ("美股" in _src or "台股" in _src) else (_hour >= 15))
    _slot = "美股應變分析" if _is_us else "台股應變分析"
    # INC-214：只承諾真的會發生的排程（美股時段 21:30 每交易日固定產出）。
    _next = ("次一交易日 21:30 固定更新" if _is_us
             else "未觸發門檻則沿用此份；美股時段 21:30 每交易日固定更新")
    _note = (f'<p style="font-size:12px;color:#6e6e73;margin-bottom:6px">'
             f'{EM_EMIT}{_gen[:16]}（{_slot}；{_next}）</p>') if _gen else ""
    # P0-1（2026-09-30 使用者核准）：內文若為前一日產出，其中資產／負債／覆蓋率屬當時快照，
    # 不得偽裝成當日現況 → 強制標示 as_of。舊分析保留作歷史紀錄。
    _dt_src = str(_d.get("date") or "")[:10]
    _is_stale = bool(_dt_src) and _dt_src != _today
    _stale_badge = (f'<p style="font-size:12.5px;color:#b45309;font-weight:700;margin-bottom:6px;'
                    f'background:#fffbeb;border-left:3px solid #f59e0b;padding:6px 8px">'
                    f'⚠️ 歷史內文（as_of={_dt_src}）：以下為 {_dt_src} 的緊急應變分析，其中資產、負債、'
                    f'覆蓋率等數字為<b>當時快照，非 {_today} 現況</b>；{_today} 真值請以日報第 1 章'
                    f'「財富生命線」為準。</p>') if _is_stale else ""
    # INC-283（2026-10-03，裁示②）：範圍內＝完全靜默（與 index.html／rebalance_dashboard 同口徑）。
    try:
        from report_components import band_filter as _band_filter
        _r = _band_filter(_r)
    except Exception as _bfe:
        print(f"[WARN] band_filter 套用失敗（緊急應變內文，範圍內靜默可能失效）：{_bfe}")
    _html = f'<div class="callout callout-warn">{_stale_badge}{_note}{_r.replace(chr(10), "<br>" + chr(10))}</div>'
    # 連結（自動找最新可用檔案）；`%s.html` 為沿用的已知缺陷，見 docstring。
    _ef = sorted(_base.glob("emergency_report_2*.html"), reverse=True)
    _tf = sorted(_base.glob("emergency_taiex_report_2*.html"), reverse=True)
    if _ef:
        _html += ('<br><a href="%s.html" target="_blank" '
                  'style="display:inline-block;margin-top:10px;color:#34D399;font-weight:bold">'
                  '📄 檢視完整 LLM 緊急應變報告 →</a>') % (PAGES_BASE + "/" + _ef[0].name)
    if _tf:
        _html += ('<br><a href="%s.html" target="_blank" style="font-size:13px;color:#6e6e73">'
                  '📊 數據版報告（備援）</a>') % (PAGES_BASE + "/" + _tf[0].name)
    return _html
