# -*- coding: utf-8 -*-
"""tests/test_public_mask.py — 公開面遮蔽正反例（2026-10-12 資安處置：清理公開資料）"""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import public_mask as pm  # noqa: E402

PASS = FAIL = 0
def ck(label, cond, detail=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ✅ {label}")
    else: FAIL += 1; print(f"  ❌ {label} {detail}")

print("=== 公開面遮蔽（正反例）===")
print("① 帳號識別碼")
ck("① 002***75 → •••", "002***75" not in pm.mask_accounts("台新帳號 002***75 是否納管"), pm.mask_accounts("台新帳號 002***75 是否納管"))
ck("① 007-0099804310022717 → •••", "0099804310022717" not in pm.mask_accounts("轉入 007-0099804310022717"), "")
ck("① 帳號後金額不受影響（負向：不得誤遮金額）", "197,205" in pm.mask_accounts("台新帳戶 40,044／永豐 197,205"), pm.mask_accounts("台新帳戶 40,044／永豐 197,205"))
ck("① 一般數字／日期不被誤遮", pm.mask_accounts("2026-10-12 配息 64,611") == "2026-10-12 配息 64,611", pm.mask_accounts("2026-10-12 配息 64,611"))
print("② 安全線門檻")
ck("② 安全線：40,000 → 內部門檻", "40,000" not in pm.mask_safety_lines("安全線：40,000（生活帳戶）"), pm.mask_safety_lines("安全線：40,000（生活帳戶）"))
ck("② 197,205 門檻亦遮", "197,205" not in pm.mask_safety_lines("安全線：197,205"), "")
ck("② 負向：非『安全線：』語境的同數字不得被改", pm.mask_safety_lines("餘額 40,000") == "餘額 40,000", pm.mask_safety_lines("餘額 40,000"))
print("③ 行庫顯示值")
for k in ("yushan", "fubon", "sinopac", "safe_line_sinopac", "cathay", "card_sum"):
    ck(f"③ {k} → ●●●", pm.display_value(k, 40044) == pm.AMOUNT_MASK, str(pm.display_value(k, 40044)))
ck("③ 負向：非行庫鍵不得被遮（總資產／配息仍是真值）", pm.display_value("div_total", 64611) is None and pm.display_value("cash_total", 1827363) is None, "")
print("④ scrub 合併套用")
s = pm.scrub("台新帳號 002***75；安全線：197,205；轉入 007-0099804310022717")
ck("④ 三者皆遮蔽", ("002***75" not in s) and ("197,205" not in s) and ("0099804310022717" not in s), s)
ck("④ 保留可讀結構", "內部門檻（不公開）" in s, s)
print(f"\n== 結果：{PASS} PASS / {FAIL} FAIL ==")
sys.exit(1 if FAIL else 0)
