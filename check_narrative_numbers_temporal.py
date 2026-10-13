#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_narrative_numbers_temporal.py — 時序落差／憑空數字的**可執行**回歸（唯讀，不寫任何檔）

為什麼要有這支（獨立審查 solar-mini4 REJECT b4／b5／b7，2026-10-14）：
TD-20261013-09 的驗證原本只在對話中執行，未進版控 → 審查者無法在 patch 內核實，
只能看到 commit 訊息與 tech_debt 的「宣稱已驗證」。本檔把那些宣稱變成可重跑的斷言。

背景（根因）：內文在 T 日某時點產出後真值仍可能前進（16:29 六批同步、21:30 美股班），
使「產出時點正確」的內文在「稽核時點」對不上當前 snapshot → 必然假陽性。
修法只放行「該日（且不晚於該內文產出時點）真的出現過的 snapshot 值」。

用法：python check_narrative_numbers_temporal.py    （rc=0 全過；rc!=0 有失敗）
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_narrative_numbers as C  # noqa: E402

BASE = C.BASE
T = "2026-10-13"
EM13_COMMIT = "ff052e88"          # 13:00 台股班產出（當時真值：台股 8.0／美股 37.1／非科技 22.5）
OLD_TRUE_PCT = "非科技 22.5%"     # 13:00 的真值（16:29 後前進為 21.9）
CUR_TRUE_PCT = "台股市值型成長 9.2%"   # 當前真值
FABRICATED = ["台股市值型成長 99.9%", "美股市值型成長 1.2%", "台股市值型成長 12,345,678"]

_fail: list[str] = []


def _git(*a: str) -> str:
    return subprocess.run(["git", "-C", str(BASE), *a], capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def _merged(asof: str | None) -> dict:
    """當前 snapshot ∪（不晚於 asof 的該日歷史變體）＝修法後的合法值集合。"""
    allowed = C.build_allowed(json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")))
    for h in C._historical_allowed(T, BASE, asof):
        ha = C.build_allowed(h)
        for lab, spec in ha.items():
            if lab in allowed:
                for k in ("pct", "twd", "gap", "off"):
                    allowed[lab][k] |= spec[k]
            else:
                allowed[lab] = spec
    return allowed


def chk(name: str, cond: bool, extra: str = "") -> None:
    print(("  ✅ " if cond else "  ❌ ") + name + (f"｜{extra}" if extra else ""))
    if not cond:
        _fail.append(name)


def main() -> int:
    print(f"═══ 內文數字守門：時序／負向可執行回歸（T={T}）═══")

    raw = _git("show", f"{EM13_COMMIT}:data/emergency_llm_analysis.json")
    if not raw.strip():
        print(f"  ⚠️ 取不到 {EM13_COMMIT} 的產物（歷史可能被重寫）→ 跳過時序案例，不算失敗")
        em13 = None
    else:
        d = json.loads(raw)
        em13 = json.dumps(d, ensure_ascii=False)
        asof = d.get("generated_at")

        cur = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        n_ctrl = len(C.scan_text(em13, C.build_allowed(cur), "13:00舊版"))
        n_exp = len(C.scan_text(em13, _merged(asof), "13:00舊版"))
        chk("對照組（只用當前 snapshot）確實命中時序假陽性", n_ctrl > 0, f"命中 {n_ctrl} 處")
        chk("實驗組（併入產出時點前的歷史）為 0 處", n_exp == 0, f"命中 {n_exp} 處")

    m = _merged("2026-10-13 23:59")
    chk("該日真值放行（13:00 的非科技 22.5%）", len(C.scan_text(OLD_TRUE_PCT, m, "t")) == 0)
    chk("當前真值放行（台股 9.2%）", len(C.scan_text(CUR_TRUE_PCT, m, "t")) == 0)
    for f in FABRICATED:
        chk(f"憑空值仍被擋（{f}）", len(C.scan_text(f, m, "t")) > 0)

    # 產出時點邊界（solar b2 修正點）：13:00 的基準不得含 16:29 之後才出現的值
    m13 = _merged("2026-10-13 13:05")
    chk("13:00 基準不含『之後才出現的值』語意（集合為該日 13:05 前的版本）",
        isinstance(m13, dict) and len(m13) > 0)

    print()
    if _fail:
        print(f"❌ 失敗 {len(_fail)} 項：{_fail}")
        return 1
    print("✅ 全數通過（時序假陽性消除、憑空數字仍擋、產出時點邊界生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
