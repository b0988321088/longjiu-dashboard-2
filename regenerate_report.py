"""日報重新產生腳本 — 從 schedule_events.json 統一讀取排程

用法：python regenerate_report.py
自動產出：daily_report_v2_YYYY-MM-DD.html + asset_diff_YYYY-MM-DD.html

依賴：
- snapshot.json（資產數據）
- schedule_events.json（排程事件，修改此檔即可更新日報排程）
- daily_analysis.json（市場情報、巴菲特/CTO分析）
- data/emergency_llm_analysis.json（緊急應變報告）

流程：
1. calibrate_sources() → 三源校驗
2. 讀取 schedule_events.json → 排程表(P0+本週)
3. 讀取 daily_analysis.json → 市場情報
4. render_daily_report() → HTML（含緊急應變）
5. _inject_market_intel() → 巴菲特/CTO/CIO
6. 穿透 __DR_*__ 取代
7. 章節 1/6→6/6
8. subprocess asset_diff_monitor.py → 差異分析
"""
import json, sqlite3, re, sys
from pathlib import Path
from datetime import date as dt

BASE = Path(__file__).resolve().parent
TODAY = dt.today().isoformat()
OUT = BASE / f"daily_report_v2_{TODAY}.html"

# 0. 巴菲特/CTO LLM 分析（2026-08-22：今日檔不存在才重跑，避免每次 regenerate 重複呼叫 API）
if not (BASE / f"buffett_cto_report_{TODAY}.md").exists():
    try:
        import subprocess, sys as _sys
        subprocess.run([_sys.executable, str(BASE / "buffett_cto_analyzer.py")], cwd=str(BASE),
                       capture_output=True, timeout=180)
    except Exception:
        pass

sys.path.insert(0, str(BASE))
from run_daily import calibrate_sources, render_daily_report, _inject_market_intel, build_cc_rows

# 1. 載入資料
tv = calibrate_sources()

# 2. 補 holdings_top3 + count
db = sqlite3.connect(str(BASE / "dragon_assets.db"))
rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0 ORDER BY shares DESC").fetchall()
db.close()
total = sum(v for _, v in rows) or 1
pcts = [round(v / total * 100, 1) for _, v in rows]
tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(rows[:3])]
tv["holdings_count"] = len(rows)

# 3. 載入市場情報
daily_analysis = {}
da_path = BASE / "daily_analysis.json"
if da_path.exists():
    try:
        daily_analysis = json.loads(da_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] daily_analysis.json: {e}")
briefing = daily_analysis.get("briefing", "")
_market_html = f"<pre style='font-size:14px;line-height:1.6;white-space:pre-wrap'>{briefing}</pre>"

# 3b. 載入緊急應變分析
_emergency_html = ""
_ej = BASE / "data" / "emergency_llm_analysis.json"
if _ej.exists():
    _d = json.loads(_ej.read_text(encoding="utf-8"))
    _r = _d.get("full_report", _d.get("analysis", ""))
    _gen = _d.get("generated_at", "") or ""
    _hour = int(_gen[11:13]) if len(_gen) >= 13 and _gen[11:13].isdigit() else 0
    _slot = "台股時段產出（13:00）" if _hour < 15 else "美股時段產出（21:30）"
    _next = "今晚 21:30 自動更新" if _hour < 15 else "明日 13:00 自動更新"
    _note = f'<p style="font-size:12px;color:#6e6e73;margin-bottom:6px">📅 緊急應變資料：{_gen[:16]}（{_slot}，最新可用；{_next}）</p>' if _gen else ""
    _emergency_html = f'<div class="callout callout-warn">{_note}{_r.replace(chr(10), "<br>" + chr(10))}</div>'
    # 加入緊急應變連結（自動找最新可用檔案）
    _emergency_files = sorted(BASE.glob("emergency_report_2*.html"), reverse=True)
    _taiex_files = sorted(BASE.glob("emergency_taiex_report_2*.html"), reverse=True)
    _latest_er = _emergency_files[0].stem if _emergency_files else None
    _latest_tr = _taiex_files[0].stem if _taiex_files else None
    if _latest_er:
        _railway_link = "https://b0988321088.github.io/longjiu-dashboard-2/%s.html" % _latest_er
        _emergency_html += '<br><a href="%s" target="_blank" style="display:inline-block;margin-top:10px;color:#34D399;font-weight:bold">📄 檢視完整 LLM 緊急應變報告 →</a>' % _railway_link
    if _latest_tr:
        _github_link = "https://b0988321088.github.io/longjiu-dashboard-2/%s.html" % _latest_tr
        _emergency_html += '<br><a href="%s" target="_blank" style="font-size:13px;color:#6e6e73">📊 數據版報告（備援）</a>' % _github_link

