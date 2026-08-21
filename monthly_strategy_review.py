#!/usr/bin/env python3
"""monthly_strategy_review.py — 月戰略檢討（P1-4）
每月 1 號 cron 產出月報時，強制加入「月戰略檢討」單元：
1. SAA 目標是否仍符合現況（核貸進度/現金流/利率環境）
2. 目標漂移檢查：本月實際 vs 目標 vs 上月，是否需調整 SAA
3. 產出結構化 JSON + Markdown，供月報 LLM agent 使用

輸出：monthly_strategy_review_{YYYY-MM}.json
"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent

# 每個目標的「環境檢查點」— 影響 SAA 是否需調整的因素
ENV_CHECKS = {
    "台股市值型成長": {
        "factors": ["台股資金流向", "外資動向", "核貸解除後可投入資金"],
        "adjust_rule": "核貸解除+資金轉入後，若持續超配/低配>10pp 連續2個月 → 考慮調整目標",
    },
    "美股市值型成長": {
        "factors": ["US30Y 趨勢", "美股估值", "防禦模式持續時間"],
        "adjust_rule": "US30Y 持續>5.30% 或防禦模式>3個月 → 檢討是否下修美股目標",
    },
    "防守型配息": {
        "factors": ["配息覆蓋率", "退休現金流需求"],
        "adjust_rule": "覆蓋率<100% 連續2個月 → 上修防守目標",
    },
    "債券": {
        "factors": ["US30Y 水準", "債券底倉需求"],
        "adjust_rule": "US30Y<5.20% 且債券低配 → 可上修債券目標",
    },
    "現金/安全網": {
        "factors": ["6個月支出底線", "核貸/轉貸現金流需求"],
        "adjust_rule": "現金<6個月底線 → 暫緩一切部署，先補現金",
    },
}

def build_monthly_review(snap: dict, us30y: float = None) -> dict:
    pen = snap.get("penetration", {})
    apct = pen.get("actual_pct", {})
    targets = pen.get("targets", {})
    total = snap.get("total_assets", 0)

    target_map = {
        "台股市值型成長": ("台股市值型目標", "台股市值型成長"),
        "美股市值型成長": ("美股市值型目標", "美股市值型成長"),
        "防守型配息": ("配息型目標", "防守型配息"),
        "債券": ("債券型目標", "債券"),
        "現金/安全網": ("現金目標", "現金/安全網"),
    }

    # 環境狀態
    env = {
        "核貸進度": snap.get("cathay_refinance_note", "審查中"),
        "現金底線覆蓋": f"{snap.get('real_liquid_assets',0):,} vs 6個月 {snap.get('monthly_expense',152781)*6:,.0f}",
        "US30Y": us30y,
        "負債比": snap.get("debt_ratio", "?"),
    }

    rows = []
    for asset, (tgt_key, pct_key) in target_map.items():
        tgt = targets.get(tgt_key, 0)
        cur = apct.get(pct_key, 0)
        dev = cur - tgt
        checks = ENV_CHECKS.get(asset, {})
        # 建議：|dev|>10 → 建議調整；>5 → 觀察；否則維持
        if abs(dev) > 10:
            suggestion = "🔴 建議調整目標（連續2個月>10pp 才執行）"
        elif abs(dev) > 5:
            suggestion = "🟡 觀察（連續2個月>10pp 才調整）"
        else:
            suggestion = "🟢 維持"
        rows.append({
            "資產分類": asset,
            "現況": cur,
            "目標": tgt,
            "偏離pp": round(dev, 1),
            "環境檢查點": checks.get("factors", []),
            "調整規則": checks.get("adjust_rule", ""),
            "建議": suggestion,
        })

    review = {
        "month": date.today().strftime("%Y-%m"),
        "環境狀態": env,
        "SAA複檢": rows,
        "總結": {
            "需調整": [r["資產分類"] for r in rows if "調整" in r["建議"]],
            "觀察中": [r["資產分類"] for r in rows if "觀察" in r["建議"]],
            "維持": [r["資產分類"] for r in rows if "維持" in r["建議"]],
        },
    }
    out = BASE / f"monthly_strategy_review_{date.today().strftime('%Y-%m')}.json"
    out.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return review

def to_markdown(review: dict) -> str:
    lines = [
        "## 🗓️ 月戰略檢討（SAA 複檢）",
        "",
        f"**月份：** {review['month']}",
        f"**環境狀態：** 核貸={review['環境狀態']['核貸進度']}｜現金={review['環境狀態']['現金底線覆蓋']}｜US30Y={review['環境狀態']['US30Y']}｜負債比={review['環境狀態']['負債比']}",
        "",
        "| 資產 | 現況% | 目標% | 偏離 | 建議 |",
        "|---|---|---|---|---|",
    ]
    for r in review["SAA複檢"]:
        lines.append(f"| {r['資產分類']} | {r['現況']}% | {r['目標']}% | {r['偏離pp']:+.1f} | {r['建議']} |")
    lines.append("")
    lines.append("**調整規則：** 偏離>10pp 連續2個月才調整目標；<5pp 維持；核貸/轉貸重大事件可即時複檢。")
    return "\n".join(lines)

def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    us30y = None
    try:
        st = json.loads((BASE / "us30y_state.json").read_text(encoding="utf-8"))
        us30y = st.get("last_rate")
    except Exception:
        pass
    review = build_monthly_review(snap, us30y)
    print(to_markdown(review))

if __name__ == "__main__":
    main()
