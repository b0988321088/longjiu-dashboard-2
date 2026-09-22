#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_cost_report.py — AI 費用頁（cost.html）＋ 即時資料（cost_data.json）

單一真值：`data/ai_cost_daily.jsonl`（由 ai_cost_watch.py 維護）
  → 本檔呼叫 ai_cost_watch.build() 取得同一份口徑，**不自己重算任何數字**
  → 產出兩個檔：
      cost.html      靜態完整頁（種子 JSON 內嵌 → 無 JS/fetch 失敗也能看）
      cost_data.json 前端開頁時 fetch 覆寫（cache:no-store）→ 開頁即最新

設計決策（2026-09-22）：
  · 固定檔名 cost.html（無日期）→ 儀表板那顆按鈕永遠不會指向舊檔
    （links_config.PLACEHOLDER_FIXED）。日期型檔名的報表每過一天就會變成落後連結。
  · 前端只寫一份渲染邏輯（JS），Python 只負責產生種子 JSON —— 避免
    「Python 靜態層與 JS 即時層兩套規則要同步」的雙寫陷阱。
  · 自帶 CSS（不依賴 Tailwind／CDN）：載入失敗時版面仍完整（見技能 dashboard-mobile-pitfalls）。
  · JS 一律 ES5（var / function / 字串相加）：舊 WebView 不會整段解析失敗。

用法：
  python build_cost_report.py            # 產出 cost.html + cost_data.json
  python build_cost_report.py --quiet    # 只產檔、不印摘要（cron 用）
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import ai_cost_watch as acw  # noqa: E402

OUT_HTML = BASE / "cost.html"
OUT_JSON = BASE / "cost_data.json"

