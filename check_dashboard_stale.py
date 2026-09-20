#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_dashboard_stale.py — 產出檔 index.html 的「舊值殘留」掃描（單一入口）

背景（2026-09-20 修正假陽性）：
  原掃描邏輯內嵌在 sync_all.py 的步驟清單裡（一行 python -c），只做 `值 in html` 的
  字串比對 → 它分不清「活的顯示值」與「引用的歷史文字」。9/20 實踩：9/16 CIO 審查全文
  （歸檔於 `<details class="cio-old">` 與 JS 註解裡的離線快照）內含「可動用 772,607」，
  該數字是 9/16 當日的真值引用，卻被當成殘留舊值 → sync_all 在最後一步中止
  （其餘步驟其實全過，須人工補跑）。

判準（只排除「不渲染 / 已歸檔」的區塊，不放寬真正的顯示值與 JS 硬編碼）：
  ① HTML 註解 `<!-- ... -->`、JS 註解 `/* ... */`  → 不渲染，排除
  ② `<details class="cio-old" ...>...</details>`  → CIO 審查「看全文」歸檔區，排除
  ③ 其他一律照掃：**含 <script> 內的 JS 陣列/fallback 硬編碼**
     （2026-08-29 血淚：JS 內 '房租已收',78000 / || 62969 不經 rep dict，只掃 HTML 會漏）

用法：
  python check_dashboard_stale.py [index.html]     # 預設 index.html
退出碼：0 = 乾淨；1 = 有殘留（附落點與上下文）
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGET = BASE / (sys.argv[1] if len(sys.argv) > 1 else "index.html")

# 舊值清單（canonical：2026-08-29 全量盤點＝配息口徑舊值 + 穿透卡五桶舊市值 +
# 保單A舊值 + 當月已收舊值 + 監控卡片合計舊值 + JS 內舊值）
STALE = [
    "35,583", "63,027", "2,723,839", "7,753,544", "88,507", "109,645",
    "143.9%", "144%", "199,960", "62,969", "78000", "78,000",
    "5,103,722", "1,889,388", "11,499,725", "1,089,462", "5,917,259",
    "5,798,988", "3,735,174", "7,764,551", "14.3%", "-0.7pp", "799,612",
    "815,066", "20260821_1", "20260829_1", "772,607", "123,607",
    "27,738", "499,316", "458,343", "20,776", "6,960", "0 TWD（應收 2,100）",
    "753,388", "138,627", "102,469", "243,434", "225,918",
]

RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_JS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RE_CIO_OLD = re.compile(r'<details[^>]*class="cio-old".*?</details>', re.S)


def scannable(html: str) -> str:
    """回傳「需要比對的區塊」＝原文扣除不渲染／已歸檔區塊。"""
    out = RE_CIO_OLD.sub(" ", html)
    out = RE_JS_COMMENT.sub(" ", out)
    out = RE_HTML_COMMENT.sub(" ", out)
    return out


def scan(html: str):
    """回傳 [(值, 上下文), ...]（空 = 乾淨）。"""
    text = scannable(html)
    hits = []
    for v in STALE:
        for m in re.finditer(re.escape(v), text):
            ctx = text[max(0, m.start() - 70):m.start() + 40].replace("\n", " ")
            hits.append((v, ctx))
    return hits


def main() -> int:
    if not TARGET.exists():
        print(f"❌ 找不到 {TARGET.name}")
        return 1
    html = TARGET.read_text(encoding="utf-8", errors="replace")
    hits = scan(html)
    if hits:
        print(f"❌ 儀表板殘留舊值 {len(hits)} 處（{TARGET.name}）：")
        for v, ctx in hits[:12]:
            print(f"   - {v} @ ...{ctx}...")
        if len(hits) > 12:
            print(f"   …其餘 {len(hits) - 12} 處省略")
        print(f"   ℹ️ 只掃『會被渲染的區塊』（HTML/JS 註解、cio-old 歸檔區已排除）— "
              f"若此值確實是活的顯示值，修法是讓它讀 snapshot，不是加豁免。")
        return 1
    print(f"✅ 儀表板無舊值殘留（{TARGET.name}｜掃描 {len(scannable(html)):,} 字元，"
          f"排除註解與 cio-old 歸檔區）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
