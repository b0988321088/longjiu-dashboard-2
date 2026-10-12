# -*- coding: utf-8 -*-
"""pending_store.py — pending_decisions.json 的唯一寫入通道（跨程序互斥鎖 ＋ 原子替換）。

【案件】TD-20261009-16（P0 事故）
2026-10-09 22:00 job（evening_sync.py → pending_reconcile.py --apply）以「非原子整檔重寫」
覆蓋 pending_decisions.json，把併發新增的 PEND-20261009-15 整張卡吃掉
（備份 65 張／重寫後 64 張）。根因＝整檔非原子寫入 ＋ 無跨程序鎖 → 讀-改-寫競態
last-writer-wins，任何與寫入者併發建立的卡片都可能靜默消失（資料遺失）。

【本模組契約】
1. 跨程序互斥：所有寫入者共用「同一把鎖」BASE/pending_decisions.lock
   （單一鎖同時保護 pending_decisions.json 與 pending_decisions_archive.json，
     避免兩把鎖造成鎖序死結）。Windows 走 msvcrt.locking，POSIX 走 fcntl.flock。
   → 原子替換只能防「寫到一半被中斷」，**不能**防競態；兩者必須同時成立。
2. 取得鎖失敗＝fail-closed：丟 LockTimeout，呼叫端不得改走無鎖寫入。
3. 原子替換：tmp（同目錄）→ flush＋fsync → 讀回驗證 → os.replace。
   任何例外一律清 tmp、正本不動。
4. 格式保持：newline 依現有檔案自動判定（CRLF/LF），避免整檔假 diff。
5. 行程被殺時由作業系統自動釋放鎖，不需人為清理陳舊鎖。

用法：
    import pending_store
    with pending_store.locked():
        with pending_store.transaction(PEND) as tx:      # 鎖內讀-改-寫
            data = tx.data
            data.append({"title": "..."})
            tx.stage(data)                               # 退出時原子寫入
    # 或單純寫入（呼叫端已持有鎖）：
    pending_store.atomic_write_json(PEND, data, indent=2)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOCK_PATH = BASE / "pending_decisions.lock"
DEFAULT_TIMEOUT = 60.0
RECONCILE_PATHS = ("pending_decisions.json", "pending_decisions_archive.json")

_HELD: dict[str, int] = {}


class LockTimeout(RuntimeError):
    """取鎖逾時：呼叫端必須放棄寫入（fail-closed），不得改走無鎖路徑。"""


class WriteRejected(RuntimeError):
    """寫入前驗證失敗：正本未動。"""


def _holder_info() -> dict:
    return {"pid": os.getpid(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "argv": [Path(a).name for a in sys.argv[:3]]}


class _FileLock:
    def __init__(self, path: Path, timeout: float):
        self.path = Path(path)
        self.timeout = float(timeout)
        self._fh = None
        self._reentrant = False

    # ── 取鎖 ──────────────────────────────────────────────
    def acquire(self) -> "_FileLock":
        key = str(self.path.resolve())
        if _HELD.get(key):                 # 同行程可重入（避免自我死結）
            _HELD[key] += 1
            self._reentrant = True
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8", newline="")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise LockTimeout(
                        f"取鎖逾時 {self.timeout}s：{self.path}（fail-closed，未寫入）")
                time.sleep(0.05)
        try:                                # 診斷資訊（持有者／時間）
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(_holder_info(), ensure_ascii=False))
            fh.flush()
        except Exception:
            pass
        self._fh = fh
        _HELD[key] = 1
        return self

    def release(self) -> None:
        key = str(self.path.resolve())
        if self._reentrant:
            _HELD[key] = max(0, _HELD.get(key, 1) - 1)
            self._reentrant = False
            return
        _HELD.pop(key, None)
        fh, self._fh = self._fh, None
        if fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        finally:
            fh.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False


def locked(timeout: float = DEFAULT_TIMEOUT, path: Path | None = None) -> _FileLock:
    """取得「pending 系列唯一鎖」。逾時丟 LockTimeout（fail-closed）。"""
    return _FileLock(path or LOCK_PATH, timeout)


def lock_holder(path: Path | None = None) -> dict:
    """讀鎖檔內的持有者資訊（僅供診斷；不代表一定仍持有）。"""
    p = Path(path or LOCK_PATH)
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


# ── 原子寫入 ────────────────────────────────────────────────
def detect_newline(path: Path) -> str:
    """依現有檔案判定換行風格（保持原格式，避免整檔假 diff）。"""
    p = Path(path)
    if not p.exists():
        return "lf"
    head = p.read_bytes()[:4096]
    return "crlf" if b"\r\n" in head else "lf"


def _render(data, indent: int, newline: str) -> str:
    txt = json.dumps(data, ensure_ascii=False, indent=indent)
    if newline == "crlf":
        txt = txt.replace("\r\n", "\n").replace("\n", "\r\n")
    return txt + ("\r\n" if newline == "crlf" else "\n")


def sweep_tmp(path) -> list[str]:
    """回收同一目標殘留的 tmp（前次寫入者在 replace 前被殺 → 無法自我清理）。

    僅在「已持有鎖」的前提下呼叫才安全：此時任何同目標 tmp 必為崩潰殘留，
    不會誤刪他人進行中的暫存檔。
    """
    p = Path(path)
    gone = []
    for f in p.parent.glob(f"{p.name}.tmp*"):
        try:
            f.unlink()
            gone.append(f.name)
        except OSError:
            pass
    return gone


def atomic_write_text(path, text: str, *, fsync: bool = True, verify_json: bool = True) -> str:
    """tmp → flush+fsync → 驗證 → os.replace。失敗清 tmp 且正本不動。回傳實際寫入內容。

    寫入前先 sweep_tmp()：崩潰殘留的 .tmp-<pid> 在此回收（呼叫端須已持鎖）。
    """
    p = Path(path)
    sweep_tmp(p)
    tmp = p.with_name(f"{p.name}.tmp-{os.getpid()}")
    if verify_json:
        try:
            json.loads(text)
        except Exception as e:
            raise WriteRejected(f"拒絕寫入（內容非合法 JSON）：{type(e).__name__}: {e}")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            if fsync:
                os.fsync(f.fileno())
        os.replace(str(tmp), str(p))
        return text
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_json(path, data, indent: int = 2, newline: str | None = None) -> str:
    nl = newline or detect_newline(Path(path))
    return atomic_write_text(path, _render(data, indent, nl))


# ── 鎖內交易 ────────────────────────────────────────────────
class _Tx:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = None
        self._staged = None

    def __enter__(self):
        self.data = json.loads(self.path.read_text(encoding="utf-8"))
        return self

    def stage(self, data):
        self._staged = data

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None and self._staged is not None:
            atomic_write_json(self.path, self._staged)
        return False


def transaction(path) -> _Tx:
    return _Tx(path)


# ── 卡數／卡別追溯 ──────────────────────────────────────────
def card_key(card: dict) -> str:
    """卡片穩定鍵（優先 id；無 id 者退 title；無 title 者退序列化前 60 字）。"""
    if not isinstance(card, dict):
        return f"<non-dict:{type(card).__name__}>"
    for k in ("id", "ID", "cleanup_id", "title"):
        v = card.get(k)
        if v:
            return f"{k}:{str(v)[:80]}"
    return "raw:" + json.dumps(card, ensure_ascii=False)[:60]


def card_keys(data) -> list[str]:
    lst = data.get("pending_decisions") if isinstance(data, dict) else data
    return [card_key(c) for c in (lst or []) if isinstance(c, (dict, str))]


def diff_keys(before: list[str], after: list[str]) -> dict:
    b, a = list(before), list(after)
    sb, sa = set(b), set(a)
    return {"added": [k for k in a if k not in sb],
            "removed": [k for k in b if k not in sa],
            "count_before": len(b), "count_after": len(a)}


def snapshot_file(path, out_json: Path | None = None) -> dict:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    snap = {"path": str(p), "keys": card_keys(data), "count": len(card_keys(data))}
    if out_json:
        Path(out_json).write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    return snap
