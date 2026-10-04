"""國泰房貸利率／月付 單一來源（2026-10-01）
避免同一數字散落多支產生器各自寫死（INC-267 型靜默失效）。
優先序：snapshot.mortgage_cathay_rate（權威鍵）→ monthly_fixed_expense['房貸_國泰']×12/本金
2026-10-04 P0（CIO 六審）：兩者皆缺 → 回 None（缺真值）並由呼叫端明示，**禁以 0.026／26,000 編造**
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def load_snapshot(snap=None):
    if isinstance(snap, dict) and snap:
        return snap
    try:
        return json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def cathay_rate(snap=None):
    """國泰轉貸年利率（小數，如 0.026）"""
    s = load_snapshot(snap)
    r = float(s.get("mortgage_cathay_rate") or 0)
    if r:
        return r
    mf = float((s.get("monthly_fixed_expense") or {}).get("房貸_國泰") or 0)
    pr = float(s.get("mortgage_cathay") or 0)
    # 2026-10-04 P0：原 else FALLBACK_RATE（0.026）＝缺真值時編造 2.6% → 改回 None
    return (mf * 12 / pr) if (mf and pr) else None


def cathay_rate_pct(snap=None, digits=1):
    """國泰轉貸年利率（百分比字串，如 '2.6'）"""
    _r = cathay_rate(snap)
    return f"{_r * 100:.{digits}f}" if _r is not None else "⚠️ 缺真值"


def cathay_principal(snap=None):
    return float(load_snapshot(snap).get("mortgage_cathay") or 0)


def cathay_wan(snap=None):
    """國泰轉貸本金（萬元，整數字串，如 '1200'）"""
    return f"{cathay_principal(snap) / 10000:,.0f}"


def cathay_monthly(snap=None):
    """寬限期月付＝本金×利率/12（單一來源）；本金缺值時才退回 snapshot 存放的月付鍵"""
    s = load_snapshot(snap)
    pr = cathay_principal(s)
    _r = cathay_rate(s)
    # 2026-10-04 P0（CIO 六審）：原 `or 26000` 為硬編碼假月付；利率缺真值亦不得派生 → 回 None
    if pr > 0:
        return round(pr * _r / 12) if _r is not None else None
    _mf = float(s.get("mortgage_cathay_monthly") or 0)
    return round(_mf) if _mf else None


def reconcile_stored_monthly(snap):
    """把「重複存放的國泰月付鍵」同步成派生值（rate×本金/12），消除第二來源漂移。
    影響鍵：snapshot.mortgage_cathay_monthly、monthly_fixed_expense['房貸_國泰']，
    以及（僅在原本自洽 合計 == 各項加總 時才重算的）monthly_fixed_expense['合計']。
    ⚠️ 合計不自洽時只回報不改 —— 不覆蓋使用者定版值。
    回傳 [(鍵路徑, 舊值, 新值), ...]（就地修改 snap，由呼叫端的 snapshot 單一寫入者落盤）。"""
    if not isinstance(snap, dict) or not snap:
        return []
    m = cathay_monthly(snap)
    if m is None:
        print("⚠️ [mortgage_rate] 國泰月付缺真值（利率／本金／月付鍵皆缺）→ **不寫入**月付鍵（不編造）")
        return []
    mfe = snap.get("monthly_fixed_expense")
    # 合計＝下表各項加總（與 check_thresholds 同口徑；差旅費 10,000 等「註記型」項不計入，
    # 故不可用「全部數值鍵加總」，否則會對不上而每次都誤發警告）
    _parts = ("生活支出", "醫療_常態回診", "房貸_永豐", "房貸_國泰",
              "保單借貸利息", "券商質押利息", "基金質押利息")
    _ok = isinstance(mfe, dict) and all(k in mfe for k in _parts)
    _old_sum = sum(mfe[k] for k in _parts) if _ok else None     # ⚠️ 必須在改動任何項之前先算
    _old_total = mfe.get("合計") if isinstance(mfe, dict) else None
    changes = []
    if snap.get("mortgage_cathay_monthly") != m:
        changes.append(("mortgage_cathay_monthly", snap.get("mortgage_cathay_monthly"), m))
        snap["mortgage_cathay_monthly"] = m
    if isinstance(mfe, dict) and mfe.get("房貸_國泰") != m:
        changes.append(("monthly_fixed_expense.房貸_國泰", mfe.get("房貸_國泰"), m))
        mfe["房貸_國泰"] = m
    if _ok and _old_total is not None:
        if _old_total == _old_sum:              # 原本自洽 → 跟著重算
            _new_sum = sum(mfe[k] for k in _parts)
            if _new_sum != _old_total:
                changes.append(("monthly_fixed_expense.合計", _old_total, _new_sum))
                mfe["合計"] = _new_sum
        else:                                   # 原本就不自洽 → 只回報不改（不覆蓋定版值）
            print(f"  ⚠️ monthly_fixed_expense 合計（{_old_total}）≠ 各項加總（{_old_sum}）"
                  f" → 只同步國泰月付、不重算合計（請人工確認定版值）")
    return changes


def yongfeng_rate(snap=None):
    return float(load_snapshot(snap).get("mortgage_yy_rate") or 0.025)


def yongfeng_principal(snap=None):
    s = load_snapshot(snap)
    return sum(float(s.get(k) or 0) for k in ("mortgage_yy", "mortgage_yydu", "mortgage_xz"))
