#!/usr/bin/env python3
"""error_log_summary.py — 解析 ERROR_LOG.md，產出 INC 摘要供 memory 使用"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
ERROR_LOG = BASE / "ERROR_LOG_20260710.md"
OUTPUT = BASE / "error_summary_cache.txt"

if not ERROR_LOG.exists():
    print("❌ ERROR_LOG.md 不存在")
    exit(1)

text = ERROR_LOG.read_text(encoding="utf-8")

# 解析 INC 區塊
incs = re.findall(
    r"(INC-\d+)\s*[-:：]\s*(.*?)(?=\n(?:INC-|\Z))",
    text + "\n",
    re.DOTALL
)

summary_lines = []
for inc_id, desc in incs:
    # 取第一行做摘要
    first_line = desc.strip().split("\n")[0][:80]
    # 抓根因
    root_cause = ""
    m = re.search(r"根因[：:]\s*(.+?)(?:\n|$)", desc)
    if m:
        root_cause = m.group(1).strip()[:60]
    
    if root_cause:
        summary_lines.append(f"{inc_id}：{first_line}（根因：{root_cause}）")
    else:
        summary_lines.append(f"{inc_id}：{first_line}")

summary = "\n".join(summary_lines)
OUTPUT.write_text(summary, encoding="utf-8")
print(f"✅ ERROR_LOG 摘要：{len(summary_lines)} 條 INC")
for line in summary_lines:
    print(f"  {line}")
