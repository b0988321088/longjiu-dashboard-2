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
            etfs, etfs_all, total_foreign = {}, {}, 0
            for r in data.get("data", []):
                if len(r) < 12:
                    continue
                code = r[0].strip()
                try:
                    fnet = int(r[4].replace(",", ""))
                except Exception:
                    continue
                total_foreign += fnet
                try:
                    etfs_all[code] = {"name": r[1].strip(), "法人淨買賣超": int(r[11].replace(",", ""))}
                except Exception:
                    pass
                if code in watch:
                    etfs[code] = fnet
            return {"date": f"{d:%Y-%m-%d}", "外資總買賣超": total_foreign, "etfs": etfs, "etfs_all": etfs_all}
        except Exception as e:
            return {"error": str(e)[:80], "date": f"{d:%Y-%m-%d}"}
    return {"error": "近 6 日無交易資料", "date": f"{(day or date.today()):%Y-%m-%d}"}


def fetch_cftc():
    """CFTC COT 非商業淨多單（Socrata API 6dca-aqww Legacy - Futures Only）。
    黃金/原油抓最新+前一期算週增減；美債10年 CFTC 公開資料僅至 2022-02-01（改用 fetch_tnx 殖利率動能代理）。回傳 {date, contracts}"""
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


def fetch_tnx():
    """10年美債殖利率動能（Yahoo ^TNX range=1mo）— 代理美債10年聰明錢方向（CFTC 公開資料僅至2022）。
    殖利率↓ = 債券價格↑ = 聰明錢買債 → 債券綠燈。回傳 {date, last, momentum}"""
    try:
        raw = http_get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?range=1mo&interval=1d")
        d = json.loads(raw.decode("utf-8"))
        closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c]
        if len(closes) >= 2:
            return {"date": date.today().isoformat(), "last": closes[-1], "momentum": (closes[-1] - closes[0]) / closes[0] * 100}
    except Exception:
        pass
    return {"error": "TNX 抓取失敗"}


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


# ─────────────────────────── Phase 2：產業資金流向 ───────────────────────────

# 台股 ETF → 產業桶（名稱關鍵字優先，輔以代碼集）
_TW_SECTOR_CODES = {
    "0050": "市值型", "006208": "市值型", "009816": "市值型", "00850": "市值型", "006204": "市值型",
    "00924": "科技", "00891": "科技", "00895": "科技", "00851": "科技", "00981A": "科技",
    "0055": "金融", "00635U": "原物料避險", "00642U": "原物料避險", "00738U": "原物料避險",
    "00679B": "債券", "00795B": "債券", "00937B": "債券", "00751B": "債券",
    "00878": "高股息防禦", "0056": "高股息防禦", "00919": "高股息防禦", "00918": "高股息防禦",
    "00713": "高股息防禦", "00929": "高股息防禦", "00934": "高股息防禦", "00936": "高股息防禦",
    "00940": "高股息防禦", "00944": "高股息防禦", "00900": "高股息防禦",
}


def _tw_sector_bucket(code: str, name: str) -> str:
    if code in _TW_SECTOR_CODES:
        return _TW_SECTOR_CODES[code]
    # 個股/ETF 名稱關鍵字分類（依順序檢查，先專有名詞後通用）
    for kw_bucket, kws in _TW_NAME_KW:
        if any(k in name for k in kws):
            return kw_bucket
    if any(k in name for k in ["科技", "半導體", "5G", "AI", "伺服器", "機器人", "ICT"]):
        return "科技"
    if any(k in name for k in ["金融", "銀行"]):
        return "金融"
    if any(k in name for k in ["高息", "高股息", "低波", "永續高息"]):
        return "高股息防禦"
    if "債" in name:
        return "債券"
    if any(k in name for k in ["黃金", "石油", "原物料", "能源"]):
        return "原物料避險"
    return "其他"


