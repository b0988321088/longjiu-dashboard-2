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
import public_mask  # 2026-10-12 資安處置：公開面遮蔽（唯一實作）

BASE = Path(__file__).resolve().parent
TODAY = dt.today().isoformat()
OUT = BASE / f"daily_report_v2_{TODAY}.html"
CNY_TWD = 4.73  # 2026-09-14 使用者確認（200 CNY≈944 TWD）；Yahoo CNYTWD 4.734
_EMERGENCY_LANE = os.environ.get("LJ_EMERGENCY_LANE") == "1"
_NO_PUSH = ("--no-push" in sys.argv) or _EMERGENCY_LANE
# 2026-09-17 INC-210：核准前本機產出用（不 commit/push）。
# 2026-10-15 使用者裁決（緊急應變產線 B 修正版）：「產出與驗收可以完成，發布權限仍受
#   獨立閘門控制」。四階段口徑就此分離 —— ①產物生成＋②驗收＝本檔一律執行；
#   ③提交＋④發布＝預設關閉，只能走經授權的發布路徑（07:00 主產線 morning_deploy.py）。
#   LJ_EMERGENCY_LANE=1 為「只收緊」的車道標記（13:00 台股／21:30 美股緊急應變 cron 設定）：
#   即使 prompt 漂移成不帶 --no-push，本車道呼叫也不會 commit/push。不新增授權途徑、
#   不繞過發布閘門（publish_gate／publish_plan／LJ_EMERGENCY_COMMIT 全部不動）。

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
import time as _time
_RUN_T0 = _time.time()          # 本輪起跑時刻（producer 邊界窗口下端；定點認領用）


def _head_sha(_f):
    """HEAD:<檔> 的內容指紋；HEAD 無此檔（未追蹤）或讀取失敗 → None。"""
    try:
        _r = subprocess.run(["git", "show", f"HEAD:{_f}"], capture_output=True, cwd=str(BASE))
        if _r.returncode != 0 or not _r.stdout:
            return None
        return _hl.sha256(_r.stdout).hexdigest()
    except Exception:
        return None


def _claim_dirty_fixed_point(_f, _a):
    """既有 dirty 檔的「定點認領」（2026-10-12 TD-20261012-25；使用者裁決之三條件＋允許範圍防線）。

    背景：produced = after − before。若某候選檔在**進場前就已 dirty**，而本輪又重寫出位元相同的
    內容（before == after 的定點），舊判準永遠不認領它 → 一經漏出即永久殘留（今天清、明天又漏）。
    三條件同時成立才認領，任一不成立即維持原判準（不認領）：
      ① 相對 HEAD 確實 dirty（內容 ≠ HEAD blob；HEAD 無此檔者走「本輪新增」分支，不經此處）
      ② 本輪執行窗口內確實被寫入（mtime 不早於本輪起跑時刻 _RUN_T0）
      ③ after 指紋可靠（呼叫端已驗，非 _UNREADABLE）
    允許範圍防線：認領仍須符合原候選範圍（檔案存在、副檔名 ∈ _SNAP_EXT、大小 ≤ _SNAP_MAX）；
    本函式只對「這一個檔案」作答 —— 認領成功不得連帶把其他 dirty 檔納入提交候選。
    """
    _h = _head_sha(_f)
    if _h is None or _h == _a:
        return False                               # 未追蹤，或內容與 HEAD 相同 → 不認領
    try:
        _st = (BASE / _f).stat()
    except Exception:
        return False
    if _st.st_mtime < _RUN_T0:
        return False                               # 窗口外（本輪未寫它）→ 不認領
    if (BASE / _f).suffix.lower() not in _SNAP_EXT or _st.st_size > _SNAP_MAX:
        return False                               # 超出原允許範圍 → 不認領
    return True


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
    # 2026-10-18（實證死鎖）：前一輪失敗殘留的「未進版控今日產物」，在下一輪會被判成既有 dirty
    #   （內容位元相同、又不在 before 差異內），而 _claim_dirty_fixed_point 的條件①
    #   「相對 HEAD 確實 dirty」對未追蹤檔永遠不成立（HEAD 無此檔）→ 兩條路都不認領
    #   → 連結閘門「連結目標未進版控」永久 FAIL，該日產物永遠上不了線
    #   （當日 8 檔：asset_diff／penetration／rebalance_dashboard／rebalance_eval／
    #     retirement_plan／structural_health／industry_penetration／buffett_cto_report）。
    #   未追蹤＝沒有既有版本會被覆蓋；檔名逐字列在 _push_candidates（本輪宣告）→ 可安全認領。
    if _head_sha(_f) is None:
        return True
    if _before[_f] == _UNREADABLE:
        return False                               # before 不可信 → 不得算本輪產物
    if _before[_f] != _a:
        return True                                # 內容確實變了 → 本輪產物
    # 定點：進場前已 dirty ＋ 本輪窗口內被寫出位元相同內容 → 認領（2026-10-12 TD-20261012-25）
    return _claim_dirty_fixed_point(_f, _a)


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

