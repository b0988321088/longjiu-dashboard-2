#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_skills_stale_pledge_0915.py — 技能庫舊質押口徑清理（2026-09-15 使用者指示）。

做法：①在受影響技能首頁插入「口徑更新」橫幅（一行，後續所有舊數字以它為準）
      ②把以「現況」姿態出現的舊數字就地更正（350萬→540萬、MMF 指定用途→已轉 B11）
歷史段落（標明 8/xx 版、v1/v2 舊計畫）不改，只靠橫幅設限。
"""
from pathlib import Path

SK = Path(r"C:/Users/bot/AppData/Local/hermes/skills")

BANNER = ("> ⚠️ **口徑更新（2026-09-15 清查）**：本文若見「擔保池 700 萬 → 質押 350 萬」"
          "或「MMF 500/600 萬＝10 月標案預備金」，一律以本行為準 —— 兩者皆已作廢。"
          "現行＝擔保池 **1,200 萬**（富達 600＋聯博 100＋貝萊德 B11 500）×4.5 成 ＝ 質押 **540 萬@2.77%**"
          "（9/11 僅額度核定、未對保，~9/25 撥款）→ 全數清償 500 萬高息負債（保單 400@4%＋券商 100@3.92%）；"
          "10 月押標金 240 萬來源延 9 月底評估；MMF 500 萬已於 9/9 贖回、9/11 轉申購 B11（質押擔保池）。")

TARGETS = [
    "financial/debt-restructure-execution/SKILL.md",
    "financial/debt-restructure-arbitrage-engine/SKILL.md",
    "financial/debt-restructure-arbitrage-engine/references/pledge-ltv-safety-0822.md",
    "financial/financial-report-calibration/SKILL.md",
    "financial/financial-report-calibration/references/cashflow-dual-perspective-and-daa-targets-0822.md",
    "financial/fund-component-breakdown/SKILL.md",
    "financial/fund-component-penetration/SKILL.md",
    "financial/investment-philosophy/SKILL.md",
    "financial/dynamic-asset-allocation/SKILL.md",
    "financial/rebalance-monitoring-sop/SKILL.md",
    "financial/longjiu-cashflow-analysis/SKILL.md",
    "financial/macro-regime-daa-v3/SKILL.md",
    "buffett-style-asset-analysis/SKILL.md",
    "asset-penetration-update-sop/SKILL.md",
    "longjiu/radar-data-sync/SKILL.md",
    "longjiu/dashboard-single-source/SKILL.md",
    "longjiu/longjiu-pipeline-governance/SKILL.md",
    "software-development/python-rendering-pitfalls/SKILL.md",
]

# 就地更正（以「現況」姿態出現的舊數字）
FIXES = [
    ("PI 質押 350萬@2.77%", "國泰整池質押 540萬@2.77%"),
    ("質押 350萬@2.77% 還 4.2%/3.92% 債 = 年省 48,650",
     "質押 540萬@2.77% 清償 4%/3.92% 債 = 年省 19.9 萬"),
    ("PI 富達質押 350萬@2.77%", "國泰整池質押 540萬@2.77%（1,200 萬×4.5 成）"),
    ("質押息（富達 350萬×2.77%÷12 = 8,083）", "質押息（整池 540萬×2.77%÷12 = 12,465）"),
    ("富達質押息 8,083/月（350萬×2.77%÷12", "質押息 12,465/月（540萬×2.77%÷12"),
    ("`funds_cathay`（富達600+聯博100+MMF500=1,200萬）",
     "`funds_cathay`（富達 5,853,439＋聯博 971,483＋貝萊德B11 4,981,060＝11,805,982；MMF 500 萬已於 9/11 轉 B11）"),
    ("MMF 500萬（標案300+補救200）", "貝萊德B11 500萬（質押擔保池）"),
    ("MMF 500萬已指定標案/質押補救", "MMF 500 萬已轉申購 B11 擔保品"),
    ("PI 後從 MMF 500萬 撥出", "PI 後（原 MMF 500 萬已轉 B11，實際執行改由現金流）"),
    ("- 8/20 定案後執行鏈（富達600萬+MMF600萬→PI認列→質押300萬@2.77%還安聯→標案預備金）相關討論",
     "- ⛔ 舊口徑（已作廢 9/11／9/12，僅供對照）：8/20 定案後執行鏈（富達600萬+MMF600萬→PI認列→質押300萬@2.77%還安聯→標案預備金）"),
    ("質押 350萬 / 擔保池700萬", "質押 540萬 / 擔保池1,200萬"),
    ("現行 LTV 執行版", "現行 LTV 執行版（⚠️ 本檔為 8/22 版；現行口徑見檔首橫幅）"),
]

changed, banner_added, unmatched = [], [], []

for rel in TARGETS:
    p = SK / rel
    if not p.exists():
        unmatched.append((rel, "檔案不存在")); continue
    t = p.read_text(encoding="utf-8")
    orig = t
    for old, new in FIXES:
        if old in t and new not in t:
            t = t.replace(old, new)
            changed.append((rel, old[:40]))
    if "口徑更新（2026-09-15 清查）" not in t:
        lines = t.split("\n")
        # 找 frontmatter 結束（第二個 ---）
        ins = 0
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    ins = i + 1
                    break
        lines.insert(ins, "\n" + BANNER + "\n")
        t = "\n".join(lines)
        banner_added.append(rel)
    if t != orig:
        p.write_text(t, encoding="utf-8")
        print(f"✍️  {rel}（修正 {sum(1 for o,_ in FIXES if o in orig)} 處；橫幅{'＋' if rel in banner_added else '已有'}）")

print(f"\n=== 橫幅新增 {len(banner_added)} 檔｜就地更正 {len(set(c[0] for c in changed))} 檔 ===")
print("未命中清單：", unmatched if unmatched else "無")
