#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/cost_watch.py digest（cron 只吃單一檔名、不傳參數）。

2026-09-28 追加（使用者核准）：digest 產出的費用頁（cost.html／cost_data.json／
data/ai_cost_daily.jsonl）過去只留在本機，線上 Pages 要等到「四源同步」
（07:00／09:2x／23:15）那一班才更新 → 白天打開頁面永遠看到早上那版，
與 13:30／18:30 的推播必然對不起來。
實例：9/28 線上版 09:29（今日 42）vs 13:30 推播（今日 59），使用者提問。

改為：digest 跑完就地提交自家三檔（純資料）→ 走 auto_push.py 唯一出口推送。
頁面與推播自此同一時點、同一份資料。

設計要點：
  · 只 stage 自家三檔（不用 --auto-stage 的 `git add -A`，避免掃進別條路徑的未完成檔）
  · 無變更就不 commit、不 push（靜默，cron 不會推空 commit）
  · digest 失敗（rc≠0）仍嘗試推送已產出的費用頁 —— 頁面停在舊版的代價比少推一次大
  · auto_push 的 rc 原樣帶回（0＝已上線並驗證遠端 sha；3/4/5/6＝失敗，cron 端要看得到）
  · 2026-10-15（使用者核准）：rc=3 若源自「他條路徑尚未落紀錄的 commit」→ 改判為「跳過並記錄」
    （return 0 ＋ 明列該 commit）。只 stage 自家三檔，別條路徑的未審 commit 不是本 job 的失敗；
    但若範圍內唯一未落紀錄的就是本 job 自己那顆，仍原樣回 rc=3（fail-closed，不掩蓋）。
"""
import datetime as dt
import json
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
if REPO not in sys.path:
    sys.path.insert(0, REPO)  # 供 artifact_manifest 匯入（B 案）
TARGET = os.path.join(REPO, "cost_watch.py")
COST_FILES = ("cost.html", "cost_data.json", "data/ai_cost_daily.jsonl")


def _git(*args, **kw):
    return subprocess.run(["git", *args], cwd=REPO, text=True,
                          capture_output=True, **kw)


def _unpushed() -> list[str]:
    """origin/clean-main..HEAD 的 commit（`<short sha> <subject>`，新到舊）。"""
    r = _git("log", "--format=%h %s", "origin/clean-main..HEAD")
    return [ln for ln in (r.stdout or "").splitlines() if ln.strip()]


def main() -> int:
    if not os.path.exists(TARGET):
        sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
        return 1

    r = subprocess.run([sys.executable, TARGET, "digest"], cwd=REPO)
    if r.returncode != 0:
        print(f"⚠️ digest rc={r.returncode}（費用頁仍嘗試推送，不讓線上停在舊版）")

    # ── B 案（INC-20261106-01，使用者 2026-11-06 裁決③）────────────────────
    # 舊行為：git add → git commit → auto_push。2026-11-06 13:30 因此產生 f83b2d2d，
    #         讓人工核對窗口內 HEAD 漂移；且因範圍含缺 RECORD 的 9dd6e960 被 rc=3 擋下。
    # 新行為：產生 → 驗證 → 寫 artifact_manifest.json → 停止（不 commit／不 push）。
    #         前一顆 commit 缺 CIO RECORD 時，不得由本排程繞過審查或重排發布順序；
    #         該問題由獨立 CIO 流程處理。commit 統一交每日單一窗口（22:38）。
    rc_verify = 0 if r.returncode == 0 else r.returncode
    try:
        from artifact_manifest import write_manifest
        _snap = {}
        try:
            _snap = json.loads((REPO / "snapshot.json").read_text(encoding="utf-8"))
        except Exception:
            _snap = {}
        write_manifest(
            producer="cost_watch_digest.py",
            artifacts=list(COST_FILES),
            report_base_date=str(_snap.get("date") or "")[:10] or None,
            source_dates={"cost_ledger": dt.date.today().isoformat()},
            note=f"digest rc={r.returncode}；B 案停止於留痕，未 commit／未 push",
        )
    except Exception as exc:  # 留痕失敗不得靜默
        sys.stderr.write(f"ERROR: artifact_manifest 寫入失敗：{exc}\n")
        return 1

    print("⏸ B 案：已留痕，未 commit、未 push（發布交由每日單一窗口）")
    return rc_verify


if __name__ == "__main__":
    sys.exit(main())
