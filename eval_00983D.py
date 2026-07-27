#!/usr/bin/env python3
"""00983D 策略重新評估報告"""
import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
holdings = snap.get("securities", {}).get("holdings", [])
today = date.today().isoformat()

# Get 00983D data
d9 = [h for h in holdings if h["ticker"] == "00983D"][0]

# Classify ETFs
def classify(t):
    if t in ("0050","006208","009816"): return "市值型"
    if t in ("00878","00713","0056","00919","00918","00888"): return "高股息"
    if t in ("00981A","00984A"): return "主動型"
    if t in ("00983D",): return "債券型"
    if t in ("00646","009823","009824"): return "美股型"
    return "其他"

cats = {}
for h in holdings:
    c = classify(h["ticker"])
    cats.setdefault(c, []).append(h)

# Performance comparison
print("=" * 70)
print("  00983D 策略重新評估報告")
print(f"  {today}")
print("=" * 70)
print()

# Section 1: Current Status
print("─" * 70)
print("  📊 一、00983D 現況")
print("─" * 70)
print(f"  持有股數: {d9['shares']:,} 股")
print(f"  成本均價: {d9['cost']:.2f}")
print(f"  現價:     {d9['price']:.2f}")
print(f"  市值:     {d9['value']:,} TWD")
print(f"  損益:     {d9['pnl']:+,} TWD ({d9['pnl_pct']:+.2f}%)")
print(f"  月配息:   0.06元/股 → 年化 {0.06*12/d9['cost']*100:.2f}%")
print(f"  年配息:   {d9['shares'] * 0.06 * 12:,} TWD")
print()

# Section 2: Performance comparison
print("─" * 70)
print("  📈 二、各類別報酬率比較")
print("─" * 70)
print(f"  {'類別':8s} {'ETF':6s} {'價格報酬':>10s} {'配息率':>8s} {'總報酬':>10s}")
for cat_name in ["市值型","高股息","債券型","美股型","主動型"]:
    items = cats.get(cat_name, [])
    if not items:
        continue
    for h in sorted(items, key=lambda x: x["pnl_pct"], reverse=True):
        div = {"00878":0.42,"00919":0.33,"0056":1.35,"00713":1.0,"00918":1.26,
               "00981A":0.63,"00983D":0.72,"00646":1.38,"0050":0.6,"006208":4.75,
               "009816":0,"009823":0,"009824":0,"00888":0,"00984A":0}.get(h["ticker"],0)
        div_yield = div / h["cost"] * 100 if div else 0
        total_ret = h["pnl_pct"] + div_yield
        print(f"  {cat_name:8s} {h['ticker']:6s} {h['pnl_pct']:>+9.2f}% {div_yield:>7.2f}% {total_ret:>+9.2f}%")
print()

# Section 3: Penetration impact
print("─" * 70)
print("  🎯 三、穿透影響分析")
print("─" * 70)
print(f"  目前債券佔比 19.3%（目標5%）→ 超標 +14.3pp")
print(f"  00983D 市值 {d9['value']:,}，僅佔總穿透分母 ~0.6%")
print(f"  但 251萬 建倉完成後，債券將增至 ~34%")
print(f"  質押後淨債券曝險將降至 ~11%")
print()

# Section 4: Strategy Options
print("─" * 70)
print("  💡 四、策略選項比較")
print("─" * 70)

plans = [
    ("A) 原計畫執行", 
     "自有251萬買00983D→質押借198萬→買006208+00713",
     "✅ 保有債券月配現金流\n✅ 質押槓桿買股\n✅ 轉貸後結構完整\n⚠️ 00983D成長性低\n⚠️ 債券佔比先升後降",
     "適合：想要月配現金流 + 股債平衡",
     "穿透改善程度：★★★☆☆"),
    ("B) 減少00983D，直接買股",
     "自有100萬買00983D + 151萬直接買006208/00713",
     "✅ 簡化操作，免質押\n✅ 台股直接增加\n✅ 債券不過度超標\n⚠️ 無質押槓桿\n⚠️ 月配現金流較少",
     "適合：追求簡潔配置，不想要質押槓桿",
     "穿透改善程度：★★★★☆"),
    ("C) 00983D換成高股息ETF",
     "251萬買00878/00919/00713，取代00983D",
     "✅ 價格報酬更高（+11~21%）\n✅ 配息率接近（4~5%）\n✅ 防守型一次補足\n⚠️ 波動較00983D大\n⚠️ 無質押標的",
     "適合：信任台股長線，用高股息取代債券",
     "穿透改善程度：★★★★★"),
    ("D) 00983D降為現金替代",
     "只保留50萬00983D，剩200萬做現金+定存",
     "✅ 最保守，流動性最高\n✅ 保留子彈等大跌\n⚠️ 報酬率最低\n⚠️ 通膨侵蝕實質購買力",
     "適合：極度看空市場，想保留最多現金",
     "穿透改善程度：★★☆☆☆"),
]

for title, desc, pros, suitable, score in plans:
    print(f"\n  {title}")
    print(f"  {'─'*50}")
    print(f"  作法：{desc}")
    print(f"  優缺：{pros}")
    print(f"  適合：{suitable}")
    print(f"  評分：{score}")

print()
print("─" * 70)
print("  🧓 五、建議")
print("─" * 70)
print("""  考量你的整體狀況：

  1️⃣ 你已有 15 檔 ETF + 保險 + 基金，配置已夠分散
  2️⃣ 目前穿透：債券 19.3% 嚴重超標，台股 15.6% 嚴重不足
  3️⃣ 00983D 的優勢在月配現金流（年化 ~7.1%）和低波動
     劣勢在價格成長幾乎為 0（+0.4%）

  🔑 核心問題：你要的是「月配現金流」還是「長期資本成長」？

  方案 B 可能是最佳平衡點：
  • 100萬買00983D → 年化月配 ~5,950元（現金流）
  • 151萬直接買006208(100萬)+00713(51萬) → 補台股+防守
  • 穿透變：台股 ~21% / 防守 ~15% / 債券 ~12%
  • 免質押、免槓桿、管理簡單

  若你仍想要質押槓桿放大報酬，方案 A 在質押後也會改善穿透。
""")
print("=" * 70)
