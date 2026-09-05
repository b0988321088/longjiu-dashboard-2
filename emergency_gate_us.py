"""emergency_gate_us.py — 美股緊急應變 21:30 門檻觸發 watchdog（P1 方案A, 2026-09-06）

作為 cron monitor script：平常輸出 CALM（與上次相同 → agent 完全抑制，零成本）；
S&P500 當日跌幅 ≤ -1.8% 或費半(SOX) ≤ -2.5% 輸出 TRIGGER（輸出變動 → 喚醒 agent
執行現有完整流程）。fetch 失敗輸出固定 UNKNOWN（fail-safe 趨向喚醒）。

鐵則：
- 純 stdlib（cron 環境無第三方套件）；輸出禁止時間戳（逐位元組比對）
- 美股假日（如 Labor Day）：今日無 K 棒 → CALM。以最後一根 K 棒日期 = 今日(美東)判別
- 美東時區：2026-11-01 前 EDT=UTC-4，其後 EST=UTC-5（夏令時間截止日）
閾值可經 data/emergency_gate.json 覆寫：{"us": {"spx_pct": -1.8, "sox_pct": -2.5}}
"""
import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
DEFAULT_SPX = -1.8  # S&P500
DEFAULT_SOX = -2.5  # 費城半導體（持股相關，次級觸發線）

# 美東 = UTC-4 (EDT) 直到 2026-11-01 日光節約結束；其後 EST = UTC-5
US_TZ = timezone(timedelta(hours=-4 if date.today() < date(2026, 11, 1) else -5))


def _cfg() -> tuple:
    try:
        d = json.loads((LJ / "data" / "emergency_gate.json").read_text(encoding="utf-8"))
        us = d.get("us", {})
        return (
            float(us.get("spx_pct", DEFAULT_SPX)),
            float(us.get("sox_pct", DEFAULT_SOX)),
        )
    except Exception:
        return DEFAULT_SPX, DEFAULT_SOX


def fetch_today_pct(symbol: str):
    """回傳今日(美東)漲跌幅 %；今日無交易/抓取失敗回 None。"""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?interval=1d&range=5d"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    res = d["chart"]["result"][0]
    closes = [x for x in res["indicators"]["quote"][0].get("close", []) if x]
    ts = res.get("timestamp", [])
    if len(closes) < 2 or not ts:
        return None
    last_bar_local = datetime.fromtimestamp(ts[-1], US_TZ).date()
    if last_bar_local != date.today():  # 今日無 K 棒 = 假日/盤未開（21:30 TW = 09:30 ET）
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100


def classify(pcts: dict, spx_th: float, sox_th: float) -> str:
    """純函數，供單元測試。任一觸發即 TRIGGER。"""
    for sym, pct in pcts.items():
        th = sox_th if "SOX" in sym else spx_th
        if pct <= th:
            return f"TRIGGER|{sym}|{pct:+.2f}%"
    return "CALM"


def main() -> None:
    spx_th, sox_th = _cfg()
    pcts = {}
    try:
        p = fetch_today_pct("%5EGSPC")
        if p is not None:
            pcts["SPX"] = p
        p = fetch_today_pct("%5ESOX")
        if p is not None:
            pcts["SOX"] = p
    except Exception:
        print("UNKNOWN|fetch_failed")
        return
    if not pcts:  # 兩個都無今日 K 棒（假日）或空
        print("CALM")
        return
    print(classify(pcts, spx_th, sox_th))


if __name__ == "__main__":
    main()
