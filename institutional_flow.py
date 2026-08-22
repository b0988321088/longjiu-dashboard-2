# -*- coding: utf-8 -*-
"""
institutional_flow.py — 機構流向雷達 (Institutional Flow Radar)
==============================================================
追蹤大資金流向 + 機構配置邏輯，避免單壓方向。

資料源：
  - 證交所三大法人（每日）：https://www.twse.com.tw/fund/T86
  - CFTC COT（每週五）：https://www.cftc.gov/dea/newcot/com_disagg.txt
  - Fed H.4.1（每週四）：https://www.federalreserve.gov/releases/h41/current/h41.htm
  - USD/TWD（每日）：Yahoo chart API（判斷台幣強升）

輸出：
  - radar_state.json  — 單一真值（日報/週報/TG 都讀這份）
  - 摘要 markdown（stdout，供 cron 推送）

燈號邏輯（radar_config.json 可調）：
  🟢 綠：機構流向 與 個人加碼方向 一致（順勢）
  🟡 黃：個人策略與機構反向（暫停自動加碼，日報載明理由）
  🔴 紅：機構大規模撤離但個人擬加碼（凍結該資產調度）
"""
import json, os, re, ssl, sys, urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")
SSL_CTX = ssl.create_default_context()
try:
    SSL_CTX = ssl._create_unverified_context()  # CFTC 舊證書相容
except Exception:
    pass

DEFAULT_CONFIG = {
    "twse": {
        "watch_etfs": ["00878", "0050", "006208", "009816", "00919", "00635U"],
        "外資連續買超_綠": 1,     # 連續 N 日外資淨買超 → 台股綠
        "外資連續賣超_黃": 2,     # 連續 N 日外資淨賣超 → 台股黃
        "外資單日賣超_紅": -2000000000,  # 單日外資賣超 ≥ 20億 → 紅（台股大撤離）
    },
    "cot": {
        "contracts": {
            "黃金": {"keyword": "GOLD", "週增減_綠": 0.0},   # 非商業淨多單週增 → 綠
            "原油": {"keyword": "WTI", "週增減_綠": 0.0},
            "美債10年": {"keyword": "10-YEAR", "週增減_綠": 0.0},
        },
        "週增減_紅": -0.10,  # 非商業淨多單週減 > 10% → 紅
    },
    "fed": {
        "週增_綠": 0.0,       # 資產負債表週增 → 流動性擴張綠
        "週減_紅": -0.02,     # 週減 > 2% → 紅
    },
    "twd": {
        "強升_綠_upgrade": -0.005,  # 台幣單週升值 > 0.5% → 綠燈升級
    },
}


def load_json(p, default=None):
    if Path(p).exists():
        try:
            return json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception:
            pass
    return default if default is not None else {}


def save_json(p, obj):
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX).read()


# ─────────────────────────── Fetchers ───────────────────────────

def fetch_twse(day=None):
    """證交所三大法人買賣超（含各標的明細）。週末/休市自動往前找最近交易日。回傳 {date, 外資總買賣超, etfs}"""
    cfg = load_json(BASE / "radar_config.json", DEFAULT_CONFIG)
    watch = set(cfg["twse"]["watch_etfs"])
    for back in range(0, 6):
        d = (day or date.today()) - timedelta(days=back)
        if d.weekday() >= 5:  # 六日跳過
            continue
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={d:%Y%m%d}&selectType=ALL"
        try:
            data = json.loads(http_get(url).decode("utf-8"))
            if data.get("stat") != "OK":
                continue
            etfs, total_foreign = {}, 0
            for r in data.get("data", []):
                if len(r) < 12:
                    continue
                code = r[0].strip()
                try:
                    fnet = int(r[4].replace(",", ""))
                except Exception:
                    continue
                total_foreign += fnet
                if code in watch:
                    etfs[code] = fnet
            return {"date": f"{d:%Y-%m-%d}", "外資總買賣超": total_foreign, "etfs": etfs}
        except Exception as e:
            return {"error": str(e)[:80], "date": f"{d:%Y-%m-%d}"}
    return {"error": "近 6 日無交易資料", "date": f"{(day or date.today()):%Y-%m-%d}"}


