"""龍九台股緊急應變 13:00 — 刷新情報 + 彙整 + 三份產出"""
import subprocess, sys, json
from pathlib import Path
from datetime import datetime
import requests # Added for Yahoo Finance API call

LJ = Path.home() / "Desktop" / "longjiu_system"
today = __import__("datetime").date.today().isoformat()

def run_step(label, cmd, timeout=120):
    ts = datetime.now().strftime("%H%M")
    print(f"[{ts}] {label}...", end=" ", flush=True)
    try:
        r = subprocess.run(cmd, cwd=str(LJ), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            print(f"❌ 失敗\\n{r.stderr[:200]}")
            return False
        out = r.stdout.strip()
        if out:
            for l in out.split("\\n")[-3:]:
                print(f"  {l}")
        print("✅")
        return True
    except subprocess.TimeoutExpired:
        print("❌ 超時")
        return False

def fetch_etf_data(symbol):
    """從 Yahoo Finance 抓取 ETF 即時數據"""
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        c = [x for x in q.get("close",[]) if x]
        v = [x for x in q.get("volume",[]) if x]
        if len(c) < 2: return None
        return {"close": c[-1], "prev": c[-2], "change": c[-1]-c[-2],
                "pct": (c[-1]-c[-2])/c[-2]*100, "volume": v[-1]}
    except Exception as e:
        print(f"⚠️ 抓取 {symbol} 失敗: {e}")
        return None

def fetch_taiex():
    """從 Yahoo Finance 抓取即時台股指數"""
    try:
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range=2d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        c = [x for x in q.get("close",[]) if x]
        if len(c) < 2: return None
        return {"close": c[-1], "prev": c[-2], "change": c[-1]-c[-2],
                "pct": (c[-1]-c[-2])/c[-2]*100}
    except Exception as e:
        print(f"⚠️ 抓取台股指數失敗: {e}")
        return None

def generate_emergency_report(taiex_data=None, etf_0050_data=None, etf_00878_data=None):
    """產出緊急應變報告"""
    snap = json.loads((LJ / "snapshot.json").read_text("utf-8"))
    items = [("證券",snap.get("securities_total_market_value",0)),
             ("保單",snap.get("insurance_current_value",0)),
             ("基金",snap.get("fund_market_value",0)),
             ("現金",snap.get("cash_total",0))]
    total = sum(v for _,v in items)
    rows = "".join(f"<tr><th>{k}</th><td>{v:,}</td></tr>" for k,v in items)
    
    market_overview = ""
    if taiex_data:
        level = "🔴 重挫" if taiex_data["pct"] < -2 else ("🟠 下跌" if taiex_data["pct"] < -1 else "🟢 正常")
        market_overview += f'''
        <div class="alert {'' if taiex_data["pct"] >= -1 else 'alert-red'}">
            <h3>📈 市場概況：台股加權指數</h3>
            <p>{level}：{taiex_data["close"]:,.2f}點 ({taiex_data["change"]:+.2f} / {taiex_data["pct"]:+.2f}%)</p>
        </div>
        '''
    else:
        market_overview = '<div class="warn">⚠️ 即時台股資料無法取得，以下為本機最後記錄</div>'

    holdings_analysis = ""
    if taiex_data and (etf_0050_data or etf_00878_data):
        holdings_analysis += "<h3>📊 持股關聯分析</h3>"
        if etf_0050_data:
            impact_0050 = "受到較大影響" if etf_0050_data["pct"] < taiex_data["pct"] * 0.8 else "與大盤走勢一致"
            holdings_analysis += f"<p><b>0050.TW (元大台灣50)</b>: {etf_0050_data['close']:,.2f}點 ({etf_0050_data['change']:+.2f} / {etf_0050_data['pct']:+.2f}%)，{impact_0050}。</p>"
        if etf_00878_data:
            impact_00878 = "受到較大影響" if etf_00878_data["pct"] < taiex_data["pct"] * 0.8 else "與大盤走勢一致"
            holdings_analysis += f"<p><b>00878.TW (國泰永續高股息)</b>: {etf_00878_data['close']:,.2f}點 ({etf_00878_data['change']:+.2f} / {etf_00878_data['pct']:+.2f}%)，{impact_00878}。</p>"
        holdings_analysis += "<p><b>009816/00984A (上櫃+ETF)</b>: 由於資料無法即時抓取，請手動關注其相關新聞與走勢。</p>"

    buffett_advice = """
    <h3>🧠 巴菲特/蒙格式建議</h3>
    <ul>
        <li><b>安全邊際</b>：市場波動時，優質資產的價格可能被低估，這是建立安全邊際的好時機。評估您持股的內在價值，避免恐慌性拋售。</li>
        <li><b>管理費侵蝕</b>：長期持有 ETF 需注意管理費對複利效果的侵蝕。定期審視您的投資組合，確保費用合理。</li>
        <li><b>集中度風險</b>：檢視您的資產配置是否過於集中在某些類別或標的。分散投資可以降低單一事件的衝擊。</li>
    </ul>
    """

    action_recommendation = """
    <h3>💡 應變行動建議</h3>
    <ul>
        <li><b>減碼</b>：若資金有其他更高報酬的用途，或持股已達預設停利點，可考慮適度減碼。</li>
        <li><b>持有</b>：若持股仍符合長期投資策略，且資金無急用，建議繼續持有，避免追高殺低。</li>
        <li><b>加碼</b>：若優質資產因市場恐慌而出現明顯折價，且您有閒置資金，可考慮分批加碼。</li>
    </ul>
    """
    
    html = f'''<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">
    <title>🚨 台股緊急應變 {today}</title>
    <style>
    body{{font-family:-apple-system,sans-serif;max-width:800px;margin:20px auto;padding:0 15px;color:#1d1d1f}}

    h1{{color:#d32f2f;font-size:28px;text-align:center;margin-bottom:20px}}

    h3{{color:#424242;font-size:20px;margin-top:25px;margin-bottom:10px;border-bottom:1px solid #eeeeee;padding-bottom:5px}}

    .alert{{background:#ffebee;padding:15px 20px;border-radius:8px;margin:15px 0;font-size:17px;font-weight:600;border-left:5px solid #d32f2f;color:#d32f2f}}

    .alert-red{{background:#ffebee;border-color:#d32f2f;color:#d32f2f}}

    .warn{{background:#fff3e0;padding:15px 20px;border-radius:8px;margin:15px 0;border-left:5px solid #f57c00;color:#f57c00}}

    table{{width:100%;border-collapse:collapse;margin:15px 0}}

    th,td{{padding:12px;text-align:right;border-bottom:1px solid #e5e5ea}}

    th{{text-align:left;font-weight:600;background:#f9f9f9}}

    ul{{list-style-type:disc;margin-left:20px;padding-left:0}}

    li{{margin-bottom:8px;line-height:1.6}}

    b{{color:#333}}

    .meta{{font-size:14px;color:#6e6e73;margin-top:20px;padding-top:15px;border-top:1px solid #e5e5ea;text-align:center}}

    </style></head><body>
    <h1>🚨 台股緊急應變報告</h1>
    <p class="meta">產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 資料源：{('Yahoo Finance' if taiex_data else 'snapshot.json')}</p>
    {market_overview}
    {holdings_analysis}
    <h3>📊 資產配置</h3>
    <table><tr><th>資產類別</th><th>金額 TWD</th></tr>{rows}
    <tr><th>合計</th><td>{total:,}</td></tr></table>
    {buffett_advice}
    {action_recommendation}
    <p class="meta">⏰ 下次執行：下個交易日 13:00</p></body></html>'''
    (LJ / f"emergency_taiex_report_{today}.html").write_text(html, "utf-8")
    print(f"✅ 緊急應變報告已產出至 emergency_taiex_report_{today}.html")


ts = datetime.now().strftime("%H%M")
print(f"\\n[{ts}] 🚨 台股緊急應變啟動")

# Main execution flow
run_step("刷新情報", [sys.executable, str(LJ / "daily_intel.py")], 60)
run_step("彙整情報", [sys.executable, str(LJ / "compile_intel.py")], 30)

taiex_realtime_data = fetch_taiex()
etf_0050_data = fetch_etf_data("0050.TW")
etf_00878_data = fetch_etf_data("00878.TW")
generate_emergency_report(taiex_realtime_data, etf_0050_data, etf_00878_data)

run_step("更新 snapshot", [sys.executable, "-c",
    f"import json; p=r'{LJ}/snapshot.json'; s=json.loads(open(p).read()); print('snapshot 已讀取')"], 15)
run_step("日報+儀表板", [sys.executable, str(LJ / "run_daily.py")], 120)
run_step("差異分析", [sys.executable, str(LJ / "asset_diff_monitor.py")], 60)
run_step("推送", [sys.executable, str(LJ / "daily_deploy.py")], 300)

print(f"\\n✅ [{datetime.now().strftime('%H%M')}] 緊急應變完成")
