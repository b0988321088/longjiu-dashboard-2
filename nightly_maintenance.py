"""
龍九夜間自動整理腳本 — 每天 22:30 執行
1. 資料庫整理 (vacuum + 清理舊資料)
2. 今日決策檢討
3. 列出明日優先改善清單
4. 通知 Telegram
"""
import json, os, sqlite3, shutil
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LONGJIU = Path(os.path.expanduser("~/Desktop/龍九系統"))
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# ── 1. 資料庫整理 ──
def cleanup_db():
    results = []
    db_path = LONGJIU / "dragon_assets.db"
    if not db_path.exists():
        return ["❌ db 不存在"]
    
    try:
        db = sqlite3.connect(str(db_path))
        old_size = db_path.stat().st_size
        
        # Vacuum 壓縮
        db.execute("VACUUM")
        new_size = db_path.stat().st_size
        saved = old_size - new_size
        
        # 清理超過 30 天的舊記錄
        db.execute("DELETE FROM assets WHERE date < date('now', '-30 days')")
        db.execute("DELETE FROM liabilities WHERE date < date('now', '-30 days')")
        db.execute("DELETE FROM income WHERE date < date('now', '-30 days')")
        
        db.commit()
        db.close()
        
        results.append(f"✅ db 壓縮: {old_size/1024:.0f}KB → {new_size/1024:.0f}KB (省 {saved/1024:.0f}KB)")
    except Exception as e:
        results.append(f"⚠️ db 整理失敗: {e}")
    
    return results