def fetch_cftc():
    """CFTC COT 非商業淨多單（Socrata API 6dca-aqww，取代已下架的新舊 txt 檔）。
    黃金/原油抓最新+前一期算週增減；美債10年 TFF 資料至 2022（v1 標待接）。回傳 {date, contracts}"""
    ctx = SSL_CTX
    api = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
    specs = {
        "黃金": "GOLD%20-%20COMMODITY%20EXCHANGE%20INC%25",
        "原油": "CRUDE%20OIL%2C%20LIGHT%20SWEET-WTI%25",
    }
    contracts = {}
    for key, like in specs.items():
        try:
            url = f"{api}?$where=market_and_exchange_names%20like%20%27{like}%27&$limit=2&$order=report_date_as_yyyy_mm_dd%20DESC"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            rows = json.loads(urllib.request.urlopen(req, timeout=30, context=ctx).read().decode("utf-8"))
            if not rows:
                continue
            cur = rows[0]
            prev = rows[1] if len(rows) > 1 else None
            contracts[key] = {
                "net": round(float(cur.get("noncomm_positions_long_all", 0)) - float(cur.get("noncomm_positions_short_all", 0))),
                "prev": round(float(prev.get("noncomm_positions_long_all", 0)) - float(prev.get("noncomm_positions_short_all", 0))) if prev else None,
                "date": str(cur.get("report_date_as_yyyy_mm_dd", ""))[:10],
            }
        except Exception as e:
            contracts[key] = {"error": str(e)[:60]}
    return {"date": contracts.get("黃金", {}).get("date"), "contracts": contracts}


def fetch_fed():
    """Fed H.4.1 總資產。回傳 {date, total_assets}"""
    try:
        h = http_get("https://www.federalreserve.gov/releases/h41/current/h41.htm").decode("utf-8", errors="ignore")
        m = re.search(r"Total factors supplying reserve funds.*?<td[^>]*>\s*([\d,]+\.?\d*)", h, re.S)
        if not m:
            return {"error": "H.4.1 解析失敗"}
        return {"date": date.today().isoformat(), "total_assets": float(m.group(1).replace(",", ""))}
    except Exception as e:
        return {"error": str(e)[:80]}


def fetch_twd():
    """USD/TWD 匯率（Yahoo chart，range=5d 取週變化）"""
    try:
        raw = http_get("https://query1.finance.yahoo.com/v8/finance/chart/TWD=X?range=5d&interval=1d")
        d = json.loads(raw.decode("utf-8"))
        closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c]
        if len(closes) >= 2:
            return {"date": date.today().isoformat(), "last": closes[-1], "週變化": (closes[-1] - closes[0]) / closes[0]}
    except Exception:
        pass
    return {"error": "匯率抓取失敗"}


# ─────────────────────────── Signals ───────────────────────────

