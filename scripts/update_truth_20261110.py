#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""2026-11-10 真值日更新（截圖/CSV 為權威）

來源：
  1. 國泰直購三檔（質押擔保池）總庫存損益 — 參考淨值日 2026/11/09
  2. 安聯 App 我的投資（QL18610694／QL18488224）— 2026-11-10 11:38
  3. 第一金人壽 我的帳戶表現 — 2026-11-10
  4. 鉅亨 帳戶總覽（台幣市值 684,204）＋ 一般申購 CSV（21 檔，淨值日 11/09）
  5. 鉅亨 自由PAY 專頁（3 檔）

本批同時修正口徑錯誤：
  鉅亨「一般申購」原以日圓原幣（473,493 JPY）直接併入台幣合計 →
  改為台幣等值（×0.2190）。此為 2026-11-09 該輪 `fund_caliber` 調整引入的錯誤。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
if not (BASE / "snapshot.json").exists():
    BASE = BASE.parent
sys.path.insert(0, str(BASE))
import asset_sync  # noqa: E402

TODAY = "2026-11-10"
SNAP = BASE / "snapshot.json"

# ── 1) 國泰直購（參考淨值日 2026/11/09）──────────────────────────
CATHAY = {
    "富達全球動能多元B股C月配息美元": 5746087,
    "貝萊德智慧數據收益成長B11-美元-強化穩定月配息": 5052715,
    "聯博全球多元收益AD美元月配": 984706,
}
CATHAY_TOTAL = sum(CATHAY.values())  # 11,783,508

# ── 2) 鉅亨一般申購（台幣等值；日圓已換算）──────────────────────
JPY_TWD = 0.2190  # 截圖口徑：日圓 477,716 → 台幣 104,616
GENERAL = {
    "元大台灣卓越50ETF(0050)連結基金-台幣B配息": 44023,
    "台中銀台灣優息基金-B配息台幣": 42133,
    "安聯台灣科技基金": 2520,
    "安聯AI收益成長多重資產基金-B(月配)美元": 180,
    "國泰台灣高股息基金B": 6531,
    "台新美日台半導體基金A-日圓": 104616,  # 原幣 477,716 JPY × 0.2190
    "路博邁台灣5G股票基金T月配級別(台幣)": 69577,
    "聯博-全球多元收益基金AD月配美元": 2951,
    "聯博-美國成長基金AP總報酬月配美元": 2978,
    "摩根基金-JPM多重收益美元對沖A穩定月配": 2979,
    "貝萊德世界黃金A2美元": 3378,
    "貝萊德全球股票收益A6美元穩定配息": 3108,
    "貝萊德世界科技A10美元總報酬穩定配息": 3624,
    "貝萊德世界能源A10美元總報酬穩定配息": 5353,
    "貝萊德世界健康科學A10美元總報酬穩定配息": 5269,
    "貝萊德世界黃金A10美元總報酬穩定配息": 2708,
    "貝萊德全球智慧數據股票入息A11美元強化穩定配息": 3009,
    "富達全球動能多元基金A股C月配美元": 2889,
    "安聯收益成長AMg7月收總收益美元": 3369,
    "M&G入息基金A(美元避險月配)F": 2996,
}
GENERAL_TOTAL = sum(GENERAL.values())  # 314,191

# ── 3) 鉅亨自由 Pay ─────────────────────────────────────────────
FREEPAY = {
    "元大台灣卓越50ETF(0050)連結基金-台幣A不配息": 101992,
    "統一奔騰基金": 74862,
    "路博邁台灣5G股票基金T累積級別(台幣)": 193339,
}
FREEPAY_TOTAL = sum(FREEPAY.values())  # 370,193
HENG_TOTAL = GENERAL_TOTAL + FREEPAY_TOTAL  # 684,384（截圖台幣市值 684,204 + 美元帳戶 180）

