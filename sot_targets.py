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
import re
from pathlib import Path  # 2026-09-29：restricted_cash 缺 key 時回退讀 snapshot.json 用

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


def sync_scenario_verification(snap: dict, today: str | None = None) -> dict:
    """market_scenario_standards.現況驗證 ← dual_dimension_metric 單向派生同步。

    2026-09-30 P0-1（使用者核准）：原 stored「防禦 53.8%」無程式寫入者（疑舊人工值），
    與派生公式 49.1% 並存 → 同一份報告同時出現「53.8% 合格」與「49.1% 不合格」雙答案。
    改為一律由 dual_dimension_metric.佔比 產生，門檻判定同源。
    LTV 現況＝基金質押借款 ÷ 國泰擔保池（真值鍵，禁寫死）。
    """
    ms = dict(snap.get("market_scenario_standards") or {})
    if not ms:
        return ms
    ddm = snap.get("dual_dimension_metric") or {}
    _def = (ddm.get("防禦維度") or {}).get("佔比")
    _inc = (ddm.get("收入維度") or {}).get("佔比")
    _scenes = ms.get("情境") or {}
    _cur = next((k for k, v in _scenes.items() if (v or {}).get("當前")), "區間震盪")
    _sc = _scenes.get(_cur) or {}

    def _num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    # LTV 現況：基金質押借款 ÷ 擔保池市值
    _loan = _num(snap.get("fund_pledge_loan")) or 0.0
    _pool = _num(((snap.get("cathay_pledge_0911") or {}).get("擔保池") or {}).get("合計")) or 0.0
    _ltv = round(_loan / _pool * 100, 1) if _pool else None

    _dmin, _imin, _lmax = _sc.get("防禦最低"), _sc.get("收入最低"), _sc.get("LTV上限")
    _d_ok = (_def is not None and _dmin is not None and _def >= _dmin)
    _i_ok = (_inc is not None and _imin is not None and _inc >= _imin)
    _l_ok = (_ltv is not None and _lmax is not None and _ltv <= _lmax)
    _all_ok = _d_ok and _i_ok and _l_ok
    ms["現況驗證"] = {
        "防禦": _def, "防禦門檻": _dmin, "防禦合格": _d_ok,
        "收入": _inc, "收入門檻": _imin, "收入合格": _i_ok,
        "LTV": _ltv, "LTV上限": _lmax, "LTV合格": _l_ok,
        "結論": (f"完全符合「{_cur}」標準" if _all_ok
                 else f"未完全符合「{_cur}」標準（防禦 {_def}% vs ≥{_dmin}%、收入 {_inc}% vs ≥{_imin}%、LTV {_ltv}% vs ≤{_lmax}%）"),
        "source": "sot_targets.sync_scenario_verification（派生自 dual_dimension_metric；2026-09-30 P0-1 建立單一寫入者）",
        "derived_at": today or dt.date.today().isoformat(),
    }
    return ms


def build_dual_dimension_metric(snap: dict, today: str | None = None) -> dict:
    """雙維度資產定位：防禦維度佔比由「組成加總 ÷ 配置分母」派生（不再手寫）。

    配置分母＝total_assets − restricted_cash（指定用途款隔離後不屬配置資金；
    2026-09-29 裁示口徑）。收入維度含不動產租金，其組成非全金額鍵 → 只重算防禦維度。
    """
    ddm = dict(snap.get("dual_dimension_metric") or {})
    if not ddm:
        return ddm
    _total_cfg = (snap.get("total_assets") or 0) - restricted_cash(snap)
    _def = dict(ddm.get("防禦維度") or {})
    _comp = _def.get("組成") or {}
    if _comp and _total_cfg > 0:
        _amt = sum(v for v in _comp.values() if isinstance(v, (int, float)))
        _def["合計"] = _amt
        _def["佔比"] = round(_amt / _total_cfg * 100, 1)
        _def["分母"] = _total_cfg
        _def["derived_at"] = today or dt.date.today().isoformat()
        ddm["防禦維度"] = _def
    return ddm


def refresh_stale_amounts(text: str, snap: dict) -> str:
    """把歷史內文（前一日的 LLM 分析）中的清償前舊金額，替換為當日 snapshot 真值。

    2026-09-30 P0-1：9/29 的緊急應變內文含「現金 6,719,182／總資產 31,808,561／
    總負債 36,003,720」等清償前數字，注入 9/30 日報後讀者無從分辨 → 直接以真值覆蓋。
    只替換「唯一指向舊值」的金額；`5,900,000` 同時是現行基金質押借款餘額，
    故僅在「指定用途款／指定清償款」語境下替換。
    """
    if not text:
        return text
    _cash = float(snap.get("cash_total") or 0)
    _rc = restricted_cash(snap)
    _ta = snap.get("total_assets")
    _tl = snap.get("total_liabilities")
    _exp = snap.get("monthly_expense")
    _pi = snap.get("passive_income") or {}
    _cons = _pi.get("total_conservative")

    # 先處理「指定用途款 5,900,000」這種組合語境（避免誤改質押借款餘額）
    if _rc and _rc != 5900000:
        text = re.sub(r"(指定(?:用途|清償)款\s*)5,900,000", rf"\g<1>{_rc:,.0f}", text)
        text = re.sub(r"(指定用途款\s*)5,900,000", rf"\g<1>{_rc:,.0f}", text)

    repl = {
        "6,719,182": f"{_cash:,.0f}" if _cash else None,
        "31,808,561": f"{_ta:,}" if _ta else None,
        "36,003,720": f"{_tl:,}" if _tl else None,
        "162,781": f"{_exp:,}" if _exp else None,
        "96,798": f"{_cons:,.0f}" if _cons else None,
    }
    for old, new in repl.items():
        if new and old != new:
            text = text.replace(old, new)
    return text


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


