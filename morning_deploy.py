#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""morning_deploy.py — 龍九晨間產線（no_agent，零 LLM）

取代原 agent cron「龍九晨間自動化」（6f4e4b91262c，13 天 NT$22 ≈ 每月 NT$50）。
工作內容本來就是機械動作：regenerate_report.py 自己會做完整套 —
三源/產出檢查 → CIO 審查 → 落 RECORD（auto_record）→ push clean-main + main
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
from datetime import datetime
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"
REPORT = BASE / "daily_report_v2_{d}.html"
PAGES = "https://b0988321088.github.io/longjiu-dashboard-2"
LINK_RE = re.compile(r"(📰|📈|🏠|🔄|📊|🚨)\s*([^:：]+)[:：]\s*(https?://\S+)")
LOG_DIR = BASE / "logs"
# 2026-10-20（使用者核准）：失敗摘要優先結構化擷取。matplotlib 字型警告會把尾段淹掉，
# 過去 10/16–10/19 三次失敗因此只回報「rc=1」而看不到真因（⛔ 行不在 ❌ 掃描範圍）。
NOISE = ("UserWarning", "missing from font", "Glyph ", "plt.tight_layout",
         "fig.savefig", "warnings.warn", "tight_layout(")
ERROR_KEYS = ("❌", "⛔", "Traceback", "Exception", "未推送上線", "已跳過 commit",
              "fail-closed", "REJECT")


def write_full_log(text: str) -> Path | None:
    """完整 stdout+stderr 落地；失敗時訊息只需指路，不必再塞尾段。"""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        p = LOG_DIR / f"morning_{datetime.now():%Y%m%d}.log"
        p.write_text(text or "", encoding="utf-8")
        return p
    except Exception:
        return None


def diagnose(text: str, limit: int = 12) -> tuple[list[str], list[str]]:
    """擷取錯誤行（含緊接的 '  - ' 詳情）與 gate 段；雜訊行先濾除。"""
    keep: list[str] = []
    collecting = False
    for ln in (text or "").splitlines():
        if any(n in ln for n in NOISE):
            continue
        s = ln.strip()
        if any(k in ln for k in ERROR_KEYS):
            if len(keep) < limit:
                keep.append(s)
            collecting = True
        elif collecting and s.startswith("- "):
            if len(keep) < limit:
                keep[-1] = keep[-1] + " " + s
        else:
            collecting = False
    gate = [ln.strip() for ln in (text or "").splitlines()
            if any(k in ln for k in ("閘門模式", "F1 ", "F2 ", "F3 ", "F4 ", "FAIL ", "分類："))
            and not any(k in ln for k in ("❌", "⛔"))][:8]
    return keep[:limit], gate



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

    if rc in (12, 13):
        # F1 第三階段（2026-10-21 使用者裁決）：rc 12/13 只在「日報已產出並上線、僅應變段需人工」
        # 時出現，不得報成「產線失敗」（會掩蓋已上線事實、誘使重跑）。退出碼保留，cron 仍會告警；
        # 但 12/13 不列入自動重試（Hermes cron 本就不重試，僅記 error＋發一次警報）。
        _label = ("應變段驗證失敗，未注入（H12）" if rc == 12
                  else "應變功能關閉卻有當日資料，未注入（H13）")
        print(f"⚠️ 晨間日報已上線 — {_label}；rc={rc}，需人工處理")
        for _icon, _name, _url in have:
            print(f"{_icon} {_name}：{_url}")
        _bad, _gate = diagnose(text)
        _log = write_full_log(text)
        if _bad:
            print("應變段：\n" + "\n".join(_bad))
        else:
            print("應變段：（未擷取到錯誤行，完整輸出見日誌）")
        if _gate:
            print("閘門段：\n" + "\n".join("  " + g for g in _gate))
        print(f"📄 完整日誌：{_log}" if _log else "📄 完整日誌：寫入失敗（logs/ 不可寫）")
        sys.exit(rc)

    if rc != 0 or not have:
        print("⚠️ 晨間產線失敗 — 需人工處理")
        print(f"regenerate_report.py rc={rc}；抓到連結 {len(links)} 個")
        _bad, _gate = diagnose(text)
        _log = write_full_log(text)
        if _bad:
            print("失敗項：\n" + "\n".join(_bad))
        else:
            print("失敗項：（未擷取到錯誤行，完整輸出見下方日誌路徑）")
        if _gate:
            print("閘門段：\n" + "\n".join("  " + g for g in _gate))
        print(f"📄 完整日誌：{_log}" if _log else "📄 完整日誌：寫入失敗（logs/ 不可寫）")
        if not _bad:
            # fallback：只有在完全擷取不到錯誤行時才回到舊行為
            tail = text.strip()[-1000:]
            if tail:
                print("--- 輸出尾段（fallback） ---\n" + tail)
        sys.exit(rc if rc != 0 else 1)

    lines = ["✅ 晨間日報已產出並上線" if not os.environ.get("LJ_MORNING_DRY")
             else "🧪 DRY RUN（未實際執行管線）"]
    for icon, name, url in have:
        lines.append(f"{icon} {name}：{url}")
    # 2026-09-29（使用者回報）：原本把 🔄／📊／🚨 三個連結用「｜」串成同一行，
    # Telegram 上一條長行裡兩個網址看起來黏在一起（再平衡儀表板｜穿透分析｜緊急應變），
    # 手指也容易點錯。改為一行一個連結（訊息多 2~3 行，換取可辨識與可點擊）。
    for _icon in ("🔄", "📊", "🚨"):
        if _icon in links:
            _label, _url = links[_icon]
            lines.append(f"{_icon} {_label}：{_url}")
    # 2026-09-23（INC-240）：原本只挑含 ❌ 的行 → 詳情行（"  - …"）被丟掉，訊息只剩光禿禿
    # 一句「❌ 儀表板同步檢查失敗:」看不出原因（真因藏在下一行）。改為 ❌ 行＋緊接的詳情行一起收。
    bad, _collect = [], False
    for _ln in text.splitlines():
        _s = _ln.strip()
        if "❌" in _ln:
            bad.append(_s)
            _collect = True
        elif _collect and _s.startswith("- "):
            if bad and len(bad[-1]) + len(_s) <= 300:
                bad[-1] += " " + _s
        else:
            _collect = False
    lines.append("⛔ 檢查項：" + ("；".join(bad[:5]) if bad else "全部通過（產出檢查＋CIO 審查）"))
    head = snapshot_head()
    if head:
        lines.append(head)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
