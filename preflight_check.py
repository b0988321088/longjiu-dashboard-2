"""
preflight_check.py — 數據更新前檢查腳本
先比對 snapshot / DB / HTML 三源差異，列出待更新項目再同步

用法：
  python preflight_check.py           # 只檢查，不動任何檔案
  python preflight_check.py --sync    # 檢查後跑 four_source_sync.py（需使用者核准）
"""
import json, sqlite3, os, re, sys

BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

print("=" * 50)
print("🔍 數據更新前檢查 — preflight check")
print("=" * 50)

issues = []

# 1. 讀 snapshot
snap = json.load(open('snapshot.json', encoding='utf-8'))
today = snap.get('date', '?')

print(f"\n📅 日期：{today}")
print(f"📋 snapshot 關鍵數字：")
print(f"   保單 A+B:      {snap.get('allianz_combined', 0):>12,}")
print(f"   第一金 FL65:   {snap.get('firstjin_fl65_current_value', 0):>12,}")
print(f"   保單合計:      {(snap.get('allianz_combined', 0) + snap.get('firstjin_fl65_current_value', 0)):>12,}")
print(f"   證券:          {snap.get('securities_total_market_value', 0):>12,}")
print(f"   基金:          {snap.get('fund_market_value', 0):>12,}")
print(f"   現金:          {snap.get('real_liquid_assets', 0):>12,}")

# 2. 讀 DB
conn = sqlite3.connect('dragon_assets.db')
db_row = conn.execute("SELECT insurance, securities, funds, cash_total, total_assets FROM assets WHERE date=?", (today,)).fetchone()
conn.close()

if db_row:
    db_ins, db_sec, db_fund, db_cash, db_total = db_row
    print(f"\n🗄️  DB ({today})：")
    print(f"   保單:          {db_ins:>12,}")
    print(f"   證券:          {db_sec:>12,}")
    print(f"   基金:          {db_fund:>12,}")
    print(f"   現金:          {db_cash:>12,}")
    print(f"   總資產:        {db_total:>12,}")

    # 比對差異
    snap_ins = snap.get('allianz_combined', 0) + snap.get('firstjin_fl65_current_value', 0)
    snap_sec = snap.get('securities_total_market_value', 0)
    snap_fund = snap.get('fund_market_value', 0)
    snap_cash = snap.get('real_liquid_assets', 0)

    diffs = []
    if abs(snap_ins - db_ins) > 1000:
        diffs.append(f"保單 snapshot={snap_ins:,} ≠ DB={db_ins:,}")
    if abs(snap_sec - db_sec) > 1000:
        diffs.append(f"證券 snapshot={snap_sec:,} ≠ DB={db_sec:,}")
    if abs(snap_fund - db_fund) > 1000:
        diffs.append(f"基金 snapshot={snap_fund:,} ≠ DB={db_fund:,}")
    if abs(snap_cash - db_cash) > 1000:
        diffs.append(f"現金 snapshot={snap_cash:,} ≠ DB={db_cash:,}")

    if diffs:
        print(f"\n❌ {len(diffs)} 個差異待同步：")
        for d in diffs:
            print(f"   • {d}")
        issues.extend(diffs)
    else:
        print(f"\n✅ snapshot 與 DB 一致")

else:
    print(f"\n⚠️  DB 無 {today} 資料，需新增")

# 3. 檢查關鍵值合理性
print(f"\n🔎 合理性檢查：")

snap_fl65 = snap.get('firstjin_fl65_current_value', 0)
if snap_fl65 < 100000:
    print(f"   ⚠️ 第一金 FL65 值異常偏低：{snap_fl65:,}")
    issues.append(f"FL65 偏低")

snap_ab = snap.get('allianz_combined', 0)
if snap_ab < 5000000:
    print(f"   ⚠️ 安聯 A+B 異常：{snap_ab:,}")
    issues.append(f"安聯偏低")

snap_total = snap_ins + snap_sec + snap_fund + snap_cash
if snap_total < 10000000:
    print(f"   ⚠️ 總流動資產偏低：{snap_total:,}")
    issues.append(f"總資產偏低")

if snap_total > 50000000:
    print(f"   ⚠️ 總流動資產異常高：{snap_total:,}（可能含不動產）")
    issues.append(f"總資產偏高（可能含不動產）")

# 4. 檢查緊急應變深色背景
html_files = [f for f in os.listdir('.') if f.startswith('daily_report') and f.endswith('.html')]
if html_files:
    latest = max(html_files)
    with open(latest, encoding='utf-8') as f:
        content = f.read()
    if '#1e293b' in content or '#e2e8f0' in content:
        print(f"   ⚠️ {latest} 含深色背景（#1e293b），需改為白底")
        issues.append("深色背景")

# 5. 建議
print(f"\n{'='*50}")
if issues:
    print(f"⚠️ 發現 {len(issues)} 個問題：")
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")
    print(f"\n建議：修正後再跑同步")
else:
    print(f"✅ 無異常，可安全同步")

# 6. --sync 模式（需使用者核准後執行）
if "--sync" in sys.argv:
    print(f"\n{'='*50}")
    print("🚀 執行 four_source_sync.py ...")
    os.system('python four_source_sync.py')
