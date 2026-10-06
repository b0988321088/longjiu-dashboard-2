# -*- coding: utf-8 -*-
"""dirty_gate.py — per-commit scope isolation（v2，2026-10-06 使用者裁決採方案 2）

【語義變更（核心裁決）】
  舊（v1）：dirty(整個 worktree) − declared − KNOWN_RUNTIME ≠ ∅ → rc=9
          → 任何一個未納管的 dirty（例如 runtime 心跳檔）都會讓**所有**產線一起停擺。
  新（v2）：以「本輪 commit scope」為核心
          · scope 內檔案：必須乾淨、必須驗證、必須受 gate 管控
            （staged ⊆ scope；scope 內 dirty 不得只挑一部分提交）
          · scope 外既有 dirty：不得自動納入 commit、不得阻擋本輪 commit、必須保留原狀
  這不是放寬，而是把責任邊界從「整個工作區」縮到「本次 commit」。
  核心裁決原文：「不是放寬 dirty_gate，而是讓它從『整個工作區不能髒』升級成
  『每個 commit 只能對自己的 scope 負責』。」

【commit / scope manifest】
  每一次 commit 都必須能回答：「這個 commit 預期允許哪些檔案？」
  位置：<git-dir>/scope/<label>-<timestamp>.json（不進工作樹，避免自我製造 dirty）
  稽核：<git-dir>/scope/COMMIT_SCOPE.log（比照 PUSH_LANE.log，純稽核）
  欄位：
    label        本輪標籤（寫進訊息與稽核）
    allow        本 commit 唯一允許觸碰的路徑集合（＝唯一允許 stage 的集合）
    produced     本輪實際產物（必須 ⊆ allow → 防「宣告少列本輪產物」）
    allow_extra  allow 中非本輪產物者，需人工核可＋具名理由（防藉 scope 混入無關檔案）
    expected     produced 中實際存在者之 (path, sha256) → 防「內容與預期產物不一致」

【嚴格禁止（本模組不做，呼叫端也不得代做）】
  自動 stash／reset／checkout／clean／刪除／覆寫任何 dirty 檔；
  `git add -A`；stage／commit／push scope 外檔案。

【KNOWN_RUNTIME 定位（2026-10-06 裁決）】
  降級為**資訊分類**用，不再參與判定。scope 外 dirty 本來就不阻擋本輪，
  因此不需要靠 KNOWN_RUNTIME 放行；亦不得用它掩蓋 scope isolation 這個真問題。
  保留常數與 out_of_scope() 僅為向後相容與報表可讀性。

【用法】
    from dirty_gate import build_manifest, assert_scoped_commit, assert_staged_in_scope
    m = build_manifest(label=f"regenerate_report({TODAY})", produced=_push_files, base=BASE)
    assert_scoped_commit(m, base=BASE)            # stage 前：scope 合法性＋expected 內容
    subprocess.run(["git", "add", *m["allow"]])   # 只 stage scope 內（絕不 add -A）
    assert_staged_in_scope(m, base=BASE)          # stage 後、commit 前：staged ⊆ scope

CLI（唯讀盤點）
    python dirty_gate.py --declared a b c        # 舊相容：以此清單當本輪 scope
    python dirty_gate.py --manifest <json>       # 檢查既有 manifest
    ... 可加 --staged 一併檢查 staged
"""
from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

EXIT_DIRTY = 9

SCOPE_SUBDIR = "scope"
SCOPE_LOG = "COMMIT_SCOPE.log"

# 資訊分類用（**不參與判定**）：常態 runtime 產物，每次執行必然變動。
# 2026-10-06 建立時觀測 baseline；v2 起僅用於報表可讀性，不再影響任何放行判定。
KNOWN_RUNTIME = (
    "logs/*",
    "data/ai_cost_daily.jsonl",
    "hunter_cache/*",
    "notion_bridge/*",
    "cost_log.csv",
    "*.log",
)

