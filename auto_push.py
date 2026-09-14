#!/usr/bin/env python
"""auto_push.py — 自動化路徑的「保證推得上去」統一出口（2026-09-14）

為什麼有這支：
  15 條自動化路徑各自手寫「commit → auto_record → git push」三件事，結果出現三種
  「腳本走完但沒送上去」的實例：
    ① 推送範圍裡有「沒落紀錄」的 commit（別條路徑／別人的 commit 夾在中間）→ 閘門擋下，
       但腳本只印一句 ⚠️ 就結束（cron 看起來成功）
    ② push 一次失敗就放棄（SSH/網路抖一下＝當晚沒上線），沒有重試
    ③ 沒有人驗證「遠端真的前進了」——`git push` 回 0 不等於線上是最新的（也可能是
       no-op：其實沒東西可推，或推了舊 ref）
  這支把三件事收成一個出口：**確保範圍內每顆 commit 都有審查紀錄 → 重試推送 → 驗證遠端 sha**。

用法：
  python auto_push.py --script evening_sync.py --auto-stage --commit "auto: 晚報校準 2026-09-14"
  python auto_push.py --script radar_push.py --own radar_state.json "radar_report_*.html"   # 已自行 commit，只補紀錄＋推
  python auto_push.py --script regenerate_report.py --record skip      # 已走真 CIO 審查，不自動落紀錄

參數：
  --script NAME       呼叫端腳本名（寫進 RECORD reviewer，並寫入 AUTO_PUSH.log）
  --auto-stage        先 `git add -A` ＋ `auto_record.py --clean-stage`（add -A 型路徑用）
  --commit MSG        有 staged 變更就 commit（沒有變更則跳過，不算失敗）
  --record {auto,skip}
                      auto（預設）：推送範圍內每顆「沒有紀錄」的 commit 逐顆補落 RECORD；
                                    若其中含程式檔 → 拒絕推送（程式改動必須走真 CIO 審查）
                      skip：完全不動紀錄（呼叫端已自行走 cio_approve 真審查）
  --own GLOB...       轉發給 auto_record：本 job 產出未提交 → 硬擋
  --branch REF        預設 clean-main:main（第一支照推、第二支 --force-with-lease）
  --no-verify         略過遠端 sha 驗證（不建議）
  --dry-run           只印將做什麼，不動任何東西

退出碼（cron 依此判斷有沒有送上去）：
  0 = 已推且遠端 sha 已驗證（或本來就無事可做）
  3 = 範圍內有含程式檔的未落紀錄 commit → 拒絕推送
  4 = push 重試後仍失敗
  5 = push 回 0 但遠端 sha 與 HEAD 不符（線上是舊的）
  6 = 環境問題（不在 repo／remote 讀不到）
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_REFS = ["clean-main", "clean-main:main"]
CODE_RE = r"\.(py|sh|bat|ps1|cmd|toml|yml|yaml|js|ts|sql)$|^\.githooks/|^\.gitattributes$|^\.gitignore$|^index_template\.html$"


def run(args: list[str], cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def base_dir() -> Path:
    p = run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
    if p.returncode != 0:
        print("❌ auto_push：不在 git repo 內", file=sys.stderr)
        sys.exit(6)
    return Path(p.stdout.strip())


def git_dir(base: Path) -> Path:
    p = run(["git", "rev-parse", "--git-dir"], base)
    gd = Path(p.stdout.strip()) if p.returncode == 0 and p.stdout.strip() else Path(".git")
    return gd if gd.is_absolute() else (base / gd)


def tree_approved(base: Path, commit: str) -> bool:
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


def commit_has_code(base: Path, commit: str) -> list[str]:
    p = run(["git", "diff-tree", "--no-commit-id", "--name-status", "-M", "-r", commit], base)
    hits = []
    for line in p.stdout.splitlines():
        for f in line.split("\t")[1:]:
            if f and re.search(CODE_RE, f, re.I):
                hits.append(f)
    return hits


def log(base: Path, line: str) -> None:
    try:
        with open(git_dir(base) / "AUTO_PUSH.log", "a", encoding="utf-8") as fh:
            ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            fh.write(f"{ts}\t{line}\n")
    except Exception:  # noqa: BLE001
        pass


def remote_sha(base: Path, branch: str) -> str | None:
    r = run(["git", "ls-remote", "origin", f"refs/heads/{branch}"], base, timeout=120)
    if r.returncode != 0:
        return None
    out = r.stdout.strip().split()
    return out[0] if out else ""


def push_once(base: Path, refspec: str, lease: bool) -> subprocess.CompletedProcess:
    args = ["git", "push", "origin", refspec] + (["--force-with-lease"] if lease else [])
    return run(args, base, timeout=300)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", default="unknown")
    ap.add_argument("--auto-stage", action="store_true")
    ap.add_argument("--commit", default="")
    ap.add_argument("--record", choices=["auto", "skip"], default="auto")
    ap.add_argument("--own", nargs="+", default=[])
    ap.add_argument("--branch", default="")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    base = base_dir()
    refs = [a.branch] if a.branch else list(DEFAULT_REFS)

    # 1) staging（add -A 型路徑）——程式檔先 unstage，避免掃進本 job 的 commit
    if a.auto_stage:
        if a.dry_run:
            print("[dry-run] 將 git add -A ＋ auto_record --clean-stage")
        else:
            run(["git", "add", "-A"], base)
            cs = run([sys.executable, str(base / "auto_record.py"), "--clean-stage"], base, timeout=180)
            if (cs.stdout or "").strip():
                print(cs.stdout.strip())

    # 2) commit（有 staged 變更才做；委外 commit 的路徑用 --record skip 或自行 commit）
    if a.commit:
        if a.dry_run:
            print(f"[dry-run] 將 commit：{a.commit}")
        else:
            staged = run(["git", "diff", "--cached", "--quiet"], base).returncode != 0
            if not staged:
                print("ℹ️ 無 staged 變更 → 略過 commit（仍會確保既有 commit 推得上去）")
            else:
                c = run(["git", "commit", "-m", a.commit], base, timeout=120)
                print((c.stdout or c.stderr).strip().splitlines()[-1] if (c.stdout or c.stderr) else "")

    head = run(["git", "rev-parse", "HEAD"], base).stdout.strip()
    if not head:
        print("❌ 讀不到 HEAD", file=sys.stderr)
        return 6

    # 3) 推送範圍內的紀錄覆蓋（本支的核心價值）
    primary = refs[0].split(":")[0]
    rng = run(["git", "rev-list", f"origin/{primary}..HEAD"], base)
    if rng.returncode != 0:
        print(f"⚠️ 讀不到 origin/{primary}（尚未 fetch／遠端不存在）→ 跳過範圍檢查，直接嘗試推送")
        pending = []
    else:
        pending = [c for c in rng.stdout.split() if not tree_approved(base, c)]

    if pending and a.record == "auto":
        bad: list[tuple[str, list[str]]] = [(c, commit_has_code(base, c)) for c in pending]
        blockers = [(c, f) for c, f in bad if f]
        if blockers:
            print("❌ 推送範圍內有未落紀錄且含程式檔的 commit → 不推送（程式改動必須走真 CIO 審查）", file=sys.stderr)
            for c, f in blockers:
                print(f"   - {c[:12]}：{', '.join(f[:4])}", file=sys.stderr)
            print("   怎麼修：對該 commit 跑真審查後 `python cio_approve.py --result <審查JSON> --reviewer CIO-Gemini --commit <sha>`", file=sys.stderr)
            print("   注意：clone／全新環境不會帶 .git/CIO_APPROVED（它不在版控裡）→ 在該環境看到「整段範圍都未落紀錄」屬正常；", file=sys.stderr)
            print("        落紀錄請用 cio_approve.py／auto_record.py，不要手改檔案（TAB 分隔格式手改易錯，會被判為無紀錄）。", file=sys.stderr)
            log(base, f"REFUSED\t{a.script}\t{','.join(c[:12] for c, _ in blockers)}")
            return 3
        for c, _ in bad:
            if a.dry_run:
                print(f"[dry-run] 將補落 RECORD：{c[:12]}")
                continue
            ar = run([sys.executable, str(base / "auto_record.py"), "--script", f"{a.script}(range)",
                      "--commit", c], base, timeout=300)
            if ar.returncode != 0:
                print(f"❌ {c[:12]} 補落紀錄失敗 → 不推送：{((ar.stdout or '') + (ar.stderr or ''))[-200:]}",
                      file=sys.stderr)
                log(base, f"RECORD-FAIL\t{a.script}\t{c[:12]}")
                return 3
            print(f"✅ 補落 RECORD：{c[:12]}")

    if a.dry_run:
        print(f"[dry-run] 將推送 {refs}（HEAD {head[:12]}）")
        return 0

    # 3b) --own 守門：即使沒有待補紀錄的 commit，也要確認「本 job 產出」已進 commit
    #     （否則會出現「紀錄說推了、內容其實是舊的」靜默落後）
    if a.own and not pending:
        chk = run([sys.executable, str(base / "auto_record.py"), "--script", f"{a.script}(own)",
                   "--dry-run", "--own", *a.own], base, timeout=300)
        if chk.returncode != 0:
            print(f"❌ 本 job 產出未提交 → 不推送\n   {((chk.stdout or '') + (chk.stderr or '')).strip()[-200:]}",
                  file=sys.stderr)
            log(base, f"OWN-DIRTY\t{a.script}\t{a.own}")
            return 3

    # 4) 推送（每支最多 3 次，2/5/10 秒退避）
    for ref in refs:
        lease = ":" in ref and ref.split(":")[0] != ref.split(":")[1]
        ok, last = False, None
        for attempt in range(3):
            last = push_once(base, ref, lease)
            if last.returncode == 0:
                ok = True
                break
            print(f"⚠️ push {ref} 第 {attempt + 1} 次失敗，重試中…〔{(last.stderr or '').strip().splitlines()[-1][:120] if (last.stderr or '').strip() else ''}〕")
            time.sleep([2, 5, 10][min(attempt, 2)])
        if not ok:
            err = ((last.stderr or "") + (last.stdout or "")).strip()[-300:]
            print(f"❌ push {ref} 重試 3 次仍失敗 → 本次未推送\n   {err}", file=sys.stderr)
            log(base, f"PUSH-FAIL\t{a.script}\t{ref}\t{head[:12]}\t{err[:160].replace(chr(10), ' ')}")
            return 4

    # 5) 驗證遠端真的前進（不是只信 returncode）
    if not a.no_verify:
        problems = []
        for ref in refs:
            branch = ref.split(":")[-1]
            rsha = remote_sha(base, branch)
            if rsha is None:
                problems.append(f"{branch}：讀不到遠端 sha")
            elif rsha != head:
                problems.append(f"{branch}：遠端 {rsha[:12]} ≠ 本機 {head[:12]}")
        if problems:
            msg = "；".join(problems)
            print(f"❌ 推送後驗證不符（線上是舊的）→ {msg}", file=sys.stderr)
            log(base, f"VERIFY-FAIL\t{a.script}\t{msg}")
            return 5
        print(f"✅ 已推送並驗證遠端 sha：{head[:12]}（{'、'.join(r.split(':')[-1] for r in refs)}）")
    else:
        print(f"✅ 已推送（未驗證遠端）：{head[:12]}")

    log(base, f"OK\t{a.script}\t{head[:12]}\t{len(pending)} 顆補紀錄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
