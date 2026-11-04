#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-10-12 真值套用（部分）：安聯保單 B 逐檔（App 截圖 標的列表）
來源：永旭保險經紀人 App「我的投資」→ 吉利發發變額萬能壽險戊型（QL18488224）標的列表（2026-10-12 13:21）
規則：截圖 = authoritative；六檔逐檔合計必須等於價值總額（assert 硬擋）
範圍：本次僅 B 保單（A／第一金／國泰／鉅亨／證券 未提供新截圖，維持原值）
"""
import json, shutil, sys
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(BASE))
P = BASE / "snapshot.json"
shutil.copy(P, BASE / "snapshot.backup_20261012.json")   # 日期備份（不覆蓋 rolling backup）
snap = json.loads(P.read_text(encoding="utf-8"))

# ============ 安聯保單 B（QL18488224）價值總額 2,630,180／−2.41% ============
B = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 372201,
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 488170,
    "USDEQ5680 貝萊德世界健康科學基金 A10美元(總報酬穩定配息)": 236957,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 619526,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 765418,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 147908,
}
B_TOTAL = 2630180
assert sum(B.values()) == B_TOTAL, f"安聯B 逐檔合計 {sum(B.values()):,} != {B_TOTAL:,}"

A_TOTAL = int(snap["allianz_a"])          # 4,956,894（10/08 截圖，本次未更新）
FJ_TOTAL = int(snap["firstjin"])          # 1,868,043（10/08 截圖，本次未更新）
OLD_B = int(snap["allianz_b"])

snap["allianz_b_breakdown"] = dict(B)
snap["allianz_b_performance"] = -2.41
snap["allianz_b_breakdown_note"] = (
    "2026-10-12 保單B App 標的列表截圖（QL18488224 戊型，價值總額 2,630,180／−2.41%）："
    "六檔逐檔合計＝價值總額 ✓。vs 10/08（2,648,097）：−17,917／−0.68%。"
    "逐檔變動：元大台灣高股息 376,671→372,201、安聯收益成長 491,298→488,170、"
    "健康科學A10 238,879→236,957、M&G 624,122→619,526、PIMCO 768,110→765,418、"
    "黃金A10 149,017→147,908。截圖標示：元大 +0.00%、安聯收益成長 −4.88%、M&G −1.36%、"
    "PIMCO −0.25%、黃金A10 −10.76%；健康科學兩張截圖顯示 ±4.69% 不一致，僅採金額為真。")
snap["allianz_note_20261012"] = (
    "2026-10-12 安聯保單 App『我的投資』標的列表（僅 B 保單截圖）：B 2,630,180（−2.41%）；"
    "A 4,956,894（10/08 值，未更新）→ A+B 合計 7,587,074。"
    "第一金 1,868,043（10/08 值）→ 保險合計 9,455,117。逐檔明細見 allianz_b_breakdown。")

for k in ("allianz_b", "allianz_b_current_value", "allianz_b_funds", "allianz_b_value",
          "allianz_policy_b", "allianz_policy_b_value", "policy_b_total"):
    snap[k] = B_TOTAL
for k in ("allianz_ab", "allianz_ab_current_value", "allianz_combined", "allianz_current_value", "allianz_total"):
    snap[k] = A_TOTAL + B_TOTAL

ib = dict(snap.get("insurance_breakdown") or {})
ib["policy_a_total"] = A_TOTAL
ib["policy_b_total"] = B_TOTAL
ib["allianz_ab_total"] = A_TOTAL + B_TOTAL
ib["policy_b_funds"] = dict(B)
ib["note"] = ("安聯 B 逐檔＝2026-10-12 App 截圖；安聯 A／第一金＝2026-10-08 截圖（未更新）")
snap["insurance_breakdown"] = ib

INSURANCE = A_TOTAL + B_TOTAL + FJ_TOTAL
for k in ("insurance", "insurance_current_value", "insurance_total"):
    snap[k] = INSURANCE
snap["insurance_total_note"] = ("含配息（安聯A 2026-10-08／安聯B 2026-10-12／第一金 2026-10-08 截圖）")

P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"✅ 已套用：B {OLD_B:,} → {B_TOTAL:,}（{B_TOTAL-OLD_B:+,}）｜A {A_TOTAL:,}｜A+B {A_TOTAL+B_TOTAL:,}")
print(f"✅ 保險合計 = {INSURANCE:,}（原 {OLD_B + A_TOTAL + FJ_TOTAL:,}）")
print("   逐檔驗證：", sum(B.values()) == B_TOTAL)
print("   下一步：asset_sync --rebuild-liabilities → update_data --check → sync_all 2026-10-12")
