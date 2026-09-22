#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""maintenance.py — 清理維護單一入口（整合 7 支：session_poison_sweep/weekly_system_cleanup/gmail_cleanup/notion_cleanup/weekly_db_maintenance/run_nightly_wrapper）。

  light    高頻清毒（*/10）
  deep     週深清（週一 03:00）
  db       DB 保養（週日 05:00）
  nightly  夜間維護＋VACUUM（22:50）"""
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


def run(target, extra=(), shell_script=False, timeout=900):
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
    if out:
        print(out)
    if err:
        tag = 'stderr' if proc.returncode == 0 else f'失敗 rc={proc.returncode}'
        print(f"⚠️ {target}（{tag}）：" + err.replace(chr(10), ' ')[:300])
    return proc.returncode

DEFAULT_MODE = 'light'
MODES = {'light': [('session_poison_sweep.py', (), False)], 'deep': [('weekly_system_cleanup.py', (), False), ('gmail_cleanup.py', (), False), ('notion_cleanup.py', (), False)], 'db': [('weekly_db_maintenance.sh', (), True)], 'nightly': [('run_nightly_wrapper.py', (), False)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', nargs='?', default=DEFAULT_MODE,
                    help='子命令，預設 %(default)s')
    ap.add_argument('--list', action='store_true', help='列出所有模式與其步驟')
    a = ap.parse_args()
    if a.list:
        for k, steps in MODES.items():
            print(f"  {k:12s} → " + ', '.join(t for t, _e, _s in steps))
        return 0
    steps = MODES.get(a.mode)
    if steps is None:
        print(f"❌ 未知模式 {a.mode!r}（可用：{', '.join(MODES)}）")
        return 2
    failed = [t for t, extra, sh in steps if run(t, extra, sh) != 0]
    if failed:
        print(f"⚠️ 批次內失敗 {len(failed)}/{len(steps)} 項：{', '.join(failed)}")
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
