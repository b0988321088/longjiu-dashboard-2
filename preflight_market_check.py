#!/usr/bin/env python3
"""preflight_market_check：檢查日報 market 區塊日期是否為今日"""
import re
import sys
from pathlib import Path

def check(report_path: str):
    p = Path(report_path)
    if not p.exists():
        # 嘗試同名 .html
        p_html = p.with_suffix('.html')
        if p_html.exists():
            p = p_html
        else:
            print(f"[PREFLIGHT FAIL] 檔案不存在：{report_path}")
            sys.exit(1)

    text = p.read_text(encoding='utf-8')
    today = "2026-07-18"
    # 找到所有 2026-07-XX 日期
    dates = set(re.findall(r'2026-07-\d+', text))
    if today not in dates:
        print(f"[PREFLIGHT FAIL] 今日日期 {today} 未出現於日報 market 區塊")
        print(f"[PREFLIGHT FAIL] 發現日期：{sorted(dates)}")
        sys.exit(1)
    print(f"[PREFLIGHT OK] 日報 market 日期為今日：{today}")

if __name__ == "__main__":
    check(sys.argv[1] if len(sys.argv) > 1 else f"daily_report_v2_{__import__('datetime').date.today().isoformat()}.md")
