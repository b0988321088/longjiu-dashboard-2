"""龍九情報彙整"""
import sqlite3, json, re, glob
from datetime import date, datetime
from pathlib import Path
from logging_config import get_logger
logger = get_logger("compile_intel")

BASE = Path(__file__).resolve().parent
today = date.today().isoformat()

# 新增的持股定義
HOLDINGS = {
    "0050": {"name": "元大台灣50", "impact_factors": ["台積電", "權值股", "大盤", "科技股", "出口"]},
    "00878": {"name": "國泰永續高股息", "impact_factors": ["金融股", "傳產", "高股息", "內需", "穩定"]},
}

def get_sentiment(text):
    """根據關鍵字判斷簡單情緒"""
    if any(k in text for k in ["大漲", "買超", "利多", "上漲", "強勢", "看好", "樂觀"]):
        return "positive"
    if any(k in text for k in ["大跌", "賣超", "利空", "下跌", "弱勢", "看壞", "悲觀"]):
        return "negative"
    return "neutral"

def get_signal_level(impact_score, sentiment):
    """根據影響分數和情緒判斷訊號等級"""
    if impact_score > 0.7 and sentiment == "negative":
        return "🔴 重要 (負面)"
    if impact_score > 0.7 and sentiment == "positive":
        return "🔴 重要 (正面)"
    if impact_score > 0.4:
        return "🟡 注意"
    return "✅ 參考"

def analyze_market_intel():
    """分析市場情報，濃縮成3-5條重點"""
    condensed_intel = []
    
    # 1. 讀取 hunter_intel 產生的市場數據
    market_intel_file = BASE / "hunter_cache" / f"market_intel_{today}.json"
    market_data = {}
    if market_intel_file.exists():
        market_data = json.loads(market_intel_file.read_text(encoding="utf-8")).get("market_data", {})

    # 2. 處理市場數據，生成第一批情報
    if market_data:
        for stock_name, value_str in market_data.items():
            match = re.search(r"\((?P<change>[+-]?\d+\.\d+)%\)", value_str)
            change_percent = float(match.group("change")) if match else 0.0

            sentiment = "neutral"
            if change_percent > 1.0: sentiment = "positive"
            if change_percent < -1.0: sentiment = "negative"

            # 針對主要指數和台積電給出資訊
            if stock_name in ["台股加權", "台積電", "費半"]:
                description = f"{stock_name} 今日 {value_str}，市場情緒{'看漲' if sentiment=='positive' else '看跌' if sentiment=='negative' else '持平'}。"
                
                # 評估對 0050/00878 的影響
                holding_impact = []
                for holding_code, holding_info in HOLDINGS.items():
                    for factor in holding_info["impact_factors"]:
                        if factor in stock_name or (stock_name == "台積電" and "科技股" in holding_info["impact_factors"]):
                            holding_impact.append(holding_code)
                            break
                
                impact_score = abs(change_percent) / 5.0 # 簡單量化影響分數
                if impact_score > 1.0: impact_score = 1.0
                
                condensed_intel.append({
                    "title": f"市場動態：{stock_name}",
                    "description": description,
                    "holdings_impact": list(set(holding_impact)),
                    "sentiment": sentiment,
                    "signal_level": get_signal_level(impact_score, sentiment),
                    "raw_source": f"Yahoo Finance - {stock_name}"
                })

    # 3. 處理 compile_intel.py 原有的訊號
    #db = sqlite3.connect(str(BASE / "dragon_assets.db")) # db connection moved to compile_intel
    txts = sorted(glob.glob(str(BASE / "hunter_logs" / f"intel_{today.replace(chr(45),chr(45))}_*.txt")))
    
    # 原始的 sig 填充邏輯
    sig = {"sell": [], "buy": []}
    for f in txts:
        try:
            for line in Path(f).read_text("utf-8",errors="ignore").splitlines():
                if not line.strip(): continue
                for k in ["賣出","賣超","大跌","跌破"]:
                    if k in line: sig["sell"].append(line.strip()); break
                for k in ["買進","買超","大漲"]:
                    if k in line: sig["buy"].append(line.strip()); break

                current_sentiment = get_sentiment(line)
                
                # 評估對 0050/00878 的影響
                holding_impact = []
                for holding_code, holding_info in HOLDINGS.items():
                    for factor in holding_info["impact_factors"]:
                        if factor in line or (("0050" in holding_code and ("權值股" in line or "科技股" in line)) or ("00878" in holding_code and ("金融股" in line or "高股息" in line))):
                            holding_impact.append(holding_code)
                            break

                impact_score = 0.5 # 預設影響分數，可根據關鍵字更精細調整
                if any(k in line for k in ["大漲", "大跌", "重大利多", "重大利空"]):
                    impact_score = 0.8
                
                if holding_impact: # 只納入與持股相關的情報
                    condensed_intel.append({
                        "title": "Hunter 情報",
                        "description": line.strip(),
                        "holdings_impact": list(set(holding_impact)),
                        "sentiment": current_sentiment,
                        "signal_level": get_signal_level(impact_score, current_sentiment),
                        "raw_source": f
                    })
        except Exception as e:
            print(f"Error processing {f}: {e}")

    # 4. 篩選並濃縮至 3-5 條
    # 優先級：🔴 > 🟡 > ✅
    # 如果數量過多，優先保留「重要」和「注意」的資訊，並根據情緒平衡選擇
    
    final_intel = []
    important_intel = [i for i in condensed_intel if i["signal_level"].startswith("🔴")]
    warning_intel = [i for i in condensed_intel if i["signal_level"].startswith("🟡")]
    reference_intel = [i for i in condensed_intel if i["signal_level"].startswith("✅")]

    # 盡量納入重要和注意的情報
    final_intel.extend(important_intel)
    remaining_slots = 5 - len(final_intel)

    if remaining_slots > 0:
        final_intel.extend(warning_intel[:remaining_slots])
        remaining_slots = 5 - len(final_intel)

    if remaining_slots > 0:
        final_intel.extend(reference_intel[:remaining_slots])

    # 如果仍然超過 5 條，則按照訊號等級、情緒（正負各半）和原始來源時間進行最終篩選
    if len(final_intel) > 5:
        # 簡單的排序和截斷
        final_intel.sort(key=lambda x: (x["signal_level"].count("🔴"), x["signal_level"].count("🟡"), x["sentiment"] == "positive"), reverse=True)
        final_intel = final_intel[:5]
        
    return final_intel, sig # 返回 sig