def restricted_cash(snap: dict) -> float:
    """指定用途現金（質押撥款待清償等）— 不計入桶位／乾粉／Runway。

    真值來源＝snapshot.restricted_cash.金額（禁寫死）；清償入帳後由該欄歸零即自動解除。
    2026-09-29 使用者核准：避免「指定還債款」被當超額現金 → 桶位假超標觸發自動減碼。
    """
    def _parse(_v) -> float:
        if isinstance(_v, dict):
            _v = _v.get("金額")
        try:
            return float(_v or 0)
        except (TypeError, ValueError, AttributeError):
            return 0.0

    if isinstance(snap, dict) and "restricted_cash" in snap:
        return _parse(snap.get("restricted_cash"))
    # 2026-09-29 CIO major：呼叫端拿到的可能是不含該欄的精簡 dict（例：run_daily.calibrate_sources()
    # 的回傳值，regenerate_report.py 走的就是這條生產路徑）→ 缺 key 一律回退讀 snapshot.json，
    # 否則顯示端會把質押撥款 590 萬當可動用現金。
    try:
        import json as _json
        _p = Path(__file__).resolve().parent / "snapshot.json"
        return _parse((_json.loads(_p.read_text(encoding="utf-8")) or {}).get("restricted_cash"))
    except Exception:
        return 0.0


def available_cash(snap: dict) -> float:
    """可動用現金 ＝ cash_total − restricted_cash（下限 0）。"""
    try:
        _cash = float((snap or {}).get("cash_total") or (snap or {}).get("cash") or 0)
    except (TypeError, ValueError, AttributeError):
        _cash = 0.0
    return max(0.0, _cash - restricted_cash(snap))

def liability_interest(snap: dict) -> dict:
    """負債月息明細（單一來源｜2026-09-30 使用者核准動態化）。

    各項＝餘額 × 利率 / 12；餘額/利率一律讀 snapshot.liabilities_build_up（禁寫死）。
    房貸不列入（房貸月付已以「房貸」項計入月支出，再算利息＝重複）。
    用途：sabbatical_checklist_update 的「每月負債成本」、run_daily 的月支出口徑、check_thresholds 不變式。
    """
    lb = snap.get("liabilities_build_up") or {}
    _map = [
        ("保單借貸利息", "保單借貸", "保單借貸利率", 0.04),
        ("券商質押利息", "券商質押", "券商質押利率", 0.0392),
        ("基金質押利息", "基金質押", "基金質押利率", 0.0265),
    ]
    out: dict = {}
    for name, bal_key, rate_key, dflt_rate in _map:
        bal = float(lb.get(bal_key) or 0)
        rate = float(lb.get(rate_key) or dflt_rate or 0)
        out[name] = round(bal * rate / 12)
    out["合計"] = sum(v for k, v in out.items() if k != "合計")
    out["_note"] = "保單借貸＋券商質押＋基金質押之月息；房貸不計（已於月支出以房貸項計入）｜來源 snapshot.liabilities_build_up"
    return out

def restricted_breakdown(snap: dict) -> str:
    """指定用途款明細（先註記、後入帳）— 報告用單行文字（單一來源）。

    使用者 2026-09-30 指示：指定用途款要「註記原始撥款 590 萬＋各筆狀態」，
    已入帳（截圖確認）才寫入；轉帳中（未確認）只標「執行中」，不動帳。
    """
    rc = snap.get("restricted_cash") or {}
    rows = rc.get("明細") or []
    if not rows:
        return ""
    _icon = lambda st: ("✅" if "已清償" in st or "已入帳" in st else ("🔄" if "執行中" in st else "⏳"))
    parts = [f"{_icon(str(x.get('狀態','')))} {x.get('簡稱') or str(x.get('項目',''))[:10]} {float(x.get('金額') or 0)/10000:.0f}萬"
             for x in rows]
    _orig = float(rc.get("原始撥款") or 0)
    _head = f"指定用途款 {_orig/10000:.0f}萬" if _orig else "指定用途款"
    return _head + "＝" + "＋".join(parts)
