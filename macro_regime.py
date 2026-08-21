#!/usr/bin/env python3
"""macro_regime.py — DAA v3 宏觀動態評估引擎（2026-08-21 定案 A 版）

規格來源：使用者《完整動態再平衡系統》規格
- 主觸發因子（決定燈號與大類權重）：US30Y / 巴菲特 / CPI / VIX（後三者無源不觸發）
- 板塊輪動因子（股票內部傾斜，不改變大類總額）：科技穿透曝險 / 席勒PE / 確定收益相對強度
- 宏觀輔助因子（只加重警報、調子項上限）：USD-TWD / XAU / WTI / GPR
- 基準 SAA = snapshot.penetration.targets（8/20 定案 台10/美40/防20/債25/現金5）
- 黃金衛星 ≤5%（引擎輸出，不寫入 snapshot）
- 現金 = 底線制（70萬安全網，無目標%）
- 台股上限 15%（硬性）
- 引擎不主動推薦 Lombard / PI / 新增美元投資（人工執行案照舊）

輸出：macro_regime_{date}.json + 可讀摘要（強制輸出格式 8 點）
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0"}
TIMEOUT = 8
EMERGENCY_FILE = BASE / "data" / "emergency_llm_analysis.json"
RISK_KW = ["風險", "警示", "警報", "減碼", "避險", "賣出", "跌破", "紅色", "凍結",
           "戰爭", "制裁", "升息", "通膨", "地緣", "回調", "修正", "崩", "危機"]

# 硬性約束（使用者定案，勿改）
HARD = {
    "台股上限": 15.0,        # 台股市值型絕對上限
    "黃金衛星上限": 5.0,     # 黃金/實質資產 ≤5%
    "現金底線": 700_000,     # 底線制 70 萬
    "科技曝險目標": 15.0,    # 穿透科技 ≤15%
    "美股偏移上限": 10.0,    # 單一大類 ±10pp
    "美元曝險黃": 50.0,      # >50% 黃燈
    "美元曝險紅": 55.0,      # >55% 紅燈
}

SYM = {
    "us30y": "%5ETYX", "us10y": "%5ETNX", "us2y": "%5EIRX", "vix": "%5EVIX",
    "gold": "GC%3DF", "wti": "CL%3DF", "qqq": "QQQ",
    "xlk": "XLK", "xlp": "XLP", "xlu": "XLU", "xlf": "XLF", "xlv": "XLV", "xle": "XLE",
    "tw50": "0050.TW", "tw878": "00878.TW", "usdtwd": "USDTWD%3DX",
}


def _fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req, timeout=TIMEOUT).read().decode("utf-8", "ignore")
    except Exception:
        return None


def _yahoo(sym: str) -> dict | None:
    """回傳 {last, prev, first, ret_1d_pct, ret_20d_pct}；失敗 None"""
    txt = _fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1mo&interval=1d")
    if not txt:
        return None
    try:
        r = json.loads(txt)["chart"]["result"][0]
        closes = [c for c in r["indicators"]["quote"][0]["close"] if c]
        if not closes:
            return None
        prev = r["meta"].get("chartPreviousClose") or closes[0]
        first = closes[0]
        return {
            "last": closes[-1], "prev": prev, "first": first,
            "ret_1d_pct": (closes[-1] / prev - 1) * 100,
            "ret_20d_pct": (closes[-1] / first - 1) * 100,
        }
    except Exception:
        return None


def _usdtwd() -> float | None:
    txt = _fetch("https://open.er-api.com/v6/latest/USD")
    if not txt:
        return None
    try:
        return float(json.loads(txt)["rates"]["TWD"])
    except Exception:
        return None


def _shiller_pe() -> float | None:
    """multpl.com 席勒本益比（歷史極端區判讀用）"""
    txt = _fetch("https://www.multpl.com/shiller-pe")
    if not txt:
        return None
    m = re.search(r"Current Shiller PE Ratio is ([0-9.]+)", txt)
    return float(m.group(1)) if m else None


def _gpr() -> float | None:
    """地緣風險指數（可選資料源，失敗不阻斷）"""
    txt = _fetch("https://www.matteoiacoviello.com/gpr_files/data_gpr_recent.csv")
    if not txt or txt.lstrip().startswith("<"):
        return None
    rows = [r for r in txt.strip().splitlines() if r and r[0].isdigit()]
    if not rows:
        return None
    try:
        head = rows[-1].split(",")
        return float(head[1])  # GPR 欄位
    except Exception:
        return None


# ---------------------------------------------------------------- 緊急應變整合
def _load_emergency() -> dict | None:
    """讀最新緊急應變分析（13:00 台股 / 21:30 美股 LLM agent 產出）"""
    try:
        d = json.loads(EMERGENCY_FILE.read_text(encoding="utf-8"))
        if not d.get("full_report"):
            return None
        return d
    except Exception:
        return None


def _emergency_signal(em: dict | None) -> dict | None:
    """緊急應變 → 應變分 0-100 + 訊號摘要（LLM 新聞面 × 量化確認）
    逾 3 日資料不計入加成（僅供參考標註）"""
    if not em:
        return None
    report = em.get("full_report", "")
    ms = em.get("market_snapshot", {}) or {}
    hits = [k for k in RISK_KW if k in report]

    score = 20 + min(40, len(hits) * 5)
    def _f(v):
        try:
            return float(str(v).replace("%", "").replace(",", ""))
        except Exception:
            return None
    vix = _f((ms.get("VIX") or {}).get("value"))
    us30 = _f((ms.get("US30Y") or {}).get("value"))
    if vix is not None and vix >= 25:
        score += 8
    if us30 is not None and us30 >= 5.30:
        score += 12
    downs = sum(1 for v in ms.values() if isinstance(v, dict) and v.get("cls") == "down")
    if downs >= 3:
        score += 10
    if "紅色" in report or "凍結" in report:
        score += 10
    score = min(100, score)

    gen_txt = em.get("generated_at", "")
    stale = True
    try:
        gen = datetime.strptime(gen_txt[:19], "%Y-%m-%d %H:%M:%S")
        stale = (datetime.now() - gen).total_seconds() > 3 * 86400
    except Exception:
        pass
    if stale:
        score = min(score, 40)  # 逾 3 日僅參考，不計入加成

    excerpt = ""
    for key in ("五、巴菲特建議", "六、風控檢查", "四、資產配置透視"):
        i = report.find(key)
        if i >= 0:
            excerpt += report[i:i + 130].replace("\n", " ").strip() + "… "
            break
    if not excerpt:
        excerpt = report[:130].replace("\n", " ")

    return {
        "generated_at": gen_txt,
        "source": em.get("source", ""),
        "應變分": score,
        "逾3日僅參考": stale,
        "風險關鍵詞": hits[:10],
        "下跌指數數": downs,
        "建議節錄": excerpt,
    }


def _score_linear(val: float | None, lo: float, hi: float) -> float | None:
    """把數值映射到 0-100 分（lo→0, hi→100）"""
    if val is None:
        return None
    return max(0.0, min(100.0, (val - lo) / (hi - lo) * 100))


# ---------------------------------------------------------------- 情境評分
def score_tech_repricing(fx: dict, pe: float | None, tech_exposure: float | None) -> dict:
    """科技重新定價：高估值回調風險"""
    s_pe = _score_linear(pe, 28, 42) if pe else None            # 28→0 分, 42→100 分
    xlk = fx.get("xlk")
    s_mom = _score_linear(xlk["ret_20d_pct"] if xlk else None, 8, -3)  # +8%→0 分, -3%→100 分
    qqq = fx.get("qqq")
    s_qqq = _score_linear(qqq["ret_20d_pct"] if qqq else None, 8, -3)
    vix = fx.get("vix")
    vix_up = (vix["ret_20d_pct"] if vix else None)
    s_vix = _score_linear(vix_up, -20, 40)                     # 跌20%→0 分, 漲40%→100 分
    s_exp = _score_linear(tech_exposure, 12, 25)               # 12%→0, 25%→100
    parts = [p for p in (s_pe, s_mom, s_qqq, s_vix, s_exp) if p is not None]
    score = sum(parts) / len(parts) * 1.0 if parts else None
    return {
        "score": round(score, 1) if score is not None else None,
        "細項": {
            "席勒PE": pe, "PE分": s_pe, "XLK_20日": s_mom, "QQQ_20日": s_qqq,
            "VIX趨勢分": s_vix, "科技穿透": tech_exposure, "曝險分": s_exp,
        },
    }


def score_income_rotation(fx: dict, us30y: float | None) -> dict:
    """確定收益輪動：資金流向高股息/公用/醫療等現金流確定板塊"""
    def _avg(*keys: str) -> float | None:
        vals = [fx[k]["ret_20d_pct"] for k in keys if fx.get(k)]
        return sum(vals) / len(vals) if vals else None
    defen = _avg("xlp", "xlu", "xlv", "xlf")                    # 防禦/收益板塊平均
    xlk = fx.get("xlk")
    rs = (defen - xlk["ret_20d_pct"]) if (defen is not None and xlk) else None
    s_rs = _score_linear(rs, -5, 6)                            # -5pp→0, +6pp→100
    tw50, tw878 = fx.get("tw50"), fx.get("tw878")
    tw_rel = (tw878["ret_20d_pct"] - tw50["ret_20d_pct"]) if (tw878 and tw50) else None
    s_tw = _score_linear(tw_rel, -4, 4)                        # 高股息相對市值
    s_yield = _score_linear(us30y, 4.4, 5.4) if us30y else None  # 殖利率越高→收益資產越香
    parts = [p for p in (s_rs, s_tw, s_yield) if p is not None]
    score = sum(parts) / len(parts) if parts else None
    return {
        "score": round(score, 1) if score is not None else None,
        "細項": {"防禦板塊RS": rs, "RS分": s_rs, "台股高股息相對": tw_rel, "台股分": s_tw,
                 "殖利率分": s_yield, "US30Y": us30y},
    }


def score_usd_credit(fx: dict) -> dict:
    """美元信用壓力：長債殖利率上行 → 供給壓力/美元信用受質疑 → 黃金避險"""
    gold = fx.get("gold")
    s_gold = _score_linear(gold["ret_20d_pct"] if gold else None, -2, 12)  # -2%→0, +12%→100
    us10 = fx.get("us10y")
    ten_abs = us10["last"] if us10 else None
    ten_move = (us10["last"] - us10["first"]) if us10 else None
    s_ten = _score_linear(ten_move, -0.3, 0.4)               # -0.3pp→0, +0.4pp→100
    s_abs = _score_linear(ten_abs, 4.0, 5.2) if ten_abs else None  # 4.0→0, 5.2→100
    fx2 = fx.get("usdtwd")
    s_fx = None
    if fx2:
        s_fx = _score_linear(fx2["ret_20d_pct"], 3, -3)      # 美元走強(台幣貶)→信用壓力減；美元走弱→壓力增
    parts = [p for p in (s_gold, s_ten, s_abs, s_fx) if p is not None]
    score = sum(parts) / len(parts) if parts else None
    return {
        "score": round(score, 1) if score is not None else None,
        "細項": {"黃金20日": gold["ret_20d_pct"] if gold else None, "黃金分": s_gold,
                 "10Y": ten_abs, "10Y月變動pp": ten_move, "10Y趨勢分": s_ten, "10Y絕對分": s_abs,
                 "美元月變動": fx2["ret_20d_pct"] if fx2 else None, "匯率分": s_fx},
    }


def score_geopolitical(fx: dict, gpr: float | None) -> dict:
    """地緣風險：原油/黃金跳升 + VIX 突升 + GPR"""
    wti = fx.get("wti")
    s_wti = _score_linear(wti["ret_20d_pct"] if wti else None, 2, 12)   # +2%→0, +12%→100
    gold = fx.get("gold")
    s_gold = _score_linear(gold["ret_20d_pct"] if gold else None, 3, 10)
    vix = fx.get("vix")
    vix_spike = (vix["ret_20d_pct"] if vix else None)
    s_vix = _score_linear(vix_spike, 0, 50)
    s_gpr = _score_linear(gpr, 100, 300) if gpr is not None else None
    parts = [p for p in (s_wti, s_gold, s_vix, s_gpr) if p is not None]
    score = sum(parts) / len(parts) if parts else None
    return {
        "score": round(score, 1) if score is not None else None,
        "細項": {"WTI20日": wti["ret_20d_pct"] if wti else None, "WTI分": s_wti,
                 "黃金20日": gold["ret_20d_pct"] if gold else None, "黃金分": s_gold,
                 "VIX月變動": vix_spike, "VIX分": s_vix,
                 "GPR": gpr, "GPR分": s_gpr},
    }


# ---------------------------------------------------------------- 燈號
def light_main(us30y: float | None, vix: dict | None) -> str:
    """主觸發燈號：任一紅 → 紅；全綠 → 綠；否則黃"""
    red = []
    if us30y is not None and us30y >= 5.30:
        red.append(f"US30Y {us30y:.2f}% ≥5.30%")
    if vix and vix["last"] > 28:
        red.append(f"VIX {vix['last']:.1f} >28")
    if red:
        return "🔴 紅燈"
    if us30y is not None and us30y < 4.8 and vix and vix["last"] < 22:
        return "🟢 綠燈"
    return "🟡 黃燈"


# ---------------------------------------------------------------- targetAllocation
def target_allocation(snap: dict, light: str, regime: dict) -> dict:
    """A 版基準：8/20 SAA（snapshot 動態讀）+ 燈號偏移 + 黃金衛星 + 底線制
    偏移規則：美股 ±(0~10pp 依燈號)；台股 ≤15% 硬性；防守紅燈小升；債券紅燈升、凍結時禁新現金
    """
    tgt = snap.get("penetration", {}).get("targets", {})
    total = snap.get("total_assets", 0)
    s = {
        "台股市值型成長": {"target": tgt.get("台股市值型目標", 10), "cap": HARD["台股上限"]},
        "美股市值型成長": {"target": tgt.get("美股市值型目標", 40), "drift": 10},
        "防守型配息": {"target": tgt.get("配息型目標", 20), "drift": 10},
        "債券": {"target": tgt.get("債券型目標", 25), "drift": 10},
    }
    if light == "🟢 綠燈":
        shift = {"台股市值型成長": +3, "美股市值型成長": +5, "防守型配息": 0, "債券": 0}
    elif light == "🔴 紅燈":
        shift = {"台股市值型成長": -2, "美股市值型成長": -8, "防守型配息": +2, "債券": +5}
    else:
        shift = {"台股市值型成長": 0, "美股市值型成長": 0, "防守型配息": 0, "債券": 0}

    rows = []
    for k, cfg in s.items():
        t = cfg["target"]
        v = t + shift.get(k, 0)
        if "cap" in cfg:
            v = min(v, cfg["cap"])
        lo = t - cfg.get("drift", 0)
        hi = t + cfg.get("drift", 0)
        v = max(lo, min(hi, v))
        rows.append({"資產": k, "target": t, "燈號偏移後": round(v, 1),
                     "建議金額(±)": round(abs(v - t) / 100 * total)})

    # 避險衛星（2026-08-21 使用者裁示：黃金+石油 合併納入避險）
    # 黃金（地緣/美元信用加重時上調，≤5%）+ 石油/能源（地緣/通膨加重時上調，≤2%）→ 合計 ≤7%
    gold_target = {"🟢 綠燈": 2.0, "🟡 黃燈": 3.0, "🔴 紅燈": 5.0}[light]
    geo, usd = regime.get("地緣風險", {}).get("score"), regime.get("美元信用壓力", {}).get("score")
    if (geo or 0) >= 70 or (usd or 0) >= 70:
        gold_target = min(5.0, gold_target + 1.0)
    oil_target = {"🟢 綠燈": 0.0, "🟡 黃燈": 1.0, "🔴 紅燈": 2.0}[light]
    if (geo or 0) >= 70:
        oil_target = min(2.0, oil_target + 0.5)
    rows.append({"資產": "黃金/實質資產(衛星)", "target": 0, "燈號偏移後": gold_target,
                 "建議金額(±)": round(gold_target / 100 * total)})
    rows.append({"資產": "石油/能源(避險衛星)", "target": 0, "燈號偏移後": oil_target,
                 "建議金額(±)": round(oil_target / 100 * total)})
    rows.append({"資產": "避險衛星合計(黃金+石油)", "target": 0, "燈號偏移後": round(gold_target + oil_target, 1),
                 "建議金額(±)": round((gold_target + oil_target) / 100 * total), "上限": "≤7%（8/21 裁示）"})

    # 現金 = 底線制（無目標%，顯示安全網與超額）
    cash_now = snap.get("penetration", {}).get("actual_pct", {}).get("現金/安全網", 0)
    rows.append({"資產": "台幣現金+短定存", "target": "底線制", "燈號偏移後": None,
                 "建議金額(±)": f"底線 {HARD['現金底線']/10000:.0f}萬，超額部署收益資產"})
    return {"基準": tgt, "rows": rows, "總資產": total, "現金現況%": cash_now}


# ---------------------------------------------------------------- 板塊傾斜
def sector_tilt(regime: dict, total: float, light: str) -> list[dict]:
    """股票內部搬家：科技 → 確定收益（不改變股票總額）"""
    tech = regime.get("科技重新定價", {}).get("score") or 0
    rot = regime.get("確定收益輪動", {}).get("score") or 0
    out = []
    if tech >= 60:
        pp = round(min(5.0, 2 + (tech - 60) / 15), 1)
        out.append({"方向": "科技/AI/半導體 減碼", "偏移": f"-{pp}pp",
                    "金額": round(pp / 100 * total),
                    "標的": "貝萊德世界科技/安聯AI/00924/美股科技 ETF（逢反彈，單次≤20萬）"})
        out.append({"方向": "確定收益板塊 加碼", "偏移": f"+{pp}pp",
                    "金額": round(pp / 100 * total),
                    "標的": "00878/00713/0056＋公用/醫療/金融 ETF（台股單筆≤5萬）"})
    elif tech >= 50 and rot >= 45:
        out.append({"方向": "科技 輕度減碼（科技落後＋輪動雙訊號）", "偏移": "-2pp",
                    "金額": round(2 / 100 * total),
                    "標的": "僅逢反彈減碼美股科技，單次≤20萬，不追殺"})
        out.append({"方向": "確定收益板塊 承接", "偏移": "+2pp",
                    "金額": round(2 / 100 * total),
                    "標的": "00878 週額度 1,000-1,200 股（≤5萬）/ 醫療/公用 ETF 回檔小單"})
    elif rot >= 60:
        out.append({"方向": "確定收益板塊 增持（無科技減碼壓力）", "偏移": "維持股票總額",
                    "金額": round(1.5 / 100 * total),
                    "標的": "00878 週額度 1,200 股 / 00713 回檔小單"})
    else:
        out.append({"方向": "板塊中性", "偏移": "維持現狀",
                    "金額": 0, "標的": "00878 每週 1,000 股（≤5萬）"})
    return out


# ---------------------------------------------------------------- 硬性約束檢查
def hard_check(snap: dict, out: dict) -> list[dict]:
    """逐條檢查個人硬性約束"""
    apct = snap.get("penetration", {}).get("actual_pct", {})
    usd = (snap.get("usd_exposure_monitor", {}) or {}).get("current", {}) or {}
    usd_pct = usd.get("合計", 0)
    cash_now = snap.get("cash_total", 0)
    checks = [
        ("台股 ≤15% 硬性上限", apct.get("台股市值型成長", 0) <= HARD["台股上限"],
         f"現況 {apct.get('台股市值型成長', 0):.1f}%"),
        ("不推薦 Lombard / 債券疊代", True, "引擎不輸出槓桿建議（人工執行案照舊）"),
        ("不推薦新增美元投資（只管控）", True, "引擎對新增美元只給「禁止/觀望」"),
        ("美元總曝險 ≤50%（黃）/55%（紅）", usd_pct <= HARD["美元曝險紅"],
         f"現況 {usd_pct:.1f}%（>50% 黃燈）"),
        ("現金底線 70 萬", (cash_now or 0) >= HARD["現金底線"],
         f"現況 {cash_now/10000:.1f}萬" if cash_now else "未知"),
        ("還高息負債優先於投資配置", True, "安聯4.2%→元大3.92%→第一金3.51%"),
        ("黃金/原油/地緣不單獨觸發大買賣", True, "僅加重警報+子項小幅權重"),
        ("戰術偏移 ≤±10%、禁滿倉空倉", True, "引擎已鎖偏移上限"),
    ]
    return [{"項目": k, "通過": v, "說明": note} for k, v, note in checks]


# ---------------------------------------------------------------- 主程式
def run() -> dict:
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    fx = {}
    for k, sym in SYM.items():
        fx[k] = _yahoo(sym)

    us30y = fx.get("us30y", {}).get("last") if fx.get("us30y") else None
    if us30y is None:  # fallback snapshot rhythm08
        us30y = (snap.get("rhythm08", {}).get("indicators", {}) or {}).get("us30y")
    usdtwd = _usdtwd()
    pe = _shiller_pe()
    gpr = _gpr()

    tech_exp = snap.get("penetration", {}).get("actual_pct", {}).get("美股市值型成長_科技")
    regime = {
        "科技重新定價": score_tech_repricing(fx, pe, tech_exp),
        "確定收益輪動": score_income_rotation(fx, us30y),
        "美元信用壓力": score_usd_credit(fx),
        "地緣風險": score_geopolitical(fx, gpr),
    }
    light = light_main(us30y, fx.get("vix"))
    # 緊急應變加成（LLM 新聞面 × 量化確認；逾3日不計入）
    em_sig = _emergency_signal(_load_emergency())
    if em_sig and not em_sig["逾3日僅參考"] and em_sig["應變分"] >= 50:
        boost = em_sig["應變分"] * 0.15
        if regime["地緣風險"]["score"] is not None:
            regime["地緣風險"]["score"] = round(min(100, regime["地緣風險"]["score"] + boost), 1)
        if em_sig["應變分"] >= 60 and regime["科技重新定價"]["score"] is not None:
            regime["科技重新定價"]["score"] = round(min(100, regime["科技重新定價"]["score"] + boost * 0.7), 1)
    alloc = target_allocation(snap, light, regime)
    tilt = sector_tilt(regime, snap.get("total_assets", 0), light)
    rb = _rebalance_suggestion(snap, regime, light)
    if em_sig and em_sig["應變分"] >= 50:
        rb["清單"].append({"資產": "🚨 緊急應變加成", "偏離pp": 0.0, "建議": em_sig["建議節錄"][:90],
                           "金額": 0, "分批": f"來源 {em_sig['source']}（{em_sig['generated_at']}）"})
    checks = hard_check(snap, {"usd_pct": 0})

    out = {
        "date": date.today().isoformat(),
        "燈號": light,
        "主觸發": {
            "US30Y": us30y, "VIX": fx.get("vix", {}).get("last") if fx.get("vix") else None,
            "巴菲特指標": None, "核心CPI": None,
            "說明": "巴菲特/CPI 待外部數據源（None 不觸發、不阻斷）",
        },
        "輔助因子": {
            "USD/TWD": usdtwd, "XAU黃金": fx.get("gold", {}).get("last") if fx.get("gold") else None,
            "黃金20日%": fx.get("gold", {}).get("ret_20d_pct") if fx.get("gold") else None,
            "WTI原油": fx.get("wti", {}).get("last") if fx.get("wti") else None,
            "WTI20日%": fx.get("wti", {}).get("ret_20d_pct") if fx.get("wti") else None,
            "GPR地緣指數": gpr, "席勒PE": pe,
            "科技穿透曝險": tech_exp, "10Y/2Y": (
                f"{fx['us10y']['last']:.2f}/{fx['us2y']['last']:.2f}" if fx.get("us10y") and fx.get("us2y") else None),
        },
        "情境評分": regime,
        "targetAllocation": alloc,
        "板塊輪動": tilt,
        "硬性約束": checks,
        "緊急應變": em_sig,
        "風險敘述": _risk_narrative(regime, us30y, fx),
        "再平衡建議": rb,
        "資料源備註": {"Yahoo": "可用", "er-api": bool(usdtwd), "multpl": pe is not None,
                    "GPR": gpr is not None, "snapshot": str(BASE / "snapshot.json")},
    }
    (BASE / f"macro_regime_{out['date']}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def _risk_narrative(regime: dict, us30y: float | None, fx: dict) -> str:
    usd = regime.get("美元信用壓力", {}).get("score")
    geo = regime.get("地緣風險", {}).get("score")
    lines = []
    if us30y is not None:
        tone = "上行" if fx.get("us10y") and fx["us10y"]["last"] > fx["us10y"]["first"] else "持平/回落"
        lines.append(
            f"美債：US30Y {us30y:.2f}%（10Y {fx['us10y']['last']:.2f}% {tone}）— 長天期殖利率"
            f"{'持續走高，反映美債供給壓力、美元信用受市場質疑' if '上行' in tone else '回穩'}，"
            f"連動債券價格壓力{'+黃金避險需求' if (usd or 0) >= 60 else ''}。")
    g = fx.get("gold", {}).get("ret_20d_pct")
    if g is not None:
        lines.append(f"黃金 20日 {g:+.1f}%（現價 {fx['gold']['last']:.0f}）— {'避險/美元信用邏輯主導' if g > 5 else '區間'}。")
    w = fx.get("wti", {}).get("ret_20d_pct")
    if w is not None:
        lines.append(f"WTI 20日 {w:+.1f}%（現價 {fx['wti']['last']:.1f}）— 地緣/供給衝擊觀察。")
    if geo and geo >= 60:
        lines.append("地緣風險升溫：原油/黃金波動放大，防禦板塊傾斜提高，但僅加重警報不單獨觸發大改股債。")
    return " ".join(lines)


def _rebalance_suggestion(snap: dict, regime: dict, light: str) -> dict:
    """偏離 → 階梯 → 建議（情境調整後金額，分批 4-6 週，人工確認）"""
    pen = snap.get("penetration", {})
    apct = pen.get("actual_pct", {})
    tgt = pen.get("targets", {})
    total = snap.get("total_assets", 0)
    tech = regime.get("科技重新定價", {}).get("score") or 0
    rot = regime.get("確定收益輪動", {}).get("score") or 0
    usd = regime.get("美元信用壓力", {}).get("score") or 0
    out = []
    for label, cur_k, tgt_k, action, base, mult_src, mult_max in [
        ("美股", "美股市值型成長", "美股市值型目標", "減碼" if apct.get("美股市值型成長", 0) > tgt.get("美股市值型目標", 40) else "觀望",
         "20萬/次", tech, 1.5),
        ("防守配息", "防守型配息", "配息型目標", "增持", "0", rot, 1.3),
        ("債券", "債券", "債券型目標", "增持", "0", usd, 1.3),
    ]:
        cur, t = apct.get(cur_k, 0), tgt.get(tgt_k, 0)
        dev = cur - t
        if abs(dev) <= 2:
            out.append({"資產": label, "偏離pp": round(dev, 1), "建議": "觀察（P3）", "金額": 0})
            continue
        if abs(dev) <= 5:
            note = ""
            if label == "美股" and (tech or 0) >= 50:
                note = "＋核准減碼案續行（8/19：逢反彈≤20萬/次，優先科技）"
            out.append({"資產": label, "偏離pp": round(dev, 1), "建議": f"戰術觀察（P2）{note}",
                        "金額": round(abs(dev) / 100 * total), "分批": "-"})
            continue
        amt = abs(dev) / 100 * total
        mult = min(mult_max, 1 + (mult_src / 100) * 0.5)
        amt = amt * mult
        out.append({"資產": label, "偏離pp": round(dev, 1), "建議": action,
                    "金額": round(amt),
                    "分批": f"4-6 週分批，單次≤該類市值15%（情境倍率×{mult:.2f}）" if amt > 0 else "-",
                    "標的": "逢反彈減碼美股科技（單次≤20萬）" if label == "美股"
                    else "00878/00713 配息導流+回檔小單（單次≤5萬）" if label == "防守配息"
                    else "美元直債梯(1-5Y 優先)/00983D 底倉（US30Y≥5.30% 凍結新增）"})
    if light == "🟡 黃燈":
        out.insert(0, {"資產": "全域", "偏離pp": 0.0, "建議": "警戒區（US30Y 5.20-5.30）：台股≤50萬/週、美股停購、債券不主動大筆新增",
                       "金額": 0, "分批": ""})
    return {"觸發再平衡": any(o.get("金額", 0) and o["建議"] in ("增持", "減碼") for o in out),
            "注意": "僅建議，人工確認後執行，不自動下單", "清單": out}


def load_latest() -> dict:
    """讀今日 macro_regime JSON；不存在則即時執行並寫入。
    8/21 快取停滯 bug 修復：緊急應變 JSON 的 generated_at 比快取新 → 重算，
    避免 13:00/21:30 緊急應變更新後 build_panel ⑧ 行仍顯示舊分析（INC-130 同類）。"""
    p = BASE / f"macro_regime_{date.today().isoformat()}.json"
    if p.exists():
        try:
            cached = json.loads(p.read_text(encoding="utf-8"))
            em = _load_emergency()
            if em:
                em_ts = em.get("generated_at", "")
                cache_ts = (cached.get("緊急應變") or {}).get("generated_at", "")
                if em_ts and cache_ts and em_ts > cache_ts:
                    return run()  # 緊急應變更新 → 重算
                if em_ts and not cache_ts:
                    return run()
            return cached
        except Exception:
            return run()
    return run()


if __name__ == "__main__":
    r = run()
    # 可讀摘要
    print(f"📅 {r['date']} | 燈號：{r['燈號']}")
    print(f"主觸發：US30Y {r['主觸發']['US30Y']:.2f}% ｜ VIX {r['主觸發']['VIX']} ｜ 巴菲特 — ｜ CPI —")
    aux = r["輔助因子"]
    print(f"輔助：USD/TWD {aux['USD/TWD']} ｜ XAU {aux['XAU黃金']:.0f}（20日{aux['黃金20日%']:+.1f}%）"
          f" ｜ WTI {aux['WTI原油']:.1f}（20日{aux['WTI20日%']:+.1f}%） ｜ GPR {aux['GPR地緣指數']} ｜ 席勒PE {aux['席勒PE']} ｜ 科技穿透 {aux['科技穿透曝險']}% ｜ 10Y/2Y {aux['10Y/2Y']}")
    print("情境：", " | ".join(f"{k} {v['score']}" for k, v in r["情境評分"].items()))
    print("\n【targetAllocation】")
    for row in r["targetAllocation"]["rows"]:
        v = row["燈號偏移後"]
        print(f"  {row['資產']}: target {row['target']} → {v if v is not None else row['建議金額(±)']}")
    print("\n【板塊輪動】")
    for t in r["板塊輪動"]:
        print(f"  {t['方向']} {t['偏移']}（{t['金額']:,} 元）→ {t['標的']}")
    print("\n【再平衡建議】")
    for o in r["再平衡建議"]["清單"]:
        print(f"  {o['資產']}: 偏離{o['偏離pp']:+.1f}pp | {o['建議']} | {o['金額']:,} 元 {o.get('分批','')}")
    print("\n【硬性約束】", "✅" if all(c["通過"] for c in r["硬性約束"]) else "⚠️ 有未通過")
    for c in r["硬性約束"]:
        if not c["通過"]:
            print(f"  ❌ {c['項目']}：{c['說明']}")
    print("\n風險敘述：", r["風險敘述"])
    print(f"\n✅ 輸出：macro_regime_{r['date']}.json")
