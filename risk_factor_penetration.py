# -*- coding: utf-8 -*-
"""risk_factor_penetration.py — 底層風險因子穿透對照圖
追蹤「名義分散、實質集中」：把穿透桶 + 幣別 + 因子集中度視覺化，
加碼前看一眼：這筆錢會不會又進同一個籃子。

輸入：snapshot.json（穿透 actual_twd/actual_pct/targets + 美元曝險分析值）
輸出：risk_factor_penetration_YYYY-MM-DD.png
"""
import json
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 中文字體
for f in ["Microsoft YaHei", "Microsoft JhengHei", "Noto Sans CJK TC"]:
    try:
        font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.sans-serif"] = [f]
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
TODAY = date.today().isoformat()

def load(p):
    return json.loads((BASE / p).read_text(encoding="utf-8"))

def build_chart():
    """產生底層風險因子穿透對照圖 PNG，回傳 Path（run_daily 每日重生成 + base64 嵌入日報）"""
    s = load("snapshot.json")
    pen = s.get("penetration", {})
    atwd, apct, tgt = pen.get("actual_twd", {}), pen.get("actual_pct", {}), pen.get("targets", {})
    total = s.get("total_assets", 0)

    # 五桶
    buckets = ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"]
    labels_cn = ["台股", "美股", "防守", "債券", "現金"]
    actuals = [apct.get(b, 0) for b in buckets]
    targets = [tgt.get(k, 0) for k in ["台股市值型目標", "美股市值型目標", "配息型目標", "債券型目標", "現金目標"]]
    twd_v = [atwd.get(b, 0) for b in buckets]

    # 美元曝險（8/22 分析值 64%：美股桶全美元 + 債券桶美元基金 + MMF 美元 + 保單美元平衡）
    usd_pct = float(s.get("usd_exposure_pct", 64.0))  # snapshot.usd_exposure_pct 可覆寫
    usd_twd = total * usd_pct / 100

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), dpi=130)
    fig.suptitle(f"底層風險因子穿透對照（流動資產 {total/1e4:.0f}萬）｜{TODAY}", fontsize=16, fontweight="bold")

    # Panel 1: 五桶 vs 目標
    ax = axes[0][0]
    x = range(len(labels_cn))
    ax.bar([i - 0.18 for i in x], actuals, width=0.36, label="現況", color="#3b82f6")
    ax.bar([i + 0.18 for i in x], targets, width=0.36, label="目標", color="#94a3b8")
    for i, (a, t_) in enumerate(zip(actuals, targets)):
        ax.text(i - 0.18, a + 0.5, f"{a:.1f}%", ha="center", fontsize=10, fontweight="bold")
        ax.text(i + 0.18, t_ + 0.5, f"{t_:.0f}%", ha="center", fontsize=10, color="#64748b")
    ax.set_title("五桶穿透 vs 目標（%）", fontsize=13, fontweight="bold")
    ax.set_xticks(list(x)); ax.set_xticklabels(labels_cn)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_ylim(0, max(actuals + targets) * 1.15)

    # Panel 2: 幣別曝險
    ax = axes[0][1]
    usd_other = max(usd_twd - twd_v[1] - 5000000 - twd_v[3] * 0.6, 0)  # 不重算，僅顯示分析值
    ax.pie([usd_pct, 100 - usd_pct], labels=["美元", "台幣"], autopct="%.0f%%",
           colors=["#ef4444", "#22c55e"], startangle=90,
           explode=(0.04, 0))
    ax.set_title(f"幣別曝險（美元 {usd_twd/1e4:.0f}萬）｜紅線 50%", fontsize=13, fontweight="bold")
    ax.text(0, -1.35, "⚠️ 超紅線 14pp — 新增資金一律台幣", ha="center", fontsize=11, color="#dc2626")

    # Panel 3: 底層因子集中度
    ax = axes[1][0]
    factors = ["美股相關（直接+平衡底層）", "美元信用債", "台股", "現金（台幣）", "黃金/新興/REITs"]
    vals = [60, 20, 7.2, 12.8, 0]
    colors = ["#ef4444", "#f97316", "#3b82f6", "#22c55e", "#94a3b8"]
    ax.barh(factors, vals, color=colors)
    for i, v in enumerate(vals):
        ax.text(v + 0.8, i, f"{v:.1f}%", va="center", fontsize=10, fontweight="bold")
    ax.set_title("底層風險因子集中度（% 流動資產，8/22 拆解）", fontsize=13, fontweight="bold")
    ax.set_xlim(0, 75)
    ax.invert_yaxis()

    # Panel 4: 集中風險警示
    ax = axes[1][1]
    ax.axis("off")
    risks = [
        "[紅] 美元曝險 64%（紅線 50%）— 台幣升5%資產縮水3%",
        "[紅] 美股相關 >60% — 平衡基金底層重疊",
        "[黃] 科技 13.8%（上限 15%）— 8/24 保單轉換持續稀釋",
        "[黃] 新興市場 0% ｜ 黃金 0%（PI 後建衛星）",
        "[黃] 台股 7.2%（目標 10%）— 慢慢買補缺口",
        "[OK] 現金 22.1% = 戰術停泊乾粉（底線制 70萬）",
        "[OK] 防守合併口徑 69.5% 無缺口（勿被 4.2% 誤導）",
        "",
        "執行紀律：",
        "1) 新增資金全台幣（唯一解美元之路）",
        "2) 美股逢彈減碼 ≤20萬/次",
        "3) 台股 0050/006208 分批 8-12 週",
        "4) 黃金衛星 PI 後分 3 批（勿追高）",
    ]
    ax.text(0.02, 0.98, "\n".join(risks), va="top", ha="left", fontsize=11.5, linespacing=1.6,
            family="Microsoft YaHei")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    out = BASE / f"risk_factor_penetration_{TODAY}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    print(f"✅ 穿透圖已產出: {out}")
    return out

def main():
    build_chart()

if __name__ == "__main__":
    main()
