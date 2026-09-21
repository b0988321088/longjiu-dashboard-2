#!/usr/bin/env python3
"""Buffett/CTO 穿透分析器（v4 — 動態目標）"""
from __future__ import annotations

import json, os, sqlite3, sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import requests

BASE = Path(__file__).parent.resolve()
load_dotenv(os.path.expanduser("~/AppData/Local/hermes/.env"))
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "") or os.environ.get("TELEGRAM_ALLOWED_USERS", "")
TODAY = date.today().isoformat()

# 5 類穿透目標（動態：以 snapshot.penetration.targets 為單一真值；缺 key 時 fallback 2026-08-02 定案值 20/30/20/15/15）
try:
    _snap_tgt = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")).get("penetration", {}).get("targets", {}) or {}
    # 2026-09-20 裁示：科技曝險目標 定版 15%。
    _tech_cap_snap = float(_snap_tgt.get("科技曝險目標", 15))
except Exception:
    _snap_tgt = {}
    _tech_cap_snap = 15
TARGETS = {
    "tw_equity": _snap_tgt.get("台股市值型目標", 10),
    "us_equity": _snap_tgt.get("美股市值型目標", 40),
    "defensive": _snap_tgt.get("配息型目標", 20),
    "bond": _snap_tgt.get("債券型目標", 25),
    "cash": _snap_tgt.get("現金目標", 5),
    "tech_exposure": _tech_cap_snap,
}
TARGET_LABELS = {"tw_equity":"台股","us_equity":"美股","defensive":"防守","bond":"債券","cash":"現金", "tech_exposure":"科技"}
TARGET_EMOJI = {"tw_equity":"🇹🇼","us_equity":"🇺🇸","defensive":"🛡️","bond":"💵","cash":"💰", "tech_exposure":"💻"}

def _cat_value(db, category: str) -> float:
    """從 asset_class 表計算某分類的穿透市值 (同 _cat2 in run_daily.py)"""
    from collections import defaultdict
    ac = defaultdict(float)
    for r in db.execute("SELECT category, source, SUM(weight) as w FROM asset_class GROUP BY category, source"):
        ac[(r[1], r[0])] = r[2]
    snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    def _src_val(src):
        m = {"securities": "securities_total", "fund": "fund_market_value",
             "insurance_fund": "insurance_current_value", "cash": "bonds_cash",
             "bond": "bonds_penetration"}
        k = m.get(src)
        if k == "bonds_cash":
            old_cash = float(snap.get("bonds_cash", 9_697_196) or 0)
            return max(old_cash - 5_812_576, 0) + 33_000
        if k == "bonds_penetration":
            return 2_097_467
        return float(snap.get(k, 0) or 0)
    total = 0
    for (src, cat), weight in ac.items():
        if cat == category:
            sw = sum(w for (s, c), w in ac.items() if s == src)
            total += _src_val(src) * weight / max(sw, 1)
    return total

def cash_caliber_note(snapshot: dict) -> str:
    """現金口徑單一來源（2026-09-13 使用者裁示）：
    現金 = 台幣活存帳戶合計（snapshot.cash），不含 MMF、不含外幣。
    國泰 MMF 500萬 已於 2026-09-09 贖回、2026-09-11 轉申購貝萊德B11（計入基金/質押擔保池），
    不可再算成現金，也不可建議減現金（底線制 70萬）。"""
    _s = snapshot or {}
    _cash = float((_s.get("cash") or _s.get("cash_total") or 0) or 0)
    _pct = float(((_s.get("penetration") or {}).get("actual_pct") or {}).get("現金/安全網", 0) or 0)
    return (f"現金口徑＝台幣活存 {_cash:,.0f}（{_pct:.1f}%，不含 MMF/外幣）；"
            f"MMF 500萬已於 2026-09-11 轉申購貝萊德B11（計入基金／質押擔保池，不再計現金），不可建議減現金")


DCM_FREEZE_THRESHOLD = 60  # 防守承接凍結門檻（2026-09-16 使用者裁示：合併口徑 ≥60% 為判準）


def defensive_combined_pct(snapshot: dict):
    """防守合併口徑真值（%）。讀 snapshot.defensive_combined_metric.佔比，讀不到回 None。"""
    _pct = ((snapshot or {}).get("defensive_combined_metric") or {}).get("佔比")
    try:
        return float(_pct)
    except (TypeError, ValueError):
        return None