CSS = """
:root{
  --bg:#0b1120; --bg2:#0f172a; --card:rgba(30,41,59,.72); --line:rgba(255,255,255,.07);
  --ink:#e8eefc; --muted:#93a4c4; --ds:#38bdf8; --gem:#a78bfa; --free:#34d399;
  --ok:#34d399; --warn:#fbbf24; --bad:#fb7185;
}
*{box-sizing:border-box}
body{margin:0;background:
  radial-gradient(1200px 600px at 12% -10%,rgba(56,189,248,.10),transparent 60%),
  radial-gradient(900px 500px at 88% 0%,rgba(167,139,250,.10),transparent 55%),
  var(--bg);
  color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans TC","Helvetica Neue",Arial,sans-serif;
  -webkit-text-size-adjust:100%;line-height:1.55;}
.wrap{max-width:1080px;margin:0 auto;padding:18px 14px 56px}
header.top{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;justify-content:space-between;margin-bottom:16px}
h1{font-size:22px;margin:0;letter-spacing:.5px}
h1 small{display:block;font-size:11.5px;color:var(--muted);font-weight:400;margin-top:4px;letter-spacing:0}
h2{font-size:14.5px;margin:0 0 10px;display:flex;flex-wrap:wrap;gap:8px;align-items:baseline}
h2 em{font-style:normal;font-size:11.5px;color:var(--muted);font-weight:400}
.card{background:var(--card);backdrop-filter:blur(10px);border:1px solid var(--line);
  border-radius:16px;padding:14px 16px;margin-bottom:14px;box-shadow:0 10px 25px -8px rgba(0,0,0,.45)}
.grid{display:grid;gap:12px}
.k4{grid-template-columns:repeat(2,minmax(0,1fr))}
.k2{grid-template-columns:repeat(1,minmax(0,1fr))}
@media(min-width:760px){ .k4{grid-template-columns:repeat(4,minmax(0,1fr))} .k2{grid-template-columns:repeat(2,minmax(0,1fr))} }
.kpi{background:linear-gradient(160deg,rgba(255,255,255,.055),rgba(255,255,255,.015));
  border:1px solid var(--line);border-radius:14px;padding:12px 13px;position:relative;overflow:hidden}
.kpi .lab{font-size:11px;color:var(--muted);letter-spacing:.4px}
.kpi .val{font-size:23px;font-weight:800;font-variant-numeric:tabular-nums;margin-top:3px}
.kpi .sub{font-size:11px;color:var(--muted);margin-top:3px}
.kpi.accent{box-shadow:inset 0 0 0 1px rgba(56,189,248,.18)}
.muted{color:var(--muted)}
.chip{display:inline-block;font-size:10.5px;padding:2px 8px;border-radius:999px;border:1px solid;white-space:nowrap}
.chip.ok{color:var(--ok);border-color:rgba(52,211,153,.45);background:rgba(52,211,153,.10)}
.chip.warn{color:var(--warn);border-color:rgba(251,191,36,.45);background:rgba(251,191,36,.10)}
.chip.bad{color:var(--bad);border-color:rgba(251,113,133,.45);background:rgba(251,113,133,.10)}
.chip.info{color:#7dd3fc;border-color:rgba(125,211,252,.35);background:rgba(125,211,252,.08)}
.bdrow{border-top:1px dashed var(--line);padding:11px 0 4px}
.bdrow:first-child{border-top:0;padding-top:2px}
.bdhead{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:700;font-size:13.5px}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block}
.dot.ds{background:var(--ds)} .dot.gem{background:var(--gem)} .dot.free{background:var(--free)}
.bdnums{font-size:12.5px;margin-top:4px;font-variant-numeric:tabular-nums}
.bdnums b{font-size:15px}
.bdsub{font-size:11.5px;color:var(--muted);margin-top:2px}
.spark{display:flex;gap:4px;align-items:flex-end;height:34px;margin-top:8px}
.spark i{flex:1;background:linear-gradient(180deg,var(--ds),rgba(56,189,248,.25));border-radius:4px 4px 2px 2px;min-height:3px;display:block}
.spark.gem i{background:linear-gradient(180deg,var(--gem),rgba(167,139,250,.25))}
.spark.free i{background:linear-gradient(180deg,var(--free),rgba(52,211,153,.22))}
.bars{position:absolute;left:42px;right:0;bottom:0;height:118px;display:flex;gap:3px;align-items:flex-end;border-bottom:1px solid var(--line)}
.plot{position:relative;height:134px;margin-top:4px}
.gl{position:absolute;left:42px;right:0;border-top:1px dashed rgba(255,255,255,.08)}
.gl span{position:absolute;left:-42px;top:-7px;width:38px;text-align:right;font-size:9.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:3px;height:100%;position:relative}
.col .vlab{font-size:8.5px;color:#cbd5e1;font-variant-numeric:tabular-nums;white-space:nowrap}
.col .st{width:100%;display:flex;flex-direction:column;justify-content:flex-end;gap:2px}
.seg{border-radius:3px 3px 0 0}
.seg.ds{background:linear-gradient(180deg,#38bdf8,#0ea5e9)}
.seg.gem{background:linear-gradient(180deg,#a78bfa,#7c3aed)}
.seg.free{background:linear-gradient(180deg,#34d399,#059669)}
.xlab{display:flex;gap:3px;margin:6px 0 0 42px}
.xlab span{flex:1;text-align:center;font-size:9.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.xlab span.w{color:var(--warn)}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin-top:8px}
.legend i{width:9px;height:9px;border-radius:2px;display:inline-block;margin-right:5px}
.tl{position:relative;padding-left:16px}
.tl:before{content:"";position:absolute;left:4px;top:4px;bottom:4px;width:1px;background:var(--line)}
.tl .ev{position:relative;padding:6px 0;font-size:12.5px}
.tl .ev .src{display:block;font-size:11px;color:var(--muted);margin-top:1px}
.tl .ev:before{content:"";position:absolute;left:-15px;top:12px;width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(52,211,153,.14)}
.alert{display:flex;gap:9px;align-items:flex-start;border:1px solid;border-radius:12px;padding:9px 11px;margin-bottom:7px;font-size:12.5px}
.alert.warn{border-color:rgba(251,191,36,.35);background:rgba(251,191,36,.07)}
table.fb{width:100%;border-collapse:collapse;font-size:12.5px}
table.fb th{text-align:left;font-weight:500;color:var(--muted);padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap;width:38%}
table.fb td{padding:6px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.alert.critical{border-color:rgba(251,113,133,.45);background:rgba(251,113,133,.09)}
.alert .code{font-weight:800;font-size:11px;opacity:.85;white-space:nowrap}
.note{font-size:11.5px;color:var(--muted);border-top:1px solid var(--line);margin-top:6px;padding-top:9px}
.bar2{height:9px;border-radius:6px;background:rgba(255,255,255,.06);overflow:hidden;margin-top:5px}
.bar2 i{display:block;height:100%;border-radius:6px}
footer{font-size:11px;color:var(--muted);text-align:center;margin-top:18px;line-height:1.8}
a.back{color:#7dd3fc;text-decoration:none;font-size:12px}
"""

