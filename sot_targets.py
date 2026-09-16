#!/usr/bin/env python3
"""sot_targets.py — 桶目標單一入口（SoT：snapshot.thresholds_2026_0915.桶目標_pct）

2026-09-16 INC-201：SoT 化（INC-187）把 `snapshot.penetration.targets` 的鍵名改成 SoT 名
（台股市值型／美股市值型／防守型配息／債券／現金／科技），但十幾個消費端仍讀舊鍵
（台股市值型目標／美股市值型目標／配息型目標／債券型目標／現金目標／科技曝險目標）
→ 每個消費端都「悄悄地」落回自己的硬編碼 fallback（20／25／15／40…＝8 月口徑），
於是儀表板、日報、圖表出現「目標值不見了／顯示舊值」而沒有任何人報錯。

本模組把「SoT 目標 + 舊鍵別名」一次產生：寫入端（build_penetration_report／update_data）
用它寫 penetration.targets，未遷移的消費端即可直接讀到正確值；新程式請直接讀 SoT。
"""
from __future__ import annotations

SOT_KEY = "thresholds_2026_0915"

# 舊鍵 → SoT 鍵（rename 對照；只做鍵名對映，不含任何數值）
LEGACY_ALIASES = {
    "台股市值型目標": "台股市值型",
    "美股市值型目標": "美股市值型",
    "配息型目標": "防守型配息",
    "債券型目標": "債券",
    "現金目標": "現金",
    "科技曝險目標": "科技",
}


def sot_bucket_pct(snap: dict) -> dict:
    """只回傳 SoT 原始桶目標（不含別名）。"""
    return dict(((snap.get(SOT_KEY) or {}).get("桶目標_pct")) or {})


def bucket_targets(snap: dict) -> dict:
    """回傳「SoT 桶目標 + 舊鍵別名」，供 penetration.targets 寫入與未遷移消費端讀取。

    SoT 不存在時回傳 {}（呼叫端自行決定 fallback，不得在此寫死數字）。
    """
    sot = sot_bucket_pct(snap)
    if not sot:
        return {}
    out = dict(sot)
    for _legacy, _new in LEGACY_ALIASES.items():
        if _new in sot:
            out[_legacy] = sot[_new]
    return out


# 防守（配息資產）合併口徑＝2026-08-21 使用者裁示：基金也有配息，防守應合併計算 →
# ≥ 凍結承接門檻（SoT `防守合併口徑_pct.凍結承接`，現 60%）即「防守已足、承接凍結」。
# 2026-09-16 INC-201：金額改為「組成加總」派生（stored 的 `配息資產合計` 曾是人工寫入、
# 與明細對不上：合計 18,097,158 但組成加總 18,072,925，差 24,233）。
def defensive_caliber(snap: dict) -> dict:
    dcm = snap.get("defensive_combined_metric") or {}
    comp = dcm.get("組成") or {}
    amt = sum(v for v in comp.values() if isinstance(v, (int, float)))
    total = snap.get("total_assets") or 0
    thr = (((snap.get("thresholds_2026_0915") or {}).get("防守合併口徑_pct")) or {}).get("凍結承接")
    pct = round(amt / total * 100, 1) if total else 0.0
    return {
        "金額": amt,
        "佔比": pct,
        "門檻": thr,
        "已足": (thr is not None and pct >= thr),
        "組成": comp,
        "stored_佔比": dcm.get("佔比"),
        "stored_合計": dcm.get("配息資產合計"),
    }
