# -*- coding: utf-8 -*-
"""留停門檻／被動收入口徑 唯讀驗證器（2026-09-28 建立；CIO 建議落地進 repo）

為什麼在 repo 裡：原本放在 %TEMP%，暫存一清就沒有自動守門 → 門檻口徑改動失去回歸保護。
設計原則：**相對式斷言**——所有期望值由 snapshot ＋ passive_caliber 現算，
不寫死金額/百分比/日期，因此跨真值日不會自己轉紅（寫死是舊守門腳本爛掉的主因）。

用法（唯讀，不改任何檔）：
    python tools/verify_ficriteria.py                 # repo 自動定位、base 用內建歷史 sha
    python tools/verify_ficriteria.py <repo> <base_sha>

被驗的規格（2026-09-28 使用者裁示）：
  ①留停門檻三條＝保守覆蓋 ≥100% ＋ 壓力情境 ≥100% ＋ 跑道 ≥540 天 ＋ 現金 ≥底線
  ②150% 為「加碼級 A+」理想值，不是門檻
  ③壓力情境採常態配息口徑（常態×0.8＋常態租金−空置）；原「保守配息再×0.8」降為極端情境參考軌，
    且 FI 跑道分母一律用極端情境（數值不得因改版而變動）
"""
from __future__ import annotations

import ast
import glob
import json
import os
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path

# 9/28 口徑改版的前一顆已推版本（釘死 sha，不用 HEAD^／<sha>^：後續疊 commit 會漂掉）
PRE_FI_CRITERIA_SHA = "b4e0f256"
CODE_FILES = ["passive_caliber.py", "sabbatical_checklist_update.py", "coast_fi_engine.py",
              "build_retirement_plan.py", "build_dashboard.py", "build_rebalance_dashboard.py",
              "run_daily.py", "check_dividend_caliber.py"]

_ok = _fail = 0


def ck(name, cond, info=""):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}  {info}")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _latest(repo: Path, pattern: str):
    """取最新一份逐日產物（不寫死日期）。"""
    hits = sorted(glob.glob(str(repo / pattern)))
    return Path(hits[-1]) if hits else None


