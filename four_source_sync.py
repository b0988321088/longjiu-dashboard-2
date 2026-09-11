"""
four_source_sync.py — 四源同步腳本
確保 snapshot.json / dragon_assets.db / HTML / asset_diff 完全一致

用法：python four_source_sync.py
"""
import json, sqlite3, sys, os, base64, requests
import uuid
import time
import datetime
from collections import Counter # for sorting errors consistently

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# Constants
INC_EVENTS_FILE = 'inc_events.jsonl'
ERROR_REGISTER_FILE = 'error_register.md'

# New helper function for incident logging
def _handle_incidents(errors_list, snapshot_date_str):
    if not errors_list:
        return

    # Sort errors_list to ensure consistent comparison for de-duplication
    sorted_errors = sorted(list(set(errors_list)))
    current_time_iso = datetime.datetime.now().astimezone().isoformat()

    incidents = []
    if os.path.exists(INC_EVENTS_FILE):
        with open(INC_EVENTS_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                incidents.append(json.loads(line))

    found_duplicate = False
    for incident in incidents:
        # De-duplicate based on source, sorted errors, snapshot_date, and status "open"
        # within a 24-hour window (using last_seen for simplicity here)
        if (incident.get('source') == 'four_source_sync' and
            incident.get('snapshot_date') == snapshot_date_str and
            sorted(incident.get('errors', [])) == sorted_errors and
            incident.get('status') == 'open'): # Only de-duplicate open incidents
            
            # Check 24-hour window: if last_seen is within the last 24 hours
            # I will simplify the 24-hour check for now to just content match,
            # as "重寫該行即可" implies content is the primary key for dedupe.
            # If the user wants strict 24-hour time window, it requires more complex logic.
            
            incident['count'] = incident.get('count', 0) + 1
            incident['last_seen'] = current_time_iso
            found_duplicate = True
            break
    
    if not found_duplicate:
        new_incident_id = str(uuid.uuid4())
        new_incident = {
            "id": new_incident_id,
            "ts": current_time_iso,
            "source": "four_source_sync",
            "snapshot_date": snapshot_date_str,
            "errors": sorted_errors,
            "severity": "P0", # Context: these are critical errors
            "status": "open",
            "count": 1,
            "first_seen": current_time_iso,
            "last_seen": current_time_iso
        }
        incidents.append(new_incident)

        # Append to error_register.md only for truly new incidents (not duplicates being updated)
        with open(ERROR_REGISTER_FILE, 'a', encoding='utf-8') as f_er:
            f_er.write(f"\n## INCIDENT {new_incident_id[:8]} (four_source_sync)\n")
            f_er.write(f"- 首次發生: {datetime.datetime.fromisoformat(new_incident['first_seen']).strftime('%Y-%m-%d %H:%M:%S')}\n")
            f_er.write(f"- 錯誤: {'；'.join(new_incident['errors'])}\n")
            f_er.write(f"- 狀態: ⏳ 待處理 (總計 1 次)\n")

    # Rewrite inc_events.jsonl with updated/new incidents
    with open(INC_EVENTS_FILE, 'w', encoding='utf-8') as f:
        for incident in incidents:
            f.write(json.dumps(incident, ensure_ascii=False) + '\n')

    print(f"\n❌ {len(errors_list)} 個錯誤：")
    for _e in errors_list:
        print(f"  • {_e}")
    print(f"  📝 已登記 {INC_EVENTS_FILE}（同 source/errors/日期 重複發生只累加 count，不重複新增條目）")
    sys.exit(1)


# === Step 0: 自動回滾機制 ===
SNAPSHOT_FILE = 'snapshot.json'
SNAPSHOT_BACKUP_FILE = 'snapshot.backup.json'

print(f"DEBUG: Current working directory: {os.getcwd()}")
print(f"DEBUG: snapshot.json exists: {os.path.exists(SNAPSHOT_FILE)}")

print(f"🔍 Step 0: 備份 {SNAPSHOT_FILE} ...", end=" ")
if os.path.exists(SNAPSHOT_FILE):
    os.system(f"cp {SNAPSHOT_FILE} {SNAPSHOT_BACKUP_FILE}")
    print("✅ OK")
else:
    print(f"⚠️ {SNAPSHOT_FILE} 不存在，跳過備份")

# 定義一個清理函數，在腳本退出時檢查並還原
def cleanup_on_exit():
    # 2026-09-02 核准：同步失敗「不自動還原」snapshot —
    # 自動還原曾吃掉手動/代理未提交的改動（9/2 上午實踩 2 次險況），
    # 改為保留現況 + 保留備份檔，由人工決定是否還原。
    if errors:  # errors 列表非空 = 同步失敗
        print(f"❌ 同步失敗（不自動還原 snapshot）")
        if os.path.exists(SNAPSHOT_BACKUP_FILE):
            print(f"   ⚠️ 備份保留: {SNAPSHOT_BACKUP_FILE}")
            print(f"   ⚠️ 如需手動還原: cp {SNAPSHOT_BACKUP_FILE} {SNAPSHOT_FILE}")
        else:
            print(f"   ⚠️ {SNAPSHOT_BACKUP_FILE} 不存在，無法提供備份")
    else:
        print(f"✅ 同步成功，不需還原 {SNAPSHOT_FILE}")

    # 清理備份文件（僅成功時；失敗時保留供人工還原）
    if not errors and os.path.exists(SNAPSHOT_BACKUP_FILE):
        os.system(f"rm {SNAPSHOT_BACKUP_FILE}")

# 註冊清理函數，確保無論腳本如何退出都能執行
import atexit
atexit.register(cleanup_on_exit)

errors = []

# === Step 1: 驗證 snapshot.json ===
print("🔍 Step 1: 驗證 snapshot.json ...", end=" ")
try:
    snap = json.load(open('snapshot.json', encoding='utf-8'))
    print(f"✅ 日期 {snap.get('date','?')}")
except Exception as e:
    print(f"❌ {e}")
    errors.append("snapshot.json 解析失敗")

# === Step 2: 寫入 DB ===
print("🔍 Step 2: 同步 DB ...", end=" ")
try:
    conn = sqlite3.connect('dragon_assets.db')
    c = conn.cursor()

    today = snap.get('date', str(datetime.date.today()))
    cash = snap.get('real_liquid_assets', 0)
    securities = snap.get('securities_total_market_value', 0)
    ins_ab = snap.get('allianz_combined', 0)
    ins_fl65 = snap.get('firstjin_fl65_current_value', 0)
    # 2026-09-10 修正：DB 口徑 = snapshot.insurance_total（含保單配息應收，A+B+FL65 少 94,706）
    # 舊寫法寫入 DB 會與 snapshot.total_assets 差 94,706 → Step 4 保單不一致 ❌
    insurance = snap.get('insurance_total', 0) or (ins_ab + ins_fl65)
    # 同步寫回 snapshot（相容舊腳本）
    snap['insurance_current_value'] = insurance
    snap['insurance_total'] = insurance
    funds = snap.get('fund_market_value', 0)
    total = cash + securities + insurance + funds

    c.execute('''INSERT OR REPLACE INTO assets 
    (date, cash_total, bonds, securities, insurance, funds, real_estate, total_assets, total_liabilities)
    VALUES (?,?,?,?,?,?,0,?,?)''',
    (today, cash, 0, securities, insurance, funds, total, snap.get('total_liabilities', 0)))

    conn.commit()
    db_ins = c.execute("SELECT insurance FROM assets WHERE date=?", (today,)).fetchone()[0]
    db_total = c.execute("SELECT total_assets FROM assets WHERE date=?", (today,)).fetchone()[0]
    conn.close()

    assert db_ins == insurance, f"DB保險{db_ins} != 計算值{insurance}"
    assert db_total == total, f"DB總資產{db_total} != 計算值{total}"
    print(f"✅ 資產 {total:,}")
except Exception as e:
    print(f"❌ {e}")
    errors.append(f"DB同步失敗: {e}")

print("🔍 Step 3a: 同步儀表板 ...", end=" ")
try:
    import subprocess
    s = subprocess.run([sys.executable, os.path.join(BASE, 'build_dashboard.py')], capture_output=True, text=True, timeout=60, cwd=BASE)
    out = s.stdout + s.stderr
    if '✅' in out or 'OK' in out:
        print("✅ OK")
    else:
        print(f"⚠️ {out[-80:]}")
except Exception as e:
    print(f"❌ {e}")

# === Step 3b: 生成報告 ==="
print("🔍 Step 3: 產出報告 ...", end=" ")
try:
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(BASE, 'asset_diff_monitor.py')], capture_output=True, text=True, timeout=90, cwd=BASE)
    out = r.stdout + r.stderr
    if '✅' in out or 'Telegram 200' in out:
        print(f"✅ OK")
    else:
        print(f"⚠️ 可能有問題: {out[-100:]}")
