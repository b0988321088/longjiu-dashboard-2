# -*- coding: utf-8 -*-
"""build_investment_performance.py — 投資績效月報（2026-09-04 建立，9/4 使用者裁示）

核心：每月一個乾淨的「投資績效」主數字，借貸帳面徹底分離。
  投資績效(月) = 真實市值變化(剔除當月新增投入) + 配息實收 − 投資利息 − 申購手續費

口徑鐵則：
  · 借貸不創造淨值：轉貸撥款買資產 = 資產/負債同步增加 → 列「資金調度」，不計績效
  · 市值變化 = 月底投資市值 − 月初投資市值 − 當月新增投入本金（申購/買入）
  · 非常態收入（專案）獨立列示，不混入投資績效

資料源（自動優先）：
  dragon_assets.db assets 表：securities+funds+insurance 每月起訖
  snapshot.json：dividend_records（當月配息實收）、fund_purchase_fees（手續費）

校正檔（investment_performance_adjust.json，每月申購本金寫這裡）：
  {"2026-08": {"新增投入": 12000000, "市值變化": 235000, "配息": 139000,
               "利息": 42000, "手續費": 15000, "專案收入": 332342, "備註": "..."}}

db 無月初基準的月份（如 2026-07，系統 7/19 才開始追蹤）→ 需校正檔帶入，否則無法算整月。

用法：
  python build_investment_performance.py            # 預設最近完整月
  python build_investment_performance.py 2026-08    # 指定 YYYY-MM
"""
import json, sys, sqlite3, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ADJ_FILE = BASE / "investment_performance_adjust.json"


def db_asset_on(db, date):
    r = db.execute(
        "SELECT date, securities, funds, insurance FROM assets "
        "WHERE date <= ? ORDER BY date DESC LIMIT 1", (date,)).fetchone()
    return r


def main():
    today = datetime.date.today()
    if len(sys.argv) > 1:
        ym = sys.argv[1]
        y, m = int(ym[:4]), int(ym[5:7])
    else:
        prev = today.replace(day=1) - datetime.timedelta(days=1)
        y, m = prev.year, prev.month

    month_start = datetime.date(y, m, 1)
    month_end = (datetime.date(y, m + 1, 1) - datetime.timedelta(days=1)) if m < 12 else datetime.date(y + 1, 1, 1) - datetime.timedelta(days=1)
    prev_end = month_start - datetime.timedelta(days=1)
    mk = f"{y:04d}-{m:02d}"

    adj = {}
    if ADJ_FILE.exists():
        adj = json.loads(ADJ_FILE.read_text(encoding="utf-8"))
    a = adj.get(mk, {}) or {}

    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(str(BASE / "dragon_assets.db"))
    end_row = db_asset_on(db, month_end.isoformat())
    start_row = db_asset_on(db, prev_end.isoformat())
    db.close()

    # ── 自動：投資市值起訖 ──
    auto_mv_chg = None
    start_note = ""
    if end_row:
        end_mv = end_row[1] + end_row[2] + end_row[3]
        if start_row:
            start_mv = start_row[1] + start_row[2] + start_row[3]
            auto_mv_chg = end_mv - start_mv
            start_note = f"{start_row[0]}"
        else:
            start_note = f"（db 自 {end_row[0]} 起，無月初基準）"

    # ── 校正檔優先（月報審查值：市值變化=已剔除新增投入的真實值），其次自動 ──
    if "市值變化" in a:
        pure_mv = a["市值變化"]               # 真實市值變化（校正檔已剔除投入）
        extra = a.get("新增投入", 0)           # 僅供顯示參考
        mv_chg_total = pure_mv + extra         # 帳面總變化（顯示用）
    elif auto_mv_chg is not None:
        mv_chg_total = auto_mv_chg
        extra = a.get("新增投入", 0)
        pure_mv = mv_chg_total - extra         # 真實市值變化（自動模式需扣投入）
    else:
        print(f"⚠️ {mk}: 無 db 月初基準亦無校正檔 → 無法算投資績效")
        print("  請在 investment_performance_adjust.json 填 {月份:{市值變化, 新增投入, 配息, 利息, 手續費}}")
        return
    div = a.get("配息")
    if div is None:
        dr = (snap.get("dividend_records") or {}).get(mk, {}) or {}
        div = sum(v for v in dr.values() if isinstance(v, (int, float))) if dr else 0
    interest = a.get("利息", 0)
    fees = a.get("手續費")
    if fees is None:
        fees = sum(v for k, v in (snap.get("fund_purchase_fees") or {}).items()
                   if str(k)[:7] == mk and isinstance(v, (int, float)))
    project = a.get("專案收入", 0)

    perf = pure_mv + div - interest - fees

    # ── 輸出 ──
    L = []
    L.append(f"📊 投資績效月報 {y:04d}-{m:02d}")
    L.append("=" * 44)
    L.append(f"📈 投資市值（證券+基金+保單）")
    L.append(f"   帳面變化 {mv_chg_total:>12,.0f}")
    L.append(f"   − 新增投入 {extra:>12,.0f}")
    L.append(f"   ＝ 真實市值變化 {pure_mv:>+12,.0f}")
    L.append(f"💰 配息實收      {div:>+12,.0f}")
    L.append(f"💸 投資利息      {-interest:>+12,.0f}")
    L.append(f"🧾 申購手續費    {-fees:>+12,.0f}")
    if project:
        L.append(f"📦 專案收入(非常態) {project:>+12,.0f}  ← 另計不混入")
    L.append("=" * 44)
    L.append(f"🎯 投資績效（月）= {perf:+,.0f}  ＝  {(perf/10000):+.1f} 萬")
    L.append("=" * 44)
    L.append(f"口徑：借貸不計（資產/負債同步）；配息為當月實收；市值含未實現損益")
    print("\n".join(L))


if __name__ == "__main__":
    main()
