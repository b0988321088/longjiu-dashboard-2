#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""publish_gate.py — 發布授權閘門（簡化版 v3）

PG-20261011 v2 裁決的落地。核心問題：**系統無法可靠判斷「這次要發布的檔案，是不是它有權發布的」**。

設計原則：
  1. 只看「本次實際變更」（git diff --name-status，含 A/M/D/R），
     **不從歷史產物推導、不做靜態分析**（前者會把舊錯誤制度化、後者無法掌握動態路徑）。
  2. 白名單以「**變更檔案集合**」為鍵，**不以腳本名稱為鍵**。
     → 呼叫端無法藉 --script 自稱取得授權（此即 R7 的結構性消除）。
  3. 特殊類別（審查結果、治理紀錄、備份檔、程式檔）一律強制走真 CIO 審查。
  4. 白名單讀**版控內版本**（git show），工作區就地改寫無效。
  5. 所有檢查一律執行、結果分別記錄，最後統一裁決（不得讓前一項失敗遮蔽後續）。

三道關卡：
  一：本次實際變更
  二：簡單規則 → AUTO 或 CIO
  三：核准紀錄與 tree 綁定驗證（舊核准不得重用；CIO 路徑不得由 AUTO 蓋章代簽）

輸出 rc：0 可發布／3 拒絕（fail-closed）／6 用法或來源不可用
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK = 0
EXIT_REJECT = 3
EXIT_USAGE = 6

ALLOWLIST_PATH = "publish_allowlist.json"
AUTO_PREFIX = "AUTO-checker:"

# 一律強制真 CIO 審查（不得由 AUTO 通道發布）
NEVER_AUTO_EXACT = {
    "error_register.md",
    "pending_decisions.json",
    "pending_decisions_archive.json",
    "work_log.json",
    "dashboard_decisions.json",
    "snapshot.json",
    "inc_events.jsonl",
    "publish_allowlist.json",
}
NEVER_AUTO_PREFIX = (
    "reviews/",
    "scopes/",
    ".hermes/",
    ".githooks/",
    "logs/",
    "data/decision_intake",
)
NEVER_AUTO_SUFFIX = (".bak", ".backup", ".old", ".orig", ".tmp", ".env", ".envrc")
CODE_SUFFIX = (".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml",
               ".js", ".ts", ".sql", ".json5", ".ini", ".conf", ".cfg", ".xml",
               ".properties", ".exe", ".bin", ".jar", ".so", ".dll", ".dylib", ".msi")


def _git(base: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(base), capture_output=True, text=True, timeout=timeout)


def _norm(p: str) -> str:
    return str(p).replace("\\", "/").lstrip("./")


def git_dir(base: Path) -> Path:
    r = _git(base, ["rev-parse", "--git-dir"])
    d = Path(r.stdout.strip())
    return d if d.is_absolute() else (base / d)


# ---------------------------------------------------------------- 關卡一

def changes(base: Path, range_base: str) -> tuple[dict[str, str] | None, str]:
    """本次實際變更 → {path: status}，status ∈ A/M/D/R/T…（R 取新路徑）。"""
    r = _git(base, ["diff", "--name-status", "-M", f"{range_base}..HEAD"])
    if r.returncode != 0:
        return None, f"無法取得變更清單（{range_base}..HEAD）：{(r.stderr or '').strip()[:120]}"
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st = parts[0][:1]
        path = parts[2] if (st == "R" and len(parts) >= 3) else parts[1]
        out[_norm(path)] = st
    return out, "ok"


def special_reason(path: str, base: Path | None = None) -> str | None:
    """特殊類別 → 強制真 CIO 審查。回傳原因或 None。

    比對一律**不分大小寫**（本系統在 Windows 上執行，大小寫不敏感的檔案系統
    可能讓 'Reviews/x.json' 繞過 'reviews/' 前綴比對）。
    """
    p = _norm(path)
    lp = p.lower()
    if lp in {x.lower() for x in NEVER_AUTO_EXACT}:
        return f"列於強制 CIO 清單：{p}"
    for pre in NEVER_AUTO_PREFIX:
        if lp.startswith(pre.lower()):
            return f"屬強制 CIO 前綴（{pre}）：{p}"
    for suf in NEVER_AUTO_SUFFIX:
        if lp.endswith(suf.lower()):
            return f"備份／暫存／憑證檔不得自動發布：{p}"
    for suf in CODE_SUFFIX:
        if lp.endswith(suf.lower()):
            return f"程式／設定檔改動必須走真 CIO 審查：{p}"
    # 符號連結：目標可能指向未授權路徑 → 一律不得自動發布
    if base is not None:
        try:
            fp = base / p
            if fp.is_symlink():
                return f"符號連結不得自動發布（目標未受白名單管轄）：{p}"
        except Exception:
            return f"無法安全判定檔案型態（保守拒絕）：{p}"
    return None


# ---------------------------------------------------------------- 關卡二

