#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""it_health_alert_check.py — A 案整合測試（2026-10-10 建立；2026-10-13 修硬編碼假設）

── 2026-10-13 修正（使用者核准方案 1；原裁決「限施工與驗收」之另行發布前置）──

── 2026-10-13 已知失效（記錄，不另案；使用者裁決：測試對照組污染）────────────────
A 案已於 2026-10-13 發布，並依部署範圍把 `hermes/scripts/health_alert_check.py`
由 `28a3b769`（舊版）同步為 `e27792b1`（新版）。本檔的 ORIG 對照組正是讀那條路徑，
於是 ORIG 與 NEW 變成同一份內容 → Part 2 的兩個負向對照（分數 55 應重現紅燈、
曝險 72% 應重現誤報）自此必然 FAIL（實測 21/23）。

性質：**部署後對照組污染**，非程式缺陷，**不影響線上行為**。
A 案的驗收證據以部署前那一輪為準（單元 21/21、整合 23/23、cron 實跑 🟡）。
要恢復可重現的負向對照，需另存「部署前版本」當基準檔 —— 依裁決列為記錄（不擴大成新工單）。
P1 的必要驗收不依賴本檔（見 tools/test_p1_review_gate.py，全數自足）。

根因確認（先行唯讀盤點已定位到行號）：原版把 2026-10-10 **當日實況**寫死在斷言裡，
跨日必然失效。2026-10-13 實跑為 9/12，三個 FAIL 全部來自過期硬編碼、與原修復程式無關：

  :76  「原版有『健康分數』字樣」   → 原版只在分數 <60 才印；今日 93 🟢 不印
  :86  「修改版仍輸出 🔴 現金紅線」 → 今日現金未低於底線，紅線本就不該觸發
  :89  「明細仍含曝險現值 71.4」    → 71.4 是 10-10 當日值，今日 69.5

修法（不刪斷言、不降強度、不使用寬鬆字串比對）：
  Part 1  真實環境端到端 —— 斷言一律**由當次 snapshot 推導**（曝險現值、五維紅線一致性），
          不再假設任一維度必定觸發。
  Part 2  情境注入 —— 以可控 d 餵入**兩版** main()，**主動建立**紅線觸發／非觸發與分數紅燈
          的測試條件，缺陷對照（負向對照）不再依賴當日資料。
  Part 3  紅線政策不變 —— 同一組合成輸入下，兩版 🔴 維度集合必須一致（A 案只動推播層）。

