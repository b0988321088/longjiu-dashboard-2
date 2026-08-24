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

if __name__ == "__main__":
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
