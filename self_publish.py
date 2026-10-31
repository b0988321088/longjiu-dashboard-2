#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""self_publish.py — 「自身產出就地提交」共用實作（2026-10-12 TD-20261012-25 延伸）。

問題（結構性、每晚必犯）：
    producer 腳本把產物寫進工作區，但**沒有任何提交出口** → 該檔永遠停在 dirty，
    22:40 收工稽核每晚判「已追蹤未提交」。既有三處（cost_watch_close／cost_watch_digest／
    append_dashboard_decisions）各自複製同一段 25 行邏輯；本模組把同一語意抽成單一實作，
    供其餘 producer 直接呼叫（不在各檔再複製一份）。

語意（與 evening_sync／cost_watch_close 完全一致，不新增判定）：
    ① 認領範圍＝呼叫端**逐字宣告**的 allowlist（不得用「未知檔一律可提交」換取綠燈）
    ② 只認「本輪確實寫出」的檔：相對 HEAD dirty 且 mtime ≥ 本輪起跑時刻
       （對應 regenerate_report._claim_dirty_fixed_point 的定點認領三條件）
    ③ 只 stage 認領清單（禁用 git add -A）；stage 後驗證「staged ⊆ 認領清單」，
       多一個就整批 fail-closed → 不 commit／不 push
    ④ 無變更 → 不 commit、不 push（不製造空 commit）
    ⑤ 推送唯一出口＝auto_push.py；其 rc 原樣回報（0＝已上線並驗 remote sha）

    邊界（fail-closed）：
        · allowlist 條目不得為絕對路徑、不得含 `..`、不得指向 .git/、不得以 `*` 開頭、
          `*` 前的字面前綴 ≥3 字元、不得含程式副檔名（.py 等）—— 違反即整批拒絕。
        · 目錄掃描只用 allowlist 內的樣式，不用「整個目錄」。
        · untracked 檔不在本模組範圍（屬另一類，不因本模組被帶進 commit）。

    ⚠️ 呼叫端契約（2026-10-13 實跑踩到）：
        「本輪起跑時刻」預設＝**本模組被 import 的時刻** → 呼叫端必須在「開始做事之前」import；
        若在本輪工作**之後**才 import（例：先寫完產物、結尾才 import 綁定），T0 會晚於產物 mtime
        → 一律不認領（實例：notion_context_loader 首版把 import 放在 load_context() 之後 →
        明明剛寫完檔卻回報「本輪未寫它」）。要自帶起跑時刻時用 `since=` 明確傳入。
        設計取捨：寧可漏認領（下次執行再收），不可誤認領（把上一輪的檔當本輪帶走）。
