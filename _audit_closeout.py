"""閉環稽核（2026-09-13）：數字一致性、部署、cron、鏡像、殘留檢查。"""
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

R = Path.home() / "Desktop" / "longjiu_system"
H = Path(os.environ["LOCALAPPDATA"]) / "hermes"
T = "2026-09-13"
ok = lambda b: "✅" if b else "❌"
fail = []

# ── 1) 舊數字殘留（全 repo 報告/資料）────────────────────────
print("=== 1) 舊數字殘留掃描 ===")
stale = {
    "30,404,569": "女友借款誤列負債的中間值",
    "4,319,011": "同上淨值",
    "66,699": "舊信用卡 pending",
    "28,101": "舊 cc_liability",
    "71,799": "舊 DB 卡債",
    "15,793": "舊『循環』口徑",
}
for pat, desc in stale.items():
    hits = []
    for f in list(R.glob("*.html")) + list(R.glob("*.json")) + list(R.glob("*.md")):
        if f.name.startswith("_"):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pat in txt:
            hits.append(f.name)
    print(f"  {pat:12s} ({desc}) → {hits if hits else '無 ✅'}")
    if hits and "error_register" not in " ".join(hits) and "work_log" not in " ".join(hits):
        fail.append(f"舊值殘留 {pat} in {hits}")

# ── 2) 四源一致 ────────────────────────────────────────────
print("=== 2) 四源一致 ===")
s = json.loads((R / "snapshot.json").read_text(encoding="utf-8"))
h = json.loads((R / "asset_diff_history.json").read_text(encoding="utf-8"))
db = sqlite3.connect(R / "dragon_assets.db")
d13 = db.execute("select total_assets,total_liabilities from assets where date=?", (T,)).fetchone()
l13 = db.execute("select total_liabilities,credit_card from liabilities where date=?", (T,)).fetchone()
d12 = db.execute("select total_liabilities from assets where date='2026-09-12'").fetchone()[0]
html = (R / f"daily_report_v2_{T}.html").read_text(encoding="utf-8")
checks = [
    ("snapshot 負債 = DB assets = DB liabilities", s["total_liabilities"] == int(d13[1]) == l13[0]),
    ("snapshot 負債 = 日報 HTML", f"{s['total_liabilities']:,}" in html),
    ("snapshot 淨值 = asset_diff_history", int(h[T]["net_worth"]) == s["net_worth"]),
    ("信用卡 34,025 一致", s["cc_liability"] == l13[1] == 34025),
    ("9/12 歷史列未被污染", d12 == 30160643),
    ("應收款備忘 290,500", s["receivables_total"] == 290500 and s["receivables"]["女友借款"] == 290500),
    ("負債拆解可完全解釋", sum([s["liabilities_build_up"]["房貸_含國泰"],
                              s["liabilities_build_up"]["保單借貸"],
                              s["liabilities_build_up"]["券商質押"],
                              s["liabilities_build_up"]["信用卡_當期未繳_全額扣繳"]]) == s["total_liabilities"]),
]
for name, res in checks:
    print(f"  {ok(res)} {name}")
    if not res:
        fail.append(f"四源: {name}")

# ── 3) 線上部署 ────────────────────────────────────────────
print("=== 3) GitHub Pages ===")
BASE = "https://b0988321088.github.io/longjiu-dashboard-2/"
try:
    with urllib.request.urlopen(BASE + f"snapshot.json?t={os.urandom(4).hex()}", timeout=20) as r:
        live = json.loads(r.read().decode("utf-8"))
    num = [
        ("線上負債 = 本機", live["total_liabilities"] == s["total_liabilities"]),
        ("線上淨值 = 本機", live["net_worth"] == s["net_worth"]),
        ("線上有應收款欄位", live.get("receivables_total") == 290500),
    ]
    for name, res in num:
        print(f"  {ok(res)} {name}")
        if not res:
            fail.append(f"線上: {name}")
except Exception as e:
    print(f"  ❌ 線上讀取失敗 {e}")
    fail.append("線上讀取失敗")