# ── 4) 安聯 A / B ───────────────────────────────────────────────
A_FUNDS = {
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 2648319,
    "USDEQ5440 摩根投資基金-多重收益基金-JPM多重收益(美元對沖)-A股(穩定月配)": 689972,
    "USDEQ6550 PIMCO收益增長基金-M級類別(月收息強化股份)": 1612214,
}
A_TOTAL = sum(A_FUNDS.values())  # 4,950,505
B_FUNDS = {
    "NTDEQ2640 元大台灣高股息優質龍頭基金-新台幣(B)配息": 254106,
    "NTDET0010 元大台灣卓越50": 902864,
    "USDEQ3490 安聯收益成長基金-AM穩定月收類股(美元)": 486081,
    "USDEQ5700 M&G入息基金A(美元避險月配)F": 632138,
    "USDEQ6730 貝萊德世界黃金基金 A10美元(總報酬穩定配息)": 159773,
}
B_TOTAL = sum(B_FUNDS.values())  # 2,434,962
AB_TOTAL = A_TOTAL + B_TOTAL  # 7,385,467

# ── 5) 第一金 ───────────────────────────────────────────────────
FIRSTJIN = 1873523
INSURANCE_TOTAL = AB_TOTAL + FIRSTJIN  # 9,258,990

FUNDS_TOTAL = CATHAY_TOTAL + HENG_TOTAL  # 12,467,892

# ── 6) 逐檔（fund_holdings by code）─────────────────────────────
HOLDINGS = {
    "A05144": 44023, "A17030": 42133, "A36004": 2520, "A36135": 180,
    "A37170": 6531, "A47219": 104616, "A49015": 69577,
    "B03629": 2951, "B03870": 2978, "B08291": 2979, "B09006": 3378,
    "B09261": 3108, "B09460": 3624, "B09461": 5353, "B09462": 5269,
    "B09463": 2708, "B14445": 2889, "B20186": 3369, "B31138": 2996,
    "A05143": 101992, "A09012": 74862, "A49038": 193339,
}


