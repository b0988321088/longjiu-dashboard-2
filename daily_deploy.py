#!/usr/bin/env python3
"""
龍九控股 自動推送腳本
流程：
  1. 呼叫 run_daily.py 產出檔案
  2. 呼叫 daily_checklist.py 檢查
  3. 呼叫 GitHub Contents API 推送 daily_report_v2_{date}.html + index.html
  4. 完成後推送兩個連結到 Telegram
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import base64
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
DAILY_REPORT = BASE / f"daily_report_v2_{TODAY}.html"
INDEX_FILE = BASE / "index.html"
REPO = os.getenv("GITHUB_REPO", "b0988321088/longjiu-dashboard-2")
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "clean-main")


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"\n[STEP] {name}")
    result = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[FAIL] {name}\n{result.stderr[:500]}")
        return False
    print(f"[OK] {name}")
    return True


def checklist_failed() -> bool:
    print("\n[STEP] checklist")
    result = subprocess.run(
        [sys.executable, str(BASE / "daily_checklist.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    return result.returncode != 0


def cio_review_failed() -> tuple[bool, str]:
    print("[STEP] cio_review")
    result = subprocess.run(
        [sys.executable, str(BASE / "cio_review.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        return True, result.stdout
    return False, result.stdout


def gemini_review_failed() -> tuple[bool, dict]:
    print("[STEP] gemini_review")
    result = subprocess.run(
        [sys.executable, str(BASE / "gemini_review.py")],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"[SKIP/WARN] gemini_review: {result.stderr[:200]}")
        return False, {}
    try:
        data = json.loads(result.stdout)
    except Exception:
        print(f"[WARN] gemini_review output parse failed: {result.stdout[:200]}")
        return False, {}
    status = data.get("status", "")
    if status == "rejected":
        print(f"[REJECTED] Gemini review: {data.get('summary', '')}")
        return True, data
    if status == "error":
        print(f"[ERROR] Gemini review: {data.get('reason', '')}")
        return False, data
    print(f"[OK] Gemini review: score={data.get('score', '?')}, summary={data.get('summary', '')}")
    return False, data


def github_push(filepath: str) -> bool:
    result = subprocess.run(
        ["git", "add", filepath],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        ["git", "commit", "-m", f"auto: {filepath} {TODAY}"],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  git commit: {result.stderr[:200]}")
    result = subprocess.run(
        ["git", "push", "origin", GITHUB_BRANCH],
        cwd=BASE,
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    print(f"  push {filepath} via git: {result.returncode}")
    if not ok:
        print(f"  {result.stderr[:300]}")
    return ok


def telegram_push(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[SKIP] Telegram 未設定，跳過推送")
        return True
    import requests

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text}
    r = requests.post(url, data=payload, timeout=10)
    ok = r.status_code == 200
    print(f"  telegram: {r.status_code}")
    return ok


def main() -> None:
    print(f"[DEPLOY] 日期：{TODAY}")

    # 1. 產出
    if not run_step("run_daily", [sys.executable, str(BASE / "run_daily.py")]):
        return

    # 2. 檢查
    if checklist_failed():
        print("[STOP] 檢查未過，停止推送")
        return

    # 2.5 CIO 審查
    failed_cio, cio_out = cio_review_failed()
    if failed_cio:
        print("[STOP] CIO 審查未過，停止推送")
        return

    # 2.6 Gemini review
    failed_gemini, gemini_data = gemini_review_failed()
    if failed_gemini:
        print("[STOP] Gemini 審查未過，停止推送")
        return

    # 3. 推送
    daily_name = DAILY_REPORT.name
    index_name = INDEX_FILE.name
    ok1 = github_push(daily_name)
    ok2 = github_push(index_name)

    if not (ok1 and ok2):
        print("[FAIL] GitHub 推送失敗")
        return

    # 4. Telegram
    daily_url = f"https://b0988321088.github.io/{REPO.split('/')[1]}/{daily_name}?v={TODAY.replace('-','')}"
    index_url = f"https://b0988321088.github.io/{REPO.split('/')[1]}/{index_name}?v={TODAY.replace('-','')}"
    msg = (
        f"龍九控股日報 {TODAY}\n\n"
        f"日報：{daily_url}\n"
        f"靜態儀表板：{index_url}"
    )
    telegram_push(msg)
    print("\n[DONE] 全部流程完成")


if __name__ == "__main__":
    main()