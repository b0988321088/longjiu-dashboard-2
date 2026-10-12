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
    # 本輪 CIO 指摘的修正驗證
    check("E7 大小寫變體被擋（Windows 大小寫不敏感）",
          pg.special_reason("Reviews/x.json") is not None
          and pg.special_reason("PENDING_DECISIONS.JSON") is not None)
    check("E8 憑證／設定檔被擋（.env/.ini/.conf/.xml）",
          all(pg.special_reason(x) is not None for x in ("cfg.env", "app.ini", "s.conf", "d.xml")))
    check("E9 二進位／執行檔被擋（.exe/.dll/.jar/.so）",
          all(pg.special_reason(x) is not None for x in ("a.exe", "b.dll", "c.jar", "d.so")))
    # 空 allow 檢查（既有實作，供 review 追溯）
    repo4, head4, base4 = make_repo({"cost.html": "a"},
                                    allowlist={"version": 1, "entries": [{"label": "x", "allow": []}]})
    r4 = pg.decide(repo4, base4, None, allowlist_ref=base4)
    check("E10 條目 allow 為空字串→拒（既有檢查）",
          not r4["ok"] and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r4["blockings"]))


# ------------------------------------------------ 純資料批次授權路徑（v3）

ALLOW_RADAR = {"version": 3, "entries": [
    {"label": "雷達發布產物", "producer": "radar_push.py",
     "patterns": ["radar_state.json", "radar_report_*.html"],
     "evidence": "radar_weekly.py 產生、build_dashboard.py 重繪；檔名含日期", "risk": "low"}]}


def s_data_batch_lane() -> None:
    """正向：已登記的純資料批次走 AUTO；負向：未登記／混合一律不走 AUTO。"""
    print("\n【純資料批次授權路徑】")
    repo, head, base = make_repo({"radar_state.json": "{}",
                                  "radar_report_2026-10-12.html": "<html>"},
                                 allowlist=ALLOW_RADAR)
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("D1 已登記純資料批次（含日期樣式）→ 可發布 AUTO",
          r["ok"] and r["mode"] == "AUTO", str(r.get("blockings"))[:200])
    check("D1b 命中正確條目", r["allow_entry"] == "雷達發布產物", str(r["allow_entry"]))
    # 只有 state（子集）也命中同一條目
    repo2, head2, base2 = make_repo({"radar_state.json": "{}"}, allowlist=ALLOW_RADAR)
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("D2 子集（僅 state）→ 可發布 AUTO", r2["ok"] and r2["mode"] == "AUTO",
          str(r2.get("blockings"))[:200])
    # 負向：未登記檔
    repo3, head3, base3 = make_repo({"radar_state.json": "{}", "unknown_thing.json": "{}"},
                                    allowlist=ALLOW_RADAR)
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("D3 未登記檔（純資料）→ 拒（不得因未知而自動核准）", not r3["ok"])
    check("D3b blocking=CIO_REQUIRED", any(b["id"] == "CIO_REQUIRED" for b in r3["blockings"]),
          str([b["id"] for b in r3["blockings"]]))
    # 負向：混合範圍（登記資料 + 程式檔）
    repo4, head4, base4 = make_repo({"radar_state.json": "{}", "helper.py": "x"},
                                    allowlist=ALLOW_RADAR)
    r4 = pg.decide(repo4, base4, None, allowlist_ref=base4)
    check("D4 混合範圍（資料＋程式）→ 拒", not r4["ok"])
    check("D4b 特殊類別仍被記錄", r4["checks"]["special"]["ok"] is False)
    # 負向：混合範圍（登記資料 + 治理紀錄）
    repo5, head5, base5 = make_repo({"radar_state.json": "{}", "work_log.json": "{}"},
                                    allowlist=ALLOW_RADAR)
    r5 = pg.decide(repo5, base5, None, allowlist_ref=base5)
    check("D5 混合範圍（資料＋治理紀錄）→ 拒", not r5["ok"])
    # 負向：登記資料 + 未登記檔（樣式不得吸收）
    repo6, head6, base6 = make_repo({"radar_report_2026-10-12.html": "<html>",
                                     "radar_report_evil.json": "{}"},
                                    allowlist=ALLOW_RADAR)
    r6 = pg.decide(repo6, base6, None, allowlist_ref=base6)
    check("D6 樣式不得跨副檔名吸收（*.json 未登記）→ 拒", not r6["ok"],
          str([b["id"] for b in r6["blockings"]]))


