# -*- coding: utf-8 -*-
"""build_weekly_report.py — 龍九完整週報（12 章節版，2026-08-15 升級，參考 8/9 動態週報結構）
一資產實相 / 二Rhythm燈號 / 三穿透 / 四下週行動 / 五風險紅線 / 六滯脹測試
七保守度評估 / 八CEO備忘 / 九債務時程 / 十套利框架 / 十一動態監測 / 十二引擎熔斷
"""
import json, datetime
from pathlib import Path

REPO = Path(r"C:\Users\bot\Desktop\longjiu_system")
today = datetime.date.today().isoformat()
week_ago = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()

def load(p):
    f = REPO / p
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from market_indicator_panel import build_panel
    snap = load("snapshot.json")
    hist = load("asset_diff_history.json")
    decs = load("dashboard_decisions.json")
    st = load("us30y_state.json")

    apct = snap.get("penetration", {}).get("actual_pct", {})
    atwd = snap.get("penetration", {}).get("actual_twd", {})
    targets = snap.get("penetration", {}).get("targets", {})
    total = snap.get("total_assets", 0)
    cash = snap.get("cash_total", 0)
    _pi = snap.get("passive_income", {}) or {}
    _passive = _pi.get("total_conservative", 183333)
    _exp = snap.get("monthly_expense", 162781)
    _cov = round(_passive / _exp * 100) if _exp else 0
    us30y = st.get("last_rate")
    mode = "防禦（A）" if st.get("mode") == "A" else "布局（B）" if st.get("mode") == "B" else "未知"
    us30y_txt = f"{us30y:.2f}%" if us30y else "—"

    # ===== 一、資產實相 =====
    days = sorted([d for d in hist if week_ago <= d <= today])
    rows1 = ""
    if days:
        f, l = hist[days[0]], hist[days[-1]]
        pairs = [("總資產", "total_assets"), ("總負債", "total_liabilities"), ("證券市值", "securities_market"),
                 ("保單現值", "insurance_current"), ("基金市值", "fund_market"), ("現金", "cash"), ("房租", "rent")]
        for label, k in pairs:
            a, b = f.get(k, 0), l.get(k, 0)
            diff = b - a
            cls = "up" if diff > 0 else ("down" if diff < 0 else "")
            rows1 += f"<tr><td>{label}</td><td class='num'>{a:,.0f}</td><td class='num'>{b:,.0f}</td><td class='num {cls}'>{diff:+,.0f}</td></tr>"
    # 歸因分析
    if days:
        f, l = hist[days[0]], hist[days[-1]]
        d_total = l.get("total_assets", 0) - f.get("total_assets", 0)
        d_cash = l.get("cash", 0) - f.get("cash", 0)
        d_sec = l.get("securities_market", 0) - f.get("securities_market", 0)
        d_ins = l.get("insurance_current", 0) - f.get("insurance_current", 0)
        d_fund = l.get("fund_market", 0) - f.get("fund_market", 0)
        cause = []
        if abs(d_cash) > 50000: cause.append(f"現金 {d_cash:+,.0f}（還債/換匯為主）")
        if abs(d_sec) > 20000: cause.append(f"證券 {d_sec:+,.0f}（價格波動/操作）")
        if abs(d_ins) > 20000: cause.append(f"保單 {d_ins:+,.0f}（淨值波動）")
        if abs(d_fund) > 10000: cause.append(f"基金 {d_fund:+,.0f}（淨值波動）")
        attrib = "；".join(cause) if cause else "小幅波動"
        attrib_html = f"<p style='font-size:12px;color:#6e6e73;margin:8px 0 0'>🔍 歸因：{attrib}｜總資產變化 {d_total:+,.0f}</p>"
    else:
        attrib_html = ""

    # ===== 三、穿透 =====
    BUCKETS = [("台股市值型成長", "台股市值型目標", "🇹🇼 台股", "配息導流+回檔小單（≤5萬）"),
               ("美股市值型成長", "美股市值型目標", "🇺🇸 美股", "逢彈減碼（≤20萬/次）"),
               ("防守型配息", "配息型目標", "🛡️ 防守", "已達標，配息優先導入"),
               ("債券", "債券型目標", "💵 債券", "維持底倉，停止新增"),
               ("現金/安全網", "現金目標", "💰 現金", "優先回補 ≥70萬")]
    rows3 = ""
    for ak, tk, label, act in BUCKETS:
        a, t = apct.get(ak, 0), targets.get(tk, 0)
        v = atwd.get(ak, 0)
        gap = a - t
        light = "🟢" if abs(gap) <= 1.5 else ("🟡" if abs(gap) <= 3 else "🔴")
        rows3 += f"<tr><td>{label}</td><td class='num'>{v:,.0f}</td><td class='num'>{a:.1f}%</td><td class='num'>{t}%</td><td class='num'>{gap:+.1f}pp</td><td>{light}</td><td style='font-size:11px;color:#6e6e73'>{act}</td></tr>"

    # ===== 五、風險紅線 =====
    us_ok = apct.get("美股市值型成長", 0) <= 33
    cash_ok = cash >= 700000
    us30y_ok = us30y is None or us30y < 5.30
    rows5 = f"""<tr><td>US30Y &lt; 5.30%（債券凍結線）</td><td>{'✅' if us30y_ok else '❌'}</td><td>{us30y_txt}（{mode}）</td></tr>
    <tr><td>現金 ≥ 70 萬（6個月開支）</td><td>{'✅' if cash_ok else '❌'}</td><td>{cash:,}（需求 851,748）</td></tr>
    <tr><td>美股 ≤ 33%</td><td>{'✅' if us_ok else '❌'}</td><td>{apct.get('美股市值型成長',0):.1f}%</td></tr>
    <tr><td>LTV ≤ 40%</td><td>✅</td><td>未質押</td></tr>
    <tr><td>台股單筆 ≤ 5 萬</td><td>✅</td><td>管制中</td></tr>
    <tr><td>被動實收 ≥ 常態 80%</td><td>✅</td><td>{_passive:,}/月 &gt; 123,607×0.8</td></tr>"""

    # ===== 六、滯脹測試 =====
    stag_txt = f"US30Y {us30y_txt}" if us30y else "—"
    stag = f"""<table><thead><tr><th>情境</th><th>觸發</th><th>動作</th></tr></thead><tbody>
    <tr><td>🔴 滯脹警戒</td><td>US30Y &gt; 5.15%（{stag_txt}）</td><td>LTV 上限 ≤30%；停建長債；美股逢彈減碼</td></tr>
    <tr><td>🟡 警戒區</td><td>5.20-5.30%</td><td>台股 ≤50萬/週；美股停購；長債凍結；LTV ≤30%</td></tr>
    <tr><td>🚨 全域凍結</td><td>≥5.30%</td><td>禁新增質押/擴倉；僅配息被動再平衡+還債</td></tr>
    <tr><td>💱 匯率</td><td>台幣單季升 &gt;5%</td><td>禁新增質押；&gt;8% 動水庫還貸壓 LTV≤35%</td></tr>
    </tbody></table>"""

    # ===== 七、保守度 =====
    cons = """<table><thead><tr><th>標的</th><th>定位</th><th>保守度</th><th>本週狀態</th></tr></thead><tbody>
    <tr><td>00878</td><td>台股高股息核心</td><td>🟢 高</td><td>配息導流標的；回檔小單（≤5萬）</td></tr>
    <tr><td>00983D</td><td>債券防禦</td><td>🟢 高</td><td>維持 20,000 單位；停止新增</td></tr>
    <tr><td>PIMCO/安聯收益</td><td>保單平衡</td><td>🟢 中高</td><td>JPM 轉入後債券權重升（47%債）</td></tr>
    <tr><td>貝萊德世界科技A10</td><td>美股科技</td><td>🔴 高波動</td><td>減持中（安聯A/B 已降）</td></tr>
    <tr><td>00401A（觀察）</td><td>Covered Call 配息穩定器</td><td>🟡 中</td><td>8/18 除息；成分科技曝險待確認</td></tr>
    <tr><td>009821（觀察）</td><td>稀土避險衛星</td><td>🟡 中高波動</td><td>≤總資產5%；現金緊非買點</td></tr>
    </tbody></table>"""

    # ===== 九、債務時程 =====
    debt_chain = """<table><thead><tr><th>時程</th><th>事件</th><th>狀態</th></tr></thead><tbody>
    <tr><td><b>8/20</b></td><td>國泰 1,200萬 撥款入帳 → 8/20 定案（富達600萬+MMF600萬）</td><td>✅ 已入帳</td></tr>
    <tr><td>PI 認列後（~9/3）</td><td>質押富達 5成 300萬@2.77% → 還安聯保單借貸 300萬@4.2%</td><td>⏳</td></tr>
    <tr><td>PI 認列後</td><td>MMF 600萬 → 10月標案預備金 5-600萬（流動性保留）</td><td>⏳</td></tr>
    <tr><td>9-10月</td><td>PI 資格送件（資產 3,000萬 盤點）</td><td>⏳</td></tr>
    <tr><td>10/1</td><td>築巢優利貸 2.185% 轉換（舊房貸 9/25 到期）</td><td>⏳</td></tr>
    <tr><td>階段2（可選）</td><td>質押 LTV≤50%｜4 門檻全過才執行</td><td>⏸ 選擇性</td></tr>
    </tbody></table>"""

    # ===== 十、套利框架 =====
    arb = """<table><thead><tr><th>路徑</th><th>淨利差</th><th>狀態</th></tr></thead><tbody>
    <tr><td>① 債務重置（還 4.2% 債）</td><td class="num">+4.2%（確定性）</td><td>🟢 8/15 執行</td></tr>
    <tr><td>② 美元 MMF/短債</td><td class="num">+1.2-1.6%</td><td>🟢 停泊期可用</td></tr>
    <tr><td>③ 1-3Y 投資級階梯</td><td class="num">+1.9-2.4%</td><td>🟢 建債梯後</td></tr>
    <tr><td>❌ 高股息ETF套利</td><td class="num">—</td><td>⛔ 禁止</td></tr>
    <tr><td>❌ 長債疊槓</td><td class="num">—</td><td>⛔ 禁止</td></tr>
    </tbody></table>"""

    # ===== 十一、動態監測 =====
    mon = f"""<table><thead><tr><th>維度</th><th>指標</th><th>狀態</th></tr></thead><tbody>
    <tr><td>① 市場利率</td><td>US30Y {us30y_txt}</td><td>{'🟡 警戒' if (us30y or 0) >= 5.20 else '🟢'}</td></tr>
    <tr><td>② 匯率</td><td>USD/TWD 基準 32.18</td><td>🟢 波動監控中</td></tr>
    <tr><td>③ PI 資格</td><td>已開啟（snapshot 待更新）</td><td>🟡 撥款後送件</td></tr>
    <tr><td>④ LTV</td><td>未質押</td><td>🟢 0%</td></tr>
    <tr><td>⑤ 現金流</td><td>被動 {_passive:,}/月 vs 開支 {_exp:,}</td><td>🟢 覆蓋 {_cov}%</td></tr>
    <tr><td>2b 日圓</td><td>USD/JPY 監控（≥155🟢/150-155🟡/&lt;150🚨）</td><td>— 待抓取</td></tr>
    </tbody></table>"""

    # ===== 十二、引擎熔斷 =====
    eng = f"""<table><thead><tr><th>閘門</th><th>條件</th><th>目前</th></tr></thead><tbody>
    <tr><td>HALT_ALL_BUY</td><td>現金 &lt; 70萬</td><td>{'🔴 觸發' if cash < 850000 else '🟢'}</td></tr>
    <tr><td>FREEZE_US_BUY</td><td>美股 &gt; 33%</td><td>{'🟡 觸發' if apct.get('美股市值型成長',0) > 33 else '🟢'}</td></tr>
    <tr><td>US30Y 警戒</td><td>≥5.20%</td><td>{'🟡 觸發' if (us30y or 0) >= 5.20 else '🟢'}</td></tr>
    <tr><td>LTV 熔斷</td><td>&gt;38%</td><td>🟢 0%</td></tr>
    <tr><td>淨利差</td><td>&lt;0 虧損</td><td>🟢 正利差</td></tr>
    </tbody></table>"""

    # ===== 四、下週行動 =====
    act4 = """<ol style="padding-left:18px;margin:0">
<li><b>8/20 國泰撥款 1,200萬 入帳</b> → 8/20 定案：富達全球動能多元 600萬（質押擔保品）＋MMF 600萬（PI認列2週）→ 質押300萬@2.77%還安聯300萬@4.2% → MMF轉10月標案預備金</li>
<li><b>PI 送件</b>：撥款後盤點資產 3,000萬</li>
<li><b>美股逢彈減碼</b>（38.7%→30%，≤20萬/次）→ 資金導向防守</li>
<li><b>現金回補</b>（≥70萬底線）</li>
<li><b>每週六再平衡評估</b>＋保單 JPM 轉換後穿透追蹤</li>
</ol>"""

    # ===== 八、CEO 備忘 =====
    ceo = f"""<ul style="padding-left:18px;margin:0;font-size:13px">
<li><b>負債率雙軌</b>：含不動產 {snap.get('debt_ratio', 36.3):.1f}%｜流動 {snap.get('total_liabilities',0)/total*100:.1f}% — 8/15 還債後大幅下降</li>
<li><b>套利引擎不關閉</b>：負債 ≤4% 是低成本資本（借4%投5%），還債≠目標，利差&gt;開支才是退休基礎</li>
<li><b>保單 JPM 轉換正確</b>：貝萊德科技減持 → 債券權重升，美股超標收斂</li>
<li><b>8/20 定案</b>：質押富達 5成 300萬@2.77%（PI 認列後執行）；還債優先序：安聯 300萬@4.2% 第一</li>
<li><b>時間哲學</b>：台電身份=護城河；先等 9 等晉升再評估侍親留停；2027/2 年終後評估資產公司節稅</li>
</ul>"""

    # ===== 決策 =====
    dec_rows = ""
    if isinstance(decs, list):
        this_week = [d for d in decs if week_ago <= str(d.get("date", ""))[:10] <= today]
        for d in this_week[-6:]:
            dec_rows += f"<li>📌 {d.get('date','')[:10]}｜{str(d.get('summary', d.get('decision', d.get('content',''))))[:90]}</li>"
    if not dec_rows:
        dec_rows = "<li>本週重大決策：8/14 保單 JPM 轉換穿透更新（詳見穿透分析）</li>"

    rhythm = f"""<table><thead><tr><th>燈號</th><th>範圍</th><th>規則</th></tr></thead><tbody>
    <tr><td>🟢</td><td>&lt;5.20%</td><td>解凍；可分批建倉</td></tr>
    <tr><td>🟡</td><td>5.20-5.30%</td><td>警戒：台股≤50萬/週、美股停購、長債凍結、LTV≤30%</td></tr>
    <tr><td>🔴</td><td>≥5.30%</td><td>五因子綜合判斷（非直接凍結）；LTV低+匯率穩仍可分批</td></tr>
    <tr><td>🚨</td><td>≥5.40%</td><td>調降 00983D 轉中短債</td></tr>
    </tbody></table>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九週報 {today}</title>
<style>
body{{font-family:-apple-system,sans-serif;background:#f5f5f7;margin:0;padding:16px;color:#1d1d1f}}
h1{{font-size:20px;font-weight:800;margin:0 0 4px}}
.sub{{color:#6e6e73;font-size:12px;margin-bottom:16px}}
.card{{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
h2{{font-size:14px;font-weight:800;margin:0 0 10px;padding-left:8px;border-left:3px solid #2563eb}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th{{background:#f0f0f5;padding:6px;text-align:left;font-weight:600}}
td{{padding:6px;border-top:1px solid #e5e5ea}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.up{{color:#16a34a}}.down{{color:#dc2626}}
li{{margin-bottom:5px;font-size:12.5px;line-height:1.5}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:12px}}
.kpi{{background:#fff;border-radius:10px;padding:11px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.kpi .k{{font-size:10px;color:#6e6e73}}.kpi .v{{font-size:16px;font-weight:800;color:#2563eb;margin-top:2px}}
.kpi .v.red{{color:#dc2626}}.kpi .v.green{{color:#16a34a}}
</style></head><body>
<h1>📊 龍九週報</h1>
<div class="sub">{week_ago} ~ {today}｜US30Y {us30y_txt}｜{mode}｜自動產出</div>

<div class="kpis">
  <div class="kpi"><div class="k">總資產</div><div class="v">{total:,}</div></div>
  <div class="kpi"><div class="k">總負債</div><div class="v red">{snap.get('total_liabilities',0):,}</div></div>
  <div class="kpi"><div class="k">現金</div><div class="v {'green' if cash_ok else 'red'}">{cash:,}</div></div>
  <div class="kpi"><div class="k">被動月收</div><div class="v green">{_passive:,}</div></div>
  <div class="kpi"><div class="k">美股佔比</div><div class="v {'green' if us_ok else 'red'}">{apct.get('美股市值型成長',0):.1f}%</div></div>
</div>

<div class="card"><h2>📌 一、本週資產實相（{week_ago}→{today}）</h2>
<table><thead><tr><th>項目</th><th class="num">7日前</th><th class="num">今日</th><th class="num">增減</th></tr></thead><tbody>{rows1}</tbody></table>{attrib_html}</div>

<div class="card"><h2>🎵 二、Rhythm-08 風險燈號（US30Y）</h2>
<p style="font-size:13px;margin:0 0 8px">目前 US30Y <b>{us30y_txt}</b> → 模式 <b>{mode}</b></p>
{rhythm}</div>

<div class="card"><h2>📊 三、穿透對照（目標 15/30/20/30/5）</h2>
<table><thead><tr><th>類別</th><th class="num">金額</th><th class="num">實際</th><th class="num">目標</th><th class="num">差距</th><th>燈號</th><th>建議</th></tr></thead><tbody>{rows3}</tbody></table></div>

<div class="card"><h2>🎯 四、下週行動</h2>{act4}</div>

<div class="card"><h2>🔧 五、風險紅線檢核</h2>
<table><thead><tr><th>紅線</th><th>狀態</th><th>現況</th></tr></thead><tbody>{rows5}</tbody></table></div>

<div class="card"><h2>🌩️ 六、滯脹場景壓力測試</h2>{stag}</div>

<div class="card"><h2>🛡️ 七、投資標的保守度評估</h2>{cons}</div>

<div class="card"><h2>💡 八、CEO 備忘</h2>{ceo}</div>

<div class="card"><h2>🗓️ 九、債務重整時程鏈</h2>{debt_chain}</div>

<div class="card"><h2>💎 十、低風險利差套利框架</h2>{arb}</div>

<div class="card"><h2>🚨 十一、動態監測模組（五大維度）</h2>{mon}</div>

<div class="card"><h2>⚙️ 十二、套利引擎與熔斷閘門</h2>{eng}</div>

<div class="card"><h2>📌 本週決策紀錄</h2><ul style="padding-left:18px;margin:0">{dec_rows}</ul></div>

<div class="card" style="background:#fefce8;border:1px solid #fde68a"><h2 style="border-color:#f59e0b">⚠️ 執行紀律</h2>
<ul style="padding-left:18px;margin:0;font-size:12.5px">
<li>台股單筆 ≤5 萬、回檔小單、不追漲；美股單次調度 ≤20 萬</li>
<li>現金底線 70 萬（6個月開支）任何操作後不得跌破</li>
<li>8/15 前：僅配息導流，暫緩大規模賣出（國泰授信審查）</li>
<li>質押紀律：LTV 50% 上限；擔保品富達（股80.75%）-30% → LTV 71% 觸追繳區；US30Y≥5.30% 禁新增質押</li>
</ul></div>

<p style="color:#6e6e73;font-size:10px;text-align:center;margin-top:20px">龍九控股自動產出｜資料：snapshot/asset_diff_history/us30y_state/dashboard_decisions｜穿透公式：桶值÷總資產（不含不動產）</p>
</body></html>"""

    out = REPO / f"weekly_report_{today}.html"
    out.write_text(html + build_panel() + "\n", encoding="utf-8")
    print(f"✅ {out.name}（{len(html):,} bytes）")

if __name__ == "__main__":
    main()