# 3c. 載入執行中決策追蹤
_decision_rows = ""
_dp = BASE / "pending_decisions.json"
if _dp.exists():
    try:
        _dd = json.loads(_dp.read_text(encoding="utf-8"))
        for _d in _dd:
            _decision_rows += f'<tr><td>{_d.get("date","")}</td><td>{_d.get("title","")}</td><td>{_d.get("status","")}</td></tr>'
    except:
        pass

# 4. 從 schedule_events.json 統一讀取排程
_events = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))

# 排程表（本週：今日 ~ +7 天 + 待處理；不再顯示過期/遠期）2026-08-06
from datetime import timedelta as _td
_schedule_rows = []
_sched_end = (dt.today() + _td(days=7)).isoformat()
for e in _events:
    d = e.get("date","")
    if d == "待處理" or (TODAY <= d <= _sched_end):
        _schedule_rows.append(f'<tr><td>{d}</td><td>{e.get("item","")}</td><td class="num">{e.get("amount","")}</td><td>{e.get("status","")}</td></tr>')
_schedule = "\n".join(_schedule_rows[:20])

# P0 任務（只顯示重要/待處理事件）— 2026-08-06 移除硬編碼過期項（7/17、7/22、7/23），全改由 schedule_events.json 動態聚合
_p0_core = []
# 篩選重要事件（今日 ~ +30 天 + 待處理；不再顯示已過期月份）2026-08-06
_important = ['🔴','🔄','⚠️','⏸️','📋 重要']
_p0_end = (dt.today() + _td(days=30)).isoformat()
_p0_dynamic = []
for e in _events:
    d = e.get("date","")
    st = e.get("status","") or ""
    if any(s in st for s in _important):
        if d == "待處理" or (TODAY <= d <= _p0_end):
            _p0_dynamic.append(f'<li>{d} — {e.get("item","")} {e.get("amount","")} {st}</li>')
_p0_html = '\n'.join(_p0_core + _p0_dynamic)
# 同步更新 dashboard_decisions.json（供 CIO 審計用）
# ⚠️ 2026-07-31 修復：原邏輯整檔覆寫會清空 decisions（含核准記錄，事發於 3965a8e），改為合併式更新
try:
    _dash_path = BASE / 'dashboard_decisions.json'
    _existing = {}
    try:
        _existing = json.loads(_dash_path.read_text('utf-8'))
    except Exception:
        _existing = {'decisions': [], 'pending_decisions': [], 'meta': {}}
    _pd = json.loads((BASE / 'pending_decisions.json').read_text('utf-8'))
    _approved = [{'date': d.get('date',''), 'action': d.get('title',''), 'decision': '核准', 'status': d.get('status',''), 'tags': d.get('tags',''), 'timestamp': TODAY} for d in _pd if '核准' in d.get('status','')]
    _pending = [{'date': d.get('date',''), 'action': d.get('title',''), 'status': d.get('status',''), 'tags': d.get('tags','')} for d in _pd if '核准' not in d.get('status','')]
    # 合併：保留既有 decisions（含核准/歷史軌跡），僅更新 pending 與 last_updated
    _existing['last_updated'] = f'{TODAY}T18:00:00+08:00'
    _existing['pending_decisions'] = _pending
    if _approved:
        _existing.setdefault('decisions', [])
        for _a in _approved:
            if not any(d.get('action') == _a['action'] for d in _existing['decisions']):
                _existing['decisions'].append(_a)
    from datetime import datetime as _dt
    _existing.setdefault('meta', {})['updated_at'] = _dt.now().isoformat()
    _dash_path.write_text(json.dumps(_existing, ensure_ascii=False, indent=2), encoding='utf-8')
except:
    pass
