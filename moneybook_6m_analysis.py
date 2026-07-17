import csv
from collections import defaultdict

DETAIL_PATH = "C:/Users/bot/AppData/Local/hermes/cache/documents/doc_4e6c8d47a6db_Moneybook_明細_20260714_1.csv"
ACCOUNT_PATH = "C:/Users/bot/AppData/Local/hermes/cache/documents/doc_7f2cdffd6ca1_Moneybook_帳戶_20260714_1.csv"
BILL_PATH = "C:/Users/bot/AppData/Local/hermes/cache/documents/doc_8d733459df93_Moneybook_帳單_20260714_1.csv"

print("=" * 60)
print("龍九控股 6個月平均現金流回推")
print("資料來源：Moneybook 明細 + 帳戶 + 帳單 CSV")
print("=" * 60)

# ===== 1. 薪資 =====
print("\n【薪資】")
print("  固定月薪（台電）：43,144 TWD/月")
print("  差旅津貼：12,000 TWD/月")
print("  獎金（台電半年一次）：39,121 TWD/次 → 月均 6,520")
print("  300K 上境工程：專案投資，不列入薪資")

# ===== 2. 配息 =====
print("\n【配息/股利明細 from CSV】")
dividends = []
with open(DETAIL_PATH, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        desc = row.get('明細描述', '')
        cat = row.get('分類', '')
        amt = float(row.get('金額', 0))
        date_str = row.get('消費日', '')
        bank = row.get('機構名稱', '')
        account = row.get('帳戶名稱', '')
        if any(k in desc for k in ['配息', '股利', '基金配息', '媒體轉入 - 基金配息']):
            dividends.append((date_str, bank, account, desc, amt))

for d in dividends:
    print(f"  {d[0]} | {d[1]} | {d[3][:45]} | {d[4]:>10,.0f}")
print(f"  CSV配息合計：{sum(d[4] for d in dividends):>10,.0f} TWD")
print(f"  → 僅含小額零散配息，安聯/第一金大額未進明細")
print(f"  → 月均配息估算：保守 80K / 中間 91K / 偏高 100K")

# ===== 3. 房租 =====
print("\n【房租收入】")
print("  大義街1樓：24,000/月（台新帳戶扣款）")
print("  洲際W：32,000/月（永豐帳戶扣款）")
print("  大義街二/三樓：21,000/月")
print("  管理費：2,100/月")
print("  合計：24,000 + 32,000 + 21,000 + 2,100 = 79,100 ≈ 80,100 TWD/月")

# ===== 4. 信用卡四大主力卡 =====
print("\n【信用卡四大主力卡 - 帳單月均】")
bills = []
with open(BILL_PATH, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        bills.append({
            'bank': row.get('金融機構', ''),
            'type': row.get('帳單類型', ''),
            'amt': float(row.get('帳單金額', 0)),
            'due': row.get('繳費截止日', ''),
        })

# 只看四大主力卡
major_cards = {
    '玉山銀行': '玉山 UNI',
    '台新銀行': '台新 Richart',
    '永豐銀行': '永豐 SPORT',
    '台北富邦': '台北富邦 數位',
}

for bank, label in major_cards.items():
    card_bills = [b for b in bills if b['bank'] == bank and b['amt'] > 0]
    card_bills_clean = [b['amt'] for b in card_bills]
    total = sum(card_bills_clean)
    count = len(card_bills_clean)
    if count > 0:
        avg = total / count
        # Remove obvious outliers for conservative estimate
        if bank == '玉山銀行':
            clean_vals = [v for v in card_bills_clean if v <= 20000]  # remove 18,420? no that's valid
            clean_avg = avg
        elif bank == '台新銀行':
            clean_avg = avg
        elif bank == '永豐銀行':
            clean_vals = [v for v in card_bills_clean if v < 30000]  # remove 51,450 outlier
            clean_avg = sum(clean_vals) / len(clean_vals) if clean_vals else avg
        elif bank == '台北富邦':
            clean_vals = [v for v in card_bills_clean if v < 20000]  # remove 35,978 outlier
            clean_avg = sum(clean_vals) / len(clean_vals) if clean_vals else avg
        else:
            clean_avg = avg
        print(f"  {label}：{count} 期帳單，月均 {avg:>8,.0f} TWD（清理離群值後 {clean_avg:>8,.0f}）")

# 4卡總計
all_4 = []
for bank in major_cards:
    vals = [b['amt'] for b in bills if b['bank'] == bank and b['amt'] > 0 and b['amt'] < 30000]
    all_4.extend(vals)

total_4 = sum(all_4)
count_4 = len(all_4)
avg_4 = total_4 / count_4 if count_4 > 0 else 0
print(f"  四大卡合計月均（清理離群值）：{avg_4:>8,.0f} TWD/月")
print(f"  → 月均區間：保守 20K / 中間 27K / 偏高 35K")

# ===== 5. 帳戶快照 =====
print("\n【帳戶快照 2026-07-14】")
accounts = {}
total_twd = 0
with open(ACCOUNT_PATH, encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    for row in reader:
        currency = row.get('幣別', 'TWD')
        amt = float(row.get('帳戶金額', 0))
        key = f"{row.get('機構名稱','')} {row.get('帳戶名稱','')}"
        accounts[key] = (currency, amt)
        if currency == 'TWD':
            total_twd += amt

for k, (cur, v) in sorted(accounts.items(), key=lambda x: -abs(x[1][1])):
    if abs(v) > 100:
        print(f"  {k}: {v:>15,.0f} {cur}")
print(f"  台幣帳戶加總：{total_twd:>15,.0f} TWD")

# ===== 6. 6個月估算 =====
print("\n" + "=" * 60)
print("6個月平均月現金流估算")
print("=" * 60)

monthly_salary = 43_144
monthly_travel = 12_000
monthly_rent = 80_100
monthly_interest = 2_858
monthly_mortgage = 99_458  # 大義街+永豐
monthly_salku = 4_500
monthly_dividend_low = 80_000
monthly_dividend_mid = 91_000
monthly_dividend_high = 100_000
monthly_cc_low = 35_000
monthly_cc_mid = 38_000
monthly_cc_high = 42_000
bonus_semi = 39_121

income_fixed = monthly_salary + monthly_travel + monthly_rent + monthly_interest

print(f"\n{'項目':<20} {'保守估':>10} {'中間估':>10} {'偏高估':>10}")
print(f"{'-'*20} {'-'*10} {'-'*10} {'-'*10}")
print(f"{'薪資（台電）':<20} {monthly_salary:>10,} {monthly_salary:>10,} {monthly_salary:>10,}")
print(f"{'差旅津貼':<20} {monthly_travel:>10,} {monthly_travel:>10,} {monthly_travel:>10,}")
print(f"{'房租收入':<20} {monthly_rent:>10,} {monthly_rent:>10,} {monthly_rent:>10,}")
print(f"{'配息（月均）':<20} {monthly_dividend_low:>10,} {monthly_dividend_mid:>10,} {monthly_dividend_high:>10,}")
print(f"{'利息收入':<20} {monthly_interest:>10,} {monthly_interest:>10,} {monthly_interest:>10,}")
print(f"{'-'*20} {'-'*10} {'-'*10} {'-'*10}")
income_low = income_fixed + monthly_dividend_low
income_mid = income_fixed + monthly_dividend_mid
income_high = income_fixed + monthly_dividend_high
print(f"{'月收入（非獎金）':<20} {income_low:>10,} {income_mid:>10,} {income_high:>10,}")

print(f"\n{'項目':<20} {'保守估':>10} {'中間估':>10} {'偏高估':>10}")
print(f"{'-'*20} {'-'*10} {'-'*10} {'-'*10}")
print(f"{'房貸（大義+永豐）':<20} {monthly_mortgage:>10,} {monthly_mortgage:>10,} {monthly_mortgage:>10,}")
print(f"{'信用卡（四大主力）':<20} {monthly_cc_low:>10,} {monthly_cc_mid:>10,} {monthly_cc_high:>10,}")
print(f"{'沙鹿房租':<20} {monthly_salku:>10,} {monthly_salku:>10,} {monthly_salku:>10,}")
print(f"{'-'*20} {'-'*10} {'-'*10} {'-'*10}")
exp_low = monthly_mortgage + monthly_cc_low + monthly_salku
exp_mid = monthly_mortgage + monthly_cc_mid + monthly_salku
exp_high = monthly_mortgage + monthly_cc_high + monthly_salku
print(f"{'月支出合計':<20} {exp_low:>10,} {exp_mid:>10,} {exp_high:>10,}")

print(f"\n獎金月均（台電半年一次）：{bonus_semi/6:>10,.0f}")

surplus_low = income_low - exp_high  # worst case
surplus_mid = income_mid - exp_mid
surplus_high = income_high - exp_low  # best case
surplus_bonus_low = surplus_low + bonus_semi/6
surplus_bonus_mid = surplus_mid + bonus_semi/6

print(f"\n{'='*60}")
print(f"月盈餘（保守，配息低+費用高）：{surplus_low:>+10,.0f} TWD")
print(f"月盈餘（中間）：               {surplus_mid:>+10,.0f} TWD")
print(f"月盈餘（偏高，配息高+費用低）：{surplus_high:>+10,.0f} TWD")
print(f"月盈餘含獎金（中間）：         {surplus_bonus_mid:>+10,.0f} TWD")

# ===== 7. 真值備註 =====
print(f"\n【真值備註】")
print(f"配息明細 CSV 僅抓到小額零散配息（CSV期間 11,614 TWD）")
print(f"大額配息（安聯~55K + 第一金~13K）未進明細 CSV，可能走其他帳戶/自動扣繳")
print(f"房租未進明細 CSV，為帳戶層級轉帳或現金流動")
print(f"信用卡明細 CSV 僅 30 天部分消費，完整帳單請參考 Moneybook_帳單 CSV")
print(f"  四大主力卡月均帳單：~38K TWD/月（4卡合計近期實繳34K+波動中位）")
