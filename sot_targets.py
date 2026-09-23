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

import datetime as dt

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
# ─────────────────────────────────────────────────────────────
# 防守組成的「真值派生」（2026-09-23 INC-242b v3）
# 為什麼：`組成` 一直是人工維護，而 `配息資產合計`／`佔比` 由它加總派生 → 任何一個
# 分量過期，整組數字就「一致地錯」。本輪實測：`保單月配基金` 停在舊安聯 A+B
# 7,553,405（真值 allianz_combined 7,652,217）→ 佔比被低估，而這個佔比被 20+ 個
# 報表／判準消費（防守合併口徑 ≥60% 決定「承接凍結」）。
# 修法：每個分量都回到真值鍵；派生不到的鍵（口徑未定，如鉅亨月配）保留原值，不猜。
# ─────────────────────────────────────────────────────────────
SEC_DEF_TICKERS = ("00713", "00878", "0056", "00919", "00918", "00888")  # 與 update_all._SEC_DEF 同源
CATHAY_MONTHLY_NAME_KEYS = ("富達", "聯博")  # 國泰月配＝富達C＋聯博AD（不含 B11 後收級別）


def derive_defensive_components(snap: dict) -> dict:
    """由真值鍵派生防守組成（派生不到的分量保留 stored 原值）。"""
    comp = dict(((snap.get("defensive_combined_metric") or {}).get("組成")) or {})

    def _num(v):
        return v if isinstance(v, (int, float)) and v else None

    _ab = _num(snap.get("allianz_combined")) or (
        (_num(snap.get("allianz_policy_a_value")) or 0)
        + (_num(snap.get("allianz_policy_b_value")) or 0) or None)
    if _ab:
        comp["保單月配基金"] = int(_ab)

    _cy = sum(int(v) for k, v in (snap.get("fund_breakdown_cathay") or {}).items()
              if isinstance(v, (int, float)) and any(s in str(k) for s in CATHAY_MONTHLY_NAME_KEYS))
    if _cy:
        for _k in list(comp):
            if _k.startswith("國泰月配"):
                comp[_k] = _cy

    _etf = sum(int(h.get("value") or 0)
               for h in ((snap.get("securities") or {}).get("holdings") or [])
               if str(h.get("ticker", "")) in SEC_DEF_TICKERS)
    if _etf:
        comp["防守ETF"] = _etf

    _fj = _num(snap.get("firstjin_fl65_current_value"))
    if _fj:
        comp["第一金ID01"] = int(_fj)
    return comp


def build_defensive_metric(snap: dict, today: str | None = None) -> dict:
    """回傳「自癒後」的 defensive_combined_metric（組成／合計／佔比／說明全部派生）。

    呼叫端（update_data）寫回 snapshot；說明字串一併重生，避免舊金額被當成口徑
    寫進報告（原 `組成說明` 內就寫死了 7,553,405）。
    """
    dcm = dict(snap.get("defensive_combined_metric") or {})
    comp = derive_defensive_components(snap)
    amt = sum(v for v in comp.values() if isinstance(v, (int, float)))
    total = snap.get("total_assets") or 0
    dcm["組成"] = comp
    dcm["配息資產合計"] = amt
    dcm["佔比"] = round(amt / total * 100, 1) if total else 0.0
    dcm["derived_at"] = today or dt.date.today().isoformat()
    dcm["source"] = ("sot_targets.build_defensive_metric（組成加總派生：安聯×allianz_combined／"
                     "國泰×fund_breakdown_cathay／防守ETF×holdings ticker／第一金×firstjin_fl65_current_value）")
    _cy_key = next((k for k in comp if k.startswith("國泰月配")), None)
    dcm["組成說明"] = (
        f"由真值鍵派生（INC-242b v3）：保單月配基金＝allianz_combined {int(comp.get('保單月配基金') or 0):,}；"
        f"國泰月配＝富達C＋聯博AD {int(comp.get(_cy_key) or 0):,}（不含 B11 後收級別）；"
        f"防守ETF＝{len(SEC_DEF_TICKERS)} 檔 ticker 加總 {int(comp.get('防守ETF') or 0):,}；"
        f"第一金ID01＝firstjin_fl65_current_value {int(comp.get('第一金ID01') or 0):,}"
    )
    if "鉅亨月配" in comp:
        dcm["組成說明"] += f"；⚠️ 鉅亨月配口徑未定，暫留原值 {int(comp.get('鉅亨月配') or 0):,}"
    dcm.setdefault("裁示", "防守承接凍結（2026-08-21 使用者：基金也有配息應合併計算）")
    return dcm


def defensive_caliber(snap: dict) -> dict:
    dcm = snap.get("defensive_combined_metric") or {}
    comp = derive_defensive_components(snap)
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
