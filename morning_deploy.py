#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""morning_deploy.py — 龍九晨間產線（no_agent，零 LLM）

取代原 agent cron「龍九晨間自動化」（6f4e4b91262c，13 天 NT$22 ≈ 每月 NT$50）。
工作內容本來就是機械動作：regenerate_report.py 自己會做完整套 —
三源/產出檢查 → CIO 審查 → git commit([cioreviewed]) → push clean-main + main
→ Pages 上線驗證（4 次重試），最後印出所有連結。本腳本只負責：
  1. 跑 regenerate_report.py（cwd = longjiu_system）
  2. 抽出連結（日報／差異分析／儀表板）＋ 檢查/CIO 結果，組成精簡訊息交付
  3. 失敗（rc≠0 或抽不到連結）→ 印錯誤尾段並以非零碼結束（cron 會發錯誤警報）
4. 附 snapshot 資料日與三個頭部數字（確定性讀取，不呼叫 LLM）

用法：python morning_deploy.py            # 正常
      LJ_MORNING_DRY=1 python morning_deploy.py  # 只驗證解析（不跑管線，讀取 fixture）
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
REPORT = BASE / "daily_report_v2_{d}.html"
PAGES = "https://b0988321088.github.io/longjiu-dashboard-2"
LINK_RE = re.compile(r"(📰|📈|🏠|🔄|📊|🚨)\s*([^:：]+)[:：]\s*(https?://\S+)")


def read_stdout() -> tuple[str, int]:
    if os.environ.get("LJ_MORNING_DRY"):
        # 沙箱解析測試：fixture 放在系統 temp（不污染 repo）。無 fixture → 提示如何產生。
        fx = Path(os.environ.get("TEMP", "/tmp")) / "morning_stdout_fixture.txt"
        if not fx.exists():
            print(f"🧪 DRY RUN：找不到 fixture（{fx}）— 先跑一次 "
                  f"LJ_MORNING_CAPTURE=1 python morning_deploy.py 產生")
            return "", 0
        return fx.read_text(encoding="utf-8", errors="replace"), 0
    try:
        r = subprocess.run([sys.executable, str(BASE / "regenerate_report.py")],
                           cwd=str(BASE), capture_output=True, text=True, timeout=1800)
    except Exception as e:
        print(f"⚠️ 晨間產線執行失敗（無法啟動 regenerate_report.py）：{e}")
        sys.exit(2)
    if os.environ.get("LJ_MORNING_CAPTURE"):
        try:
            (Path(os.environ.get("TEMP", "/tmp")) / "morning_stdout_fixture.txt").write_text(
                r.stdout or "", encoding="utf-8")
        except Exception:
            pass
    return (r.stdout or "") + ("\n" + r.stderr if r.stderr else ""), r.returncode


def pick_links(text: str) -> dict:
    links = {}
    for line in text.splitlines():
        m = LINK_RE.search(line)
        if not m:
            continue
        url = m.group(3).strip().rstrip("）)")
        # 防禦：上游若把 Path 清單/物件印成連結（曾發生於緊急應變行），一律丟棄
        if any(bad in url for bad in ("WindowsPath", "[", "]", " ")):
            continue
        links[m.group(1)] = (m.group(2).strip(), url)
    return links


def snapshot_head() -> str:
    try:
        s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        bits = []
        for label, key in (("現金", "cash"),
                           ("保單", "insurance_current_value"),
                           ("配息", "monthly_dividend_total")):
            v = s.get(key)
            if isinstance(v, (int, float)):
                bits.append(f"{label} {v:,.0f}")
        d = s.get("date", "?")
        return f"📌 snapshot 資料日 {d}" + ("（" + "／".join(bits) + "）" if bits else "")
    except Exception:
        return ""


def main() -> None:
    text, rc = read_stdout()
    links = pick_links(text)
    want = [("📰", "日報"), ("📈", "差異分析"), ("🏠", "儀表板")]
    have = [(icon, name, links[icon][1]) for icon, name in want if icon in links]

    if rc != 0 or not have:
        print("⚠️ 晨間產線失敗 — 需人工處理")
        print(f"regenerate_report.py rc={rc}；抓到連結 {len(links)} 個")
        bad = [ln.strip() for ln in text.splitlines() if "❌" in ln][:10]
        if bad:
            print("失敗項：\n" + "\n".join(bad))
        tail = text.strip()[-1000:]
        if tail:
            print("--- 輸出尾段 ---\n" + tail)
        sys.exit(rc if rc != 0 else 1)

    lines = ["✅ 晨間日報已產出並上線" if not os.environ.get("LJ_MORNING_DRY")
             else "🧪 DRY RUN（未實際執行管線）"]
    for icon, name, url in have:
        lines.append(f"{icon} {name}：{url}")
    extra = [f"{links[i][0]}：{links[i][1]}" for i in ("🔄", "📊", "🚨") if i in links]
    if extra:
        lines.append("　" + "｜".join(extra))
    bad = [ln.strip() for ln in text.splitlines() if "❌" in ln]
    lines.append("⛔ 檢查項：" + ("、".join(bad[:5]) if bad else "全部通過（產出檢查＋CIO 審查）"))
    head = snapshot_head()
    if head:
        lines.append(head)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
