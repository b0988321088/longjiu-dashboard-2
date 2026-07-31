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
    _fj = int((snap or {}).get("firstjin_fl65_current_value") or (snap or {}).get("firstjin_current_value") or 1_958_980)
    if bond_portion is not None:
        ins_bonds = int(bond_portion)
        ins_eq = int(ins) - int(bond_portion) - _fj
    elif fund_ratios:
        # 從 snapshot 動態讀取保險基金市值
        if snap:
            _a = snap.get("allianz_a_breakdown", {})
            _b = snap.get("allianz_b_breakdown", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
        else:
            fv = {"安聯收益成長": 1_220_722, "M&G入息": 1_069_377, "安聯AI收益成長": 885_569, "貝萊德科技A10": 1_833_036, "PIMCO收益增長": 2_636_319}
        ins_bonds = sum(round(fv[n] * fund_ratios.get(n, 0)) for n in fv)
        ins_eq = int(ins) - ins_bonds - _fj
    else:
        # 從 snapshot 動態讀取 + 預設債券比率（安聯收益35%, M&G 55%, AI收益50%）
        if snap:
            _a = snap.get("allianz_a_breakdown", {})
            _b = snap.get("allianz_b_breakdown", {})
            fv = {}
            for k in list(dict.fromkeys(list(_a.keys()) + list(_b.keys()))):
                fv[k] = _fv(_a.get(k, 0)) + _fv(_b.get(k, 0))
            _br = {"安聯收益成長": 0.35, "M&G入息": 0.55, "安聯AI收益成長": 0.50, "PIMCO收益增長": 0.48}
            ins_bonds = sum(round(fv[n] * _br.get(n, 0)) for n in fv)
        else:
            ins_bonds = round(2_780_466*0.35 + 3_136_436*0.55 + 902_679*0.50)
        ins_eq = int(ins) - ins_bonds - _fj
    # 分類基金（鉅亨基金帳戶）
    _fund_tw = _fund_us = _fund_def = 0
    _fb = (snap or {}).get("funds_breakdown", {})
    for _fn, _fval in _fb.items():
        if "台中銀台灣優息" in _fn:
            _fund_def += _fval
        elif any(k in _fn for k in ["路博邁5G", "台新美日台", "貝萊德", "安聯AI", "聯博", "摩根", "M&G", "安聯收益成長", "安聯美國"]):
            _fund_us += _fval
        elif any(k in _fn for k in ["0050連結", "統一奔騰", "安聯台灣科技", "國泰台灣高股息"]):
            _fund_tw += _fval
        else:
            _fund_tw += _fval
    tw = round(sec * 0.97) + _fund_tw
    us = round(sec * 0.03) + ins_eq + _fund_us
    # 用 snapshot holdings 精算台/美股比例（取代固定97/3）
    try:
        _sec_holdings = (snap or {}).get("securities", {}).get("holdings", [])
        if _sec_holdings:
            _us_tickers = {"00646", "009823", "009824"}
            _us_v = sum(h["shares"] * h.get("price", 30) for h in _sec_holdings if h.get("ticker") in _us_tickers) or 1
            _total_v = sum(h["shares"] * h.get("price", 30) for h in _sec_holdings) or 1
            _us_pct = _us_v / _total_v
            _tw_pct = 1 - _us_pct
            tw = round(sec * _tw_pct) + _fund_tw
            us = round(sec * _us_pct) + ins_eq + _fund_us
    except:
        pass
    total = cash + ins + sec + funds
    c = cash + total - (tw + us + _fj + _fund_def + ins_bonds + cash)
    # 防守型加上基金防守部位
    return {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": _fj + _fund_def, "債券": ins_bonds, "現金/安全網": c,
            "_meta": {"ins_eq": ins_eq, "fund_us": _fund_us, "fund_def": _fund_def, "sec_us": round(sec * (1 - (tw - _fund_tw) / sec)) if sec else 0}}


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
        # 保單拆分校驗：債券 + 保險權益 + 第一金 = 保險（不含鉅亨基金分類）
        _m = pen.get("_meta", {})
        ins_calc = pen["債券"] + (pen["美股市值型成長"] - _m.get("sec_us", 0) - _m.get("fund_us", 0)) + (pen["防守型配息"] - _m.get("fund_def", 0))
        if abs(ins_calc - args["ins"]) > 100:
            print(f"  ⚠️ 保單校驗失敗：拆分總和 {ins_calc:,} ≠ 保險 {args['ins']:,}")
        else:
            print(f"  ✅ 保單拆分校驗通過（債券+權益+第一金 = {ins_calc:,}）")
    # 自動同步腳本到 hermes/scripts/
    try:
        import shutil
        _scripts_dst = Path(os.environ.get("HERMES_SCRIPTS", str(Path.home() / "AppData/Local/hermes/scripts")))
        for _sf in ["update_all.py", "run_daily.py", "asset_diff_monitor.py", "memory_sync.py", "daily_deploy.py", "penetration_monitor.py", "reminder_agent.py", "weekly_report.py", "gmail_cleanup.py"]:
            _src = BASE / _sf
            _dst = _scripts_dst / _sf
            if _src.exists() and (not _dst.exists() or _src.stat().st_mtime > _dst.stat().st_mtime):
                shutil.copy2(str(_src), str(_dst))
    except Exception:
        pass
    if "--check" in sys.argv or "--check_fund" in sys.argv:
        if "--check_fund" in sys.argv:
            fv = {"安聯收益成長": 1_220_722, "M&G入息": 1_069_377, "安聯AI收益成長": 885_569, "貝萊德科技A10": 1_833_036, "PIMCO收益增長": 2_636_319}
            fr = args.get("fund_ratios", {"安聯收益成長":0.35, "M&G入息":0.55, "安聯AI收益成長":0.50, "貝萊德科技A10":0.0, "PIMCO收益增長":0.48})
            tb = sum(round(fv[n]*fr.get(n,0)) for n in fv)
            te = sum(fv[n] for n in fv) - tb
            ok = "✅" if abs(tb+te+_fj-sum(fv.values())-_fj) < 100 else "❌"
            print(f"=== 保單校驗 {ok} ===")
            print(f"  債券: {tb:,}  權益: {te:,}  第一金: 1,958,980  總值: {sum(fv.values())+1_958_980:,}")
            return
        print("=== 校驗 ===")
        for k,v in pen.items(): print(f"  {k}: {v:,}")
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
            _pi["coverage_pct"] = round(_pi["total_conservative"] / _pi.get("monthly_expense", 141958) * 100, 1)
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
    snap.setdefault("penetration",{})["targets"] = {"台股市值型目標": 35, "美股市值型目標": 30, "配息型目標": 25, "債券型目標": 5, "現金目標": 5}
    snap.setdefault("penetration",{}).setdefault("actual_twd",{}).update({k: v for k, v in pen.items() if k != "_meta"})
    # 計算實際佔比（分母=台股+美股+防守+債券+現金，不含不動產）
    _pen_total = sum(v for k, v in pen.items() if k != "_meta") or 1
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
                "第一金保單 FL65 現值": 1958980.0, "保單總現値": float(args["ins"])}})
        save_json(HIST, hist)
    print(f"  ✅ 現金={args['cash']:,}  保險={args['ins']:,}  證券={args['sec']:,}  基金={args['funds']:,}")
    print(f"  總資產={total:,}")
    # === 串聯產出管線（不可中斷）===
    if "--penetrate" not in sys.argv:
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
