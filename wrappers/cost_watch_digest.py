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
"""
import datetime as dt
import os
import subprocess
import sys

REPO = r"C:/Users/bot/Desktop/longjiu_system"
TARGET = os.path.join(REPO, "cost_watch.py")
COST_FILES = ("cost.html", "cost_data.json", "data/ai_cost_daily.jsonl")


def _git(*args, **kw):
    return subprocess.run(["git", *args], cwd=REPO, text=True,
                          capture_output=True, **kw)


def main() -> int:
    if not os.path.exists(TARGET):
        sys.stderr.write(f"ERROR: 找不到真身 {TARGET}\n")
        return 1

    r = subprocess.run([sys.executable, TARGET, "digest"], cwd=REPO)
    if r.returncode != 0:
        print(f"⚠️ digest rc={r.returncode}（費用頁仍嘗試推送，不讓線上停在舊版）")

    add = _git("add", *COST_FILES)
    if add.returncode != 0:
        sys.stderr.write(add.stderr or add.stdout)
        return 1

    if _git("diff", "--cached", "--quiet", "--", *COST_FILES).returncode == 0:
        print("費用頁無變更，略過推送")
        return r.returncode

    msg = f"data: 費用頁同步（digest {dt.datetime.now():%Y-%m-%d %H:%M}）"
    c = _git("commit", "-m", msg, "--", *COST_FILES)
    if c.returncode != 0:
        sys.stderr.write((c.stdout or "") + (c.stderr or ""))
        return 1
    print((c.stdout or msg).strip().splitlines()[0])

    return subprocess.run([sys.executable, "auto_push.py",
                           "--script", "cost_watch_digest.py"], cwd=REPO).returncode


if __name__ == "__main__":
    sys.exit(main())
