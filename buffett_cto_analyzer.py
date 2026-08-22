#!/usr/bin/env python3
"""Buffett/CTO 穿透分析器（v4 — 動態目標）"""
from __future__ import annotations

import json, os, sqlite3
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
except Exception:
    _snap_tgt = {}
TARGETS = {
    "tw_equity": _snap_tgt.get("台股市值型目標", 20),
    "us_equity": _snap_tgt.get("美股市值型目標", 30),
    "defensive": _snap_tgt.get("配息型目標", 20),
    "bond": _snap_tgt.get("債券型目標", 15),
    "cash": _snap_tgt.get("現金目標", 15),
}
TARGET_LABELS = {"tw_equity":"台股","us_equity":"美股","defensive":"防守","bond":"債券","cash":"現金"}
TARGET_EMOJI = {"tw_equity":"🇹🇼","us_equity":"🇺🇸","defensive":"🛡️","bond":"💵","cash":"💰"}

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
        gaps = {cat: actual.get(cat, 0) - TARGETS[cat] for cat in TARGETS}
        growth_pct = actual.get("tw_equity", 0) + actual.get("us_equity", 0)
        defense_pct = actual.get("defensive", 0)
        safety_pct = actual.get("bond", 0) + actual.get("cash", 0)
        growth_target = TARGETS["tw_equity"] + TARGETS["us_equity"]
        defense_target = TARGETS["defensive"]
        safety_target = TARGETS["bond"] + TARGETS["cash"]
        key_risk, key_action = "", ""
        max_gap_cat = max(gaps, key=lambda k: abs(gaps[k]))
        if gaps[max_gap_cat] > 5:
            key_risk = f"{TARGET_EMOJI[max_gap_cat]}{TARGET_LABELS[max_gap_cat]} 超標 +{gaps[max_gap_cat]:.1f}pp"
            if max_gap_cat in ("us_equity",):
                key_action = "等反彈確認後減碼至目標"
        elif gaps[max_gap_cat] < -5:
            key_risk = f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp"
            if max_gap_cat == "tw_equity":
                key_action = "台股市值低配屬逐步架構預期：僅回檔小單分批低吸，不強迫貼齊"
            elif max_gap_cat == "defensive":
                key_action = f"防守型第一優先：00878/00713 分批建倉至目標 {TARGETS[max_gap_cat]:.0f}%"
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
    max_gap_cat = max(gaps, key=lambda k: abs(gaps[k]))
    if gaps[max_gap_cat] > 5:
        key_risk = f"{TARGET_EMOJI[max_gap_cat]}{TARGET_LABELS[max_gap_cat]} 超標 +{gaps[max_gap_cat]:.1f}pp"
        if max_gap_cat in ("us_equity",):
            key_action = "等反彈確認後減碼至目標"
    elif gaps[max_gap_cat] < -5:
        key_risk = f"{TARGET_EMOJI[max_gap_cat]} {TARGET_LABELS[max_gap_cat]} 不足 {gaps[max_gap_cat]:.1f}pp"
        if max_gap_cat == "tw_equity":
            key_action = "台股市值低配屬逐步架構預期：僅回檔小單分批低吸，不強迫貼齊"
        elif max_gap_cat == "defensive":
            key_action = f"防守型第一優先：00878/00713 分批建倉至目標 {TARGETS[max_gap_cat]:.0f}%"
    
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


def generate_buffett_report(pen: dict, market_text: str = "") -> list:
    """巴菲特視角 — LLM 真實分析優先（2026-08-22 升級），失敗 fallback 模板"""
    a, g = pen["actual"], pen["gaps"]
    try:
        from llm_analysis import ask_llm
        _fmt = "、".join(f"{TARGET_LABELS[c]} {a.get(c,0):.1f}%（目標{TARGETS[c]}%，{g.get(c,0):+.1f}pp）"
                         for c in ["tw_equity", "us_equity", "defensive", "bond", "cash"])
        _prompt = (
            f"你是巴菲特（波克夏董事長）。以下是龍九控股資產穿透資料（總投資 {pen['total_inv']/1e4:.0f}萬台幣）：\n"
            f"五桶：{_fmt}\n"
            f"主要偏離：{pen.get('key_risk','—')}｜建議：{pen.get('key_action','—')}\n"
            f"成長 {pen['growth_pct']:.1f}%（目標{pen['growth_target']}%）；防禦 {pen['defense_pct']:.1f}%；安全網 {pen['safety_pct']:.1f}%\n"
            f"結構風險：美元曝險64%（紅線50%）、高科技17.5%（紅線30%）、機構雷達 台股🟢/黃金🟢/原油🔴/美債10Y🟡\n"
            f"產業與風險因子：{_industry_context()}\n"
            f"{market_text}\n"
            f"硬性約束（違反即無效，不可建議）：現金=底線制70萬（22.1%含 MMF 500萬 已指定標案/質押補救，不可減現金）；"
            f"台股加碼單筆≤5萬、8-12週分批；美股逢彈減碼≤20萬/次；新增資金全台幣（禁止兌外幣/匯率避險建議）；"
            f"債券等 US30Y<5.30%；石油 Locked 禁建議；防守合併口徑69.5%已足勿追大額；黃金衛星≤5% PI後分3批；不動產(REITs)禁建議（實體3,401萬已超配）。\n"
            f"請以巴菲特投資哲學（護城河、安全邊際、能力圈、長期持有、別人恐懼我貪婪）做 3 點具體觀察 + 1 個紀律提醒，200字內，繁體中文，不要重複數字表。"
        )
        _out = ask_llm(_prompt, system="你是巴菲特視角的投資分析師。輸出繁體中文，精簡犀利，有具體觀點。")
        if _out:
            return ["🧓 巴菲特視角（LLM 真實分析）", _out]
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

