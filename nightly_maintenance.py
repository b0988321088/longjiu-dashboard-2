"""
龍九夜間自動整理腳本 — 每天 22:30 執行
1. 資料庫整理 (vacuum + 清理舊資料)
2. 今日決策檢討
3. 列出明日優先改善清單
4. 通知 Telegram
"""
import json, os, sqlite3
from datetime import date, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LONGJIU = Path(os.path.expanduser("~/Desktop/longjiu_system"))
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
        if not isinstance(d, dict):
            d = {"decisions": d if isinstance(d, list) else []}
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
                # 2026-08-24 修正：dashboard_decisions 用 action 欄位（非 text/id）
                results.append(f"  ⏸️ {p.get('action', p.get('text', p.get('id','?')))[:60]}")
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
        if not isinstance(d, dict):
            d = {"decisions": d if isinstance(d, list) else []}
        decisions = d.get("decisions", [])
        recent_decs = [dec for dec in decisions if dec.get("approved_at", "")[:10] >= (date.today() - __import__("datetime").timedelta(days=7)).isoformat()]
        
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
def _load_snapshot():
    return json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))


def _rent_due_windows(snap):
    """從 rent_received_records 推每項的歷史入帳日窗口。

    2026-11-03 修正（使用者指證：租金有固定入帳時間，卻每天被列為「明日優先改善」）：
      原邏輯只看「本月應收 - 本月已收 > 0」就列入優先，未考慮約定入帳日，
      導致 11/03（店面 1 日已收、其餘約定 18–28 日）每天誤報。
    回傳 {項目: (最早日, 最晚日, 樣本數)}，取最近 6 期。
    """
    from collections import defaultdict
    hist = defaultdict(list)
    for d, items in (snap.get("rent_received_records") or {}).items():
        if not isinstance(items, dict):
            continue
        try:
            day = int(str(d).split("-")[2])
        except (IndexError, ValueError):
            continue
        for k in items:
            hist[k].append(day)
    out = {}
    for k, days in hist.items():
        days = sorted(days)[-6:]
        out[k] = (min(days), max(days), len(days))
    return out


def rent_status(snap):
    """回傳 (actions, infos)。只有「已過約定入帳窗口仍未收」才算待辦。"""
    today = date.today()
    ym = today.strftime("%Y-%m")
    rb = (snap.get("rent_receivable_by_month") or {}).get(ym) or (snap.get("rent_breakdown") or {})
    got = {}
    for d, items in (snap.get("rent_received_records") or {}).items():
        if not str(d).startswith(ym):      # 只算當月
            continue
        if items and isinstance(items, dict):
            for k, v in items.items():
                got[k] = got.get(k, 0) + v
        elif isinstance(items, (int, float)):
            got["其他"] = got.get("其他", 0) + items
    win = _rent_due_windows(snap)
    due, recv = sum(rb.values()), sum(got.values())
    missing = {k: v for k, v in rb.items() if got.get(k, 0) < v}

    actions, infos = [], []
    overdue, notyet, inwin = [], [], []
    for k, v in missing.items():
        lo, hi, n = win.get(k, (None, None, 0))
        if lo is None:
            notyet.append(f"{k} {v:,}（無歷史入帳日，人工確認）")
        elif today.day > hi:
            overdue.append(f"{k} {v:,}（約定 {lo}–{hi} 日，已逾期 {today.day - hi} 天）")
        elif today.day < lo:
            notyet.append(f"{k} {v:,}（約定 {lo}–{hi} 日）")
        else:
            inwin.append(f"{k} {v:,}（約定 {lo}–{hi} 日，窗口內待入帳）")

    if overdue:
        actions.append(f"🔴 租金逾期未收：{' + '.join(overdue)}")
    if inwin:
        infos.append(f"🟡 租金窗口內待入帳：{' + '.join(inwin)}")
    if notyet:
        infos.append(f"ℹ️ 租金未到入帳日：{' + '.join(notyet)}")

    # 與 snapshot.rent_monthly_gap 交叉驗證（單一真值）
    gap = float(snap.get("rent_monthly_gap") or 0)
    if abs(sum(missing.values()) - gap) > 1:
        actions.append(f"⚠️ 租金待收合計 {sum(missing.values()):,} 與 snapshot.rent_monthly_gap {gap:,.0f} 不一致（待查）")

    if not missing:
        infos.append(f"✅ 租金已全收（本月應收 {due:,}／已收 {recv:,}）")
    else:
        infos.append(f"租金進度：本月應收 {due:,}／已收 {recv:,}／待收 {sum(missing.values()):,}")
    return actions, infos


def tw_market_read(snap):
    """實算台股加權單日與近 5 交易日跌幅，門檻讀 thresholds 單日急跌煞車。

    2026-11-03 修正（使用者指證「監控結果是什麼」）：原本是寫死字串
    「監控台股單週跌幅，距 ±10% 觸發線」——沒有計算，且 thresholds_2026_0915
    並無「單週 ±10%」這條門檻（±10 是 DAA 動態偏移上限，屬配置偏移非跌幅）。
    """
    import urllib.request
    th = (snap.get("thresholds_2026_0915") or {}).get("風險煞車", {}) or {}
    brake = float(th.get("單日急跌_pct") or 3)
    try:
        u = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=1mo&interval=1d"
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.load(resp)
        r = d["chart"]["result"][0]
        px = [(t, c) for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        if len(px) < 6:
            raise ValueError("樣本不足")
        last, prev, wk = px[-1][1], px[-2][1], px[-6][1]
        d1 = (last / prev - 1) * 100
        w5 = (last / wk - 1) * 100
        asof = datetime.utcfromtimestamp(px[-1][0]).strftime("%m/%d")
        head = f"台股加權 {last:,.2f}（{asof}，{d1:+.2f}%）｜近 5 交易日 {w5:+.2f}%"
        notes = []
        if abs(d1) >= brake:
            notes.append(
                f"🔴 {head}｜已觸發單日急跌 {brake:g}% 煞車（thresholds_2026_0915.風險煞車）：只回報不動作，暫緩加減碼"
            )
        else:
            notes.append(f"🟢 {head}｜單日急跌煞車門檻 {brake:g}%（未觸發）")
        notes.append("ℹ️ 單週跌幅僅供觀察；系統無「單週 ±10%」門檻，加減碼授權仍看 US30Y 閘門與單日急跌煞車")
        return notes
    except Exception as e:
        return [f"⚠️ 台股報價抓取失敗（{type(e).__name__}），本日不顯示跌幅，不以舊 snapshot 代替"]


def tomorrow_priorities():
    """回傳 (actions, infos)：actions 才是真正要處理的事。"""
    snap = _load_snapshot()
    actions, infos = rent_status(snap)
    for line in tw_market_read(snap):
        (actions if line.startswith("🔴") else infos).append(line)
    return actions, infos


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
    
    _acts, _infos = tomorrow_priorities()
    lines.append("📌 明日優先改善：")
    if _acts:
        lines.extend(f"  {p}" for p in _acts)
    else:
        lines.append("  ✅ 無需動作（租金未到入帳窗口／無其他待辦）")
    if _infos:
        lines.append("")
        lines.append("📎 現況資訊：")
        lines.extend(f"  {p}" for p in _infos)
    
    text = "\n".join(lines)
    print(text)
    tg_send(text)
