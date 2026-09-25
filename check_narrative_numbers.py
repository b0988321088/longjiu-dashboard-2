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
import sys
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
# 標籤字串互為子字串（科技 ⊂ 非科技）→ 前置字元守門，避免把「非科技 6,333,937」算成「科技」的違規
LABEL_GUARD = {"科技": "(?<!非)"}
# 同一標籤的「另一種真值口徑」也要放行（例：現金＝活存 real_liquid_assets vs 穿透桶 現金/安全網）
EXTRA_AMOUNTS = {"現金": ("real_liquid_assets", "cash_total", "bank_assets_moneybook")}
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
        for _x in EXTRA_AMOUNTS.get(label, ()):
            _v = (snap or {}).get(_x)
            if isinstance(_v, (int, float)):
                twds.add(float(_v))
        allowed[label] = {"pct": pcts, "twd": twds, "gap": gps, "off": set()}

    # ── 2026-09-23 補洞：現金派生口徑（乾粉／餘裕＝現金 − 底線）────────────────
    # 為什麼：內文常寫「乾粉＝現金 861,818 − 底線 700,000 = 161,818」，這個派生口徑是
    # 合法的（規則：讀取端一律現算，見 snapshot.乾粉執行_0926），但原本的合法值集合只收
    # 現金原值 → 正確的派生數字被誤判「對不上 snapshot」。以 snapshot 門檻現算補入，
    # 不放寬其他檢查（非法金額仍會被擋）。
    _thr = ((snap or {}).get("thresholds_2026_0915") or {}).get("現金_twd") or {}
    _cash = (snap or {}).get("cash_total")
    if isinstance(_cash, (int, float)) and "現金" in allowed:
        _extras: set[float] = set()
        for _k in ("生活底線", "追繳緩衝", "合計底線"):
            _f = _thr.get(_k)
            if isinstance(_f, (int, float)):
                _extras.add(float(_f))                  # 底線本身也會被內文引用
                if _cash - _f > 0:
                    _extras.add(float(_cash - _f))      # 乾粉／餘裕
        allowed["現金"]["twd"] |= _extras

    for label, gname in LABEL_GICS.items():
        row = gics.get(gname)
        if isinstance(row, dict) and isinstance(row.get("佔比"), (int, float)):
            allowed.setdefault(label, {"pct": set(), "twd": set(), "gap": set(), "off": set()})
            allowed[label]["pct"].add(float(row["佔比"]))
    _engine_calibers(allowed)
    return allowed


# 標籤 → DAA 引擎 targetAllocation.rows 的資產名（引擎口徑的來源列）
ENGINE_ROWS = {
    "台股市值型成長": ("台股", "台股市值型成長"),
    "美股市值型成長": ("美股", "美股市值型成長"),
    "防守型配息": ("防守型配息",),
    "債券": ("債券",),
    # 2026-09-25 B 批補覆蓋：避險衛星（8/22 裁示 ≤7%＝黃金≤5%+石油≤2%）。修前
    # allowed 根本沒有衛星標籤 → 內文引用衛星的值從來沒被掃過（覆蓋缺口，非假陽性）。
    # 刻意「不」註冊 黃金／石油 個別標籤：那兩字會與商品報價（黃金 2,400/oz 這種
    # 千分位數字）碰撞，掃了會生出假陽性；等內文真的出現「黃金 5%」再補。
    "避險衛星合計(黃金+石油)": ("避險衛星", "衛星"),
}


