# -*- coding: utf-8 -*-
"""verify_cbe_20261011.py — 工單 C／B／E 回歸測試（唯讀；工單A/D 另見 verify_dry_powder／verify_band_conflict）

C｜防守口徑揭露：配息資產合計 ÷ 總資產，≠防守桶＋債券；鉅亨月配列分類待確認＋揭露排除後試算。
B｜資產分解不變量：五桶＋衛星＋在途＋指定用途款＝總資產；不閉合 → 阻擋精確調度建議。
E｜調度欄位結構化：戰略偏差／戰術偏差／理論調整金額／風控後可執行金額／阻擋規則（＋分母、
   公式、政策來源）；煞車或欠資料 → 如實阻擋，理論不得充當可執行。

使用者裁決：不得自行改值（25%／27–33%／66.6%／17,820,490）、不得補平或正規化、不得放寬風控。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sot_targets as st            # noqa: E402
import tactical_table as tt         # noqa: E402

SNAP = json.loads((ROOT / "snapshot.json").read_text(encoding="utf-8"))
P, F = [], []


def rec(tag: str, desc: str, ok: bool, extra: str = "") -> None:
    (P if ok else F).append(tag)
    print(f"  {'✅' if ok else '❌'} {tag} {desc}" + (f" — {extra}" if extra else ""))


def _src(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


print("== 1. C｜防守口徑揭露（值不動、定義＋分母＋待確認試算）==")
_dc = st.defensive_caliber(SNAP)
_thr_freeze = ((SNAP.get("thresholds_2026_0915") or {}).get("防守合併口徑_pct") or {}).get("凍結承接")
rec("C-1", "防守合併金額／佔比未動（17,820,490／66.6）",
    _dc["金額"] == 17820490 and str(_dc["佔比"]) == "66.6", f"{_dc['金額']:,}／{_dc['佔比']}%")
rec("C-2", "凍結承接門檻未動（60%）", _thr_freeze == 60, str(_thr_freeze))
_pen = float(_dc["組成"].get("鉅亨月配") or 0)
_excl = _dc["金額"] - _pen
_tot = float(SNAP.get("total_assets") or 0)
rec("C-3", "待確認項＝鉅亨月配 358,196（不刪除、不歸類）", _pen == 358196, f"{_pen:,.0f}")
rec("C-4", f"排除待確認項目試算＝{_excl:,.0f}（≈{_excl / _tot * 100:.2f}%）",
    _excl == 17462294 and abs(_excl / _tot * 100 - 65.28) < 0.01)
_rs = json.loads((ROOT / "radar_state.json").read_text(encoding="utf-8"))
_rows = ((_rs.get("weekly_plan") or {}).get("rows") or [])
_def_row = " ".join(str(r.get("內容", "")) for r in _rows if "防守" in str(r.get("類別", "")) + str(r.get("內容", "")))
rec("C-5", "週計畫 防守 行揭露『金額 ÷ 總資產 = %}』", bool(re.search(r"配息資產合計 [\d,]+ ÷ 總資產 [\d,]+ = [\d.]+%", _def_row)),
    _def_row[:70])
rec("C-6", "週計畫 防守 行明確寫『≠防守桶＋債券』", "≠防守桶＋債券" in _def_row)
rec("C-7", "週計畫 防守 行揭露待確認項＋排除後試算（僅試算）",
    "358,196" in _def_row and "17,462,294" in _def_row and "65.28%" in _def_row)
rec("C-8", "舊樣式（無定義的『合併口徑 X% 已足』）已不存在",
    not re.search(r"合併口徑 [\d.]+% 已足", _def_row), _def_row[:60])
rec("C-9", "靜態：寫死 fallback（get(\"佔比\", 69.2) 樣式）已移除（institutional_flow）",
    "69.2)" not in _src("institutional_flow.py"))

print("\n== 2. B｜資產分解不變量 ==")
_d = st.asset_decomposition(SNAP)
rec("B-1", "五桶合計＝24,996,566（93.44%）", _d["五桶合計"] == 24996566, f"{_d['五桶合計']:,.0f}")
rec("B-2", "衛星＝853,894（黃金 328,153＋健康 525,741）",
    _d["衛星合計"] == 853894 and _d["衛星"].get("黃金") == 328153 and _d["衛星"].get("健康") == 525741,
    str(_d["衛星"]))
rec("B-3", "在途 591／指定款 900,000 各自列示", _d["在途"] == 591 and _d["指定款"] == 900000)
rec("B-4", "不變量閉合：五桶＋衛星＋在途＋指定款＝總資產 26,751,051、未歸類 0",
    _d["closed"] is True and _d["未歸類"] == 0 and _d["已歸類合計"] == _tot,
    f"已歸類 {_d['已歸類合計']:,.0f}")
rec("B-5", "衛星不與 actual_twd 名稱掃描重複計算", _d["未歸類明細"] == {} and not _d["未歸類"])
_line = st.asset_decomposition_line(SNAP)
rec("B-6", "單行揭露含分母來源與『不變量閉合』", "snapshot.total_assets" in _line and "不變量閉合" in _line, _line[:60])
for _tag, _bad, _why in (("B-7", {k: v for k, v in SNAP.items() if k != "total_assets"}, "缺 total_assets"),
                         ("B-8", {k: v for k, v in SNAP.items() if k != "penetration"}, "缺 penetration")):
    try:
        st.asset_decomposition(_bad)
        rec(_tag, f"{_why} → raise（不以 0 冒充）", False, "未 raise")
    except Exception as _e:
        rec(_tag, f"{_why} → raise（不以 0 冒充）", True, type(_e).__name__)
_dup = json.loads(json.dumps(SNAP))
_dup["penetration"]["actual_twd"]["指定用途款"] = 900000     # 注入：指定款誤入 actual_twd
_d2 = st.asset_decomposition(_dup)
rec("B-9", "注入 actual_twd.指定用途款 → 不重複計算（未歸類仍 0、closed 仍 True）",
    _d2["closed"] is True and _d2["未歸類"] == 0, f"未歸類 {_d2['未歸類']:,.0f}")
_miss = json.loads(json.dumps(SNAP))
_miss["penetration"].pop("satellite_twd", None)
_d3 = st.asset_decomposition(_miss)
rec("B-10", "缺 satellite_twd → 未歸類 853,894 且 closed=False（不補平、不正規化）",
    _d3["closed"] is False and abs(_d3["未歸類"] - 853894) < 1, f"未歸類 {_d3['未歸類']:,.0f}")
rec("B-11", "靜態：穿透產出器已 persist satellite_twd", "satellite_twd" in _src("build_penetration_report.py"))
rec("B-12", "靜態：eval 產生器已引用 asset_decomposition（不閉合→阻擋）",
    "asset_decomposition" in _src("build_rebalance_dashboard.py") and "不變量未閉合" in _src("build_rebalance_dashboard.py"))

print("\n== 3. E｜調度欄位結構化 ==")
_sf = st.scheduling_fields(SNAP, us30y=None, sellable_twd={"美股市值型成長": 200000})
_us = _sf["美股市值型成長"]
_need = ("戰略偏差_pp", "戰術偏差_pp", "理論調整金額_twd", "風控後可執行金額_twd", "阻擋規則名稱")
rec("E-1", "五個結構化欄位齊備", all(k in _us for k in _need), str([k for k in _need if k not in _us]))
rec("E-2", "美股：戰略偏差 +8.1pp、理論調整 2,166,835（含公式與分母）",
    (_us["戰略偏差_pp"] == 8.1 and abs(_us["理論調整金額_twd"] - 2166835) <= 2
     and "分母" in _us["公式"]),
    f"{_us['戰略偏差_pp']:+.1f}pp／{_us['理論調整金額_twd']:,}")
rec("E-3", "理論金額＝|偏差pp|÷100×分母（獨立複算）",
    abs(_us["理論調整金額_twd"] - round(abs(_us["戰略偏差_pp"]) / 100 * _tot)) <= 1)
rec("E-4", "風控後可執行 ≤ 單筆上限 200,000（不得以理論充當可執行）",
    _us["風控後可執行金額_twd"] <= 200000 < _us["理論調整金額_twd"], f"{_us['風控後可執行金額_twd']:,}")
rec("E-5", "單筆上限保留政策來源（2026-08-22 裁示）且標出與 500,000 的衝突",
    "2026-08-22" in _us["單筆上限來源"]["來源"] and "500000" in str(_us["單筆上限來源"]["衝突"]),
    str(_us["單筆上限來源"]["衝突"]))
rec("E-6", "戰術目標無 SoT → 明確標示『不計算』（不得自填 27%）",
    _us["戰術偏差_pp"] is None and "不計算" in _us["戰術來源"])
_sfb = st.scheduling_fields(SNAP, us30y=5.60, sellable_twd={"美股市值型成長": 200000})["美股市值型成長"]
rec("E-7", "US30Y 5.60（煞車生效）→ 可執行 0、可執行 False、阻擋含『US30Y 煞車』",
    _sfb["風控後可執行金額_twd"] == 0 and _sfb["可執行"] is False
    and any("US30Y 煞車" in b for b in _sfb["阻擋規則名稱"]), str(_sfb["阻擋規則名稱"])[:70])
_sfn = st.scheduling_fields(SNAP, us30y=None)["美股市值型成長"]
rec("E-8", "未提供可減部位 → 可執行 0 且阻擋寫明 fail-closed（不得猜）",
    _sfn["風控後可執行金額_twd"] == 0 and any("未提供" in b for b in _sfn["阻擋規則名稱"]))
try:
    st.scheduling_fields({k: v for k, v in SNAP.items() if k != "total_assets"})
    rec("E-9", "缺 total_assets → raise", False, "未 raise")
except Exception as _e:
    rec("E-9", "缺 total_assets → raise", True, type(_e).__name__)
rec("E-10", "靜態：週計畫與 eval 皆引用 scheduling_fields",
    "scheduling_fields" in _src("institutional_flow.py") and "scheduling_fields" in _src("build_rebalance_dashboard.py"))

print(f"\n=== 結果：{'PASS' if not F else 'FAIL'}（PASS {len(P)}／FAIL {len(F)}） ===")
if F:
    print("FAIL:", ", ".join(F))
sys.exit(0 if not F else 1)