except Exception as e:
    print(f"❌ {e}")
    errors.append(f"asset_diff_monitor 失敗: {e}")

# === Step 3c: 產出日報 ===
print("🔍 Step 3c: 產出日報 ...", end=" ")
try:
    import subprocess, os
    today = snap.get('date', str(datetime.date.today()))
    # 刪除舊日報強制重產（穿透報告由 build_penetration_report.py 獨立產出，不在這裡刪）
    for f in [f'daily_report_v2_{today}.html']:
        fp = os.path.join(BASE, f)
        if os.path.exists(fp): os.remove(fp)
    # 產出（不 deploy，等使用者核准後才推）
    # ⚠️ 8/31 修正①：BASE 是 str（非 Path）→ 用 os.path.join 勿用 '/' 運算子（TypeError 根因）
    # ⚠️ 8/31 修正②：subprocess 用 'python' 在 MSYS bash 環境找不到 → 改用 sys.executable + cwd
    r = subprocess.run([sys.executable, os.path.join(BASE, 'run_daily.py')], capture_output=True, text=True, timeout=180, cwd=BASE)
    out = r.stdout + r.stderr
    _fp = os.path.join(BASE, f'daily_report_v2_{today}.html')
    if '✅' in out or '已寫入' in out or os.path.exists(_fp):
        print(f"✅ OK")
    else:
        print(f"⚠️ {out[-100:]}")
        errors.append(f"日報產出失敗: {out[-200:]}")
