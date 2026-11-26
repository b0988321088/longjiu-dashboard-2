#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盤前快報（2026-11-25 使用者要求：早上看昨夜台指期夜盤＋對策方向＋流向雷達整體評估）

四段：
  ① 夜盤台指期結果（期交所 MIS，盤後 MarketType=1）與今日開盤方向推估
  ② 美股隔夜（S&P500／納斯達克／費半／台積電 ADR／VIX）
  ③ 對策方向：五桶 vs 目標與硬上限、LTV 階段、US30Y 模式、乾粉、防守判準
     → 直接給「今天做什麼／買什麼多少／等什麼訊號」，不是列數字讓你自己判
  ④ 流向雷達整體評估：外資/投信/自營、融資、COT、Fed、台幣、類股輪動 → 一句結論

原則：所有數字即時讀檔／即時抓，不寫死；抓不到就標「—」不得編造。
輸出為純文字，cron no_agent 直接推 Telegram。
"""
from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import tx_night

BASE = Path(__file__).resolve().parent
TPE = timezone(timedelta(hours=8))


def _j(name: str) -> dict:
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pct(v) -> str:
    return "—" if v is None else f"{v:+.2f}%"


def _pos_label(pos: float) -> str:
    """收盤位置標籤，門檻與 _trend_read 對齊（60=收腳/近高起點、30=續殺線），
    避免「標籤說中段、趨勢說收腳」自相矛盾。"""
    if pos >= 70:
        return "近高"
    if pos >= 60:
        return "中上"
    if pos > 30:
        return "中段"
    return "近低"


def _trend_read(ref, pos, amp_pct, last, hi, lo) -> str:
    """夜盤 → 隔日趨勢判讀（2026-11-26 使用者核准 A）。

    三件事決定趨勢，不是只看漲跌：方向（夜盤收 vs 日盤收）× 收盤位置（區間內哪一端）
    × 振幅（波動大小）。同樣 -2.8%，收在區間上緣＝有承接、收在下緣＝續殺。
    """
    if pos is None or ref is None:
        return ""
    up = ref > 0
    ext = abs(ref) >= 1.5
    big_amp = (amp_pct or 0) >= 2.5
    if ext and not up:
        if pos >= 60:
            return (f"偏空但收腳——最低 {lo:,.0f} 後拉回 {last - lo:,.0f} 點、收在區間 {pos:.0f}%；"
                    f"開低有承接，別追空，等回補缺口再判方向")
        if pos <= 30:
            return (f"偏空續殺——收在區間 {pos:.0f}%（貼近夜盤低 {lo:,.0f}）；"
                    f"開低不接刀，反彈先當減碼機會")
        return f"偏空震盪——收在區間中段 {pos:.0f}%；開低後看 09:30 前能否站回夜盤均價"
    if ext and up:
        if pos <= 40:
            return (f"偏多但收弱——最高 {hi:,.0f} 後回落 {hi - last:,.0f} 點、收在區間 {pos:.0f}%；"
                    f"開高易見賣壓，不追高")
        if pos >= 70:
            return (f"偏多續攻——收在區間 {pos:.0f}%（貼近夜盤高）；"
                    f"開高偏強，回測不破夜盤低即續抱")
        return f"偏多震盪——收在區間中段 {pos:.0f}%；開高後看量能是否跟上"
    if big_amp:
        return (f"方向中性、但夜盤振幅 {amp_pct:.1f}%（{lo:,.0f}–{hi:,.0f}）→ "
                f"隔日波動放大，雙向都可能，別用夜盤猜方向")
    return f"方向中性（夜盤變動 <1.5%、振幅 {amp_pct:.1f}%）→ 開盤照日盤節奏，不因夜盤改策略"


# ── ① 夜盤 ────────────────────────────────────────────────────────
def block_night() -> tuple[list[str], dict]:
    info: dict = {}
    try:
        night = tx_night._near([tx_night._parse(r) for r in tx_night._quote_list(1)])
        day = tx_night._near([tx_night._parse(r) for r in tx_night._quote_list(0)])
    except Exception as e:
        return [f"① 夜盤台指期｜抓取失敗（{type(e).__name__}）"], info
    if not night:
        return ["① 夜盤台指期｜無報價（假日或 API 無資料）"], info

    lines = [f"① 夜盤台指期（{night['contract']} 契約）"]
    lines.append(f"　收 {night['last']:,.0f}｜{_pct(night['pct'])}（{tx_night._fmt_diff(night['diff'])} 點）"
                 f"｜高 {tx_night._fmt(night['high'])} 低 {tx_night._fmt(night['low'])}｜量 {tx_night._fmt(night['vol'])} 口")
    # 2026-11-26 修：09:00–13:45 之間 MarketType=0 是「今日日盤現價」不是收盤價。
    #   直接當「日盤收」會把「今天開高」印成「夜盤偏空」（實測 09:15 手動跑印出 -2.83%）。
    #   當日日盤未收盤 → 不用它推估開盤方向，只保留夜盤紀錄。
    _now = datetime.now(TPE)
    _day_ref = None
    if day and isinstance(day.get("last"), (int, float)):
        if (str(day.get("date") or "") == _now.strftime("%Y%m%d")
                and (_now.hour, _now.minute) < (13, 45)):
            lines.append(f"　（今日日盤進行中 {day['last']:,.0f}；夜盤已收 {night['last']:,.0f}）"
                         f"→ 日盤已開，夜盤不再用來推估開盤方向")
        else:
            _day_ref = day["last"]
            d = night["last"] - _day_ref
            lines.append(f"　對日盤收 {_day_ref:,.0f}：{d:+,.0f} 點（{d / _day_ref * 100:+.2f}%）")
            info["night_vs_day_pct"] = d / _day_ref * 100
    hi, lo, last_v = night.get("high"), night.get("low"), night.get("last")
    pos = amp_pct = None
    if all(isinstance(x, (int, float)) for x in (hi, lo, last_v)) and hi > lo:
        _base = _day_ref or last_v
        pos = (last_v - lo) / (hi - lo) * 100
        amp_pct = (hi - lo) / _base * 100 if _base else None
        if amp_pct is not None:
            lines.append(f"　振幅 {hi - lo:,.0f} 點（{amp_pct:.1f}%）｜收盤位 {pos:.0f}%（{_pos_label(pos)}）")
    info["night_pos"] = pos
    info["night_amp_pct"] = amp_pct
    lines.append(f"　資料時間 {night.get('date')} {tx_night._hhmm(night.get('time'))}")
    info["night_pct"] = night.get("pct")
    info["night_last"] = last_v

    ref = info.get("night_vs_day_pct")
    if ref is not None:
        if ref <= -1.5:
            lines.append("　→ 開盤偏空（夜盤跌幅 ≥1.5%，留意跳空與追繳線）")
        elif ref <= -0.5:
            lines.append("　→ 開盤偏弱（夜盤小跌，觀察 09:00 後是否止穩）")
        elif ref >= 1.5:
            lines.append("　→ 開盤偏多（夜盤漲幅 ≥1.5%）")
        elif ref >= 0.5:
            lines.append("　→ 開盤偏強（夜盤小漲）")
        else:
            lines.append("　→ 開盤中性（夜盤變動 <0.5%）")
    _trend = _trend_read(ref, pos, amp_pct, last_v, hi, lo)
    if _trend:
        lines.append("　→ 趨勢：" + _trend)
    if isinstance(hi, (int, float)) and isinstance(lo, (int, float)):
        _kl = f"　關鍵價：支撐 {lo:,.0f}（夜盤低）｜壓力 {hi:,.0f}（夜盤高）"
        if _day_ref:
            _kl += f"｜缺口回補 {_day_ref:,.0f}（日盤收）"
        lines.append(_kl)
    return lines, info


# ── ② 美股隔夜 ────────────────────────────────────────────────────
YF = "https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=1mo&interval=1d"
WATCH = [("^GSPC", "S&P500"), ("^IXIC", "納斯達克"), ("^SOX", "費半"),
         ("TSM", "台積電ADR"), ("^VIX", "VIX")]


def _yahoo(sym: str):
    """回傳（最新收盤, 前一交易日收盤）。

    ⚠️ 2026-11-26 修：原版用 meta.chartPreviousClose（配 range=5d）→ 那是「5 個交易日前」
    的收盤，等於把 5 日累計漲跌印成「隔夜」（實測 11/25 費半真實 -4.49%，被印成 -12.67%；
    台積電ADR 真實 -5.01%，被印成 -8.53%）。改為直接取日線序列最後兩根收盤。
    """
    req = urllib.request.Request(YF.format(s=sym), headers={"User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=12).read().decode("utf-8", "replace"))
    res = d["chart"]["result"][0]
    q = (res.get("indicators", {}).get("quote") or [{}])[0]
    closes = [c for c in (q.get("close") or []) if c]
    if len(closes) >= 2:
        return closes[-1], closes[-2]
    # 不退回 meta.previousClose／chartPreviousClose：那不是前一交易日收盤（INC-171）
    # → 寧可顯示「—」，也不要印出錯的隔夜漲跌。
    return None, None


def block_us() -> list[str]:
    def one(item):
        sym, name = item
        try:
            p, prev = _yahoo(sym)
            return name, p, (p - prev) / prev * 100 if p and prev else None
        except Exception:
            return name, None, None

    with ThreadPoolExecutor(max_workers=5) as ex:
        res = list(ex.map(one, WATCH))
    if all(p is None for _, p, _ in res):
        return ["② 美股隔夜｜Yahoo 抓取失敗（稍後看日報）"]
    parts = []
    for name, p, chg in res:
        parts.append(f"{name} {'—' if p is None else f'{p:,.2f}'}（{_pct(chg)}）")
    lines = ["② 美股隔夜", "　" + "｜".join(parts)]
    sox = next((c for n, _, c in res if n == "費半"), None)
    tsm = next((c for n, _, c in res if n == "台積電ADR"), None)
    if sox is not None and tsm is not None:
        if sox < -1 and tsm < -1:
            lines.append("　→ 半導體與 ADR 同步走弱：台股電子今早承壓，留意夜盤是否已反映")
        elif sox > 1 and tsm > 1:
            lines.append("　→ 半導體與 ADR 同步走強：電子有撐")
        else:
            lines.append("　→ 半導體與 ADR 分歧：台股電子看個股，別用指數當方向")
    return lines


# ── ③ 對策方向 ────────────────────────────────────────────────────
def block_plan(info: dict) -> list[str]:
    s = _j("snapshot.json")
    th = (s.get("thresholds_2026_0915") or {})
    tgt = th.get("桶目標_pct") or {}
    ladder = th.get("動作階梯_pp") or {}
    brake = th.get("風險煞車") or {}
    ladders = th.get("ltv分級_pct") or {}
    pen = (s.get("penetration") or {})
    act = pen.get("actual_pct") or {}
    pledge = _j("pledge_maintenance_state.json")
    u3 = _j("us30y_state.json")
    radar = _j("radar_state.json")

    obs = ladder.get("觀察", 3)
    divert = ladder.get("導流", 6)
    to_target = ladder.get("減至目標加", 2)
    pair = [("台股市值型成長", "台股市值型", "台股市值型成長"),
            ("美股市值型成長", "美股市值型", "美股市值型成長"),
            ("債券", "債券", "債券"),
            ("防守型配息", "防守型配息", "防守型配息"),
            ("現金/安全網", "現金", "現金")]
    ltv = pledge.get("last_ltv_pct")
    stage = pledge.get("last_ltv_stage")
    u3_rate = u3.get("last_rate")
    u3_mode = u3.get("mode_label") or u3.get("mode")
    avail = (s.get("cash_layers") or {}).get("unrestricted_cash")
    dry = (avail - 700000) if isinstance(avail, (int, float)) else None
    tw_light = ((radar.get("signals") or {}).get("台股") or {})
    night_chg = info.get("night_vs_day_pct")
    total = s.get("total_assets") or 0

    lines = ["③ 對策方向（依既定授權與動作階梯判，不用重新討論）"]
    lines.append("　桶位（實際／目標／偏離）：")
    for key, tkey, label in pair:
        v = act.get(key)
        t = tgt.get(tkey)
        if not isinstance(v, (int, float)) or not isinstance(t, (int, float)):
            continue
        gap = v - t
        lines.append(f"　　· {label} {v}%／{t}%／{gap:+.1f}pp")
    bail = (act.get("債券") or 0) + (act.get("現金/安全網") or 0)
    lines.append(f"　防禦判準（waiver 後）：債券＋現金 = {bail:.1f}%（門檻 30%）"
                 f"{'✅' if bail >= 30 else '❌'}")
    lines.append(f"　質押 LTV {ltv}%（{stage}）｜US30Y {u3_rate}%（{u3_mode}）"
                 + (f"｜乾粉 {dry:,.0f}" if isinstance(dry, (int, float)) else ""))

    # 煞車優先
    braked = []
    if isinstance(u3_rate, (int, float)) and u3_rate >= brake.get("us30y_pct", 5.30):
        braked.append(f"US30Y {u3_rate}% ≥{brake.get('us30y_pct', 5.3)}% 行動線")
    if isinstance(night_chg, (int, float)) and night_chg <= -brake.get("單日急跌_pct", 3):
        braked.append(f"夜盤 {night_chg:+.2f}%（單日急跌 ≥3%）")
    if isinstance(ltv, (int, float)) and ltv >= brake.get("ltv_pct", 53):
        braked.append(f"LTV {ltv}% ≥{brake.get('ltv_pct', 53)}%")

    advice: list[str] = []
    if braked:
        advice.append("⛔ 煞車觸發（" + "、".join(braked) + "）→ 依風險煞車規則：只回報、暫緩加碼與減碼。")
    for key, tkey, label in pair:
        v = act.get(key)
        t = tgt.get(tkey)
        if not isinstance(v, (int, float)) or not isinstance(t, (int, float)):
            continue
        if label == "防守型配息":
            continue  # 2026-11-25 已 waive
        gap = v - t
        if gap >= divert:
            cut = (v - (t + to_target)) / 100 * total if total else 0
            if label == "美股市值型成長":
                advice.append(f"美股 {v}% 超目標 {gap:+.1f}pp（≥導流 {divert}pp）→ 理論減 {cut / 10000:,.0f} 萬"
                              f"至 {t + to_target}%；但 11/25 裁決②：降美元曝險走台幣計價／避險級別、不賣美股，"
                              f"且可減部位只認非後收／非保單內。")
            else:
                advice.append(f"{label} {v}% 超目標 {gap:+.1f}pp → 減至 {t + to_target}%（約 {cut / 10000:,.0f} 萬），"
                              f"單週不超過部位 1/3。")
        elif gap >= obs:
            advice.append(f"{label} {v}% 超目標 {gap:+.1f}pp（觀察帶 {obs}–{divert}pp）→ 停止加碼、配息導流，不主動賣。")
        elif gap <= -divert:
            advice.append(f"{label} {v}% 低於目標 {gap:+.1f}pp → 只可用配息與自然流入補，不動用質押彈藥。")
        elif gap <= -obs:
            advice.append(f"{label} {v}% 低目標 {gap:+.1f}pp（觀察帶）→ 可分批補，單筆 ≤{ladder.get('單筆上限_twd', 200000):,.0f}。")

    if isinstance(ltv, (int, float)) and ltv >= (ladders.get("綠上限") or 45):
        advice.append(f"LTV {ltv}% 不在綠燈（<{ladders.get('綠上限', 45)}%）：機會子彈暫停，"
                      + (f"乾粉 {dry:,.0f} 全留現金。" if isinstance(dry, (int, float)) else "乾粉全留現金。"))
    if tw_light.get("color") == "🔴":
        advice.append(f"流向雷達台股 🔴（{str(tw_light.get('note'))[:40]}）→ 台股今天不加碼。")
    if isinstance(night_chg, (int, float)) and night_chg <= -1.5:
        advice.append(f"夜盤 {night_chg:+.2f}%：開盤承壓，今天只做「已排定的分批」與「不追價」，不臨時加碼。")
    if not advice:
        advice.append("今天沒有任何桶位觸發閘門 → 照原計畫分批，不因單日波動改策略。")

    lines += ["　今日動作："] + [f"　　· {a}" for a in advice]
    lines.append("　（規則推導，不是預測；要改規則請明說）")
    return lines


# ── ④ 雷達整體評估 ────────────────────────────────────────────────
def block_radar() -> list[str]:
    r = _j("radar_state.json")
    d = r.get("data") or {}
    sig = r.get("signals") or {}
    tw = d.get("twse") or {}
    mg = d.get("margin") or {}
    cot = ((d.get("cot") or {}).get("contracts") or {}).get("黃金") or {}
    fed = d.get("fed") or {}
    twd = d.get("twd") or {}
    sf = (r.get("sector_flow") or {})

    def yi(v):
        return "—" if not isinstance(v, (int, float)) else f"{v / 1e8:+,.0f} 億"

    lines = [f"④ 流向雷達整體評估（{tw.get('date') or r.get('last_run', '')[:10]}）"]
    # 2026-11-26 使用者核准：三大法人行加上「承接比例＋合計」，並在融資後加外資期貨部位
    _f, _t, _dl = tw.get("外資總買賣超"), tw.get("投信_元"), tw.get("自營_元")
    _carry = f"　三大法人：外資 {yi(_f)}｜投信 {yi(_t)}"
    if isinstance(_f, (int, float)) and isinstance(_t, (int, float)) and _f < 0 and _t > 0:
        _carry += f"（接走 {abs(_t) / abs(_f) * 100:.0f}%）"
    _carry += f"｜自營 {yi(_dl)}"
    if all(isinstance(x, (int, float)) for x in (_f, _t, _dl)):
        _carry += f"｜合計 {yi(_f + _t + _dl)}"
    lines.append(_carry)
    if mg:
        lines.append(f"　融資：{mg.get('融資餘額億')} 億（單日 {mg.get('單日增減億'):+.0f} 億／"
                     f"{mg.get('期間增減%'):+.1f}% 期間）"
                     if isinstance(mg.get("單日增減億"), (int, float)) else f"　融資：{mg.get('融資餘額億')} 億")
    if cot:
        lines.append(f"　COT 黃金淨多單 {cot.get('net'):,}（週 {((cot.get('net', 0) - cot.get('prev', 0)) / abs(cot.get('prev') or 1) * 100):+.1f}%）"
                     if isinstance(cot.get("net"), (int, float)) else "　COT：—")
    if fed:
        lines.append(f"　Fed 資產 {fed.get('total_assets'):,.0f} 百萬美元（{fed.get('as_of')}）"
                     if isinstance(fed.get("total_assets"), (int, float)) else "　Fed：—")
    if isinstance(twd.get("last"), (int, float)):
        lines.append(f"　USD/TWD {twd['last']:.3f}（週 {twd.get('週變化', 0) * 100:+.2f}%）")

    # 2026-11-26 使用者核准：外資台指期部位（現貨賣超是避險還是真撤）
    _fut = r.get("tw_futures") or {}
    _net = _fut.get("foreign_net_oi")
    if isinstance(_net, (int, float)):
        _side = f"淨空單 {abs(_net):,} 口" if _net < 0 else f"淨多單 {_net:,} 口"
        _fs = f"　期貨部位：外資台指期 {_side}"
        _p = _fut.get("prev_net_oi")
        if isinstance(_p, (int, float)):
            _fs += f"（前日 {_p:+,} → 今日 {_net:+,}，{_net - _p:+,} 口）"
        if _fut.get("stale"):
            _fs += "｜⚠️ 延遲（顯示前次快照）"
        lines.append(_fs)

    tw_rank = [x for x in (sf.get("台股") or {}).items()
               if isinstance(x[1], dict) and isinstance(x[1].get("法人淨買賣超"), (int, float))]
    if tw_rank:
        top = sorted(tw_rank, key=lambda x: -x[1]["法人淨買賣超"])[:2]
        bot = sorted(tw_rank, key=lambda x: x[1]["法人淨買賣超"])[:2]
        lines.append("　台股類股：買超 " + "／".join(f"{k}" for k, _ in top) +
                     "｜賣超 " + "／".join(f"{k}" for k, _ in bot))
    if sf.get("美股總結"):
        lines.append(f"　美股輪動：{str(sf['美股總結'])[:60]}")

    lights = [f"{k} {v.get('color', '')}" for k, v in sig.items() if isinstance(v, dict) and v.get("color")]
    if lights:
        lines.append("　燈號：" + "｜".join(lights[:6]))

    # 結論
    verdict = []
    if (sig.get("台股") or {}).get("color") == "🔴":
        verdict.append("台股資金面偏空")
    if isinstance(mg.get("單日增減億"), (int, float)) and mg["單日增減億"] > 100:
        verdict.append(f"融資單日 +{mg['單日增減億']:.0f} 億（散戶加碼、浮額變多）")
    if (sig.get("黃金") or {}).get("color") == "🔴":
        verdict.append("黃金聰明錢撤離")
    if (sig.get("美債10年") or {}).get("color") == "🟢":
        verdict.append("10Y 殖利率動能下行（債券有撐、但長端未鬆）")
    lines.append("　→ " + ("；".join(verdict) + "。" if verdict else "無明顯單邊訊號。") +
                 "對應動作：不追高、不攤平、等訊號。")
    return lines


def build() -> str:
    head = f"🌅 盤前快報 {datetime.now(TPE).strftime('%m/%d')}"
    night_lines, info = block_night()
    parts = [[head], night_lines, block_us(), block_plan(info), block_radar()]
    return "\n".join("\n".join(p) for p in parts if p)


def main() -> int:
    print(build())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
