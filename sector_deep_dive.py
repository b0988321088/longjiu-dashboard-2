# -*- coding: utf-8 -*-
"""sector_deep_dive.py — 產業輪動深度討論（2026-08-23 折衷版：只對有動作的產業 ✅/⏸/🔴）

輸入：snapshot.rotation_recommendation（全產業規則建議）+ industry_penetration + 機構流向 + 總體情境
輸出：snapshot.sector_deep_dive = {產業: 質化討論文字}（僅含動作非「維持現況」的產業）
LLM 失敗 → 寫空 dict，呼叫端面板顯示「無深度討論」graceful degradation。
掛載：build_rebalance_dashboard.py（rotation_engine 之後呼叫本模組）。
"""
from __future__ import annotations
import json
from pathlib import Path
from llm_analysis import ask_llm

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"


def _load() -> dict:
    return json.loads(SNAP.read_text(encoding="utf-8"))


def build_discussion(rows: list, pen: dict, sector_flow: dict, macro: dict) -> dict:
    """只對動作非「維持現況」的產業，產出質化討論。"""
    targets = [r for r in rows if r.get("動作") and "維持現況" not in r.get("動作", "")]
    if not targets:
        return {}

    # 組 prompt：每產業一行現況 + 要求 2-3 句質化討論
    lines = []
    for r in targets:
        lines.append(
            f"- {r['產業']}：現況 {r['現況']}%（目標 {r['目標']}%，資金分數 {r['資金分數']:+d}），"
            f"動作「{r['動作']}」，規則理由：{r['理由']}"
        )
    ind_summary = "、".join(
        f"{k} {v.get('佔比', 0):.1f}%" for k, v in (pen.get("產業") or {}).items()
        if v.get("佔比", 0) >= 1.0
    )[:500]
    macro_txt = "；".join(f"{k}: {v}" for k, v in macro.items())[:300]

    prompt = (
        "以下是龍九控股再平衡引擎對各產業的規則建議（只列有動作的產業）。\n"
        f"GICS 產業穿透現況：{ind_summary}\n"
        f"總體情境：{macro_txt}\n"
        "請對「每個」列出的產業寫 2-3 句深度質化討論（繁體中文、有具體觀點），包含：\n"
        "① 資金流向解讀（為什麼流入/流出，機構行為背後含義）\n"
        "② 輪動位置（相對強弱、是否已擁擠/超跌）\n"
        "③ 對應動作的執行細節與風險（如分批節奏、進場條件、停損線）\n"
        "④ 與總體情境（殖利率/美元信用/地緣）的關聯\n"
        "格式：每個產業一個段落，開頭「【產業名】」，內容精簡不重複規則表的數字。\n\n"
        + "\n".join(lines)
    )
    system = (
        "你是龍九控股的產業輪動分析師。輸出繁體中文、精簡專業、有具體觀點。"
        "只討論列出的產業，不要新增其他產業。不要輸出 Markdown 表格。"
    )
    out = ask_llm(prompt, system=system, max_tokens=1200, temperature=0.4)
    if not out:
        return {}

    # 解析「【產業名】…」區塊 → dict
    import re
    result = {}
    cur = None
    for line in out.splitlines():
        m = re.match(r"【(.+?)】", line.strip())
        if m:
            cur = m.group(1)
            result[cur] = line.strip()
        elif cur and line.strip():
            result[cur] += "\n" + line.strip()
    # 只保留目標產業的 key（LLM 可能改名/多寫）
    valid = {r["產業"] for r in targets}
    return {k: v for k, v in result.items() if any(vk in k for vk in valid) or k in valid}


def main() -> dict:
    snap = _load()
    rec = snap.get("rotation_recommendation", {})
    rows = rec.get("全產業", [])
    pen = snap.get("industry_penetration", {})
    radar = {}
    try:
        radar = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    sector_flow = radar.get("sector_flow", {})
    # 總體情境（macro_regime 或 us30y_state）
    macro = {}
    try:
        mm = json.loads((BASE / "macro_regime_2026-08-23.json").read_text(encoding="utf-8"))
        macro["US30Y/情境"] = str(mm.get("scenario", mm.get("label", "")))[:80]
    except Exception:
        pass
    try:
        us = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        macro["US30Y"] = us.get("us30y", us.get("value", ""))
    except Exception:
        pass
    if not macro:
        macro = {"情境": "未讀取"}

    d = build_discussion(rows, pen, sector_flow, macro)
    snap["sector_deep_dive"] = d
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ sector_deep_dive 已寫入 snapshot（{len(d)} 個產業有深度討論）")
    for k, v in d.items():
        print(f"  【{k}】{v[:60]}…")
    return d


if __name__ == "__main__":
    main()