def compile_intel(force_refresh=False):
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    
    # 呼叫新的分析函數並獲取 sig
    condensed_intel_list, sig = analyze_market_intel()

    # 恢復獲取 tw_index, tsmc, sox, tw_change 的邏輯
    p = db.execute("SELECT tw_index,tsmc,sox,tw_change FROM market_intel WHERE date=? AND source='daily_intel' ORDER BY id DESC LIMIT 1",(today,)).fetchone()
    if p: ti,ts,so,tc=p
    else: ti=ts=so=0; tc=0.0

    # 將濃縮後的情報儲存到 daily_condensed_intel_YYYY-MM-DD.json
    output_file = BASE / f"daily_condensed_intel_{today}.json"
    output_file.write_text(json.dumps(condensed_intel_list, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 更新 market_intel 表的 summary 和 raw_data
    summary_text = "\n".join([f"{item['signal_level']} {item['title']} - {item['description']} (影響持股: {','.join(item['holdings_impact'])})" for item in condensed_intel_list])
    
    # 這裡的 hunter_count, buy_count, sell_count 需要從 sig 計算
    hunter_count_val = len(glob.glob(str(BASE / "hunter_logs" / f"intel_{today.replace(chr(45),chr(45))}_*.txt")))
    buy_count_val = len(sig["buy"])
    sell_count_val = len(sig["sell"])

    c={"date":today,"timestamp":datetime.now().strftime("%H%M"),"source":"compiled","tw_index":ti,"tsmc":ts,"sox":so,"tw_change":tc,"dow":0,"nasdaq":0,"sp500":0,"nikkei":0,"summary":summary_text,"signals":json.dumps(sig,ensure_ascii=False),"raw_data":json.dumps(condensed_intel_list, ensure_ascii=False),"hunter_count":hunter_count_val,"buy_count":buy_count_val,"sell_count":sell_count_val}
    if force_refresh: db.execute("DELETE FROM market_intel WHERE date=? AND source='compiled'",(today,))
    db.execute("INSERT OR REPLACE INTO market_intel(date,timestamp,source,tw_index,tsmc,sox,tw_change,dow,nasdaq,sp500,nikkei,summary,signals,raw_data,hunter_count,buy_count,sell_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(c["date"],c["timestamp"],c["source"],c["tw_index"],c["tsmc"],c["sox"],c["tw_change"],c["dow"],c["nasdaq"],c["sp500"],c["nikkei"],c["summary"],c["signals"],c["raw_data"],c["hunter_count"],c["buy_count"],c["sell_count"]))
    db.commit(); db.close()
    print(f"加權:{c[chr(116)+chr(119)+chr(95)+chr(105)+chr(110)+chr(100)+chr(101)+chr(120)]:,.0f}" if c[chr(116)+chr(119)+chr(95)+chr(105)+chr(110)+chr(100)+chr(101)+chr(120)] else "無資料")
    print(f"已生成濃縮情報報告：{output_file}")
    
    return c
if __name__=="__main__": compile_intel()