# ── 2. 清理 Hunter logs（保留最近 10 筆）──
def cleanup_hunter_logs():
    results = []
    hunter_dir = LONGJIU / "hunter_logs"
    if not hunter_dir.exists():
        return ["ℹ️ 無 hunter_logs 目錄"]
    
    files = sorted(hunter_dir.glob("intel_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
    keep = 10  # 保留最近 10 筆
    deleted = 0
    for f in files[keep:]:
        f.unlink()
        deleted += 1
    
    if deleted:
        results.append(f"✅ 清理 hunter_logs: 刪除 {deleted} 個舊檔，保留 {keep} 筆")
    else:
        results.append(f"ℹ️ hunter_logs: {len(files)} 筆，無需清理")
    
    return results


# ── 3. 今日決策檢討 ──
def review_decisions():
    results = []
    dec_file = LONGJIU / "dashboard_decisions.json"
    if not dec_file.exists():
        return ["ℹ️ 無決策記錄"]
    
    try:
        d = json.loads(dec_file.read_text(encoding="utf-8"))
        decisions = d.get("decisions", [])
        today = date.today().isoformat()
        
        today_decs = [dec for dec in decisions if dec.get("approved_at", "")[:10] == today or dec.get("timestamp", "")[:10] == today]
        
        if today_decs:
            results.append(f"📋 今日決策 ({len(today_decs)} 項)：")
            for dec in today_decs[-5:]:
                name = dec.get("text", dec.get("name", dec.get("id", "?")))[:60]
                action = dec.get("action", dec.get("status", "?"))
                results.append(f"  {action} {name}")
        else:
            results.append("📋 今日無新決策")
        
        # Pending
        pending = d.get("pending_decisions", [])
        if pending:
            results.append(f"⏳ Pending ({len(pending)} 項)：")
            for p in pending:
                results.append(f"  ⏸️ {p.get('text', p.get('id','?'))[:60]}")
    except Exception as e:
        results.append(f"⚠️ 決策讀取失敗: {e}")
    
    return results


# ── 5. db 自動備份 ──
def backup_db():
    results = []
    BACKUP_DIR = Path(os.path.expanduser("~/龍九備份"))
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    for fname in ["dragon_assets.db", "snapshot.json", "dashboard_decisions.json"]:
        src = LONGJIU / fname
        dst = BACKUP_DIR / f"{today}_{fname}"
        if src.exists():
            import shutil
            shutil.copy2(str(src), str(dst))
            results.append(f"✅ {fname} → backup/{today}_{fname}")
    # 保留最近 30 天
    for f in sorted(BACKUP_DIR.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)[30:]:
        f.unlink()
    return results


# ── 6. 缺失檢討與技能建議 ──
def gaps_analysis():
    """檢視今日問題，建議新增技能或改善"""
    results = []
    today = date.today().isoformat()
    
    # 1. 檢查 cron 錯誤
    results.append("🔄 Cron 健康檢查：")
    hunter_dir = LONGJIU / "hunter_logs"
    if hunter_dir.exists():
        recent = sorted(hunter_dir.glob("intel_*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
        if recent:
            results.append(f"  ✅ Hunter intel: {len(recent)} 筆")
    
    # 2. 決策模式分析
    dec_file = LONGJIU / "dashboard_decisions.json"
    if dec_file.exists():
        d = json.loads(dec_file.read_text(encoding="utf-8"))
        decisions = d.get("decisions", [])
        recent_decs = [dec for dec in decisions if dec.get("approved_at", "")[:10] >= (date.today() - __import__('datetime').timedelta(days=7)).isoformat()]
        
        # 統計核准 vs 延後
        approved = sum(1 for dec in recent_decs if dec.get("action") == "核准" or "核准" in str(dec.get("status","")))
        deferred = sum(1 for dec in recent_decs if "延後" in str(dec.get("action","")) or "延後" in str(dec.get("status","")))
        results.append(f"\n📊 本週決策統計：核准 {approved} / 延後 {deferred}")
    
    # 3. 技能建議
    results.append("\n💡 技能改善建議：")
    
    # 檢查是否有未 pin model 的 cron
    suggestions = []
    try:
        import subprocess, json as _j
        out = subprocess.run(["hermes", "cron", "list", "--json"], capture_output=True, text=True, timeout=10)
        crons = _j.loads(out.stdout) if out.stdout else []
        if isinstance(crons, list):
            no_model = [c.get("name","?") for c in crons if not c.get("model")]
            if no_model:
                suggestions.append(f"⚠️ {len(no_model)} 支 cron 未 pin model（{', '.join(no_model[:3])}）需手動 pin")
    except Exception:
        pass
    
    # 資產穿透分類是否完整
    try:
        import sqlite3
        db = sqlite3.connect(str(LONGJIU / "dragon_assets.db"))
        count = db.execute("SELECT COUNT(*) FROM asset_class").fetchone()[0]
        db.close()
        suggestions.append(f"📦 asset_class 分類表：{count} 筆分類，新增標的時記得加入")
    except Exception:
        pass
    
    if suggestions:
        results.extend(f"  {s}" for s in suggestions)
    else:
        results.append("  ✅ 系統狀態良好，無需新增技能")
    
    return results
def tomorrow_priorities():
    today = date.today()
    
    # 自動判斷明日應辦事項
    priorities = []
    
    # 8/14 Notion 扣款提醒（如果接近）
    if today.month == 8 and today.day >= 7 or (today.month == 7 and today.day >= 28):
        priorities.append("🔴 Notion 訂閱 8/14 扣款 US$12 - 確認方案")
    
    # 月底房租待收
    if today.day >= 25:
        priorities.append("🟡 確認大義街23樓 21,000 + 管理費 2,100 入帳")
    
    # 信用卡繳款
    cc_schedule = [(22, "玉山 3,176"), (27, "台新 1,000")]
    for day, name in cc_schedule:
        if today.day <= day <= today.day + 3:
            priorities.append(f"🟡 {name} 信用卡繳款截止")
    
    # 機會子彈監控
    priorities.append("🟢 監控台股單週跌幅，距 ±10% 觸發線")
    
    return priorities or ["✅ 無緊急事項"]


# ── Telegram 通知 ──
def tg_send(text):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    try:
        import requests
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
    except Exception:
        pass


# ══════════════════════════════════════
if __name__ == "__main__":
    lines = [f"🌙 龍九夜間整理 {date.today().isoformat()}", "=" * 30, ""]
    
    lines.append("📦 資料庫整理：")
    lines.extend("  " + r for r in cleanup_db())
    lines.append("")
    
    lines.append("🗑️ 舊檔清理：")
    lines.extend("  " + r for r in cleanup_hunter_logs())
    lines.append("")
    
    lines.append("📋 今日決策檢討：")
    lines.extend("  " + r for r in review_decisions())
    lines.append("")
    
    lines.append("💾 db 備份：")
    lines.extend("  " + r for r in backup_db())
    lines.append("")
    
    lines.append("🔍 缺失檢討與技能建議：")
    lines.extend("  " + r for r in gaps_analysis())
    lines.append("")
    
    lines.append("📌 明日優先改善：")
    for p in tomorrow_priorities():
        lines.append(f"  {p}")
    
    text = "\n".join(lines)
    print(text)
    tg_send(text)