def _engine_calibers(allowed: dict, base: Path = BASE) -> None:
    """把 DAA 引擎（macro_regime_*.json）的三種口徑一次補進合法值集合。

    ── 2026-09-25 補洞（收工稽核第 13 類 ❌；同型已第四次）──────────────────
    內文（緊急應變報告、紅線期因應卡）會自然引用引擎的：
      ① 戰術偏移 ＝ 燈號偏移後 − 目標（例：債券的正偏移，寫成 +Npp）
      ② 偏移後目標值本身（例：該桶的偏移後權重 N%）
      ③ 建議金額 ±（例：美股的金額型建議）
    三者都是合法派生口徑，但合法值集合原本只有「現況缺口」與「穿透真值」
    → 正確的引擎數字被判「對不上 snapshot」。
    本函式一次補齊這些口徑（不再逐次補單一值），全部讀最新 macro_regime_*.json
    現算，不在本檔寫死任何數字。

    ── 2026-09-25 補洞 #2（A/B 批加固）────────────────────────────────────
      · 引擎偏移改存獨立的 off 集合（有號、不翻符號）：原本把 ±delta 都塞進 gap，
        「幅度對、方向反」的敘述會被放行（詳見 _pp_caliber 的說明）。
      · 選檔改為「只認 macro_regime_YYYY-MM-DD.json 並取最新日期」：原本用
        sorted(glob)[-1]（字典序），一旦出現 macro_regime_backup.json 之類的非日期檔
        就會被當成最新檔（'2' < 'b'）→ 拿錯口徑且無聲。
      · 缺檔／壞檔／rows 型別不符一律出聲到 stderr：原本 except 靜默 return，症狀會
        顯示成「內文數字對不上」（假陽性），無法區分是內文錯還是引擎檔壞。
      · 本函式新建的標籤若補完仍全空就移除並警示：空集合在 scan_text 內是「跳過比對」
        ＝靜默放行（假陰性），不可留在 allowed 裡。
    """
    try:
        _files: list[tuple[str, Path]] = []
        for _p in base.glob("macro_regime_*.json"):
            _m = re.fullmatch(r"macro_regime_(\d{4}-\d{2}-\d{2})\.json", _p.name)
            if _m:
                _files.append((_m.group(1), _p))
        if not _files:
            print(f"  ⚠️ _engine_calibers：{base} 找不到 macro_regime_YYYY-MM-DD.json"
                  f"（無檔或全為非日期命名）→ 引擎口徑未補入，內文引用引擎值時會誤報",
                  file=sys.stderr)
            return
        _files.sort()
        data = json.loads(_files[-1][1].read_text(encoding="utf-8"))
        _created: list[str] = []
        for row in ((data.get("targetAllocation") or {}).get("rows") or []):
            name = str(row.get("資產", "")).strip()
            if name not in ENGINE_ROWS:
                continue
            t, off, amt = row.get("target"), row.get("燈號偏移後"), row.get("建議金額(±)")
            _n_pairs = isinstance(t, (int, float)) and isinstance(off, (int, float))
            _n_t = isinstance(t, (int, float))
            _n_amt = isinstance(amt, (int, float))
            for lab in ENGINE_ROWS[name]:
                spec = allowed.get(lab)
                if spec is None:
                    spec = {"pct": set(), "twd": set(), "gap": set(), "off": set()}
                    allowed[lab] = spec
                    _created.append(lab)
                spec.setdefault("off", set())
                if _n_pairs:
                    spec["off"].add(round(float(off) - float(t), 1))  # ① 有號引擎戰術偏移
                    spec["pct"].add(round(float(off), 1))             # ② 偏移後目標值
                if _n_t:
                    spec["pct"].add(round(float(t), 1))               # ③ 目標值本身
                if _n_amt:
                    spec["twd"].add(float(amt))                       # ④ 建議金額
            if not (_n_pairs or _n_t or _n_amt):
                # 既有標籤不會走下面的「新建標籤移除」分支 → 這裡必須另外出聲，否則引擎欄位
                # 改名／型別變動時，症狀只會顯示成「內文數字對不上」（假陽性），查不到根因。
                print(f"  ⚠️ _engine_calibers：引擎列『{name}』的 target／燈號偏移後／"
                      f"建議金額(±) 全非數字 → 該列未補入任何口徑（欄位改名或型別變動？）",
                      file=sys.stderr)
        # 空集合在 scan_text 內＝跳過比對＝靜默放行（假陰性）→ 本函式新建卻補不到值的
        # 標籤一律移除並出聲（引擎欄位改名／型別變動時要看得到，不能默默變成不掃）。
        for lab in dict.fromkeys(_created):
            if not (allowed[lab]["pct"] or allowed[lab]["twd"]
                    or allowed[lab]["gap"] or allowed[lab]["off"]):
                del allowed[lab]
                print(f"  ⚠️ _engine_calibers：{lab} 未取得任何合法值（欄位型別不符？）"
                      f"→ 不納入掃描（否則空集合會靜默放行）", file=sys.stderr)
    except Exception as _e:
        print(f"  ⚠️ _engine_calibers 略過（{type(_e).__name__}: {_e}）→ 引擎口徑未補入，"
              f"內文引用引擎值時會誤報；請檢查 {base} 的 macro_regime_*.json",
              file=sys.stderr)
        return


def _pct_ok(vals: set, x: float) -> bool:
    return any(abs(x - v) <= TOL for v in vals)


def _amt_ok(vals: set, x: float) -> bool:
    return any(abs(x - v) < 1 for v in vals)


# ── 2026-09-25 B 批：pp 的語境詞 → 口徑 ──────────────────────────────────────
# 「引擎戰術偏移」(off) 與「現況缺口」(gap) 是兩個不同意義的有號量，同一標籤可能
# 符號相反（債券現況低於目標＝負缺口，但引擎要加碼＝正偏移）。修前把 ±delta 都塞進
# gap 同一個集合，代價是「幅度對、方向反」的敘述會被放行。
# 語境詞刻意只收「單義」者：
#   超標/超配/低配 ＝ 描述現況 vs 目標的偏離 → 只能用現況缺口集合
#   戰術偏移/偏移後 ＝ 描述引擎動作結果   → 只能用引擎偏移集合
# 缺口/不足/建議/加碼/減碼 一律不收：實測語料裡模型會拿它們講「建議幅度」而非現況
# 缺口（「缺口：台股 -2.2pp」是現況，「建議收回 9.5pp」是建議），硬套會製造假陽性。
_CALIBER_WORDS = {
    "gap": ("超標", "超配", "低配"),
    "off": ("戰術偏移", "偏移後"),
}


