#!/usr/bin/env python3
"""build_dashboard.py — 儀表板動態注入（2026-08-26 建立）
問題：index_template.html 大量寫死財務值（保單/現金/配息/房租）→ 一鍵更新後儀表板舊值
解法：每次從 snapshot.json 讀真值 → replace 模板寫死值 → 產 index.html
用法：python build_dashboard.py（sync_all 已整合為步驟）
"""
import json, re
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent

def _fmt(n):
    return f"{n:,.0f}"

def main():
    snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    tpl = (BASE / "index_template.html").read_text(encoding="utf-8")

    # ── 從 snapshot 計算真值 ──
    cash = snap.get("cash_total", 0) or 0
    ins = snap.get("insurance_total", 0) or 0
    allianz = snap.get("allianz_combined", 0) or 0
    firstjin = snap.get("firstjin_fl65_current_value", snap.get("firstjin_current_value", 0)) or 0
    cum_div = snap.get("firstjin_cum_dividend", 111513) or 0
    mdb = snap.get("monthly_dividend_breakdown", {}) or {}
    div_ins = mdb.get("insurance", 0) or 0
    div_total = mdb.get("total", 0) or 0
    firstjin_div = mdb.get("firstjin", 0) or 0
    expense = snap.get("monthly_expense", 162781) or 162781
    salary = 39727

    # 租金已收（8 月）
    rent_got = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith("2026-08"):
            if isinstance(v, dict):
                rent_got += sum(x for x in v.values() if isinstance(x, (int, float)))
            elif isinstance(v, (int, float)):
                rent_got += v
    got_total = salary + div_total + rent_got

    # ── replace 模板寫死值（2026-08-26 盤點清單）──
    rep = {
        "9,682,433": _fmt(ins),            # 保單總值
        "7,753,544": _fmt(allianz),        # 安聯 A+B
        "1,928,889": _fmt(firstjin),       # 第一金現值
        "111,513": _fmt(cum_div),          # 第一金累計配息
        "88,507": _fmt(div_ins),           # 保單配息合計
        "25,538": _fmt(firstjin_div),      # 第一金本月領息
        "815,066": _fmt(cash),             # 現金
        "227,372": _fmt(got_total),        # 當月已收合計
        "109,645": _fmt(div_total),        # 配息實收
        "78,000": _fmt(rent_got),          # 租金已收
        "162,781": _fmt(expense),          # 月支出
    }
    # ── 銀行水位（2026-08-26：模板寫死各銀行餘額 → 從 snapshot cash_detail 動態）──
    cd = snap.get("cash_detail", {}) or {}
    taiwan = (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般", 0) or 0) + (cd.get("敦南Richart外幣", 0) or 0)
    rep["499,316"] = _fmt(taiwan)          # 台新合計
    rep["139,446"] = _fmt(cd.get("文心綜活儲存款-薪轉", 177765) or 0)  # 文心薪轉
    rep["97,353"] = _fmt(cd.get("敦南Richart數位一般", 90524) or 0)   # Richart一般
    # 2026-08-28 修正：銀行水位全動態（Moneybook 8/27 帳戶）
    rep["177,599"] = _fmt((cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0))  # 永豐合計
    rep["50,104"] = _fmt(cd.get("臺幣綜存", 40950) or 0)              # 玉山（臺幣綜存）
    rep["20260821_1"] = "20260828_1"       # 資料日期
    hits = 0
    for old, new in rep.items():
        if old in tpl:
            tpl = tpl.replace(old, new)
            hits += 1

    # ── 今日狀態列動態化（2026-08-27：今日 + 近3天 + 下一個；含保單轉換等決策事件）──
    try:
        _evs = json.loads((BASE / "schedule_events.json").read_text(encoding="utf-8"))
        if isinstance(_evs, dict):
            _evs = _evs.get("events", _evs.get("items", []))
        _td = date.today().isoformat()
        _wk = (date.today() + timedelta(days=7)).isoformat()
        _ACT = ("🔴", "📞", "📋", "📡", "🏦", "🔍", "📅")  # 需動作事件前綴
        _today_act = [e for e in _evs if str(e.get("date","")) == _td and str(e.get("item","")).startswith(_ACT)]
        _soon3 = sorted([e for e in _evs if _td < str(e.get("date","")) <= (date.today() + timedelta(days=3)).isoformat() and str(e.get("item","")).startswith(_ACT)],
                        key=lambda x: str(x.get("date","")))
        _next = sorted([e for e in _evs if _td < str(e.get("date","")) <= _wk and str(e.get("item","")).startswith(_ACT)],
                       key=lambda x: str(x.get("date","")))
        _parts = []
        if _today_act:
            for e in _today_act[:2]:
                _parts.append(f"🔴 今日要做：{str(e.get('item',''))[:48]}")
        else:
            _parts.append("🟢 今日無需操作")
        if _soon3:
            _d3 = " ｜ ".join(f"{str(e.get('date',''))[5:]} {str(e.get('item',''))[:26]}" for e in _soon3[:3])
            _parts.append(f"📌 近 3 天：{_d3}")
        if _next:
            _n = next((e for e in _next if str(e.get("date","")) > (date.today() + timedelta(days=3)).isoformat()), None) or _next[0]
            _parts.append(f"⏭ 下一個：{str(_n.get('date',''))[5:]} {str(_n.get('item',''))[:44]}")
        tpl = tpl.replace("__TODAY_STATUS__", "<br>".join(_parts))
        tpl = tpl.replace("__TODAY__", _td)
    except Exception:
        tpl = tpl.replace("__TODAY_STATUS__", "🟢 今日狀態：無需人工操作")
        tpl = tpl.replace("__TODAY__", date.today().isoformat())

    # ── 健康度卡（2026-08-27：共享組件 report_components.render_health_card）──
    try:
        from report_components import render_health_card as _rhc
        tpl = tpl.replace("__HEALTH_CARD__", _rhc(snap))
    except Exception:
        tpl = tpl.replace("__HEALTH_CARD__", "")

    # ── 八大連結動態化（2026-08-26：模板連結寫死 8/21-23 → glob 最新檔名）──
    import glob as _glob
    _link_map = {
        "__ASSET_DIFF__": "asset_diff_*.html",
        "__BUFFETT_MD__": "buffett_cto_report_*.md",
        "__DAILY_REPORT__": "daily_report_v2_*.html",
        "__EMERGENCY__": "emergency_report_*.html",
        "__INDUSTRY_PNG__": "industry_penetration_*.png",
        "__PEN_REPORT__": "penetration_report_*.html",
        "__REBALANCE_DASH__": "rebalance_dashboard_*.html",
        "__REBALANCE_MD__": "rebalance_summary_*.md",
        "__RISK_PNG__": "risk_factor_penetration_*.png",
        "__WEEKLY__": "weekly_report_*.html",
    }
    _link_hits = 0
    for _ph, _pat in _link_map.items():
        if _ph in tpl:
            _fs = sorted(_glob.glob(str(BASE / _pat)))
            if _fs:
                _new = str(_fs[-1]).replace("\\", "/").split("/")[-1]  # Windows glob 回傳 str
                tpl = tpl.replace(_ph, _new)
                _link_hits += 1
            else:
                # 2026-08-27 fallback：找不到檔案 → 指向儀表板首頁（不留死佔位符）
                tpl = tpl.replace(_ph, "index.html")
                _link_hits += 1
    (BASE / "index.html").write_text(tpl, encoding="utf-8")
    print(f"✅ 儀表板注入完成（{hits} 組值 + {_link_hits} 連結動態化）｜現金 {_fmt(cash)} / 保單 {_fmt(ins)} / 配息 {_fmt(div_total)} / 租金 {_fmt(rent_got)}")

if __name__ == "__main__":
    main()
