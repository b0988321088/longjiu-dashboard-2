#!/usr/bin/env python3
"""技術債登錄工具（2026-10-11 建立）

背景：工程／治理類待辦（守門、閘門、驗證器、寫死、發布機制、文件一致性…）原本被
登錄進 pending_decisions.json，導致「執行中決策追蹤」膨脹（10/09 +22、10/11 +16，
87 筆中約 76% 非資產決策）。本檔為這些項目的唯一去處：**決策歸決策、工程債歸工程債**。
儀表板於「系統工作日誌」卡下方獨立呈現本清單（讀 tech_debt.json）。

用法：
  python tech_debt.py list [--open] [--severity P0]
  python tech_debt.py add --title "..." [--severity P1] [--source "CIO required_fixes"]
                        [--detail "..."] [--due 2026-10-20] [--tags "閘門,驗證器"]
  python tech_debt.py close --id TD-20261011-03 --evidence "commit abc123"
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
PATH = BASE / "tech_debt.json"
OPEN_STATES = ("開放", "暫緩")


def load() -> list:
    if not PATH.exists():
        return []
    try:
        d = json.loads(PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def save(items: list) -> None:
    PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def next_id(items: list, day: str) -> str:
    pre = f"TD-{day.replace('-', '')}-"
    n = 0
    for it in items:
        _id = str(it.get("id", ""))
        if _id.startswith(pre):
            try:
                n = max(n, int(_id[len(pre):]))
            except ValueError:
                pass
    return f"{pre}{n + 1:02d}"


def cmd_list(a) -> int:
    items = load()
    if a.open:
        items = [x for x in items if str(x.get("status", "")) in OPEN_STATES]
    if a.severity:
        items = [x for x in items if str(x.get("severity", "")).upper() == a.severity.upper()]
    items.sort(key=lambda x: (str(x.get("severity", "NA")), str(x.get("date", ""))))
    sev = {}
    for x in load():
        k = str(x.get("severity", "NA"))
        sev[k] = sev.get(k, 0) + 1
    print(f"🔧 技術債：{len(load())} 筆（P0 {sev.get('P0', 0)}／P1 {sev.get('P1', 0)}／"
          f"P2 {sev.get('P2', 0)}／未分級 {sev.get('NA', 0)}）")
    for x in items:
        print(f"  [{x.get('severity', 'NA'):>2}] {x.get('id', ''):<18} {str(x.get('date', ''))[:10]} "
              f"{str(x.get('status', ''))[:6]} | {str(x.get('title', ''))[:78]}")
    return 0


def cmd_add(a) -> int:
    items = load()
    today = date.today().isoformat()
    entry = {
        "id": next_id(items, today),
        "date": today,
        "title": a.title,
        "severity": (a.severity or "NA").upper(),
        "source": a.source or "施工自我發現",
        "status": "開放",
        "status_raw": "",
        "detail": a.detail or "",
        "tags": a.tags or "",
        "due_date": a.due or "",
        "owner": a.owner or "龍九",
        "moved_from": "",
        "moved_at": today,
        "cleanup_reason": "",
    }
    items.append(entry)
    save(items)
    print(f"✅ 已登錄 {entry['id']}｜{entry['severity']}｜{entry['title'][:60]}")
    return 0


def cmd_close(a) -> int:
    items = load()
    hit = [x for x in items if str(x.get("id", "")) == a.id]
    if not hit:
        print(f"❌ 找不到 id={a.id}", file=sys.stderr)
        return 1
    it = hit[0]
    it["status"] = "已結案"
    it["status_raw"] = f"✅ 已結案({date.today().isoformat()})：{a.evidence or ''}"
    it["cleanup_reason"] = f"tech_debt close：{a.evidence or ''}"
    it["updated_at"] = date.today().isoformat()
    save(items)
    print(f"✅ 已結案 {a.id}｜{it['title'][:60]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="技術債登錄工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出技術債")
    p.add_argument("--open", action="store_true", help="只看開放／暫緩")
    p.add_argument("--severity", help="只列指定等級（P0/P1/P2/NA）")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="登錄技術債")
    p.add_argument("--title", required=True)
    p.add_argument("--severity", default="NA")
    p.add_argument("--source", default="")
    p.add_argument("--detail", default="")
    p.add_argument("--due", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--owner", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("close", help="結案技術債")
    p.add_argument("--id", required=True)
    p.add_argument("--evidence", default="")
    p.set_defaults(func=cmd_close)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
