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

def sot_monthly_expense(snap: dict) -> float:
    """月支出單一入口（2026-10-01 INC-270）：消費端**禁**自帶 fallback 常數。

    為什麼：全 repo 曾有 ~15 處在讀 monthly_expense 時自帶 162,781（8 月口徑）當 fallback，
    之後該值被 172,543、159,210 兩次取代。fallback 平時不觸發，但 snapshot 一旦
    缺值／壞檔，頁面會**靜默印出三代前的月支出**，覆蓋率／安全線／乾粉等派生值跟著全錯
    且沒有任何告警（與 INC-201「消費端悄悄落回硬編碼」同病）。

    來源順序：snapshot.monthly_expense → snapshot.monthly_fixed_expense.合計
    （同檔同義，check_thresholds 每次驗兩者相等）→ 都沒有就 **raise**（大聲失敗，
    不以舊數字頂替）。
    """
    v = (snap or {}).get("monthly_expense")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        v = ((snap or {}).get("monthly_fixed_expense") or {}).get("合計")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise KeyError("snapshot 缺 monthly_expense 與 monthly_fixed_expense.合計："
                       "拒絕以舊口徑編造月支出（詳見 sot_monthly_expense docstring）")
    return float(v)


def sot_monthly_income(snap: dict) -> float:
    """月收入單一入口（2026-10-01 INC-270）：缺值即 raise，不以 228,751 之類常數頂替。"""
    v = (snap or {}).get("monthly_income")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise KeyError("snapshot 缺 monthly_income：拒絕以舊口徑編造月收入")
    return float(v)


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


# ═══════════════════════════════════════════════════════════════════════
# 2026-09-30 Q4 核心原則：先修真值，再修狀態；先修狀態，再談配置。
# 以下四塊全部「派生、可重算、單一寫入者」——呼叫端（update_data）寫回 snapshot，
# 其餘報表只讀；禁止在報表內重算或手寫。
# ═══════════════════════════════════════════════════════════════════════

def cash_layers(snap: dict, today: str | None = None) -> dict:
    """現金分層（使用者 2026-09-30 規格）：現金不得只看單一總額。

        cash_total
        ├── unrestricted_cash          真正可動用
        ├── restricted_cash
        │   ├── debt_repayment_reserve 指定還債款（本輪質押撥款）
        │   └── other_restricted       其他指定用途
        └── emergency_cash             底線內不動用（cash_floor）

    壓力測試「能不能撐住」一律用 unrestricted_cash（＋真正可動用的信用額度，
    目前無真值來源 → credit_line_available 回 None，不得推估）。
    """
    total = float(snap.get("cash_total") or snap.get("cash") or 0)
    rc = snap.get("restricted_cash")
    debt_res = other_res = 0.0
    rows: list = []
    if isinstance(rc, dict):
        amt = float(rc.get("金額") or 0)
        rows = list(rc.get("明細") or [])
        use = str(rc.get("用途") or "")
        # 明細裡的每一筆都是同一用途（指定還債）；用途不含「清償／還」者歸 other_restricted
        if "清償" in use or "還" in use or not use:
            debt_res = amt
        else:
            other_res = amt
    else:
        debt_res = float(rc or 0)
    restricted = debt_res + other_res
    unrestricted = max(0.0, total - restricted)
    floor = float(snap.get("cash_floor") or 0)
    emergency = min(unrestricted, floor) if floor else 0.0
    return {
        "cash_total": round(total),
        "unrestricted_cash": round(unrestricted),
        "restricted_cash": {
            "total": round(restricted),
            "debt_repayment_reserve": round(debt_res),
            "other_restricted": round(other_res),
            "明細": rows,
            "狀態": (rc or {}).get("狀態") if isinstance(rc, dict) else None,
        },
        "emergency_cash": {
            "金額": round(emergency),
            "定義": "現金底線內、不得動用的部分（cash_floor）",
            "floor": round(floor),
        },
        "dry_powder": round(max(0.0, unrestricted - emergency)),
        "credit_line_available": None,
        "credit_line_note": "⚠️ 無真值來源：可動用信用額度（未動用質押額度／保單借款空間）尚未建檔 → 壓力測試不得推估",
        "語義": (f"現金 {total:,.0f} 中 {restricted:,.0f} 係指定還債款（同時撐『清償承諾』與『追繳緩衝』，"
                 f"清償卡住則兩邊同時破）；可動用僅 unrestricted_cash {unrestricted:,.0f}；"
                 "撐不撐得住一律看 unrestricted_cash，不得把指定還債款當普通現金。"),
        "source": "sot_targets.cash_layers（派生：cash_total／restricted_cash／cash_floor）",
        "derived_at": today or dt.date.today().isoformat(),
    }


