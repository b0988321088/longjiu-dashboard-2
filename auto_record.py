#!/usr/bin/env python
"""auto_record.py — 自動化推送路徑的「落紀錄」helper（P2，2026-09-14）

用途：資料/報表類自動化路徑（nightly_dashboard_sync / evening_sync / radar_push /
      radar_weekly / investment_perf_monthly / update_and_deploy / refresh_all /
      complete_operation / cio_review_ingest / schedule_events_weekly_clean / pre-run.sh）
      在 commit 之後、push 之前呼叫，把「這個 commit 的 tree」寫進 RECORD 通道，
      取代舊的 `[cioreviewed]` 自打標籤（那條只證明作者自己說審過了）。

用法：
  python auto_record.py --script evening_sync.py [--commit <sha>] [--check "cmd"]... [--dry-run]
  python auto_record.py --clean-stage      # git add -A 型路徑：commit 前把程式檔 unstage

內建 deterministic 檢查（任一失敗 → 不落地、exit 3 → push 被閘門擋下＝寧可斷、不要無審上線）：
  ① 變更清單不得含程式檔（.py/.sh/.bat/.ps1/.cmd/.toml/.yml/.yaml/.js/.ts/.sql、
     .githooks/*、.gitattributes、.gitignore、index_template.html）
     → 程式/邏輯改動只能走真 CIO 審查，不得由自動化腳本自己落紀錄
  ② 變更的 *.json 必須能 json.loads（防截斷/半寫入的資料上線）
  ③ 變更的 *.html 必須非空且有 </html>（同上）
  ④ 工作區相對 HEAD 不得有「已追蹤檔」的未提交變更（紀錄要對得上要推的內容）
  ⑤ --check 指定的額外檢查（可重複；exit != 0 視為失敗）

界線（不要誤用）：reviewer 記為 AUTO-checker:<script>，只證明「上述結構檢查通過」，
      **不證明設計正確**。程式/邏輯改動走這條會被閘門硬擋（pre-push v4.2：AUTO 紀錄
      不得涵蓋含程式檔的 commit）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

CODE_RE = re.compile(
    r"\.(py|sh|bat|ps1|cmd|toml|yml|yaml|js|ts|sql)$"
    r"|^\.githooks/"
    r"|^\.gitattributes$"
    r"|^\.gitignore$"
    r"|^index_template\.html$",
    re.I,
)


def run(args: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def base_dir() -> Path:
    p = run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if p.returncode != 0:
        print("❌ 不在 git repo 內（auto_record 必須在龍九 repo 執行）", file=sys.stderr)
        sys.exit(4)
    return Path(p.stdout.strip())


def changed_files(base: Path, commit: str) -> list[tuple[str, str]]:
    """[(status, path)]；同時涵蓋改名/複製的舊路徑（-M）。"""
    p = run(["git", "diff-tree", "--no-commit-id", "--name-status", "-M", "-r", commit], base)
    if p.returncode != 0:
        print(f"❌ 讀變更清單失敗：{p.stderr.strip()}", file=sys.stderr)
        sys.exit(4)
    out: list[tuple[str, str]] = []
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            st = parts[0]
            for path in parts[1:]:
                if path:
                    out.append((st, path))
    return out


def clean_stage(base: Path) -> int:
    """staging 去程式檔（給 `git add -A` 型路徑在 commit 前呼叫）。

    理由（2026-09-14）：`git add -A` 會把工作區「所有」變更掃進本 job 的 commit（包含
    別人留下的未提交程式改動）→ auto_record 判定「含程式檔」→ 不落紀錄 → 該班次斷推
    （22:00 晚報是第一線受害者）。這裡只排除程式檔、保留資料/報表，並把排除清單印出來。
    """
    raw = run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"], base).stdout
    staged = [x for x in raw.split("\0") if x.strip()]
    code = [f for f in staged if CODE_RE.search(f)]
    if not code:
        return 0
    p = run(["git", "restore", "--staged", "--"] + code, base)
    if p.returncode != 0:
        print(f"❌ clean-stage 失敗（無法 unstage 程式檔）：{p.stderr.strip()[:160]}", file=sys.stderr)
        return 4
    print(f"⚠️ clean-stage：已排除 {len(code)} 個程式檔（不進本 job 的 commit）→ {', '.join(code[:6])}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="unknown", help="呼叫端腳本名（寫進 reviewer：AUTO-checker:<script>）")
    ap.add_argument("--commit", default="HEAD", help="要落紀錄的 commit（預設 HEAD）")
    ap.add_argument("--check", action="append", default=[], help="額外 deterministic 檢查指令（可重複）")
    ap.add_argument("--note", default="", help="附加備註")
    ap.add_argument("--dry-run", action="store_true", help="只印出將寫入的內容，不動任何檔")
    ap.add_argument("--clean-stage", action="store_true",
                    help="只做 staging 去程式檔（git add -A 型路徑在 commit 前呼叫），不落紀錄")
    a = ap.parse_args()

    base = base_dir()
    if a.clean_stage:
        return clean_stage(base)
    sha = run(["git", "rev-parse", f"{a.commit}^{{commit}}"], base)
    if sha.returncode != 0:
        print(f"❌ 找不到 commit {a.commit}", file=sys.stderr)
        return 4
    commit = sha.stdout.strip()
    tree = run(["git", "rev-parse", f"{commit}^{{tree}}"], base).stdout.strip()

    files = changed_files(base, commit)
    problems: list[str] = []

    # ① 不得含程式檔
    code = sorted({p for _st, p in files if CODE_RE.search(p)})
    if code:
        problems.append(f"含程式檔（程式改動必須走真 CIO 審查）：{', '.join(code[:5])}")
    if not files:
        problems.append("變更清單為空（沒有東西要落紀錄）")

    # ②③ 資料檔結構
    for st, path in files:
        if st.startswith("D"):
            continue
        fp = base / path
        if not fp.exists():
            problems.append(f"{path} 不存在於工作區")
            continue
        if path.lower().endswith(".json"):
            try:
                json.loads(fp.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                problems.append(f"{path} 不是合法 JSON：{str(e)[:60]}")
        elif path.lower().endswith(".html"):
            try:
                txt = fp.read_text(encoding="utf-8", errors="replace")
            except Exception as e:  # noqa: BLE001
                problems.append(f"{path} 無法讀取：{str(e)[:60]}")
                continue
            if len(txt) < 200 or "</html>" not in txt.lower():
                problems.append(f"{path} 疑似截斷（{len(txt)} bytes、無 </html>）")

    # ④ 工作區乾淨（只看已追蹤檔）
    st = run(["git", "status", "--porcelain", "--untracked-files=no"], base).stdout.strip()
    if st:
        problems.append(f"工作區有未提交的已追蹤變更：{st.splitlines()[0][:60]}")

    # ⑤ 額外檢查
    for cmd in a.check:
        p = subprocess.run(cmd, cwd=base, shell=True, capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            problems.append(f"檢查失敗（{cmd}）：{(p.stdout + p.stderr).strip()[-160:]}")

    summary = (
        f"auto_record {a.script} | {len(files)} 檔 | builtin(code/json/html/clean)"
        f"{f' +{len(a.check)} extra' if a.check else ''} | {dt.datetime.now():%H:%M}"
    )
    if a.note:
        summary += f" | {a.note}"

    if problems:
        print("❌ auto_record 檢查未通過 → 不落紀錄（push 會被閘門擋下）", file=sys.stderr)
        for p_ in problems:
            print(f"   - {p_}", file=sys.stderr)
        return 3

    if a.dry_run:
        print("（dry-run 不動任何檔）將寫入：")
        print(f"  commit   = {commit}")
        print(f"  tree     = {tree}")
        print(f"  reviewer = AUTO-checker:{a.script}")
        print(f"  note     = {summary[:120]}")
        return 0

    r = run(
        [
            sys.executable,
            str(base / "cio_approve.py"),
            "--verdict", "APPROVE",
            "--reviewer", f"AUTO-checker:{a.script}",
            "--note", summary,
            "--commit", commit,
        ],
        base,
    )
    sys.stdout.write(r.stdout)
    sys.stderr.write(r.stderr)
    if r.returncode != 0:
        print(f"⚠️ 落紀錄失敗（rc={r.returncode}）→ push 會被閘門擋下", file=sys.stderr)
        return r.returncode
    print(f"✅ 已落 RECORD：{a.script} → commit {commit[:12]} tree {tree[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
