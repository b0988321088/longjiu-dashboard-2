# -*- coding: utf-8 -*-
"""publish_gate 隔離測試（PG-20261011 v2：白名單 + 實際變更集合）

全程在 tempfile 建立的臨時 git repo 內執行，不碰正式 repo、不推送。
覆蓋：正向、負向、邊界、多重錯誤並存、R7 冒充、白名單完整性。

執行：python -X utf8 tests/test_publish_gate.py
"""
from __future__ import annotations

import importlib.util as _u
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = _u.spec_from_file_location("pg", REPO / "publish_gate.py")
pg = _u.module_from_spec(_spec)
_spec.loader.exec_module(pg)

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f" ｜{detail}" if detail and not cond else ""))


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=60)
    return r.stdout.strip() if r.returncode == 0 else ""


ALLOW_COST = {"version": 1, "entries": [
    {"label": "AI 成本帳", "allow": ["cost.html", "cost_data.json", "data/ai_cost_daily.jsonl"]}]}


def make_repo(files: dict, allowlist: dict | None = ALLOW_COST, reviewer: str = "AUTO-checker:demo.py",
              verdict: str = "APPROVE", tree_override: str | None = None, approvals: bool = True,
              per_commit_reviewer: dict | None = None) -> tuple[Path, str, str]:
    """先建 base commit（含白名單），再建產物 commit。回傳 (repo, head, 'HEAD^' 之基準)。"""
    repo = Path(tempfile.mkdtemp(prefix="pgtest_"))
    for a in (["init", "-q"], ["config", "user.email", "t@example.com"],
              ["config", "user.name", "tester"], ["config", "core.autocrlf", "false"]):
        _git(repo, *a)
    if allowlist is not None:
        (repo / "publish_allowlist.json").write_text(
            json.dumps(allowlist, ensure_ascii=False, indent=1), encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    for rel, content in files.items():
        fp = repo / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "produce")
    head = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    if approvals:
        (repo / ".git" / "CIO_APPROVED").write_text(
            f"2026-10-11T00:00:00Z\t{tree_override or tree}\t{head}\t{verdict}\t{reviewer}\tnote\n",
            encoding="utf-8")
    return repo, head, "HEAD^"


# ------------------------------------------------------------------ 正向

def s_positive() -> None:
    print("\n【正向】")
    r = pg.decide(*(lambda t: (t[0], t[2]))(make_repo({"cost.html": "a", "cost_data.json": "{}"})), allowlist_ref="HEAD^")
    check("P1 變更⊆白名單＋AUTO 紀錄→可發布", r["ok"] and r["mode"] == "AUTO", str(r.get("blockings"))[:200])
    check("P1b 命中條目正確", r["allow_entry"] == "AI 成本帳", str(r["allow_entry"]))
    repo, head, base = make_repo({"cost.html": "a"}, reviewer="CIO-Gemini")
    r2 = pg.decide(repo, base, None, allowlist_ref=base)
    check("P2 變更⊆白名單＋真 CIO 紀錄→可發布（CIO 更嚴格，允許）", r2["ok"], str(r2.get("blockings"))[:200])
    # 完整三檔
    repo3, head3, base3 = make_repo({"cost.html": "a", "cost_data.json": "{}",
                                     "data/ai_cost_daily.jsonl": "{}\n"})
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("P3 白名單完整三檔→可發布", r3["ok"], str(r3.get("blockings"))[:200])


# ------------------------------------------------------------------ 負向

def s_not_allowlisted() -> None:
    print("\n【負向：未命中白名單】")
    repo, head, base = make_repo({"index.html": "<html>"})
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("N1 未命中白名單＋僅 AUTO 蓋章→拒", not r["ok"])
    check("N1b blocking=CIO_REQUIRED", any(b["id"] == "CIO_REQUIRED" for b in r["blockings"]),
          str([b["id"] for b in r["blockings"]]))
    repo2, head2, base2 = make_repo({"index.html": "<html>"}, reviewer="CIO-Gemini")
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("N2 未命中白名單＋真 CIO 蓋章→可發布（走 CIO 是允許的）", r2["ok"], str(r2.get("blockings"))[:200])


def s_special_forbidden() -> None:
    print("\n【負向：特殊類別一律強制真 CIO】")
    cases = {
        "reviews/x_cio_result.json": "審查結果檔",
        "pending_decisions.json": "治理紀錄",
        "work_log.json": "治理紀錄",
        "error_register.md": "治理紀錄",
        "old_snapshot.json.bak": "備份檔",
        "helper.py": "程式檔",
        "logs/pipeline_llm_usage.jsonl": "logs/ 前綴",
        "publish_allowlist.json": "白名單自身",
        ".githooks/pre-push": "hook",
    }
    for path, label in cases.items():
        repo, head, base = make_repo({path: "x"})
        r = pg.decide(repo, base, None, allowlist_ref=base)
        check(f"F-{label}（{path}）→ 拒", not r["ok"], str([b["id"] for b in r["blockings"]]))
        check(f"F-{label}b 判定為 CIO 模式", r["mode"] == "CIO")


def s_record_problems() -> None:
    print("\n【負向：核准紀錄】")
    repo, head, base = make_repo({"cost.html": "a"}, tree_override="0" * 40)
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("R1 tree 不符→拒（舊核准不得重用）", not r["ok"])
    repo2, head2, base2 = make_repo({"cost.html": "a"}, approvals=False)
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("R2 無紀錄→拒", not r2["ok"])
    repo3, head3, base3 = make_repo({"cost.html": "a"}, verdict="REJECT")
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("R3 verdict=REJECT→拒", not r3["ok"])


