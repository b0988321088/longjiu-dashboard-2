#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_link_publish_gate.py — 正式報表「已連結但未入庫」閘門回歸測試（2026-10-22）

背景（三次實案，同一型）：
  10/12、10/16、10/21 的 21:30 美股緊急應變報告都成功產出、也被 index.html 連結，
  但沒進 git → Pages 按鈕 404。而收尾稽核把所有未追蹤檔一律印成「備份/暫存，預期」，
  check_dashboard_sync 的 PREPUSH 豁免又把跨日未入庫的檔降成 ℹ️ → 漏登無人攔。

本測試鎖住兩條新規則（皆以 AST 從「真碼」抽函式執行，不複製一份邏輯）：
  G1  classify_linked_artifacts()（_audit_closeout.py）
      · 被 index.html 連結且不在版控 → reports（呼叫端列 fail）
      · 被連結但本機不存在 → missing（呼叫端列 fail）
      · 未連結的暫存/備份/快取 → temp（只印 ℹ️，不誤擋）
      · .gitignore 忽略的連結檔同樣抓得到（不靠 untracked 清單）
  G2  _is_pending_this_commit()（check_dashboard_sync.py）
      · 只有「今天產生」的檔能拿到 PREPUSH 豁免（ℹ️ 待本次 commit）
      · 跨日仍未入庫 → 不給豁免 → FAIL

執行：python -X utf8 tools/test_link_publish_gate.py      （全過 rc=0，任一失敗 rc=1）
"""
from __future__ import annotations

import ast
import datetime
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = 0
FAIL = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def extract_func(path: Path, name: str, ns: dict):
    """從真碼抽出單一頂層函式編譯執行（不執行 module 其他 top-level 副作用）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), ns)
            return ns[name]
    raise AssertionError(f"{path.name} 找不到函式 {name}（被改名或刪除 → 閘門失效）")


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} 失敗: {r.stderr.strip()}")
    return r.stdout


def mk_repo(tmp: Path) -> None:
    git(tmp, "init", "-q")
    git(tmp, "config", "user.email", "gate@test.local")
    git(tmp, "config", "user.name", "gate-test")
    git(tmp, "config", "core.autocrlf", "false")


def tracked_of(repo: Path) -> list:
    return [x for x in git(repo, "ls-files").splitlines() if x]


def untracked_of(repo: Path) -> list:
    """與 _audit_closeout.py 同一指令（逐檔展開，不受 directory folding 影響）。"""
    return [x for x in git(repo, "ls-files", "--others", "--exclude-standard").splitlines() if x]


def set_mtime(p: Path, when: datetime.date) -> None:
    ts = time.mktime(datetime.datetime(when.year, when.month, when.day, 21, 30).timetuple())
    os.utime(p, (ts, ts))


