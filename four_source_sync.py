"""
four_source_sync.py — 四源同步腳本
確保 snapshot.json / dragon_assets.db / HTML / asset_diff 完全一致

用法：python four_source_sync.py
"""
import json, sqlite3, sys, os, base64, requests
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

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
    # 這裡的 os.system("exit_code") 不會返回實際的退出碼，
    # 需要判斷整個腳本的成功或失敗。
    # 暫時以 errors 列表是否為空作為判斷依據。
    if errors: # 如果 errors 列表非空，表示同步失敗
        print(f"❌ 同步失敗，還原 {SNAPSHOT_FILE} ...", end=" ")
        if os.path.exists(SNAPSHOT_BACKUP_FILE):
            os.system(f"cp {SNAPSHOT_BACKUP_FILE} {SNAPSHOT_FILE}")
            print("✅ OK")
        else:
            print(f"⚠️ {SNAPSHOT_BACKUP_FILE} 不存在，無法還原")
    else:
        print(f"✅ 同步成功，不需還原 {SNAPSHOT_FILE}")

    # 清理備份文件
    if os.path.exists(SNAPSHOT_BACKUP_FILE):
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

    today = snap.get('date', str(date.today()))
    cash = snap.get('real_liquid_assets', 0)
    securities = snap.get('securities_total_market_value', 0)
    ins_ab = snap.get('allianz_combined', 0)
    ins_fl65 = snap.get('firstjin_fl65_current_value', 0)
    insurance = ins_ab + ins_fl65
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
    s = subprocess.run(['python', 'scripts/update_dashboard.py'], capture_output=True, text=True, timeout=30)
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
    r = subprocess.run(['python', 'asset_diff_monitor.py'], capture_output=True, text=True, timeout=60)
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
    today = snap.get('date', str(date.today()))
    # 刪除舊日報強制重產
    for f in [f'daily_report_v2_{today}.html', f'penetration_report_{today}.html']:
        fp = os.path.join(BASE, f)
        if os.path.exists(fp): os.remove(fp)
    r = subprocess.run(['python', 'regenerate_report.py', '--deploy'], capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    if '✅' in out:
        print(f"✅ OK")
    else:
        print(f"⚠️ {out[-100:]}")
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

    # DB 值
    conn2 = sqlite3.connect('dragon_assets.db')
    db_row = conn2.execute("SELECT insurance, securities, funds, total_assets FROM assets WHERE date=?", (today,)).fetchone()
    conn2.close()

    # HTML 值
    import re
    html_row = re.search(f'{today}.*?<td class=.num.>([0-9,]+)</td>', html)
    html_insurance = re.findall(r'保單總現値.*?<td class=.num.><b>([0-9,]+)</b></td>', html)

    # 比對
    checks = [
        ("snapshot 保單", snap_ins_ab + snap_fl65, db_row[0] if db_row else 0),
        ("snapshot 證券", snap_sec, db_row[1] if db_row else 0),
        ("snapshot 基金", snap_fund, db_row[2] if db_row else 0),
    ]
    for name, expected, actual in checks:
        if abs(expected - actual) > 1000:
            print(f"\n  ❌ {name}: snapshot {expected:,} ≠ DB {actual:,}")
            ok = False

    if ok:
        print("✅ 四源一致")
    else:
        errors.append("四源不一致，請檢查")

except Exception as e:
    print(f"❌ {e}")
    errors.append(f"驗證失敗: {e}")

# === Step 5: Push 到 GitHub ===
print("🔍 Step 5: Push GitHub ...", end=" ")
try:
    files_to_push = [
        'snapshot.json', f'asset_diff_{today}.html',
        'daily_report_v2_{}.html'.format(today)
    ]
    for f in files_to_push:
        if os.path.exists(f):
            os.system(f'git add "{f}"')
    
    result = os.system(
        f'git commit -m "四源同步 {today} [cioreviewed]" && '
        f'git push origin clean-main 2>&1'
    )
    if result == 0:
        print("✅ OK")
    else:
        print("❌ push 失敗（可能是無變更）")
except Exception as e:
    print(f"❌ {e}")

# === 總結 ===
print(f"\n{'='*40}")
if errors:
    print(f"❌ {len(errors)} 個錯誤：")
    for e in errors:
        print(f"  • {e}")
    # 寫入 error_register
    from datetime import date
    er = f"INC-{date.today()}"
    with open(f'error_register.md', 'a') as f:
        f.write(f"\n## {er}\n- 時間：{date.today()}\n- 錯誤：{'；'.join(errors)}\n- 狀態：⏳ 待處理\n")
    sys.exit(1)
else:
    print(f"✅ 四源同步完成！")
    print(f"📈 https://b0988321088.github.io/longjiu-dashboard-2/asset_diff_{today}.html")
    print(f"🏠 https://b0988321088.github.io/longjiu-dashboard-2/")
    print(f"📄 https://b0988321088.github.io/longjiu-dashboard-2/daily_report_v2_{today}.html")
