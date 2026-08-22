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
    "0050": {"資訊科技": 0.55, "金融": 0.15, "工業": 0.08, "核心消費": 0.05, "通訊服務": 0.04, "原物料": 0.04, "其他": 0.09},
    "006208": {"資訊科技": 0.55, "金融": 0.15, "工業": 0.08, "核心消費": 0.05, "通訊服務": 0.04, "原物料": 0.04, "其他": 0.09},
    "009816": {"資訊科技": 0.55, "金融": 0.15, "工業": 0.08, "核心消費": 0.05, "通訊服務": 0.04, "原物料": 0.04, "其他": 0.09},
    "00878": {"金融": 0.25, "資訊科技": 0.20, "工業": 0.15, "核心消費": 0.10, "其他": 0.30},
    "0056": {"金融": 0.30, "資訊科技": 0.20, "工業": 0.15, "核心消費": 0.10, "其他": 0.25},
    "00919": {"資訊科技": 0.35, "金融": 0.25, "工業": 0.15, "核心消費": 0.10, "其他": 0.15},
    "00918": {"金融": 0.30, "資訊科技": 0.25, "工業": 0.15, "核心消費": 0.10, "其他": 0.20},
    "00713": {"金融": 0.25, "通訊服務": 0.15, "工業": 0.15, "核心消費": 0.15, "公用事業": 0.10, "其他": 0.20},
    "00888": {"資訊科技": 0.45, "金融": 0.20, "工業": 0.15, "其他": 0.20},
    "00981A": {"資訊科技": 0.55, "金融": 0.15, "工業": 0.10, "其他": 0.20},
    "00984A": {"金融": 0.30, "資訊科技": 0.35, "工業": 0.10, "核心消費": 0.10, "其他": 0.15},
    "00646": {"資訊科技": 0.32, "金融": 0.13, "醫療保健": 0.11, "非核心消費": 0.10, "通訊服務": 0.09,
              "工業": 0.08, "核心消費": 0.06, "能源": 0.04, "公用事業": 0.03, "原物料": 0.03, "不動產": 0.01},
    "009823": {"資訊科技": 0.32, "金融": 0.13, "醫療保健": 0.11, "非核心消費": 0.10, "通訊服務": 0.09,
               "工業": 0.08, "核心消費": 0.06, "能源": 0.04, "公用事業": 0.03, "原物料": 0.03, "不動產": 0.01},
    "00924": {"資訊科技": 1.00},
    "00983D": {"固收/現金": 1.00},
}

# ── 基金/保單產業權重（L1/L3/L4 混合，鍵=名稱關鍵字）──
# 格式: {關鍵字: {產業: 權重, "_src": "層級說明"}}
_FUND_IND = {
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
    "聯博全球多元收益": {"固收/現金": 0.55, "資訊科技": 0.12, "金融": 0.08, "醫療保健": 0.06, "非核心消費": 0.05, "工業": 0.05, "其他": 0.09, "_src": "L1 股55/債40/現5；股票產業 L3 基準"},
    "摩根JPM多重收益": {"資訊科技": 0.124, "金融": 0.0819, "工業": 0.0387, "醫療保健": 0.0381, "非核心消費": 0.0352, "其他": 0.1822, "固收/現金": 0.50, "_src": "L1 晨星2026/6 股46.05/債46.06/現3.94/其他3.96；行業科技12.4/金融8.19/工業3.87/醫療3.81/非核心消費3.52（8/23截圖真值）"},
    "M&G入息": {"金融": 0.10, "資訊科技": 0.0807, "工業": 0.058, "非核心消費": 0.0481, "通訊服務": 0.0238, "其他": 0.0641, "固收/現金": 0.6253, "_src": "L1 晨星2026/6 股39.25/債57.89/現4.64/其他-1.78；行業金融10/科技8.07/工業5.8/非核心消費4.81/電信2.38（8/23截圖真值）"},
    "PIMCO收益增長": {"資訊科技": 0.167, "金融": 0.08, "其他": 0.273, "固收/現金": 0.48, "_src": "L1 槓桿型 有效52:48（股65.9/債61.2/現-27.2 期貨槓桿）；產業科技16.7%最大（鉅亨 2026/3）"},
    "安聯收益成長": {"資訊科技": 0.15, "金融": 0.10, "通訊服務": 0.06, "醫療保健": 0.06, "其他": 0.263, "固收/現金": 0.367, "_src": "L1 晨星2026/6 股33.23/債32.07/現4.6/其他30.1（其他保守計權益）；產業 L3 基準"},
    "施羅德環球收息": {"固收/現金": 0.70, "資訊科技": 0.10, "金融": 0.08, "其他": 0.12, "_src": "L4 收息債券型"},
    # 貨幣
    "貨幣": {"固收/現金": 1.00, "_src": "L1 貨幣型"},
}


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

    def _add(w: dict, value: float, label: str):
        _src = w.pop("_src", "L4") if "_src" in w else "L4"
        for ind, wt in w.items():
            if ind == "其他":
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

    # 3) 保單基金（A/B breakdown）
    for bd_key in ["allianz_a_breakdown", "allianz_b_breakdown"]:
        for name, v in snap.get(bd_key, {}).items():
            if not isinstance(v, (int, float)):
                v = v.get("value", 0) if isinstance(v, dict) else 0
            w = _match_fund(name)
            if w and v:
                _add(dict(w), v, f"保單-{name}")

    # 4) 第一金 FA81（聯博全球多元收益）— 2026-08-22 修正：讀 firstjin_detail 最新值（8/21 轉換後 1,992,265），舊 firstjin_fl65_current_value 是 FL65 時期市值
    fj = (snap.get("firstjin_detail", {}).get("base_value_before_dividend")
          or snap.get("firstjin_current_value")
          or snap.get("firstjin_fl65_current_value") or 0)
    if fj:
        _add(dict(_FUND_IND["聯博全球多元收益"]), fj, "第一金FA81聯博")

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
    return {
        "日期": TODAY,
        "總資產": total,
        "產業": {k: {"金額": round(acc[k]), "佔比": round(pct[k], 1)} for k in acc},
        "實體不動產_另計": re_note,
        "估算層級": {k: sorted(v)[:3] for k, v in src_notes.items()},
        "備註": "L1=公開月報權重 L2=公開成分權重 L3=指數基準 L4=名稱/類型推估；基金產業比重為估算（月報待精確化）",
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
