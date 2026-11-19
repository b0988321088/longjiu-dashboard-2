#!/usr/bin/env python3
"""hold_impact_preview.py — 上 PUSH_HOLD 前的影響預演（唯讀，不改任何狀態）。

## 為什麼需要這支

2026-11-19 事故（二次傷害）：
  21:57 為止血「未授權推送」建立 .git/PUSH_HOLD
  → .githooks/pre-commit 依 2026-10-31 設計「HOLD 一律拒絕 commit」
  → 22:38 data_closeout_commit 無法收尾 → 當日 6 檔產物堆在工作區
  → 22:40 收工檢查 ② 閉環稽核 ❌、⑤ 遠端同步 ❌ → cron 連 3 次失敗

上鎖本身是對的。錯的是「上鎖前不知道它會連帶擋掉什麼」，於是止血變成新的故障源。

## 用法

    python tools/hold_impact_preview.py            # 預演「如果現在上 HOLD」
    python tools/hold_impact_preview.py --active   # 檢查「目前已上的 HOLD 是否語意正確」

退出碼：0 = 無矛盾；2 = 發現會導致二次故障的配置矛盾。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HOLD = BASE / ".git" / "PUSH_HOLD"

# 會在排程中自行 git commit 的腳本（grep 得來，新增自動提交流程時請同步維護）
COMMITTERS = [
    ("data_closeout_commit.py", "22:38", "當日資料／報表收尾"),
    ("evening_sync.py", "22:00", "晚間產物落版"),
    ("auto_push.py", "多支呼叫", "commit→審查→推送出口（受 --dry-run 保護）"),
    ("morning_deploy.py", "07:00", "晨報（經 regenerate_report.py）"),
]


def _read(rel: str) -> str:
    p = BASE / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def check_precommit_blocks_commit() -> tuple[bool, str]:
    """pre-commit 在 HOLD 生效時是否『一律拒絕 commit』（= 二次故障的首要成因）。"""
    src = _read(".githooks/pre-commit")
    if not src:
        return False, ".githooks/pre-commit 不存在（無 commit 層閘門）"
    # 找 PUSH_HOLD 判斷區塊
    m = re.search(r'PUSH_HOLD.*?(?=\nfi\b)', src, re.S)
    if not m:
        return False, "pre-commit 未檢查 PUSH_HOLD"
    block = m.group(0)
    if re.search(r"^\s*exit\s+1\s*$", block, re.M):
        return True, "pre-commit 在 HOLD 生效時 exit 1 → 所有自動產線無法入庫"
    return False, "pre-commit 在 HOLD 生效時僅警告、允許 commit（語意正確）"


def check_closeout_aware() -> tuple[bool, str]:
    """closeout_check ⑤ 是否認得 HOLD（否則『刻意未推』被當成漏推失敗）。"""
    src = _read("closeout_check.py")
    if not src:
        return False, "closeout_check.py 不存在"
    if "PUSH_HOLD" in src and "_hold" in src:
        return True, "⑤ 認得 PUSH_HOLD，HOLD 期間未推列為預期（仍可見）"
    return False, "⑤ 不認得 PUSH_HOLD → HOLD 期間每次收工檢查都會判未推失敗"


def check_pages_workflow_name() -> tuple[bool, str]:
    """⑨ 的 workflow 名稱是否涵蓋實際部署 workflow（配置漂移偵測）。"""
    src = _read("closeout_check.py")
    wf = _read(".github/workflows/pages.yml")
    if not src or not wf:
        return False, "缺少 closeout_check.py 或 .github/workflows/pages.yml"
    m = re.search(r"^name:\s*(.+)$", wf, re.M)
    actual = (m.group(1).strip().strip('"\'') if m else "")
    if not actual:
        return False, "pages.yml 讀不到 name"
    known = re.findall(r'"([^"]+)"', src[src.find("PAGES_WORKFLOWS"):src.find("PAGES_WORKFLOWS") + 400]) \
        if "PAGES_WORKFLOWS" in src else re.findall(r'PAGES_WORKFLOW\s*=\s*"([^"]+)"', src)
    if actual in known:
        return True, f"⑨ 認得實際 workflow『{actual}』"
    return False, f"⑨ 不認得實際 workflow『{actual}』（已知：{known}）→ 每次推送誤報未觸發"


def unpushed_count() -> int:
    try:
        r = subprocess.run(["git", "rev-list", "--count", "origin/clean-main..HEAD"],
                           cwd=BASE, capture_output=True, text=True, timeout=30)
        return int((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return -1


def main(argv: list[str]) -> int:
    active = "--active" in argv
    mode = "目前 HOLD 語意自檢" if active else "上 HOLD 影響預演"

    print(f"=== PUSH_HOLD {mode}（{'HOLD 已生效' if HOLD.exists() else 'HOLD 未生效'}）===\n")

    problems: list[str] = []

    blocks, msg1 = check_precommit_blocks_commit()
    print(f"{'❌' if blocks else '✅'} commit 層：{msg1}")
    if blocks:
        problems.append("pre-commit 凍結 commit → 自動產線無法入庫，22:40 閉環稽核必失敗")

    ok2, msg2 = check_closeout_aware()
    print(f"{'✅' if ok2 else '❌'} 收工 ⑤：{msg2}")
    if not ok2:
        problems.append("closeout ⑤ 不認 HOLD → 每次收工檢查判未推失敗")

    ok3, msg3 = check_pages_workflow_name()
    print(f"{'✅' if ok3 else '❌'} 收工 ⑨：{msg3}")
    if not ok3:
        problems.append("closeout ⑨ workflow 名稱漂移 → 每次推送誤報 Pages 未部署")

    n = unpushed_count()
    print(f"{'ℹ️' if n <= 0 else '⏸️'} 待推：{n if n >= 0 else '讀取失敗'} 顆"
          f"{'（HOLD 期間為預期）' if n > 0 else ''}")

    print("\n--- 上 HOLD 後會被擋住的提交路徑 ---")
    for script, when, desc in COMMITTERS:
        exists = (BASE / script).exists()
        print(f"  {'·' if exists else '（缺）'} {when:<8} {script:<26} {desc}")

    print("\n--- 發布端防護（HOLD 期間仍有效）---")
    print("  ① pre-push：HOLD 生效 → 需 release_auth 一次性授權（驗範圍／期限／次數）")
    print("  ② auto_push.py：未推佇列含非本輪 commit → rc=3 拒推")
    print("  ③ data_closeout_commit.py：同上斷言")
    print("  殘餘風險：git push --no-verify 可繞過 pre-push（既有風險，非 HOLD 新增）")

    if problems:
        print("\n=== ❌ 發現會導致二次故障的配置矛盾 ===")
        for p in problems:
            print(f"  - {p}")
        print("\n修法：commit 層只警告不阻擋；檢查器認得 HOLD 與實際 workflow 名稱。")
        return 2

    print("\n=== ✅ 無矛盾：HOLD 只凍結發布，不凍結入庫與稽核 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
