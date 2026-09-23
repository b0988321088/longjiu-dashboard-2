"""閉環稽核（2026-09-14 v2）：數字一致性、部署、cron、鏡像、殘留、排程認領檢查。

基準日 T 動態化（2026-09-14）：預設今天；DB 尚無今天資料（上午跑／假日）→ 退回最新已落庫日。
可用 LJ_AUDIT_DATE=YYYY-MM-DD 覆寫（補跑歷史稽核用）。
"""
import datetime as _dtime
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

R = Path.home() / "Desktop" / "longjiu_system"
H = Path(os.environ["LOCALAPPDATA"]) / "hermes"
ok = lambda b: "✅" if b else "❌"
fail = []
# 預期由其他排程每日更新的狀態檔（髒了不算 fail）：21:40 收工登錄會改 .cache_audit_state.json
BENIGN_DIRTY = {"data/.cache_audit_state.json"}


def resolve_T(db):
    """回傳 (基準日, 是否為 fallback)。今天資料尚未落庫時退回最新已落庫日。"""
    want = os.environ.get("LJ_AUDIT_DATE") or _dtime.date.today().isoformat()
    if db.execute("select 1 from assets where date=?", (want,)).fetchone():
        return want, False
    latest = (db.execute("select max(date) from assets").fetchone() or [None])[0]
    return (latest or want), True


T = os.environ.get("LJ_AUDIT_DATE") or _dtime.date.today().isoformat()

# ── 1) 舊數字殘留（全 repo 報告/資料）────────────────────────
_T_SCAN = T  # 本次基準日（供歷史/現行分類）
print("=== 1) 舊數字殘留掃描 ===")
print("  （本區僅供追蹤：命中『歷史歸檔/錯誤帳本』不列為問題；只有出現『現行檔』才算 ❌）")


def _is_hist(name: str) -> bool:
    """歷史歸檔或帳本檔：舊數字本來就該留在裡面（不列為問題）。

    2026-09-15 修正：檔名只有「日期 != 基準日 T」才算歷史歸檔 → 今日日報若殘留舊值仍會亮
    ⚠️ 現行檔（首版用「檔名含 _20xx-xx-xx 就算歷史」會把今日報告一起放行，等於遮蔽真問題，
    負向測試抓到）。帳本/封存類無日期可比者一律視為歷史。
    """
    for k in ("error_register", "work_log", "card_caliber_assessment", "BUDGET_WEEKLY_REPORT"):
        if k in name:
            return True
    m = re.search(r"(20\d\d-\d\d-\d\d)", name)
    if m:
        return m.group(1) != _T_SCAN
    return False
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
    if not hits:
        print(f"  {pat:12s} ({desc}) → 無 ✅")
    else:
        _live = [h for h in hits if not _is_hist(h)]
        _tail = f"⚠️ 現行檔 {_live}" if _live else f"歷史 {len(hits)} 筆（不列問題）"
        print(f"  {pat:12s} ({desc}) → {_tail}")
    if hits and "error_register" not in " ".join(hits) and "work_log" not in " ".join(hits):
        fail.append(f"舊值殘留 {pat} in {hits}")

