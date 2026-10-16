#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cio_lane.py — 「真 CIO 審查＋落 RECORD」的共用車道（2026-10-13 建立）

為什麼要有這一支（2026-10-13 台股緊急應變發布故障根因）：
    閘門（publish_gate）把 index.html／daily_report_v2_*.html（未命中白名單）與 snapshot.json／
    dashboard_decisions.json／pending_decisions.json／work_log.json（特殊類別）列為「強制真 CIO」。
    任何 producer 只要把這類檔 commit 進本機歷史、卻沒取得真 CIO RECORD，那顆 commit 就永遠
    推不出去，而且會把**整條推送範圍**（含其他 producer 之後的新 commit）一起卡死——
    13:01 的兩顆 daily_deploy commit 就是這樣讓 13:06 的緊急應變資料與四源同步全部上不了線
    （線上緊急應變 HTML 一度 404）。

語意與 regenerate_report.py 的 `_cio_review_and_record` 同源（該檔為模組層腳本、無法被 import，
故抽出共用版；regenerate_report 內的原實作保留不動，避免動到 07:00 主產線）。
    fail-closed 條件：範圍不唯一（舊 commit 阻塞）／審查工具不可用／輸出不可解析／非 APPROVE／
    有 blocking／回傳的 commit 或 tree 與實際不符／紀錄寫入失敗／寫入後複驗失敗。
    契約（使用者 2026-10-12 條件 1／2）：待推範圍內每一顆都必須有 RECORD；只有 HEAD 可由本步驟送審補上。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIFF_CAP = 32000                      # 送審內文上限（與 review_chain.DEFAULT_DIFF_CAP 同值；2026-10-16 裁決 12,000 → 32,000，段數↓但涵蓋率仍 100%）
# 2026-10-13（TD-20261013-05）：審查者標籤改為**動態**（由 review_chain 回報實際使用者）。
# 本常數僅保留為「鏈全數失敗時」的敘述基準，不再寫進 RECORD。
REVIEWER_FALLBACK_NOTE = "CIO-review-chain（異質：Pollinations／nous-longcat／nous-laguna）"


def _git(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(BASE), timeout=timeout)


def governance_invariant(commit: str) -> str:
    """治理檔不變量（使用者條件 2：meta 不一致 → 停止發布）。回傳錯誤訊息，空字串＝通過。

    只驗 dashboard_decisions.json：決策只許純追加、meta 除 updated_at 外逐位元不變。
    """
    gov = "dashboard_decisions.json"
    changed = _git("show", "--name-only", "--format=", commit).stdout.split()
    if gov not in changed:
        return ""
    old_raw = _git("show", f"{commit}^:{gov}").stdout
    new_raw = _git("show", f"{commit}:{gov}").stdout
    try:
        old = json.loads(old_raw)
        new = json.loads(new_raw)
    except Exception as e:  # noqa: BLE001
        return f"{gov} 解析失敗（{type(e).__name__}: {str(e)[:60]}）→ fail-closed"
    if old.get("meta") != new.get("meta"):
        # 產線每次執行都會重寫 updated_at（時間戳），只放行該欄；其餘 meta 變動＝真異常 → fail-closed
        _om = {k: v for k, v in (old.get("meta") or {}).items() if k != "updated_at"}
        _nm = {k: v for k, v in (new.get("meta") or {}).items() if k != "updated_at"}
        if _om != _nm:
            return f"{gov}.meta 變動（非 updated_at 時間戳）→ fail-closed"
    o, n = old.get("decisions") or [], new.get("decisions") or []
    if len(n) < len(o) or n[:len(o)] != o:
        return f"{gov}.decisions 非純追加（{len(o)}→{len(n)}）→ fail-closed"
    return ""


def review_and_record(tag: str = "cio_lane") -> tuple[bool, str]:
    """外部入口：先切到 repo 根目錄再執行。

    為什麼要 chdir：`cio_approve.py` 在 import 期與內部一律用「相對於 cwd」的 git 呼叫
    （`git rev-parse --git-dir` 失敗即 sys.exit(2)）。cron 從 hermes/scripts 啟動本車道時
    cwd 不在 repo 內 → 整個流程會被 sys.exit(2) 殺掉，呼叫端已 commit 的那顆就變成
    「未落紀錄又推不出去」的毒藥 commit（2026-10-13 22:15 實跑踩到）。故在此統一切換 cwd。
    """
    import os
    prev = os.getcwd()
    try:
        os.chdir(BASE)
        return _review_and_record_repo_cwd(tag)
    finally:
        os.chdir(prev)