METRIC_VERSION = "2.0.0"          # 2026-09-30 P0-1：口徑版本化起點
METRIC_CHANGED_AT = "2026-09-30"
METRIC_CHANGE_REASON = ("P0-1 真值層單一寫入者：防禦維度／市場情境現況驗證改為派生，"
                        "配置分母排除指定用途款；緊急應變舊金額以當日真值覆蓋")


def metrics_registry(snap: dict, today: str | None = None) -> dict:
    """口徑版本註冊表：度量修正必須可追溯，不得與財務惡化混為一談。

    背景（CIO 2026-09-30）：P0-1 上線後壓力情境由 101.7%→95.9%、留停驗收掉到 B 級，
    屬「度量修正」而非資產變動 → 報表／月報必須標註，否則月報會把系統改版誤讀成財務惡化。
    """
    try:
        import passive_caliber as _pcal
        _sc = _pcal.scenarios(snap)
        _stress = round(_sc["stress"]["coverage"], 1)
        _con = round(_sc["con"]["coverage"], 1)
    except Exception:
        _stress = _con = None
    _ddm = ((snap.get("dual_dimension_metric") or {}).get("防禦維度") or {})
    return {
        "metric_version": METRIC_VERSION,
        "changed_at": METRIC_CHANGED_AT,
        "change_reason": METRIC_CHANGE_REASON,
        "classification": "度量修正（口徑變嚴格，非資產變動）",
        "影響": {
            "壓力情境覆蓋率": {
                "歷史值": 101.7,
                "現行值": _stress,
                "性質": "度量修正",
                "說明": ("P0-1 前為 101.7%（口徑較鬆）；P0-1 後以常態配息×0.8＋常態租金−洲際W空置÷"
                         "當期固定支出重算 → 低於 100% 屬度量口徑揭露，不表示現金流惡化"),
            },
            "防禦維度": {
                "歷史值": 53.8,
                "現行值": _ddm.get("佔比"),
                "性質": "度量修正",
                "說明": "舊 stored 53.8% 無程式寫入者（疑人工值）→ 停用，改派生（分母排除指定用途款）",
            },
            "保守被動覆蓋率": {"現行值": _con, "性質": "未變更"},
        },
        "標註規則": "凡顯示未達標（B 級／<100%）處，一律附「（度量修正 v2.0.0，非資產變動）」；月報需獨立一行「口徑變更影響」",
        "source": "sot_targets.metrics_registry",
        "derived_at": today or dt.date.today().isoformat(),
    }


