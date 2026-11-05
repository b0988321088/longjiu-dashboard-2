#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""月損益警戒契約測試（2026-11-05 裁決規格）

驗的是「規則語意」，不是當日數字：
  - 邊界：-1.00／-2.00／-3.00 必須落在該級（含等號）
  - 資料不足 → 灰燈、且**不得**回綠燈或給裁示
  - 距下一級方向：-1.58% 的下一級是 -2%（橘），不是 -3%
  - 影子模式視窗 2026-11-05 ~ 2027-02-05（期滿需人工裁決）
  - 裁決文字不得含自動交易語意（不得出現「賣出」「自動減碼」）
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import monthly_risk_watch as m  # noqa: E402

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


# ── 分級邊界 ──────────────────────────────────────────────
ck("0% → 綠", m.classify(0.0)[0] == "green")
ck("+1.20% → 綠", m.classify(1.2)[0] == "green")
ck("-0.99% → 綠", m.classify(-0.99)[0] == "green")
ck("-1.00% → 黃（含等號）", m.classify(-1.0)[0] == "watch")
ck("-1.50% → 黃", m.classify(-1.5)[0] == "watch")
ck("-1.99% → 黃", m.classify(-1.99)[0] == "watch")
ck("-2.00% → 橘（含等號）", m.classify(-2.0)[0] == "alert")
ck("-2.99% → 橘", m.classify(-2.99)[0] == "alert")
ck("-3.00% → 紅（含等號）", m.classify(-3.0)[0] == "severe")
ck("-7.40% → 紅", m.classify(-7.4)[0] == "severe")

# ── 資料不足：灰燈、不裁示 ────────────────────────────────
ck("None → 灰", m.classify(None)[0] == "unknown")
ck("None 不得回綠", m.classify(None)[0] != "green")
ck("'abc' → 灰（字串不炸）", m.classify("abc")[0] == "unknown")
ck("字串數字可解析", m.classify("-1.5")[0] == "watch")
ck("灰燈裁示＝不裁示", "不裁示" in m.stance(None, "insufficient"))
ck("降級品質也不裁示交易", "不裁示" in m.stance(-2.5, "degraded"))

# ── 距下一級方向 ─────────────────────────────────────────
g = m.next_gap(-1.58)
ck("-1.58% 下一級 = -2%（橘）", g["next"] == -2.0 and g["code"] == "alert", str(g))
ck("-1.58% 差距 0.42pp", abs(g["gap_pp"] - 0.42) < 1e-9, str(g["gap_pp"]))
ck("-0.30% 下一級 = -1%（黃）", m.next_gap(-0.3)["code"] == "watch")
ck("-2.40% 下一級 = -3%（紅）", m.next_gap(-2.4)["code"] == "severe")
ck("-4.00% 已最深", "紅燈" in m.next_gap(-4.0)["text"])
ck("None → 無法計算", m.next_gap(None)["gap_pp"] is None)

# ── 裁決語意（不得暗示自動交易）──────────────────────────
texts = [m.stance(x, "ok") for x in (0.5, -1.2, -2.5, -3.6)]
ck("綠 → HOLD", "HOLD" in texts[0])
ck("黃 → 觀察", "觀察" in texts[1])
ck("橘 → 防守準備", "防守" in texts[2])
ck("紅 → 防守並要求核准", "核准" in texts[3])
def _no_auto_trade(t):
    """出現「自動賣出／自動減碼」時必須緊接否定語（不自動…），否則視為違規。"""
    for kw in ("自動賣出", "自動減碼"):
        i = t.find(kw)
        while i != -1:
            if t[max(0, i - 1):i] != "不":
                return False
            i = t.find(kw, i + 1)
    return True


ck("裁決文字無自動交易語意（否定式允許）", all(_no_auto_trade(x) for x in texts), str(texts))
ck("紅燈必須人工核准", "需你核准" in texts[3])

# ── 影子模式視窗 ────────────────────────────────────────
ck("2026-11-05 在影子期", m.in_shadow("2026-11-05"))
ck("2026-11-04 不在", not m.in_shadow("2026-11-04"))
ck("2027-02-05 在（含末日）", m.in_shadow("2027-02-05"))
ck("2027-02-06 已過期（需人工轉正式）", not m.in_shadow("2027-02-06"))

# ── 規則表單一來源 ──────────────────────────────────────
tb = m.rule_table()
ck("規則表三級", len(tb) == 3 and [r["門檻"] for r in tb] == [-3.0, -2.0, -1.0])

# ── 端到端：真實 snapshot（唯讀）──────────────────────────
snap = __import__("json").loads(
    (Path(__file__).resolve().parent.parent / "snapshot.json").read_text(encoding="utf-8"))
res = m.assess(snap)
ck("assess 不拋例外且欄位齊", isinstance(res, dict) and "gap" in res and "stance" in res)
ck("assess 燈號與報酬率一致", m.classify(res["ret_pct"])[0] == res["level"], str(res.get("ret_pct")))
ck("assess 灰燈時不裁示", res["quality"] != "insufficient" or "不裁示" in res["stance"])

# ── 壓力情境（唯讀推算）──────────────────────────────────
_st = m.stress(snap)
ck("壓力情境兩級", [x["shock_pct"] for x in _st] == [-5.0, -10.0])
ck("-5% 總資產下降", _st[0]["total_after"] < snap["total_assets"])
ck("-10% 幅度大於 -5%", abs(_st[1]["assets_delta"]) > abs(_st[0]["assets_delta"]))
ck("LTV 隨下跌上升", _st[1]["ltv_after"] > _st[0]["ltv_after"])
ck("維持率與 LTV 互為倒數",
   abs(_st[1]["maintenance_after"] * _st[1]["ltv_after"] / 100 - 100) < 0.6,
   f'{_st[1]["maintenance_after"]} x {_st[1]["ltv_after"]}')
ck("-5% 仍低於 53% 停止線→無需還本", _st[0]["ltv_after"] < 53.0 and _st[0]["repay_to_53"] == 0)
ck("-10% 需回補金額 > 0", _st[1]["ltv_after"] > 53.0 and _st[1]["repay_to_53"] > 0)

print(f"\n{PASS} PASS / {FAIL} FAIL")
raise SystemExit(1 if FAIL else 0)
