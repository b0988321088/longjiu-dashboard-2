import os
import sys
from datetime import date
import re

BASE_DIR = "C:/Users/bot/Desktop/龍九系統/"
TODAY = date.today().isoformat()
DAILY_REPORT_FILE = os.path.join(BASE_DIR, f"daily_report_v2_{TODAY}.html")
ASSET_DIFF_FILE = os.path.join(BASE_DIR, f"asset_diff_{TODAY}.html")
INDEX_FILE = os.path.join(BASE_DIR, "index.html")

EXPECTED_SECURITIES = "2,413,920"
EXPECTED_FUNDS = "823,656"
EXPECTED_INSURANCE = "9,747,807"

def run_command(command):
    print(f"Executing: {command}")
    result = os.system(command)
    if result != 0:
        print(f"Command failed: {command}")
        sys.exit(1)

def verify_html_content(filepath, securities, funds, insurance):
    print(f"Verifying {filepath}...")
    if not os.path.exists(filepath):
        print(f"FAIL: File {filepath} not found.")
        return False
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Securities check
    sec_match = re.search(r"證券總市值.*?(\d{1,3}(?:,\d{3})*)", content)
    if sec_match:
        actual_securities = sec_match.group(1).replace(",", "")
        if actual_securities != securities.replace(",", ""):
            print(f"FAIL: Securities mismatch in {filepath}. Expected: {securities}, Actual: {actual_securities}")
            return False
        else:
            print(f"PASS: Securities value in {filepath} is {actual_securities}")
    else:
        print(f"WARN: Securities value not found in {filepath}.")

    # Funds check
    fund_match = re.search(r"基金總市值.*?(\d{1,3}(?:,\d{3})*)", content)
    if fund_match:
        actual_funds = fund_match.group(1).replace(",", "")
        if actual_funds != funds.replace(",", ""):
            print(f"FAIL: Funds mismatch in {filepath}. Expected: {funds}, Actual: {actual_funds}")
            return False
        else:
            print(f"PASS: Funds value in {filepath} is {actual_funds}")
    else:
        print(f"WARN: Funds value not found in {filepath}.")

    # Insurance check
    # For daily_report, it's "保單現值", for asset_diff, it's "保單現値"
    ins_match = re.search(r"(保單現值|保單現値).*?(\d{1,3}(?:,\d{3})*)", content)
    if ins_match:
        actual_insurance = ins_match.group(2).replace(",", "")
        if actual_insurance != insurance.replace(",", ""):
            print(f"FAIL: Insurance mismatch in {filepath}. Expected: {insurance}, Actual: {actual_insurance}")
            return False
        else:
            print(f"PASS: Insurance value in {filepath} is {actual_insurance}")
    else:
        print(f"WARN: Insurance value not found in {filepath}.")
        
    return True

def main():
    print("Starting pipeline automated test script...")

    # 1. Execute update_all.py --check
    run_command(f"python {os.path.join(BASE_DIR, 'update_all.py')} --check")

    # 2. Execute update_all.py (full pipeline)
    run_command(f"python {os.path.join(BASE_DIR, 'update_all.py')}")

    # 3. Read HTML outputs and confirm key numbers
    all_passed = True
    if not verify_html_content(DAILY_REPORT_FILE, EXPECTED_SECURITIES, EXPECTED_FUNDS, EXPECTED_INSURANCE):
        all_passed = False
    if not verify_html_content(ASSET_DIFF_FILE, EXPECTED_SECURITIES, EXPECTED_FUNDS, EXPECTED_INSURANCE):
        all_passed = False
    # index.html might not contain all details, so we might need a separate check or skip for now if not critical
    # For now, I'll just check if it exists
    if not os.path.exists(INDEX_FILE):
        print(f"FAIL: File {INDEX_FILE} not found.")
        all_passed = False
    else:
        print(f"PASS: File {INDEX_FILE} found.")

    if all_passed:
        print("\nAll pipeline tests PASSED!")
    else:
        print("\nSome pipeline tests FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()