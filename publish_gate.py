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
import re
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
NEVER_AUTO_SUFFIX = (".bak", ".backup", ".old", ".orig", ".tmp",
                     # 憑證／金鑰／機密材料：一律不得自動發布
                     ".env", ".envrc", ".pem", ".key", ".crt", ".cer", ".p12", ".pfx",
                     ".jks", ".keystore", ".asc", ".gpg", ".kdbx", ".ppk", ".der")
CODE_SUFFIX = (".py", ".sh", ".bat", ".ps1", ".cmd", ".toml", ".yml", ".yaml",
               ".js", ".ts", ".sql", ".json5", ".ini", ".conf", ".cfg", ".xml",
               ".properties", ".exe", ".bin", ".jar", ".so", ".dll", ".dylib", ".msi")

# ---------------------------------------------- append-only 受限車道（PG-20261012 v4）
# 使用者 2026-10-12 裁決（有條件核准設計）：
#   dashboard_decisions.json 與 data/decision_intake_receipts.jsonl 是決策權威紀錄，
#   屬 NEVER_AUTO_EXACT／NEVER_AUTO_PREFIX（永不得自動發布）；但 append_dashboard_decisions.py
#   每筆入庫都會產生一顆「純資料追加」commit，該 commit 永遠拿不到真 CIO 章 →
#   留在 origin/<branch>..HEAD 上會讓整段範圍對所有 producer 變 CIO（推不動的 commit＝產線死鎖）。
#
#   裁決：不放寬整個決策資料目錄、不取消 CIO 審查，只開一條「受限自動車道」——
#     ① 逐字限定這兩條路徑（不得含樣式、不得夾帶其他路徑）
#     ② 條目必須標明 producer
#     ③ 放行前由閘門逐 commit 重算內容不變量（不靠呼叫端自稱的名字）
#     ④ 任一不變量不符 → 直接拒絕（fail-closed），不靜默降級為 CIO 放行
APPEND_ONLY_PATHS = ("dashboard_decisions.json", "data/decision_intake_receipts.jsonl")
DECISIONS_PATH, RECEIPTS_PATH = APPEND_ONLY_PATHS
APPEND_ONLY_DECISION_KEYS = ("id", "timestamp", "agent", "task", "summary", "status", "source")
INDEX_REV = ":0"  # git 索引（staged）內容的 revision spec


def _git(base: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(base), capture_output=True, text=True, timeout=timeout)


def _norm(p: str) -> str:
    """正規化路徑。

    只剝**成對的開頭 `./`**，不可用 `lstrip("./")`——那會把開頭多個 `.` 一併剝掉，
    使 `.env` 變 `env`、`.githooks/pre-push` 變 `githooks/pre-push`，
    讓 NEVER_AUTO_SUFFIX 的 `.env` 與 NEVER_AUTO_PREFIX 的 `.githooks/`、`.hermes/`
    永遠比不中（＝這兩個保護形同不存在）。2026-10-12 CIO 審查 F1 指出，舊碼即有此盲點。
    """
    s = str(p).replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


# ------------------------------------------------- 純資料批次授權（PG-20261011 v3）

def glob_match(pattern: str, path: str) -> bool:
    """單層 glob：'*' 只匹配同一路徑段落內的字元（不跨 '/'）。"""
    rx = "^" + re.escape(_norm(pattern)).replace(r"\*", "[^/]*") + "$"
    return re.match(rx, _norm(path)) is not None


def spec_items(entry: dict) -> list[str]:
    """條目的規格元素（allow 為字面路徑；patterns 為單層 glob）。"""
    out: list[str] = []
    for key in ("allow", "patterns"):
        v = entry.get(key)
        if isinstance(v, list):
            out.extend(str(x) for x in v)
    return out