def _pp_caliber(text: str, m: re.Match, pad: int = 24) -> str | None:
    """從命中點往前找最近的子句，回傳 pp 該用哪個口徑（判不出＝None → 用聯集）。

    以標點切段是必要的：「美股超標 9.5pp、債券 +5pp」若共用視窗，債券的 +5pp 會被
    鄰句的「超標」污染成現況缺口口徑 → 假陽性。切段後 `債券 +5pp` 只看得到「債券」。
    """
    # 切段依據＝標點「或任何數字」。數字必須切，否則沒有標點的相鄰子句會互相污染：
    # 實測「美股超標 9pp 但債券 +5pp」會把債券的引擎偏移值判成現況缺口 → 新假陽性。
    # （小數點也在切段字元內，但真正的保險是 \d：整數 pp 沒有小數點可切。）
    seg = re.split(r"[，。；、,;.／/｜|\n（）()\[\]\d]",
                   text[max(0, m.start() - pad):m.start()])[-1]
    hit = {c for c, ws in _CALIBER_WORDS.items() if any(w in seg for w in ws)}
    return hit.pop() if len(hit) == 1 else None


def scan_text(text: str, allowed: dict, where: str) -> list[str]:
    out: list[str] = []
    # 標籤後只允許空白/冒號（複合詞如「高科技/半導體」自然被排除）
    for label, spec in allowed.items():
        _g = LABEL_GUARD.get(label, "")
        for m in re.finditer(rf"{_g}{re.escape(label)}\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%", text):
            val = float(m.group(1))
            if spec["pct"] and not _pct_ok(spec["pct"], val):
                out.append(f"{where}：{label} {val}% ∉ 合法值 {sorted(spec['pct'])}｜片段 …{_ctx(text, m)}…")
        for m in re.finditer(rf"{_g}{re.escape(label)}\s*[:：]?\s*([+-]?\d+(?:\.\d+)?)\s*pp", text):
            _raw = m.group(1)
            val = float(_raw)
            _cal = _pp_caliber(text, m)
            if _cal == "gap":
                _vals, _name = spec["gap"], "現況缺口"
            elif _cal == "off":
                _vals, _name = spec["off"], "引擎偏移"
            else:
                _vals, _name = (spec["gap"] | spec["off"]), "現況缺口∪引擎偏移"
            if not _vals:
                # 該口徑尚無值（例：科技沒有引擎列，off 為空）→ 退回聯集。
                # 修前是「直接比對 gap」，所以在這裡 continue 等於憑空開了一條假陰性通道。
                _vals, _name = (spec["gap"] | spec["off"]), "現況缺口∪引擎偏移"
            if not _vals:
                continue
            if not _raw.startswith(("+", "-")):
                _ok = _pct_ok({abs(_v) for _v in _vals}, abs(val))   # 沒寫號＝只比幅度
            else:
                _ok = _pct_ok(_vals, val)                            # 寫了號＝必須同號
            if not _ok:
                _oname = "現況缺口" if _name == "引擎偏移" else "引擎偏移"
                _other = sorted(spec["gap"] if _name == "引擎偏移" else spec["off"])
                out.append(f"{where}：{label} {val:+}pp ∉ 合法{_name}值 {sorted(_vals)}"
                           f"｜（{_oname}＝{_other}）｜片段 …{_ctx(text, m)}…")
        for m in re.finditer(rf"{_g}{re.escape(label)}\s*[:：]?\s*(\d{{1,3}}(?:,\d{{3}})+)", text):
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
    if h:
        # 修復指引（2026-09-25 加）：讓「合法派生口徑被誤判」變成機械動作，
        # 不再每次都要重新診斷（同型已第四次：科技分母→現金派生→引擎偏移）。
        print("  ℹ️ 修法：若該數字是合法派生口徑（非模型自行推算），到 build_allowed／"
              "ENGINE_ROWS＋_engine_calibers 補『來源』，並在 check_narrative_numbers_selftest.py "
              "加一組正／負向案例；一律修集合、不改內文、不放寬比對。")
        print("  ℹ️ 自測：python check_narrative_numbers_selftest.py（收工稽核第 13 類會先跑它）")
    print(f"內文數字守門（{t}）：{'✅ 全部可追溯' if not h else f'❌ {len(h)} 處對不上'}")