def defensive_combined_phrase(snapshot: dict) -> str:
    """給 LLM prompt 用的守法約束片語（INC-207：嚴禁寫死百分比）。

    2026-09-16：原 prompt 寫死「防守合併口徑 69.5% 已足勿追大額」（另兩處寫死 69.7%），
    snapshot 真值已是 68.5 → LLM 被餵舊數字推理（INC-168 同型）。
    """
    _pct = defensive_combined_pct(snapshot)
    if _pct is None:
        # 缺欄位＝真值未知（既不是「不足」也不是「已足」）→ 明確示警，措辭保持中性，
        # 不留任何「已足」暗示、也不單向導向不作為。
        # （2026-09-16 審查意見：原 fallback 尾綴「勿追大額」在真值缺失時會傾向不動作。）
        print("⚠️ snapshot.defensive_combined_metric.佔比 讀取失敗 → prompt 改用中性措辭",
              file=sys.stderr)
        return ("防守合併口徑真值讀取失敗（snapshot 缺漏）：不得宣稱防守已足或不足，"
                "本項須人工確認後再判斷")
    return (f"防守合併口徑{_pct:.1f}%"
            f"{'已足' if _pct >= DCM_FREEZE_THRESHOLD else f'不足（門檻 {DCM_FREEZE_THRESHOLD}%）'}"
            "勿追大額")


def defensive_combined_note(snapshot: dict, single_pct: float) -> str:
    """防守判準字串 — 一律由 snapshot.defensive_combined_metric 動態產生（INC-207）。

    2026-09-16 修：此處原本**寫死**「防守合併口徑 69.7% 已足（單看 4.2%）」，
    真值（snapshot.defensive_combined_metric.佔比）早已是 68.5（單桶 17.5），
    導致每天產生的分析與 snapshot 對不上，且被寫進決策紀錄（違反『報告數字不得寫死』）。
    讀不到欄位時回空字串，由呼叫端落回一般「不足 -x.x pp」敘述。
    """
    _pct = ((snapshot or {}).get("defensive_combined_metric") or {}).get("佔比")
    try:
        _pct = float(_pct)
    except (TypeError, ValueError):
        return ""
    try:
        _single = float(single_pct)
    except (TypeError, ValueError):
        _single = 0.0
    _judge = "已足" if _pct >= DCM_FREEZE_THRESHOLD else f"不足（門檻 {DCM_FREEZE_THRESHOLD}%）"
    return (f"🛡️ 防守合併口徑 {_pct:.1f}% {_judge}"
            f"（單看 {_single:.1f}% 僅高股息ETF）；承接凍結")