def build_segments(commit: str, tree: str, subj: str, files: str, stat: str, patch: str,
                   diff_cap: int = DIFF_CAP) -> tuple[list[str], dict, list[str]]:
    """分段送審（2026-10-15 基建修復）：回 (prompts, coverage, segs)。

    舊版症狀（2026-10-15 實測，0da98b37）：自己做字元切片後，把「本段所屬檔案」脈絡
    **串進 patch 參數** → 該段長度 = diff_cap + 脈絡（12000 + 43 = 12043）→
    `build_review_prompt` 內 `patch[:diff_cap]` 二次截斷 → `_coverage_note` 明示
    「涵蓋率 99.6%」→ 當日 B1／R1 守門（涵蓋率 <100% 不得 APPROVE）必然 REJECT，
    且與內容無關（審查者自述「內容本身未見可指名之阻塞缺陷」）。

    修法：① 分段與 prompt 一律走 `review_chain.build_review_prompts`（單一真值；
       切片後每段 ≤ diff_cap，故不再發生二次截斷，coverage 由該函式回報）；
      ② 「本段所屬檔案」脈絡改加在 **prompt 開頭（diff fence 之外）**，不佔 diff 預算。
    守門不放寬：涵蓋率 <100% 仍由 `review_segmented` 直接 REJECT（不呼叫模型）。
    """
    total = len(patch or "")
    import review_chain as _rc          # 模組層未 import（本檔原有呼叫端在函式內延遲載入），此處沿用同風格
    # 2026-10-16（使用者裁決「修掉切片造成的假拒絕」）：分段改走 review_chain.split_patch
    #   單一真值 —— 以**檔案邊界**優先、單檔超限才續切；本檔不再自行做字元切片
    #   （自有切片會切穿檔案與超長行，實測 cost.html 的 seed JSON 被切半 → 假 REJECT）。
    segs = [d["text"] for d in _rc.split_patch(patch, diff_cap)] or [""]
    if "".join(segs) != patch:          # 切片自我檢查：無遺漏、無重複
        raise ValueError("分段覆蓋不完整（切片自我檢查失敗）")
    prompts, cov = _rc.build_review_prompts(commit, tree, subj, files, stat, diff_cap, patch)
    if len(prompts) != len(segs) or int(cov.get("segments", -1)) != len(segs):
        raise ValueError("prompt 段數與切片段數不一致（內部不變量）")
    _off = 0
    for k, seg in enumerate(segs):
        # 段首常落在檔案中段（該段沒有 diff --git 行）→ 補「本段所屬檔案」脈絡；
        # 加在 prompt 開頭，不進 diff → 不會吃掉 diff 預算（本次修復的關鍵）。
        # 2026-10-16：分段以檔案邊界為優先後，此脈絡對「超限單檔續切段」仍有作用，
        #   且與 review_chain 的分段脈絡（第 j/m 段）互補、不衝突。
        _head = patch[:_off]
        _di = _head.rfind("diff --git ")
        _seg_file = (_head[_di:].splitlines()[0].split(" b/")[-1]
                     if _di >= 0 else "（本段為 commit 開頭）")
        prompts[k] = f"# ⓘ 本段所屬檔案：{_seg_file}\n{prompts[k]}"
        _off += len(seg)
    return prompts, cov, segs


