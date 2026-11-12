#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-11-12 安聯 A/B 真值套用（使用者 08:42-08:43 Telegram 截圖）

來源：
  ① 我的投資 總覽：帳戶總價值 7,435,397；本月累積配息/撥回 2 筆共 11,076；
     風險屬性積極型（效期至 116/01/21）。
  ② QL18610694（A）4,962,614（-0.98%）：USDEQ3490 2,663,061／USDEQ5440 690,329／
     USDEQ6550 1,609,224 → 逐檔合計＝表頭 ✓（本次 A 明細截圖已補齊，前次 gap 2,767 歸零）
  ③ QL18488224（B）2,472,783（-7.87%）：NTDEQ2640 267,003／NTDET0010 923,692／
     USDEQ3490 488,787／USDEQ5700 637,615／USDEQ6730 155,686 → 逐檔合計＝表頭 ✓

⚠️ 使用者口述「黃金與醫療都已轉換」：截圖顯示
   - 醫療（USDEQ5680 貝萊德世界健康科學）：A、B 皆已無此檔 → 已轉換完成 ✓
   - 黃金（USDEQ6730）：A 已無、**B 仍有 155,686（-6.07%）** → 尚未轉出，本腳本不動此檔
"""
import json
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
snap = json.loads(P.read_text(encoding="utf-8"))

A_FUNDS = {
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 2663061,
    "USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)": 690329,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 1609224,
}
A_TOTAL = 4962614
B_FUNDS = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 267003,
    "NTDET0010 元大台灣卓越50": 923692,
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 488787,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 637615,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 155686,
}
B_TOTAL = 2472783
assert sum(A_FUNDS.values()) == A_TOTAL, sum(A_FUNDS.values())
assert sum(B_FUNDS.values()) == B_TOTAL, sum(B_FUNDS.values())
TOTAL = A_TOTAL + B_TOTAL
assert TOTAL == 7435397, TOTAL

FIRSTJIN = 1882263  # 11/11 截圖真值，本次未變動

# 同義鍵全群組指派（血淚：sync_snapshot_keys 的 master 是 allianz_policy_a/b 本身，
# 不在 SYNONYM_GROUPS 值清單內 → 只設群組鍵會被 master 舊值反覆寫回）
snap["allianz_policy_a"] = A_TOTAL
snap["allianz_policy_b"] = B_TOTAL
for k in ("allianz_a", "allianz_a_funds", "allianz_a_current_value",
          "allianz_policy_a_value", "policy_a_total"):
    snap[k] = A_TOTAL
for k in ("allianz_b", "allianz_b_funds", "allianz_b_current_value",
          "allianz_policy_b_value", "policy_b_total"):
    snap[k] = B_TOTAL
for k in ("allianz_ab", "allianz_combined", "allianz_ab_current_value"):
    snap[k] = TOTAL

ib = snap["insurance_breakdown"]
ib["policy_a_total"] = A_TOTAL
ib["policy_b_total"] = B_TOTAL
ib["allianz_ab_total"] = TOTAL
ib["policy_a_funds"] = dict(A_FUNDS)
ib["policy_b_funds"] = dict(B_FUNDS)
ib["firstjin_total"] = FIRSTJIN
ib["note"] = (
    "2026-11-12 08:42 安聯 App：A 4,962,614（-0.98%，三檔逐檔合計＝表頭 ✓）／"
    "B 2,472,783（-7.87%，五檔逐檔合計＝表頭 ✓）＝7,435,397。"
    f"第一金 {FIRSTJIN:,}（11/11，100% IDXX M&G入息A 美元避險月配）。"
)
ib["allianz_note_20261112"] = (
    "2026-11-12 08:42-08:43 安聯 App：帳戶總價值 7,435,397（A 4,962,614 -0.98%／B 2,472,783 -7.87%）；"
    "本月累積配息撥回 11,076（2 筆）；風險屬性積極型（效期 2027/01/21）。"
    "A 逐檔 3 檔、B 逐檔 5 檔均與表頭一致 → allianz_a_detail_gap 歸零。"
    "組合確認：醫療基金（USDEQ5680 貝萊德世界健康科學）A/B 皆已無 → 已轉換；"
    "黃金基金（USDEQ6730）A 已無、B 仍持 155,686（-6.07%）。"
)
snap["allianz_a_detail_gap"] = {"amount": 0, "as_of": "2026-11-12",
                               "reason": "A 逐檔三檔合計＝4,962,614＝表頭", "source": "11/12 08:42 截圖"}
snap["allianz_b_detail_gap"] = {"amount": 0, "as_of": "2026-11-12",
                               "reason": "B 逐檔五檔合計＝2,472,783＝表頭", "source": "11/12 08:43 截圖"}

# 醫療已全數轉出 → 記錄校正事件（不改金額，僅狀態）
snap["satellite_reality_20261112"] = {
    "日期": "2026-11-12",
    "醫療基金": {"代號": "USDEQ5680 貝萊德世界健康科學A10", "持股": 0,
             "說明": "A、B 保單逐檔皆無此檔 → 使用者所述「醫療已轉換」已成立；帳上金額 0"},
    "黃金基金": {"代號": "USDEQ6730 貝萊德世界黃金A10", "持股": 155686,
             "說明": "A 已無；B 仍持 155,686（11/12 08:43 截圖，使用者同日確認「B 保單裡面還有黃金」）→ 部位保留，不列為已轉換"},
    "結論": "醫療部位歸零（已轉換）；黃金部位僅剩 B 155,686，避險衛星不得再以舊值 367,192 敘述",
}

snap["insurance_total"] = TOTAL + FIRSTJIN
for k in ("insurance_current_value", "insurance"):
    snap[k] = snap["insurance_total"]
snap["insurance_market_value"] = snap["insurance_total"]

from asset_sync import sync_snapshot_keys, rebuild_liabilities  # noqa: E402
snap = sync_snapshot_keys(snap)
snap["total_assets"] = (snap["insurance_total"] + snap["securities_total_market_value"]
                        + snap["fund_market"] + snap["cash_total"])
snap = rebuild_liabilities(snap)
snap["generated_at"] = "2026-11-12T08:50:00"
snap["last_updated"] = "2026-11-12"

P.write_text(json.dumps(snap, ensure_ascii=False, indent=1).replace("\n", "\r\n"),
             encoding="utf-8", newline="")

print("--- 2026-11-12 安聯 A/B 真值套用完成 ---")
for k in ("insurance_total", "allianz_combined", "allianz_policy_a_value", "allianz_policy_b_value",
          "total_assets", "total_liabilities", "net_worth"):
    print(f"  {k}: {snap.get(k):,}")
print(f"  黃金(B)：{B_FUNDS['USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)']:,}｜健康：0")
