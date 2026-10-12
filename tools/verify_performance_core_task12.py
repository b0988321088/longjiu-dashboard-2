# -*- coding: utf-8 -*-
"""verify_performance_core_task12.py — INC-282 A 案 Task 1+2 唯讀驗證器（永久 regression）。

驗收條件（使用者 2026-10-03 裁示）：Task 1「純新檔、不改既有行為」＋ Task 2「重產後既有輸出逐位元不變」。
本驗證器只讀 repo，所有實際執行都在 %TEMP% 沙盒複本上跑（不寫任何 repo 產物）。

用法：
    python tools/verify_performance_core_task12.py [commit]     # commit 預設 HEAD

檢查項：
    1. tree 綁定（被審 commit 的 tree 與 git 實際相符）
    2. AST 可解析（performance_core.py / build_mtd_report.py / build_investment_performance.py）
    3. performance_core 重現三個閉月 net：2026-07 100,649｜2026-08 428,802｜2026-09 6,315
    4. A/B 逐位元：舊版（parent commit）vs 新版（工作區）
         · mtd_performance.html / mtd_data.json → 相同（僅遮罩 generated_at 時間戳）
         · investment_performance.html → 完全相同
         · 兩支 console 輸出（TG 月報文字）→ 完全相同
    5. 既有閘門無新增 FAIL（check_dividend_caliber FAIL 白名單）

離線可跑；失敗 exit 1。
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
# 2026-10-12（使用者核准 A｜依設計文件校正 F1）：
#   `--contract-only`＝F1 封版契約模式。依 .hermes/plans/2026-10-09_220000-perf-gate-decoupling-design.md §2.1，
#   F1 的斷言只有「可解析／stat 僅含 4 檔／AST／performance_core 重現 7/8/9 月 net」，
#   且該文件在 C1 列明文寫「不是『該 commit 與現在的工作區逐位元相同』」。
#   故逐位元 A/B（含 console）在此模式僅呈現、不計入契約；不帶旗標時行為完全不變（仍為 FAIL 並 rc=1）。
CONTRACT_ONLY = "--contract-only" in sys.argv
_ARGV = [a for a in sys.argv[1:] if not a.startswith("--")]
SHA = _ARGV[0] if _ARGV else "HEAD"

PASS, FAIL = [], []


def chk(name: str, cond: bool, detail: str = "") -> None:
    (PASS if cond else FAIL).append(name)
    print(("  ✅ " if cond else "  ❌ ") + name + (f" — {detail}" if detail else ""))


AB_REPORT = []


def chk_ab(name: str, cond: bool, detail: str = "") -> None:
    """逐位元 A/B 項（自 2026-10-03 封版基準的輸出漂移比較）。

    2026-10-12（使用者核准 A）：依設計文件 §2.1／C1，本類不比對「封版 commit 與現在工作區
    逐位元相同」，故 F1 契約模式（--contract-only）下僅呈現、不計入 PASS/FAIL 與 rc；
    不帶旗標時仍照舊判定，作為獨立的「零輸出漂移」報告。
    """
    AB_REPORT.append((name, bool(cond), detail))
    if CONTRACT_ONLY:
        print(("  · " if cond else "  ⚠️ ") + name + (f" — {detail}" if detail else "")
              + "   ［輸出漂移報告項，不計入 F1 契約］")
        return
    chk(name, cond, detail)


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def run(cmd: list[str], cwd: Path, timeout: int = 300):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout,
                          env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})


CODEFILES = ["performance_core.py", "build_mtd_report.py", "build_investment_performance.py"]
COMMIT_FILES = CODEFILES + ["tools/verify_performance_core_task12.py"]
GATES = ["mtd_performance.html", "mtd_data.json", "investment_performance.html"]
KNOWN_GATE_FAILS = {
    "可動用現金＝cash_layers.available（唯一真值）",
    "穿透桶『現金/安全網』＝可動用＋在途未對帳（不得參與決策）",
    "穿透桶口徑＝可動用＋589 在途／未對帳（不得參與決策）",
    "穿透桶『現金/安全網』不得當可動用（在途／未對帳）",
    # 2026-10-05（使用者核准 PEND-20261005-04）：以下兩條原本被白名單吸收 → 回歸擋關能力實際失效
    # （CIO 審查 35a33be1 的 known limit）。已施工修掉根源並**自白名單釋放**：
    #   · "Pending schema 五欄齊備（26 筆一次遷移）" → 檢查改動態口徑（名稱改為「全卡動態」，已不再 FAIL）
    #   · "status 正規化為四態（原字串保留 status_raw）" → 5 張非 ENUM 的 status 逐張正規化（原字串保留）
    # 釋放後：任何新卡若欄位缺漏或 status 跑出四態，閘門會真的亮紅（不得再靠白名單吸收）。
}

print("== 1. tree 綁定 ==")
_sha = git("rev-parse", f"{SHA}^{{commit}}").strip().splitlines()[0] if git("rev-parse", f"{SHA}^{{commit}}").strip() else ""
chk("被審 commit 可解析", len(_sha) == 40, _sha[:12])
ST = git("show", "--stat", "--format=", _sha).strip()
chk("commit 只動本批 4 檔（範圍乾淨）",
    all(f in ST for f in COMMIT_FILES) and ST.count("|") == len(COMMIT_FILES),
    ST.replace("\n", " ")[:160])

print("== 2. AST ==")
for f in CODEFILES:
    try:
        import ast
        ast.parse((REPO / f).read_text(encoding="utf-8"))
        chk(f"AST 可解析：{f}", True)
    except Exception as e:  # noqa: BLE001
        chk(f"AST 可解析：{f}", False, str(e)[:80])

print("== 3. 唯一計算層重現三個閉月 ==")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))   # 2026-10-11：受限標籤遮罩正規化（tools/label_mask.py）
import label_mask as _label_mask  # noqa: E402
import performance_core as pc  # noqa: E402
_snap = json.loads((REPO / "snapshot.json").read_text(encoding="utf-8"))
_adj = json.loads((REPO / "investment_performance_adjust.json").read_text(encoding="utf-8"))
_db = sqlite3.connect(str(REPO / "dragon_assets.db"))
for _ym, _want in (("2026-07", 100649), ("2026-08", 428802), ("2026-09", 6315)):
    _r = pc.monthly_performance(_ym, snap=_snap, adjust_all=_adj, db=_db)
    chk(f"{_ym} net = {_want:,}", abs(_r["net"] - _want) < 0.5, f"實得 {_r['net']:,.0f}")
_db.close()
_chk_core = (REPO / "build_mtd_report.py").read_text(encoding="utf-8")
chk("mtd 閉月已改讀 performance_core（無自家重算）", "perf_core.monthly_performance(" in _chk_core)
chk("bip 已改讀 performance_core", "_perf_core.monthly_performance(" in (REPO / "build_investment_performance.py").read_text(encoding="utf-8"))
chk("bip 已無第二份配息分類表（_MAP 移除）", "_MAP = {" not in (REPO / "build_investment_performance.py").read_text(encoding="utf-8"))

print("== 4. A/B 逐位元（%TEMP% 沙盒；舊版 = parent commit）==")
SB = Path(tempfile.gettempdir()) / "verify_pc_task12"
if SB.exists():
    shutil.rmtree(SB)
SB.mkdir(parents=True)
# 2026-10-12（使用者核准擴範圍 +1 檔；CIO blocking #1）：
#   build_mtd_report.py 的依賴模組必須與 CODEFILES 一起進沙盒，否則沙盒 ModuleNotFoundError
#   → 「A/B 新版可執行」rc≠0、連帶 F1 封版契約 FAIL（實踩：新增 import notion_weekly_trend_wrapper）。
#   新增任何模組層級依賴都要同步本清單（build_mtd_report 現依賴：bip／performance_core＋下列模組）。
_MODULE_DEPS = ("notion_weekly_trend_wrapper.py",)
for f in ("snapshot.json", "dragon_assets.db", "investment_performance_adjust.json",
          "dividend_caliber.py", "sot_targets.py") + _MODULE_DEPS:
    shutil.copy2(REPO / f, SB / f)

_par = {}
for f in CODEFILES:
    src = git("show", f"{_sha}^:{f}")
    _par[f] = bool(src.strip())
    (SB / f).write_text(src, encoding="utf-8")

_run_old = []
for f in ("mtd_performance.html", "mtd_data.json", "investment_performance.html"):
    _run_old.append(True)
_r1 = run([PY, "build_mtd_report.py"], SB)
_r2 = run([PY, "build_investment_performance.py"], SB)
chk("A/B 舊版可執行", _r1.returncode == 0 and _r2.returncode == 0, f"rc={_r1.returncode}/{_r2.returncode}")
(SB / "_old").mkdir(exist_ok=True)
for f in GATES:
    if (SB / f).exists():
        shutil.copy2(SB / f, SB / "_old" / f)
(SB / "_old" / "mtd.log").write_text(_r1.stdout + _r1.stderr, encoding="utf-8")
(SB / "_old" / "bip.log").write_text(_r2.stdout + _r2.stderr, encoding="utf-8")

for f in CODEFILES:
    shutil.copy2(REPO / f, SB / f)
_t_new = time.time()
_r3 = run([PY, "build_mtd_report.py"], SB)
_r4 = run([PY, "build_investment_performance.py"], SB)
chk("A/B 新版可執行", _r3.returncode == 0 and _r4.returncode == 0, f"rc={_r3.returncode}/{_r4.returncode}")


def _fresh_after_build(path: Path, since: float) -> bool:
    """該產物是否真的由本輪「新版」子程序重產（非沿用沙盒殘留）。

    2026-10-12（使用者核准擴範圍 +1 檔；CIO blocking #2）：
      新版 builder rc≠0 時，受測檔案其實從未被產出 → 舊檔互比會得到假 PASS，
      內容保護在最需要它的失敗模式下失效。故此處一律 fail-closed。
    """
    try:
        return path.exists() and path.stat().st_mtime >= since
    except OSError:
        return False
# 2026-10-11：把「新版」console 落地到沙盒，供 tools/test_label_mask.py 做真實 A/B
#   （原本測試找不到新版 log → T14/T14b 長期靜默略過；獨立 CIO 審查 required_fix #4）
for _n, _r in (("_new_mtd.log", _r3), ("_new_bip.log", _r4)):
    (SB / _n).write_text(_r.stdout + _r.stderr, encoding="utf-8")


def _norm_ts(t: str) -> str:
    return re.sub(r'"generated_at": "[\d\- :]+"', '"generated_at": "<TS>"', t)


for f in ("mtd_performance.html", "mtd_data.json"):
    if not _fresh_after_build(SB / f, _t_new):
        chk_ab(f"逐位元相同（僅遮罩 generated_at）：{f}", False,
               f"新版 builder rc={_r3.returncode}／產物未重產 → fail-closed（禁止舊檔互比）")
        continue
    a = _norm_ts((SB / f).read_text(encoding="utf-8", errors="replace"))
    b = _norm_ts((SB / "_old" / f).read_text(encoding="utf-8", errors="replace"))
    chk_ab(f"逐位元相同（僅遮罩 generated_at）：{f}", a == b, f"{len(a)} vs {len(b)} chars")
a = (SB / "investment_performance.html").read_bytes() if (SB / "investment_performance.html").exists() else None
b = (SB / "_old" / "investment_performance.html").read_bytes() if (SB / "_old" / "investment_performance.html").exists() else None
# 2026-10-11（使用者裁決「受限契約正規化」）：本項改為「正規化後完全相同」。
#   唯一被正規化的欄位＝保單標籤代號（第一金 FJ<2> / vs FJ<2>，數值型或遮罩型一律視為等價）；
#   任何非標籤差異仍會 FAIL（tools/label_mask.py 的 same_after_mask ＋ test_label_mask.py T3–T5）。
if a is None or b is None or not _fresh_after_build(SB / "investment_performance.html", _t_new):
    chk_ab("逐位元完全相同（標籤遮罩正規化後）：investment_performance.html", False,
           "A/B 產物缺失或未由新版重產 → fail-closed（不完整產物不得冒充通過）")
else:
    chk_ab("逐位元完全相同（標籤遮罩正規化後）：investment_performance.html",
           _label_mask.same_after_mask(a, b), f"{len(a)} vs {len(b)} bytes")
    # 2026-10-11（獨立 CIO 審查 required_fix #1）：A/B 不再比對標籤代號，缺口用「正向遮罩斷言」補回。
    #   出貨頁面必須是遮罩型；若哪天又輸出未遮罩數值代號（re-leak），本條轉紅。
    #   覆蓋範圍界線（CIO 第二輪 RF#1 之二選一，採「明文記錄」）：本斷言只套 bip 頁。
    #   mtd_performance.html 仍含未遮罩代號（來源 build_mtd_report.py 硬編，屬既有狀態），硬套會誤傷，
    #   且使用者本票界線明定「不擴大至其他頁面」→ mtd 頁目前僅靠「逐位元 A/B（僅遮罩 generated_at）」
    #   保護內容變更；待 PEND-20261011-07 完成遮罩清理後，再把本斷言擴及 mtd 頁。
    _pg = a.decode("utf-8", "replace")
    chk("標籤遮罩未回歸：investment_performance.html 無未遮罩代號",
        not _label_mask.has_unmasked_label(_pg), "出現 第一金 FJ<數字>／vs FJ<數字> 即視為遮罩回歸")
_o1, _o2 = _r3.stdout + _r3.stderr, _r1.stdout + _r1.stderr
_o3, _o4 = _r4.stdout + _r4.stderr, _r2.stdout + _r2.stderr
if not _o1.strip() or not _o2.strip():
    chk_ab("console/TG 文字相同：build_mtd_report", False, "console 輸出為空 → fail-closed")
else:
    # 2026-10-11（獨立 CIO 審查 required_fix #2）：獨立重現證明 mtd console 舊/新逐位元相同，
    #   本項無須放寬 → 維持原始位元相等（唯一放寬面只留真的非放寬不可的 bip console）。
    chk_ab("console/TG 文字相同：build_mtd_report", _o1 == _o2)
if not _o3.strip() or not _o4.strip():
    chk_ab("console/TG 文字相同（標籤遮罩正規化後）：build_investment_performance", False,
           "console 輸出為空 → fail-closed")
else:
    chk_ab("console/TG 文字相同（標籤遮罩正規化後）：build_investment_performance",
           _label_mask.same_after_mask(_o3, _o4))

print("== 5. 環境健康度（獨立呈現；不計入 Task 1+2 契約）==")
# 2026-10-09（Phase 03，設計 v2 §2.3）：**解耦**。
#   原設計把「現行 check_dividend_caliber 的即時紅燈」計入 Task 1+2 的 rc，
#   造成跨任務／跨時間耦合：白名單凍結後新增的無關紅燈會被算成本契約的回歸
#   （Phase 01 實證：月度閘門 F 項唯一 FAIL 的真因）。
#   改為：本節只「報告」環境狀態並輸出結構化 ENV_JSON，**不寫入 FAIL**；
#   分類與判定交由月度閘門 F3（受治理快照）獨立負責 → 單一判定來源。
_g = run([PY, "check_dividend_caliber.py"], REPO, timeout=600)
_gate_out = (_g.stdout or "") + (_g.stderr or "")
_m = re.search(r"(\d+)/(\d+) PASS.*?FAIL: \[(.*?)\]", _gate_out, re.S)
ENV = {"gate": "check_dividend_caliber", "parseable": False,
       "pass_count": None, "total": None, "fail_names": []}
if not _m:
    print("  ⚠️ 環境健康度：check_dividend_caliber 輸出無法解析（不計入本契約；F3 應 FAIL-CLOSED）")
else:
    ENV["parseable"] = True
    ENV["pass_count"], ENV["total"] = int(_m.group(1)), int(_m.group(2))
    ENV["fail_names"] = re.findall(r"'([^']+)'", _m.group(3))
    print(f"  ℹ️ 環境狀態：{ENV['pass_count']}/{ENV['total']} PASS｜紅燈 {len(ENV['fail_names'])} 條"
          f"（分類與判定由月度閘門 F3 負責，本契約不計入）")
    print("  （不計入本契約的原始清單）")
    for _n in ENV["fail_names"]:
        print("     ・", _n)
print("ENV_JSON:" + json.dumps(ENV, ensure_ascii=False))

# 2026-10-12（使用者核准 A）：輸出漂移報告——獨立於 F1 契約呈現
if AB_REPORT:
    _ab_bad = [n for n, ok, _ in AB_REPORT if not ok]
    print(f"\n=== 輸出漂移報告（2026-10-03 封版基準 2d1b9ed2^；獨立報告，不計入 F1 契約）===")
    print(f"  {len(AB_REPORT) - len(_ab_bad)}/{len(AB_REPORT)} 項與封版基準逐位元一致"
          + ("；差異項：" + "、".join(_ab_bad) if _ab_bad else "（無差異）"))
    print("  註：本報告僅供可見性；mtd 頁面內容變更屬已核准的本輪交付，不需與封版基準相同。")

print(f"\n=== Task 1+2 驗收：PASS {len(PASS)} / FAIL {len(FAIL)} ===")
for f in FAIL:
    print("  FAIL:", f)
sys.exit(1 if FAIL else 0)
