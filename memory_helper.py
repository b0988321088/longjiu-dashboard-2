"""記憶寫入共用工具 — 供所有腳本呼叫，寫入 dashboard_decisions.json 再由 memory_sync.py 同步到 holographic

2026-10-05（P0-2 使用者核准）— 加入 duplicate guard
------------------------------------------------------------------
問題：本檔過去**無條件 append**。每次呼叫就多一筆等價收據；`run_daily.py` 尾段
      每天都呼叫它兩次（日報／資產穿透），產線多跑幾次就多幾筆 —— 實測
      「日報 2026-09-30 ×70」「資產穿透 2026-09-30 ×70」（同日同任務同摘要）。

規則（同一決策／同一任務／同一 execution 不得產生多筆等價收據）：
      duplicate key = (task, source, 當地日期 YYYY-MM-DD)
      命中 → **不再 append**，回傳既有 id，並印一行說明。
備註：既有歷史重複**不刪不改**（使用者明令）；標記與統計見
      tools/decision_dedup_report.py → data/decision_dedup_report.json。
"""
import json
import re
from datetime import datetime
from pathlib import Path


_DATE_IN_TASK = re.compile(r"\d{4}-\d{2}-\d{2}")


def _dup_key(entry: dict):
    """等價收據判定鍵。

    * 任務名**自帶日期**（如 `日報2026-09-30`）→ 身分已完整 `(task, source)`。
      實測這些任務會被跨日重寫（09-30 的日報有 4 筆 timestamp 落在 10/01），
      若再乘 timestamp 日期就抓不到 —— 使用者點名的「×70」正是在這個口徑下成立。
    * 任務名不帶日期 → `(task, source, timestamp 當地日期)`，同日重跑視為同一筆。
    * **空任務名 → 回 None（不參與去重）**：沒有任務名就無法判定身分，
      寧可放行也不可誤擋（實測歷史有 task=None 的舊決策，同日多筆是正常現象）。

    summary 不列入：同一任務重複執行時 payload 本來就會變（日報 09-30 的 70 筆有 6 種
    summary），身分是 (任務, 來源[, 日期])，summary 只是當下內容。
    """
    task = str(entry.get("task") or "")
    if not task:
        return None
    if _DATE_IN_TASK.search(task):
        return (task, entry.get("source"))
    return (task, entry.get("source"), str(entry.get("timestamp", ""))[:10])


def find_duplicate(decisions: list, entry: dict):
    """回傳既有等價收據（沒命中／無法判定身分回 None）。"""
    k = _dup_key(entry)
    if k is None:                      # 空任務名 → 不參與去重
        return None
    for e in decisions:
        if isinstance(e, dict) and _dup_key(e) == k:
            return e
    return None


def _receipt_path(dec_path: Path) -> Path:
    """收據檔位置＝決策檔同一 repo 下的 data/（測試注入沙盒時自動跟著走，不污染真 repo）。"""
    return Path(dec_path).parent / "data" / "decision_intake_receipts.jsonl"


def write_auto_receipt(entry: dict, ok: bool, msg: str, dec_path: Path) -> None:
    """自動寫入也留收據（2026-11-23 CIO ② 收據覆蓋率）。

    為什麼：reconcile_decision_intake 過去只認得 append_dashboard_decisions.py 產生的收據，
    run_daily 每天兩筆 add_memory（日報／資產穿透）在檔案裡看得到、在收據裡看不到 →
    「有條目、收據看不到」的結構盲點，也讓 auto 噪音與人工缺口長得一樣。
    本函式只補稽核軌跡，不改任何判定：source 記 'auto'，reconcile 會歸在「自動車道」。
    寫入失敗不得影響決策入庫（收據是旁證，不是入庫前置）→ 一律吞例外並印警告。
    """
    try:
        p = _receipt_path(dec_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": entry.get("timestamp"), "id": entry.get("id"), "task": entry.get("task"),
               "source": entry.get("source"), "ok": bool(ok), "note": msg}
        with p.open("a", encoding="utf-8", newline="") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\r\n")
    except Exception as e:                                  # noqa: BLE001
        print(f"  ⚠️ 收據寫入失敗（不影響入庫）：{type(e).__name__}: {e}")


def add_memory(agent: str, task: str, summary: str, status: str = "completed",
               *, allow_duplicate: bool = False, path=None, receipt: bool = True):
    """寫入一條記憶/決策到 dashboard_decisions.json

    用法: from memory_helper import add_memory
          add_memory("Hermes", "日報產出", "證券2,479,320 配息118,296")

    allow_duplicate=True：明確允許同日同任務同摘要再寫一筆（預設 False＝去重）。
    path：僅供測試注入沙盒檔案（預設＝repo 內 dashboard_decisions.json）。
    receipt：預設 True＝同時寫收據（source=auto）。去重命中（沒 append）時不寫收據，
             與 append_dashboard_decisions.py 的 idempotent 語意一致。
    """
    path = Path(path) if path else (Path(__file__).resolve().parent / "dashboard_decisions.json")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # ⚠️ 2026-08-27 相容：檔案可能被寫成純 list → 包回 dict（.setdefault 在 list 會炸）
        if not isinstance(data, dict):
            data = {"decisions": data if isinstance(data, list) else []}
    except Exception:
        data = {"decisions": [], "meta": {"version": 1}}

    entry = {
        "id": f"mem-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(data['decisions'])}",
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "task": task,
        "summary": summary,
        "status": status,
        "source": "auto"
    }

    # ── duplicate guard（P0-2）──────────────────────────────────────────────
    if not allow_duplicate:
        dup = find_duplicate(data.setdefault("decisions", []), entry)
        if dup is not None:
            print(f"  ♻️ 記憶略過（同日同任務同摘要已存在）: [{agent}] {task}"
                  f"（既有 id={dup.get('id')}）")
            return dup.get("id")

    data.setdefault("decisions", []).append(entry)
    data.setdefault("meta", {})["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    if receipt:
        # 收據只記「真的 append 了什麼」（去重命中不寫，否則會造出檔案沒有的假收據）
        write_auto_receipt(entry, True, f"✅ 自動寫入 id={entry['id']}（memory_helper）", path)
    print(f"  🧠 記憶已寫入: [{agent}] {task}")
    return entry["id"]

if __name__ == "__main__":
    # 測試
    add_memory("Hermes", "測試", "記憶寫入工具測試")
    print("✅ memory_helper 測試完成")
