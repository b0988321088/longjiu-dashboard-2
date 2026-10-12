# -*- coding: utf-8 -*-
"""tests/_lock_worker.py — 併發測試用的獨立程序（讀-改-寫 pending_decisions.json）。

用法：python tests/_lock_worker.py <file> <card_title> [--sleep S] [--nolock] [--hold S]
  --nolock  模擬修復前的 legacy 直寫（無鎖、非原子），用於負向對照
  --hold S  取鎖後持續持有 S 秒（測逾時）
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def main() -> int:
    args = [a for a in sys.argv[1:]]
    path = Path(args[0]); title = args[1]
    sleep = float(args[args.index("--sleep") + 1]) if "--sleep" in args else 0.0
    hold = float(args[args.index("--hold") + 1]) if "--hold" in args else 0.0
    nolock = "--nolock" in args
    lock_path = Path(args[args.index("--lock") + 1]) if "--lock" in args else None
    import pending_store

    def body():
        data = json.loads(path.read_text(encoding="utf-8"))
        time.sleep(sleep)                     # 放大競態窗口
        data.append({"title": title, "status": "待處理"})
        if nolock:                            # legacy 路徑：裸寫、無鎖
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            pending_store.atomic_write_json(path, data, indent=2)

    if nolock:
        body()
    else:
        with pending_store.locked(timeout=20, path=lock_path):
            body()
            if hold:
                time.sleep(hold)
    print(f"ok {title}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
