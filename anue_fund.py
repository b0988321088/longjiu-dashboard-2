"""龍九系統 — 鉅亨買基金穿透資料（2026-07-10 截圖真值）"""

ANUE_FUND = [
    {"type": "一般申購", "code": "A47219", "name": "台新美日台半導體基金A-日圓", "currency": "JPY", "cost": 609172, "market_value": 690493, "pnl": 81321},
    {"type": "一般申購", "code": "A17030", "name": "台中銀台灣優息基金-B配息台幣", "currency": "TWD", "cost": 30014, "market_value": 50070, "pnl": 20056},
    {"type": "一般申購", "code": "A49015", "name": "路博邁台灣5G股票基金T月配級別(台幣)", "currency": "TWD", "cost": 30000, "market_value": 102792, "pnl": 72792},
    {"type": "一般申購", "code": "A05144", "name": "元大台灣卓越50ETF(0050)連結基金-台幣B配息", "currency": "TWD", "cost": 21448, "market_value": 47797, "pnl": 0},
    {"type": "自由PAY", "code": "A49038", "name": "路博邁台灣5G股票基金T累積級別(台幣)", "currency": "TWD", "cost": 110000, "market_value": 276149, "pnl": 171245},
    {"type": "自由PAY", "code": "A05143", "name": "元大台灣卓越50ETF(0050)連結基金-台幣A不配息", "currency": "TWD", "cost": 100000, "market_value": 110054, "pnl": 10054},
    {"type": "自由PAY", "code": "A09012", "name": "統一奔騰基金", "currency": "TWD", "cost": 100000, "market_value": 94458, "pnl": -5542},
]

ACCOUNT_SUMMARY = {
    "market_value": 873041,
    "daily_change": 311,
    "daily_pct": 0.04,
    "cost_twd": 563153,
    "pnl": 309888,
    "distributed_amount": 17167,
    "return_with_dist": 58.08,
    "return_without_dist": 55.03,
    "yoy_change": 623772,
    "yoy_pct": 250.24,
    "currency": "TWD",
}


def total_market_value():
    return sum(item["market_value"] for item in ANUE_FUND)


def filter_by(threshold=5000):
    out = []
    for item in ANUE_FUND:
        if abs(item.get("market_value", 0)) >= threshold or abs(item.get("cost", 0)) >= threshold:
            out.append(item)
    return out


def summary_text():
    return (
        f"市值 {total_market_value():,.0f} TWD | "
        f"成本 {ACCOUNT_SUMMARY['cost_twd']:,.0f} TWD | "
        f"損益 {ACCOUNT_SUMMARY['pnl']:,.0f} TWD | "
        f"含息報酬率 {ACCOUNT_SUMMARY['return_with_dist']:.2f}%"
    )


if __name__ == "__main__":
    print(summary_text())
    for item in filter_by(5000):
        print(f"{item['type']} {item['code']} {item['name']} 市值{item['market_value']:,.0f}")
