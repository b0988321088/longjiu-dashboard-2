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
   2026-09-15 起：點名的 commit 先用 `sha_state()` 複核 —— 已補審查紀錄／已上遠端／已被改寫成
   孤兒（不在 HEAD 歷史）者列為「已解決 ℹ️」，只有仍在推送範圍內又沒紀錄的才算 ❌。
5. **auto_record 警告稽核**（INC-180 配套）：`.git/AUTO_WARN.log` 近 24h 的 `data-dirty`／
   `code-dirty`／`range-missing`。前兩類是「別班或有人的未提交變更」（只記錄），
   `range-missing`（推送範圍內有 commit 無審查紀錄 → 那次 push 必定被閘門擋下）列入問題，
   但同樣先用 `sha_state()` 複核（被擋後改走 RECORD 重做、舊 commit 變孤兒者不列問題）。

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

# 已解決狀態的說明字串（v4.2 收工稽核：只有 pending 才算問題）
SETTLED_REASON = {
    "approved": "該 commit 之後已取得審查紀錄",
    "remote": "已在 origin/<branch>（早就推出去，非在飛）",
    "obsolete": "已改寫、不在 HEAD 歷史 → 不會再進入任何推送範圍",
}


def _git(*args: str) -> str:
    p = subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True)
    return (p.stdout or "").strip()


def _is_ancestor(sha: str, ref: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", sha, ref],
                          cwd=str(REPO), capture_output=True).returncode == 0


def sha_state(sha: str) -> str:
    """判斷被閘門／稽核點名的 commit 現在該算不算問題（2026-09-15 新增）。

    回傳：
      approved：tree 在 .git/CIO_APPROVED 有紀錄（真審或 AUTO 補審）→ 已解決
      remote  ：已是 origin/<branch> 的祖先（那顆早就成功推出去了）→ 已解決
      pending ：仍在 HEAD 歷史、未上遠端、又沒有紀錄 → ❌ 真問題（未來 push 必被閘門擋）
      obsolete：已不在 HEAD 歷史（被 amend/rebase 改寫或丟棄）→ ℹ️ 不會再進任何推送範圍

    背景：閘門擋下（TAG-BLOCKED-CODE）或被擋的那次推送範圍（range-missing）若之後改走
    RECORD 重做成新 commit，舊 commit 就變成孤兒；舊寫法只看 tree_approved，會讓這種
    「已改寫重做」的案件在稽核裡掛滿 24h（每晚誤報一次），實際上沒有任何東西待處理。
    """
    if apush.tree_approved(REPO, sha):
        return "approved"
    # 非 commit（例如誤抓到 tree hash）→ 保守視為未解決
    if subprocess.run(["git", "cat-file", "-t", sha], cwd=str(REPO),
                      capture_output=True, text=True).stdout.strip() != "commit":
        return "pending"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "HEAD"
    if _is_ancestor(sha, f"origin/{branch}"):
        return "remote"
    if _is_ancestor(sha, "HEAD"):
        return "pending"
    return "obsolete"


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
            flagged.append((lane, parts[2], sha_state(parts[2])))
    if not quiet:
        used = "、".join(f"{k}×{v}" for k, v in sorted(counts.items())) or "無推送"
        print(f"③ 推送通道（近 24h）：{used}")
    settled: list = []
    for lane, sha, st in flagged:
        tag = f"{lane} {sha[:12]}"
        if st != "pending":
            settled.append(f"{tag}｜{SETTLED_REASON[st]}")
            continue
        if lane == "SKIPREVIEW-CODE":
            problems.append(f"程式檔走例外通道（未經真審、仍在推送範圍）：{tag}")
        else:
            problems.append(f"自動化以 TAG 推程式被擋（該路徑需改走 RECORD、仍在推送範圍）：{tag}")
    if not quiet and settled:
        print(f"   （已解決、不列問題：{len(settled)} 筆）")
        for s in settled:
            print(f"     ℹ️ {s}")
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
            # 逐顆複核：被點名的 commit 若之後已補上審查紀錄／已上遠端／已被改寫 → 視為已解決，不列問題
            # （否則一筆「當下落後、稍後補齊」的正常過程會在稽核裡掛 24 小時）
            shas = re.findall(r"\b[0-9a-f]{7,40}\b", parts[4])
            unresolved = [s for s in shas if sha_state(s) == "pending"]
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
            print(f"   （range-missing 已補紀錄／已改寫、不列問題：{len(resolved)} 筆）")
        if not missed and (counts or resolved):
            print("   ℹ️ 以上皆為他班／歷史 range 的未提交檔或已補紀錄案件 → 非本次問題（真問題只有 range-missing 未補）")
    for x in missed:
        problems.append(f"推送範圍有 commit 無審查紀錄（該次 push 會被擋）：{x}")
    return problems


