#!/usr/bin/env python3
"""LLM 內文數字守門：內文提到的穿透數字必須對得上 snapshot 單一真值。

2026-09-23 INC-245 新增。背景：日報 CTO 內文寫「科技17.5%已破15%紅線」，而穿透表是 15.3%
—— 模型自己算/沿用舊值，沒有任何閘門擋；同一段還有「美股超配+10.9pp」（用了五桶合計當分母），
與穿透表的 +9.5pp 不一致（分母混用）。使用者正是被這兩個數字問「科技只有 15% 為什麼會超標」。

**檢查範圍（刻意收窄，零假陽性優先）**：只認「標籤＋純空白/冒號＋數字」這種直述句
（`科技 15.3%`、`科技：15.3%`、`科技15.3%`），因為那是模型最容易寫錯、也最像事實陳述的型態。
複合詞（`高科技/半導體`、`科技股`）與有中介詞的句子（`防守合併 68.5%`、`科技目標 ≤20%`）
不在此閘門 —— 它們多為模板渲染或另一種口徑，硬比會產生假陽性。

每個標籤的合法值集合（任一命中即放行）：
  · 佔總資產口徑：snapshot.penetration.actual_pct[key]
  · 佔投資部位口徑：actual_twd[key] / Σ五桶 × 100（內文有時用這個分母）
  · GICS 產業口徑：snapshot.industry_penetration.產業[...].佔比（僅 科技/資訊科技、金融 等有對應者）
  金額：actual_twd[key]（逗號格式）
  pp：gap ∈ {snapshot.gaps[key], 各口徑 pct − 目標}
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path.home() / "Desktop" / "longjiu_system"

# 標籤 → snapshot.penetration 鍵
LABEL_KEYS = {
    "科技": "美股市值型成長_科技",
    "非科技": "美股市值型成長_非科技",
    "美股市值型成長": "美股市值型成長",
    "美股": "美股市值型成長",
    "台股市值型成長": "台股市值型成長",
    "台股": "台股市值型成長",
    "防守型配息": "防守型配息",
    "債券": "債券",
    "現金": "現金/安全網",
}
# 標籤 → GICS 產業名（industry_penetration.產業）
LABEL_GICS = {"科技": "資訊科技", "資訊科技": "資訊科技", "金融": "金融"}

TOL = 0.25  # 百分比容差（顯示四捨五入 + 兩口徑並存）


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_allowed(snap: dict) -> dict:
    """回傳 {label: {"pct": {...}, "twd": {...}, "gap": {...}}}（label 含 GICS 別名）。"""
    pen = (snap or {}).get("penetration", {}) or {}
    atwd = pen.get("actual_twd", {}) or {}
    apct = pen.get("actual_pct", {}) or {}
    gaps = pen.get("gaps", {}) or {}
    tgt = pen.get("targets", {}) or {}
    gics = ((snap or {}).get("industry_penetration", {}) or {}).get("產業", {}) or {}
    total_inv = sum(float(v) for k, v in atwd.items()
                    if isinstance(v, (int, float)) and not k.endswith(("_科技", "_非科技"))) or 1

    allowed: dict[str, dict] = {}
    for label, key in LABEL_KEYS.items():
        pcts, twds, gps = set(), set(), set()
        if key in atwd:
            twds.add(float(atwd[key]))
            pcts.add(round(float(atwd[key]) / total_inv * 100, 1))  # 佔投資部位
        if key in apct:
            pcts.add(float(apct[key]))  # 佔總資產
        if key in gaps:
            gps.add(float(gaps[key]))
        # targets 鍵名：科技→科技曝險目標；其餘「<桶>目標」
        tkey = "科技曝險目標" if key.endswith("_科技") else f"{key.split('_')[0]}目標"
        if key in tgt:
            tkey = key
        if tkey in tgt:
            for p in list(pcts):
                gps.add(round(p - float(tgt[tkey]), 1))
        gk = "科技曝險" if key.endswith("_科技") else ("債券及安全現金" if key == "債券" else key)
        if gk in gaps:
            gps.add(float(gaps[gk]))
        allowed[label] = {"pct": pcts, "twd": twds, "gap": gps}
    for label, gname in LABEL_GICS.items():
        row = gics.get(gname)
        if isinstance(row, dict) and isinstance(row.get("佔比"), (int, float)):
            allowed.setdefault(label, {"pct": set(), "twd": set(), "gap": set()})
            allowed[label]["pct"].add(float(row["佔比"]))
    return allowed


def _pct_ok(vals: set, x: float) -> bool:
    return any(abs(x - v) <= TOL for v in vals)


def _amt_ok(vals: set, x: float) -> bool:
    return any(abs(x - v) < 1 for v in vals)


def scan_text(text: str, allowed: dict, where: str) -> list[str]:
    out: list[str] = []
    # 標籤後只允許空白/冒號（複合詞如「高科技/半導體」自然被排除）
    for label, spec in allowed.items():
        for m in re.finditer(rf"{re.escape(label)}\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%", text):
            val = float(m.group(1))
            if spec["pct"] and not _pct_ok(spec["pct"], val):
                out.append(f"{where}：{label} {val}% ∉ 合法值 {sorted(spec['pct'])}｜片段 …{_ctx(text, m)}…")
        for m in re.finditer(rf"{re.escape(label)}\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*pp", text):
            val = float(m.group(1))
            if spec["gap"] and not _pct_ok(spec["gap"], val):
                out.append(f"{where}：{label} {val:+}pp ∉ 合法值 {sorted(spec['gap'])}｜片段 …{_ctx(text, m)}…")
        for m in re.finditer(rf"{re.escape(label)}\s*[:：]?\s*(\d{{1,3}}(?:,\d{{3}})+)", text):
            _after = text[m.end():m.end() + 4]
            if re.match(r"\s*(?:\.\d|點)", _after):
                continue  # 指數點數（台股 47,800.17（+81 點））不是部位金額
            val = float(m.group(1).replace(",", ""))
            if spec["twd"] and not _amt_ok(spec["twd"], val):
                out.append(f"{where}：{label} 金額 {m.group(1)} ∉ 合法值 "
                           f"{[f'{v:,.0f}' for v in sorted(spec['twd'])]}｜片段 …{_ctx(text, m)}…")
    return out


def _ctx(text: str, m: re.Match, pad: int = 14) -> str:
    return re.sub(r"\s+", " ", text[max(0, m.start() - pad):m.end() + pad])


def _doc_date(p: Path) -> str | None:
    """內文自帶的日期（有就用來判歷史；沒有回 None＝當現行處理）。"""
    d = _load(p)
    if isinstance(d, dict):
        for k in ("date", "日期", "generated_at", "updated_at", "時間"):
            v = d.get(k)
            if isinstance(v, str) and len(v) >= 10:
                return v[:10]
    return None


def narrative_sources(T: str, base: Path = BASE) -> list[Path]:
    """當日「現行」LLM 內文來源。

    刻意只取有效內文（避免常駐假警報）：
      · CTO 快取：只取當日**最新**一份（同一天每個時點各有一份快取，舊的是當時的答案，
        拿全部來比會永遠亮紅燈，卻與現在讀者看到的不一致）
      · buffett_cto_report_{T}.md：當日實際產出（＝渲染來源）
      · emergency_llm_analysis.json：僅當其自帶日期 == T（否則屬歷史內文，跳過）
    """
    out: list[Path] = []
    cts = sorted((base / "data").glob(f"cto_{T}_*.json"), key=lambda p: p.stat().st_mtime)
    if cts:
        out.append(cts[-1])
    md = base / f"buffett_cto_report_{T}.md"
    if md.exists():
        out.append(md)
    em = base / "data" / "emergency_llm_analysis.json"
    if em.exists() and _doc_date(em) in (None, T):
        out.append(em)
    return out


def _text_of(p: Path) -> str:
    if p.suffix == ".md":
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    d = _load(p)
    if isinstance(d, str):
        return d
    if isinstance(d, dict):
        return json.dumps(d, ensure_ascii=False)
    if isinstance(d, list):
        return json.dumps(d, ensure_ascii=False)
    return ""


def scan(T: str, base: Path = BASE) -> list[str]:
    snap = _load(base / "snapshot.json") or {}
    allowed = build_allowed(snap)
    hits: list[str] = []
    for p in narrative_sources(T, base):
        txt = _text_of(p)
        if txt:
            hits += scan_text(txt, allowed, p.name)
    return hits


if __name__ == "__main__":
    import datetime as _dt
    import sys

    t = sys.argv[1] if len(sys.argv) > 1 else _dt.date.today().isoformat()
    h = scan(t)
    for line in h:
        print("  ❌", line)
    print(f"內文數字守門（{t}）：{'✅ 全部可追溯' if not h else f'❌ {len(h)} 處對不上'}")
