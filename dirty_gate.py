# -*- coding: utf-8 -*-
"""dirty_gate.py — production auto-commit 的「dirty worktree fail-closed」閘門

裁決 2026-10-06（使用者）：production pipeline 在 commit 前，若偵測到
「非本輪宣告範圍」的既有 dirty 檔 → 直接停止，不 auto-commit。

嚴格禁止（本閘門不做，呼叫端也不得代做）：
  自動 stash／自動 reset／自動刪除／自動 commit／自行決定哪些檔案屬於本輪。
本閘門只做一件事：看見不乾淨 → 停止 → 列清單 → 人工處理。

設計要點
  1. declared = 本輪「唯一授權提交」的 pathspec（精確檔名或 glob）。
  2. KNOWN_RUNTIME = 常態性 runtime 產物（每次執行都會動、且不由本輪宣告提交）。
     ⚠️ 治理原則（使用者 2026-10-06 核可）：KNOWN_RUNTIME 是 **allowlist**，
        不是「所有非宣告檔案都可以放行」的通配退路。
        不變量必須永遠維持：dirty − declared − KNOWN_RUNTIME ≠ ∅ → rc=9
        新增髒檔案「不得」自動歸類成 runtime；要擴充本清單必須人工核可並留下理由。
  3. 判定 = dirty_now − declared − KNOWN_RUNTIME；非空 → SystemExit(9)。
  4. 一律 fail-closed：本身故障（git 讀不到）也視為 FAIL，不得放行。
  5. 呼叫端「不得」吞掉本閘門的 SystemExit(9) 後繼續 commit/push（CIO 驗收項）。

用法
    from dirty_gate import assert_clean_scope
    assert_clean_scope(_push_files, base=BASE, label=f"regenerate_report({TODAY})")
CLI（唯讀盤點）
    python dirty_gate.py --declared index.html snapshot.json
"""
from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

EXIT_DIRTY = 9

# 常態 runtime 產物：每次執行必然變動、且不是任何一輪「宣告提交」的對象。
# 2026-10-06 建立時，觀測 baseline 為：
#   dashboard_decisions.json / data/ai_cost_daily.jsonl / hunter_cache/*.json /
#   logs/pipeline_llm_usage.jsonl / notion_bridge/*.md
# ⚠️ 待使用者核可後才視為定版；未核可前只影響「不擋」的範圍，不影響 fail-closed 主體。
KNOWN_RUNTIME = (
    "logs/*",
    "data/ai_cost_daily.jsonl",
    "hunter_cache/*",
    "notion_bridge/*",
    "cost_log.csv",
    "*.log",
)


def _base(base=None) -> Path:
    return Path(base) if base else Path(__file__).resolve().parent


def dirty_paths(base=None) -> set:
    """git status --porcelain --untracked-files=all → 相對路徑集合（rename 取新名）。"""
    try:
        st = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", cwd=str(_base(base)))
    except Exception as e:
        raise SystemExit(f"[dirty_gate] 無法讀取 git status（視為 FAIL，不放行）：{e}")
    if st.returncode != 0:
        raise SystemExit(f"[dirty_gate] git status rc={st.returncode}（視為 FAIL，不放行）")
    out = set()
    for ln in (st.stdout or "").splitlines():
        if len(ln) < 4 or not ln.strip():
            continue
        p = ln[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ")[-1]
        out.add(p)
    return out


def out_of_scope(declared, dirty, known_runtime=KNOWN_RUNTIME):
    def _keep(p):
        return any(p == d or fnmatch.fnmatch(p, d) for d in declared)
    def _rt(p):
        return any(fnmatch.fnmatch(p, k) for k in known_runtime)
    return sorted(p for p in dirty if not _keep(p) and not _rt(p))


def assert_clean_scope(declared, base=None, label="", hard=True):
    extra = out_of_scope(list(declared), dirty_paths(base))
    if not extra:
        print(f"[dirty_gate] OK  {label}：無宣告範圍外的既有 dirty 檔")
        return []
    print(f"[dirty_gate] STOP {label}：偵測到 {len(extra)} 個『非本輪宣告範圍』的既有 dirty 檔 → 停止，不 auto-commit")
    for p in extra[:40]:
        print(f"    - {p}")
    if len(extra) > 40:
        print(f"    ... 其餘 {len(extra) - 40} 檔")
    print("[dirty_gate] 人工檢視後自行 commit／丟棄／保留（本閘門不代為 stash/reset/commit）")
    if hard:
        raise SystemExit(EXIT_DIRTY)
    return extra


if __name__ == "__main__":
    decl = []
    if "--declared" in sys.argv:
        i = sys.argv.index("--declared")
        decl = sys.argv[i + 1:]
    extra = assert_clean_scope(decl, label="CLI", hard=False)
    print(f"\n宣告範圍={len(decl)} 檔；範圍外 dirty={len(extra)} 檔")
    sys.exit(EXIT_DIRTY if extra else 0)
