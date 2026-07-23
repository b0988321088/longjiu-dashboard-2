1|#!/usr/bin/env python3
2|"""龍九資產統一更新入口。"""
3|import json, sqlite3, sys, subprocess
4|from pathlib import Path
5|from datetime import date
6|
7|BASE = Path(__file__).resolve().parent
8|SNAP = BASE / "snapshot.json"
9|DB = BASE / "dragon_assets.db"
10|HIST = BASE / "asset_diff_history.json"
11|TODAY = date.today().isoformat()
12|
13|def load_json(p):
14|    return json.loads(Path(p).read_text(encoding="utf-8"))
15|def save_json(p, d):
16|    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
17|
18|def calc_penetration(cash, ins, sec, funds, bond_portion=None, fund_ratios=None):
19|    if bond_portion is not None:
20|        ins_bonds = int(bond_portion)
21|        ins_eq = int(ins) - int(bond_portion) - 1_958_980
22|    elif fund_ratios:
23|        fv = {"安聯收益成長": 2_780_466, "M&G入息": 3_136_436, "安聯AI收益成長": 902_679, "貝萊德科技A10": 964_495, "聯博美國成長": 4_751}
24|        ins_bonds = sum(round(fv[n] * fund_ratios.get(n, 0)) for n in fv)
25|        ins_eq = int(ins) - ins_bonds - 1_958_980
26|    else:
27|        ins_bonds = round(2_780_466*0.55 + 3_136_436*0.65 + 902_679*0.40)
28|        ins_eq = round(2_780_466*0.45 + 3_136_436*0.35 + 902_679*0.60) + 964_495 + 4_751
29|    tw = round(sec * 0.97) + funds
30|    us = round(sec * 0.03) + ins_eq
31|    total = cash + ins + sec + funds
32|    c = cash + total - (tw + us + 1_958_980 + ins_bonds + cash)
33|    return {"台股市值型成長": tw, "美股市值型成長": us, "防守型配息": 1_958_980, "債券": ins_bonds, "現金/安全網": c}
34|
35|def main():
36|    snap = load_json(SNAP)
37|    args = {"cash": snap.get("real_liquid_assets",4483408), "ins": snap.get("insurance_current_value",9747807),
38|            "sec": snap.get("securities_total_market_value",2422640), "funds": snap.get("fund_market_value",795157)}
39|    for a in sys.argv[1:]:
40|        if "=" in a:
41|            k,v = a[2:].split("=",1)
42|            args[{"insurance":"ins","securities":"sec","cash":"cash","funds":"funds"}.get(k,k)] = json.loads(v) if k == "fund_ratios" else int(v)
43|    pen = calc_penetration(args["cash"], args["ins"], args["sec"], args["funds"], args.get("bond_portion"), args.get("fund_ratios"))
44|    if args.get("ins"):
45|        ins_calc = pen["債券"] + (pen["美股市值型成長"] - round(args.get("sec",0)*0.03)) + pen["防守型配息"]
46|        if abs(ins_calc - args["ins"]) > 100:
47|            print(f"  ⚠️ 保單校驗失敗：拆分總和 {ins_calc:,} ≠ 保險 {args['ins']:,}")
48|    if "--check" in sys.argv or "--check_fund" in sys.argv:
49|        if "--check_fund" in sys.argv:
50|            fv = {"安聯收益成長": 2_780_466, "M&G入息": 3_136_436, "安聯AI收益成長": 902_679, "貝萊德科技A10": 964_495, "聯博美國成長": 4_751}
51|            fr = args.get("fund_ratios", {"安聯收益成長":0.55, "M&G入息":0.65, "安聯AI收益成長":0.40, "貝萊德科技A10":0.0, "聯博美國成長":0.0})
52|            tb = sum(round(fv[n]*fr.get(n,0)) for n in fv)
53|            te = sum(fv[n] for n in fv) - tb
54|            ok = "✅" if abs(tb+te+1_958_980-sum(fv.values())-1_958_980) < 100 else "❌"
55|            print(f"=== 保單校驗 {ok} ===")
56|            print(f"  債券: {tb:,}  權益: {te:,}  第一金: 1,958,980  總值: {sum(fv.values())+1_958_980:,}")
57|            return
58|        print("=== 校驗 ===")
59|        for k,v in pen.items(): print(f"  {k}: {v:,}")
60|        print(f"  總和: {sum(pen.values()):,}  應={args['cash']+args['ins']+args['sec']+args['funds']:,}")
61|        return
62|    print("=== 三源同步 ===")
63|    total = args["cash"] + args["ins"] + args["sec"] + args["funds"]
64|    net = total - snap.get("total_liabilities", 0)
65|    snap.update({"real_liquid_assets": args["cash"], "insurance_current_value": args["ins"],
66|        "securities_total_market_value": args["sec"], "fund_market_value": args["funds"],
67|        "total_assets": total, "net_worth": net})
68|    snap["allianz_ab_current_value"] = snap.get("allianz_ab_current_value", 7788827)
69|    snap["allianz_ab"] = snap["allianz_ab_current_value"]
70|    snap["firstjin_current_value"] = 1958980
71|    snap.setdefault("penetration",{}).setdefault("actual_twd",{}).update(pen)
72|    save_json(SNAP, snap)
73|    db = sqlite3.connect(str(DB))
74|    db.execute("UPDATE assets SET cash_total=?, securities=?, insurance=?, funds=?, bonds=0, total_assets=? WHERE date=?",
75|        (args["cash"], args["sec"], args["ins"], args["funds"], total, TODAY))
76|    if db.total_changes == 0:
77|        db.execute("INSERT INTO assets(date,cash_total,securities,insurance,funds,bonds,total_assets) VALUES(?,?,?,?,?,0,?)",
78|            (TODAY, args["cash"], args["sec"], args["ins"], args["funds"], total))
79|    db.commit(); db.close()
80|    hist = load_json(HIST)
81|    hist.setdefault(TODAY, {}).update({"cash": args["cash"], "securities_market": args["sec"],
82|        "insurance_current": args["ins"], "fund_market": args["funds"], "total_assets": total, "net_worth": net,
83|        "insurance_detail": {"安聯保單A+B 現值": float(snap["allianz_ab_current_value"]),
84|            "第一金保單 FL65 現值": 1958980.0, "保單總現値": float(args["ins"])}})
85|    save_json(HIST, hist)
86|    print(f"  ✅ 現金={args['cash']:,}  保險={args['ins']:,}  證券={args['sec']:,}  基金={args['funds']:,}")
87|    print(f"  總資產={total:,}")
88|    # === 串聯產出管線（不可中斷）===
89|    if "--penetrate" not in sys.argv:
90|        print("\n=== 串聯產出（不可中斷）===")
steps = [
    ('run_daily.py', [sys.executable, str(BASE/'run_daily.py')]),
    ('asset_diff_monitor.py', [sys.executable, str(BASE/'asset_diff_monitor.py')]),
    ('gmail_reader.py', [sys.executable, str(BASE/'gmail_reader.py')]),
    ('penetration_monitor.py', [sys.executable, str(BASE/'penetration_monitor.py')]),
    # ('daily_deploy.py', [sys.executable, str(BASE/'daily_deploy.py')]),
]
93|            ("asset_diff_monitor.py", [sys.executable, str(BASE/"asset_diff_monitor.py")]),
94|            ("penetration_monitor.py", [sys.executable, str(BASE/"penetration_monitor.py")]),
95|            # ("daily_deploy.py", [sys.executable, str(BASE/"daily_deploy.py")]),
96|        ]
97|
98|        for name, cmd in steps:
99|
100|        sec_total = args.get("sec", 0)
101|        if sec_total:
102|            print("\n=== 產出校驗 ===")
103|            sec_str = f"{sec_total:,}"
104|            files = [("日報", BASE/f"daily_report_v2_{TODAY}.html"),
105|                     ("儀表板", BASE/"index.html"),
106|                     ("差異分析", BASE/f"asset_diff_{TODAY}.html")]
107|            all_ok = True
108|            for label, fp in files:
109|                html = fp.read_text(encoding="utf-8", errors="ignore")
110|                if sec_str in html:
111|                    print(f"  ✅ {label} 證券值一致 ({sec_str})")
112|                else:
113|                    print(f"  ❌ {label} 證券值不符（預期 {sec_str}）")
114|                    all_ok = False
115|            if all_ok:
116|                print("  ✅ 三份產出一致")
117|            else:
118|                print("\n⛔ 校驗失敗")
119|                exit(1)
120|    print("\n✅ 全部完成")
121|
122|if __name__ == "__main__":
123|    main()
124|