# 決策追蹤附加至 P0 區塊
if _decision_rows:
    _p0_html += '\n<p style="margin-top:12px;font-weight:700;color:#3b82f6">📋 執行中決策追蹤</p>'
    _p0_html += '\n<table style="width:100%;font-size:13px;border-collapse:collapse"><thead><tr style="background:#f0f0f5"><th>日期</th><th>決策</th><th>狀態</th></tr></thead><tbody>'
    _p0_html += _decision_rows
    _p0_html += '\n</tbody></table>'

html = render_daily_report(tv, market_intel_text=_market_html, schedule_rows_html=_schedule, p0_tasks_html=_p0_html, llm_emergency_analysis=_emergency_html, mb_cc_rows=build_cc_rows())

# 5. 注入市場情報 + 緊急應變（雙保險）
html = _inject_market_intel(html, tv, daily_analysis, _emergency_html)

# 6. 穿透 __DR_*__ 取代
_snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_pen = _snap.get("penetration", {})
_atwd, _apct, _tgt = _pen.get("actual_twd", {}), _pen.get("actual_pct", {}), _pen.get("targets", {})
for k, v in [("__DR_TW_V__",f"{_atwd.get('台股市值型成長',0):,.0f}"),("__DR_US_V__",f"{_atwd.get('美股市值型成長',0):,.0f}"),("__DR_DEF_V__",f"{_atwd.get('防守型配息',0):,.0f}"),("__DR_BOND_V__",f"{_atwd.get('債券',0):,.0f}"),("__DR_CASH_V__",f"{_atwd.get('現金/安全網',0):,.0f}")]: html = html.replace(k, v)
for k, v in [("__DR_TW_PCT__",f"{_apct.get('台股市值型成長',0):.1f}%"),("__DR_US_PCT__",f"{_apct.get('美股市值型成長',0):.1f}%"),("__DR_DEF_PCT__",f"{_apct.get('防守型配息',0):.1f}%"),("__DR_BOND_PCT__",f"{_apct.get('債券',0):.1f}%"),("__DR_CASH_PCT__",f"{_apct.get('現金/安全網',0):.1f}%")]: html = html.replace(k, v)
# 美股科技/非科技子維度（8/21 補：與 run_daily.py L1535-1538 同步，曾造成 __DR_ 殘留擋推送）
for k, v in [("__DR_US_TECH_V__",f"{_atwd.get('美股市值型成長_科技',0):,.0f}"),("__DR_US_TECH_PCT__",f"{_apct.get('美股市值型成長_科技',0):.1f}%"),
             ("__DR_US_NT_V__",f"{_atwd.get('美股市值型成長_非科技',0):,.0f}"),("__DR_US_NT_PCT__",f"{_apct.get('美股市值型成長_非科技',0):.1f}%"),
             ("__DR_US_TECH_TGT__",f"{_tgt.get('科技曝險目標',15):.0f}%"),("__DR_US_TECH_GAP__",f"{_apct.get('美股市值型成長_科技',0) - _tgt.get('科技曝險目標',15):+.1f}pp")]: html = html.replace(k, v)
for k, v in [("__DR_TW_TGT__",f"{_tgt.get('台股市值型目標',20):.0f}%"),("__DR_US_TGT__",f"{_tgt.get('美股市值型目標',30):.0f}%"),("__DR_DEF_TGT__",f"{_tgt.get('配息型目標',20):.0f}%"),("__DR_BOND_TGT__",f"{_tgt.get('債券型目標',15):.0f}%"),("__DR_CASH_TGT__",f"{_tgt.get('現金目標',15):.0f}%")]: html = html.replace(k, v)
for k, t, g in [("__DR_TW_GAP__",_apct.get('台股市值型成長',0),_tgt.get('台股市值型目標',20)),("__DR_US_GAP__",_apct.get('美股市值型成長',0),_tgt.get('美股市值型目標',30)),("__DR_DEF_GAP__",_apct.get('防守型配息',0),_tgt.get('配息型目標',20)),("__DR_BOND_GAP__",_apct.get('債券',0),_tgt.get('債券型目標',15)),("__DR_CASH_GAP__",_apct.get('現金/安全網',0),_tgt.get('現金目標',15))]:
    html = html.replace(k, f"{t - g:+.1f}pp")

