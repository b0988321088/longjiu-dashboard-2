# -*- coding: utf-8 -*-
"""perf_gate_contract.py — 績效閘門契約層 F1–F4（Phase 03 隔離實作）

設計依據：.hermes/plans/2026-10-09_220000-perf-gate-decoupling-design.md（v2）
目的：修正「Task 1+2 零回歸」與「現行環境紅燈」的跨任務／跨時間耦合。

四個獨立斷言（互不冒充）：
  F1 封版契約      固定歷史基準 2d1b9ed2；與被審對象完全脫鉤
  F2 本輪範圍契約  四層盤點：候選 commit／未提交變更／未追蹤／產物依賴
  F3 環境健康度    受治理基準快照（完整性、有效期、雜湊、禁止回吞）
  F4 發布一致性    核准來源／建置來源／產物雜湊／推送內容

唯讀：本模組不寫任何 repo 產物。
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

# ── 固定歷史基準（封版 commit，保留其歷史比較用途；不得因它讓測試失敗就移除）──
BASELINE_SHA = "2d1b9ed2"
BASELINE_FILES = [
    "performance_core.py",
    "build_mtd_report.py",
    "build_investment_performance.py",
    "tools/verify_performance_core_task12.py",
]

# ── 2026-10-05 使用者核准「自白名單釋放」的兩條；不得藉快照更新重新吸收（R-e／R2）──
RELEASED_20261005 = [
    "Pending schema 五欄齊備（26 筆一次遷移）",
    "status 正規化為四態（原字串保留 status_raw）",
]

# ── 快照（受治理）──
SNAPSHOT_PATH = REPO / "tools" / "gate_baseline_dividend_caliber.json"
SNAPSHOT_REQUIRED_FIELDS = ("as_of", "expires_at", "created_by", "updated_by", "reason",
                            "content_sha256", "approval_ref", "fail_set")

# 快照的更新／核准不得由「產生該次 FAIL 的同一流程」執行（R-c／T10／T13）
SNAPSHOT_FORBIDDEN_UPDATERS = ("check_dividend_caliber", "verify_performance_core_task12",
                               "verify_performance_monthly")
# 註（2026-10-09 CIO 第二輪 minor）：**不**把代理（hermes-agent／龍九）列入禁列。
#   禁列對象是「產生該次 FAIL 的同一流程」（R-c），代理只是執行使用者授權的更新；
#   授權獨立性由 approval_ref（外部授權來源）＋不可覆寫歷史（R-a～R-d）保證。
#   檢查已改為同時比對 updated_by 與 executed_by，避免閘門名藏進任一欄而失效。

CHECK_NAME_BRACKETS = re.compile(r"[（(]")


def norm_check_name(s) -> str:
    """檢查項名稱正規化：去掉括號註解後比對（2026-10-09 CIO minor）。

    檢查名會隨口徑修訂而變（例：'Pending schema 五欄齊備（26 筆一次遷移）' → '（全卡動態）'），
    全字串相等比對會讓『已釋放規則被回吞』的攔阻靜默失效 → 改為比對括號前的主體。
    """
    return CHECK_NAME_BRACKETS.split(str(s))[0].strip()

ENV_JSON_MARKER = "ENV_JSON:"


def git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd or REPO), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def fail_set_sha(fail_set) -> str:
    """快照內容雜湊：對排序後的 fail_set 取 sha256（防事後改寫，T16）。"""
    canon = "\n".join(sorted(str(x) for x in fail_set))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def _parse_env_json(stdout: str):
    for line in (stdout or "").splitlines():
        if line.strip().startswith(ENV_JSON_MARKER):
            try:
                return json.loads(line.strip()[len(ENV_JSON_MARKER):].strip())
            except Exception:
                return None
    return None


# ══════════════════════════════ F1 ══════════════════════════════

def f1_baseline_contract(baseline_sha: str = BASELINE_SHA) -> dict:
    """封版契約：2d1b9ed2 的內容與範圍仍可被驗證。與被審對象無關（時間相依＝無）。"""
    out = {"id": "F1", "name": "封版契約", "checks": [], "env_json": None}

    def ck(label, cond, detail=""):
        out["checks"].append({"label": label, "ok": bool(cond), "detail": str(detail)[:200]})

    r = subprocess.run(
        [PY, str(REPO / "tools" / "verify_performance_core_task12.py"), baseline_sha],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace")
    stdout = r.stdout or ""
    out["env_json"] = _parse_env_json(stdout)

    _sha = git("rev-parse", f"{baseline_sha}^{{commit}}").strip().splitlines()
    _sha = _sha[0] if _sha else ""
    ck("基準 commit 可解析", len(_sha) == 40, _sha[:12])

    st = git("show", "--stat", "--format=", _sha).strip()
    ck("基準 commit 只動封版 4 檔",
       all(f in st for f in BASELINE_FILES) and st.count("|") == len(BASELINE_FILES),
       st.replace("\n", " ")[:160])

    lines = stdout.splitlines()
    running = [ln.strip().strip("=").strip() for ln in lines if "驗收：" in ln]
    ck("封版契約檢查器 rc=0（只由契約檢查決定）", r.returncode == 0,
       running[0] if running else f"rc={r.returncode}")
    failed = [ln.split("FAIL:", 1)[1].strip() for ln in lines if ln.strip().startswith("FAIL:")]
    ck("封版契約無未過檢查項", not failed, "、".join(failed) if failed else "0 條")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


# ══════════════════════════════ F2 ══════════════════════════════

def f2_scope(candidate: str = "HEAD", allowed_files=None, approval_ref: str = "",
             deliverables=None, worktree_root: Path | None = None) -> dict:
    """本輪範圍契約：四層盤點。任何無法判定 → FAIL-CLOSED（不得預設通過）。"""
    out = {"id": "F2", "name": "本輪範圍契約", "checks": [],
           "worktree_dirty": [], "untracked": [], "out_of_scope": []}
    root = Path(worktree_root or REPO)

    def ck(label, cond, detail=""):
        out["checks"].append({"label": label, "ok": bool(cond), "detail": str(detail)[:300]})

    allowed = [a for a in (allowed_files or []) if a]

    # (a) 允許範圍未提供 → FAIL-CLOSED（Q1/T11）
    if not allowed:
        ck("允許範圍已提供（呼叫端明示）", False,
           "FAIL-CLOSED：未提供 --allowed-files，不得預設「範圍不限」")
        out["ok"] = False
        return out
    # (b) 核准紀錄缺失 → FAIL-CLOSED（Q1/T15）
    if not approval_ref.strip():
        ck("獨立 CIO 核准紀錄已提供", False,
           "FAIL-CLOSED：缺 approval_ref，核准對象無法核對")
        out["ok"] = False
        return out
    ck("允許範圍已提供（呼叫端明示）", True, f"{len(allowed)} 檔")
    ck("獨立 CIO 核准紀錄已提供", True, approval_ref[:80])

    # ① 候選 commit 的變更範圍
    _sha = git("rev-parse", f"{candidate}^{{commit}}", cwd=root).strip().splitlines()
    _sha = _sha[0] if _sha else ""
    if len(_sha) != 40:
        ck("候選版本可解析", False, candidate)
        out["ok"] = False
        return out
    # ① 候選 commit 的變更範圍
    #   2026-10-09（CIO 阻擋 #1）：原用 `git show --name-only`（未帶 -M），rename 只吐**新路徑**，
    #   導致「舊路徑已宣告」的 rename 被判為範圍外 → 本批被自己的閘門永久阻擋、發布路徑不可達。
    #   改為 `--name-status -M`：rename 兩側都認，任一側在允許範圍內即視為已宣告（不再單看新路徑）。
    _pairs: list[list[str]] = []
    for _ln in git("show", "--name-status", "-M", "--format=", _sha, cwd=root).splitlines():
        _p = [x.strip() for x in _ln.split("\t")[1:] if x.strip()]
        if _p:
            _pairs.append(_p)
    changed = sorted({p for grp in _pairs for p in grp})
    # 2026-10-09（CIO 第二輪 minor）：原「任一側在 allowed 即算已宣告」可被洗入——
    #   把未宣告檔 `git mv` 成已宣告檔名即可過關（審查者以臨時 repo 實測）。
    #   改為**每一側都須在 allowed**；本批 rename 兩側本就都已宣告，零成本封住。
    outside = sorted({p for grp in _pairs if not all(x in allowed for x in grp) for p in grp})
    out["out_of_scope"] = outside
    ck("①候選 commit 變更集 ⊆ 允許範圍", not outside,
       "、".join(outside) if outside else f"{len(changed)} 檔（{len(_pairs)} 筆變更）全在範圍內")

    # ② 未提交變更 / ③ 未追蹤檔案
    porc = git("status", "--porcelain", cwd=root).splitlines()
    dirty = sorted(l[3:].strip() for l in porc if l[:2].strip() and l[3:].strip())
    untracked = sorted(l[3:].strip() for l in porc if l[:2] == "??")
    out["worktree_dirty"] = dirty
    out["untracked"] = untracked

    dels = [d for d in (deliverables or []) if d]
    if not dels:
        ck("交付清單已明示", False,
           "FAIL-CLOSED：未提供 deliverables，無法證明工作樹污染不會被納入交付")
        out["ok"] = False
        return out
    ck("交付清單已明示", True, f"{len(dels)} 項")
    collide = sorted(set(dels) & (set(dirty) | set(untracked)))
    ck("②③交付清單 ∩ (未提交變更 ∪ 未追蹤) 為空", not collide,
       ("交付項同時存在未提交/未追蹤異動：" + "、".join(collide)) if collide
       else f"dirty {len(dirty)} 檔、untracked {len(untracked)} 檔，均不在交付清單內（未納入本輪交付）")

    # ④ 交付產物與依賴存在
    missing = [d for d in dels if not (root / d).exists()]
    ck("④交付產物與依賴檔案存在", not missing, "、".join(missing) if missing else f"{len(dels)} 項齊備")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


# ══════════════════════════════ F3 ══════════════════════════════

def load_snapshot(path: Path | None = None):
    p = Path(path or SNAPSHOT_PATH)
    if not p.exists():
        return None, "快照檔不存在"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"快照無法解析：{e}"
    if not isinstance(d, dict):
        return None, "快照格式非物件"
    miss = [f for f in SNAPSHOT_REQUIRED_FIELDS if not d.get(f)]
    if miss:
        return None, "快照缺必要欄位：" + "、".join(miss)
    if not isinstance(d.get("fail_set"), list):
        return None, "fail_set 非陣列"
    return d, ""


def f3_environment(env_json: dict | None, snapshot_path: Path | None = None,
                   today: str | None = None) -> dict:
    """環境健康度：獨立呈現，不計入 Task 1+2 契約。任何不可信 → FAIL-CLOSED（Q2/T6/T9）。"""
    import datetime as _dt
    out = {"id": "F3", "name": "環境健康度", "checks": [],
           "new_fails": [], "baseline_fails": [], "scope_class": [], "env_unavailable": False}
    today = today or _dt.date.today().isoformat()

    def ck(label, cond, detail=""):
        out["checks"].append({"label": label, "ok": bool(cond), "detail": str(detail)[:300]})

    if not env_json:
        ck("環境閘門輸出可取得", False, "FAIL-CLOSED：check_dividend_caliber 輸出無法解析")
        out["env_unavailable"] = True
        out["ok"] = False
        return out
    current = [n for n in (env_json.get("fail_names") or [])]

    snap, err = load_snapshot(snapshot_path)
    if snap is None:
        ck("基準快照可用（存在／可解析／欄位齊備）", False, f"FAIL-CLOSED：{err}")
        out["ok"] = False
        return out
    ck("基準快照可用（存在／可解析／欄位齊備）", True,
       f"as_of={snap['as_of']}／expires_at={snap['expires_at']}／by={snap['created_by']}")

    # 有效期（Q2）
    ck("基準快照未過期", str(snap["expires_at"]) >= today,
       f"expires_at={snap['expires_at']} vs today={today}")

    # 內容雜湊（R-d／T16）
    expect = fail_set_sha(snap["fail_set"])
    ck("快照 content_sha256 與 fail_set 相符", expect == snap["content_sha256"],
       f"實得 {expect[:16]}／宣稱 {str(snap['content_sha256'])[:16]}")

    # 禁止回吞已釋放規則（R-e／T17）
    _rel_norm = {norm_check_name(x) for x in RELEASED_20261005}
    swallow = sorted({x for x in snap["fail_set"] if norm_check_name(x) in _rel_norm})
    ck("快照未回吞 2026-10-05 已釋放規則", not swallow,
       "、".join(swallow) if swallow else "0 條")

    # 獨立核准／職責分離（R-c／T10／T13）
    # 2026-10-09（CIO 第二輪 minor）：語意已拆為 updated_by（授權來源）／executed_by（執行者），
    #   只讀 updated_by 會使檢查變死碼 → 兩欄一起比對（閘門名寫在哪一欄都攔得到）。
    _upd = str(snap.get("updated_by", "")) + "｜" + str(snap.get("executed_by", ""))
    _collide = [u for u in SNAPSHOT_FORBIDDEN_UPDATERS if u in _upd]
    ck("快照更新者非產生該 FAIL 的同一流程（職責分離）", not _collide,
       (f"更新者={_upd} 與 {_collide} 重疊 → 自我核准，不得採信") if _collide
       else f"updated_by={_upd}｜approval_ref={str(snap.get('approval_ref'))[:40]}")

    base = set(snap["fail_set"])
    scope = [n for n in current if n.startswith("變更範圍")]
    new = [n for n in current if n not in base and not n.startswith("變更範圍")]
    out["new_fails"] = sorted(new)
    out["baseline_fails"] = sorted(n for n in current if n in base)
    out["scope_class"] = sorted(scope)

    ck("白名單外新增 FAIL 為空", not new,
       ("、".join(out["new_fails"])) if new else
       f"新增 0 條｜既有 {len(out['baseline_fails'])} 條（獨立呈現，不計入 Task 1+2）")
    # 範圍類獨立呈現（Q3：不濾除，必須可見）
    ck("範圍類紅燈獨立呈現（未被靜默排除）", True,
       ("、".join(out["scope_class"])) if out["scope_class"] else "0 條")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


# ══════════════════════════════ F4 ══════════════════════════════

def _git_dir(root=None) -> Path | None:
    r = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(root or REPO),
                       capture_output=True, text=True)
    d = (r.stdout or "").strip()
    if not d:
        return None
    p = Path(d)
    return p if p.is_absolute() else (Path(root or REPO) / p)


def head_tree(root=None) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=str(root or REPO),
                       capture_output=True, text=True)
    return (r.stdout or "").strip()


def load_cio_approved(root=None, path=None) -> dict:
    """讀 CIO 核准紀錄（tab 分隔、append-only）→ {tree: [verdict, ...]}。

    2026-10-09 使用者裁決：F4 的正式核准來源＝cio_approve.py 的核准紀錄（唯一入口）。
    path 僅為**測試接縫**（指向沙箱檔），不改變「必須有 APPROVE 才放行」的語意。
    """
    if path is not None:
        f = Path(path)
    else:
        gd = _git_dir(root)
        f = (gd / "CIO_APPROVED") if gd else None
    out: dict = {}
    if not f or not f.exists():
        return out
    for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        r = line.split("\t")
        if len(r) >= 4:
            out.setdefault(r[1].strip(), []).append(r[3].strip())
    return out


def load_publish_scope(path=None) -> dict:
    """F2／F4 的宣告來源：獨立治理宣告檔（呼叫端不得自行擴張範圍）。"""
    p = Path(path) if path else (REPO / "governance" / "publish_scope.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def f4_publish_consistency(approval_tree: str = "", candidate_tree: str = "",
                           build_source: str = "", artifacts=None,
                           approved_artifacts=None, pushed_manifest: str = "",
                           approval_file=None) -> dict:
    """發布一致性：核准來源／建置來源／產物雜湊／推送內容 四者須一致（T8/T14/T18）。"""
    out = {"id": "F4", "name": "發布一致性", "checks": []}

    def ck(label, cond, detail=""):
        out["checks"].append({"label": label, "ok": bool(cond), "detail": str(detail)[:300]})

    # 2026-10-09（CIO 阻擋 #2）：原設計「呼叫端傳 approval_tree 即跳過核准查核」＝可繞過。
    #   改為：**一律**以 CIO 核准紀錄（預設 .git/CIO_APPROVED；測試以 approval_file 注入沙箱檔）
    #   驗證候選 tree 是否 APPROVE；呼叫端參數只能**收斂**（不得覆寫、不得取代查核）。
    _scope = load_publish_scope()
    if not candidate_tree.strip():
        candidate_tree = head_tree()
    if not build_source.strip():
        build_source = candidate_tree
    # 2026-10-09（CIO 第二輪 blocking）：原以「呼叫端傳 approval_file」作測試接縫，
    #   但該參數一旦對呼叫端開放，就等於**可取代 CIO 核准查核**（審查者實測：自製一份
    #   四欄 tab 檔指向候選 tree → f4 全項通過）。封法兩層：
    #   ①生產入口（CLI）不得暴露此參數（見 verify_performance_monthly.py 已移除）
    #   ②此接縫只允許 repo 外的路徑；repo 內（可被 commit／發布的檔案）一律拒絕採信。
    _apf = None
    if approval_file is not None:
        _p = Path(approval_file)
        try:
            _inside = _p.resolve().is_relative_to(REPO.resolve())
        except Exception:
            _inside = False
        if _inside:
            ck("已取得 CIO 核准 tree 綁定", False,
               f"FAIL-CLOSED：核准來源不得指向 repo 內檔案（{approval_file}）→ 拒絕採信")
            out["ok"] = False
            return out
        _apf = _p
    _appr = load_cio_approved(path=_apf)
    if not _appr:
        ck("已取得 CIO 核准 tree 綁定", False,
           f"BLOCKED：無 CIO 核准紀錄（{approval_file or '預設 .git/CIO_APPROVED'}）→ 不得發布")
        out["ok"] = False
        return out
    if "APPROVE" not in _appr.get(candidate_tree, []):
        ck("已取得 CIO 核准 tree 綁定", False,
           f"BLOCKED：核准紀錄共 {len(_appr)} 筆，無本候選 tree {candidate_tree[:16]} 的 APPROVE "
           f"→ 未經核准，不得發布（呼叫端參數不得取代此查核）")
        out["ok"] = False
        return out
    if approval_tree.strip() and approval_tree.strip() != candidate_tree:
        ck("已取得 CIO 核准 tree 綁定", False,
           f"FAIL：呼叫端宣稱核准 tree {approval_tree[:16]} ≠ 候選 {candidate_tree[:16]}（不得覆寫）")
        out["ok"] = False
        return out
    approval_tree = candidate_tree
    ck("已取得 CIO 核准 tree 綁定", True, f"{approval_tree[:16]}（紀錄 APPROVE）")
    if not approved_artifacts:
        approved_artifacts = dict(_scope.get("artifact_hashes") or {})
    ck("實際建置來源 == 核准來源", build_source == approval_tree,
       f"build={build_source[:16]}／approved={approval_tree[:16]}")
    ck("待發布 tree == 核准 tree", candidate_tree == approval_tree,
       f"candidate={candidate_tree[:16]}／approved={approval_tree[:16]}")

    arts = artifacts or {}
    appr = approved_artifacts or {}
    if not appr:
        ck("核准產物清單已提供", False, "FAIL-CLOSED：無核准產物清單，無法核對內容雜湊")
        out["ok"] = False
        return out
    mismatch = sorted(k for k, v in arts.items() if appr.get(k) != v)
    ck("產物內容雜湊 == 核准清單", not mismatch,
       "、".join(mismatch) if mismatch else f"{len(arts)} 項相符")
    ck("推送內容與核准清單一致", (not pushed_manifest) or pushed_manifest == approval_tree,
       pushed_manifest[:16] if pushed_manifest else "(無推送紀錄)")

    out["ok"] = all(c["ok"] for c in out["checks"])
    return out


# ══════════════════════════════ 總和 ══════════════════════════════

def evaluate(*, baseline_sha: str = BASELINE_SHA, candidate: str = "HEAD",
             allowed_files=None, approval_ref: str = "", deliverables=None,
             snapshot_path=None, worktree_root=None,
             approval_tree: str = "", build_source: str = "", candidate_tree: str = "",
             artifacts=None, approved_artifacts=None, pushed_manifest: str = "",
             approval_file=None,
             env_json=None, f1_precomputed: dict | None = None) -> dict:
    # f1_precomputed 為**測試接縫**：讓對抗性測試台不必為每個情境重跑慢速 F1。
    # candidate_tree（tree hash）與 candidate（rev，如 HEAD）語意不同，必須分開傳；
    #   2026-10-09 測試台 T7 抓到原本混用會讓 F4 恆為不符（真缺陷）。
    f1 = f1_precomputed if f1_precomputed is not None else f1_baseline_contract(baseline_sha)
    f2 = f2_scope(candidate, allowed_files, approval_ref, deliverables, worktree_root)
    f3 = f3_environment(env_json if env_json is not None else f1.get("env_json"), snapshot_path)
    f4 = f4_publish_consistency(approval_tree, candidate_tree, build_source,
                                artifacts, approved_artifacts, pushed_manifest,
                                approval_file=approval_file)
    task_contract_ok = bool(f1["ok"] and f2["ok"] and f4["ok"])
    return {
        "f1": f1, "f2": f2, "f3": f3, "f4": f4,
        "task_contract": {"ok": task_contract_ok,
                          "members": {"F1": f1["ok"], "F2": f2["ok"], "F4": f4["ok"]}},
        "environment": {"ok": f3["ok"], "id": "F3"},
        "rc": 0 if (task_contract_ok and f3["ok"]) else 1,
    }
