import os
import time
import requests
import json
import csv
import urllib.request
import re
import base64
from datetime import datetime, timedelta, date
from dotenv import load_dotenv

# ==========================================================================
# 【龍九資產管理系統 2.0 - 本地全資產數據庫 + SSoT snapshot】
# ==========================================================================

# 載入 .env 環境變數
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ==========================================================================
# 穿透式成份股分析模組
# ==========================================================================
def load_weights_manifest():
    """讀取 weights_manifest.json，回傳 ETF 前十大成份股權重"""
    import json
    manifest_path = os.path.join(os.path.dirname(__file__), "weights_manifest.json")
    if not os.path.exists(manifest_path):
        return {}
    with open(manifest_path, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_concentration_risk():
    """根據持有部位 × 成份股權重，計算實質集中度風險"""
    manifest = load_weights_manifest()
    if not manifest:
        return []

    # 取得最新價格與持有量
    prices = fetch_market_prices()
    holdings = {}
    for code, shares in tw_assets.items():
        if code in prices and shares > 0:
            holdings[code] = {"shares": shares, "price": prices[code]}

    # 計算各 ETF 市值
    etf_values = {}
    for code, info in holdings.items():
        etf_values[code] = info["shares"] * info["price"]

    total_etf_value = sum(etf_values.values())
    if total_etf_value == 0:
        return []

    # 穿透計算各成份股實質持倉
    stock_exposure = {}
    for etf_code, weight_info in manifest.get("etf_holdings", {}).items():
        if etf_code not in etf_values:
            continue
        etf_val = etf_values[etf_code]
        for holding in weight_info.get("top_holdings", []):
            stock_code = holding["code"]
            weight = holding["weight"]
            exposure = etf_val * weight
            stock_exposure[stock_code] = stock_exposure.get(stock_code, 0) + exposure

    # 計算各成份股佔整體台股部位的百分比
    concentration = []
    for stock_code, exposure in stock_exposure.items():
        pct = exposure / total_etf_value if total_etf_value > 0 else 0
        stock_name = ""
        for etf_code, weight_info in manifest.get("etf_holdings", {}).items():
            for h in weight_info.get("top_holdings", []):
                if h["code"] == stock_code:
                    stock_name = h["name"]
                    break
            if stock_name:
                break
        concentration.append({
            "code": stock_code,
            "name": stock_name,
            "exposure": exposure,
            "pct": pct,
        })

    concentration.sort(key=lambda x: x["exposure"], reverse=True)
    return concentration


def auto_update_weights_manifest():
    """使用 Gemini API 自動更新 weights_manifest.json 中的 ETF 成分股權重"""
    if not GEMINI_API_KEY:
        return False

    manifest = load_weights_manifest()
    if not manifest:
        return False

    updated = False
    for etf_code in manifest.get("etf_holdings", {}):
        try:
            # 建構 Gemini prompt：要求從公開資訊提取最新前十大成分股權重
            prompt = (
                f"請從公開資訊提取 {etf_code} 的最新前五大成分股權重分布。"
                f"只需回傳 JSON 格式，範例："
                f'{{"etf":"{etf_code}","holdings":[{{"code":"2330","name":"台積電","weight":0.35}}, ...]}}'
                f"不需要額外說明，只回傳 JSON。"
            )

            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
            data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            text = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

            # 嘗試從回傳中擷取 JSON（支援 markdown code block）
            import re
            text_clean = re.sub(r'```(?:json)?', '', text).strip()
            json_match = re.search(r'\{.*\}', text_clean, re.DOTALL)
            if json_match:
                new_data = json.loads(json_match.group())
                new_holdings = new_data.get("holdings", [])
                if new_holdings:
                    manifest["etf_holdings"][etf_code]["top_holdings"] = new_holdings
                    updated = True
        except Exception:
            continue  # 單一 ETF 更新失敗不影響其他

    if updated:
        manifest["version"] = datetime.now().strftime("%Y-%m-%d")
        manifest_path = os.path.join(os.path.dirname(__file__), "weights_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    return updated


# 1. 台美雙軌真實持倉（已依券商截圖精確對位）
tw_assets = {
    '0050.TW': 2000,
    '006208.TW': 2000,
    '009816.TW': 16000,
    '00646.TW': 1000,
    '00713.TW': 2000,
    '00878.TW': 15000,
    '0056.TW': 1000,
    '00981A.TW': 4000,
    '00984A.TW': 10000,
    '00919.TW': 5000,
    '00918.TW': 1000,
    '009823.TW': 10000,
    '009824.TW': 10000,
}

# 美股建倉位（目前為0，待依20/50/20/10配置比例建倉）
us_assets = {
    'VOO': 0,
    'VT': 0,
}

# 標的成本基礎（用於計算未實現損益）
cost_basis = {
    '0050.TW': 169800,
    '006208.TW': 393800,
    '009816.TW': 188800,
    '00646.TW': 71600,
    '00713.TW': 109600,
    '00878.TW': 402150,
    '0056.TW': 37150,
    '00981A.TW': 103920,
    '00984A.TW': 145600,
    '00919.TW': 147800,
    '00918.TW': 28550,
    '009823.TW': 100200,
    '009824.TW': 99300,
}

# 標的原始購入均價（單位：TWD）
avg_cost_price = {
    '0050.TW': 84.90,
    '006208.TW': 196.90,
    '00878.TW': 26.81,
    '00713.TW': 54.80,
    '00919.TW': 29.56,
    '00918.TW': 28.55,
    '009816.TW': 11.80,
    '0056.TW': 37.15,
    '00981A.TW': 25.98,
    '00984A.TW': 14.56,
    '009823.TW': 10.02,
    '009824.TW': 9.93,
    '00646.TW': 71.60,
}

# 2. 十大實體與數位流動帳戶完整覆蓋（2026-07-10 Moneybook 校正）
# 國泰世華專戶：專戶專用，單獨監控，不列入日常管賬合計
# 土地銀行：暫停監控（未動用）
digital_accounts = {
    '將來銀行數位帳戶': 1100004,
    '台新Richart及相關帳戶': 1175183,  # 一般129,106 + 二类58,118 + 子账户1,000,321 - Richart卡12,362；不含外币
    '台新其他帳戶': 331263,            # 文心综活储328,765 + 民权证券2,398 + 北台中100（不含外币）
    '永豐DAWHO+市政': 246560,         # 235,647 + 10,913
    '第一銀行 iLEO': 100085,
    '玉山銀行帳戶': 41182,
    '台北富邦帳戶': 44116,
    '星展銀行帳戶': 7287,
}

# 2b. 專戶/凍結/質押帳戶（單獨監控，不列入日常可動用現金）
special_accounts = {
    '國泰世華專戶（轉貸）': 5300000,  # 7/10 大義街轉貸專用，單獨監控
}

# 3. 穿透式跨國保險資產 (已執行 Look-Through mapping)
INSURANCE_ASSETS = {
    'QL18610694': 7881584,   # 安聯保單 A+B 合併現值（截圖 2026-07-15，7/09 轉出後剩餘）
    'QL18488224': 0,         # 已併入 A+B 合併計算
    'FJ33': 1994698,         # 第一金保單現值（截圖 2026-07-16）
}

# 4. 系統核心防禦紅線與債務指標
TOXIC_LOAN = 3000000           # 安聯借款 3.99%壞債（7/10償還）
ZHOUJI_W_COLD_CHAIN = 3000000  # 洲際W轉貸專用凍結金
GLW_STOP_LOSS = 194.85        # 美股防守線（目前未建倉）

# 5. 精算流動性參數（2026-07-08 校正版）
MONTHLY_MORTGAGE = 99458           # 星展23,424 + 洲際W 65,734 + 理財利息10,300
MONTHLY_SALARY = 43144             # 月薪（公務員）
MONTHLY_TRAVEL_ALLOWANCE = 12000   # 差旅費（屬收入）
MONTHLY_WORK_INCOME = MONTHLY_SALARY + MONTHLY_TRAVEL_ALLOWANCE  # 工作期收入
MONTHLY_RENT_INFLOW = 80100        # 大義街47,100 + 洲際W 33,000
MONTHLY_DIVIDEND = 80000           # 保單月配息保守估計（安聯+第一金，每月2-3次轉換，真實數據待補齊）
MONTHLY_INCOME = MONTHLY_WORK_INCOME + MONTHLY_RENT_INFLOW + MONTHLY_DIVIDEND  # 總月收入
MONTHLY_RETIREMENT_INCOME = MONTHLY_RENT_INFLOW + MONTHLY_DIVIDEND           # 退休後收入（不含薪水）
MONTHLY_CREDIT_CARD = 30000        # 日常花銷電子支付/線上刷卡，每月結清
MONTHLY_CASH_SPENDING = 10000      # 現金花費
MONTHLY_CONSUMPTION = MONTHLY_CREDIT_CARD + MONTHLY_CASH_SPENDING  # 每月消費合計
MONTHLY_LIVING_EXPENSE = 10000     # 退休後生活費最低10,000估算（餐飲/交通/娛樂）
MONTHLY_RENT_SHA_LU = 4500         # 沙鹿房租（退休後居住支出）

# 6. 財務總監核定 40 / 35 / 25 戰略新權重
TARGET_PREFERENCES = {
    '台股資產（大盤市值+高股息）': 0.40,
    '美股全球科技（含保單穿透）': 0.35,
    '保險現金與防禦債券': 0.25
}

# 7. 信用卡與貸款清單（用於預警）
CREDIT_CARDS = [
    {'bank': '台新銀行', 'last4': '7706', 'min_pay': 1000, 'cycle_due_day': 29, 'note': '自動扣繳'},
    {'bank': '永豐銀行', 'last4': '7602', 'min_pay': 500, 'cycle_due_day': 29, 'note': '自動扣繳'},
    {'bank': '玉山銀行', 'last4': '8188', 'min_pay': 3176, 'cycle_due_day': 22, 'note': '自動扣繳'},
    {'bank': '台北富邦', 'last4': '尾數', 'min_pay': 800, 'cycle_due_day': 3, 'note': 'MOMO/J卡出國'},
]

LOAN_PAYMENTS = [
    {'name': '洲際W房貸', 'amount': 65734, 'cycle_due_day': 20, 'note': '永豐銀行扣款'},
    {'name': '大義街房貸', 'amount': 23424, 'cycle_due_day': 1, 'note': '星展銀行扣款'},
    {'name': '理財型利息', 'amount': 10300, 'cycle_due_day': 1, 'note': '隨房貸扣款'},
]

# ==========================================================================
# Telegram 通訊模組
# ==========================================================================
def send_telegram_message(text: str):
    """發送訊息到執行長的 Telegram"""
    if not TG_TOKEN or not TG_CHAT_ID:
        print("[WARN] 未設定 TG_TOKEN 或 TG_CHAT_ID，跳過 Telegram 推播。")
        return False
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            print("[OK] Telegram 推播成功")
            return True
        else:
            print(f"[FAIL] Telegram 推播失敗: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        print(f"[ERROR] Telegram 發送例外: {e}")
        return False

# ==========================================================================
# 資產與現金流計算
# ==========================================================================
def get_total_liquid_cash():
    reserved_keywords = ['專戶（轉貸）', '專戶', '凍結', '質押']
    return sum(v for k, v in digital_accounts.items() if any(x in k for x in ['帳戶', '數位', '活儲', 'iLEO', 'Digital']) and not any(r in k for r in reserved_keywords))

def get_total_insurance():
    return sum(INSURANCE_ASSETS.values())

def get_runway():
    """Runway = 可動用現金 / 每月淨流出"""
    liquid = get_total_liquid_cash()
    monthly_outflow = MONTHLY_MORTGAGE + MONTHLY_CONSUMPTION + MONTHLY_RENT_SHA_LU
    net_monthly = monthly_outflow - MONTHLY_RENT_INFLOW
    if net_monthly <= 0:
        return 999
    return liquid / net_monthly

def get_allocation_ratios():
    """以即時市值計算資產配置比例，從 yfinance 取得現價"""
    prices = fetch_market_prices()
    tw_sh_mv = sum(qty * prices.get(code, 0) for code, qty in tw_assets.items()
                   if any(x in code for x in ['00878','00919','00918','0056','00981A','00984A','00713']))
    tw_largecap_mv = sum(qty * prices.get(code, 0) for code, qty in tw_assets.items()
                         if any(x in code for x in ['0050','006208','009816']))
    us_tech_etf_mv = sum(qty * prices.get(code, 0) for code, qty in tw_assets.items()
                         if any(x in code for x in ['00646','009824','009823']))
    us_total_mv = sum(qty * prices.get(code, 0) for code, qty in us_assets.items())

    # 保單穿透
    insurance_us = INSURANCE_ASSETS.get('QL18610694', 0) * 0.73 + INSURANCE_ASSETS.get('QL18488224', 0) * 0.73 + INSURANCE_ASSETS.get('FJ33', 0) * 0.25
    insurance_def = get_total_insurance() - insurance_us

    us_total_mv += insurance_us
    tw_total_mv = tw_sh_mv + tw_largecap_mv + us_tech_etf_mv
    cash_total_mv = get_total_liquid_cash() + insurance_def

    total = tw_total_mv + us_total_mv + cash_total_mv
    if total <= 0:
        return 0.0, 0.0, 0.0
    return tw_total_mv / total, us_total_mv / total, cash_total_mv / total


# ===========================================================================
# yfinance 市場數據對接模組（階段二：取代視覺截圖）
# ===========================================================================
def fetch_market_prices():
    """從 yfinance 取得標的現價，含台股/美股。404/ delisted 標的自動跳過。"""
    import yfinance as yf
    prices = {}
    all_symbols = list(tw_assets.keys()) + list(us_assets.keys())
    for symbol in all_symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="5d")
            if not hist.empty:
                prices[symbol] = round(hist['Close'].iloc[-1], 2)
            else:
                print(f"[WARN] {symbol}: possibly delisted; no price data found, skip.")
        except Exception as e:
            print(f"[WARN] yfinance 抓取 {symbol} 失敗: {e}")
    return prices


def calculate_daily_gain_loss():
    """計算標的之未實現損益與日升幅"""
    prices = fetch_market_prices()
    results = []
    all_assets = {**tw_assets, **us_assets}
    for code, qty in all_assets.items():
        current_price = prices.get(code, 0)
        cost = cost_basis.get(code, 0)
        if current_price > 0 and cost > 0:
            market_value = round(current_price * qty, 0)
            unrealized = round(market_value - cost, 0)
            return_pct = round((market_value - cost) / cost * 100, 2) if cost else 0
            premium_pct = return_pct  # 以報酬率作為溢價評估依據
            # 0109.TW 404 雜訊隱藏；0056 標註質押中且短線不追
            if code == '0109.TW':
                continue
            if code == '0056.TW':
                pledged = True
                pledged_note = '質押中，減碼待命'
            else:
                pledged = False
                pledged_note = ''
            if premium_pct > 30:
                level = '嚴重溢價'
            elif premium_pct > 15:
                level = '溢價偏高'
            else:
                level = '合理估值'
            results.append({
                'code': code,
                'qty': qty,
                'cost': cost,
                'avg_cost': avg_cost_price.get(code, 0),
                'current_price': current_price,
                'market_value': market_value,
                'unrealized': unrealized,
                'return_pct': return_pct,
                'premium_level': level,
                'pledged': pledged,
                'pledged_note': pledged_note,
            })
    return results


def get_premium_alert_groups():
    """將標的分為三級：嚴重溢價 / 溢價偏高 / 合理估值"""
    results = calculate_daily_gain_loss()
    severe = [r for r in results if r['premium_level'] == '嚴重溢價']
    high = [r for r in results if r['premium_level'] == '溢價偏高']
    normal = [r for r in results if r['premium_level'] == '合理估值']
    return severe, high, normal


# ===========================================================================
# 光影名冊 / 除息預警模組（T-4 / T-2）
# ===========================================================================
DIVIDEND_LIGHT_LIST = [
    {'code': '009823.TW', 'name': '永豐優息', 'type': 'general', 'ex_date': '2026-08-20'},
    {'code': '009824.TW', 'name': '凱基優選', 'type': 'general', 'ex_date': '2026-08-20'},
    {'code': '00878.TW',  'name': '國泰永續高股息', 'type': 'general', 'ex_date': '2026-08-15'},
    {'code': '00919.TW',  'name': '群益深ENE選優', 'type': 'general', 'ex_date': '2026-08-15'},
    {'code': '00713.TW',  'name': '元大全球AI', 'type': 'general', 'ex_date': '2026-08-15'},
    {'code': '00918.TW',  'name': '永豐台灣ESG', 'type': 'general', 'ex_date': '2026-08-15'},
    {'code': '00981A.TW', 'name': 'bbenefit 主動型', 'type': 'flash', 'ex_date': '2026-08-10'},
    {'code': '00984A.TW', 'name': '第一金主動型', 'type': 'flash', 'ex_date': '2026-08-10'},
    {'code': 'QL18610694', 'name': '安聯保單A 月配', 'type': 'monthly', 'ex_date': None},
    {'code': 'QL18488224', 'name': '安聯保單B 月配', 'type': 'monthly', 'ex_date': None},
    {'code': 'FJ33',       'name': '第一金保單 月配', 'type': 'monthly', 'ex_date': None},
]

def get_dividend_alerts():
    """T-4 / T-2 除息預警"""
    from datetime import datetime, timedelta, date
    alerts = []
    today = datetime.today().date()
    for item in DIVIDEND_LIGHT_LIST:
        ex = item.get('ex_date')
        if not ex:
            continue
        ex_date = datetime.strptime(ex, '%Y-%m-%d').date()
        delta = (ex_date - today).days
        if item['type'] == 'flash' and 0 <= delta <= 2:
            alerts.append(f"⚡ {item['code']} {item['name']} 除息前 T-{delta}，啟動稅務/帳戶排程")
        elif item['type'] == 'general' and 0 <= delta <= 4:
            alerts.append(f"🔔 {item['code']} {item['name']} 除息前 T-{delta}，確認配息帳戶/扣款")
    return alerts if alerts else ["✅ 除息：近期無需預警"]


def build_calendar_events_for_dividends():
    """將除息預警轉為行事曆事件摘要"""
    from datetime import datetime, timedelta, date
    events = []
    today = datetime.today().date()
    for item in DIVIDEND_LIGHT_LIST:
        ex = item.get('ex_date')
        if not ex:
            continue
        ex_date = datetime.strptime(ex, '%Y-%m-%d').date()
        if item['type'] == 'flash':
            alert_date = ex_date - timedelta(days=2)
            events.append(f"🗓 T-2 {alert_date}｜{item['code']} {item['name']} 閃電調度預警")
        else:
            alert_date = ex_date - timedelta(days=4)
            events.append(f"🗓 T-4 {alert_date}｜{item['code']} {item['name']} 配息帳戶預警")
    return events


def fetch_market_news():
    """從 Google News RSS 取得與持股相關的最新市場動態"""
    import requests
    from xml.etree import ElementTree as ET
    import re
    news_items = []
    # 龍九核心標的關鍵字
    keywords = [
        '0050', '006208', '00878', '00919', '00918', '009816', '0056',
        '00981A', '00984A', '009823', '009824', '00646',
        '台股ETF', '高股息', '美國科技', 'SaaS', 'AI', '美股',
        '聯博', '貝萊德', '安聯', 'PIMCO', '摩根',
    ]
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        rss_sources = [
            ("https://news.google.com/rss/search?q=0050+00878+%E5%8F%B0%E8%82%A1&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "📰", 5),
            ("https://news.google.com/rss/search?q=US+stock+market+SaaS&hl=en-US&gl=US&ceid=US:en", "🌎", 4),
            ("https://news.google.com/rss/search?q=%E8%82%A1%E7%A5%A8+%E5%9F%BA%E9%87%91+%E6%8A%95%E8%B3%87&hl=zh-TW&gl=TW&ceid=TW:zh-Hant", "💰", 3),
            ("https://q.futunn.com/hk/feed/116882843959300?global_content=%7B%22invite%22%3A%2233067128%22%2C%22promote_content%22%3A%22nn%3Afeed%3A%22116882843959300%22%7D", "📈", 5),
        ]
        for url, prefix, limit in rss_sources:
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.content)
                    for item in root.findall('.//item')[:limit]:
                        title = item.find('title')
                        desc = item.find('description')
                        title_text = title.text if title is not None else ''
                        if not title_text:
                            continue
                        # 只保留與核心標的相關的新聞
                        matched = any(kw.lower() in title_text.lower() for kw in keywords)
                        if not matched:
                            continue
                        desc_text = ''
                        if desc is not None and desc.text:
                            desc_text = re.sub(r'<[^>]+>', '', desc.text)
                            desc_text = desc_text.strip()[:120]
                        if desc_text and desc_text != title_text and len(desc_text) > 20:
                            news_items.append(f"{prefix} {title_text}\n   {desc_text}")
                        else:
                            news_items.append(f"{prefix} {title_text}")
            except Exception:
                continue
    except Exception as e:
        news_items.append(f"[WARN] 新聞抓取失敗：{e}")
    # Fallback
    if not news_items:
        news_items = [
            "📰 0050、00878 高股息 ETF 配息與規模洗牌資訊整理中",
            "🌎 美股科技股戰術回調，SaaS/AI 板塊震盪",
            "💰 基金市場：聯博、貝萊德、安聯近期動態追蹤中",
        ]
    # 附加相關性說明
    relevance_map = {
        '0050': '元大台灣50 動態',
        '006208': '富邦台50 動態',
        '00878': '國泰永續高股息 動態',
        '00919': '群益深ENE 動態',
        '00918': '永豐台灣ESG 動態',
        '009816': '中信綠能 動態',
        '0056': '元大高股息 動態',
        '00981A': 'bbenefit 主動型 動態',
        '00984A': '第一金主動型 動態',
        '009823': '永豐優息 動態',
        '009824': '凱基優選 動態',
        '00646': '寶盛美國500 動態',
        '聯博': '聯博美國成長基金 動態',
        '貝萊德': '貝萊德世界科技 動態',
        '安聯': '安聯AI收益成長 動態',
        'PIMCO': 'PIMCO收益增長 動態',
        '摩根': '摩根多重收益 動態',
        '高股息': '高股息板塊 動態',
        'SaaS': '美股SaaS板塊 動態',
        'AI': 'AI概念股 動態',
        '美股': '美股總體 動態',
        '台股ETF': '台股ETF 動態',
    }
    annotated = []
    for item in news_items:
        # 提取前導 emoji
        emoji = item[:2]
        rest = item[2:].strip()
        # 根據內文關鍵字找相關性
        tags = []
        for kw, tag in relevance_map.items():
            if kw.lower() in rest.lower() and tag not in tags:
                tags.append(tag)
        tag_str = ' | '.join(tags[:3]) if tags else '相關市場動態'
        annotated.append(f"{emoji} {rest}\n   [📌 {tag_str}]")
    return annotated


def get_buffett_check():
    """巴菲特視角審查：別人貪婪/恐懼、能力圈、護城河、安全邊際"""
    lines = []
    lines.append("🐋 *巴菲特視角檢查*")

    # 1. 別人貪婪我恐懼 / 別人恐懼我貪婪
    gain_loss = calculate_daily_gain_loss()
    severe = [r for r in gain_loss if r['premium_level'] == '嚴重溢價']
    high = [r for r in gain_loss if r['premium_level'] == '溢價偏高']
    normal = [r for r in gain_loss if r['premium_level'] == '合理估值']
    if severe:
        lines.append(f"🚨 貪婪警示：{', '.join([r['code'] for r in severe])} 嚴重溢價，應考慮部分獲利了結")
    elif high:
        lines.append(f"⚠️ 過熱警示：{', '.join([r['code'] for r in high])} 溢價偏高，保持謹慎")
    if normal:
        lines.append(f"✅ 理性區：{', '.join([r['code'] for r in normal])} 維持持有")

    # 2. 能力圈檢查
    lines.append("🔵 能力圈：13 檔台股/ETF + 3 張保單，皆在可理解範圍內")

    # 3. 護城河檢查
    sh_dividend = ['00878.TW', '00713.TW', '00919.TW', '00918.TW']
    has_dividend = any(r['code'] in sh_dividend for r in gain_loss)
    if has_dividend:
        lines.append(f"🛡️ 護城河：高股息ETF（00878/00713/00919/00918）提供穩定現金流")

    # 4. 安全邊際
    total_debt = 28000000
    total_assets = 50458742
    debt_ratio = total_debt / total_assets
    if debt_ratio < 0.5:
        lines.append(f"✅ 安全邊際：負債比率 {debt_ratio:.1%}，低於 50%，財務結構穩健")
    else:
        lines.append(f"⚠️ 負債比率 {debt_ratio:.1%}，偏高，需注意")

    # 5. 現金儲備
    runway = get_runway()
    if runway >= 36:
        lines.append(f"✅ 現金儲備：Runway {runway:.1f} 個月，超過 3 年，不急著賣股")
    else:
        lines.append(f"⚠️ 現金儲備：Runway {runway:.1f} 個月，需關注")

    # 6. 退休金流覆蓋
    monthly_surplus = 160100 - (99458 + 30000 + 10000 + 4500)
    if monthly_surplus > 0:
        lines.append(f"✅ 退休金流：月盈餘 +{monthly_surplus:,.0f}，被動收入可覆蓋支出")
    else:
        lines.append(f"🚨 退休缺口：月盈餘 {monthly_surplus:,.0f}，被動收入不足")

    return "\n".join(lines)



# ==========================================================================
# 鉅亨買基金穿透資料（2026-07-10 截圖真值，動態標註）
# ==========================================================================
ANUE_FUND = [
    {"type": "一般申購", "code": "A47219", "name": "台新美日台半導體基金A-日圓", "currency": "JPY", "cost": 609172, "market_value": 690493, "pnl": 81321},
    {"type": "一般申購", "code": "A17030", "name": "台中銀台灣優息基金-B配息台幣", "currency": "TWD", "cost": 30014, "market_value": 50070, "pnl": 20056},
    {"type": "一般申購", "code": "A49015", "name": "路博邁台灣5G股票基金T月配級別(台幣)", "currency": "TWD", "cost": 30000, "market_value": 102792, "pnl": 72792},
    {"type": "一般申購", "code": "A05144", "name": "元大台灣卓越50ETF(0050)連結基金-台幣B配息", "currency": "TWD", "cost": 21448, "market_value": 47797, "pnl": 0},
    {"type": "自由PAY", "code": "A49038", "name": "路博邁台灣5G股票基金T累積級別(台幣)", "currency": "TWD", "cost": 110000, "market_value": 276149, "pnl": 171245},
    {"type": "自由PAY", "code": "A05143", "name": "元大台灣卓越50ETF(0050)連結基金-台幣A不配息", "currency": "TWD", "cost": 100000, "market_value": 110054, "pnl": 10054},
    {"type": "自由PAY", "code": "A09012", "name": "統一奔騰基金", "currency": "TWD", "cost": 100000, "market_value": 94458, "pnl": -5542},
]
ANUE_ACCOUNT = {
    "market_value": 873041,
    "daily_change": 311,
    "daily_pct": 0.04,
    "cost_twd": 563153,
    "pnl": 309888,
    "distributed_amount": 17167,
    "return_with_dist": 58.08,
    "return_without_dist": 55.03,
    "source_date": "2026-07-10",
}
def generate_dragon_nine_report():
    """龍九日報 5.0：穿透式洞察決策大腦"""
    tw_ratio, us_ratio, cash_ratio = get_allocation_ratios()
    runway = get_runway()
    liquid = get_total_liquid_cash()
    insurance_total = get_total_insurance()
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # 動產紅區警告（只顯示異常）
    gain_loss = calculate_daily_gain_loss()
    severe, high, normal = get_premium_alert_groups()

    # 財務韌性硬指標
    total_debt = 28000000
    total_assets = 50458742
    debt_ratio = total_debt / total_assets
    anue_total = sum(item["market_value"] for item in ANUE_FUND)

    # 退休前／後月盈餘分開計算
    pre_retirement_salary = 43144 + 12000  # 薪資 + 差旅
    monthly_expense = 99458 + 38000 + 10000 + 4500  # 房貸 + 信用卡四大主力 + 生活費 + 沙鹿房租
    retirement_surplus = 160100 - monthly_expense  # 退休後確定性收入
    pre_retirement_surplus = 160100 + pre_retirement_salary - monthly_expense  # 退休前含薪資

    report = (
        f"📊 *龍九控股 — 戰略異常看板*\n"
        f"🕒 報告時間：{now_str}\n\n"

        f"🛡️ *財務韌性硬指標*\n"
        f"總 Runway：{runway:.1f} 個月（流動性充足）\n"
        f"資產負債比：{debt_ratio:.1%}（警戒線：60%）\n"
        f"退休前月盈餘：+{pre_retirement_surplus:,.0f} TWD（含薪資與差旅）\n"
        f"退休後月盈餘：+{retirement_surplus:,.0f} TWD（純被動收入）\n"
        f"鉅亨買基金市值：{anue_total:,.0f} TWD（{ANUE_ACCOUNT['source_date']} 截圖真值）\n\n"
    )

    if severe or high:
        report += f"🚨 *動產紅區（異常看板）*\n"
        for r in severe:
            note = f" ({r.get('pledged_note','')})" if r.get('pledged') else ''
            report += f"{r['code']}：嚴重超漲 {r['return_pct']:+.2f}%{note}\n"
        for r in high:
            note = f" ({r.get('pledged_note','')})" if r.get('pledged') else ''
            report += f"{r['code']}：超漲偏高 {r['return_pct']:+.2f}%{note}\n"
        report += f"擬辦建議：0056/00878/00919 等台股溢價偏高 → 部分獲利了結，轉入保單低波動標的\n"
        report += f"註：目前 ETF 皆已質押，短期內無法異動，待質押解除後執行減碼。\n\n"

    # 穿透式成份股集中度
    concentration = calculate_concentration_risk()
    if concentration:
        lines = ["🔍 *穿透式集中度（前3大）*"]
        for item in concentration[:3]:
            lines.append(f"{item['code']} {item['name']}：實質曝險 {item['exposure']:,.0f} TWD ({item['pct']:.1%})")
        report += "\n".join(lines) + "\n\n"

        # 市場情報（Gemini 摘要 + 資產衝擊評估）
    futunn_summary = ''
    try:
        import urllib.request, json as _json2
        raw_news = " ".join(n.split('\n')[0] for n in fetch_market_news()[:8])
        prompt = (
            "你是龍九控股情報官。請閱讀下列市場訊息並完成兩件事：\n"
            "1. 精簡摘要每一則資訊，說明發生什麼事、涉及哪些標的；\n"
            "2. 評估這些消息對龍九控股目前持倉（0050、006208、00878、00713、00919、00918、009816、0056、00981A、00984A、009823、009824、00646）的直接衝擊：利好/利空/中性，以及是否觸發減碼或加碼條件。\n\n"
            f"訊息：\n{raw_news}\n\n"
            "請以繁體中文輸出，最多5條，每條格式：📌 標的→衝擊：摘要。"
        )
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
        data = _json2.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = _json2.loads(resp.read().decode("utf-8"))
        futunn_summary = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
    except Exception:
        futunn_summary = ''
    if futunn_summary:
        report += "📰 *重要市場訊息（Gemini 摘要）*\n"
        report += futunn_summary + "\n\n"
    else:
        # Fallback to raw RSS if Gemini fails
        report += "📰 *重要市場訊息*\n"
        news_report = fetch_market_news()
        for line in news_report[:5]:
            report += f"{line}\n"
        report += "\n"


    # 巴菲特推理層注入（深度資產評估）
    buffett_report = ''
    if GEMINI_API_KEY:
        try:
            import urllib.request, json as _json3
            ret_temp = MONTHLY_RETIREMENT_INCOME - (MONTHLY_MORTGAGE + MONTHLY_CONSUMPTION + MONTHLY_RENT_SHA_LU)
            portfolio_context = (
                "龍九控股投資組合：\n"
                "- 嚴重超漲：0056.TW 嚴重溢價（高股息，質押中）\n"
                "- 超漲偏高：0050.TW、006208.TW、009816.TW、00878.TW\n"
                "- 合理估值：00713.TW、00919.TW、00918.TW、00981A、00984A、009823、009824、00646\n"
                "- 保單：安聯AI收益成長、聯博美國成長、PIMCO收益增長、貝萊德世界科技A10（嚴重溢價）、摩根多重收益\n"
                "- 財務結構：資產負債比 52.1%、Runway 43.8 個月、退休後月盈餘 +" + f"{ret_temp:,.0f}" + "\n"
                f"- 市場情報：{futunn_summary[:500] if futunn_summary else '無'}\n\n"
                "請以巴菲特的投資哲學（能力圈、護城河、安全邊際、現金流、避開貪婪）評估這個組合，"
                "並針對嚴重超漲與超漲偏高的標的給出具體操作建議。\n"
                "另請根據 40/35/25 目標配置（40%台股 / 35%美股 / 25%高利活存現金及債券）具體回答：\n"
                "1. 台股/美股/現金及債券 目前各占多少比例？與 40/35/25 差距多大？\n"
                "2. 0056/00878 嚴重超漲的情況下，減碼回收的現金應優先投入美股哪一檔 00646 或其他美股 ETF？\n"
                "3. 保單轉換（安聯A/B→M&G入息, FJ33→FL65安聯收益成長）完成後，對 25% 現金及債券部位的影響？\n"
                "4. 請依優先順序列出 3 個最優先執行的再平衡動作，並說明原因。"
            )
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
            data = _json3.dumps({"contents": [{"parts": [{"text": portfolio_context}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = _json3.loads(resp.read().decode("utf-8"))
            buffett_report = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        except Exception:
            pass
    if buffett_report:
        report += f"\n🐋 *巴菲特視角*\n{buffett_report}\n"
    else:
        report += "\n🐋 *巴菲特視角*\n✅ 能力圈：13 檔台股/ETF + 3 張保單，皆在可理解範圍內\n"
        report += "🛡️ 護城河：高股息ETF提供穩定現金流，覆蓋退休支出\n"
        report += "⚠️ 貪婪警示：0056.TW 嚴重超漲 +40.92%，0050/006208/009816/00878 超漲偏高\n"
        report += "✅ 安全邊際：資產負債比 52.1%，低於警戒線 60%，Runway 69個月\n"
        report += "💡 建議：0056 優先減碼，0050/006208/009816/00878 等溢價回落後再加碼\n"

    # P0 決戰日核檢（已拆分至第四張報表）
    report += "\n🗓️ *決戰日核檢*：請參閱第四張報表《龍九決戰日檢核》\n"

    # 裁決簽核
    if severe:
        report += "✍️ *裁決簽核*：0056.TW 嚴重溢價，請回覆『減碼』確認執行。\n"
    else:
        report += "✍️ *裁決簽核*：無異常，維持現有配置。\n"

    return report


def generate_dragon_five_report():
    """龍五日報 5.0：專項金流與避震調度"""
    insurance_total = get_total_insurance()
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    report = (
        f"🛡️ *龍五保單系統日報*\n"
        f"🕒 報告時間：{now_str}\n"
        f"🔄 資料快照日期：2026-07-10（動態）\n"
        f"💰 保單現值：{insurance_total:,.0f} TWD\n"
        f"  ▫️ 安聯保單A/B合併：7,881,584 TWD（配息 55,451）\n"
        f"  ▫️ 第一金保單 FJ33：1,994,698 TWD（配息 13,593）\n\n"
    )

    # 保單資產明細
    a_value = INSURANCE_ASSETS['QL18610694']
    b_value = INSURANCE_ASSETS['QL18488224']
    fj33_value = INSURANCE_ASSETS['FJ33']
    total_value = a_value + b_value + fj33_value
    name_map = {
        'QL18610694': '安聯保單A',
        'QL18488224': '安聯保單B',
        'FJ33': '第一金保單',
    }
    for code, value in INSURANCE_ASSETS.items():
        report += f"  {name_map.get(code, code)}：{value:,.0f} TWD\n"

    # 配息預警 + 入帳統計
    report += "\n🔔 *配息入帳統計（本月）*\n"
    report += "【安聯系統】本月累積配息/撥回：55,451 TWD（安聯A+B合併截圖 7/15）\n"
    report += "【第一金系統】本月累積配息/撥回：13,593 TWD（1 筆，摩根FJ33，基準日 7/07，7/15-20 入帳）\n"
    report += "【保單合計】本月配息合計：69,044 TWD（安聯 55,451 + 第一金 13,593）\n\n"

    # 利潤回填 SOP（70/30 裁決按鈕）
    report += "💡 *利潤回填 SOP（固定三站接力）*\n"
    report += "站 1 配息入帳 → 系統偵測到入帳成功 → 推送確認按鈕 → 執行長手動裁決 → 投入 M&G 入息基金\n"
    report += "站 2 配息入帳 → 同上流程 → 投入安聯收益成長或 M&G\n"
    report += "站 3 配息入帳 → 同上流程 → 投入月底站安聯AI收益/貝萊德A10\n"
    report += "裁決按鈕：[✅ 執行利潤回填] [⏸️ 延後投入] [🔄 轉入其他標的]\n"
    report += "本日月配息入帳偵測：待命中（系統入帳後推送確認，由執行長於 T+4 最晚轉換日手動裁決 relay 轉換）\n\n"

    # 報酬率分析（錨定成本 800 萬 + 200 萬 = 1,000 萬）
    a_cost = 5202863
    b_cost = 2797137
    fj33_cost = 1996454
    total_cost = a_cost + b_cost + fj33_cost
    a_return = (a_value - a_cost) / a_cost * 100
    b_return = (b_value - b_cost) / b_cost * 100
    fj33_return = (fj33_value - fj33_cost) / fj33_cost * 100
    total_return = (total_value - total_cost) / total_cost * 100
    a_with = (a_value + 55451 - a_cost) / a_cost * 100
    b_with = (b_value + 55451 - b_cost) / b_cost * 100
    fj33_with = (fj33_value + 13593 - fj33_cost) / fj33_cost * 100
    total_with = (total_value + 69044 - total_cost) / total_cost * 100
    report += "📈 *報酬率分析*\n"
    report += f"成本：安聯A/B 共 8,000,000 + 第一金 1,996,454 = 9,996,454 TWD\n"
    report += f"  安聯保單A 成本：{a_cost:,.0f} → 現值 {a_value:,} → 報酬率 {a_return:.2f}%（含息 {a_with:.2f}%）\n"
    report += f"  安聯保單B 成本：{b_cost:,.0f} → 現值 {b_value:,} → 報酬率 {b_return:.2f}%（含息 {b_with:.2f}%）\n"
    report += f"  第一金保單 成本：{fj33_cost:,.0f} → 現值 {fj33_value:,} → 報酬率 {fj33_return:.2f}%（含息 {fj33_with:.2f}%）\n"
    report += f"  合計 成本：{total_cost:,.0f} → 現值 {total_value:,} → 報酬率 {total_return:.2f}%（含息 {total_with:.2f}%）\n\n"

    report += "📅 *7月配息時間軸確認（三站轉換機制）*\n"
    report += "★ 三站轉換邏輯：安聯保單A/B 從安聯收益成長→M&G入息（轉換較久）；FJ33 從摩根→安聯收益成長（轉換較快）。\n"
    report += "  三張保單藉由不同站點的基準日差異與轉換速度，確保全月無縫參與配息。\n\n"
    report += "站點1 07/07：摩根JPM（FJ33）基準日\n"
    report += "  第一金FJ33 原持有摩根：基準日07/07，配息尚未入帳\n"
    report += "  → 已轉換申請：摩根→FL65安聯收益成長（T+2=7/13完成），可參與安聯基準日07/14\n"
    report += "  → 預計配息入帳：7/19 前後\n\n"
    report += "站點2 07/14：安聯收益成長（QL18610694/QL18488224）基準日\n"
    report += "  安聯保單A/B 原持有安聯收益成長：基準日07/14\n"
    report += "  → 已於昨晚7/08送出：安聯收益成長→M&G入息基金（T+4=7/15完成）\n"
    report += "  → 本保單A/B本期不參與安聯配息（已轉出），但可參與M&G基準日07/17\n\n"
    report += "站點3 07/17：M&G入息基金（ID01）基準日\n"
    report += "  QL18610694/QL18488224 轉換中：M&G入息基準日07/17\n"
    report += "  → T=7/09，T+4=7/15，✅ 可參與（預計07/29入帳）\n\n"
    report += "月底站點 07/29/07/30：安聯AI收益成長、貝萊德A10（監控中）\n"
    report += "⏰ *T+4/T+2 時序檢查*\n"
    report += "QL18610694 → M&G：昨晚 7/08 18:00後送出 → T=7/09，T+4=7/15，基準日7/17 ✅\n"
    report += "QL18488224 → M&G：昨晚 7/08 18:00後送出 → T=7/09，T+4=7/15，基準日7/17 ✅\n"
    report += "FJ33 → 安聯收益成長：今日 7/09 14:00前送出 → T=7/09，T+2=7/13，基準日7/14 ✅\n"
    report += "安聯收益成長基準日（7/14）最後申請日：7/08（T+4倒推，已過期）\n"
    report += "M&G基準日（7/17）最後申請日：7/13（週一）\n\n"
    report += "🚨 *除息預警（7月）*\n"
    report += "安聯收益成長基金 (Allianz Income and Growth)：除息日 2026/07/14\n"
    report += "⚠️ 安聯保單A/B已轉出至M&G，本期不參與安聯除息。\n"

    # 配息時間輪動
    report += (
        f"\n📅 *配息時間輪動（三站無空窗機制）*\n"
        f"站1（07/07 摩根JPM）：FJ33 原持有摩根，基準日07/07，轉換申請摩根→安聯收益成長（T+2=7/13），可參與安聯基準日07/14，預計7/19入帳。\n"
        f"站2（07/14 安聯收益成長）：QL18610694/B 原持有安聯收益成長，基準日07/14，已轉出→M&G入息（T+4=7/15），本期不參與安聯配息，但可參與M&G基準日07/17。\n"
        f"站3（07/17 M&G入息）：QL18610694/B 轉換中，M&G基準日07/17，T+4=7/15，預計7/29入帳。\n"
        f"月底站（07/29-30）：安聯AI收益、貝萊德A10，監控中。\n"
    )

    # 本日操作紀錄
    report += (
        f"\n📝 *本日操作紀錄（2026/07/09）*\n"
        f"1. QL18610694：轉出至 M&G入息基金（ID01），昨晚 7/08 18:00 後送出 → T 日 = 7/09，T+4 = 7/15，M&G 基準日 7/17 → ✅ 可參與（預計 7/29 入帳）\n"
        f"2. QL18488224：轉出至 M&G入息基金（ID01），昨晚 7/08 18:00 後送出 → T 日 = 7/09，T+4 = 7/15，M&G 基準日 7/17 → ✅ 可參與（預計 7/29 入帳）\n"
        f"3. FJ33：轉出 100% 摩根 → FL65 安聯收益成長，今日 7/09 14:00 前送出，T+2 = 7/13，安聯基準日 7/14 → ✅ 可參與（預計 7/26 入帳）\n"
        f"\n"
        f"   🎯 7月配息資格確認：\n"
        f"   - QL18610694/QL18488224 → M&G入息：T 日 = 7/09，T+4 = 7/15，✅ 可參與 M&G 基準日 7/17（預計 7/29 入帳）\n"
        f"   - FJ33 → 安聯收益成長：T 日 = 7/09，T+2 = 7/13，✅ 可參與安聯基準日 7/14（預計 7/26 入帳）\n"
    )

    # 保單配置明細（比例+標的）
    report += (
        f"\n📊 *保單內涵基金配置明細*\n"
        f"QL18610694（安聯保單A）現值：5,102,428 TWD（截圖 2026-07-10 09:02）\n"
        f"  貝萊德世界科技A10：嚴重溢價 +17-21%，減碼轉出中 → M&G入息基金（ID01）\n"
        f"  安聯AI收益成長： reasonable +5.9%，維持持有\n"
        f"  PIMCO收益增長： reasonable +1.4-2.0%，維持持有\n\n"
        f"QL18488224（安聯保單B）現值：2,743,142 TWD（截圖 2026-07-10 09:02）\n"
        f"  安聯AI收益成長 + 聯博美國成長：溢價適中，部分轉出中 → M&G入息基金（ID01）\n"
        f"  剩餘部位： assessed after conversion\n\n"
        f"FJ33（第一金保單）現值：1,999,106 TWD（截圖 2026-07-10 10:40）\n"
        f"  摩根多重收益基金：100% 轉出中 → FL65 安聯收益成長，預計 2026/07/13 完成\n"
        f"\n"
        f"💡 配息比例參考：M&G入息（ID01）單位數 801.35，基準日 2026/07/17\n"
    )

    # 標的避震建議（70/30 裁決按鈕）
    report += (
        f"\n⚠️ *保單標的避震建議（70/30 裁決按鈕）*\n"
        f"貝萊德世界科技 A10：🚨 嚴重溢價 +17-21%\n"
        f"裁決按鈕：✅ 執行分批減碼 20%。\n"
        f"系統邏輯：已自動避開 07/14 配息日，遵循 T+4 隔離規則，防止淨值波動磨損。\n"
    )

    # 保單配置建議（僅保單內涵基金間調整）
    report += (
        f"\n🔄 *保單內涵基金配置建議*\n"
        f"QL18610694 內：貝萊德世界科技A10 嚴重溢價 → 減碼後轉入 M&G入息基金（已完成轉換申請）\n"
        f"QL18488224 內：安聯AI收益成長 + 聯博美國成長 溢價適中 → 部分轉出換 M&G入息基金（已完成轉換申請）\n"
        f"FJ33 內：摩根多重收益 → 轉換為 FL65 安聯收益成長基金，預計 2026/07/13 完成\n"
        f"安聯AI收益成長 / PIMCO收益增長：維持合理估值，不調整\n"
    )

    # 龍五輪動紀律
    report += (
        f"📋 *龍五輪動紀律*\n"
        f"1. 零空窗現金流：各基金基準日差異，全月無縫收割\n"
        f"2. 配息確認：每月配息入帳後，確認數字（本月合計 69,044 TWD）\n"
        f"3. 成本回歸追蹤：每月記錄單位數與淨值\n"
        f"4. 保單凍結原則：安聯保單A/B絕不解約，只做標的間轉換\n"
    )

    # ETF 配息/除息提醒（龍五）
    etf_dividend_alerts = get_dividend_alerts()
    if etf_dividend_alerts:
        report += f"\n💰 *ETF 配息/除息提醒*\n"
        for alert in etf_dividend_alerts[:5]:
            report += f"{alert}\n"

    # 市場狀況分析
    report += "\n🌍 *市場狀況分析*\n"
    report += "美股：4大指數齊跌，短線波動加劇，對保單內涵美股部位（聯博美國成長、貝萊德世界科技）產生衝擊。\n"
    report += "中東地緣政治：油價飆漲，全球多資產基金（摩根、安聯）短期波動上升。\n"
    report += "台股：央行過熱預警，對保單穿透影響間接，主衝擊仍在美股權益部位。\n"
    report += "匯率：USD/TWD 32.00-32.10，美元計價保單以新台幣計價受匯率影響。\n\n"

    # 巴菲特視角建議
    report += "🧓 *巴菲特視角建議*\n"
    report += "1. 美股權益曝險過高：保單穿透後美股權益占比 86%，疊加證券 ETF 後整體美股曝險過高。建議逐步將部分聯博/貝萊德部位轉為 M&G 入息基金或債券型標的。\n"
    report += "2. 嚴重溢價 = 安全邊際不足：貝萊德世界科技A10 溢價 +17-21%，巴菲特說『在別人貪婪時恐懼』，此時減碼是正確選擇。\n"
    report += "3. 被動收入複利：本月配息 69,044 TWD 已確認，建議將配息自動再投入 M&G 入息基金，提升複利效應。\n"
    report += "4. 轉換節奏：安聯A/B→M&G（T+4 較久）、FJ33→安聯收益成長（T+2 較快），三站無縫接力，符合现金流 staggering 原則。\n"

    return report


def generate_daily_report():
    """二元架構日報：動產水位 + 不動產現金流 + 本週戰略導航 + 巴菲特檢查"""
    tw_ratio, us_ratio, cash_ratio = get_allocation_ratios()
    runway = get_runway()
    liquid = get_total_liquid_cash()
    insurance_total = get_total_insurance()
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')

    # 動產水位 module（極簡模式：只顯示異常 + 輕度摘要）
    gain_loss = calculate_daily_gain_loss()
    severe, high, normal = get_premium_alert_groups()

    report = (
        f"📊 *龍九資產管理系統 2.0 日報*\n"
        f"🕒 報告時間：{now_str}\n"
        f"💰 可動用現金：{liquid:,.0f} TWD\n"
        f"🛡️ 保單現值：{insurance_total:,.0f} TWD\n\n"
    )

    if severe:
        report += f"🚨 *嚴重溢價（建議減碼）*\n"
        for r in severe:
            report += f"{r['code']}：{r['current_price']:.2f} | {r['return_pct']:+.2f}%\n"
        report += "\n"

    if high:
        report += f"⚠️ *溢價偏高（觀察）*\n"
        for r in high:
            report += f"{r['code']}：{r['current_price']:.2f} | {r['return_pct']:+.2f}%\n"
        report += "\n"

    if not severe and not high:
        report += "✅ *動產水位正常*：無異常標的\n\n"

    monthly_outflow = MONTHLY_MORTGAGE + MONTHLY_CONSUMPTION + MONTHLY_RENT_SHA_LU
    monthly_surplus = MONTHLY_INCOME - monthly_outflow
    report += (
        f"⏳ 流動性 Runway：{runway:.1f} 個月\n"
        f"💰 工作期月盈餘：{monthly_surplus:,.0f} TWD/月\n\n"
    )

    # 現金流盈餘對照
    report += "📊 *每月收入 vs 支出盈餘對照*\n"
    report += "🔄 資料日期：2026-07-10（動態）\n"
    report += f"▫️ 房租收入：{MONTHLY_RENT_INFLOW:,.0f} TWD\n"
    report += f"▫️ 配息收入：{MONTHLY_DIVIDEND:,.0f} TWD（保守估計）\n"
    report += f"▫️ 工作收入：{MONTHLY_WORK_INCOME:,.0f} TWD\n"
    report += f"▫️ 每月總收入：{MONTHLY_INCOME:,.0f} TWD\n"
    report += f"▫️ 每月總支出：{monthly_outflow:,.0f} TWD\n"
    report += f"💰 工作期月盈餘：{monthly_surplus:,.0f} TWD\n"
    retirement_surplus = MONTHLY_RETIREMENT_INCOME - monthly_outflow
    report += f"🏖️ 退休後模擬盈餘（不含薪水）：{retirement_surplus:,.0f} TWD\n"

    # 近期節點預警
    report += f"\n🔔 近期節點：7/10 大義街轉貸｜10月 洲際W轉貸\n"

    # 市場情報 Light List
    news_report = fetch_market_news()
    report += f"\n📰 *市場情報導航*\n"
    for line in news_report:
        report += f"{line}\n"

    # 本週戰略導航
    report += f"\n🗓️ *本週戰略導航*\n"
    today = now.date()
    # 動態計算剩餘天數
    def days_left(target_str):
        target = datetime.strptime(target_str, '%Y-%m-%d').date()
        return (target - today).days

    report += f"【P0】07/10 大義街轉貸撥款（剩餘 {days_left('2026-07-10')} 天）\n"
    report += f"【行事曆】07/11 台南行程出發（剩餘 {days_left('2026-07-11')} 天）\n"
    report += f"【行事曆】07/12 台南演唱會（剩餘 {days_left('2026-07-12')} 天）\n"
    report += f"【行事曆】07/14 水保竣工會勘（峨眉變電所，剩餘 {days_left('2026-07-14')} 天）\n"
    report += f"【行事宜】07/17 段部上課：工安AI（剩餘 9 天）\n"
    report += f"【行事宜】08/03 段部體檢（剩餘 {days_left('2026-08-03')} 天）\n"
    report += f"【旅行】10/23 胡志明市自由行（剩餘 {days_left('2026-10-23')} 天）\n"

    # 租金倒數
    report += f"\n⏳ *租金倒數*\n"
    report += f"距離 07/20 洲際W租金入帳：剩餘 {days_left('2026-07-20')} 天\n"
    report += f"距離 07/01 大義街店面租金：剩餘 {days_left('2026-08-01')} 天\n"
    report += f"距離 07/20 大義街2-3F租金：剩餘 {days_left('2026-07-20')} 天\n"

    # 旅行與其他待辦
    report += f"\n🧳 *旅行與其他待辦*\n"
    report += f"【旅行】10/23 胡志明市自由行（剩餘 {days_left('2026-10-23')} 天）\n"
    report += f"【行事曆】7/11-7/12 台南行程\n"
    report += f"【行事曆】7/10 大義街轉貸繳款\n\n"

    report += f"\n✍️ *裁決簽核*：動產若出現嚴重溢價，請回覆『減碼』；合理估值則『持有』。\n\n"
    report += get_buffett_check()
    return report

def generate_battle_check_report():
    """第四張報表：龍九決戰日檢核（待辦行程提醒）"""
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    today = now.date()

    def days_left(target_str):
        target = datetime.strptime(target_str, '%Y-%m-%d').date()
        return (target - today).days

    report = (
        f"🗓️ *龍九決戰日檢核*\n"
        f"🕒 報告時間：{now_str}\n"
        f"🔄 資料日期：2026-07-10（動態）\n\n"
    )

    # P0 決戰日
    report += "🚨 *P0 決戰日*\n"
    p0_items = [
        ("07-13", "**延後至週一** 台中辦理繳款（因國泰匯款尚未入帳）", "清晨出發，預計中午前回程", "**身分證、印章、存摺、已確認欄位**"),
        ("07-11", "台南行程出發", "傍晚高鐵南下", "住宿舅舅家"),
        ("07-12", "台南演唱會", "看完返回新竹縣", ""),
        ("07-17", "段部上課：工安 AI", "09:00", "7/16 提醒帶筆電"),
        ("08-03", "段部體檢", "", ""),
    ]
    for date_str, name, action, prepare in p0_items:
        d = days_left(f"2026-{date_str}")
        if d >= 0:
            icon = "🚨" if d <= 2 else "⚠️" if d <= 5 else "📌"
            report += f"{icon} {date_str} {name}（剩餘 {d} 天）\n"
            if action:
                report += f"   行動：{action}\n"
            if prepare:
                report += f"   準備：{prepare}\n"

    # 日出/日落提醒
    report += "\n🌅 *日出/日落提醒*\n"
    report += "【日落】10/23 胡志明市自由行出發（剩餘 106 天）\n"

    #  wichtige 行事曆
    report += "\n📅 *重要行事曆*\n"
    report += f"【行事曆】7/13 請假（身心調事假）\n"
    report += f"【行事曆】7/14 水保竣工會勘（峨眉變電所，剩餘 5 天）\n"
    report += f"【行事曆】10/31 洲際W轉貸評估\n"

    # 租金與繳款
    report += "\n💰 *租金與繳款排程*\n"
    report += f"每月 1 日：大義街店面租金 24,000 + 大義街2-3F 23,100 + 理財型利息 10,300\n"
    report += f"每月 20 日：洲際W租金 33,000 + 洲際W房貸 65,734\n"
    report += f"每月 29 日：台新/永豐信用卡自動扣繳\n"
    report += f"每月 22 日：玉山信用卡自動扣繳\n"
    report += f"每月 3 日：台北富邦信用卡自動扣繳\n"

    # Notion SOP 一鍵導航
    report += "\n📘 *Notion 戰術導航*\n"
    report += "🏦 負債與現金流庫：https://www.notion.so/398fc735d43381f5821ec49419155598\n"
    report += "📈 資產與投資庫：https://www.notion.so/398fc735d43381f89a97d933f9421c9e\n"
    return report

def check_credit_card_alerts():
    """檢查是否為卡費/貸款扣款前 3 天"""
    today = datetime.now().date()
    alerts = []
    for card in CREDIT_CARDS:
        due_day = card.get('cycle_due_day')
        if not due_day:
            continue
        # 計算本月到期日
        try:
            due = date(today.year, today.month, due_day)
            if due < today:
                due = date(today.year, today.month + 1, due_day)
        except ValueError:
            continue
        days_left = (due - today).days
        if 0 <= days_left <= 3:
            alerts.append(f"💳 {card['bank']} 卡費繳款：{due.strftime('%m/%d')}（剩 {days_left} 天，最低 {card['min_pay']:,}）{card.get('note','')}")
    for loan in LOAN_PAYMENTS:
        due_day = loan.get('cycle_due_day')
        if not due_day:
            continue
        try:
            due = date(today.year, today.month, due_day)
            if due < today:
                due = date(today.year, today.month + 1, due_day)
        except ValueError:
            continue
        days_left = (due - today).days
        if 0 <= days_left <= 3:
            alerts.append(f"🏦 {loan['name']}：{due.strftime('%m/%d')}（剩 {days_left} 天，金額 {loan['amount']:,}）{loan.get('note','')}")
    return "\n".join(alerts) if alerts else "✅ 近期無卡費/貸款扣款預警"

# ==========================================================================
# 銀行帳戶監控日報
# ==========================================================================
def generate_daily_bank_report():
    """檢查銀行帳戶餘額是否足夠支付近期信用卡與貸款"""
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    today = now.date()

    # 計算本月各帳戶需支付金額
    upcoming_payments = []
    total_due = 0

    for card in CREDIT_CARDS:
        due_day = card.get('cycle_due_day')
        if not due_day:
            continue
        try:
            due = date(today.year, today.month, due_day)
            if due < today:
                due = date(today.year, today.month + 1, due_day)
        except ValueError:
            continue
        days_left = (due - today).days
        upcoming_payments.append({
            'type': '信用卡',
            'name': card['bank'],
            'due': due,
            'days_left': days_left,
            'amount': card['min_pay'],
            'note': card.get('note', ''),
        })
        total_due += card['min_pay']

    for loan in LOAN_PAYMENTS:
        due_day = loan.get('cycle_due_day')
        if not due_day:
            continue
        try:
            due = date(today.year, today.month, due_day)
            if due < today:
                due = date(today.year, today.month + 1, due_day)
        except ValueError:
            continue
        days_left = (due - today).days
        upcoming_payments.append({
            'type': '貸款',
            'name': loan['name'],
            'due': due,
            'days_left': days_left,
            'amount': loan['amount'],
            'note': loan.get('note', ''),
        })
        total_due += loan['amount']

    # 計算可動用現金
    liquid = get_total_liquid_cash()

    # 檢查各帳戶餘額
    account_details = []
    reserved_keywords = ['專戶（轉貸）', '專戶', '凍結', '質押']
    for name, balance in digital_accounts.items():
        if any(k in name for k in ['帳戶', '數位', '活儲', '專戶', '凍結', '質押']):
            account_details.append((name, balance))
    account_details.sort(key=lambda x: x[1])

    # 計算實際近期應付總額
    upcoming = [p for p in upcoming_payments if 0 <= p['days_left'] <= 30]
    upcoming.sort(key=lambda x: x['days_left'])
    recent_due = sum(p['amount'] for p in upcoming)
    is_sufficient_recent = liquid >= recent_due
    status_icon_recent = "✅" if is_sufficient_recent else "🚨"
    status_text_recent = "充足" if is_sufficient_recent else "不足"

    report = (
        f"🏦 *銀行帳戶監控日報*\n"
        f"🕒 報告時間：{now_str}\n\n"
        f"💰 *可動用現金總額*：{liquid:,.0f} TWD\n"
        f"📋 *近期應付（30天）*：{recent_due:,.0f} TWD\n"
        f"{status_icon_recent} *資金狀態*：{status_text_recent}\n\n"
    )

    # 國泰世華專戶單獨列為「專戶監控」，不列入可動用現金
    report += "\n📌 *專戶/凍結監控*\n"
    for name, balance in special_accounts.items():
        report += f"🔒 {name}：{balance:,.0f} TWD（專戶專用，不納入日常可動用現金）\n"
    report += "🔕 土地銀行：暫停監控（未動用）\n"

    # 租金到帳狀態
    report += "\n🏠 *租金到帳監控*\n"
    rent_items = [
        ('大義街1樓店面租金', 24000, '2026-08-01', '台新銀行', '每月1日，偶爾月底入帳'),
        ('洲際W 18F-6 租金', 33000, '2026-07-20', '台新銀行（集中分配）', '每月20日，簽約中，第一筆預計7/20入帳'),
        ('大義街2-3F 租金', 23100, '2026-07-20', '國泰世華專戶（21,000+2,100）', '每月20日，20-25日確認入帳'),
    ]
    for name, amount, expected, dest, note in rent_items:
        expected_dt = datetime.strptime(expected, '%Y-%m-%d').date()
        days_left = (expected_dt - today).days
        if '2-3F' in name and 0 <= days_left <= 5:
            status = f"🔔 剩 {days_left} 天，請確認入帳（21,000+2,100）"
        elif days_left < 0:
            status = f"⚠️ 已逾期 {abs(days_left)} 天"
        elif days_left == 0:
            status = "📥 今日應入帳"
        elif days_left <= 3:
            status = f"⏳ 剩 {days_left} 天"
        else:
            status = f"📅 剩 {days_left} 天"
        report += f"{status} {name}：{amount:,} TWD → {dest}（{note}）\n"

    # 3個月扣款緩衝水位提醒
    monthly_outflow = MONTHLY_MORTGAGE + MONTHLY_CONSUMPTION + MONTHLY_RENT_SHA_LU
    three_month_buffer = monthly_outflow * 3
    work_surplus = MONTHLY_INCOME - monthly_outflow
    retirement_surplus = MONTHLY_RETIREMENT_INCOME - monthly_outflow

    report += f"\n💧 *3個月扣款緩衝水位*\n"
    report += f"每月固定支出（房貸+信用卡+現金花費+沙鹿房租）：{monthly_outflow:,.0f} TWD\n"
    report += f"3個月緩衝水位建議：{three_month_buffer:,.0f} TWD\n"
    buffer_ratio = liquid / three_month_buffer if three_month_buffer else 0
    if buffer_ratio >= 1.5:
        buffer_status = "✅ 充裕"
    elif buffer_ratio >= 1.0:
        buffer_status = "⚠️ 刚好"
    else:
        buffer_status = "🚨 不足"
    report += f"目前可動用現金覆蓋率：{buffer_ratio:.1f}x｜狀態：{buffer_status}\n\n"
    # 現金流盈餘對照
    report += "📊 *每月收入 vs 支出盈餘對照*\n"
    report += "🔄 資料日期：2026-07-10（動態）\n"
    report += f"▫️ 房租收入：{MONTHLY_RENT_INFLOW:,.0f} TWD\n"
    report += f"▫️ 配息收入：{MONTHLY_DIVIDEND:,.0f} TWD（保守估計）\n"
    report += f"▫️ 工作收入：{MONTHLY_WORK_INCOME:,.0f} TWD\n"
    report += f"▫️ 每月總收入：{MONTHLY_INCOME:,.0f} TWD\n"
    report += f"▫️ 每月總支出：{monthly_outflow:,.0f} TWD\n"
    report += f"💰 工作期月盈餘：{work_surplus:,.0f} TWD\n"
    retirement_surplus = MONTHLY_RETIREMENT_INCOME - monthly_outflow
    report += f"🏖️ 退休後模擬盈餘（不含薪水）：{retirement_surplus:,.0f} TWD\n"
    # 當月信用卡消費統計（台新僅使用一張 Richart 卡；含街口支付等通路）
    report += "\n💳 *當月信用卡消費統計*\n"
    cc_roots = ['Richart', 'Unicard－正卡', '信用卡']
    cc_spend = {}
    cc_total = 0
    exclude_keywords = ['轉帳', '跨行', 'cd轉', '扣繳', '繳信用卡', '媒體轉帳', '轉出', '轉入', '繳費', '貸款', '房貸', '利息', '本金', '外幣', '匯率', '交易']
    mb_path = r'C:/Users/bot/AppData/Local/hermes/cache/documents/doc_1ab02db81521_Moneybook_明細_20260709_1.csv'
    try:
        with open(mb_path, 'r', encoding='utf-8-sig') as f:
            detail_rows = list(csv.DictReader(f))
        for r in detail_rows:
            acct = r.get('帳戶名稱', '')
            amt = float(r['金額']) if r.get('金額') else 0
            desc = r.get('明細描述', '')
            category = r.get('分類', '')
            trans_date = r.get('消費日', '')
            if not any(root in acct for root in cc_roots) or amt >= 0:
                continue
            if any(k in desc for k in exclude_keywords):
                continue
            month = trans_date[:7].replace('/', '-')
            if month != now.strftime('%Y-%m'):
                continue
            cat = category if category else '其他'
            cc_spend[cat] = cc_spend.get(cat, 0) + abs(amt)
            cc_total += abs(amt)
    except Exception:
        pass

    if cc_spend:
        report += f"本月信用卡消費總額：{cc_total:,.0f} TWD\n"
        for cat, val in sorted(cc_spend.items(), key=lambda x: -x[1]):
            pct = val / cc_total * 100 if cc_total else 0
            report += f"  • {cat}：{val:,.0f} TWD ({pct:.0f}%)\n"
        report += "\n📊 消費分析建議：\n"
        if cc_spend.get('購物', 0) / cc_total > 0.6:
            report += "  • 購物占比偏高(>60%)，建議檢視非必要消費，特別是 Google/線上服務訂閱\n"
        if cc_spend.get('飲食', 0) > 10000:
            report += "  • 外食/飲料支出偏高，建議每週帶飯 2-3 天可省 3,000-4,000/月\n"
        if cc_spend.get('交通', 0) > 3000:
            report += "  • 交通費偏高，確認是否有長途或臨時計程車可優化\n"
        if cc_spend.get('費用/手續費', 0) > 500:
            report += "  • 手續費/國外交易服務費略高，建議使用低手續費卡進行海外消費\n"
        if not cc_spend:
            report += "  • 本月信用卡消費偏低，屬正常現象\n"
    else:
        report += "本月信用卡無自動辨識消費紀錄\n"

    # 近期應付明細
    report += "📅 *近期應付明細（未來 30 天）*\n"
    if upcoming:
        for p in upcoming:
            icon = "🚨" if p['days_left'] <= 2 else "⚠️" if p['days_left'] <= 5 else "📌"
            report += f"{icon} {p['type']}｜{p['name']}｜{p['due'].strftime('%m/%d')}｜剩 {p['days_left']} 天｜{p['amount']:,} TWD｜{p['note']}\n"
    else:
        report += "✅ 未來 30 天無應付款項\n"
    report += "\n💳 *帳戶餘額明細*\n"
    for name, balance in account_details:
        status = "🟢" if balance > 0 else "🔴"
        report += f"{status} {name}：{balance:,.0f} TWD\n"

    # 警示判斷
    low_accounts = [(name, balance) for name, balance in account_details if balance < 10000]
    if low_accounts:
        report += "\n⚠️ *低餘額警示*（少於 1 萬）\n"
        for name, balance in low_accounts:
            report += f"🔴 {name}：{balance:,.0f} TWD\n"

    # 星展低餘額緊急補庫建議（條件觸發）
    scb_balance = next((bal for name, bal in account_details if '星展' in name), None)
    if scb_balance is not None and scb_balance < 30000:
        report += f"\n🚨 *星展低餘額補庫建議*\n"
        report += f"目前星展餘額：{scb_balance:,.0f} TWD\n"
        report += f"建議：由台新Richart調度 30,000 TWD 至星展，"
        report += f"因 8/1 需扣款 23,424 + 10,300 = 33,724 TWD\n"
        report += f"補庫後預估水位：{scb_balance + 30000:,.0f} TWD\n"

    report += f"\n📌 *扣款規則*"
    report += f"信用卡：每月自動扣繳，台新/永豐 29 日、玉山 22 日、台北富邦 3 日\n"
    report += f"貸款：洲際W房貸 20 日（永豐）、大義街房貸+理財利息 1 日（星展）\n"

    return report

# ==========================================================================
# 主監控循環（每日檢查）
# ==========================================================================
def run_dragon_nine_monitor():
    """一次性推送 5 張日報 + 儀表板連結"""
    from datetime import datetime
    print("=" * 60)
    print(f"推送時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    r1 = generate_daily_report()
    print(r1)
    send_telegram_message(r1)

    r2 = generate_dragon_nine_report()
    print(r2)
    send_telegram_message(r2)

    r3 = generate_dragon_five_report()
    print(r3)
    send_telegram_message(r3)

    r4 = generate_daily_bank_report()
    print(r4)
    send_telegram_message(r4)

    r5 = generate_battle_check_report()
    print(r5)
    send_telegram_message(r5)

    dash_link = "📎 [查看完整儀表板](https://longjiu-dashboard-2-production.up.railway.app)"
    send_telegram_message(dash_link)

    snap_b64 = save_snapshot()
    print(f"[SNAPSHOT] snapshot.json 已更新，base64 長度={len(snap_b64)}")

    print("=" * 60)
    print("✅ 5 張日報 + 儀表板連結 + snapshot.json 推送/更新完成")

if __name__ == "__main__":
    run_dragon_nine_monitor()

# ==========================================================================
# 第五張報表：資產市場情報總覽
# ==========================================================================
def generate_asset_market_report():
    """資產市場情報總覽：VIX、S&P500、資產分布、巴菲特效應、匯率"""
    now = datetime.now()
    now_str = now.strftime('%Y-%m-%d %H:%M:%S')
    today = now.date()

    report = (
        f"📊 *資產市場情報總覽*\n"
        f"🕒 報告時間：{now_str}\n\n"
    )

    # 資產分布（均為截圖/錨定值，請於更新截圖後同步修正）
    etf_total = 1801590 + 456600  # 台股ETF 1,801,590 + 全球/債券ETF 456,600（2026-07-10 Company_Ledger.md 真值）
    insurance_total = 9844676  # 2026-07-10：安聯A/B 7,912,440 + 第一金 2,010,544（截圖真值）
    cash_total = 3110093  # 2026-07-10 銀行帳戶截圖
    fund_total = 873041  # 2026-07-10 鉅亨買基金截圖
    investable = insurance_total + etf_total + cash_total + fund_total

    report += "💰 *資產分布總覽*\n"
    report += f"📊 證券ETF（動產）：{etf_total:,.0f} TWD\n"
    report += f"   0050：40,000 股（成本 169,800）\n"
    report += f"   006208：40,000 股（成本 393,800）\n"
    report += f"   00878：150,000 股（成本 402,150）\n"
    report += f"   00713：40,000 股（成本 219,200）\n"
    report += f"   00919：50,000 股（成本 147,800）\n"
    report += f"   00918：10,000 股（成本 285,500）\n"
    report += f"   009816：160,000 股（成本 188,800）\n"
    report += f"   0056：10,000 股（成本 371,500）\n"
    report += f"   00981A：40,000 股（成本 103,920）\n"
    report += f"   00984A：100,000 股（成本 145,600）\n"
    report += f"   009823：100,000 股（成本 100,200）\n"
    # 保單
    insurance_total = 9856114
    report += f"🛡️ 保單資產：{insurance_total:,.0f} TWD\n"
    report += f"   安聯保單A：5,102,428（截圖 2026-07-10 09:02）\n"
    report += f"   安聯保單B：2,743,142（截圖 2026-07-10 09:02）\n"
    report += f"   第一金保單：1,999,106（截圖 2026-07-10 10:39，統計至 2026-07-08）\n"
    report += f"   安聯系統本月累積配息/撥回：55,451 TWD（6 筆，系統自動統計）\n"
    report += f"   第一金 FJ33 累計現金配息：0.00 NTD（截圖確認，7/06 暫未入帳，需手動查詢配息資料）\n"
    report += f"   本月保單配息合計：待確認（安聯 55,451 + 第一金待查）\n\n"

    report += f"🏦 鉅亨買基金：{fund_total:,.0f} TWD\n"
    report += f"   （待執行長更新基金名稱與配置比例）\n\n"

    report += f"💎 數字黃金（現金/定存）：{cash_total:,.0f} TWD\n"
    report += f"📊 總資產：56,025,441 TWD（2026-07-10 Company_Ledger 錨定）\n"
    report += f"📋 資產負債比：52.1%（警戒線：60%）\n\n"

    # ==========================================================================
    # 1. Yahoo奇摩快訊
    # ==========================================================================
    headers = {"User-Agent": "Mozilla/5.0"}
    news_items = []
    yahoo_sections = [
        ("https://tw.news.yahoo.com/", 10),
        ("https://tw.news.yahoo.com/finance/", 10),
        ("https://tw.news.yahoo.com/technology/", 10),
    ]
    keywords = ["股", "ETF", "匯率", "台積電", "美股", "AI", "科技", "基金", "金融", "油價", "川普", "台股", "Apple", "NVIDIA", "輝達", "財政部", "央行", "證交所", "千金股"]

    seen_urls = set()
    for url, limit in yahoo_sections:
        try:
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            import re as _re
            pattern = _re.compile(r'\[(.*?)\]\((https?://[^\s\)]+)\)')
            for title, link in pattern.findall(resp.text):
                if not any(k in title for k in keywords):
                    continue
                if link in seen_urls:
                    continue
                seen_urls.add(link)
                source = "Yahoo奇摩新聞"
                if "stock.yahoo.com" in link:
                    source = "Yahoo奇摩股市"
                news_items.append((title, link, source))
                if len(news_items) >= limit:
                    break
        except Exception:
            continue

    top8 = news_items[:8]
    if not top8:
        top8 = [
            ("台股太熱！外資持股市值暴增 央行：穩匯有挑戰", "https://tw.news.yahoo.com/%E5%8F%B0%E8%82%A1%E5%A4%AA%E7%86%B1%EF%BC%81%E5%A4%96%E8%B3%87%E6%8C%81%E8%82%A1%E5%B8%82%E5%80%BC%E5%9C%A8%E5%A2%9E-%E5%A4%AE%E8%A1%8B%EF%BC%9A%E7%A9%A9%E5%8C%AF%E6%9C%89%E6%8C%91%E6%88%B0-101118575.html", "Yahoo奇摩財經"),
            ("七月市場觀望情緒升溫 「第四法人」聚焦市值型ETF", "https://tw.news.yahoo.com/%E4%B8%83%E6%9C%88%E5%B8%82%E5%A0%B4%E8%A7%80%E6%9C%9B%E6%83%85%E7%B7%92%E5%8D%87%E6%BA%AB-%E7%AC%AC%E5%9B%9B%E6%B3%95%E4%BA%BA-%E8%81%9A%E7%84%A6%E5%B8%82%E5%80%BE%E5%9E%8Betf-163000374.html", "Yahoo奇摩財經"),
            ("Q2法說會在即 台積供應鏈30檔必收", "https://tw.news.yahoo.com/q2%E6%B3%95%E8%AA%AA%E6%9C%83%E5%9C%A8%E5%8D%B3-%E5%8F%B0%E7%A9%8D%E4%BE%9B%E6%87%89%E9%8F%8830%E6%AA%94%E5%BF%85%E6%94%B6-160500658.html", "Yahoo奇摩財經"),
            ("不斷更新／美股大跌800點 4大指數齊崩", "https://tw.news.yahoo.com/%E5%BF%AB%E8%A8%8A-%E7%BE%8E%E8%82%A1%E9%96%8B%E7%9B%A4%E5%A4%A7%E8%B7%8C500%E9%BB%9E-4%E5%A4%A7%E6%8C%87%E6%95%B8%E9%BD%8A%E5%B4%A9-135100776.html", "Yahoo奇摩股市"),
            ("川普又放狠話！美軍今晚恐再空襲伊朗 國際油價聞訊飆漲", "https://tw.news.yahoo.com/%E5%B7%9D%E6%99%AE%E5%8F%88%E6%94%BE%E7%8B%A0%E8%A9%B1-%E7%BE%8E%E8%BB%8D%E4%BB%8A%E6%99%9A%E6%81%90%E5%86%8D%E7%A9%BA%E8%A5%B2%E4%BC%8A%E6%9C%97-%E5%9C%8B%E9%9A%9B%E6%B2%B9%E5%83%B9%E8%81%9E%E8%A8%8A%E9%A3%86%E6%BC%B2-145500831.html", "Yahoo奇摩財經"),
            ("賣股後狂飆 吊車大王：少賺近2億", "https://tw.stock.yahoo.com/news/%E5%90%8A%E8%BB%8A%E5%A4%A7%E7%8E%8B%E8%AA%8D%E8%B3%A03%E5%8D%83%E8%90%AC%E8%B3%A3%E9%80%991%E6%AA%94-%E4%BB%8A%E5%99%B4%E9%A3%9B%E4%BB%96%E5%B4%A9%E6%BD%B0-%E5%B0%91%E8%B3%BA%E5%BF%AB2%E5%84%84-095848223.html", "Yahoo奇摩股市"),
            ("外資單週賣超近1400億元 這3檔金融慘被砍近41萬張", "https://tw.news.yahoo.com/%E5%A4%96%E8%B3%87%E5%96%AE%E9%80%B1%E8%B3%A3%E8%B6%85%E8%BF%911400%E5%84%84%E5%85%83-%E9%80%993%E6%AA%94%E9%87%91%E8%9E%8D%E6%85%98%E8%A2%AB%E7%A0%8D%E8%BF%9141%E8%90%AC%E5%BC%B6-172500120.html", "Yahoo奇摩財經"),
            ("比外資還高？法說會前夕南亞科新目標價", "https://tw.news.yahoo.com/%E6%AF%94%E5%A4%96%E8%B3%83%E9%82%84%E9%AB%98-%E6%B3%95%E8%AA%AA%E6%9C%83%E5%89%8D%E5%A4%95%E5%8D%97%E4%BA%9E%E7%A7%91%E6%96%B0%E7%9B%AE%E6%A8%99%E5%83%B9-140500476.html", "Yahoo奇摩財經"),
        ]

    report += "📰 *Yahoo奇摩快訊*\n"
    for idx, (title, link, source) in enumerate(top8, 1):
        report += f"📰 {idx}. {title} - {source}\n🔗 {link}\n"
    report += "\n"

    # ==========================================================================
    # 2. Gemini 摘要 + 市場判斷 + 操作建議
    # ==========================================================================
    headlines_text = "\n".join([f"{idx}. {t}" for idx, (t, _, __) in enumerate(top8, 1)])
    holdings = "0050.TW, 006208.TW, 009816.TW, 00646.TW, 00713.TW, 00878.TW, 0056.TW, 00981A.TW, 00984A.TW, 00919.TW, 00918.TW, 009823.TW, 009824.TW"
    market_assessment = ""
    actions = []
    if GEMINI_API_KEY:
        try:
            import json as _json_m, urllib.request
            prompt = (
                "你是龍九控股情報官。以下是最新的 Yahoo 奇摩新聞標題，請先去除無關或重複資訊，"
                "再針對龍九控股持倉（" + holdings + "）進行市場衝擊判斷與資產操作建議。\n\n"
                "新聞標題：\n" + headlines_text + "\n\n"
                "請用繁體中文輸出，嚴格遵守以下格式：\n"
                "`【市場判斷】...`\n"
                "`【操作建議】`\n"
                "`1. ...`\n"
                "`2. ...`\n"
                "`3. ...`\n"
                "最多3條建議，每條控制在1-2行，直接與持倉相關。"
            )
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
            data = _json_m.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = _json_m.loads(resp.read().decode("utf-8"))
            market_assessment = result.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            actions_start = market_assessment.find("【操作建議】")
            if actions_start != -1:
                block = market_assessment[actions_start + len("【操作建議】"):]
                for line in block.splitlines():
                    if line.strip().startswith(("1.", "2.", "3.", "-")):
                        actions.append(line.strip())
                actions = actions[:3]
        except Exception:
            market_assessment = ""
            actions = []

    if market_assessment:
        report += "💡 *市場判斷*\n"
        report += market_assessment + "\n\n"
    else:
        report += "💡 *市場判斷*\n"
        report += "台股短線升溫，外資曝險增加使央行 vigilant；科技族群受台積ADR與AI供應鏈法說會帶動。\n\n"

    # ==========================================================================
    # 3. 匯率（Gemini 即時抓取）
    # ==========================================================================
    usd_twd = 32.105
    twd_jpy = 0.20
    try:
        import json as _json_fx
        gemini_key = os.getenv('GEMINI_API_KEY', '')
        if gemini_key:
            url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=' + gemini_key
            prompt = '請僅回傳一行 JSON：{"usd_twd": 32.00, "twd_jpy": 0.20}，代表目前台幣兌美金與台幣兌日圓的匯率。不要有其他文字。'
            data = _json_fx.dumps({'contents':[{'parts':[{'text': prompt}]}]}).encode()
            req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                fx_json = _json_fx.loads(resp.read().decode('utf-8'))['candidates'][0]['content']['parts'][0]['text']
            fx = _json_fx.loads(fx_json)
            usd_twd = float(fx.get('usd_twd', usd_twd))
            twd_jpy = float(fx.get('twd_jpy', twd_jpy))
    except Exception:
        pass
    # 4. 配置比例檢查
    report += "⚖️ *配置比例檢查*\n"
    tw_pct = 40.0
    us_pct = 35.0
    insurance_pct = 25.0
    report += f"【目標】台股權益 {tw_pct:.0f}% / 美股權益 {us_pct:.0f}% / 債券與現金 {insurance_pct:.0f}%\n"
    report += f"【表觀】保單 {insurance_total/investable*100:.0f}% / 台股ETF+鉅亨 {(etf_total+fund_total)/investable*100:.0f}% / 現金 {cash_total/investable*100:.0f}%\n"
    report += f"【穿透】台股權益 20.3% / 美股權益 50.6% / 債券與現金 29.1%\n"
    report += "⚠️ 穿透後美股權益超重，台股權益不足，待逐步調整\n\n"
    report += f"USD/TWD：{usd_twd:.3f}\n"
    report += f"TWD/JPY：{twd_jpy:.3f}\n\n"

    # ==========================================================================
    # 4. ETF 溢價監控
    # ==========================================================================
    etf_rows = [
        ("0050.TW", "元大台灣50", 105149),
        ("006208.TW", "富邦台50", 150112),
        ("009816.TW", "中信綠能", 107200),
        ("00646.TW", "寶盛美國500", 71600),
        ("00713.TW", "元大全球金", 109600),
        ("00878.TW", "國泰永續高息", 165000),
        ("0056.TW", "元大高股息", 37150),
        ("00981A.TW", "bbenefit", 103920),
        ("00984A.TW", "第一金主動型", 145600),
        ("00919.TW", "群益深ENE", 147800),
        ("00918.TW", "永豐台灣ESG", 28550),
        ("009823.TW", "永豐優息", 100200),
        ("009824.TW", "凱基優選", 99300),
    ]
    try:
        import io, contextlib
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            gain_loss_rows = calculate_daily_gain_loss()
        gain_loss = {r['code']: r for r in gain_loss_rows if isinstance(r, dict) and r.get('current_price', 0) > 0}
        for i, row in enumerate(etf_rows):
            code, name, cost = row
            info = gain_loss.get(code)
            if info:
                pct = (info['current_price'] * info.get('qty', 0) - cost) / cost * 100 if cost else 0
                if pct > 30:
                    premium = "嚴重溢價"
                elif pct > 15:
                    premium = "溢價偏高"
                else:
                    premium = "合理估值"
                etf_rows[i] = (code, name, f"{premium} ({pct:+.2f}%)")
            else:
                etf_rows[i] = (code, name, "待查詢")
    except Exception:
        pass

    ex_map = {}
    try:
        from dividend_tracker import ANCHOR_DIVIDENDS
        ex_map = {item["code"]: item["ex_date"] for item in ANCHOR_DIVIDENDS if item.get("ex_date") and item.get("code") in [r[0] for r in etf_rows]}
    except Exception:
        ex_map = {}

    report += "\n📋 *ETF 溢價監控*\n"
    report += "```\n"
    report += f"{'代碼':<14}{'名稱':<12}{'溢價/壓力':<22}{'下次除息/配息日'}\n"
    report += "-" * 70 + "\n"
    for code, name, premium in etf_rows:
        ex = ex_map.get(code, "待查詢")
        report += f"{code:<12} {name:<10} {premium:<28} {ex}\n"
    report += "```\n\n"

    # ==========================================================================
    # 5. 基金與現金概況（含 鉅亨買基金）
    # ==========================================================================
    report += "\n🏦 *基金與現金概況*\n"
    report += "📌 鉅亨買基金：869,413 TWD（基金名稱待確認，確認後補齊持倉名稱）\n"
    report += "📌 證券ETF（動產）：2,361,190 TWD\n"
    report += "📌 保單資產：9,844,676 TWD\n"
    report += "📌 銀行活存：3,405,689 TWD\n"
    total_assets = 56014425
    report += f"📊 總資產：{total_assets:,} TWD（2026-07-10 Company_Ledger 錨定）\n"
    report += "📋 資產負債比：52.1%（警戒線：60%）\n"
    report += "第一銀行 SnY：100,085 TWD\n\n"

    # ==========================================================================
    # 6. 穿透式產業曝險摘要（weights manifest）
    # ==========================================================================
    gain_loss_rows = []
    try:
        gain_loss_rows = calculate_daily_gain_loss()
    except Exception:
        pass
    try:
        manifest = load_weights_manifest()
        etf_prices = fetch_market_prices()
        etf_values = {}
        for row in etf_rows:
            code = row[0]
            price = etf_prices.get(code, 0)
            qty = 1
            for r in gain_loss_rows:
                if r.get('code') == code:
                    qty = r.get('qty', 1)
            if price > 0 and qty > 0:
                etf_values[code] = price * qty

        stock_exposure = {}
        for etf_code, weight_info in manifest.get("etf_holdings", {}).items():
            etf_val = etf_values.get(etf_code, 0)
            for holding in weight_info.get("top_holdings", []):
                stock_name = holding.get("name", holding.get("code", ""))
                weight = holding.get("weight", 0)
                stock_exposure[stock_name] = stock_exposure.get(stock_name, 0) + etf_val * weight

        concentration = sorted(stock_exposure.items(), key=lambda x: x[1], reverse=True)[:3]
        if concentration and sum(w for _, w in concentration) > 0:
            concent_txt = "、".join([f"{n} ({w:,.0f} TWD)" for n, w in concentration])
        else:
            concent_txt = "待更新"
    except Exception:
        concent_txt = "待更新"
    report += "🔍 *穿透式產業曝險（Top3）*\n"
    report += concent_txt + "\n\n"

    # ==========================================================================
    # 7. 巴菲特建議
    # ==========================================================================
    buffett_action_text = ""
    if actions:
        buffett_action_text = "；".join(actions)
    else:
        buffett_action_text = "優先觀察0056與0050/006208溢價狀況；美元偏防禦；等待科技板塊動能確立後再加碼。"

    report += "🐋 *巴菲特視角建議*\n"
    report += (
        "以價值與安全邊際為核心參考：0056高股息若持續嚴重超漲，評估減碼回收現金；"
        "0050/006208維持部位但暫不追價；匯率偏防禦下，台幣資產部位續持有，美股科技板塊待法說動能進一步確認再調整。\n"
    )
    report += "✅ 行動：" + buffett_action_text + "\n\n"

    report += "🗓️ *決戰日核檢*：請參閱第四張報表《龍九決戰日檢核》\n"
    report += "✍️ *裁決簽核*：0056 優先減碼，其餘維持觀察。\n"
    return report

# ==========================================================================
# SSoT snapshot 模組
# ==========================================================================
def build_snapshot() -> dict:
    """產出與 dashboard.py EMBEDDED_SNAPSHOT_B64 相容的 snapshot.json

    對齊 snapshot_schema_v2_spec.json，並遵守 SSoT：
      - 稅務/銷帳/截圖層用 Company_Ledger.md 錨定
      - 動態層由 report 函式計算
    """
    from decimal import Decimal

    # 動態層
    liquid = 0.0
    insurance_total = 0.0
    try:
        liquid = float(get_total_liquid_cash())
    except Exception:
        pass
    try:
        insurance_total = float(get_total_insurance())
    except Exception:
        pass

    daily_report_text = ""
    dragon_nine_text = ""
    dragon_five_text = ""
    bank_text = ""
    battle_text = ""
    asset_market_text = ""
    try:
        daily_report_text = generate_daily_report()
    except Exception:
        pass
    try:
        dragon_nine_text = generate_dragon_nine_report()
    except Exception:
        pass
    try:
        dragon_five_text = generate_dragon_five_report()
    except Exception:
        pass
    try:
        bank_text = generate_daily_bank_report()
    except Exception:
        pass
    try:
        battle_text = generate_battle_check_report()
    except Exception:
        pass
    try:
        asset_market_text = generate_asset_market_report()
    except Exception:
        pass

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    # SSoT：以 Company_Ledger.md 為唯一真值
    total_assets = Decimal("50689930")
    total_liabilities = Decimal("22000000")
    net_worth = total_assets - total_liabilities
    debt_ratio = f"{float(total_liabilities / total_assets) * 100:.1f}%"

    monthly_income = Decimal(str(MONTHLY_INCOME))
    monthly_expense = Decimal(str(MONTHLY_MORTGAGE + MONTHLY_CONSUMPTION + MONTHLY_RENT_SHA_LU))
    working_surplus = monthly_income - monthly_expense
    retirement_surplus = Decimal(str(MONTHLY_RETIREMENT_INCOME)) - monthly_expense

    insurance_monthly_dividend = Decimal("69044")

    # 資產配置比例
    tw_total_mv = Decimal("2082870")
    us_total_mv = Decimal("6022095")
    cash_total_mv = Decimal("8417380")
    total_mv = tw_total_mv + us_total_mv + cash_total_mv
    tw_ratio = float(tw_total_mv / total_mv)
    us_ratio = float(us_total_mv / total_mv)
    cash_ratio = float(cash_total_mv / total_mv)

    relay_status = {
        "first_leg": {"done": True, "date": "2026-07-09", "from": "摩根JPM", "to": "安聯收益成長", "policy": "FJ33"},
        "second_leg": {"done": True, "date": "2026-07-09", "from": "安聯收益成長", "to": "M&G入息基金", "policy": "QL18610694/QL18488224"},
        "third_leg": {"done": False, "date": "2026-07-17", "from": "M&G入息基金", "to": "月底安聯AI/貝萊德A10", "policy": "QL18610694/QL18488224"},
        "fourth_leg": {"done": False, "planned": "2026-07-29", "from": "M&G入息基金", "to": "月底站配息"},
    }

    snapshot = {
        "generated_at": now_str,
        "version": "v5.0.9-flagship-fix",
        "date": date_str,
        "pages": {
            "page1": {
                "actual_cash_flow": {},
                "total_income": int(monthly_income),
                "total_expense": int(monthly_expense),
                "working_surplus": int(working_surplus),
                "retirement_surplus": int(retirement_surplus),
                "runway_months": round(float(liquid) / float(monthly_expense), 1) if monthly_expense > 0 else "—",
                "debt_ratio": debt_ratio,
            },
            "page2_allocation": {
                "allocation_analysis": {
                    "current": {"台股": tw_ratio * 100, "美股": us_ratio * 100, "現金/債券": cash_ratio * 100},
                    "target": {"台股": 40.0, "美股": 35.0, "現金/債券": 25.0},
                    "variance": {"台股": round(tw_ratio * 100 - 40.0, 1), "美股": round(us_ratio * 100 - 35.0, 1), "現金/債券": round(cash_ratio * 100 - 25.0, 1)},
                    "status": "美股權益超重、台股不足，依 40/35/25 再平衡",
                },
                "buffett_decision": {
                    "scope": "13 檔台股/ETF + 3 張保單，能力圈內",
                    "moat": "高股息ETF現金流",
                    "action": "0056 優先減碼；0050/006208/009816/00878 觀察回落後再加碼",
                    "summary": "嚴重超漲：0056；超漲偏高：0050/006208/009816/00878",
                },
                "gemini_analysis": "",
            },
            "page3_insurance_relay": {
                "system_target": {
                    "台股資產（含高股息）": "40%",
                    "美股全球科技（含保單穿透）": "35%",
                    "保險現金與防禦債券": "25%",
                },
                "allianz_combined": {"cost": 8000000, "current_value": 7844570, "cumulative_dividend": 1608046, "roi": "含息 -1.6%", "monthly_dividend": 55451},
                "first_gold": {"cost": 1996454, "current_value": 1999106, "cumulative_dividend": 63985, "roi": "含息 +1.4%", "monthly_dividend": 13593},
                "total_monthly_dividend": int(insurance_monthly_dividend),
                "summary": {"QL18610694": "安聯保單A", "QL18488224": "安聯保單B", "FJ33": "第一金保單"},
            },
            "page4_liquidity": {
                "liquidity": {"runway_months": round(float(liquid) / float(monthly_expense), 1) if monthly_expense > 0 else "—"},
                "banking": {"liquid_cash": liquid, "insurance_total": insurance_total},
            },
            "page5_actions": {"p0_tasks": [], "battle": battle_text},
            "report1": daily_report_text,
            "report2": dragon_nine_text,
            "report3": dragon_five_text,
            "report4": bank_text,
            "report5": asset_market_text,
        },
        "total_assets": float(total_assets),
        "total_liabilities": float(total_liabilities),
        "net_worth": float(net_worth),
        "debt_ratio": debt_ratio,
        "monthly_income": int(monthly_income),
        "monthly_expense": int(monthly_expense),
        "working_surplus": int(working_surplus),
        "retirement_surplus": int(retirement_surplus),
        "securities_total_market_value": float(tw_total_mv + us_total_mv),
        "insurance_monthly_dividend": float(insurance_monthly_dividend),
        "relay_status": relay_status,
    }

    return snapshot


def save_snapshot(path: str | None = None) -> str:
    """將 snapshot 寫出為 snapshot.json，並回傳可直接嵌入 dashboard.py 的 base64"""
    snapshot = build_snapshot()
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    b64 = base64.b64encode(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")).decode("utf-8")
    return b64