def generate_cto_report(pen: dict, market_text: str = "") -> list:
    """CTO 技術視角 — LLM 真實分析優先（2026-08-22 升級），失敗 fallback 模板"""
    a, g = pen["actual"], pen["gaps"]
    try:
        from llm_analysis import ask_llm
        _fmt = "、".join(f"{TARGET_LABELS[c]} {a.get(c,0):.1f}%（目標{TARGETS[c]}%，{g.get(c,0):+.1f}pp）"
                         for c in ["tw_equity", "us_equity", "defensive", "bond", "cash"])
        _prompt = (
            f"你是龍九控股的 CTO（技術分析師）。以下為資產穿透資料（總投資 {pen['total_inv']/1e4:.0f}萬）：\n"
            f"五桶：{_fmt}\n"
            f"主要偏離：{pen.get('key_risk','—')}｜建議：{pen.get('key_action','—')}\n"
            f"結構風險：美元曝險64%（紅線50%）、高科技17.5%（紅線30%）、機構雷達 台股🟢/黃金🟢/原油🔴/美債10Y🟡、US30Y 5.32% 貼近5.30%凍結線\n"
            f"產業與風險因子：{_industry_context()}\n"
            f"{market_text}\n"
            f"硬性約束（違反即無效，不可建議）：現金=底線制70萬（22.1%含 MMF 500萬 已指定標案/質押補救，不可建議減現金）；"
            f"台股加碼單筆≤5萬、8-12週分批（不可建議單筆大額）；美股逢彈減碼≤20萬/次；新增資金全台幣（禁止兌外幣/匯率避險建議）；"
            f"債券等 US30Y<5.30%（禁建議買債）；石油 Locked 禁建議；防守合併口徑69.5%已足勿追大額；黃金衛星≤5% PI後分3批；不動產(REITs)禁建議（實體3,401萬已超配）。\n"
            f"請以技術面（動能、趨勢、支撐壓力、風險）+ 產業資金流向（哪個產業順勢/逆勢）給：今日最大風險 + 具體建議動作（含標的/金額節奏，須符合上述約束），150字內，繁體中文。"
        )
        _out = ask_llm(_prompt, system="你是技術分析師（CTO）。輸出繁體中文，直接給結論與動作，不要客套。")
        if _out:
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
            _mkt_txt = f"市場：加權 {_r[3]:,.0f} ({_r[4]:+.2f}%) | SOX {_r[5]:,.0f} | Hunter {_r[2]}筆 (買{_r[0]}/賣{_r[1]})"
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
    
    # 6. Telgram 推（摘要）
    if TG_TOKEN and TG_CHAT_ID:
        msg = f"🧓 Buffett/CTO 動態分析 {TODAY}\n"
        for cat in ["tw_equity", "us_equity", "defensive", "bond", "cash"]:
            v = pen["actual"].get(cat, 0)
            t = TARGETS[cat]
            gv = pen["gaps"].get(cat, 0)
            msg += f"{TARGET_EMOJI[cat]} {v:.1f}%（目標{t}%、{'✅' if abs(gv)<=5 else '+'+str(gv)[:4] if gv>0 else str(gv)[:4]}pp）\n"
        msg += f"\n{pen['key_risk']}\n{pen['key_action']}"
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                         json={"chat_id": TG_CHAT_ID, "text": msg}, timeout=10)
        except: pass

if __name__ == "__main__":
    main()
