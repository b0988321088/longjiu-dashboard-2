#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""close_card19_20261016.py — 結卡 #19（內文數字 17.5%）＋ 依慣例完成事項改記 work_log

背景：pending_decisions.json 的卡狀態含「已完成／✅」會讓 build_dashboard 整卡靜默隱藏
（check_thresholds 第 8 類閘門 FAIL）。慣例＝完成事項記 work_log.json，卡片自 pending 移除。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from pending_store import transaction

BASE = Path(__file__).resolve().parent
TITLE_KEY = "科技 17.5"
WL = BASE / "work_log.json"

# 1) 卡片自 pending 移除
with transaction(BASE / "pending_decisions.json") as tx:
    data = tx.data
    items = data if isinstance(data, list) else data["pending_decisions"]
    keep = [c for c in items if TITLE_KEY not in json.dumps(c, ensure_ascii=False)]
    removed = len(items) - len(keep)
    if removed != 1:
        raise SystemExit(f"⚠️ 預期移除 1 張，實際 {removed} → 中止（不寫入）")
    if isinstance(data, list):
        data[:] = keep
    else:
        data["pending_decisions"] = keep
    tx.stage(data)
print(f"✅ pending 卡 {len(items)} → {len(keep)}（移除內文數字卡）")

# 2) work_log 追加完成紀錄（沿用既有格式：date/category/item/detail）
raw = WL.read_bytes()
_text = raw.decode("utf-8")
_nl = "\r\n" if "\r\n" in _text[:400] else "\n"
try:
    _indent = len(_text.split(_nl)[1]) - len(_text.split(_nl)[1].lstrip(" "))
except Exception:
    _indent = 1
_wl = json.loads(_text)
_its = _wl if isinstance(_wl, list) else _wl.get("work_log", [])
shutil.copy2(WL, Path(__import__("os").environ.get("LOCALAPPDATA", str(BASE))) / "Temp" / "_bak_work_log_20261016.json")
_entry = {
    "date": "2026-10-16",
    "category": "完成",
    "item": "內文數字守門：buffett_cto_report『科技 17.5%』源頭治理（卡 #19 結案）",
    "detail": "真因＝buffett_cto_analyzer._industry_context 的 LLM prompt 寫死「現金(台幣)~12.8%、科技 17.5%」（2026-08-22 舊值）→ 模型照抄進 CTO 內文 → 內文數字守門判 17.5% ∉ 合法值 [14.8, 15.5, 24.3]。修法（源頭治理，未改內文、未放寬比對）：① 該行改讀 snapshot.penetration.actual_pct（科技 14.8%、現金 4.3%），缺值即省略；② build_rebalance_dashboard 的 `佔比_估 17.5` 舊值 fallback 移除，改以穿透真值兜底；③ analyzer 腳本哈希改變 → 快取自動失效，md 於 12:42 重產。驗收：check_narrative_numbers.py ✅ 0 處（全部可追溯）；線上日報 科技14.8%×3、科技17.5%×0；儀表板高科技 24.3%、無 17.5。",
}
_its.append(_entry)
if isinstance(_wl, list):
    _wl = _its
else:
    _wl["work_log"] = _its
WL.write_text(json.dumps(_wl, ensure_ascii=False, indent=_indent) + _nl, encoding="utf-8")
print(f"✅ work_log {len(_its)-1} → {len(_its)}（category=完成）")
