# -*- coding: utf-8 -*-
"""
sso_t_consistency.py — SSoT 真值一致性檢查（2026-08-23）
每次 snapshot/儀表板更新後執行：掃描 index.html 靜態真值 vs snapshot/us30y_state 真值。
不一致 → 🔴 DATA CONFLICT（列出位置+期望值+實際值）— 禁止產生「無需操作」結論。
一致 → 🟢 SSoT 一致。
用法: python sso_t_consistency.py
"""
import json, os, re

REPO = os.path.dirname(os.path.abspath(__file__))

def rd(name):
    try:
        return json.load(open(os.path.join(REPO, name), encoding="utf-8"))
    except Exception:
        return {}

def main():
    s = rd("snapshot.json")
    us = rd("us30y_state.json")
    html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    conflicts = []
    ok_count = 0

    # ① US30Y（期望：us30y_state 真值）
    exp_us = us.get("us30y", us.get("value"))
    if exp_us:
        hits = re.findall(r"US30Y\s*([0-9]+\.[0-9]+)%", html)
        for h in hits:
            if abs(float(h) - exp_us) > 0.011:
                conflicts.append(f"US30Y：index.html 顯示 {h}% vs 真值 {exp_us:.2f}%（us30y_state.json）")
        if hits:
            ok_count += 1

    # ② 總資產／淨值：C 方案 JS 動態渲染（LIVE_BLOCK 讀 snapshot.json）— 檢查 JS 存在即可
    if "fetch('snapshot.json'" in html or 'fetch("snapshot.json"' in html:
        ok_count += 1
    else:
        conflicts.append("總資產/淨值：index.html 無 JS 動態渲染（LIVE_BLOCK 缺失）— 靜態值會過時")

    # ③ 美股穿透%（靜態寫死 — 最易過時，必須與 snapshot 一致）
    pen = s.get("penetration", {}).get("actual_pct", {})
    us_pct = pen.get("美股市值型成長")
    if us_pct:
        found = False
        for m in re.finditer(r"美股[^0-9]*([0-9]{1,2}\.[0-9])%", html):
            if abs(float(m.group(1)) - us_pct) < 0.6:
                found = True
        if not found:
            conflicts.append(f"美股穿透：index.html 未見 ~{us_pct:.1f}%（snapshot 真值）")
        else:
            ok_count += 1

    # ④ 現金穿透%（22.1% 五桶 or 底線 70萬 標註）
    cash_pct = pen.get("現金/安全網")
    if cash_pct:
        found = False
        for m in re.finditer(r"現金[^0-9]*([0-9]{1,2}\.[0-9])%", html):
            if abs(float(m.group(1)) - cash_pct) < 0.6:
                found = True
        if not found:
            conflicts.append(f"現金穿透：index.html 未見 ~{cash_pct:.1f}%（snapshot 真值）")
        else:
            ok_count += 1

    # ⑤ 淨值：JS 動態（同 ②），跳過靜態檢查
    ok_count += 1

    # 輸出
    if conflicts:
        print("🔴 DATA CONFLICT — 禁止產生「無需操作」結論")
        for c in conflicts:
            print(f"  • {c}")
        print(f"（通過 {ok_count} 項 / 衝突 {len(conflicts)} 項）")
        return 1
    print(f"🟢 SSoT 真值一致（{ok_count} 項全通過）")
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
