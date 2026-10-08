#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""truth_day_finalize.py — 真值日更新後的「固定入口」（2026-10-09 建立；PEND #12）

問題（實證）：
  真值日的步驟 4（留停驗收表）與 4b（Coast FI --write）原本只寫在 monthly-truth-day SOP
  的文字裡，由 LLM 自行決定跑不跑。結果 2026-10 真值日發生：步驟 4 跑到 2026-10、
  步驟 4b 停在 2026-09-28（同一批真值日、後半步被跳過），而當時沒有任何閘門發現。

目的：
  把「LLM 記得跑」改成「跑一支腳本就會做」——順序固定、失敗看得見、可重複執行。

固定順序（勿調換）：
  ① sabbatical_checklist_update.py      步驟 4    留停驗收表（記錄[當月]／A-B-C 驗收）
  ② coast_fi_engine.py --write          步驟 4b   Coast FI 四指標寫回 snapshot
  ③ coast_fi_engine.py --notify         步驟 4b   燈號有變才輸出（相同則完全靜默）
  ④ post_update_reminder.py             步驟 6    固定格式回覆（3-5 行）

失敗契約：
  ① ② 為硬性步驟 → rc 不允許即中止、回非 0（② 只接受 0）。
  ① 允許 rc=2（＝副本缺漏警示，主工作已完成；sabbatical_checklist_update.py 既有契約）。
  ③ ④ 為輸出步驟 → 失敗只警告不中止（不讓提醒步驟擋掉已完成的資料更新）。

搭配閘門：
  check_thresholds.py ②g「Coast FI freshness」——真值已定稿（DB assets[真值日] 已落）
  但 snapshot.coast_fi_engine.asof 仍早於真值日 → rc=1 fail-closed。
  該閘門掛在 sync_all.py 的「門檻SoT檢查」步驟（fail-closed），因此本腳本未跑會被擋關。

用法：
  python truth_day_finalize.py          # 依序執行四步
  python truth_day_finalize.py --dry    # 只列將執行的步驟，不執行
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent

# (標籤, 參數, 硬/軟, 可接受的 rc 集合)
STEPS: list[tuple[str, list[str], str, set[int]]] = [
    ("步驟 4　留停驗收表", ["sabbatical_checklist_update.py"], "hard", {0, 2}),
    ("步驟 4b Coast FI 寫回", ["coast_fi_engine.py", "--write"], "hard", {0}),
    ("步驟 4b Coast FI 燈號", ["coast_fi_engine.py", "--notify"], "soft", {0}),
    ("步驟 6　更新後提醒", ["post_update_reminder.py"], "soft", {0}),
]


def run_step(label: str, args: list[str], kind: str, ok_codes: set[int]) -> bool:
    cmd = [sys.executable, *args]
    print("=" * 62)
    print(f"▶ {label}　$ python {' '.join(args)}")
    print("=" * 62)
    try:
        p = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except Exception as e:                                  # 找不到直譯器／腳本
        print(f"❌ {label} 無法執行：{e}")
        return False
    out = ((p.stdout or "") + (p.stderr or "")).rstrip()
    if out:
        print(out)
    if p.returncode in ok_codes:
        note = "" if p.returncode == 0 else f"（rc={p.returncode}：副本缺漏警示，主工作已完成）"
        print(f"\n✅ {label} 完成{note}")
        return True
    print(f"\n❌ {label} 失敗（rc={p.returncode}）")
    return False


def main() -> int:
    if "--dry" in sys.argv:
        print("（--dry：只列步驟，不執行）")
        for label, args, kind, _ in STEPS:
            print(f"   [{kind}] {label:24s} $ python {' '.join(args)}")
        return 0

    failed: list[str] = []
    for label, args, kind, ok_codes in STEPS:
        if not run_step(label, args, kind, ok_codes):
            failed.append(label if kind == "hard" else f"{label}（soft）")
            if kind == "hard":
                print(f"\n⛔ 硬性步驟失敗 → 中止（後續步驟未執行）：{label}")
                break

    print("\n" + "=" * 62)
    if failed:
        print(f"❌ 真值日收尾未完成（{len(failed)} 項）：" + "、".join(failed))
        return 1
    print("✅ 真值日收尾完成（步驟 4 → 4b 寫回 → 4b 燈號 → 更新後提醒）")
    print("   下一步：python check_thresholds.py --sot-only 應回綠（Coast FI freshness 閘門）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