SNAP_FILE = REPO / "snapshot.json"
INDEX_FILE = REPO / "index.html"
LIFE_ACCOUNT_MIN = "40000"   # 玉山／富邦生活帳戶安全線（4 萬，刻意常數；非 3 個月支出）
EXPECT_SAFE_ANCHORS = 4      # 儀表板 safe_line 錨點數（4 張 3 個月安全線卡）
EXPECT_BANK_MIN = 4          # 3 個月安全線門檻數（國泰／台新／永豐／將來）
EXPECT_LIFE_MIN = 2          # 生活帳戶門檻數（玉山／台北富邦）


def step_consistency(quiet: bool) -> list:
    """⑤ 真值一致性（2026-09-21 INC-233）：月支出口徑與儀表板安全線不得靜默漂移。

    檢查：
      - snapshot：monthly_expense_cash + monthly_expense_accrual == monthly_expense（缺欄位／非數字＝❌）
      - snapshot：若殘留 monthly_fixed_expense.分層 重複來源 → 必須與頂層同值（單一來源＝缺席才正常）
      - index.html：safe_line 錨點與 data-min 門檻數量必須齊全、值等於月支出×3；不得殘留佔位符
    原則：畸形值不得讓本步拋例外（否則 cron --silent-ok 只剩 traceback、丟掉整份問題清單）。
    """
    import json as _json

    def _num(v):
        """寬鬆轉數字：None／布林／空字串／千分位／浮點 → int；真的非數字才回 None（由呼叫端列為問題）。"""
        if v is None or isinstance(v, bool):
            return None
        try:
            return int(float(str(v).replace(",", "").strip()))
        except Exception:
            return None

    problems: list = []
    expense = cash = accrual = None   # 先綁定：畸形 snapshot 時摘要列印也不得 UnboundLocalError
    try:
        snap = _json.loads(SNAP_FILE.read_text(encoding="utf-8"))
    except Exception as e:                                     # snapshot 壞掉不算本步問題（別班會亮）
        if not quiet:
            print(f"⑤ 真值一致性：⚪ 無法讀 snapshot（{e}）")
        return problems
    try:                        # ① snapshot 側（獨立 try：這裡壞掉不得遮住儀表板檢查）
        if not isinstance(snap, dict):
            raise TypeError(f"snapshot 根不是物件（{type(snap).__name__}）")
        expense = _num(snap.get("monthly_expense"))
        if expense is None:
            problems.append(f"monthly_expense 不是數字（{snap.get('monthly_expense')!r}）")
        cash = _num(snap.get("monthly_expense_cash"))
        accrual = _num(snap.get("monthly_expense_accrual"))
        if snap.get("monthly_expense_cash") is None or snap.get("monthly_expense_accrual") is None:
            problems.append("月支出分層欄位缺失（monthly_expense_cash／monthly_expense_accrual）→ 無法驗證現金扣帳口徑")
        elif cash is None or accrual is None:
            problems.append(f"月支出分層非數字（現金 {snap.get('monthly_expense_cash')!r}／帳上 {snap.get('monthly_expense_accrual')!r}）")
        elif expense is not None and cash + accrual != expense:
            problems.append(f"月支出分層不合：現金扣帳 {cash} + 帳上計息 {accrual} ≠ 月支出 {expense}")
        mfe = snap.get("monthly_fixed_expense")
        if mfe is not None and not isinstance(mfe, dict):
            problems.append(f"monthly_fixed_expense 型別異常（{type(mfe).__name__}）")
        lay = (mfe or {}).get("分層") if isinstance(mfe, dict) else None
        if isinstance(lay, dict):   # 單一來源＝不該有這個副本；有副本就必須同值（2026-09-21 已刪除重複來源）
            for k, v in (("現金扣帳合計", cash), ("帳上計息合計", accrual), ("合計", expense)):
                if v is None:
                    continue
                if _num(lay.get(k)) != v:
                    problems.append(f"分層副本漂移：monthly_fixed_expense.分層.{k}={lay.get(k)!r} ≠ {v}")
        elif lay is not None:
            problems.append(f"monthly_fixed_expense.分層 型別異常（{type(lay).__name__}）")
    except Exception as e:
        problems.append(f"真值一致性（snapshot 側）檢查異常：{type(e).__name__}: {e}")
    try:                        # ② 產出側
        if expense is None:
            if not quiet:
                print("⑤ 真值一致性：⚪ monthly_expense 無法解析，儀表板比對略過")
        else:
            safe3 = expense * 3
            want = f"{safe3:,}"
            if not INDEX_FILE.exists():
                problems.append(f"index.html 不存在（無法驗證安全線 {want}）")
            else:
                html = INDEX_FILE.read_text(encoding="utf-8", errors="replace")
                anchors = re.findall(r'data-k="safe_line">([^<]*)<', html)
                bad = sorted({v for v in anchors if v != want})
                if bad:
                    problems.append(f"index.html 安全線錨點為 {bad}（應為 {want}＝月支出 {expense:,}×3）")
                if len(anchors) != EXPECT_SAFE_ANCHORS:
                    problems.append(f"index.html 安全線錨點數量 {len(anchors)} ≠ {EXPECT_SAFE_ANCHORS}（元素被刪／結構變動）")
                mins = re.findall(r'data-min="([^"]*)"', html)
                bank = [v for v in mins if v != LIFE_ACCOUNT_MIN]
                life = [v for v in mins if v == LIFE_ACCOUNT_MIN]
                for v in sorted(set(bank)):
                    if not v.isdigit():
                        problems.append(f"index.html 銀行卡門檻格式錯誤 {v!r}（JS Number() 會得 NaN）")
                    elif int(v) != safe3:
                        problems.append(f"index.html 銀行卡門檻未跟月支出：{v}（應為 {safe3}）")
                if len(bank) != EXPECT_BANK_MIN:
                    problems.append(f"index.html 銀行卡門檻數量 {len(bank)} ≠ {EXPECT_BANK_MIN}")
                if len(life) != EXPECT_LIFE_MIN:
                    problems.append(f"index.html 生活帳戶門檻數量 {len(life)} ≠ {EXPECT_LIFE_MIN}")
                if "__SAFE_LINE_RAW__" in html:
                    problems.append("index.html 殘留未取代佔位符 __SAFE_LINE_RAW__")
    except Exception as e:
        problems.append(f"真值一致性（index.html 側）檢查異常：{type(e).__name__}: {e}")
    if not quiet:
        _c = f"{cash:,}" if cash is not None else "—"
        _a = f"{accrual:,}" if accrual is not None else "—"
        _e = f"{expense:,}" if expense is not None else "—"
        print(f"⑤ 真值一致性：月支出 {_e}（現金 {_c}＋帳上 {_a}）"
              f"｜{'❌ ' + str(len(problems)) + ' 項' if problems else '✅'}")
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
        cons_problems = step_consistency(args.quiet or args.silent_ok)

        problems = []
        if left_claims:
            problems.append(f"未釋放的排程認領 {left_claims} 筆")
        if "全部通過" not in concl:
            problems.append(concl.replace("閉環稽核結果：", ""))
        problems.extend(lane_problems)
        problems.extend(warn_problems)
        problems.extend(cons_problems)

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
