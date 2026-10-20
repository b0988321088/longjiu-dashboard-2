# -*- coding: utf-8 -*-
"""test_f3_monthly_chain.py — F3 月度比較鏈回歸測試（2026-10-21 一次性根因修復）

背景（兩次連續失敗）：
  · 2026-10-20 07:00：F3「due_date 一律來自既有文字（不猜、不推算）」FAIL → 產線 rc=1
  · 2026-10-21 07:00：F3「status 正規化為四態（原字串保留 status_raw）」FAIL → 產線 rc=1

根因：
  ① due_date：卡片 due_date_source 寫成推算式文字（非「既有文字…」開頭）→ 屬資料違規，
     閘門判定正確，修法是修資料（47f41c73），不是放寬檢查。
  ② status：卡片 status 直接寫自由文字「進行中」；pending_engine.norm_status 的
     「已確認」關鍵詞表漏了「進行中」→ 正規化鏈無法覆蓋此同義詞，卡片停在非四態值。

修法（不刪檢查、不放寬、不擴白名單）：
  · norm_status 增補「進行中」→ 已確認（單一來源補同義詞）
  · 三個謂詞移入 pending_engine（status_violations／due_date_source_violations／
    missing_due_date_flag），閘門與本測試共用同一份實作，避免兩份邏輯漂移
  · 資料修復：PEND-20261020-02 status → 已確認，status_raw 保留「進行中」

本檔同時驗「正常／異常／缺漏」三態與「閘門是否仍 fail-closed」。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import pending_engine as pe  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def ck(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), str(detail)[:160]))


def card(**kw) -> dict:
    base = {"id": "T-1", "title": "測試卡", "status": "待處理", "status_raw": "待處理",
            "due_date": None, "due_date_source": "", "needs_due_date": True}
    base.update(kw)
    return base


items = pe.load_items()
real = {x.get("id"): x for x in items}

# ── A. norm_status 同義詞表（10/21 根因）────────────────────────────────
ck("A1 norm_status('進行中') == 已確認（10/21 根因修復）",
   pe.norm_status("進行中") == "已確認", pe.norm_status("進行中"))
ck("A2 norm_status 仍認得 執行中／核准／HOLD → 已確認",
   all(pe.norm_status(s) == "已確認" for s in ("執行中", "使用者核准", "HOLD 等窗口")),
   [pe.norm_status(s) for s in ("執行中", "使用者核准", "HOLD 等窗口")])
ck("A3 ✅／已完成 → 已完成，關案／作廢 → 關案",
   pe.norm_status("✅ 已結清") == "已完成" and pe.norm_status("關案：已入庫") == "關案",
   [pe.norm_status("✅ 已結清"), pe.norm_status("關案：已入庫")])
ck("A4 未辨識字串仍落 待處理（未因放寬而全數歸「已確認」）",
   pe.norm_status("某個沒定義的說法") == "待處理", pe.norm_status("某個沒定義的說法"))
ck("A5 進行中不得落 待處理（防止關鍵詞日後被移掉）",
   pe.norm_status("進行中") != "待處理", pe.norm_status("進行中"))
ck("A6 norm_status 輸出必為四態之一",
   all(pe.norm_status(s) in pe.STATUS_ENUM
       for s in ("進行中", "執行中", "✅", "關案", "未知", "", "核准")), "四態")

# ── B. status 謂詞：正常／異常／缺漏 ────────────────────────────────────
ck("B1 真實資料 status 違規 = 0", pe.status_violations(items) == [],
   pe.status_violations(items)[:3])
ck("B2 注入「進行中」→ 必須被抓（負向）",
   [t for t, _v in pe.status_violations([card(status="進行中", status_raw="進行中")])] == ["測試卡"],
   pe.status_violations([card(status="進行中", status_raw="進行中")]))
ck("B3 缺 status_raw → 必須被抓（負向）",
   len(pe.status_violations([{k: v for k, v in card().items() if k != "status_raw"}])) == 1,
   pe.status_violations([{k: v for k, v in card().items() if k != "status_raw"}]))
ck("B4 四態皆合法（正常）",
   pe.status_violations([card(status=s, status_raw=s) for s in pe.STATUS_ENUM]) == [], "0 違規")
ck("B5 status=None → 被抓（缺漏）",
   len(pe.status_violations([card(status=None)])) == 1, pe.status_violations([card(status=None)]))
ck("B6 10/21 實際故障卡已修復且原字串保留",
   (real.get("PEND-20261020-02") or {}).get("status") == "已確認"
   and (real.get("PEND-20261020-02") or {}).get("status_raw") == "進行中",
   (real.get("PEND-20261020-02") or {}).get("status"))

# ── C. due_date 來源謂詞（10/20 根因）──────────────────────────────────
ck("C1 真實資料 due_date 來源違規 = 0", pe.due_date_source_violations(items) == [],
   pe.due_date_source_violations(items)[:3])
ck("C2 due_date + 推算式來源 → 必須被抓（10/20 情境再現）",
   pe.due_date_source_violations([card(due_date="2026-11-03", due_date_source="推算自 11/03 檢視日")])
   == ["測試卡"], "推算")
ck("C3 due_date + 來源空白 → 必須被抓（缺漏）",
   pe.due_date_source_violations([card(due_date="2026-11-03", due_date_source="")]) == ["測試卡"], "空白")
ck("C4 due_date + 「既有文字…」→ 合法（正常）",
   pe.due_date_source_violations(
       [card(due_date="2026-11-03", due_date_source="既有文字：保單檢視日 11/03")]) == [], "既有文字")
ck("C5 無 due_date 者不因來源文字被誤抓",
   pe.due_date_source_violations([card(due_date=None, due_date_source="待提供")]) == [], "0")

# ── D. 期限旗標謂詞 ──────────────────────────────────────────────────
ck("D1 真實資料 needs_due_date 違規 = 0", pe.missing_due_date_flag(items) == [],
   pe.missing_due_date_flag(items)[:3])
ck("D2 進行中卡無日期又無旗標 → 被抓（缺漏）",
   pe.missing_due_date_flag([card(status="待處理", due_date=None, needs_due_date=False)])
   == ["測試卡"], "缺旗標")
ck("D3 結案態無日期 → 不抓（不得假紅燈）",
   pe.missing_due_date_flag([card(status="已完成", due_date=None, needs_due_date=False)]) == [], "0")
ck("D4 有 needs_due_date 標記 → 不抓（正常）",
   pe.missing_due_date_flag([card(needs_due_date=True)]) == [], "0")

# ── E. 閘門本身仍 fail-closed（不得靠刪檢查／擴白名單變綠）─────────────
src_cal = (REPO / "check_dividend_caliber.py").read_text(encoding="utf-8", errors="replace")
ck("E1 兩個檢查標籤仍在（未被刪除或改名）",
   "due_date 一律來自既有文字（不猜、不推算）" in src_cal
   and "status 正規化為四態（原字串保留 status_raw）" in src_cal, "標籤存在")
ck("E2 閘門改用共用謂詞（未再內嵌副本）",
   "due_date_source_violations" in src_cal and "status_violations" in src_cal
   and "startswith(\"既有文字\")" not in src_cal, "單一來源")

snap = json.loads((REPO / "tools" / "gate_baseline_dividend_caliber.json").read_text(encoding="utf-8"))
fs = [str(x) for x in (snap.get("fail_set") or [])]
ck("E3 快照 fail_set 未吸收這兩個 FAIL（＝沒有用白名單換綠燈）",
   len(fs) == 4 and not any("status 正規化" in x or "due_date" in x for x in fs), fs)
sys.path.insert(0, str(REPO / "tools"))
import perf_gate_contract as pgc  # noqa: E402
rel = {pgc.norm_check_name(x) for x in pgc.RELEASED_20261005}
ck("E4 2026-10-05 已釋放規則未被回吞",
   "status 正規化為四態" in rel and any("Pending schema 五欄齊備" in x for x in rel), sorted(rel))

# 實跑真閘門（整合）：這兩項不得出現在 FAIL 清單
r = subprocess.run([sys.executable, "check_dividend_caliber.py"], cwd=str(REPO),
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
m = re.search(r"—\s*FAIL:\s*(\[.*?\])\s*$", (r.stdout or "").strip(), re.M)
fails = json.loads(m.group(1).replace("'", '"')) if m else None
ck("E5 實跑閘門：exit 與摘要可解析", m is not None and r.returncode in (0, 1),
   f"rc={r.returncode} fails={fails}")
ck("E6 實跑閘門：這兩項已不在 FAIL（根因已修）",
   fails is not None and not any("status 正規化" in x or "due_date 一律" in x for x in fails), fails)

# ── 合計 ─────────────────────────────────────────────────────────────
p = sum(1 for _n, ok, _d in RESULTS if ok)
for n, ok, d in RESULTS:
    print(f"{'PASS' if ok else 'FAIL'} {n}" + (f"｜{d}" if d else ""))
print("=" * 62)
print(f"合計 {p} PASS / {len(RESULTS) - p} FAIL")
if fails:
    print(f"（閘門其餘 FAIL，非本輪兩項根因，獨立呈現：{fails}）")
sys.exit(0 if p == len(RESULTS) else 1)
