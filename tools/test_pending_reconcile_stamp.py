#!/usr/bin/env python3
"""pending_reconcile 時間戳同步與 streak 語意測試（2026-10-15 建立）

來由（真 CIO 審查 finding，2026-10-15 對 13bd9b28 的 REJECT）：
  ① 真缺陷：pending_reconcile 只寫 status_raw／status，未維護 updated_at →
     「敘述已重算到 10-15、updated_at 仍停在 10-14」的資料一致性缺陷。
  ② 語意混用：status 只寫「紅線連續 N 日」未標門檻，與「模式A（≥5.20%）連續日數」
     混讀 → 審查者拿模式A 的 32／33 質疑紅線的 17。

本測試以「複製最小檔案集到暫存目錄、跑真 --apply」驗證，不動 repo 產物：
  T1 時間戳自我修復：status_raw 已有當日重算戳、updated_at 落後 → 補正且敘述不動
  T2 狀態重算同步：敘述更新時 updated_at 一起更新
  T3 負向：規則未命中的卡片 → status_raw／updated_at 皆不動
  T4 守恆：pending＋archive 筆數不變
  T5 語意：敘述中的紅線數字 == us30y_state.red_line_streak，且能被區別於 mode_a_streak

跑法：python tools/test_pending_reconcile_stamp.py（全過 exit 0）
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}{(' — ' + detail) if detail else ''}")


_COPY = ["pending_reconcile.py", "pending_engine.py", "pending_store.py", "sot_targets.py",
         "snapshot.json", "us30y_state.json"]


def _fixture_card(title: str, status_raw: str, updated_at: str, pid: str) -> dict:
    return {"id": pid, "date": "2026-10-01", "title": title, "status": "🟡 執行中",
            "status_raw": status_raw, "updated_at": updated_at,
            "tags": "測試", "detail": "測試用 fixture（不得寫回 repo）"}


def run_reconcile(cards: list[dict]) -> tuple[dict, str]:
    """在暫存目錄跑真 --apply，回 (寫入後的 pending 結構, stdout)。"""
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        for f in _COPY:
            src = BASE / f
            if src.exists():
                shutil.copy2(src, t / f)
        (t / "pending_decisions.json").write_text(
            json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
        (t / "pending_decisions_archive.json").write_text("[]", encoding="utf-8")
        p = subprocess.run([sys.executable, "-X", "utf8", str(t / "pending_reconcile.py"), "--apply"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           cwd=str(t), timeout=300)
        out = (p.stdout or "") + (p.stderr or "")
        res = json.loads((t / "pending_decisions.json").read_text(encoding="utf-8"))
        arch = json.loads((t / "pending_decisions_archive.json").read_text(encoding="utf-8"))
        return {"pend": res, "arch": arch, "out": out}, out


def main() -> int:
    print("=== pending_reconcile 時間戳同步／streak 語意（2026-10-15 審查 finding） ===")
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    today = str(snap.get("date"))
    st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
    rl, ma = st.get("red_line_streak"), st.get("mode_a_streak")

    _t = "台股解凍後分批規則定版（節奏／單次上限／停止條件）"
    # 先取得「規則產出的標準敘述」——自我修復分支（T1）必須以完全相同內容為前提，
    # 否則會走「狀態重算」而非「時間戳同步」，測不到 self-heal 路徑。
    _probe = run_reconcile([_fixture_card(_t, "🟡 舊敘述", "2026-10-01T09:00:00+08:00", "P-T0")])[0]
    _canon = str(_probe["pend"][0].get("status_raw")).split(" ｜ 舊 raw：")[0]
    check("T0 前提：可取得規則產出的標準敘述（自我修復分支的前提）",
          "紅線（≥5.30%）連續" in _canon, _canon[:80])

    # T1：敘述＝規則產出內容、但 updated_at 落後一天 → 只補時間戳（不動敘述）
    _lag_card = _fixture_card(_t, _canon, "2026-10-14T22:10:03+08:00", "P-T1")
    out = run_reconcile([_lag_card])[0]
    _c = out["pend"][0]
    check(f"T1 自我修復：updated_at 由 10-14 補正為 {today}（敘述逐字不變）",
          str(_c.get("updated_at"))[:10] == today and str(_c.get("status_raw")) == _canon,
          f"updated_at={_c.get('updated_at')}")
    check("T1b 修復以『時間戳同步』動作揭露（可稽核）", "時間戳同步" in out["out"], out["out"][-200:])

    # T2：敘述更新（含新語意）＋ updated_at 同步
    _stale_card = _fixture_card(_t, "🟡 舊敘述（2026-10-01真值重算）",
                                "2026-10-01T09:00:00+08:00", "P-T2")
    out2 = run_reconcile([_stale_card])[0]
    _c2 = out2["pend"][0]
    _raw2 = str(_c2.get("status_raw"))
    check(f"T2 狀態重算：updated_at 同步為 {today}", str(_c2.get("updated_at"))[:10] == today,
          f"updated_at={_c2.get('updated_at')}")

    # T5：語意（紅線口徑 vs 模式A）——紅線值取真值源、兩者都被標明
    check(f"T5 敘述區分兩個口徑（紅線（≥5.30%）連續 {rl} 交易日／模式A警戒（≥5.20%）連續 {ma} 日）",
          f"紅線（≥5.30%）連續 {rl} 交易日" in _raw2
          and f"模式A警戒（≥5.20%）連續 {ma} 日" in _raw2, _raw2[:160])
    check("T5b 紅線數字 ≠ 模式A 數字（不得再混用同一 streak）",
          rl != ma and f"紅線（≥5.30%）連續 {ma} " not in _raw2,
          f"rl={rl} ma={ma}")

    # T3：規則未命中的卡片不得被動到（負向）
    _unhit = _fixture_card("純測試卡片（不匹配任何規則）", "🟡 原始敘述", "2026-10-14T10:00:00+08:00", "P-T3")
    out3 = run_reconcile([_unhit])[0]
    _c3 = out3["pend"][0]
    check("T3 負向：未命中規則的卡片 → status_raw／updated_at 皆不動",
          _c3.get("status_raw") == "🟡 原始敘述" and str(_c3.get("updated_at")).startswith("2026-10-14"),
          f"raw={_c3.get('status_raw')} ts={_c3.get('updated_at')}")

    # T4：守恆
    out4 = run_reconcile([_lag_card, _stale_card, _unhit])[0]
    check("T4 守恆：pending＋archive 筆數不變（3 → 3）",
          len(out4["pend"]) + len(out4["arch"]) == 3,
          f"pend={len(out4['pend'])} arch={len(out4['arch'])}")

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
