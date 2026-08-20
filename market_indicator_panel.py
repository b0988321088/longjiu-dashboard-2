#!/usr/bin/env python3
"""市場指標燈號面板（2026-08-21 定版）— 日報 + 週報共用。
主觸發：US30Y(即時) / 巴菲特 / VIX / CPI（後三者待外部數據源，None 不觸發）
質押比例：擔保池 / 質押金額 / LTV / 成數上限 / 壓力情境
輔助觀察：匯率 / 黃金 / 原油 / 科技曝險
"""
import json
import re
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _fetch_us30y_live(timeout: int = 8) -> float | None:
    """Yahoo ^TYX 即時（FRED 延遲 1-2 天）；失敗回傳 None"""
    try:
        req = urllib.request.Request(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ETYX?range=5d&interval=1d",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
        closes = [c for c in data["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
        return float(closes[-1]) if closes else None
    except Exception:
        return None


def _light_for_us30y(r: float) -> str:
    if r < 4.8:
        return "🟢 綠燈"
    if r < 5.30:
        return "🟡 黃燈"
    return "🔴 紅燈"


def build_panel(snap: dict | None = None) -> str:
    """產出市場指標燈號面板 HTML（含質押比例）"""
    s = snap or json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    eng = s.get("market_indicator_engine", {})
    us30y = _fetch_us30y_live()
    if us30y is None:
        us30y = (s.get("rhythm08", {}).get("indicators", {}) or {}).get("us30y")
    us30y = float(us30y) if us30y else None
    light = _light_for_us30y(us30y) if us30y else "—（無 US30Y 資料）"

    # 質押比例（8/20 定案）
    pz = (s.get("cathay_disbursement", {}).get("plan_0820_final", {}) or {}).get("質押計畫", {})
    pledge_amt = pz.get("金額_保守版", "350萬")
    m = re.search(r"質押\s*([\d,]+萬)", str(pledge_amt))
    pledge_amt = m.group(1) if m else "350萬"
    collateral = "擔保池 700萬（富達600+聯博100）"
    ltv_now = 0  # 尚未質押
    ltv_light = "🟢 ≤53%"
    if ltv_now:
        ltv_light = "🟢" if ltv_now <= 53 else ("🟡" if ltv_now <= 58 else "🔴")

    # 科技曝險
    pen_pct = s.get("penetration", {}).get("actual_pct", {})
    tech = pen_pct.get("美股市值型成長_科技", 0)
    tech_light = "🟢" if tech <= 15 else ("🟡" if tech <= 20 else "🔴")

    # 美元曝險
    usd = (s.get("usd_exposure_monitor", {}) or {}).get("current", {}) or {}
    usd_pct = usd.get("合計", 0)
    usd_light = "🟢" if usd_pct <= 50 else ("🟡" if usd_pct <= 55 else "🔴")

    rows = []
    rows.append(
        f"<div class='callout' style='margin-top:12px;border-left:3px solid "
        f"{'#22c55e' if '綠' in light else ('#f59e0b' if '黃' in light else '#ef4444')}'>"
    )
    rows.append(f"<h3>🚦 市場指標燈號面板（DAA｜2026-08-21 定版）｜目前：{light}</h3>")
    rows.append("<div style='font-size:12.5px;line-height:1.9'>")
    rows.append(
        f"<strong>① 主觸發：</strong>US30Y {us30y:.2f}% → {light}（🟢<4.8 / 🟡4.8~5.3 / 🔴≥5.30）｜"
        f"巴菲特 —（待數據）｜VIX —｜CPI —<br/>"
    )
    rows.append(
        f"<strong>② 質押比例：</strong>{collateral}｜質押上限 {pledge_amt}（50%，銀行口頭待書面）｜"
        f"目前 LTV {ltv_now}% {ltv_light}<br/>"
        f"&nbsp;&nbsp;&nbsp;&nbsp;壓力情境：富達-30%＋聯博-20% → 擔保池 500萬 → LTV 70% 💥 追繳警戒<br/>"
    )
    rows.append(
        f"<strong>③ 輔助觀察（不單獨觸發）：</strong>匯率 —｜黃金 —｜原油 —｜"
        f"科技曝險 {tech:.1f}% {tech_light}（≤15/≤20/&gt;20）｜美元曝險 {usd_pct:.1f}% {usd_light}（≤50/≤55/&gt;55）<br/>"
    )
    rows.append(
        f"<strong>④ 執行紀律：</strong>動態偏移 ≤±10%（vs SAA）｜±5pp 再平衡閾值｜週六正式評估｜"
        f"個人硬性約束 &gt; 市場訊號（質押≤50%／PI先於還債／現金底線70萬）"
    )
    rows.append("</div></div>")
    return "\n".join(rows)


if __name__ == "__main__":
    print(build_panel())