_BAD_CHARS = ("*", "?", "[", "]")


# ── 基礎工具 ─────────────────────────────────────────────────────────────
def _base(base=None) -> Path:
    return Path(base) if base else Path(__file__).resolve().parent


def _run_git(args, base=None, what="git"):
    st = subprocess.run(["git", *args], capture_output=True, text=True,
                        encoding="utf-8", errors="replace", cwd=str(_base(base)))
    if st.returncode != 0:
        # fail-closed：讀不到就視為 FAIL，不得放行
        raise SystemExit(f"[dirty_gate] {what} 失敗（rc={st.returncode}，視為 FAIL 不放行）："
                         f"{(st.stderr or st.stdout or '').strip()[:200]}")
    return st.stdout


def _norm(p: str) -> str:
    return str(p).replace("\\", "/").strip().strip('"')


def _sha256_file(fp: Path) -> str:
    h = hashlib.sha256()
    with open(fp, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_dir(base=None) -> Path:
    """回傳 git dir（支援 worktree）。"""
    out = _run_git(["rev-parse", "--git-dir"], base, "rev-parse --git-dir").strip()
    p = Path(out)
    return p if p.is_absolute() else (_base(base) / p)


def scope_dir(base=None, create=True) -> Path:
    d = git_dir(base) / SCOPE_SUBDIR
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def dirty_paths(base=None) -> set:
    """git status --porcelain --untracked-files=all → 相對路徑集合（rename 取新名）。"""
    out = _run_git(["status", "--porcelain", "--untracked-files=all"], base, "git status")
    res = set()
    for ln in (out or "").splitlines():
        if len(ln) < 4 or not ln.strip():
            continue
        p = _norm(ln[3:])
        if " -> " in p:
            p = p.split(" -> ")[-1].strip()
        res.add(p)
    return res


def staged_paths(base=None) -> set:
    """git diff --cached --name-only → 已 stage 的路徑集合。"""
    out = _run_git(["diff", "--cached", "--name-only"], base, "git diff --cached")
    return {_norm(l) for l in (out or "").splitlines() if l.strip()}


def out_of_scope(declared, dirty, known_runtime=KNOWN_RUNTIME):
    """（向後相容，**資訊用**）回傳不在 declared ∪ known_runtime 內的 dirty。

    v2 起不再用於阻擋判定；阻擋判定請用 manifest_violations／staged_violations。
    """
    import fnmatch

    def _keep(p):
        return any(p == d or fnmatch.fnmatch(p, d) for d in declared)

    def _rt(p):
        return any(fnmatch.fnmatch(p, k) for k in known_runtime)

    return sorted(p for p in dirty if not _keep(p) and not _rt(p))


def outside_scope(allow, dirty) -> list:
    """本輪 scope 之外的既有 dirty（不阻擋、不納入、保留原狀）。"""
    a = {_norm(x) for x in allow}
    return sorted(p for p in dirty if p not in a)


# ── manifest ────────────────────────────────────────────────────────────
def build_manifest(label, produced, allow=None, allow_extra=None, base=None,
                   write=True, hash_content=True) -> dict:
    """建立本輪 commit scope manifest。

    produced     本輪實際產物（必列；漏列會被 manifest_violations 判 STOP）
    allow        本 commit 允許觸碰的集合（預設＝produced）
    allow_extra  allow 中非本輪產物者，[{"path":..., "reason":...}]（需人工核可＋理由）
    write        是否落地到 <git-dir>/scope/（+ 稽核 log）
    """
    prod = sorted({_norm(p) for p in (produced or [])})
    alw = sorted({_norm(p) for p in (allow if allow is not None else produced or [])})
    extra = []
    for e in (allow_extra or []):
        if isinstance(e, str):
            extra.append({"path": _norm(e), "reason": ""})
        else:
            extra.append({"path": _norm(e.get("path", "")), "reason": str(e.get("reason") or "")})
    expected = []
    if hash_content:
        for p in prod:
            fp = _base(base) / p
            if fp.exists() and fp.is_file():
                expected.append({"path": p, "sha256": _sha256_file(fp)})
    m = {
        "label": str(label or ""),
        "created_at": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "allow": alw,
        "produced": prod,
        "allow_extra": extra,
        "expected": expected,
    }
    if write:
        _write_manifest(m, base)
    return m


def _write_manifest(m: dict, base=None) -> Path:
    d = scope_dir(base, create=True)
    slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in (m.get("label") or "manifest"))[:60]
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    fp = d / f"{slug}-{ts}.json"
    fp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        with open(d / SCOPE_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')}\t"
                    f"{m.get('label')}\tallow={len(m.get('allow') or [])}\t"
                    f"produced={len(m.get('produced') or [])}\tfile={fp.name}\n")
    except Exception:
        pass
    return fp