def _us30y_state_file() -> dict:
    try:
        import json as _json
        _p = Path(__file__).resolve().parent / "us30y_state.json"
        return _json.loads(_p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def us30y_gate(snap: dict | None = None, state: dict | None = None,
               max_lag_days: int = 3) -> dict:
    """US30Y 讀值有效性閘門（CIO 2026-09-30 P0）：as_of 落後真值日 → UNKNOWN，禁止解凍判定。

    「舊資料觸發投資決策」是本閘門要擋的唯一風險：
    解凍／凍結判定必須同時具備 value + as_of + 連續天數；as_of 缺漏或落後真值日
    超過 max_lag_days（假日容忍）→ status=UNKNOWN、unfreeze_allowed=False。
    """
    snap = snap or {}
    st = state if state is not None else _us30y_state_file()
    try:
        import us30y_monitor as _mon
        _red = float(getattr(_mon, "RED_LINE", 0) or 0) or None
    except Exception:
        _red = None
    if _red is None:
        _red = ((snap.get("thresholds_2026_0915") or {}).get("US30Y紅線")) or None
    ref = str(snap.get("date") or dt.date.today().isoformat())
    as_of = st.get("last_date")
    value = st.get("last_rate")
    lag = None
    try:
        lag = (dt.date.fromisoformat(ref[:10]) - dt.date.fromisoformat(str(as_of)[:10])).days
    except Exception:
        lag = None
    if as_of in (None, "") or lag is None:
        status, reason = "UNKNOWN", "缺 us30y_as_of（讀值日期）→ 不得判定解凍／凍結"
    elif lag > max_lag_days:
        status, reason = "STALE", f"讀值日 {as_of} 落後真值日 {ref} 達 {lag} 天（> {max_lag_days}）→ 不得判定解凍"
    else:
        status, reason = "OK", f"讀值日 {as_of}（落後 {lag} 天，在容忍值 {max_lag_days} 天內）"
    below = (value is not None and _red is not None and float(value) < float(_red))
    return {
        "status": status,
        "value": value,
        "as_of": as_of,
        "ref_date": ref,
        "lag_days": lag,
        "max_lag_days": max_lag_days,
        "red_line": _red,
        "streak_days": st.get("streak"),
        "below_red_line": below,
        "unfreeze_allowed": bool(status == "OK" and below),
        "reason": reason,
        "source": "sot_targets.us30y_gate（us30y_state.json + us30y_monitor.RED_LINE）",
    }


# 紅線長期化階梯（使用者 2026-09-30 定案）：目的不是逼投資，
# 而是避免「暫停」最後變成「沒有人再處理」。
REDLINE_LADDER = (
    (0, 30, "維持現有配置，不交易"),
    (30, 45, "每週重新檢查資產配置與現金流"),
    (45, 60, "啟動替代配置評估（替代路線 A/B/C）"),
    (60, 10 ** 9, "CIO 必須重新審查「原本解凍邏輯是否仍適用」"),
)


def redline_policy(streak_days, today: str | None = None) -> dict:
    """US30Y 紅線長期化政策（REDLINE_LONG_DURATION_POLICY）。

    依「連續 ≥紅線天數」給出階段與應做事項；>45 天啟動替代配置評估，
    但實際買賣仍需另案核准（本政策不授權交易）。
    """
    try:
        d = int(streak_days or 0)
    except (TypeError, ValueError):
        d = 0
    stage = next((i + 1 for i, (lo, hi, _) in enumerate(REDLINE_LADDER) if lo <= d < hi), None)
    _lo, _hi, _action = next(((lo, hi, a) for lo, hi, a in REDLINE_LADDER if lo <= d < hi),
                             (0, 0, "無對應階段"))
    _nxt = next((f"{lo} 天：{a}" for lo, hi, a in REDLINE_LADDER if lo > d), None)
    return {
        "policy": "REDLINE_LONG_DURATION_POLICY",
        "streak_days": d,
        "stage": stage,
        "階段區間": f"{_lo}–{_hi if _hi < 10**9 else '∞'} 天",
        "應做事項": _action,
        "下一階段": _nxt,
        "授權邊界": "本政策只決定『檢查頻率與評估啟動』，不授權任何買賣；交易一律另案核准",
        "目的": "避免『暫停』變成『沒有人再處理』",
        "ladder": [{"下限天數": lo, "上限天數": (hi if hi < 10 ** 9 else None), "應做事項": a}
                   for lo, hi, a in REDLINE_LADDER],
        "source": "sot_targets.redline_policy（使用者 2026-09-30 定案）",
        "derived_at": today or dt.date.today().isoformat(),
    }


# ════════════════════════════════════════════════════════════════════════════
# 決策核心單一入口（使用者 2026-10-02 裁示；第 1 批：現金三層／留停 Gate／觸發器）
# ════════════════════════════════════════════════════════════════════════════
# 裁示重點：
#   ① 可動用現金唯一真值＝cash_layers.unrestricted_cash（853,675）；
#      穿透桶『現金/安全網』（854,264）列「在途／未對帳差異」，
#      不得參與 Gate／覆蓋率／投資決策。
#   ② 留停硬 Gate＝自由現金 ≥100 萬＋壓力現金流 ≥100%＋跑道 ≥540 天；
#      保守覆蓋與 3 個月趨勢降為**參考指標**（不參與 GO/WAIT）；取消 B 級與健康度分數敘事。
#   ③ 70～100 萬＝防守模式（禁新增槓桿／主動加碼，不擋既有定額）；<70 萬＝現金保全模式。
#   ④ LTV ≥53%＝禁止新增質押（用語「新增質押上限 53%」）；≤45 正常；45~53 注意；70% 追繳層。

CASH_MODE_NOTE = "可動用現金＝cash_layers.unrestricted_cash（唯一真值，2026-10-02 裁示）"


def allowable_cash(snap: dict) -> float:
    """可動用現金唯一真值（2026-10-02 裁示定案：cash_layers.available ＝ 853,675）。

    穿透桶『現金/安全網』為在途／未對帳口徑（差額 589），不得用於 Gate／覆蓋率／投資決策。
    """
    cl = (snap or {}).get("cash_layers") or {}
    for k in ("available", "unrestricted_cash"):
        v = cl.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    raise KeyError("snapshot.cash_layers.unrestricted_cash 缺值 → 可動用現金無真值，拒絕判斷"
                   "（2026-10-02 裁示：不得改用穿透桶『現金/安全網』）")


def cash_floor(snap: dict) -> float:
    """現金硬底線（70 萬）：cash_floor_rule.cash_floor → thresholds.現金_twd.生活底線。"""
    v = ((snap or {}).get("cash_floor_rule") or {}).get("cash_floor")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        v = (((snap or {}).get(SOT_KEY) or {}).get("現金_twd") or {}).get("生活底線")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise KeyError("snapshot 缺現金底線（cash_floor_rule.cash_floor／現金_twd.生活底線）→ 拒絕判斷")
    return float(v)


def gate_thresholds(snap: dict) -> dict:
    """留停硬 Gate 門檻（SoT：snapshot.sabbatical_gate_twd；缺值即 raise，不猜）。"""
    g = (snap or {}).get("sabbatical_gate_twd") or {}
    need = ("自由現金_twd", "壓力覆蓋_pct", "跑道天數")
    missing = [k for k in need if not isinstance(g.get(k), (int, float))]
    if missing:
        raise KeyError(f"snapshot.sabbatical_gate_twd 缺 {missing} → 留停 Gate 無門檻真值，拒絕判斷")
    return g


def cash_mode(snap: dict) -> dict:
    """現金模式（裁示 2026-10-02 第 3 點）。

    正常（≥100 萬）：無現金面限制
    防守模式（70～100 萬）：禁新增槓桿（質押／借款／借錢投資）＋主動加碼風險資產
                            ＋新增高額一次性投資；既有定期定額、已排定契約付款、
                            必要資產維護**不擋**
    現金保全模式（<70 萬）：連既有定額投入也暫停
    """
    avail = allowable_cash(snap)
    floor = cash_floor(snap)
    cap = float(gate_thresholds(snap)["自由現金_twd"])
    if avail < floor:
        mode, color = "現金保全模式", "red"
        ban = ["新增質押", "新增借款", "借錢投資", "主動加碼風險資產",
               "新增高額一次性投資", "既有定期定額投入"]
        allow = ["必要資產維護", "已排定之保單／契約付款"]
    elif avail < cap:
        mode, color = "防守模式", "amber"
        ban = ["新增質押", "新增借款", "借錢投資", "主動加碼風險資產", "新增高額一次性投資"]
        allow = ["已承諾之定期定額", "已排定之保單／契約付款", "必要資產維護"]
    else:
        mode, color = "正常", "green"
        ban, allow = [], ["（無現金面限制）"]
    return {"模式": mode, "燈號": color, "可動用": avail, "底線": floor,
            "自由現金門檻": cap, "餘裕": avail - floor, "距門檻": cap - avail,
            "禁止": ban, "允許": allow,
            "說明": "可動用＝cash_layers.unrestricted_cash（唯一真值）；"
                    "穿透桶『現金/安全網』為在途／未對帳口徑，不參與判斷",
            "source": "sot_targets.cash_mode（使用者 2026-10-02 裁示）"}


def sabbatical_gate(snap: dict) -> dict:
    """留停 Gate（裁示 2026-10-02 第 2 點）：三條硬門檻 → GO/WAIT；其餘為參考指標。"""
    import passive_caliber as _pc          # 延遲匯入（passive_caliber 反向 import 本模組）
    sc = _pc.scenarios(snap) or {}
    thr = gate_thresholds(snap)
    avail = allowable_cash(snap)
    stress = float((sc.get("stress") or {}).get("coverage") or 0.0)
    con_cov = float((sc.get("con") or {}).get("coverage") or 0.0)
    act_cov = float((sc.get("act") or {}).get("coverage") or 0.0)
    runway = float(_pc.runway_days(sc) or 0.0)
    gates = [
        {"名稱": "自由現金 ≥100 萬", "現值": avail, "門檻": float(thr["自由現金_twd"]),
         "通過": avail >= float(thr["自由現金_twd"]),
         "顯示": "{:,.0f} / {:,.0f}".format(avail, float(thr["自由現金_twd"]))},
        {"名稱": "壓力現金流 ≥100%", "現值": stress, "門檻": float(thr["壓力覆蓋_pct"]),
         "通過": stress >= float(thr["壓力覆蓋_pct"]), "顯示": "{:.1f}%".format(stress)},
        {"名稱": "跑道 ≥540 天", "現值": runway, "門檻": float(thr["跑道天數"]),
         "通過": runway >= float(thr["跑道天數"]), "顯示": "{:,.0f} 天".format(runway)},
    ]
    go = all(g["通過"] for g in gates)
    return {
        "判定": "GO" if go else "WAIT",
        "燈號": "🟢 GO（取得留停選擇權）" if go else "🟡 WAIT（尚未取得）",
        "gate": gates,
        "未達": [g["名稱"] for g in gates if not g["通過"]],
        "參考指標": {"保守覆蓋_pct": round(con_cov, 1), "當月實收覆蓋_pct": round(act_cov, 1),
                     "3個月趨勢": "需連續 3 個月真值日資料（不參與判定）"},
        "現金模式": cash_mode(snap)["模式"],
        "說明": "硬 Gate 只決定 GO/WAIT；保守覆蓋與 3 個月趨勢為參考指標，不參與判定"
                "（裁示 2026-10-02）；已取消 B 級與健康度分數敘事",
        "source": "sot_targets.sabbatical_gate（使用者 2026-10-02 裁示）",
    }


def _ltv_values(snap: dict) -> dict:
    """質押池 LTV（%）→ {池名: 值}；無真值回 {}（呼叫端顯示『無真值』，不推估）。"""
    out: dict = {}
    raw = (snap or {}).get("LTV") or (snap or {}).get("ltv") or {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                out[str(k)] = float(str(v).replace("%", "").strip())
            except Exception:
                pass
    if out:
        return out
    try:
        import pledge_status as _ps
        _f = _ps.pledge_facts(snap) or {}
        _c = _f.get("成數")
        if isinstance(_c, (int, float)) and _c > 0:
            # 成數＝質押金額 ÷ 擔保池市值（即 LTV）；0.5 → 50%
            out["國泰質押池"] = round(float(_c) * 100, 1)
            return out
        _txt = _ps.pledge_status_line(snap, style="full") or ""
        for _m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9（）()_-]{2,12})\s*LTV\s*(\d+(?:\.\d+)?)\s*%", _txt):
            out[_m.group(1)] = float(_m.group(2))
    except Exception:
        pass
    return out