def _review_and_record_repo_cwd(tag: str = "cio_lane") -> tuple[bool, str]:
    """對「待推範圍」取得真 CIO APPROVE 並落 RECORD。回傳 (可否繼續推送, 說明)。

    已有 APPROVE 的 tree → 直接回 True（不重複審查、不重複落紀錄）。
    前置：cwd 必須在 repo 內（由 review_and_record() 保證）。
    """
    import cio_approve as _ca          # 既有工具：紀錄格式單一真值（不自行解析 tab 格式）
    import review_chain as _rc         # 審查鏈單一實作（2026-10-13 TD-20261013-05／06）

    rng = _git("rev-list", "origin/clean-main..HEAD")
    if rng.returncode != 0:
        return False, "讀不到 origin/clean-main（尚未 fetch／遠端不存在）→ fail-closed"
    pending = [c for c in rng.stdout.split() if c]
    if not pending:
        return True, "無待推 commit"
    unrecorded = []
    for c in pending:
        t = _git("rev-parse", f"{c}^{{tree}}").stdout.strip()
        if not t:
            return False, f"取不到 tree（{c[:12]}）→ fail-closed"
        if not _ca.is_approved(t):
            unrecorded.append(c)
    others = [c for c in unrecorded if c != pending[0]]
    if others:
        return False, (f"待推範圍含未落紀錄的舊 commit（{len(others)} 顆："
                       f"{', '.join(c[:12] for c in others)}）→ 先清阻塞再重跑（fail-closed）")
    commit = pending[0]
    tree = _git("rev-parse", f"{commit}^{{tree}}").stdout.strip()
    if not tree:
        return False, "取不到 tree → fail-closed"
    if commit not in unrecorded:
        return True, f"tree {tree[:12]} 已有 APPROVE 紀錄（跳過審查）"

    inv = governance_invariant(commit)
    if inv:
        return False, inv

    files = _git("show", "--name-only", "--format=", commit).stdout.strip()
    subj = _git("log", "-1", "--format=%s", commit).stdout.strip()
    stat = _git("show", "--stat", "--format=", commit).stdout.strip()
    # 2026-10-14 W1（使用者核准 A+C）：送**完整 patch**，不再以 --stat 統計代替程式碼。
    # 原版送 --name-only 158 字元＋--stat 504 字元＝662 字元，審查者看不到任何一行程式碼
    # → APPROVE 只證明通過「通道類型判斷」，不及內容正確性。
    patch = _git("show", "--format=", commit).stdout or ""
    try:
        prompts, cov, segs = build_segments(commit, tree, subj, files, stat, patch)
    except Exception as e:  # noqa: BLE001
        return False, f"分段組裝失敗（{type(e).__name__}: {str(e)[:100]}）→ fail-closed"
    if int(cov.get("segments", 1)) != len(prompts):
        return False, "分段數與送審 prompt 數不一致（內部不變量）→ fail-closed"
    if float(cov.get("pct", 0.0) or 0.0) < 100.0:
        return False, (f"diff 涵蓋率 {cov.get('pct')}% < 100% → fail-closed"
                       "（不得以未完整檢視的審查落 RECORD）")

    # 逐段審查＋彙總走 review_chain 單一真值（review_segmented）：涵蓋率 <100% 直接
    # REJECT 且不呼叫模型；每段都必須原樣回報 12 碼 commit／tree 綁定，否則整體 REJECT。
    # json_mode=False 沿用本車道既有行為（本次修復只針對覆蓋率，不改變送審模式）。
    try:
        _txt, _reviewer1, _meta = _rc.review_segmented(
            prompts, cov, max_tokens=8192, timeout=300, json_mode=False,
            expect_pair=(commit[:12], tree[:12]))
    except Exception as e:  # noqa: BLE001
        return False, (f"審查鏈不可用（{type(e).__name__}: {str(e)[:120]}）"
                       "→ fail-closed（不降級、不落 RECORD）")
    reviewers: list[str] = [_reviewer1]
    seg_notes: list[str] = list(_meta.get("labels") or [])
    rev = _rc.parse_review(_txt)
    if not isinstance(rev, dict):
        return False, "審查輸出無法解析出 JSON → fail-closed"
    _v = str(rev.get("verdict") or "").strip().upper()
    _blk = rev.get("blocking") or []
    if _v != "APPROVE":
        return False, (f"審查未通過（verdict={_v or '空'}）→ fail-closed"
                       f"｜note：{str(rev.get('note') or '')[:200]}"
                       f"｜blocking：{json.dumps(_blk[:2], ensure_ascii=False)[:300]}")
    if _blk:
        return False, (f"審查有 blocking {len(_blk)} 項 → fail-closed"
                       f"｜{json.dumps(_blk[:2], ensure_ascii=False)[:300]}")
    # B1／R1 契約（blocking 非空 ⇔ REJECT）跨段再驗一次：`review_segmented` 只以 blocking
    # 彙總，若某段回 REJECT 而 blocking 為空（＝無效審查、未指名缺陷），彙總會變成
    # APPROVE → 這類「無效審查」不得當成核准。逐段 verdict 記在彙總 note（seg{k}:VERDICT@label）。
    _seg_note = str(rev.get("note") or "")
    if ":REJECT" in _seg_note.replace(" ", ""):
        return False, (f"分段審查含 REJECT 但未指名缺陷（無效審查）→ fail-closed"
                       f"｜{_seg_note[:200]}")
    _cv = _rc.contract_violation(rev)
    if _cv:
        return False, f"審查契約違規（{_cv}）→ fail-closed"
    # 完整性記錄（使用者契約 2026-10-14：總字元數／送審字元數／是否含 patch／各段覆蓋）
    _sent = sum(len(s) for s in segs)
    rev["_lane_meta"] = {
        "patch_total_chars": len(patch),
        "patch_sent_chars": _sent,
        "has_patch": bool(patch),
        "segments": len(segs),
        "coverage_pct": round(_sent / len(patch) * 100, 2) if patch else 100.0,
        "segment_verdicts": seg_notes,
        "reviewers": reviewers,
    }
    # 2026-10-14 W1：per-段 verdict／blocking／commit-tree 綁定已在上方迴圈**逐段**驗證完畢
    # （原單段檢查已移除，避免與分段邏輯各判一次而漂移）。綁定仍採 12 碼前綴——
    # 免費層模型抄寫 40 碼 sha 會掉字元（c3b3a143 該輪 tree 40 碼被抄成 39 碼，曾造成連續誤擋）。
    if rev is None or not rev.get("_lane_meta"):
        return False, "分段審查未產生完整性紀錄（內部不變量）→ fail-closed"
    # 2026-10-14 W1：分段審查後 reviewer 由單一值改為清單；此處合成標籤（去重保序），
    # 供 cio_approve 落紀錄與回傳訊息使用。原單段版殘留的 `_reviewer` 變數已由迴圈取代
    # （測試 test_01 在改名時抓到 NameError，修復於此）。
    _reviewer = " + ".join(dict.fromkeys(reviewers)) if reviewers else "unknown"
    rdir = BASE / ".git" / "cio_reviews"
    try:
        rdir.mkdir(parents=True, exist_ok=True)
        rj = rdir / f"{date.today().isoformat()}_{tag}_{commit[:12]}.json"
        rj.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return False, f"審查紀錄寫入失敗（{str(e)[:60]}）→ fail-closed"
    ap_ = subprocess.run([sys.executable, str(BASE / "cio_approve.py"), "--result", str(rj),
                          "--reviewer", _reviewer, "--commit", commit],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE))
    if ap_.returncode != 0:
        return False, f"cio_approve 落紀錄失敗（rc={ap_.returncode}）→ fail-closed"
    if not _ca.is_approved(tree):
        return False, "落紀錄後複驗失敗（tree 仍無 APPROVE）→ fail-closed"
    return True, f"真 CIO RECORD 已落地（{_reviewer}｜tree {tree[:12]}）"


