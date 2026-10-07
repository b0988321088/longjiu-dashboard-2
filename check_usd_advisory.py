#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_usd_advisory.py — 卡② 硬性防呆閘門（唯讀、可重複執行）。

用途：即使 prompt 未被遵守、或哪個模組忘了吃 advisory_only，只要 **產出檔**裡出現
「美元曝險＋資產調整指令」的句子，本閘門就 FAIL（exit 1），阻擋後續 commit/push。

規則：usd_exposure_monitor.advisory_only 為真時，掃描指定產出檔，命中
usd_advisory.violations 即 FAIL；非 advisory 時一律 SKIP（exit 0，維持舊行為）。

排除項（避免誤判歷史存檔）：含 'emergency_report_'（緊急應變存檔連結標記）或
'已作廢'（明示作廢段）的「行」不列入判定 —— 這些是歷史區塊，非本輪產出。

用法：
  python check_usd_advisory.py [YYYY-MM-DD]      # 掃當日產出檔
  python check_usd_advisory.py --files a.html b.html
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from usd_advisory import is_advisory, violations  # noqa: E402

# 靜態政策區塊與歷史存檔不是「本輪 LLM 產出」，不列入判定（避免誤擋產線）。
SKIP_MARKERS = ("emergency_report_", "已作廢", "因應三步驟", "三階段執行路徑")
_ARCHIVE_START = ("緊急應變分析區塊", "緊急應變資料：")


def _scan_lines(text: str):
    """逐行掃描；跳過緊急應變存檔區段（起點→存檔連結）與 SKIP_MARKERS 行。"""
    skipping = False
    for line in text.split("\n"):
        if any(s in line for s in _ARCHIVE_START):
            skipping = True
        if skipping:
            if "emergency_report_" in line:
                skipping = False
            continue
        if any(m in line for m in SKIP_MARKERS):
            continue
        yield line


def default_files(today: str) -> list:
    """掃描面＝LLM 產出物本身（2026-10-07 第三版定案）。

    為何不掃 HTML 報告：日報／儀表板內含大量**非 LLM** 的靜態與歷史區塊（緊急應變存檔、
    風險卡內文、帳戶清單…），這些內容合法且不該被本閘門判定；而報告裡的 LLM 段落
    來源就是下列檔案 → 在這裡擋住，等於在源頭擋住所有下游報告。
    """
    stamp = today.replace("-", "")
    files = []
    # 每個任務只取「當日最新」那一份（＝現行 prompt 指紋產生、已在中和後寫入的那份）；
    # 同日舊指紋的殘留快取是 pre-scrub 素材，不代表任何已發布內容，不列入判定。
    for pat in ("buffett_cto_report_*.md", "buffett_*.json", "cto_*.json", "cio_llm_*.json",
                "data/buffett_*.json", "data/cto_*.json", "data/cio_llm_*.json"):
        cands = [f for f in BASE.glob(pat) if (today in f.name or stamp in f.name)]
        if cands:
            files.append(max(cands, key=lambda f: f.stat().st_mtime))
    return files


def main() -> int:
    args = [a for a in sys.argv[1:]]
    if "--files" in args:
        i = args.index("--files")
        files = [Path(a) for a in args[i + 1:]]
    else:
        from datetime import date
        today = args[0] if args else date.today().isoformat()
        files = default_files(today)

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    if not is_advisory(snap):
        print("➖ 美元曝險非 advisory_only → 跳過（exit 0）")
        return 0

    total_hits, scanned = [], 0
    for f in files:
        if not f.exists():
            continue
        scanned += 1
        text = f.read_text(encoding="utf-8", errors="ignore")
        for line in _scan_lines(text):
            # strict=False：閘門只認「明確的資產調整指令」，避免誤擋合法政策/歷史內容
            for h in violations(line, snap, strict=False):
                total_hits.append((f.name, h["主體"], h["動詞"], h["片段"]))

    if total_hits:
        print(f"❌ 美元曝險 advisory 閘門：{len(total_hits)} 處把『僅顯示』寫成資產調整指令")
        for fn, subj, verb, seg in total_hits[:12]:
            print(f"   · [{fn}] {subj}＋{verb}：{seg}")
        print("   → 修正產出（重跑產線會自動中和），或確認該句不屬本輪產出")
        return 1
    print(f"✅ 美元曝險 advisory 閘門通過（掃描 {scanned} 檔，無資產調整指令）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
