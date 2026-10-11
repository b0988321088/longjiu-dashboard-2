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
ck("待處理 31 天工程類＋逾期 due_date→歸檔",
   m.check_conditions(card(date=d31, title="守門技術債", tags="技術債", due_date=d31))[0] is True)
ck("待處理 31 天資產類→不歸檔", m.check_conditions(card(date=d31, title="美債 ladder 延後", tags="債券,美債"))[0] is False)
ck("待處理 31 天無法歸類→不歸檔", m.check_conditions(card(date=d31, title="無分類項目", tags=""))[0] is False)
ck("有未來 due_date→不歸檔", m.check_conditions(card(date=d31, title="閘門技術債", tags="技術債", due_date=fut))[0] is False)
ck("已確認 89 天工程類＋逾期 due_date→不歸檔",
   m.check_conditions(card(date=d89, title="驗證器技術債", status="已確認", tags="驗證器", due_date=d89))[0] is False)
ck("已確認 91 天工程類＋逾期 due_date→歸檔",
   m.check_conditions(card(date=d91, title="驗證器技術債", status="已確認", tags="驗證器", due_date=d91))[0] is True)
ck("舊敘述狀態（非四態）→不歸檔", m.check_conditions(card(date=d31, title="閘門技術債", status="🔄 執行中", tags="技術債"))[0] is False)
ck("工程類但含資產關鍵字→不歸檔", m.check_conditions(card(date=d31, title="保單 fallback 寫死", tags="技術債,保單"))[0] is False)
ck("STATUS_OPEN 契約＝(待處理,已確認)", tuple(m.STATUS_OPEN) == ("待處理", "已確認"))
ck("築巢關鍵字規則未被破壞", m.check_conditions(card(title="築巢優利貸 台銀"))[0] is True)
ck("00983D 分支不拋例外", isinstance(m.check_conditions(card(title="00983D策略：方案B")), tuple))

print("[2] archive 先寫入驗證、再移出正本")
p, a = tmp / "p.json", tmp / "a.json"
keep = card(date="2026-10-01", title="保留卡", tags="質押")
gone = card(date="2026-08-01", title="閘門技術債卡", tags="技術債,閘門,驗證器", due_date="2026-08-01")
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
def _git_show(spec):
    r = _sp.run(["git", "show", spec], cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout) if r.stdout.strip() else None
_BASE_PEND = _git_show("9196b047:pending_decisions.json") or []
_BASE_ARCH = _git_show("9196b047:pending_decisions_archive.json") or []
pend = json.loads(PEND.read_text(encoding="utf-8")); arch = json.loads(ARCH.read_text(encoding="utf-8"))
td = json.loads((BASE / "tech_debt.json").read_text(encoding="utf-8"))
ENUM = ("待處理", "已確認", "已完成", "關案")
bad = [(str(i.get("title", ""))[:26], i.get("status")) for i in pend if i.get("status") not in ENUM]
ck("正本 status 全落四態", not bad, bad[:3])
ck("正本量級：>0 且 < 基線（分流後必然縮減）", 0 < len(pend) < len(_BASE_PEND),
   f"{len(pend)}/{len(_BASE_PEND)}")
ck("正本 title 無重複", len({i.get("title") for i in pend}) == len(pend))
# 2026-10-12（CIO 二輪 RF-1）：改「批次守恆」相對斷言 —— 不再硬編碼本輪增量（原 +66
# 會與 HEAD 位置耦合，在本 commit 上永久 FAIL）。改為：本批移出的每一張卡都必須
# 出現在 archive 且帶本批 cleanup_reason。
_BATCH_OUT = [str(x.get("title", "")) for x in _BASE_PEND
              if str(x.get("title", "")) not in {str(y.get("title", "")) for y in pend}
              and str(x.get("title", "")) not in {str(y.get("title", "")) for y in
                                                   json.loads((BASE / "tech_debt.json").read_text(encoding="utf-8"))}]
_arch_by_title = {}
for _x in arch:
    if isinstance(_x, dict):
        _arch_by_title.setdefault(str(_x.get("title", "")), []).append(_x)
_missing = [_t for _t in _BATCH_OUT
            if not any(str(_y.get("cleanup_reason", "") or "").strip()
                       for _y in _arch_by_title.get(_t, []))]
ck(f"本批移出 {len(_BATCH_OUT)} 張皆在 archive 且帶本批 cleanup_reason", not _missing, _missing[:2])
ck("archive 未縮減（≥ 基線 42）", len(arch) >= len(_BASE_ARCH), f"{len(arch)} vs {len(_BASE_ARCH)}")
# 2026-10-12（CIO 三輪 RF-1）：移除殘餘硬編碼（原 _new=arch[-66:]、len(td)==60、len==21、
# 守恆算術 87）→ 全部改為「溯源／守恆」相對斷言，資料演進不再 false-red。
# 溯源鍵＝標題＋日期（容忍合法內容增補，例：CIO RF5 為取代卡補回 detail/reopen_conditions）
def _key(x):
    return (str(x.get("title", "")), str(x.get("date", "")))