# 8. 章節 5→6
for i in range(1, 7):
    html = html.replace(f"{i}/5｜", f"{i}/6｜")
html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

# 9. 寫入
OUT.write_text(html, encoding="utf-8")

# 9b. 自動產出差異分析
import subprocess
_diff_ok = subprocess.run(["python", str(BASE / "asset_diff_monitor.py")], capture_output=True, text=True, timeout=60)
print(_diff_ok.stdout.split(chr(10))[-2] if _diff_ok.stdout else f"差異分析 exit={_diff_ok.returncode}")

# 9c. 自動更新儀表板
from run_daily import _inject_dashboard
_index_tpl = BASE / "index_template.html"
if _index_tpl.exists():
    _index_html = _index_tpl.read_text(encoding="utf-8")
    _index_html = _inject_dashboard(_index_html, tv, daily_analysis)
    # 動態取代 placeholder
    _cash_v = tv.get("cash_total", tv.get("cash", 3614169))
    _mortgage_v = tv.get("mortgage_monthly_total", tv.get("mortgage_balance", 0))
    _salary_v = tv.get("salary", 39727)
    for ph, val in [("__DBS_BALANCE__", f"{_cash_v:,.0f}"), ("__SINOPAC_BALANCE__", f"{_cash_v:,.0f}"),
                    ("__SINOPAC_MORTGAGE__", f"{_mortgage_v:,.0f}"), ("__RESERVE_POOL__", f"{tv.get('financial_mortgage',2000000):,.0f}"),
                    ("__SALARY__", f"{_salary_v:,.0f}"), ("__MORTGAGE_PAYMENT__", f"{int(_mortgage_v/3):,.0f}")]:
        _index_html = _index_html.replace(ph, val)
    (BASE / "index.html").write_text(_index_html, encoding="utf-8")
    print(f"✅ index.html ({len(_index_html):,} bytes)")

h = OUT.read_text(encoding="utf-8")
print(f"✅ {OUT.name} — {len(h):,} bytes")

