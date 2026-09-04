# -*- coding: utf-8 -*-
"""build_radar_report.py — 機構流向雷達獨立報告頁（2026-09-04 建立）
讀 radar_state.json → 產 radar_report_{date}.html（手機可讀完整版）
內容：燈號 / 追蹤ETF法人 / 產業資金流向（台股+美股）/ 政策面 / 凍結資產
由 radar_push.py（每日16:15）與 radar_weekly.py（週六08:30）在雷達更新後呼叫。
"""
import json, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _fmt_money(n):
    """百萬簡寫"""
    if n is None:
        return "-"
    v = n / 1_000_000
    return f"{v:+.1f}百萬" if abs(v) >= 0.05 else f"{v:+.0f}萬"


def _arrow(direction):
    return {"inflow": "🟢 流入", "outflow": "🔴 流出", "neutral": "⚪ 中性"}.get(direction, direction or "-")


def _color(direction):
    return {"inflow": "#16a34a", "outflow": "#dc2626", "neutral": "#6b7280"}.get(direction, "#6b7280")


def main():
    rs = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
    last_run = str(rs.get("last_run", ""))[:16].replace("T", " ")
    sig = rs.get("signals", {}) or {}
    tw = (rs.get("data", {}) or {}).get("twse", {}) or {}
    sf = rs.get("sector_flow", {}) or {}
    pn = rs.get("policy_notes", {}) or {}
    locked = rs.get("locked_assets", []) or []
    d = (rs.get("data", {}) or {})

    # 燈號統計
    reds = sum(1 for v in sig.values() if str(v.get("color", "")).startswith("🔴"))
    yellows = sum(1 for v in sig.values() if str(v.get("color", "")).startswith("🟡"))
    greens = sum(1 for v in sig.values() if str(v.get("color", "")).startswith("🟢"))

    # ── 燈號卡片 ──
    sig_cards = ""
    for k, v in sig.items():
        color = str(v.get("color", "⚪"))
        bg = {"🟢": "#f0fdf4", "🟡": "#fffbeb", "🔴": "#fef2f2"}.get(color[0], "#f9fafb")
        bd = {"🟢": "#86efac", "🟡": "#fcd34d", "🔴": "#fca5a5"}.get(color[0], "#d1d5db")
        sig_cards += (f"<div style='flex:1;min-width:130px;background:{bg};border:1px solid {bd};"
                      f"border-radius:10px;padding:10px 12px'>"
                      f"<div style='font-size:11px;color:#6b7280;font-weight:700'>{k}</div>"
                      f"<div style='font-size:20px;margin:2px 0'>{color}</div>"
                      f"<div style='font-size:11px;color:#374151;line-height:1.5'>{v.get('note','')}</div></div>")
    sig_row = (f"<div style='display:flex;gap:8px;flex-wrap:wrap'>{sig_cards}</div>"
               f"<p style='font-size:11px;color:#6b7280;margin:6px 0 0'>🔴紅 {reds}｜🟡黃 {yellows}｜🟢綠 {greens}｜更新 {last_run}</p>")

    # ── 追蹤 ETF 法人 ──
    etf_html = ""
    if tw.get("etfs"):
        rows = "".join(
            f"<tr><td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{k}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:right;color:{'#16a34a' if v>0 else '#dc2626'}'>{v/1000:+,.0f}千</td></tr>"
            for k, v in tw["etfs"].items() if v)
        etf_html = (f"<div style='background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:12px'>"
                    f"<h3 style='font-size:13px;font-weight:800;margin:0 0 6px;color:#1d1d1f'>📈 追蹤 ETF 法人買賣超（{tw.get('date','')}）</h3>"
                    f"<table style='width:100%;font-size:12px;border-collapse:collapse'>{rows}</table>"
                    f"<p style='font-size:11px;color:#6b7280;margin:6px 0 0'>外資總買賣超：{_fmt_money(tw.get('外資總買賣超'))}</p></div>")

    # ── 產業資金流向：台股 ──
    tw_sector = sf.get("台股", {}) or {}
    tw_rows = ""
    if tw_sector:
        for k, v in sorted(tw_sector.items(), key=lambda x: -(x[1].get("法人淨買賣超", 0) or 0)):
            amt = v.get("法人淨買賣超", 0) or 0
            tw_rows += (f"<tr><td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{k}</td>"
                        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:right;font-weight:600;color:{_color(v.get('方向'))}'>{_fmt_money(amt)}</td>"
                        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:center'>{_arrow(v.get('方向'))}</td></tr>")
    tw_flow_html = ""
    if tw_rows:
        tw_flow_html = (f"<div style='background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:12px'>"
                        f"<h3 style='font-size:13px;font-weight:800;margin:0 0 2px;color:#1d1d1f'>🏭 產業資金流向｜台股法人</h3>"
                        f"<p style='font-size:11px;color:#6b7280;margin:0 0 6px'>{sf.get('台股總結','')}</p>"
                        f"<table style='width:100%;font-size:12px;border-collapse:collapse'>"
                        f"<tr style='color:#6b7280'><th style='text-align:left;padding:4px 8px'>產業</th><th style='text-align:right;padding:4px 8px'>法人淨買賣超</th><th style='padding:4px 8px'>方向</th></tr>"
                        f"{tw_rows}</table></div>")

    # ── 產業資金流向：美股 ──
    us_sector = sf.get("美股", {}) or {}
    us_rows = ""
    if us_sector:
        for k, v in sorted(us_sector.items(), key=lambda x: -(x[1].get("RS_vs_SPY", 0) or 0)):
            rv = v.get("RS_vs_SPY", 0) or 0
            _rc = "#16a34a" if rv > 0 else ("#dc2626" if rv < 0 else "#6b7280")
            us_rows += (f"<tr><td style='padding:4px 8px;border-bottom:1px solid #f3f4f6'>{k}</td>"
                        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:right'>{v.get('動能%',0):+.1f}%</td>"
                        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:right;font-weight:600;color:{_rc}'>{rv:+.1f}pp</td>"
                        f"<td style='padding:4px 8px;border-bottom:1px solid #f3f4f6;text-align:center'>{_arrow(v.get('方向'))}</td></tr>")
    us_flow_html = ""
    if us_rows:
        us_flow_html = (f"<div style='background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:12px'>"
                        f"<h3 style='font-size:13px;font-weight:800;margin:0 0 2px;color:#1d1d1f'>🏭 產業資金流向｜美股 RS（vs SPY {sf.get('SPY基準','')}%）</h3>"
                        f"<p style='font-size:11px;color:#6b7280;margin:0 0 6px'>{sf.get('美股總結','')}</p>"
                        f"<table style='width:100%;font-size:12px;border-collapse:collapse'>"
                        f"<tr style='color:#6b7280'><th style='text-align:left;padding:4px 8px'>產業</th><th style='text-align:right;padding:4px 8px'>動能%</th><th style='text-align:right;padding:4px 8px'>RS vs SPY</th><th style='padding:4px 8px'>方向</th></tr>"
                        f"{us_rows}</table></div>")

    # ── 政策面 ──
    pol_items = ""
    src = pn.get("來源", "")
    if pn.get("會議正名"):
        pol_items += f"<p style='margin:4px 0;font-size:12px'><b>🗓️ {pn['會議正名']}</b></p>"
    for k in pn:
        if not str(k).startswith("新聞"):
            continue
        v = pn[k] or {}
        if isinstance(v, dict):
            _mkt = f"<div style='font-size:11.5px;color:#6b7280;margin-top:2px'>📉 市場反應：{v.get('市場反應','')}</div>" if v.get("市場反應") else ""
            _imp = f"<div style='font-size:11.5px;color:#6b7280'>💡 對資產影響：{v.get('對資產影響','')}</div>" if v.get("對資產影響") else ""
            pol_items += (f"<div style='border-left:3px solid #f59e0b;background:#fffbeb;border-radius:0 8px 8px 0;padding:8px 10px;margin:6px 0'>"
                          f"<div style='font-size:12.5px;font-weight:700;color:#92400e'>{v.get('內容','')}</div>"
                          f"{_mkt}{_imp}</div>")
    for k2 in ["原油綜合判斷", "債券升息敏感度"]:
        if pn.get(k2):
            pol_items += f"<p style='margin:5px 0;font-size:12px;color:#374151'>📌 <b>{k2}：</b>{pn[k2]}</p>"
    pol_html = (f"<div style='background:#fff;border-radius:12px;padding:12px 14px;box-shadow:0 1px 3px rgba(0,0,0,.06);margin-bottom:12px'>"
                f"<h3 style='font-size:13px;font-weight:800;margin:0 0 6px;color:#1d1d1f'>🏛️ 政策面標註{f'（{src}）' if src else ''}</h3>{pol_items or '<p style=font-size:12px;color:#6b7280>無重大政策事件</p>'}</div>")

    # ── 凍結資產 ──
    lock_html = ""
    if locked:
        lock_html = (f"<div style='background:#fef2f2;border:1px solid #fecaca;border-radius:12px;padding:10px 14px;margin-bottom:12px'>"
                     f"<span style='font-size:12px;font-weight:700;color:#b91c1c'>🔒 凍結資產：{'、'.join(locked)}（機構大規模撤離，暫停調度）</span></div>")

    # ── COT/Fed 原始 ──
    cot = (d.get("cot") or {}).get("contracts", {}) or {}
    cot_txt = "｜".join(f"{k} 淨多單 {v.get('net',0):,}（週增 {((v.get('net',0)-(v.get('prev',0) or 0))/abs(v.get('prev',1) or 1)*100):+.1f}%）" for k, v in cot.items()) if cot else "無"
    tnx = d.get("tnx") or {}
    fed = d.get("fed") or {}
    _fed_txt = fed.get("error") or (f"總資產 {fed.get('total', 0):,.0f}" if fed.get("total") else "無資料")
    raw_html = (f"<div style='background:#f9fafb;border-radius:12px;padding:12px 14px;margin-bottom:12px'>"
                f"<h3 style='font-size:13px;font-weight:800;margin:0 0 6px;color:#1d1d1f'>🗄️ 原始數據</h3>"
                f"<p style='font-size:11.5px;color:#4b5563;margin:3px 0'>COT（{str((d.get('cot') or {}).get('date',''))[:10]}）：{cot_txt}</p>"
                f"<p style='font-size:11.5px;color:#4b5563;margin:3px 0'>美債10Y：{tnx.get('last',0):.3f}%（月動能 {tnx.get('momentum',0):+.1f}%）</p>"
                f"<p style='font-size:11.5px;color:#4b5563;margin:3px 0'>Fed H.4.1：{_fed_txt}</p></div>")

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>📡 機構流向雷達 {last_run[:10]}</title>
<style>body{{font-family:-apple-system,'PingFang TC','Microsoft JhengHei',sans-serif;background:#f5f5f7;margin:0;padding:16px}}
a{{color:#2563eb;text-decoration:none}}</style></head>
<body>
<div style="background:#f5f5f7;max-width:760px;margin:0 auto">
<div style="background:linear-gradient(135deg,#1e293b,#0f172a);border-radius:14px;padding:16px 18px;color:#fff;margin-bottom:12px">
<h1 style="font-size:18px;font-weight:900;margin:0 0 4px">📡 機構流向雷達</h1>
<div style="font-size:11.5px;color:#94a3b8">更新 {last_run}｜證交所法人 + CFTC COT + Fed H.4.1 + 產業資金流向</div>
</div>
{lock_html}
{sig_row}
<div style="height:10px"></div>
{etf_html}
{tw_flow_html}
{us_flow_html}
{pol_html}
{raw_html}
<div style="font-size:10.5px;color:#94a3b8;text-align:center;padding:8px 0 20px">龍九控股 機構流向雷達 ｜ radar_state.json 動態產生 ｜ 資料僅供內部決策參考</div>
</div></body></html>"""

    out = BASE / f"radar_report_{last_run[:10]}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 雷達報告頁 {out.name}（{out.stat().st_size:,} bytes）")


if __name__ == "__main__":
    main()
