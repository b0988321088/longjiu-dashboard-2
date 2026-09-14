#!/usr/bin/env python
"""auto_record.py — 自動化推送路徑的「落紀錄」helper（P2，2026-09-14）

用途：資料/報表類自動化路徑（nightly_dashboard_sync / evening_sync / radar_push /
      radar_weekly / investment_perf_monthly / update_and_deploy / refresh_all /
      complete_operation / cio_review_ingest / schedule_events_weekly_clean / pre-run.sh）
      在 commit 之後、push 之前呼叫，把「這個 commit 的 tree」寫進 RECORD 通道，
      取代舊的 `[cioreviewed]` 自打標籤（那條只證明作者自己說審過了）。

用法：
  python auto_record.py --script evening_sync.py [--commit <sha>] [--check "cmd"]... [--dry-run]
  python auto_record.py --script radar_push.py --own radar_state.json "radar_report_*.html"
  python auto_record.py --clean-stage      # git add -A 型路徑：commit 前把程式檔 unstage

內建 deterministic 檢查（任一失敗 → 不落地、exit 3 → push 被閘門擋下＝寧可斷、不要無審上線）：
  ① 變更清單不得含程式檔（.py/.sh/.bat/.ps1/.cmd/.toml/.yml/.yaml/.js/.ts/.sql、
     .githooks/*、.gitattributes、.gitignore、index_template.html）
     → 程式/邏輯改動只能走真 CIO 審查，不得由自動化腳本自己落紀錄
  ② 變更的 *.json 必須能 json.loads（防截斷/半寫入的資料上線）
  ③ 變更的 *.html 必須非空且有 </html>（同上）
  ④ 工作區相對 HEAD 的未提交檔只記警告、**不阻擋**（見下方「守門維度」）
  ④-1 --own 指名的本 job 產出若未提交 → 硬擋（防「產出沒進 commit 卻落了紀錄」的靜默落後）
  ⑤ --check 指定的額外檢查（可重複；exit != 0 視為失敗）

守門維度（INC-179 → INC-180）：紀錄綁的是**該 commit 的 tree**，所以守門只該看「本次推送範圍」。
  工作區有別班次未提交的檔（整點 cron、別條路徑正在改的 .py）是常態，不影響推送內容的正確性；
  舊版把「整個工作區必須乾淨」當條件，讓 --clean-stage 的 7 條路徑（它們刻意把別班程式檔留在
  工作區）在有人手上握一顆未提交 .py 時必定斷推。程式改動的防線改由 ① ＋ pre-push 的
  AUTO-BLOCKED-CODE 承擔。警告一律寫進 `<git-dir>/AUTO_WARN.log`，由每日收工稽核（closeout_check）
  讀取，避免「只警告 = 沒人看到」。

界線（不要誤用）：reviewer 記為 AUTO-checker:<script>，只證明「上述結構檢查通過」，
      **不證明設計正確**。程式/邏輯改動走這條會被閘門硬擋（pre-push v4.2：AUTO 紀錄
      不得涵蓋含程式檔的 commit）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
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


def git_dir(base: Path) -> Path:
    p = run(["git", "rev-parse", "--git-dir"], base)
    gd = Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else Path(".git")
    return gd if gd.is_absolute() else (base / gd)


def tree_approved(base: Path, commit: str) -> bool:
    """該 commit 的 tree 在 CIO_APPROVED 是否已有 APPROVE 紀錄（＝閘門會不會放行）。"""
    f = git_dir(base) / "CIO_APPROVED"
    if not f.exists():
        return False
    p = run(["git", "rev-parse", f"{commit}^{{tree}}"], base)
    if p.returncode != 0:
        return False
    t = p.stdout.strip()
    for ln in f.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split("\t")
        if len(parts) >= 5 and parts[1] == t and parts[3] == "APPROVE":
            return True
    return False


def log_warn(base: Path, commit: str, script: str, kind: str, detail: str) -> None:
    """警告寫進 <git-dir>/AUTO_WARN.log（append-only）→ 每日收工稽核（closeout_check）讀取。
    「只印在 stdout 的警告＝沒人看到」，cron 的 stdout 沒人翻。"""
    try:
        with open(git_dir(base) / "AUTO_WARN.log", "a", encoding="utf-8") as fh:
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            fh.write(f"{ts}\t{commit[:12]}\t{script}\t{kind}\t{detail}\n")
    except Exception:  # noqa: BLE001 — 警告寫不進去不該擋掉正常紀錄
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="unknown", help="呼叫端腳本名（寫進 reviewer：AUTO-checker:<script>）")
    ap.add_argument("--commit", default="HEAD", help="要落紀錄的 commit（預設 HEAD）")
    ap.add_argument("--check", action="append", default=[], help="額外 deterministic 檢查指令（可重複）")
    ap.add_argument("--note", default="", help="附加備註")
    ap.add_argument("--own", nargs="+", default=[], metavar="GLOB",
                    help="本 job 的產出檔（glob，可多個）：這些檔若未提交 → 硬擋（防產出沒進 commit 卻落了紀錄）")
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

    # ④ 工作區（只看已追蹤檔）：只警告、不阻擋 —— 守門維度是「本次推送的 commit tree」，不是工作區。
    #    2026-09-14 INC-180（INC-179 的檢討）：舊版要求「工作區乾淨」，但 --clean-stage 的 7 條路徑
    #    （evening_sync／refresh_all／update_and_deploy／complete_operation／investment_perf_monthly／
    #    radar_weekly／pre-run.sh）本來就會把別班未提交的程式檔留在工作區 → 只要有人手上握一顆未提交的
    #    .py，這些路徑就必定斷推（clone 實測 22:00 晚報情境 rc=3）。程式改動的防線不靠這裡：
    #    ①（commit 內含程式檔即擋）＋ pre-push AUTO-BLOCKED-CODE。
    #    真正該擋的背書風險是「本 job 自己的產出沒進這個 commit」→ 用 --own 指名（見 ④-1）。
    warnings: list[tuple[str, str]] = []
    dirty_lines = [
        ln for ln in run(["git", "status", "--porcelain", "--untracked-files=no"], base).stdout.splitlines() if ln.strip()
    ]
    dirty_paths: list[str] = []
    for ln in dirty_lines:
        for p in ln[3:].strip().split(" -> "):  # 改名/複製同時看舊、新路徑
            p = p.strip().strip('"')
            if p:
                dirty_paths.append(p)
    dirty_code = sorted({p for p in dirty_paths if CODE_RE.search(p)})
    dirty_data = sorted({p for p in dirty_paths if not CODE_RE.search(p)})
    if dirty_code:
        warnings.append((
            "code-dirty",
            f"工作區有未提交的程式檔 {len(dirty_code)} 個（不會進本次推送）：{', '.join(dirty_code[:3])}",
        ))
    if dirty_data:
        warnings.append((
            "data-dirty",
            f"他班未提交資料檔 {len(dirty_data)} 個、不在本次推送範圍：{', '.join(dirty_data[:3])}",
        ))

    # ④-1 本 job 產出守門（--own <glob>）：產出沒進 commit 就落紀錄＝「紀錄說推了、內容還是舊的」
    if a.own and dirty_paths:
        own_dirty = sorted({
            p for p in dirty_paths
            if any(fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(os.path.basename(p), pat) for pat in a.own)
        })
        if own_dirty:
            problems.append(
                f"本 job 產出未提交（--own）：{', '.join(own_dirty[:3])} → 產出沒進 commit 就落紀錄＝靜默落後"
            )

    # ⑤ 額外檢查
    for cmd in a.check:
        p = subprocess.run(cmd, cwd=base, shell=True, capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            problems.append(f"檢查失敗（{cmd}）：{(p.stdout + p.stderr).strip()[-160:]}")

    summary = (
        f"auto_record {a.script} | {len(files)} 檔 | builtin(code/json/html/worktree)"
        f"{f' +{len(a.check)} extra' if a.check else ''} | {dt.datetime.now():%H:%M}"
    )
    # 警告放 note 前面：cio_approve.clean() 會把 note 截到 120 字，長 --note 會把警告吃掉
    if warnings:
        summary += " | ⚠️ " + "；".join(msg for _kind, msg in warnings)
    if a.note:
        summary += f" | {a.note}"

    if warnings:
        print("⚠️ auto_record 警告（不阻擋，僅留痕 → .git/AUTO_WARN.log）：")
        for kind, msg in warnings:
            print(f"   - [{kind}] {msg}")
            if not a.dry_run:      # dry-run 是探測，不該污染稽核日誌
                log_warn(base, commit, a.script, kind, msg)

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

    # ⑥ 推送範圍自檢（診斷，不阻擋）：origin/<branch>..HEAD 內若有 commit 沒被審查紀錄涵蓋，
    #    閘門必定擋下（常見成因：落紀錄與 push 之間又插進別的 commit）→ 先講清楚是哪幾顆，
    #    省掉「push 失敗只看到一句 refs 錯誤」的困惑。
    try:
        br = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], base).stdout.strip()
        rr = run(["git", "rev-list", f"origin/{br}..HEAD"], base) if br and br != "HEAD" else None
        if rr is not None and rr.returncode == 0:
            miss = [c for c in rr.stdout.split() if not tree_approved(base, c)]
            if miss:
                short = ", ".join(c[:12] for c in miss[:4])
                print(f"⚠️ 推送範圍內另有 {len(miss)} 顆 commit 無審查紀錄（閘門會擋）：{short}", file=sys.stderr)
                log_warn(base, commit, a.script, "range-missing", f"{len(miss)} 顆無紀錄：{short}")
    except Exception as e:  # noqa: BLE001 — 自檢失敗不影響已落地的紀錄
        print(f"（推送範圍自檢略過：{str(e)[:80]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