# 3b-0. 緊急應變隔夜交接閘門（F1 第三階段，2026-10-21 使用者授權）
#   21:30 只寫 repo 外 staging；本檔是本批唯一發布出口。
#   旗標 LJ_EMERGENCY_HANDOFF 未設／off 且當日無交接資料 → mode=legacy，
#   行為與舊版**完全相同**（回滾語意＝把旗標設回 off）。
#   呼叫端只看 gate().mode／rc，不以 rc=0 推論「驗證通過」（dry-run 亦為 rc=0）。
_hgate = None
try:
    import staging_handoff as _sh_h
    _hgate = _sh_h.gate(TODAY)
    print(f"🗂 緊急應變交接：mode={_hgate.mode} state={_hgate.state} rc={_hgate.rc}"
          + (f"｜{_hgate.public}" if _hgate.public else ""))
except Exception as _e_h:
    print(f"[WARN] 交接驗證未執行（沿用舊行為）：{_e_h}")
_em_mode = _hgate.mode if _hgate is not None else "legacy"

# 3b. 緊急應變分析（INC-291：唯一實作＝daily_report_assembly.build_emergency_block）
#   canonical 行為＝本檔 2026-10-09 前的已上線實作（refresh_stale_amounts 舊值覆蓋／as_of
#   `_stale_badge`／`<br>` 換行／2 條連結）；run_daily.py main() 亦呼叫同一函式
#   → 兩個 producer 不再各自組裝。連結 `.html.html` 重綴缺陷已於 INC-294 修正（見共用模組 docstring）。
from daily_report_assembly import build_emergency_block as _asm_em
_snap_em = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
if _em_mode == "inject":
    # 只有「通過交接驗證的當日分析」才可進 repo：先寫暫存檔再原子替換，
    # 不讓半寫入的 JSON 落成當日正式檔（21:30 不得直接寫入此路徑）。
    _em_src = _hgate.result.path / "analysis.json"
    _em_dst = BASE / "data" / "emergency_llm_analysis.json"
    _em_tmp = None
    try:
        _em_raw = _em_src.read_bytes()
        _em_tmp = _em_dst.with_suffix(".json.tmp")
        _em_tmp.write_bytes(_em_raw)
        _em_tmp.replace(_em_dst)
        print(f"🗂 應變分析已由交接複製入 repo（{len(_em_raw):,} bytes，經 SHA-256 驗證）")
    except Exception as _e_cp:
        print(f"⛔ 複製應變分析失敗（不注入）: {_e_cp}")
        # 失敗不得留下半成品暫存檔（否則工作區多出未追蹤檔、也可能被誤認本輪產物）
        try:
            if _em_tmp is not None and _em_tmp.exists():
                _em_tmp.unlink()
                print("🧹 已清除暫存檔（複製失敗殘留）")
        except Exception as _e_rm:
            print(f"[WARN] 暫存檔清除失敗（需人工確認）: {_e_rm}")
        _em_mode = "block"
if _em_mode in ("legacy", "inject"):
    _emergency_html = _asm_em(BASE, _snap_em, TODAY)
elif _em_mode == "block":
    _em_txt = _hgate.public if (_hgate is not None and _hgate.public) else "應變資料驗證失敗（未分類）（H99）"
    _emergency_html = (f'<div class="callout callout-warn"><p style="font-size:13px;color:#b45309;'
                       f'font-weight:700">⚠️ 緊急應變交接驗證失敗，未注入：{_em_txt}</p></div>')
else:  # blank：無資料／dry-run／功能關閉但有資料 → 第八章留空，不拿舊檔冒充當日
    _em_txt = f"｜{_hgate.public}" if (_hgate is not None and _hgate.public) else ""
    _emergency_html = (f'<div class="callout callout-warn"><p style="font-size:13px;color:#6e6e73">'
                       f'ℹ️ 今日無可用的緊急應變交接資料（未注入）{_em_txt}</p></div>')

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
# 2026-10-16 P0（US30Y 單一來源）：輸出前呼叫唯一實作（daily_report_assembly.unify_us30y_live）
try:
    from daily_report_assembly import unify_us30y_live as _u30
    html = _u30(html, BASE)
except Exception:
    pass
