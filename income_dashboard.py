#!/usr/bin/env python3
"""income_dashboard.py — 被動收入儀表板
每月自動產出配息+房租的圓餅圖+趨勢圖，Telegram 推送"""

import json, sys, os
from pathlib import Path
from datetime import date, timedelta
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

BASE = Path(__file__).resolve().parent
plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei"]
plt.rcParams["axes.unicode_minus"] = False

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def build_chart():
    snap = load_json(BASE / "snapshot.json")
    mdb = snap.get("monthly_dividend_breakdown", {})
    
    insurance_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    total = insurance_div + etf_div + fund_div + rent
    
    # 圓餅圖
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor('#f5f5f7')
    
    labels = ["保單配息", "ETF配息", "基金配息", "房租收入"]
    values = [insurance_div, etf_div, fund_div, rent]
    colors = ["#16a34a", "#2563eb", "#7c3aed", "#f59e0b"]
    explode = (0.03, 0.03, 0.03, 0.03)
    
    wedges, texts, autotexts = ax1.pie(
        values, labels=labels, colors=colors, explode=explode,
        autopct=lambda p: f'{p:.1f}%\n({p*total/100/10000:.0f}萬)',
        startangle=90, textprops={"fontsize": 10}
    )
    ax1.set_title(f"被動收入結構 — {total:,} TWD/月", fontsize=13, fontweight=800, pad=15)
    
    # 趨勢圖（從 history 取近7日）
    hist = load_json(BASE / "asset_diff_history.json")
    sorted_dates = sorted(hist.keys())[-7:]
    if len(sorted_dates) >= 2:
        rent_vals = [hist[d].get("rent_monthly", 80100) for d in sorted_dates]
        ax2.plot(range(len(sorted_dates)), rent_vals, color="#f59e0b", marker="o", label="房租")
        ax2.set_title("近7日被動收入趨勢", fontsize=13, fontweight=800)
        ax2.set_xticks(range(len(sorted_dates)))
        ax2.set_xticklabels([d[-5:] for d in sorted_dates], rotation=30, fontsize=8)
        ax2.legend(fontsize=9)
        ax2.grid(axis="y", alpha=0.3)
    
    plt.tight_layout()
    out_path = BASE / "income_dashboard.png"
    fig.savefig(str(out_path), dpi=150, bbox_inches="tight", facecolor="#f5f5f7")
    plt.close()
    
    print(f"📊 被動收入儀表板：{total:,} TWD/月")
    print(f"  保單 {insurance_div:,} + ETF {etf_div:,} + 基金 {fund_div:,} + 房租 {rent:,}")
    print(f"  ✅ 圖表已儲存：{out_path}")
    return str(out_path)

if __name__ == "__main__":
    path = build_chart()
    # 推送 Telegram
    try:
        from asset_diff_monitor import send_telegram_document
        send_telegram_document(path, f"📊 被動收入儀表板 — 合計 {json.loads((BASE/'snapshot.json').read_text()).get('monthly_dividend_breakdown',{}).get('total',0)+80100:,} TWD/月")
    except Exception as e:
        print(f"  ⚠️ 推送失敗：{e}")
