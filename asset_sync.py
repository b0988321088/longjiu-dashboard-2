#!/usr/bin/env python3
"""asset_sync.py — 欄位同步函數（P0-1 防呆）
更新 snapshot 資產時，自動同步所有「同義欄位」，避免漏改導致穿透/日報不一致。

用法：
    from asset_sync import update_asset, sync_snapshot_keys
    update_asset(snapshot, insurance=9891257, securities=2887310, funds=772694, cash=2914656)
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 同義欄位對照（key 群組，全部要同步）
SYNONYM_GROUPS = {
    # 保險總值
    "insurance_total": ["insurance_total", "insurance_current_value", "insurance"],
    # 證券總值（含 8/24 新增 securities_current_value）
    "securities_total": ["securities_total_market_value", "securities_total", "securities_market", "securities_current_value"],
    # 基金總值（5 個 key + 國泰基金市值 8/24 新增）
    "funds_total": ["fund_market", "fund_market_value", "funds_total", "fund_total_market_value", "funds"],
    "funds_cathay": ["funds_cathay", "funds_cathay_market_value"],
    # 現金總值（4 個 key）
    "cash_total": ["cash_total", "cash", "real_liquid_assets", "bank_assets_moneybook"],
    # 安聯 A+B
    "allianz_combined": ["allianz_combined", "allianz_ab_current_value", "allianz_ab"],
    # 第一金
    "firstjin_total": ["firstjin_fl65_current_value", "firstjin_current_value", "firstjin"],
}

def sync_snapshot_keys(snap: dict) -> dict:
    """根據主 key 值，同步所有同義欄位"""
    for master, keys in SYNONYM_GROUPS.items():
        val = snap.get(master)
        if val is None:
            # 從其他 key 找回
            for k in keys:
                if snap.get(k) is not None:
                    val = snap[k]
                    break
        if val is not None:
            for k in keys:
                snap[k] = val
    return snap

def update_asset(snap: dict, insurance=None, securities=None, funds=None, cash=None,
                 allianz_combined=None, firstjin=None) -> dict:
    """更新資產並自動同步同義欄位 + 重算總資產"""
    if insurance is not None:
        snap["insurance_total"] = insurance
    if securities is not None:
        snap["securities_total_market_value"] = securities
    if funds is not None:
        snap["fund_market"] = funds
    if cash is not None:
        snap["cash_total"] = cash
    if allianz_combined is not None:
        snap["allianz_combined"] = allianz_combined
    if firstjin is not None:
        snap["firstjin_fl65_current_value"] = firstjin

    snap = sync_snapshot_keys(snap)

    # 總資產重算 = 保險 + 證券 + 基金 + 現金
    ins = snap.get("insurance_total", 0) or 0
    sec = snap.get("securities_total_market_value", 0) or 0
    fund = snap.get("fund_market", 0) or 0
    cashv = snap.get("cash_total", 0) or 0
    snap["total_assets"] = ins + sec + fund + cashv
    return snap

def verify_synonyms(snap: dict) -> list:
    """檢查同義欄位是否一致，回傳不一致清單"""
    issues = []
    for master, keys in SYNONYM_GROUPS.items():
        vals = {k: snap.get(k) for k in keys}
        non_none = [v for v in vals.values() if v is not None]
        if non_none and len(set(non_none)) > 1:
            issues.append(f"{master}: {vals}")
    return issues


# ─────────────────────────────────────────────────────────────
# 負債模型（2026-09-13 INC-159 P2）：負債由組成明細推導，禁手寫
# 背景：total_liabilities / net_worth / cc_liability 原本全系統沒有任何計算來源
# （grep 全 repo 無 assignment）→ 每次靠手寫，導致 78,099 無法解釋的殘差、
# cc_liability 停在 28,101、DB 與 snapshot 卡片金額不一致。
# 口徑（使用者 2026-09-13 明示）：無循環利息、每月全額自動扣繳 →
#   信用卡負債 = credit_card dict 負值合計（當期未繳，將被全額扣掉）
# ─────────────────────────────────────────────────────────────
INCLUDE_PERSONAL_LOANS = True    # 2026-09-13 使用者核可：女友借款計入總負債（用剩餘本金，非原始金額）
PERSONAL_LOAN_PAYDAY_DEFAULT = 5  # 每月 5 號還款（info 沒寫時用）


def personal_loan_remaining(info: dict, today=None) -> float:
    """女友借款「剩餘本金」=（原始金額 − 月還款 × 已過還款期數）。

    例：300,000（7/25 起、每月 5 號還 6,000）→ 9/13 已過 8/5、9/5 兩期 → 剩 288,000；
    12/5 最後一期後歸零（之後自動從負債表消失）。寫死 300,000 會一路錯到清償。
    """
    import datetime as _dt
    import re as _re
    amt = float(info.get("金額") or 0)
    pay = float(info.get("月還款") or 0)
    start = str(info.get("日期") or "")
    payday = int(_re.sub(r"\D", "", str(info.get("還款日") or "")) or PERSONAL_LOAN_PAYDAY_DEFAULT)
    if not (amt and pay and start):
        return amt
    try:
        d0 = _dt.date.fromisoformat(start)
    except Exception:
        return amt
    today = today or _dt.date.today()
    # 最後清償日（例：2026-12-05）→ 當天最後一期清掉餘額，之後歸零
    _final = str(info.get("最後清償") or "").strip()
    if _final:
        try:
            if today >= _dt.date.fromisoformat(_final):
                return 0.0
        except Exception:
            pass
    n, y, m = 0, d0.year, d0.month
    while (y, m) <= (today.year, today.month):
        try:
            pd = _dt.date(y, m, payday)
        except ValueError:
            pd = None
        if pd and d0 < pd <= today:
            n += 1
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return max(0.0, amt - pay * n)


def cc_unpaid(snap: dict) -> int:
    """信用卡當期未繳 = credit_card dict 負值合計。"""
    cc = snap.get("credit_card") or {}
    if not isinstance(cc, dict):
        return 0
    return int(abs(sum(v for v in cc.values() if isinstance(v, (int, float)) and v < 0)))


def rebuild_liabilities(snap: dict) -> dict:
    """由明細重建 cc_liability / total_liabilities / net_worth（冪等）。"""
    unpaid = cc_unpaid(snap)
    snap["credit_card_pending"] = unpaid
    snap["cc_liability"] = unpaid

    mort = snap.get("mortgage_balance") or snap.get("mortgage") or 0
    pol = snap.get("policy_loan") or 0
    ple = snap.get("pledge_loan") or 0
    _per_detail = {}
    if INCLUDE_PERSONAL_LOANS:
        pl = snap.get("personal_loans") or {}
        if isinstance(pl, dict):
            for _k, _v in pl.items():
                if isinstance(_v, dict):
                    _r = personal_loan_remaining(_v)
                    if _r > 0:
                        _per_detail[_k] = int(_r)
    per = sum(_per_detail.values())

    total = int(mort) + int(pol) + int(ple) + unpaid + int(per)
    snap["total_liabilities"] = total
    snap["liabilities_build_up"] = {
        "房貸_含國泰": int(mort),
        "保單借貸": int(pol),
        "券商質押": int(ple),
        "信用卡_當期未繳_全額扣繳": unpaid,
        "個人借款_剩餘本金": _per_detail,
        "total": total,
        "note": ("2026-09-13 建立：負債改由明細推導（原為手寫值，曾出現 78,099 不明殘差）；"
                 "個人借款用剩餘本金（每月 5 號還 6,000，12/5 歸零）"),
    }
    snap["net_worth"] = int(snap.get("total_assets") or 0) - total
    # 負債率雙軌（2026-08-10 使用者裁示格式）：含不動產主顯示 / 不含不動產流動監控
    _ta = float(snap.get("total_assets") or 0)
    _re = float(snap.get("real_estate_value") or 0)
    snap["debt_ratio"] = round(total / (_ta + _re) * 100, 1) if (_ta + _re) else 0
    snap["debt_ratio_flow"] = round(total / _ta * 100, 1) if _ta else 0
    return snap

if __name__ == "__main__":
    import sys as _sys
    if "--rebuild-liabilities" in _sys.argv:
        # 唯一入口：由明細重建 cc_liability / total_liabilities / net_worth / 負債率雙軌，
        # 並同步 DB assets.total_liabilities + liabilities 表（避免 snapshot/DB 再度分岔）
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        snap = rebuild_liabilities(snap)
        (BASE / "snapshot.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            import sqlite3
            _db = sqlite3.connect(str(BASE / "dragon_assets.db"))
            _t = __import__("datetime").date.today().isoformat()   # DB 以「執行日」為列（與 update_data 一致）
            _db.execute("UPDATE assets SET total_liabilities=?, total_assets=? WHERE date=?",
                        (snap["total_liabilities"], snap.get("total_assets"), _t))
            _lrow = (snap.get("mortgage_yy", 0), snap.get("mortgage_yydu", 0),
                     snap.get("mortgage_xz", 0), snap.get("policy_loan", 0),
                     snap.get("pledge_loan", 0), snap.get("cc_liability", 0),
                     snap.get("total_liabilities", 0), snap.get("mortgage_cathay", 0))
            if _db.execute("SELECT COUNT(*) FROM liabilities WHERE date=?", (_t,)).fetchone()[0]:
                _db.execute("""UPDATE liabilities SET mortgage_yy=?, mortgage_yydu=?, mortgage_xz=?,
                    policy_loan=?, pledge_loan=?, credit_card=?, total_liabilities=?, mortgage_cathay=?
                    WHERE date=?""", _lrow + (_t,))
            else:
                _db.execute("""INSERT INTO liabilities (mortgage_yy, mortgage_yydu, mortgage_xz,
                    policy_loan, pledge_loan, credit_card, total_liabilities, mortgage_cathay, date)
                    VALUES (?,?,?,?,?,?,?,?,?)""", _lrow + (_t,))
            _db.commit()
            print(f"✅ DB 已同步（{_t}）：assets.total_liabilities＋liabilities 表（信用卡 {snap['cc_liability']:,}）")
        except Exception as _e:
            print(f"⚠️ DB 同步失敗：{_e}")
        bu = snap["liabilities_build_up"]
        print(f"✅ 負債重建：房貸 {bu['房貸_含國泰']:,} + 保單 {bu['保單借貸']:,}"
              f" + 質押 {bu['券商質押']:,} + 信用卡 {bu['信用卡_當期未繳_全額扣繳']:,}"
              f" = {snap['total_liabilities']:,}")
        print(f"   淨值 {snap['net_worth']:,}｜負債率 {snap['debt_ratio']}%（含不動產）"
              f"／{snap['debt_ratio_flow']}%（流動）")
        _sys.exit(0)
    # 自檢
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    issues = verify_synonyms(snap)
    if issues:
        print("❌ 同義欄位不一致：")
        for i in issues:
            print(f"  {i}")
    else:
        print("✅ 所有同義欄位一致")
    print(f"  總資產: {snap.get('total_assets'):,}")