def s_allowlist_integrity() -> None:
    print("\n【負向：白名單完整性】")
    repo, head, base = make_repo({"cost.html": "a"}, allowlist=None)
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("A1 白名單不存在→拒", not r["ok"])
    check("A1b blocking=ALLOWLIST_UNAVAILABLE",
          any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r["blockings"]))
    # 格式錯誤
    repo2, head2, base2 = make_repo({"cost.html": "a"}, allowlist={"version": 1})
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("A2 白名單缺 entries→拒", not r2["ok"])
    repo3, head3, base3 = make_repo({"cost.html": "a"},
                                    allowlist={"version": 1, "entries": [{"label": "x", "allow": []}]})
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("A3 條目空 allow→拒", not r3["ok"])
    # 工作區改寫無效（讀 HEAD 版本）
    repo4, head4, base4 = make_repo({"cost.html": "a"})
    wide = {"version": 1, "entries": [{"label": "wide", "allow": ["cost.html", "index.html", "evil.py"]}]}
    r4a = pg.decide(repo4, base4, None, allowlist_ref=base4)
    (repo4 / "publish_allowlist.json").write_text(json.dumps(wide), encoding="utf-8")
    r4b = pg.decide(repo4, base4, None, allowlist_ref=base4)
    check("A4 工作區改寫白名單不生效", r4a["ok"] and r4b["ok"] and r4b["allow_entry"] == "AI 成本帳",
          f"a={r4a['ok']} b={r4b['ok']} entry={r4b['allow_entry']}")


def s_r7_impersonation() -> None:
    """R7 驗收：判定不看腳本名稱 → 冒充結構性無效。"""
    print("\n【R7：冒充腳本名稱（簡化設計後應失效）】")
    # 未命中白名單的產物，即使自稱是「有白名單的」腳本名 → 仍必須走 CIO
    repo, head, base = make_repo({"index.html": "<html>"}, reviewer="AUTO-checker:cost_watch_digest.py")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("R7-1 自稱他人腳本名仍無法取得 AUTO（判定不看 --script）", not r["ok"],
          str([b["id"] for b in r["blockings"]]))
    # 命中白名單者，任何腳本名都能走 AUTO（因為是「變更集合」取得授權，不是身分）
    repo2, head2, base2 = make_repo({"cost.html": "a"}, reviewer="AUTO-checker:any_random_name.py")
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("R7-2 命中白名單者，腳本名不影響判定（授權來自變更集合）", r2["ok"], str(r2.get("blockings"))[:160])


def s_multi_error() -> None:
    print("\n【多重錯誤並存】")
    repo, head, base = make_repo({"index.html": "<html>", "evil.py": "x"},
                                 reviewer="AUTO-checker:x.py", tree_override="1" * 40)
    r = pg.decide(repo, base, ["nonexistent.json"], allowlist_ref=base)
    ids = {b["id"] for b in r["blockings"]}
    check("M1 記錄失敗與其他檢查並存", "RECORD" in ids and len(ids) >= 2, str(sorted(ids)))
    check("M2 特殊類別仍被記錄", r["checks"]["special"]["ok"] is False, str(r["checks"]["special"]))
    check("M3 own 越權仍被記錄", any(b["id"] == "OWN_OUTSIDE" for b in r["blockings"]))
    check("M4 checks 含全部關卡鍵",
          {"changes", "special", "allowlist", "mode", "records", "cio_signoff", "producer_own"}
          <= set(r["checks"]), str(sorted(r["checks"])))
    check("M5 整體 FAIL", not r["ok"])


def s_edge() -> None:
    print("\n【邊界】")
    repo, head, base = make_repo({})
    r = pg.decide(repo, "HEAD", None, allowlist_ref="HEAD")
    check("E1 空變更→拒（RANGE_EMPTY）", not r["ok"] and any(b["id"] == "RANGE_EMPTY" for b in r["blockings"]))
    # 變更狀態解析（M / A / D）
    repo2, head2, base2 = make_repo({"cost.html": "a", "cost_data.json": "{}"})
    (repo2 / "cost_data.json").unlink()
    _git(repo2, "add", "-A")
    _git(repo2, "commit", "-q", "-m", "delete")
    head2b = _git(repo2, "rev-parse", "HEAD")
    ch, why = pg.changes(repo2, base2)
    check("E2 刪除狀態被納入變更", ch is not None and ch.get("cost_data.json") == "D", str(ch))
    # 白名單最貼合條目選擇
    al = {"version": 1, "entries": [
        {"label": "narrow", "allow": ["cost.html"]},
        {"label": "wide", "allow": ["cost.html", "cost_data.json", "data/ai_cost_daily.jsonl"]}]}
    repo3, head3, base3 = make_repo({"cost.html": "a"}, allowlist=al)
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("E3 多條目命中時取最貼合者（narrow）", r3["allow_entry"] == "narrow", str(r3["allow_entry"]))
    # special_reason 直接邊界
    check("E4 例外：data/ 目錄不因前綴被誤擋",
          pg.special_reason("data/ai_cost_daily.jsonl") is None)
    check("E5 .bak 被擋", pg.special_reason("x.json.bak") is not None)
    check("E6 reviews/ 被擋", pg.special_reason("reviews/a.json") is not None)


def main() -> int:
    print("=" * 70)
    print("publish_gate 隔離測試（白名單 + 實際變更集合）")
    print("=" * 70)
    s_positive()
    s_not_allowlisted()
    s_special_forbidden()
    s_record_problems()
    s_allowlist_integrity()
    s_r7_impersonation()
    s_multi_error()
    s_edge()
    print("\n" + "=" * 70)
    print(f"通過 {len(PASS)} 項｜失敗 {len(FAIL)} 項")
    for f in FAIL:
        print("  -", f)
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
