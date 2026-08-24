#!/usr/bin/env python3
"""monthly_report.py — 每月資產彙整月報
彙整月初vs月末資產變化 + 被動收入 + 保單組合變動 + 穿透配置
用法：python monthly_report.py 2026-07
"""
import json, sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent

def load_json(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

def main():
    ym = sys.argv[1] if len(sys.argv) > 1 else "2026-07"
    year, month = ym.split("-")
    hist = load_json(BASE / "asset_diff_history.json")
    snap = load_json(BASE / "snapshot.json")

    # 該月所有歷史日期（top-level 從 DB 來，正確）
    month_dates = sorted([d for d in hist if d.startswith(ym)])
    if not month_dates:
        print(f"❌ {ym} 無資料")
        return
    first_d = month_dates[0]
    last_d = month_dates[-1]
    first, last = hist[first_d], hist[last_d]

    # 資產變化：用四源加總（現金+證券+保險+基金），避免 bonds 口徑差異
    def liq(h):
        return (h.get("cash", 0) or 0) + (h.get("securities_market", 0) or 0) + (h.get("insurance_current", 0) or 0) + (h.get("fund_market", 0) or 0)

    rows = []
    for key, label in [("cash", "現金"), ("securities_market", "證券市值"), ("insurance_current", "保單現值"), ("fund_market", "基金市值")]:
        fv, lv = first.get(key, 0) or 0, last.get(key, 0) or 0
        rows.append((label, fv, lv, lv - fv))
    rows.append(("流動資產合計", liq(first), liq(last), liq(last) - liq(first)))
    if first.get("total_liabilities") and last.get("total_liabilities"):
        rows.append(("總負債", first["total_liabilities"], last["total_liabilities"], last["total_liabilities"] - first["total_liabilities"]))
        rows.append(("淨資產(流動-負債)", liq(first) - first["total_liabilities"], liq(last) - last["total_liabilities"], (liq(last) - last["total_liabilities"]) - (liq(first) - first["total_liabilities"])))

    # 被動收入
    mdb = snap.get("monthly_dividend_breakdown", {})
    ins_div = mdb.get("allianz", 0) + mdb.get("firstjin", 0)

    # 現金流審查變數（2026-08-24 新增：實際 = snapshot 真值口徑）
    _sal = snap.get("salary", 39727) or 39727
    _rent_got = sum(v for d, items in (snap.get("rent_received_records", {}) or {}).items() if str(d).startswith(ym) for v in (items.values() if isinstance(items, dict) else [items]))
    _div_act = sum(v for k, v in (snap.get("dividend_records", {}) or {}).items() if str(k).startswith(ym) for v in (v.values() if isinstance(v, dict) else [v])) or snap.get("dividend_month_actual", 0) or 0
    _gf = 0
    for _k, _v in (snap.get("girlfriend_repayment_records", {}) or {}).items():
        if str(_k).startswith(ym):
            _gf += _v.get("amount", 0) if isinstance(_v, dict) else (_v if isinstance(_v, (int, float)) else 0)
    _expense = snap.get("monthly_expense", 141958) or 141958
    _rent_exp = snap.get("rent_monthly_total", 80100) or 80100
    _sal_exp, _div_exp = 39727, 100000
    _exp_total = _sal_exp + _rent_exp + _div_exp + 6000
    _act_total = _sal + _rent_got + _div_act + _gf
    _passive_act = _div_act + _rent_got
    _coverage = _passive_act / _expense * 100 if _expense else 0
    # HTML 卡別名（對齊模板變數名）
    sal_exp, sal_act, rent_exp, rent_got, div_exp, div_act = _sal_exp, _sal, _rent_exp, _rent_got, _div_exp, _div_act
    gf_act, exp_total, act_total, rent_gap = _gf, _exp_total, _act_total, _rent_exp - _rent_got
    passive_act, coverage, expense = _passive_act, _coverage, _expense
    div_norm = snap.get("monthly_dividend_total", 153389) or 153389  # 常態全月基準（含月底撥回）
    etf_div = mdb.get("etf", 0)
    fund_div = mdb.get("fund", 0)
    rent = snap.get("rent_monthly_actual", 80100)
    total_income = ins_div + etf_div + fund_div + rent

    # 保單組合變動（7/31 明細）
    brk = snap.get("insurance_breakdown", {})
    pa = brk.get("policy_a_funds", {})
    pb = brk.get("policy_b_funds", {})
    ab = snap.get("allianz_combined", 0)
    fj = snap.get("firstjin_fl65_current_value", 0)

    # 穿透配置
    pen = snap.get("penetration", {}).get("actual_twd", {})
    pct = snap.get("penetration", {}).get("actual_pct", {})

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍七月報 {ym}</title>
<style>body{{font-family:-apple-system,sans-serif;background:#f5f5f7;margin:0;padding:16px;color:#1d1d1f}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h2{{font-size:16px;font-weight:800;margin:0 0 8px;padding-left:8px;border-left:3px solid #2563eb}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
th{{background:#f0f0f5;padding:8px 6px;text-align:left;font-weight:600}}
td{{padding:8px 6px;border-top:1px solid #e5e5ea}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.up{{color:#16a34a}} .down{{color:#dc2626}}</style></head><body>
<h2>📊 龍七控股月報 {ym}</h2>
<p style="font-size:13px;color:#6e6e73">資料期間 {first_d} ~ {last_d}（歷史自 {first_d} 起追蹤）</p>
<div class="card"><h2>資產變化</h2><table><thead><tr><th>項目</th><th class="num">{first_d}</th><th class="num">{last_d}</th><th class="num">增減</th></tr></thead><tbody>"""
    for label, fv, lv, diff in rows:
        cls = "up" if diff > 0 else "down" if diff < 0 else ""
        html += f'<tr><td>{label}</td><td class="num">{fv:,.0f}</td><td class="num">{lv:,.0f}</td><td class="num {cls}">{diff:+,.0f}</td></tr>'
    html += f"""</tbody></table>
<p style="font-size:12px;color:#6e6e73;margin-top:6px">流動資產 = 現金 + 證券 + 保單 + 基金（不含不動產；歷史 bonds 口徑差異已排除）</p></div>

<div class="card"><h2>被動收入（月）</h2>
<table><thead><tr><th>來源</th><th class="num">月收</th></tr></thead><tbody>
<tr><td>保單配息</td><td class="num">{ins_div:,}</td></tr>
<tr><td>ETF配息</td><td class="num">{etf_div:,}</td></tr>
<tr><td>基金配息</td><td class="num">{fund_div:,}</td></tr>
<tr><td>房租收入</td><td class="num">{rent:,}</td></tr>
<tr style="font-weight:700;border-top:2px solid #2563eb"><td>合計</td><td class="num">{total_income:,}</td></tr>
</tbody></table></div>

<div class="card"><h2>💵 現金流審查（{ym}，2026-08-24 新增）</h2>
<table><thead><tr><th>項目</th><th class="num">預期</th><th class="num">實際</th><th class="num">差異</th></tr></thead><tbody>
<tr><td>台電薪水</td><td class="num">{sal_exp:,}</td><td class="num">{sal_act:,}</td><td class="num">{sal_act-sal_exp:+,}</td></tr>
<tr><td>租金（已收）</td><td class="num">{rent_exp:,}</td><td class="num">{rent_got:,}</td><td class="num">{rent_got-rent_exp:+,}</td></tr>
<tr><td>配息（實收）</td><td class="num">{div_exp:,}</td><td class="num">{div_act:,}</td><td class="num">{div_act-div_exp:+,}</td></tr>
<tr><td style="font-size:11px;color:#6e6e73">配息常態（全月基準）</td><td class="num">—</td><td class="num">{div_norm:,}</td><td class="num">⏳ 月底補齊</td></tr>
<tr><td>女友還款</td><td class="num">6,000</td><td class="num">{gf_act:,}</td><td class="num">{gf_act-6000:+,}</td></tr>
<tr style="font-weight:700;border-top:2px solid #2563eb"><td>合計</td><td class="num">{exp_total:,}</td><td class="num">{act_total:,}</td><td class="num">{act_total-exp_total:+,}</td></tr>
</tbody></table>
<p style="font-size:12px;color:#6e6e73;margin-top:6px">預期 = snapshot 月收入口徑（配息保守 100,000）｜實際 = snapshot 真值（dividend_records 合計 + rent_received_records）｜待收租金 = {rent_gap:,}｜一次性收入（環保標結餘等）不計常態</p>
<p style="font-size:12.5px;margin-top:8px"><strong>覆蓋率：</strong>被動（配息 {div_act:,} + 租金 {rent_got:,} = {passive_act:,}） vs 月開支 {expense:,} = {coverage:.0f}% {'✅' if coverage >= 100 else '🔴'}</p>
</div>

<div class="card"><h2>保單組合（{last_d}）</h2>
<table><thead><tr><th>保單</th><th>基金</th><th class="num">現值</th></tr></thead><tbody>"""
    for pname, funds in [("安聯A", pa), ("安聯B", pb)]:
        for fname, fval in funds.items():
            v = fval["value"] if isinstance(fval, dict) else fval
            html += f'<tr><td>{pname}</td><td>{fname}</td><td class="num">{v:,.0f}</td></tr>'
    html += f"""<tr style="border-top:2px solid #2563eb;font-weight:700"><td>安聯A+B</td><td></td><td class="num">{ab:,.0f}</td></tr>
<tr><td>第一金FA81聯博</td><td></td><td class="num">{fj:,.0f}</td></tr>
<tr style="font-weight:700"><td>保單總值</td><td></td><td class="num">{snap.get('insurance_current_value', 0):,.0f}</td></tr>
</tbody></table></div>

<div class="card"><h2>穿透配置（{last_d}）</h2>
<table><thead><tr><th>類別</th><th class="num">金額</th><th class="num">佔比</th></tr></thead><tbody>"""
    for k, label in [("台股市值型成長", "台股"), ("美股市值型成長", "美股"), ("防守型配息", "防守"), ("債券", "債券"), ("現金/安全網", "現金")]:
        v = pen.get(k, 0)
        p = pct.get(k, 0)
        html += f'<tr><td>{label}</td><td class="num">{v:,.0f}</td><td class="num">{p:.1f}%</td></tr>'
    html += f"""</tbody></table></div>

<div class="card"><h2>本月重點</h2>
<ul style="font-size:14px;line-height:1.8;margin:0;padding-left:20px">
<li>🔁 保單組合調整：新增 PIMCO收益增長（A 1,683,485 + B 952,834），聯博美國成長出清，安聯B M&G 轉出</li>
<li>🏦 國泰轉貸：核貸 2.6% 進行中（預計 8/2 完成），以轉貸清償保單借貸</li>
<li>📉 Fed 7/30 維持利率 3.50-3.75%，30年公債破 5.2%，市場震盪</li>
<li>💰 本月配息：保單 118,296 + ETF 10,740 + 基金 615 = 129,651</li>
</ul></div>
<p style="font-size:12px;color:#9a9aa0;text-align:center">龍七控股自動月報 · 資料來源 snapshot.json + dragon_assets.db</p>
</body></html>"""

    out = BASE / f"monthly_report_{ym}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 月報: {out.name}")

if __name__ == "__main__":
    main()