OUT.write_text(public_mask.scrub(close_html_tail(html)), encoding="utf-8")  # 2026-10-12 資安處置：公開面遮蔽

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
# 9c-1. 退休規劃報告（P2／2026-10-12 工單，使用者裁決：既有流程歸屬＝本產線 9c 段）
#   根因：build_retirement_plan.py 全庫零呼叫者（run_daily／sync_all／morning_batch／four_source_sync 皆查無），
#   產出檔只有 update_dashboard_links.py 的 glob 會吃進按鈕 → 沒有任何流程負責入庫。
#   2026-10-12 實踩：線上「退休規劃」按鈕指向 retirement_plan_2026-10-12.html（未追蹤）→ Pages 404 一整天。
#   放在 build_dashboard 之前：先產檔、後刷連結，按鈕才不會指到不存在的檔案；產物與 index.html 同一輪、
#   同一個 commit scope（「發布責任明確」＝本輪 commit，不再靠人工補）。
#   失敗不阻擋本輪（僅告警）——與同段其他非日報產物一致；真 404 由下游發布前連結閘門擋。
try:
    _r_ret = subprocess.run([sys.executable, str(BASE / "build_retirement_plan.py")], cwd=str(BASE),
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    _ret_lines = (_r_ret.stdout or "").strip().splitlines()
    print("  " + (_ret_lines[-1] if _ret_lines else "✅ retirement_plan"))
    if _r_ret.returncode != 0:
        print(f"  ⚠️ 退休規劃產出異常（不影響日報）: rc={_r_ret.returncode} "
              f"{(_r_ret.stderr or '').strip()[:160]}")
except Exception as _e9cr:
    print(f"  ⚠️ 退休規劃產出異常（不影響日報）: {_e9cr}")
# 9c-1b. 財務結構健檢報告（2026-10-17 新增；使用者需求：可定期檢核的結構變化報告）
#   同退休規劃模式：先產檔、後刷連結（按鈕 __STRUCT_HEALTH__ 才不會指到不存在的檔案）；
#   產物與 index.html 同一輪、同一 commit scope（發布責任明確＝本輪）。失敗不阻擋本輪。
try:
    _r_sh = subprocess.run([sys.executable, str(BASE / "build_structural_health.py")], cwd=str(BASE),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    _sh_lines = (_r_sh.stdout or "").strip().splitlines()
    print("  " + (_sh_lines[0] if _sh_lines else "✅ structural_health"))
    if _r_sh.returncode != 0:
        print(f"  ⚠️ 結構健檢產出異常（不影響日報）: rc={_r_sh.returncode} "
              f"{(_r_sh.stderr or '').strip()[:160]}")
except Exception as _e9csh:
    print(f"  ⚠️ 結構健檢產出異常（不影響日報）: {_e9csh}")
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
        (BASE / "index.html").write_text(public_mask.scrub(_idx_html), encoding="utf-8")
    except Exception:
        pass
# 緊急應變連結（2026-08-22 修正：週末/例假日不產出 → 一律 glob 最新，避免 __TODAY__ 404）
try:
    _latest_er = sorted(BASE.glob("emergency_report_2*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
    _er_name = _latest_er[0].name if _latest_er else f"emergency_report_{TODAY}.html"
    _idx_html2 = (BASE / "index.html").read_text(encoding="utf-8").replace("__EMERGENCY_REPORT__", _er_name)
    (BASE / "index.html").write_text(public_mask.scrub(_idx_html2), encoding="utf-8")
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

# ── B 案（TD-20261012-23）真 CIO RECORD 前置步驟 ──────────────────────────────
# 使用者 2026-10-12 裁決：①真 CIO RECORD 是唯一正常通道 ②任何不確定一律 fail-closed
#   （不得降級成 TAG、不得自動補標籤、不得放寬 auto_push.py 的判定）。
# 背景（本輪唯讀盤點）：0a7d36d9 之後落版側把「閘門會判 CIO 的整個集合」列為強制真 CIO 類，
#   而日常產出必然碰 index.html／snapshot.json／dashboard_decisions.json → auto_record 一律拒落
#   （實測 62f09db6 與 f506a72f 以同一理由被拒）→ auto_push 恆 rc=3，產線等於無法自我部署。
#   白名單救不了：index.html 依裁決必須經真 CIO 審查。故改為讓產線自己取得那份審查紀錄。
_CIO_DIFF_CAP = 32000   # 送審內文上限（與 review_chain.DEFAULT_DIFF_CAP 同值；2026-10-16 裁決 12,000 → 32,000）
# 2026-10-13（TD-20261013-05／06）：審查者標籤改為**動態**（由 review_chain 回報實際使用者）。
# 原本寫死 "CIO-Pollinations(openai)" 且送審直接打 Pollinations 單點 —— 402 即全停。
_CIO_REVIEWER_FALLBACK_NOTE = "CIO-review-chain（異質：Pollinations／nous-longcat／nous-laguna）"


def _cio_governance_invariant(commit: str) -> str:
    """治理檔不變量（使用者條件 2：meta 不一致 → 停止發布）。回傳錯誤訊息，空字串＝通過。

    只驗 dashboard_decisions.json：決策只許純追加、meta 逐位元不變。
    （與 publish_gate 的 append-only 車道同一組不變量語意；此處為「送審前」的 fail-closed 前置。）
    """
    gov = "dashboard_decisions.json"
    changed = subprocess.run(["git", "show", "--name-only", "--format=", commit],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(BASE)).stdout.split()
    if gov not in changed:
        return ""
    old_raw = subprocess.run(["git", "show", f"{commit}^:{gov}"], capture_output=True, cwd=str(BASE)).stdout
    new_raw = subprocess.run(["git", "show", f"{commit}:{gov}"], capture_output=True, cwd=str(BASE)).stdout
    try:
        old = json.loads(old_raw.decode("utf-8", "replace"))
        new = json.loads(new_raw.decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        return f"{gov} 解析失敗（{str(e)[:60]}）→ fail-closed"
    if old.get("meta") != new.get("meta"):
        # 2026-10-12 沙盒實證：dashboard_decisions.json.meta 只有 {"updated_at": …}，而產線**每次執行
        # 都會重寫它**（decisions 1165→1165 不變、updated_at 由 21:32→22:36）。若要求 meta 逐位元不變，
        # 等於要求產線永不執行（必然死結）。故只放行 updated_at 這個時間戳，其餘 meta 變動一律 fail-closed
        # —— 仍守住使用者條件 2「meta 不一致→停止」的防護意圖（非時間戳的 meta 變動＝真異常）。
        _om = {k: v for k, v in (old.get("meta") or {}).items() if k != "updated_at"}
        _nm = {k: v for k, v in (new.get("meta") or {}).items() if k != "updated_at"}
        if _om != _nm:
            return f"{gov}.meta 變動（非 updated_at 時間戳）→ fail-closed"
    o, n = old.get("decisions") or [], new.get("decisions") or []
    if len(n) < len(o) or n[:len(o)] != o:
        return f"{gov}.decisions 非純追加（{len(o)}→{len(n)}）→ fail-closed"
    return ""


def _cio_review_and_record() -> tuple[bool, str]:
    """auto_push 之前：對「待推範圍」取得真 CIO APPROVE 並落 RECORD。回傳 (可否繼續, 說明)。

    fail-closed 條件：範圍不唯一（舊 commit 阻塞）／審查工具不可用／輸出不可解析／非 APPROVE／
    有 blocking／回傳的 commit 或 tree 與實際不符／紀錄寫入失敗／寫入後複驗失敗。
    """
    import cio_approve as _ca          # 既有工具：紀錄格式單一真值（不自行解析 tab 格式）
    import review_chain as _rc         # 審查鏈單一實作（2026-10-13 TD-20261013-05／06）

    def _git(*args: str):
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=str(BASE))

    rng = _git("rev-list", f"origin/clean-main..HEAD")
    if rng.returncode != 0:
        return False, "讀不到 origin/clean-main（尚未 fetch／遠端不存在）→ fail-closed"
    pending = [c for c in rng.stdout.split() if c]
    if not pending:
        return True, "無待推 commit"
    # 契約（使用者 2026-10-12 條件 1／2）：範圍內每一顆都必須有 RECORD；
    # 只有「本輪這一顆（HEAD）」可以由本步驟送審補上。其餘未落紀錄者＝舊 commit 阻塞 → 停止。
    unrecorded = []
    for c in pending:
        t = _git("rev-parse", f"{c}^{{tree}}").stdout.strip()
        if not t:
            return False, f"取不到 tree（{c[:12]}）→ fail-closed"
        if not _ca.is_approved(t):
            unrecorded.append(c)
    others = [c for c in unrecorded if c != pending[0]]
    if others:
        return False, (f"待推範圍含未落紀錄的舊 commit（{len(others)} 顆："
                       f"{', '.join(c[:12] for c in others)}）→ 先清阻塞再重跑（fail-closed）")
    commit = pending[0]
    tree = _git("rev-parse", f"{commit}^{{tree}}").stdout.strip()
    if not tree:
        return False, "取不到 tree → fail-closed"
    if commit not in unrecorded:
        return True, f"tree {tree[:12]} 已有 APPROVE 紀錄（跳過審查，避免重複審查／重複落紀錄）"
    inv = _cio_governance_invariant(commit)
    if inv:
        return False, inv

    files = _git("show", "--name-only", "--format=", commit).stdout.strip()
    subj = _git("log", "-1", "--format=%s", commit).stdout.strip()
    diff = _git("show", "--stat", "--format=", commit).stdout.strip()
    # 2026-10-13 P1：prompt 收斂到 review_chain（單一真值）；綁定一律 12 碼
    #   （原內嵌複本用完整 40 碼，會踩免費層抄寫掉字元的坑）。
    # 2026-10-15 B1（R1）：原版**只送 --stat、完全不送內容**（審查者看不到一行程式碼），
    #   且超量時不得靜默截斷 → 改為送完整 patch，超量由 review_chain 完整分段，
    #   涵蓋率 <100% 或分段未回報 commit/tree 綁定 → 直接拒絕核准（fail-closed）。
    patch = _git("show", "--format=", commit).stdout or ""
    prompts, cov = _rc.build_review_prompts(commit, tree, subj, files, diff,
                                            _CIO_DIFF_CAP, patch=patch)
    try:
        txt, _reviewer, _meta = _rc.review_segmented(prompts, cov,
                                                     expect_pair=(commit[:12], tree[:12]))
    except Exception as e:  # noqa: BLE001
        return False, f"審查鏈全數不可用（{type(e).__name__}: {str(e)[:120]}）→ fail-closed（不降級 TAG）"
    import re as _re_cio
    m = _re_cio.search(r"\{.*\}", txt, _re_cio.S)
    if not m:
        return False, "審查輸出無法解析出 JSON → fail-closed"
    try:
        rev = json.loads(m.group(0))
    except Exception as e:  # noqa: BLE001
        return False, f"審查 JSON 解析失敗（{str(e)[:60]}）→ fail-closed"
    verdict = str(rev.get("verdict", "")).strip().upper()
    blocking = rev.get("blocking") or []
    # 2026-10-13 P1：綁定比對一律 12 碼前綴（與 build_review_prompt 的 12 碼慣例對齊）
    ok_pairs = {(str(x.get("commit", ""))[:12], str(x.get("tree", ""))[:12])
                for x in (rev.get("reviewed_commits") or []) if isinstance(x, dict)}
    if verdict != "APPROVE":
        return False, f"審查未通過（verdict={verdict or '空'}）→ fail-closed"
    if blocking:
        return False, f"審查有 blocking {len(blocking)} 項 → fail-closed"
    if (commit[:12], tree[:12]) not in ok_pairs:
        return False, ("審查回傳的 commit／tree 與實際待推內容不符（範圍無法對應）→ fail-closed")
    rdir = BASE / ".git" / "cio_reviews"
    try:
        rdir.mkdir(parents=True, exist_ok=True)
        rj = rdir / f"{TODAY}_regenerate_{commit[:12]}.json"
        rj.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        return False, f"審查紀錄寫入失敗（{str(e)[:60]}）→ fail-closed"
    ap_ = subprocess.run([sys.executable, str(BASE / "cio_approve.py"), "--result", str(rj),
                          "--reviewer", _reviewer, "--commit", commit],
                         capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(BASE))
    if ap_.returncode != 0:
        return False, f"cio_approve 落紀錄失敗（rc={ap_.returncode}）→ fail-closed"
    if not _ca.is_approved(tree):
        return False, "落紀錄後複驗失敗（tree 仍無 APPROVE）→ fail-closed"
    return True, f"真 CIO RECORD 已落地（{_reviewer}｜tree {tree[:12]}）"


if _NO_PUSH:
    # INC-210：核准前本機產出（交付鐵則：改完先傳本地檔案，使用者說「推」才 push）
    # 2026-10-15：緊急應變車道固定只做產物生成＋驗收，提交／發布不在本班職權內。
    _why_np = "LJ_EMERGENCY_LANE=1（緊急應變車道）" if _EMERGENCY_LANE else "--no-push"
    print(f"\n🧪 {_why_np}：產物生成＋驗收完成；略過 commit/push（發布須另行授權）")
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
                        'performance_monthly.html',
                        # 2026-10-12（工單 P2）：退休規劃報告 —— 9c-1 段產出，發布責任歸屬本輪 commit
                        #   （原本零呼叫者、零發布責任 → 2026-10-12 線上按鈕 404）
                        f'retirement_plan_{TODAY}.html']
    # 再平衡儀表板（2026-08-22：每日重跑，build_rebalance_dashboard.py 讀 snapshot+radar_state）
    try:
        subprocess.run([sys.executable, str(BASE / "build_rebalance_dashboard.py")], cwd=str(BASE),
                       capture_output=True, timeout=120)
        _push_candidates.append(f'rebalance_dashboard_{TODAY}.html')
        _push_candidates.append(f'rebalance_eval_{TODAY}.html')
        _push_candidates.append(f'rebalance_summary_{TODAY}.md')
        _push_candidates.append(f'industry_penetration_{TODAY}.png')
    except Exception:
        pass
    # 2026-10-15 B1（§5 HTML 方案 A）：首頁「重要連結」的兩份報告頁納入 producer stage 白名單。
    #   背景（2026-10-15 實測、check_dashboard_sync 第 12 項 FAIL）：index.html 以 links_config
    #   前綴 glob 指向最新檔（emergency_report_*／weekly_report_*），但這兩份的 producer
    #   （emergency_1330.py／build_weekly_report.py）都不是本輪 commit 的產物來源
    #   → 檔案被首頁連結卻從未進版控 → 線上 404。
    #   本輪起改由本清單明確認領；仍須通過 dirty_gate 的「本輪產物／dirty 定點認領」判準
    #   （既有他班 dirty 不會被夾帶進 commit），發布面由 publish_allowlist.json 對應條目放行。
    _push_candidates.append(f'emergency_report_{TODAY}.html')
    # 2026-10-18：結構健檢報告（build_structural_health.py 產出，檔名為 structural_health_YYYYMMDD.html，
    #   由 index.html 連結）長期未納入本輪認領 → 連結閘門「連結目標未進版控」擋住整批發布。
    _push_candidates.append(f'structural_health_{TODAY.replace("-", "")}.html')
    # 2026-10-15 21:5x 使用者裁決（緊急應變產線 B 修正版）：emergency_taiex_report_*.html
    #   與 emergency_report_*.html 同一批產出（gen_emergency_taiex_auto.py 同時寫兩檔），
    #   長期未納入版控 → 首頁連結若指向它必 404。兩家族同一套受控產物規則（逐字檔名
    #   認領，不做目錄級 stage）；白名單對應條目＝publish_allowlist.json「首頁重要連結報告頁」。
    _push_candidates.append(f'emergency_taiex_report_{TODAY}.html')
    _push_candidates.append(f'weekly_report_{TODAY}.html')
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
        # F1 第三階段：非 inject 時，應變三件（兩份報告頁＋分析 JSON）一律不進本輪發布；
        # inject 時才明確認領分析 JSON（該檔由上面的驗證複製步驟寫入）。
        _em_artifacts = {f'emergency_report_{TODAY}.html', f'emergency_taiex_report_{TODAY}.html'}
        if _em_mode == "inject":
            _push_candidates.append('data/emergency_llm_analysis.json')
        else:
            _before_n = len(_push_candidates)
            _push_candidates = [c for c in _push_candidates if c not in _em_artifacts]
            if len(_push_candidates) != _before_n:
                print(f"  ⏭ 應變報告頁不納入本輪發布（mode={_em_mode}，排除 "
                      f"{_before_n - len(_push_candidates)} 檔）")
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
        # 2026-10-09（使用者裁決，方案 1：閘門作用域修正）：日常產線明確宣告「非發布批次」
        #   → 閘門只驗 F1／F3＋A–E 數字一致性；F2（宣告範圍）／F4（核准產物雜湊）屬
        #   **發布步驟**契約，日常產線沿用即恆 FAIL。模式由本程式（可信任的呼叫端，
        #   受 pre-push 程式檔規則與 CIO 審查）決定，不由待驗證的產物宣告；
        #   未帶此旗標者一律走嚴格路徑（預設 publish）。
        _vg_cmd = [sys.executable, str(BASE / "tools" / "verify_performance_monthly.py"),
                   "--check-mode", "daily"]
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
    _links_ok = True   # P1（2026-10-12 工單）：發布前連結閘門結果；False → 本輪不 commit、不推送
    # 2026-10-17（使用者裁決「授權 1+2」）：發布放行條件 ③⑥
    #   ③ 範圍類 ∩ produced：未宣告的 .py 真的進入本輪發布集合才擋（不誤擋、不隱藏 FAIL）
    #   ⑥ 新鮮度：snapshot.date 非當日且無有效 T-1 例外標記 → 擋（不補日期、不偽裝）
    #   任何異常一律 fail-closed；本閘門只「阻擋」，不新增任何放行途徑。
    if _gate_ok and _push_files:
        try:
            from tools.publish_gate import check_publish_gate as _pg_check
            _snap_d = str((json.loads((BASE / "snapshot.json").read_text(encoding="utf-8")) or {}).get("date") or "")
            _pg = _pg_check(_push_files, _snap_d, TODAY, BASE)
            for _n in _pg["notes"]:
                print("  🔓 " + _n)
            if not _pg["ok"]:
                _gate_ok = False
                print("  ⛔ 發布放行條件未通過（fail-closed）：")
                for _b in _pg["blocking"]:
                    print("    " + _b)
        except Exception as _pge:
            _gate_ok = False
            print(f"  ⛔ 發布放行閘門異常 → 視為 FAIL、阻擋推送：{_pge}")
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
        # P1（2026-10-12 工單，使用者核准）：發布前連結閘門 —— 第 12 項（連結目標未進版控）只在
        #   「已 stage、未 commit」這個時點判得準：`git ls-files` 讀的是 index，本輪已 stage 的檔
        #   已算 tracked；沒進 index 的連結目標＝本次不會上線＝線上必 404。
        #   為什麼要補這道：產線兩處呼叫（9c2／收尾）都帶 LJ_PREPUSH=1 → 第 12 項永遠只印 ℹ️，
        #   push 前沒有任何一道會真的擋。2026-10-12 實踩：index.html「退休規劃」按鈕指向未入庫檔
        #   （retirement_plan_2026-10-12.html）→ 線上 404 一整天，直到人工補版控才修好。
        #   刻意「不」帶 LJ_PREPUSH，且放在 commit 之前 → 擋下時不會留下「已 commit 卻推不動」的
        #   毒化 commit（那顆會讓 origin/clean-main..HEAD 整段對所有 producer 變 CIO 模式）。
        _links_ok, _links_lines = True, []
        if _staged:
            try:
                _lk_gate = subprocess.run([sys.executable, str(BASE / "check_dashboard_sync.py")],
                                          capture_output=True, text=True, encoding="utf-8",
                                          errors="replace", timeout=120, cwd=str(BASE))
                _links_ok = _lk_gate.returncode == 0
                if not _links_ok:
                    _links_lines = [l.strip() for l in (_lk_gate.stdout or "").splitlines()
                                    if "❌" in l or "未進版控" in l or "不存在" in l]
            except Exception as _e_lk:
                # fail-closed：驗證器跑不起來 → 視為 FAIL（不得因驗證器故障而放行）
                _links_ok = False
                _links_lines = [f"發布前連結閘門無法執行: {_e_lk}"]
            if not _links_ok:
                print("  ⛔ 發布前連結閘門 FAIL（index.html 有連結目標不會上線 → 線上必 404）"
                      "→ 本次不 commit、不推送：")
                for _l in (_links_lines or ["（無細節輸出）"]):
                    print("    " + _l)
                print("  ⛔ 兩種既有解法（不繞過閘門、不手動 git add）：")
                print("     (a) 該檔的 producer 先自行入庫（例如 21:30 美股緊急應變 job）→ 重跑本產線")
                print("     (b) 該檔確屬本輪產物 → 加進 _push_candidates 後重跑（一次到位）")
                _unstage = subprocess.run(['git', 'restore', '--staged', '--']
                                          + list(_scope.get('allow') or _push_files),
                                          capture_output=True, text=True, cwd=BASE)
                print("  ↩️ 已取消 stage（不留 staged 殘留，避免混入下一班 commit）"
                      if _unstage.returncode == 0
                      else f"  ⚠️ 取消 stage 失敗：{(_unstage.stderr or '').strip()[:120]}")
        if _staged and _links_ok:
            # stage 後、commit 前：staged 必須完全落在本輪 scope 內（絕對禁止 scope 外檔案進入 commit）
            _dsi(_scope, base=BASE, label=f"regenerate_report({TODAY})")
            subprocess.run(['git', 'commit', '-m', _msg], capture_output=True, text=True, cwd=BASE)
            # 2026-09-14（INC-183）：此處原本寫 --record skip，但檔案內沒有任何地方替這顆 commit 落紀錄
            # （cio_review.py 只是本地規則檢查、不寫紀錄；cio_approve 從未被呼叫；原先是靠 [cioreviewed]
            # 標籤通道，v4.2 對本路徑收掉標籤後就沒人補位）→ 閘門逐 commit 驗 tree 必然擋下，
            # 07:00 morning_deploy 變成「產出完成但不部署」。改走預設 auto：由 auto_push → auto_record
            # 的 deterministic 檢查把關；範圍內若含程式檔一律拒推（exit 3）＝我們要的 fail-closed。
            # B 案（TD-20261012-23，使用者 2026-10-12 裁決）：先取得真 CIO RECORD（異質審查＋
            #   cio_approve 落紀錄＋範圍對應複驗），再交給 auto_push。任何不確定 → fail-closed，
            #   不降級 TAG、不自動補標籤、不動 auto_push 的判定。
            _cio2_ok, _cio2_msg = _cio_review_and_record()
            print(f"  🔐 真 CIO RECORD：{_cio2_msg}")
            if _cio2_ok:
                _ar = subprocess.run([sys.executable, str(BASE / "auto_push.py"), "--script", "regenerate_report.py"],
                                     capture_output=True, text=True, timeout=900, cwd=BASE)
                print((_ar.stdout or "").strip() or (_ar.stderr or "").strip())
                if _ar.returncode != 0:
                    print(f"⚠️ 未推送上線（rc={_ar.returncode}）")
                _recorded = _ar.returncode == 0
                if not _recorded:
                    print("  ⛔ 未推送上線（見上方 auto_push 訊息）")
                elif _em_mode == "inject" and _hgate is not None:
                    # 發布成功才落 published（供日後 archive／H09 批次衝突判定）
                    try:
                        _sh_h.mark_published(TODAY)
                        print("  🗂 交接 published 紀錄已寫入")
                    except Exception as _e_mp:
                        print(f"[WARN] 交接 published 紀錄未寫入（不影響本次發布）：{_e_mp}")
            else:
                _recorded = False
                print("  ⛔ 未推送（fail-closed：真 CIO RECORD 未取得，不做 TAG 降級）")
        elif not _links_ok:
            print("⚠️ 已跳過 commit（發布前連結閘門 FAIL，見上方 ⛔；本輪產物留在工作區、未提交）")
        else:
            print("⚠️ 無檔案可提交（全部已是最新，跳過 commit）")
    elif not _push_files:
        print("⚠️ 無任何報表檔案可推送")
    # 推送與遠端 sha 驗證已在 auto_push.py 內完成（含重試與 ls-remote 覆核）
    # 驗證上線（2026-09-23 INC-240：呼叫 check_dashboard_sync.py --post-push ——
    # index.html 全部本機連結逐條驗線上 200，取代原本只驗 4 個檔；有 404 即 rc≠0 → 不假裝成功）
    # 2026-10-11（使用者裁決）：只在「本次真的推成功」或「本輪無待推產物（線上狀態未被本次改動）」時才驗線上。
    #   閘門 FAIL／推送失敗時，本輪新檔必然還沒上線 → 逐條驗必然 404，只會蓋掉真因
    #   （實踩 10/11 07:00：F1 封版契約 FAIL 擋推，卻噴 3 檔線上 404，讓「閘門 FAIL」被誤讀成「部署壞了」）。
    #   fail-loud 不放寬：有產物＋閘門 PASS 卻沒推成 → 明確標記失敗，不靠 404 巧合。
    _push_pending = bool(_push_files) and _gate_ok   # 本次「應」推送成功
    if _recorded or (_gate_ok and not _push_files):
        _post = subprocess.run([sys.executable, str(BASE / "check_dashboard_sync.py"), "--post-push"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=900, cwd=str(BASE))
        print((_post.stdout or "").strip())
        if _post.returncode != 0:
            _pages_ok = False
            print("  ⛔ 線上連結驗證未過（見上方 ❌）→ 本次不視為成功（cron 會發警報）")
    elif _push_pending and not _links_ok:
        _pages_ok = False
        print("  ⛔ 發布前連結閘門 FAIL → 本輪未 commit、未推送（見上方 ⛔ 與兩種既有解法）；"
              "本次不視為成功（cron 會發警報）")
    elif _push_pending:
        _pages_ok = False
        print("  ⛔ 有本輪產物且閘門 PASS，但推送未成功（見上方 auto_push 訊息）→ 略過線上連結驗證"
              "（未推送的新檔必然 404），本次不視為成功（cron 會發警報）")
    else:
        print("  ⏭ 本次未推送（閘門 FAIL 或無本輪產物）→ 略過線上連結驗證"
              "（未推送的新檔必然 404 屬假警報；真因見上方 ⛔，本次仍不視為成功）")
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
# F1 第三階段退出碼語意（2026-10-21 授權）：
#   既有成敗（產出／線上驗證／閘門）失敗 → 1（維持不變）
#   既有全綠但交接狀態需人工處理 → 12（已發布但應變段無效）／13（功能關閉卻有當日資料）
#   兩者皆不得自動重試；rc=12 已發布，不可誤報為未推送殘留。
_rc_final = 0
if not (ok and _pages_ok and _gate_ok):
    _rc_final = 1
elif _hgate is not None and _hgate.rc:
    _rc_final = _hgate.rc
    print(f"⚠️ 應變交接需人工處理：mode={_em_mode} rc={_rc_final}（不列入自動重試）")
sys.exit(_rc_final)
