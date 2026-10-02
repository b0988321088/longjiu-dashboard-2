#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄轉發器 → repo/cost_watch.py close（cron 只吃單一檔名、不傳參數）。

2026-10-02 追加（22:40 收工稽核連續誤報修復）：close（22:30）會 upsert 帳本
data/ai_cost_daily.jsonl，但過去只留在工作區不提交 → 22:00 晚報（git add -A）之後才寫入，
於是 22:40 稽核每晚必判「已追蹤未提交」（10/1、10/2 實例）。
改為：close 跑完就地提交自家費用檔（純資料）→ 走 auto_push.py 唯一出口推送。
設計要點與 digest 班完全一致：
  · 只 stage 自家檔案（費用頁／帳本），不用 `git add -A`，避免掃進別條路徑的未完成檔
  · 無變更就不 commit、不 push（靜默，cron 不會推空 commit）
  · close 失敗（rc≠0）仍嘗試推送已更新的帳本 —— 帳本停在舊版的代價比少推一次大
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

    r = subprocess.run([sys.executable, TARGET, "close"], cwd=REPO)
    if r.returncode != 0:
        print(f"⚠️ close rc={r.returncode}（帳本仍嘗試提交，不讓 22:40 稽核每晚誤報）")

    add = _git("add", *COST_FILES)
    if add.returncode != 0:
        sys.stderr.write(add.stderr or add.stdout)
        return 1

    if _git("diff", "--cached", "--quiet", "--", *COST_FILES).returncode == 0:
        print("費用帳本無變更，略過推送")
        return r.returncode

    msg = f"data: 費用帳本日結（close {dt.datetime.now():%Y-%m-%d %H:%M}）"
    c = _git("commit", "-m", msg, "--", *COST_FILES)
    if c.returncode != 0:
        sys.stderr.write((c.stdout or "") + (c.stderr or ""))
        return 1
    print((c.stdout or msg).strip().splitlines()[0])

    # 推送仍走唯一出口；但 close 本體失敗時 rc 要留著（帳本照推、故障照報，不靜默）
    push_rc = subprocess.run([sys.executable, "auto_push.py",
                              "--script", "cost_watch_close.py"], cwd=REPO).returncode
    return push_rc or r.returncode


if __name__ == "__main__":
    sys.exit(main())
