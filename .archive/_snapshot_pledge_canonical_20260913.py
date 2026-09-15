# -*- coding: utf-8 -*-
"""一次性：質押欄位單一真值校正（2026-09-13）

問題：cathay_pledge_0911 內同時存在互相矛盾的欄位 —
  「用途」還停在 9/11 版（300萬還安聯＋240萬押標金），
  「執行時序_20260911更正」寫「撥款已於 9/11 入帳」（與 撥款=❌未撥款 直接矛盾）。
其他報表讀到哪個欄位就顯示哪個版本 → 使用者看到過期文字。

修法：以 2026-09-12 使用者裁示（ruling_20260912 ⑤⑥）為唯一真值：
  540萬全數優先清償 500萬高息負債（保單質押400萬@4%＋券商質押100萬@3.92%），
  10月標案押標金不預留（9月底評估）；矛盾欄位刪除；補上結構化欄位
  （撥款預估日／成數_數值／券商質押利率）供 pledge_status.py 動態組句。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"

s = json.loads(SNAP.read_text(encoding="utf-8"))
p = s["cathay_pledge_0911"]
lb = s.setdefault("liabilities_build_up", {})

# ── 結構化欄位（原本只存在文字描述裡）──
pool = p.get("額度_本金") or 0
amt = p.get("可貸金額") or 0
p["成數_數值"] = round(amt / pool, 4) if pool else 0
p["撥款預估日"] = "2026-09-25"

pol = s.get("policy_pledge_loan") or 0
pol_rate = s.get("policy_pledge_rate") or 0
broker = lb.get("券商質押") or 0
lb["券商質押利率"] = 0.0392
broker_rate = lb["券商質押利率"]

old_month = (pol * pol_rate + broker * broker_rate) / 12
new_month = amt * float(str(p.get("利率", "0%")).replace("%", "")) / 100 / 12
target = pol + broker

# ── 用途：對齊 2026-09-12 裁示 ──
p["用途"] = (f"{amt/10000:,.0f}萬全數優先清償 {target/10000:,.0f}萬高息負債"
             f"（保單質押 {pol/10000:,.0f}萬@{pol_rate*100:.1f}%：安聯A2＋B1＋第一金；"
             f"券商質押 {broker/10000:,.0f}萬@{broker_rate*100:.2f}%）— 2026-09-12 裁示"
             f"（月息 {old_month:,.0f} → {new_month:,.0f}，月省約 {old_month-new_month:,.0f}）；"
             f"10月標案押標金 240萬 不預留（9月底評估再定）")

# ── 利差試算重算（原試算基於已廢的 300萬還安聯版）──
p["利差試算"] = {
    "省息": f"{target:,.0f} × 加權 {((pol*pol_rate+broker*broker_rate)/target*100 if target else 0):.2f}% = {old_month*12:,.0f}/年（{old_month:,.0f}/月）",
    "新增借息": f"{amt:,.0f} × {p.get('利率','')} = {new_month*12:,.0f}/年（{new_month:,.0f}/月）",
    "淨增": f"約 +{old_month*12-new_month*12:,.0f}/年（{old_month-new_month:,.0f}/月）",
    "備註": "基準＝2026-09-12 使用者裁示：540萬不為押標金保留餘額，優先清償高息負債；原 300萬還安聯＋240萬押標金版已廢。",
}

# ── 刪除矛盾殘留欄位 ──
removed = [k for k in ("執行時序_20260911更正", "擔保池註記") if k in p]
for k in removed:
    del p[k]

SNAP.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")

# ── 驗證 ──
chk = json.loads(SNAP.read_text(encoding="utf-8"))["cathay_pledge_0911"]
print("removed:", removed)
print("成數_數值:", chk.get("成數_數值"), "| 撥款預估日:", chk.get("撥款預估日"))
print("撥款:", chk.get("撥款")[:40])
print("用途:", chk.get("用途"))
print("利差試算:", json.dumps(chk.get("利差試算"), ensure_ascii=False))

import pledge_status  # noqa: E402
print("\n[full ]", pledge_status.pledge_status_line())
print("[card ]", pledge_status.pledge_status_line(style="card"))
print("[short]", pledge_status.pledge_status_line(style="short"))
