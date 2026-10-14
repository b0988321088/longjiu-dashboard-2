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
# 2026-10-07 裁決②③：美元曝險政策門檻唯一來源（usd_advisory ← thresholds_2026_0915.美元曝險_pct）＋觀測線命名
from usd_advisory import tier_limit_text as usd_tier_limit_text  # noqa: E402

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
    # 2026-10-04 P0（CIO 六審）：原 `or 0.0` → 缺 fund_pledge_loan 時 _loan=0、_ltv=0.0、
    # `LTV合格=True` → 每日穿透報表情境 callout 印「LTV 0.0%（≤52% ✅）」（與同份報告該列
    # 「⚠️ 缺真值」自相矛盾），且本函式輸出會被呼叫端寫回 snapshot.market_scenario_standards
    # ＝假真值入庫。缺鍵一律 None；None 不得被判定為合格。
    _loan = _num(snap.get("fund_pledge_loan"))
    _pool = _num(((snap.get("cathay_pledge_0911") or {}).get("擔保池") or {}).get("合計"))
    _ltv = (round(_loan / _pool * 100, 1)
            if (_loan is not None and _pool) else None)

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
                 else f"未完全符合「{_cur}」標準（防禦 {_def}% vs ≥{_dmin}%、收入 {_inc}% vs ≥{_imin}%、"
                      f"LTV {'⚠️ 缺真值' if _ltv is None else f'{_ltv}%'} vs ≤{_lmax}%）"),
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
    _comp = dict(_def.get("組成") or {})
    # 2026-10-02 使用者裁示：現金/貨幣停泊一律派生自可動用現金唯一真值
    # （sot_targets.allowable_cash＝cash_layers.available／unrestricted_cash）。
    # 目的：消滅「第二份人工輸入的現金真值」（曾出現 819,182 ≠ 853,675）。
    # 缺真值時 allowable_cash 直接 raise（fail-closed），不沿用舊值、不編造。
    if "現金/貨幣停泊" in _comp:
        _cash_sot = float(allowable_cash(snap))
        # 保持既有型別（整數元 → int），避免重產後整份 snapshot 出現 853675.0 型別漂移
        _comp["現金/貨幣停泊"] = int(_cash_sot) if _cash_sot.is_integer() else _cash_sot
    _def["組成"] = _comp
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

    # ── 2026-10-12（總工單 A2/A3 收尾）：**失效敘述覆蓋**，與金額覆蓋同一層、同一入口 ──
    # 症狀：日報與再平衡報表會嵌入先前班次的「緊急應變 LLM 內文」
    #       （data/emergency_llm_analysis.json）。該內文可能仍寫「押標金 240 萬＝條件式事件、
    #       檢視日 10/15」，甚至列在『要做的事』清單裡 —— 即使真值已裁決取消。
    # 為何在此修、不直接改產物文字：這兩份產物共用本函式；在此以 snapshot **狀態**驅動覆蓋，
    #       單一入口、兩處同步生效；若日後裁決改變（狀態不再含「取消」）即不再覆蓋，不寫死。
    # 2026-10-12 獨立審查（首版被 REJECT）後的硬化：
    #   ① 全部改為**語境錨定 regex**（不再用裸子字串 replace）——避免誤傷同金額的其他語境
    #   ② 日期只接受 YYYY-MM-DD，否則退回具名預設並具名示警（不自帶未驗證字串進產物）
    #   ③ 若內文仍含失效片語但 snapshot 狀態欄缺失/未取消 → **fail-loud 示警**（不靜默放行）
    _bid = snap.get("標案押標金_1010")
    _bid_st = str((_bid or {}).get("狀態") or "")
    _STALE_PATS = (r"、\s*10/15 標案押標金(?:來源)?的資訊蒐集",
                   r"條件式事件：10 月標案押標金 2,400,000 元[^。]*。",
                   r"10 月標案押標金 240 萬來源定案",
                   r"10\s*月標案押標金不預留[，,]\s*9\s*月底評估")
    if "取消" in _bid_st:
        _bd_raw = str((_bid or {}).get("裁示日_取消") or "").strip()
        _bd = _bd_raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _bd_raw) else ""
        if not _bd:
            print(f"[WARN] 標案押標金取消裁示日非 YYYY-MM-DD（{_bd_raw!r}）→ 敘述覆蓋以『已取消』呈現、不帶日期")
        _suffix = f"（{_bd}）" if _bd else ""
        _mid = f" {_bd} " if _bd else "本輪"
        text = re.sub(_STALE_PATS[0], "", text)
        text = re.sub(_STALE_PATS[1],
                      f"條件式事件：10 月標案押標金 2,400,000 元已於{_mid}經使用者裁決取消"
                      f"（不再評估、不辦理保證函、不列任何需求與排程）。", text)
        text = re.sub(_STALE_PATS[2], f"10 月標案押標金 240 萬（已取消{'：' + _bd if _bd else ''}）", text)
        text = re.sub(_STALE_PATS[3], f"10 月標案押標金已取消{_suffix}", text)
    else:
        _hit = [p for p in _STALE_PATS if re.search(p, text)]
        if _hit:
            print(f"[WARN] 內文仍含失效之押標金敘述 {len(_hit)} 種，但 snapshot.標案押標金_1010.狀態"
                  f"未載明『取消』（現值 {_bid_st[:24]!r}）→ 未覆蓋；請確認裁決與真值是否同步")
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


LONG_TERM_CASH_GOAL = 1000000   # 長期目標（僅標示用；不取代硬底線 700,000，2026-10-11 工單A）