# ── 1b) 寫死日期/金額掃描（現行 .py；2026-09-15 新增）────────────
# 背景：使用者實際回報的錯誤都是「程式裡寫死的舊日期／舊金額」——事件過去了還天天印在報表上
# （薪資 39,727＝8 月值、里程碑 8/24/8/31、計畫標題「8/29 全資產面結論」）。舊數字殘留掃描
# 只掃產出檔（漏掉生產者），本區掃生產者：現行 .py 內若出現「寫死日期/金額」的輸出字串即列問題。
# 排除：.archive/、_ 開頭檔、以及含「原/寫死/舊/歷史/INC-/＃」的敘述行（檢討紀錄本來就會寫到舊值）。
print("=== 1b) 寫死日期/金額掃描（現行 .py）===")
_HARD_PAT = [
    (re.compile(r"（\d{1,2}/\d{1,2}[^）」\n]{0,12}結論"), "計畫標題寫死日期"),
    (re.compile(r"\d+月新增[:：]"), "寫死月份的新增敘述"),
    (re.compile(r"\d+月台幣乾粉分配"), "寫死月份的乾粉卡標題"),
    (re.compile(r"(?:月薪|薪資|salary)[^\n\"']{0,12}39,?727"), "寫死舊薪資 39,727"),
    # 2026-09-16（INC-207）：防守合併口徑是每天裁決依據，寫死會與 snapshot 對不上。
    # 動態寫法（f"...{x:.1f}%"）不含字面數字，不會命中。
    (re.compile(r"防守合併口徑\s*\d+(?:\.\d+)?%"), "寫死防守合併口徑%"),
]
_hard_hits = []
for _f in sorted(R.rglob("*.py")):
    if ".archive" in _f.parts or _f.name.startswith("_"):
        continue
    try:
        _lines = _f.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        continue
    for _i, _l in enumerate(_lines, 1):
        if _l.lstrip().startswith("#"):
            continue  # 純註解行
        # 敘述行（檢討紀錄本來就會寫到舊值）：含這些字樣不列問題
        # （不可用單一 '#' 判斷——CSS 顏色如 #22c55e 會把真缺陷誤放行，2026-09-15 自踩）
        if any(_k in _l for _k in ("寫死", "舊", "歷史", "INC-", "已作廢")):
            continue
        for _rx, _desc in _HARD_PAT:
            if _rx.search(_l):
                _hard_hits.append(f"{_f.name}:{_i} {_desc}")
                break
if _hard_hits:
    print(f"  ❌ {len(_hard_hits)} 處：" + "；".join(_hard_hits[:6]))
    fail.append(f"寫死日期/金額 {len(_hard_hits)} 處：{_hard_hits[:3]}")
else:
    print("  ✅ 無寫死日期/金額（現行 .py 全數動態）")

# ── 2) 四源一致 ────────────────────────────────────────────
print("=== 2) 四源一致 ===")
s = json.loads((R / "snapshot.json").read_text(encoding="utf-8"))
h = json.loads((R / "asset_diff_history.json").read_text(encoding="utf-8"))
db = sqlite3.connect(R / "dragon_assets.db")
T, T_fallback = resolve_T(db)
print(f"  基準日 T = {T}" + ("（今日尚未落庫 → 退回最新已落庫日）" if T_fallback else ""))
d13 = db.execute("select total_assets,total_liabilities from assets where date=?", (T,)).fetchone() or (None, None)
# 2026-09-15：DB liabilities 只在「負債有變動」的日子落列（唯一寫入入口 asset_sync.py --rebuild-liabilities）。
# 當天沒有新列時，原本 `l13[0]` 會 TypeError 中斷整份稽核 → 只吐 traceback、沒有結論行（收工檢查變靜默假失敗）。
# 改為取「≤T 的最新一列」當基準（語意正確：負債當日未變動＝沿用上次落庫值），並在完全查無列時以 fail 回報而非崩潰。
_lt_row = db.execute("select date from liabilities where date<=? order by date desc limit 1", (T,)).fetchone()
L_SRC = _lt_row[0] if _lt_row else None
l13 = (db.execute("select total_liabilities,credit_card from liabilities where date=?", (L_SRC,)).fetchone()
       if L_SRC else None)
print(f"  DB 負債基準列 = {L_SRC or '（查無任何列）'}" + ("" if L_SRC == T else f"（T={T} 當日未變動 → 沿用最近落庫列）"))
# 歷史列未被污染：兩表所有「同日都有列」的日期，總負債必須相同
# （原寫死 9/12/30160643 單日值 → 2026-09-14 改為全歷史動態；liabilities 表本來就只在變動日落列）
hist_days = db.execute("select count(*) from liabilities l join assets a on a.date=l.date").fetchone()[0]
hist_bad = db.execute(
    "select l.date, l.total_liabilities, a.total_liabilities from liabilities l "
    "join assets a on a.date = l.date where l.total_liabilities != a.total_liabilities").fetchall()