def spec_unsafe_reason(item: str) -> str | None:
    """白名單條目規格安全檢查（fail-closed）。

    條目是「明確授權」，但不得因寫得太寬而實質變成通用放行
    （＝使用者裁決「不得把未知檔案一律視為可自動核准」的程式化防線）。
    規則：① 不得以 '*' 開頭 ② '*' 前的字面前綴需 ≥3 字元
         ③ 副檔名位置不得含 '*' ④ 副檔名不得落於備份／憑證／程式類
         ⑤ 不得落於強制 CIO 前綴 ⑥ 不得恰為強制 CIO 檔名
    """
    raw = str(item).strip()
    if not raw:
        return "空字串"
    p = _norm(raw)
    lp = p.lower()
    if "*" not in p:
        if lp in {x.lower() for x in NEVER_AUTO_EXACT}:
            return f"不得授權強制 CIO 檔：{raw}"
        for pre in NEVER_AUTO_PREFIX:
            if lp.startswith(pre.lower()):
                return f"不得授權強制 CIO 前綴（{pre}）：{raw}"
        for suf in tuple(NEVER_AUTO_SUFFIX) + tuple(CODE_SUFFIX):
            if lp.endswith(str(suf).lower()):
                return f"不得授權禁止副檔名（{suf}）：{raw}"
        return None
    if p.startswith("*"):
        return f"樣式不得以 '*' 開頭（無路徑約束＝實質通用放行）：{raw}"
    head, _, tail = p.partition("*")
    if len(head) < 3:
        return f"'*' 前的字面前綴過短（<3 字元）：{raw}"
    if "." in tail and "*" in tail.split(".", 1)[1]:
        return f"副檔名位置不得含 '*'：{raw}"
    if "." not in tail:
        return f"樣式必須明示副檔名（不得寫可吸收任意副檔名的樣式）：{raw}"
    if "." in tail:
        ext = "." + tail.rsplit(".", 1)[1]
        for suf in tuple(NEVER_AUTO_SUFFIX) + tuple(CODE_SUFFIX):
            if ext.lower() == str(suf).lower():
                return f"樣式副檔名落於禁止類（{suf}）：{raw}"
    for pre in NEVER_AUTO_PREFIX:
        if head.lower().startswith(pre.lower()):
            return f"樣式前綴落於強制 CIO 前綴（{pre}）：{raw}"
    return None


def spec_matches(items: list[str], path: str) -> bool:
    """path 是否落在條目規格內（字面相等或 glob 命中）。"""
    p = _norm(path)
    for it in items:
        s = _norm(it)
        if "*" in s:
            if glob_match(s, p):
                return True
        elif s == p:
            return True
    return False


def spec_specificity(items: list[str]) -> tuple[int, int]:
    """規格嚴謹度排序鍵（供 reverse=True 排序）：字面比樣式嚴謹（字面前綴給大值）；
    同樣含樣式時，前綴越長越嚴謹；元素越少越嚴謹（以負數表達）。
    """
    lits = [len(_norm(i).partition("*")[0]) for i in items if "*" in _norm(i)]
    lit = min(lits) if lits else 10 ** 6
    return (lit, -len(items))



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
    """讀**已提交版本**的產物白名單（工作區改寫無效）。

    v3：條目可用 `allow`（字面路徑）或 `patterns`（單層 glob）。
    載入時做規格安全檢查（fail-closed）——任一條目寫得過寬
    （以 '*' 開頭、副檔名含 '*'、指向程式／治理／備份類）
    即整份白名單視為不可用，不靜默忽略該條目。
    """
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
        if not isinstance(e, dict):
            return None, f"白名單條目格式錯誤：{e!r}"
        items = spec_items(e)
        if not items:
            return None, f"白名單條目格式錯誤（allow／patterns 皆空）：{e!r}"
        if any(not str(x).strip() for x in items):
            return None, "白名單條目含空字串"
        for it in (e.get("allow") or []):
            if "*" in str(it):
                return None, f"allow 為字面路徑、不得含 '*'（需要樣式請改用 patterns）：{it}"
        # append_only 受限車道（PG-20261012 v4）：唯一能逐字列出受限兩檔的條目型態。
        # 條件缺一即整份白名單不可用（fail-closed），不做「忽略該條目」的靜默降級。
        if e.get("append_only") is True:
            if not str(e.get("producer") or "").strip():
                return None, f"append_only 條目必須標明 producer（產物歸屬）：{e.get('label')}"
            for it in items:
                if "*" in str(it) or _norm(it) not in APPEND_ONLY_PATHS:
                    return None, (f"append_only 條目只能逐字列出受限兩檔、"
                                  f"不得含樣式或夾帶其他路徑（{e.get('label')}）：{it}")
            continue  # 兩檔本在 NEVER_AUTO 內；僅此受限車道下放行，其餘檢查不適用
        if not str(e.get("producer") or "").strip() and "patterns" in e:
            return None, f"含 patterns 的條目必須標明 producer（產物歸屬）：{e.get('label')}"
        for it in items:
            why = spec_unsafe_reason(it)
            if why:
                return None, f"白名單條目規格過寬／越界（{e.get('label')}）：{why}"
    return m, "ok"