def s_pattern_safety() -> None:
    """負向：條目規格過寬 → 整份白名單不可用（fail-closed，不得靜默忽略）。"""
    print("\n【白名單規格安全（fail-closed）】")
    bad = {
        "以 * 開頭": ["*_report.html"],
        "通用 json": ["*.json"],
        "副檔名含 *": ["radar_*.h*ml"],
        "前綴過短": ["a*.html"],
        "程式副檔名": ["radar_report_*.py"],
        "備份副檔名": ["radar_*.bak"],
        "治理檔字面": ["work_log.json"],
        "reviews 前綴": ["reviews/radar_*.json"],
        "空字串": [""],
    }
    for label, pats in bad.items():
        al = {"version": 3, "entries": [{"label": "壞條目", "producer": "x.py",
                                         "patterns": pats}]}
        repo, head, base = make_repo({"radar_state.json": "{}"}, allowlist=al)
        r = pg.decide(repo, base, None, allowlist_ref=base)
        ok = (not r["ok"]) and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r["blockings"])
        check(f"S-{label}（{pats}）→ 白名單不可用、拒", ok,
              str([b["id"] for b in r["blockings"]]))
    # patterns 未標 producer → 拒
    al2 = {"version": 3, "entries": [{"label": "無歸屬", "patterns": ["radar_state.json"]}]}
    repo2, head2, base2 = make_repo({"radar_state.json": "{}"}, allowlist=al2)
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("S-無 producer 的 patterns 條目→拒",
          not r2["ok"] and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r2["blockings"]))
    # 合法樣式仍可用（避免防線過度）
    repo3, head3, base3 = make_repo({"radar_report_2026-10-12.html": "<html>"},
                                    allowlist=ALLOW_RADAR)
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("S-合法樣式 radar_report_*.html→仍可用", r3["ok"] and r3["mode"] == "AUTO",
          str(r3.get("blockings"))[:160])


def s_forgery() -> None:
    """負向：偽造標記／偽造授權。"""
    print("\n【偽造】")
    # 1) 工作區改寫白名單（憑空長出授權）→ 讀 HEAD 版本，無效
    repo, head, base = make_repo({"unknown_thing.json": "{}"}, allowlist=ALLOW_RADAR)
    r1a = pg.decide(repo, base, None, allowlist_ref=base)
    forged = {"version": 3, "entries": [{"label": "偽造", "producer": "x.py",
                                         "patterns": ["unknown_thing.json"]}]}
    (repo / "publish_allowlist.json").write_text(json.dumps(forged, ensure_ascii=False),
                                                 encoding="utf-8")
    r1b = pg.decide(repo, base, None, allowlist_ref=base)
    check("X1 工作區改寫白名單偽造授權→無效", (not r1a["ok"]) and (not r1b["ok"]),
          f"a={r1a['ok']} b={r1b['ok']}")
    # 2) 自稱他人 producer 名 → 判定不看身分，仍拒
    repo2, head2, base2 = make_repo({"unknown_thing.json": "{}"},
                                    reviewer="AUTO-checker:radar_push.py")
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("X2 自稱已登記 producer 名→仍拒（授權來自檔案集合）", not r2["ok"],
          str([b["id"] for b in r2["blockings"]]))
    # 3) 偽造 tree 綁定
    repo3, head3, base3 = make_repo({"radar_state.json": "{}"}, allowlist=ALLOW_RADAR,
                                    tree_override="f" * 40)
    r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
    check("X3 偽造／過期 tree 的核准紀錄→拒", not r3["ok"])
    # 4) 未命中條目但自落 AUTO 章
    repo4, head4, base4 = make_repo({"dashboard_decisions.json": "{}"},
                                    reviewer="AUTO-checker:x.py")
    r4 = pg.decide(repo4, base4, None, allowlist_ref=base4)
    check("X4 未登記治理檔 + AUTO 章→拒", not r4["ok"] and r4["mode"] == "CIO")


