# -*- coding: utf-8 -*-
"""industry_penetration.py — GICS 11 大產業穿透引擎（Phase 1，2026-08-22）
將持倉（台股 ETF/個股 + 鉅亨基金 + 保單基金 + 第一金）依 GICS 11 產業拆解，
產出 industry_penetration 結構 + 分布圖（stacked bar），供再平衡儀表板/日報嵌入。

估算層級（資料誠實度）：
  L1 = 公開月報/說明書精確權重（如富達 股80.75/債14.03）
  L2 = 公開成分股權重（如 0050 台積電 ~50%）
  L3 = 指數基準產業權重（如 S&P500：科技 32%/金融 13%...）
  L4 = 名稱/類型推估（無公開資料時，依基金類型估算）
"""
import json
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()

for f in ["Microsoft YaHei", "Microsoft JhengHei", "Noto Sans CJK TC"]:
    try:
        font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [f]
        break
    except Exception:
        continue

# ── GICS 11 大產業（+ 固收/現金 合併列）──
GICS = ["資訊科技", "金融", "醫療保健", "核心消費", "非核心消費", "工業",
        "能源", "公用事業", "不動產", "通訊服務", "原物料"]
GICS_COLORS = {
    "資訊科技": "#3b82f6", "金融": "#22c55e", "醫療保健": "#f43f5e", "核心消費": "#f59e0b",
    "非核心消費": "#eab308", "工業": "#64748b", "能源": "#8b5cf6", "公用事業": "#14b8a6",
    "不動產": "#ec4899", "通訊服務": "#06b6d4", "原物料": "#a16207", "固收/現金": "#94a3b8",
}

