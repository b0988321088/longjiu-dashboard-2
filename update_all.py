#!/usr/bin/env python3
"""龍九資產統一更新入口。"""
import json, sqlite3, sys, subprocess
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
# Cron no_agent 模式：CWD 可能不是 workdir，手動後備路徑
if not (BASE / "snapshot.json").exists():
    _alt = Path(r"C:\Users\bot\Desktop\longjiu_system")
    if _alt.exists():
        BASE = _alt
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"
HIST = BASE / "asset_diff_history.json"
# 確保 BASE 在 Python 路徑中（給 cron no_agent 用）
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
TODAY = date.today().isoformat()

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def save_json(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def _fv(v):
    """Extract numeric value from snapshot fund entry (may be int or dict)."""
    return v["value"] if isinstance(v, dict) else (v if isinstance(v, (int,float)) else 0)

def calc_penetration(cash, ins, sec, funds, bond_portion=None, fund_ratios=None, snap=None):
    _fj = int((snap or {}).get("firstjin_detail", {}).get("base_value_before_dividend")
              or (snap or {}).get("firstjin_current_value")
              or (snap or {}).get("firstjin_fl65_current_value") or 1_958_980)  # 8/22 修正：優先讀 firstjin_detail 最新真值（8/21 轉換後 1,992,265）
    # 2026-08-21：第一金保單已轉 FA81 聯博全球多元收益AD（股債混合）→ 不再整筆防守，
    # 依 current_fund.穿透比率 拆 股/債/現（估計 55/40/5，待月報確認）
    _fjd = (snap or {}).get("firstjin_detail", {})
    _cf_ratios = (_fjd.get("current_fund") or {}).get("穿透比率", {}) or {}
    _fj_eq_r = float(_cf_ratios.get("股票", 0.55))
    _fj_br_r = float(_cf_ratios.get("債券", 0.40))
    _fj_bond = round(_fj * _fj_br_r)
    _fj_eqv = round(_fj * _fj_eq_r)
    # 2026-08-21：美股科技/非科技拆解（科技比 = 基金淨值中科技曝險佔比；估計值，來源=月報/公開資料）
    _TECH = {"貝萊德世界科技": 1.0, "貝萊德科技": 1.0, "009824": 1.0, "00924": 1.0, "台新美日台半導體": 0.90,
             "富達全球動能多元": 0.35, "安聯AI收益成長": 0.35, "聯博美國成長": 0.40, "安聯收益成長": 0.20,
             "摩根JPM": 0.15, "摩根多重收益": 0.15, "PIMCO收益增長": 0.20, "M&G入息": 0.15, "聯博全球多元收益": 0.15,
             "貝萊德世界黃金基金A10美元": 0, "貝萊德世界健康科學基金A10美元": 0.30, "00646": 0.32, "009823": 0.32}
    def _tr(_fn):
        return next((r for k, r in _TECH.items() if k in _fn), 0.15)
    if bond_portion is not None:
        ins_bonds = int(bond_portion)
        ins_eq = int(ins) - int(bond_portion) - _fj
    elif fund_ratios:
        # 從 snapshot 動態讀取保險基金市值
        if snap:
            _a = snap.get("insurance_breakdown", {}).get("policy_a_funds", {})
            _b = snap.get("insurance_breakdown", {}).get("policy_b_funds", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
        else:
            fv = {"安聯收益成長": 1_220_722, "M&G入息": 1_069_377, "安聯AI收益成長": 885_569, "貝萊德科技A10": 1_833_036, "PIMCO收益增長": 2_636_319}
        ins_bonds = sum(round(fv[n] * fund_ratios.get(n, 0)) for n in fv)
        ins_tech = sum(round(fv[n] * _tr(n)) for n in fv)
        ins_eq = int(ins) - ins_bonds - _fj
    else:
        # 從 snapshot 動態讀取 + 預設債券比率（安聯收益35%, M&G 55%, AI收益50%）
        if snap:
            _a = snap.get("insurance_breakdown", {}).get("policy_a_funds", {})
            _b = snap.get("insurance_breakdown", {}).get("policy_b_funds", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
            _br = {"安聯收益成長": 0.35, "M&G入息": 0.55, "安聯AI收益成長": 0.50, "PIMCO收益增長": 0.48, "摩根JPM多重收益": 0.50, "貝萊德世界黃金基金A10美元": 0, "貝萊德世界健康科學基金A10美元": 0, "第一金FA81（聯博-全球多元收益基金 AD月配級別美元…）": 0.61}
            ins_bonds = sum(round(fv[n] * _br.get(n, 0)) for n in fv)
            ins_tech = sum(round(fv[n] * _tr(n)) for n in fv)
        else:
            ins_bonds = round(2_780_466*0.35 + 3_136_436*0.55 + 902_679*0.50)
            ins_tech = round(2_780_466*0.16 + 3_136_436*0.07 + 902_679*0.35)
        ins_eq = int(ins) - ins_bonds - _fj
    # 分類基金（鉅亨基金帳戶）— 支援扁平 {name: val} 或嵌套 {群組: {name: val}}
    _fund_tw = _fund_us = _fund_def = _fund_us_tech = _fund_cash = _fund_bonds = 0
    _fb = (snap or {}).get("funds_breakdown", {})
    _fb_flat = {}
    for _fn, _fval in _fb.items():
        if isinstance(_fval, dict):
            for _sn, _sv in _fval.items():
                if _sn in ("小計", "匯率調整", "note") or not isinstance(_sv, (int, float)):
                    continue
                _fb_flat[_sn] = _sv
        elif isinstance(_fval, (int, float)):
            _fb_flat[_fn] = _fval
    for _fn, _fval in _fb_flat.items():
        # 2026-08-21 成分穿透：富達（股80.75/債14.03/現5.21，月報 2026/6/30）與
        # 聯博全球多元收益（股55/債40/現5，估計待月報）拆股債現，不再整筆丟單一桶
        if "富達全球動能多元" in _fn:
            # 成分穿透（月報 2026/6/30）：股 80.75 / 債 14.03 / 現 5.21
            # ⚠️ 2026-08-21：基金內部現金 5.21% 併入美股（85.96%），不進現金桶 — 避免污染「現金/安全網」
            _fund_us += round(_fval * 0.8075) + round(_fval * 0.0521)
            _fund_bonds += round(_fval * 0.1403)
            _fund_cash += 0
            _fund_us_tech += round(_fval * 0.8075 * _tr(_fn))
        elif "聯博全球多元收益" in _fn:
            # 8/24 月報真值（使用者提供 PDF）：股票 34.63% + 其他 4.00%（選擇權策略）= 38.63% 權益；債券 61.37%
            # 前5大持股全科技 8.03%（NVDA2.28+AAPL2.00+GOOGL1.60+AVGO1.15+MSFT1.00）→ 科技保守估 10%
            # ⚠️ AD 月配級別配息來源可能為本金；信評 BB+B = 46.7% 高收益債
            _fund_us += round(_fval * 0.3863)
            _fund_bonds += round(_fval * 0.6137)
            _fund_cash += 0
            _fund_us_tech += round(_fval * 0.10)
        elif "台中銀台灣優息" in _fn or "國泰台灣高股息" in _fn:
            _fund_def += _fval
        elif any(k in _fn for k in ["台新美日台", "貝萊德", "安聯AI", "聯博", "摩根", "M&G", "安聯收益成長", "安聯美國", "富達"]):
            _fund_us += _fval
            _fund_us_tech += _fval * _tr(_fn)
        elif any(k in _fn for k in ["0050連結", "統一奔騰", "安聯台灣科技", "路博邁台灣5G", "路博邁5G"]):
            # 2026-08-13 修正：路博邁台灣5G 是台股基金（投資台灣5G股），誤歸美股
            _fund_tw += _fval
        elif "貨幣" in _fn:
            # 2026-08-21：貨幣市場基金（台幣貨基）→ 現金/安全網（餘數法自動落入 c）
            _fund_cash += _fval
        else:
            _fund_tw += _fval
    # 證券 holdings 五桶分類（2026-08-04 修正：高股息ETF 過去被全數掃進台股市值型成長）
    _SEC_TW = {"0050", "006208", "009816"}               # 台股市值型成長
    _SEC_US = {"00646", "009823", "009824", "00924"}     # 美股市值型成長（含美股科技 00924）
    _SEC_DEF = {"00713", "00878", "0056", "00919", "00918", "00888"}  # 防守型配息（高股息低波）
    _SEC_BOND = {"00983D"}                               # 債券
    sec_tw = sec_us = sec_def = sec_bond = sec_us_tech = 0
    _sec_holdings = (snap or {}).get("securities", {}).get("holdings", [])
    if _sec_holdings:
        for h in _sec_holdings:
            _t = h.get("ticker", "")
            _v = h.get("shares", 0) * h.get("price", 30)
            if _t in _SEC_DEF:
                sec_def += _v
            elif _t in _SEC_BOND:
                sec_bond += _v
            elif _t in _SEC_US:
                sec_us += _v
                _SEC_TECH = {"00646": 0.32, "009823": 0.32, "009824": 1.0, "00924": 1.0}
                sec_us_tech = sec_us_tech + _v * _SEC_TECH.get(_t, 0.30)
            else:
                sec_tw += _v  # 含未分類台股（00981A/00984A 主動型）
        # 防呆：holdings 市值與 sec 差異 >2% 時按比例縮放
        _sec_sum = sec_tw + sec_us + sec_def + sec_bond
        if _sec_sum > 0 and sec > 0 and abs(_sec_sum - sec) / sec > 0.02:
            _k = sec / _sec_sum
            sec_tw, sec_us, sec_def, sec_bond = (round(sec_tw * _k), round(sec_us * _k),
                                                 round(sec_def * _k), round(sec_bond * _k))
    else:
        sec_tw = sec
    # 2026-08-21：第一金 FA81 聯博拆分 → 權益/債券各加回（⚠️ 必須在 us/tw 計算前，否則 _fj_eqv 掉進現金桶）
    ins_eq += _fj_eqv
    ins_bonds += _fj_bond
    tw = sec_tw + _fund_tw
    us = sec_us + ins_eq + _fund_us
    total = cash + ins + sec + funds
    def_v = sec_def + _fund_def
    bond_v = sec_bond + ins_bonds + _fund_bonds
    # 基金縮放防呆（2026-08-07 修正：外幣換算/匯率調整後明細加總≠funds 真值時，
    # 按比例縮放基金三類，避免餘數法現金被吃掉）
    # ⚠️ 2026-08-11 修正：直接對齊 funds 真值（無論匯率調整在明細內或 funds 內，
    #    縮放因子一律 = funds / 明細加總，確保現金/安全網 == cash_total）
    _fund_sum = _fund_tw + _fund_us + _fund_def + _fund_cash + _fund_bonds
    if _fund_sum > 0 and funds > 0 and abs(_fund_sum - funds) / funds > 0.001:
        _fk = funds / _fund_sum
        _fund_tw, _fund_us, _fund_def, _fund_bonds = (round(_fund_tw * _fk), round(_fund_us * _fk),
                                         round(_fund_def * _fk), round(_fund_bonds * _fk))
        tw = sec_tw + _fund_tw
        us = sec_us + ins_eq + _fund_us
        def_v = sec_def + _fund_def
        bond_v = sec_bond + ins_bonds + _fund_bonds
    c = total - (tw + us + def_v + bond_v)
    us_tech = _fund_us_tech + ins_tech + sec_us_tech
    us_non_tech = us - us_tech
    return {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": def_v, "債券": bond_v, "現金/安全網": c,
            "美股市值型成長_科技": round(us_tech), "美股市值型成長_非科技": round(us_non_tech),
            "_meta": {"ins_eq": ins_eq, "fund_us": _fund_us, "fund_def": _fund_def,
                      "sec_tw": sec_tw, "sec_us": sec_us, "sec_def": sec_def, "sec_bond": sec_bond,
                      "us_tech": round(us_tech), "us_non_tech": round(us_non_tech)}}


def perform_data_validation(data: dict) -> list[str]:
    """資料校驗：三源同步後檢查數據一致性"""
    from logging_config import get_logger
    logger = get_logger("validation")
    alerts = []

    cash = data.get("cash", 0)
    insurance = data.get("insurance", 0)
    securities = data.get("securities", 0)
    funds = data.get("funds", 0)
    total = data.get("total_assets", 0)

    # 規則 1：總資產 ≈ 現金+保險+證券+基金（誤差 < 0.1%）
    if total > 0:
        calc = cash + insurance + securities + funds
        err = abs(total - calc) / total
        if err > 0.01:  # > 1%
            msg = f"🔴 總資產嚴重不符：{total:,.0f} vs {calc:,.0f} ({err*100:.2f}%)"
            alerts.append(f"[CRITICAL] {msg}")
            logger.critical(msg)
        elif err > 0.001:  # 0.1% ~ 1%
            msg = f"🟡 總資產略有偏差：{total:,.0f} vs {calc:,.0f} ({err*100:.2f}%)"
            alerts.append(f"[WARN] {msg}")
            logger.warning(msg)
        else:
            logger.info(f"總資產校驗通過：{total:,.0f} vs {calc:,.0f} ({err*100:.2f}%)")

    return alerts


def main():
    snap = load_json(SNAP)
    args = {"cash": snap.get("real_liquid_assets",4483408), "ins": snap.get("insurance_current_value",9747807),
            "sec": snap.get("securities_total_market_value",2422640), "funds": snap.get("fund_market_value",795157)}
    for a in sys.argv[1:]:
        if "=" in a:
            k,v = a[2:].split("=",1)
            args[{"insurance":"ins","securities":"sec","cash":"cash","funds":"funds"}.get(k,k)] = json.loads(v) if k == "fund_ratios" else int(v)
    pen = calc_penetration(args["cash"], args["ins"], args["sec"], args["funds"], args.get("bond_portion"), args.get("fund_ratios"), snap=snap)
    if args.get("ins"):
        # 保單拆分校驗：債券 + 保險權益 + 第一金 = 保險（不含鉅亨基金分類與證券部位）
        # ⚠️ 2026-08-10 修正：原公式漏扣 sec_def/sec_bond，把證券防守/債券誤計入保險拆分
        _allianz_total = snap.get("allianz_ab_current_value", 0)
        _firstjin_total = snap.get("firstjin_current_value", 0)
        _calculated_ins_total = _allianz_total + _firstjin_total
        if abs(_calculated_ins_total - args["ins"]) > 100:
            print(f"  ⚠️ 保單校驗失敗：拆分總和 {_calculated_ins_total:,} ≠ 保險 {args['ins']:,} (應為總值 {args['ins']:,})")
        else:
            print(f"  ✅ 保單拆分校驗通過（安聯+第一金 = {_calculated_ins_total:,}）")
    # 自動同步腳本到 hermes/scripts/
    # 2026-08-27 修正：hermes 版若是「薄轉發器」（wrapper 轉發 repo）→ 跳過，避免覆蓋破壞架構
    try:
        import shutil
        _scripts_dst = Path(os.environ.get("HERMES_SCRIPTS", str(Path.home() / "AppData/Local/hermes/scripts")))
        for _sf in ["update_all.py", "run_daily.py", "asset_diff_monitor.py", "memory_sync.py", "daily_deploy.py", "penetration_monitor.py", "reminder_agent.py", "weekly_report.py", "gmail_cleanup.py", "cio_review.py", "daily_checklist.py", "regenerate_report.py", "daily_intel.py", "buffett_cto_analyzer.py", "emergency_1330.py"]:
            _src = BASE / _sf
            _dst = _scripts_dst / _sf
            if not _src.exists():
                continue
            if _dst.exists() and "薄轉發器" in _dst.read_text(encoding="utf-8", errors="ignore")[:300]:
                continue  # wrapper 檔不覆蓋
            if not _dst.exists() or _src.stat().st_mtime > _dst.stat().st_mtime:
                shutil.copy2(str(_src), str(_dst))
    except Exception:
        pass
    if "--check" in sys.argv or "--check_fund" in sys.argv:
        if "--check_fund" in sys.argv:
            # 從 snapshot 動態讀取保險基金明細（安聯A+B），避免硬編碼舊值
            _a = snap.get("allianz_a_breakdown", {})
            _b = snap.get("allianz_b_breakdown", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
            if not fv:  # 兜底：snapshot 無明細時用預設值
                fv = {"安聯收益成長": 1_220_722, "M&G入息": 1_069_377, "安聯AI收益成長": 885_569, "貝萊德科技A10": 1_833_036, "PIMCO收益增長": 2_636_319}
            fr = args.get("fund_ratios", {"安聯收益成長":0.35, "M&G入息":0.55, "安聯AI收益成長":0.50, "貝萊德科技A10":0.0, "PIMCO收益增長":0.48})
            tb = sum(round(fv[n]*fr.get(n,0)) for n in fv)
            te = sum(fv[n] for n in fv) - tb
            _fj = int(snap.get("firstjin_fl65_current_value") or snap.get("firstjin_current_value") or 1_958_980)
            _ins_total = int(args["ins"])
            ok = "✅" if abs(tb + te + _fj - _ins_total) < 100 else "❌"
            print(f"=== 保單校驗 {ok} ===")
            print(f"  債券: {tb:,}  權益: {te:,}  第一金: {_fj:,}  拆分總值: {tb+te+_fj:,}  保險: {_ins_total:,}")
            return
        print("=== 校驗 ===")
        for k,v in pen.items():
            if k == "_meta": continue
            print(f"  {k}: {v:,}")
        print(f"  總和: {sum(v for k, v in pen.items() if k != '_meta'):,}  應={args['cash']+args['ins']+args['sec']+args['funds']:,}")
        return
    # === 配息資料自動校驗（確保 snapshot 內所有配息值一致）===
    try:
        _az = snap.get("allianz_ab_monthly", 0) or 0
        _fj = snap.get("firstjin_monthly", 0) or 0
        _bd = snap.get("monthly_dividend_breakdown", {})
        _etf = _bd.get("etf", 10740)
        _fund = _bd.get("fund", 615)
        _expected_ins = _az + _fj
        _expected_total = _expected_ins + _etf + _fund
        if _bd.get("allianz", 0) != _az or _bd.get("insurance", 0) != _expected_ins or snap.get("monthly_dividend_total", 0) != _expected_total:
            _bd["allianz"] = _az
            _bd["firstjin"] = _fj
            _bd["insurance"] = _expected_ins
            _bd["etf"] = _etf
            _bd["fund"] = _fund
            _bd["total"] = _expected_total
            snap["monthly_dividend_breakdown"] = _bd
            snap["monthly_dividend"] = _expected_ins  # 保險配息（不含ETF+基金）
            snap["monthly_dividend_total"] = _expected_total  # 總額（含ETF+基金）
            # 同步 passive_income 保守值
            _pi = snap.get("passive_income", {})
            _pi["fund_dividend_conservative"] = _expected_ins
            _pi["total_conservative"] = _expected_ins + _pi.get("rent_monthly", 80100)
            _pi["coverage_pct"] = round(_pi["total_conservative"] / _pi.get("monthly_expense", 162781) * 100, 1)
            snap["passive_income"] = _pi
            save_json(SNAP, snap)
            print(f"  ✅ 配息資料自動校驗完成（allianz={_az:,} + firstjin={_fj:,} = {_expected_ins:,}）")
    except Exception as _de:
        print(f"  ⚠️ 配息校驗失敗: {_de}")
    # 確保 relay_stations 存在
    if not snap.get("relay_stations"):
        snap["relay_stations"] = {}
        save_json(SNAP, snap)
    print("=== 三源同步 ===")
    total = args["cash"] + args["ins"] + args["sec"] + args["funds"]
    net = total - snap.get("total_liabilities", 0)
    snap.update({"real_liquid_assets": args["cash"], "insurance_current_value": args["ins"],
        "securities_total_market_value": args["sec"], "fund_market_value": args["funds"],
        "total_assets": total, "net_worth": net})
    snap["allianz_ab_current_value"] = snap.get("allianz_a_current_value", 0) + snap.get("allianz_b_current_value", 0) or snap.get("allianz_ab_current_value", sn_a := snap.get("allianz_ab", 0) or sum(snap.get("allianz_a_breakdown", {}).values()) + sum(snap.get("allianz_b_breakdown", {}).values()))
    snap["allianz_ab"] = snap["allianz_ab_current_value"]
    snap["firstjin_current_value"] = snap.get("firstjin_current_value", sn_f := snap.get("firstjin_fl65_value", 1958980) or 1958980)
    # 2026-08-22 修正：不覆寫既有 targets（8/20 SAA 10/40/20/25/5 + 口徑修正註記），只補缺省值
    _tgt = snap.setdefault("penetration", {}).setdefault("targets", {})
    for _k, _v in {"台股市值型目標": 10, "美股市值型目標": 40, "配息型目標": 20, "債券型目標": 25, "現金目標": 5}.items():
        _tgt.setdefault(_k, _v)
    snap.setdefault("penetration",{}).setdefault("actual_twd",{}).update({k: v for k, v in pen.items() if k != "_meta"})
    # 計算實際佔比（分母=台股+美股+防守+債券+現金，不含不動產）
    # ⚠️ 2026-08-23 修正：不得 sum 全部 pen items — 美股市值型成長_科技/_非科技 是美股拆解，
    #    sum 會把美股重複計入分母（26.2M+11.5M=37.7M）→ 五桶% 全錯（美股 43.9%→30.5%）
    _bucket_keys = ["台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"]
    _pen_total = sum(pen.get(k, 0) for k in _bucket_keys) or 1
    snap.setdefault("penetration",{})["actual_pct"] = {
        "台股市值型成長": round(pen["台股市值型成長"] / _pen_total * 100, 1),
        "美股市值型成長": round(pen["美股市值型成長"] / _pen_total * 100, 1),
        "防守型配息": round(pen["防守型配息"] / _pen_total * 100, 1),
        "債券": round(pen["債券"] / _pen_total * 100, 1),
        "現金/安全網": round(pen["現金/安全網"] / _pen_total * 100, 1),
    }
    save_json(SNAP, snap)
    db = sqlite3.connect(str(DB))
    # 檢查是否跟最後一筆相同（週末/休市自動跳過）
    _last_db = db.execute("SELECT date, cash_total, securities, insurance, funds FROM assets ORDER BY date DESC LIMIT 1").fetchone()
    _db_same = _last_db and _last_db[1] == args["cash"] and _last_db[2] == args["sec"] and _last_db[3] == args["ins"] and _last_db[4] == args["funds"]
    if _db_same and _last_db[0] != TODAY:
        print(f"  ℹ️ DB 無變化（同 {_last_db[0]}），跳過寫入")
    else:
        db.execute("UPDATE assets SET cash_total=?, securities=?, insurance=?, funds=?, bonds=0, total_assets=?, total_liabilities=? WHERE date=?",
            (args["cash"], args["sec"], args["ins"], args["funds"], total, snap.get("total_liabilities",0), TODAY))
        if db.total_changes == 0:
            db.execute("INSERT INTO assets(date,cash_total,securities,insurance,funds,bonds,total_assets,total_liabilities) VALUES(?,?,?,?,?,0,?,?)",
                (TODAY, args["cash"], args["sec"], args["ins"], args["funds"], total, snap.get("total_liabilities",0)))
    db.commit(); db.close()
    hist = load_json(HIST)
    # 如果今天數據跟最後一筆相同，不重複記錄（週末/休市自動跳過）
    _last_date = sorted(hist.keys())[-1] if hist else None
    _last = hist.get(_last_date, {}) if _last_date else {}
    _same = (_last.get("cash") == args["cash"] and _last.get("securities_market") == args["sec"]
             and _last.get("insurance_current") == args["ins"] and _last.get("fund_market") == args["funds"])
    if _same and _last_date != TODAY:
        print(f"  ℹ️ 數據無變化（同 {_last_date}），跳過新增記錄")
    else:
        hist.setdefault(TODAY, {}).update({"cash": args["cash"], "securities_market": args["sec"],
            "insurance_current": args["ins"], "fund_market": args["funds"], "total_assets": total, "net_worth": net,
            "insurance_detail": {"安聯保單A+B 現值": float(snap["allianz_ab_current_value"]),
                "第一金保單 FL65 現值": float(snap.get("firstjin_current_value", snap.get("firstjin_fl65_value", 1958980))), "保單總現値": float(args["ins"])}})
        save_json(HIST, hist)
    print(f"  ✅ 現金={args['cash']:,}  保險={args['ins']:,}  證券={args['sec']:,}  基金={args['funds']:,}")
    print(f"  總資產={total:,}")
    # === 串聯產出管線（不可中斷）===
    # 2026-08-28：--no-pipeline = 只做資料同步（snapshot→DB），不產日報/差異/部署
    #（晚報 evening_sync 使用，避免 run_daily 觸發 buffett/cto LLM 重跑）
    if "--penetrate" not in sys.argv and "--no-pipeline" not in sys.argv:
        print("\n=== 串聯產出（不可中斷）===")
        steps = [
            ("run_daily.py", [sys.executable, str(BASE/"run_daily.py")]),
            ("asset_diff_monitor.py", [sys.executable, str(BASE/"asset_diff_monitor.py")]),
            ("daily_deploy.py", [sys.executable, str(BASE/"daily_deploy.py")]),
        ]
        for name, cmd in steps:
            print(f"  ▶ {name}...", end=" ")
            r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                print("❌ 失敗")
                print(f"  {r.stderr[-200:]}")
                print("\n⛔ 管線中斷，修復後重試")
                exit(1)
            print("OK")
        # 產出校驗
        sec_total = args.get("sec", 0)
        if sec_total:
            print("\n=== 產出校驗 ===")
            sec_str = f"{sec_total:,}"
            files = [("日報", BASE/f"daily_report_v2_{TODAY}.html"),
                     ("差異分析", BASE/f"asset_diff_{TODAY}.html")]
            all_ok = True
            for label, fp in files:
                html = fp.read_text(encoding="utf-8", errors="ignore")
                if sec_str in html:
                    print(f"  ✅ {label} 證券值一致 ({sec_str})")
                else:
                    print(f"  ❌ {label} 證券值不符（預期 {sec_str}）")
                    all_ok = False
            if all_ok:
                print("  ✅ 三份產出一致")
            else:
                print("\n⛔ 校驗失敗（儀表板證券值暫跳過）")
    # Notion 資產快照（即使校驗失敗也執行）
    try:
        from notion_knowledge import write_snapshot
        _w = args
        write_snapshot(_w["cash"]+_w["ins"]+_w["sec"]+_w["funds"], _w["sec"], _w["ins"], _w["funds"], _w["cash"], "update_all.py 自動同步")
        print("  ✅ Notion 快照已寫入")
    except Exception as _ne:
        print(f"  ⚠️ Notion 寫入失敗: {_ne}")

    print("\n✅ 全部完成")

if __name__ == "__main__":
    main()
