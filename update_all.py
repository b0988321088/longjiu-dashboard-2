#!/usr/bin/env python3
"""龍九資產統一更新入口：一次更新 snapshot/db/history，確保三源一致。"""
import json, sqlite3, sys, subprocess
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
DB = BASE / "dragon_assets.db"
HIST = BASE / "asset_diff_history.json"
TODAY = date.today().isoformat()

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))
def save_json(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def calc_penetration(cash, ins, sec, funds, bond_portion=None, fund_ratios=None):
    """穿透計算。bond_portion 指定保單債券總額；fund_ratios 逐檔指定債券比例。"""
    if bond_portion is not None:
        ins_bonds = int(bond_portion)
        ins_eq = int(ins) - int(bond_portion) - 1_958_980  # ins - bonds - firstjin
    elif fund_ratios:
        ins_bonds = 0
        for name, val in fund_ratios.items():
            total_fund = {"安聯收益成長": 2_780_466, "M&G入息": 3_136_436, "安聯AI收益成長": 902_679, "貝萊德科技A10": 964_495, "聯博美國成長": 4_751}.get(name, 0)
            ins_bonds += round(total_fund * val)
        ins_eq = int(ins) - ins_bonds - 1_958_980
    else:
        # 預設比例
        ins_bonds = round(2_780_466*0.55 + 3_136_436*0.65 + 902_679*0.40)
        ins_eq = round(2_780_466*0.45 + 3_136_436*0.35 + 902_679*0.60) + 964_495 + 4_751
    tw = round(sec * 0.97) + funds
    us = round(sec * 0.03) + ins_eq
    d = 1_958_980
    b = ins_bonds
    c = cash
    total = cash + ins + sec + funds
    c += total - (tw + us + d + b + c)
    return {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": d, "債券": b, "現金/安全網": c}

def main():
    snap = load_json(SNAP)
    args = {"cash": snap.get("real_liquid_assets",4483408), "ins": snap.get("insurance_current_value",9747807),
            "sec": snap.get("securities_total_market_value",2422640), "funds": snap.get("fund_market_value",795157)}

    for a in sys.argv[1:]:
        if "=" in a:
            k,v = a[2:].split("=",1)
            if k == "fund_ratios":
                args[k] = json.loads(v)
            elif k == "bond_portion":
                args[k] = int(v)
            else:
                args[k] = int(v)

    pen = calc_penetration(args["cash"], args["ins"], args["sec"], args["funds"], args.get("bond_portion"), args.get("fund_ratios"))

    if "--check" in sys.argv:
        print("=== 校驗 ===")
        for k,v in pen.items(): print(f"  {k}: {v:,}")
        print(f"  總和: {sum(pen.values()):,}  應={args['cash']+args['ins']+args['sec']+args['funds']:,}")
        return

    print("=== 三源同步 ===")
    total = args["cash"] + args["ins"] + args["sec"] + args["funds"]
    net = total - snap.get("total_liabilities", 0)

    # snapshot
    snap.update({"real_liquid_assets": args["cash"], "insurance_current_value": args["ins"],
        "securities_total_market_value": args["sec"], "fund_market_value": args["funds"],
        "total_assets": total, "net_worth": net})
    snap["allianz_ab_current_value"] = snap.get("allianz_ab_current_value", 7788827)
    snap["allianz_ab"] = snap["allianz_ab_current_value"]
    snap["firstjin_current_value"] = 1958980
    snap.setdefault("penetration",{}).setdefault("actual_twd",{}).update(pen)
    save_json(SNAP, snap)

    # db
    db = sqlite3.connect(str(DB))
    db.execute("UPDATE assets SET cash_total=?, securities=?, insurance=?, funds=?, bonds=0, total_assets=? WHERE date=?",
        (args["cash"], args["sec"], args["ins"], args["funds"], total, TODAY))
    if db.total_changes == 0:
        db.execute("INSERT INTO assets(date,cash_total,securities,insurance,funds,bonds,total_assets) VALUES(?,?,?,?,?,0,?)",
            (TODAY, args["cash"], args["sec"], args["ins"], args["funds"], total))
    db.commit(); db.close()

    # history
    hist = load_json(HIST)
    hist.setdefault(TODAY, {}).update({"cash": args["cash"], "securities_market": args["sec"],
        "insurance_current": args["ins"], "fund_market": args["funds"], "total_assets": total, "net_worth": net,
        "insurance_detail": {"安聯保單A+B 現值": float(snap["allianz_ab_current_value"]),
            "第一金保單 FL65 現值": 1958980.0, "保單總現値": float(args["ins"])}})
    save_json(HIST, hist)

    print(f"  ✅ 現金={args['cash']:,}  保險={args['ins']:,}  證券={args['sec']:,}  基金={args['funds']:,}")
    print(f"  總資產={total:,}")

    # deploy
    if "--penetrate" not in sys.argv:
        print("\n=== 部署 ===")
        r = subprocess.run([sys.executable, str(BASE/"daily_deploy.py")], cwd=BASE, capture_output=True, text=True, timeout=180)
        for line in r.stdout.split("\n"):
            if any(k in line for k in ["OK","DONE","完成","telegram","CIO"]):
                print(f"  {line}")
        if r.returncode != 0:
            print(f"  ❌ {r.stderr[-200:]}")
    print("\n✅ 全部完成")

if __name__ == "__main__":
    main()