"""
from __future__ import annotations

import fnmatch
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
AUTO_PUSH = REPO / "auto_push.py"

# 本輪起跑時刻（模組被 import 時）：mtime 早於此者＝不是本輪寫的 → 不認領
_T0 = time.time()

_CODE_EXT = {
    ".py", ".pyc", ".pyo", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bat", ".cmd",
    ".ps1", ".rb", ".go", ".rs", ".java", ".c", ".h", ".cpp", ".cs", ".php",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".db", ".sqlite", ".sqlite3", ".pem", ".key",
}
_MAX_PREFIX_LEN = 3   # 樣式 `*` 前的字面前綴下限


def _bad(reason: str, entry: str) -> None:
    sys.stderr.write(f"⛔ self_publish 拒絕：{reason}（條目 {entry!r}）\n")
    raise SystemExit(2)


def _check_entry(entry: str) -> None:
    """allowlist 條目的 fail-closed 安全檢查（規格同 publish_gate 擴白名單）。"""
    if not entry or entry.startswith("/") or ":" in entry or "\\" in entry:
        _bad("不得為絕對／磁碟路徑", entry)
    if ".." in Path(entry).parts:
        _bad("不得含 ..", entry)
    if entry.startswith(".git") or "/.git/" in entry:
        _bad("不得指向 .git", entry)
    if entry.startswith("*"):
        _bad("不得以 * 開頭", entry)
    if "*" in entry or "?" in entry:
        head = entry.split("*")[0].split("?")[0]
        if len(head) < _MAX_PREFIX_LEN:
            _bad(f"`*` 前的字面前綴需 ≥{_MAX_PREFIX_LEN} 字元", entry)
    if Path(entry).suffix.lower() in _CODE_EXT:
        _bad("不得指向程式檔（程式改動須走真 CIO 審查）", entry)


def _g(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def _resolve(allow: list[str]) -> list[str]:
    """把 allowlist 樣式展成實際路徑（只掃樣式本身，不掃整個目錄）。"""
    out: list[str] = []
    for entry in allow:
        if any(ch in entry for ch in "*?"):
            parent = (REPO / Path(entry).parent) if Path(entry).parent.as_posix() != "." else REPO
            if not parent.is_dir():
                continue
            for p in sorted(parent.iterdir()):
                if not p.is_file():
                    continue
                rel = p.relative_to(REPO).as_posix()
                if fnmatch.fnmatch(rel, entry) or fnmatch.fnmatch(p.name, Path(entry).name):
                    out.append(rel)
        elif (REPO / entry).is_file():
            out.append(entry)
    return sorted(set(out))


def _dirty_vs_head(rel: str) -> bool:
    """相對 HEAD 是否真的 dirty（untracked 不算：本模組不帶走未追蹤檔）。"""
    r = _g("diff", "--name-only", "HEAD", "--", rel)
    return r.returncode == 0 and bool(r.stdout.strip())


def claim_files(allow: list[str], since: float | None = None) -> tuple[list[str], list[str]]:
    """回傳（可認領, 略過並附原因）。since＝本輪起跑時刻（預設＝本模組 import 時刻）。"""
    t0 = _T0 if since is None else since
    keep, drop = [], []
    for entry in allow:
        _check_entry(entry)
    for rel in _resolve(allow):
        try:
            mtime = (REPO / rel).stat().st_mtime
        except OSError:
            drop.append(f"{rel}（讀不到）")
            continue
        if mtime < t0:
            drop.append(f"{rel}（本輪未寫它）")
            continue
        if not _dirty_vs_head(rel):
            drop.append(f"{rel}（與 HEAD 相同）")
            continue
        keep.append(rel)
    return keep, drop


def _classify_auto(rel: str) -> tuple[bool, str]:
    """回傳（可否走 AUTO 車道, 原因）。

    2026-10-19 事故根治：先前只擋「程式副檔名」，未問 publish_gate「這檔能不能 AUTO」，
    於是 maintenance_deep 把「未命中白名單」的舊報告更正橫幅 commit 進歷史 → auto_push 被
    閘門判需真 CIO（rc=3）→ 留下一顆推不動的 commit，把 origin/clean-main..HEAD 整段範圍
    變成 CIO 模式，隔天 07:00 晨間產線連四天 rc=1。
    契約：AUTO 車道只落「閘門側真的會給 AUTO」的檔；其餘一律不 commit（留工作區、寫警告）。
    載不到 publish_gate → fail-closed（不落版），不退回較寬鬆的規則。
    """
    try:
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        import publish_gate as _pg  # noqa: PLC0415
        v = _pg.classify_paths(REPO, [rel], ref="HEAD") or {}
    except Exception as e:  # noqa: BLE001
        return False, f"publish_gate 不可用（{e}）→ fail-closed"
    if v.get("mode") == "AUTO":
        return True, ""
    return False, str(v.get("reason") or "非 AUTO 車道")


def _warn_blocked(script: str, blocked: list[str]) -> None:
    """把「需真 CIO 但本車道不落版」的檔寫進 <git-dir>/AUTO_WARN.log（收工稽核會讀）。"""
    try:
        gd = _g("rev-parse", "--git-dir").stdout.strip() or ".git"
        p = Path(gd)
        if not p.is_absolute():
            p = REPO / p
        with (p / "AUTO_WARN.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\tCIO-REQUIRED\t{script}\t"
                    + "; ".join(blocked) + "\n")
    except Exception:  # noqa: BLE001
        pass


def commit_own(script: str, allow: list[str], *, dry_run: bool = False,
               producer_rc: int = 0, since: float | None = None) -> int:
    """把「本輪自己寫出的產物」就地提交並推送（唯一出口 auto_push.py）。

    參數：
        script       producer 名（= auto_push.py --script 的值，也是 commit 訊息署名）
        allow        逐字宣告的產物清單／樣式（必填，空清單＝拒絕）
        dry_run      只列印不落地
        producer_rc  producer 本體 rc；推送成功時回傳它，讓本體故障不被靜默
        since        本輪起跑時刻（預設＝本模組 import 時刻；見上方呼叫端契約）
    回傳：推送結果（0＝已上線並驗 remote sha；非 0＝失敗，cron 端要看得到）
    """
    # 2026-10-31 緊急事故隔離：.git/PUSH_HOLD 存在 → 一律不 stage/commit/push。
    # 本函式是 intel_sync／notion_context_loader／maintenance_deep 等共同提交入口，
    # 缺此檢查會讓事故隔離被繞過（排程暫停 ≠ 入口被鎖）。
    if (REPO / ".git" / "PUSH_HOLD").exists():
        print(f"⏸️ PUSH_HOLD 生效：{script} 跳過 commit/push（事故隔離）")
        return 0

    if not allow:
        sys.stderr.write("⛔ self_publish 拒絕：allowlist 為空（不得用空清單放行整棵樹）\n")
        return 2

    keep, drop = claim_files(allow, since)
    if drop:
        print("🚫 不認領：" + "；".join(drop[:8]) + ("…" if len(drop) > 8 else ""))

    # 只落「閘門側真的會給 AUTO」的產物；需真 CIO 者不 commit（避免製造推不動的 commit）
    if keep:
        _ok, _blocked = [], []
        for _rel in keep:
            _allowed, _why = _classify_auto(_rel)
            if _allowed:
                _ok.append(_rel)
            else:
                _blocked.append(f"{_rel}（{_why}）")
        if _blocked:
            sys.stderr.write("⛔ 需真 CIO 審查 → 本車道不落版（留工作區）："
                             + "；".join(_blocked[:8]) + ("…" if len(_blocked) > 8 else "") + "\n")
            _warn_blocked(script, _blocked)
        keep = _ok

    if not keep:
        print(f"⏭️ {script}：本輪無可提交產物（不 commit／不 push）")
        return producer_rc

    print(f"📦 {script}：本輪產物 {len(keep)} 檔就地提交 → {', '.join(keep[:8])}"
          + ("…" if len(keep) > 8 else ""))
    if dry_run:
        return producer_rc

    add = _g("add", "--", *keep)
    if add.returncode != 0:
        sys.stderr.write(f"⛔ git add 失敗 rc={add.returncode}：{(add.stderr or '').strip()[:300]}\n")
        return 1

    staged = [p for p in _g("diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    extra = sorted(set(staged) - set(keep))
    if extra:                      # 只 stage 自己的產物；多一個就整批不推
        sys.stderr.write(f"⛔ staged 超出認領清單（多出 {extra}）→ 不 commit／不 push（fail-closed）\n")
        return 1
    if not staged:
        # 產物相對 HEAD 已無差異（例：內容與 HEAD blob 相同）→ 無事可做
        print(f"⏭️ {script}：staged 無差異（git 正規化後與 HEAD 相同）→ 不 commit")
        return producer_rc

    msg = (f"data: {script} 自身產出就地提交（{time.strftime('%Y-%m-%d %H:%M')}）\n\n"
           + "".join(f"- {f}\n" for f in staged))
    commit = _g("commit", "-m", msg, "--", *staged)
    if commit.returncode != 0:
        sys.stderr.write(((commit.stdout or "") + (commit.stderr or "")).strip()[:400] + "\n")
        return 1
    print(((commit.stdout or "").splitlines() or [msg])[0])

    ap = subprocess.run([sys.executable, str(AUTO_PUSH), "--script", script],
                        cwd=str(REPO))
    return ap.returncode or producer_rc


if __name__ == "__main__":
    print("self_publish：供 producer 呼叫的模組（見 commit_own）")
    sys.exit(0)