def main(dry_run: bool = False) -> int:
    s = json.loads(SNAP.read_text(encoding="utf-8"))
    before = {k: s.get(k) for k in
              ("total_assets", "insurance_total", "funds_total",
               "allianz_combined", "firstjin_total", "funds_cathay")}

    # funds_breakdown
    fb = s.setdefault("funds_breakdown", {})
    fb["一般申購"] = dict(GENERAL)
    fb["自由Pay"] = dict(FREEPAY)
    fb["國泰直購"] = dict(CATHAY)
    fb["一般申購_平台小計"] = GENERAL_TOTAL
    fb["平台小計"] = HENG_TOTAL
    fb["note"] = (
        f"【數值日期 2026-11-09（鉅亨）／2026-11-10（國泰・安聯・第一金）｜本 note 為 {TODAY} 真值日更新】"
        f"口徑修正：一般申購之日圓部位（台新美日台半導體 477,716 JPY × {JPY_TWD}）改以台幣等值 104,616 計入，"
        f"不再以原幣直接併入台幣合計（修正 2026-11-09 fund_caliber 調整引入的虛增）。"
        f"鉅亨：一般申購 {GENERAL_TOTAL:,}＋自由Pay {FREEPAY_TOTAL:,}＝{HENG_TOTAL:,}"
        f"（App 表頭台幣市值 684,204 為不含美元帳戶 180 之口徑）。"
        f"國泰直購三檔以平台參考淨值日 2026/11/09 為準：合計 {CATHAY_TOTAL:,}。"
    )
    fb["note_date"] = TODAY

    # 國泰兩份逐檔鏡像 + 總值
    s["funds_cathay_breakdown"] = dict(CATHAY)
    s["fund_breakdown_cathay"] = dict(CATHAY)
    s["funds_cathay"] = CATHAY_TOTAL
    s["funds_cathay_market_value"] = CATHAY_TOTAL

    s["fund_general"] = GENERAL_TOTAL
    s["fund_freepay"] = FREEPAY_TOTAL
    s[f"funds_heng_total_20261110"] = HENG_TOTAL

    # 安聯 A/B（master 先寫，再由 sync_snapshot_keys 統一）
    s["allianz_policy_a"] = A_TOTAL
    s["allianz_policy_b"] = B_TOTAL
    s["allianz_combined"] = AB_TOTAL
    s["firstjin_total"] = FIRSTJIN

    ib = s.setdefault("insurance_breakdown", {})
    ib["policy_a_total"] = A_TOTAL
    ib["policy_b_total"] = B_TOTAL
    ib["allianz_ab_total"] = AB_TOTAL
    ib["firstjin_total"] = FIRSTJIN
    ib["policy_a_funds"] = dict(A_FUNDS)
    ib["policy_b_funds"] = dict(B_FUNDS)
    ib["note"] = (
        f"2026-11-10 真值日（安聯 App 11:38＋第一金 帳戶表現）："
        f"A {A_TOTAL:,}／B {B_TOTAL:,}，逐檔合計＝表頭 ✓；"
        f"第一金 {FIRSTJIN:,}（100% ID05 M&G入息A 美元避險月配；累計配息 169,024 與系統一致）。"
    )

    # master 群組（funds_total master = 國泰＋鉅亨）
    s["funds_total"] = FUNDS_TOTAL
    s["insurance_total"] = INSURANCE_TOTAL

    # 質押擔保池（國泰）
    cp = s.setdefault("cathay_pledge_0911", {})
    pool = dict(CATHAY)
    pool["合計"] = CATHAY_TOTAL
    pool["資料日"] = f"{TODAY}（截圖：總庫存損益，參考淨值日 2026/11/09）"
    cp["擔保池"] = pool

    # 逐檔
    for h in s.get("fund_holdings", []):
        code = h.get("code")
        if code in HOLDINGS:
            h["value"] = HOLDINGS[code]
            if "market_value" in h:
                h["market_value"] = HOLDINGS[code]

    # 淨值日／匯入日
    s.setdefault("fund_nav_dates", {}).update({
        "國泰直購（富達/聯博/B11）": "2026-11-09",
        "鉅亨（一般申購＋自由Pay）": "2026-11-09",
        "安聯保單內基金（App）": "2026-11-10",
    })
    s.setdefault("source_import_dates", {}).update({
        "保單 第一金": TODAY,
        "保單 安聯 A/B（App）": TODAY,
        "基金 國泰直購（富達/聯博/B11）": TODAY,
        "基金 鉅亨（一般申購＋自由Pay）": TODAY,
    })

    # 同義鍵同步 + 總資產重算（不傳 allianz_combined，讓它由 A+B 派生驗證）
    s = asset_sync.update_asset(
        s,
        insurance=INSURANCE_TOTAL,
        funds=FUNDS_TOTAL,
        allianz_combined=AB_TOTAL,
        firstjin=FIRSTJIN,
    )
    s = asset_sync.sync_snapshot_keys(s)
    s["generated_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    issues = asset_sync.verify_synonyms(s)

    print("=== 更新前 → 更新後 ===")
    for k, v in before.items():
        print(f"  {k}: {v} → {s.get(k)}")
    print(f"  總資產: {s.get('total_assets'):,}")
    print(f"  保單合計: {s.get('insurance_total'):,}（安聯 {AB_TOTAL:,}＋第一金 {FIRSTJIN:,}）")
    print(f"  基金合計: {s.get('funds_total'):,}（國泰 {CATHAY_TOTAL:,}＋鉅亨 {HENG_TOTAL:,}）")
    print(f"  同義鍵不一致: {issues if issues else '無'}")

    if dry_run:
        print("（dry-run，未寫檔）")
        return 0
    SNAP.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 已寫入 {SNAP.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry_run="--dry-run" in sys.argv))
