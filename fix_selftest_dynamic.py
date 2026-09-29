#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIO 必修：守門自測的穿透/缺口案例改為動態讀 snapshot（同 _cash_cases 模式）。"""
from pathlib import Path

P = Path(r"C:/Users/bot/Desktop/longjiu_system/check_narrative_numbers_selftest.py")
t = P.read_text(encoding="utf-8")

old_cases = '''    ("超標：美股 +2.2pp", True, "現況缺口口徑（動態，見 _pen_cases）"),
    ("超標：美股 -2.2pp", False, "負向：超標必為正缺口，寫成負 → 擋"),
    ("美股超標 2.2pp、債券 +5pp", True, "切段：鄰句『超標』不得污染債券的引擎值"),
'''
new_cases = '''    # 2026-09-29：原寫死 9.5pp（9 月舊缺口）→ 改由 _pen_cases() 動態生成，避免真值日案例落後。
'''
assert old_cases in t
t = t.replace(old_cases, new_cases)

gen = '''

def _pen_cases() -> list[tuple[str, bool, str]]:
    """2026-09-29：動態生成「穿透真值／現況缺口」案例（讀 snapshot.penetration）。

    原本寫死 9 月值（美股 +9.5pp、債券 +3.7/+4.7pp、科技 15.3%、防守 17.3%）
    → 真值日更新穿透後，案例落後使自測假失敗（看起來像守門壞掉）。
    動態生成維持同樣守門強度：值仍須落在守門算出的合法集合內才算放行。
    """
    import json
    try:
        _s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    _pct = ((_s.get("penetration") or {}).get("actual_pct") or {})
    _out: list[tuple[str, bool, str]] = []
    _us = _pct.get("美股市值型成長")
    if isinstance(_us, (int, float)) and _us > 30:
        _gap = round(_us - 30, 1)
        _out.append((f"超標：美股 +{_gap}pp", True, "現況缺口口徑（動態）"))
        _out.append((f"超標：美股 -{_gap}pp", False, "負向：超標必為正缺口，寫成負 → 擋"))
        _out.append((f"美股超標 {_gap}pp、債券 +5pp", True, "切段：鄰句『超標』不得污染債券的引擎值"))
    _bd = _pct.get("債券")
    if isinstance(_bd, (int, float)):
        _out.append((f"債券 {_bd - 25:+.1f}pp", True, "現況缺口（佔總資產分母，動態）"))
    _tech = _pct.get("美股市值型成長_科技")
    if isinstance(_tech, (int, float)):
        _out.append((f"科技 {_tech}%", True, "穿透真值（動態）"))
    _defe = _pct.get("防守型配息")
    if isinstance(_defe, (int, float)):
        _out.append((f"防守型配息 {_defe}%", True, "穿透真值（動態）"))
    return _out


CASES += _pen_cases()
'''
old_call = "\nCASES += _cash_cases()\n"
assert old_call in t
t = t.replace(old_call, "\nCASES += _cash_cases()\n" + gen)
P.write_text(t, encoding="utf-8")
print("✅ check_narrative_numbers_selftest.py：穿透/缺口案例已改動態生成")
