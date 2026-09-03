#!/usr/bin/env python3
"""entry_monitor.py — 進場提醒監控（2026-08-24 建立）
使用者要求：「要提醒我哪時候進場，告知我，不是跟我講自己觀察」
每日檢查進場條件 → 達成 → TG 通知（明確：買什麼/多少/何時）

進場計畫（entry_plan.json，可調）：
  台股慢慢買：PI 認列（snapshot.pi_status）→ 每週 0050/006208 1.5-2萬
  美股減碼：SPY/費半 反彈 ≥2% → 00646/009823/009824 ≤20萬
  黃金衛星：00635U 回檔 -3% 或 PI 後 → 第一批 20萬
  PI 質押：PI 認列 → 質押富達 350萬 還債（安聯300+元大50）
  保單轉換：8/25 執行（PIMCO M120/M&G 115/健康25/黃金A10 15）
"""
import json, os, sys, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
TG_TOKEN = os.environ.get("TG_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

def _tg_send(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        print(text)
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=15)
    except Exception as e:
        print(f"⚠️ TG 失敗: {e}\n{text}")

def _yf_close(sym):
    import urllib.request, urllib.parse
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=10d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=15).read())
    closes = [c for c in d['chart']['result'][0]['indicators']['quote'][0]['close'] if c]
    return closes

def main():
    today = datetime.date.today()
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    alerts = []

    # 1. PI 認列（9/3 前）→ 台股慢慢買 + 質押還債 + 黃金衛星啟動
    pi = snap.get("pi_status", {}) or {}
    pi_done = pi.get("認列") in (True, "✅", "已認列") or "認列" in str(pi.get("status", ""))
    if pi_done:
        alerts.append("🎯 PI 已認列 → 執行鏈啟動：\n├ 台股慢慢買 0050/006208（每週 1.5-2萬）\n├ 質押富達 350萬@2.77% 還安聯300+元大50\n└ 黃金衛星 00635U 第一批 ≤20萬")
    else:
        _days = (datetime.date(2026, 9, 3) - today).days
        if 0 <= _days <= 3:
            alerts.append(f"⏰ PI 認列剩 {_days} 天（9/3 前）→ 準備執行鏈（質押還債/慢慢買/衛星）")

    # 2. 美股減碼：SPY 反彈 ≥2%（10 日內低點）
    try:
        spy = _yf_close("SPY")
        if len(spy) >= 5:
            low = min(spy[-10:])
            bounce = (spy[-1] - low) / low * 100
            if bounce >= 2:
                alerts.append(f"📈 美股反彈 {bounce:.1f}%（10日低點）→ 可減碼 00646/009823/009824 ≤20萬/次（逢彈紀律）")
    except Exception:
        pass

    # 3. 黃金衛星：00635U 回檔 -3%（10 日內高點）或 PI 後
    try:
        g = _yf_close("00635U.TW")
        if len(g) >= 5:
            hi = max(g[-10:])
            drawdown = (g[-1] - hi) / hi * 100
            if drawdown <= -3 and not pi_done:
                alerts.append(f"🥇 黃金回檔 {drawdown:.1f}% → 00635U 可進第一批（≤20萬，回檔紀律）")
            elif drawdown <= -3 and pi_done:
                alerts.append(f"🥇 黃金回檔 {drawdown:.1f}% + PI 已認列 → 00635U 第一批 20萬 可執行")
    except Exception:
        pass

    # 4. 保單轉換（8/25）提醒
    if today == datetime.date(2026, 8, 25):
        alerts.append("🔴 今日執行保單轉換 300萬：PIMCO(M級月配)120 + M&G 115 + 健康科學A2 25 + 黃金A10 15")

    # 5. 台股慢慢買例行（PI 後每週）
    if pi_done and today.weekday() == 0:
        alerts.append("🇹🇼 週一 → 台股慢慢買 0050/006208（每週 1.5-2萬）")

    if alerts:
        print("📡 龍九進場提醒 " + today.isoformat() + "\n" + "\n".join(alerts))
    else:
        print("✅ 無進場條件觸發（安靜）")

if __name__ == "__main__":
    main()
