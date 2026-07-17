#!/usr/bin/env python3
"""holographic_daily_check.py - 每日壓力測試監控腳本"""

from pathlib import Path
import sqlite3
import time

BASE = Path("C:/Users/bot/.hermes")
MEM = BASE / "memory_store.db"
REPORT = Path("C:/Users/bot/Desktop/龍九系統/PRESSURE_TEST_LOG.md")


def check():
    conn = sqlite3.connect(str(MEM))
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    high_trust = conn.execute("SELECT COUNT(*) FROM facts WHERE trust_score >= 0.8").fetchone()[0]
    entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
    fact_entities = conn.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]

    query = "信用卡"
    start = time.time()
    conn.execute(
        "SELECT fact_id FROM facts WHERE LOWER(content) LIKE ? OR LOWER(tags) LIKE ?",
        ("%" + query + "%", "%" + query + "%"),
    ).fetchall()
    latency = (time.time() - start) * 1000

    conn.close()

    today = time.strftime("%Y-%m-%d")
    achieved = total >= 20
    entry = "\\n## " + today + "\\n"
    entry += "- 總事實: " + str(total) + "\\n"
    entry += "- 高信號事實: " + str(high_trust) + "\\n"
    entry += "- 實體: " + str(entities) + "\\n"
    entry += "- 連結: " + str(fact_entities) + "\\n"
    entry += "- LIKE 延遲: " + ("{:.1f}".format(latency)) + "ms\\n"
    entry += "- 目標達成: " + ("✅" if achieved else "❌") + "\\n"

    with open(REPORT, "a", encoding="utf-8") as f:
        f.write(entry)

    return total, high_trust, latency


if __name__ == "__main__":
    total, high_trust, latency = check()
    print("壓力測試簽到: facts={}, high_trust={}, latency={:.1f}ms".format(total, high_trust, latency))