def s_classify_single_truth() -> None:
    """classify 為兩側共用真值：classify_paths 與 decide 對同一集合給出相同 mode。"""
    print("\n【單一真值（落版側／閘門側一致）】")
    cases = [
        ({"cost.html": "a"}, ALLOW_COST, "AUTO"),
        ({"radar_state.json": "{}", "radar_report_2026-10-12.html": "<html>"}, ALLOW_RADAR, "AUTO"),
        ({"unknown_thing.json": "{}"}, ALLOW_RADAR, "CIO"),
        ({"radar_state.json": "{}", "helper.py": "x"}, ALLOW_RADAR, "CIO"),
        ({"work_log.json": "{}"}, ALLOW_RADAR, "CIO"),
    ]
    for files, al, want in cases:
        repo, head, base = make_repo(files, allowlist=al)
        rd = pg.decide(repo, base, None, allowlist_ref=base)["mode"]
        rc = pg.classify_paths(repo, sorted(files), ref=base)["mode"]
        check(f"T 兩側一致 {sorted(files)} → {want}", rd == want and rc == want,
              f"decide={rd} classify_paths={rc}")


def s_hardening_f1_f2_f3() -> None:
    """CIO 審查 required_fixes F1／F2／F3 的加固驗證。"""
    print("\n【加固：F1 前導點盲點／F2 allow 樣式／F3 無副檔名樣式】")
    # F1：_norm 不得把開頭多個 '.' 剝掉
    check("F1a _norm 保留前導點（.env）", pg._norm(".env") == ".env", pg._norm(".env"))
    check("F1b _norm 仍剝成對的 './'", pg._norm("./x/y.json") == "x/y.json", pg._norm("./x/y.json"))
    check("F1c _norm 保留 .githooks/", pg._norm("./.githooks/pre-push") == ".githooks/pre-push",
          pg._norm("./.githooks/pre-push"))
    check("F1d special_reason('.env') 必須命中", pg.special_reason(".env") is not None)
    check("F1e special_reason('.githooks/pre-push') 必須命中",
          pg.special_reason(".githooks/pre-push") is not None)
    check("F1f special_reason('.hermes/x.json') 必須命中",
          pg.special_reason(".hermes/x.json") is not None)
    # F1 端到端：把 .githooks/* 註冊進 patterns 也不得放行
    for pats in (["\.githooks/*"], [".githooks/pre-push"]):
        al = {"version": 3, "entries": [{"label": "壞", "producer": "x.py", "patterns": pats}]}
        repo, head, base = make_repo({"x.json": "{}"}, allowlist=al)
        r = pg.decide(repo, base, None, allowlist_ref=base)
        check(f"F1g patterns={pats} → 白名單不可用、拒", not r["ok"],
              str([b["id"] for b in r["blockings"]]))
    # F2：allow 內含 '*' → fail-closed（allow 語意為字面路徑）
    al2 = {"version": 1, "entries": [{"label": "字面混樣式", "allow": ["radar_*.html"]}]}
    repo2, head2, base2 = make_repo({"radar_report_9.html": "<html>"}, allowlist=al2)
    r2 = pg.decide(repo2, base2, None, allowlist_ref=base2)
    check("F2 allow 含 '*' → 白名單不可用、拒（不得靜默當 glob）",
          not r2["ok"] and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r2["blockings"]),
          str([b["id"] for b in r2["blockings"]]))
    # F3：樣式必須明示副檔名
    for pats in (["data/*"], ["radar_*"], ["dir/sub*"]):
        al3 = {"version": 3, "entries": [{"label": "無副檔名", "producer": "x.py", "patterns": pats}]}
        repo3, head3, base3 = make_repo({"x.json": "{}"}, allowlist=al3)
        r3 = pg.decide(repo3, base3, None, allowlist_ref=base3)
        check(f"F3 patterns={pats} → 白名單不可用、拒", not r3["ok"],
              str([b["id"] for b in r3["blockings"]]))
    # 回歸：合法樣式仍可用
    repo4, head4, base4 = make_repo({"radar_report_2026-10-12.html": "<html>"},
                                    allowlist=ALLOW_RADAR)
    r4 = pg.decide(repo4, base4, None, allowlist_ref=base4)
    check("F3 回歸 合法樣式 radar_report_*.html 仍可用",
          r4["ok"] and r4["mode"] == "AUTO", str(r4.get("blockings"))[:160])