html = (R / f"daily_report_v2_{T}.html").read_text(encoding="utf-8")
# 2026-09-14：以下兩個檢查原寫死 34,025（信用卡）與 290,500（應收款）→ 真值一變就每晚假 ❌
# （cc 9/14 已由 34,025→60,810；應收款 10/5 起每月累計 1,250 利息也會變）。改為跨源一致＋內部可重建，
# 數值仍印在檢查名上供人眼比對變動，但不再用凍結常數判定（違反 no-hardcode-mandate）。
_cc = int(s["cc_liability"])
_rec = int(s["receivables_total"])
_bup = s["liabilities_build_up"]
_bd = (s.get("receivables_breakdown") or {})["女友借款"]
checks = [
    (f"snapshot 負債 = DB assets = DB liabilities（DB 負債列 = {L_SRC or '無'}）",
     bool(l13) and d13[1] is not None and s["total_liabilities"] == int(d13[1]) == l13[0]),
    ("snapshot 負債 = 日報 HTML", f"{s['total_liabilities']:,}" in html),
    ("snapshot 淨值 = asset_diff_history", int(h[T]["net_worth"]) == s["net_worth"]),
    (f"信用卡當期未繳三源一致（{_cc:,}）", bool(l13) and _cc == l13[1] == _bup["信用卡_當期未繳_全額扣繳"]),
    (f"歷史列未被污染（{hist_days} 個重疊日 assets = liabilities）", hist_days > 0 and not hist_bad),
    (f"應收款備忘可重建（{_rec:,}）", _rec == s["receivables"]["女友借款"] == _bd["本金"] + _bd["未收利息"]),
    ("負債拆解可完全解釋", sum([_bup["房貸_含國泰"],
                              _bup["保單借貸"],
                              _bup["券商質押"],
                              _bup["信用卡_當期未繳_全額扣繳"]]) == s["total_liabilities"]),
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
        # 2026-09-14（CIO REJECT 指出）：原 `== 290500` 寫死 → 10/5 起利息累計後線上檢查會假 ❌
        (f"線上應收款 = 本機（{s['receivables_total']:,}）", live.get("receivables_total") == s["receivables_total"]),
    ]
    for name, res in num:
        print(f"  {ok(res)} {name}")
        if not res:
            fail.append(f"線上: {name}")
except Exception as e:
    print(f"  ❌ 線上讀取失敗 {e}")
    fail.append("線上讀取失敗")
import time as _time  # INC-220b：連結檢查重試用（區域匯入，僅此段需要）
for f in [f"daily_report_v2_{T}.html", "index.html", f"asset_diff_{T}.html", f"penetration_report_{T}.html"]:
    # INC-220b（2026-09-18 實例）：Pages/CDN 在推送後偶有短暫非 200，一次就判 ERR 會產生假 ❌
    # → 改為最多 2 次嘗試（間隔 5 秒）；仍非 200 才列問題，並標註已重試。
    code = "ERR"
    for _attempt in range(2):
        try:
            code = urllib.request.urlopen(BASE + f, timeout=20).status
        except Exception as e:
            code = getattr(e, "code", "ERR")
        if code == 200:
            break
        if _attempt == 0:
            _time.sleep(5)
    print(f"  {ok(code == 200)} {f} → {code}" + ("" if code == 200 else "（已重試仍失敗）"))
    if code != 200:
        fail.append(f"連結 {f} = {code}")

# ── 4) git ────────────────────────────────────────────────
print("=== 4) git 狀態 ===")
st = subprocess.run(["git", "status", "--porcelain"], cwd=R, capture_output=True, text=True).stdout.strip().splitlines()
sb = subprocess.run(["git", "status", "-sb"], cwd=R, capture_output=True, text=True).stdout.splitlines()[0]
print(f"  {sb}")
# 注意：本機 git 的 porcelain 是「<1 碼狀態><空白><路徑>」（非標準 XY+空白），字元切片會切錯 →
# 一律用 git diff --name-only 取「已追蹤且被改動」的精準路徑，porcelain 只用於顯示未追蹤清單。
_dirty = (
    subprocess.run(["git", "diff", "--name-only"], cwd=R, capture_output=True, text=True).stdout.split()
    + subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=R, capture_output=True, text=True).stdout.split()
)
benign = [p for p in _dirty if p.replace("\\", "/") in BENIGN_DIRTY]
tracked = [p for p in _dirty if p.replace("\\", "/") not in BENIGN_DIRTY]
untracked = [x.split(" ", 1)[1] for x in st if x.startswith("??")]
print(f"  {ok(not tracked)} 已追蹤檔案無未提交變更（{len(tracked)} 筆）")
if benign:
    print(f"  ℹ️ 由排程每日更新、當下尚未提交的狀態檔（不列 fail）：{benign}")
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
    _rep = j.get("repeat") or {}
    try:
        _limited_done = (_rep.get("times") is not None
                         and int(_rep.get("completed") or 0) >= int(_rep.get("times") or 0))
    except (TypeError, ValueError):
        _limited_done = False
    if en is False and kind == "once":
        mark = "ℹ️"   # 歷史一次性排程（已完成，停用正常）
    elif en is False and _limited_done:
        mark = "ℹ️"   # 限次排程（repeat.times 已跑完 → 自動停用屬正常；2026-09-18 INC-220）
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

