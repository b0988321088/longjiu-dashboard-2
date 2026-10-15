#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_daily_report_penetration_live.py — 日報「五桶佔比」段落必須等於當日真值（回歸）

背景（2026-10-15 真 CIO 重審 blocking）：
    日報會原樣嵌入緊急應變內文（data/emergency_llm_analysis.json，前一產出日）。
    該內文的【四、資產配置透視】帶有「當日」數字（現金／總資產／債券佔比），
    現金真值更新後（1,055,740 → 1,170,934；總資產 26,970,031 → 27,085,225），
    同一份日報同時出現兩套真值 → 屬 blocking。

修法：sot_targets.refresh_stale_amounts 於嵌入時以 snapshot.penetration 即時覆蓋
    （佔比一律重算，不硬編 26.4% 之類字面值）。

本測試兩層：
    A. 單元：餵入「前一日的舊值文本」→ 產出必須為 live 值、舊值必須消失、且具冪等性。
    B. 產物：掃 actual daily_report_v2_<date>.html 的「五桶佔比」句，
       逐桶比對 snapshot.penetration.actual_pct / actual_twd；
       並確認全檔無舊值（26,970,031／1,055,740／355,740／26.4%／36.4%／3.9%）。
    C. 負向自測：把舊值文本直接餵給 B 的檢查器 → 必須被抓到（證明檢查器有牙）。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PASS = FAIL = 0
FAILS = []


def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        FAILS.append(name)
        print(f"  ❌ {name}｜{detail}")


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return json.load(f)


BUCKETS = [("台股市值型成長", "台股市值型成長"),
           ("美股市值型成長", "美股市值型成長"),
           ("防守型配息", "防守型配息"),
           ("債券", "債券"),
           ("現金", "現金/安全網")]

STALE_TOKENS = ("26,970,031", "1,055,740", "355,740")
# 舊值樣式（regex）：含左邊界，避免把「43.9%」的尾數誤判成舊值「3.9%」
STALE_PATTERNS = tuple(re.escape(t) for t in STALE_TOKENS) + (
    r"(?<![\d.])26\.4%", r"(?<![\d.])36\.4%", r"(?<![\d.])3\.9%")


def stale_hits(text: str) -> list:
    return [p for p in STALE_PATTERNS if re.search(p, text)]

# 前一日（真值更新前）的內文樣本 —— 取自 data/emergency_llm_analysis.json 的實際結構
STALE_SAMPLE = (
    "五桶佔比：台股市值型成長 9.2%（2,468,426）｜美股市值型成長 36.4%"
    "（9,808,190；科技 14.5%＝3,907,015、非科技 21.9%＝5,901,175）"
    "｜防守型配息 17.7%（4,782,077）｜債券 26.4%（7,114,069）｜現金 3.9%（1,055,740）。"
    "衛星：黃金 325,171、健康 516,358；指定款 900,000；在途 0。"
    "不變量核對：五桶＋在途＋衛星＋指定款＝總資產 26,970,031 ✓。"
    "⑤ 現金：可動用 1,055,740 高於現金底線 700,000，餘裕（乾粉）355,740 → 維持乾粉。"
)


