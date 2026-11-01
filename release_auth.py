#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性發布授權（RELEASE_AUTH）— 讓事故 HOLD 期間能執行「經明確授權的單次發布」。

## 為什麼需要這支

2026-10-31 INC-236：事故隔離的 PUSH_HOLD 是**無條件**擋板，導致「已核准的發布」
與「保留 HOLD」互相否定。實測 pre-push / auto_push 兩處皆拒，repo 內沒有任何例外機制。
使用者明確要求：新機制不得靠移除 HOLD、不得 --no-verify、不得繞過 hook；
必須能驗證指定 SHA、指定遠端、指定分支、一次性使用，並留完整稽核。

## 語意（與 PUSH_HOLD 的關係）

- PUSH_HOLD 仍然有效，且仍是預設拒絕。
- 只有在 `.git/RELEASE_AUTH` 存在、且**逐項驗證通過**時，才放行**一次**推送。
- 驗證失敗 → 一律拒絕（fail-closed），並寫 `.git/RELEASE_AUTH_REJECT.log`。
- 放行後立刻消費授權（改名 + 寫使用紀錄），同一份授權無法再用第二次。

## 驗證項目（全部通過才放行）

1. 授權檔存在、JSON 合法、欄位齊備
2. `expires_at` 未過期
3. 目前 HEAD 的完整 SHA == 授權的 `head`
4. `git rev-list origin/<branch>..HEAD` 的 commit 清單 == 授權的 `commits`（順序一致）
5. 遠端 URL == 授權的 `remote_url`（防止推錯 remote）
6. 目標分支 == 授權的 `branch`
7. 已使用次數 < `max_pushes`（預設 1）

## 稽核

- 放行：`.git/RELEASE_AUTH_USED/<id>.json`（含時間、HEAD、推送範圍、遠端 URL、驗證指紋）
- 拒絕：`.git/RELEASE_AUTH_REJECT.log`（含時間、原因）
- 授權檔本身改名為 `.git/RELEASE_AUTH.used-<id>`（保留原內容，不刪除）

## 職責分離（重要）

本機制**只授權推送**，不授權 commit：`.githooks/pre-commit` 不受影響，
PUSH_HOLD 期間 commit 仍一律被拒。這樣才不會出現「一把鑰匙同時開兩道門」。

### 消費與拒絕的責任分工（2026-11-01 TD-20261031-03⑤）
- **消費（consume）與拒絕紀錄只由 `pre-push` 負責**：它會把推送目標 refs 帶進來，
  能同時核對「只推授權分支」。
- `auto_push.py` 只做預檢 `verify()`（不消費），避免同一條推送被扣兩次。
- 併發：consume 以「原子搬走 `.git/RELEASE_AUTH`」當互斥鎖；第二條同時通過 verify 的推送
  會拿到 `AlreadyConsumed` 並被拒絕（TD-20261031-02，2026-11-01）。
- `refs` 未傳入時只驗 `branch` 設定、不驗實際推送目標 → CLI 會明示「refs 未收到」。

## CLI

  python release_auth.py issue --head <sha> --commits <sha1,sha2> [--branch clean-main]
                              [--remote origin] [--ttl-min 30] [--note "..."]
  python release_auth.py verify [--refs-from-stdin]
  python release_auth.py status
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

TAIPEI = timezone(timedelta(hours=8))


def _repo() -> Path:
    return Path(os.environ.get("LJ_REPO") or Path(__file__).resolve().parent)


def _git_dir(repo: Path) -> Path:
    return repo / ".git"


def _now() -> datetime:
    return datetime.now(TAIPEI)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout.strip()


def _auth_path(repo: Path) -> Path:
    return _git_dir(repo) / "RELEASE_AUTH"


def _load(repo: Path) -> tuple[dict | None, str]:
    p = _auth_path(repo)
    if not p.exists():
        return None, "無授權檔（.git/RELEASE_AUTH 不存在）"
    try:
        j = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"授權檔非合法 JSON：{type(exc).__name__}"
    if not isinstance(j, dict):
        return None, "授權檔非 JSON 物件"
    need = ["id", "head", "commits", "branch", "remote_url", "expires_at", "max_pushes"]
    miss = [k for k in need if k not in j]
    if miss:
        return None, f"授權檔缺欄位：{','.join(miss)}"
    return j, ""


def _used_count(repo: Path, auth_id: str) -> int:
    d = _git_dir(repo) / "RELEASE_AUTH_USED"
    if not d.exists():
        return 0
    return len(list(d.glob(f"{auth_id}*.json")))


def _log_reject(repo: Path, reason: str, auth_id: str = "") -> None:
    """寫拒絕紀錄。2026-11-01 TD-20261031-03①：加授權 id 以便追溯是哪一份被拒。"""
    try:
        with open(_git_dir(repo) / "RELEASE_AUTH_REJECT.log", "a", encoding="utf-8") as fh:
            fh.write(f"{_iso(_now())}\tREJECT\t{auth_id or '-'}\t{reason}\n")
    except Exception:  # noqa: BLE001
        pass