# ------------------------------------------------- append-only 受限車道（PG-20261012 v4）

ALLOW_AO = {"version": 1, "entries": [
    {"label": "決策入庫（append-only 受限）",
     "allow": ["dashboard_decisions.json", "data/decision_intake_receipts.jsonl"],
     "append_only": True, "producer": "append_dashboard_decisions.py"}]}
ALLOW_AO_COST = {"version": 1, "entries": ALLOW_AO["entries"] + ALLOW_COST["entries"]}

_DEC = "dashboard_decisions.json"
_REC = "data/decision_intake_receipts.jsonl"


def _dec_text(entries: list[dict], meta_note: str = "m0") -> str:
    return json.dumps({"decisions": entries, "meta": {"updated_at": meta_note},
                       "last_updated": "2026-10-01"}, ensure_ascii=False, indent=1)


def _dec_entry(i: int, **over) -> dict:
    d = {"id": f"mem-20261012171635-{i}", "timestamp": f"2026-10-12T17:1{i}:00+08:00",
         "agent": "Hermes", "task": f"task-{i}", "summary": f"summary-{i}",
         "status": "completed", "source": "user"}
    d.update(over)
    return d


def _rec_line(i: int, ok: bool = True) -> str:
    return json.dumps({"ts": f"2026-10-12T17:1{i}:00+08:00", "id": f"mem-20261012171635-{i}",
                       "task": f"task-{i}", "source": "user", "ok": ok, "note": "n"},
                      ensure_ascii=False)


