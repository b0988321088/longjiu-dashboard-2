#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2026-09-29 質押撥款入帳 590 萬 → snapshot 更新（現金／負債／撥款狀態）。
使用者 9/29 確認：國泰實撥 590 萬（表定 540 萬），10:57 入帳、末五碼 85061。
冪等：重跑不會重複加錢（以 _marker 為準）。
"""
import json, sys, shutil
from pathlib import Path

BASE = Path(r"C:/Users/bot/Desktop/longjiu_system")
P = BASE / "snapshot.json"
AMT = 5_900_000
MARK = "pledge_disbursement_20260929"
ACC = "活期儲蓄存款"          # 國泰一般活存（末五碼 85061）
POOL = 11_786_060             # 質押基金池市值（cathay_pledge_0911.擔保池.合計，9/11 口徑）

snap = json.loads(P.read_text(encoding="utf-8"))
if snap.get(MARK):
    print("⚠️ 已標記過撥款入帳 → 不重複加錢（若需重做請先移除", MARK, "）")
    sys.exit(0)

before = {
    "cash": snap.get("cash_total"), "acc": (snap.get("cash_detail") or {}).get(ACC),
    "total_assets": snap.get("total_assets"), "total_liab": snap.get("total_liabilities"),
    "net_worth": snap.get("net_worth"),
}
assert before["acc"] == 92935, f"國泰活存基準不符：{before['acc']}（應 92,935）"

# ① 現金入帳（帳戶明細 + 總額；同義鍵由 sync_snapshot_keys 統一）
snap["cash_detail"][ACC] = before["acc"] + AMT
snap["cash_total"] = before["cash"] + AMT
# ② 總資產 +590 萬（現金屬資產項）
snap["total_assets"] = before["total_assets"] + AMT
# ③ 新增負債欄位：國泰基金質押 590 萬@2.77%（獨立於券商質押 100 萬@3.92%）
snap["fund_pledge_loan"] = AMT
snap["fund_pledge_rate"] = 0.0277
snap["fund_pledge_note"] = ("2026-09-29 撥款入帳：國泰基金質押借款 590 萬@2.77%"
                            "（表定 540 萬＝池本金 1,200 萬×4.5 成；實撥 590 萬≒池市值 1,178.6 萬×5 成）"
                            "；擔保池：富達＋聯博＋貝萊德B11；清償用途見 cathay_pledge_0911.用途")

# ④ 撥款狀態（cathay_pledge_0911）
p = snap.setdefault("cathay_pledge_0911", {})
p["撥款"] = (f"✅ 2026-09-29 10:57 入帳 NT$5,900,000（國泰世華 App 入帳通知，入帳帳號末五碼 85061＝{ACC}）"
             f"；使用者 9/29 確認實撥 590 萬（表定 540 萬，多 50 萬）")
p["已撥款"] = True
p["表定可貸金額"] = 5_400_000
p["可貸金額"] = AMT
p["實際撥款金額"] = AMT
p["實際撥款日"] = "2026-09-29"
p["成數_數值"] = 0.5
p["成數"] = "實撥 590 萬≒池市值 1,178.6 萬 × 5 成（表定 4.5 成 × 本金 1,200 萬 = 540 萬）"
p["LTV"] = f"50.0%（借款 {AMT:,} / 池市值 {POOL:,}）"
p["撥款預估日"] = "2026-09-29（已完成）"
p["用途"] = (f"實撥 590 萬：500 萬優先清償高息負債（保單質押 400 萬@4.0%：安聯A2＋B1＋第一金；"
             f"券商質押 100 萬@3.92%）— 2026-09-12 裁示；多撥 50 萬（590 vs 表定 540）用途待定，"
             f"建議①加碼清償②留現金緩衝（10 月押標金 240 萬 10/02 評估）③立即還回（閒置成本 2.77% ≈ 1,154/月）")
p["月息"] = f"13,615/月（5,900,000 × 2.77% ÷ 12）；清償 500 萬後舊息 16,600/月 → 淨省 2,985/月"
if isinstance(p.get("待補"), list):
    p["待補"] = [x for x in p["待補"] if "撥款確切日" not in str(x)] + ["銀行側撥款通知／對帳單（月付息日、繳息方式）"]

# ⑤ 事件標記（冪等保護 + 稽核可追溯）
snap[MARK] = {
    "日期": "2026-09-29", "時間": "10:57:21", "金額": AMT,
    "銀行": "國泰世華", "入帳帳號": f"{ACC}（末五碼 85061）",
    "性質": "基金質押撥款（負債，非收入）",
    "來源": "使用者提供國泰世華 App 入帳通知截圖 + 9/29 對話確認「撥款 590 萬」",
}

from asset_sync import sync_snapshot_keys, rebuild_liabilities   # noqa: E402
snap = sync_snapshot_keys(snap)
snap = rebuild_liabilities(snap)

P.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

print("=== 更新前後 ===")
for k, v in before.items():
    print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
print("=== 更新後 ===")
for k in ("cash_total", "real_liquid_assets", "total_assets", "fund_pledge_loan",
          "total_liabilities", "net_worth"):
    print(f"  {k}: {(snap.get(k) or 0):,}")
bu = snap["liabilities_build_up"]
print("  負債拆解:", {k: f"{v:,}" if isinstance(v, int) else v for k, v in bu.items() if k != "note"})
assert snap["total_assets"] == before["total_assets"] + AMT, "total_assets 未正確增加"
assert snap["net_worth"] == before["net_worth"], \
    f"淨值應不變（借貸同時增加資產與負債）但為 {snap['net_worth']:,}（原 {before['net_worth']:,}）"
print("✅ 淨值不變驗證通過（借款不創造淨值）")