def manifest_violations(m: dict, base=None) -> list:
    """stage 前的靜態檢查（scope 自身合法性 + 預期產物內容）。"""
    v: list = []
    allow = {_norm(p) for p in (m.get("allow") or [])}
    produced = {_norm(p) for p in (m.get("produced") or [])}
    extra = m.get("allow_extra") or []
    if not allow:
        return v  # 空 scope：沒有要提交的東西，呼叫端不應 commit

    # V1：本輪產物必須在 scope 內（防「manifest 少列本班應提交檔案」）
    miss = sorted(produced - allow)
    if miss:
        v.append(f"manifest 少列本輪產物（produced ⊄ allow）{len(miss)} 檔：{miss[:10]}")

    # V2：scope 內非本輪產物者，必須經人工核可（allow_extra）並具名理由
    extra_paths = {_norm(e.get("path")) for e in extra}
    unknown = sorted(allow - produced - extra_paths)
    if unknown:
        v.append(f"allow 含非本輪產物且未經人工核可 {len(unknown)} 檔（禁止藉 scope 混入）：{unknown[:10]}")

    # V3：allow_extra 必須有具名理由
    nores = sorted(_norm(e.get("path")) for e in extra if not str(e.get("reason") or "").strip())
    if nores:
        v.append(f"allow_extra 缺具名理由（需人工核可）{len(nores)} 檔：{nores[:10]}")

    # V5：路徑合法性（不得絕對路徑、..、.git/、萬用字元）
    bad = [p for p in sorted(allow)
           if p.startswith("/") or p.startswith(".git/") or ".." in p.split("/")
           or any(c in p for c in _BAD_CHARS) or not p]
    if bad:
        v.append(f"allow 含不合法路徑（絕對／../／.git/／萬用字元）：{bad[:10]}")

    # V4：預期產物內容必須與宣告一致
    for e in (m.get("expected") or []):
        p = _norm(e.get("path"))
        fp = _base(base) / p
        if not fp.exists():
            v.append(f"預期產物不存在：{p}")
        elif _sha256_file(fp) != e.get("sha256"):
            v.append(f"預期產物內容已變（sha256 不符，宣告後被改寫）：{p}")
    return v


def staged_violations(m: dict, base=None) -> list:
    """stage 後、commit 前的動態檢查。"""
    v: list = []
    allow = {_norm(p) for p in (m.get("allow") or [])}
    if not allow:
        return v
    stg = staged_paths(base)
    dirty = dirty_paths(base)

    # V7：staged 必須是 scope 的子集合（絕對禁止 stage scope 外檔案）
    outside = sorted(stg - allow)
    if outside:
        v.append(f"staged 含 scope 外檔案 {len(outside)} 檔（絕對禁止納入 commit）：{outside[:10]}")

    # V8：scope 內 dirty 必須全部 stage（不得只挑一部分提交）
    not_staged = sorted((dirty & allow) - stg)
    if not_staged:
        v.append(f"scope 內 dirty 未 stage {len(not_staged)} 檔（不得只挑一部分提交）：{not_staged[:10]}")
    return v