def load_allowlist(base: Path, ref: str = "HEAD") -> tuple[dict | None, str]:
    """讀**已提交版本**的產物白名單（工作區改寫無效）。"""
    r = _git(base, ["show", f"{ref}:{ALLOWLIST_PATH}"])
    if r.returncode != 0:
        return None, f"白名單不存在（{ref}:{ALLOWLIST_PATH}）"
    try:
        m = json.loads(r.stdout)
    except Exception as e:
        return None, f"白名單非合法 JSON：{e}"
    if not isinstance(m, dict) or not isinstance(m.get("entries"), list) or not m["entries"]:
        return None, "白名單格式錯誤（需 entries 非空陣列）"
    for e in m["entries"]:
        if not isinstance(e, dict) or not isinstance(e.get("allow"), list) or not e["allow"]:
            return None, f"白名單條目格式錯誤：{e!r}"
        if any(str(x).strip() == "" for x in e["allow"]):
            return None, "白名單條目含空字串"
    return m, "ok"


def match_entry(changed: set[str], allowlist: dict) -> tuple[dict | None, str]:
    """找出「本次變更全部落在其 allow 內」的白名單條目；無則回 None。"""
    hits = []
    for e in allowlist["entries"]:
        allowed = {_norm(x) for x in e["allow"]}
        if changed <= allowed:
            hits.append(e)
    if not hits:
        return None, "本次變更不在任何已核准的低風險白名單內"
    # 取最貼合者（allow 最小）作為判定依據，避免寬鬆條目意外吸收
    best = sorted(hits, key=lambda e: len(e["allow"]))[0]
    return best, "ok"


# ---------------------------------------------------------------- 關卡三

def approvals(base: Path) -> dict[str, dict]:
    p = git_dir(base) / "CIO_APPROVED"
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) >= 5:
            out[parts[2].strip()] = {"at": parts[0], "tree": parts[1], "verdict": parts[3],
                                     "reviewer": parts[4], "note": parts[5] if len(parts) > 5 else ""}
    return out


def commit_tree(base: Path, commit: str) -> str:
    return _git(base, ["rev-parse", f"{commit}^{{tree}}"]).stdout.strip()


def commits_in_range(base: Path, range_base: str) -> list[str]:
    r = _git(base, ["rev-list", f"{range_base}..HEAD"])
    return [c for c in r.stdout.split() if c] if r.returncode == 0 else []


def is_auto(rec: dict) -> bool:
    return str(rec.get("reviewer") or "").startswith(AUTO_PREFIX)


# ---------------------------------------------------------------- 統一裁決

