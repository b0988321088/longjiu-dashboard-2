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
    # 2026-08-29 修正：配息一律用 dividend_records 當月實收（mdb 是常態預估口徑，
    # 之前用 mdb 覆蓋模板實收值 → 第一金顯示 35,583 常態被標「已入帳」，實收應為 25,538）
    # 2026-09-01 修正：月份動態化（原寫死 2026-08 → 9月仍顯示 8 月配息 138,627）
    import datetime as _dt
    _today_m = _dt.date.today().strftime("%Y-%m")
    _dr = snap.get("dividend_records", {}).get(_today_m, {}) or {}
    firstjin_div = sum(v for k, v in _dr.items() if "第一金" in k and isinstance(v, (int, float))) or 0
    az_div = _dr.get("安聯保單撥回", 0) or 0
    div_ins = az_div + firstjin_div
    div_total = sum(v for k, v in _dr.items() if isinstance(v, (int, float))) or 0
    expense = snap.get("monthly_expense", 162781) or 162781
    # 薪水（當月已收，salary_records 動態）
    salary = 0
    for k, v in (snap.get("salary_records", {}) or {}).items():
        if str(k).startswith(_today_m):
            salary += (v.get("amount", 0) if isinstance(v, dict) else v) or 0

    # 租金已收（當月）
    rent_got = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith(_today_m):
            if isinstance(v, dict):
                rent_got += sum(x for x in v.values() if isinstance(x, (int, float)))
            elif isinstance(v, (int, float)):
                rent_got += v
    got_total = salary + div_total + rent_got

    # ── replace 模板寫死值（2026-08-26 盤點清單）──
    rep = {
        "9,682,433": _fmt(ins),            # 保單總值
        "7,753,544": _fmt(allianz),        # 安聯 A+B
        "2,723,839": _fmt(snap.get("allianz_b", 0) or 0),  # 保單B 現值（2026-08-29 補：漏掉沒替換）
        "1,928,889": _fmt(firstjin),       # 第一金現值
        "111,513": _fmt(cum_div),          # 第一金累計配息
        "88,507": _fmt(div_ins),           # 保單配息合計（實收）
        "25,538": _fmt(firstjin_div),      # 第一金本月領息
        "63,027": _fmt(az_div),            # 安聯本月領息（2026-08-29 補：原寫死舊值）
        "815,066": _fmt(cash),             # 現金
        "772,607": _fmt(cash),             # 現金（2026-08-31 補：8/30 template 值 → 777,767）
        "227,372": _fmt(got_total),        # 當月已收合計（說明欄）
        "199,960": _fmt(got_total),        # 📊 當月已收合計卡片（2026-08-29 補：漏替換 → 舊值 199,960 殘留）
        "109,645": _fmt(div_total),        # 配息實收
        "123,607": _fmt(div_total),        # 配息實收（2026-08-31 補：8/30 template 值 → 138,627）
        "78,000": _fmt(rent_got),          # 租金已收
        "162,781": _fmt(expense),          # 月支出
    }
    # ── 雷達＋本週投資計劃（2026-08-29：模板寫死 8/23 舊版 → 讀 radar_state.json 動態）──
    try:
        import json as _json
        from pathlib import Path as _Path
        _rd_path = _Path(__file__).resolve().parent / "radar_state.json"
        if _rd_path.exists():
            _rd = _json.loads(_rd_path.read_text(encoding="utf-8"))
            _sig = _rd.get("signals", {}) or {}
            _signals_txt = "｜".join(
                f"{k}{v.get('color','')}" for k, v in _sig.items() if v.get("color")
            )
            _pn = _rd.get("policy_notes", {}) or {}
            _policy_txt = ""
            _titles = {"新聞1_華許升息": "華許放鷹（升息）", "新聞2_美委石油協議": "美委石油協議", "新聞3_伊朗戰爭SPR": "伊朗戰爭SPR"}
            for _k, _v in _pn.items():
                if isinstance(_v, dict):
                    _c = _v.get("內容", "")
                    _imp = _v.get("對資產影響", "")
                    _t = _titles.get(_k, _k)
                    if _c:
                        _policy_txt += (("｜" if _policy_txt else "") + f"{_t}：{_imp or _c[:30]}")
                elif isinstance(_v, str) and _v and _k in ("原油綜合判斷", "債券升息敏感度"):
                    _policy_txt += (("｜" if _policy_txt else "") + _v[:45])
            if not _policy_txt:
                _policy_txt = "無重大政策變動"
            # 本週計劃（同 institutional_flow 結論邏輯，精簡版）
            _pen2 = snap.get("penetration", {}).get("actual_pct", {}) or {}
            _dry2 = snap.get("乾粉執行_0926", {}).get("戰術乾粉總額", {}).get("當前", 0)
            _usd2 = snap.get("usd_exposure_monitor", {}).get("current", {}).get("合計", 0)
            _plan = []
            _plan.append(f"台股慢慢買 0050/006208 每週1.5-2萬（缺口 -{10-_pen2.get('台股市值型成長',7.5):.1f}pp）")
            _plan.append("防守合併已足凍結；債券等 US30Y<5.30%")
            _plan.append(f"乾粉 {_dry2/10000:.1f}萬 優先非核心消費（0051 回檔-5%）")
            _plan.append("9/2 保單轉換截止（PIMCO120+M&G80-100+醫療50+黃金30）；8/26已轉80萬 8/30生效")
            if _usd2 > 55:
                _plan.append(f"美元曝險 {_usd2}% 超標→美股減碼")
            _plan.append("9/3 PI→質押350萬還債")
            rep["__RADAR_DATE__"] = _rd.get("last_run", "2026-08-29")[:10]
            rep["__RADAR_SIGNALS__"] = _signals_txt
            rep["__RADAR_PLAN__"] = "｜".join(_plan)
            rep["__RADAR_POLICY__"] = _policy_txt
        else:
            rep["__RADAR_DATE__"] = "2026-08-29"
            rep["__RADAR_SIGNALS__"] = "雷達資料缺（radar_state.json 不存在）"
            rep["__RADAR_PLAN__"] = "待雷達更新"
            rep["__RADAR_POLICY__"] = "無"
    except Exception as _e:
        rep["__RADAR_DATE__"] = "2026-08-29"
        rep["__RADAR_SIGNALS__"] = f"雷達讀取失敗: {_e}"
        rep["__RADAR_PLAN__"] = "待雷達更新"
        rep["__RADAR_POLICY__"] = "無"
    # ── 銀行水位（2026-08-26：模板寫死各銀行餘額 → 從 snapshot cash_detail 動態）──
    cd = snap.get("cash_detail", {}) or {}
    taiwan = (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般", 0) or 0) + (cd.get("敦南Richart外幣", 0) or 0)
    rep["499,316"] = _fmt(taiwan)          # 台新合計
    rep["139,446"] = _fmt(cd.get("文心綜活儲存款-薪轉", 177765) or 0)  # 文心薪轉
    rep["97,353"] = _fmt(cd.get("敦南Richart數位一般", 90524) or 0)   # Richart一般
    # 管理費入帳狀態（2026-08-29：模板寫死「待入帳 0（應收 2,100）」→ 依 rent_received_records 動態）
    _fee = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith("2026-08") and isinstance(v, dict) and "管理費" in v:
            _fee = v["管理費"] or 0
    if _fee > 0:
        rep["<span class=\"text-amber-400\">⏳ 待入帳</span><span class=\"text-slate-300\">管理費</span></div><span class=\"text-xs font-mono text-slate-400\">0 TWD（應收 2,100）</span>"] = \
            f"<span class=\"text-emerald-400\">✅ 已入帳</span><span class=\"text-slate-300\">管理費</span></div><span class=\"text-xs font-mono text-emerald-400 font-bold\">2,100 TWD</span>"
    else:
        rep["<span class=\"text-amber-400\">⏳ 待入帳</span><span class=\"text-slate-300\">管理費</span></div><span class=\"text-xs font-mono text-slate-400\">0 TWD（應收 2,100）</span>"] = \
            f"<span class=\"text-amber-400\">⏳ 待入帳</span><span class=\"text-slate-300\">管理費</span></div><span class=\"text-xs font-mono text-slate-400\">0 TWD（應收 2,100）</span>"
    # 流動性調度 tab 銀行卡（2026-08-29 補：原 6 卡全寫死 → 動態）
    rep["27,738"] = _fmt((cd.get("活期儲蓄存款", 0) or 0) + (cd.get("數位存款帳戶２類", 0) or 0))  # 國泰世華（活期+數位2類）
    rep["44,116"] = _fmt(cd.get("數位活儲", 44116) or 0)             # 台北富邦
    rep["739"] = _fmt(cd.get("Digital Savings Acco", 739) or 0)      # 將來銀行
    rep["458,343"] = _fmt(round((snap.get("monthly_expense", 162781) or 162781) * 3))  # 安全線 3個月支出（162,781×3=488,343）
    rep["20,776"] = _fmt(cd.get("活期儲蓄存款", 0) or 0)              # 國泰明細 活期儲蓄
    rep["6,960"] = _fmt(cd.get("數位存款帳戶２類", 2) or 0)           # 國泰明細 數位2類
    # 2026-08-28 修正：銀行水位全動態（Moneybook 8/27 帳戶）
    rep["177,599"] = _fmt((cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0))  # 永豐合計
    rep["50,104"] = _fmt(cd.get("臺幣綜存", 40950) or 0)              # 玉山（臺幣綜存）
    rep["20260821_1"] = "20260831_1"       # 資料日期（8/31 Moneybook）
    rep["20260829_1"] = "20260831_1"       # 資料日期（2026-08-31 補：8/30 template 殘留 8/29）
    # 現金合計卡「監控卡片合計」（2026-08-29 補：原寫死 799,612 殘留 → 動態算 cash_detail 正數，排除外幣 key）
    _mon = sum(v for k, v in cd.items() if isinstance(v, (int, float)) and v > 0 and "外幣" not in k)
    rep["799,612"] = _fmt(_mon)
    # ── 資產穿透卡五桶市值（2026-08-29 補：快照版 fallback 全部寫死舊值）──
    _ptwd = snap.get("penetration", {}).get("actual_twd", {}) or {}
    _ppct = snap.get("penetration", {}).get("actual_pct", {}) or {}
    _gaps = snap.get("penetration", {}).get("gaps", {}) or {}
    _tgt = snap.get("penetration", {}).get("targets", {}) or {}
    rep["1,889,388"] = _fmt(_ptwd.get("台股市值型成長", 0))        # 台股市值
    rep["11,499,725"] = _fmt(_ptwd.get("美股市值型成長", 0))       # 美股市值
    rep["1,089,462"] = _fmt(_ptwd.get("防守型配息", 0))            # 防守市值
    rep["5,917,259"] = _fmt(_ptwd.get("債券", 0))                  # 債券市值
    rep["5,798,988"] = _fmt(_ptwd.get("現金/安全網", 0))           # 現金市值
    rep["3,735,174"] = _fmt(_ptwd.get("美股市值型成長_科技", 0))   # 科技市值
    rep["7,764,551"] = _fmt(_ptwd.get("美股市值型成長_非科技", 0)) # 非科技市值
    # 科技/非科技文字（⚠️ 必須在市值替換前，因整句 key 含市值數字，市值先被換掉就匹配不到）
    _tch = _ppct.get("美股市值型成長_科技", 0); _ntch = _ppct.get("美股市值型成長_非科技", 0)
    _tech_gap = _tch - 15
    _tech_txt_old = "🔬 科技 14.3%（3,735,174 TWD）｜非科技 29.6%（7,764,551 TWD）｜科技目標 ≤15%（缺口 -0.7pp）"
    _tech_txt_new = f"🔬 科技 {_tch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_科技',0))} TWD）｜非科技 {_ntch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_非科技',0))} TWD）｜科技目標 ≤15%（{'缺口' if _tech_gap<0 else '溢價'} {_tech_gap:+.1f}pp）"
    # 兩階段：先用 temp 佔位保護整句 → 再換市值 → 最後還原整句
    _TECH_PH = "@@TECH_TXT@@"
    tpl = tpl.replace(_tech_txt_old, _TECH_PH)
    rep["@@TECH_TXT@@"] = _tech_txt_new
    _t_act = _ppct.get("台股市值型成長", 0); _t_tgt = _tgt.get("台股市值型目標", 10)
    _t_gap = _t_act - _t_tgt
    _t_col = "text-red-400" if _t_gap < 0 else "text-emerald-400"
    rep["現況 7 / 目標 10 (缺口 -2.8pp)"] = f"現況 {_t_act:.0f} / 目標 {_t_tgt:.0f} ({'缺口' if _t_gap<0 else '溢價'} {_t_gap:+.1f}pp)"
    rep["style=\"width: 7%\"</div>"] = f"style=\"width: {min(_t_act/55*100,100):.0f}%\"</div>"
    rep["style=\"width: -2.8%\"></div>"] = f"style=\"width: {min(max(_t_gap,0)/55*100,100):.0f}%\"></div>"
    _u_act = _ppct.get("美股市值型成長", 0); _u_tgt = _tgt.get("美股市值型目標", 40)
    _u_gap = _u_act - _u_tgt
    rep["現況 44 / 目標 40 (溢價 +3.9pp)"] = f"現況 {_u_act:.0f} / 目標 {_u_tgt:.0f} ({'溢價' if _u_gap>0 else '缺口'} {_u_gap:+.1f}pp)"
    rep["style=\"width: 44%\"></div>"] = f"style=\"width: {min(_u_act/55*100,100):.0f}%\"</div>"
    _d_act = _ppct.get("防守型配息", 0); _d_tgt = _tgt.get("配息型目標", 20)
    _d_gap = _d_act - _d_tgt
    rep["現況 4 / 目標 20 (缺口 -15.8pp)"] = f"現況 {_d_act:.0f} / 目標 {_d_tgt:.0f} ({'缺口' if _d_gap<0 else '溢價'} {_d_gap:+.1f}pp)"
    rep["style=\"width: 4%\"></div>"] = f"style=\"width: {min(_d_act/55*100,100):.0f}%\"</div>"
    rep["style=\"width: -15.8%\"></div>"] = f"style=\"width: {min(max(_d_gap,0)/55*100,100):.0f}%\"></div>"
    _b_act = _ppct.get("債券", 0); _b_tgt = _tgt.get("債券型目標", 25)
    _b_gap = _b_act - _b_tgt
    rep["現況 23 / 目標 25 (盈餘 -2.4pp)"] = f"現況 {_b_act:.0f} / 目標 {_b_tgt:.0f} ({'盈餘' if _b_gap>0 else '缺口'} {_b_gap:+.1f}pp)"
    rep["style=\"width: 23%\"></div>"] = f"style=\"width: {min(_b_act/55*100,100):.0f}%\"</div>"
    _c_act = _ppct.get("現金/安全網", 0); _c_tgt = _tgt.get("現金目標", 5)
    _c_gap = _c_act - _c_tgt
    rep["現況 22 / 目標 5 (盈餘 +17.1pp)"] = f"現況 {_c_act:.0f} / 目標 {_c_tgt:.0f} ({'盈餘' if _c_gap>0 else '缺口'} {_c_gap:+.1f}pp)"
    rep["style=\"width: 22%\"></div>"] = f"style=\"width: {min(_c_act/55*100,100):.0f}%\"</div>"
    # 科技/非科技文字
    _tch = _ppct.get("美股市值型成長_科技", 0); _ntch = _ppct.get("美股市值型成長_非科技", 0)
    _tech_gap = _tch - 15
    rep["🔬 科技 14.3%（3,735,174 TWD）｜非科技 29.6%（7,764,551 TWD）｜科技目標 ≤15%（缺口 -0.7pp）"] = \
        f"🔬 科技 {_tch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_科技',0))} TWD）｜非科技 {_ntch:.1f}%（{_fmt(_ptwd.get('美股市值型成長_非科技',0))} TWD）｜科技目標 ≤15%（{'缺口' if _tech_gap<0 else '溢價'} {_tech_gap:+.1f}pp）"
    # 安聯配息卡（8/29 補：舊 62,969 → 76,931）
    rep["62,969"] = _fmt(az_div)
    # 保單A 現值（8/29 補：舊 5,103,722 → 5,083,230）
    rep["5,103,722"] = _fmt(snap.get("allianz_a", 0) or 0)
    hits = 0
    for old, new in rep.items():
        if old in tpl:
            tpl = tpl.replace(old, new)
            hits += 1

    # ── data-k 自動注入（2026-08-31 治本：template 的 <span data-k="KEY">顯示值</span> 直接對 snapshot，
    #    不再依賴 rep 舊值字串清單 — 8/31 血淚：cash_total 772,607 殘留只因 rep 沒列 772,607）──
    import re as _re
    _data_k_map = {
        "cash_total": cash,        # 現金（snapshot.cash_total）
        "div_total": div_total,    # 配息實收
        "got_total2": got_total,   # 當月已收合計（說明欄）
        "got_total": got_total,    # 當月已收合計卡片（2026-08-31 補：template 用 data-k="got_total"）
        "rent_got": rent_got,      # 租金已收
        "mon_sum": _mon,           # 監控卡片合計（現金正數排除外幣）
    }
    for _dk, _dv in _data_k_map.items():
        _pat = _re.compile(r'(<span data-k="%s">)[^<]*(</span>)' % _dk)
        tpl, _n = _pat.subn(lambda m: m.group(1) + _fmt(_dv) + m.group(2), tpl)
        if _n:
            hits += _n

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
        "__CEO_DASH__": "ceo_dashboard_*.html",
        "__AUDIT_DASH__": "audit_dashboard_*.html",
        "__EMERGENCY__": "emergency_report_*.html",
        "__INDUSTRY_PNG__": "industry_penetration_*.png",
        "__PEN_REPORT__": "penetration_report_*.html",
        "__REBALANCE_DASH__": "rebalance_dashboard_*.html",
        "__REBALANCE_MD__": "rebalance_summary_*.md",
        "__RISK_PNG__": "risk_factor_penetration_*.png",
        "__WEEKLY__": "weekly_report_*.html",
        "__WEEKLY_REVIEW__": "dynamic_weekly_review_*.html",
        "__MONTHLY_REVIEW__": "dynamic_monthly_review_*.html",
        "__MONTHLY_REPORT__": "monthly_report_*.html",
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
