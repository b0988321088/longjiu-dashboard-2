#!/usr/bin/env python3
"""tools/publish_gate.py — 發布放行條件 ③⑥（2026-10-17 使用者裁決「授權 1+2」）

放行語意（只阻擋有風險的發布，不影響報告產生）：
  ③ 範圍類：本輪 produced 內的 .py 若不在 `check_dividend_caliber.allowed` 宣告清單
     → 阻塞。**只在本輪真的要推它時才擋**；未進 produced 的未宣告檔不影響發布，
     也不從審查結果中隱藏（F3 仍獨立呈現範圍類紅燈）。
  ⑥ 新鮮度：snapshot.date != today 且無有效 T-1 例外標記 → 阻塞。
     例外檔格式見 governance/freshness_exception.example.json；不得自行補日期、
     不得把舊資料偽裝成當日資料。

設計原則：
  - 不新增授權途徑：本模組只「阻擋」，不放行 CIO RECORD／白名單／pathspec 之外的東西。
  - 單一來源：宣告清單以 AST 讀取 check_dividend_caliber.py 的 `allowed`，
    不在此檔重複維護、也不執行該腳本（避免副作用與耗時）。
  - 純函式：所有判定可用假資料單獨測試（見 tools/test_publish_gate.py）。
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

TPE = timezone(timedelta(hours=8))
DEFAULT_EXCEPTION = "governance/freshness_exception.json"


def declared_program_files(base: Path | str) -> set[str]:
    """從 check_dividend_caliber.py 的 `allowed` 取得已宣告檔名集合（AST，不執行）。"""
    src_path = Path(base) / "check_dividend_caliber.py"
    try:
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "allowed":
                    try:
                        val = ast.literal_eval(node.value)
                    except Exception:
                        return set()
                    if isinstance(val, (set, list, tuple)):
                        return {str(x) for x in val}
    return set()


def _now() -> datetime:
    return datetime.now(TPE)


def load_freshness_exception(path: Path | str | None, base: Path | str) -> tuple[dict | None, str]:
    """讀取新鮮度例外標記；回傳 (資料, 錯誤說明)。任何不完整即視為無效。"""
    p = Path(path) if path else (Path(base) / DEFAULT_EXCEPTION)
    if not p.is_absolute():
        p = Path(base) / p
    if not p.exists():
        return None, "無例外檔"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return None, f"例外檔無法解析：{e}"
    if not isinstance(d, dict):
        return None, "例外檔格式錯誤（非物件）"
    return d, ""


def check_freshness(snapshot_date: str, today: str, base: Path | str,
                    exception_path: Path | str | None = None,
                    now: datetime | None = None) -> dict:
    """⑥ snapshot 新鮮度：當日放行；T-1 需有效例外；其餘阻塞。"""
    out = {"ok": True, "blocking": [], "notes": []}
    snap_d, today_d = str(snapshot_date or ""), str(today or "")
    if not snap_d:
        out["ok"] = False
        out["blocking"].append("⑥ 新鮮度：snapshot.date 缺失 → 無法判定資料是否為當日，阻擋發布")
        return out
    if snap_d == today_d:
        out["notes"].append(f"⑥ 新鮮度：snapshot.date={snap_d} ＝ 當日 → 放行")
        return out

    exc, err = load_freshness_exception(exception_path, base)
    if exc is None:
        out["ok"] = False
        out["blocking"].append(
            f"⑥ 新鮮度：snapshot.date={snap_d} ≠ 當日 {today_d}，且無有效例外標記（{err}）→ 阻擋發布")
        return out

    allow = str(exc.get("allow_snapshot_date") or "")
    approved = str(exc.get("approved_by") or "").strip()
    expires = str(exc.get("expires_at") or "").strip()
    reason = str(exc.get("reason") or "").strip()

    problems = []
    if allow != snap_d:
        problems.append(f"allow_snapshot_date={allow!r} ≠ snapshot.date={snap_d!r}")
    if not approved:
        problems.append("approved_by 為空（無授權來源）")
    if not reason:
        problems.append("reason 為空（無例外理由）")
    if not expires:
        problems.append("expires_at 為空（無到期時間）")
    else:
        try:
            exp_dt = datetime.fromisoformat(expires)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=TPE)
            if (now or _now()) > exp_dt:
                problems.append(f"例外已過期（expires_at={expires}）")
        except Exception:
            problems.append(f"expires_at 無法解析（{expires!r}）")

    if problems:
        out["ok"] = False
        out["blocking"].append(
            f"⑥ 新鮮度：snapshot.date={snap_d} ≠ 當日 {today_d}，例外標記無效（{'；'.join(problems)}）→ 阻擋發布")
    else:
        out["notes"].append(
            f"⑥ 新鮮度：snapshot.date={snap_d}（T-1 例外，核准={approved}，到期={expires}）→ 放行")
    return out


def check_scope(produced, base: Path | str) -> dict:
    """③ 範圍類 ∩ produced：只有未宣告的 .py 真的進入本輪發布集合才阻擋。"""
    out = {"ok": True, "blocking": [], "notes": []}
    declared = declared_program_files(base)
    hits = []
    for f in (produced or []):
        s = str(f).replace("\\", "/").strip()
        if not s.endswith(".py"):
            continue
        if Path(s).name not in declared:
            hits.append(s)
    if hits:
        out["ok"] = False
        out["blocking"].append(
            f"③ 範圍類：未宣告的程式檔進入本輪發布集合 → {', '.join(sorted(hits))}")
    else:
        out["notes"].append(
            f"③ 範圍類：本輪 produced {len(produced or [])} 檔，未宣告 .py 交集 0 → 放行")
    return out


def check_publish_gate(produced, snapshot_date: str, today: str,
                       base: Path | str, exception_path: Path | str | None = None,
                       now: datetime | None = None) -> dict:
    """回傳 {ok, blocking[], notes[], detail{}}；ok=False 時呼叫端必須 fail-closed 不推送。"""
    s = check_scope(produced, base)
    f = check_freshness(snapshot_date, today, base, exception_path, now)
    blocking = s["blocking"] + f["blocking"]
    return {
        "ok": not blocking,
        "blocking": blocking,
        "notes": s["notes"] + f["notes"],
        "detail": {"scope": s, "freshness": f},
    }


if __name__ == "__main__":  # 手動查詢用（唯讀）
    import sys
    b = Path(__file__).resolve().parent.parent
    snap = json.loads((b / "snapshot.json").read_text(encoding="utf-8"))
    print(json.dumps(
        check_publish_gate([], snap.get("date", ""), str(__import__("datetime").date.today()),
                           b, None),
        ensure_ascii=False, indent=2))
    sys.exit(0)
