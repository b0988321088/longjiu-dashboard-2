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
import json, sqlite3, re, sys, os
from pathlib import Path
from datetime import date as dt

BASE = Path(__file__).resolve().parent
TODAY = dt.today().isoformat()
OUT = BASE / f"daily_report_v2_{TODAY}.html"
CNY_TWD = 4.73  # 2026-09-14 使用者確認（200 CNY≈944 TWD）；Yahoo CNYTWD 4.734
_NO_PUSH = "--no-push" in sys.argv  # 2026-09-17 INC-210：核准前本機產出用（不 commit/push）

# ============ 0a. 日期滾動（INC-210，2026-09-17） ============
# 症狀：09-17 07:00 晨間產線產出的日報/差異分析標成 09-16（daily_report_v2_2026-09-17.html
# 內為 <title>龍九控股日報 2026-09-16</title>、asset_diff_2026-09-17.html 內 title 09-16）。
# 根因：晨間順序 = regenerate_report（先產日報/差異）→ build_penetration_report（才把
# snapshot.date 滾到當日，INC-187）→ 產出當下 snapshot.date 還是前一天，且 DB 尚無當日列
# （DB 當日列原由 22:00 four_source_sync 寫入）→ run_daily.TODAY（= snapshot.date）與
# asset_diff_monitor 的 DB fallback（最新資料日）都取到前一天。
# 修法：渲染前先滾 snapshot.date 並補當日 DB 列（assets.date 為 PRIMARY KEY，INSERT OR REPLACE
# 冪等；公式與 four_source_sync Step 2 相同），與 build_penetration_report / sync_all v3 的
# `snap["date"] = today` 語意一致。必須在 import run_daily 之前執行 —— run_daily.TODAY 是
# import 時定值的模組常數。
# ⚠️ 本檔只能在模組層被呼叫的副作用（_roll_day_to_today）下「當 script 執行」：
#    import regenerate_report 會連帶寫 snapshot.json 與 DB（2026-09-17 審查指出，現況全 repo
#    無任何 import 本檔，呼叫端皆 subprocess/run_step）。要 import 請先改造此段。
# 公式與 four_source_sync.py Step 2（L138-158）逐欄相同 → 日後該處若增減元件，這裡要同步
#    （守衛 _tot != _snap_tot 會在漂移時拒寫而非寫錯，屬 fail-safe）。
def _roll_day_to_today(_today: str) -> None:
    _sp = BASE / "snapshot.json"
    try:
        _s = json.loads(_sp.read_text(encoding="utf-8"))
    except Exception as _e:
        print(f"⚠️ INC-210 日期滾動略過（snapshot 讀取失敗）: {_e}")
        return
    _prev = str(_s.get("date") or "")
    if _prev != _today:
        _s["date"] = _today
        _sp.write_text(json.dumps(_s, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"🗓️ INC-210 snapshot.date {_prev or '?'} → {_today}（報告日期對齊當日）")
    # 補當日 DB 列（缺列時差異分析會拿「最新資料日」當標籤 → 當日報表標成前一天）
    _cash = _s.get("real_liquid_assets", 0) or 0
    _sec = _s.get("securities_total_market_value", 0) or 0
    _ins = _s.get("insurance_total", 0) or ((_s.get("allianz_combined", 0) or 0)
                                            + (_s.get("firstjin_fl65_current_value", 0) or 0))
    _fund = _s.get("fund_market_value", 0) or 0
    _tot = _cash + _sec + _ins + _fund
    _snap_tot = _s.get("total_assets", 0) or 0
    if min(_cash, _sec, _ins, _fund) <= 0 or _tot != _snap_tot:
        print(f"⚠️ INC-210 今日 DB 列未補（組件不完整：現金{_cash:,} 證券{_sec:,} 保單{_ins:,} "
              f"基金{_fund:,} 合計{_tot:,} vs snapshot {_snap_tot:,}）")
        return
    try:
        _conn = sqlite3.connect(str(BASE / "dragon_assets.db"))
        _conn.execute(
            "INSERT OR REPLACE INTO assets "
            "(date, cash_total, bonds, securities, insurance, funds, real_estate, total_assets, total_liabilities) "
            "VALUES (?,?,0,?,?,?,0,?,?)",
            (_today, _cash, _sec, _ins, _fund, _tot, _s.get("total_liabilities", 0) or 0))
        _conn.commit()
        _conn.close()
        print(f"🗓️ INC-210 DB 補列 {_today}：資產 {_tot:,}（差異分析基準對齊當日）")
    except Exception as _e:
        print(f"⚠️ INC-210 DB 補列失敗（不擋產線）: {_e}")


# ============ 0-pre. producer 邊界 before-snapshot（2026-10-08 治理 PEND-20261008-01 Phase A）============
# 規則：本輪產物（produced）必須由「執行前後狀態差」證明 —— produced = after − before。
#   呼叫端自宣告的候選清單（_push_candidates／index.html 連結）≠ 本輪真的產生。
#   邊界：只在本檔（regenerate）producer 邊界實作；不得改 dirty_gate.py／auto_push.py（Phase B 才抽共用）。
# ⚠️ 已知殘留風險（CIO 對抗審查 2026-10-08，required_fixes 已收斂）：
#   ① 讀取失敗語意已由「略過」改為 _UNREADABLE 哨兵 → 該檔一律排除（fail-closed）；不再是 fail-open。
#   ② before/after 是「整輪多分鐘」的單一內容差窗口 → 期間任何並行寫入者（他支 cron／人工編輯）
#      對候選檔的變更仍會被歸因為本 producer（僅印出警示，未縮窗）。
#   ③ 不在 _SNAP_EXT 或 > _SNAP_MAX 的候選檔無法快照 → 一律排除（under-push，不洩漏）；會示警。
import hashlib as _hl

_SNAP_EXT = {'.html', '.json', '.md', '.png', '.db', '.jsonl', '.csv', '.svg', '.txt', '.xml',
             '.webp', '.jpg', '.jpeg', '.gif', '.ico', '.pdf'}
_SNAP_MAX = 20 * 1024 * 1024
_UNREADABLE = "<UNREADABLE>"   # 存在但不可快照（讀取失敗／過大）→ 一律不得視為本輪產物


def _snap_root(_base):
    """根目錄候選檔的內容指紋；**存在卻無法快照者記為 _UNREADABLE（不是略過）**。"""
    _d = {}
    for _p in _base.iterdir():
        try:
            if not _p.is_file() or _p.suffix.lower() not in _SNAP_EXT:
                continue
            if _p.stat().st_size > _SNAP_MAX:
                _d[_p.name] = _UNREADABLE          # 過大 → 標記（不可快照）
                continue
            _d[_p.name] = _hl.sha256(_p.read_bytes()).hexdigest()
        except Exception:
            try:
                _d[_p.name] = _UNREADABLE          # 存在但讀不到 → 標記（fail-closed）
            except Exception:
                pass
    return _d


def _is_produced(_f, _before, _after):
    """本輪是否真的產生 _f。after 必須可靠；before 不可靠（_UNREADABLE）→ False（fail-closed）。"""
    _a = _after.get(_f)
    if _a is None or _a == _UNREADABLE:
        return False
    if _f not in _before:
        return True                                # 本輪新增
    if _before[_f] == _UNREADABLE:
        return False                               # before 不可信 → 不得算本輪產物
    return _before[_f] != _a


def _produced_only(_cands, _before, _after):
    """只保留本輪真正產生的檔（produced = after − before）；回傳 (produced, excluded)。"""
    _keep = [f for f in _cands if _is_produced(f, _before, _after)]
    _drop = [f for f in _cands if f not in _keep]
    return _keep, _drop


_BEFORE = _snap_root(BASE)
print(f"🧾 producer 邊界 before-snapshot：{len(_BEFORE)} 檔（本輪產物須由 before/after 差異證明）")

_roll_day_to_today(TODAY)

# 0. 巴菲特/CTO LLM 分析（2026-08-22：今日檔不存在才重跑，避免每次 regenerate 重複呼叫 API）
# 2026-08-28：--skip-llm = 跳過 LLM 分析（台股 13:00 緊急應變用 — 盤中不需要重算早上已算的巴菲特/CTO）
if "--skip-llm" not in sys.argv and not (BASE / f"buffett_cto_report_{TODAY}.md").exists():
    try:
        import subprocess, sys as _sys
        subprocess.run([_sys.executable, str(BASE / "buffett_cto_analyzer.py")], cwd=str(BASE),
                       capture_output=True, timeout=180)
    except Exception:
        pass

sys.path.insert(0, str(BASE))
from run_daily import calibrate_sources, render_daily_report, _inject_market_intel, build_cc_rows, close_html_tail

# 1. 載入資料
tv = calibrate_sources()

# 2. 補 holdings_top3 + count（2026-08-23 修正：按市值排序+市值佔比，與 run_daily.py L1717 一致；
#    原 ORDER BY shares 用股數 → 00983D 20,000股誤列第一 18.3%（8/22-23 日報實踩））
db = sqlite3.connect(str(BASE / "dragon_assets.db"))
rows = db.execute("SELECT ticker, shares FROM holdings WHERE shares > 0").fetchall()
db.close()
# 市值 = shares × snapshot 現價（DB cost_price 是成本價非現價）
try:
    _snap_h = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")).get("securities", {}).get("holdings", [])
    _snap_px = {_x.get("ticker"): _x.get("price", 0) for _x in _snap_h}
except Exception:
    _snap_px = {}
_mv = [(r[0], r[1] * _snap_px.get(r[0], 0)) for r in rows]
_mv.sort(key=lambda x: x[1], reverse=True)
_stotal = sum(v for _, v in _mv) or 1
pcts = [round(v / _stotal * 100, 1) for _, v in _mv]
tv["holdings_top3"] = [(r[0], pcts[i]) for i, r in enumerate(_mv[:3])]
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
# 2026-09-12 修：3/9 市場情報只有自動行情 + 賣出訊號（週六無情報同步 → 內容過少）。
# 補上 compile_intel 的濃縮情報（3-5 條・含持倉關聯）— 來源 daily_condensed_intel_<today>.json。
try:
    _ci_p = BASE / f"daily_condensed_intel_{TODAY}.json"
    if _ci_p.exists():
        _ci = json.loads(_ci_p.read_text(encoding="utf-8"))
        if _ci and "【情報重點（含持倉關聯）】" not in briefing:
            _ci_lines = ["", "【情報重點（含持倉關聯）】"]
            for _x in _ci[:5]:
                _imp = (f"（影響：{'/'.join(_x.get('holdings_impact') or [])}）"
                        if _x.get("holdings_impact") else "")
                _ci_lines.append(
                    f"{_x.get('signal_level','')} {_x.get('title','')}：{_x.get('description','')}{_imp}")
            briefing = (briefing.rstrip() + "\n" + "\n".join(_ci_lines)) if briefing.strip() else "\n".join(_ci_lines[1:])
except Exception as _e:
    print(f"[WARN] condensed intel 注入失敗：{_e}")
_market_html = f"<pre style='font-size:14px;line-height:1.6;white-space:pre-wrap'>{briefing}</pre>"

# 3b. 緊急應變分析（INC-291：唯一實作＝daily_report_assembly.build_emergency_block）
#   canonical 行為＝本檔 2026-10-09 前的已上線實作（refresh_stale_amounts 舊值覆蓋／as_of
#   `_stale_badge`／`<br>` 換行／2 條連結）；run_daily.py main() 亦呼叫同一函式
#   → 兩個 producer 不再各自組裝。連結 `.html.html` 重綴缺陷已於 INC-294 修正（見共用模組 docstring）。
from daily_report_assembly import build_emergency_block as _asm_em
_snap_em = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_emergency_html = _asm_em(BASE, _snap_em, TODAY)

# 3b2. Pending 期限 schema 自癒（2026-10-05 PEND-20261005-03）
# 為何在產出之前：10/05 07:00 實例是「新增卡漏 needs_due_date」→ 產線末端 check_dividend_caliber
# 亮紅 → Task1+2 驗證器第 5 類擋關 → 日報產出但**不推送**（連 3 次失敗、且擋在花完成本之後）。
# 這裡先用唯一計算層（pending_engine.normalize_cards）做無損自癒並大聲列出改了什麼；
# 「不可無損推得」的（due_date 有值但來源非既有文字＝推算）刻意不自癒，仍交回閘門 fail-closed。
# 本檔已在推送清單內（_push_candidates），自癒後的內容會隨本次四源同步一併提交。
_dp_seed = BASE / "pending_decisions.json"
if _dp_seed.exists():
    try:
        import pending_engine as _pe_seed
        _seed_items = json.loads(_dp_seed.read_text(encoding="utf-8"))
        _seed_fixes = _pe_seed.normalize_cards(_seed_items)
        if _seed_fixes:
            _dp_seed.write_text(json.dumps(_seed_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  🔧 Pending 期限 schema 自癒 {len(_seed_fixes)} 筆：")
            for _sf in _seed_fixes[:12]:
                print("     - " + _sf)
    except Exception as _e_seed:
        print(f"[WARN] Pending schema 自癒未執行（不阻擋；閘門仍會擋）：{_e_seed}")

# 3c-4. 本週行程表／P0 任務／「執行中決策追蹤」（INC-289：唯一實作＝daily_report_assembly）
#   canonical 行為＝2026-10-07 前本檔的已上線實作（維持檔案順序、缺口欄 pp、含決策追蹤章）；
#   run_daily.py main() 亦呼叫同一組函式 → 兩個 producer 不再各自實作、不再產出不同版本。
from daily_report_assembly import build_schedule_rows as _asm_sched, build_p0_tasks_html as _asm_p0
_events = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
_pending = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
_snap_asm = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
_schedule = _asm_sched(_events, TODAY)
_p0_html = _asm_p0(_events, _pending, _snap_asm, TODAY)
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

html = render_daily_report(tv, market_intel_text=_market_html, schedule_rows_html=_schedule, p0_tasks_html=_p0_html, llm_emergency_analysis=_emergency_html, mb_cc_rows=build_cc_rows())

# 5. 注入市場情報 + 緊急應變（雙保險）
html = _inject_market_intel(html, tv, daily_analysis, _emergency_html)

# 6. 穿透 __DR_*__ 取代（INC-289：唯一實作＝daily_report_assembly.substitute_dr_tokens）
#   2026-10-07 前此處為本檔私有實作，與 run_daily.py main() 的另一份私有實作分歧
#   （缺口欄 pp vs TWD 金額）→ 已收斂；canonical 口徑＝pp。
from daily_report_assembly import substitute_dr_tokens as _asm_dr
_snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
html = _asm_dr(html, _snap.get("penetration", {}))

# 8. 章節 5→6
for i in range(1, 7):
    html = html.replace(f"{i}/5｜", f"{i}/6｜")
html = html.replace("5/6｜投資決策框架", "6/6｜投資決策框架")

# 8b. DS 成本燈號注入（2026-08-27：成本可視化，🟢≤10 / 🟡10-20 / 🔴>20 CNY）
try:
    _dc = daily_analysis.get("deepseek_cost", {})
    _bal = float(_dc.get("balance", 0) or 0)
    _day = float(_dc.get("daily_cost", 0) or 0)
    _light = "🟢" if _day <= 10 else ("🟡" if _day <= 20 else "🔴")
    _cost_html = (
        f'<div style="margin:14px 0;padding:10px 14px;border-radius:10px;background:#f8fafc;'
        f'border:1px solid #e2e8f0;font-size:13px;color:#475569">'
        f'☕ <b>DS 成本</b> {_light} 今日 {_day:.1f} CNY｜餘額 {_bal:.1f} CNY（≈{_bal*CNY_TWD:.0f} 台幣）'
        f'<span style="color:#94a3b8">（月預算上限 400 CNY）</span></div>')
    if "</body>" in html:
        html = html.replace("</body>", _cost_html + "</body>")
    else:
        html += _cost_html
except Exception:
    pass

# 9. 寫入（INC-199：附加區塊原本落在 </body></html> 之後 → 寫檔前收斂回 </body> 之前）
# P0-1（2026-09-30）：日報是「現況報告」→ 寫檔前最終覆蓋清償前舊金額。
# 名單只含唯一指向舊值的金額（質押借款 5,900,000 不在其中，不會誤傷），
# 涵蓋 emergency 內文／決策追蹤／工作日誌等所有注入路徑。
try:
    from sot_targets import refresh_stale_amounts as _refresh_out
    html = _refresh_out(html, json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")))
except Exception as _e_out:
    print(f"[WARN] P0-1 日報最終舊值覆蓋失敗：{_e_out}")
OUT.write_text(close_html_tail(html), encoding="utf-8")

# 9a. 淨資產拆解自動更新（2026-09-03：儀表板 net_worth_weekly_breakdown 從 DB 真值算，
#     冪等 — 已是最新窗口即略過；週五深度審查 LLM 覆核可再細分成本）
try:
    import subprocess as _sp9a
    _nw = _sp9a.run([sys.executable, str(BASE / "weekly_nw_breakdown.py")], cwd=BASE,
                    capture_output=True, text=True, timeout=60)
    if _nw.stdout.strip():
        print("📡 " + _nw.stdout.strip().splitlines()[-1])
except Exception as _e9a:
    print(f"⚠️ 淨資產拆解略過（不擋管線）: {_e9a}")

# 9b. 自動產出差異分析
import subprocess
_diff_ok = subprocess.run([sys.executable, str(BASE / "asset_diff_monitor.py")], cwd=BASE, capture_output=True, text=True, timeout=120)
if _diff_ok.returncode != 0:
    # 2026-09-10：差異分析在管線內偶發 exit=1（stdout/stderr 皆空；單獨執行 RC=0）
    # → 自動重試一次，確保每次管線都產出當日差異分析，不留舊檔
    print(f"⏳ 差異分析 exit={_diff_ok.returncode} → 自動重試一次")
    _diff_ok = subprocess.run([sys.executable, str(BASE / "asset_diff_monitor.py")], cwd=BASE, capture_output=True, text=True, timeout=120)
print(_diff_ok.stdout.split(chr(10))[-2] if _diff_ok.stdout else f"差異分析 exit={_diff_ok.returncode}")
if _diff_ok.returncode != 0:
    print("  ⚠️ 差異分析重試仍失敗（改用既有檔案，請人工確認 asset_diff_" + TODAY + ".html）")

# 9c. 自動更新儀表板（2026-08-27 根治：統一呼叫 build_dashboard.py，舊邏輯漏連結佔位符）
import subprocess as _sp9c
# 9c0. AI 費用頁（2026-09-22 新增）：cost.html + cost_data.json，單一真值 data/ai_cost_daily.jsonl
#      放在 build_dashboard 之前 —— 連結刷新會讀實際存在的檔，先產出再刷連結才不會指向舊狀態。
try:
    _r9c0 = _sp9c.run([sys.executable, str(BASE / "build_cost_report.py"), "--quiet"], cwd=BASE,
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if _r9c0.returncode != 0:
        print("  ⚠️ AI 費用頁產出失敗（不影響日報）：" + (_r9c0.stderr or "").strip()[:160])
except Exception as _e9c0:
    print(f"  ⚠️ AI 費用頁產出異常（不影響日報）: {_e9c0}")
# 9c1. 本月績效頁（2026-09-22 新增）：mtd_performance.html + mtd_data.json
#      口徑重用 build_investment_performance.py（同一套四段式），按鈕 __MTD_PAGE__ 指向它。
try:
    _r9c1 = _sp9c.run([sys.executable, str(BASE / "build_mtd_report.py"), "--quiet"], cwd=BASE,
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if _r9c1.returncode != 0:
        print("  ⚠️ 本月績效頁產出失敗（不影響日報）：" + (_r9c1.stderr or "").strip()[:160])
except Exception as _e9c1:
    print(f"  ⚠️ 本月績效頁產出異常（不影響日報）: {_e9c1}")
# 9c2. 投資績效｜月度比較（2026-10-03 新增）：performance_monthly.html
#      口徑＝performance_core.monthly_history()（唯一計算層），按鈕 __PERF_MONTHLY__ 指向它。
try:
    _r9c2 = _sp9c.run([sys.executable, str(BASE / "build_performance_monthly.py")], cwd=BASE,
                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if _r9c2.returncode != 0:
        print("  ⚠️ 投資績效月度比較產出失敗（不影響日報）：" + (_r9c2.stderr or "").strip()[:160])
except Exception as _e9c2:
    print(f"  ⚠️ 投資績效月度比較產出異常（不影響日報）: {_e9c2}")
_r9c = _sp9c.run([sys.executable, str(BASE / "build_dashboard.py")], cwd=BASE,
                 capture_output=True, text=True, timeout=120)
if _r9c.stdout:
    print(_r9c.stdout.strip().splitlines()[-1] if _r9c.stdout.strip() else "✅ index.html")
    # 2026-08-23：刷新重要連結區（週報/月報/緊急/巴菲特/圖表指向最新檔，避免 __TODAY__ 壞連結；舊檔保留）
    _lk = subprocess.run([sys.executable, str(BASE / "update_dashboard_links.py")], capture_output=True, text=True, timeout=30)
    if _lk.stdout.strip():
        print(_lk.stdout.strip().splitlines()[-1])
    # 9c2. 儀表板同步檢查（2026-09-01：產出後自動驗證無舊值/佔位符/月份寫死 → 一次更新全同步）
    # 2026-09-23（INC-240）：帶 LJ_PREPUSH=1 —— commit 前「今天的檔還沒進版控」是必然，
    # 不該當失敗（每天自我誤報）；真 404 改由推送後 check_dashboard_sync.py --post-push 驗。
    _sync = subprocess.run([sys.executable, str(BASE / "check_dashboard_sync.py")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=120, env={**os.environ, "LJ_PREPUSH": "1"})
    if _sync.returncode == 0:
        for _l in (_sync.stdout or "").strip().splitlines():
            print("  " + _l.strip())
    else:
        print("⚠️ 儀表板同步檢查 FAIL（檢查 index.html 舊值/佔位符）:")
        for _l in (_sync.stdout or "").strip().splitlines():
            print("  " + _l.strip())

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
# 穿透報告連結（2026-08-22 修正：檔名=snapshot 日期非 today，__PEN_REPORT__ 用實際最新檔名）
if _pen_file:
    try:
        _idx_html = (BASE / "index.html").read_text(encoding="utf-8").replace("__PEN_REPORT__", _pen_file)
        (BASE / "index.html").write_text(_idx_html, encoding="utf-8")
    except Exception:
        pass
# 緊急應變連結（2026-08-22 修正：週末/例假日不產出 → 一律 glob 最新，避免 __TODAY__ 404）
try:
    _latest_er = sorted(BASE.glob("emergency_report_2*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    _er_name = _latest_er[0].name if _latest_er else f"emergency_report_{TODAY}.html"
    _idx_html2 = (BASE / "index.html").read_text(encoding="utf-8").replace("__EMERGENCY_REPORT__", _er_name)
    (BASE / "index.html").write_text(_idx_html2, encoding="utf-8")
except Exception:
    pass

ok = all(checks.values())
for k, v in checks.items():
    print(f"  {'✅' if v else '❌'} {k}")

# 11. 自動推送到 GitHub（兩個分支）
import subprocess, sys
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
_pages_ok = True  # 2026-09-23 INC-240：推送後線上連結驗證（--post-push）結果；False → 本次不視為成功
_gate_ok = True   # 2026-10-03：自動化防守閘門（performance_monthly 頁面數字 vs performance_core）；False → 阻擋推送
if _NO_PUSH:
    # INC-210：核准前本機產出（交付鐵則：改完先傳本地檔案，使用者說「推」才 push）
    print("\n🧪 --no-push：本機檔案已產出，略過 commit/push（核准後再跑一次不帶此參數）")
elif ok and _cio_ok:
    # stage + commit 所有報表檔案
    # ⚠️ 8/21 實踩：git add 清單含不存在的檔 → 整批 add 失敗 → 空 commit → Pages 404
    _msg = f"四源同步 {TODAY}"
    _push_candidates = [f'daily_report_v2_{TODAY}.html', f'asset_diff_{TODAY}.html', 'index.html', 'snapshot.json', 'dragon_assets.db',
                        # 2026-09-13：補齊儀表板會連到的今日產物（血淚：buffett_cto_report_{TODAY}.md 不在清單 → Pages 404「連結失效」）
                        f'buffett_cto_report_{TODAY}.md', f'risk_factor_penetration_{TODAY}.png', f'macro_regime_{TODAY}.json',
                        # 2026-10-08 治理（PEND-20261008-01｜C 統一卡＋A 最小止血）：
                        #   移除 5 個「本檔只讀不寫」的檔出本輪產物清單 —— work_log.json／pending_decisions.json／
                        #   schedule_events.json／radar_state.json／us30y_state.json。它們過去被宣告為本輪產物 →
                        #   dirty_gate allow=produced → V8「scope 內 dirty 必須全部 stage」→ 把當時尚未提交的
                        #   working-tree 編輯一起 commit+push（2026-10-08 19:04 實證：掃入結案歸檔中的
                        #   pending_decisions.json＋work_log.json）。只讀不寫者不得進 produced；其變更由各自
                        #   producer 負責推送（us30y_state.json 之 producer＝us30y_monitor.py:109；regenerate 呼叫鏈
                        #   僅 buffett_cto_analyzer／build_rebalance_dashboard 讀取，無任何寫入）。
                        'cio_review.json', 'dashboard_decisions.json',
                        'grand_pivot_deck.html',
                        # 2026-09-22：AI 費用頁（固定檔名，按鈕 __COST_PAGE__ 指向它）
                        'cost.html', 'cost_data.json',
                        # 2026-09-22：本月績效頁（固定檔名，按鈕 __MTD_PAGE__ 指向它）
                        'mtd_performance.html', 'mtd_data.json',
                        # 2026-10-03：投資績效｜月度比較（固定檔名，按鈕 __PERF_MONTHLY__ 指向它）
                        'performance_monthly.html']
    # 再平衡儀表板（2026-08-22：每日重跑，build_rebalance_dashboard.py 讀 snapshot+radar_state）
    try:
        subprocess.run([sys.executable, str(BASE / "build_rebalance_dashboard.py")], cwd=str(BASE),
                       capture_output=True, timeout=120)
        _push_candidates.append(f'rebalance_dashboard_{TODAY}.html')
        _push_candidates.append(f'rebalance_summary_{TODAY}.md')
        _push_candidates.append(f'industry_penetration_{TODAY}.png')
    except Exception:
        pass
    # 9c3. 收尾重刷連結（2026-09-22 根因修正）
    #      根因：步驟 9c 的 update_dashboard_links.py 跑在 #11（穿透報告）與上面
    #      build_rebalance_dashboard（再平衡儀表板／產業穿透 PNG）**之前** →
    #      這幾顆按鈕每天必然落後一天，不是「忘了手動改」。
    #      在全部產出者跑完、組 _push_files 之前再刷一次，並複驗同步檢查。
    try:
        _lk2 = subprocess.run([sys.executable, str(BASE / "update_dashboard_links.py")],
                              capture_output=True, text=True, timeout=30, cwd=str(BASE))
        _lk2_out = (_lk2.stdout or "").strip().splitlines()
        if _lk2_out:
            print("  🔗 " + _lk2_out[-1])
        _sync2 = subprocess.run([sys.executable, str(BASE / "check_dashboard_sync.py")],
                                capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=120, cwd=str(BASE), env={**os.environ, "LJ_PREPUSH": "1"})
        if _sync2.returncode != 0:
            print("  ⚠️ 收尾同步檢查 FAIL：")
            for _l in (_sync2.stdout or "").strip().splitlines():
                print("    " + _l.strip())
    except Exception as _e:
        print(f"  ⚠️ 收尾重刷連結失敗（不影響本次產出）：{_e}")
    if _pen_file:
        _push_candidates.append(_pen_file)
    # 2026-10-08 治理（PEND-20261008-01 Phase A）：commit scope 只收「本輪真正產生」的檔。
    #   produced = after − before（內容指紋差）。既有 dirty（使用者／他班未提交編輯）不得因
    #   出現在候選清單、或「被 index.html 連結」而進 commit —— 一次封住 Vector 1（靜態 over-declare）
    #   與 Vector 2（動態 dirty-link 掃入）。呼叫端宣告 ≠ 本輪產物。
    #   註：本過濾不宣稱「絕對 fail-closed」；殘留風險（並行寫入歸因、不可快照檔 under-push）見檔頭警示。
    _after = _snap_root(BASE)
    _snap_ok = bool(_BEFORE) and bool(_after)
    if not _snap_ok:
        # fail-closed：快照不完整時無法以 before/after 差異證明「本輪產物」→ 一律不推送。
        print("  ⛔ producer 邊界快照不完整（before/after 任一為空）→ 無法證明本輪產物，本次不推送（fail-closed）")
        _push_files = []
    else:
        _cands = [f for f in _push_candidates if (BASE / f).exists()]
        _push_files, _excluded = _produced_only(_cands, _BEFORE, _after)
        _unsnap = [f for f in _cands if f not in _BEFORE and f not in _after]
        if _unsnap:
            print(f"  ⚠️ 候選檔無法快照（副檔名不在 _SNAP_EXT 或過大）→ 已排除，請確認非本輪產物: {', '.join(sorted(_unsnap))}")
        if _excluded:
            print(f"  🚫 非本輪產物，排除 {len(_excluded)} 檔（既有 dirty 不得進 commit）：{', '.join(sorted(_excluded))}")
        if _push_files:
            print(f"  ✅ 本輪產物 {len(_push_files)} 檔進 commit scope：{', '.join(sorted(_push_files))}")
    # 2026-09-13：再掃 index.html 的所有本機連結補推（治本：新增產物忘了加清單 → Pages 404）；
    #   2026-10-08 收緊：由「已改動/未追蹤」改為「本輪真的產生」—— 既有 dirty 的連結目標不得因被連結
    #   而進 commit（共用 _is_produced 同一判準；before 不可讀者一律排除）。快照不完整時整段略過。
    if _snap_ok:
        try:
            import re as _re2
            _idx = (BASE / "index.html").read_text(encoding="utf-8")
            for _h in sorted(set(_re2.findall(r'href="([^"]+)"', _idx))):
                if not _h or _h.startswith(("http", "#", "mailto")) or "/" in _h:
                    continue
                if (BASE / _h).exists() and _h not in _push_files and _is_produced(_h, _BEFORE, _after):
                    _push_files.append(_h)
                    print(f"  ➕ 連結目標補推（本輪產物）: {_h}")
        except Exception as _le:
            print(f"⚠️ 連結掃描略過: {_le}")
    # 9c4. 自動化防守閘門（2026-10-03 使用者核准）：月度比較頁數字必須等於 performance_core 輸出
    #      定位＝自動化防守，不是績效功能：不碰計算邏輯、不新增口徑、不改頁面。
    #      PASS → 才允許後續 commit/push；FAIL → 阻擋推送（fail-closed），本次不視為成功。
    try:
        # 2026-10-09（使用者裁決 Q1：呼叫端明示＋核准紀錄交叉比對）：
        #   呼叫端必須**明示**本輪允許範圍、核准參照與產物清單；來源＝獨立治理宣告檔
        #   governance/publish_scope.json。呼叫端不得自行擴張範圍再用自己提供的範圍過關。
        #   缺檔／缺欄 → 不傳參數 → 閘門 F2 FAIL-CLOSED（不預設「範圍不限」）。
        _decl_path = BASE / "governance" / "publish_scope.json"
        _vg_cmd = [sys.executable, str(BASE / "tools" / "verify_performance_monthly.py")]
        if _decl_path.exists():
            try:
                _decl = json.loads(_decl_path.read_text(encoding="utf-8"))
                _af = [str(x) for x in (_decl.get("allowed_files") or [])]
                _dl = [str(x) for x in (_decl.get("deliverables") or [])]
                _ar = str(_decl.get("approval_ref") or "")
                if _af:
                    _vg_cmd += ["--allowed-files", ",".join(_af)]
                if _dl:
                    _vg_cmd += ["--deliverables", ",".join(_dl)]
                if _ar:
                    _vg_cmd += ["--approval-ref", _ar]
                print(f"  🔒 宣告來源 governance/publish_scope.json：{len(_af)} 檔／"
                      f"核准參照{'有' if _ar else '缺'}")
            except Exception as _de:
                print(f"  ⚠️ 宣告檔解析失敗（F2 將 FAIL-CLOSED）: {_de}")
        else:
            print("  ⚠️ 缺 governance/publish_scope.json → 閘門 F2 將 FAIL-CLOSED")
        _vg = subprocess.run(_vg_cmd,
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=900, cwd=str(BASE))
        _vg_out = (_vg.stdout or "").strip().splitlines()
        for _l in _vg_out[-4:]:
            print("  🔒 " + _l.strip())
        _gate_ok = _vg.returncode == 0
        if not _gate_ok:
            print("  ⛔ 月度比較閘門 FAIL → 頁面數字 ≠ performance_core 輸出，阻擋推送：")
            for _l in _vg_out:
                if "❌" in _l:
                    print("    " + _l.strip())
    except Exception as _e9c4:
        _gate_ok = False   # 閘門本身跑不起來 → 一律視為 FAIL（不得因驗證器故障而放行）
        print(f"  ⛔ 月度比較閘門異常 → 視為 FAIL、阻擋推送：{_e9c4}")

    _recorded = False
    if not _gate_ok:
        print("  ⛔ 已阻擋 commit/push（月度比較閘門 FAIL；修正後重跑 regenerate_report.py --deploy）")
        if _push_files:
            print(f"  ⛔ 有 {len(_push_files)} 個檔案待推，但閘門 FAIL → 本次不推送（fail-closed）")
    # 2026-10-06（使用者裁決，方案 2）per-commit scope isolation：
    #   舊語義＝整個 worktree 不能髒 → 任何未納管 dirty 都會擋住所有產線。
    #   新語義＝本輪 commit 只對本輪宣告 scope 負責：scope 內必須乾淨、必須驗證、必須受管控；
    #            scope 外既有 dirty 不得自動納入 commit、不得阻擋本輪 commit、必須保留原狀。
    #   ⚠️ SystemExit(9) 刻意「不吞掉」：讓整條 commit/push path 立即中止、行程 rc=9。
    #   dirty_gate 自身故障亦 fail-closed（內部 raise SystemExit），不得因驗證器故障而放行。
    from dirty_gate import (build_manifest as _bm, assert_scoped_commit as _dsc,
                            assert_staged_in_scope as _dsi)
    _scope = _bm(label=f"regenerate_report({TODAY})", produced=_push_files, base=BASE)
    _dsc(_scope, base=BASE, label=f"regenerate_report({TODAY})")
    if _push_files and _gate_ok:
        # 只 stage 本輪 scope（manifest.allow）── 絕對不使用 git add -A、絕不 stage scope 外檔案
        subprocess.run(['git', 'add', '--'] + list(_scope.get('allow') or _push_files), capture_output=True, text=True, cwd=BASE)
        _staged = subprocess.run(['git', 'diff', '--cached', '--name-only'], capture_output=True, text=True, cwd=BASE).stdout.strip()
        if _staged:
            # stage 後、commit 前：staged 必須完全落在本輪 scope 內（絕對禁止 scope 外檔案進入 commit）
            _dsi(_scope, base=BASE, label=f"regenerate_report({TODAY})")
            subprocess.run(['git', 'commit', '-m', _msg], capture_output=True, text=True, cwd=BASE)
            # 2026-09-14（INC-183）：此處原本寫 --record skip，但檔案內沒有任何地方替這顆 commit 落紀錄
            # （cio_review.py 只是本地規則檢查、不寫紀錄；cio_approve 從未被呼叫；原先是靠 [cioreviewed]
            # 標籤通道，v4.2 對本路徑收掉標籤後就沒人補位）→ 閘門逐 commit 驗 tree 必然擋下，
            # 07:00 morning_deploy 變成「產出完成但不部署」。改走預設 auto：由 auto_push → auto_record
            # 的 deterministic 檢查把關；範圍內若含程式檔一律拒推（exit 3）＝我們要的 fail-closed。
            _ar = subprocess.run([sys.executable, str(BASE / "auto_push.py"), "--script", "regenerate_report.py"],
                                  capture_output=True, text=True, timeout=900, cwd=BASE)
            print((_ar.stdout or "").strip() or (_ar.stderr or "").strip())
            if _ar.returncode != 0:
                print(f"⚠️ 未推送上線（rc={_ar.returncode}）")
            _recorded = _ar.returncode == 0
            if not _recorded:
                print("  ⛔ 未推送上線（見上方 auto_push 訊息）")
        else:
            print("⚠️ 無檔案可提交（全部已是最新，跳過 commit）")
    elif not _push_files:
        print("⚠️ 無任何報表檔案可推送")
    # 推送與遠端 sha 驗證已在 auto_push.py 內完成（含重試與 ls-remote 覆核）
    # 驗證上線（2026-09-23 INC-240：改呼叫 check_dashboard_sync.py --post-push ——
    # index.html 全部本機連結逐條驗線上 200，取代原本只驗 4 個檔；有 404 即 rc≠0 → 不假裝成功）
    _post = subprocess.run([sys.executable, str(BASE / "check_dashboard_sync.py"), "--post-push"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=900, cwd=str(BASE))
    print((_post.stdout or "").strip())
    if _post.returncode != 0:
        _pages_ok = False
        print("  ⛔ 線上連結驗證未過（見上方 ❌）→ 本次不視為成功（cron 會發警報）")
else:
    print(f"\n⛔ 產出檢查={'✅' if ok else '❌'} / CIO 審查={'✅' if _cio_ok else '❌'} → 未推送（修正後重跑 regenerate_report.py --deploy）")
# 12. 產出連結清單（不論是否推播都顯示）
print(f'\n{"="*50}')
print(f'  龍九控股 — 管線產出完成 {TODAY}')
print(f'{"="*50}')
print(f'📰 日報:      https://b0988321088.github.io/longjiu-dashboard-2/{OUT.name}')
print(f'🔄 再平衡儀表板: https://b0988321088.github.io/longjiu-dashboard-2/rebalance_dashboard_{TODAY}.html')
print('🏠 儀表板:    https://b0988321088.github.io/longjiu-dashboard-2/')
print(f'📈 差異分析:  https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{TODAY}.html')
print(f'📊 穿透分析:  https://b0988321088.github.io/longjiu-dashboard-2/{_pen_file or f"penetration_report_{TODAY}.html"}')
_emergency_link = _er_name  # v6 修正 2026-09-13：_latest_er 在 320 行已被 rebound 成 Path 清單，這裡必須用 _er_name（檔名字串），否則印出 WindowsPath 清單
print(f'🚨 緊急應變:  https://b0988321088.github.io/longjiu-dashboard-2/{_emergency_link}')

import sys
sys.exit(0 if (ok and _pages_ok and _gate_ok) else 1)
