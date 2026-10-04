#!/usr/bin/env python3
"""verify_pi_sot_20261004.py — PI 雙軌建檔＋質押四概念分離 唯讀驗證器

範圍：sot_targets.py（狀態機）、sync_professional_investor.py（白名單過濾）、
      snapshot.json（PI 容器＋cathay_pledge_0911 四概念標註）

相對式斷言：不寫死當期真值（金額現算）、不假設交付前狀態。
唯讀：不寫任何 repo 檔案（writer 一律 --dry-run）。
exit 0 = ALL PASS；exit 1 = 有 FAIL。
"""
import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PRE_FIX_SHA = "a9d7c3c49baf21708b3637a1235b40e18912c956"   # 本批修改前的 HEAD
CHANGED = ["sot_targets.py", "sync_professional_investor.py", "debt_restructure_tracker.py",
           "annotate_pledge_facts_20261004.py", "tests/pi_e2e_closure_20261004.py"]

PASS, FAIL = [], []


def chk(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅ PASS' if cond else '❌ FAIL'}  {name}" + (f"　{detail}" if detail else ""))


print("=" * 64)
print("驗證：PI 雙軌建檔 + 質押四概念分離（唯讀）")
print("=" * 64)

# ---------- ① 語法閘門 ----------
print("\n[1] 語法閘門（本批改動檔）")
r = subprocess.run([sys.executable, "-m", "py_compile"] + CHANGED, cwd=BASE,
                   capture_output=True, text=True)
chk(f"{len(CHANGED)} 檔 py_compile", r.returncode == 0, (r.stderr or "").strip()[:120])

# ---------- ② 狀態機：含終態「已完成」、拒絕非法值 ----------
print("\n[2] 狀態機（sot_targets）")
import sot_targets as sot
chk("PI_APPLICATION_STATES 含『已完成』", "已完成" in sot.PI_APPLICATION_STATES,
    "／".join(sot.PI_APPLICATION_STATES))
chk("approval 狀態集未變", sot.PI_APPROVAL_STATES == ("未核准", "已核准", "未通過", "失效"))
_d = {"professional_investor": {"application_status": "已完成", "approval_status": "已核准"}}
try:
    chk("已完成 可通過驗證", sot.pi_record(_d)["application_status"] == "已完成")
except Exception as e:
    chk("已完成 可通過驗證", False, repr(e))
for bad in ("已認列", "核准", ""):
    _b = {"professional_investor": {"application_status": bad, "approval_status": "已核准"}}
    try:
        sot.pi_record(_b)
        chk(f"非法 application_status {bad!r} → raise", False, "未 raise")
    except Exception:
        chk(f"非法 application_status {bad!r} → raise", True)

# 分軌驗證（2026-10-04 CIO 審查）：跨軌值不得互相通過
for _k, _bad in (("application_status", "已核准"), ("approval_status", "已完成")):
    _x = {"professional_investor": {"application_status": "已完成", "approval_status": "已核准"}}
    _x["professional_investor"][_k] = _bad
    try:
        sot.pi_record(_x)
        chk(f"跨軌值 {_k}={_bad!r} → raise", False, "未 raise（語意污染）")
    except Exception:
        chk(f"跨軌值 {_k}={_bad!r} → raise", True)

# ---------- ③ bug 重現：舊寫入者保留未知欄位 / 新寫入者剔除 ----------
print("\n[3] 寫入者 bug 重現（負向對照釘在 pre-fix sha 的 parent 邏輯）")
old_src = subprocess.run(["git", "show", f"{PRE_FIX_SHA}:sync_professional_investor.py"],
                         cwd=BASE, capture_output=True, text=True).stdout
chk("pre-fix 版本為『只過濾 DERIVED_KEYS』",
    'if k not in DERIVED_KEYS}' in old_src and 'if k in _known and k not in DERIVED_KEYS' not in old_src)
new_src = (BASE / "sync_professional_investor.py").read_text(encoding="utf-8")
chk("本版改為白名單過濾（k in _known）", "if k in _known and k not in DERIVED_KEYS" in new_src)

_FIXTURE = {"pi_status": "✅ 已核定", "applied_date": "2026-08-21",
            "deployment_plan": {"x": 1}, "note": "n"}
_KNOWN = {"note", "force_order", "macro_triggers", "forbidden", "lombard_bridge",
          "risk_warning", "strategy", "application_status", "approval_status",
          "source", "updated_at"}
_DERIVED = ("threshold_twd", "financial_assets_proxy_twd", "gap_twd",
            "meets_financial_threshold", "current")
_old_keep = {k: v for k, v in _FIXTURE.items() if k not in _DERIVED}
_new_keep = {k: v for k, v in _FIXTURE.items() if k in _KNOWN and k not in _DERIVED}
chk("舊邏輯保留 pi_status（＝缺陷存在）", "pi_status" in _old_keep and "deployment_plan" in _old_keep)
chk("新邏輯剔除 pi_status/deployment_plan", "pi_status" not in _new_keep and "deployment_plan" not in _new_keep)
chk("新邏輯保留合法欄位 note", "note" in _new_keep)

dr = subprocess.run([sys.executable, "sync_professional_investor.py",
                     "--application-status", "已完成", "--approval-status", "已核准",
                     "--source", "verify", "--dry-run"], cwd=BASE, capture_output=True, text=True)
chk("writer --dry-run 可執行（不寫檔）", dr.returncode == 0, (dr.stderr or "").strip()[:100])
_newline = next((l for l in dr.stdout.splitlines() if l.strip().startswith("新：")), "")
chk("dry-run 產出不含 pi_status / deployment_plan",
    _newline and "pi_status" not in _newline and "deployment_plan" not in _newline)

# ---------- ④ 真值：PI 容器欄位集與狀態 ----------
print("\n[4] 真值（snapshot.professional_investor）")
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
pi = snap.get("professional_investor") or {}
core = {"application_status", "approval_status", "source", "updated_at"}
chk("四個 persistent 欄位齊備", core <= set(pi), "／".join(sorted(pi)))
chk("approval_status == 已核准", pi.get("approval_status") == "已核准")
chk("application_status 為合法狀態", pi.get("application_status") in sot.PI_APPLICATION_STATES,
    str(pi.get("application_status")))
chk("容器內無舊欄位 pi_status／deployment_plan",
    "pi_status" not in pi and "deployment_plan" not in pi)
chk("容器內無衍生值落地（threshold／gap／current）",
    not ({"threshold_twd", "financial_assets_proxy_twd", "gap_twd", "current"} & set(pi)))

# 雙軌分離：資格軌為真，同時財力軌未達（不得互相推導）
chk("pi_is_approved() == True", sot.pi_is_approved(snap) is True)
_proxy, _thr = sot.pi_financial_asset_proxy(snap), sot.pi_regulatory_threshold()
chk("財力 proxy 未達門檻（現算）", _proxy < _thr, f"{_proxy:,.0f} / {_thr:,}")
chk("pi_meets_financial_threshold() == False", sot.pi_meets_financial_threshold(snap) is False)

# ---------- ⑤ 質押四概念（禁 credit_limit） ----------
print("\n[5] 質押四概念分離（cathay_pledge_0911）")
cp = snap.get("cathay_pledge_0911") or {}
chk("未建立 credit_limit_twd 欄位", "credit_limit_twd" not in cp)
chk("銀行核定授信額度為 null（未取得文件）", cp.get("銀行核定授信額度") is None)
chk("有『不得反推剩餘』的狀態說明",
    "不得" in str(cp.get("銀行核定授信額度狀態", "")))
chk("額度_本金語意已更正為成本口徑（非授信額度）",
    "非銀行核定授信額度" in str(cp.get("額度_本金語意", "")))
chk("四概念分離區塊存在", isinstance(cp.get("四概念分離_20261004"), dict))
chk("質押標的已具名（非類別標籤）", isinstance(cp.get("質押標的"), list) and len(cp["質押標的"]) == 3)
_drawn = snap.get("fund_pledge_loan")
chk("實際動用額現算與質押記錄一致", _drawn == cp.get("可貸金額"), f"{_drawn:,}")
chk("pledge_ltv accessor == 動用 ÷ 擔保池合計",
    abs(sot.pledge_ltv(snap) - _drawn / float(cp["擔保池"]["合計"])) < 1e-9,
    f"{sot.pledge_ltv(snap)*100:.2f}%")

# ---------- ⑥ 消費者 smoke ----------
print("\n[6] 消費者 import smoke")
for m in ("pi_card", "report_components", "pledge_status", "coast_fi_engine", "market_indicator_panel"):
    r = subprocess.run([sys.executable, "-c", f"import {m}"], cwd=BASE, capture_output=True, text=True)
    chk(f"import {m}", r.returncode == 0, (r.stderr or "").strip().splitlines()[-1][:80] if r.stderr else "")

# ---------- ⑦ E2E 回歸 ----------
print("\n[7] E2E 回歸（tests/pi_e2e_closure_20261004.py）")
import os
env = dict(os.environ, LJ_NO_TELEGRAM="1", TG_TOKEN="", TG_CHAT_ID="")
r = subprocess.run([sys.executable, "tests/pi_e2e_closure_20261004.py"], cwd=BASE,
                   capture_output=True, text=True, env=env, timeout=600)
_last = [l for l in (r.stdout or "").splitlines() if l.startswith("總計")]
chk("E2E exit 0 且 0 FAIL", r.returncode == 0 and (_last and "FAIL 0" in _last[0]),
    _last[0] if _last else (r.stderr or "")[-120:])

# ---------- ⑧ 下游回歸：debt_restructure_tracker §4 質押真值 ----------
# 2026-10-04 自查：PI 容器收斂（移除 deployment_plan）後，本檔 §4 原讀 plan["current_ltv"]，
# 會退化成 0% 假綠燈並印出 7 月寫死的「股票600+平衡300~600」。此段釘住該回歸。
print("\n[8] 回歸：debt_restructure_tracker §4 質押真值")
_env = dict(os.environ, LJ_NO_TELEGRAM="1", TG_TOKEN="", TG_CHAT_ID="")
_t = subprocess.run([sys.executable, "debt_restructure_tracker.py"], cwd=BASE,
                    capture_output=True, text=True, env=_env, timeout=600)
_o = _t.stdout or ""
chk("§4 未退化成 0% 假綠燈", "current_LTV_ratio = 0%（尚未質押）" not in _o)
chk(f"§4 LTV 值 == pledge_ltv 現算（{sot.pledge_ltv(snap)*100:.1f}%）",
    f"current_LTV_ratio = {sot.pledge_ltv(snap)*100:.1f}%" in _o)
chk("§4 不再出現 7 月寫死的『股票600+平衡』", "股票600+平衡" not in _o)
chk("§4 顯示實際動用額（現算）", f"{_drawn:,.0f}" in _o, f"{_drawn:,.0f}")

# ---------- 總結 ----------
print("\n" + "=" * 64)
print(f"合計 {len(PASS)+len(FAIL)} 項｜PASS {len(PASS)}｜FAIL {len(FAIL)}")
for n in FAIL:
    print(f"  ❌ {n}")
print("=" * 64)
sys.exit(1 if FAIL else 0)