def match_entry(changed: set[str], allowlist: dict) -> tuple[dict | None, str]:
    """找出「本次變更全部落在其規格內」的白名單條目；無則回 None。

    命中條件：changed 的**每一個**檔案都落在該條目的 allow／patterns 內。
    變更集合為空時不得命中任何條目（避免空集合被任何條目吸收）。
    """
    if not changed:
        return None, "本次變更為空"
    hits = []
    for e in allowlist["entries"]:
        items = spec_items(e)
        if items and all(spec_matches(items, p) for p in changed):
            hits.append(e)
    if not hits:
        return None, "本次變更不在任何已核准的低風險白名單內"
    # 取最嚴謹者（字面比樣式嚴謹；前綴越長、元素越少越嚴謹）作為判定依據，
    # 避免寬鬆條目意外吸收本次變更。
    best = sorted(hits, key=lambda e: spec_specificity(spec_items(e)), reverse=True)[0]
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


# ------------------------------------------------- append-only 不變量驗證器
# 只驗「內容事實」，不驗「誰說的」：呼叫端自稱 producer／--script 名稱一律不採信。

def _git_bytes(base: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    """取 blob 專用：**不可**用 text=True（換行轉換會讓逐位元比對失真）。"""
    return subprocess.run(["git", *args], cwd=str(base), capture_output=True, timeout=timeout)


def _blob(base: Path, rev: str, path: str) -> bytes | None:
    """rev 內容的 path 原始位元組；不存在／讀不到回 None。rev=INDEX_REV 讀索引。"""
    spec = f"{INDEX_REV}:{path}" if rev == INDEX_REV else f"{rev}:{path}"
    r = _git_bytes(base, ["show", spec])
    return r.stdout if r.returncode == 0 else None


def _commit_changed(base: Path, rev: str) -> tuple[dict[str, str] | None, str]:
    r = _git(base, ["diff-tree", "--no-commit-id", "--name-status", "-M", "-r", rev])
    if r.returncode != 0:
        return None, f"讀 {rev[:12]} 變更清單失敗：{(r.stderr or '').strip()[:80]}"
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st = parts[0][:1]
        path = parts[2] if (st == "R" and len(parts) >= 3) else parts[1]
        out[_norm(path)] = st
    return out, "ok"


def _staged_changed(base: Path) -> tuple[dict[str, str] | None, str]:
    r = _git(base, ["diff", "--cached", "--name-status", "-M", "HEAD"])
    if r.returncode != 0:
        return None, f"讀 staged 變更清單失敗：{(r.stderr or '').strip()[:80]}"
    out: dict[str, str] = {}
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st = parts[0][:1]
        path = parts[2] if (st == "R" and len(parts) >= 3) else parts[1]
        out[_norm(path)] = st
    return out, "ok"


def _decision_ids(doc: dict) -> set[str]:
    return {str(d.get("id")) for d in (doc.get("decisions") or []) if isinstance(d, dict)}


def is_append_only_entry(entry: dict | None) -> bool:
    return bool(entry) and entry.get("append_only") is True


# ── 2026-10-12 TD-20261012-17：合法 meta 更新 vs 歷史篡改 ─────────────────────
# 舊版對「任何頂層鍵變動」一律判「既有頂層鍵被改動」→ producer 每次入庫更新
# meta.updated_at 即判不變量失敗、降級真 CIO，受限車道形同虛設。
# 實證（commit 12dc9ea6）：唯一差異就是 meta.updated_at 13:26:49 → 19:05:51，
# 前綴逐筆相等、0 刪除、0 改寫，卻仍被降級。
# 修法＝語意判定：時間戳語意欄位（白名單）之「字串更新」放行；其餘欄位、meta 內其他子欄位、
# 既有 decisions 內容仍須零變動。**格式可驗真≠內容為真**（殘餘風險見輸出 note）。
META_TIMESTAMP_KEYS = ("updated_at", "last_updated")


def _meta_change_reasons(key: str, old_v, new_v) -> list[str]:
    """合法 meta 更新回傳空 list（放行）；疑似篡改回傳具名理由。"""
    if key in META_TIMESTAMP_KEYS:
        if isinstance(old_v, str) and isinstance(new_v, str) and new_v.strip():
            return []          # 時間戳更新＝producer 每跑必做，非歷史變更
        return [f"時間戳欄位 {key} 型別或內容不合法（{type(old_v).__name__} → {type(new_v).__name__}）"]
    if isinstance(old_v, dict) and isinstance(new_v, dict):
        bad = [kk for kk in sorted(set(old_v) | set(new_v))
               if kk not in META_TIMESTAMP_KEYS and old_v.get(kk) != new_v.get(kk)]
        if not bad:
            return []          # 只有時間戳子欄位變動
        return [f"既有頂層鍵 {key} 內含非時間戳欄位變動：{bad[:3]}"]
    return [f"既有頂層鍵被改動（{key}）——只允許時間戳 meta 更新與 decisions 追加"]


def _check_decisions(old_b: bytes | None, new_b: bytes | None) -> tuple[list[str], set[str], set[str]]:
    """決策檔不變量：只追加、既有內容零變動。回 (reasons, 新增 id, 新檔全部 id)。"""
    if old_b is None:
        return ["決策檔在變更前不存在（本車道只允許既有檔追加，不允許新建）"], set(), set()
    if new_b is None:
        return ["決策檔被刪除"], set(), set()
    try:
        old, new = json.loads(old_b.decode("utf-8")), json.loads(new_b.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return [f"決策檔非合法 UTF-8 JSON：{str(e)[:80]}"], set(), set()
    if not isinstance(old, dict) or not isinstance(new, dict):
        return ["決策檔頂層非物件"], set(), set()
    rs: list[str] = []
    for k in old:
        if k == "decisions":
            continue
        if k not in new:
            rs.append(f"既有頂層鍵被刪除（{k}）")
            continue
        if new[k] == old[k]:
            continue
        # 2026-10-12 TD-17：不再「任何變動即篡改」；改由 _meta_change_reasons 分離
        # 合法時間戳更新與真實歷史變更（既有 decisions 內容仍逐筆零變動，見下）。
        rs += _meta_change_reasons(k, old[k], new[k])
    od, nd = old.get("decisions"), new.get("decisions")
    if not isinstance(od, list) or not isinstance(nd, list):
        return rs + ["decisions 非陣列"], set(), set()
    if len(nd) < len(od):
        return rs + [f"decisions 筆數減少（{len(od)} → {len(nd)}）"], set(), _decision_ids(new)
    if nd[:len(od)] != od:
        rs.append("既有決策紀錄被修改（前綴逐筆不完全相等）")
    old_ids = {str(d.get("id")) for d in od if isinstance(d, dict)}
    added_ids: set[str] = set()
    for d in nd[len(od):]:
        if not isinstance(d, dict):
            rs.append("新增決策非物件")
            continue
        miss = [k for k in APPEND_ONLY_DECISION_KEYS if not str(d.get(k) or "").strip()]
        if miss:
            rs.append(f"新增決策缺必要欄位：{miss}")
        did = str(d.get("id") or "").strip()
        if not did:
            continue
        if did in added_ids:
            rs.append(f"新增決策 id 重複：{did}")
        if did in old_ids:
            rs.append(f"新增決策 id 與既有紀錄衝突：{did}")
        added_ids.add(did)
    if not added_ids and not rs and len(nd) == len(od):
        rs.append("decisions 無新增（本車道只允許純追加）")
    return rs, added_ids, _decision_ids(new)


def _check_receipts(old_b: bytes | None, new_b: bytes | None, added_ids: set[str],
                    all_new_ids: set[str], decisions_changed: bool) -> list[str]:
    """收據檔不變量：既有行零變動（逐位元前綴延伸）＋與決策新增互綁。"""
    if old_b is None:
        return ["收據檔在變更前不存在（本車道只允許既有檔追加）"]
    if new_b is None:
        return ["收據檔被刪除"]
    if not new_b.startswith(old_b):
        return ["既有收據行被修改或刪除（新內容不是舊內容的逐位元前綴延伸）"]
    tail = new_b[len(old_b):]
    if not tail.strip():
        return ["收據檔無新增行"]
    if not tail.endswith(b"\n"):
        return ["收據檔新增段未以換行結尾（疑似截斷）"]
    try:
        tail_s = tail.decode("utf-8")
    except Exception as e:  # noqa: BLE001
        return [f"收據新增段非 UTF-8：{e}"]
    rs: list[str] = []
    ok_true: set[str] = set()
    n_true = 0
    for ln in tail_s.splitlines():
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception as e:  # noqa: BLE001
            rs.append(f"新增收據行非合法 JSON：{str(e)[:60]}")
            continue
        if not isinstance(r, dict):
            rs.append("新增收據行非物件")
            continue
        if not isinstance(r.get("ok"), bool):
            rs.append("新增收據缺布林 ok 欄位")
            continue
        rid = str(r.get("id") or "").strip()
        if not rid:
            rs.append("新增收據缺 id")
            continue
        if r["ok"]:
            n_true += 1
            ok_true.add(rid)
            if rid not in all_new_ids:
                rs.append(f"收據 ok=true 但決策檔查無此 id：{rid}")
        elif rid in all_new_ids:
            rs.append(f"收據 ok=false 但該 id 存在於決策檔（語意矛盾）：{rid}")
    if decisions_changed:
        if ok_true != added_ids:
            rs.append(f"收據與決策不一致：新增決策 {len(added_ids)} 筆／ok=true 收據 {len(ok_true)} 筆"
                      f"（決策未落收據 {sorted(added_ids - ok_true)[:3]}、"
                      f"收據無對應決策 {sorted(ok_true - added_ids)[:3]}）")
        elif n_true != len(added_ids):
            rs.append(f"新增決策筆數（{len(added_ids)}）≠ 成功收據行數（{n_true}）")
    elif ok_true:
        rs.append(f"僅收據變更卻出現 ok=true（決策檔未同步）：{sorted(ok_true)[:3]}")
    return rs


def _verify_pair(base: Path, old_rev: str, new_rev: str,
                 changed: dict[str, str]) -> tuple[bool, dict]:
    """兩檔在 (old_rev → new_rev) 之間的不變量；changed 為該次變更集合。"""
    d_changed = DECISIONS_PATH in changed
    r_changed = RECEIPTS_PATH in changed
    reasons: list[str] = []
    added_ids: set[str] = set()
    all_new_ids: set[str] = set()
    if d_changed:
        rs, added_ids, all_new_ids = _check_decisions(
            _blob(base, old_rev, DECISIONS_PATH), _blob(base, new_rev, DECISIONS_PATH))
        reasons += [f"{DECISIONS_PATH}：{x}" for x in rs]
    else:
        nb = _blob(base, new_rev, DECISIONS_PATH)
        if nb:
            try:
                all_new_ids = _decision_ids(json.loads(nb.decode("utf-8")))
            except Exception:  # noqa: BLE001
                all_new_ids = set()
    if r_changed:
        reasons += [f"{RECEIPTS_PATH}：{x}" for x in _check_receipts(
            _blob(base, old_rev, RECEIPTS_PATH), _blob(base, new_rev, RECEIPTS_PATH),
            added_ids, all_new_ids, d_changed)]
    if d_changed and not r_changed:
        reasons.append("決策有新增但收據檔未同步變更（每筆入庫必須同輪留收據）")
    return (not reasons), {"reasons": reasons, "decisions_changed": d_changed,
                           "receipts_changed": r_changed, "added_decisions": len(added_ids)}


def verify_append_only_range(base: Path, range_base: str) -> tuple[bool, dict]:
    """閘門側：逐 commit 驗整個推送範圍（要發布什麼，就驗什麼）。"""
    cs = commits_in_range(base, range_base)
    if not cs:
        return False, {"mode": "range", "reasons": ["推送範圍為空（無事可做）"], "commits": []}
    ok_all = True
    out: list[dict] = []
    for c in cs:
        changed, why = _commit_changed(base, c)
        if changed is None:
            ok_all = False
            out.append({"commit": c[:12], "ok": False, "reasons": [why]})
            continue
        outside = [p for p in changed if p not in APPEND_ONLY_PATHS]
        bad_st = [f"{changed[p]}:{p}" for p in changed if changed[p] not in ("A", "M")]
        if outside or bad_st or not changed:
            ok_all = False
            out.append({"commit": c[:12], "ok": False,
                        "reasons": [f"超出受限兩檔範圍：{outside[:3]}（或空 commit）",
                                    f"非追加狀態（僅允許 A/M）：{bad_st[:3]}"]})
            continue
        ok, det = _verify_pair(base, f"{c}^", c, changed)
        ok_all = ok_all and ok
        out.append({"commit": c[:12], "ok": ok, **det})
    return ok_all, {"mode": "range", "range": f"{range_base}..HEAD", "commits": out}


def verify_append_only_auto(base: Path, ref: str = "HEAD") -> tuple[bool, dict]:
    """落版側查詢（classify_paths 用）：先驗 ref^..ref；該 commit 不含這兩檔時改驗 staged。"""
    changed, _why = _commit_changed(base, ref)
    if changed and set(changed) <= set(APPEND_ONLY_PATHS) and all(v in ("A", "M") for v in changed.values()):
        ok, det = _verify_pair(base, f"{ref}^", ref, changed)
        return ok, {"mode": "commit", "ref": ref, **det}
    staged, why = _staged_changed(base)
    if staged is None:
        return False, {"mode": "staged", "reasons": [why]}
    if not staged or not set(staged) <= set(APPEND_ONLY_PATHS) or any(v not in ("A", "M") for v in staged.values()):
        return False, {"mode": "staged", "reasons": ["staged 變更集合不在受限兩檔範圍內"],
                       "files": staged}
    ok, det = _verify_pair(base, "HEAD", INDEX_REV, staged)
    return ok, {"mode": "staged", **det}


# ---------------------------------------------------------------- 統一裁決

def classify(changed: set[str], entry: dict | None,
             specials: dict | None = None,
             append_only_ok: bool = False) -> tuple[str, bool, str]:
    """單一真值：一個檔案集合在發布授權上屬 AUTO 或 CIO。

    **落版側（auto_record）與閘門側（decide）必須共用此函式。**
    2026-10-12 死鎖根因即兩側各有一套判定：落版側只認「特殊類別 ∪ 程式副檔名」，
    閘門側另有「未命中白名單」→ 純資料 commit 被落 AUTO 章、卻被閘門以 CIO 模式拒絕。

    `append_only_ok`（PG-20261012 v4）：決策入庫兩檔的受限車道。**只有**在
    ①命中 append_only 條目 ②變更集合 ⊆ 受限兩檔 ③不變量驗證通過 時才為 True；
    此時「特殊類別命中」不再強制 CIO（那兩條路徑本來就在 NEVER_AUTO 內）。
    驗證未通過時呼叫端必須先落 APPEND_ONLY_VIOLATION 阻擋，不得只靠這裡降級。
    """
    sp = specials or {}
    ao = bool(append_only_ok and is_append_only_entry(entry))
    # 受限車道只收斂「受限兩檔本身」的特殊類別；若 specials 含任何其他路徑（呼叫端傳入的集合
    # 比條目更寬時的理論情境），一律回 CIO —— 不得因車道通過而連帶放行不相干的高風險路徑。
    # （2026-10-12 獨立審查 Finding 3 指出；正式路徑下 entry 命中已保證 changed ⊆ 兩檔，此為防禦性收斂。）
    if sp and not (ao and set(sp) <= set(APPEND_ONLY_PATHS)):
        return "CIO", True, "特殊類別命中"
    if entry is None:
        return "CIO", True, "未命中白名單"
    if ao:
        return "AUTO", False, "append-only 受限車道（不變量驗證通過）"
    return "AUTO", False, "命中低風險白名單"


def classify_paths(base: Path, paths, ref: str = "HEAD") -> dict:
    """給定檔案清單 → 發布授權判定（落版側查詢用；與 decide 共用 classify）。

    PG-20261012 v4：命中 append_only 條目且變更集合 ⊆ 受限兩檔時，**另外**跑內容不變量
    驗證（落版側與閘門側必須同結論，否則又會出現「一側 AUTO、一側 CIO」的死鎖）。
    驗證未通過 → 這裡回 CIO（落版側便不會蓋 AUTO 章），閘門側另會落 APPEND_ONLY_VIOLATION。
    """
    changed = {_norm(p) for p in paths if str(p).strip()}
    specials = {p: special_reason(p, base) for p in sorted(changed)}
    specials = {p: r for p, r in specials.items() if r}
    al, why_al = load_allowlist(base, ref=ref)
    if al is None:
        return {"mode": "CIO", "must_cio": True, "entry": None,
                "reason": f"白名單不可用（{why_al}）", "specials": specials,
                "files": sorted(changed)}
    entry, _why = match_entry(changed, al)
    ao_ok, ao_det = False, {"applied": False}
    if is_append_only_entry(entry) and changed and changed <= set(APPEND_ONLY_PATHS):
        try:
            ao_ok, ao_det = verify_append_only_auto(base, ref=ref)
            ao_det["applied"] = True
        except Exception as e:  # noqa: BLE001 — 驗證器失敗一律視為未通過（fail-closed）
            ao_ok, ao_det = False, {"applied": True, "mode": "error", "reasons": [str(e)[:160]]}
        ao_det["ok"] = ao_ok
    mode, must_cio, why_mode = classify(changed, entry, specials, append_only_ok=ao_ok)
    return {"mode": mode, "must_cio": must_cio,
            "entry": (entry or {}).get("label"), "reason": why_mode,
            "specials": specials, "files": sorted(changed), "append_only": ao_det}


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

    # append-only 受限車道（PG-20261012 v4）：命中受限條目且變更集合 ⊆ 兩檔時，逐 commit 重算內容不變量。
    # 不通過 → **降級為 CIO**（不給 AUTO）＋ 留 advisory 說明原因；不得靜默當成「未命中白名單」。
    # 為何不硬擋（PG-20261012 實作後修正）：硬擋會產生「合法修正無路可走」的新型死鎖 ——
    #   一顆內容不符的 commit 若經真 CIO 明確核准（含 tree 綁定），仍應可發布；硬擋會讓它永遠卡在分支上。
    #   防線不變：mode 降為 CIO ⇒ 偽造 AUTO 章一律被 CIO_REQUIRED 擋下（見關卡三）。
    advisories: list[dict] = []
    ao_ok, ao_det = False, {"applied": False}
    if is_append_only_entry(entry) and changed and changed <= set(APPEND_ONLY_PATHS):
        try:
            ao_ok, ao_det = verify_append_only_range(base, range_base)
            ao_det["applied"] = True
        except Exception as e:  # noqa: BLE001 — 驗證器不可用一律視為未通過（fail-closed）
            ao_ok, ao_det = False, {"applied": True, "mode": "range",
                                    "reasons": [f"驗證器執行失敗：{str(e)[:160]}"]}
        if not ao_ok:
            why_bad = list(ao_det.get("reasons") or [])
            for c in ao_det.get("commits") or []:
                if not c.get("ok"):
                    why_bad += [f"{c.get('commit')}：{r}" for r in (c.get("reasons") or [])]
            advisories.append({"id": "APPEND_ONLY_NOT_VERIFIED", "severity": "high",
                               "text": "決策入庫 append-only 不變量未通過 → 不給 AUTO，須真 CIO 審查："
                                       + "；".join(why_bad[:4])})
    checks["append_only"] = {"ok": ao_ok, **ao_det}

    # 模式判定：特殊類別命中 或 不在白名單 → 必須走真 CIO 審查
    mode, must_cio, why_mode = classify(changed, entry, specials, append_only_ok=ao_ok)
    checks["mode"] = {"mode": mode, "must_cio": must_cio, "reason": why_mode}

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
            "advisories": advisories,
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
        _ao = ch.get("append_only") or {}
        if _ao.get("applied"):
            print(f"  append-only 受限車道：{'✅ 不變量通過' if _ao.get('ok') else '⛔ 不變量未通過'}"
                  f"（查核模式={_ao.get('mode')}）")
        print(f"  特殊類別：{'無' if ch['special']['ok'] else ch['special']['hits']}")
        for ad in res.get("advisories") or []:
            print(f"  ⚠️ [{ad['id']}] {ad['text'][:200]}")
        print(f"  核准紀錄：{ch['records']['commits']} 顆｜失敗 {len(ch['records']['failed'])}")
        for b in res["blockings"]:
            print(f"   ⛔ [{b['id']}] {b['text']}")
    return res["rc"]


if __name__ == "__main__":
    sys.exit(main())
