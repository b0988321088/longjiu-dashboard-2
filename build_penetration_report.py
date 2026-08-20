#!/usr/bin/env python3
"""Generate detailed penetration report."""
import json
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
from update_all import calc_penetration

cash = snap.get("cash_total", 3119158)
ins = snap.get("insurance_current_value", 9802872)
sec = snap.get("securities_total_market_value", 2597360)
funds = snap.get("fund_market_value", 793434)
p = calc_penetration(cash, ins, sec, funds, snap=snap)
tw_v, us_v, def_v, bond_v, cash_pv = p["台股市值型成長"], p["美股市值型成長"], p["防守型配息"], p["債券"], p["現金/安全網"]
total = tw_v + us_v + def_v + bond_v + cash_pv

# 自動校正 snapshot 穿透數據（供日報第2章使用）
# targets 以 snapshot 現有值為準（單一真值，禁止硬編碼覆寫）；缺 key 時 fallback 2026-08-02 定案值
_existing_tgt = snap.get("penetration", {}).get("targets", {}) or {}
targets_map = {
    "台股市值型": _existing_tgt.get("台股市值型目標", 20),
    "美股市值型": _existing_tgt.get("美股市值型目標", 30),
    "配息型": _existing_tgt.get("配息型目標", 20),
    "債券型": _existing_tgt.get("債券型目標", 15),
    "現金": _existing_tgt.get("現金目標", 15),
}
actual_map = {"台股市值型成長": tw_v, "美股市值型成長": us_v, "防守型配息": def_v, "債券": bond_v, "現金/安全網": cash_pv}
actual_pct = {k: round(v / total * 100, 1) for k, v in actual_map.items()}
gaps = {
    "台股市值型成長": round(actual_pct["台股市值型成長"] - targets_map["台股市值型"], 1),
    "美股市值型成長": round(actual_pct["美股市值型成長"] - targets_map["美股市值型"], 1),
    "防守型配息": round(actual_pct["防守型配息"] - targets_map["配息型"], 1),
    "債券及安全現金": round(actual_pct["債券"] + actual_pct["現金/安全網"] - targets_map["債券型"] - targets_map["現金"], 1),
}
snap["penetration"] = {
    "updated_at": date.today().isoformat(),
    "source": "calc_penetration (auto-calibrated)",
    "targets": {f"{k}目標": v for k, v in targets_map.items()},
    "actual_pct": actual_pct,
    "gaps": gaps,
    "actual_twd": actual_map,
    "alert": f"台股不足{abs(round(actual_pct['台股市值型成長']-targets_map['台股市值型'],1))}pp；現金+債券超標{abs(round(actual_pct['債券']+actual_pct['現金/安全網']-targets_map['債券型']-targets_map['現金'],1))}pp",
}
# 每次管線執行滾動頂層日期（儀表板系統時間/記憶同步統一真值）
snap["date"] = date.today().isoformat()
snap["generated_at"] = datetime.now().isoformat()
(BASE / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  穿透數據已自動校正並寫入 snapshot.json")
holdings = snap.get("securities", {}).get("holdings", [])
today = date.today().isoformat()

# Classify holdings
def cat_ticker(t):
    if t in ("0050","006208","009816","00981A","00984A"): return "tw"
    if t in ("00646","009823","009824","00924"): return "us"
    if t in ("00713","00878","0056","00919","00918","00888"): return "def"
    if t in ("00983D",): return "bond"
    return "other"
cats_data = [
    ("tw", "台股市值型", tw_v, targets_map["台股市值型"], "#3b82f6","0050/006208/009816"),
    ("us", "美股市值型", us_v, targets_map["美股市值型"], "#06b6d4","00646/009823/009824"),
    ("def","防守型配息", def_v, targets_map["配息型"], "#22c55e","00878/00713/00919等"),
    ("bond","債券", bond_v, targets_map["債券型"], "#f59e0b","00983D"),
    ("cash","安全現金", cash_pv, targets_map["現金"], "#a855f7","銀行活存"),
]

lines = []
def w(s=""):
    lines.append(s)

w("<!DOCTYPE html><html lang='zh-TW'><head><meta charset='utf-8'>")
w(f"<title>龍九控股 穿透分析報告（詳細版）{today}</title>")
w("<meta name='viewport' content='width=device-width,initial-scale=1'><style>")
w("body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#f1f5f9;max-width:900px;margin:20px auto;padding:0 16px}")
w("h1{font-size:24px;font-weight:900;text-align:center;background:linear-gradient(135deg,#3b82f6,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent}")
w(".meta{color:#94a3b8;font-size:13px;text-align:center;margin-bottom:20px}")
w(".card{background:#1e293b;border-radius:14px;padding:16px;margin-bottom:12px;border:1px solid #334155}")
w("h2{font-size:16px;font-weight:700;margin:0 0 12px;padding-left:10px;border-left:3px solid #3b82f6}")
w("h3{font-size:14px;font-weight:600;margin:12px 0 6px;color:#60a5fa}")
w("table{width:100%;border-collapse:collapse;font-size:13px}")
w("th{background:#334155;padding:8px 6px;text-align:left;font-weight:600;color:#94a3b8}")
w("td{padding:8px 6px;border-top:1px solid #334155}")
w(".num{text-align:right;font-variant-numeric:tabular-nums}")
w(".up{color:#22c55e} .down{color:#ef4444}")
w(".bar-wrap{background:#334155;border-radius:8px;height:10px;margin:4px 0 10px;overflow:hidden}")
w(".bar-fill{height:10px;border-radius:8px}")
w(".tag{display:inline-block;padding:2px 10px;border-radius:8px;font-size:11px;font-weight:700}")
w(".over{background:#ef444420;color:#ef4444} .under{background:#f59e0b20;color:#f59e0b} .good{background:#22c55e20;color:#22c55e}")
w(".callout{background:#1e3a5f40;border-left:3px solid #3b82f6;padding:10px 14px;margin:10px 0;border-radius:6px;font-size:13px;line-height:1.7}")
w("@media(max-width:640px){table{font-size:12px}th,td{padding:6px 4px}}")
w("</style></head><body>")

w(f"<h1>📊 龍九控股 穿透分析報告（詳細版）</h1>")
w(f"<p class='meta'>{today} ｜ 穿透分母 = {total:,} TWD</p>")

# 1. Overview table
w("<div class='card'><h2>🎯 配置總覽</h2>")
w("<table><thead><tr><th>類別</th><th class='num'>金額</th><th class='num'>佔比</th><th class='num'>目標</th><th class='num'>缺口</th><th>狀態</th></tr></thead><tbody>")
for key, name, val, target, color, desc in cats_data:
    pct = val / total * 100
    gap = pct - target
    if gap > 5: st = "<span class='tag over'>⚠️ 超標</span>"
    elif gap < -5: st = "<span class='tag under'>🔴 不足</span>"
    else: st = "<span class='tag good'>✅ 正常</span>"
    gc = "down" if gap < 0 else "up"
    w(f"<tr><td>{name}</td><td class='num'>{val:,}</td><td class='num'>{pct:.1f}%</td><td class='num'>{target}%</td><td class='num {gc}'>{gap:+.1f}pp</td><td>{st}</td></tr>")
w("</tbody></table></div>")

# 2. Bar chart
w("<div class='card'><h2>📈 配置比例 vs 目標</h2>")
for key, name, val, target, color, desc in cats_data:
    pct = val / total * 100
    w(f"<div style='font-size:13px;font-weight:600;margin-top:12px'>{name}</div>")
    w(f"<div style='display:flex;justify-content:space-between;font-size:12px;color:#94a3b8'>")
    w(f"<span>實際 {pct:.1f}%</span><span>目標 {target}%</span></div>")
    w(f"<div class='bar-wrap'><div class='bar-fill' style='width:{pct:.1f}%;background:{color}'></div></div>")
    w(f"<div style='font-size:11px;color:#64748b'>{desc}</div>")
w("</div>")

# 3. Holdings detail
w("<div class='card'><h2>📋 各類別明細</h2>")
for key, name, val, target, color, desc in cats_data:
    if key == "cash":
        w(f"<h3 style='color:{color}'>{name} — {val:,} TWD</h3>")
        w("<p style='font-size:13px;color:#64748b'>銀行活存 + 定存，無個別證券</p>")
        continue
    items = [h for h in holdings if cat_ticker(h["ticker"]) == key]
    w(f"<h3 style='color:{color}'>{name} — {val:,} TWD（{val/total*100:.1f}%）</h3>")
    if items:
        w("<table><thead><tr><th>代碼</th><th>名稱</th><th class='num'>股數</th><th class='num'>現價</th>")
        w("<th class='num'>市值</th><th class='num'>佔比</th><th class='num'>損益</th></tr></thead><tbody>")
        for h in sorted(items, key=lambda x: x["value"], reverse=True):
            wp = h["value"] / val * 100 if val else 0
            pc = "up" if h["pnl"] >= 0 else "down"
            w(f"<tr><td><b>{h['ticker']}</b></td><td>{h['name']}</td>")
            w(f"<td class='num'>{h['shares']:,}</td><td class='num'>{h['price']:.2f}</td>")
            w(f"<td class='num'>{h['value']:,}</td><td class='num'>{wp:.1f}%</td>")
            w(f"<td class='num {pc}'>{h['pnl']:+,} ({h['pnl_pct']:+.1f}%)</td></tr>")
        w("</tbody></table>")
w("</div>")

# 3b. 基金明細（鉅亨基金）— 支援扁平/嵌套結構
_fb = snap.get("funds_breakdown", {})
if _fb:
    # 展平嵌套結構 {群組: {name: val}} → {name: val}（跳過小計）
    _fb_flat = {}
    for _fn, _fv2 in _fb.items():
        if isinstance(_fv2, dict):
            for _sn, _sv in _fv2.items():
                if _sn in ("小計", "匯率調整", "note") or not isinstance(_sv, (int, float)):
                    continue
                _fb_flat[f"{_fn}-{_sn}"] = _sv
        elif isinstance(_fv2, (int, float)):
            _fb_flat[_fn] = _fv2
    _fb = _fb_flat
    w("<div class='card'><h2>📦 基金穿透（鉅亨基金帳戶）</h2>")
    w("<table><thead><tr><th>基金名稱</th><th class='num'>市值</th><th>穿透分類</th></tr></thead><tbody>")
    _fund_tw = _fund_us = _fund_def = 0
    for _fn, _fv2 in sorted(_fb.items(), key=lambda x: x[1], reverse=True):
        if "台新美日台" in _fn or "貝萊德" in _fn or "安聯AI" in _fn or "聯博" in _fn or "摩根" in _fn or "M&G" in _fn or "安聯收益成長" in _fn or "富達" in _fn:
            _cat = "🌎 美股"; _fund_us += _fv2
        elif "0050連結" in _fn or "統一奔騰" in _fn or "路博邁" in _fn or "安聯台灣科技" in _fn:
            # 2026-08-13 修正：路博邁台灣5G/安聯台灣科技是台股基金
            _cat = "🇹🇼 台股"; _fund_tw += _fv2
        elif "台中銀台灣優息" in _fn or "國泰台灣高股息" in _fn:
            _cat = "🛡️ 防守型"; _fund_def += _fv2
        else:
            _cat = "🇹🇼 台股"; _fund_tw += _fv2
        w(f"<tr><td style='max-width:180px'>{_fn}</td><td class='num'>{_fv2:,}</td><td>{_cat}</td></tr>")
    w(f"<tr style='border-top:2px solid #3b82f6;font-weight:700'><td>合計</td><td class='num'>{sum(_fb.values()):,}</td>")
    w(f"<td>🇹🇼 台股 {_fund_tw:,} + 🌎 美股 {_fund_us:,} + 🛡️ 防守型 {_fund_def:,}</td></tr>")
    w("</tbody></table></div>")

# 4. Insurance（成分動態顯示，2026-08-04 改：不再硬編碼）
w("<div class='card'><h2>🏦 保險穿透（含成分）</h2>")
w("<table><thead><tr><th>項目</th><th class='num'>金額</th><th>穿透分類</th></tr></thead><tbody>")
_bond_ratio = {"安聯收益成長": 0.35, "M&G入息": 0.55, "安聯AI收益成長": 0.50, "PIMCO收益增長": 0.48, "摩根多重收益": 0.45}
_ins_brk = snap.get("insurance_breakdown", {})
for _pol, _pfunds in [("安聯保單A", _ins_brk.get("policy_a_funds", {})), ("安聯保單B", _ins_brk.get("policy_b_funds", {}))]:
    _ps = sum(v for v in _pfunds.values())
    w(f"<tr><td><b>{_pol}</b></td><td class='num'>{_ps:,}</td><td></td></tr>")
    for _fn, _fv in sorted(_pfunds.items(), key=lambda x: -x[1]):
        if _fn in ("貝萊德世界科技A10", "貝萊德科技"):
            _cls = "美股 100%"
        else:
            _br = _bond_ratio.get(_fn, 0.5)
            _cls = f"債券 {_br*100:.0f}% / 美股 {(1-_br)*100:.0f}%"
        w(f"<tr style='padding-left:20px;font-size:12px;color:#6e6e73'><td>　{_fn}</td><td class='num'>{_fv:,}</td><td>{_cls}</td></tr>")
_fj_v = snap.get("firstjin_current_value", 1934260)
_fj_name = snap.get("firstjin_fund_name", "FJ33-摩根多重收益(美元對沖)A月配")
w(f"<tr><td><b>第一金FL65（{_fj_name[:32]}…）</b></td><td class='num'>{_fj_v:,}</td><td>防守型配息 100%</td></tr>")
w(f"<tr style='border-top:2px solid #3b82f6;font-weight:700'><td>保險合計</td><td class='num'>{ins:,}</td><td></td></tr>")
w("</tbody></table>")
w("<p style='font-size:12px;color:#64748b;margin-top:8px'>成分債券比例：安聯收益成長 35% / M&G入息 55% / 安聯AI收益成長 50% / PIMCO收益增長 48%／貝萊德系列 100% 美股；FL65（摩根多重收益美元對沖）全數防守型配息</p>")
w("</div>")

# 5. Calculation methodology
w("<div class='card'><h2>🧮 計算方式說明</h2>")
w("<div class='callout'>")
w("<b>📐 穿透公式</b><br><br>")
w("<b>Step 1：分類證券</b><br>")
w("台股 = 0050 + 006208 + 009816（國內市值型 ETF）<br>")
w("美股 = 00646 + 009823 + 009824（美股/全球型 ETF）<br>")
w("防守型 = 00878 + 00713 + 0056 + 00919 + 00918 + 00888（高股息低波動）<br>")
w("債券 = 00983D（主動式投等債）<br>")
w("現金 = Moneybook 銀行帳戶總和（排除信用卡）<br><br>")
w("<b>Step 2：穿透保險基金</b><br>")
w("安聯A+B 子基金，依鉅亨晨星真值債券權重拆解（2026/6/30）：<br>")
w("• 安聯收益成長 → 32% 債券 / 68% 美股（晨星 32.07%）<br>")
w("• 摩根JPM多重收益 → 47% 債券 / 53% 美股（晨星 46.69%，8/14 取代 M&G/安聯AI）<br>")
w("• PIMCO收益增長 → 48% 債券 / 52% 美股（有效權重，2026/3 資產配置）<br>")
w("• 貝萊德A10 → 100% 美股<br>")
w("• 第一金FL65 → 全數列防守型配息<br>")
w("• （M&G入息 55% / 安聯AI 50% — 2026-08-14 已轉出，保留僅供回溯）<br><br>")
w("<b>Step 3：匯總</b><br>")
w("台股 = 證券台股（保險無台股部位）<br>")
w("美股 = 證券美股 + 保險美股穿透<br>")
w("防守型 = 證券防守型 + 第一金FL65<br>")
w("債券 = 證券債券 + 保險債券穿透<br>")
w("現金 = Moneybook 銀行現金<br><br>")
w(f"<b>📌 穿透分母 = {total:,} TWD</b><br>")
w("（不含不動產，因不參與流動性配置）")
w("</div></div>")

# 6. Strategy（動態：依修正後缺口產生，2026-08-04 改，禁止硬編碼）
_tw_gap = actual_pct["台股市值型成長"] - targets_map["台股市值型"]
_us_gap = actual_pct["美股市值型成長"] - targets_map["美股市值型"]
_def_gap = actual_pct["防守型配息"] - targets_map["配息型"]
_bc_gap = actual_pct["債券"] + actual_pct["現金/安全網"] - targets_map["債券型"] - targets_map["現金"]
w("<div class='card'><h2>🧓 再平衡策略建議</h2>")
w("<table><thead><tr><th>優先</th><th>動作</th><th>理由</th></tr></thead><tbody>")
if _tw_gap < -2:
    w(f"<tr><td><span class='tag under'>P0</span></td><td>台股市值型補碼 {_tw_gap:+.1f}pp</td><td>逢低分批買 0050/006208/009816（缺口最大）</td></tr>")
if _us_gap > 2:
    w(f"<tr><td><span class='tag over'>P1</span></td><td>美股減碼 {_us_gap:+.1f}pp</td><td>逢反彈分批減碼美股科技</td></tr>")
if _def_gap < -2:
    w(f"<tr><td><span class='tag under'>P2</span></td><td>防守型補碼 {_def_gap:+.1f}pp</td><td>加 00878/00713 抗波動</td></tr>")
else:
    w(f"<tr><td><span class='tag good'>P2</span></td><td>防守型已達標（{actual_pct['防守型配息']:.1f}% vs 目標 {targets_map['配息型']}%）</td><td>維持 00878/00713/00919，不需大補</td></tr>")
if _bc_gap > 2:
    w(f"<tr><td><span class='tag over'>P3</span></td><td>債券+現金減碼 {_bc_gap:+.1f}pp</td><td>超標資金轉向台股市值型</td></tr>")
w("</tbody></table></div>")

# 4.5 ETF 風險評估（2026-08-04 新增：人多的地方有危險）
w("<div class='card'><h2>⚠️ ETF 風險評估</h2>")
w("<table><thead><tr><th>族群</th><th class='num'>市值</th><th class='num'>佔證券</th><th>風險標記</th></tr></thead><tbody>")
_sec_t = snap.get("securities_total_market_value", 1)
_hd = {h.get("ticker"): h.get("value", 0) for h in snap.get("securities", {}).get("holdings", [])}
_def_t = sum(v for t, v in _hd.items() if t in ("00878", "00713", "0056", "00919", "00918", "00888"))
_tw_t = sum(v for t, v in _hd.items() if t in ("0050", "006208", "009816", "00981A", "00984A"))
_us_t = sum(v for t, v in _hd.items() if t in ("00646", "009823", "009824"))
_bd_t = _hd.get("00983D", 0)
w(f"<tr><td>🔴 高股息族群</td><td class='num'>{_def_t:,}</td><td class='num'>{_def_t/_sec_t*100:.1f}%</td><td>擁擠+成分重疊（00878/0056/00919 前十大同籃）</td></tr>")
w(f"<tr><td>🟡 台股市值</td><td class='num'>{_tw_t:,}</td><td class='num'>{_tw_t/_sec_t*100:.1f}%</td><td>台積電權重 ~50-57%</td></tr>")
w(f"<tr><td>🟢 美股</td><td class='num'>{_us_t:,}</td><td class='num'>{_us_t/_sec_t*100:.1f}%</td><td>009824 100% 科技</td></tr>")
w(f"<tr><td>🟢 債券</td><td class='num'>{_bd_t:,}</td><td class='num'>{_bd_t/_sec_t*100:.1f}%</td><td>低風險</td></tr>")
w("</tbody></table>")
w("<p style='font-size:12px;color:#64748b'>⚠️ 全組合半導體&科技鏈穿透（估算）：證券 ~107 萬 + 基金 ~32 萬 + 保單底層 ~228 萬 ≈ <strong>367 萬（總資產 ~22.6%）</strong>；半導體純曝險粗估 ~240 萬（~14.8%），主要來源＝保單底層（貝萊德世界科技/安聯AI）+ 台股市值 ETF 台積電權重。建議週報以成分權重精算。</p>")
w("<p style='font-size:12px;color:#64748b'>🚨 行動建議：00919/00918 停加碼（平準金+重疊度最高）；高股息族群不新增資金；00878 續持（建倉計畫內）；新資金優先現金/債券/00713 低波。</p>")
w("</div>")

w(f"<p class='meta'>龍九控股 ｜ 穿透分析 v2.1<br>數據源: snapshot.json + calc_penetration</p>")
w("</body></html>")

out_path = BASE / f"penetration_report_{today}.html"
out_path.write_text("\n".join(lines), encoding="utf-8")
print(f"✅ {out_path.name} ({len(''.join(lines)):,} bytes)")
