#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cost_watch.py — AI 費用/錢包單一入口（整合 6 支：wallet_status/ds_balance_alert/gemini_balance_reminder/ai_cost_watch/fallback_cost_guard/daily_token_account）。

  wallet  餘額＋門檻警示＋儲值連結（09:00）
  digest  日/週流量＋CER 風控＋異常（13:30/18:30）
  guard   備援花費熔斷（21:10）
  close   日結成本帳＋寫帳本（22:30；先收帳本再印日結，兩者同口徑）"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
HERM = Path(os.path.expandvars(r'%LOCALAPPDATA%/hermes/scripts'))


def _resolve(target):
    """回傳 (路徑, 是否來自 hermes/scripts)。優先在 repo 找真身，找不到再找 hermes（hermes 專用腳本）。"""
    p = BASE / target
    if p.exists():
        return p, False
    alt = HERM / target
    if alt.exists():
        return alt, True
    return None, False


def run(target, extra=(), shell_script=False, timeout=900, quiet=False):
    """執行既有腳本，保留其原始邏輯（不重寫）。單項失敗不中斷同批次其他項目。

    審查修正（2026-09-22 第二輪）：
      · cwd 依腳本來源決定：repo 腳本用 repo 根（與原 cron workdir 一致）；
        hermes 專用腳本用它自己所在目錄（避免相對路徑解析與遷移前不同）。
      · 逾時改用 Popen + kill，確保子程序真的被收掉。
      · rc=0 但 stderr 有內容時也印出（否則警告會被靜默吞掉）。
    """
    p, from_herm = _resolve(target)
    if p is None:
        print(f"⚠️ 找不到 {target}（repo 與 hermes/scripts 皆無）→ 跳過（入口仍在，不需改排程）")
        return 1
    cmd = (['bash', str(p)] if shell_script else [sys.executable, str(p)]) + list(extra)
    cwd = str(p.parent) if from_herm else str(BASE)
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True,
                                encoding='utf-8', errors='replace')
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            print(f"⏰ {target} 逾時（{timeout}s）")
            return 1
    except OSError as exc:
        print(f"⚠️ {target} 無法啟動：{exc}")
        return 1
    out = (out or '').strip()
    err = (err or '').strip()
    if out and not (quiet and proc.returncode == 0):
        print(out)
    if err:
        tag = 'stderr' if proc.returncode == 0 else f'失敗 rc={proc.returncode}'
        print(f"⚠️ {target}（{tag}）：" + err.replace(chr(10), ' ')[:300])
    return proc.returncode

DEFAULT_MODE = 'digest'
# 每項＝(檔名, 額外參數, 是否 shell, 成功時是否靜默)；第 4 項讓「只為副作用而跑」的步驟不洗版
# close 內含 ai_cost_watch（帳本 upsert；--json 只為副作用、--no-probe 免一次探測）
# —— 2026-10-01 核准：22:30 日結同時收帳本，23:55 再由 cost_watch_eod.py 收尾（18:30 後的花費當天入帳）
MODES = {'wallet': [('wallet_status.py', (), False, False), ('ds_balance_alert.py', (), False, False), ('gemini_balance_reminder.py', (), False, False)], 'digest': [('ai_cost_watch.py', (), False, False), ('build_cost_report.py', ('--quiet',), False, False)], 'guard': [('fallback_cost_guard.py', (), False, False)], 'close': [('ai_cost_watch.py', ('--json', '--no-probe'), False, True), ('daily_token_account.py', (), False, False)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', nargs='?', default=DEFAULT_MODE,
                    help='子命令，預設 %(default)s')
    ap.add_argument('--list', action='store_true', help='列出所有模式與其步驟')
    a = ap.parse_args()
    if a.list:
        for k, steps in MODES.items():
            print(f"  {k:12s} → " + ', '.join(t for t, _e, _s, _q in steps))
        return 0
    steps = MODES.get(a.mode)
    if steps is None:
        print(f"❌ 未知模式 {a.mode!r}（可用：{', '.join(MODES)}）")
        return 2
    failed = [t for t, extra, sh, quiet in steps if run(t, extra, sh, quiet=quiet) != 0]
    if failed:
        print(f"⚠️ 批次內失敗 {len(failed)}/{len(steps)} 項：{', '.join(failed)}")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
