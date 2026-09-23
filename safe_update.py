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
import json, os, subprocess, sys, datetime

PENDING_FILE = 'pending_update.json'
SNAPSHOT_FILE = 'snapshot.json'
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)

# === 合理範圍檢查 ===
RANGES = {
    'allianz_combined': (7_000_000, 8_500_000),    # 安聯A+B
    # 2026-09-23 INC-242b：原鍵名 allianz_a_value／allianz_b_value 是 legacy 帳面鍵
    # （無報表讀取、亦不在 asset_sync.SYNONYM_GROUPS）→ 走這扇門更新「保單A/B」會被靜默吸收
    # （5 個 canonical 鍵全部停在舊值）。改指向報表實際讀取的 canonical 鍵。
    'allianz_policy_a_value': (4_500_000, 5_500_000),  # 安聯A（canonical：allianz_policy_a 群組）
    'allianz_policy_b_value': (2_200_000, 3_200_000),  # 安聯B（canonical：allianz_policy_b 群組）
    'firstjin_fl65_current_value': (1_800_000, 2_200_000),  # 第一金FA81聯博
    # 2026-09-23 INC-242b v2（CIO F2）：原上限 3,000,000 已低於真值 3,006,770 → 正確更新被擋
    'securities_total_market_value': (2_000_000, 4_500_000),  # 證券
    # 2026-09-23 INC-242b：原 (600_000, 900_000) 是 8 月前的基金總值區間 → 現值 12.7M 會被判超範圍擋下
    'fund_market_value': (11_000_000, 14_000_000),   # 基金（國泰直購＋鉅亨）
    # 2026-09-23 INC-242b v2（CIO F2 同型）：現金口徑 9/13 定案後為台幣活存 866,818
    # （MMF/外幣另計），原下限 2,500,000 會擋掉每一次正常更新
    'real_liquid_assets': (300_000, 4_500_000),      # 現金（含未來賣 MMF 回流情境）
}

LABELS = {
    'allianz_combined': '安聯保單A+B',
    'allianz_policy_a_value': '保單A',
    'allianz_policy_b_value': '保單B',
    'firstjin_fl65_current_value': '第一金FA81聯博',
    'securities_total_market_value': '證券市值',
    'fund_market_value': '基金市值',
    'real_liquid_assets': '現金',
}

def load_snapshot():
    return json.load(open(SNAPSHOT_FILE, encoding='utf-8'))

