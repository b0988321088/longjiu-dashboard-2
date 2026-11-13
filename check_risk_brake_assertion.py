#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""風險煞車可測斷言（2026-11-13，週五深度審查 CIO 復盤第 2 條落地）

背景：CIO 指出「風險煞車優先於動作階梯」這條規則只存在於內文與記憶，沒有可測斷言
→ 一旦哪天報表寫出「美股超配 +6.3pp，逢彈減碼 20 萬」的執行指令，沒有任何檢查會擋。

本腳本把「煞車」變成可執行斷言：
  A. US30Y ≥ 行動門檻（預設 5.30）= 煞車中 → 主要報表必須出現煞車語意（只回報／不動作／煞車）
  B. 煞車中 → 美股超標的段落必須在同一區塊內同時出現「美股」與「只回報／不動作」
  C. 未煞車（US30Y < 顯示門檻）→ 報表不得再宣稱「煞車中」（避免解凍後仍掛舊警語）

判準來源：sot_targets / us30y_policy（門檻與狀態單一來源），不在此處寫死數字。
exit 0 = PASS；exit 1 = FAIL（有未標示煞車的報表）；exit 2 = 無法判定（真值缺失，fail-visible）
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORTS = [
    ("index.html", "儀表板"),
    ("daily_report_v2_{d}.html", "日報"),
    ("rebalance_dashboard_{d}.html", "再平衡"),
]

BRAKE_WORDS = ("只回報", "不動作", "煞車", "凍結")


def load_snapshot() -> dict:
    with open(BASE / "snapshot.json", encoding="utf-8") as f:
        return json.load(f)


def us30y_state(snap: dict) -> tuple[float | None, float, float]:
    """回傳 (現值, 警示顯示門檻, 行動門檻)；門檻一律從 us30y_policy 取。"""
    try:
        import us30y_policy as usp

        warn = float(getattr(usp, "WARN_DISPLAY_ONLY", 0) or 0)
        action = float(getattr(usp, "ACTION_THRESHOLD", 0) or 0)
    except Exception:
        warn, action = 0.0, 0.0
    v = None
    gate = snap.get("us30y_gate") or {}
    for k in ("current", "value", "rate", "現值", "讀值"):
        if isinstance(gate.get(k), (int, float)):
            v = float(gate[k])
            break
    if v is None:
        for k in ("us30y", "us30y_value"):
            if isinstance(snap.get(k), (int, float)):
                v = float(snap[k])
                break
    return v, warn, action


def main() -> int:
    snap = load_snapshot()
    v, warn, action = us30y_state(snap)
    today = str(snap.get("date") or "")[:10]
    if v is None or action <= 0:
        print(f"⚠️ 無法判定：US30Y 現值={v}／行動門檻={action}（門檻或讀值缺失）→ 不宣稱 PASS")
        return 2

    braking = v >= action
    gap_us = None
    try:
        gap_us = (snap.get("penetration") or {}).get("gaps", {}).get("美股市值型成長")
    except Exception:
        pass

    print(f"US30Y {v:.3f}%｜顯示門檻 {warn:.2f}%｜行動門檻 {action:.2f}%｜"
          f"{'🔴 煞車中' if braking else '🟢 未觸行動門檻'}｜美股缺口 {gap_us}")

    fails, checked = [], 0
    for pattern, label in REPORTS:
        name = pattern.format(d=today)
        p = BASE / name
        if not p.exists():
            print(f"  · {label} {name}：不存在，跳過")
            continue
        checked += 1
        html = p.read_text(encoding="utf-8", errors="ignore")
        has_brake = any(w in html for w in BRAKE_WORDS)

        if braking:
            # A：煞車中必須有煞車語意
            if not has_brake:
                fails.append(f"{label}：US30Y {v:.2f}% ≥ {action:.2f}% 煞車中，但全文無「只回報/不動作/煞車/凍結」")
                continue
            # B：美股與煞車語意必須同段（±260 字）
            us_hits = [m.start() for m in re.finditer(r"美股", html)]
            paired = False
            for pos in us_hits:
                seg = html[max(0, pos - 260): pos + 260]
                if any(w in seg for w in BRAKE_WORDS):
                    paired = True
                    break
            if us_hits and not paired:
                fails.append(f"{label}：有「美股」段落但周邊 260 字內無煞車語意（風險煞車未標示）")
        else:
            # C：未煞車時不得宣稱煞車中
            if "煞車中" in html:
                fails.append(f"{label}：US30Y {v:.2f}% < {action:.2f}%（未煞車）卻仍宣稱「煞車中」→ 舊警語殘留")

    print(f"受檢報表：{checked} 份")
    if fails:
        print("\n❌ 風險煞車斷言 FAIL：")
        for f in fails:
            print("   -", f)
        return 1
    print("\n✅ 風險煞車斷言 PASS：煞車狀態與報表語意一致（無未標示煞車的美股動作段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