# ── 對外斷言 ────────────────────────────────────────────────────────────
def _emit(label, viol, allow_n, base=None, hard=True) -> list:
    if not viol:
        print(f"[dirty_gate] OK  {label}：scope 內 {allow_n} 檔受控（乾淨／內容相符／"
              f"不得只挑一部分提交）")
        return []
    print(f"[dirty_gate] STOP {label}：scope 檢查未過 {len(viol)} 項 → 不 auto-commit")
    for x in viol:
        print("    - " + x)
    print("[dirty_gate] 人工檢視後自行處理（本閘門不代為 stash／reset／checkout／clean／commit）")
    if hard:
        raise SystemExit(EXIT_DIRTY)
    return viol


def assert_scoped_commit(manifest, base=None, label="", hard=True, stage_check=False) -> list:
    """stage 前：檢查 scope 合法性與預期產物內容；scope 外 dirty 僅揭露、不阻擋。

    stage_check=True 時一併做 stage 後檢查（單呼叫版管線可用）。
    """
    lbl = label or manifest.get("label") or "scoped-commit"
    allow = manifest.get("allow") or []
    viol = manifest_violations(manifest, base)
    if stage_check:
        viol += staged_violations(manifest, base)
    out = _emit(lbl, viol, len(allow), base, hard)
    _report_outside(manifest, base, lbl)
    return out


def assert_staged_in_scope(manifest, base=None, label="", hard=True) -> list:
    """stage 後、commit 前：staged 必須完全落在本輪 scope 內。"""
    lbl = label or manifest.get("label") or "scoped-commit"
    return _emit(lbl + " / staged", staged_violations(manifest, base),
                 len(manifest.get("allow") or []), base, hard)


def _report_outside(manifest, base=None, label="") -> None:
    """揭露 scope 外既有 dirty：不阻擋、不納入、保留原狀（純資訊）。"""
    try:
        rest = outside_scope(manifest.get("allow") or [], dirty_paths(base))
    except SystemExit:
        return
    if rest:
        print(f"[dirty_gate] ℹ️ {label}：scope 外既有 dirty {len(rest)} 檔"
              f"（不阻擋本輪、不納入 commit、保留原狀）：")
        for p in rest[:20]:
            print(f"    · {p}")
        if len(rest) > 20:
            print(f"    ... 其餘 {len(rest) - 20} 檔")


def assert_clean_scope(declared, base=None, label="", hard=True) -> list:
    """向後相容 wrapper：以 declared 當本輪 commit scope，套用 v2 語義。

    ⚠️ 語義已變更：由「整個 worktree 必須乾淨」改為「本輪 scope 受控、scope 外不阻擋」。
    """
    m = build_manifest(label=label or "assert_clean_scope", produced=list(declared or []),
                       base=base, write=False)
    return assert_scoped_commit(m, base=base, label=label, hard=hard)


# ── CLI（唯讀）────────────────────────────────────────────────────────────
if __name__ == "__main__":
    argv = sys.argv[1:]
    stage_check = "--staged" in argv
    if "--manifest" in argv:
        fp = argv[argv.index("--manifest") + 1]
        m = json.loads(Path(fp).read_text(encoding="utf-8"))
        lbl = f"CLI:{m.get('label')}"
    else:
        decl = []
        if "--declared" in argv:
            decl = argv[argv.index("--declared") + 1:]
        m = build_manifest(label="CLI", produced=decl, base=None, write=False)
        lbl = "CLI"
    viol = _emit(lbl, manifest_violations(m, None) + (staged_violations(m, None) if stage_check else []),
                 len(m.get("allow") or []), None, hard=False)
    _report_outside(m, None, lbl)
    print(f"\n本輪 scope={len(m.get('allow') or [])} 檔；違規={len(viol)} 項")
    sys.exit(EXIT_DIRTY if viol else 0)