def rollback_head_soft() -> tuple[bool, str]:
    """撤回本步驟剛產生的 HEAD commit（保留工作區內容），避免留下「推不出去又卡住整條範圍」的 commit。"""
    r = _git("reset", "--soft", "HEAD~1")
    if r.returncode != 0:
        return False, f"git reset --soft HEAD~1 失敗（{r.stderr.strip()[:80]}）→ 請人工處理"
    return True, "已撤回本步驟 commit（內容留在工作區，下一輪可重試）"


def _cli() -> int:
    """CLI 入口：供 cron / shell 用單一指令呼叫（語義與 auto_record.py 對稱：exit 0=OK、非 0=不要 push）。

    2026-10-13 增設：原本只有函式入口，shell 端只能用 `python -c "import cio_lane; ..."`，
    cron prompt 裡嵌引號容易出錯。補對稱的 CLI，讓產線用一行、與 auto_record.py 同形狀的指令落版。
    """
    import argparse
    ap = argparse.ArgumentParser(
        prog="cio_lane.py",
        description="真 CIO 審查＋落 RECORD（對「待推範圍」）",
    )
    ap.add_argument("--tag", default="cio_lane", help="審查紀錄檔名標籤（預設 cio_lane）")
    a = ap.parse_args()
    ok, msg = review_and_record(a.tag)
    print(("✅ OK | " if ok else "❌ FAIL | ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