def decide(base: Path, range_base: str, producer_own: list[str] | None = None,
           allowlist_ref: str = "HEAD") -> dict:
    checks: dict = {}
    blockings: list[dict] = []

    # 關卡一
    ch, why = changes(base, range_base)
    if ch is None:
        checks["changes"] = {"ok": False, "reason": why}
        blockings.append({"id": "CHANGES_UNAVAILABLE", "severity": "high", "text": why})
        ch = {}
    else:
        checks["changes"] = {"ok": bool(ch), "count": len(ch),
                             "files": {k: ch[k] for k in sorted(ch)}}
        if not ch:
            blockings.append({"id": "RANGE_EMPTY", "severity": "high",
                              "text": "本次變更為空（無事可做）"})
    changed = set(ch.keys())

    # 關卡二：特殊類別（一律執行，不因前面失敗而跳過）
    specials = {p: special_reason(p, base) for p in sorted(changed)}
    specials = {p: r for p, r in specials.items() if r}
    checks["special"] = {"ok": not specials, "hits": specials}

    al, why_al = load_allowlist(base, ref=allowlist_ref)
    if al is None:
        checks["allowlist"] = {"ok": False, "reason": why_al}
        blockings.append({"id": "ALLOWLIST_UNAVAILABLE", "severity": "high", "text": why_al})
        entry, why_e = None, why_al
    else:
        entry, why_e = match_entry(changed, al)
        checks["allowlist"] = {"ok": entry is not None, "version": al.get("version"),
                              "entries": len(al["entries"]),
                              "matched": (entry or {}).get("label"), "reason": why_e}

    # 模式判定：特殊類別命中 或 不在白名單 → 必須走真 CIO 審查
    must_cio = bool(specials) or entry is None
    mode = "CIO" if must_cio else "AUTO"
    checks["mode"] = {"mode": mode, "must_cio": must_cio,
                      "reason": ("特殊類別命中" if specials else
                                 ("未命中白名單" if entry is None else "命中低風險白名單"))}

    # 關卡三：核准紀錄與 tree 綁定（逐 commit，全部檢查）
    cs = commits_in_range(base, range_base)
    appr = approvals(base)
    per_commit, bad = [], []
    for c in cs:
        rec = appr.get(c)
        if not rec:
            bad.append({"commit": c, "reason": "無核准紀錄"})
            per_commit.append({"commit": c, "ok": False, "reviewer": "", "reason": "無核准紀錄"})
            continue
        if rec["verdict"] not in ("APPROVE", "APPROVE_WITH_FIXES"):
            bad.append({"commit": c, "reason": f"verdict={rec['verdict']}"})
            per_commit.append({"commit": c, "ok": False, "reviewer": rec["reviewer"],
                               "reason": f"verdict={rec['verdict']}"})
            continue
        actual = commit_tree(base, c)
        if rec["tree"] != actual:
            bad.append({"commit": c, "reason": "tree 不符（內容已變更，舊核准不得重用）"})
            per_commit.append({"commit": c, "ok": False, "reviewer": rec["reviewer"],
                               "reason": f"tree 不符 {rec['tree'][:12]}≠{actual[:12]}"})
            continue
        per_commit.append({"commit": c, "ok": True, "reviewer": rec["reviewer"]})
    checks["records"] = {"ok": not bad, "commits": len(cs), "failed": bad}

    # CIO 路徑：不得由 AUTO 蓋章代簽
    if mode == "CIO" and cs:
        auto_sealed = [c for c, r in zip(cs, per_commit) if r["ok"] and is_auto(
            appr.get(c, {}))]
        all_auto = len(auto_sealed) == len(cs) and cs
        checks["cio_signoff"] = {"ok": not all_auto,
                                 "auto_sealed": all_auto,
                                 "reviewers": [appr.get(c, {}).get("reviewer", "") for c in cs]}
        if all_auto:
            blockings.append({"id": "CIO_REQUIRED", "severity": "high",
                              "text": f"本次變更屬必須真 CIO 審查（{checks['mode']['reason']}），"
                                      f"但範圍內僅有 AUTO 型蓋章 → 拒"})
    else:
        checks["cio_signoff"] = {"ok": True, "auto_sealed": False, "note": "AUTO 路徑無需真 CIO 蓋章"}

    # producer_own（若提供）：僅作收斂，越權即拒（不靜默截斷）
    own = [_norm(p) for p in (producer_own or [])]
    if own:
        outside = sorted(set(own) - changed)
        checks["producer_own"] = {"ok": not outside, "provided": own, "outside": outside}
        if outside:
            blockings.append({"id": "OWN_OUTSIDE", "severity": "medium",
                              "text": f"producer_own 含本次未變更的路徑（越權）：{outside[:5]}"})
    else:
        checks["producer_own"] = {"ok": True, "provided": [], "note": "未提供"}

    # 特殊類別/未命中白名單 且 未被真 CIO 蓋章 → 統一在此收斂（避免重複計數）
    for b in bad:
        blockings.append({"id": "RECORD", "severity": "high",
                          "text": f"{b['commit'][:12]}：{b['reason']}"})
    # 註：未命中白名單本身不是 blocking —— 它只是「必須走真 CIO 審查」的標記，
    #     若已有真 CIO 蓋章即應放行（見上方 cio_signoff）。僅在「只有 AUTO 蓋章」時才擋。
    checks["not_allowlisted"] = {"is_info_only": True,
                                 "value": bool(mode == "CIO" and entry is None
                                               and not specials and changed)}

    ok = not blockings
    return {"ok": ok, "rc": EXIT_OK if ok else EXIT_REJECT,
            "mode": mode, "range": f"{range_base}..HEAD",
            "blocking_count": len(blockings), "blockings": blockings,
            "checks": checks, "changes": {k: ch[k] for k in sorted(ch)},
            "allow_entry": (entry or {}).get("label"),
            "per_commit": per_commit}


def main() -> int:
    ap = argparse.ArgumentParser(description="發布授權閘門（白名單 + 實際變更集合）")
    ap.add_argument("--range-base", default="origin/clean-main")
    ap.add_argument("--own", nargs="+", default=[], help="（相容參數）僅作收斂，不得擴大授權")
    ap.add_argument("--allowlist-ref", default="HEAD", help="讀取白名單的 ref（預設 HEAD）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    base = Path.cwd()
    if _git(base, ["rev-parse", "--git-dir"]).returncode != 0:
        print("❌ 不在 git repo 內", file=sys.stderr)
        return EXIT_USAGE
    res = decide(base, a.range_base, a.own, allowlist_ref=a.allowlist_ref)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        tag = "✅ 可發布" if res["ok"] else f"⛔ 拒絕（blocking {res['blocking_count']}）"
        print(f"{tag}｜模式={res['mode']}｜range={res['range']}")
        ch = res["checks"]
        print(f"  變更 {len(res['changes'])} 檔："
              + ", ".join(f"{v}:{k}" for k, v in list(res["changes"].items())[:6])
              + ("…" if len(res["changes"]) > 6 else ""))
        al = ch["allowlist"]
        print(f"  白名單：{'命中 '+str(al.get('matched')) if al.get('ok') else '未命中｜'+str(al.get('reason'))}")
        print(f"  特殊類別：{'無' if ch['special']['ok'] else ch['special']['hits']}")
        print(f"  核准紀錄：{ch['records']['commits']} 顆｜失敗 {len(ch['records']['failed'])}")
        for b in res["blockings"]:
            print(f"   ⛔ [{b['id']}] {b['text']}")
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