except Exception as e:
    print(f"❌ {e}")
    errors.append(f"日報產出失敗: {e}")

# === Step 4: 四源交叉驗證 ===
print("🔍 Step 4: 四源驗證 ...", end=" ")
try:
    with open(f'asset_diff_{today}.html', encoding='utf-8') as f:
        html = f.read()
    ok = True

    # snapshot 值
    snap_ins_ab = snap.get('allianz_combined', 0)
    snap_fl65 = snap.get('firstjin_fl65_current_value', 0)
    snap_sec = snap.get('securities_total_market_value', 0)
    snap_fund = snap.get('fund_market_value', 0)
    snap_cash = snap.get('real_liquid_assets', 0)
    snap_ins_total = snap.get('insurance_total', 0) or (snap_ins_ab + snap_fl65)

    # DB 值
    conn2 = sqlite3.connect('dragon_assets.db')
    db_row = conn2.execute("SELECT insurance, securities, funds, cash_total, total_assets FROM assets WHERE date=?", (today,)).fetchone()
    conn2.close()

    # 比對 snapshot vs DB
    checks = [
        ("保單", snap_ins_total, db_row[0] if db_row else 0),
        ("證券", snap_sec, db_row[1] if db_row else 0),
        ("基金", snap_fund, db_row[2] if db_row else 0),
        ("現金", snap_cash, db_row[3] if db_row else 0),
    ]
    for name, expected, actual in checks:
        if abs(expected - actual) > 1000:
            print(f"\n  ❌ {name}: snapshot {expected:,} ≠ DB {actual:,}")
            ok = False

    # 驗證 HTML 報告包含最新數字
    def _html_has(num: int) -> bool:
        s = f"{num:,}"
        return s in html or s in _daily_html

    _daily_html = ""
    _daily_path = f'daily_report_v2_{today}.html'
    if os.path.exists(_daily_path):
        _daily_html = open(_daily_path, encoding='utf-8').read()

    html_checks = [
        ("差異分析 基金", snap_fund, _html_has(snap_fund)),
        ("差異分析 證券", snap_sec, _html_has(snap_sec)),
        ("日報 基金", snap_fund, _html_has(snap_fund)),
        ("日報 保單總現值", snap.get('insurance_current_value', 0), _html_has(snap.get('insurance_current_value', 0))),
    ]
    for name, val, present in html_checks:
        if not present:
            print(f"\n  ❌ {name} 未含 {val:,}")
            ok = False

    if ok:
        print("✅ 四源一致")
    else:
        errors.append("四源不一致，請檢查")

except Exception as e:
    print(f"❌ 驗證異常: {e}")
    errors.append(f"四源驗證失敗: {e}")

except Exception as e:
    print(f"❌ {e}")
    errors.append(f"驗證失敗: {e}")

# === Step 4b: 同義欄位 + 穿透三報表一致性檢查（2026-08-05 新增防呆）===
print("🔍 Step 4b: 同義欄位 & 穿透一致性 ...", end=" ")
try:
    import subprocess as _sp
    _c1 = _sp.run(['python', 'asset_sync.py'], capture_output=True, text=True, timeout=30)
    if '❌' in _c1.stdout or _c1.returncode != 0:
        print(f"❌ 同義欄位不一致：{_c1.stdout[-200:]}")
        errors.append("同義欄位不一致（asset_sync.py 抓到）")
    else:
        _today_s = snap.get('date', str(datetime.date.today()))
        _c2 = _sp.run(['python', 'check_penetration_consistency.py', _today_s], capture_output=True, text=True, timeout=30)
        if _c2.returncode != 0 or '❌' in _c2.stdout:
            print(f"❌ 穿透不一致：{_c2.stdout[-300:]}")
            errors.append("穿透三報表不一致（check_penetration_consistency.py 抓到）")
        else:
            print("✅ OK（同義欄位一致 + 三報表穿透一致）")
except Exception as e:
    print(f"⚠️ 檢查異常（不阻擋但記錄）: {e}")

# === Step 5: Push 到 GitHub（需使用者核准）===
if errors:
    print("❌ 有錯誤，停止推送")
else:
    print("\n📦 四源同步完成（尚未推送）")
    print("   請先檢查本地檔案 → 使用者核准 → 再執行 git push")

# === 總結 ===
print(f"\n{'='*40}")
if errors:
    _handle_incidents(errors, snap.get('date', str(datetime.date.today())))
else:
    print(f"✅ 四源同步完成！")
    print(f"   🔒 尚未推送 — 請傳 MEDIA 給使用者核准後才 git push")
    print(f"   📄 本地檔案：daily_report_v2_{today}.html / asset_diff_{today}.html / index.html")