def main():
    here = Path(__file__).resolve().parent
    repo = Path(sys.argv[1]) if len(sys.argv) > 1 else here.parent
    base = sys.argv[2] if len(sys.argv) > 2 else PRE_FI_CRITERIA_SHA
    if not (repo / "snapshot.json").exists():
        print(f"❌ 找不到 snapshot.json（repo={repo}）")
        return 2

    print("== 1) 語法閘門（口徑相關程式） ==")
    for f in CODE_FILES:
        p = repo / f
        if not p.exists():
            ck(f"ast {f}", False, "檔案不存在")
            continue
        try:
            ast.parse(p.read_text(encoding="utf-8"))
            ck(f"ast {f}", True)
        except Exception as e:  # noqa: BLE001
            ck(f"ast {f}", False, str(e))

    sys.path.insert(0, str(repo))
    snap = json.loads((repo / "snapshot.json").read_text(encoding="utf-8"))
    pc = _load("pc_new", repo / "passive_caliber.py")
    sc = pc.scenarios(snap)
    exp = sc["expense"]
    div_con, div_norm = sc["div_con"], sc["div_norm"]
    rent, vacancy = sc["rent_norm"], sc["vacancy"]

    print("== 2) 情境口徑（相對式：期望值現算，不寫死） ==")
    ck("保守 = 保守配息＋常態租金", round(sc["con"]["income"]) == round(div_con + rent),
       f"{sc['con']['income']}")
    ck("壓力 = 常態配息×0.8＋常態租金−空置（單次打折）",
       round(sc["stress"]["income"]) == round(div_norm * pc.STRESS_DIV_RATIO + rent - vacancy),
       f"{sc['stress']['income']}")
    ck("極端 = 保守配息×0.8＋常態租金−空置（原壓力口徑，降為參考軌）",
       round(sc["extreme"]["income"]) == round(div_con * pc.STRESS_DIV_RATIO + rent - vacancy),
       f"{sc['extreme']['income']}")
    ck("壓力 ≠ 極端（不得雙重打折當判準）",
       round(sc["stress"]["income"]) != round(sc["extreme"]["income"]))
    ck("覆蓋率 = 月被動 ÷ 支出", all(
        abs(sc[k]["coverage"] - sc[k]["income"] / exp * 100) < 0.05 for k in ("con", "act", "stress", "extreme")))
    ck("runway_ref() 指向極端情境（跑道分母單一來源）",
       hasattr(pc, "runway_ref") and abs(pc.runway_ref(sc)["gap"] - sc["extreme"]["gap"]) < 0.01)
    ck("runway_days() = runway_ref() 的跑道天數",
       abs((pc.runway_days(sc) or 0) - (sc["extreme"]["runway_days"] or 0)) < 0.01)

    print("== 3) 舊口徑 bug 重現（base 釘死 sha，證明改版真的修掉雙重打折） ==")
    old_src = subprocess.run(["git", "-C", str(repo), "show", f"{base}:passive_caliber.py"],
                             capture_output=True, text=True, encoding="utf-8")
    if old_src.returncode == 0:
        tmp = Path(tempfile.mkdtemp()) / "pc_old.py"
        tmp.write_text(old_src.stdout, encoding="utf-8")
        old = _load("pc_old", tmp)
        so = old.scenarios(snap)
        ck("舊版壓力情境＝保守配息再打折", round(so["stress"]["income"]) == round(div_con * old.STRESS_DIV_RATIO + rent - vacancy),
           f"{so['stress']['income']}")
        ck("舊版無極端軌", "extreme" not in so)
        ck("新版壓力情境 ≠ 舊版壓力情境（口徑確實改變）",
           round(sc["stress"]["income"]) != round(so["stress"]["income"]))
        ck("新版極端情境 ≡ 舊版壓力情境（舊值未遺失，只是降級）",
           round(sc["extreme"]["income"]) == round(so["stress"]["income"]))
    else:
        ck(f"取得舊版 {base}:passive_caliber.py", False, old_src.stderr[:120])

    print("== 4) 留停門檻邏輯（真 import 呼叫，含變異對照） ==")
    sab = _load("sab", repo / "sabbatical_checklist_update.py")
    # 現金底線一律走 sabbatical._cash_floor(snap) 的單一來源（snapshot.thresholds_2026_0915.現金_twd.合計底線）；
    # 僅於 snapshot 門檻缺漏時由該函式回退 → 本檔不得再出現任何當期金額字面值
    # —— 2026-09-28 CIO 指出：此處寫死會讓「現況三條達標 → 🟢」在底線裁示變動後仍以舊值判定＝假 PASS
    # 現金底線一律走單一來源 sot_targets.cash_floor(snap)（2026-10-05 修正：
    # sabbatical_checklist_update._cash_floor 已於 4c5c68fe（10/04）移除，本檔漏改 → 直接 AttributeError、
    # 整支 FI 門檻回歸保護工具靜默失效（保護消失且無告警＝P0 假綠燈型缺陷）。
    # —— 2026-09-28 CIO 指出：此處寫死會讓「現況三條達標 → 🟢」在底線裁示變動後仍以舊值判定＝假 PASS
    sot = _load("sot", repo / "sot_targets.py")
    gate, floor = sab.RUNWAY_GATE_DAYS, sot.cash_floor(snap)
    # 2026-10-10：現金一律取「可動用」口徑（總現金 − 指定用途款，sot_targets.available_cash）。
    # 原寫 snap.cash_total → 質押指定款 900,000 被當可動用，現金門檻判定 fail-open（假 PASS），
    # 與 sabbatical/coast_fi 生產端口徑不一致。
    cash = sot.available_cash(snap)
    cov, strc = sc["con"]["coverage"], sc["stress"]["coverage"]
    rw = sc["extreme"]["runway_days"]
    _exp_light = ("🟢" if (cov >= 100 and strc >= 100 and (rw or 0) >= gate and cash >= floor)
                  else ("🟡" if cov >= 100 else "🔴"))
    ck("traffic_light ＝ 四條門檻現算（保守／壓力／跑道／可動用現金）",
       _exp_light in sab.traffic_light(cov, strc, rw, cash, floor),
       f"期望 {_exp_light}｜現算 {cov:.1f}/{strc:.1f}/{rw if rw is None else round(rw)}/{cash:,.0f} vs 底線 {floor:,.0f}")
    ck("變異：保守 <100% → 🔴", "🔴" in sab.traffic_light(99.0, strc, rw, cash, floor))
    ck("變異：壓力 <100% → 🟡", "🟡" in sab.traffic_light(cov, 90.0, rw, cash, floor))
    ck(f"變異：跑道 <{gate} 天 → 🟡", "🟡" in sab.traffic_light(cov, strc, gate - 10, cash, floor))
    ck("變異：可動用現金 <底線 → 🟡", "🟡" in sab.traffic_light(cov, strc, rw, floor - 1, floor))
    # 2026-10-02 使用者裁示：留停 Gate 由 A/B/C/A+ 級距改為「三條硬門檻 → 🟢 GO／🟡 WAIT」，
    # B 級／A+ 級／健康度分數敘事取消。本節已改驗 10/02 規格（原 A 級／A+ 級／B 級／C 級
    # 斷言自 10/02 起天天 FAIL，2026-10-10 起因 free_cash_min 改必填而整支 ValueError 中斷）。
    months = ["2026-01", "2026-02", "2026-03"]
    trend = {m: {"生活費覆蓋率": 110.0 + i} for i, m in enumerate(months)}
    # 門檻單一入口：自由現金門檻一律取自 sot_targets.gate_thresholds（禁寫死）
    fc_min = float(sot.gate_thresholds(snap)["自由現金_twd"])

    def _gate(*a, **k):
        return sab.acceptance_level(*a, free_cash_min=fc_min, **k)

    ck("Gate 三條全達標 → 🟢 GO",
       _gate(cov, strc, rw, fc_min, floor, months, trend).startswith("🟢"))
    ck("變異：自由現金 <門檻 → 🟡 WAIT",
       _gate(cov, strc, rw, fc_min - 1, floor, months, trend).startswith("🟡"))
    ck("變異：壓力 <100% → 🟡 WAIT",
       _gate(cov, 90.0, rw, fc_min, floor, months, trend).startswith("🟡"))
    ck(f"變異：跑道 <{gate} 天 → 🟡 WAIT",
       _gate(cov, strc, gate - 10, fc_min, floor, months, trend).startswith("🟡"))

    def _raises(fn):
        try:
            fn()
            return False
        except ValueError:
            return True

    ck("缺 free_cash_min → 明確失敗（不得回退寫死門檻）",
       _raises(lambda: sab.acceptance_level(cov, strc, rw, fc_min, floor, months, trend)))
    ck("已取消 A／A+／B／C 級敘事（不回傳舊級別字樣）",
       not any(x in _gate(cov, strc, rw, fc_min, floor, months, trend)
               for x in ("A級", "A+級", "B級", "C級")))

    print("== 5) 目標與缺口結構（動態派生） ==")
    tg = sab.targets(exp, floor)
    ck("被動現金流門檻 = 當期支出（覆蓋 100%，非 1.5 倍）", tg["被動現金流"]["val"] == round(exp))
    ck("加碼級門檻 = 150（理想值）", tg["加碼級覆蓋率"]["val"] == sab.ACCEL_GATE_PCT == 150)
    ck("跑道門檻 = RUNWAY_GATE_DAYS", tg["FI 跑道"]["val"] == gate)
    acc = (snap.get("sabbatical_checklist") or {}).get("驗收標準_2027_02") or {}
    ck("snapshot 已無舊 key 距A級缺口（防孤兒舊值）", "距A級缺口" not in acc, str(list(acc.keys())))
    ck("snapshot 有 距門檻缺口 ＋ 距加碼級缺口_150", "距門檻缺口" in acc and "距加碼級缺口_150" in acc)
    g = acc.get("距門檻缺口") or {}
    ck("距門檻缺口：保守/壓力皆 0（＝達標）",
       (g.get("生活費覆蓋率") or {}).get("月缺口") == 0 and (g.get("壓力情境覆蓋率") or {}).get("月缺口") == 0)
    ck("距門檻缺口：跑道缺口 = max(0, 門檻−現況)",
       (g.get("FI 跑道") or {}).get("缺口_天") == max(gate - (rw or 0), 0))
    ck("加碼級缺口 = 支出×150% − 保守被動（非門檻）",
       acc["距加碼級缺口_150"]["月缺口"] == round(exp * 1.5 - sc["con"]["income"]))
    b2 = ((snap.get("startup_plan_three_track_0901") or {}).get("final_v2_20260902") or {}).get(
        "2027_02財務驗收_A級B級C級") or {}
    ck("兩副本同步（門檻/缺口一致、皆無舊 key）",
       b2.get("距門檻缺口") == acc.get("距門檻缺口") and "距A級缺口" not in b2)

    print("== 6) coast_fi_engine：跑道分母＝極端情境、PCCR 實收同口徑 ==")
    ck("config 指定 runway_ref_scenario=extreme",
       ((snap.get("coast_fi_config") or {}).get("runway_ref_scenario")) == "extreme")
    cf = snap.get("coast_fi_engine") or {}
    cur = cf.get("current") or {}
    pccr, rwm = (cur.get("pccr") or {}), (cur.get("runway") or {})
    if pccr:
        exp_act = sc["div_act"] + sc["rent_act"]
        ck("PCCR 當月實收 = 配息實收＋房租實收（與儀表板同口徑）",
           abs(float(pccr.get("pccr_actual_pct") or 0) - exp_act / exp * 100) < 0.06,
           f"{pccr.get('pccr_actual_pct')} vs {exp_act / exp * 100:.1f}")
    if rwm:
        ck("跑道天數 = 現金 ÷ 極端缺口 × 30",
           (sc["extreme"]["gap"] <= 0 and rwm.get("runway_days") == 999)
           or abs(float(rwm.get("runway_days") or 0) - cash / sc["extreme"]["gap"] * 30) < 1.5,
           str(rwm.get("runway_days")))
        ck("跑道參考情境標記為 extreme", rwm.get("scenario") == "extreme")

    print("== 7) 逐日產物：新門檻在、舊門檻不在（相對式比對現算值） ==")
    rp = _latest(repo, "retirement_plan_*.html")
    if rp and rp.stat().st_mtime + 60 < (repo / "snapshot.json").stat().st_mtime:
        print("  ⚠️  新鮮度：snapshot.json 比最新退休規劃頁新 → 頁面可能尚未按當期真值重產（本節比對可能假紅）")
    if rp:
        t = rp.read_text(encoding="utf-8")
        ck(f"退休規劃頁存在且為最新（{rp.name}）", True)
        ck("壓力情境覆蓋率＝現算值", f"{strc:.1f}" in t, f"期望 {strc:.1f}")
        ck("極端情境覆蓋率＝現算值", f"{sc['extreme']['coverage']:.1f}" in t,
           f"期望 {sc['extreme']['coverage']:.1f}")
        ck("加碼級 A+ 標記存在", "A+級" in t)
        ck("距門檻缺口卡片存在", "距門檻缺口" in t)
        ck("無舊門檻字樣（正常 ≥150%／距 A 級缺口／244,172）",
           "正常 ≥150%" not in t and "距 A 級缺口" not in t and "244,172" not in t)
        ck("級距文字標明「經驗級距·非門檻」", "經驗級距" in t)
        import re
        _w = re.findall(r'<div class="bar"><div style="width:([\d.]+)%', t)
        # 期望值必須走與頁面同一條四捨五入鏈：頁面先用 round(cov,1) 再換算尺標
        # （2026-09-28 驗證器初版漏這步 → 未四捨五入的覆蓋率換算後與頁面差 0.1pp，假 FAIL）
        _exp_w = [f"{min(round(c, 1) / sab.ACCEL_GATE_PCT * 100, 100):.1f}"
                  for c in (cov, sc["act"]["coverage"])]
        ck("條圖尺標 0–150%：兩條寬度＝現算（且互不相同）",
           _w[:2] == _exp_w and _w[0] != _w[1], f"{_w[:2]} vs {_exp_w}")
        ck("條圖無 min(,100%) 截斷殘留", "width:min(" not in t)
        ck(f"100% 門檻線位置 = {100 / sab.ACCEL_GATE_PCT * 100:.1f}%",
           f'<i style="left:{100 / sab.ACCEL_GATE_PCT * 100:.1f}%">' in t)
    else:
        ck("找到 retirement_plan_*.html", False, "無逐日產物")
    for pat, needles in (("index.html", ["FI 跑道（極端情境口徑）"]),
                         ("daily_report_v2_*.html", ["FI 跑道（極端情境口徑）"]),
                         ("rebalance_dashboard_*.html", ["四情境", "極端情境（參考）"])):
        p = repo / pat if "*" not in pat else _latest(repo, pat)
        if not p:
            ck(f"{pat} 存在", False)
            continue
        t = p.read_text(encoding="utf-8")
        ck(f"{Path(pat).name}：{needles[0]}", all(n in t for n in needles))

    print(f"\n== 結果：{_ok} PASS / {_fail} FAIL ==")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