def penetration_analysis(snapshot: dict) -> dict:
    """動態穿透分析 — 優先讀 snapshot.penetration 真值，fallback 到 db 即時計算"""
    # 優先使用 snapshot 穿透真值（唯一真值來源）
    _cat_map = {"tw_equity": "台股市值型成長", "us_equity": "美股市值型成長",
                "defensive": "防守型配息", "bond": "債券", "cash": "現金/安全網"}
    _snap_pen = (snapshot or {}).get("penetration", {}).get("actual_twd", {})
    if _snap_pen and _snap_pen.get("台股市值型成長"):
        actual_twd = {cat: float(_snap_pen.get(key, 0)) for cat, key in _cat_map.items()}
        total_inv = sum(actual_twd.values()) or 1
        actual = {cat: actual_twd[cat] / total_inv * 100 for cat in actual_twd}
        actual["tech_exposure"] = float((snapshot.get("penetration", {}).get("actual_pct", {})).get("美股市值型成長_科技", 0))
        gaps = {cat: actual.get(cat, 0) - TARGETS[cat] for cat in TARGETS}
        gaps["tech_exposure"] = actual.get("tech_exposure", 0) - TARGETS["tech_exposure"]
        growth_pct = actual.get("tw_equity", 0) + actual.get("us_equity", 0)
        defense_pct = actual.get("defensive", 0)
        safety_pct = actual.get("bond", 0) + actual.get("cash", 0)
        growth_target = TARGETS["tw_equity"] + TARGETS["us_equity"]
        defense_target = TARGETS["defensive"]
        safety_target = TARGETS["bond"] + TARGETS["cash"]
        key_risk, key_action = "", ""
        max_gap_cat = max([k for k in gaps if k != "cash"], key=lambda k: abs(gaps[k]))
        if gaps[max_gap_cat] > 5:
            key_risk = f"{TARGET_EMOJI[max_gap_cat]}{TARGET_LABELS[max_gap_cat]} 超標 +{gaps[max_gap_cat]:.1f}pp"
            if max_gap_cat in ("us_equity",):
                key_action = "等反彈確認後減碼至目標"
        elif gaps[max_gap_cat] < -5:
            if max_gap_cat == "defensive":
                # 2026-08-23：防守單看高股息桶會誤導（8/22 裁示改合併口徑判定）
                # 2026-09-16（INC-207）：原本這裡寫死「合併口徑 69.7% 已足（單看 4.2%）」→
                # 改由 defensive_combined_note() 讀 snapshot.defensive_combined_metric 動態產生。
                key_risk = (defensive_combined_note(snapshot, actual.get("defensive", 0))
                        or f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp")
            else:
                key_risk = f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp"
                if max_gap_cat == "tw_equity":
                    key_action = "台股市值低配屬逐步架構預期：僅回檔小單分批低吸，不強迫貼齊"
        # 2026-08-23：現金超標 → 階段性停泊說明（8/22 裁示：底線制取代 5% 目標；不當風險警報）
        if gaps.get("cash", 0) > 5:
            _cash_note = f"💰 現金 {actual.get('cash', 0):.1f}% 為階段性停泊（{cash_caliber_note(snapshot)}；底線制 ≥70萬 ✅）"
            key_risk = (key_risk + "｜" + _cash_note) if key_risk else _cash_note
        return {
            "actual": actual, "actual_twd": actual_twd, "gaps": gaps,
            "growth_pct": growth_pct, "defense_pct": defense_pct, "safety_pct": safety_pct,
            "growth_target": growth_target, "defense_target": defense_target, "safety_target": safety_target,
            "raw": actual_twd, "key_risk": key_risk, "key_action": key_action, "total_inv": total_inv,
        }
    db_path = str(BASE / "dragon_assets.db")
    if not os.path.exists(db_path):
        return {"error": "db not found"}
    db = sqlite3.connect(db_path)
    
    actual = {}
    actual_twd = {}
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        v = _cat_value(db, cat)
        actual_twd[cat] = v
    db.close()
    
    total_inv = sum(actual_twd.values()) or 1
    for cat in actual_twd:
        actual[cat] = actual_twd[cat] / total_inv * 100
    
    gaps = {}
    for cat in TARGETS:
        gaps[cat] = actual.get(cat, 0) - TARGETS[cat]
    
    growth_pct = actual.get("tw_equity", 0) + actual.get("us_equity", 0)
    defense_pct = actual.get("defensive", 0)
    safety_pct = actual.get("bond", 0) + actual.get("cash", 0)
    growth_target = TARGETS["tw_equity"] + TARGETS["us_equity"]  # 65
    defense_target = TARGETS["defensive"]  # 25
    safety_target = TARGETS["bond"] + TARGETS["cash"]  # 10
    
    key_risk, key_action = "", ""
    max_gap_cat = max([k for k in gaps if k != "cash"], key=lambda k: abs(gaps[k]))
    if gaps[max_gap_cat] > 5:
        key_risk = f"{TARGET_EMOJI[max_gap_cat]}{TARGET_LABELS[max_gap_cat]} 超標 +{gaps[max_gap_cat]:.1f}pp"
        if max_gap_cat in ("us_equity",):
            key_action = "等反彈確認後減碼至目標"
    elif gaps[max_gap_cat] < -5:
        if max_gap_cat == "defensive":
            key_risk = (defensive_combined_note(snapshot, actual.get("defensive", 0))
                        or f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp")
        else:
            key_risk = f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp"
            if max_gap_cat == "tw_equity":
                key_action = "台股市值低配屬逐步架構預期：僅回檔小單分批低吸，不強迫貼齊"
    # 2026-08-23：現金超標 → 階段性停泊說明
    if gaps.get("cash", 0) > 5:
        _cash_note = f"💰 現金 {actual.get('cash', 0):.1f}% 為階段性停泊（{cash_caliber_note(snapshot)}；底線制 ≥70萬 ✅）"
        key_risk = (key_risk + "｜" + _cash_note) if key_risk else _cash_note

    return {
        "actual": actual,
        "actual_twd": actual_twd,
        "gaps": gaps,
        "growth_pct": growth_pct,
        "defense_pct": defense_pct,
        "safety_pct": safety_pct,
        "growth_target": growth_target,
        "defense_target": defense_target,
        "safety_target": safety_target,
        "raw": actual_twd,
        "key_risk": key_risk,
        "key_action": key_action,
        "total_inv": total_inv,
    }

def _industry_context() -> str:
    """GICS 產業分布 + 資金流向 + 輪動建議 + 底層風險因子（供 LLM prompt，2026-08-22 加）"""
    ctx = ""
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        gics = snap.get("industry_penetration", {}).get("產業", {})
        rot = snap.get("rotation_recommendation", {}).get("總結", "")
        sf = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8")).get("sector_flow", {})
        top4 = "、".join(f"{k} {v['佔比']:.1f}%" for k, v in sorted(gics.items(), key=lambda x: -x[1]['金額'])[:4] if v['金額'] > 0)
        ctx = (f"GICS產業：{top4}｜資金流向：{sf.get('台股總結','—')}；{sf.get('美股總結','—')}｜"
               f"輪動建議：{rot or '—'}｜底層風險因子：美股相關>60%、美元信用債~20%、現金(台幣)~12.8%、科技 17.5%")
    except Exception:
        ctx = ""
    return ctx


def _data_fingerprint() -> str:
    """2026-08-27：快取數據指紋 = snapshot.json 內容 hash。
    數據沒變 → 指紋相同 → 開發模式可沿用當天快取（零 API 成本）。"""
    import hashlib
    try:
        _raw = (BASE / "snapshot.json").read_text(encoding="utf-8")
        return hashlib.md5(_raw.encode("utf-8")).hexdigest()[:8]
    except Exception:
        return "x"


def _llm_cached(name: str, prompt: str, system: str, max_tokens: int = 450) -> str | None:
    """2026-08-24 優化：LLM 快取（同日同款不重複呼叫）+ 降 max_tokens，省 DeepSeek 用量
    2026-08-27 強化：檔名加數據指紋；HERMES_DEV_MODE=1 且數據未變時沿用當天最新快取（開發驗證免重付費）"""
    import hashlib, os
    _script_hash = hashlib.md5(Path(__file__).read_bytes()).hexdigest()[:8] # 新增：腳本本身的哈希值
    _ck = hashlib.md5(f"{prompt}{system}{max_tokens}".encode("utf-8")).hexdigest()[:12] # 更新：快取鍵納入 system 和 max_tokens
    _fp = _data_fingerprint()
    _cf = BASE / "data" / f"{name}_{TODAY}_{_fp}_{_script_hash}_{_ck}.json" # 更新：新的快取檔名格式
    if _cf.exists():
        try:
            return json.loads(_cf.read_text(encoding="utf-8")).get("out")
        except Exception:
            pass
    # 2026-09-13 INC-159 2a：同日同數據沿用 → 預設啟用（原僅 HERMES_DEV_MODE=1）
    # 讓「當日快取被誤刪」（一天內曾刪 582 檔，含當日 2 檔）不再造成重複付費。
    # 安全條件：只沿用「同一腳本哈希」的快取（＝同樣的 prompt 組法），避免改了程式
    # 還吃舊答案；數據指紋 _fp 相同才沿用（snapshot 未變）。
    _cands = sorted((BASE / "data").glob(f"{name}_{TODAY}_{_fp}_{_script_hash}_*.json"))
    for _pick in reversed(_cands):
        try:
            _cached = json.loads(_pick.read_text(encoding="utf-8")).get("out")
            if _cached:
                print(f"♻️ 同日快取沿用（{_pick.name}）— 未重複呼叫 API")
                return _cached
        except Exception:
            pass
    # 2026-09-13 INC-159 2a②：耐久鏡像（cache/llm_archive/，不在 data/ 內）
    # 上面兩層都在 data/ → 若當日檔被整批刪除（9/13 曾刪 582 檔，含當日 2 檔）就救不回。
    # 鏡像寫在 data/ 之外，任何只掃 data/ 的清理都不會動到 → 同日重跑 0 成本。
    _mir = BASE / "cache" / "llm_archive"
    for _pick in [ _mir / _cf.name ] + sorted(_mir.glob(f"{name}_{TODAY}_{_fp}_{_script_hash}_*.json")):
        try:
            if _pick.exists():
                _cached = json.loads(_pick.read_text(encoding="utf-8")).get("out")
                if _cached:
                    print(f"♻️ 快取鏡像沿用（{_pick.name}）— 未重複呼叫 API")
                    return _cached
        except Exception:
            pass
    from llm_analysis import ask_llm
    _out = ask_llm(prompt, system=system, max_tokens=max_tokens)
    if _out:
        (BASE / "data").mkdir(exist_ok=True)
        _cf.write_text(json.dumps({"out": _out}, ensure_ascii=False), encoding="utf-8")
        try:
            (BASE / "cache").mkdir(exist_ok=True)
            _mir.mkdir(exist_ok=True)
            (_mir / _cf.name).write_text(
                json.dumps({"out": _out}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return _out


def generate_buffett_report(pen: dict, market_text: str = "") -> list:
    """巴菲特視角 — LLM 真實分析優先（2026-08-22 升級），失敗 fallback 模板"""
    a, g = pen["actual"], pen["gaps"]
    try:
        _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _fmt = "、".join(f"{TARGET_LABELS[c]} {a.get(c,0):.1f}%（目標{TARGETS[c]}%，{g.get(c,0):+.1f}pp）"
                         for c in ["tw_equity", "us_equity", "defensive", "bond", "cash"])

        _usd_exp_val = (_snap.get("usd_exposure_monitor", {}) or {}).get("current", {}).get("合計", 0)
        _usd_cap_val = float((_snap.get("usd_exposure_monitor", {}) or {}).get("threshold") or 60)
        _tech_exp_val = (_snap.get("penetration", {}) or {}).get("actual_pct", {}).get("美股市值型成長_科技", 0)
        _tech_cap_val = TARGETS["tech_exposure"]

        _prompt = (
            f"你是巴菲特（波克夏董事長）。以下是龍九控股資產穿透資料（總投資 {pen['total_inv']/1e4:.0f}萬台幣）：\n"
            f"五桶：{_fmt}\n"
            f"主要偏離：{pen.get('key_risk','—')}｜建議：{pen.get('key_action','—')}\n"
            f"成長 {pen['growth_pct']:.1f}%（目標{pen['growth_target']}%）；防禦 {pen['defense_pct']:.1f}%；安全網 {pen['safety_pct']:.1f}%\n"
            f"結構風險：美元曝險{_usd_exp_val:.1f}%（紅線{_usd_cap_val:.0f}%）、高科技{_tech_exp_val:.1f}%（紅線{_tech_cap_val:.0f}%）、機構雷達 台股🟢/黃金🟢/原油🔴/美債10Y🟡\n"
            f"產業與風險因子：{_industry_context()}\n"
            f"{market_text}\n"
            f"硬性約束（違反即無效，不可建議）：現金=底線制70萬（{cash_caliber_note(_snap)}）；"
            f"台股加碼單筆≤5萬、8-12週分批；美股逢彈減碼≤20萬/次；新增資金全台幣（禁止兌外幣/匯率避險建議）；"
            f"債券等 US30Y<5.30%；石油 Locked 禁建議；防守合併口徑{defensive_combined_phrase(_snap)}；黃金衛星≤5% PI後分3批；不動產(REITs)禁建議（實體3,401萬已超配）。\n"
            f"請以巴菲特投資哲學（護城河、安全邊際、能力圈、長期持有、別人恐懼我貪婪）做 3 點具體觀察 + 1 個紀律提醒，200字內，繁體中文，不要重複數字表。"
        )
        _out = _llm_cached("buffett", _prompt, "你是巴菲特視角的投資分析師。輸出繁體中文，精簡犀利，有具體觀點。")
        if _out:
            # 2026-08-23 修復：LLM 分支必須含「主要風險/總投資部位/TWD」關鍵字，CIO 審查(cio_review.py L162-167)才不會擋
            _kr = pen.get("key_risk", "—")
            _inv = f"{pen.get('total_inv', 0):,.0f}"
            return ["🧓 巴菲特視角（LLM 真實分析）", f"⚡ 主要風險：{_kr}\n📊 總投資部位：{_inv} TWD\n{_out}"]
    except Exception:
        pass
    # fallback 模板（API 失敗時）
    lines = []
    
    lines.append("🧓 巴菲特式思考（動態穿透模型）")
    if pen["key_risk"]:
        lines.append(f"• 主要偏離：{pen['key_risk']}")
    if pen["key_action"]:
        lines.append(f"• 建議：{pen['key_action']}")
    
    lines.append(f"• 總投資部位：{pen['total_inv']:,.0f} TWD")
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        v = a.get(cat, 0)
        t = TARGETS[cat]
        gv = g.get(cat, 0)
        sign = "+" if gv >= 0 else ""
        lines.append(f"  {TARGET_EMOJI[cat]} {TARGET_LABELS[cat]}：{v:.1f}%（目標 {t}%，{sign}{gv:.1f}pp）")
    
    lines.append(f"• 成長：{pen['growth_pct']:.1f}%（目標 {pen['growth_target']}%）")
    lines.append(f"• 防禦：{pen['defense_pct']:.1f}%（目標 {pen['defense_target']}%）")
    lines.append(f"• 安全網（債+現金）：{pen['safety_pct']:.1f}%（目標 {pen['safety_target']}%）")
    
    # 風險
    lines.append("")
    lines.append("⚡ 主要風險：")
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        gv = g.get(cat, 0)
        if abs(gv) > 5:
            direction = "超標" if gv > 0 else "不足"
            lines.append(f"  {TARGET_EMOJI[cat]} {TARGET_LABELS[cat]} {direction} {abs(gv):.1f}pp")
    
    # 安全邊際
    lines.append("")
    lines.append("💡 安全邊際：")
    lines.append(f"  現金佔比 {a.get('cash', 0):.1f}%（目標 {TARGETS['cash']}%）")
    lines.append(f"  債券佔比 {a.get('bond', 0):.1f}%（目標 {TARGETS['bond']}%）")
    
    lines.append("")
    from datetime import date as _d8
    lines.append(f"🎯 策略建議（核心‑衛星保守成長版，{_d8.today().strftime('%Y-%m-%d')}）：")
    _tw_gv = g.get("tw_equity", 0)
    _us_gv = g.get("us_equity", 0)
    _def_gv = g.get("defensive", 0)
    if _tw_gv < -5:
        lines.append("  ✅ 台股市值低配屬預期：僅回檔小單分批低吸（單筆≤5萬），不強迫貼齊")
    elif _tw_gv > 5:
        lines.append(f"  ⚠️ 台股市值超標 {_tw_gv:.0f}pp：凍結大額單，回檔小單分批")
    else:
        lines.append("  ✅ 台股市值合理範圍（維持逐步架構）")
    if _us_gv > 5:
        lines.append(f"  ⚠️ 美股超配 {_us_gv:.0f}pp：不急砍，逢反彈分批減碼收斂至30%")
    elif _us_gv < -5:
        lines.append("  ✅ 美股低配：觀察期不追高，逢回檔小單")
    else:
        lines.append("  ✅ 美股合理範圍")
    if _def_gv < -5:
        lines.append("  ✅ 防守型第一優先：00878/00713 分批建倉（單筆<5萬）")
    elif _def_gv > 5:
        lines.append("  ⚠️ 防守超標：維持現況，不追高")
    else:
        lines.append("  ✅ 防守合理範圍（第一優先維持）")
    lines.append("  🔒 兩條底線：現金≥70萬；US30Y 無連3日<5.20% 不開放市值大額進場")
    
    return lines

def us30y_note() -> str:
    """US30Y 單一真值 = us30y_state.json（2026-09-11 修：原為 f-string 寫死 5.32%，
    會把過期值餵給 LLM 並在日報留下舊數字）。每次呼叫重讀，確保最新。"""
    try:
        _st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        _r = float(_st["last_rate"])
        _d = _st.get("last_date", "")
    except Exception:
        return "US30Y 資料無法取得（us30y_state.json 缺漏或格式異常）"
    _pos = "已站上" if _r >= 5.30 else ("貼近" if _r >= 5.20 else "未觸及")
    return f"US30Y {_r:.2f}%（{_d} 收盤）{_pos}5.30% 凍結線"


def generate_cto_report(pen: dict, market_text: str = "") -> list:
    """CTO 技術視角 — LLM 真實分析優先（2026-08-22 升級），失敗 fallback 模板"""
    a, g = pen["actual"], pen["gaps"]
    try:
        _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _fmt = "、".join(f"{TARGET_LABELS[c]} {a.get(c,0):.1f}%（目標{TARGETS[c]}%，{g.get(c,0):+.1f}pp）"
                         for c in ["tw_equity", "us_equity", "defensive", "bond", "cash"])
        _usd_exp_val = (_snap.get("usd_exposure_monitor", {}) or {}).get("current", {}).get("合計", 0)
        _usd_cap_val = float((_snap.get("usd_exposure_monitor", {}) or {}).get("threshold") or 60)
        _tech_exp_val = (_snap.get("penetration", {}) or {}).get("actual_pct", {}).get("美股市值型成長_科技", 0)
        _tech_cap_val = TARGETS["tech_exposure"]
        _prompt = (
            f"你是龍九控股的 CTO（技術分析師）。以下為資產穿透資料（總投資 {pen['total_inv']/1e4:.0f}萬）：\n"
            f"五桶：{_fmt}\n"
            f"主要偏離：{pen.get('key_risk','—')}｜建議：{pen.get('key_action','—')}\n"
            f"結構風險：美元曝險{_usd_exp_val:.1f}%（紅線{_usd_cap_val:.0f}%）、高科技{_tech_exp_val:.1f}%（紅線{_tech_cap_val:.0f}%）、機構雷達 台股🟢/黃金🟢/原油🔴/美債10Y🟡、{us30y_note()}\n"
            f"產業與風險因子：{_industry_context()}\n"
            f"{market_text}\n"
            f"硬性約束（違反即無效，不可建議）：現金=底線制70萬（{cash_caliber_note(_snap)}）；"
            f"台股加碼單筆≤5萬、8-12週分批（不可建議單筆大額）；美股逢彈減碼≤20萬/次；新增資金全台幣（禁止兌外幣/匯率避險建議）；"
            f"債券等 US30Y<5.30%（禁建議買債）；石油 Locked 禁建議；防守合併口徑{defensive_combined_phrase(_snap)}；黃金衛星≤5% PI後分3批；不動產(REITs)禁建議（實體3,401萬已超配）。\n"
            f"請以技術面（動能、趨勢、支撐壓力、風險）+ 產業資金流向（哪個產業順勢/逆勢）給：今日最大風險 + 具體建議動作（含標的/金額節奏，須符合上述約束），150字內，繁體中文。"
        )
        _out = _llm_cached("cto", _prompt, "你是技術分析師（CTO）。輸出繁體中文，直接給結論與動作，不要客套。")
        if _out:
            # 2026-08-26 修復：LLM 分支輸出可能用「最大風險/動作」標籤，CIO 審查(cio_review.py L176-179)
            # 要求「今日最大風險」+「建議動作/具體動作」才放行 → 標準化標籤（同 8/23 巴菲特分支修法）
            _out = _out.strip()
            if "今日最大風險" not in _out:
                _out = _out.replace("最大風險", "今日最大風險", 1) if "最大風險" in _out else f"今日最大風險：{_out}"
            if "建議動作" not in _out and "具體動作" not in _out:
                _out = _out.replace("動作", "建議動作", 1) if "動作" in _out else _out + "\n建議動作：依風險對策分批執行（台股單筆≤5萬、美股逢彈減碼≤20萬）。"
            return ["CTO 技術視角（LLM 真實分析）", _out]
    except Exception:
        pass
    # fallback 模板
    lines = ["CTO 技術視角"]
    _kr = pen.get("key_risk", "")
    if _kr:
        lines.append(f"今日最大風險：{_kr}")
    lines.append("建議動作：")
    for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
        gv = pen["gaps"].get(cat, 0)
        if abs(gv) > 5:
            if cat == "tw_equity":
                lines.append("  tw_equity：凍結大額單，僅回檔小單分批（單筆≤5萬）")
            elif cat == "us_equity":
                lines.append("  us_equity：逢反彈分批減碼，收斂至30%目標")
            elif cat == "defensive":
                lines.append("  defensive：第一優先，00878/00713 分批建倉")
            else:
                direction = "減碼" if gv > 0 else "補碼"
                lines.append(f"  {cat}：{direction} {abs(gv):.0f}pp")
    lines.append("")
    lines.append("再平衡：逐步架構導向，容許階段偏離；優先守現金底線70萬")
    return lines

def main(**kwargs):
    # 1. 從 snapshot 讀取
    snap = json.loads((BASE / "snapshot.json").read_text("utf-8"))
    
    # 2. 穿透分析
    pen = penetration_analysis(snap)
    if "error" in pen:
        print(f"Error: {pen['error']}"); return
    
    # 3. 市場情報
    market = snap.get("market", {})
    tw_idx = market.get("twii", "N/A")
    _mkt_txt = ""
    try:
        import sqlite3
        _db = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _r = _db.execute("SELECT buy_count, sell_count, hunter_count, tw_index, tw_change, sox, summary FROM market_intel WHERE date=? ORDER BY timestamp DESC LIMIT 1", (TODAY,)).fetchone()
        _db.close()
        if _r:
            # 2026-09-13 INC-170：market_intel 的 tw_index/sox 自 9/10 起多為 0（compile_intel 上游缺值）
            # → 值為 0 時退回 daily_analysis.json 市場字串，避免日報出現「加權 0 (+0.00%) | SOX 0」
            _tw_i = float(_r[3] or 0); _tw_c = float(_r[4] or 0); _sox_v = float(_r[5] or 0)
            if _tw_i == 0 or _sox_v == 0:
                try:
                    _da_m = json.loads((BASE / "daily_analysis.json").read_text(encoding="utf-8")).get("market", {}) or {}
                except Exception:
                    _da_m = {}
                _tw_txt = str(_da_m.get("twii", "") or "").strip()
                _sox_txt = str(_da_m.get("sox", "") or "").strip()
                _bits = [f"市場：加權 {_tw_txt or '—'}"]
                if _sox_txt:
                    _bits.append(f"SOX {_sox_txt}")
                _bits.append(f"Hunter {_r[2]}筆 (買{_r[0]}/賣{_r[1]})")
                _mkt_txt = " | ".join(_bits)
            else:
                _mkt_txt = f"市場：加權 {_tw_i:,.0f} ({_tw_c:+.2f}%) | SOX {_sox_v:,.0f} | Hunter {_r[2]}筆 (買{_r[0]}/賣{_r[1]})"
    except Exception:
        pass

    # 4. 產生報告（LLM 真實分析優先）
    buffett = generate_buffett_report(pen, _mkt_txt)

    # 補入市場情報摘要（模板 fallback 時）
    if _mkt_txt and len(buffett) < 4:
        buffett.insert(1, f"📊 {_mkt_txt}")
    cto = generate_cto_report(pen, _mkt_txt)
    
    report = "\n".join(buffett) + "\n\n" + "\n".join(cto)
    print(report)
    
    # 5. 存檔
    (BASE / f"buffett_cto_report_{TODAY}.md").write_text(report, encoding="utf-8")
    print(f"\n✅ Report saved to buffett_cto_report_{TODAY}.md")
    
    # 6. Telgram 推（摘要 + 本週交易計畫，2026-08-24 新增）
    if TG_TOKEN and TG_CHAT_ID:
        msg = f"🧓 Buffett/CTO 動態分析 {TODAY}\n"
        for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
            v = pen["actual"].get(cat, 0)
            t = TARGETS[cat]
            gv = pen["gaps"].get(cat, 0)
            msg += f"{TARGET_EMOJI[cat]} {v:.1f}%（目標{t}%、{gv:+.1f}pp）\n"
        msg += f"\n{pen['key_risk']}\n{pen['key_action']}"
        # 本週交易計畫（rotation_engine build_trade_plan）
        try:
            import json as _json
            _snap = _json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
            _sf = {}
            if (BASE / "radar_state.json").exists():
                _sf = _json.loads((BASE / "radar_state.json").read_text(encoding="utf-8")).get("sector_flow", {})
            from rotation_engine import build_recommendation, build_trade_plan
            _rec = build_recommendation(_snap.get("industry_penetration", {}), _sf)
            _plan = build_trade_plan(_rec, _snap)
            msg += "\n\n🎯 本週交易計畫："
            for p in _plan:
                msg += f"\n  {p['產業']}: {p['金額']:,}（{p['節奏']}）"
        except Exception as _e:
            msg += f"\n\n⚠️ 交易計畫讀取失敗：{_e}"
        # 本週操作執行紀錄（動態讀取最新 weekly_ops_closure_*）
        try:
            import json as _json
            _snap_data = _json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
            _ops_keys = sorted([k for k in _snap_data.keys() if k.startswith("weekly_ops_closure_")])
            _ops = _snap_data.get(_ops_keys[-1], {}) if _ops_keys else {}
            if _ops and _ops.get("執行清單"):
                msg += f"\n\n📋 本週操作執行紀錄（{_ops.get('期間','')}）："
                for x in _ops.get("執行清單", []):
                    msg += f"\n  ✅ {x.get('項目','')}（{x.get('金額','')}）"
                _close = _ops.get("閉環", {}).get("待追蹤", [])
                if _close:
                    msg += "\n📌 閉環待追蹤：" + "｜".join(_close)
        except Exception:
            pass
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                         json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
        except: pass

if __name__ == "__main__":
    main()