for f in [f"daily_report_v2_{T}.html", "index.html", f"asset_diff_{T}.html", f"penetration_report_{T}.html"]:
    try:
        code = urllib.request.urlopen(BASE + f, timeout=20).status
    except Exception as e:
        code = getattr(e, "code", "ERR")
    print(f"  {ok(code == 200)} {f} → {code}")
    if code != 200:
        fail.append(f"連結 {f} = {code}")

# ── 4) git ────────────────────────────────────────────────
print("=== 4) git 狀態 ===")
st = subprocess.run(["git", "status", "--porcelain"], cwd=R, capture_output=True, text=True).stdout.strip().splitlines()
sb = subprocess.run(["git", "status", "-sb"], cwd=R, capture_output=True, text=True).stdout.splitlines()[0]
print(f"  {sb}")
tracked = [x for x in st if not x.startswith("??")]
untracked = [x[3:] for x in st if x.startswith("??")]
print(f"  {ok(not tracked)} 已追蹤檔案無未提交變更（{len(tracked)} 筆）")
print(f"  未追蹤（備份/暫存，預期）：{untracked}")
if tracked:
    fail.append(f"未提交: {tracked}")

# ── 5) hermes/scripts 鏡像 ─────────────────────────────────
print("=== 5) hermes/scripts 鏡像 ===")
for f in ["asset_sync.py", "buffett_cto_analyzer.py", "closing_log.py", "update_data.py", "budget_daily_check.py"]:
    a, b = R / f, H / "scripts" / f
    if not b.exists():
        print(f"  ⚠️ {f} 不在鏡像清單（不適用）")
        continue
    same = a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")
    print(f"  {ok(same)} {f}")
    if not same:
        fail.append(f"鏡像不同步 {f}")

# ── 6) cron jobs ──────────────────────────────────────────
print("=== 6) cron jobs ===")
jp = H / "cron" / "jobs.json"
data = json.loads(jp.read_text(encoding="utf-8"))
jobs = data["jobs"] if isinstance(data, dict) else data
# 刻意停用白名單（2026-09-13）：稽核只認「意外」停用，已核准的收斂/去重停用列 ℹ️ 不列 fail
INTENTIONAL_PAUSED = {
    "1422af3c2905": "9/9 核准：記憶同步重複 cron 收斂，19:00 b18b41e13102 為唯一每日同步",
}
for j in jobs:
    if not isinstance(j, dict):
        continue
    jid = str(j.get("id", ""))[:12]
    name = (j.get("name") or "")[:34]
    scr = j.get("script") or "-"
    na = j.get("no_agent")
    en = j.get("enabled", True)
    sched = j.get("schedule") or j.get("cron") or "-"
    kind = sched.get("kind") if isinstance(sched, dict) else "cron"
    if isinstance(sched, dict):
        sched = sched.get("expr") or sched.get("run_at") or str(sched)[:20]
    if en is False and kind == "once":
        mark = "ℹ️"   # 歷史一次性排程（已完成，停用正常）
    elif en is False and jid in INTENTIONAL_PAUSED:
        mark = "ℹ️"   # 已核准的刻意停用（非意外）
    elif en is False:
        mark = "❌"
        fail.append(f"cron 意外停用：{jid} {name}")
    else:
        mark = "✅"
    print(f"  {mark} {jid:13s} {name:34s} no_agent={str(na):5s} {str(sched)[:12]:12s} {scr}")
    if en is False and jid in INTENTIONAL_PAUSED:
        print(f"       └ 刻意停用：{INTENTIONAL_PAUSED[jid]}")

# ── 7) 快取稽核 / watchdog 檔案 ────────────────────────────
print("=== 7) 監控與稽核檔 ===")
for p in [R / "data" / ".cache_audit.log", R / "data" / ".cache_audit_state.json",
          H / "scripts" / "session_bloat_watch.py"]:
    print(f"  {ok(p.exists())} {p.name}")
print(f"  .cache_audit.log 末行: {(R/'data'/'.cache_audit.log').read_text(encoding='utf-8').strip().splitlines()[-1] if (R/'data'/'.cache_audit.log').exists() else '-'}")

print()
print("=" * 46)
print(f"閉環稽核結果：{'全部通過 ✅' if not fail else '❌ 有問題：' + str(fail)}")
print("=" * 46)