def dry_powder(snap: dict) -> dict:
    """乾粉／現金缺口＝可動用現金 − 現金底線，**保留正負號**（2026-10-11 一次性工單 A 單一入口）。

    為什麼要有這支（根因）：乾粉可以為負（不足＝短少）。舊寫法在三個消費端各自
    `max(0, cash − life)` 把負值夾成 0，再用 `dry or 舊值` 回退到
    `snapshot.乾粉執行_0926.戰術乾粉總額.當前`（2026-09-29 的 119,182）→ 負值被換成
    過期正值，於是 10/11 週報／eval 同時出現「乾粉 119,182（現金 639,661 − 生活底線
    700,000）」與「短少 60,339」，且過期乾粉流入下游報告。

    回傳：available／floor／dry（有正負號）／shortfall／status／long_term_goal。
    讀取端一律呼叫本函式，**不得**再自行 max(0,…) 或回退 snapshot.乾粉執行_0926。
    缺真值 fail-closed：現金或底線無法解析即 raise，不以 0 冒充（0 是合法乾粉值，
    會與「缺值」混淆）。
    """
    _raw_cash = (snap or {}).get("cash_total", (snap or {}).get("cash"))
    if not isinstance(_raw_cash, (int, float)) or isinstance(_raw_cash, bool):
        # 缺現金鍵 → 不得以 0 冒充（會變成「短少 700,000」這種假警報），fail-closed。
        raise ValueError("乾粉口徑缺真值（snapshot 無 cash_total／cash）→ 拒絕計算")
    floor = cash_floor(snap)              # 既有單一入口（缺值即 raise）
    avail = available_cash(snap)
    if floor is None or avail is None:
        raise ValueError("乾粉口徑缺真值（available_cash／cash_floor）→ 拒絕計算")
    dry = int(round(float(avail) - float(floor)))
    # 跨源一致性（工單A 要求）：cash_total−restricted（本函式口徑）與 snapshot.cash_layers.unrestricted_cash
    #   若不一致 > 1 元 → 標記，交共用閘門 fail-closed（不得靜默選一個）。缺 cash_layers 時不誤報。
    _cl = (snap or {}).get("cash_layers") or {}
    _cl_avail = _cl.get("unrestricted_cash")
    _xgap = None
    if isinstance(_cl_avail, (int, float)) and not isinstance(_cl_avail, bool):
        if abs(float(_cl_avail) - float(avail)) > 1:
            _xgap = int(round(float(avail) - float(_cl_avail)))
    return {
        "available": float(avail),
        "floor": float(floor),
        "dry": dry,                                   # 有正負號：<0 代表短少
        "shortfall": int(max(0, -dry)),
        "status": "餘裕" if dry >= 0 else "短少",
        "long_term_goal": LONG_TERM_CASH_GOAL,        # 僅標示；10/14 結轉未入帳前不得宣告已補足
        "cross_source_gap": _xgap,                    # None＝一致；非 None＝跨源不一致（差額）
        "cross_source_ok": _xgap is None,
        "note": ("乾粉＝可動用現金 − 現金底線（可為負）；長期目標 1,000,000 僅標示，"
                 "不取代硬底線 700,000；來源 sot_targets.dry_powder"),
    }


def dry_display(dp: dict, unit: str = "twd") -> str:
    """乾粉顯示字串（單一實作）：正→「乾粉 119,182」／負→「短少 60,339」。

    unit="wan" 時改印「乾粉 11.9萬／短少 6.0萬」（供既有「萬」格式的內文沿用）。
    """
    d = dp or {}
    # 兼容兩種來源：sot_targets.dry_powder()（dry＝有正負號）與 cash_caliber()（dry_signed）
    dry = int(d["dry_signed"]) if "dry_signed" in d else int(d.get("dry") or 0)
    if dry >= 0:
        return f"乾粉 {dry/10000:.1f}萬" if unit == "wan" else f"乾粉 {dry:,}"
    sf = -dry
    return f"短少 {sf/10000:.1f}萬" if unit == "wan" else f"短少 {sf:,}"