硬線：本檔不修改受測程式；`health_alert_check.py` 的判定政策、紅線門檻一律不動。
執行：python tools/it_health_alert_check.py
"""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")
ORIG = Path(os.path.expandvars(r"%LOCALAPPDATA%/hermes/scripts/health_alert_check.py"))
NEW = REPO / "health_alert_check.py"      # 2026-10-13：執行檔移至 repo 根目錄（alerts.py 取用點）
STATE = REPO / "health_alert_state.json"

# 🔴 紅線維度（美元曝險已移出紅線 → 不列入兩版比對，其差異由 Part 2 專項驗證）
RED_DIMS = ("LTV", "現金", "覆蓋率", "防禦維度")

# 乾淨基底：所有維度都在安全區，只有被測維度依情境變動
SAFE = dict(LTV=24.3, 曝險=59.9, 現金=900000, 覆蓋=113.0, 防禦=48.5, 分數=93, 燈號="🟢")


def run_real(path):
    """以 cron 相同方式（subprocess）執行受測程式。"""
    r = subprocess.run([sys.executable, str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(REPO))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def real_today_figures():
    """獨立 process + 真模組算出當日五維度，避免與本檔 Part 2 的 stub 互相污染。"""
    code = (
        "import json,sys;sys.path.insert(0,r'{repo}');"
        "from report_components import render_health_score as f;"
        "print(json.dumps(f(json.load(open(r'{snap}',encoding='utf-8'))),ensure_ascii=False))"
        .format(repo=REPO.as_posix(), snap=(REPO / "snapshot.json").as_posix())
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=str(REPO))
    try:
        return json.loads((r.stdout or "").strip().splitlines()[-1])
    except Exception:
        return None


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def run_injected(mod, d, th=(60.0, 65.0, 70.0)):
    """把 report_components／usd_advisory 換成可控 stub、REPO 導向臨時目錄 → 回傳 main() stdout。

    不觸碰真 snapshot 與真 state 檔；結束後完整還原模組狀態。
    """
    tmp = Path(tempfile.mkdtemp(prefix="it_health_"))
    (tmp / "snapshot.json").write_text("{}", encoding="utf-8")
    rc_stub = types.ModuleType("report_components")
    rc_stub.render_health_score = lambda snap: dict(d)
    ua_stub = types.ModuleType("usd_advisory")
    ua_stub.policy = lambda snap: {"目標": th[0], "黃": th[1], "紅": th[2]}
    old_rc = sys.modules.get("report_components")
    old_ua = sys.modules.get("usd_advisory")
    old_repo = mod.REPO
    try:
        sys.modules["report_components"] = rc_stub
        sys.modules["usd_advisory"] = ua_stub
        mod.REPO = tmp
        buf = io.StringIO()
        with redirect_stdout(buf):
            mod.main()
        return buf.getvalue()
    finally:
        mod.REPO = old_repo
        if old_rc is not None:
            sys.modules["report_components"] = old_rc
        else:
            sys.modules.pop("report_components", None)
        if old_ua is not None:
            sys.modules["usd_advisory"] = old_ua
        else:
            sys.modules.pop("usd_advisory", None)


def red_dims(out):
    """抽出「以 🔴 開頭的行」所屬的紅線維度集合（排除已移出紅線的美元曝險）。"""
    s = set()
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("🔴") or "美元曝險" in line:
            continue
        for k in RED_DIMS:
            if k in line:
                s.add(k)
    return s


def main():
    if not ORIG.exists():
        print("❌ 找不到原版：%s" % ORIG)
        return 1
    if not NEW.exists():
        print("❌ 找不到部署版：%s" % NEW)
        return 1

    checks = []

    def chk(label, ok, detail=""):
        checks.append((label, bool(ok), detail))

    # ── Part 1：真實環境端到端（斷言一律由當次真值推導）────────────────────────
    bak = STATE.read_bytes() if STATE.exists() else None
    try:
        rc_o, o, eo = run_real(ORIG)
        rc_n, n, en = run_real(NEW)
    finally:
        if bak is not None:
            STATE.write_bytes(bak)
    print("===== ORIG（hermes/scripts，線上現行）rc=%d =====" % rc_o)
    print(o.strip() or "(空輸出＝靜默)")
    print("===== NEW（repo 根目錄，待發布）rc=%d =====" % rc_n)
    print(n.strip() or "(空輸出＝靜默)")
    restored = (STATE.read_bytes() == bak) if bak is not None else None
    print("state 還原檢查：%s" % ("✅ 與跑前相同" if restored else "⚠️ 不同"))
    print()

    figs = real_today_figures()
    usd = figs.get("曝險") if figs else None
    cash = figs.get("現金") if figs else None
    ltv = figs.get("LTV") if figs else None
    cov = figs.get("覆蓋") if figs else None
    dfn = figs.get("防禦") if figs else None

    chk("Part1 真實環境：新版不含已移除的『紅線50』文案",
        "紅線50" not in n and "> 60" not in n)
    chk("Part1 真實環境：新版不含『健康分數』觸發字樣", "健康分數" not in n)
    chk("Part1 真實環境：新版明細曝險值＝當次 snapshot 現值（不再固定 71.4）",
        usd is not None and ("曝險 %.1f%%" % usd) in n,
        "當次曝險=%s" % (("%.1f%%" % usd) if usd is not None else "取不到真值"))
    chk("Part1 真實環境：🔴 現金 判定與當次真值一致",
        cash is not None and (("🔴 現金" in n) == (cash < 700000)),
        "當次現金=%s（<底線=%s）" % (cash, (cash is not None and cash < 700000)))
    chk("Part1 真實環境：🔴 LTV 判定與當次真值一致",
        ltv is not None and (("🔴 LTV" in n) == (ltv > 50)),
        "當次 LTV=%s" % ltv)
    chk("Part1 真實環境：🔴 覆蓋率 判定與當次真值一致",
        cov is not None and (("🔴 覆蓋率" in n) == (cov < 100)),
        "當次覆蓋=%s" % cov)
    chk("Part1 真實環境：🔴 防禦維度 判定與當次真值一致",
        dfn is not None and (("🔴 防禦維度" in n) == (dfn < 40)),
        "當次防禦=%s" % dfn)
    chk("Part1 真實環境：state 檔測試後逐位元還原", restored is True)
    if eo.strip():
        print("[ORIG stderr]", eo.strip().splitlines()[-1][:200])
    if en.strip():
        print("[NEW stderr]", en.strip().splitlines()[-1][:200])

    # ── Part 2：情境注入（主動建立觸發條件；缺陷對照不依賴當日資料）─────────────
    orig_mod = load_module(ORIG, "ha_orig")
    new_mod = load_module(NEW, "ha_new")

    out_new_cash_red = run_injected(new_mod, dict(SAFE, 現金=500000))
    chk("Part2 情境注入：現金低於底線 → 新版仍輸出 🔴 現金紅線（主動建立觸發條件）",
        "🔴 現金" in out_new_cash_red)
    out_new_cash_ok = run_injected(new_mod, dict(SAFE, 現金=900000))
    chk("Part2 情境注入：現金高於底線 → 新版不輸出 🔴 現金紅線",
        "🔴 現金" not in out_new_cash_ok)

    out_orig_score = run_injected(orig_mod, dict(SAFE, 分數=55))
    out_new_score = run_injected(new_mod, dict(SAFE, 分數=55))
    chk("Part2 情境注入：分數 55 → 原版重現『健康分數』紅燈（缺陷存在證明）",
        "健康分數" in out_orig_score)
    chk("Part2 情境注入：分數 55 → 新版不再因分數推紅燈（修復生效）",
        "健康分數" not in out_new_score)

    out_orig_usd = run_injected(orig_mod, dict(SAFE, 曝險=72.0))
    out_new_usd = run_injected(new_mod, dict(SAFE, 曝險=72.0))
    chk("Part2 情境注入：曝險 72% → 原版誤報 🔴 美元曝險（缺陷存在證明）",
        "🔴 美元曝險" in out_orig_usd)
    chk("Part2 情境注入：曝險 72% → 新版為 🟡 高曝險觀察線且無 🔴 美元曝險",
        "🟡" in out_new_usd and "高曝險觀察線" in out_new_usd and "🔴 美元曝險" not in out_new_usd)
    out_new_649 = run_injected(new_mod, dict(SAFE, 曝險=64.9))
    chk("Part2 情境注入：曝險 64.9%（未達黃色門檻）→ 新版不觸發任何曝險提示",
        "美元曝險" not in out_new_649)
    out_new_695 = run_injected(new_mod, dict(SAFE, 曝險=69.5))
    chk("Part2 情境注入：曝險 69.5% → 新版為 🟡 黃色觀察區",
        "黃色觀察區" in out_new_695 and "🔴 美元曝險" not in out_new_695)

    # ── Part 3：紅線政策不變（A 案只動推播層；同一輸入下兩版 🔴 維度必須一致）──
    cases = [
        ("全安全", SAFE),
        ("現金紅線", dict(SAFE, 現金=500000)),
        ("LTV 紅線", dict(SAFE, LTV=55.0)),
        ("覆蓋紅線", dict(SAFE, 覆蓋=95.0)),
        ("防禦紅線", dict(SAFE, 防禦=35.0)),
        ("四線同時", dict(SAFE, LTV=55.0, 現金=500000, 覆蓋=95.0, 防禦=35.0)),
        ("邊界值（LTV 50 / 現金 700000 / 覆蓋 100 / 防禦 40）",
         dict(SAFE, LTV=50.0, 現金=700000, 覆蓋=100.0, 防禦=40.0)),
    ]
    for name, d in cases:
        ro = red_dims(run_injected(orig_mod, d))
        rn = red_dims(run_injected(new_mod, d))
        chk("Part3 紅線政策不變：%s → 兩版 🔴 維度集合一致" % name, ro == rn,
            "ORIG=%s / NEW=%s" % (sorted(ro), sorted(rn)))

    # ── 結果 ────────────────────────────────────────────────────────────────
    print("─" * 62)
    print("整合測試結果：")
    bad = 0
    for label, ok, detail in checks:
        mark = "✅" if ok else "❌"
        if not ok:
            bad += 1
        print("  %s %s%s" % (mark, label, ("｜%s" % detail) if detail else ""))
    print("─" * 62)
    print("%d/%d PASS" % (len(checks) - bad, len(checks)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
