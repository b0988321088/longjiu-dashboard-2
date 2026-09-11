import importlib.util, json, sys, io, contextlib, tempfile, os
from pathlib import Path
spec = importlib.util.spec_from_file_location("u", r"C:\Users\bot\Desktop\longjiu_system\us30y_monitor.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def run(rows, state, label):
    tmp = Path(tempfile.mkdtemp()) / "s.json"
    tmp.write_text(json.dumps(state), encoding="utf-8")
    m.STATE = tmp
    m.fetch_us30y_fred = lambda: rows
    m.fetch_us30y_yahoo = lambda: []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.main()
    out = buf.getvalue().strip()
    new = json.loads(tmp.read_text(encoding="utf-8"))
    print(f"--- {label}")
    print("  輸出:", repr(out) if out else "(靜默)")
    print("  state: last_rate=%s last_date=%s mode=%s streak=%s red_line=%s src=%s" %
          (new.get("last_rate"), new.get("last_date"), new.get("mode"), new.get("streak"), new.get("red_line"), new.get("data_source")))
    if new.get("red_line_since"): print("  red_line_since:", new["red_line_since"])
    if new.get("mode_label"): print("  mode_label:", new["mode_label"])

A = [("2026-09-11",5.363),("2026-09-10",5.361),("2026-09-09",5.286)]
B = [("2026-09-11",5.363),("2026-09-10",5.361)]
C = [("2026-09-11",5.10),("2026-09-10",5.05),("2026-09-09",5.286)]
D = [("2026-09-11",4.50),("2026-09-10",4.60)]
E = [("2026-09-11",5.15),("2026-09-10",5.10),("2026-09-09",5.28)]

print("=== 功能驗證（合成資料，不碰真實 state）===")
run(A, {"mode":"A","streak":10,"last_rate":5.361,"last_date":"2026-09-10","red_line":False}, "A) 9/10+9/11 皆≥5.30、red_line 未latch → 應發🚫紅線")
run(B, {"mode":"A","streak":11,"last_rate":5.363,"last_date":"2026-09-11","red_line":False}, "B) 同上（真實情況，只有已收盤9/10 → 9/9未達）")
run(C, {"mode":"A","streak":11,"last_rate":5.363,"last_date":"2026-09-11","red_line":True,"red_line_since":"2026-09-10"}, "C) 回落 <5.30、紅線已latch → 應發✅解除")
run(D, {"mode":"A","streak":9,"last_rate":5.28,"last_date":"2026-09-09","red_line":False}, "D) ≤4.90 → 應發🚨模式B切換")
run(E, {"mode":"A","streak":9,"last_rate":5.286,"last_date":"2026-09-09","red_line":False}, "E) 5.10-5.28 維持模式A → 應靜默")
print("=== red_line_hit 單元 ===")
print(" A:", m.red_line_hit(A[:2]), "| B:", m.red_line_hit(B[:2]), "| C:", m.red_line_hit(C[:2]), "| D:", m.red_line_hit(D[:2]))
