#!/usr/bin/env python3
"""
Buffett/CTO 穿透分析器（v3）
報告結構：
  1. 市場情報
  2. 穿透分析（asset class 占比 + 再平衡狀態）
  3. Buffett/CTO 建議
  4. 機會子彈戰術
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
import requests

BASE = Path(__file__).parent.resolve()
load_dotenv(BASE / ".env")
TODAY = date.today().isoformat()
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")


def penetration_analysis(snapshot: dict) -> dict:
    pen = snapshot.get("penetration", {})
    actual = pen.get("actual_pct", {})
    actual_twd = pen.get("actual_twd", {})
    targets = snapshot.get("saa_targets", {"growth": 0.30, "defensive": 0.60, "safety_net": 0.10})
    
    tw_equity = actual.get("台股市值型成長", 0)
    us_equity = actual.get("美股市值型成長", 0)
    dividend = actual.get("防守型配息", 0)
    bond_cash = actual.get("債券及安全現金", 0)
    safety_cash = actual_twd.get("現金/安全網", 0)
    
    growth_pct = tw_equity + us_equity
    defense_pct = dividend + bond_cash
    
    raw = {
        "台股市值型成長": actual_twd.get("台股市值型成長", 0),
        "美股市值型成長": actual_twd.get("美股市值型成長", 0),
        "防守型配息": actual_twd.get("防守型配息", 0),
        "債券及安全現金": actual_twd.get("債券及安全現金", 0),
        "現金/安全網": safety_cash,
        "不動產": actual_twd.get("不動產", 0),
    }
    
    # 用投資部位（不含不動產）計算再平衡百分比
    invest_total = sum(v for k, v in raw.items() if k != "不動產")
    safety_pct = safety_cash / invest_total * 100 if invest_total > 0 else 0
    
    return {
        "total_assets": invest_total,
        "raw": raw,
        "pct": {
            "市值型成長（台股/美股）": growth_pct,
            "配息型高股息": dividend,
            "債券型防禦": bond_cash,
            "現金/安全網": safety_pct,
            "台股市值型成長": tw_equity,
            "美股市值型成長": us_equity,
            "防守型配息": dividend,
            "債券及安全現金": bond_cash,
        },
        "targets": targets,
        "growth_pct": growth_pct,
        "defense_pct": defense_pct,
        "safety_pct": safety_pct,
        "alert": pen.get("alert", ""),
    }

def load_market_intel() -> dict:
    p = BASE / "market_intel.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def generate_report(pen: dict, intel: dict, snapshot: dict) -> str:

    # defensive: snapshot may contain dict values instead of scalars
    def _safe_int(v, fallback=0):
        if isinstance(v, dict):
            return fallback
        try:
            return int(v or 0)
        except Exception:
            return fallback

    net = snapshot.get("net_worth", 0)
    monthly_income = snapshot.get("monthly_income", 0)
    monthly_expense = snapshot.get("monthly_expense", 0)
    pi_raw = snapshot.get("passive_income", 0) or 0

    if isinstance(pi_raw, dict):

        passive_income = pi_raw.get("total_conservative", 0) or 0

    else:

        passive_income = _safe_int(pi_raw)

    # Snapshot-aware allocation context
    _has_snapshot = False
    try:
        _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _pen = _snap.get("penetration", {}).get("actual_twd", {})
        _us_eq = float(_pen.get("美股市值型成長", 0))
        _tw_eq = float(_pen.get("台股市值型成長", 0))
        _div  = float(_pen.get("防守型配息", 0))
        _bond = float(_pen.get("債券及安全現金", 0))
        _cash = float(_pen.get("現金/安全網", 0))
        _invest_total = _us_eq + _tw_eq + _div
        _us_pct = _us_eq / (_invest_total + 1e-9)
        _tw_pct = _tw_eq / (_invest_total + 1e-9)
        _safe_total = _bond + _cash
        _safe_pct = _safe_total / (_invest_total + _safe_total + 1e-9)
        _has_snapshot = True
    except Exception:
        _has_snapshot = False


    targets = pen.get("targets", {})
    raw = pen.get("raw", {})
    pct = pen.get("pct", {})

    target_growth = targets.get("growth", 0) * 100
    target_defense = targets.get("defensive", 0) * 100
    target_safety = targets.get("safety_net", 0) * 100

    actual_growth_pct = pct.get("市值型成長（台股/美股）", 0)
    actual_defense_pct = pct.get("防禦（防守型配息+債券）") if pct.get("防禦（防守型配息+債券）") else pct.get("配息型高股息", 0) + pct.get("債券型防禦", 0)
    actual_safety_pct = pct.get("現金/安全網", 0)

    drift_growth = actual_growth_pct - target_growth
    drift_defense = actual_defense_pct - target_defense
    drift_safety = actual_safety_pct - target_safety

    rebalance_needed = []
    if abs(drift_growth) > 10:
        rebalance_needed.append(f"成長型偏離目標 {drift_growth:+.1f}pp")
    if abs(drift_defense) > 10:
        rebalance_needed.append(f"防禦型偏離目標 {drift_defense:+.1f}pp")
    if abs(drift_safety) > 5:
        rebalance_needed.append(f"安全網偏離目標 {drift_safety:+.1f}pp")
    rebalance_note = "🔴 需再平衡：" + "；".join(rebalance_needed) if rebalance_needed else "✅ 配置在目標區間內"

    twii = intel.get("TAIEX", {}).get("1_week_change_pct", "N/A") if intel else "N/A"
    soxx = intel.get("SOXX", {}).get("1_week_change_pct", "N/A") if intel else "N/A"
    foreign = intel.get("foreign_flow", {}).get("7d_net", "N/A") if intel else "N/A"

    tw_growth_twd = raw.get("台股市值型成長", 0)
    us_growth_twd = raw.get("美股市值型成長", 0)
    dividend_twd = raw.get("防守型配息", 0)
    bond_twd = raw.get("債券及安全現金", 0)
    cash_twd = raw.get("現金/安全網", 0)

    lines = []
    lines.append("【市場情報】")
    lines.append(f"• 台股加權指數：{intel.get('TAIEX', {}).get('current', 'N/A')}（單週 {twii}%）")
    lines.append(f"• 費半：{soxx}%")
    lines.append(f"• 外資動向：{foreign}")
    lines.append(f"• 機會子彈觸發條件：單週漲跌幅 >= 10%（目前單週 {twii}%，{'已觸發' if abs(twii) >= 10 else '距離觸發線還有空間'}）")
    lines.append("")
    lines.append("【穿透分析】")
    lines.append("【穿透分析】")
    lines.append(f"• 淨資產：{net:,} TWD")
    denom = pen.get("total_assets", 1) or 1
    lines.append(f"• 投資部位（不含不動產）：{denom:,.0f} TWD")
    lines.append(f"• 被動收入/月支出：{passive_income:,} / {monthly_expense:,}")
    lines.append("")
    lines.append(f"▸ 資產類型 vs 目標（基於投資部位）：成長 {target_growth:.0f}% / 防禦 {target_defense:.0f}% / 安全網 {target_safety:.0f}%")
    lines.append("")
    lines.append("▸ 實際穿透：")
    lines.append(f"  • 台股市值型成長（0050/009816）：{tw_growth_twd:,.0f} TWD（{tw_growth_twd/denom*100:.1f}%）")
    lines.append(f"  • 美股市值型成長（00646/貝萊德/聯博）：{us_growth_twd:,.0f} TWD（{us_growth_twd/denom*100:.1f}%）")
    lines.append(f"  • 防守型配息（00878/00713/0056/安聯）：{dividend_twd:,.0f} TWD（{dividend_twd/denom*100:.1f}%）")
    lines.append(f"  • 債券及安全現金：{bond_twd:,.0f} TWD（{bond_twd/denom*100:.1f}%）")
    lines.append(f"  • 現金/安全網：{cash_twd:,.0f} TWD（{cash_twd/denom*100:.1f}%）")
    lines.append("")
    lines.append(f"• 再平衡狀態：{rebalance_note}")
    lines.append("")
    
    # Buffett 建議：根據穿透數字動態生成
    lines.append("【Buffett 視角建議】")
    lines.append(f"🧓 巴菲特式思考（規範：整體資產配置，非個股評論）")
    lines.append(f"場景判定：台股重挫 {twii}%，穿透部位失衡，啟動減碼防禦")
    lines.append(f"• 淨資產：{net:,} TWD")
    

    # Extract market context for scenario-aware advice
    twii = intel.get("TAIEX", {}).get("1_week_change_pct", "N/A") if intel else "N/A"
    soxx = intel.get("SOXX", {}).get("1_week_change_pct", "N/A") if intel else "N/A"
    foreign = intel.get("foreign_flow", {}).get("7d_net", "N/A") if intel else "N/A"

    # 1. 成長部位（穿透驅動，情境感知）
    if drift_growth > 10:
        lines.append(f"• 成長型部位超標 +{drift_growth:.1f}pp（實際 {actual_growth_pct:.1f}% vs 目標 {target_growth:.0f}%）")
        if not _has_snapshot:
            lines.append("  （snapshot 穿透未讀取，建議手動確認台股/美股比例後再決策）")
        else:
            # 以情境為主，避免暴跌時追跌賣出
            twii_num = float(str(twii).replace(",","")) if twii != "N/A" else None
            if twii_num is not None and twii_num <= -3:
                lines.append(f"  台股單週暴跌 {twii_num:.1f}%，此時不追跌賣出權益；等反彈確認後再減碼超標部位")
            elif twii_num is not None and twii != "N/A" and twii >= 2:
                lines.append(f"  台股反彈 +{twii_num:.1f}%，可分批減碼超標部位")
            else:
                # 震盪：指出實際過重部位
                if _us_pct > 0.35 and _tw_pct > 0.15:
                    lines.append(f"  台股 {_tw_pct*100:.1f}%、美股 {_us_pct*100:.1f}%，雙邊偏重；建議先減碼超標幅度較大的一方")
                elif _us_pct > 0.35:
                    lines.append(f"  美股佔比 {_us_pct*100:.1f}% 偏高，建議優先減碼美股科技型 ETF（00646/009824/009823）")
                elif _tw_pct > 0.20:
                    lines.append(f"  台股佔比 {_tw_pct*100:.1f}% 偏高，建議優先減碼台股集中部位（0050/009816）")
                else:
                    lines.append(f"  建議減碼整體權益部位，預計減碼 {us_growth_twd + tw_growth_twd - target_growth/100*(_invest_total+1):,.0f} TWD")
    elif drift_growth < -10:
        lines.append(f"• 成長型部位低標 {drift_growth:.1f}pp（實際 {actual_growth_pct:.1f}% vs 目標 {target_growth:.0f}%），建議分批加碼台股/美股權值")
    else:
        lines.append(f"• 成長型部位 {actual_growth_pct:.1f}%，接近目標 {target_growth:.0f}%，維持現有配置")
    
    # 2. 台股/美股配置
    tw_pct = tw_growth_twd / denom * 100 if denom > 0 else 0
    us_pct = us_growth_twd / denom * 100 if denom > 0 else 0
    lines.append(f"• 台股市值型成長 {tw_pct:.1f}%，美股 {us_pct:.1f}%")
    if tw_pct > 15 and us_pct > 40:
        lines.append("  台股/美股雙高，避免過度集中，優先分散至防禦型配息與債券部位")
    elif tw_pct > 20:
        lines.append("  台股權重偏高，注意單一市場曝險")
    elif us_pct > 40:
        lines.append("  美股權重偏高，注意美國科技股季節性回檔風險")
    else:
        lines.append("  台股/美股權重在可控範圍")
    
    # 3. 防禦部位
    if actual_defense_pct < target_defense - 10:
        lines.append(f"• 防禦部位不足 {actual_defense_pct:.1f}%（目標 {target_defense:.0f}%），建議增加 00878/00713/0056")
    else:
        lines.append(f"• 防禦部位 {actual_defense_pct:.1f}%，接近目標 {target_defense:.0f}%，維持配息型 holdings")
    
    # 4. 安全網
    if actual_safety_pct < target_safety - 5:
        lines.append(f"• 安全網不足 {actual_safety_pct:.1f}%（目標 {target_safety:.0f}%），建議補充高利活存/短債")
    else:
        lines.append(f"• 安全網 {actual_safety_pct:.1f}%，充足")
    
    # 5. 配息品質
    lines.append(f"• 本月配息 {passive_income:,} TWD 為退休現金流基石，不宜隨便解約")
    lines.append("")

    # CTO 建議：根據技術面動態生成
    lines.append("【CTO 技術視角】")
    lines.append("今日最大風險：")
    
    if abs(twii) >= 10:
        lines.append(f"1. 台股單週 {twii}%，{'大跌' if twii < 0 else '大漲'}已觸發機會子彈門檻")
    else:
        lines.append(f"1. 台股單週 {twii}%，距離機會子彈觸發線 ±10% 還有 {max(0, 10-abs(twii)):.1f}pp 空間")
    
    lines.append(f"2. 0050 內建台積電 57%，單一公司曝險過高，009816 約 42%")
    
    if us_pct > 45:
        lines.append(f"3. 美股超標 {us_pct:.1f}%（46.1% vs 40%），009824 科技巨頭比 00646 S&P500 更集中")
    else:
        lines.append(f"3. 美股曝險 {us_pct:.1f}%，{('美股權重偏高，注意美國科技股季節性回檔風險' if us_pct > 40 else '00646 S&P500 分散度優於 009824')}")
    
    lines.append("4. 配息SOP：安聯收益成長已配息入帳，屬正常除息")
    lines.append("5. PIMCO 已轉出，M&G 尚未入帳，待追蹤")
    lines.append("")
    lines.append("建議動作：")
    
    if drift_growth > 10:
        if not _has_snapshot:
            lines.append("1. 成長部位超標，建議減碼超標權益部位（advice pending snapshot）")
        elif twii_num is not None and twii != "N/A" and twii <= -3:
            lines.append(f"1. 成長部位超標，但台股暴跌中，不追跌賣出；等反彈後再減碼")
        elif _us_pct > 0.35 and _tw_pct > 0.15:
            lines.append("1. 台股/美股雙高，優先減碼超標幅度大的一方，避免一刀斬美股")
        elif _us_pct > 0.35:
            lines.append(f"1. 美股權重 {_us_pct*100:.1f}% 偏高，建議優先減碼科技型 ETF（00646/009824/009823）")
        elif _tw_pct > 0.20:
            lines.append(f"1. 台股權重 {_tw_pct*100:.1f}% 偏高，建議優先減碼台股集中部位（0050/009816）")
        else:
            lines.append(f"1. 成長部位超標，建議減碼整體權益 {drift_growth:.1f}pp")
    elif drift_growth < -10:
        lines.append(f"1. 成長部位低標，分批加碼台股/美股權值，目前低標 {abs(drift_growth):.1f}pp")
    else:
        lines.append("1. 成長部位接近目標，维持現有配置")
    
    if tw_pct < 15:
        lines.append(f"2. 台股僅 {tw_pct:.1f}%，補碼至目標 40%：0050/009816/00981A")
    else:
        lines.append(f"2. 台股 {tw_pct:.1f}%，維持分散配置，避免集中台積電")
    
    if actual_defense_pct < target_defense - 10:
        deficit = target_defense - actual_defense_pct
        lines.append(f"3. 防禦部位補足，預計增加 {deficit:.1f}pp：00878/00713/0056 + 安聯保單配息")
    else:
        lines.append("3. 防禦部位充足，維持配息型 holdings")
    
    if actual_safety_pct < target_safety - 5:
        lines.append(f"4. 安全網補充至 {target_safety:.0f}%：高利活存/短債")
    else:
        lines.append("4. 安全網充足，保留高利活存作為機會子彈資金")
    
    lines.append(f"5. 機會子彈監控：單週 ±10% 觸發，目前 {twii}%")
    lines.append("")
    lines.append("【機會子彈戰術】")
    lines.append("Trigger：單週漲跌幅 >= 10%（大漲或大跌都觸發）")
    lines.append("Deploy：大跌後第1週進30%、第2週進70%（追反彈）")
    lines.append("Take profit：+8-12% 或 30天未反彈則撤離")
    lines.append("Upper bound：機會子彈動用 ≤ 20% 安全網部位")
    lines.append(f"今天狀態：台股單週 {twii}%，{'🔴 已觸發！' if abs(twii) >= 10 else '距離觸發線-10%還有空間，持續監控'}")

    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[WARN] TG_TOKEN/TG_CHAT_ID not set")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=30)
        data = r.json()
        if not data.get("ok"):
            print(f"[WARN] Telegram send failed: {data}")
            return False
        return True
    except Exception as exc:
        print(f"[WARN] Telegram send exception: {exc}")
        return False


def run(send: bool = True) -> bool:
    snapshot = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    intel = load_market_intel()
    pen = penetration_analysis(snapshot)
    report = generate_report(pen, intel, snapshot)
    out = BASE / f"buffett_cto_report_{TODAY}.md"
    out.write_text(report, encoding="utf-8")
    print(f"[OK] Report saved to {out.name}")
    if send:
        sent = send_telegram(report)
        if sent:
            print("[OK] Telegram sent")
        return sent
    return True


if __name__ == "__main__":
    ok = run(send=True)
    raise SystemExit(0 if ok else 1)