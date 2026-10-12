# -*- coding: utf-8 -*-
"""tools/verify_pending_integrity.py — 決策卡卡數／卡別追溯驗收（TD-20261009-16 驗收條件④）。

用法：
  python tools/verify_pending_integrity.py --baseline        # 記錄目前卡況為基準（含 sha256）
  python tools/verify_pending_integrity.py --verify          # 與基準比對：任何卡片減少即 rc=2
  python tools/verify_pending_integrity.py --verify --update # 比對後把基準推進到現況（PASS 才推進）
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
import pending_store  # noqa: E402

PEND = BASE / "pending_decisions.json"
ARCH = BASE / "pending_decisions_archive.json"
BASE_FILE = BASE / "data" / "pending_integrity_baseline.json"


def _digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def collect() -> dict:
    out = {"files": {}}
    for p in (PEND, ARCH):
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        out["files"][p.name] = {"sha256": _digest(p), "count": len(pending_store.card_keys(data)),
                                "keys": pending_store.card_keys(data)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", action="store_true", help="寫入基準")
    ap.add_argument("--verify", action="store_true", help="與基準比對")
    ap.add_argument("--update", action="store_true", help="比對通過後推進基準")
    a = ap.parse_args()
    cur = collect()
    if a.baseline or not BASE_FILE.exists():
        BASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASE_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✅ 已建立基準：{BASE_FILE}")
        for n, v in cur["files"].items():
            print(f"   {n}：{v['count']} 張｜sha256 {v['sha256'][:16]}")
        return 0
    base = json.loads(BASE_FILE.read_text(encoding="utf-8"))
    rc = 0
    for name, b in base["files"].items():
        c = cur["files"].get(name)
        if c is None:
            print(f"❌ {name} 不存在（基準有、現況無）"); rc = 2; continue
        d = pending_store.diff_keys(b["keys"], c["keys"])
        tag = "✅" if not d["removed"] else "❌"
        print(f"{tag} {name}：{d['count_before']} → {d['count_after']}"
              f"｜新增 {len(d['added'])}｜移除 {len(d['removed'])}")
        for k in d["removed"]:
            print(f"     ⚠️ 移除卡片：{k}")
        for k in d["added"]:
            print(f"     ＋新增：{k}")
        if d["removed"]:
            rc = 2
    if a.update:
        if rc == 0:
            BASE_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), encoding="utf-8")
            print("✅ 基準已推進")
        else:
            print("⛔ 有卡片移除，拒絕推進基準")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
