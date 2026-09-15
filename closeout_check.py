#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""closeout_check.py — 龍九每日收工檢查（一鍵；stdlib only）

把收工要跑的檢查串成一支：原本要手動跑 6 支，現在一支跑完出報告。

步驟
----
1. **排程時點認領偵測**（INC-172）：找出「手動 fire 預先完成未來排程時點」的執行列
   → 這些會讓該次正式排程靜默消失（詳見 release_claimed_occurrences.py 檔頭）。
2. **閉環稽核**：`_audit_closeout.py`（舊值殘留／四源一致／GitHub Pages／git／鏡像／cron／監控檔／認領）。
3. **彙總**：印出結論 + 「需補跑的產出」清單（每筆給可直接複製的指令）。
4. **推送通道稽核**（v4 閘門配套）：`.git/PUSH_LANE.log` 近 24h 各通道使用次數；
   有「例外通道推程式檔」或「自動化以 TAG 推程式被擋」→ 列入問題（前者要補審、後者要遷移該路徑）。
5. **auto_record 警告稽核**（INC-180 配套）：`.git/AUTO_WARN.log` 近 24h 的 `data-dirty`／
   `code-dirty`／`range-missing`。前兩類是「別班或有人的未提交變更」（只記錄），
   `range-missing`（推送範圍內有 commit 無審查紀錄 → 那次 push 必定被閘門擋下）列入問題。

用法
----
    python closeout_check.py            # 檢查（不動任何東西）
    python closeout_check.py --fix      # 順便釋放被誤認領的時點（先備份 executions.db）
    python closeout_check.py --quiet    # 全綠時只印一行摘要
    python closeout_check.py --silent-ok  # 全綠完全不輸出（cron watchdog 用；有問題才吐整份報告）

exit code：0 = 全部通過；1 = 有問題（或仍有未釋放的認領）。
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
LANE_LOG = REPO / ".git" / "PUSH_LANE.log"   # pre-push 閘門的逐筆通道留痕（v3 起）
WARN_LOG = REPO / ".git" / "AUTO_WARN.log"   # auto_record 的警告留痕（INC-180 起）
sys.path.insert(0, str(REPO))
import release_claimed_occurrences as rco  # noqa: E402
import auto_push as apush  # noqa: E402  （複核 range-missing 是否已補紀錄）


def step_claims(fix: bool, quiet: bool) -> int:
    """回傳『未解決的認領數』。"""
    db = rco.default_db()
    jobs = rco.load_jobs()
    claims = rco.find_claims(db)
    if not claims:
        if not quiet:
            print("① 排程時點認領：✅ 乾淨（沒有被預先完成的未來時點）")
        return 0
    print(f"① 排程時點認領：❌ {len(claims)} 筆未來時點已被手動執行預先完成 → 該次排程會靜默消失")
    for c in claims:
        j = jobs.get(c["job_id"], {})
        print(f"   🔴 {c['job_id'][:12]} {(j.get('name') or '')[:26]}｜認領 {c['scheduled_instant']}")
        print(f"        補跑：{rco.rerun_hint(c['job_id'], jobs)}")
    if fix:
        bak = rco.release(db, claims)
        left = rco.find_claims(db)
        print(f"   🔧 已釋放 {len(claims)} 筆（備份 {bak.name}）→ 殘留 {len(left)} 筆")
        return len(left)
    print("   （未釋放。加 --fix 一鍵釋放後再補跑上面指令）")
    return len(claims)


def step_audit(quiet: bool) -> tuple:
    """回傳 (exit_code, 結論行, 完整輸出)。"""
    p = subprocess.run([sys.executable, str(REPO / "_audit_closeout.py")],
                       capture_output=True, text=True, cwd=str(REPO))
    out = (p.stdout or "") + (p.stderr or "")
    concl = next((l.strip() for l in out.splitlines() if l.startswith("閉環稽核結果")), "（無結論行）")
    if not quiet:
        print("\n② 閉環稽核輸出：\n" + out.rstrip())
    else:
        print(f"② 閉環稽核：{concl}")
    return p.returncode, concl, out


def step_push_lanes(quiet: bool) -> list:
    """③ 推送通道稽核（v4 閘門配套）：看 .git/PUSH_LANE.log 近 24h 各通道使用次數。

    通道：RECORD（CIO 審查紀錄）／TAG（[cioreviewed] 純資料）／SKIPREVIEW／DELETE。
    問題條件（回傳問題清單）：
      - SKIPREVIEW-CODE：走例外通道且含程式檔（未經真審就上線）→ 必須回頭補審
      - TAG-BLOCKED-CODE：自動化想用 TAG 推程式被擋下 → 該路徑需遷移到 RECORD（會靜默斷推，要提早處理）
    """
    problems: list = []
    if not LANE_LOG.exists():
        if not quiet:
            print("③ 推送通道：⚪ 尚無 PUSH_LANE.log（閘門 v3 起才寫）")
        return problems
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    counts: dict = {}
    flagged: list = []
    for ln in LANE_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = ln.split("\t")
        if len(parts) < 4:
            continue
        try:
            ts = dt.datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if ts < cut:
            continue
        lane = parts[1]
        counts[lane] = counts.get(lane, 0) + 1
        if lane in ("SKIPREVIEW-CODE", "TAG-BLOCKED-CODE"):
            flagged.append(f"{lane} {parts[2][:12]}")
    if not quiet:
        used = "、".join(f"{k}×{v}" for k, v in sorted(counts.items())) or "無推送"
        print(f"③ 推送通道（近 24h）：{used}")
    for f in flagged:
        if f.startswith("SKIPREVIEW-CODE"):
            problems.append(f"程式檔走例外通道（未經真審）：{f}")
        else:
            problems.append(f"自動化以 TAG 推程式被擋（該路徑需改走 RECORD）：{f}")
    return problems