def check_penetration_live(text, snap, label):
    """核心檢查器：回傳 (ok, 說明)。B 與 C 共用 → 負向自測才有意義。"""
    p = snap.get("penetration") or {}
    pct = p.get("actual_pct") or {}
    twd = p.get("actual_twd") or {}
    ta = snap.get("total_assets")
    hits = list(re.finditer(r"五桶(?:佔比|與缺口)[^。]{0,400}", text))
    if not hits:
        return False, f"{label}：找不到『五桶佔比／五桶與缺口』段落（格式已變，不得靜默放行）"
    seg = hits[0].group(0)
    # 不變量句通常自成一句（在句號之後）→ 另取視窗，避免只看五桶句
    inv = re.search(r"不變量核對[^。]{0,160}", text)
    problems = []
    for disp, key in BUCKETS:
        # 「現金」在日報寫作「現金/安全網」→ 一併接受（同一桶、同一真值鍵）
        m = re.search(rf"{re.escape(disp)}(?:/安全網)?\s*(\d+(?:\.\d+)?)%（([\d,]+)", seg)
        if not m:
            problems.append(f"{disp} 未出現「X.X%（金額）」")
            continue
        got_pct, got_amt = float(m.group(1)), float(m.group(2).replace(",", ""))
        if abs(got_pct - float(pct.get(key, -1))) > 0.05:
            problems.append(f"{disp} 佔比 {got_pct}% ≠ live {pct.get(key)}%")
        if abs(got_amt - float(twd.get(key, -1))) > 1:
            problems.append(f"{disp} 金額 {got_amt:,.0f} ≠ live {twd.get(key, 0):,.0f}")
    # 不變量核對句：run_daily 產出的日報含此句、regenerate_report 產出者不含
    #（雙 producer 既有差異 PEND-20261007-02）→ 不存在時不記 problem，但也不假裝驗過。
    if inv:
        m = re.search(r"總資產\s*([\d,]+)", inv.group(0))
        if not m or abs(float(m.group(1).replace(",", "")) - float(ta)) > 1:
            problems.append(f"不變量句總資產 {m.group(1) if m else '缺'} ≠ live {ta:,}")
    stale = stale_hits(seg)
    if stale:
        problems.append(f"段落仍含舊值 {stale}")
    return (not problems), f"{label}：" + ("；".join(problems) if problems else "全部等於當日真值")


print("═══ A. 單元：嵌入時以 snapshot 即時覆蓋 ═══")
import sot_targets  # noqa: E402

snap = load("snapshot.json")
fixed = sot_targets.refresh_stale_amounts(STALE_SAMPLE, snap)
_for_unit = dict(snap)
ok("A1 舊值經覆蓋後全部消失",
   not stale_hits(fixed),
   f"殘留 {stale_hits(fixed)}")
ok("A2 覆蓋後出現 live 總資產／可動用／乾粉",
   f"{snap['total_assets']:,}" in fixed and "1,170,934" in fixed and "470,934" in fixed)
_ok_seg, _why = check_penetration_live(fixed, snap, "覆蓋後")
ok("A3 覆蓋後段落通過 live 檢查", _ok_seg, _why)
ok("A4 冪等（再跑一次結果相同）",
   sot_targets.refresh_stale_amounts(fixed, snap) == fixed)

# 負向：snapshot 缺 penetration 時不得把舊值當成 live
_no_pen = json.loads(json.dumps(snap))
_no_pen.pop("penetration", None)
_left = sot_targets.refresh_stale_amounts(STALE_SAMPLE, _no_pen)
_ok2, _why2 = check_penetration_live(_left, snap, "缺 penetration")
ok("A5 缺 penetration 時，舊值文本仍會被 A 的檢查器抓到（不靜默）", not _ok2, _why2)

print("═══ B. 產物：當日日報 ═══")
html_files = sorted([f for f in os.listdir(ROOT)
                     if re.fullmatch(r"daily_report_v2_\d{4}-\d{2}-\d{2}\.html", f)])
latest = html_files[-1] if html_files else None
if latest:
    html = open(os.path.join(ROOT, latest), encoding="utf-8", errors="replace").read()
    okf, whyf = check_penetration_live(html, snap, latest)
    ok(f"B1 {latest} 五桶段等於當日真值", okf, whyf)
    stale_all = stale_hits(html)
    ok(f"B2 {latest} 全檔無舊值殘留", not stale_all, f"殘留 {stale_all}")
else:
    ok("B1 找不到日報產物", False)

print("═══ C. 負向自測：檢查器必須抓到未修的舊值文本 ═══")
_okc, _whyc = check_penetration_live(STALE_SAMPLE, snap, "舊值樣本")
ok("C1 舊值樣本被判不通過（檢查器有牙）", not _okc, _whyc)
_missing = "五桶佔比：全部刪光（模擬 producer 格式改變）"
_okd, _whyd = check_penetration_live(_missing, snap, "格式變更")
ok("C2 格式改變時判不通過（不得靜默放行）", not _okd, _whyd)

print(f"\n{'='*54}\n測試結果：{PASS} PASS / {FAIL} FAIL")
if FAILS:
    print("失敗項：" + "、".join(FAILS))
sys.exit(1 if FAIL else 0)
