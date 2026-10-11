#!/usr/bin/env python3
"""pending 分流（2026-10-11）驗證：引擎四態/資產保護/逾期邊界、archive 安全、資料契約、tech_debt 工具。"""
import importlib.util, json, shutil, subprocess, sys, tempfile
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PEND = BASE / "pending_decisions.json"
ARCH = BASE / "pending_decisions_archive.json"
R = []

def ck(name, cond, ev=""):
    R.append((name, bool(cond)))
    print(("  PASS  " if cond else "  FAIL  ") + name + (("  | " + str(ev)[:170]) if ev != "" else ""))

spec = importlib.util.spec_from_file_location("dac_t", BASE / "decision_auto_close.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
today = date.today()
tmp = Path(tempfile.mkdtemp(prefix="dac_test_"))
m.NOTION_LOG = tmp / "notion_stub_missing.py"   # 禁止測試期間真的寫 Notion

def card(**kw):
    d = {"date": "2026-01-01", "title": "x", "status": "待處理", "tags": "", "detail": ""}
    d.update(kw); return d

print("[1] 引擎條件（四態／資產保護／逾期邊界）")
d30 = (today - timedelta(days=30)).isoformat(); d31 = (today - timedelta(days=31)).isoformat()
d89 = (today - timedelta(days=89)).isoformat(); d91 = (today - timedelta(days=91)).isoformat()
fut = (today + timedelta(days=5)).isoformat()
ck("待處理 30 天（邊界）不歸檔", m.check_conditions(card(date=d30, title="閘門技術債", tags="技術債"))[0] is False)
ck("待處理 31 天工程類→歸檔", m.check_conditions(card(date=d31, title="守門技術債", tags="技術債"))[0] is True)
ck("待處理 31 天資產類→不歸檔", m.check_conditions(card(date=d31, title="美債 ladder 延後", tags="債券,美債"))[0] is False)
ck("待處理 31 天無法歸類→不歸檔", m.check_conditions(card(date=d31, title="無分類項目", tags=""))[0] is False)
ck("有未來 due_date→不歸檔", m.check_conditions(card(date=d31, title="閘門技術債", tags="技術債", due_date=fut))[0] is False)
ck("已確認 89 天工程類→不歸檔", m.check_conditions(card(date=d89, title="驗證器技術債", status="已確認", tags="驗證器"))[0] is False)
ck("已確認 91 天工程類→歸檔", m.check_conditions(card(date=d91, title="驗證器技術債", status="已確認", tags="驗證器"))[0] is True)
ck("舊敘述狀態（非四態）→不歸檔", m.check_conditions(card(date=d31, title="閘門技術債", status="🔄 執行中", tags="技術債"))[0] is False)
ck("工程類但含資產關鍵字→不歸檔", m.check_conditions(card(date=d31, title="保單 fallback 寫死", tags="技術債,保單"))[0] is False)
ck("STATUS_OPEN 契約＝(待處理,已確認)", tuple(m.STATUS_OPEN) == ("待處理", "已確認"))
ck("築巢關鍵字規則未被破壞", m.check_conditions(card(title="築巢優利貸 台銀"))[0] is True)
ck("00983D 分支不拋例外", isinstance(m.check_conditions(card(title="00983D策略：方案B")), tuple))

print("[2] archive 先寫入驗證、再移出正本")
p, a = tmp / "p.json", tmp / "a.json"
keep = card(date="2026-10-01", title="保留卡", tags="質押")
gone = card(date="2026-08-01", title="閘門技術債卡", tags="技術債,閘門,驗證器")
p.write_text(json.dumps([keep, gone], ensure_ascii=False, indent=2), encoding="utf-8")
a.write_text(json.dumps([{"date": "2026-01-01", "title": "舊歸檔"}], ensure_ascii=False, indent=1), encoding="utf-8")
m.DECISIONS, m.ARCHIVE = p, a
m.auto_close()
pn = json.loads(p.read_text(encoding="utf-8")); an = json.loads(a.read_text(encoding="utf-8"))
ck("正本移除 1 保留 1", len(pn) == 1 and pn[0]["title"] == "保留卡", len(pn))
ck("archive 1→2 筆（原有 1 ＋ 歸檔 1）", len(an) == 2, len(an))
ck("archive 條目含 cleanup_reason＋🗑 前綴",
   str(an[-1].get("cleanup_reason", "")).startswith("decision_auto_close")
   and str(an[-1].get("status", "")).startswith("🗑 自動歸檔"), an[-1].get("status", "")[:55])
ck("未殘留 .tmp 檔", not list(tmp.glob("*.tmp")))
p2 = tmp / "p2.json"; p2.write_text(json.dumps([gone], ensure_ascii=False, indent=2), encoding="utf-8")
before = p2.read_text(encoding="utf-8")
m.DECISIONS, m.ARCHIVE = p2, tmp / "no_such_dir" / "a.json"
raised = False
try:
    m.auto_close()
except Exception:
    raised = True
ck("archive 不可寫→拋例外（fail-closed）", raised)
ck("archive 不可寫→正本逐位元不變（零遺失）", p2.read_text(encoding="utf-8") == before)
m.ARCHIVE, m.DECISIONS = a, p
_a_before = a.read_text(encoding="utf-8"); _p_before = p.read_text(encoding="utf-8")
m.auto_close()
m.auto_close()
ck("重複執行冪等（正本無可歸檔項時 archive／正本皆逐位元不變）",
   a.read_text(encoding="utf-8") == _a_before and p.read_text(encoding="utf-8") == _p_before)

print("[3] 真實檔案資料契約")
import subprocess as _sp
_p_std = _sp.run(["git","show","HEAD~1:pending_decisions_archive.json"], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8").stdout
_ARCH_BASE = len(json.loads(_p_std)) + 66 if _p_std.strip() else len(json.loads(ARCH.read_text(encoding="utf-8")))
pend = json.loads(PEND.read_text(encoding="utf-8")); arch = json.loads(ARCH.read_text(encoding="utf-8"))
td = json.loads((BASE / "tech_debt.json").read_text(encoding="utf-8"))
ENUM = ("待處理", "已確認", "已完成", "關案")
bad = [(str(i.get("title", ""))[:26], i.get("status")) for i in pend if i.get("status") not in ENUM]
ck("正本 status 全落四態", not bad, bad[:3])
ck("正本＝21 筆", len(pend) == 21, len(pend))
ck("正本 title 無重複", len({i.get("title") for i in pend}) == len(pend))
ck("archive 筆數 = HEAD 基準＋本次歸檔數", len(arch) == _ARCH_BASE, f"{len(arch)} vs {_ARCH_BASE}")
_new = arch[-66:]
ck("本次歸檔 66 筆皆含 cleanup_reason", all(x.get("cleanup_reason") for x in _new),
   [x.get("title", "")[:20] for x in _new if not x.get("cleanup_reason")][:3])
ck("本次歸檔 66 筆皆含 🗑 前綴", all(str(x.get("status", "")).startswith("🗑") for x in _new))
ck("tech_debt＝60 筆", len(td) == 60, len(td))
ck("tech_debt 欄位齊備", all(x.get("id") and x.get("title") and x.get("severity") and x.get("status") for x in td))
ck("tech_debt id 唯一", len({x.get("id") for x in td}) == len(td))
ck("pending ∩ tech_debt title ＝ 空", not ({i.get("title") for i in pend} & {x.get("title") for x in td}))
ck("守恆 21＋60＋(5 關案＋1 取代)＝87",
   len(pend) + len(td) + len([x for x in _new if str(x.get("cleanup_reason", "")).startswith("關案") or "取代" in str(x.get("cleanup_reason", ""))]) == 87)
ck("tech_debt severity 分布 P0/P1/P2", {"P0", "P1", "P2"} <= {x.get("severity") for x in td})

print("[4] tech_debt.py CRUD（複本隔離）")
t2 = Path(tempfile.mkdtemp(prefix="td_test_"))
shutil.copy(BASE / "tech_debt.py", t2 / "tech_debt.py")
(t2 / "tech_debt.json").write_text("[]", encoding="utf-8")
def run(*args):
    return subprocess.run([sys.executable, "tech_debt.py", *args], cwd=str(t2),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
def tload():
    return json.loads((t2 / "tech_debt.json").read_text(encoding="utf-8"))
ck("add 成功", run("add", "--title", "測試債A", "--severity", "P1", "--source", "CIO required_fixes").returncode == 0)
run("add", "--title", "測試債B", "--severity", "P0")
ck("第二筆 id 遞增（-02）", tload()[1]["id"].endswith("02"), tload()[1]["id"])
ck("add 寫入 moved_at/status 開放", tload()[0]["status"] == "開放" and tload()[0]["moved_at"])
r = run("list", "--open", "--severity", "P0")
ck("list --severity 過濾正確", r.returncode == 0 and "測試債B" in r.stdout and "測試債A" not in r.stdout)
tid = tload()[0]["id"]
ck("close 成功且狀態→已結案", run("close", "--id", tid, "--evidence", "unit").returncode == 0 and tload()[0]["status"] == "已結案")
ck("close 不存在 id → rc=1", run("close", "--id", "TD-99999999-99").returncode == 1)
(t2 / "tech_debt.json").write_text("{ broken", encoding="utf-8")
ck("損壞檔容錯（list 不崩）", run("list").returncode == 0)

print("[5] 顯示層一致性（built index.html）")
h = (BASE / "index.html").read_text(encoding="utf-8", errors="replace")
ck("前端 JS 四態判定已上線", "if(s === '待處理' || s === '已確認') return true;" in h)
ck("前端 JS 含關案於白名單（舊資料回退）", "'已核定','關案'" in h)
ck("技術債卡 JS 已上線", "fetch('tech_debt.json'" in h)
ck("P0 卡非硬寫 ✅", "P0 戰略任務" in h and "\">✅ {_p0_st}" not in h)
i = h.find('id="decision-list"'); seg = h[i:i + 3000]
ck("靜態決策卡列數＝min(8, active)＝8", seg.count("border border-red-500/30") == 8, seg.count("border border-red-500/30"))
ck("靜態卡不含工程技術債字樣", "docstring" not in seg and "守門偵測" not in seg)
ck("檔案內不再殘留 87 筆基準字樣", "執行中 87 筆" not in h)


print("[6] CIO RF4/RF6/RF8 負向與老化測試")
for _t in ("安排家族信託文件清單備份", "四家銀行授權書備份歸檔", "新銀行帳戶開戶與備份設定"):
    ck(f"偽陰性排除：{_t}（40 天前）不歸檔",
       m.check_conditions(card(date=(today - timedelta(days=40)).isoformat(), title=_t))[0] is False)
ck("資安卡（逾期 100 天）不自動歸檔（RF8）",
   m.check_conditions(card(date=(today - timedelta(days=100)).isoformat(),
                           title="資安 remediation：repo 五步", tags="資安,P0"))[0] is False)
ck("P0 標記卡不自動歸檔（RF8）",
   m.check_conditions(card(date=(today - timedelta(days=100)).isoformat(),
                           title="技術債 P0 修復", tags="技術債,P0"))[0] is False)
import tempfile as _tf, json as _json
_t3 = Path(_tf.mkdtemp(prefix="dac_age_")); _p3 = _t3 / "p.json"; _a3 = _t3 / "a.json"
_p3.write_text(_json.dumps([card(date=(today - timedelta(days=80)).isoformat(),
                                 title="無檢視日資產卡", tags="質押")], ensure_ascii=False), encoding="utf-8")
_a3.write_text("[]", encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p3, _a3
_cl, _al = m.auto_close()
ck("無 due_date 逾期卡 → 產出老化警報（RF6）", any("無檢視日" in a for a in _al), _al[:1])
ck("無 due_date 逾期卡 → 不歸檔（advisory）", len(_json.loads(_a3.read_text(encoding="utf-8"))) == 0)
_t4 = Path(_tf.mkdtemp(prefix="dac_idem_")); _p4 = _t4 / "p.json"; _a4 = _t4 / "a.json"
_g = card(date=(today - timedelta(days=80)).isoformat(), title="閘門技術債重複測試", tags="技術債,閘門")
_p4.write_text(_json.dumps([_g], ensure_ascii=False), encoding="utf-8")
_a4.write_text(_json.dumps([dict(_g)], ensure_ascii=False), encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p4, _a4
m.auto_close()
ck("archive 已存在同 title → 不重複歸檔（RF3 冪等）",
   len(_json.loads(_a4.read_text(encoding="utf-8"))) == 1
   and len(_json.loads(_p4.read_text(encoding="utf-8"))) == 0)
ck("check_conditions 單參呼叫不拋例外（RF10）", isinstance(m.check_conditions(card(title="信貸套利 x")), tuple))

print()
ok = sum(1 for _, c in R if c); print(f"== {ok}/{len(R)} PASS ==")
if ok != len(R):
    print("FAIL: " + "; ".join(n for n, c in R if not c))
sys.exit(0 if ok == len(R) else 1)
