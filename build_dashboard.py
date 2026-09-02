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
    # 2026-09-01 修正：系統時間寫死（原模板 2026-08-29）→ 動態當天
    import datetime as _dt
    tpl = tpl.replace("系統時間：2026-08-29", "系統時間：" + _dt.date.today().strftime("%Y-%m-%d"))

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
            _plan.append("PI 核可(9/10)→質押350萬還債；9/3 起追銀行進度")
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
    # 2026-09-01 修正：資料日期動態（moneybook/ 最新帳戶 CSV 檔名；無則用 snapshot 日期）
    import glob as _glob_mb
    _mb_csv = sorted(_glob_mb.glob(str(BASE / "moneybook" / "Moneybook_帳戶_*.csv")))
    _data_date = str(_mb_csv[-1]).replace("\\", "/").split("/")[-1].replace("Moneybook_帳戶_", "").replace(".csv", "") if _mb_csv else "20260901"
    taiwan = (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般", 0) or 0) + (cd.get("敦南Richart外幣", 0) or 0)
    rep["499,316"] = _fmt(taiwan)          # 台新合計
    rep["139,446"] = _fmt(cd.get("文心綜活儲存款-薪轉", 177765) or 0)  # 文心薪轉
    rep["97,353"] = _fmt(cd.get("敦南Richart數位一般", 90524) or 0)   # Richart一般
    # 管理費入帳狀態（2026-08-29：模板寫死「待入帳 0（應收 2,100）」→ 依 rent_received_records 動態）
    _fee = 0
    for k, v in (snap.get("rent_received_records", {}) or {}).items():
        if str(k).startswith(_today_m) and isinstance(v, dict) and "管理費" in v:
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
    rep["20260821_1"] = _data_date      # 資料日期（動態：moneybook/ 最新帳戶 CSV）
    rep["20260829_1"] = _data_date      # 資料日期（2026-09-01 修正：動態，不再寫死 8/31）    # 現金合計卡「監控卡片合計」（2026-08-29 補：原寫死 799,612 殘留 → 動態算 cash_detail 正數，排除外幣 key）
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
        "salary_got": salary,      # 薪水已收（當月 salary_records；未入帳 = 0）
        "mon_sum": _mon,           # 監控卡片合計（現金正數排除外幣）
        # 2026-09-01 補齊：與 template JS V 表對齊（39 key 全注入 → 靜態 fallback 也是最新值）
        "ins_total": ins,
        "allianz_a": snap.get("allianz_a", 0) or 0,
        "allianz_b": snap.get("allianz_b", 0) or 0,
        "allianz_ab": allianz,
        "firstjin": firstjin,
        "cum_div": snap.get("allianz_cum_dividend", 0) or 0,
        "fj_cum": snap.get("firstjin_cum_dividend", 0) or 0,
        "az_div": az_div, "az_div2": az_div,
        "fj_div": firstjin_div,
        "div_ins": div_ins,
        "etf_div": sum(v for k, v in _dr.items() if any(t in k for t in ("ETF", "基金", "聯博")) and isinstance(v, (int, float))) or 0,
        "safe_line": int(expense) * 3,
        "pen_tw": _ptwd.get("台股市值型成長", 0),
        "pen_us": _ptwd.get("美股市值型成長", 0),
        "pen_def": _ptwd.get("防守型配息", 0),
        "pen_bond": _ptwd.get("債券", 0),
        "pen_cash": _ptwd.get("現金/安全網", 0),
        "pen_tech": _ptwd.get("美股市值型成長_科技", 0),
        "pen_nontech": _ptwd.get("美股市值型成長_非科技", 0),
        "cathay": (cd.get("活期儲蓄存款", 0) or 0) + (cd.get("數位存款帳戶２類", 0) or 0),
        "cathay_d1": cd.get("活期儲蓄存款", 0) or 0,
        "cathay_d2": cd.get("數位存款帳戶２類", 0) or 0,
        "taiwan": (cd.get("敦南Richart子帳戶", 0) or 0) + (cd.get("文心綜活儲存款-薪轉", 0) or 0) + (cd.get("敦南Richart數位一般", 0) or 0),
        "richart_sub": cd.get("敦南Richart子帳戶", 0) or 0,
        "wenxin": cd.get("文心綜活儲存款-薪轉", 0) or 0,
        "richart_gen": cd.get("敦南Richart數位一般", 0) or 0,
        "sinopac": (cd.get("營業部DAWHO活期儲蓄存款", 0) or 0) + (cd.get("市政分行活期儲蓄存款", 0) or 0),
        "dawho": cd.get("營業部DAWHO活期儲蓄存款", 0) or 0,
        "shizheng": cd.get("市政分行活期儲蓄存款", 0) or 0,
        "yushan": cd.get("臺幣綜存", 0) or 0,
        "fubon": cd.get("數位活儲", 0) or 0,
        "jianglai": cd.get("Digital Savings Acco", 0) or 0,
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
        # 2026-09-01 定案：優先級由資料欄位 importance 宣告（high=硬性要做 / medium=觀察 / low=例行），不再關鍵字猜
        _is_active = lambda e: str(e.get("importance", "")) == "high" and "✅" not in str(e.get("status", "")) and "已完成" not in str(e.get("status", ""))
        _today_act = [e for e in _evs if str(e.get("date","")) == _td and _is_active(e)]
        _soon3 = sorted([e for e in _evs if _td < str(e.get("date","")) <= (date.today() + timedelta(days=3)).isoformat() and _is_active(e)],
                        key=lambda x: str(x.get("date","")))
        _next = sorted([e for e in _evs if _td < str(e.get("date","")) <= _wk and _is_active(e)],
                       key=lambda x: str(x.get("date","")))
        _parts = []
        # 今日重點 = importance=high 且日期=今天（含已完成，讓使用者對照完成狀態）
        _today_key = [e for e in _evs if isinstance(e, dict) and str(e.get("date","")) == _td and str(e.get("importance","")) == "high" and str(e.get("item",""))]
        for e in _today_key[:3]:
            _st = str(e.get("status",""))
            _icon = "✅" if ("✅" in _st or "已完成" in _st) else ("🔄" if ("執行中" in _st or "待確認" in _st) else "⏳")
            _st_short = _st.lstrip("✅ ").strip()[:14]
            _parts.append(f"🔴 今日要做：{str(e.get('item',''))[:40]}（{_icon} {_st_short}）")
        if not _parts:
            _parts.append("🟢 今日無重點事項")
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

    # ── 戰略異常中心動態化（2026-09-01：雷達/交易計畫/政策面不再硬編碼 8/29 快照）──
    try:
        _rs = json.loads((BASE / "radar_state.json").read_text(encoding="utf-8"))
        _sig = _rs.get("signals", {}) or {}
        _sig_str = "｜".join(f"{k}{v.get('color', '⚪')} {v.get('note', '')}" for k, v in _sig.items())
        tpl = tpl.replace("__RADAR_SIG__", f"（雷達更新 {str(_rs.get('last_run', ''))[:10]}）{_sig_str}")
        _pn = _rs.get("policy_notes", {}) or {}
        _pol_items = []
        for _k in _pn:
            if str(_k).startswith("新聞"):
                _c = (_pn[_k].get("內容", "") or "")[:56]
                _imp = (_pn[_k].get("對資產影響", "") or "")[:42]
                _pol_items.append(f"{_c}（{_imp}）")
        _pol_str = "｜".join(_pol_items) if _pol_items else "無重大政策事件"
        _src = _pn.get("來源", "") or ""
        tpl = tpl.replace("__POLICY_NOTES__", f"🏛️ 政策面（{_src}）：{_pol_str}")
    except Exception as _e:
        tpl = tpl.replace("__RADAR_SIG__", "雷達暫無資料").replace("__POLICY_NOTES__", "政策面暫無資料")

    # ── 交易計畫（2026-09-01：從 pending_decisions 動態，非 8/29 統籌版快照）──
    try:
        _pd = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
        _plan_items = []
        for _d in (_pd if isinstance(_pd, list) else [])[:6]:
            _st = str(_d.get("status", "") or "").replace("：", ":")[:26]
            _tt = str(_d.get("title", "") or "")[:26]
            _plan_items.append(f"{_st} {_tt}")
        _plan_str = "｜".join(_plan_items) if _plan_items else "無執行中決策"
        tpl = tpl.replace("__TRADE_PLAN__", f"🎯 本週交易計畫（動態）：{_plan_str}")
    except Exception:
        tpl = tpl.replace("__TRADE_PLAN__", "交易計畫暫無資料")

    # ── 月度流入標題動態化（2026-09-01：原寫死「08月現金流入檢對核實」→ 當月）──
    tpl = tpl.replace("__INCOME_TITLE__", str(int(_today_m[5:])) + "月現金流入檢對核實")

    # ── 戰術任務動態化（2026-09-01：P0 任務 + 本週計畫從 pending_decisions 生成，非 8/29 快照）──
    try:
        _pd2 = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
        _lst = _pd2 if isinstance(_pd2, list) else []
        if _lst:
            _p0 = _lst[0]
            _p0_st = str(_p0.get("status", "") or "")[:90]
            _p0_tt = str(_p0.get("title", "") or "")[:90]
            _p0_dt = str(_p0.get("detail", "") or "")[:150]
            _p0_html = (
                '<div class="luxury-card p-6 border-l-4 border-red-500 space-y-4">'
                '<div class="flex justify-between items-start">'
                '<div><span class="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded font-mono font-bold">P0 戰略任務</span>'
                f'<h3 class="text-md font-bold text-white mt-1">✅ {_p0_st}｜{_p0_tt}</h3></div>'
                f'<span class="text-xs text-slate-400 font-mono">{str(_p0.get("date", ""))[:10]}</span></div>'
                '<div class="bg-slate-900/60 p-4 rounded-xl space-y-2 border border-slate-800 text-xs">'
                f'<p class="font-bold text-yellow-500">✅ 執行狀態：{_p0_st[:60]}</p>'
                f'<p class="text-slate-300 leading-relaxed font-mono">{_p0_dt}</p></div></div>'
            )
            tpl = tpl.replace("__P0_TASK__", _p0_html)
            _tact_rows = []
            for _d in _lst[:6]:
                _st = str(_d.get("status", "") or "").replace("：", ":")[:34]
                _tt = str(_d.get("title", "") or "")[:26]
                _tact_rows.append(
                    f'<div class="p-2 bg-slate-900/40 rounded border border-slate-800 flex justify-between">'
                    f'<span class="text-slate-300">{_tt}</span><span class="text-amber-400 font-mono">{_st}</span></div>'
                )
            tpl = tpl.replace("__TACTICAL_PLAN__",
                '<div class="luxury-card p-6 space-y-4"><h3 class="text-md font-bold text-white">🗓️ 本週計畫（動態）</h3>'
                '<div class="space-y-2 text-xs">' + "".join(_tact_rows) + '</div></div>')
        else:
            tpl = tpl.replace("__P0_TASK__", "").replace("__TACTICAL_PLAN__", "")
    except Exception:
        tpl = tpl.replace("__P0_TASK__", "").replace("__TACTICAL_PLAN__", "")

    # ── 穿透卡靜態渲染（2026-09-01：pen-card 不再依賴 JS「載入中」→ build 直接生成五桶，無 JS 也顯示）──
    _ptwd_p = snap.get("penetration", {}).get("actual_twd", {}) or {}
    _ppct_p = snap.get("penetration", {}).get("actual_pct", {}) or {}
    _tgt_p = snap.get("penetration", {}).get("targets", {}) or {}
    _defs_p = [
        ("台股市值型成長", "台股", "台股市值型目標", "#3b82f6"),
        ("美股市值型成長", "美股", "美股市值型目標", "#ef4444"),
        ("防守型配息", "防守", "配息型目標", "#22c55e"),
        ("債券", "債券", "債券型目標", "#f59e0b"),
        ("現金/安全網", "現金", "現金目標", "#94a3b8"),
    ]
    _pen_parts = [
        '<h3 class="text-md font-bold text-white">資產穿透（snapshot 真值）</h3>',
        f'<p class="text-xs text-slate-400">目標：台股 {_tgt_p.get("台股市值型目標", 10)}%｜美股 {_tgt_p.get("美股市值型目標", 40)}%｜防守 {_tgt_p.get("配息型目標", 20)}%｜債券 {_tgt_p.get("債券型目標", 25)}%｜現金 {_tgt_p.get("現金目標", 5)}%</p><div class="space-y-3 mt-3">',
    ]
    for _k, _lb, _tkey, _col in _defs_p:
        _act = _ppct_p.get(_k)
        if _act is None:
            continue
        _t = _tgt_p.get(_tkey, 0) or 0
        _twd = _ptwd_p.get(_k, 0) or 0
        _gap = _act - _t
        _gcls = "text-green-400" if abs(_gap) <= 2 else ("text-yellow-400" if abs(_gap) <= 5 else "text-red-400")
        _w = min(_act / 55 * 100, 100); _tw = min(_t / 55 * 100, 100)
        _pen_parts.append(
            f'<div><div class="flex justify-between text-xs"><span class="text-slate-300">{_lb}</span>'
            f'<span class="text-slate-100"><b>{_act:.1f}%</b> / 目標 {_t}% <span class="{_gcls}">({"+" if _gap > 0 else ""}{_gap:.1f}pp)</span></span></div>'
            f'<div class="relative h-2 bg-slate-800 rounded-full mt-1"><div class="absolute h-2 rounded-full" style="width:{_w:.0f}%;background:{_col}"></div>'
            f'<div class="absolute h-2 border-l-2 border-white/60" style="left:{_tw:.0f}%"></div></div>'
            f'<div class="text-[10px] text-slate-500 mt-0.5">市值：{_twd / 1e4:.0f} 萬 TWD</div></div>'
        )
    if _ppct_p.get("美股市值型成長_科技") is not None:
        _pen_parts.append(
            f'<div class="text-[11px] text-slate-400 pt-2 border-t border-slate-700/50">🔬 美股科技 {_ppct_p.get("美股市值型成長_科技", 0):.1f}%（{(_ptwd_p.get("美股市值型成長_科技", 0) or 0) / 1e4:.0f}萬）｜非科技 {_ppct_p.get("美股市值型成長_非科技", 0):.1f}%（{(_ptwd_p.get("美股市值型成長_非科技", 0) or 0) / 1e4:.0f}萬）｜科技目標 ≤15%</div>'
        )
    _pen_parts.append("</div>")
    tpl = tpl.replace("__PEN_CARD__", "".join(_pen_parts))

    # ── 月度流入核對清單靜態生成（2026-09-01 定案：✅已入帳 + ⏳待入帳兩段，build 生成 + JS 開頁同邏輯）──
    _inc_parts = []
    _inc_row = (
        '<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        '<div class="flex items-center gap-2 text-xs"><span class="text-emerald-400">✅ 已收</span>'
        '<span class="text-slate-300">{label}</span></div>'
        '<span class="text-xs font-mono text-emerald-400 font-bold">{amt}</span></div>'
    )
    _pend_row = (
        '<div class="flex justify-between items-center p-3 bg-slate-900/50 rounded-xl border border-slate-800">'
        '<div class="flex items-center gap-2 text-xs"><span class="text-amber-400">⏳ 待收</span>'
        '<span class="text-slate-300">{label}</span></div>'
        '<span class="text-xs font-mono text-amber-400 font-bold">{amt}</span>'
        '<span class="text-[10px] text-slate-500">{note}</span></div>'
    )
    _inc_parts.append('<div class="text-xs font-bold text-emerald-400 mb-1 mt-1">✅ 已入帳</div>')
    _has_inc = False
    _inc_total = 0
    if salary > 0:
        _inc_parts.append(_inc_row.format(label="台電薪水", amt=f"{_fmt(salary)} TWD")); _has_inc = True; _inc_total += salary
    for _k, _v in _dr.items():
        if isinstance(_v, (int, float)) and _v > 0:
            _inc_parts.append(_inc_row.format(label=_k, amt=f"{_fmt(_v)} TWD")); _has_inc = True; _inc_total += _v
    # 當月房租已收明細（rent_received_records）
    _rent_recv = {}
    for _d, _v in (snap.get("rent_received_records", {}) or {}).items():
        if str(_d).startswith(_today_m):
            if isinstance(_v, dict):
                for _k2, _v2 in _v.items():
                    _rent_recv[_k2] = _rent_recv.get(_k2, 0) + (_v2 or 0)
            elif isinstance(_v, (int, float)):
                _rent_recv["房租"] = _rent_recv.get("房租", 0) + _v
    for _k3, _v3 in _rent_recv.items():
        if _v3 > 0:
            _inc_parts.append(_inc_row.format(label=_k3 + "房租", amt=f"{_fmt(_v3)} TWD")); _has_inc = True; _inc_total += _v3
    _gf_inc = sum(v for k, v in (snap.get("girlfriend_repayment_records", {}) or {}).items()
                  if str(k).startswith(_today_m) and isinstance(v, (int, float))) or 0
    if _gf_inc > 0:
        _inc_parts.append(_inc_row.format(label="女友還款", amt=f"{_fmt(_gf_inc)} TWD")); _has_inc = True; _inc_total += _gf_inc
    if not _has_inc:
        _inc_parts = ['<div class="text-slate-400">本月尚無入帳</div>']
    else:
        _inc_parts[0] = f'<div class="text-xs font-bold text-emerald-400 mb-1 mt-1">✅ 已收（{_fmt(_inc_total)} TWD）</div>'
    # 待入帳段
    _pend2 = []
    if salary <= 0:
        _pend2.append(("台電薪水", snap.get("monthly_salary", 39727) or 39727, "9/6 入帳"))
    if _gf_inc <= 0:
        _pend2.append(("女友還款", 6000, "9/5 入帳"))
    for _k4, _v4 in (snap.get("rent_breakdown", {}) or {}).items():
        _g4 = _rent_recv.get(_k4, 0)
        if _g4 < _v4:
            _pend2.append((_k4 + "房租", _v4 - _g4, ""))
    if _pend2:
        _pend_total = sum(x[1] for x in _pend2)
        _inc_parts.append(f'<div class="text-xs font-bold text-amber-400 mt-2 mb-1">⏳ 待收（{_fmt(_pend_total)} TWD）</div>')
        for _pl, _pv, _pn in _pend2:
            _inc_parts.append(_pend_row.format(label=_pl, amt=f"{_fmt(_pv)} TWD", note=_pn))
    # 第一金配息（2026-09-01：FA81 8/31 基準日 → 9 月入帳；App 應收推估，待確認）
    _fj_exp = (snap.get("firstjin_dividend_expected", {}) or {}).get(_today_m, {}) or {}
    _fj_amt = _fj_exp.get("amount", 0) or 0
    if _fj_amt > 0 and not any("第一金" in str(x[0]) for x in _pend2):
        _fj_note = _fj_exp.get("note", "")[:40]
        _inc_parts.append(_pend_row.format(label="第一金 FA81 配息", amt=f"{_fmt(_fj_amt)} TWD", note=_fj_note))
        _inc_parts[0 if not _has_inc else -1] = _inc_parts[0 if not _has_inc else -1]  # noop 保留
        # 更新待收段標題合計
        for _k_i, _p in enumerate(_inc_parts):
            if "⏳ 待收（" in _p:
                _inc_parts[_k_i] = _inc_parts[_k_i].replace("）</div>", "）</div>").replace(
                    f"{_fmt(_pend_total)} TWD", f"{_fmt(_pend_total + _fj_amt)} TWD")
                break
    tpl = tpl.replace("__INCOME_LIST__", "".join(_inc_parts))

    # ── 執行中決策追蹤靜態生成（2026-09-01：decision-track 不再硬編碼 8/21 快照 → 讀 pending_decisions）──
    try:
        _pd3 = json.loads((BASE / "pending_decisions.json").read_text(encoding="utf-8"))
        _dt_html = []
        for _d in (_pd3 if isinstance(_pd3, list) else [])[:6]:
            _d_date = str(_d.get("date", ""))[5:].replace("-", "/")
            _d_tt = str(_d.get("title", "") or "")[:44]
            _d_st = str(_d.get("status", "") or "")[:64]
            _dt_html.append(
                f'<div class="flex items-center gap-3 p-2 bg-slate-900/30 rounded border border-red-500/30">'
                f'<span class="text-amber-400 font-mono font-bold w-14">{_d_date}</span>'
                f'<span class="text-white font-bold flex-1">{_d_tt}</span>'
                f'<span class="text-slate-300 font-mono">{_d_st}</span></div>'
            )
        tpl = tpl.replace("__DECISION_TRACK__", "".join(_dt_html) if _dt_html else '<div class="text-slate-400">無執行中決策</div>')
    except Exception:
        tpl = tpl.replace("__DECISION_TRACK__", '<div class="text-slate-400">決策追蹤暫無資料</div>')

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