_pend_t = {str(i.get("title", "")) for i in pend}
_td_t = {str(x.get("title", "")) for x in td}
_base_keys = {_key(x) for x in _BASE_PEND}
_live_keys = ({_key(x) for x in pend} | {_key(x) for x in td}
              | {_key(x) for x in arch if isinstance(x, dict)})
_unarchived = [k[0] for k in _base_keys if k not in _live_keys]
ck("溯源：基線每一張卡仍可在 正本∪tech_debt∪archive 找到", not _unarchived, _unarchived[:3])
# 只檢查「本批」歸檔項（archive 另有 pending_reconcile 的 ✅ 自動閉環項，非本批）
_BATCH_REASON = ("分流", "關案歸檔", "被 2026-10-01")
ck("本批歸檔項皆為 🗑 前綴（未覆蓋原文）",
   all(str(x.get("status", "")).startswith("🗑")
       for x in arch if str(x.get("cleanup_reason", "") or "").startswith(_BATCH_REASON)))
ck("tech_debt 欄位齊備", all(x.get("id") and x.get("title") and x.get("severity") and x.get("status") for x in td))
ck("tech_debt id 唯一", len({x.get("id") for x in td}) == len(td))
ck("pending ∩ tech_debt title ＝ 空", not ({i.get("title") for i in pend} & {x.get("title") for x in td}))
_bo_t = set(_BATCH_OUT)
ck("守恆：基線全部卡＝正本 ∪ tech_debt ∪ 本批歸檔（且三兩互斥）",
   (_pend_t | _td_t | _bo_t) == {str(x.get("title", "")) for x in _BASE_PEND}
   and not (_pend_t & _td_t) and not (_bo_t & _pend_t) and not (_bo_t & _td_t),
   f"pend={len(_pend_t)} td={len(_td_t)} out={len(_bo_t)} base={len(_BASE_PEND)}")
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
_d80 = (today - timedelta(days=80)).isoformat()
_g = card(date=_d80, title="閘門技術債重複測試", tags="技術債,閘門", due_date=_d80)
_p4.write_text(_json.dumps([_g], ensure_ascii=False), encoding="utf-8")
_a4.write_text(_json.dumps([dict(_g)], ensure_ascii=False), encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p4, _a4
m.auto_close()
ck("archive 已存在同 title → 不重複歸檔（RF3 冪等）",
   len(_json.loads(_a4.read_text(encoding="utf-8"))) == 1
   and len(_json.loads(_p4.read_text(encoding="utf-8"))) == 0)
ck("check_conditions 單參呼叫不拋例外（RF10）", isinstance(m.check_conditions(card(title="信貸套利 x")), tuple))


print("[7] 第三輪修正回歸（CIO 二輪 blocking／required_fixes）")
import tempfile as _tf2, json as _j3
# blocking：archive 損壞 → fail-closed、兩檔皆逐位元不變
_t5 = Path(_tf2.mkdtemp(prefix="dac_corrupt_")); _p5 = _t5 / "p.json"; _a5 = _t5 / "a.json"
_d80b = (today - timedelta(days=80)).isoformat()
_p5.write_text(_j3.dumps([card(date=_d80b, title="閘門技術債損壞測試", tags="技術債,閘門", due_date=_d80b)], ensure_ascii=False), encoding="utf-8")
_a5.write_text(_j3.dumps([{"date": "2026-01-01", "title": f"舊{_i}"} for _i in range(5)], ensure_ascii=False) + "GARBAGE", encoding="utf-8")
_pb5, _ab5 = _p5.read_bytes(), _a5.read_bytes(); _raised5 = ""
try:
    m.DECISIONS, m.ARCHIVE = _p5, _a5; m.auto_close()
except Exception as _e:
    _raised5 = str(_e)
ck("archive 損壞（尾端殘字）→ fail-closed 拋例外", "fail-closed" in _raised5, _raised5[:70])
ck("archive 損壞 → 正本逐位元不變", _p5.read_bytes() == _pb5)
ck("archive 損壞 → archive 逐位元不變（零遺失）", _a5.read_bytes() == _ab5)
# RF-2：.tmp 不殘留
_t6 = Path(_tf2.mkdtemp(prefix="dac_tmp_")); _p6 = _t6 / "p.json"
_p6.write_text("ORIGINAL", encoding="utf-8")
try:
    m._atomic_write(_p6, "{ broken")
except Exception:
    pass
ck("_atomic_write 失敗不殘留 .tmp 且正本不變",
   not list(_t6.glob("*.tmp")) and _p6.read_text(encoding="utf-8") == "ORIGINAL")
# RF-3：無 due_date 工程卡 advisory-only
_t7 = Path(_tf2.mkdtemp(prefix="dac_adv_")); _p7 = _t7 / "p.json"; _a7 = _t7 / "a.json"
_p7.write_text(_j3.dumps([card(date=(today - timedelta(days=80)).isoformat(), title="無檢視日工程卡", tags="技術債,閘門")], ensure_ascii=False), encoding="utf-8")
_a7.write_text("[]", encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p7, _a7
_cl7, _al7 = m.auto_close()
ck("無 due_date 之工程卡 → 不歸檔（RF6 優先序）", len(_j3.loads(_a7.read_text(encoding="utf-8"))) == 0)
ck("無 due_date 之工程卡 → 產 advisory 警報", any("無檢視日" in a for a in _al7), _al7[:1])
# 讀側 fail-closed：pending 截斷
_p8 = _t7 / "p8.json"; _p8.write_text('{"date":"x"', encoding="utf-8"); _pb8 = _p8.read_bytes()
_r8 = ""
try:
    m.DECISIONS, m.ARCHIVE = _p8, _a7; m.auto_close()
except Exception as _e:
    _r8 = str(_e)
ck("pending 截斷 → fail-closed 且不覆寫", "fail-closed" in _r8 and _p8.read_bytes() == _pb8, _r8[:60])
# RF-4：PROTECT 詞邊界
_d100 = (today - timedelta(days=100)).isoformat()
ck("P1X 回歸（偽 P1）不誤保護 → 逾期工程卡仍歸檔",
   m.check_conditions(card(date=_d100, title="P1X 回歸技術債", tags="技術債,回歸", due_date=_d100))[0] is True)
ck("P10 驗證器（偽 P1）不誤保護",
   m.check_conditions(card(date=_d100, title="P10 驗證器技術債", tags="技術債,驗證器", due_date=_d100))[0] is True)
ck("真 P0（tag）仍受保護",
   m.check_conditions(card(date=_d100, title="技術債修復", tags="技術債,P0", due_date=_d100))[0] is False)
_d200 = (today - timedelta(days=200)).isoformat()
ck("『資安』仍受保護",
   m.check_conditions(card(date=_d200, title="資安補強技術債", tags="技術債,資安", due_date=_d200))[0] is False)

# 2026-10-12（CIO 三輪 blocking）：不同卡同 title 不得被誤判「已歸檔」而兩檔皆無。
_t9 = Path(_tf2.mkdtemp(prefix="dac_coll_")); _p9 = _t9 / "p.json"; _a9 = _t9 / "a.json"
_dued = (today - timedelta(days=80)).isoformat()
_p9.write_text(_j3.dumps([card(date=_dued, title="例行複核", detail="NEW-CARD-UNIQUE-DETAIL",
                               tags="技術債,閘門", due_date=_dued)], ensure_ascii=False), encoding="utf-8")
_a9.write_text(_j3.dumps([{"date": "2020-01-01", "title": "例行複核", "detail": "OLD-ARCHIVED-CARD"}],
                         ensure_ascii=False), encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p9, _a9
m.auto_close()
_p9n = _j3.loads(_p9.read_text(encoding="utf-8")); _a9n = _j3.loads(_a9.read_text(encoding="utf-8"))
_all9 = _j3.dumps(_p9n, ensure_ascii=False) + _j3.dumps(_a9n, ensure_ascii=False)
ck("同 title 不同卡 → 內容不得遺失（三輪 blocking 回歸）",
   "NEW-CARD-UNIQUE-DETAIL" in _all9 and len(_a9n) == 2 and len(_p9n) == 0,
   f"archive={len(_a9n)} pend={len(_p9n)} kept={'NEW-CARD-UNIQUE-DETAIL' in _all9}")
# 寫入順序視窗：同一張卡同時存在兩檔 → 收斂時只自正本移除、archive 不重複
_t10 = Path(_tf2.mkdtemp(prefix="dac_win_")); _p10 = _t10 / "p.json"; _a10 = _t10 / "a.json"
_same = card(date=_dued, title="閘門技術債視窗測試", detail="SAME-CARD", tags="技術債,閘門", due_date=_dued)
_arch_same = dict(_same)
_arch_same["status"] = "🗑 自動歸檔：測試｜原狀態：待處理"; _arch_same["cleanup_reason"] = "decision_auto_close：測試"
_p10.write_text(_j3.dumps([_same], ensure_ascii=False), encoding="utf-8")
_a10.write_text(_j3.dumps([_arch_same], ensure_ascii=False), encoding="utf-8")
m.DECISIONS, m.ARCHIVE = _p10, _a10
m.auto_close()
ck("同卡同時存在兩檔 → 冪等收斂（archive 不增、正本移除）",
   len(_j3.loads(_a10.read_text(encoding="utf-8"))) == 1
   and len(_j3.loads(_p10.read_text(encoding="utf-8"))) == 0)

print()
ok = sum(1 for _, c in R if c); print(f"== {ok}/{len(R)} PASS ==")
if ok != len(R):
    print("FAIL: " + "; ".join(n for n, c in R if not c))
sys.exit(0 if ok == len(R) else 1)