# ── 8) 手動 fire 誤認領排程時點（2026-09-14 INC-172）────────
# 手動 fire（cronjob run / CLI cron run）會把「下一個排程時點」寫成該執行列的 scheduled_instant
# 並標 completed → 到點時 tick 用 completed_occurrence() 判定已完成而跳過（該次排程靜默消失）。
# 判準：status='completed' 且 scheduled_instant 在「未來」= 不可能成立的狀態（零誤報）。
print("=== 8) 手動 fire 認領排程時點 ===")
try:
    import datetime as _dt
    _ex = sqlite3.connect(H / "cron" / "executions.db")
    _now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    _names = {str(j.get("id")): (j.get("name") or "") for j in jobs if isinstance(j, dict)}
    _row = _ex.execute(
        "SELECT job_id, started_at, scheduled_instant FROM executions "
        "WHERE status='completed' AND scheduled_instant IS NOT NULL AND scheduled_instant > ? "
        "ORDER BY scheduled_instant", (_now,)).fetchall()
    if _row:
        for _jid, _start, _inst in _row:
            print(f"  ❌ {str(_jid)[:12]} {_names.get(str(_jid), '')[:26]}"
                  f"｜{str(_start)[:16]} 手動執行即標記完成未來時點 {_inst}")
            fail.append(f"排程時點被吃掉：{_jid} @ {_inst}")
        print("     └ 修法：python release_claimed_occurrences.py --fix（釋放後補跑該次產出）")
    else:
        print("  ✅ 沒有『未來時點已標完成』的執行列")
    _ex.close()
except Exception as _e:
    print(f"  ❌ 讀取 executions.db 失敗 {_e}")
    fail.append("executions.db 讀取失敗")

# ── 9) 決策狀態一致（2026-09-14 新增）──────────────────────
# 觸發：CIO 抓到「DS 儲值已入帳，待辦狀態沒回收」。兩份決策檔語意不同但同一件事會同時存在，
# 一旦只在其中一份回收狀態，日報／CIO 復盤就會用過期前提（dashboard_decisions.json 是 CIO Part A 的輸入）。
# 判準：同標題項在 pending_decisions.json 已標結案標記，dashboard_decisions.json 的 pending 不得仍無結案標記。
print("=== 9) 決策狀態一致（pending_decisions.json ↔ dashboard_decisions.json）===")
try:
    _pd_std = json.loads((R / "pending_decisions.json").read_text(encoding="utf-8"))
    _pd_dash = json.loads((R / "dashboard_decisions.json").read_text(encoding="utf-8"))["pending_decisions"]
    _CLOSED = ("✅", "已結案", "已定案", "已閉環", "已完成")
    _std = {x.get("title"): str(x.get("status", "")) for x in _pd_std if isinstance(x, dict)}
    _drift = []
    for _e in _pd_dash:
        if not isinstance(_e, dict):
            continue
        _new = _std.get(_e.get("action"))
        if _new is None:
            continue
        if any(_m in _new for _m in _CLOSED) and not any(_m in str(_e.get("status", "")) for _m in _CLOSED):
            _drift.append(_e.get("action"))
    if _drift:
        for _t in _drift:
            print(f"  ❌ {str(_t)[:52]}｜pending_decisions.json 已結案，dashboard_decisions.json 仍列未完成")
        fail.append(f"決策狀態未回收: {_drift}")
    else:
        print(f"  ✅ 已結案項目狀態一致（比對 {len(_std)} 筆）")
except Exception as _e:
    print(f"  ❌ 決策檔讀取失敗 {_e}")
    fail.append("決策檔讀取失敗")