class AlreadyConsumed(RuntimeError):
    """授權已被另一條推送消費（或授權檔已消失）→ 必須拒絕，不得重複放行。"""


def log_reject(repo: Path, reason: str, auth_id: str = "") -> None:
    """公開入口：供 auto_push 等呼叫端補寫拒絕紀錄（TD-20261031-03④）。

    verify() 內部的失敗已自行寫 log；這支是給「呼叫端自己出錯」的情境用
    （例如 auto_push 預檢拋例外），避免拒絕原因只存在 stdout、事後查不到。
    """
    _log_reject(repo, reason, auth_id)


def verify(repo: Path | None = None, refs: list[str] | None = None) -> tuple[bool, str, dict]:
    """回傳 (是否放行, 原因, 稽核用指紋)。全部驗證通過才放行。"""
    repo = repo or _repo()
    _aid = ""                      # 授權檔載入前先給值：載入失敗也要能寫拒絕紀錄
    j, err = _load(repo)
    if j is None:
        _log_reject(repo, err, _aid)
        return False, err, {}
    _aid = str(j.get("id") or "")

    # 2. 期限
    try:
        exp = datetime.fromisoformat(str(j["expires_at"]))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=TAIPEI)
    except Exception:  # noqa: BLE001
        _log_reject(repo, "expires_at 無法解析", _aid)
        return False, "expires_at 無法解析", {}
    if _now() > exp:
        _log_reject(repo, f"授權已過期（{j['expires_at']}）", _aid)
        return False, f"授權已過期（{j['expires_at']}）", {}

    # 7. 使用次數
    used = _used_count(repo, str(j["id"]))
    if used >= int(j.get("max_pushes") or 1):
        _log_reject(repo, f"授權已用盡（{used} 次）", _aid)
        return False, f"授權已用盡（{used} 次）", {}

    # 3. HEAD
    try:
        head = git(repo, "rev-parse", "HEAD")
    except RuntimeError as exc:
        _log_reject(repo, str(exc), _aid)
        return False, str(exc), {}
    if head != str(j["head"]).strip():
        _log_reject(repo, f"HEAD 不符：實際 {head[:12]}，授權 {str(j['head'])[:12]}", _aid)
        return False, f"HEAD 不符（實際 {head[:12]} / 授權 {str(j['head'])[:12]}）", {}

    # 5. remote URL
    try:
        url = git(repo, "remote", "get-url", str(j.get("remote") or "origin"))
    except RuntimeError as exc:
        _log_reject(repo, str(exc), _aid)
        return False, str(exc), {}
    if url != str(j["remote_url"]).strip():
        _log_reject(repo, "遠端 URL 不符", _aid)
        return False, f"遠端 URL 不符（實際 {url}）", {}

    # 6. 目標分支（可由 hook 傳入 refs 交叉核對）
    branch = str(j["branch"]).strip()
    if refs:
        target = "refs/heads/" + branch
        bad = [r for r in refs if r and not r.endswith(target)]
        if bad:
            _log_reject(repo, f"推送目標含非授權分支：{bad[:3]}", _aid)
            return False, f"推送目標含非授權分支（僅允許 {branch}）", {}

    # 4. 待推範圍
    try:
        base = git(repo, "rev-parse", f"refs/remotes/{j.get('remote') or 'origin'}/{branch}")
    except RuntimeError:
        base = ""
    rng = git(repo, "rev-list", f"{base}..HEAD" if base else "HEAD").split()
    want = [str(c).strip() for c in (j["commits"] or [])]
    # 順序不比對：rev-list 由新到舊、授權檔由舊到新；同一組 commit 即可
    # （HEAD 與 base 已各自驗證，集合相同即代表推送範圍一致）。
    if sorted(rng) != sorted(want):
        _log_reject(repo, f"推送範圍不符：實際 {[c[:8] for c in rng]}，授權 {[c[:8] for c in want]}", _aid)
        return False, f"推送範圍不符（實際 {len(rng)} 顆 / 授權 {len(want)} 顆）", {}

    fp = {
        "id": j["id"],
        "head": head,
        "branch": branch,
        "remote_url": url,
        "commits": rng,
        "base": base,
        "verified_at": _iso(_now()),
        "declared_by": j.get("declared_by", ""),
        "note": j.get("note", ""),
    }
    return True, "授權有效", fp


