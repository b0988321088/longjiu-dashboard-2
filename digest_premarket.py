#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盤前 digest：把 09:00–09:20 原本各自推的 6 支檢查合成一則（2026-11-25 使用者核准）

理由：原本早上 20 分鐘內會有 5–6 則通知（標案×3、盤前、質押、保單），
一次一坨等於沒有優先序。合併後只發一則，有內容的才列。

規則（沿用並強化使用者裁決的「只推三種」）：
- 各支腳本自己判斷要不要出聲（沒事的本來就無輸出）。
- 本支只做「收集＋排版」，不新增判斷、不改各支邏輯。
- 全部無輸出 → 完全不輸出（cron 靜默）。
- 任一腳本執行失敗 → 在該節標「⚠️ 檢查失敗」並附最後一行錯誤（不得靜默失敗）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(os.environ.get("LOCALAPPDATA", r"C:\Users\bot\AppData\Local")) / "hermes" / "scripts"

# (腳本, 顯示標題, 逾時秒)
TARGETS = [
    ("alerts_morning.py", "健康度／紅線", 90),
    ("taipower_tender_watch.py", "台電標案", 180),
    ("design_supervision_watch.py", "中部設計監造小額案", 240),
    ("forestry_supervision_watch.py", "林業署設計監造", 120),
    ("pledge_maintenance_alert.py", "質押維持率", 90),
    ("policy_switch_watch.py", "保單轉換時機", 90),
]


def _run(script: str, timeout: int) -> tuple[str, str | None]:
    p = SCRIPTS / script
    if not p.exists():
        return "", f"找不到脚本 {script}"
    try:
        r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return "", f"逾時 {timeout}s"
    out = (r.stdout or "").strip()
    if r.returncode != 0:
        tail = ((r.stderr or "").strip().splitlines() or [""])[-1][:120]
        return out, f"rc={r.returncode}｜{tail}"
    return out, None


MAX_LINES = 12


def _cap(text: str, max_lines: int = MAX_LINES) -> str:
    """單節上限：digest 不是報表，超過就截斷並註明去哪裡看全文。
    2026-11-25：台電標案原本一次列 24 筆把整則通知淹掉。"""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    _tail = f"…（另有 {len(lines) - max_lines} 行，完整內容請見採購網／來源腳本）"
    return "\n".join(lines[:max_lines] + [_tail])


def build() -> str:
    """6 支並行跑：原本串行最壞要 8 分鐘，cron 會逾時；並行後牆鐘≈最慢那支。"""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=len(TARGETS)) as ex:
        futs = [(t, ex.submit(_run, sc, to)) for sc, t, to in TARGETS]
        results = [(t, *f.result()) for t, f in futs]
    blocks = []
    for title, out, err in results:
        if err:
            blocks.append(f"⚠️【{title}】檢查失敗：{err}")
        elif out:
            blocks.append(f"【{title}】\n{_cap(out)}")
    if not blocks:
        return ""
    now = datetime.now()
    head = f"🌅 盤前 digest（{now.strftime('%m/%d %H:%M')}）— 只列有事項"
    return "\n\n".join([head] + blocks)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    out = build()
    if not out:
        if a.dry_run:
            print("今日 6 支檢查全部無事項 → 靜默（不推播）")
        return 0
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
