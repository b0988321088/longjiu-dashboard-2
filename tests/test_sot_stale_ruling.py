# -*- coding: utf-8 -*-
"""sot_targets.refresh_stale_amounts：失效敘述覆蓋（押標金取消）正反例

2026-10-12：日報與再平衡報表共用此刷新層嵌入「緊急應變 LLM 內文」。
內文可能仍以「押標金 240 萬＝條件式事件／檢視日 10-15」敘述 → 由 snapshot 狀態驅動覆蓋。
獨立審查首版 REJECT 後硬化（語境錨定 regex／日期驗證／fail-loud 示警），本檔同步覆蓋：
  · 正例：四種失效措辭皆被覆蓋
  · 反例：狀態未取消／缺欄位／空輸入 → 零改動（不寫死）
  · 反例：同金額但**不同語境**（未含失效片語）→ 不得被動到
  · 邊界：裁示日格式不合法 → 不得把未驗證字串寫進產物
執行：python -X utf8 tests/test_sot_stale_ruling.py
"""
from __future__ import annotations
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from sot_targets import refresh_stale_amounts as R  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" ｜{detail}" if detail and not cond else ""))


def run_capture(text, snap):
    buf = io.StringIO()
    with redirect_stdout(buf):
        out = R(text, snap)
    return out, buf.getvalue()


CANCELLED = {"標案押標金_1010": {"狀態": "❌ 已取消（2026-10-12 使用者裁決）", "裁示日_取消": "2026-10-12"}}
CANCELLED_BADDATE = {"標案押標金_1010": {"狀態": "❌ 已取消", "裁示日_取消": "2026/10/12"}}
PENDING = {"標案押標金_1010": {"狀態": "⏳ 來源暫空、待重估"}}
RAW = ("要做的事只有既有已核准項：配息導流、保單內部標的轉換批次（不受紅線限制）、"
       "10/15 標案押標金來源的資訊蒐集。\n"
       "⑥ 條件式事件：10 月標案押標金 2,400,000 元，未得標不屬 90 天已確認需求，"
       "不預先辦理保證函；檢視日 2026-10-15。\n"
       "另註：10 月標案押標金 240 萬來源定案（不得預設由 540 萬撥款支付）\n"
       "質押句尾：10月標案押標金不預留，9月底評估")

out = R(RAW, CANCELLED)
check("正例：移除『要做的事』中的押標金資訊蒐集", "資訊蒐集" not in out)
check("正例：⑥ 條件式事件改寫為已取消", "已於 2026-10-12 經使用者裁決取消" in out and "檢視日 2026-10-15" not in out)
check("正例：來源定案卡措辭改為（已取消）", "10 月標案押標金 240 萬（已取消：2026-10-12）" in out)
check("正例：舊質押句改為已取消", "9月底評估" not in out and "10 月標案押標金已取消（2026-10-12）" in out)
check("正例：其餘內文不動（配息導流那段保留）", "配息導流、保單內部標的轉換批次" in out)

neg = R(RAW, PENDING)
check("反例：狀態未取消 → 一個字都不改", neg == RAW, str(neg[:60]))
check("反例：缺 標案押標金_1010 欄位 → 不改", R(RAW, {}) == RAW)
check("反例：空字串輸入安全", R("", CANCELLED) == "")

# 反例（獨立審查 Finding：不得誤傷同金額其他語境）
OTHER = "本季檢討：10 月標案押標金 240 萬屬於第二職涯營運桶的週轉需求說明（非本輪裁決範圍）。"
check("反例：同金額但不同語境 → 不得被改寫", R(OTHER, CANCELLED) == OTHER, str(R(OTHER, CANCELLED))[:80])

# 邊界：日期格式不合法 → 不把未驗證字串寫進產物 + 具名示警
o2, w2 = run_capture(RAW, CANCELLED_BADDATE)
check("邊界：裁示日格式不合法 → 產物不含該字串", "2026/10/12" not in o2)
check("邊界：裁示日格式不合法 → 具名 WARN（不靜默）", "[WARN]" in w2 and "YYYY-MM-DD" in w2, w2[:120])

# 邊界（審查 Finding：schema 變動不得靜默）
o3, w3 = run_capture(RAW, PENDING)
check("邊界：內文有失效片語但狀態未載明取消 → fail-loud WARN", "[WARN]" in w3 and "未覆蓋" in w3, w3[:140])

print(f"\n通過 {len(PASS)} 項｜失敗 {len(FAIL)} 項")
sys.exit(1 if FAIL else 0)