def save_snapshot(snap):
    json.dump(snap, open(SNAPSHOT_FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)  # INC-184：snapshot canonical=1

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
        print("\n  ⚠️  注意事項：")
        for w in warnings:
            print(f"    {w}")
    
    if errors:
        print("\n  ❌  錯誤（已阻止）：")
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
    print("  核准後執行：python safe_update.py --apply")
    print(f"{'='*55}")

def apply_changes(snap, changes):
    """套用變更：寫入 key，並把**新值**同步到它所屬的同義群組全部成員。

    2026-09-23 INC-242b v2（CIO 第二輪 REJECT 的 MUST）：
    不可改用 `asset_sync.sync_snapshot_keys()` —— 它的 anchor 是「群組名鍵」本身
    （`val = snap.get(master)`），群組名鍵不存在時 fallback 到清單第一個非 None 鍵。
    對 `allianz_policy_a`（群組名鍵不存在 → fallback 命中 legacy 的 `allianz_a`）以及
    `securities_total`／`funds_total`／`cash_total`（群組名鍵存在、但仍是**舊值**）而言，
    它會把剛套用的新值**回退成舊值**，而 do_apply 已先印 ✅ 成功
    → 實測 7 個 RANGES 鍵有 5 個「假成功」。故改為「以新值為準、往外覆蓋整個群組」。
    legacy 鍵（無讀者、語意不明）一律拒寫，避免更新被靜默吸收。
    """
    from asset_sync import SYNONYM_GROUPS, LEGACY_KEYS
    # 2026-09-23 INC-242b v2 複審（CIO M1／S3）：先全數驗證、再動 snapshot，避免
    # 中途拋錯時把已處理的鍵留在記憶體（雖然 do_apply 會先 exit，不落檔）。
    # ① 同一群組在 changes 只允許出現一次：兩鍵同群組且新值不同時，
    #    下面「往外覆蓋」會變成後寫者勝、先寫者被靜默丟棄，而 do_apply 仍為
    #    兩個鍵各印一次 ✅（日誌與落地值不一致）→ fail-closed 拒寫。
    # ② 未登錄任何同義群組的鍵 → 只寫單鍵、家族不同步（INC-242 的原始失效模式）
    #    → 印警告，讓下一個新增 RANGES 鍵的人先登錄群組。
    seen_group = {}
    for key, c in changes.items():
        if key in LEGACY_KEYS:
            raise ValueError(f"{key} 是 legacy 鍵（{LEGACY_KEYS[key]}）→ 請改用 canonical 鍵")
        for _master, members in SYNONYM_GROUPS.items():
            if key in members:
                if _master in seen_group and seen_group[_master][1] != c['new']:
                    raise ValueError(
                        f"同義群組 {_master} 同時出現兩個鍵且新值不同："
                        f"{seen_group[_master][0]}={seen_group[_master][1]:,} vs {key}={c['new']:,}"
                        " → 拒絕套用（同群組請只留一個鍵）")
                seen_group[_master] = (key, c['new'])
                break
        else:
            print(f"  ⚠️ {key} 未登錄於任何同義群組 → 只寫單鍵、家族不會同步"
                  "（新增 RANGES 鍵時請先登錄 asset_sync.SYNONYM_GROUPS）")

    for key, c in changes.items():
        new = c['new']
        snap[key] = new
        for _master, members in SYNONYM_GROUPS.items():
            if key in members:
                for _k in members:
                    snap[_k] = new
                break
    return snap


def validate_ranges(changes):
    """合理範圍檢查（--plan 與 --apply 共用）。

    2026-09-23 INC-242b v2 複審（CIO M1）：範圍原本只在 do_plan 檢查，do_apply 拿到
    pending_update.json 就直接套用 → 一份過期計畫（repo 內 2026-07-30 的
    fund_market_value=699,855）會被 v2 的新廣播行為灌進整個同義家族五鍵。
    凡寫入路徑都必須 fail-closed，過期 pending 一律拒套用。
    """
    errs = []
    for key, c in changes.items():
        if key not in RANGES:
            continue
        lo, hi = RANGES[key]
        v = c.get('new')
        if not isinstance(v, (int, float)) or v < lo or v > hi:
            errs.append(f"{LABELS.get(key, key)}：{v} 超出合理範圍 [{lo:,} ~ {hi:,}]")
    return errs


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
    # 2026-09-23 INC-242b v2 複審（CIO M1）：範圍檢查先前只在 --plan，--apply 會直接
    # 套用 pending_update.json（repo 內躺著 2026-07-30 的舊計畫 fund_market_value=699,855）
    # → 補上寫入路徑的 fail-closed 重驗，過期 pending 一律拒套用。
    _range_errs = validate_ranges(changes)
    if _range_errs:
        print("=" * 55)
        for _e in _range_errs:
            print(f"  ❌ {_e}")
        print(f"  ⛔ 待套用變更未通過範圍檢查（pending 可能已過期，"
              f"generated_at={pending.get('generated_at')}）→ 不套用，請重跑 --plan")
        sys.exit(1)

    print("  🚀 套用變更中...")
    print("=" * 55)

    snap = load_snapshot()
    try:
        snap = apply_changes(snap, changes)
    except ValueError as _e:
        print(f"  ❌ 拒絕套用：{_e}")
        sys.exit(1)
    for key, c in changes.items():
        print(f"  ✅ {c['label']}:  {c['new']:,}（已同步同義群組）")

    # 更新日期
    today = datetime.date.today().strftime('%Y-%m-%d')
    snap['date'] = today
    snap['last_calibrated'] = f"{today}T{datetime.datetime.now().strftime('%H:%M:%S')}"

    save_snapshot(snap)
    print("\n  ✅ snapshot.json 已更新")

    # 自動四源同步
    print("\n  🔄 執行四源同步...")
    ret = os.system('python four_source_sync.py')
    
    if ret != 0:
        print(f"\n  ❌ 四源同步失敗（exit={ret}）")
        sys.exit(1)

    # CIO 審查（INC-138 原則：未過審不 commit、不 push）
    print("\n  🔍 CIO 審查...")
    try:
        _cio = subprocess.run([sys.executable, os.path.join(BASE, 'cio_review.py')],
                              capture_output=True, text=True, timeout=120, cwd=BASE)
        if (_cio.stdout or '').strip():
            print(_cio.stdout.strip())
        cio_ret = _cio.returncode
    except Exception as _ce:
        print(f"  ⚠️  CIO 審查執行失敗: {_ce}")
        cio_ret = 1
    if cio_ret != 0:
        # 2026-09-14：舊版只印警告照推（等於閘門空轉）→ 改成硬擋，與 regenerate_report.py 一致
        print(f"\n  ⛔ CIO 審查未通過（exit={cio_ret}）→ 不 commit、不 push。修正資料後重跑 --apply。")
        sys.exit(1)

    # P2（2026-09-14）：改走 RECORD 通道（原為自打 [cioreviewed]）
    print("\n  📤 Git commit + push...")
    os.system('git add snapshot.json')
    os.system(f'git commit -m "safe_update {today}" 2>&1')
    # 2026-09-14：紀錄＋推送統一走 auto_push.py（範圍紀錄覆蓋／重試 3 次／遠端 sha 驗證）。
    # 舊版只 `git push origin clean-main` 且完全不看回傳碼 → main 沒同步、失敗也當成功。
    _ap = subprocess.run([sys.executable, os.path.join(BASE, 'auto_push.py'),
                          '--script', 'safe_update.py'], cwd=BASE,
                         capture_output=True, text=True, timeout=600)
    print(((_ap.stdout or '') + (_ap.stderr or '')).strip()[-300:])
    if _ap.returncode != 0:
        print(f"  ⛔ 未推送上線（rc={_ap.returncode}）")
        sys.exit(1)
    
    pending['applied'] = True
    pending['applied_at'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    save_pending(pending)
    print("\n  ✅ 全部完成！")

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
