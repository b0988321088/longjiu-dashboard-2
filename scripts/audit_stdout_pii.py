"""audit_stdout_pii.py — 稽核「某支腳本的 stdout」有沒有吐出敏感格式（PII 遮蔽計畫的盤點工具）

為什麼需要：safe_read.py 只保護「我主動讀檔」這條路徑；龍九管線腳本自己跑出來的 stdout
仍可能帶帳號/身分證/金鑰，而 stdout 正是進 LLM context 的入口。要改哪幾支不能憑感覺，
先用這支工具把「哪支腳本、哪種規則、幾筆」量出來。

用法：
    python scripts/audit_stdout_pii.py <script.py> [-- 參數...]     # 跑腳本並稽核 stdout+stderr
    python scripts/audit_stdout_pii.py --file <任意輸出檔>          # 稽核既有輸出檔
    python scripts/audit_stdout_pii.py <script.py> --dry             # 只印「會跑什麼」，不執行

行為：
    - 一律只印統計與「已遮罩」的短樣本，不印原始內容（避免稽核工具自己把毒物帶進 context）
    - 逾時預設 300 秒；結束碼照原樣回報
    - 只讀 stdout/stderr，不寫任何檔案

注意：這是盤點工具，不是防線。真正要防的是「腳本輸出前就遮罩」——有命中的腳本再由人工
在輸出邊界呼叫 safe_read.sanitize（一次一支、改完做前後比對）。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

LONGJIU = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LONGJIU)
try:
    import safe_read as sr
except ImportError:  # pragma: no cover
    print(f"FATAL: 找不到 safe_read.py（預期在 {LONGJIU}）")
    raise SystemExit(2)

PY = sys.executable


def audit_text(text: str, label: str) -> dict[str, int]:
    _clean, stats = sr.sanitize_with_stats(text)
    stats = dict(stats)
    print(f"  {label}: {stats or '0（乾淨）'}")
    for name in stats:
        # 只印已遮罩的樣本（safe_read 已處理），最多 3 筆
        pat = dict(sr.RULES).get(name)
        if not pat:
            continue
        shown = 0
        for m in pat.finditer(text):
            frag = sr.sanitize(m.group(0))
            print(f"    - {name}: {frag!r}")
            shown += 1
            if shown >= 3:
                break
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("script", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("args", nargs="*", help="傳給腳本的參數（放在 -- 之後）")
    a = ap.parse_args()

    if a.file:
        text = open(a.file, encoding="utf-8", errors="replace").read()
        print(f"稽核輸出檔 {a.file}（{len(text):,} 字元）")
        stats = audit_text(text, "hits")
        print("VERDICT:", "⚠️ 有命中，需要遮蔽" if stats else "✅ 乾淨")
        return 0

    if not a.script:
        print(__doc__)
        return 2
    if not os.path.exists(a.script):
        print(f"file not found: {a.script}")
        return 2

    cmd = [PY, a.script, *a.args]
    print(f"執行: {' '.join(cmd)}  (cwd={LONGJIU}, timeout={a.timeout}s)")
    if a.dry:
        print("DRY-RUN：未執行")
        return 0

    try:
        p = subprocess.run(cmd, cwd=LONGJIU, capture_output=True, text=True, timeout=a.timeout, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(f"⚠️ 逾時（>{a.timeout}s）→ 視為未完成，輸出未稽核")
        return 1
    print(f"結束碼 = {p.returncode}；stdout {len(p.stdout or ''):,} 字元、stderr {len(p.stderr or ''):,} 字元")
    s1 = audit_text(p.stdout or "", "stdout")
    s2 = audit_text(p.stderr or "", "stderr")
    total = sum(s1.values()) + sum(s2.values())
    print("VERDICT:", f"⚠️ 有命中 {total} 筆，需在輸出邊界遮蔽" if total else "✅ 乾淨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
