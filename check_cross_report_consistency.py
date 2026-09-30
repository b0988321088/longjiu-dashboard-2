#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_cross_report_consistency.py — P0-1.5 跨報告一致性檢查（CIO 審查前置）

規則（2026-09-30 使用者核定）：
  同一 as-of 日期，同一欄位只能有一個真值。
  任何報告出現不同值 → FAIL（exit 1），CIO 審查直接不通過。

檢查三類：
  A. 真值覆蓋：主要報告必須出現 snapshot 真值。
  B. 失效舊值：清償／口徑變更前的舊值不得再出現在報告內文
     （總資產／總負債舊值僅允許出現在資產差異的歷史逐日列）。
  C. 口徑雙答案：防禦比例不得同時出現 stored 舊值與派生值。

已知的「非誤判」說明：
  · index.html 的數字由 JS 從 seed JSON 渲染 → 此檔不剝除 script 再比對。
  · 再平衡儀表板談的是五桶穿透，不含雙維度 → 不列入防禦比例的真值覆蓋要求。

用法：
  python check_cross_report_consistency.py            # 人類可讀
  python check_cross_report_consistency.py --json      # 機器可讀
"""
import argparse
import json
import pathlib
import re
import sys

BASE = pathlib.Path(__file__).resolve().parent

REPORTS = [
    "daily_report_v2_{d}.html",
    "asset_diff_{d}.html",
    "penetration_report_{d}.html",
    "rebalance_dashboard_{d}.html",
    "index.html",
]

# JS 渲染（數字在 seed JSON 內）→ 比對時不剝除 script
JS_RENDERED = {"index.html"}

# 失效舊值 → 出現即 FAIL
STALE = {
    "6,719,182": "舊帳戶層現金（500萬高息清償前）",
    "96,798": "舊被動收入（8月口徑）",
    "162,781": "舊月支出",
}

# 舊值僅允許出現在這些報告（資產差異的歷史逐日列本身即歷史真值）
STALE_HISTORY_OK = {
    "31,808,561": ("舊總資產（清償前）", ["asset_diff_"]),
    "36,003,720": ("舊總負債（清償前）", ["asset_diff_"]),
}

# 真值必須出現的報告
# 註：index.html 為 JS 即時渲染外殼（數字由 fetch 的 JSON 決定，靜態檔內為 `total_assets||0`
#     形式），不列入靜態字串比對，否則必然誤報。
REQUIRED_IN = {
    "total_assets": ["daily_report_v2_{d}.html", "asset_diff_{d}.html", "rebalance_dashboard_{d}.html"],
    "total_liabilities": ["daily_report_v2_{d}.html"],
    "available_cash": ["daily_report_v2_{d}.html", "rebalance_dashboard_{d}.html"],
    "defensive_ratio": ["penetration_report_{d}.html"],
}

# 防禦比例口徑雙答案偵測（stored 舊值 vs 派生值）
DEFENSE_STALE = "53.8"

# 敘述性上下文（更新日誌／沿革／修復說明）允許「提及」舊值以求可追溯，
# 但不得出現在任何當期數據區 → 降為 warn 不阻擋。
NARRATIVE_HINTS = ("移除", "舊值", "舊口徑", "stored", "歷史", "修復", "更正", "改派生")


def is_narrative(ctx: str) -> bool:
    return any(h in ctx for h in NARRATIVE_HINTS)


def load_truth(snap: dict) -> dict:
    rc = float((snap.get("restricted_cash") or {}).get("金額") or 0)
    pi = snap.get("passive_income") or {}
    return {
        "total_assets": snap.get("total_assets"),
        "total_liabilities": snap.get("total_liabilities"),
        "cash_total": snap.get("cash_total"),
        "available_cash": float(snap.get("cash_total") or 0) - rc,
        "defensive_ratio": (snap.get("dual_dimension_metric") or {}).get("防禦維度", {}).get("佔比"),
        "monthly_expense": snap.get("monthly_expense"),
        "passive_income_conservative": pi.get("total_conservative"),
        "coverage_ratio": pi.get("coverage_pct"),
    }


def body_of(fn: str, html: str) -> str:
    """回傳可比對的內文；JS 渲染頁保留 script（數字在 seed JSON 裡）。"""
    if pathlib.Path(fn).name in JS_RENDERED:
        return html
    return re.sub(r"<script.*?</script>", " ", html, flags=re.S)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    d = a.date or str(snap.get("date") or "")
    TRUTH = load_truth(snap)

    files = {}
    for tpl in REPORTS:
        f = BASE / tpl.format(d=d)
        if f.exists():
            files[tpl.format(d=d)] = f

    fails: list[str] = []
    warns: list[str] = []

    # ── A. 真值覆蓋 ──
    for field, targets in REQUIRED_IN.items():
        v = TRUTH.get(field)
        if v is None:
            warns.append(f"真值缺漏：{field} 在 snapshot 不存在")
            continue
        if isinstance(v, float) and v == int(v):
            v = int(v)
        pat = f"{v:,}" if isinstance(v, (int, float)) and abs(v) >= 10000 else str(v)
        for t in targets:
            fn = t.format(d=d)
            if fn not in files:
                warns.append(f"報告不存在：{fn}")
                continue
            if pat not in body_of(fn, files[fn].read_text(encoding="utf-8", errors="ignore")):
                fails.append(f"[真值缺席] {fn}：找不到 {field} = {pat}")

    # ── B1. 失效舊值（全報告） ──
    for fn, f in files.items():
        body = body_of(fn, f.read_text(encoding="utf-8", errors="ignore"))
        for stale, why in STALE.items():
            for m in re.finditer(re.escape(stale), body):
                ctx = body[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")
                if is_narrative(ctx):
                    warns.append(f"[敘述提及，非阻擋] {fn}：{stale}（{why}）… {ctx.strip()[:80]}")
                    continue
                fails.append(f"[失效舊值] {fn}：{stale}（{why}）… {ctx.strip()[:80]}")

    # ── B2. 失效舊值（總資產／總負債，僅允許歷史列所在報告） ──
    for stale, (why, allow) in STALE_HISTORY_OK.items():
        for fn, f in files.items():
            tpl_hit = any(fn.startswith(p) for p in allow)
            if tpl_hit:
                continue
            body = body_of(fn, f.read_text(encoding="utf-8", errors="ignore"))
            for m in re.finditer(re.escape(stale), body):
                ctx = body[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")
                if is_narrative(ctx):
                    warns.append(f"[敘述提及，非阻擋] {fn}：{stale}（{why}）… {ctx.strip()[:80]}")
                    continue
                fails.append(f"[失效舊值] {fn}：{stale}（{why}；僅歷史列允許）… {ctx.strip()[:80]}")

    # ── C. 口徑雙答案（僅當期數據區才算 FAIL；更新日誌的敘述提及降為 warn） ──
    for fn, f in files.items():
        body = body_of(fn, f.read_text(encoding="utf-8", errors="ignore"))
        true_v = str(TRUTH.get("defensive_ratio"))
        for m in re.finditer(re.escape(DEFENSE_STALE), body):
            ctx = body[max(0, m.start() - 45):m.end() + 45].replace("\n", " ")
            if is_narrative(ctx):
                warns.append(f"[敘述提及，非阻擋] {fn}：防禦舊值 {DEFENSE_STALE} … {ctx.strip()[:80]}")
                continue
            if true_v in body:
                fails.append(f"[口徑雙答案] {fn}：同時出現防禦 {DEFENSE_STALE} 與 {true_v}")
                break

    out = {
        "as_of": d,
        "truth": TRUTH,
        "files": list(files),
        "fails": fails,
        "warns": warns,
        "result": "FAIL" if fails else "PASS",
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"═══ 跨報告一致性檢查（as-of {d}）═══")
        print(f"真值：總資產 {TRUTH['total_assets']:,}｜總負債 {TRUTH['total_liabilities']:,}"
              f"｜現金 {TRUTH['cash_total']:,}｜可動用 {TRUTH['available_cash']:,.0f}"
              f"｜防禦 {TRUTH['defensive_ratio']}%｜月支出 {TRUTH['monthly_expense']:,}"
              f"｜保守被動 {TRUTH['passive_income_conservative']:,}｜覆蓋 {TRUTH['coverage_ratio']}%")
        print(f"受檢報告：{len(files)} 份")
        if fails:
            print(f"\n❌ FAIL（{len(fails)} 項）：")
            for x in fails:
                print(f"  · {x}")
        if warns:
            print(f"\n⚠️ 警告（{len(warns)} 項）：")
            for x in warns:
                print(f"  · {x}")
        if not fails:
            print("\n✅ PASS：同一 as-of 下，各報告欄位一致、無失效舊值。")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