def compute_signals(tw, cot, fed, twd, cfg, state):
    """三色燈號。回傳 {signals: {類別: {color, note}}, summary}"""
    sig = {}
    c = cfg
    today = date.today().isoformat()

    # 台股：外資方向 vs 個人台股慢慢買（順勢/反向）
    tw_sig = "⚪"
    tw_note = "—"
    if "外資總買賣超" not in tw:
        tw_note = "無交易日資料（週末/休市）"
    else:
        fnet = tw["外資總買賣超"]
        prev_days = state.get("twse", {}).get("外資連日", [])
        streak = (prev_days + [fnet])[-3:] if fnet else prev_days
        buy_days = sum(1 for v in streak[-3:] if v > 0)
        if fnet < c["twse"]["外資單日賣超_紅"]:
            tw_sig, tw_note = "🔴", f"外資單日賣超 {fnet/1e8:.1f}億 大撤離 — 凍結台股加碼"
        elif buy_days >= c["twse"]["外資連續買超_綠"]:
            tw_sig, tw_note = "🟢", f"外資淨買超 {fnet/1e8:.1f}億（連{buy_days}日）— 台股慢慢買順勢"
        elif sum(1 for v in streak[-3:] if v < 0) >= c["twse"]["外資連續賣超_黃"]:
            tw_sig, tw_note = "🟡", f"外資連賣 — 台股加碼暫緩，等方向"
        else:
            tw_sig, tw_note = "⚪", f"外資淨買超 {fnet/1e8:.1f}億 — 中性"
        state.setdefault("twse", {})["外資連日"] = streak[-3:]
    sig["台股"] = {"color": tw_sig, "note": tw_note}

    # 避險衛星（黃金/原油）+ 債券：COT 聰明錢方向
    for key in ["黃金", "原油", "美債10年"]:
        cc = cot.get("contracts", {}).get(key)
        if not cc or cc.get("error"):
            sig[key] = {"color": "⚪", "note": "COT 資料待接（美債10年 CFTC 僅至2022）" if key == "美債10年" else "COT 無資料"}
            continue
        prev = cc.get("prev") or state.get("cot", {}).get(key, {}).get("net")
        chg = ((cc["net"] - prev) / abs(prev)) if prev else 0
        threshold = c["cot"]["週增減_紅"]
        if prev is None:
            sig[key] = {"color": "⚪", "note": f"淨多單 {cc['net']:,}（基準建立中）"}
        elif chg <= threshold:
            sig[key] = {"color": "🔴", "note": f"淨多單 {cc['net']:,} 週減 {chg*100:.1f}% — 聰明錢撤離"}
        elif chg >= 0:
            sig[key] = {"color": "🟢", "note": f"淨多單 {cc['net']:,} 週增 {chg*100:.1f}% — 順勢"}
        else:
            sig[key] = {"color": "🟡", "note": f"淨多單 {cc['net']:,} 週減 {chg*100:.1f}% — 觀望"}
        state.setdefault("cot", {})[key] = {"net": cc["net"], "date": cc["date"]}

    # Fed 流動性
    if fed.get("total_assets"):
        prev_fed = state.get("fed", {}).get("total_assets")
        if prev_fed:
            chg = (fed["total_assets"] - prev_fed) / prev_fed
            if chg <= c["fed"]["週減_紅"]:
                sig["Fed流動性"] = {"color": "🔴", "note": f"資產負債表週縮 {chg*100:.1f}%"}
            elif chg >= c["fed"]["週增_綠"]:
                sig["Fed流動性"] = {"color": "🟢", "note": f"資產負債表週擴 {chg*100:.1f}%"}
            else:
                sig["Fed流動性"] = {"color": "🟡", "note": f"資產負債表 {chg*100:+.1f}%"}
        else:
            sig["Fed流動性"] = {"color": "⚪", "note": f"總資產 {fed['total_assets']/1e9:.0f}B（基準建立中）"}
        state["fed"] = {"total_assets": fed["total_assets"], "date": fed["date"]}

    # 台幣強升 → 綠燈升級
    if twd.get("週變化") is not None:
        if twd["週變化"] <= c["twd"]["強升_綠_upgrade"]:
            for k, v in sig.items():
                if v["color"] == "🟢":
                    v["color"] = "🟢🔥"
                    v["note"] += "＋台幣強升，升級強烈綠燈"
        sig["台幣"] = {"color": "⚪", "note": f"USD/TWD {twd.get('last', 0):.2f} 週變化 {twd.get('週變化', 0)*100:+.2f}%"}

    return sig


def render_summary(sig, tw, cot, fed):
    lines = [f"📡 機構流向雷達 {date.today().isoformat()}"]
    reds = [k for k, v in sig.items() if (v.get("color") or "").startswith("🔴")]
    yellows = [k for k, v in sig.items() if (v.get("color") or "").startswith("🟡")]
    lines.append(f"燈號：🔴紅 {len(reds)}｜🟡黃 {len(yellows)}｜綠 {sum(1 for v in sig.values() if (v.get('color') or '').startswith('🟢'))}")
    for k, v in sig.items():
        lines.append(f"  {v.get('color') or '⚪'} {k}：{v['note']}")
    if tw.get("etfs"):
        etf_txt = "、".join(f"{k} {v/1000:+.0f}千" for k, v in tw["etfs"].items() if v)
        lines.append(f"  追蹤ETF法人：{etf_txt}")
    return "\n".join(lines)


def main():
    cfg = load_json(BASE / "radar_config.json", DEFAULT_CONFIG)
    if not Path(BASE / "radar_config.json").exists():
        save_json(BASE / "radar_config.json", DEFAULT_CONFIG)
    state = load_json(BASE / "radar_state.json", {})

    tw = fetch_twse()
    cot = fetch_cftc()
    fed = fetch_fed()
    twd = fetch_twd()

    sig = compute_signals(tw, cot, fed, twd, cfg, state)
    state["last_run"] = datetime.now().isoformat()
    state["data"] = {"twse": tw, "cot": cot, "fed": fed, "twd": twd}
    state["signals"] = sig
    save_json(BASE / "radar_state.json", state)

    summary = render_summary(sig, tw, cot, fed)
    print(summary)

    # 黃/紅燈輸出給 cron 判斷（非空即有警示）
    alerts = [f"{k}：{v['note']}" for k, v in sig.items() if v["color"].startswith(("🔴", "🟡"))]
    if alerts:
        print("\n⚠️ ALERTS:\n" + "\n".join("  " + a for a in alerts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
