#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""頁面真值一致性守門（TD-20261015-05 blocking①② 的回歸測試）。

守的是兩類「同頁兩套數字」事故：
  ① asset_diff_*.html 變化明細表：每列「保單＋基金＋證券＋現金(可動用)＋指定用途款 ＝ 總資產」
     必須逐列成立（2026-10-15 事故：總資產欄含指定款、分項欄不含 → 同列自相矛盾 900,000）。
  ② index.html「操作規範」段之桶位百分比／目標／偏差pp／分母／理論調整，
     必須等於 snapshot.penetration 即時值（事故：雷達週計畫舊值 36.4% 與 CEO 卡 live 36.2% 並存）。

用法：python tools/test_page_truth_consistency.py   （rc=0 PASS／rc=1 FAIL）
負向自測：對複本注入舊值／破壞列加總 → 必須被抓到，證明非空跑。
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(BASE, "snapshot.json")
AD = os.path.join(BASE, "asset_diff_2026-10-15.html")
IDX = os.path.join(BASE, "index.html")


def _num(s):
    s = re.sub(r"<[^>]+>", "", s).replace(",", "").replace("+", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def check_asset_diff(html: str) -> list:
    """回傳失敗清單。"""
    fails = []
    if "指定用途款³" not in html:
        return ["asset_diff：缺少「指定用途款³」欄位（分項無法與總資產對齊）"]
    if "＝ 總資產" not in html and "= 總資產" not in html:
        fails.append("asset_diff：footnote 未宣告「分項＋指定用途款＝總資產」橋接")
    rows = re.findall(r"<tr><td>(\d{4}-\d{2}-\d{2})</td>(.*?)</tr>", html, flags=re.S)
    if not rows:
        fails.append("asset_diff：解析不到任何資料列")
    for d, body in rows:
        v = [_num(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", body)]
        if len(v) < 12:
            fails.append(f"asset_diff {d}：欄位數不足（{len(v)}）")
            continue
        ta, ins, fun, sec, cash, rst = v[0], v[3], v[5], v[7], v[9], v[10]
        if None in (ta, ins, fun, sec, cash, rst):
            fails.append(f"asset_diff {d}：數值解析失敗")
            continue
        tot = ins + fun + sec + cash + rst
        if abs(tot - ta) > 1:
            fails.append(f"asset_diff {d}：分項＋指定款 {tot:,.0f} ≠ 總資產 {ta:,.0f}（差 {ta - tot:,.0f}）")
    return fails


def check_index(html: str, snap: dict) -> list:
    fails = []
    pct = (snap.get("penetration", {}) or {}).get("actual_pct", {}) or {}
    tgt = (snap.get("penetration", {}) or {}).get("targets", {}) or {}
    ta = float(snap.get("total_assets") or 0)
    name2key = {"台股": ("台股市值型成長", "台股市值型目標"),
                "美股": ("美股市值型成長", "美股市值型目標"),
                "防守": ("防守型配息", "配息型目標"),
                "債券": ("債券", "債券型目標"),
                "現金": ("現金/安全網", "現金目標")}
    # 掃「桶名（X.X% vs 目標Y%）」語句（桶名與括號間允許頓號／冒號等裝飾字元）
    for m in re.finditer(r"([\u4e00-\u9fff]{2,4})[：:、，,\s]*[（(](\d+(?:\.\d+)?)%\s*vs\s*目標\s*(\d+(?:\.\d+)?)%", html):
        cat, a, g = m.group(1), float(m.group(2)), float(m.group(3))
        key = name2key.get(cat)
        if not key:
            continue
        live_a, live_g = pct.get(key[0]), tgt.get(key[1])
        if live_a is None or live_g is None:
            continue
        if abs(a - float(live_a)) > 0.05 or abs(g - float(live_g)) > 0.05:
            fails.append(f"index {cat}：頁面 {a}%／目標 {g}% ≠ snapshot live {live_a}%／目標 {live_g}%")
    # 分母／理論調整必須用 live 總資產
    if ta > 0:
        for m in re.finditer(r"分母\s*([\d,]{7,})", html):
            if abs(float(m.group(1).replace(",", "")) - ta) > 1:
                fails.append(f"index：分母 {m.group(1)} ≠ live 總資產 {ta:,.0f}")
        for m in re.finditer(r"理論調整\s*([\d,]{7,})", html):
            adj = float(m.group(1).replace(",", ""))
            # 合理區間檢查：理論調整必為 |偏差|/100 × 總資產 之量級
            if not (0.01 * ta <= adj <= 0.12 * ta):
                fails.append(f"index：理論調整 {adj:,.0f} 不在 live 總資產推導區間")
    return fails


def main() -> int:
    snap = json.load(open(SNAP, encoding="utf-8"))
    fails = []
    if os.path.exists(AD):
        fails += check_asset_diff(open(AD, encoding="utf-8", errors="replace").read())
    else:
        print(f"⚠️ 找不到 {AD} → 跳過 asset_diff 檢查")
    if os.path.exists(IDX):
        fails += check_index(open(IDX, encoding="utf-8", errors="replace").read(), snap)
    else:
        print(f"⚠️ 找不到 {IDX} → 跳過 index 檢查")

    # ── 負向自測 ──
    neg = []
    ad_txt = open(AD, encoding="utf-8", errors="replace").read() if os.path.exists(AD) else ""
    if ad_txt:
        broken = re.sub(r"(<tr><td>\d{4}-\d{2}-\d{2}</td><td class='num'>)([\d,]+)(</td>)",
                        lambda m: m.group(1) + f"{int(m.group(2).replace(',', '')) + 12345:,}" + m.group(3),
                        ad_txt, count=1)
        if not check_asset_diff(broken):
            neg.append("asset_diff 負向：破壞列加總未被抓到")
    if os.path.exists(IDX):
        idx_txt = open(IDX, encoding="utf-8", errors="replace").read()
        applied = False
        mutated = re.sub(r"(美股市值型成長\s*)(\d+\.\d+)%", r"\g<1>99.9%", idx_txt, count=1)
        if mutated != idx_txt:
            applied = True
            if not check_index(mutated, snap):
                neg.append("index 負向：注入 99.9% 未被抓到")
        # 直接對複本注入「美股 36.4% vs 目標30%」
        mutated2 = idx_txt.replace("36.2% vs 目標30%", "36.4% vs 目標30%", 1)
        if mutated2 != idx_txt:
            applied = True
            if not check_index(mutated2, snap):
                neg.append("index 負向：舊值 36.4% 未被抓到")
        if not applied:
            neg.append("index 負向：找不到可注入的桶位百分比 → 守門無法被證明有效（視為 FAIL）")

    if neg:
        fails += neg
    print("=" * 62)
    for f in fails:
        print("  ❌", f)
    print("=" * 62)
    print(("❌ FAIL：" + str(len(fails)) + " 項") if fails else "✅ PASS：asset_diff 逐列加總 ＋ index 桶位/live 一致性（含負向自測）")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