def main() -> int:
    print("=" * 62)
    print("連結發布閘門回歸測試（G1 closeout 分類 / G2 PREPUSH 豁免）")
    print("=" * 62)

    classify = extract_func(ROOT / "_audit_closeout.py", "classify_linked_artifacts",
                            {"Path": Path})
    pending = extract_func(ROOT / "check_dashboard_sync.py", "_is_pending_this_commit",
                           {"datetime": datetime})
    # collect_link_issues 內部呼叫 classify_linked_artifacts → 需一併注入（同一份真碼抽出的函式）
    collect = extract_func(ROOT / "_audit_closeout.py", "collect_link_issues",
                           {"Path": Path, "classify_linked_artifacts": classify})

    today = datetime.date(2026, 10, 22)

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        mk_repo(repo)

        # 基準：一個已入庫的正式報表 + 一個暫存檔 + 一個子目錄產物
        (repo / "index.html").write_text(
            '<a href="emergency_report_2026-10-21.html">10/21</a>'
            '<a href="daily_report_v2_2026-10-22.html">日報</a>'
            '<a href="missing_report_2026-10-23.html">未產出</a>'
            '<a href="ignored_report_2026-10-22.html">被忽略</a>'
            '<a href="./daily_report_v2_2026-10-22.html">相對前綴</a>'
            '<a href="daily_report_v2_2026-10-22.html?t=123">query</a>'
            '<a href="site/">目錄</a>'
            '<a href="https://example.com/x.html">外部</a>'
            '<a href="#top">錨點</a>', encoding="utf-8")
        (repo / "daily_report_v2_2026-10-22.html").write_text("<html>ok</html>", encoding="utf-8")
        (repo / "backup_20261022.json").write_text("{}", encoding="utf-8")
        (repo / "site").mkdir()
        (repo / "site" / "x.html").write_text("<html>site</html>", encoding="utf-8")
        (repo / ".gitignore").write_text("ignored_report_*.html\n", encoding="utf-8")
        # 被 .gitignore 排除的正式報表（存在、但 push 帶不上去）：baseline 就存在
        (repo / "ignored_report_2026-10-22.html").write_text("<html>被忽略</html>", encoding="utf-8")
        git(repo, "add", "index.html", "daily_report_v2_2026-10-22.html", ".gitignore")
        git(repo, "commit", "-q", "-m", "baseline")

        linked = {"emergency_report_2026-10-21.html", "daily_report_v2_2026-10-22.html",
                  "missing_report_2026-10-23.html", "ignored_report_2026-10-22.html",
                  "./daily_report_v2_2026-10-22.html",
                  "daily_report_v2_2026-10-22.html?t=123", "site/",
                  "https://example.com/x.html", "#top"}

        def run_classify():
            return classify(linked, tracked_of(repo), untracked_of(repo), repo)

        # ── G1-C1 正式報表存在且已入庫 → 通過 ──────────────────
        rep, temp, miss = run_classify()
        check("C1 已入庫的正式報表不算漏登", "daily_report_v2_2026-10-22.html" not in rep,
              f"reports={rep}")

        # ── G1-C2 被連結但未入庫（10/21 實案）→ 必須列 reports ──
        ev = repo / "emergency_report_2026-10-21.html"
        ev.write_text("<html>應變</html>", encoding="utf-8")
        set_mtime(ev, datetime.date(2026, 10, 21))
        rep, temp, miss = run_classify()
        check("C2 被連結卻未入庫 → 列 fail 清單（10/21 實案）",
              "emergency_report_2026-10-21.html" in rep, f"reports={rep}")
        check("C2b 該檔不得落進『暫存不阻擋』清單", "emergency_report_2026-10-21.html" not in temp,
              f"temp={temp}")

        # ── G1-C3 暫存/備份/快取未連結 → 不誤擋 ─────────────────
        check("C3 未連結的備份檔不阻擋",
              "backup_20261022.json" in temp and "backup_20261022.json" not in rep,
              f"temp={temp} reports={rep}")
        check("C3b 未連結的子目錄產物不誤判為正式報表",
              "site/x.html" in temp, f"temp={temp}")

        # ── G1-C4 連結目標本機不存在 → missing ──────────────────
        check("C4 連結目標不存在 → 列 missing（狀態不一致）",
              miss == ["missing_report_2026-10-23.html"], f"missing={miss}")
        check("C4b 外部連結／錨點不參與本機檔案檢查",
              not any(u.startswith(("http", "#")) for u in miss), f"missing={miss}")

        # ── G1-C10 連結寫法正規化（./、query、目錄）─────────────
        rep, temp, miss = run_classify()
        check("C10 './x.html' 與 x.html 視為同一檔（已入庫不誤報）",
              "./daily_report_v2_2026-10-22.html" not in rep, f"reports={rep}")
        check("C10b 帶 query 的連結正規化後不誤判為漏產",
              not any("?" in u for u in miss), f"missing={miss}")
        check("C10c 目錄連結不算交付物（不列 missing／reports）",
              "site/" not in miss and "site" not in miss, f"missing={miss}")

        # ── G1-C5 被 .gitignore 忽略的連結檔 → 仍必須抓到 ────────
        # （舊寫法只比 untracked 清單，ignored 檔不會出現 → 靜默漏）
        ig = repo / "ignored_report_2026-10-22.html"
        rep, temp, miss = run_classify()
        check("C5 .gitignore 忽略的連結檔仍列 fail", "ignored_report_2026-10-22.html" in rep,
              f"reports={rep}")
        check("C5b 該檔不在 untracked 清單（證明不能只靠 untracked 判定）",
              "ignored_report_2026-10-22.html" not in untracked_of(repo),
              "ignored 檔竟出現在 --exclude-standard 清單")

        # ── G3 行為級：closeout 真的會把漏登變成 fail（不是 grep 原始碼片段）──
        issues, lines = collect(linked, tracked_of(repo), untracked_of(repo), repo)
        check("H1 10/21 漏登 → closeout 產生 fail 條目",
              any("正式報表未入庫" in i and "emergency_report_2026-10-21.html" in i for i in issues),
              f"issues={issues}")
        check("H2 連結目標不存在 → closeout 產生 fail 條目",
              any("連結目標不存在" in i and "missing_report_2026-10-23.html" in i for i in issues),
              f"issues={issues}")
        check("H3 暫存/備份只報數量、不逐檔洗版、不成為 fail",
              any("未追蹤暫存/備份" in l for l in lines)
              and not any("backup_20261022.json" in i for i in issues), f"lines={lines}")

        # ── G1-C6 入庫後即恢復通過（修復回歸）──────────────────
        git(repo, "add", "emergency_report_2026-10-21.html")
        git(repo, "commit", "-q", "-m", "補登 10/21")
        rep, temp, miss = run_classify()
        check("C6 補登入庫後該檔從 reports 消失",
              "emergency_report_2026-10-21.html" not in rep, f"reports={rep}")
        issues2, _ = collect(linked, tracked_of(repo), untracked_of(repo), repo)
        check("H4 補登後 closeout 不再把 emergency 列為未入庫",
              not any("emergency_report_2026-10-21.html" in i for i in issues2),
              f"issues={issues2}")

        # ── G2-C7 PREPUSH + 今天產生的檔 → 豁免（ℹ️）────────────
        fresh = repo / "daily_report_v2_2026-10-22.html"
        set_mtime(fresh, today)
        check("C7 今天產生的連結檔 → 取得 PREPUSH 豁免", pending(fresh, today) is True)

        # ── G2-C11 日期判準走本地時區（台北 UTC+8）邊界 ──────────
        def _mt(dt):
            ts = time.mktime(dt.timetuple())
            os.utime(fresh, (ts, ts))

        _mt(datetime.datetime(2026, 10, 22, 0, 1))
        check("C11 當日 00:01 → 取得豁免（不誤擋）", pending(fresh, today) is True)
        _mt(datetime.datetime(2026, 10, 22, 23, 59))
        check("C11b 當日 23:59 → 取得豁免", pending(fresh, today) is True)
        _mt(datetime.datetime(2026, 10, 21, 23, 59))
        check("C11c 昨日 23:59 → 不給豁免（跨日即阻擋）", pending(fresh, today) is False)

        # ── G2-C8 跨日仍未入庫 → 不給豁免（三次實案）────────────
        for ev_day in ("2026-10-12", "2026-10-16", "2026-10-21"):
            p = repo / f"emergency_report_{ev_day}.html"
            p.write_text("<html>應變</html>", encoding="utf-8")
            set_mtime(p, datetime.date.fromisoformat(ev_day))
            check(f"C8 跨日漏登不給豁免（{ev_day} 實案）",
                  pending(p, today) is False, f"{ev_day} 被判為待本次 commit")
        check("C8b 昨日產出、今日檢查 → FAIL 判準",
              pending(repo / "emergency_report_2026-10-21.html", today) is False)
        check("C8c 同一檔在當天（10/21）檢查 → 仍屬待本次 commit",
              pending(repo / "emergency_report_2026-10-21.html", datetime.date(2026, 10, 21)) is True)

        # ── G2-C9 檔案不存在 → 不給豁免（由『本機不存在』分支負責 FAIL）──
        check("C9 檔案不存在 → 不給豁免", pending(repo / "not_there.html", today) is False)

    # ── G0 結構守門：兩支真碼仍提供這些函式（改名/刪除即測試失敗）──
    check("G0a _audit_closeout.py 仍提供 classify_linked_artifacts", callable(classify))
    check("G0b check_dashboard_sync.py 仍提供 _is_pending_this_commit", callable(pending))
    _cds = (ROOT / "check_dashboard_sync.py").read_text(encoding="utf-8")
    _close = (ROOT / "_audit_closeout.py").read_text(encoding="utf-8")
    check("G0c check_dashboard_sync 已接上跨日 FAIL 分支", "跨日仍未進版控" in _cds)
    check("G0d _audit_closeout 已把 link issues 併入 fail（不是只印訊息）",
          "fail.extend(_link_issues)" in _close)
    check("G0e _audit_closeout 以 tracked 全集判定（涵蓋 ignored）",
          "classify_linked_artifacts(" in _close and "_tracked_all" in _close)
    check("G0f collect_link_issues 為可呼叫行為（非字串守門）", callable(collect))

    print("-" * 62)
    print(f"結果：PASS {PASS}／FAIL {FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
