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
REVIEWER = "CIO-Pollinations(openai)"  # 異質審查者（非 DeepSeek、非 Google）


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
    """對「待推範圍」取得真 CIO APPROVE 並落 RECORD。回傳 (可否繼續推送, 說明)。

    已有 APPROVE 的 tree → 直接回 True（不重複審查、不重複落紀錄）。
    """
    import cio_approve as _ca          # 既有工具：紀錄格式單一真值（不自行解析 tab 格式）
    import llm_review_client as _lrc

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
    diff = _git("show", "--stat", "--format=", commit).stdout.strip()
    prompt = (
        "你是龍九控股的獨立 CIO 審查者（異質審查，不得預設放行）。只回傳 JSON，不要任何其他文字。\n"
        f"待推送 commit：{commit}\n待推送 tree：{tree}\n主旨：{subj}\n\n"
        f"變更檔案清單：\n{files[:DIFF_CAP]}\n\n變更統計：\n{diff[:DIFF_CAP]}\n\n"
        "審查重點：①是否含程式／治理紀錄／憑證類變更而走資料通道 ②資料是否自相矛盾或截斷 "
        "③是否與使用者既定裁決衝突（例如公開首頁必經真 CIO、不可放寬審查）④是否有 blocking 級缺陷。\n"
        "輸出格式（務必逐字包含 commit 與 tree，用於綁定）：\n"
        '{"verdict":"APPROVE 或 REJECT","reviewed_commits":[{"commit":"' + commit + '","tree":"' + tree + '"}],'
        '"blocking":[],"required_fixes":[],"note":"理由（160 字內）"}'
    )
    try:
        txt = _lrc._call(_lrc.POLLI_URL, {"Content-Type": "application/json", "User-Agent": _lrc.UA},
                         _lrc.POLLI_MODEL, prompt, 8192, 300, extra={"reasoning_effort": "low"})
    except Exception as e:  # noqa: BLE001
        return False, f"審查工具不可用（{type(e).__name__}: {str(e)[:80]}）→ fail-closed（不降級）"
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return False, "審查輸出無法解析出 JSON → fail-closed"
    try:
        rev = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        return False, f"審查 JSON 解析失敗（{str(e)[:60]}）→ fail-closed"
    verdict = str(rev.get("verdict", "")).strip().upper()
    blocking = rev.get("blocking") or []
    ok_pairs = {(str(x.get("commit", ""))[:12], str(x.get("tree", ""))) for x in (rev.get("reviewed_commits") or [])
                if isinstance(x, dict)}
    if verdict != "APPROVE":
        return False, f"審查未通過（verdict={verdict or '空'}）→ fail-closed"
    if blocking:
        return False, f"審查有 blocking {len(blocking)} 項 → fail-closed"
    if (commit[:12], tree) not in ok_pairs:
        return False, "審查回傳的 commit／tree 與實際待推內容不符（範圍無法對應）→ fail-closed"
    rdir = BASE / ".git" / "cio_reviews"
    try:
        rdir.mkdir(parents=True, exist_ok=True)
        rj = rdir / f"{date.today().isoformat()}_{tag}_{commit[:12]}.json"
        rj.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return False, f"審查紀錄寫入失敗（{str(e)[:60]}）→ fail-closed"
    ap_ = subprocess.run([sys.executable, str(BASE / "cio_approve.py"), "--result", str(rj),
                          "--reviewer", REVIEWER, "--commit", commit],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE))
    if ap_.returncode != 0:
        return False, f"cio_approve 落紀錄失敗（rc={ap_.returncode}）→ fail-closed"
    if not _ca.is_approved(tree):
        return False, "落紀錄後複驗失敗（tree 仍無 APPROVE）→ fail-closed"
    return True, f"真 CIO RECORD 已落地（{REVIEWER}｜tree {tree[:12]}）"


def rollback_head_soft() -> tuple[bool, str]:
    """撤回本步驟剛產生的 HEAD commit（保留工作區內容），避免留下「推不出去又卡住整條範圍」的 commit。"""
    r = _git("reset", "--soft", "HEAD~1")
    if r.returncode != 0:
        return False, f"git reset --soft HEAD~1 失敗（{r.stderr.strip()[:80]}）→ 請人工處理"
    return True, "已撤回本步驟 commit（內容留在工作區，下一輪可重試）"
