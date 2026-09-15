#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_thresholds.py — 門檻單一真值（SoT）一致性檢查（2026-09-15 INC-187）

背景：門檻曾散落 7 處（各腳本硬編碼），其中 4 處是 7-8 月舊口徑，
      造成「同一件事兩套值」與「假警報／漏警報」（實踩：債券目標 15 vs 25、
      LTV 安全值 35% vs 現行 53%、美股減碼 33% vs 40%）。
規則：所有門檻一律讀 snapshot.thresholds_2026_0915；本檢查負責
      ① 確認 SoT 存在且欄位齊全
      ② 確認各消費端程式真的有引用 SoT（不是口頭說要讀）
      ③ 掃描全庫殘留的舊門檻字面（擋 patch over patch）
用法：python check_thresholds.py     # 有違規 exit 1
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOT_KEY = "thresholds_2026_0915"

REQUIRED_SECTIONS = ["桶目標_pct", "動作階梯_pp", "單桶硬上限_pct", "減碼可執行性",
                     "風險煞車", "ltv分級_pct", "美元曝險_pct", "現金_twd", "避險衛星_pct"]

# 消費端必須引用 SoT 的程式
CONSUMERS = ["allocation_alert.py", "debt_restructure_tracker.py", "institutional_flow.py",
             "build_rebalance_dashboard.py", "build_penetration_report.py"]

# 已退役的舊門檻字面（掃到即視為殘留）
LEGACY_PATTERNS = [
    (r'"債券"\s*:\s*15\b', "舊桶目標 債券15%（現行 25%）"),
    (r'"現金/安全網"\s*:\s*15\b', "舊桶目標 現金15%（現行 5% + 現金底線制）"),
    (r'"防守型配息"\s*:\s*20\b', "舊桶目標 防守20%（現行 30%）"),
    (r'安全值\s*≤\s*35%', "舊 LTV 安全值 35%（現行 綠≤45／黃≤53／追繳70）"),
    (r'完成後\s*20\.4%', "8 月預估 LTV 20.4%（已失效）"),
    (r'us_ratio\s*>\s*33\b', "舊美股門檻 33%（現行 單桶硬上限 40%）"),
    (r'DEVIATION_TOLERANCE_PP\s*=\s*10\b', "舊容忍帶 10pp（現行導流 6pp）"),
    (r'LTV[^\n]{0,20}≥\s*0\.3[58]\b', "舊 LTV 門檻 35%/38%（現行 45/53）"),
]
SKIP_DIRS = {".git", "data", "cache", "node_modules", "__pycache__"}
SKIP_NAME = re.compile(r"^(_|snapshot_|snapshot\.|.*_archive|.*\.bak|.*backup|.*stale)")


def main() -> int:
    errs: list[str] = []
    warns: list[str] = []

    # ① SoT 存在且欄位齊全
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ snapshot.json 無法解析：{e}")
        return 1
    sot = snap.get(SOT_KEY)
    if not isinstance(sot, dict):
        errs.append(f"snapshot 缺 {SOT_KEY}（門檻 SoT 未建立）")
        sot = {}
    for sec in REQUIRED_SECTIONS:
        if sec not in sot:
            errs.append(f"{SOT_KEY}.{sec} 缺漏")
    # 桶目標 = penetration.targets 需一致（同一件事不得兩套值）
    _bt = sot.get("桶目標_pct") or {}
    _tg = (snap.get("penetration") or {}).get("targets") or {}
    for _k, _pk in [("台股市值型", "台股市值型目標"), ("美股市值型", "美股市值型目標"),
                    ("防守型配息", "配息型目標"), ("債券", "債券型目標"), ("現金", "現金目標")]:
        if _k in _bt and _pk in _tg and float(_bt[_k]) != float(_tg[_pk]):
            errs.append(f"桶目標不一致：SoT {_k}={_bt[_k]} vs penetration.targets.{_pk}={_tg[_pk]}")

    # ② 消費端有引用 SoT
    for f in CONSUMERS:
        p = BASE / f
        if not p.exists():
            errs.append(f"消費端檔案不存在：{f}")
            continue
        if SOT_KEY not in p.read_text(encoding="utf-8", errors="replace"):
            errs.append(f"{f} 未引用 {SOT_KEY}（可能仍在用硬編碼門檻）")

    # ③ 五桶＋衛星 = 總資產（穿透完整性；衛星＝黃金/健康為獨立避險桶，
    #    不在 penetration.actual_twd 內 → 必須另外加回。2026-09-15 有審查方只看 actual_twd
    #    五桶就判「資產對不上」→ 此檢查把不變量固定下來，避免同類誤判重演。）
    try:
        _a = (snap.get("penetration") or {}).get("actual_twd") or {}
        _five = sum(float(v) for k, v in _a.items() if not k.startswith("美股市值型成長_"))
        _sat = 0.0
        import importlib.util as _ilu
        _spec = _ilu.spec_from_file_location("_ua_chk", BASE / "update_all.py")
        _mod = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        _pv = _mod.calc_penetration(snap.get("cash_total"), snap.get("insurance_current_value"),
                                    snap.get("securities_total_market_value"),
                                    snap.get("fund_market_value"), snap=snap)
        _sat = float(_pv.get("黃金", 0)) + float(_pv.get("健康", 0))
        _tot = float(snap.get("total_assets", 0))
        _diff = _five + _sat - _tot
        if abs(_diff) > 1:
            errs.append(f"穿透完整性失敗：五桶 {_five:,.0f} + 衛星 {_sat:,.0f} = {_five+_sat:,.0f} ≠ 總資產 {_tot:,.0f}（差 {_diff:,.0f}）")
        else:
            print(f"✅ 穿透完整性：五桶 {_five:,.0f} + 衛星 {_sat:,.0f} = 總資產 {_tot:,.0f}")
    except Exception as _e:
        errs.append(f"穿透完整性檢查執行失敗：{_e}")

    # ④ 舊門檻字面殘留掃描
    hits: list[str] = []
    for p in BASE.rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".json", ".sh"):
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if SKIP_NAME.match(p.name):
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for ln, line in enumerate(txt.splitlines(), 1):
            # 說明/檢討用的引述行不掃（標記慣例：行內含 sot-exempt）；
            # 全域字串比對若連「解釋舊值錯在哪」的行都擋，就會讓人不想寫檢討 → 綁形式不綁字面。
            if "sot-exempt" in line:
                continue
            for pat, desc in LEGACY_PATTERNS:
                if re.search(pat, line):
                    hits.append(f"  {p.relative_to(BASE)}:{ln} → {desc}")
    if hits:
        errs.append(f"殘留舊門檻 {len(hits)} 處：\n" + "\n".join(sorted(set(hits))[:15]))

    print("=" * 50)
    print("  門檻 SoT 一致性檢查（check_thresholds.py）")
    print("=" * 50)
    if errs:
        for e in errs:
            print(f"❌ {e}")
        print(f"\n❌ 檢查未通過（{len(errs)} 項）")
        return 1
    print(f"✅ SoT 完整（{len(REQUIRED_SECTIONS)} 區塊）")
    print(f"✅ 消費端 {len(CONSUMERS)} 支皆引用 {SOT_KEY}")
    print("✅ 無舊門檻字面殘留")
    return 0


if __name__ == "__main__":
    sys.exit(main())
