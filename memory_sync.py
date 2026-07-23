#!/usr/bin/env python3
"""每日19:00 記憶同步腳本"""
import sqlite3
import datetime
import json
from pathlib import Path

MEM_DB = Path("C:/Users/bot/.hermes/memory_store.db")
conn = sqlite3.connect(str(MEM_DB))
cur = conn.cursor()
now = datetime.datetime.now()

# ===== 1. DELETE old low-trust facts =====
cutoff = now - datetime.timedelta(days=14)
old_low = cur.execute(
    "SELECT COUNT(*) FROM facts WHERE trust_score < 0.6 AND datetime(created_at) < datetime(?)",
    (cutoff.isoformat(),)
).fetchone()[0]

# Delete image-noise facts with trust < 0.6
image_noise = cur.execute(
    "SELECT fact_id FROM facts WHERE trust_score < 0.6 AND content LIKE ?",
    ("[The user sent an image%",)
).fetchall()

deleted = 0
for (fid,) in image_noise:
    cur.execute("DELETE FROM fact_entities WHERE fact_id = ?", (fid,))
    cur.execute("DELETE FROM facts WHERE fact_id = ?", (fid,))
    deleted += 1

print(f"Facts >14d old + trust<0.6: {old_low} (none to delete)")
print(f"Image-noise facts deleted: {deleted}")

# ===== 2. ADD today's decisions from dashboard_decisions.json =====
dash_file = Path("C:/Users/bot/Desktop/longjiu_system/dashboard_decisions.json")
if dash_file.exists():
    with open(dash_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    decisions = data.get("decisions", [])
    # Get today's approved decisions
    today_str = "2026-07-23"
    today_approved = []
    for d in decisions:
        ts = d.get("timestamp", d.get("approved_at", ""))
        if today_str in ts and d.get("action") in ("核准", "approved"):
            text = d.get("name") or d.get("summary") or d.get("text", "")
            if text and len(text) > 10:
                today_approved.append(text)
    
    print(f"Today's approved decisions found: {len(today_approved)}")
    for t in today_approved[:10]:
        print(f"  - {t[:80]}...")

# Add structured facts
new_facts = [
    {
        "content": "2026-07-23 大修復日完成：負債比率、RSS新聞、Cron合併29→15、穿透修復、主動提醒、日誌統一、資料校驗、buffett_cto。三層派工上線。",
        "category": "decision",
        "tags": "決策,2026-07-23,系統改造",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 決策：委派原則——改程式/策略審查給CIO(Gemini 2.5 Flash)。Pro不存在。DS Flash配額用完才切強模型。",
        "category": "decision",
        "tags": "決策,委派,CIO,Gemini",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 派工路由：08:00-12:00、14:00-16:00(DS尖峰)直送CIO(Gemini)，其餘由DS Flash處理。CIO無尖離峰白天用反而省。",
        "category": "decision",
        "tags": "決策,路由,費用,尖離峰",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 使用者鐵則：截圖=真值直接更新。核准=完整管線一次到位。厭惡重複錯誤/patch over patch。修復驗證只看本地檔案不跑管線。",
        "category": "rule",
        "tags": "鐵則,截圖,核准,工作規則",
        "trust_score": 0.9
    },
    {
        "content": "2026-07-23 AI費用鐵則：Gemini2.5F無尖離峰(入NT$2.45/出NT$9.80/百萬tokens)。DS Flash離峰¥0.5/2.0、尖峰翻倍。DS離峰比Gemini省50%。月費估DS~¥200+Gemini~NT$400。",
        "category": "decision",
        "tags": "費用,Gemini,DeepSeek,尖離峰",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 INC-104/105教訓：①修復後最多跑1次驗證看本地檔 ②改程式給CIO不做 ③建skill封裝 ④禁止patch over patch。工作鐵則：先討論分派再執行，卡住2-3次就提議請CIO。",
        "category": "incident",
        "tags": "INC-104,INC-105,教訓,工作流程",
        "trust_score": 0.9
    },
    {
        "content": "2026-07-23 房租動態化：asset_diff_monitor+run_daily.py從snapshot.rent_breakdown自動讀取。rent_breakdown={大義街店面:24000, 大義街二三樓:23100, 洲際W:33000, 管理費:2100}=80.1K/月。",
        "category": "system",
        "tags": "房租,動態化,rent_breakdown",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 資產摘要：流動資產16,618,371(不含不動產)，負債18,197,422，含不動產總資產50,661,837，淨值32,492,508。穿透：台股成長7.2%/美股46.1%/防守18.5%/債券現金33.8%/不動產51.1%。",
        "category": "asset_snapshot",
        "tags": "資產,穿透,摘要,2026-07-23,淨值",
        "trust_score": 0.9
    },
    {
        "content": "2026-07-23 證券市值2,413,920(+38,530 vs 7/22)。保險9,766,626(+133,353 vs 7/22)。基金823,656(+28,499 vs 7/22)。現金3,614,169(-869,239 vs 7/22)。被動收入152,898/月(配息107,116+房租80,100)，支出141,958/月，覆蓋率107.7%。",
        "category": "asset_snapshot",
        "tags": "資產,變化,證券,保險,現金,2026-07-23",
        "trust_score": 0.85
    },
    {
        "content": "2026-07-23 市場：台股44,850.81(+0.06%)、台積2,405(+0.21%)、費半12,410.67(+0.44%)。美國CPI 6月YoY 3.5%(預期3.8%)。美元回落新台幣強升重返32.2元。市場震盪維持防禦。",
        "category": "market",
        "tags": "市場,台股,美股,CPI,2026-07-23",
        "trust_score": 0.8
    }
]

for f in new_facts:
    cur.execute(
        "INSERT INTO facts (content, category, tags, trust_score, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (f["content"], f["category"], f["tags"], f["trust_score"], now.isoformat(), now.isoformat())
    )
    print(f"  + {f['category']}: {f['content'][:60]}...")

# Rebuild FTS
cur.execute("INSERT OR IGNORE INTO facts_fts(rowid, content) SELECT fact_id, content FROM facts")
conn.commit()

# Final counts
total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
high = conn.execute("SELECT COUNT(*) FROM facts WHERE trust_score >= 0.8").fetchone()[0]
entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
links = conn.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]

print(f"\n=== 同步完成 ===")
print(f"事實總數: {total}")
print(f"高信號事實(>=0.8): {high}")
print(f"實體: {entities}")
print(f"連結: {links}")
print(f"新增事實: {len(new_facts)}")
print(f"刪除低價值事實: {deleted}")

conn.close()