def make_ao_repo(dec_before: str, rec_before: str, dec_after: str | None, rec_after: str | None,
                 allowlist: dict | None = ALLOW_AO, extra_after: dict | None = None,
                 reviewer: str = "AUTO-checker:append_dashboard_decisions.py",
                 approvals: bool = True, msg: str = "produce",
                 include_gate: bool = False) -> tuple[Path, str, str]:
    """base commit 已含兩檔；第二顆 commit 依參數追加（dec_after=None ＝ 刪除該檔）。

    include_gate=True 時把受測的 publish_gate.py 放進 base commit（供 auto_record.force_cio_paths
    在同一個 base 內 import 用）。
    """
    repo = Path(tempfile.mkdtemp(prefix="pgtest_ao_"))
    for a in (["init", "-q"], ["config", "user.email", "t@example.com"],
              ["config", "user.name", "tester"], ["config", "core.autocrlf", "false"]):
        _git(repo, *a)
    if include_gate:
        (repo / "publish_gate.py").write_text((REPO / "publish_gate.py").read_text(encoding="utf-8"),
                                              encoding="utf-8")
    if allowlist is not None:
        (repo / "publish_allowlist.json").write_text(
            json.dumps(allowlist, ensure_ascii=False, indent=1), encoding="utf-8")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / _DEC).write_text(dec_before, encoding="utf-8")
    (repo / _REC).parent.mkdir(parents=True, exist_ok=True)
    (repo / _REC).write_text(rec_before, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    for rel, content in (extra_after or {}).items():
        fp = repo / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
    if dec_after is None:
        _git(repo, "rm", "-q", "--", _DEC)
    else:
        (repo / _DEC).write_text(dec_after, encoding="utf-8")
    if rec_after is None:
        _git(repo, "rm", "-q", "--", _REC)
    elif rec_after != rec_before:
        (repo / _REC).write_text(rec_after, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    head = _git(repo, "rev-parse", "HEAD")
    if approvals:
        tree = _git(repo, "rev-parse", "HEAD^{tree}")
        (repo / ".git" / "CIO_APPROVED").write_text(
            f"2026-10-12T00:00:00Z\t{tree}\t{head}\tAPPROVE\t{reviewer}\tnote\n", encoding="utf-8")
    return repo, head, base


def _ao_blocked(r) -> bool:
    """不變量未通過的正確行為：不得給 AUTO（mode=CIO）＋ 必須留下具名 advisory 可稽核。

    不硬擋的理由：一顆內容不符的 commit 若經真 CIO 明確核准（tree 綁定）仍應可發布；
    硬擋會製造「合法修正無路可走」的新型死鎖。偽造 AUTO 章則由 CIO_REQUIRED 擋下。
    """
    return (not r["ok"]) and r["mode"] == "CIO" \
        and r["checks"]["append_only"].get("ok") is False \
        and any(a["id"] == "APPEND_ONLY_NOT_VERIFIED" for a in r.get("advisories", []))


def s_append_only_lane() -> None:
    print("\n【append-only 受限車道（決策入庫兩檔）】")
    e1, e2 = _dec_entry(1), _dec_entry(2)
    dec0, rec0 = _dec_text([e1, e2]), _rec_line(1) + "\r\n" + _rec_line(2) + "\r\n"

    # ── 正向：合法追加
    e3 = _dec_entry(3)
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]), rec0 + _rec_line(3) + "\r\n")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-P1 合法追加（決策+1／收據+1／meta 不動）→ 可發布 AUTO",
          r["ok"] and r["mode"] == "AUTO", str(r.get("blockings"))[:220])
    check("AO-P1b 命中受限條目", r["allow_entry"] == "決策入庫（append-only 受限）", str(r["allow_entry"]))
    check("AO-P1c 不變量驗證確實執行且通過",
          r["checks"]["append_only"].get("ok") is True and r["checks"]["append_only"].get("mode") == "range",
          str(r["checks"]["append_only"])[:200])
    v = pg.classify_paths(repo, [_DEC, _REC], ref="HEAD")
    check("AO-P1d 落版側與閘門側同結論（AUTO）→ 不再出現一側 AUTO／一側 CIO 死鎖",
          v["mode"] == "AUTO" and v.get("append_only", {}).get("ok") is True, str(v)[:220])

    # ── 正向：失敗收據（決策檔未動、收據 ok=false）
    repo, head, base = make_ao_repo(dec0, rec0, dec0, rec0 + _rec_line(9, ok=False) + "\r\n")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-P2 僅失敗收據（ok=false、決策未動）→ 仍可發布 AUTO",
          r["ok"] and r["mode"] == "AUTO", str(r.get("blockings"))[:220])

    # ── 負向：既有紀錄被動到
    cases = [
        ("AO-N1 修改既有決策內容",
         _dec_text([dict(e1, summary="竄改"), e2]), rec0),
        ("AO-N2 刪除既有決策",
         _dec_text([e1]), rec0),
        ("AO-N3 改動 meta（頂層鍵）",
         _dec_text([e1, e2], meta_note="CHANGED"), rec0),
        ("AO-N4 決策有新增但收據未同步",
         _dec_text([e1, e2, e3]), rec0),
        ("AO-N5 決策檔被刪除", None, rec0),
    ]
    for name, dec_after, rec_after in cases:
        repo, head, base = make_ao_repo(dec0, rec0, dec_after, rec_after)
        r = pg.decide(repo, base, None, allowlist_ref=base)
        check(f"{name} → 拒", _ao_blocked(r),
              str([b["id"] for b in r["blockings"]]))
        check(f"{name}b 回 CIO 模式（不得自動發布）", r["mode"] == "CIO")

    # ── 負向：收據被動到
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]),
                                    rec0.replace('"note": "n"', '"note": "X"', 1) + _rec_line(3) + "\r\n")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N6 修改既有收據行 → 拒",
          _ao_blocked(r),
          str([b["id"] for b in r["blockings"]]))

    repo, head, base = make_ao_repo(dec0, rec0, dec0, rec0 + _rec_line(7) + "\r\n")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N7 憑空 ok=true 收據（決策檔無此 id）→ 拒",
          _ao_blocked(r),
          str([b["id"] for b in r["blockings"]]))

    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]),
                                    rec0 + _rec_line(3) + "\r\n" + _rec_line(8) + "\r\n")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N8 決策 1 筆／成功收據 2 筆（筆數不一致）→ 拒",
          _ao_blocked(r),
          str([b["id"] for b in r["blockings"]]))

    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]), rec0 + _rec_line(3) + "\r\n",
                                    extra_after={"helper.py": "x = 1\n"})
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N9 同一顆 commit 混入程式碼 → 拒",
          not r["ok"] and any(b["id"] == "CIO_REQUIRED" for b in r["blockings"]),
          str([b["id"] for b in r["blockings"]]))
    check("AO-N9b 受限車道未被套用（append_only.applied=False）",
          r["checks"]["append_only"].get("applied") is False, str(r["checks"]["append_only"])[:160])

    # ── 負向：偽造 producer 自稱（授權不來自名字）
    fake = {"version": 1, "entries": [
        {"label": "x", "allow": [_DEC, _REC], "append_only": True, "producer": "someone_else.py"}]}
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([dict(e1, summary="竄改"), e2]), rec0,
                                    allowlist=fake, msg="data(decisions): 入庫 append_dashboard_decisions.py")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N10 自稱 append_dashboard_decisions.py 但內容非追加 → 仍拒（不靠自稱）",
          _ao_blocked(r),
          str([b["id"] for b in r["blockings"]]))

    # ── 負向：條目本身不合法 → 整份白名單不可用（fail-closed，非靜默忽略）
    bad_entries = {
        "AO-N11 條目夾帶第三條路徑": {"allow": [_DEC, _REC, "cost.html"], "append_only": True, "producer": "p.py"},
        "AO-N12 條目使用樣式": {"patterns": [_DEC, "data/decision_intake_*.jsonl"], "append_only": True, "producer": "p.py"},
        "AO-N13 條目缺 producer": {"allow": [_DEC, _REC], "append_only": True},
        "AO-N14 條目指向範圍外檔案": {"allow": [_DEC, "snapshot.json"], "append_only": True, "producer": "p.py"},
    }
    for name, entry in bad_entries.items():
        al = {"version": 1, "entries": [entry]}
        repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]), rec0 + _rec_line(3) + "\r\n",
                                        allowlist=al)
        r = pg.decide(repo, base, None, allowlist_ref=base)
        check(f"{name} → 白名單不可用、拒",
              not r["ok"] and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r["blockings"]),
              str([b["id"] for b in r["blockings"]]))

    # ── 落版側與閘門側同結論（本輪修掉的第二處 divergence：auto_record.force_cio_paths 二次推翻）
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import auto_record as _ar
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]), rec0 + _rec_line(3) + "\r\n",
                                    include_gate=True)
    got = _ar.force_cio_paths([_DEC, _REC], repo)
    check("AO-P3 落版側 force_cio_paths：合法追加 → 不再列為強制 CIO（否則又死鎖）",
          got == [], str(got))
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([dict(e1, summary="竄改"), e2]), rec0,
                                    include_gate=True)
    got2 = _ar.force_cio_paths([_DEC, _REC], repo)
    check("AO-N15 落版側 force_cio_paths：非追加內容 → 仍列為強制 CIO",
          sorted(got2) == sorted([_DEC, _REC]), str(got2))

    # ── 防禦性收斂（獨立審查 Finding 3）：車道只收斂受限兩檔本身的特殊類別
    check("AO-N17 classify：車道通過但 specials 含範圍外高風險路徑 → 仍回 CIO",
          pg.classify({_DEC, _REC}, {"append_only": True},
                      {"work_log.json": "治理紀錄"}, append_only_ok=True)[0] == "CIO")
    check("AO-P5 classify：車道通過且 specials 僅含受限兩檔 → AUTO（收斂成立、非全面豁免）",
          pg.classify({_DEC, _REC}, {"append_only": True},
                      {_DEC: "列於強制 CIO 清單"}, append_only_ok=True)[0] == "AUTO")

    # ── 新語意：不變量未通過＝不給 AUTO，但真 CIO 明確核准仍可發布（合法修正有出路）
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([dict(e1, summary="CIO 核准的修正"), e2]), rec0,
                                    reviewer="CIO-Gemini")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-P4 不變量未通過＋真 CIO 核准（tree 綁定）→ 可發布（不是死鎖）", r["ok"],
          str(r.get("blockings"))[:200])
    check("AO-P4b 仍不給 AUTO（mode=CIO、advisory 保留可稽核）",
          r["mode"] == "CIO" and any(a["id"] == "APPEND_ONLY_NOT_VERIFIED" for a in r["advisories"]),
          str(r.get("advisories"))[:160])

    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([dict(e1, summary="竄改"), e2]), rec0,
                                    reviewer="AUTO-checker:append_dashboard_decisions.py")
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-N16 不變量未通過＋偽造 AUTO 章 → 拒（CIO_REQUIRED）",
          not r["ok"] and any(b["id"] == "CIO_REQUIRED" for b in r["blockings"]),
          str([b["id"] for b in r["blockings"]]))

    # ── 回歸：新增條目不得影響既有成本帳條目
    repo, head, base = make_repo({"cost.html": "a", "cost_data.json": "{}"}, allowlist=ALLOW_AO_COST)
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-R1 回歸：成本帳條目仍判 AUTO（受限車道未污染其他條目）",
          r["ok"] and r["mode"] == "AUTO" and r["allow_entry"] == "AI 成本帳", str(r.get("blockings"))[:200])

    # ── 回歸：決策兩檔在「非 append-only 條目」下仍必須走真 CIO
    legacy = {"version": 1, "entries": [{"label": "一般資料條目", "allow": [_DEC, _REC]}]}
    repo, head, base = make_ao_repo(dec0, rec0, _dec_text([e1, e2, e3]), rec0 + _rec_line(3) + "\r\n",
                                    allowlist=legacy)
    r = pg.decide(repo, base, None, allowlist_ref=base)
    check("AO-R2 回歸：未帶 append_only 的條目列出這兩檔 → 白名單不可用（不得藉一般條目放行）",
          not r["ok"] and any(b["id"] == "ALLOWLIST_UNAVAILABLE" for b in r["blockings"]),
          str([b["id"] for b in r["blockings"]]))


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
    s_data_batch_lane()
    s_pattern_safety()
    s_forgery()
    s_classify_single_truth()
    s_hardening_f1_f2_f3()
    s_append_only_lane()
    print("\n" + "=" * 70)
    print(f"通過 {len(PASS)} 項｜失敗 {len(FAIL)} 項")
    for f in FAIL:
        print("  -", f)
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