# 個股名稱 → 產業桶（T86 含全部上市櫃，名稱關鍵字分類；順序=優先權）
_TW_NAME_KW = [
    ("台積電", ["台積電", "積電"]),
    ("科技", ["聯發科", "鴻海", "廣達", "緯創", "英業達", "仁寶", "和碩", "日月光", "聯電", "台達電",
               "大立光", "瑞昱", "聯詠", "矽力", "力積電", "南亞科", "華邦電", "旺宏", "群創", "友達",
               "佳世達", "研華", "光寶", "台光電", "欣興", "景碩", "譜瑞", "祥碩", "創意", "世芯"]),
    ("通訊服務", ["中華電", "遠傳", "台灣大", "台灣大哥大"]),
    ("金融", ["金控", "銀行", "證券", "保險", "產險", "壽險", "租賃", "票券"]),
    ("生技醫療", ["生技", "藥", "醫", "美時", "葡萄王", "大樹", "合一"]),
    ("航運", ["長榮", "陽明", "萬海", "華航", "長榮航", "星宇"]),
    ("鋼鐵", ["中鋼", "鋼鐵", "豐興", "東和"]),
    ("塑化", ["台塑", "南亞", "台化", "台塑化", "塑膠", "石化"]),
    ("食品", ["統一", "味全", "大成", "卜蜂", "佳格", "聯華食"]),
    ("能源", ["台電", "綠能", "中興電", "士電", "華城"]),
    ("汽車", ["裕隆", "和泰", "中華車", "三陽", "東陽"]),
    ("營建", ["台泥", "亞泥", "潤泰", "興富發", "遠雄", "國建", "皇翔"]),
    ("百貨", ["遠百", "特力", "統一超", "全家"]),
    ("不動產", ["信義", "永慶", "愛山林"]),
]


def aggregate_tw_sector(tw: dict) -> dict:
    """將 T86 全部標的（ETF+個股）法人淨買賣超依產業桶彙總（Phase 2）"""
    agg = {}
    for code, v in (tw.get("etfs_all") or {}).items():
        b = _tw_sector_bucket(code, v.get("name", ""))
        agg.setdefault(b, {"法人淨買賣超": 0, "檔數": 0})
        agg[b]["法人淨買賣超"] += v.get("法人淨買賣超", 0)
        agg[b]["檔數"] += 1
    for b in agg:
        agg[b]["方向"] = "inflow" if agg[b]["法人淨買賣超"] > 0 else ("outflow" if agg[b]["法人淨買賣超"] < 0 else "neutral")
    return agg


