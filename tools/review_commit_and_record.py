#!/usr/bin/env python3
"""對指定 commit 跑「真 CIO 審查（完整覆蓋）」並（僅在 APPROVE 時）落 RECORD。

用途（2026-10-15）：cio_lane.py 的契約限制「只有 HEAD 能由該步驟送審補上」，但 22:30
費用帳本 lane 在本批之後又落了一顆 commit → 0da98b37 變成「範圍內的舊 commit」，
cio_lane 對它 fail-closed。auto_push 對這情境的官方指示是：
   「對該 commit 跑真審查後 python cio_approve.py --result <審查JSON> --reviewer X --commit <sha>」
本腳本即照該指示執行：review_chain 真審查（分段、涵蓋率 100%、契約檢查）→ 只在
verdict=APPROVE 且 blocking=[] 且 coverage=100% 時才呼叫 cio_approve 落紀錄。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import review_chain as rc          # noqa: E402
import cio_lane as lane            # noqa: E402


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=str(BASE), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def main() -> int:
    _arg = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    tag = sys.argv[2] if len(sys.argv) > 2 else "manual_range"
    # 2026-10-15 實踩：誤以「自己補齊的 40 碼 sha」當參數 → git 解析失敗但 show 回空字串
    # → patch=0 字元仍被送審並 APPROVE（等於無證據放行）。此處一律以 rev-parse 解析，
    # 且 patch 為空即中止（不送審、不落紀錄）。
    commit = git("rev-parse", f"{_arg}^{{commit}}").strip()
    if len(commit) != 40:
        print(f"❌ 參數無法解析為 commit：{_arg!r} → 中止")
        return 2
    tree = git("rev-parse", f"{commit}^{{tree}}").strip()
    files = git("show", "--name-only", "--format=", commit).strip()
    stat = git("show", "--stat", "--format=", commit).strip()
    subj = git("log", "-1", "--format=%s", commit).strip()
    patch = git("show", "--format=", commit)

    if not patch.strip() or not files.strip():
        print(f"❌ 取不到 {commit[:12]} 的 patch／檔案清單（空內容不得送審）→ 中止")
        return 2
    prompts, cov, segs = lane.build_segments(commit, tree, subj, files, stat, patch)
    print(f"[審查] commit={commit[:12]} tree={tree[:12]} 段數={len(prompts)} "
          f"涵蓋率={cov.get('pct')}% patch={len(patch)} 字元")
    if float(cov.get("pct", 0)) < 100.0:
        print("❌ 涵蓋率 <100% → 不送審、不落紀錄（fail-closed）")
        return 3
    try:
        txt, label, meta = rc.review_segmented(prompts, cov, max_tokens=8192, timeout=300,
                                               expect_pair=(commit[:12], tree[:12]))
    except Exception as e:  # noqa: BLE001
        print(f"❌ 審查鏈不可用：{type(e).__name__}: {str(e)[:160]} → 不落紀錄")
        return 4
    rev = rc.parse_review(txt) or {}
    verdict = str(rev.get("verdict") or "").upper()
    blocking = rev.get("blocking") or []
    cv = rc.contract_violation(rev)
    seg_note = str(rev.get("note") or "")
    print(f"[結果] reviewer={label} verdict={verdict} blocking={len(blocking)} 契約={cv or 'OK'}")
    print(f"[逐段] {seg_note[:400]}")
    for b in blocking[:5]:
        print(f"   - {str(b)[:220]}")

    _bad = (verdict != "APPROVE" or blocking or cv
            or ":REJECT" in seg_note.replace(" ", ""))
    if _bad:
        print("❌ 未通過 → 不落 RECORD（依裁決：重審仍有 blocking 不得自行寫入核准紀錄）")
        return 5

    rdir = BASE / ".git" / "cio_reviews"
    rdir.mkdir(parents=True, exist_ok=True)
    rj = rdir / f"{date.today().isoformat()}_{tag}_{commit[:12]}.json"
    rj.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[紀錄] 審查 JSON → {rj}")
    ap = subprocess.run([sys.executable, str(BASE / "cio_approve.py"), "--result", str(rj),
                         "--reviewer", label, "--commit", commit],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        cwd=str(BASE))
    print("[cio_approve]", (ap.stdout or "").strip()[-300:] or (ap.stderr or "").strip()[-300:])
    if ap.returncode != 0:
        print("❌ 落紀錄失敗 → fail-closed")
        return 6
    import cio_approve as ca
    ok = ca.is_approved(tree)
    print(f"[複驗] is_approved(tree {tree[:12]}) = {ok}")
    return 0 if ok else 7


if __name__ == "__main__":
    raise SystemExit(main())
