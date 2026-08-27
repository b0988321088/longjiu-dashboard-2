#!/usr/bin/env python3
"""每日19:00 記憶同步腳本 v2.0 — 動態讀取longjiu_system數據"""
import sqlite3, datetime, json
from pathlib import Path

MEM_DB   = Path("C:/Users/bot/.hermes/memory_store.db")
LONGJIU  = Path("C:/Users/bot/Desktop/longjiu_system")
now      = datetime.datetime.now()
today    = now.strftime("%Y-%m-%d")

conn = sqlite3.connect(str(MEM_DB), timeout=30)
cur = conn.cursor()
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

# ── Schema init ──
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
if not tables:
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS facts (
            fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT DEFAULT '',
            trust_score REAL DEFAULT 0.5,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS entities (
            entity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            entity_type TEXT DEFAULT 'unknown',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS fact_entities (
            fact_id INTEGER REFERENCES facts(fact_id) ON DELETE CASCADE,
            entity_id INTEGER REFERENCES entities(entity_id),
            relationship TEXT DEFAULT 'related_to',
            PRIMARY KEY (fact_id, entity_id)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
            content, content=facts, content_rowid=fact_id
        );
    """)
    conn.commit()
    print("[init] Schema created")

deleted = 0

# ═══ Step 1: Clean old/low-trust facts ═══
cutoff = now - datetime.timedelta(days=14)

# Stale facts (>14d + trust<0.6)
stale = cur.execute(
    "SELECT fact_id FROM facts WHERE trust_score < 0.6 AND datetime(created_at) < datetime(?)",
    (cutoff.isoformat(),)
).fetchall()

# Image noise
image_noise = cur.execute(
    "SELECT fact_id FROM facts WHERE trust_score < 0.6 AND content LIKE ?",
    ("[The user sent an image%",)
).fetchall()

for (fid,) in stale + image_noise:
    cur.execute("DELETE FROM fact_entities WHERE fact_id = ?", (fid,))
    cur.execute("DELETE FROM facts WHERE fact_id = ?", (fid,))
    deleted += 1

conn.commit()
print(f"[1] Cleaned: {len(stale)} stale + {len(image_noise)} noise = {deleted} total")

# ═══ Step 2: Read dragon_assets.db ═══
dragon = sqlite3.connect(str(LONGJIU / "dragon_assets.db"))
try:
    latest = dragon.execute("SELECT * FROM assets ORDER BY rowid DESC LIMIT 1").fetchone()
    cols = [d[1] for d in dragon.execute("PRAGMA table_info(assets)").fetchall()]
    ad = dict(zip(cols, latest)) if latest else {}
finally:
    dragon.close()

db_date    = ad.get("date", "?")
ta         = int(ad.get("total_assets", 0))
mb_cash    = int(ad.get("cash_total", 0))
sec        = int(ad.get("securities", 0))
ins        = int(ad.get("insurance", 0))
fund       = int(ad.get("funds", 0))
print(f"[2] DB latest: {db_date} TA={ta:,} cash={mb_cash:,}")

# ═══ Step 3: Read snapshot.json + asset_diff_history.json ═══
snap = {}
snap_path = LONGJIU / "snapshot.json"
if snap_path.exists():
    snap = json.loads(snap_path.read_text("utf-8"))

history = {}
hist_path = LONGJIU / "asset_diff_history.json"
if hist_path.exists():
    history = json.loads(hist_path.read_text("utf-8"))
    latest_hist = history.get(today) or (list(history.values())[-1] if history else {})
else:
    latest_hist = {}

print(f"[3] snapshot date: {snap.get('date','?')}")

# ═══ Step 4: Read today's decisions ═══
decisions_text = []
data_for_count = {"decisions": []}
dash_file = LONGJIU / "dashboard_decisions.json"
if dash_file.exists():
    data_for_count = json.loads(dash_file.read_text("utf-8"))
    # ⚠️ 相容：可能被寫成純 list（2026-08-27 bug）→ 包回 dict
    if not isinstance(data_for_count, dict):
        data_for_count = {"decisions": data_for_count if isinstance(data_for_count, list) else []}
    for d in data_for_count.get("decisions", []):
        ts = str(d.get("timestamp", "") or d.get("approved_at", ""))
        if today in ts and d.get("source") != "auto":
            text = d.get("summary") or d.get("task") or d.get("name") or d.get("action", "")
            if text and len(text) > 10:
                decisions_text.append(text)
    for d in data_for_count.get("pending_decisions", []):
        if d.get("date") and today in str(d.get("date", "")):
            at = d.get("action", "")
            st = d.get("status", "")
            if at:
                decisions_text.append(f"⏳ {at} — {st}")

print(f"[4] Today's decisions: {len(decisions_text)}")

# ═══ Step 5: Compile & write new facts ═══
new_facts = []

# 5a: Today's decisions
if decisions_text:
    summary = "；".join(decisions_text[:8])
    approved_count = len([d for d in data_for_count.get('decisions', []) if d.get('date')==today and d.get('decision') in ('核准', 'approved')])
    new_facts.append({
        "content": f"{today} 決策摘要：核准{approved_count}筆。{summary}",
        "category": "decision",
        "tags": f"決策,{today},同步",
        "trust_score": 0.85
    })

# 5b: Asset summary from DB
asset_summary = (
    f"{today} 資產摘要："
    f"總資產{ta:,}元，"
    f"證券{sec:,}元，"
    f"保險{ins:,}元，"
    f"基金{fund:,}元，"
    f"現金{mb_cash:,}元"
)
new_facts.append({
    "content": asset_summary,
    "category": "asset_snapshot",
    "tags": f"資產摘要,{today},同步",
    "trust_score": 0.9
})

# 5c: Penetration analysis from snapshot
pen = snap.get("penetration", {})
actual = pen.get("actual_pct", {})
if actual:
    tw  = actual.get("台股市值型成長", 0)
    us  = actual.get("美股市值型成長", 0)
    de  = actual.get("防守型配息", 0)
    bd  = actual.get("債券", 0)
    ca  = actual.get("現金/安全網", 0)
    gaps = pen.get("gaps", {})
    g_tw = gaps.get("台股市值型成長", 0)
    g_us = gaps.get("美股市值型成長", 0)
    pen_fact = (
        f"{today} 穿透分析："
        f"台股{tw:.1f}%/美股{us:.1f}%/防守{de:.1f}%/債券{bd:.1f}%/現金{ca:.1f}%。"
        f"缺口：台股{g_tw:.1f}%/美股{g_us:.1f}%"
    )
    new_facts.append({
        "content": pen_fact,
        "category": "asset_snapshot",
        "tags": f"穿透,資產配置,{today}",
        "trust_score": 0.85
    })

# 5d: Asset changes from history
if latest_hist:
    h_ta  = latest_hist.get("total_assets", 0)
    h_sec = latest_hist.get("securities_market", 0)
    h_ins = latest_hist.get("insurance_current", 0)
    h_cash = latest_hist.get("cash", 0)
    h_fund = latest_hist.get("fund_market", 0)
    h_net = latest_hist.get("net_worth", 0)
    change_fact = (
        f"{today} 資產變化："
        f"總資產{h_ta:,}元(淨值{h_net:,}元)，"
        f"證券{h_sec:,}元，保險{h_ins:,}元，基金{h_fund:,}元，現金{h_cash:,}元"
    )
    new_facts.append({
        "content": change_fact,
        "category": "asset_snapshot",
        "tags": f"資產變化,{today}",
        "trust_score": 0.85
    })

# Write all new facts (INSERT OR IGNORE for UNIQUE constraint)
written = 0
skipped = 0
for f in new_facts:
    try:
        cur.execute(
            "INSERT OR IGNORE INTO facts (content, category, tags, trust_score, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f["content"], f["category"], f["tags"], f["trust_score"],
             now.isoformat(), now.isoformat())
        )
        if cur.rowcount > 0:
            written += 1
            print(f"  + [{f['category']}] {f['content'][:70]}...")
        else:
            skipped += 1
            print(f"  ~ [{f['category']}] duplicate skipped")
    except Exception as e:
        skipped += 1
        print(f"  ! [{f['category']}] error: {e}")
print(f"   → 寫入 {written} 條，跳過 {skipped} 條重複")

conn.commit()

# ═══ Step 6: Rebuild FTS index ═══
try:
    cur.execute("INSERT OR IGNORE INTO facts_fts(rowid, content) SELECT fact_id, content FROM facts")
except Exception:
    print("[FTS] Recreating corrupted index...")
    cur.execute("DROP TABLE IF EXISTS facts_fts")
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    cur.execute("CREATE VIRTUAL TABLE facts_fts USING fts5(content, content=facts, content_rowid=fact_id)")
    cur.execute("INSERT OR IGNORE INTO facts_fts(rowid, content) SELECT fact_id, content FROM facts")
conn.commit()

# ═══ Final stats ═══
total  = cur.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
high   = cur.execute("SELECT COUNT(*) FROM facts WHERE trust_score >= 0.8").fetchone()[0]
ents   = cur.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
links  = cur.execute("SELECT COUNT(*) FROM fact_entities").fetchone()[0]

print(f"\n{'='*40}")
print(f"記憶同步完成 | {today}")
print(f"{'='*40}")
print(f"🗑️  清理：{deleted} 條")
print(f"➕ 新增：{len(new_facts)} 條")
print(f"📊 事實總數：{total}")
print(f"🔵 高信號(>=0.8)：{high}")
print(f"🏷️  實體：{ents}")
print(f"🔗 連結：{links}")

conn.close()
