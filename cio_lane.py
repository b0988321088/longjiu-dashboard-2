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
DIFF_CAP = 12000                      # 送審內文上限（避免把整份 HTML 塞進 prompt）
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
    segs = [patch[i:i + DIFF_CAP] for i in range(0, len(patch), DIFF_CAP)] or [""]
    if "".join(segs) != patch:      # 切片自我檢查：無遺漏、無重複
        return False, "分段覆蓋不完整（切片自我檢查失敗）→ fail-closed"

    rev = None
    reviewers, seg_notes = [], []
    _off = 0
    for _idx, _seg in enumerate(segs, 1):
        # 分段時補「本段所屬檔案」脈絡：段首常落在檔案中段（該段沒有 diff --git 行），
        # 審查者會看不出在看哪個檔（2026-10-14 首次實戰踩到）。
        _head = patch[:_off]
        _di = _head.rfind("diff --git ")
        _seg_file = (_head[_di:].splitlines()[0].split(" b/")[-1]
                     if _di >= 0 else "（本段為 commit 開頭）")
        # prompt 仍走 review_chain 單一真值（不在此另寫一份）
        prompt = _rc.build_review_prompt(commit, tree, subj, files, stat, DIFF_CAP,
                                         patch=f"# ⓘ 本段所屬檔案：{_seg_file}\n{_seg}",
                                         segment=(_idx, len(segs)))
        _off += len(_seg)
        try:
            txt, _rvw = _rc.review(prompt, max_tokens=8192, timeout=300)
        except Exception as e:  # noqa: BLE001
            return False, (f"第 {_idx}/{len(segs)} 段審查鏈不可用"
                           f"（{type(e).__name__}: {str(e)[:120]}）→ fail-closed（不降級、不落 RECORD）")
        reviewers.append(_rvw)
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return False, f"第 {_idx}/{len(segs)} 段審查輸出無法解析出 JSON → fail-closed"
        try:
            _rv = json.loads(m.group(0))
        except Exception as e:  # noqa: BLE001
            return False, f"第 {_idx}/{len(segs)} 段審查 JSON 解析失敗（{str(e)[:60]}）→ fail-closed"
        _v = str(_rv.get("verdict", "")).strip().upper()
        _blk = _rv.get("blocking") or []
        _pairs = {(str(x.get("commit", ""))[:12], str(x.get("tree", ""))[:12])
                  for x in (_rv.get("reviewed_commits") or []) if isinstance(x, dict)}
        if _rv.get("commit") and _rv.get("tree"):
            _pairs.add((str(_rv["commit"])[:12], str(_rv["tree"])[:12]))
        if _v != "APPROVE":
            _nt = str(_rv.get("note") or "")[:200]
            _bl = json.dumps(_blk[:2], ensure_ascii=False)[:300]
            return False, (f"第 {_idx}/{len(segs)} 段審查未通過（verdict={_v or '空'}）→ fail-closed"
                           f"｜note：{_nt}｜blocking：{_bl}")
        if _blk:
            _bl = json.dumps(_blk[:2], ensure_ascii=False)[:300]
            return False, (f"第 {_idx}/{len(segs)} 段審查有 blocking {len(_blk)} 項 → fail-closed"
                           f"｜{_bl}")
        if (commit[:12], tree[:12]) not in _pairs:
            return False, (f"第 {_idx}/{len(segs)} 段回傳的 commit／tree 與實際待推內容不符"
                           "（範圍無法對應）→ fail-closed")
        seg_notes.append(f"seg{_idx}:{_v}/blocking={len(_blk)}/{_rvw}")
        if _idx == 1:
            rev = _rv
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
