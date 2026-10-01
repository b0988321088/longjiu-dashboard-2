"""國泰房貸利率／月付 單一來源（2026-10-01）
避免同一數字散落多支產生器各自寫死（INC-267 型靜默失效）。
優先序：snapshot.mortgage_cathay_rate（權威鍵）→ monthly_fixed_expense['房貸_國泰']×12/本金 → 0.026
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
FALLBACK_RATE = 0.026


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
    return (mf * 12 / pr) if (mf and pr) else FALLBACK_RATE


def cathay_rate_pct(snap=None, digits=1):
    """國泰轉貸年利率（百分比字串，如 '2.6'）"""
    return f"{cathay_rate(snap) * 100:.{digits}f}"


def cathay_principal(snap=None):
    return float(load_snapshot(snap).get("mortgage_cathay") or 0)


def cathay_wan(snap=None):
    """國泰轉貸本金（萬元，整數字串，如 '1200'）"""
    return f"{cathay_principal(snap) / 10000:,.0f}"


def cathay_monthly(snap=None):
    """寬限期月付＝本金×利率/12"""
    return round(cathay_principal(snap) * cathay_rate(snap) / 12)


def yongfeng_rate(snap=None):
    return float(load_snapshot(snap).get("mortgage_yy_rate") or 0.025)


def yongfeng_principal(snap=None):
    s = load_snapshot(snap)
    return sum(float(s.get(k) or 0) for k in ("mortgage_yy", "mortgage_yydu", "mortgage_xz"))