JS = """
function esc(s){ s = (s===null||s===undefined) ? '' : String(s);
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function money(n){ n = Number(n||0); var s = Math.round(n).toString();
  return s.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ','); }
function n1(n){ return (Math.round(Number(n||0)*10)/10).toString(); }
function cls(level){ return level==='normal'?'ok':(level==='elevated'?'warn':(level==='spike'?'bad':'info')); }
function verdictWord(level){ return level==='normal'?'正常':(level==='elevated'?'偏高':(level==='spike'?'異常集中':'—')); }

function walletVerdict(b, topN, CW){
  if(!b.total_twd){ return '正常（無花費）'; }
  if(b.ratio===null||b.ratio===undefined){ return '集中（多數日 0，'+Math.round((b.top3_share||0)*100)+'% 來自前 '+topN+' 天）'; }
  var t = verdictWord(b.level)+'（日均 '+n1(b.ratio)+'× 中位數）';
  if((b.top3_share||0) >= 0.8){ t += '｜'+Math.round(b.top3_share*100)+'% 集中在前 '+topN+' 天';
    if(b.cer_days){ t += '（其中 '+b.cer_days+' 天 CER ≥ '+CW+'）'; } }
  return t;
}

function kpi(lab, val, sub, accent){
  return '<div class="kpi'+(accent?' accent':'')+'"><div class="lab">'+esc(lab)+'</div>'+
         '<div class="val">'+val+'</div><div class="sub">'+sub+'</div></div>';
}

function walletBadge(days, warnAt, critAt){
  if(days===null||days===undefined){ return '<span class="chip info">無資料</span>'; }
  var c = days<critAt?'bad':(days<warnAt?'warn':'ok');
  return '<span class="chip '+c+'">'+n1(days)+' 天</span>';
}

function bdRow(name, dotCls, b, topN, CW){
  var mx = 1; (b.series||[]).forEach(function(v){ if(v>mx){ mx=v; } });
  var bars = (b.series||[]).map(function(v){
    var h = Math.max(3, Math.round(v/mx*30));
    return '<i style="height:'+h+'px"></i>'; }).join('');
  return '<div class="bdrow"><div class="bdhead"><span class="dot '+dotCls+'"></span>'+esc(name)+
    '<span class="chip '+cls(b.level)+'">'+verdictWord(b.level)+'</span></div>'+
    '<div class="bdnums">合計 <b>NT$'+money(b.total_twd)+'</b>　｜　日均 NT$'+n1(b.avg_twd)+
    '　｜　中位數 NT$'+money(b.median_twd)+'</div>'+
    '<div class="bdsub">'+esc(walletVerdict(b, topN, CW))+'</div>'+
    '<div class="spark '+dotCls+'">'+bars+'</div></div>';
}

function niceMax(v){
  if(!v || v<=0){ return 1; }
  var p = Math.pow(10, Math.floor(Math.log(v)/Math.LN10));
  var step = p/2;
  return Math.ceil(v/step)*step;
}

function chart(series, CW){
  var mx = 1; series.forEach(function(r){ if(r.total_twd>mx){ mx=r.total_twd; } });
  var top = niceMax(mx), H = 118;   // H ＝ 可用柱高；上方留 16px 給數值標籤，避免撞到卡片標題
  var narrow = (typeof window!=='undefined' && window.innerWidth && window.innerWidth<620);
  var cols = '', labs = '';
  series.forEach(function(r, i){
    var h = Math.max(3, Math.round(r.total_twd/top*H));
    var ds = Math.round(r.ds_twd/top*H), ge = Math.round(r.gemini_twd/top*H);
    var stack = '';
    if(ge>0){ stack += '<div class="seg gem" style="height:'+Math.max(2,ge)+'px"></div>'; }
    if(ds>0){ stack += '<div class="seg ds" style="height:'+Math.max(2,ds)+'px"></div>'; }
    var vlab = (!narrow && r.total_twd >= top*0.55) ? '<div class="vlab">NT$'+money(r.total_twd)+'</div>' : '';
    cols += '<div class="col" title="'+esc(r.date)+' 合計 NT$'+money(r.total_twd)+
            '（DS '+money(r.ds_twd)+'／Gemini '+money(r.gemini_twd)+'）">'+vlab+
            '<div class="st" style="height:'+h+'px">'+stack+'</div></div>';
    var warn = r.cer >= CW;
    if(narrow && i%2){ labs += '<span></span>'; }
    else { labs += '<span class="'+(warn?'w':'')+'" title="CER '+r.cer+' 次">'+esc(r.date.slice(5))+(warn&&!narrow?' ⚠️':'')+'</span>'; }
  });
  var gl = '';
  [0,0.5,1].forEach(function(f){
    gl += '<div class="gl" style="bottom:'+Math.round(f*H)+'px"><span>'+(f===0?'0':'NT$'+money(top*f))+'</span></div>';
  });
  return '<div class="plot">'+gl+'<div class="bars">'+cols+'</div></div><div class="xlab">'+labs+'</div>'+
    '<div class="legend"><span><i class="seg ds"></i>DeepSeek</span><span><i class="seg gem"></i>Gemini</span>'+
    '<span>⚠️ = 當日 CER ≥ '+CW+' 次（內容風控次數，不是花費異常）</span></div>';
}

function render(d){
  var w = d.week || {}, wal = d.wallets || {}, cer = d.cer || {}, gov = d.governance || {};
  var bd = w.breakdown || {};
  var pg = d.page || {}, topN = pg.top_n || 3, CW = pg.cer_warn || 20;
  var h = [];

  h.push('<header class="top"><div><h1>💸 AI 費用監控<small>資料時間 '+esc(d.generated_at||'')+
    '　·　帳本 '+(d.ledger_rows||0)+' 天　·　單一真值 data/ai_cost_daily.jsonl</small></h1></div>'+
    '<div><a class="back" href="index.html">← 回主儀表板</a></div></header>');

  var wow = (w.wow_pct===null||w.wow_pct===undefined)?'':'（日均較前 '+w.prev7_days+' 日 '+(w.wow_pct>0?'+':'')+w.wow_pct+'%）';
  h.push('<section class="grid k4">');
  h.push(kpi('今日（進行中）','NT$'+money((d.today||{}).total_twd),
    'CER '+((d.today||{}).cer||0)+' 次　429 '+((d.today||{}).q429||0)+' 次', true));
  h.push(kpi('近 7 日合計','NT$'+money(w.last7_total),
    '日均 NT$'+money(w.last7_daily_avg)+' '+esc(wow)));
  h.push(kpi('DeepSeek 錢包','¥'+n1(wal.ds_balance_cny),
    '≈NT$'+money(wal.ds_balance_twd)+'　日耗 NT$'+money(wal.ds_daily_twd)+' '+walletBadge(wal.ds_days_left,14,7)));
  h.push(kpi('Gemini 錢包','NT$'+money(wal.gemini_balance_twd),
    '日耗 NT$'+money(wal.gemini_daily_twd)+' '+walletBadge(wal.gemini_days_left,14,7)));
  h.push('</section>');

  h.push('<section class="card"><h2>◆ 花費拆解<em>近 '+(bd.days||0)+' 日'+
    ((bd.dates&&bd.dates.length)?'（'+esc(bd.dates[0].slice(5))+'~'+esc(bd.dates[bd.dates.length-1].slice(5))+'）':'')+
    '　判定基準：日均 ÷ 中位數 ≤'+n1(pg.avg_ok||1.5)+'× 正常、&gt;'+n1(pg.avg_high||3)+'× 異常</em></h2>');
  h.push(bdRow('DeepSeek','ds', bd.ds||{}, topN, CW));
  h.push(bdRow('Gemini',  'gem', bd.gemini||{}, topN, CW));
  h.push(bdRow('免費入口','free', bd.free||{}, topN, CW));
  h.push('<div class="note">免費入口 '+(bd.free_calls||0)+' 次呼叫、NT$'+money((bd.free||{}).total_twd)+
    '（`:free` 與 `-free` 尾綴的模型一律不計價）。Gemini 的錢幾乎都花在 CER 高的日子 —— '+
    '扣掉集中那幾天後，平日的日均只有個位數。</div></section>');

  h.push('<section class="card"><h2>◆ 日花費序列<em>堆疊＝DS＋Gemini（NT$）</em></h2>'+chart(d.series||[], CW)+'</section>');

  h.push('<section class="card"><h2>◆ DS 內容風控（CER）<em>風控擋下的呼叫數，與花費分開看</em></h2>'+
    '<div class="grid k2"><div>'+
    '<div class="bdnums">今日 <b>'+cer.today+'</b> 次　｜　近 7 日 <b>'+cer.last7_total+'</b> 次（前 7 日 '+cer.prev7_total+'）</div>'+
    '<div class="bdsub">出現 '+cer.days_with_cer+'/7 天　｜　連續未收斂 '+cer.streak_days+' 天'+
    (cer.streak_capped?'（已回溯到帳本起點，可能更長）':'')+'　｜　429 合計 '+cer.q429_last7+' 次</div>'+
    '<div class="bdnums" style="margin-top:9px">風控外溢成本（推定）<b>NT$'+money(cer.spillover_strict_twd)+'</b></div>'+
    '<div class="bar2"><i style="width:'+Math.min(100,Math.round((cer.spillover_strict_twd||0)/Math.max(1,(cer.paid_backup_on_cer_days_upper_twd||1))*100))+
    '%;background:linear-gradient(90deg,#fb7185,#fbbf24)"></i></div>'+
    '<div class="bdsub">上限值 NT$'+money(cer.paid_backup_on_cer_days_upper_twd)+
    '（CER 當日 Gemini 全部花費；含非 CER 任務，不可當成外溢）</div></div><div>'+
    (cer.series||[]).map(function(x){ var c = x.cer>=CW?'bad':(x.cer>0?'warn':'ok');
      return '<span class="chip '+c+'" style="margin:0 4px 4px 0">'+esc(x.date.slice(5))+' '+x.cer+'</span>'; }).join('')+
    '</div></div><div class="note">CER＝DeepSeek 內容風控擋下的呼叫數，與花費分開看。'+
    '「風控外溢成本」只算 CER ≥ '+CW+' 次且免費入口接手率 &lt;10% 的日子 —— 那些日子免費層沒分擔，錢幾乎全落到 Gemini，是推定值；'+
    '「上限值」是同一批日子 Gemini 的全部花費（含與風控無關的任務），只能當天花板，不是外溢金額。</div></section>');

  var tp = (d.topups||[]), tu = (d.topups_unresolved||[]);
  h.push('<section class="card"><h2>◆ 儲值事件<em>近 14 日</em></h2><div class="tl">');
  if(!tp.length && !tu.length){ h.push('<div class="ev muted">（無）</div>'); }
  tp.forEach(function(e){ h.push('<div class="ev"><b>'+esc(e.date)+'</b>　'+esc(e.wallet)+'　+'+n1(e.amount)+' '+esc(e.unit)+
    '（≈NT$'+money(e.twd)+'）<span class="src">來源：'+esc(e.evidence)+'</span></div>'); });
  tu.forEach(function(u){ h.push('<div class="ev"><b>'+esc(u.date)+'</b>　<span class="chip warn">待人工確認</span>　'+
    esc(u.from)+'→'+esc(u.date)+' 中間缺 '+(u.gap_days-1)+' 天帳本，餘額升 '+n1(u.amount)+' '+esc(u.unit)+'</div>'); });
  h.push('</div></section>');

  var al = (d.alerts||[]);
  h.push('<section class="card"><h2>◆ 異常<em>'+(al.length?al.length+' 項':'無 ✅')+'</em></h2>');
  if(!al.length){ h.push('<div class="muted" style="font-size:12.5px">全部正常。</div>'); }
  al.forEach(function(a){ h.push('<div class="alert '+esc(a.level)+'"><span class="code">'+esc(a.code)+'</span><span>'+
    esc(a.msg)+'</span></div>'); });
  h.push('</section>');

  var gp = gov.pending ? ('基準日 '+esc(gov.baseline_date||'')+' → 自 '+esc(gov.start_date||'')+
      ' 00:00 起算（今日不併入，剩 '+(gov.days_until_start||0)+' 天）')
    : ('自 '+esc(gov.start_date||'')+' 起 '+(gov.days||0)+' 天：DS NT$'+money(gov.ds_twd)+'／Gemini NT$'+money(gov.gem_twd)+
       '／免費 NT$'+money(gov.free_twd)+'｜CER '+((gov.cer)||0)+' 次');
  h.push('<footer>◆ 治理後累計：'+gp+'<br>資料來源：data/ai_cost_daily.jsonl（ai_cost_watch.py 維護）　·　'+
    '產出：build_cost_report.py　·　<a class="back" href="index.html">回主儀表板</a></footer>');

  document.getElementById('app').innerHTML = h.join('');
}

function boot(){
  var el = document.getElementById('seed');
  var seed = null;
  try { seed = JSON.parse(el.textContent); } catch(e) { seed = null; }
  if(seed){ render(seed); }
  if(window.fetch){
    fetch('cost_data.json', {cache:'no-store'}).then(function(r){ return r.json(); })
      .then(function(d){ if(d && d.series){ render(d); } })
      .catch(function(){ /* fetch 失敗 → 保留種子版（永不顯示壞畫面） */ });
  }
}
if(document.readyState==='loading'){ document.addEventListener('DOMContentLoaded', boot); } else { boot(); }
"""

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-Hant-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>龍九 · AI 費用監控</title>
<style>__CSS__</style>
</head>
<body>
<div class="wrap" id="app">__FALLBACK__</div>
<script type="application/json" id="seed">__SEED__</script>
<script>__JS__</script>
</body>
</html>
"""


def payload() -> dict:
    """資料一律來自 ai_cost_watch.build()（同一份口徑），本檔不重算任何數字。"""
    d = acw.build(14, probe=False)
    cos = acw.THRESHOLDS.get("spend_top_n", 3)
    d["page"] = {"top_n": cos, "cer_warn": acw.THRESHOLDS.get("cer_warn", 20),
                 "avg_ok": acw.THRESHOLDS.get("spend_avg_vs_median_ok", 1.5),
                 "avg_high": acw.THRESHOLDS.get("spend_avg_vs_median_high", 3.0)}
    d["generated_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return d


def static_fallback(p: dict) -> str:
    """無 JS／JS 失敗時的靜態摘要（2026-09-22）。

    背景：本頁內容由 JS 依 seed 渲染 —— 若使用者的 WebView 解析失敗，畫面會變空白
    （2026-08-29 手機慘案的同一類風險）。因此先把關鍵數字寫成純 HTML 放進 #app，
    JS 成功時才覆寫它；fetch 即時資料失敗也保有這份，永不顯示壞畫面。
    """
    w = p.get("week", {}) or {}
    wal = p.get("wallets", {}) or {}
    cer = p.get("cer", {}) or {}
    alerts = p.get("alerts", []) or []
    bd = w.get("breakdown", {}) or {}

    def _nt(v):
        try:
            return f"{int(round(float(v))):,}"
        except Exception:
            return "—"

    ds, ge, fr = (bd.get("ds") or {}), (bd.get("gemini") or {}), (bd.get("free") or {})
    rows = [
        ("今日（進行中）", "NT$" + _nt((p.get("today") or {}).get("total_twd"))),
        ("近 7 日", "NT$" + _nt(w.get("last7_total")) + "／日均 NT$" + _nt(w.get("last7_daily_avg"))),
        ("　DeepSeek", "NT$" + _nt(ds.get("total_twd")) + "／日均 NT$" + _nt(ds.get("avg_twd"))),
        ("　Gemini", "NT$" + _nt(ge.get("total_twd")) + "／日均 NT$" + _nt(ge.get("avg_twd"))),
        ("　免費入口", "NT$" + _nt(fr.get("total_twd")) + "／" + _nt(bd.get("free_calls")) + " 次呼叫"),
        ("DS 錢包", f"¥{wal.get('ds_balance_cny')}（≈NT${_nt(wal.get('ds_balance_twd'))}）｜剩 {wal.get('ds_days_left')} 天"),
        ("Gemini 錢包", f"NT${_nt(wal.get('gemini_balance_twd'))}｜剩 {wal.get('gemini_days_left')} 天"),
        ("CER 風控", f"今日 {cer.get('today')} 次｜近 7 日 {cer.get('last7_total')} 次"),
        ("風控外溢（推定）", "NT$" + _nt(cer.get("spillover_strict_twd"))),
        ("異常", f"{len(alerts)} 項"),
    ]
    tr = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return ('<section class="card"><h2>◆ 摘要<em>（靜態版；JS 可用時自動升級為完整圖表）</em></h2>'
            f'<table class="fb"><tbody>{tr}</tbody></table></section>')


def main() -> int:
    ap = argparse.ArgumentParser(description="產出 AI 費用頁（cost.html + cost_data.json）")
    ap.add_argument("--quiet", action="store_true", help="只產檔、不印摘要（cron 用）")
    a = ap.parse_args()

    d = payload()
    seed = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    html = (HTML_TPL.replace("__CSS__", CSS).replace("__JS__", JS).replace("__SEED__", seed)
            .replace("__FALLBACK__", static_fallback(d)))
    OUT_HTML.write_text(html, encoding="utf-8", newline="\n")
    OUT_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")

    if not a.quiet:
        w = d["week"]
        print(f"✅ {OUT_HTML.name}（{OUT_HTML.stat().st_size:,} bytes）＋ {OUT_JSON.name}"
              f"（{OUT_JSON.stat().st_size:,} bytes）")
        print(f"   近 7 日 NT${w['last7_total']}｜日均 NT${w['last7_daily_avg']}（{w['wow_pct']:+d}%）"
              f"｜DS NT${w['ds']}／Gemini NT${w['gemini']}／免費 NT${w['free']}｜異常 {len(d['alerts'])} 項")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
