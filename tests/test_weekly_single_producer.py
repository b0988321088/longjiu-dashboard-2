# -*- coding: utf-8 -*-
"""tests/test_weekly_single_producer.py — TD-20261009-12（P0）：週報只能有一個 producer。

事故型態（實測）：legacy weekly_report.py（4 章節、2.5KB）與 build_weekly_report.py
（12 章節、17.5KB）寫同一路徑 weekly_report_{date}.html；週日 19:00 排程跑的是 legacy
→ 把正式版覆蓋掉（修正字串消失）。根治＝單一 producer。

驗收（TD-20261009-12）：①排程實際入口為單一 producer ②輸出路徑全庫唯一
③排程跑完後修正字串仍在 ④重跑 legacy 不再覆蓋（或 legacy 已不存在）
"""
import json
import re
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
EXCLUDE = re.compile(r"(\.archive|backups|__pycache__|_bak_|\.bak|/tests/|node_modules)")
_ok = _fail = 0
FAILS = []


def ck(name, cond, detail=""):
    global _ok, _fail
    if cond:
        _ok += 1; print(f"  ✅ {name}")
    else:
        _fail += 1; FAILS.append(name); print(f"  ❌ {name} {detail}")


def repo_files(suffix=".py"):
    for p in BASE.rglob(f"*{suffix}"):
        rel = str(p).replace("\\", "/")
        if EXCLUDE.search(rel) or rel.endswith(str(BASE).replace("\\", "/") + "/tests"):
            continue
        yield p


def main() -> int:
    print("=== 週報單一 producer 驗收（TD-20261009-12）===")

    # ② 輸出路徑全庫唯一
    writers = []
    for p in repo_files():
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in re.finditer(r"weekly_report_\{?\w*\}?\.html", src):
            if re.search(r"open\(|write_text|write_bytes|json\.dump|out\s*=\s*REPO\s*/", src):
                writers.append(p.name)
                break
    ck("② 全庫僅一個週報寫入者", set(writers) == {"build_weekly_report.py"}, f"writers={sorted(set(writers))}")

    # ④ legacy 已不存在（工作樹與 HEAD）
    ck("④ legacy weekly_report.py 不存在於工作樹", not (BASE / "weekly_report.py").exists())
    g = subprocess.run(["git", "ls-files", "weekly_report.py"], cwd=BASE, capture_output=True, text=True)
    ck("④ legacy 不在版控（HEAD）", not g.stdout.strip(), g.stdout.strip())

    # ① 排程入口＝新版（cron 不得再呼叫 legacy）
    jobs = json.loads((Path.home() / "AppData/Local/hermes/cron/jobs.json").read_text(encoding="utf-8"))
    jl = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    blob = json.dumps(jl, ensure_ascii=False)
    ck("① cron 無 `python weekly_report.py`", not re.search(r"python\s+weekly_report\.py", blob))
    ck("① cron 指向 build_weekly_report.py", "build_weekly_report.py" in blob)
    weekly_jobs = [j for j in jl if "週報" in json.dumps(j, ensure_ascii=False) and j.get("enabled")]
    ck("① 週報排程存在且啟用", bool(weekly_jobs), str([j.get("id", "")[:12] for j in weekly_jobs]))

    # ③ 產物層驗收（以最新產物為準；legacy 版本特徵＝4 章節／約 2.5KB）
    outs = sorted(BASE.glob("weekly_report_*.html"), key=lambda x: x.stat().st_mtime, reverse=True)
    if outs:
        h = outs[0].read_text(encoding="utf-8", errors="replace")
        n_ch = len(re.findall(r"<h2", h))
        ck(f"③ 最新產物為 12 章節版（{outs[0].name}｜{len(h)} bytes）", len(h) > 8000 and n_ch >= 8,
           f"h2={n_ch}")
        ck("③ 產物含修正字串「月租金」", "月租金" in h, "缺 月租金")
        ck("③ 產物不含 legacy 特徵（4 章節／<3KB）", not (len(h) < 3000), f"{len(h)} bytes")
    else:
        ck("已有週報產物可檢查", False, "找不到 weekly_report_*.html")

    print(f"\n== 結果：{_ok} PASS / {_fail} FAIL ==")
    if FAILS:
        print("FAIL 清單:", FAILS)
    return 0 if _fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
