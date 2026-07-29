"""
safe_update.py — 安全更新腳本
強制兩階段：先 --plan → 使用者核准 → 再 --apply

用法：
  python safe_update.py --plan key=value key=value ...
  # → 顯示計劃變更，寫入 pending_update.json
  # → 把摘要給使用者確認

  python safe_update.py --apply
  # → 套用 pending_update.json 的變更
  # → 自動四源同步 + Git push
"""
import json, os, sys, datetime

PENDING_FILE = 'pending_update.json'
SNAPSHOT_FILE = 'snapshot.json'
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# === 合理範圍檢查 ===
RANGES = {
    'allianz_combined': (7_000_000, 8_500_000),    # 安聯A+B
    'allianz_a_value': (4_500_000, 5_500_000),      # 安聯A
    'allianz_b_value': (2_200_000, 3_200_000),      # 安聯B
    'firstjin_fl65_current_value': (1_800_000, 2_200_000),  # 第一金FL65
    'securities_total_market_value': (2_000_000, 3_000_000),  # 證券
    'fund_market_value': (600_000, 900_000),         # 基金
    'real_liquid_assets': (2_500_000, 4_500_000),    # 現金
}

LABELS = {
    'allianz_combined': '安聯保單A+B',
    'allianz_a_value': '保單A',
    'allianz_b_value': '保單B',
    'firstjin_fl65_current_value': '第一金FL65',
    'securities_total_market_value': '證券市值',
    'fund_market_value': '基金市值',
    'real_liquid_assets': '現金',
}

def load_snapshot():
    return json.load(open(SNAPSHOT_FILE, encoding='utf-8'))

def save_snapshot(snap):
    json.dump(snap, open(SNAPSHOT_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def load_pending():
    if os.path.exists(PENDING_FILE):
        return json.load(open(PENDING_FILE, encoding='utf-8'))
    return {}

def save_pending(data):
    json.dump(data, open(PENDING_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

def do_plan(args):
    """第一階段：計劃變更，不寫入"""
    snap = load_snapshot()
    changes = {}
    errors = []
    warnings = []

    for arg in args:
        if '=' not in arg:
            errors.append(f"格式錯誤（需 key=value）：{arg}")
            continue
        key, val_str = arg.split('=', 1)
        key = key.strip()
        try:
            val = int(val_str.replace(',', ''))
        except:
            try:
                val = float(val_str.replace(',', ''))
            except:
                errors.append(f"數值錯誤：{val_str}")
                continue

        # 檢查 key 是否在 snapshot 中
        if key not in snap:
            warnings.append(f"⚠️ {key} 不在 snapshot 中，將新增")
        
        old_val = snap.get(key, None)
        
        # 合理性檢查
        if key in RANGES:
            lo, hi = RANGES[key]
            if val < lo or val > hi:
                errors.append(f"❌ {LABELS.get(key, key)}：{val:,} 超出合理範圍 [{lo:,} ~ {hi:,}]")
                continue
        
        label = LABELS.get(key, key)
        if old_val is not None and old_val != val:
            diff = val - old_val
            changes[key] = {
                'label': label,
                'old': old_val,
                'new': val,
                'diff': diff
            }
        elif old_val is None:
            changes[key] = {
                'label': label,
                'old': '無',
                'new': val,
                'diff': '新增'
            }

    # 保單總值檢查
    ab_new = None
    fl65_new = None
    for arg in args:
        if arg.startswith('allianz_combined='):
            ab_new = int(arg.split('=')[1].replace(',', ''))
        if arg.startswith('firstjin_fl65_current_value='):
            fl65_new = int(arg.split('=')[1].replace(',', ''))

    if ab_new is not None and fl65_new is not None:
        total = ab_new + fl65_new
        if total < 8_000_000 or total > 11_000_000:
            warnings.append(f"⚠️ 保單合計 {total:,} 偏離正常範圍（8M~11M）")

    # === 輸出 ===
    print("=" * 55)
    print("  📋 計劃變更一覽")
    print("=" * 55)

    if not changes:
        print("\n  無變更")
    
    for key, c in changes.items():
        if isinstance(c['old'], int):
            print(f"\n  🔄 {c['label']}")
            print(f"     舊值：{c['old']:,}")
            print(f"     新值：{c['new']:,}")
            print(f"     差異：{c['diff']:+,}")
        else:
            print(f"\n  ➕ {c['label']}")
            print(f"     新值：{c['new']:,}")

    if warnings:
        print(f"\n  ⚠️  注意事項：")
        for w in warnings:
            print(f"    {w}")
    
    if errors:
        print(f"\n  ❌  錯誤（已阻止）：")
        for e in errors:
            print(f"    {e}")
        print("\n  → 請修正後重試")
        sys.exit(1)

    # 寫入 pending 檔
    pending = {
        'generated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'changes': changes,
        'errors': errors,
        'warnings': warnings,
        'applied': False
    }
    save_pending(pending)
    
    print(f"\n{'='*55}")
    print(f"  ⏸️  已暫存至 {PENDING_FILE}")
    print(f"  核准後執行：python safe_update.py --apply")
    print(f"{'='*55}")

def do_apply():
    """第二階段：套用變更"""
    pending = load_pending()
    if not pending:
        print("❌ 無待套用的變更")
        sys.exit(1)
    if pending.get('applied'):
        print("❌ 已套用過，不可重複")
        sys.exit(1)

    changes = pending.get('changes', {})
    if not changes:
        print("❌ 無變更內容")
        sys.exit(1)

    print("=" * 55)
    print("  🚀 套用變更中...")
    print("=" * 55)

    snap = load_snapshot()
    for key, c in changes.items():
        snap[key] = c['new']
        print(f"  ✅ {c['label']}:  {c['new']:,}")

    # 更新日期
    today = datetime.date.today().strftime('%Y-%m-%d')
    snap['date'] = today
    snap['last_calibrated'] = f"{today}T{datetime.datetime.now().strftime('%H:%M:%S')}"

    save_snapshot(snap)
    print(f"\n  ✅ snapshot.json 已更新")

    # 自動四源同步
    print(f"\n  🔄 執行四源同步...")
    ret = os.system('python four_source_sync.py')
    
    if ret != 0:
        print(f"\n  ❌ 四源同步失敗（exit={ret}）")
        sys.exit(1)

    # CIO 審查
    print(f"\n  🔍 CIO 審查...")
    cio_ret = os.system('python cio_review.py 2>&1')
    if cio_ret != 0:
        print(f"  ⚠️  CIO 審查有警訊（exit={cio_ret}）— 請手動確認")

    # 強制 commit 加 [cioreviewed]
    print(f"\n  📤 Git push...")
    os.system('git add snapshot.json')
    os.system(f'git commit -m "safe_update {today} [cioreviewed]" 2>&1')
    os.system('git push origin clean-main 2>&1')
    
    pending['applied'] = True
    pending['applied_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    save_pending(pending)
    print(f"\n  ✅ 全部完成！")

def main():
    if len(sys.argv) < 2:
        print("用法：")
        print("  python safe_update.py --plan key=value key=value ...")
        print("  python safe_update.py --apply")
        print()
        print("範例：")
        print("  python safe_update.py --plan allianz_combined=7765339 firstjin_fl65_current_value=1958980")
        sys.exit(1)

    mode = sys.argv[1]
    if mode == '--plan':
        do_plan(sys.argv[2:])
    elif mode == '--apply':
        do_apply()
    else:
        print(f"❌ 未知模式：{mode}")
        sys.exit(1)

if __name__ == '__main__':
    main()