# ── 10) 管線 JSON 寫入 indent 一致（2026-09-14 新增／INC-184）──────────────
# 各檔 canonical indent 不同（round-trip 位元比對的唯一解）：
#   schedule_events / pending_decisions / dashboard_decisions = 2；snapshot / work_log / radar_state = 1
# 用錯 indent → 整檔重排、上千行假 diff（掩蓋真改動）。這裡掃 repo 內 .py 的 json.dump 呼叫，
# 解析寫入目標（字面檔名 → 同檔常數 → 鄰近上下文），indent 與 canonical 不符即 ❌。
_CANON_INDENT = {"schedule_events.json": 2, "pending_decisions.json": 2, "dashboard_decisions.json": 2,
                 "snapshot.json": 1, "work_log.json": 1, "radar_state.json": 1}
print("=== 10) 管線 JSON 寫入 indent 一致 ===")
try:
    _bad = []
    for _p in sorted(R.glob("*.py")):
        if _p.name.startswith("_") and not _p.name.endswith("_report.py"):
            pass  # 仍要掃 `_xxx.py`（歷史 ad-hoc 腳本也會被重跑），故不跳過
        try:
            _lines = _p.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        _const = {}
        for _l in _lines:
            _m = re.search(r"(\w+)\s*=\s*[^=\n]*?[\"']([\w\-]+\.json)[\"']", _l)
            if _m:
                _const[_m.group(1)] = _m.group(2)
        for _i, _l in enumerate(_lines):
            if "json.dump" not in _l:
                continue
            # 只看這次呼叫本身（含續行 2 行）。用 ±8 行上下文會把鄰近其他檔案的寫入誤算進來（實測誤判 safe_update.py:54）
            _seg = "\n".join(_lines[_i:min(len(_lines), _i + 3)])
            _mm = re.search(r"indent\s*=\s*(\d+)", _seg)
            if not _mm:
                continue
            _ind = int(_mm.group(1))
            _tgt = None
            for _f in _CANON_INDENT:
                # 邊界比對：避免 rebalance_snapshot.json / tactical_table_*.json 被子字串誤中（實測誤判 action_loop/tactical_table）
                if re.search(r"(?<![\w\-.])" + re.escape(_f), _seg):
                    _tgt = _f
                    break
            if _tgt is None:  # 同檔常數（SNAP / DEC / EVENTS...）→ 檔名
                for _var, _f in _const.items():
                    if _f in _CANON_INDENT and re.search(r"(?<![\w.])" + re.escape(_var) + r"(?![\w])", _seg):
                        _tgt = _f
                        break
            if _tgt is None or _ind == _CANON_INDENT[_tgt]:
                continue
            _bad.append(f"{_p.name}:{_i + 1} → {_tgt} 用 indent={_ind}（canonical={_CANON_INDENT[_tgt]}）")
    if _bad:
        for _b in _bad:
            print(f"  ❌ {_b}")
        fail.append(f"JSON 寫入 indent 不符（{len(_bad)} 處）")
    else:
        print("  ✅ 掃到的寫入者 indent 與 canonical 一致")
except Exception as _e:
    print(f"  ❌ indent 檢查失敗 {_e}")
    fail.append("indent 檢查失敗")

