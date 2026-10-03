# -*- coding: utf-8 -*-
"""verify_performance_monthly.py — 「投資績效｜月度比較」防回歸閘門（唯讀）

驗收條件（使用者 2026-10-03 裁示）：
  A. 頁面每月數字 == performance_core 輸出（唯一真值來源）
  B. 7/8/9/10 月的分類**由 core 狀態決定**，不是前端人工判斷 → 以「突變測試」證明：
     把 core 輸出裡 8 月改成基準月、9 月改成歷史參考後重繪，頁面分區必須跟著變
  C. 累計只計「基準月之後且已完成」的月份；基準月／歷史參考／Baseline／進行中一律不列入
  D. HTML 內不得出現未經 core 產生的績效數字（禁止寫死）
  E. 儀表板按鈕存在、目標檔存在且在版控內
  F. Task 1+2 既有輸出零回歸（呼叫 tools/verify_performance_core_task12.py）

用法：python tools/verify_performance_monthly.py [--keep]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import build_performance_monthly as bpm  # noqa: E402
import performance_core as pc  # noqa: E402

PAGE = BASE / "performance_monthly.html"
NUM_RE = re.compile(r"[+-]?\d{1,3}(?:,\d{3})+")
fails: list[str] = []


def chk(cond: bool, label: str, detail: str = "") -> None:
    print(("  ✅ " if cond else "  ❌ ") + label + (f" — {detail}" if detail else ""))
    if not cond:
        fails.append(label)


def payload_of(html: str) -> dict:
    m = re.search(r'<script id="pm-data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise SystemExit("❌ 頁面缺少 pm-data payload（無法驗證）")
    return json.loads(m.group(1))


def main() -> int:
    keep = "--keep" in sys.argv
    html = PAGE.read_text(encoding="utf-8")
    print("== A. 頁面數字 == core 輸出 ==")
    snap = json.loads(bpm.SNAP.read_text(encoding="utf-8"))
    adjust = json.loads(bpm.ADJ.read_text(encoding="utf-8"))
    import sqlite3
    months = sorted(k for k in adjust if len(k) == 7 and k[4] == "-")
    import datetime as dt
    today = dt.date.today()
    if today.strftime("%Y-%m") not in months:
        months.append(today.strftime("%Y-%m"))
    db = sqlite3.connect(bpm.DB)
    try:
        fresh = pc.monthly_history(months, snap=snap, adjust_all=adjust, db=db, today=today)
    finally:
        db.close()
    emb = payload_of(html)
    chk(json.dumps(emb, sort_keys=True) == json.dumps(fresh, sort_keys=True),
        "頁面內嵌資料 == core 重算（逐欄位）",
        f"{len(fresh['months'])} 個月")
    for m in fresh["months"]:
        shown = m["net"]
        txt = f"{shown:+,.0f}"
        chk(txt in html, f"{m['label']} 淨投資績效 {txt} 出現在頁面",
            f"role={m['role']} usable={m['usable']}")

    print("== B. 分類由 core 決定（突變測試）==")
    mut = json.loads(json.dumps(fresh))
    for m in mut["months"]:
        if m["month"] == "2026-08":
            m["role"], m["role_label"] = pc.ROLE_CAPITAL_BASELINE, pc.ROLE_LABEL[pc.ROLE_CAPITAL_BASELINE]
        if m["month"] == "2026-09":
            m["role"], m["role_label"] = pc.ROLE_REFERENCE, pc.ROLE_LABEL[pc.ROLE_REFERENCE]
    mut["baseline_month"] = "2026-08"
    orig = pc.monthly_history
    pc.monthly_history = lambda *a, **k: mut          # noqa: E731 — 只為重繪測試
    tmp = Path(tempfile.gettempdir()) / "verify_pm_mutation.html"
    try:
        bpm.build(today=today, out_path=tmp)
        mut_html = tmp.read_text(encoding="utf-8")
    finally:
        pc.monthly_history = orig
    if not keep and tmp.exists():
        tmp.unlink()
    base_card = mut_html.split("◆ 資本基準月")[1].split("◆ 基準後累計")[0]
    ref_block = mut_html.split("◆ 歷史參考區（不列入累計）")[1].split("◆ 損益來源")[0]
    chk("2026/08" in base_card, "突變：基準月區跟著 core 改成 2026/08")
    chk("2026/09" in ref_block, "突變：9 月被移到歷史參考區（非寫死）")

    print("== C. 累計口徑 ==")
    acc = fresh["post_accum"]
    post_complete = [m for m in fresh["months"]
                     if m["role"] == pc.ROLE_POST_BASELINE and m["usable"] == pc.USE_COMPLETE]
    chk(acc["n"] == len(post_complete), "累計月數 == 基準後且完成的月數", f"n={acc['n']}")
    chk(acc["n"] == 0 or abs(acc["sum"] - sum(m["net"] for m in post_complete)) < 0.01,
        "累計金額 == 基準後完成月之和")
    excluded = [m["month"] for m in fresh["months"]
                if m["role"] in (pc.ROLE_LEGACY, pc.ROLE_REFERENCE, pc.ROLE_CAPITAL_BASELINE)]
    chk(all(m not in (fresh["post_months"]) for m in excluded),
        "基準月／歷史參考／Baseline 不列入基準後清單", ",".join(excluded))
    chk(sorted(set(fresh["post_months"])) == sorted(
        [m["month"] for m in fresh["months"] if m["role"] == pc.ROLE_POST_BASELINE]),
        "post_months 與 core 角色一致")

    print("== D. 無寫死數字 / 無前端月份判斷 ==")
    def _nums(o, acc):
        if isinstance(o, dict):
            for v in o.values():
                _nums(v, acc)
        elif isinstance(o, list):
            for v in o:
                _nums(v, acc)
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            acc.add(f"{o:+,.0f}")
            acc.add(f"{o:,.0f}")
        return acc

    core_nums = {x.lstrip("+-") for x in _nums(fresh, set())}
    # core 的文字欄位（如 src「國泰轉貸 1,200萬」）也可能含逗號數字 → 一併允許
    core_nums |= {n.lstrip("+-") for n in NUM_RE.findall(json.dumps(fresh, ensure_ascii=False))}
    # 報表另有「該月市值變化小計」（＝core rows 的 mkt 相加，屬 core 衍生物）→ 一併允許
    for m in fresh["months"]:
        s = sum(r["mkt"] for r in m["rows"])
        core_nums |= {f"{s:+,.0f}".lstrip("+-"), f"{s:,.0f}".lstrip("+-")}
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", html, flags=re.S)   # CSS 色彩 tuple 非金額
    body = re.sub(r'<pre id="pm-data-json">.*?</pre>', "", body, flags=re.S)  # core 原始輸出區
    body = body.split('<script id="pm-data"')[0]
    stray = sorted({n for n in NUM_RE.findall(body) if n.lstrip("+-") not in core_nums})
    chk(not stray, "HTML 內沒有 core 未產生的金額", ",".join(stray[:6]))
    blocks = re.findall(r"<script\b[^>]*>.*?</script>", html, re.S)
    blob = "\n".join(b for b in blocks if 'id="pm-data"' not in b)
    chk("2026-0" not in blob and "2026/0" not in blob,
        "非資料 script 內沒有月份字串判斷", f"{len(blocks)} 個 script 區塊")
    chk("if(" not in blob, "inline script 無分支邏輯（純資料）")

    print("== E. 儀表板按鈕 ==")
    idx = (BASE / "index.html").read_text(encoding="utf-8")
    chk('href="performance_monthly.html"' in idx, "index.html 有 performance_monthly.html 連結")
    chk(PAGE.exists(), "performance_monthly.html 存在")
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "performance_monthly.html"],
                             cwd=str(BASE), capture_output=True).returncode == 0
    chk(tracked, "performance_monthly.html 已進版控（否則 Pages 404）")

    print("== F. Task 1+2 零回歸 ==")
    r = subprocess.run([sys.executable, str(BASE / "tools" / "verify_performance_core_task12.py"),
                        "2d1b9ed2"], cwd=str(BASE), capture_output=True, text=True)
    tail = [ln for ln in (r.stdout or "").splitlines() if "驗收" in ln or "FAIL" in ln]
    # 2026-10-03（INC-283）：原本 detail 取「最後一行含 FAIL 者」→ 會把檢查項名稱
    #   「無新增 FAIL（既有 6 條白名單外為空）」貼在「Task1+2 驗證器 PASS」後面，
    #   讀起來像「PASS — FAIL」，把「有 1 條新 FAIL」誤讀成「沒有新增 FAIL」。
    #   改為：摘要行（驗收：PASS x / FAIL y）＋ 逐條列出未過的檢查項名稱。
    _lines = (r.stdout or "").splitlines()
    _summary = next((ln.strip().strip("=").strip() for ln in _lines if "驗收：" in ln), (tail[-1].strip() if tail else ""))
    _failed = [ln.split("FAIL:", 1)[1].strip() for ln in _lines if ln.strip().startswith("FAIL:")]
    chk(r.returncode == 0, "Task1+2 驗證器零回歸（rc=0）",
        (_summary + ("｜未過檢查項：" + "、".join(_failed) if _failed else "")).strip())

    total = 12 + len(fresh["months"]) + 14
    print(f"\n=== 月度比較閘門：{'PASS' if not fails else 'FAIL'}（FAIL {len(fails)}）===")
    for f in fails:
        print("  - " + f)
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
