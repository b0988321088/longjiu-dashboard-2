#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""monthly_risk_card.py — 日報第 1 章「本月投資風險摘要」卡（淺色版）

2026-11-05 使用者裁決：日報只要看三件事——今天賺賠多少、風險有沒有超標、該不動還是防守。
數字一律來自 monthly_risk_watch.assess()（該層再委派 performance_core），本檔不計算任何績效。
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]


def _money(v):
    if v is None:
        return "—"
    return f"{v:+,.0f}"


def _pct(v):
    return "—" if v is None else f"{v:+.2f}%"


def render(snap: dict | None = None, theme: str = "light") -> str:
    import monthly_risk_watch as mrw

    if snap is None:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    r = mrw.assess(snap)
    try:
        mrw.log_daily(r)                     # 影子模式：每天留紀錄（含未觸發）
    except Exception:
        pass

    tone = {"green": "#059669", "watch": "#d97706", "alert": "#ea580c",
            "severe": "#dc2626", "unknown": "#6b7280"}.get(r["level"], "#6b7280")
    bg = {"green": "#ecfdf5", "watch": "#fffbeb", "alert": "#fff7ed",
          "severe": "#fef2f2", "unknown": "#f9fafb"}.get(r["level"], "#f9fafb")
    q_note = {"ok": "TWR（時間加權、含配息與匯率）", "degraded": "降級口徑（非時間加權，僅參考）",
              "insufficient": "資料不足"}.get(r["quality"], r["quality"])
    # 壓力情境（唯讀推算）：-5%／-10% 對總資產與質押 LTV 的影響
    try:
        _rows = mrw.stress(snap)
        stress_txt = "｜".join(
            f'{int(x["shock_pct"])}%：總資產 {x["total_after"]:,.0f}（{x["total_delta_pct"]:+.2f}%）'
            + (f'、質押 LTV {x["ltv_after"]:.2f}%（維持率 {x["maintenance_after"]:.1f}%）'
               + (f'、回 53% 需還 {x["repay_to_53"]:,.0f}' if x.get("repay_to_53") else '')
               if x.get("ltv_after") is not None else '')
            for x in _rows)
    except Exception:
        stress_txt = "—"
    days = r.get("days")
    asof = r.get("asof") or "—"
    shadow = ("影子模式（2026-11-05～2027-02-05）：只顯示燈號，不觸發交易、不改 G1/G2/G3"
              if r.get("shadow") else "影子期已結束，待人工裁決是否轉正式")

    return f'''<div class="card" style="border-left:6px solid {tone};background:{bg}">
<h2>🛡️ 本月投資風險摘要（MTD｜相對口徑）</h2>
<table>
<tr><th style="width:28%">本月累積報酬率</th><td><b style="color:{tone};font-size:16px">{_pct(r["ret_pct"])}</b>
　<span style="color:{tone};font-weight:700">{r["icon"]} {r["label"]}</span></td></tr>
<tr><th>本月帳面損益</th><td>{_money(r["net_twd"])} TWD <span class="note">（含配息與費用；與報酬率不同源）</span></td></tr>
<tr><th>距下一級警戒</th><td>{r["gap"]["text"]}</td></tr>
<tr><th>壓力情境（資產價格同幅下跌）</th><td>{stress_txt}</td></tr>
<tr><th>當日投資風險裁示</th><td><b>{r["stance"]}</b></td></tr>
</table>
<p class="note">口徑：{q_note}｜資料 as-of {asof}{f"（{days} 個估值日）" if days else ""}。
警戒門檻：月累積 -1% 黃燈／-2% 橘燈／-3% 紅燈（相對口徑，不受資產規模影響）。
15 日滾動損益只作歷史風險校準，不代表月累積損益。{shadow}。</p>
</div>'''