print("=== 11) 保單同義欄位與分項合計不變式 ===")
# 2026-09-18 新增。背景：allianz_a/b_current_value 與 allianz_policy_a/b_value 是同一件事
# 的兩個欄位，曾分歧（4,925,927 vs 4,957,369），而 asset_diff 印出「分項相加 ≠ 顯示合計」
# （4,957,369-31,442 + 2,655,604-28,126 ≠ 7,612,973）。這種矛盾必須自動擋，不靠人眼。
try:
    import json as _json2
    _snap = _json2.loads((R / "snapshot.json").read_text(encoding="utf-8"))
    _pa = float(_snap.get("allianz_policy_a_value") or 0)
    _pb = float(_snap.get("allianz_policy_b_value") or 0)
    _ab = float(_snap.get("allianz_ab_current_value") or 0)
    _ca = float(_snap.get("allianz_a_current_value") or 0)
    _cb = float(_snap.get("allianz_b_current_value") or 0)
    _ba = sum(v for v in (_snap.get("allianz_a_breakdown") or {}).values() if isinstance(v, (int, float)))
    _bb = sum(v for v in (_snap.get("allianz_b_breakdown") or {}).values() if isinstance(v, (int, float)))
    _rows = [
        (f"同義欄位 A 兩組一致（policy {_pa:,.0f} ≡ current {_ca:,.0f}）", _pa == _ca),
        (f"同義欄位 B 兩組一致（policy {_pb:,.0f} ≡ current {_cb:,.0f}）", _pb == _cb),
        (f"分項相加 = A+B 合計（{_pa + _pb:,.0f} ≡ {_ab:,.0f}）", abs((_pa + _pb) - _ab) < 1),
        (f"子基金加總 = 保單A（{_ba:,.0f}）", abs(_ba - _pa) < 1),
        (f"子基金加總 = 保單B（{_bb:,.0f}）", abs(_bb - _pb) < 1),
    ]
    for _n, _b in _rows:
        print(f"  {ok(_b)} {_n}")
        if not _b:
            fail.append(f"保單不變式：{_n}")
except Exception as _e:
    print(f"  ❌ 保單不變式檢查失敗 {_e}")
    fail.append("保單不變式檢查失敗")

print("=== 12) 報告空值守門（金額 0 但佔比 > 0）===")
# 2026-09-23 INC-244 新增。日報穿透表「└ 科技股／└ 非科技」曾金額欄印 0 TWD 而佔比 15.3%／24.2% 正常
# （update_data 重建 penetration 時只把子維度補回 actual_pct，actual_twd 被丟掉，renderer `.get(key,0)` 靜默印 0）。
# 第 1 類「舊值殘留」掃不到這種「空值」症狀：舊值掃描找的是已知舊數字，被丟掉的鍵根本沒有數字可掃。
# 判定：金額 0 的儲存格「下一格」就是正的佔比 → ❌（用相鄰格，因穿透表同一列還有『目標』百分比欄，
# 整列比對會把「0 TWD＋目標 3%」誤判，2026-09-23 自測案例抓到）。
try:
    import sys as _sys12
    if str(R) not in _sys12.path:
        _sys12.path.insert(0, str(R))
    from check_report_zero_values import scan as _scan_zero
    _zhits = _scan_zero(T, R)
    if _zhits:
        for _z in _zhits[:6]:
            print(f"  ❌ {_z}")
        fail.append(f"報告金額 0 但佔比 > 0（{len(_zhits)} 列）")
    else:
        print("  ✅ 無『金額 0 ＋ 佔比 > 0』矛盾列")
except Exception as _e:
    print(f"  ❌ 空值守門無法執行 {_e}")
    fail.append("空值守門無法執行（check_report_zero_values）")

print("=== 13) LLM 內文數字可追溯（對得上 snapshot）===")
# 2026-09-23 INC-245 新增。背景：CTO 內文寫「科技17.5%已破15%紅線」，穿透表卻是 15.3%
# （模型自行推算/沿用舊值）；同段「美股超配+10.9pp」用了五桶合計當分母，與 +9.5pp 不一致。
# 閘門：內文「標籤＋純空白/冒號＋數字」的直述句，其 %/pp/金額必須落在 snapshot 的合法值集合內
# （容許「佔總資產」「佔投資部位」兩種口徑與 GICS 別名）。複合詞與中介詞句子刻意不比，避免假陽性。
try:
    import sys as _sys13
    if str(R) not in _sys13.path:
        _sys13.path.insert(0, str(R))
    from check_narrative_numbers import scan as _scan_narr
    _nhits = _scan_narr(T, R)
    if _nhits:
        for _n in _nhits[:6]:
            print(f"  ❌ {_n}")
        fail.append(f"內文數字對不上 snapshot（{len(_nhits)} 處）")
    else:
        print("  ✅ 內文穿透數字全部可追溯")
except Exception as _e:
    print(f"  ❌ 內文數字守門無法執行 {_e}")
    fail.append("內文數字守門無法執行（check_narrative_numbers）")

print()
print("=" * 46)
print(f"閉環稽核結果：{'全部通過 ✅' if not fail else '❌ 有問題：' + str(fail)}")
print("=" * 46)
