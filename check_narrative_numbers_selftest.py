#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_narrative_numbers_selftest.py — 內文數字守門的回歸自測（唯讀，不寫任何檔）

用途：收工稽核第 13 類會「先跑本檔再實掃」。守門本身被改壞（合法值集合漏掉某個
派生口徑、或比對被放寬成永遠通過）時，同一晚就會亮紅燈，而不是等下一次誤報才發現。

為什麼要有它（2026-09-25 教訓）：
  第 13 類自 2026-09-23 上線後，3 天內被「合法派生口徑不足」觸發 4 次
  （科技分母 → 現金派生 → 引擎偏移 → 偏移後目標值/建議金額）。
  每次都是同一種病：集合落後於內文會引用的口徑。修法是「補集合 + 補案例」，
  本檔就是把那些案例固定下來，防止回歸。

判準：正向案例必須放行、負向案例必須擋下；任一不符 → exit 1。
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import check_narrative_numbers as C  # noqa: E402

# (內文片段, 應放行?, 說明)
CASES: list[tuple[str, bool, str]] = [
    # ── 引擎口徑（2026-09-25 新增補洞）──
    ("債券 +5pp", True, "引擎戰術偏移（燈號偏移後 − 目標）"),
    ("美股 -8pp", True, "引擎戰術偏移（負向）"),
    ("美股 8pp", True, "引擎戰術偏移（內文寫成減碼幅度）"),
    ("債券 30%", True, "引擎偏移後目標值"),
    ("美股 22%", True, "引擎偏移後目標值"),
    ("債券 +9pp", False, "負向：不存在的偏移"),
    ("美股 12%", False, "負向：不存在的目標值"),
    # ── 引擎偏移 vs 現況缺口的口徑分流（2026-09-25 B 批）──
    ("偏移後債券 +5pp", True, "引擎偏移口徑（偏移後＝+5）"),
    ("偏移後債券 -5pp", False, "負向：引擎是加碼 +5，寫成減碼 → 擋"),
    ("超標：美股 +9.5pp", True, "現況缺口口徑（超標＝+9.5）"),
    ("超標：美股 -9.5pp", False, "負向：超標必為正缺口，寫成負 → 擋"),
    ("美股超標 9.5pp、債券 +5pp", True, "切段：鄰句『超標』不得污染債券的引擎值"),
    # ── 獨立複審抓到的兩條迴歸（2026-09-25，固定下來不再退化）──
    ("美股超標 9pp 但債券 +5pp", True, "回歸 V-A2：無標點的整數 pp 鄰句不得污染口徑"),
    ("偏移後科技 5pp", False, "回歸 V-B：口徑為引擎偏移但該標籤 off 為空 → 退回聯集擋下，不得靜默跳過"),
    # ── 避險衛星覆蓋（2026-09-25 B 批；修前這些標籤根本不存在＝從未被掃）──
    ("衛星 7%", True, "避險衛星合計偏移後目標"),
    ("避險衛星 7%", True, "同上（長標籤寫法）"),
    ("衛星 5%", False, "負向：非衛星列任何口徑的值"),
    ("黃金 5%", True, "刻意未註冊黃金標籤（會與金價 2,400 碰撞）→ 不掃"),
    ("衛星 +183.1萬", True, "萬為單位無千分位 → 金額型態不成立，不掃"),
    # ── known limitation：空集合＝該口徑不掃（既有設計，非本批引入）──
    # build_allowed 對每個標籤只補「它有來源」的口徑（LABEL_GICS 來源的標籤通常只有 pct），
    # scan_text 對空集合一律跳過比對。本批新增的「移除＋警示」只涵蓋 _engine_calibers
    # 新建的標籤；既有標籤的空集合（金融／資訊科技 無 twd、衛星／避險衛星 無 gap、
    # 現金 無 gap/off …）仍是不掃的。下面兩條把行為固定下來 —— 任何「改成會掃」的
    # 變動都必須是刻意的，不能順手改掉。
    ("金融 1,234,567", True, "known limitation：金融 無 twd 集合 → 金額不掃"),
    ("現金 5pp", True, "known limitation：現金 gap/off 皆空 → pp 不掃"),
    # ── 穿透真值（既有）──
    ("債券 +3.7pp", True, "現況缺口（佔總資產分母）"),
    ("債券 +4.7pp", True, "現況缺口（佔投資部位分母）"),
    ("科技 15.3%", True, "穿透真值"),
    ("防守型配息 17.3%", True, "穿透真值"),
    ("科技 17.5%", False, "負向：INC-245 原始案例（模型自行推算）"),
    # ── 現金派生口徑（INC-244）──
    ("現金 861,818", True, "現金原值"),
    ("現金 161,818", True, "乾粉＝現金 − 生活底線"),
    ("現金 1,200,000", True, "合計底線"),
    ("現金 999,999", False, "負向：不存在的現金金額"),
    # ── 守門不該掃的型態（零假陽性合約）──
    ("高科技/半導體 17.5%", True, "複合詞不掃（刻意不比）"),
    ("防守合併 68.5%", True, "中介詞句子不掃"),
    ("科技目標 ≤20%", True, "中介詞句子不掃"),
]


def main() -> int:
    snap = C._load(BASE / "snapshot.json") or {}
    allowed = C.build_allowed(snap)
    fails = 0
    for text, expect_pass, note in CASES:
        hits = C.scan_text(text, allowed, "SELFTEST")
        ok = (not hits) == expect_pass
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'} | {'應放行' if expect_pass else '應擋下'} | {text} | {note}"
              + ("" if ok else f" | hits={hits}"))
    # 印 gap（現況缺口）／off（引擎偏移）／pct 三集合：口徑拆分後 gap 不再含引擎值，
    # 只看 gap 會誤以為引擎口徑消失了（收工稽核第 13 類讀的就是這一行）。
    print(f"--- 內文守門自測：{len(CASES) - fails}/{len(CASES)} 通過"
          f"｜債券 gap={sorted(allowed['債券']['gap'])} off={sorted(allowed['債券']['off'])}"
          f" pct={sorted(allowed['債券']['pct'])}")
    if fails:
        print("❌ 自測未過 → 守門本身有問題，先修守門再談內文")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