def liability_interest(snap: dict) -> dict:
    """負債月息明細（單一來源｜2026-09-30 使用者核准動態化）。

    各項＝餘額 × 利率 / 12；餘額/利率一律讀 snapshot.liabilities_build_up（禁寫死）。
    房貸不列入（房貸月付已以「房貸」項計入月支出，再算利息＝重複）。
    用途：sabbatical_checklist_update 的「每月負債成本」、run_daily 的月支出口徑、check_thresholds 不變式。

    2026-10-04 P0（PEND-20261004-02／CIO 三審必改3）：移除 dflt_rate 常數退路
    （保單 4.0%／券商 3.92%／基金 2.65%）。真值缺利率時**不得**用預設利率算出一條看起來
    正常的月息（例：基金質押 5,900,000 缺利率仍印 13,029）。改為該項回 None、`合計` 亦回 None
    （禁部分加總偽裝完整），並以 `_缺真值` 列出缺哪個利率鍵供呼叫端明示。
    邊界：餘額為 0 時利率不影響結果（0 是正確值）→ 不列缺真值，避免無謂的全域退化。
    """
    lb = snap.get("liabilities_build_up") or {}
    _map = [
        ("保單借貸利息", "保單借貸", "保單借貸利率"),
        ("券商質押利息", "券商質押", "券商質押利率"),
        ("基金質押利息", "基金質押", "基金質押利率"),
    ]
    out: dict = {}
    _miss: list = []
    for name, bal_key, rate_key in _map:
        bal = float(lb.get(bal_key) or 0)
        rate_v = lb.get(rate_key)
        if rate_v in (None, ""):
            out[name] = None if bal else 0
            if bal:
                _miss.append(rate_key)
            continue
        try:
            out[name] = round(bal * float(rate_v) / 12)
        except (TypeError, ValueError):
            out[name] = None if bal else 0
            if bal:
                _miss.append(rate_key)
    _vals = [out["保單借貸利息"], out["券商質押利息"], out["基金質押利息"]]
    out["合計"] = None if any(v is None for v in _vals) else sum(_vals)
    out["_缺真值"] = _miss
    out["_note"] = ("保單借貸＋券商質押＋基金質押之月息；房貸不計（已於月支出以房貸項計入）"
                    "｜來源 snapshot.liabilities_build_up｜缺利率 → 該項與合計皆為 None（禁以預設利率頂替）")
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
        # 2026-10-11 工單A：dry_powder 維持「可動用超出底線的部分」（≥0）——與 check_thresholds
        #   的閉合不變式（底線＋乾粉＝可動用）相容：不足時底線＝全部可動用、乾粉＝0。
        #   另外獨立輸出「短少」與「有正負號的乾粉」，供報告層如實顯示「短少 60,339」，
        #   不再讓負值被夾成 0 後被消費端回退成 snapshot.乾粉執行_0926 的過期正值。
        "dry_powder": round(max(0.0, unrestricted - emergency)),
        "dry_powder_signed": round(unrestricted - floor),
        "cash_shortfall": round(max(0.0, floor - unrestricted)),
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

    2026-10-02 二階段（使用者裁示「統一現金口徑」）：穿透桶『現金/安全網』**已改讀此真值**
    （update_all.calc_penetration），餘數法與真值的差額（在途／未對帳，實測 589）
    改揭露於 penetration._meta.cash_in_transit，不再併入桶位。

    2026-10-14 第 0 批 R2（使用者裁決）：`snapshot.cash_available`（772,607，2026-10-08 殘值）
    經全庫盤點確認為**零消費端的過期欄位**（*.py／*.html／*.js 及 repo 外皆 0 引用；
    僅存在於備份檔與 2026-10-01 的 CIO 口徑審查紀錄）。權威口徑＝本函式，
    原始值依裁決「原始資料的移除須另有證據」**保留不刪**，禁再被消費。
    """
    cl = (snap or {}).get("cash_layers") or {}
    for k in ("available", "unrestricted_cash"):
        v = cl.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    raise KeyError("snapshot.cash_layers.unrestricted_cash 缺值 → 可動用現金無真值，拒絕判斷"
                   "（2026-10-02 裁示：不得改用穿透桶『現金/安全網』）")


# ═══════════════════════════════════════════════════════════════
# 總額級真值 accessor（2026-10-04 P0 假真值退路清除）
#
# 為什麼要有這層：這 6 個總額在全 repo 有 14 處 `.get(key, <大額常數>)` 假真值退路
# （不動產 34,017,063／34,000,000、總負債 22,000,000、保單 9,802,872／9,876,282、
# 現金 4,483,408／3,614,169／3,119,158、證券 2,597,360、基金 793,434／765,991）。
# fallback 平時不觸發，但 snapshot 一旦缺鍵／壞檔，報表會**靜默印出數個月前的舊真值**，
# 且沒有任何告警（與 INC-201「消費端悄悄落回硬編碼」、INC-278「missing → 假真值」同病）。
#
# 規則（使用者 2026-10-04 裁示）：
#   ① 同義鍵清單只准有一份＝asset_sync.SYNONYM_GROUPS（沿用，禁在此複製一份）。
#   ② 缺值一律 raise（fail-closed），**禁止** or 0、get(key, 0)、新常數兜底。
#   ③ 呼叫端不得再自行 `.get(..., 常數)`——一律走本層。
# ═══════════════════════════════════════════════════════════════

def _synonym_truth(snap: dict, group: str, label: str) -> float:
    """同義鍵群組取真值；群組內全部無值 → raise（不以任何常數頂替）。"""
    from asset_sync import SYNONYM_GROUPS
    keys = SYNONYM_GROUPS[group]
    for _k in keys:
        _v = (snap or {}).get(_k)
        if isinstance(_v, (int, float)) and not isinstance(_v, bool):
            return float(_v)
    raise KeyError(f"snapshot 缺{label}（同義鍵 {'／'.join(keys)} 皆無值）→ 拒絕以寫死常數頂替"
                   "（2026-10-04 P0 假真值退路清除；詳見 sot_targets._synonym_truth docstring）")


def total_cash(snap: dict) -> float:
    """總現金真值（含指定用途款）。可動用口徑請用 allowable_cash()／available_cash()。"""
    return _synonym_truth(snap, "cash_total", "總現金")


def total_liabilities(snap: dict) -> float:
    """總負債真值：liabilities_build_up.total（明細推導，canonical）→ total_liabilities（相容鍵）→ raise。"""
    _lb = ((snap or {}).get("liabilities_build_up") or {}).get("total")
    if isinstance(_lb, (int, float)) and not isinstance(_lb, bool):
        return float(_lb)
    return _synonym_truth(snap, "total_liabilities", "總負債")


def real_estate_value(snap: dict) -> float:
    """不動產價值真值（real_estate_value／real_estate 同義）。"""
    return _synonym_truth(snap, "real_estate", "不動產價值")


def insurance_total(snap: dict) -> float:
    """保單總現值真值（insurance_total／insurance_current_value／insurance 同義）。"""
    return _synonym_truth(snap, "insurance_total", "保單總現值")


def securities_total(snap: dict) -> float:
    """證券總市值真值（securities_total_market_value 為 canonical；其餘為同義鍵）。"""
    return _synonym_truth(snap, "securities_total", "證券總市值")


def funds_total(snap: dict) -> float:
    """基金總市值真值（fund_market／fund_market_value／funds_total／funds 同義）。"""
    return _synonym_truth(snap, "funds_total", "基金總市值")


def policy_pledge_loan(snap: dict) -> float:
    """保單借貸餘額真值：liabilities_build_up.保單借貸（明細推導）→ policy_pledge_loan（相容鍵）→ raise。

    2026-10-04 P0 假真值案例：build_final.py 原 `.get('policy_pledge_loan', 4000000)`
    會在 snapshot 缺鍵時，把「已於 2026-09-29＋10-01 全數清償」的 400 萬保單借貸復活。
    這是負債假真值——比顯示 0 更危險，因為它讓已消滅的債務看起來還在。
    """
    _lb = ((snap or {}).get("liabilities_build_up") or {}).get("保單借貸")
    if isinstance(_lb, (int, float)) and not isinstance(_lb, bool):
        return float(_lb)
    _v = (snap or {}).get("policy_pledge_loan")
    if isinstance(_v, (int, float)) and not isinstance(_v, bool):
        return float(_v)
    raise KeyError("snapshot 缺保單借貸餘額（liabilities_build_up.保單借貸／policy_pledge_loan）→ "
                   "拒絕以 4,000,000 舊負債頂替（2026-10-04 P0 假真值退路清除）")


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
        _adv = bool(usd.get("advisory_only"))
        if _adv:
            # 2026-10-07 使用者裁決：美元曝險自動化＝真值回歸，非重新制定政策。
            # 60/65/70 門檻與 9/12 放寬政策衝突 → 只顯示、不得轉成資產操作（觸發=False）。
            out.append({"id": "usd_exposure", "項目": "美元曝險", "現值": "{:.1f}%".format(usd_now),
                        "門檻": (usd_tier_limit_text(snap) if _adv
                                 else "目標值 {}／黃色觀察 {}／高曝險觀察線 {}".format(
                                     usd_thr.get("目標"), _y, _r)),
                        "觸發": False, "僅顯示": True, "等級": _lvl,
                        "動作": "🟡 僅顯示：不觸發「不再增加美元資產」（2026-10-07 裁決；政策衝突留待 10 月戰略檢討）",
                        "來源": "snapshot.usd_exposure_monitor（advisory_only；usd_exposure_sync.py 自動產生）"
                                " ＋ thresholds_2026_0915.美元曝險_pct"})
        else:
            out.append({"id": "usd_exposure", "項目": "美元曝險", "現值": "{:.1f}%".format(usd_now),
                        "門檻": "目標值 {}／黃色觀察 {}／高曝險觀察線 {}".format(usd_thr.get("目標"), _y, _r),
                        "觸發": _lvl != "正常",
                        "動作": ("不再增加美元資產（高曝險觀察線）" if _lvl == "紅"
                                 else ("留意，避免再加美元" if _lvl == "黃" else "無限制")),
                        "來源": "snapshot.usd_exposure_monitor ＋ thresholds_2026_0915.美元曝險_pct"})
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


# ════════════════════════════════════════════════════════════════════════════
# 資產分解（2026-10-11 工單B｜使用者裁決）
#   不變量：五桶 ＋ 衛星 ＋ 在途 ＋ 指定用途款 = 總資產
#   為什麼：只印五桶會出現「合計 93.44%」而無從得知其餘 6.56% 是什麼（10/11 週報症狀）。
#   規則：不閉合 → closed=False，呼叫端必須**阻擋精確調度建議**（fail-closed），
#        不得自行補平、不得為湊 100% 正規化、不得把未歸類項塞進任一桶。
# ════════════════════════════════════════════════════════════════════════════
MAIN_BUCKETS = ("台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網")
_SUBKEY_SUFFIX = ("_科技", "_非科技")      # 美股子集，非獨立桶（重複計算陷阱）
SAT_KEYWORDS = ("黃金", "健康")            # 衛星（2026-09-03 已從美股主桶移出獨立回報）


def asset_decomposition(snap: dict) -> dict:
    """資產分解唯一入口（五桶／衛星／在途／指定款／未歸類，含分母與閉合判定）。

    回傳：
      總資產、五桶(dict)、五桶合計、衛星(dict)、衛星合計、在途、指定款、
      已歸類合計、未歸類、未歸類明細(dict)、缺口、closed(bool)、分母、說明
    缺 `total_assets` 或 `penetration.actual_twd` → raise（不以 0 冒充，fail-closed）。
    """
    if not isinstance(snap, dict):
        raise ValueError("asset_decomposition 需要 snapshot dict")
    _tot = snap.get("total_assets")
    if not isinstance(_tot, (int, float)) or _tot <= 0:
        raise ValueError("資產分解缺真值：total_assets（拒絕計算）")
    _atwd = (snap.get("penetration") or {}).get("actual_twd")
    if not isinstance(_atwd, dict) or not _atwd:
        raise ValueError("資產分解缺真值：penetration.actual_twd（拒絕計算）")

    _five = {k: float(_atwd.get(k) or 0) for k in MAIN_BUCKETS}
    _five_sum = sum(_five.values())
    # 衛星：優先讀 penetration.satellite_twd（工單B 新增的獨立鍵）；缺則由 actual_twd 名稱掃描。
    # 其餘鍵：子集鍵（_科技/_非科技）不計；含「指定/在途/restricted」者不計（各自另有來源，
    # 避免雙重計算）；其餘列為未歸類明細。
    _sat, _unclassified = {}, {}
    _sat_src = (snap.get("penetration") or {}).get("satellite_twd")
    if isinstance(_sat_src, dict) and _sat_src:
        _sat = {k: float(v or 0) for k, v in _sat_src.items()}
    for k, v in _atwd.items():
        if k in MAIN_BUCKETS or any(k.endswith(s) for s in _SUBKEY_SUFFIX):
            continue
        if k in _sat:
            continue
        if any(w in k for w in ("指定", "在途", "restricted", "transit")):
            continue
        if any(w in k for w in SAT_KEYWORDS):
            _sat[k] = float(v or 0)
        else:
            _unclassified[k] = float(v or 0)

    _transit = float((snap.get("penetration") or {}).get("cash_in_transit") or 0)
    _restricted = float(restricted_cash(snap) or 0)      # 指定用途款（不在桶位內）
    _sat_sum = sum(_sat.values())
    _classified = _five_sum + _sat_sum + _transit + _restricted
    _other = _tot - _classified
    _closed = abs(_other) <= 1.0                          # 允許 1 元四捨五入
    return {
        "總資產": float(_tot),
        "五桶": _five, "五桶合計": _five_sum,
        "衛星": _sat, "衛星合計": _sat_sum,
        "在途": _transit,
        "指定款": _restricted,
        "已歸類合計": _classified,
        "未歸類": _other,
        "未歸類明細": _unclassified,
        "closed": _closed,
        "分母": "snapshot.total_assets",
        "說明": ("五桶＋衛星＋在途＋指定用途款＝總資產（不變量）；未歸類 >1 元＝closed=False → "
                 "呼叫端必須阻擋精確調度建議，不得補平或正規化"),
    }


def asset_decomposition_line(snap: dict) -> str:
    """單行揭露字串（週報／eval 共用）——五桶只佔 93.4% 時必須交代其餘部分。"""
    d = asset_decomposition(snap)
    _tot = d["總資產"] or 1
    _parts = [f"五桶 {d['五桶合計']:,.0f}（{d['五桶合計'] / _tot * 100:.2f}%）"]
    if d["衛星合計"]:
        _parts.append(f"衛星 {d['衛星合計']:,.0f}（{d['衛星合計'] / _tot * 100:.2f}%）")
    if d["在途"]:
        _parts.append(f"在途 {d['在途']:,.0f}")
    if d["指定款"]:
        _parts.append(f"指定用途款 {d['指定款']:,.0f}（不列桶位）")
    if d["未歸類明細"]:
        _parts.append("＋".join(f"未歸類:{k} {v:,.0f}" for k, v in d["未歸類明細"].items()))
    elif abs(d["未歸類"]) > 1:
        _parts.append(f"未歸類 {d['未歸類']:,.0f}")
    _tail = (f"＝ 總資產 {d['總資產']:,.0f}（{d['分母']}）✅ 不變量閉合"
             if d["closed"] else
             f"≠ 總資產 {d['總資產']:,.0f}（差 {d['未歸類']:,.0f}）⚠️ 不變量未閉合 → 阻擋精確調度建議")
    return "｜".join(_parts) + " " + _tail


def scheduling_fields(snap: dict, us30y: float | None = None, sellable_twd: dict | None = None) -> dict:
    """調度欄位（結構化）＝程式產生，報告只引用（2026-10-11 工單E）。

    使用者裁決：每個調度建議都必須有程式計算依據；理論金額**不得**冒充可執行金額；
    逢反彈紀律（單次≤200,000、4–6 週）必須保留**政策來源**，不得只把文字變成常數。
    缺必要資料或煞車／凍結生效 → 如實輸出阻擋狀態（fail-closed）。

    回傳 {桶: {...}}，每桶欄位：現況_pct／戰略目標_pct／戰略偏差_pp／戰術目標_pct／戰術偏差_pp／
    分母_twd／理論調整金額_twd／公式／單筆上限_twd／風控後可執行金額_twd／阻擋規則名稱／
    可執行(bool)／來源(dict)。
    """
    _tot = snap.get("total_assets")
    if not isinstance(_tot, (int, float)) or _tot <= 0:
        raise ValueError("調度欄位缺真值：total_assets（拒絕計算）")
    _thr = snap.get("thresholds_2026_0915") or {}
    _tgt = _thr.get("桶目標_pct") or {}
    _tac = _thr.get("桶戰術目標_pct") or {}          # SoT 未定義時為空 → 戰術偏差標「不計算」
    _lad = _thr.get("動作階梯_pp") or {}
    _hard = _thr.get("單桶硬上限_pct") or {}
    _exe = _thr.get("減碼可執行性") or {}
    _brake = _thr.get("風險煞車") or {}
    _apct = (snap.get("penetration") or {}).get("actual_pct") or {}

    # 逢反彈紀律：政策來源必須跟著常數走（使用者 2026-08-22 裁示）
    _single_cap = {
        "金額": 200000,
        "週數": "4-6",
        "來源": "使用者 2026-08-22 裁示（美股逢反彈分批減碼，單次≤20萬／4-6 週完成）",
        "衝突": (f"thresholds.動作階梯_pp.單筆上限_twd={_lad.get('單筆上限_twd')}"
                 if _lad.get("單筆上限_twd") and _lad.get("單筆上限_twd") != 200000 else None),
    }
    _brake_on = bool(us30y is not None and isinstance(_brake.get("us30y_pct"), (int, float))
                     and us30y >= _brake["us30y_pct"])
    _brake_name = (f"US30Y 煞車（{_brake.get('us30y_pct')}%，連 {_brake.get('us30y_連續日')} 日；"
                   f"優先於動作階梯與單桶硬上限）") if _brake_on else ""
    _exe_name = (f"可減部位限制（{_exe.get('可減部位', '非後收/非保單內/無CDSC')}）"
                 f"→ 不可減部位處理：{_exe.get('不可減部位處理', '停新增＋配息導流')}")

    _mapping = {"台股市值型成長": "台股市值型", "美股市值型成長": "美股市值型",
                "防守型配息": "防守型配息", "債券": "債券", "現金/安全網": "現金"}
    out = {}
    for _pen_name, _sot_name in _mapping.items():
        _cur = _apct.get(_pen_name)
        _st = _tgt.get(_sot_name)
        if not isinstance(_cur, (int, float)) or not isinstance(_st, (int, float)):
            out[_pen_name] = {"現況_pct": _cur, "戰略目標_pct": _st, "戰略偏差_pp": None,
                              "戰術目標_pct": None, "戰術偏差_pp": None,
                              "理論調整金額_twd": None, "風控後可執行金額_twd": None,
                              "可執行": False, "阻擋規則名稱": ["缺真值（現況或戰略目標）→ 不計算"],
                              "來源": {"現況": "penetration.actual_pct", "戰略目標": "thresholds.桶目標_pct"}}
            continue
        _dev = round(_cur - _st, 1)
        _theo = int(round(abs(_dev) / 100 * float(_tot)))          # 理論調整金額（雙向）
        _tac_t = _tac.get(_sot_name)
        _blocks = []
        if _brake_name:
            _blocks.append(_brake_name)
        _cap = _single_cap["金額"]
        _sell = (sellable_twd or {}).get(_pen_name)
        _exec_amt = _theo
        if _dev <= 0:
            _exec_amt = 0
            _blocks.append("方向為加碼 → 受現金底線/凍結規則約束（非減碼路徑）")
        if _brake_on:
            _exec_amt = 0
        if _theo > _cap:
            _exec_amt = min(_exec_amt, _cap)
            _blocks.append(f"單筆上限（{_cap:,}）封頂：理論 {_theo:,} > 上限")
        if isinstance(_sell, (int, float)):
            if _exec_amt > _sell:
                _exec_amt = int(_sell)
                _blocks.append(f"可動部位（{_sell:,.0f}）封頂")
            if _sell <= 0:
                _exec_amt = 0
        else:
            _blocks.append("可減部位未提供 → 不計算可執行金額（fail-closed）")
            _exec_amt = 0
        if _hard.get(_sot_name) is not None and _cur > _hard[_sot_name]:
            _blocks.append(f"已破單桶硬上限 {_hard[_sot_name]}%")
        out[_pen_name] = {
            "現況_pct": _cur,
            "戰略目標_pct": _st,
            "戰略偏差_pp": _dev,
            "戰術目標_pct": _tac_t,
            "戰術偏差_pp": (round(_cur - _tac_t, 1) if isinstance(_tac_t, (int, float)) else None),
            "戰術來源": ("thresholds.桶戰術目標_pct" if isinstance(_tac_t, (int, float))
                         else "無 SoT（週報曾引用『戰術 27%』但 thresholds 無此鍵）→ 不計算"),
            "分母_twd": float(_tot), "分母來源": "snapshot.total_assets",
            "理論調整金額_twd": _theo,
            "公式": "|戰略偏差_pp| ÷ 100 × 分母_twd",
            "單筆上限_twd": _cap, "單筆上限來源": _single_cap,
            "可動部位_twd": _sell,
            "風控後可執行金額_twd": int(_exec_amt),
            "阻擋規則名稱": _blocks,
            "可執行": bool(_exec_amt > 0 and not _brake_on),
            "來源": {"現況": "penetration.actual_pct", "戰略目標": "thresholds_2026_0915.桶目標_pct",
                     "階梯": "thresholds_2026_0915.動作階梯_pp",
                     "硬上限": "thresholds_2026_0915.單桶硬上限_pct",
                     "執行性": "thresholds_2026_0915.減碼可執行性",
                     "煞車": "thresholds_2026_0915.風險煞車"},
        }
    return out


def band_conflicts(snap: dict) -> list:
    """「目標值落在自身可接受範圍之外」的桶（2026-10-11 一次性工單 D）。

    使用者裁決（2026-10-11）：**不自選值修訂**。25%（`thresholds_2026_0915.桶目標_pct.債券`）
    與 27–33%（2026-10-02 裁示② `snapshot.可接受範圍_pct`）都是可追溯的正式設定，衝突屬
    「策略裁決層」→ 本函式只**偵測並揭露**，不改任何值；偵測到即 fail-closed：
    該桶不得自動交易（呼叫端須據此把動作降為「待裁示」且金額 0），且報告不得把目標寫成上限。
    """
    out: list = []
    try:
        bands = acceptable_band(snap)
    except Exception:
        return out
    for name, cfg in (bands or {}).items():
        tgt, lo, hi = cfg.get("目標"), cfg.get("下限"), cfg.get("上限")
        if not isinstance(tgt, (int, float)):
            continue
        _c = ""
        if isinstance(lo, (int, float)) and tgt < lo:
            _c = f"目標 {tgt:g}% < 下限 {lo:g}%"
        elif isinstance(hi, (int, float)) and tgt > hi:
            _c = f"目標 {tgt:g}% > 上限 {hi:g}%"
        if _c:
            out.append({
                "桶": name, "目標": tgt, "下限": lo, "上限": hi, "衝突": _c,
                "來源": ("snapshot.可接受範圍_pct（2026-10-02 使用者裁示②）"
                         f" vs thresholds_2026_0915.桶目標_pct（{tgt:g}%）"),
                "處置": "待使用者裁決；裁決前本桶自動交易 fail-closed（動作降為待裁示、金額 0）",
                "禁止": "不得自行改目標或改範圍以求一致；不得把目標值敘述為『上限』",
            })
    return out


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
         + format(d["門檻_pct"], ",.0f") + "%)")
    return s


# ═══════════════════════════════════════════════════════════════
# PI 專業投資人｜雙軌模型（使用者 2026-10-04 裁決，規格 PI_DATA_LIFECYCLE_SPEC.md）
#   ① 財力軌（proxy vs 法規門檻）與 ② 資格軌（application／approval）**完全分離**。
#      資產達標 ≠ PI 已核准；只有 approval_status == "已核准" 可解鎖 Lombard／entry hard lock。
#   ② 門檻＝外部法規常數，唯一位置在本模組，**不進 snapshot、不 fail-closed**。
#   ③ 財力 proxy 為「本系統內部送件 readiness proxy」，**不等同**金融機構最終資格認定；
#      不得命名或對外宣稱為「法規認定資產」。
#   ④ proxy／gap／meets 一律**即時計算、不得落地儲存**
#      （避免再現 28,220,311 型 stale 假真值：落地值會隨資產變動而過期）。
#   ⑤ 頂層 snapshot.pi_status 與舊欄名「認列」已廢除。
# ═══════════════════════════════════════════════════════════════

PI_CONTAINER_KEY = "professional_investor"

# 金管會「專業投資人」自然人財力門檻（金融資產 3,000 萬元）──外部法規常數，唯一位置。
PI_REGULATORY_THRESHOLD_TWD = 30_000_000

# 兩軌狀態機（使用者 2026-10-04 裁決；application 4 態 + 終態「已完成」、approval 4 態＝共 9 值；
# 拒絕／失效不得塞回「未申請」）
PI_APPLICATION_STATES = ("未申請", "已送件", "補件中", "審核中", "已完成")
PI_APPROVAL_STATES = ("未核准", "已核准", "未通過", "失效")
PI_ALL_STATES = PI_APPLICATION_STATES + PI_APPROVAL_STATES


def pi_regulatory_threshold() -> int:
    """外部法規常數（專業投資人財力門檻）。不進 snapshot、不參與 fail-closed。"""
    return PI_REGULATORY_THRESHOLD_TWD


def pi_record(snap: dict) -> dict:
    """PI 唯一容器（snapshot.professional_investor）。缺值／狀態非法 → raise（fail-closed）。

    禁 `or {}`、禁預設「申請中」、禁由資產推導核准。
    """
    rec = (snap or {}).get(PI_CONTAINER_KEY)
    if not isinstance(rec, dict) or not rec:
        raise KeyError(
            f"snapshot 缺 {PI_CONTAINER_KEY} → PI 無真值，拒絕以預設值頂替"
            "（2026-10-04 PI 資料生命週期裁決；頂層 snapshot.pi_status／舊欄名「認列」已廢除）")
    for _k, _allowed in (("application_status", PI_APPLICATION_STATES),
                         ("approval_status", PI_APPROVAL_STATES)):
        _v = rec.get(_k)
        if not isinstance(_v, str) or not _v:
            raise KeyError(f"{PI_CONTAINER_KEY}.{_k} 缺值 → PI 狀態無真值，拒絕判斷")
        # 2026-10-04 CIO 審查：原用兩軌聯集（PI_ALL_STATES）驗證，會讓
        # approval_status="已完成" 這種跨軌值通過讀取驗證（語意污染）。改分軌驗證。
        if _v not in _allowed:
            raise KeyError(
                f"{PI_CONTAINER_KEY}.{_k}={_v!r} 非合法狀態（合法：{'／'.join(_allowed)}）"
                "→ 拒絕回退為「未申請」（禁 fail-open）")
    return rec


def pi_application_status(snap: dict) -> str:
    """送件流程狀態（未申請／已送件／補件中／審核中）。"""
    return pi_record(snap)["application_status"]


def pi_approval_status(snap: dict) -> str:
    """資格核准結果（未核准／已核准／未通過／失效）。"""
    return pi_record(snap)["approval_status"]


def pi_financial_asset_proxy(snap: dict) -> float:
    """PI 財力檢核口徑（內部 readiness proxy）＝證券＋基金＋保單＋現金（含存款）。

    口徑裁決：使用者 2026-10-04（含現金）。**即時計算、不落地**。
    本值為系統內部 proxy，不等同金融機構最終資格認定。
    """
    return (securities_total(snap) + funds_total(snap)
            + insurance_total(snap) + total_cash(snap))


def pi_gap_twd(snap: dict) -> float:
    """距財力門檻缺口（達標為 0）。僅為財力檢核，**不構成資格判定**。"""
    return max(0.0, float(PI_REGULATORY_THRESHOLD_TWD) - pi_financial_asset_proxy(snap))


def pi_meets_financial_threshold(snap: dict) -> bool:
    """財力 proxy 是否達門檻。**不得**用來推導 PI 已核准（第五測）。"""
    return pi_financial_asset_proxy(snap) >= float(PI_REGULATORY_THRESHOLD_TWD)


def pi_is_approved(snap: dict) -> bool:
    """PI hard lock 的唯一解鎖條件：approval_status == '已核准'。不得由資產推導。"""
    return pi_approval_status(snap) == "已核准"


# ── 質押事實 accessor（2026-10-04：professional_investor.deployment_plan 廢除後，
#    LTV／擔保池／借款金額的唯一來源。禁再由 PI 容器或寫死值推導）──────────────
def pledge_loan_twd(snap: dict) -> float:
    """實際動用額（＝snapshot.fund_pledge_loan；與 DB liabilities.pledge_loan 同源）。"""
    return float((snap or {}).get("fund_pledge_loan") or 0)


def pledge_collateral_market_value(snap: dict) -> float:
    """質押品市值：優先用 擔保池.合計（該筆質押專屬），退回國泰基金總市值。"""
    cp = (snap or {}).get("cathay_pledge_0911") or {}
    pool = cp.get("擔保池") or {}
    v = pool.get("合計") if isinstance(pool, dict) else None
    return float(v or (snap or {}).get("funds_cathay_market_value") or 0)


def pledge_ltv(snap: dict) -> float:
    """LTV＝實際動用 ÷ 質押品市值。無質押（任一為 0）→ 0.0。"""
    mv = pledge_collateral_market_value(snap)
    ln = pledge_loan_twd(snap)
    return (ln / mv) if (mv and ln) else 0.0


def mortgage_principal_cathay(snap: dict) -> float | None:
    """國泰（大義街）房貸本金權威鍵＝snapshot.mortgage_cathay。

    2026-10-04：原槓桿風控卡以 professional_investor.deployment_plan.total 讀取房貸本金，
    該容器隨 PI 收斂廢除後，該行退化成常量 12,000,000 fallback（假真值）。
    改為單一 accessor。缺值 → **None**（禁回退常量、禁退 0；呼叫端須明示缺值或略過該層）。
    語意邊界：**明確的 0 是「真的沒有房貸」**（真值存在）→ 回 0.0；只有缺鍵／空字串／
    無法解析（None、''、'abc'）才回 None。
    """
    v = (snap or {}).get("mortgage_cathay")
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def pledge_truth_present(snap: dict) -> bool:
    """質押事實是否具備真值（鍵存在、可解析、且質押品市值 > 0）。

    2026-10-04：質押 accessor（pledge_loan_twd／pledge_collateral_market_value）為
    「無質押 → 0」語意；缺鍵時也回 0，無法與「真的沒質押」區分 → 這是 fail-open 的縫。
    呼叫端要 fail-closed 時必須先問本函式，缺真值時顯示缺值、不得顯示 0 或估算。
    """
    s = snap or {}
    if "fund_pledge_loan" not in s:
        return False
    try:
        float(s.get("fund_pledge_loan"))
    except (TypeError, ValueError):
        return False
    return pledge_collateral_market_value(s) > 0


# ── 質押池逐池 LTV（2026-10-14 第 0 批 R1；使用者裁決 §0-R1）───────────────
# 裁決：①不可只新增欄位——須證明每個質押池 LTV **獨立判定**（各池分別判定，不加總平均）
#       ②門檻一律讀 thresholds_2026_0915.ltv分級_pct（禁硬編碼）
#       ③缺門檻或缺資料時 **不得默認綠燈**（fail-closed）
LTV_GRADE_KEYS = ("綠上限", "黃上限", "單池上限", "追繳")


def _finite(v):
    """有限數才回傳；其餘（None／''／'abc'／NaN／±Inf）回 None。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def ltv_grades(snap: dict) -> dict:
    """LTV 分級門檻（單一來源＝thresholds_2026_0915.ltv分級_pct）。

    任一鍵缺失／非數值／順序無效（需 0 < 綠上限 ≤ 單池上限 ≤ 黃上限 ≤ 追繳 ≤ 100）
    → 回 {}。呼叫端**必須**報「門檻不可得」，不得套用預設值、不得默認綠燈。
    """
    g = ((snap or {}).get(SOT_KEY) or {}).get("ltv分級_pct")
    if not isinstance(g, dict):
        return {}
    out = {}
    for k in LTV_GRADE_KEYS:
        v = _finite(g.get(k))
        if v is None:
            return {}
        out[k] = v
    if not (0 < out["綠上限"] <= out["單池上限"] <= out["黃上限"] <= out["追繳"] <= 100):
        return {}
    out["判定單位"] = str(g.get("判定單位")
                          or "各池分別判定（不加總平均；追繳看單池）")
    return out