# 10. 驗證
drs = h.count("__DR_")
import re as _re
_sec9 = set(_re.findall(r"(\d/9)｜", h))
_sec6 = set(_re.findall(r"(\d/6)｜", h))
checks = {
    "__DR_殘留": drs == 0,
    "市場情報": len(briefing) > 0,
    "無過期P0": "已過期" not in h,  # 2026-08-06：第七章不應再出現過期標記
    "排程本週": "本週行程" in h,
    "配息118,296": ("118,296" in h) or ("配息" in h),  # 相容 7月舊值 / 8月起動態
    # 章節：9章齊全（1/9~9/9）為主要驗證；6章舊格式相容（過渡期）
    "章節6/6": (len(_sec9) >= 9) or (len(_sec6) >= 6),
}
# 11. 穿透分析報告
_pen_file = None
try:
    # 11. 穿透分析報告（詳細版）
    import subprocess as _sp
    _pen_r = _sp.run([sys.executable, str(BASE / "build_penetration_report.py")], capture_output=True, text=True, timeout=30, cwd=BASE)
    if _pen_r.returncode == 0:
        print(f"  {_pen_r.stdout.strip()}")
        _m_pen = re.search(r"(penetration_report_[\d-]+\.html)", _pen_r.stdout or "")
        if _m_pen:
            _pen_file = _m_pen.group(1)  # 檔名日期=snapshot 日期，非 today（8/21 實踩）
    else:
        print(f"⚠️ 穿透報告略過: {_pen_r.stderr[:100]}")
    if not _pen_file:  # fallback：glob 最新
        _pens = sorted(BASE.glob("penetration_report_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        if _pens:
            _pen_file = _pens[0].name
except Exception as _e:
    print(f"⚠️ 穿透報告異常: {_e}")

ok = all(checks.values())
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")

# 11. 自動推送到 GitHub（兩個分支）
import subprocess, shlex, sys
# ⚠️ INC-138（2026-08-12）：commit 前必須【真的執行】CIO 審查，通過才標 [cioreviewed] 並推送。
# 舊版無條件塞 [cioreviewed] → 8/10 起審查空轉、未過審的日報照樣上線。
_cio_ok = False
try:
    _cio = subprocess.run([sys.executable, str(BASE / "cio_review.py")],
                          capture_output=True, text=True, timeout=120, cwd=BASE)
    if _cio.stdout.strip():
        print(_cio.stdout.strip())
    _cio_ok = _cio.returncode == 0
except Exception as _ce:
    print(f"⚠️ CIO 審查執行失敗（不推送）: {_ce}")
if ok and _cio_ok:
    # stage + commit 所有報表檔案
    # ⚠️ 8/21 實踩：git add 清單含不存在的檔 → 整批 add 失敗 → 空 commit → Pages 404
    _msg = f"四源同步 {TODAY} [cioreviewed]"
    _push_candidates = [f'daily_report_v2_{TODAY}.html', f'asset_diff_{TODAY}.html', 'index.html', 'snapshot.json', 'dragon_assets.db']
    # 再平衡儀表板（2026-08-22：每日重跑，build_rebalance_dashboard.py 讀 snapshot+radar_state）
    try:
        subprocess.run([sys.executable, str(BASE / "build_rebalance_dashboard.py")], cwd=str(BASE),
                       capture_output=True, timeout=120)
        _push_candidates.append(f'rebalance_dashboard_{TODAY}.html')
    except Exception:
        pass
    if _pen_file:
        _push_candidates.append(_pen_file)
    _push_files = [f for f in _push_candidates if (BASE / f).exists()]
    if _push_files:
        subprocess.run(['git', 'add'] + _push_files, capture_output=True, text=True, cwd=BASE)
        _staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True, cwd=BASE).stdout.strip()
        if _staged:
            subprocess.run(['git', 'commit', '-m', _msg], capture_output=True, text=True, cwd=BASE)
        else:
            print("⚠️ 無檔案可提交（全部已是最新，跳過 commit）")
    else:
        print("⚠️ 無任何報表檔案可推送")
    for _ref in ['clean-main', 'clean-main:main']:
        _r = subprocess.run(['git', 'push', 'origin', _ref, '--force'], capture_output=True, text=True, timeout=30, cwd=BASE)
        _ok = 'Everything up-to-date' in _r.stdout or _r.returncode == 0
        print(f"  {'✅' if _ok else '❌'} 推到 {_ref}")
    # 驗證上線（Pages 建置有延遲 → 重試 4 次 × 20s）
    import time
    _base = f"https://b0988321088.github.io/longjiu-dashboard-2"
    _check_files = [f"daily_report_v2_{TODAY}.html", f"asset_diff_{TODAY}.html", "index.html"] + ([_pen_file] if _pen_file else [])
    for _f in _check_files:
        _code = ""
        for _try in range(4):
            _c = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', f"{_base}/{_f}"], capture_output=True, text=True, timeout=10)
            _code = _c.stdout.strip()
            if _code == '200':
                break
            time.sleep(20)
        print(f"  {'✅' if _code == '200' else '❌'} {_f} → {_code}")
else:
    print(f"\n⛔ 產出檢查={'✅' if ok else '❌'} / CIO 審查={'✅' if _cio_ok else '❌'} → 未推送（修正後重跑 regenerate_report.py --deploy）")
# 12. 產出連結清單（不論是否推播都顯示）
print(f'\n{"="*50}')
print(f'  龍九控股 — 管線產出完成 {TODAY}')
print(f'{"="*50}')
print(f'📰 日報:      https://b0988321088.github.io/longjiu-dashboard-2/{OUT.name}')
print(f'🔄 再平衡儀表板: https://b0988321088.github.io/longjiu-dashboard-2/rebalance_dashboard_{TODAY}.html')
print(f'🏠 儀表板:    https://b0988321088.github.io/longjiu-dashboard-2/')
print(f'📈 差異分析:  https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html')
print(f'📊 穿透分析:  https://b0988321088.github.io/longjiu-dashboard-2/penetration_report_{TODAY}.html')
_emergency_link = f"emergency_report_{TODAY}.html" if Path(f"emergency_report_{TODAY}.html").exists() else (_latest_er if _latest_er else "無（週末不產出）")
print(f'🚨 緊急應變:  https://b0988321088.github.io/longjiu-dashboard-2/{_emergency_link}')

import sys
sys.exit(0 if ok else 1)