def triggers(snap: dict) -> dict:
    """今日觸發器（裁示 2026-10-02 第 1 批③）：把散落的煞車／上限／門檻收斂成單一入口。

    只回報狀態，不產生買賣指令；每條標明真值來源。無真值者記「未建真值」，
    依龍九原則「沒有可靠真值，不准判斷」。
    """
    t = (snap or {}).get(SOT_KEY) or {}
    pen = (snap or {}).get("penetration") or {}
    gaps = pen.get("gaps") or {}
    actual = pen.get("actual_pct") or {}
    ladder = t.get("動作階梯_pp") or {}
    caps = t.get("單桶硬上限_pct") or {}
    brake = t.get("風險煞車") or {}
    out: list = []

    # 1) 風險煞車：US30Y（優先於階梯）
    g30 = (snap or {}).get("us30y_gate") or {}
    _v, _rl = g30.get("value"), g30.get("red_line")
    _streak, _need = g30.get("streak_days") or 0, brake.get("us30y_連續日") or 2
    if isinstance(_v, (int, float)) and isinstance(_rl, (int, float)):
        hot = _v >= _rl and _streak >= _need
        out.append({"id": "us30y_煞車", "項目": "風險煞車：US30Y",
                    "現值": "{:.3f}%（連續 {} 日，{}）".format(_v, _streak, g30.get("as_of") or "—"),
                    "門檻": "≥{:.2f}% 連續 {} 日".format(_rl, _need), "觸發": hot,
                    "動作": (brake.get("動作") or "只回報不動作（暫緩減碼/加碼）"),
                    "來源": "snapshot.us30y_gate ＋ thresholds.風險煞車"})
    else:
        out.append({"id": "us30y_煞車", "項目": "風險煞車：US30Y", "現值": "無真值", "門檻": "—",
                    "觸發": None, "動作": "待補真值（us30y_gate）", "來源": "—"})

    # 2) 現金模式
    cm = cash_mode(snap)
    out.append({"id": "cash_mode", "項目": "現金模式",
                "現值": "{:,.0f}（{}）".format(cm["可動用"], cm["模式"]),
                "門檻": "底線 {:,.0f}／自由現金 {:,.0f}".format(cm["底線"], cm["自由現金門檻"]),
                "觸發": cm["模式"] != "正常",
                "動作": "；".join(cm["禁止"]) if cm["禁止"] else "無限制",
                "來源": "sot_targets.cash_mode"})

    # 3) 留停 Gate（三條）
    try:
        gt = sabbatical_gate(snap)
        out.append({"id": "sabbatical_gate", "項目": "留停 Gate（三條）",
                    "現值": "／".join("{}{}".format(g["名稱"].split(" ")[0], "✅" if g["通過"] else "❌")
                                      for g in gt["gate"]),
                    "門檻": "三條全達標", "觸發": gt["判定"] != "GO",
                    "動作": ("留停＝WAIT（尚未取得選擇權）" if gt["判定"] != "GO"
                             else "留停＝GO（取得選擇權）"),
                    "來源": "sot_targets.sabbatical_gate"})
    except Exception as _e:
        out.append({"id": "sabbatical_gate", "項目": "留停 Gate（三條）", "現值": "無真值",
                    "門檻": "三條全達標", "觸發": None,
                    "動作": "無法判定：{}".format(_e), "來源": "sot_targets.sabbatical_gate"})

    # 4) 桶位：**可接受範圍制**（2026-10-02 裁示②）＋單桶硬上限（US30Y 煞車生效時一律「暫緩」）
    #    範圍內＝完全靜默（不列、不產生任何行動文字）；範圍外只標示「範圍外」，
    #    實際動作仍走既有 3/6/10pp 階梯＋硬上限（本批未變更階梯／煞車邏輯）。
    _brake_on = any(x["id"] == "us30y_煞車" and x["觸發"] is True for x in out)
    try:
        _bands = acceptable_band(snap)
    except Exception as _e_band:
        _bands = {}
        out.append({"id": "band_nodata", "項目": "可接受範圍", "現值": "無真值", "門檻": "—",
                    "觸發": None, "動作": "無法判定：{}".format(_e_band),
                    "來源": "sot_targets.acceptable_band"})
    for _n, _b in _bands.items():
        if not _b.get("顯示行動"):
            continue                                   # ← 範圍內完全靜默
        _tgt = _b.get("目標")
        _abs = abs(float(_b["現值"]) - float(_tgt)) if isinstance(_tgt, (int, float)) else 0.0
        if _abs >= float(ladder.get("大規模") or 10):
            _stage = "大規模調整"
        elif _abs >= float(ladder.get("導流") or 6):
            _stage = "導流"
        elif _abs >= float(ladder.get("觀察") or 3):
            _stage = "觀察（僅記錄）"
        else:
            _stage = "僅標示範圍外（未達階梯門檻，不動作）"
        out.append({"id": "band_" + _n, "項目": "範圍外：" + _n,
                    "現值": "{:.1f}%".format(_b["現值"]),
                    "門檻": "可接受 {}~{}%".format(_b["下限"], _b["上限"]),
                    "觸發": True,
                    "動作": ("⏸ 暫緩（US30Y 煞車生效，只回報不動作）" if _brake_on
                             else _stage + "（走再平衡授權）"),
                    "來源": "snapshot.可接受範圍_pct ＋ penetration.actual_pct"})
    for _n, _cap in caps.items():
        _cur = actual.get(_n)
        if isinstance(_cur, (int, float)) and float(_cur) > float(_cap):
            out.append({"id": "cap_" + _n, "項目": "單桶硬上限：" + _n, "現值": "{:.1f}%".format(_cur),
                        "門檻": "≤{}%".format(_cap), "觸發": True,
                        "動作": ("⏸ 暫緩（US30Y 煞車生效，只回報）" if _brake_on
                                 else "減碼至上限（硬上限優先於階梯）"),
                        "來源": "snapshot.penetration.actual_pct ＋ thresholds.單桶硬上限_pct"})

    # 5) 美元曝險
    usd = (snap or {}).get("usd_exposure_monitor") or {}
    usd_now = (usd.get("current") or {}).get("合計")
    usd_thr = t.get("美元曝險_pct") or {}
    if isinstance(usd_now, (int, float)):
        _y, _r = usd_thr.get("黃"), usd_thr.get("紅")
        _lvl = ("紅" if (isinstance(_r, (int, float)) and usd_now >= _r)
                else ("黃" if (isinstance(_y, (int, float)) and usd_now >= _y) else "正常"))
        out.append({"id": "usd_exposure", "項目": "美元曝險", "現值": "{:.1f}%".format(usd_now),
                    "門檻": "目標 {}／黃 {}／紅 {}".format(usd_thr.get("目標"), _y, _r),
                    "觸發": _lvl != "正常",
                    "動作": ("不再增加美元資產（紅線）" if _lvl == "紅"
                             else ("留意，避免再加美元" if _lvl == "黃" else "無限制")),
                    "來源": "snapshot.usd_exposure_monitor ＋ thresholds.美元曝險_pct"})
    else:
        out.append({"id": "usd_exposure", "項目": "美元曝險", "現值": "無真值", "門檻": "—", "觸發": None,
                    "動作": "待補真值（usd_exposure_monitor.current.合計）", "來源": "—"})

    # 6) LTV（新增質押上限 53%）
    ltv_thr = t.get("ltv分級_pct") or {}
    ltv_now = _ltv_values(snap)
    if ltv_now:
        _worst = max(ltv_now.values())
        _g, _y, _call = ltv_thr.get("綠上限"), ltv_thr.get("黃上限"), ltv_thr.get("追繳")
        if isinstance(_call, (int, float)) and _worst >= _call:
            _st, _act = "追繳層", "契約層級重大風險：先回報（不得新增質押）"
        elif isinstance(_y, (int, float)) and _worst >= _y:
            _st, _act = "禁止新增質押", "已達「新增質押上限 {}%」→ 禁止新增質押".format(_y)
        elif isinstance(_g, (int, float)) and _worst >= _g:
            _st, _act = "提高注意", "45~53% 區間：提高注意、不主動加槓桿"
        else:
            _st, _act = "正常", "≤{}%：正常".format(_g)
        out.append({"id": "ltv", "項目": "LTV（各池分別）",
                    "現值": "／".join("{} {:.1f}%".format(k, v) for k, v in ltv_now.items()),
                    "門檻": "正常 ≤{}%／新增質押上限 {}%／追繳 {}%".format(_g, _y, _call),
                    "觸發": _st != "正常", "動作": _act,
                    "來源": "質押池 LTV ＋ thresholds.ltv分級_pct"})
    else:
        out.append({"id": "ltv", "項目": "LTV（各池分別）", "現值": "無真值",
                    "門檻": "新增質押上限 {}%".format(ltv_thr.get("黃上限")), "觸發": None,
                    "動作": "待補真值來源（質押池 LTV）", "來源": "—"})

    fired = [x for x in out if x["觸發"] is True]
    unknown = [x for x in out if x["觸發"] is None]
    return {"列表": out, "觸發數": len(fired),
            "未建真值": [x["項目"] for x in unknown],
            "今日結論": ("✅ 今日不需動作" if not fired else "⚠️ {} 項觸發".format(len(fired))),
            "授權邊界": "本表只回報狀態；任何買賣／加減碼一律另案核准（US30Y 煞車優先於階梯）",
            "source": "sot_targets.triggers（使用者 2026-10-02 裁示 第 1 批③）"}


