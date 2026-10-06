"""
mb_extract.py — Moneybook ZIP 自動解壓+校準
上傳 ZIP 後執行：python mb_extract.py /path/to/Moneybook_明細_20260727.zip

自動：
  1. 解壓 ZIP（AES 加密，密碼從 env 讀取）
  2. 解析帳戶 CSV → 現金餘額
  3. 對比 snapshot 現金值
  4. 如有差異，建議更新
"""
import sys, os, csv, json, pyzipper

BASE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT = f'{BASE}/snapshot.json'

def get_password():
    """從 .env 讀取 Moneybook ZIP 密碼。

    憑證不得硬編碼在程式裡（2026-10-06 資安 remediation 第 1 步）。
    來源優先序：行程環境變數 → Hermes .env（repo 外，憑證正本）→ repo .env。
    未設定時明確報錯，不得有任何硬編碼退路。
    """
    v = os.environ.get('MONEYBOOK_ZIP_PASSWORD', '').strip()
    if not v:
        home = os.environ.get('HERMES_HOME') or os.path.join(
            os.path.expanduser('~'), 'AppData', 'Local', 'hermes')
        for p in (os.path.join(home, '.env'), os.path.join(BASE, '.env')):
            if not os.path.exists(p):
                continue
            for line in open(p, encoding='utf-8', errors='ignore'):
                if line.strip().startswith('MONEYBOOK_ZIP_PASSWORD='):
                    v = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
            if v:
                break
    if not v:
        raise SystemExit(
            '❌ 未設定 MONEYBOOK_ZIP_PASSWORD：請寫進 Hermes .env（憑證不得硬編碼在程式裡）')
    return v

def extract(zip_path, out_dir):
    with pyzipper.AESZipFile(zip_path, 'r') as zf:
        pw = get_password()
        zf.pwd = pw.encode()
        files = zf.namelist()
        for f in files:
            zf.extract(f, out_dir)
        return files

def parse_account(csv_path):
    total = 0
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                val = float(row.get('餘額', row.get('金額', 0)))
                total += val
            except: pass
    return total

def main():
    if len(sys.argv) < 2:
        print('用法：python mb_extract.py /path/to/Moneybook_*.zip')
        sys.exit(1)
    
    zip_path = sys.argv[1]
    if not os.path.exists(zip_path):
        print(f'❌ 找不到檔案：{zip_path}')
        sys.exit(1)
    
    out = f'{BASE}/tmp_mb_extract'
    os.makedirs(out, exist_ok=True)
    
    print('📦 解壓 Moneybook ZIP...')
    files = extract(zip_path, out)
    for f in files:
        print(f'  ✅ {f}')
    
    # 找帳戶 CSV
    acct_csv = [f for f in files if '帳戶' in f]
    if acct_csv:
        full_path = f'{out}/{acct_csv[0]}'
        cash = parse_account(full_path)
        print(f'\n💰 Moneybook 現金：{cash:,.0f}')
        
        # 對比 snapshot
        snap = json.load(open(SNAPSHOT))
        snap_cash = snap.get('real_liquid_assets', 0)
        diff = cash - snap_cash
        if abs(diff) > 1000:
            print(f'⚠️ 差異 {diff:+,.0f}（snapshot={snap_cash:,} vs MB={cash:,}）')
            print(f'   建議：python lj.py fix real_liquid_assets={int(cash)}')
        else:
            print(f'✅ 與 snapshot 一致（{snap_cash:,}）')
    
    print(f'\n📁 解壓目錄：{out}')

if __name__ == '__main__':
    main()