def consume(repo: Path, fp: dict) -> Path:
    """放行後立即消費：以「搬走授權檔」當互斥鎖，確保同一份授權只放行一次。

    2026-11-01 TD-20261031-02：原版先寫 USED、再選擇性 rename（`if p.exists()`），
    兩條推送同時通過 verify 時都會寫出 USED、都拿到成功 → max_pushes=1 形同虛設。
    改為：先把 `.git/RELEASE_AUTH` 原子搬成 `.used-<id>`，搬成功的那一條才寫 USED
    並放行；搬不到（已被另一條搬走／已被清除）→ AlreadyConsumed → 拒絕。
    搬成功但寫 USED 失敗時，授權檔已不在 → 後續 verify 一律拒絕（fail-closed）。
    """
    g = _git_dir(repo)
    d = g / "RELEASE_AUTH_USED"
    d.mkdir(parents=True, exist_ok=True)
    p = _auth_path(repo)
    try:
        p.rename(g / f"RELEASE_AUTH.used-{fp['id']}")
    except FileNotFoundError:
        _log_reject(repo, "授權檔已不存在（已被另一條推送消費或已清除）→ 拒絕重複放行",
                    str(fp.get("id") or ""))
        raise AlreadyConsumed("授權已被消費") from None
    except OSError as exc:
        _log_reject(repo, f"消費失敗：{type(exc).__name__}: {exc}", str(fp.get("id") or ""))
        raise
    out = d / f"{fp['id']}.json"
    out.write_text(json.dumps(fp, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def issue(head: str, commits: list[str], branch: str = "clean-main", remote: str = "origin",
          ttl_min: int = 30, note: str = "", declared_by: str = "") -> Path:
    repo = _repo()
    url = git(repo, "remote", "get-url", remote)
    aid = uuid.uuid4().hex[:12]
    obj = {
        "id": aid,
        "issued_at": _iso(_now()),
        "expires_at": _iso(_now() + timedelta(minutes=ttl_min)),
        "head": head.strip(),
        "commits": [c.strip() for c in commits],
        "branch": branch,
        "remote": remote,
        "remote_url": url,
        "max_pushes": 1,
        "declared_by": declared_by,
        "note": note,
    }
    p = _auth_path(repo)
    if p.exists():
        print(f"⛔ 已有未消費的授權檔，拒絕覆寫：{p}\n"
              f"   請先確認該授權是否還要用（`python release_auth.py status`）；\n"
              f"   確定作廢就刪除該檔或等它過期，再重新 issue。", file=sys.stderr)
        raise SystemExit(3)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def status() -> dict:
    repo = _repo()
    j, err = _load(repo)
    d = _git_dir(repo) / "RELEASE_AUTH_USED"
    return {
        "hold": (_git_dir(repo) / "PUSH_HOLD").exists(),
        "auth_exists": j is not None,
        "auth_error": err,
        "auth": j,
        "used_records": sorted(x.name for x in d.glob("*.json")) if d.exists() else [],
        "head": (git(repo, "rev-parse", "HEAD")[:12] if True else ""),
    }


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "issue":
        head = ""
        commits: list[str] = []
        branch, remote, ttl, note, by = "clean-main", "origin", 30, "", ""
        i = 2
        while i < len(argv):
            a = argv[i]
            if a == "--head": head = argv[i + 1]; i += 2
            elif a == "--commits": commits = argv[i + 1].split(","); i += 2
            elif a == "--branch": branch = argv[i + 1]; i += 2
            elif a == "--remote": remote = argv[i + 1]; i += 2
            elif a == "--ttl-min": ttl = int(argv[i + 1]); i += 2
            elif a == "--note": note = argv[i + 1]; i += 2
            elif a == "--declared-by": by = argv[i + 1]; i += 2
            else:
                print(f"未知參數 {a}", file=sys.stderr); return 2
        if not head or not commits:
            print("用法：issue --head <sha> --commits <sha1,sha2> [...]", file=sys.stderr)
            return 2
        p = issue(head, commits, branch, remote, ttl, note, by)
        print(f"✅ 已建立一次性授權：{p}")
        return 0

    if cmd == "verify":
        refs = None
        if "--refs-from-stdin" in argv:
            # git pre-push 的 stdin 每行四欄：<local ref> <local sha> <remote ref> <remote sha>
            refs = []
            for ln in sys.stdin.read().splitlines():
                parts = ln.split()
                if parts:
                    refs.append(parts[2] if len(parts) >= 3 else parts[0])
        ok, reason, fp = verify(refs=refs)
        if not ok:
            print(f"⛔ 授權驗證失敗：{reason}", file=sys.stderr)
            return 1
        if "--no-consume" in argv:
            _r = f"｜refs {'已核對' if refs else '未收到（僅驗 branch 設定）'}"
            print(f"✅ 一次性授權有效（未消費，由 pre-push 消費）｜{len(fp['commits'])} 顆｜{fp['branch']}{_r}")
            return 0
        try:
            out = consume(_repo(), fp)
        except AlreadyConsumed:
            print("⛔ 授權已被消費（或授權檔已消失）→ 拒絕重複放行", file=sys.stderr)
            return 1
        print(f"✅ 一次性授權通過並已消費：{out.name}｜{len(fp['commits'])} 顆｜{fp['branch']}")
        return 0

    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0

    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