# ════════════════════════════════════════════════════════════════════════════
# 可接受範圍＋靜默原則（第 2 批｜使用者 2026-10-02 裁示 ②）
#   台股 7–13｜美股 27–33｜債券 27–33｜防禦（防守型配息）27–33｜科技 ≤15（上限）
#   現金：**不設百分比**（由 Gate／cash_mode 管理，不得塞進配置範圍）
#
#   ★ 「目標值」與「可接受範圍」分離（裁示重點）：
#     範圍只負責顯示與判讀；**落在範圍內＝完全靜默**——不得出現
#     「低於目標 Xpp／距離目標還差 Xpp／建議增加／需再平衡」等行動文字。
#     超出範圍也只標示「範圍外」；真正交易判斷仍沿用既有 3/6/10pp 階梯＋US30Y 煞車。
#     本函式不改變任何投資決策邏輯、不新增市場指標、不碰質押／借款／自動賣股。
# ════════════════════════════════════════════════════════════════════════════
BAND_EXCLUDED = ("現金", "現金/安全網", "cash")   # 不進 allocation 可接受範圍（裁示：現金不設百分比）


def acceptable_band(snap: dict) -> dict:
    """各投資桶可接受範圍（SoT：snapshot.可接受範圍_pct；缺值即 raise，不猜）。

    回傳 {桶名: {...}}；`顯示行動` 為 False＝落在範圍內 → 任何行動文字都不得出現。
    """
    tbl = (snap or {}).get("可接受範圍_pct")
    if not isinstance(tbl, dict) or not tbl:
        raise KeyError("snapshot.可接受範圍_pct 缺值 → 可接受範圍無真值，拒絕判斷（2026-10-02 裁示②）")
    actual = ((snap or {}).get("penetration") or {}).get("actual_pct") or {}
    targets = (((snap or {}).get(SOT_KEY) or {}).get("桶目標_pct") or {})
    hard = (((snap or {}).get(SOT_KEY) or {}).get("單桶硬上限_pct") or {})
    out: dict = {}
    for name, cfg in tbl.items():
        if str(name).startswith("_") or not isinstance(cfg, dict):
            continue                      # 略過 _規則／_來源 等說明欄
        if any(x in str(name) for x in BAND_EXCLUDED):
            continue
        _cur_key = cfg.get("現值鍵") or name
        cur = actual.get(_cur_key, actual.get(name))
        lo, hi = cfg.get("下限"), cfg.get("上限")
        typ = cfg.get("類型") or ("硬上限" if (lo is None and hi is not None) else "帶狀")
        tgt = targets.get(str(name).replace("成長", "")) if cfg.get("目標") is None else cfg.get("目標")
        state = "無現值"
        if isinstance(cur, (int, float)):
            if isinstance(hi, (int, float)) and cur > hi:
                state = "超上限"
            elif isinstance(lo, (int, float)) and cur < lo:
                state = "低於下限"
            elif lo is None:
                state = "在上限內"
            else:
                state = "範圍內"
        show = state in ("超上限", "低於下限")
        out[name] = {
            "類型": typ, "目標": tgt, "下限": lo, "上限": hi, "現值": cur,
            "狀態": state, "顯示行動": show,
            "硬上限_pct": hard.get(str(name).replace("成長", "")) or hard.get(name),
            "說明": ("範圍內＝完全靜默（不產生任何行動建議）" if not show
                     else "範圍外 → 僅標示『範圍外』；實際動作走 3/6/10pp 階梯（US30Y 煞車優先）"),
        }
    return out


