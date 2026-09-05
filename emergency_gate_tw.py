"""emergency_gate_tw.py — 台股緊急應變 13:00 門檻觸發 watchdog（P1 方案A, 2026-09-06）

作為 cron monitor script：平常輸出 CALM（逐位元組與上次相同 → agent 完全抑制，
零 LLM 成本零推播）；TAIEX 當日跌幅 ≤ 閾值輸出 TRIGGER（輸出變動 → 喚醒 agent
執行現有完整緊急應變流程）。fetch 失敗輸出固定 UNKNOWN（fail-safe 趨向喚醒，
重複失敗次日相同輸出會再次抑制）。

鐵則：
- 純 stdlib（cron 環境無第三方套件，勿 import requests）
- 輸出禁止時間戳/浮動內容（monitor 為逐位元組比對，輸出漂移 = 每天誤觸發）
- 今日無交易（假日）→ CALM：以「最後一根 K 棒日期 = 今日(台北)」判別
閾值可經 data/emergency_gate.json 覆寫：{"tw": {"threshold_pct": -1.5}}
"""
import json
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

LJ = Path.home() / "Desktop" / "longjiu_system"
DEFAULT_THRESHOLD = -1.5  # TAIEX 單日跌幅百分比
SYMBOL = "%5ETWII"  # TAIEX 加權指數
TW_TZ = timezone(timedelta(hours=8))  # 台北 UTC+8


def _cfg_threshold() -> float:
    try:
        d = json.loads((LJ / "data" / "emergency_gate.json").read_text(encoding="utf-8"))
        return float(d.get("tw", {}).get("threshold_pct", DEFAULT_THRESHOLD))
    except Exception:
        return DEFAULT_THRESHOLD


def fetch_today_pct(symbol: str = SYMBOL):
    """回傳今日(台北)盤中漲跌幅 %；今日無交易/抓取失敗回 None。"""
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
    last_bar_local = datetime.fromtimestamp(ts[-1], TW_TZ).date()
    if last_bar_local != date.today():  # 今日無 K 棒 = 假日/盤未開
        return None
    return (closes[-1] - closes[-2]) / closes[-2] * 100


def classify(pct: float, threshold: float) -> str:
    """純函數，供單元測試。"""
    if pct <= threshold:
        return f"TRIGGER|TAIEX|{pct:+.2f}%"
    return "CALM"


def main() -> None:
    try:
        pct = fetch_today_pct()
    except Exception:
        print("UNKNOWN|fetch_failed")
        return
    if pct is None:
        print("CALM")
        return
    print(classify(pct, _cfg_threshold()))


if __name__ == "__main__":
    main()