def fetch_us_sector():
    """美股 SPDR 板塊 ETF 月動能 + relative strength vs SPY（Phase 2，Yahoo 免費）"""
    SECTOR_ETFS = {"XLK": "科技", "XLF": "金融", "XLV": "醫療", "XLE": "能源", "XLY": "非核心消費",
                   "XLP": "核心消費", "XLI": "工業", "XLU": "公用", "XLRE": "不動產", "XLB": "原物料"}
    spy_mom = None
    try:
        raw = http_get("https://query1.finance.yahoo.com/v8/finance/chart/SPY?range=1mo&interval=1d")
        closes = [c for c in json.loads(raw.decode("utf-8"))["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
        if len(closes) >= 2:
            spy_mom = (closes[-1] - closes[0]) / closes[0] * 100
    except Exception:
        pass
    out = {}
    for tk, name in SECTOR_ETFS.items():
        try:
            raw = http_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}?range=1mo&interval=1d")
            closes = [c for c in json.loads(raw.decode("utf-8"))["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                mom = (closes[-1] - closes[0]) / closes[0] * 100
                rs = round(mom - spy_mom, 1) if spy_mom is not None else None
                out[tk] = {"產業": name, "動能%": round(mom, 1), "RS_vs_SPY": rs,
                           "方向": "inflow" if mom > 0.5 else ("outflow" if mom < -0.5 else "neutral")}
        except Exception:
            continue
    return {"date": date.today().isoformat(), "spy_動能%": round(spy_mom, 1) if spy_mom is not None else None, "etfs": out}


def compute_sector_flow(tw, us_sec, state):
    """產業資金流向 → 寫入 state['sector_flow']（Phase 2）"""
    flow = {"generated_at": datetime.now().isoformat()}

    # 台股產業桶
    tw_sector = aggregate_tw_sector(tw)
    flow["台股"] = tw_sector

    # 美股板塊
    us_out = {}
    for tk, v in (us_sec or {}).get("etfs", {}).items():
        us_out[f"{v['產業']}({tk})"] = {"動能%": v["動能%"], "RS_vs_SPY": v.get("RS_vs_SPY"), "方向": v["方向"]}
    flow["美股"] = us_out
    flow["SPY基準"] = us_sec.get("spy_動能%") if us_sec else None

    # 輪動總結：台股最強/最弱桶 + 美股 RS 最強板塊
    try:
        tw_sorted = sorted(tw_sector.items(), key=lambda x: -x[1]["法人淨買賣超"])
        if tw_sorted:
            parts = [f"{b} {v['法人淨買賣超']/1e6:+.0f}百萬" for b, v in tw_sorted if v["法人淨買賣超"]]
            flow["台股總結"] = "法人淨買賣超：" + "，".join(parts)
    except Exception:
        pass
    try:
        us_sorted = sorted(us_out.items(), key=lambda x: -(x[1]["RS_vs_SPY"] or -99))
        if us_sorted and us_sorted[0][1]["RS_vs_SPY"] is not None:
            flow["美股總結"] = f"RS最強 {us_sorted[0][0]}（{us_sorted[0][1]['RS_vs_SPY']:+.1f}pp vs SPY）｜最弱 {us_sorted[-1][0]}"
    except Exception:
        pass

    state["sector_flow"] = flow
    return flow


# ─────────────────────────── Signals ───────────────────────────

def compute_signals(tw, cot, fed, twd, tnx, cfg, state):
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

    # 避險衛星（黃金/原油）：COT 聰明錢方向（美債10年改用 TNX 動能，見下方）
    for key in ["黃金", "原油"]:
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

    # 美債10年：CFTC 公開資料僅至 2022 → 用 10Y 殖利率動能代理（殖利率↓=買債=順勢）
    if tnx.get("momentum") is not None:
        mom = tnx["momentum"]
        if mom <= -2.0:
            sig["美債10年"] = {"color": "🟢", "note": f"10Y殖利率月動能 {mom:+.1f}%（債價↑ 買債順勢）"}
        elif mom <= 0:
            sig["美債10年"] = {"color": "🟢", "note": f"10Y殖利率月動能 {mom:+.1f}%（緩步下行，偏順勢）"}
        elif mom <= 3.0:
            sig["美債10年"] = {"color": "🟡", "note": f"10Y殖利率月動能 {mom:+.1f}%（上行，債券觀望）"}
        else:
            sig["美債10年"] = {"color": "🔴", "note": f"10Y殖利率月動能 {mom:+.1f}%（急升，債券承壓）"}
    else:
        sig["美債10年"] = {"color": "⚪", "note": "TNX 資料待接"}

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


def render_summary(sig, tw, cot, fed, sector_flow=None):
    lines = [f"📡 機構流向雷達 {date.today().isoformat()}"]
    reds = [k for k, v in sig.items() if (v.get("color") or "").startswith("🔴")]
    yellows = [k for k, v in sig.items() if (v.get("color") or "").startswith("🟡")]
    lines.append(f"燈號：🔴紅 {len(reds)}｜🟡黃 {len(yellows)}｜綠 {sum(1 for v in sig.values() if (v.get('color') or '').startswith('🟢'))}")
    for k, v in sig.items():
        lines.append(f"  {v.get('color') or '⚪'} {k}：{v['note']}")
    if tw.get("etfs"):
        etf_txt = "、".join(f"{k} {v/1000:+.0f}千" for k, v in tw["etfs"].items() if v)
        lines.append(f"  追蹤ETF法人：{etf_txt}")
    # Phase 2：產業資金流向摘要
    if sector_flow:
        lines.append("  ── 產業資金流向（Phase 2）──")
        if sector_flow.get("台股總結"):
            lines.append(f"  台股：{sector_flow['台股總結']}")
        if sector_flow.get("美股總結"):
            lines.append(f"  美股：{sector_flow['美股總結']}")
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
    tnx = fetch_tnx()
    us_sec = fetch_us_sector()

    sig = compute_signals(tw, cot, fed, twd, tnx, cfg, state)
    sector_flow = compute_sector_flow(tw, us_sec, state)  # Phase 2：產業資金流向
    state["last_run"] = datetime.now().isoformat()
    # 瘦身：etfs_all（14,867 筆）不寫入 state，只保留彙總結果，避免 radar_state 膨脹
    _tw_slim = {k: v for k, v in tw.items() if k != "etfs_all"}
    state["data"] = {"twse": _tw_slim, "cot": cot, "fed": fed, "twd": twd, "tnx": tnx, "us_sector": us_sec}
    state["signals"] = sig
    state["sector_flow"] = sector_flow
    save_json(BASE / "radar_state.json", state)

    summary = render_summary(sig, tw, cot, fed, sector_flow)
    print(summary)

    # 黃/紅燈輸出給 cron 判斷（非空即有警示）
    alerts = [f"{k}：{v['note']}" for k, v in sig.items() if v["color"].startswith(("🔴", "🟡"))]
    if alerts:
        print("\n⚠️ ALERTS:\n" + "\n".join("  " + a for a in alerts))
    # 政策面標註（2026-08-29：使用者提供貝森特會議升息可能 → 原油政策利空 vs COT 機械綠燈矛盾）
    try:
        _pn = (state.get("policy_notes") or {})
        if _pn:
            print("\n🏛️ 政策面標註:\n  " + _pn.get("內容", ""))
            if _pn.get("與雷達衝突"):
                print("  ⚠️ " + _pn["與雷達衝突"])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
