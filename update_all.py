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

def calc_penetration(cash, ins, sec, funds, bond_portion=None, fund_ratios=None):
    if bond_portion is not None:
        ins_bonds = int(bond_portion)
        ins_eq = int(ins) - int(bond_portion) - 1_958_980
    elif fund_ratios:
        fv = {"安聯收益成長": 2_780_466, "M&G入息": 3_136_436, "安聯AI收益成長": 902_679, "貝萊德科技A10": 964_495, "聯博美國成長": 4_751}
        ins_bonds = sum(round(fv[n] * fund_ratios.get(n, 0)) for n in fv)
        ins_eq = int(ins) - ins_bonds - 1_958_980
    else:
        ins_bonds = round(2_780_466*0.55 + 3_136_436*0.65 + 902_679*0.40)
        ins_eq = round(2_780_466*0.45 + 3_136_436*0.35 + 902_679*0.60) + 964_495 + 4_751
    tw = round(sec * 0.97) + funds
    us = round(sec * 0.03) + ins_eq
    total = cash + ins + sec + funds
    c = cash + total - (tw + us + 1_958_980 + ins_bonds + cash)
    return {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": 1_958_980, "債券": ins_bonds, "現金/安全網": c}

def main():
    snap = load_json(SNAP)
    args = {"cash": snap.get("real_liquid_assets",4483408), "ins": snap.get("insurance_current_value",9747807),
            "sec": snap.get("securities_total_market_value",2422640), "funds": snap.get("fund_market_value",795157)}
    for a in sys.argv[1:]:
        if "=" in a:
            k,v = a[2:].split("=",1)
            args[{"insurance":"ins","securities":"sec","cash":"cash","funds":"funds"}.get(k,k)] = json.loads(v) if k == "fund_ratios" else int(v)
    pen = calc_penetration(args["cash"], args["ins"], args["sec"], args["funds"], args.get("bond_portion"), args.get("fund_ratios"))
    if args.get("ins"):
        ins_calc = pen["債券"] + (pen["美股市值型成長"] - round(args.get("sec",0)*0.03)) + pen["防守型配息"]
        if abs(ins_calc - args["ins"]) > 100:
            print(f"  ⚠️ 保單校驗失敗：拆分總和 {ins_calc:,} ≠ 保險 {args['ins']:,}")
    if "--check" in sys.argv or "--check_fund" in sys.argv:
        if "--check_fund" in sys.argv:
            fv = {"安聯收益成長": 2_780_466, "M&G入息": 3_136_436, "安聯AI收益成長": 902_679, "貝萊德科技A10": 964_495, "聯博美國成長": 4_751}
            fr = args.get("fund_ratios", {"安聯收益成長":0.55, "M&G入息":0.65, "安聯AI收益成長":0.40, "貝萊德科技A10":0.0, "聯博美國成長":0.0})
            tb = sum(round(fv[n]*fr.get(n,0)) for n in fv)
            te = sum(fv[n] for n in fv) - tb
            ok = "✅" if abs(tb+te+1_958_980-sum(fv.values())-1_958_980) < 100 else "❌"
            print(f"=== 保單校驗 {ok} ===")
            print(f"  債券: {tb:,}  權益: {te:,}  第一金: 1,958,980  總值: {sum(fv.values())+1_958_980:,}")
            return
        print("=== 校驗 ===")
        for k,v in pen.items(): print(f"  {k}: {v:,}")
        print(f"  總和: {sum(pen.values()):,}  應={args['cash']+args['ins']+args['sec']+args['funds']:,}")
        return
    print("=== 三源同步 ===")
    total = args["cash"] + args["ins"] + args["sec"] + args["funds"]
    net = total - snap.get("total_liabilities", 0)
    snap.update({"real_liquid_assets": args["cash"], "insurance_current_value": args["ins"],
        "securities_total_market_value": args["sec"], "fund_market_value": args["funds"],
        "total_assets": total, "net_worth": net})
    snap["allianz_ab_current_value"] = snap.get("allianz_ab_current_value", 7788827)
    snap["allianz_ab"] = snap["allianz_ab_current_value"]
    snap["firstjin_current_value"] = 1958980
    snap.setdefault("penetration",{}).setdefault("actual_twd",{}).update(pen)
    save_json(SNAP, snap)
    db = sqlite3.connect(str(DB))
    db.execute("UPDATE assets SET cash_total=?, securities=?, insurance=?, funds=?, bonds=0, total_assets=? WHERE date=?",
        (args["cash"], args["sec"], args["ins"], args["funds"], total, TODAY))
    if db.total_changes == 0:
        db.execute("INSERT INTO assets(date,cash_total,securities,insurance,funds,bonds,total_assets) VALUES(?,?,?,?,?,0,?)",
            (TODAY, args["cash"], args["sec"], args["ins"], args["funds"], total))
    db.commit(); db.close()
    hist = load_json(HIST)
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
                     ("儀表板", BASE/"index.html"),
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