# ── 台股 ETF 產業權重（L2：公開成分權重估算）──
_ETF_IND = {
    "0050": {"資訊科技": 0.8784, "金融": 0.082, "通訊服務": 0.0183, "原物料": 0.0117, "核心消費": 0.0037, "固收/現金": 0.0026, "工業": 0.0025, "公用事業": 0.0008, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "006208": {"資訊科技": 0.8784, "金融": 0.082, "通訊服務": 0.0183, "原物料": 0.0117, "核心消費": 0.0037, "固收/現金": 0.0026, "工業": 0.0025, "公用事業": 0.0008, "_src": "L2 MoneyDJ 成分產業（同 0050，2026/08 基準）"},
    "009816": {"資訊科技": 0.7275, "金融": 0.1971, "通訊服務": 0.026, "固收/現金": 0.0181, "原物料": 0.0129, "工業": 0.0085, "醫療保健": 0.0051, "核心消費": 0.0033, "能源": 0.0015, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00646": {"資訊科技": 0.3699, "金融": 0.1205, "通訊服務": 0.0933, "醫療保健": 0.091, "非核心消費": 0.0899, "工業": 0.082, "核心消費": 0.0441, "能源": 0.0339, "固收/現金": 0.0208, "公用事業": 0.0194, "原物料": 0.0178, "不動產": 0.0174, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00713": {"金融": 0.2559, "非核心消費": 0.1722, "資訊科技": 0.1619, "通訊服務": 0.1521, "核心消費": 0.1102, "工業": 0.0625, "原物料": 0.0315, "固收/現金": 0.0255, "其他": 0.0216, "公用事業": 0.0066, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00878": {"資訊科技": 0.4676, "金融": 0.3354, "通訊服務": 0.0708, "工業": 0.0603, "核心消費": 0.0246, "其他": 0.0223, "非核心消費": 0.019, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "0056": {"資訊科技": 0.4979, "金融": 0.2567, "原物料": 0.1015, "工業": 0.0506, "通訊服務": 0.0489, "核心消費": 0.0251, "固收/現金": 0.0158, "非核心消費": 0.0035, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00981A": {"資訊科技": 0.9511, "通訊服務": 0.0489, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00984A": {"資訊科技": 0.5908, "其他": 0.1532, "金融": 0.1512, "原物料": 0.0411, "醫療保健": 0.0357, "固收/現金": 0.028, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00919": {"金融": 0.5382, "資訊科技": 0.2959, "工業": 0.097, "非核心消費": 0.0277, "其他": 0.0198, "核心消費": 0.0149, "原物料": 0.0065, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00918": {"資訊科技": 0.429, "金融": 0.3281, "工業": 0.1689, "其他": 0.0433, "原物料": 0.0215, "固收/現金": 0.0092, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "009824": {"資訊科技": 0.9704, "非核心消費": 0.0232, "工業": 0.0037, "其他": 0.0027, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "009823": {"資訊科技": 0.5149, "金融": 0.1243, "醫療保健": 0.092, "工業": 0.0822, "核心消費": 0.0658, "非核心消費": 0.046, "能源": 0.0334, "公用事業": 0.0222, "原物料": 0.0191, "其他": 0.0001, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00888": {"資訊科技": 0.8757, "金融": 0.0984, "通訊服務": 0.0199, "工業": 0.0052, "非核心消費": 0.0008, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
    "00983D": {"固收/現金": 0.2039, "通訊服務": 0.1419, "金融": 0.1274, "能源": 0.1086, "非核心消費": 0.0862, "資訊科技": 0.0705, "公用事業": 0.0663, "醫療保健": 0.0632, "核心消費": 0.0588, "原物料": 0.0511, "工業": 0.0221, "_src": "L2 MoneyDJ ETF 持股分佈(依產業)，2026/08 基準"},
}

# ── 基金/保單產業權重（L1/L3/L4 混合，鍵=名稱關鍵字）──
# 格式: {關鍵字: {產業: 權重, "_src": "層級說明"}}
_FUND_IND = {
    # 富達全球動能 A 股級別＝同一檔基金 → 指向 B 股權重（2026-09-23 細化）
    "富達全球動能A股": None,  # 由下方 _canon 填入
    "貝萊德智慧數據收益成長": {"固收/現金": 0.3760, "資訊科技": 0.194, "金融": 0.1008, "工業": 0.0676, "醫療保健": 0.057, "非核心消費": 0.0528, "通訊服務": 0.0526, "核心消費": 0.0297, "能源": 0.0252, "原物料": 0.0202, "公用事業": 0.0145, "不動產": 0.0096,
        "_src": "L3 官方 fact sheet 2026/8/31 股62.58/債32.65/現4.77（1,870 檔、前10大僅10.71%）；權益部依 MSCI World 產業權重（iShares URTH 2026/9/21）"},
    "貝萊德世界健康科學": {"醫療保健": 0.9898, "固收/現金": 0.0102,
        "_src": "L1 MoneyDJ 官方月報 2026/06/30（製藥46.98+生物技術23.46+醫療保健服務11.20+生命科學工具8.74+醫療保健設備8.60；現金1.02）"},
    "統一奔騰": {"資訊科技": 0.8967, "通訊服務": 0.0486, "工業": 0.0194, "其他": 0.0353,
        "_src": "L1 MoneyDJ 官方月報 2026/08/31（電子零組件39.85+上櫃電子零組件2.58+半導體22.59+上櫃半導體6.76+電腦及週邊13.71+其他電子4.18→資訊科技；通信網路4.86→通訊服務；電機機械1.94→工業）"},

    # 台股基金
    "安聯台灣科技": {"資訊科技": 1.00, "_src": "L4 名稱推估（純科技）"},
    "台新美日台半導體": {"資訊科技": 0.90, "其他": 0.10, "_src": "L2 公開成分（半導體90%）"},
    "路博邁台灣5G": {"資訊科技": 0.70, "通訊服務": 0.15, "其他": 0.15, "_src": "L4 名稱推估（5G/科技）"},
    "台中銀台灣優息": {"金融": 0.30, "工業": 0.25, "核心消費": 0.15, "其他": 0.30, "_src": "L4 類型推估（台股優息）"},
    "元大台灣卓越50連結": {"資訊科技": 0.55, "金融": 0.15, "工業": 0.08, "核心消費": 0.05, "通訊服務": 0.04, "原物料": 0.04, "其他": 0.09, "_src": "L2 成分權重（同0050）"},
    "國泰台灣高股息": {"金融": 0.25, "資訊科技": 0.20, "工業": 0.15, "核心消費": 0.10, "其他": 0.30, "_src": "L4 類型推估（高股息）"},
    # 美股基金
    "聯博美國成長": {"資訊科技": 0.40, "非核心消費": 0.15, "通訊服務": 0.15, "醫療保健": 0.10, "金融": 0.10, "其他": 0.10, "_src": "L3 美國成長型基準"},
    "安聯AI收益成長": {"資訊科技": 0.50, "通訊服務": 0.15, "工業": 0.10, "其他": 0.25, "_src": "L4 名稱推估（AI科技）"},
    "貝萊德世界科技": {"資訊科技": 1.00, "_src": "L1 公開月報（純科技）"},
    "貝萊德世界黃金": {"原物料": 1.00, "_src": "L1 公開月報（黃金）"},
    "貝萊德全球股票收益": {"資訊科技": 0.30, "金融": 0.15, "醫療保健": 0.12, "非核心消費": 0.10, "工業": 0.08, "其他": 0.25, "_src": "L3 全球股票基準"},
    "貝萊德世界能源": {"能源": 1.00, "_src": "L1 公開月報（能源）"},
    # 股債平衡（股債拆解後股票部分再分產業）
    "富達全球動能多元": {"資訊科技": 0.2179, "金融": 0.126, "原物料": 0.087, "通訊服務": 0.0677, "工業": 0.0668, "其他": 0.2579, "固收/現金": 0.1767, "_src": "L1 官方2026/6 股74.81/債15.03/現2.64/其他7.52；行業2025/12 科技21.79/金融12.6/原物料8.7/電信6.77/工業6.68（整體資產口徑，8/22 截圖真值）"},
    "聯博全球多元收益": {"固收/現金": 0.55, "資訊科技": 0.10, "金融": 0.08, "醫療保健": 0.06, "非核心消費": 0.05, "工業": 0.05, "通訊服務": 0.015, "其他": 0.095, "_src": "L1 股55/債45（8/20）；8/23 前10大持股真值 NVDA2.31+AAPL2.14+AVGO1.21+MSFT1.21+UST1.09+GOOGL1.06 → 科技下限7.9% 估10%（通訊服務含GOOGL）"},
    "摩根JPM多重收益": {"資訊科技": 0.124, "金融": 0.0819, "工業": 0.0387, "醫療保健": 0.0381, "非核心消費": 0.0352, "其他": 0.1822, "固收/現金": 0.50, "_src": "L1 晨星2026/6 股46.05/債46.06/現3.94/其他3.96；行業科技12.4/金融8.19/工業3.87/醫療3.81/非核心消費3.52（8/23截圖真值）"},
    "M&G入息": {"金融": 0.10, "資訊科技": 0.0807, "工業": 0.058, "非核心消費": 0.0481, "通訊服務": 0.0238, "其他": 0.0641, "固收/現金": 0.6253, "_src": "L1 晨星2026/6 股39.25/債57.89/現4.64/其他-1.78；行業金融10/科技8.07/工業5.8/非核心消費4.81/電信2.38（8/23截圖真值）"},
    "PIMCO收益增長": {"資訊科技": 0.167, "金融": 0.05, "工業": 0.03, "醫療保健": 0.03, "通訊服務": 0.03, "非核心消費": 0.02, "核心消費": 0.02, "能源": 0.01, "原物料": 0.01, "公用事業": 0.01, "其他": 0.14, "固收/現金": 0.48, "_src": "L1 槓桿型 有效52:48（股65.9/債61.2/現-27.2 期貨槓桿）；科技16.7%（鉅亨 2026/3）；8/23 鉅亨截圖：前10持股=FNMA TBA 5% MBS/NVDA2.1/台積電1.7/MSFT/Apple1.6/AT&T1.0/Cisco1.0/FNMA TBA 6%/TJX0.9/AbbVie0.9；行業10類名稱真值（%除科技外為保守估）"},
    "安聯收益成長": {"資訊科技": 0.135, "金融": 0.047, "工業": 0.040, "非核心消費": 0.038, "醫療保健": 0.031, "通訊服務": 0.015, "其他": 0.327, "固收/現金": 0.367, "_src": "L1 晨星2026/6 股33.23/債32.07/現4.6/其他30.1（其他保守計權益）；8/23 截圖真值：前5大行業=資訊技術13.48/金融4.66/工業~4.0/非日常消費3.77/醫療3.14（整體資產口徑）；前10持股=輝達2.80/蘋果2.50/亞馬遜1.50/谷歌1.40/美光1.10/博通1.00（通訊含谷歌）"},
    "施羅德環球收息": {"固收/現金": 0.70, "資訊科技": 0.10, "金融": 0.08, "其他": 0.12, "_src": "L4 收息債券型"},
    # 貨幣
    "貨幣": {"固收/現金": 1.00, "_src": "L1 貨幣型"},
}


_FUND_IND["富達全球動能A股"] = _FUND_IND["富達全球動能多元"]
_FUND_IND["貝萊德世界健康"] = _FUND_IND["貝萊德世界健康科學"]   # 保單 A10／一般申購名稱別名
_FUND_IND["第一金ID01"] = _FUND_IND["M&G入息"]                  # 第一金通路代碼（9/16 已轉 M&G）


def _lvl_rank(src: str) -> int:
    """估算層級排序：L1 > L2 > L3 > L4（讓『估算層級』優先顯示最權威來源）"""
    for i, t in enumerate(("L1", "L2", "L3", "L4"), start=1):
        if t in src:
            return i
    return 9


def _match_fund(name: str):
    """回傳最匹配基金的產業權重 dict（含 _src），找不到回 None"""
    for key, w in _FUND_IND.items():
        if key in name:
            return w
    return None


def calc_industry_penetration(snap: dict) -> dict:
    """計算 GICS 產業穿透：回傳 {產業: {金額, 佔比, 主要來源}}"""
    total = snap.get("total_assets", 0)
    acc = {g: 0.0 for g in GICS}
    acc["固收/現金"] = 0.0
    src_notes = {}
    other_contrib = {}  # 未分類組成：{來源: 金額}（2026-08-23 透明化）
    unmatched = {}      # 未匹配基金/持倉：{名稱: 金額}

    def _add(w: dict, value: float, label: str):
        _src = w.pop("_src", "L4") if "_src" in w else "L4"
        for ind, wt in w.items():
            if ind == "其他":
                other_contrib[label] = other_contrib.get(label, 0) + value * wt
                continue  # 不歸類
            amt = value * wt
            acc[ind] = acc.get(ind, 0) + amt
            src_notes.setdefault(ind, set()).add(f"{label}({_src})")
        # 未拆分部分（其他）→ 依比例分配太複雜，併入「其他」不做（維持誠實）

    # 1) 證券（台股/美股 ETF）
    for h in snap.get("securities", {}).get("holdings", []):
        t = h.get("ticker", "")
        v = h.get("shares", 0) * h.get("price", 0)
        w = _ETF_IND.get(t)
        if w and v:
            _add(dict(w), v, t)

    # 2) 鉅亨基金（funds_breakdown flat）
    fb = snap.get("funds_breakdown", {})
    flat = {}
    for grp, items in fb.items():
        if isinstance(items, dict):
            for k, v in items.items():
                if k in ("小計", "匯率調整", "note") or not isinstance(v, (int, float)):
                    continue
                flat[k] = v
    for name, v in flat.items():
        w = _match_fund(name)
        if w and v:
            _add(dict(w), v, name)
        elif v:
            unmatched[name] = v  # 未匹配 → 未分類

    # 3) 保單基金（A/B breakdown）
    for bd_key in ["allianz_a_breakdown", "allianz_b_breakdown"]:
        for name, v in snap.get(bd_key, {}).items():
            if not isinstance(v, (int, float)):
                v = v.get("value", 0) if isinstance(v, dict) else 0
            w = _match_fund(name)
            if w and v:
                _add(dict(w), v, f"保單-{name}")
            elif v:
                unmatched[f"保單-{name}"] = v

    # 4) 第一金 — INC-219（2026-09-18）：基金已於 9/16 由 FJ33 轉為 M&G入息，原寫死用「聯博全球多元收益」映射
    #    會把第一金歸到舊基金產業 → 改依 snapshot firstjin_detail.current_fund 動態選映射。
    fj = (snap.get("firstjin_detail", {}).get("base_value_before_dividend")
          or snap.get("firstjin_current_value")
          or snap.get("firstjin_fl65_current_value") or 0)
    _fjcf = (snap.get("firstjin_detail", {}) or {}).get("current_fund", {}) or {}
    _fjnm = str(_fjcf.get("name") or snap.get("firstjin_fund_name") or "")
    if "M&G" in _fjnm:
        _fjkey = "M&G入息"
    elif "摩根" in _fjnm:
        _fjkey = "摩根JPM多重收益"
    else:
        _fjkey = "聯博全球多元收益"
    if fj:
        _add(dict(_FUND_IND.get(_fjkey) or _FUND_IND["M&G入息"]), fj, f"第一金{_fjcf.get('code') or _fjkey}")

    # 5) 現金（台幣活存 + MMF 已在 fund 貨幣處理；活存單獨加）
    cash = snap.get("cash_total", 0)
    acc["固收/現金"] += cash

    pct = {k: (v / total * 100 if total else 0) for k, v in acc.items()}
    # 未分類（各基金「其他」權重 + 未匹配持倉）— 誠實標註，讓產業加總 = 總資產（2026-08-22）
    acc["未分類(其他權重)"] = max(total - sum(v for k, v in acc.items() if k != "未分類(其他權重)"), 0)
    pct["未分類(其他權重)"] = acc["未分類(其他權重)"] / total * 100 if total else 0
    # 實體不動產（2026-08-22：GICS 分母=流動資產，不動產另行計列 — 避免誤讀為 0）
    re_val = snap.get("real_estate_value", 0)
    re_note = {
        "金額": re_val,
        "佔比_含不動產": (re_val / (total + re_val) * 100) if (total + re_val) else 0,
        "note": "兩間房（大義街 1F店面24,000+2-3F住宅21,000、洲際W 33,000，+管理費2,100=80,100/月）；GICS 分母為流動金融資產（8/10 雙軌裁示），實體不動產另行計列",
    }
    # 未分類組成明細（2026-08-23 透明化：各基金「其他」權重 + 未匹配持倉）
    _unc_contrib = sorted(other_contrib.items(), key=lambda x: -x[1])[:12]
    _unc_contrib += sorted(unmatched.items(), key=lambda x: -x[1])[:6]
    unc_detail = {k: round(v) for k, v in _unc_contrib if v > 0}

    return {
        "日期": TODAY,
        "總資產": total,
        "產業": {k: {"金額": round(acc[k]), "佔比": round(pct[k], 1)} for k in acc},
        "未分類組成": unc_detail,
        "實體不動產_另計": re_note,
        "估算層級": {k: sorted(v, key=lambda s: (_lvl_rank(s), s))[:3] for k, v in src_notes.items()},
        "備註": ("L1=公開月報權重 L2=公開成分權重 L3=指數基準 L4=名稱/類型推估。2026-09-23 細化：ETF 15 檔改 L2（MoneyDJ 持股分佈依產業）、貝萊德智慧數據收益成長 B11 由未分類改 L3（官方 fact sheet 股債比 62.58/32.65/4.77＋權益部依 MSCI World 產業權重）、世界健康A10／統一奔騰／富達A股 改 L1/別名。未分類＝各基金月報『其他』權重（富達 25.8%、安聯收益成長 32.7%、摩根 18.2%、PIMCO 14%）＋指數『其他』桶，屬真實未知，非估算缺口"),
    }


def build_chart(pen: dict, out=None):
    """產業分布堆疊長條圖（單條 stacked bar，按金額排序）"""
    inds = {k: v for k, v in pen["產業"].items() if v["金額"] > 0}
    order = sorted(inds.keys(), key=lambda k: -inds[k]["金額"])
    fig, ax = plt.subplots(figsize=(12, 4.2), dpi=130)
    left = 0
    for ind in order:
        amt = inds[ind]["金額"]
        ax.barh([0], [amt], left=left, color=GICS_COLORS.get(ind, "#94a3b8"), height=0.5,
                label=f"{ind} {amt/1e4:.0f}萬 ({inds[ind]['佔比']:.1f}%)")
        left += amt
    ax.set_yticks([])
    ax.set_xlim(0, left * 1.02)
    ax.set_xlabel("金額（TWD）")
    ax.set_title(f"GICS 產業穿透分布（{TODAY}，總資產 {pen['總資產']/1e4:.0f}萬）", fontsize=13, fontweight="bold")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=4, fontsize=8)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    plt.tight_layout()
    if out is None:
        out = BASE / f"industry_penetration_{TODAY}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"✅ 產業分布圖已產出: {out}")
    return out


def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    pen = calc_industry_penetration(snap)
    # 寫入 snapshot（單一真值，pipeline 不覆寫）
    snap["industry_penetration"] = pen
    (BASE / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print("✅ industry_penetration 已寫入 snapshot")
    build_chart(pen)
    for ind in sorted(pen["產業"].items(), key=lambda x: -x[1]["金額"]):
        v = ind[1]
        print(f"  {ind[0]:<8} {v['金額']:>12,.0f}（{v['佔比']:>5.1f}%）")


if __name__ == "__main__":
    main()
