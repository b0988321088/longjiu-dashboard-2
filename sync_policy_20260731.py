"""2026-07-31 保單截圖同步 — 更新 snapshot.json 安聯A/B 成分與現值"""
import json
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
SNAP = BASE / "snapshot.json"
snap = json.loads(SNAP.read_text(encoding="utf-8"))

# ===== 截圖真值（2026-07-31）=====
A_TOTAL = 4_997_734
B_TOTAL = 2_647_289
AB_TOTAL = A_TOTAL + B_TOTAL  # 7,645,023（App 帳戶總價值一致）

# 安聯A (QL18610694) — 5 檔
A_FUNDS = {
    "安聯收益成長":    {"value": 715_842,  "code": "USDEQ3490", "performance_pct": -2.54},
    "M&G入息":         {"value": 1_069_377, "code": "USDEQ5700", "performance_pct": -0.68},
    "貝萊德世界科技A10": {"value": 1_176_673, "code": "USDEQ6080", "performance_pct": -0.80},
    "安聯AI收益成長":   {"value": 352_357,  "code": "USDEQ6270", "performance_pct": 2.00},
    "PIMCO收益增長":    {"value": 1_683_485, "code": "USDEQ6550", "performance_pct": -0.18},
}
# 安聯B (QL18488224) — 4 檔（M&G/聯博已轉出）
B_FUNDS = {
    "安聯收益成長":    {"value": 504_880,  "code": "USDEQ3490", "performance_pct": -2.54},
    "貝萊德世界科技A10": {"value": 656_363,  "code": "USDEQ6080", "performance_pct": 2.42},
    "安聯AI收益成長":   {"value": 533_212,  "code": "USDEQ6270", "performance_pct": 2.00},
    "PIMCO收益增長":    {"value": 952_834,  "code": "USDEQ6550", "performance_pct": -0.18},
}
assert sum(v["value"] for v in A_FUNDS.values()) == A_TOTAL, "安聯A 總和不等於截圖"
assert sum(v["value"] for v in B_FUNDS.values()) == B_TOTAL, "安聯B 總和不等於截圖"

# ===== 1. breakdown 明細 =====
snap["allianz_a_breakdown"] = {k: v["value"] for k, v in A_FUNDS.items()}
snap["allianz_b_breakdown"] = {k: v["value"] for k, v in B_FUNDS.items()}

# ===== 2. 現值總額（同步所有相容 key）=====
snap["allianz_a_current_value"] = A_TOTAL
snap["allianz_a"] = A_TOTAL
snap["allianz_a_value"] = A_TOTAL
snap["allianz_policy_a_value"] = A_TOTAL
snap["allianz_b_current_value"] = B_TOTAL
snap["allianz_b"] = B_TOTAL
snap["allianz_b_value"] = B_TOTAL
snap["allianz_policy_b_value"] = B_TOTAL
snap["allianz_ab_current_value"] = AB_TOTAL
snap["allianz_ab"] = AB_TOTAL
snap["allianz_combined"] = AB_TOTAL

# ===== 3. insurance_breakdown（asset_diff 資料源）=====
brk = snap.setdefault("insurance_breakdown", {})
brk["policy_a_total"] = A_TOTAL
brk["policy_b_total"] = B_TOTAL
brk["policy_a_funds"] = {k: dict(v) for k, v in A_FUNDS.items()}
brk["policy_b_funds"] = {k: dict(v) for k, v in B_FUNDS.items()}

# ===== 4. 績效（截圖：保單A -0.63% / 保單B +0.42%）=====
snap["allianz_a_performance"] = -0.63
snap["allianz_b_performance"] = 0.42
snap.setdefault("allianz_a_monthly", {})["total"] = A_TOTAL
snap.setdefault("allianz_a_monthly", {})["performance_pct"] = -0.63
snap.setdefault("allianz_b_monthly", {})["total"] = B_TOTAL
snap.setdefault("allianz_b_monthly", {})["performance_pct"] = 0.42

# ===== 5. 保單總現值 = 安聯A+B + 第一金 =====
firstjin = snap.get("firstjin_fl65_current_value") or snap.get("firstjin_current_value") or 1_958_980
ins_total = AB_TOTAL + firstjin
snap["insurance_current_value"] = ins_total
snap["insurance_total"] = ins_total

# ===== 6. 日期 =====
snap["date"] = "2026-07-31"

SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✅ snapshot.json 已更新")
print(f"   安聯A {A_TOTAL:,} = " + " + ".join(f"{k} {v['value']:,}" for k, v in A_FUNDS.items()))
print(f"   安聯B {B_TOTAL:,} = " + " + ".join(f"{k} {v['value']:,}" for k, v in B_FUNDS.items()))
print(f"   安聯合計 {AB_TOTAL:,}  第一金 {firstjin:,}  保單總值 {ins_total:,}")