def step_auto_warns(quiet: bool) -> list:
    """④ auto_record 警告稽核（近 24h）：`.git/AUTO_WARN.log`。

    INC-180：警告若只印在 cron 的 stdout 等於沒人看到 → 收進每日收工稽核。
    kind：data-dirty（他班未提交資料檔）／code-dirty（工作區有人留著未提交程式檔）／
          range-missing（推送範圍內有 commit 無審查紀錄 → 該次 push 必定被閘門擋下）。
    只有 range-missing 列入問題（data/code-dirty 是常態，記錄供追蹤）。
    """
    problems: list = []
    if not WARN_LOG.exists():
        if not quiet:
            print("④ auto_record 警告：⚪ 尚無 AUTO_WARN.log（INC-180 起才寫）")
        return problems
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    counts: dict = {}
    last: dict = {}
    missed: list = []
    resolved: list = []
    for ln in WARN_LOG.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = ln.split("\t")
        if len(parts) < 5:
            continue
        try:
            ts = dt.datetime.strptime(parts[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if ts < cut:
            continue
        kind = parts[3]
        counts[kind] = counts.get(kind, 0) + 1
        last[kind] = f"{parts[1]} {parts[2]}｜{parts[4][:70]}"
        if kind == "range-missing":
            # 逐顆複核：被點名的 commit 若之後已補上審查紀錄 → 視為已解決，不列問題
            # （否則一筆「當下落後、稍後補齊」的正常過程會在稽核裡掛 24 小時）
            shas = re.findall(r"\b[0-9a-f]{7,40}\b", parts[4])
            unresolved = [s for s in shas if not apush.tree_approved(REPO, s)]
            if unresolved:
                missed.append(f"{parts[1]} {parts[2]}｜{parts[4][:70]}")
            else:
                resolved.append(f"{parts[1]} {parts[2]}")
    if not quiet:
        used = "、".join(f"{k}×{v}" for k, v in sorted(counts.items())) or "無警告"
        print(f"④ auto_record 警告（近 24h）：{used}")
        for k in sorted(last):
            print(f"   - {k} 最後：{last[k]}")
        if resolved:
            print(f"   （range-missing 已補紀錄、不列問題：{len(resolved)} 筆）")
        if not missed and (counts or resolved):
            print("   ℹ️ 以上皆為他班／歷史 range 的未提交檔或已補紀錄案件 → 非本次問題（真問題只有 range-missing 未補）")
    for x in missed:
        problems.append(f"推送範圍有 commit 無審查紀錄（該次 push 會被擋）：{x}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="龍九每日收工檢查（一鍵）")
    ap.add_argument("--fix", action="store_true", help="釋放被誤認領的排程時點")
    ap.add_argument("--quiet", action="store_true", help="全綠時只印摘要")
    ap.add_argument("--silent-ok", action="store_true",
                    help="全綠時完全不輸出（cron watchdog 用：只有出問題才吐報告）")
    args = ap.parse_args()

    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    buf = io.StringIO()
    sink = contextlib.redirect_stdout(buf) if args.silent_ok else contextlib.nullcontext()
    with sink:
        if not (args.quiet or args.silent_ok):
            print("=" * 52)
            print(f"龍九收工檢查　{stamp}")
            print("=" * 52)

        left_claims = step_claims(args.fix, args.quiet or args.silent_ok)
        rc, concl, out = step_audit(args.quiet or args.silent_ok)
        lane_problems = step_push_lanes(args.quiet or args.silent_ok)
        warn_problems = step_auto_warns(args.quiet or args.silent_ok)

        problems = []
        if left_claims:
            problems.append(f"未釋放的排程認領 {left_claims} 筆")
        if "全部通過" not in concl:
            problems.append(concl.replace("閉環稽核結果：", ""))
        problems.extend(lane_problems)
        problems.extend(warn_problems)

        print()
        print("=" * 52)
        if not problems:
            print(f"收工檢查：全部通過 ✅　（{stamp}）")
        else:
            print("收工檢查：❌ 有問題")
            for x in problems:
                print(f"  - {x}")
        print("=" * 52)

    if args.silent_ok:
        if not problems:
            return 0                      # 全綠 → 靜默（cron 不推送）
        print(buf.getvalue().rstrip())    # 有問題 → 完整報告整份吐出
        return 1
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
