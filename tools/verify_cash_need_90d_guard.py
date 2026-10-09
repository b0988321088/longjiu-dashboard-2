# -*- coding: utf-8 -*-
"""verify_cash_need_90d_guard.py — 90 天需求守門的正反向測試（P0 驗收）

驗證 tools/cash_need_90d_guard.py（數值判定；散文式判定已依裁決移除）。

  P1 真實日報（daily_report_v2_<today>.html）→ PASS
  P2 與守門同口徑（index.html ＋ 日報 拼接）→ PASS
  N1 產物把押標金併入需求（分母＝A+2,400,000）→ FAIL（數值不符）
  N2 產物完全沒有覆蓋率渲染式 → FAIL（不得因找不到而默認通過）
  N3 押標金多處合法語境出現、但分母正確 → PASS（證明不再有散文式假紅燈；
     舊版正則會因「⑥ 未得標不屬 90 天已確認需求」誤判，語境版會因決策卡清單誤判）

註：本檔曾驗「語境」判定，該設計實測脆弱已移除（見 guard module docstring）。
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cash_need_90d_guard as G  # noqa: E402

A = 477630.0
TODAY = datetime.date.today().isoformat()
R = []


def rec(tid, desc, expect, behaved, detail):
    """behaved＝守門行為符合預期（True 代表本項測試通過）。"""
    R.append({"id": tid, "desc": desc, "expect": expect,
              "ok": bool(behaved), "detail": detail})


daily = REPO / f"daily_report_v2_{TODAY}.html"
index = REPO / "index.html"

# ── P1：真實日報 ─────────────────────────────────────────────────────────────
if daily.exists():
    txt = daily.read_text(encoding="utf-8", errors="replace")
    ok, d = G.check_rendered_denominator(txt, A)
    rec("P1", f"真實日報 {daily.name}：分母＝A 區", "PASS", ok, d)
else:
    rec("P1", f"{daily.name} 不存在", "PASS", False, "無法取得真實產物")

# ── P2：與守門口徑一致（拼接） ───────────────────────────────────────────────
blob = ""
for f in (index, daily):
    if f.exists():
        blob += f.read_text(encoding="utf-8", errors="replace")
ok, d = G.check_rendered_denominator(blob, A)
rec("P2", "index.html ＋ 日報 拼接（守門同口徑）", "PASS", ok, d)

# ── N1：押標金被併入需求 → 必須 FAIL ─────────────────────────────────────────
bad = f"未來 90 天現金需求覆蓋率 22.2%（可動用 639,661 ÷ 已確認 {A + 2400000:,.0f}；門檻 100%)"
ok, d = G.check_rendered_denominator(bad, A)
rec("N1", "產物把押標金併入需求（分母 A+2,400,000）", "FAIL", not ok, d)

# ── N2：沒有渲染式 → 不得默認通過 ────────────────────────────────────────────
ok, d = G.check_rendered_denominator("（無覆蓋率字樣）", A)
rec("N2", "產物缺覆蓋率渲染式（無法數值驗證）", "FAIL", not ok, d)

# ── N3：押標金多語境但分母正確 → PASS ────────────────────────────────────────
mix = (
    "10 月標案押標金 240 萬來源定案（不得預設由 540 萬撥款支付）"
    "P0-2 資金鏈閉環（240萬押標金＝條件式事件，不提前占用現金）"
    "⑥ 條件式事件：10 月標案押標金 2,400,000 元，未得標不屬 90 天已確認需求。"
    f"未來 90 天現金需求覆蓋率 133.9%（可動用 639,661 ÷ 已確認 {A:,.0f}；門檻 100%)"
)
ok, d = G.check_rendered_denominator(mix, A)
rec("N3", "押標金多語境出現、分母正確 → 不得誤判", "PASS", ok, d)

print("=" * 68)
print("90 天需求守門 正反向測試（數值判定）")
print("=" * 68)
for r in R:
    print(f"  {'✅' if r['ok'] else '❌'} {r['id']} {r['desc']}｜預期 {r['expect']}")
    print(f"        {r['detail']}")
n_ok = sum(1 for r in R if r["ok"])
print(f"\n== 結果：{n_ok}/{len(R)} PASS ==")
sys.exit(0 if n_ok == len(R) else 1)