def band_line(snap: dict, bucket: str) -> str:
    """單一桶顯示片段：**範圍內回空字串**（靜默）；範圍外只標示範圍外，不下指令。"""
    try:
        b = acceptable_band(snap).get(bucket)
    except Exception:
        b = None
    if not b or not b.get("顯示行動"):
        return ""
    if b["狀態"] == "超上限":
        return f"{bucket} {b['現值']:.1f}%（範圍外：高於可接受上限 {b['上限']}%）"
    return f"{bucket} {b['現值']:.1f}%（範圍外：低於可接受下限 {b['下限']}%）"


def band_silent_buckets(snap: dict) -> list:
    """落在可接受範圍內（＝必須靜默）的桶名清單；稽核守門用。"""
    return [k for k, v in acceptable_band(snap).items() if not v.get("顯示行動")]


# ════════════════════════════════════════════════════════════════════════════
# 90 天資金需求（第 4 批｜使用者 2026-10-02 裁示④）
#   A｜已確認（Confirmed）＝固定月支出 × 3 ＋ 其他已確認清單 → **納入 Coverage**
#   B｜條件式（Conditional）＝押標金 240 萬（得標後才成立）→ **不進分母**，
#        不得因此觸發借款／質押／賣股；真正接案後才進行資金來源比較
#   公式：可動用現金 ÷ A 區（毛需求）。被動收入僅作參考，不得用來美化現金安全度。
# ════════════════════════════════════════════════════════════════════════════
def cash_need_90d(snap: dict) -> dict:
    """90 天資金需求（A 已確認／B 條件式）與覆蓋率；缺 SoT 即 raise，不猜。"""
    cfg = (snap or {}).get("cash_need_90d")
    if not isinstance(cfg, dict) or not isinstance(cfg.get("A_已確認"), dict):
        raise KeyError("snapshot.cash_need_90d 缺值 → 90 天需求無真值，拒絕判斷（2026-10-02 裁示④）")
    a_cfg = cfg["A_已確認"]
    months = float(a_cfg.get("固定月支出_月數") or 3)
    fixed = float(sot_monthly_expense(snap)) * months
    others = a_cfg.get("其他已確認") or []
    other_sum = 0.0
    for it in others:
        v = it.get("金額") if isinstance(it, dict) else it
        if isinstance(v, (int, float)):
            other_sum += float(v)
    total_a = fixed + other_sum
    avail = allowable_cash(snap)
    thr = float(cfg.get("門檻_pct") or 100)
    cov = (avail / total_a * 100.0) if total_a > 0 else None
    # 2026-10-02 使用者更正裁示：**不建立 B 區**。得標與否未定的款項（如押標金 240 萬）
    # 不屬 90 天已確認需求 → 不進分母、不顯示、不觸發任何動作，僅留存於 SoT 備註（不渲染）。
    passive = ((snap or {}).get("passive_income") or {}).get("monthly_dividend_total")
    return {
        "A_已確認": {"固定月支出_月額": float(sot_monthly_expense(snap)), "月數": months,
                     "固定月支出_合計": fixed, "其他已確認": others, "其他合計": other_sum,
                     "合計": total_a},
        "可動用": avail,
        "覆蓋率_pct": round(cov, 1) if isinstance(cov, (int, float)) else None,
        "門檻_pct": thr,
        "燈號": (None if cov is None else ("🟢 充足" if cov >= thr else "🔴 不足")),
        "被動收入_參考（不參與）": passive,
        "說明": "毛需求為 Gate；被動收入僅參考；未得標之條件式事件（如押標金）不屬 90 天需求，不進分母也不顯示",
        "source": "sot_targets.cash_need_90d（使用者 2026-10-02 裁示④）",
    }


def cash_need_90d_line(snap: dict) -> str:
    """決定卡／日報用單行文字（A 覆蓋率＋B 條件式標註）。"""
    try:
        d = cash_need_90d(snap)
    except Exception as e:
        return "90 天現金需求：無法判定（" + str(e) + "）"
    a = d["A_已確認"]["合計"]
    s = ("未來 90 天現金需求覆蓋率 <b>" + ("{:.1f}%".format(d["覆蓋率_pct"]) if d["覆蓋率_pct"] is not None else "—")
         + "</b>（可動用 " + format(d["可動用"], ",.0f") + " ÷ 已確認 " + format(a, ",.0f") + "；門檻 "
         + format(d["門檻_pct"], ",.0f") + "%）")
    return s