def ltv_grade_of(ltv, grades: dict) -> str:
    """單池 LTV → 分級字串。門檻或 LTV 不可得 → 'unverified'（不得回綠燈）。

    ≥追繳 → 追繳｜≥黃上限 → 禁新增質押｜>單池上限 → 超限｜≤綠上限 → 正常｜
    其餘（綠上限, 單池上限] → 未定義區間（門檻未定義動作，只顯示不升級）
    """
    if ltv is None or not grades:
        return "unverified"
    if ltv >= grades["追繳"]:
        return "追繳"
    if ltv >= grades["黃上限"]:
        return "禁新增質押"
    if ltv > grades["單池上限"]:
        return "超限"
    if ltv <= grades["綠上限"]:
        return "正常"
    return "未定義區間"


# (池名, 借款真值來源, 擔保品真值來源)
PLEDGE_POOLS = (
    ("國泰基金質押池", "fund_pledge_loan",
     "cathay_pledge_0911.擔保池.合計／funds_cathay_market_value"),
    ("券商質押池", "liabilities_build_up.券商質押", "（未建池別真值）"),
    ("保單借貸池", "policy_pledge_loan", "（未建池別真值）"),
)


def pledge_pools(snap: dict) -> list:
    """質押池逐池 LTV：每池獨立一列，**不得**以加總平均或取最大值代替逐池判定。

    回傳 list[dict]：{池名, 借款_twd, 擔保品市值_twd, ltv_pct, 分級, 真值, 說明,
                     借款來源, 擔保品來源}
    fail-closed：
      - 借款 > 0 但擔保品市值不可得／≤ 0 → 分級 'unverified'、真值 False
      - LTV 門檻不可得（ltv分級_pct 無效）→ 有借款的池一律 'unverified'
      - 借款不可得或 ≤ 0 → 分級 '無借款'、真值 True（該池確實無借款，非判定失敗）
    """
    s = snap or {}
    grades = ltv_grades(s)
    lb = s.get("liabilities_build_up") or {}
    rows = []
    for name, borrow_src, coll_src in PLEDGE_POOLS:
        if name.startswith("國泰"):
            borrow = _finite(s.get("fund_pledge_loan"))
            coll = _finite(pledge_collateral_market_value(s))
        elif name.startswith("券商"):
            borrow = _finite(lb.get("券商質押"))
            coll = None
        else:
            borrow = _finite(s.get("policy_pledge_loan"))
            coll = None

        row = {"池名": name, "借款_twd": borrow, "擔保品市值_twd": coll,
               "ltv_pct": None, "分級": "unverified", "真值": False, "說明": "",
               "借款來源": borrow_src, "擔保品來源": coll_src}

        if borrow is None or borrow <= 0:
            row["分級"], row["真值"] = "無借款", True
            row["說明"] = "無借款（不判定）"
            rows.append(row)
            continue

        if coll is None or coll <= 0:
            row["說明"] = ("借款 > 0 但擔保品市值不可得 → 無法判定"
                           "（fail-closed：不得默認綠燈、不得估算）")
            rows.append(row)
            continue

        row["ltv_pct"] = round(borrow / coll * 100, 2)
        row["真值"] = True
        if not grades:
            row["真值"] = False
            row["說明"] = ("LTV 門檻不可得（thresholds_2026_0915.ltv分級_pct）"
                           "→ 無法分級（不得默認綠燈）")
        else:
            row["分級"] = ltv_grade_of(row["ltv_pct"], grades)
            if row["分級"] == "未定義區間":
                row["說明"] = ("介於綠上限與單池上限之間；門檻未定義動作"
                               "（只顯示，不升級）")
        rows.append(row)
    return rows
