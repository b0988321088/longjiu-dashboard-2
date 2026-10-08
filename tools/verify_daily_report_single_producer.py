# -*- coding: utf-8 -*-
"""INC-289 閘門：日報是否只有一套 canonical producer。

驗的不是「今天這份 HTML 看起來恢復了」，而是**正式發布來源只有一套實作**——
否則下一次排程仍可能再產出「有章／沒章」兩種版本。

四個面向：
  S1 唯一實作：兩個 producer 都必須呼叫 daily_report_assembly；不得各自實作
  S2 呼叫契約：AST 檢查兩邊呼叫同一函式、參數來源一致；同一輸入兩次呼叫逐位元相同
  S3 真實輸入產出：決策追蹤章存在、列數 == 卡片數、洲際W轉貸計數一致、缺口欄＝pp、無 __DR_ 殘留
  S4 負向對照：把私有實作塞回暫存副本 → 閘門必須 FAIL（證明閘門非空洞）

INC-291（2026-10-09）擴充：涵蓋第 4 條雙 producer 分歧「緊急應變（美股／台股）LLM 區塊」——
  唯一實作＝`daily_report_assembly.build_emergency_block()`。
  偵測鍵以 \\u 轉義持有（故掃描器不會自我命中、亦無須自我豁免跳過，R2）；白名單一律以 **repo 相對
  路徑** 判定（R1）；標記比對去 emoji（R3-V1/V2）；私有 formatter 以 **AST** 判定 content_type
  引數（R3-V3，引號／位置引數無關）。
  新增：S1.11、S3.17（today 值敏感）、S5.9/S5.10（today 來源不變量）、S4.7–S4.12（六種變體＋對照）。

已揭露的偵測極限（分層防禦，不是單點保證）：
  ① 若 producer 把標記 **拆成變數拼接**（`KEY="緊急應變"+"資料"`）且檔內同時不出現 `daily_report_v2`
     字面，V2 抓不到 → 仍由 S1.7d／S2.6／S5.7 的結構檢查（兩 producer 必須呼叫同一函式）兜底。
  ② 掃描是「文字＋AST」啟發式，不是資料流分析；要證明「無第二實作」最終仍靠 code review。

唯讀：只讀 repo 檔＋寫 %TEMP% 暫存副本。rc=0 全過、rc=1 有 FAIL。
ROLE: DETECTOR-ONLY

用法：python tools/verify_daily_report_single_producer.py [--report <html>]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS, FAIL, SKIP = [], [], []


def ck(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  | {detail}" if detail else ""))
    return bool(cond)


def rd(p):
    return io.open(p, encoding="utf-8", errors="replace").read()


SHARED = BASE / "daily_report_assembly.py"
REGEN = BASE / "regenerate_report.py"
RUNDAILY = BASE / "run_daily.py"
REQUIRED_API = ("build_schedule_rows", "build_p0_tasks_html", "substitute_dr_tokens", "build_decision_rows",
                "build_emergency_block")
_MARKER = "執行中決策追蹤"
# 只認「會被寫進 HTML 的那一行」，註解／docstring 提到這串字不算私有實作
# INC-292：以 \u 轉義持有（同 _EM_KEY 手法）→ 掃描器自身不持有原文，
# 故 has_emit 可與一般檔同一套規則判定，無須靠自我豁免跳過。
_EMIT = "\U0001f4cb \u57f7\u884c\u4e2d\u6c7a\u7b56\u8ffd\u8e64</p>"
_EMIT_TPL = '<p style="margin-top:12px;font-weight:700;color:#3b82f6">' + _EMIT

print("=" * 78)
print("INC-289 閘門：日報單一 canonical producer")
print("=" * 78)

# ═══════════ S1. 唯一實作（白名單式全 repo 掃描）═══════════
print("\n[S1] 唯一實作（白名單式全 repo 掃描；未知新檔不得自建組裝路徑）")

# 白名單一律以「repo 相對路徑」判定（INC-291 R1：用 basename 判 → 任意子目錄放同名檔即全豁免）
DR_WHITELIST = {"daily_report_assembly.py",   # 唯一取代實作
                "run_daily.py"}                # 日報模板持有者（__DR_*__ 佔位符本身）
EMIT_WHITELIST = {"daily_report_assembly.py"}  # 只有它能 emit「執行中決策追蹤」章
# INC-291：緊急應變區塊的私有組裝偵測（唯一出處＝共用模組）
# 標記刻意以 \u 轉義持有（R2）：掃描器自身不得因「持有字面」被自我豁免，
# 也不得因持有字面而在全 repo 掃描命中自己 → 本組檢查因此可置於自我豁免之前。
_EM_KEY = "\u7dca\u6025\u61c9\u8b8a\u8cc7\u6599"   # 正規化鍵：去 emoji（R3：有無 📅 都要抓到）
_EM_CT_KEY = ("\u0065\u006d\u0065\u0072\u0067\u0065\u006e\u0063\u0079"
              "\u005f\u0061\u006e\u0061\u006c\u0079\u0073\u0069\u0073")  # emergency_analysis
_DAILY_NAME = "daily_report_v2"   # 會產出／讀取日報的檔（V1：任何上下文皆不得持有該標記）
EM_WHITELIST = {"daily_report_assembly.py"}
# 掃描器自身（僅偵測、不產出）；豁免前提＝不得有 .replace(__DR_*) 或匯入共用組裝模組
# ⚠️ 以 rel 判定：本檔在 tools/ 底下（R1 改 rel 後，用 basename 會漏掉自己→被自己的白名單判為違規）
_SELF_EXEMPT = {"tools/verify_daily_report_single_producer.py"}
_SELF_REL = "tools/verify_daily_report_single_producer.py"
_SELF_MARK = "ROLE: DETECTOR-ONLY"
_SELF_NAME = "verify_daily_report_single_producer.py"
_SCAN_EXT = (".py", ".sh", ".js")
_SCAN_SKIP_DIRS = {"backups", ".bak-inc-unclosed", ".archive", ".git", "cache",
                   "logs", "__pycache__", "node_modules", ".venv", "venv"}
_DR_TOKEN_RE = re.compile(r"^__DR_[A-Z_]+__$")


def _imports_shared(src):
    """是否從共用組裝模組匯入（＝具備產出日報的能力）。"""
    return bool(re.search(r"^\s*(from|import)\s+daily_report_assembly", src, re.M))


def _fold_str(node, tbl=None):
    """把 AST 節點盡力還原成字串常數（Constant／字串加法拼接／已知變數）。

    INC-292：常數折疊發生在 compile 階段，`ast.parse` 不做 → `"__DR"+"_TW_GAP__"`
    在 AST 上永遠是 BinOp，只比對 ast.Constant 會漏掉，故須自行折疊。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        _l, _r = _fold_str(node.left, tbl), _fold_str(node.right, tbl)
        if _l is not None and _r is not None:
            return _l + _r
    if isinstance(node, ast.Name) and tbl and node.id in tbl:
        return tbl[node.id]
    return None


def _has_private_dr_replace(src):
    """抓 `X.replace(<__DR_ token>)`，含「先存變數再 replace」與「拼接組出 token」。

    （2026-10-07 CIO 對抗性審查實證：純字面比對 `\.replace\("__DR_` 可用變數名繞過。
     2026-10-09 INC-292：`"__DR"+"_TW_GAP__"` 為 BinOp 拼接，須折疊後比對。）
    """
    tree = ast.parse(src)
    _consts = {}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            v = _fold_str(node.value, _consts)
            if v is not None:
                _consts[node.targets[0].id] = v
    tok_names = {k for k, v in _consts.items() if _DR_TOKEN_RE.match(v)}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "replace" and node.args):
            continue
        a0 = node.args[0]
        v = _fold_str(a0, _consts)
        if v is not None and _DR_TOKEN_RE.match(v):
            return True
        if isinstance(a0, ast.Name) and a0.id in tok_names:
            return True
    return False


def _emit_like_em_lines(src):
    """回傳「看起來在產出緊急應變區塊」的行（R3：不綁 emoji／引號樣式）。

    判準＝同一行同時含標記與 HTML／插值語境（`<` 或 `{`）。
    註解、純字串常數（例如 `check_usd_advisory.py` 用來跳過歷史存檔區段的行首標記）不含上述語境 → 不算。
    """
    return [ln for ln in src.splitlines() if _EM_KEY in ln and ("<" in ln or "{" in ln)]


def _private_em_formatter_calls(src):
    """AST：把 `emergency_analysis` 當內容型別傳進呼叫者（R3：引號／空白樣式無關）。

    兩種形式都算：`f(x, content_type="emergency_analysis")`、`f(x, "emergency_analysis")`。
    AST 解析失敗（非合法 Python）→ 回空清單，不讓閘門因單一壞檔崩潰。
    """
    import ast as _ast
    try:
        tree = _ast.parse(src)
    except SyntaxError:
        return []
    hits = []
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        for _kw in node.keywords:
            _v = _kw.value
            if isinstance(_v, _ast.Constant) and _v.value == _EM_CT_KEY:
                hits.append(f"kw:{_kw.arg}")
        if len(node.args) >= 2:
            _a1 = node.args[1]
            if isinstance(_a1, _ast.Constant) and _a1.value == _EM_CT_KEY:
                hits.append("pos2")
    return hits


def scan_producers(root, extra_skip=()):
    """白名單式掃描 → [(相對路徑, 違規說明), ...]；同時回傳掃描檔數。"""
    root = Path(root)
    viol, n = [], 0
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in _SCAN_EXT:
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except Exception:
            continue
        if any(seg in _SCAN_SKIP_DIRS for seg in Path(rel).parts) or rel in extra_skip:
            continue
        n += 1
        txt = rd(f)
        has_lit = bool(re.search(r"__DR_[A-Z_]+__", txt))
        has_emit = _EMIT in txt
        # ── INC-291 緊急應變檢查：置於自我豁免之前 → 任何檔名都不得跳過（R2）──
        # V1 在任何上下文都不得持有標記（擋變數間接）；V2 擋 emit 語境的私有組裝；
        # V3 以 AST 擋私有 formatter（引號／空白樣式無關）。
        if rel not in EM_WHITELIST:
            if _DAILY_NAME in txt and _EM_KEY in txt:
                viol.append((rel, "會產出／讀取日報，且檔內出現緊急應變標記（任何上下文皆不得持有）"))
            elif _emit_like_em_lines(txt):
                viol.append((rel, "emit 緊急應變區塊但不在白名單（未知 producer 自建組裝路徑）"))
            if _private_em_formatter_calls(txt):
                viol.append((rel, "出現私有 emergency_analysis formatter 呼叫（唯一組裝＝共用模組）"))
        # INC-292：決策追蹤章的 emit 檢查與緊急應變同級 —— 置於自我豁免之前，
        # 任何檔名（含掃描器自身）都不得跳過。掃描器已不持有 _EMIT 原文（\u 轉義），
        # 故此檢查可對自身生效而不會自我誤判（a6c：僅 emit 決策章 → 必須被擋）。
        if has_emit and rel not in EMIT_WHITELIST:
            viol.append((rel, "emit 決策追蹤章但不在白名單"))
        if rel in _SELF_EXEMPT:
            # 掃描器自身：可持有偵測用字面、可為「比對」而匯入共用模組，
            # 但不得自行取代 __DR_*__，且必須自我標記 DETECTOR-ONLY（否則白名單即後門）
            if _has_private_dr_replace(txt):
                viol.append((rel, "掃描器自身出現 .replace(__DR_*) 產出行為"))
            elif _SELF_MARK not in txt:
                viol.append((rel, "自我豁免但缺 " + _SELF_MARK + " 標記"))
            continue
        if has_lit and rel not in DR_WHITELIST:
            viol.append((rel, "出現 __DR_*__ 字面但不在白名單（未知 producer 自建取代路徑）"))
        if rel == "run_daily.py" and _has_private_dr_replace(txt):
            viol.append((rel, "模板持有者 run_daily.py 不得自行取代 __DR_*__"))
    return viol, n


ck("S1.1 daily_report_assembly.py 存在", SHARED.exists(), str(SHARED))
src_shared = rd(SHARED) if SHARED.exists() else ""
_shared_tree = ast.parse(src_shared) if src_shared else None
_shared_defs = {n.name for n in ast.walk(_shared_tree) if isinstance(n, ast.FunctionDef)} if _shared_tree else set()
ck("S1.2 共用模組提供完整 API", all(a in _shared_defs for a in REQUIRED_API),
   "缺：" + str([a for a in REQUIRED_API if a not in _shared_defs]))

for tag, path in (("regenerate_report.py", REGEN), ("run_daily.py", RUNDAILY)):
    s_ = rd(path)
    tree = ast.parse(s_)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "daily_report_assembly":
            imported |= {a.name for a in node.names}
    ck(f"S1.3 {tag} 自共用模組匯入組裝 API",
       len(imported & set(REQUIRED_API)) >= 3, "匯入：" + str(sorted(imported)))
    ck(f"S1.4 {tag} 無私有 __DR_*__ 取代（AST 判定，含變數間接形式）",
       not _has_private_dr_replace(s_), "AST 掃描")
    ck(f"S1.5 {tag} 無私有「執行中決策追蹤」實作", _EMIT_TPL not in s_, f"命中 {s_.count(_EMIT_TPL)} 處")
    ck(f"S1.6 {tag} 實際呼叫組裝函式",
       ("_asm_p0(" in s_ and "_asm_dr(" in s_) or ("build_p0_tasks_html(" in s_ and "substitute_dr_tokens(" in s_))
ck("S1.7 共用模組是決策追蹤章唯一出處（emit 字串僅 1 處）",
   src_shared.count(_EMIT_TPL) == 1, f"命中 {src_shared.count(_EMIT_TPL)} 處")
# ---- INC-291：緊急應變區塊同樣只有一套實作 ----
ck("S1.7b 共用模組是緊急應變區塊唯一 emit 出處（標記僅 1 處）",
   src_shared.count(_EM_KEY) == 1, f"命中 {src_shared.count(_EM_KEY)} 處")
ck("S1.7c 共用模組提供 build_emergency_block", "build_emergency_block" in _shared_defs)
for tag, path in (("regenerate_report.py", REGEN), ("run_daily.py", RUNDAILY)):
    _s = rd(path)
    ck(f"S1.7d {tag} 無緊急應變區塊私有 emit（私有組裝已刪）", _EM_KEY not in _s,
       f"命中 {_s.count(_EM_KEY)} 處")
    ck(f"S1.7e {tag} 無私有 emergency_analysis formatter 呼叫（AST 判定）",
       not _private_em_formatter_calls(_s))
    ck(f"S1.7f {tag} 無私有 as_of 標示實作（_stale_badge 賦值）",
       not re.search(r"^\s*_stale_badge\s*=", _s, re.M), "AST/正則：賦值才算實作，註解提及不算")
_selfsrc_p = BASE / _SELF_REL
ck("S1.11 掃描器以 \\u 轉義持有偵測鍵（不會自我命中，故無須自我豁免跳過）",
   _EM_KEY not in rd(_selfsrc_p) and _EMIT not in rd(_selfsrc_p),
   f"緊急應變鍵殘留 {rd(_selfsrc_p).count(_EM_KEY)} 處／決策章 emit 字面殘留 {rd(_selfsrc_p).count(_EMIT)} 處")

_repo_viol, _scanned = scan_producers(BASE)
ck("S1.8 全 repo 白名單掃描：無未授權的組裝路徑", not _repo_viol, str(_repo_viol[:5]))
ck("S1.9 掃描確實有掃到檔案（防空掃描假綠）", _scanned > 50, f"掃描 {_scanned} 檔")
_PROD_REFS = []
for _n in ("regenerate_report.py", "run_daily.py", "morning_deploy.py",
           "sync_all.py", "daily_build.py", "four_source_sync.py"):
    _fp = BASE / _n
    if _fp.exists() and _SELF_NAME in rd(_fp):
        _PROD_REFS.append(_n)
ck("S1.10 掃描器純偵測、未被任何 producer/orchestrator 引用", not _PROD_REFS, str(_PROD_REFS))

# ═══════════ S2. 呼叫契約 ─══════════
print("\n[S2] 呼叫契約（同一函式、同一輸入來源）")
_CALL_ARGS = {}


def _calls(src, funcs):
    """回傳 {共用函式名: [位置參數個數, ...]}；本檔以別名匯入（_asm_p0 等）亦解析。"""
    tree = ast.parse(src)
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "daily_report_assembly":
            for a in node.names:
                alias[a.asname or a.name] = a.name
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            nm = getattr(f, "id", None) or getattr(f, "attr", None)
            nm = alias.get(nm, nm)
            if nm in funcs:
                found.setdefault(nm, []).append(len(node.args))
    return found


_c_regen = _calls(rd(REGEN), set(REQUIRED_API))
_c_run = _calls(rd(RUNDAILY), set(REQUIRED_API))
ck("S2.1 regenerate 呼叫 build_p0_tasks_html（4 位置參數）",
   _c_regen.get("build_p0_tasks_html") == [4], str(_c_regen.get("build_p0_tasks_html")))
ck("S2.2 run_daily 呼叫 build_p0_tasks_html（4 位置參數）",
   _c_run.get("build_p0_tasks_html") == [4], str(_c_run.get("build_p0_tasks_html")))
ck("S2.3 兩邊缺口口徑同一函式（substitute_dr_tokens 2 參數）",
   _c_regen.get("substitute_dr_tokens") == [2] and _c_run.get("substitute_dr_tokens") == [2],
   f"regen={_c_regen.get('substitute_dr_tokens')} run={_c_run.get('substitute_dr_tokens')}")
ck("S2.6 兩邊緊急應變同一函式（build_emergency_block 3 位置參數）",
   _c_regen.get("build_emergency_block") == [3] and _c_run.get("build_emergency_block") == [3],
   f"regen={_c_regen.get('build_emergency_block')} run={_c_run.get('build_emergency_block')}")

import daily_report_assembly as asm

_events = asm.load_events(BASE)
_pending = asm.load_pending(BASE)
_snap = json.loads(rd(BASE / "snapshot.json"))


def _md5(x):
    return hashlib.md5(x.encode("utf-8")).hexdigest()


_today = _snap.get("date") or __import__("datetime").date.today().isoformat()
_a1 = asm.build_p0_tasks_html(_events, _pending, _snap, _today)
_a2 = asm.build_p0_tasks_html(_events, _pending, _snap, _today)
ck("S2.4 同一輸入兩次呼叫逐位元相同（決定性）", _md5(_a1) == _md5(_a2), _md5(_a1)[:12])
_pen = _snap.get("penetration", {})
_f1 = asm.substitute_dr_tokens("__DR_TW_GAP__|__DR_BOND_GAP__|__DR_US_TECH_GAP__", _pen)
_f2 = asm.substitute_dr_tokens("__DR_TW_GAP__|__DR_BOND_GAP__|__DR_US_TECH_GAP__", _pen)
ck("S2.5 缺口欄＝pp 口徑且決定性", _md5(_f1) == _md5(_f2) and re.fullmatch(r"[+-]\d+\.\dpp(\|[+-]\d+\.\dpp){2}", _f1),
   f"{_f1}")

# ═══════════ S3. 真實輸入產出 ═══════════
print("\n[S3] 真實輸入產出（artifact integrity）")
ck("S3.1 決策追蹤章存在", _MARKER in _a1)
_n_rows = _a1.count("<tr>")
ck("S3.2 決策卡列數 == pending 卡片數", _n_rows == len(_pending), f"rows={_n_rows} cards={len(_pending)}")
_zh = sum(1 for x in _pending if "洲際W轉貸" in (str(x.get("title", "")) + str(x.get("status", ""))))
_zo = _a1.count("洲際W轉貸")
ck("S3.3 洲際W轉貸計數一致（卡片數 vs 產出）", _zh == _zo and _zo > 0, f"cards={_zh} html={_zo}")
ck("S3.4 產出無未替換模板佔位符", "__" not in _a1.replace("__", "", 0) or not re.search(r"__[A-Z_]+__", _a1),
   str(re.findall(r"__[A-Z_]+__", _a1)[:3]))
_tpl = rd(RUNDAILY)
_tpl_tokens = set(re.findall(r"__DR_[A-Z_]+__", _tpl))
_sub = asm.substitute_dr_tokens(" ".join(sorted(_tpl_tokens)), _pen)
_noon = re.findall(r"__DR_[A-Z_]+__", _sub)
ck("S3.5 模板全部 __DR_*__ 皆可被取代（無殘留）", not _noon, str(_noon[:5]))
_gap_bad = []
for _tok in ("__DR_TW_GAP__", "__DR_US_GAP__", "__DR_DEF_GAP__", "__DR_BOND_GAP__",
             "__DR_CASH_GAP__", "__DR_US_TECH_GAP__"):
    _o = asm.substitute_dr_tokens(_tok, _pen)
    if not re.fullmatch(r"[+-]?\d+\.\dpp", _o):
        _gap_bad.append((_tok, _o))
ck("S3.6 六個缺口欄逐欄皆為 pp（舊 TWD 金額格式已消滅）", not _gap_bad, str(_gap_bad))

# INC-291：緊急應變區塊（唯一實作）以真實輸入實測
_ej_p = BASE / "data" / "emergency_llm_analysis.json"
if _ej_p.exists():
    try:
        _dt_em = str(json.loads(rd(_ej_p)).get("date") or "")[:10]
    except Exception:
        _dt_em = ""
    _em1 = asm.build_emergency_block(BASE, _snap, _today)
    _em2 = asm.build_emergency_block(BASE, _snap, _today)
    ck("S3.12 緊急應變區塊決定性（同輸入兩次 md5 相同）", _md5(_em1) == _md5(_em2), _md5(_em1)[:12])
    ck("S3.13 緊急應變區塊＝單一 callout-warn 容器（連結在其內）",
       _em1.startswith('<div class="callout callout-warn">')
       and _em1.count('<div class="callout callout-warn">') == 1 and _em1.count("</div>") == 1, _em1[:26])
    ck("S3.14 as_of 標示與資料日一致（資料日 != 今天 → 必標）",
       ("歷史內文（as_of=" in _em1) == bool(_dt_em and _dt_em != _today),
       f"data_date={_dt_em} today={_today}")
    ck("S3.15 連結 2 條（完整報告＋數據版備援）",
       _em1.count("📄 檢視完整 LLM 緊急應變報告 →") == 1
       and _em1.count("📊 數據版報告（備援）") == 1, f"links={_em1.count('<a href=')}")
    ck("S3.16 緊急應變區塊無未替換模板佔位符", not re.search(r"__[A-Z_]+__", _em1),
       str(re.findall(r"__[A-Z_]+__", _em1)[:3]))
    # R4：today 是「值」敏感的（決定要不要上 as_of 標示）→ 資料日與牆鐘日兩個值都必須符合判準，
    #     不得只驗「閘門自己取的那個值」（否則正好掩蓋兩 producer 的 today 來源差異）。
    _wall = __import__("datetime").date.today().isoformat()
    for _tv in sorted({_today, _wall}):
        _b = asm.build_emergency_block(BASE, _snap, _tv)
        ck(f"S3.17 today={_tv}（值敏感）as_of 標示符合判準",
           ("歷史內文（as_of=" in _b) == bool(_dt_em and _dt_em != _tv), f"data_date={_dt_em}")
else:
    SKIP.append("S3.12-16 無 data/emergency_llm_analysis.json（略過）")

# 產出檔（若已存在）
_ap = argparse.ArgumentParser()
_ap.add_argument("--report", default=None)
_args, _ = _ap.parse_known_args()
_rpt = Path(_args.report) if _args.report else (BASE / f"daily_report_v2_{_today}.html")
if _rpt.exists():
    _h = rd(_rpt)
    ck(f"S3.7 產出檔含決策追蹤章（{_rpt.name}）", _MARKER in _h)
    _seg = ""
    if _EMIT in _h:
        _seg = _h.split(_EMIT, 1)[1].split("</tbody></table>", 1)[0]
    # 表頭是 <tr style=...>（不符 <tr>），故用 </tr> 扣 1 才是資料列數
    _n_out = _seg.count("</tr>") - 1 if _seg else 0
    ck("S3.8 產出檔決策卡列數 == pending 卡片數", _n_out == len(_pending),
       f"rows={_n_out} cards={len(_pending)}")
    ck("S3.9 產出檔無 __DR_ 殘留", "__DR_" not in _h, str(re.findall(r"__DR_[A-Z_]+__", _h)[:3]))
    ck("S3.10 產出檔缺口欄為 pp", bool(re.search(r">[+-]\d+\.\dpp<", _h)),
       str(re.findall(r">[+-]\d+\.\dpp<", _h)[:3]))
    _gp = re.findall(r"<td>([+-][\d,]+)</td>", _h)
    ck("S3.11 產出檔缺口欄無純金額型（負向）", not _gp, str(_gp[:3]))
else:
    SKIP.append(f"S3.7-11 產出檔不存在：{_rpt.name}")

# ═══════════ S5. 雙 producer 同輸入等效性 ═══════════
print("\n[S5] 雙 producer 同輸入等效性（呼叫點正規化後必須相同）")


def _sources(src):
    """回傳 {變數名: 正規化來源}。

      x = json.loads((BASE / "y.json").read_text(...))  →  "file:y.json"
      x = <expr>.get("penetration", {})                  →  "penetration"
    走訪全部節點（兩邊的賦值分別在模組層與 main() 內）。
    """
    m = {}
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not isinstance(tgt, ast.Name):
            continue
        seg = ast.get_source_segment(src, node.value) or ""
        g = re.search(r'["\']([A-Za-z0-9_.\-]+\.json)["\']', seg)
        if g and "json.loads" in seg:
            m[tgt.id] = "file:" + g.group(1)
        elif re.search(r'\.get\(\s*["\']penetration["\']', seg):
            m[tgt.id] = "penetration"
    return m


_HTML_NAMES = {"html", "daily_html", "_html", "out"}


def _normalize(path, funcname):
    """把某 producer 對 funcname 的呼叫，正規化成來源標記序列。"""
    src = rd(path)
    sources = _sources(src)
    tree = ast.parse(src)
    alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "daily_report_assembly":
            for a in node.names:
                alias[a.asname or a.name] = a.name
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            nm = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if alias.get(nm, nm) != funcname:
                continue
            out = []
            for a in node.args:
                if isinstance(a, ast.Name):
                    # html 參數先判（同名的區塊變數可能也被 json.loads 賦值，會污染來源表）
                    if a.id in _HTML_NAMES:
                        out.append("html")
                    elif a.id in sources:
                        out.append(sources[a.id])
                    elif a.id == "TODAY":
                        out.append("today")
                    else:
                        out.append("name:" + a.id)
                else:
                    seg = (ast.get_source_segment(src, a) or "").strip()
                    if "today()" in seg and "isoformat" in seg:
                        out.append("today")
                    elif re.search(r'\.get\(\s*["\']penetration["\']', seg):
                        out.append("penetration")
                    else:
                        out.append("expr:" + seg)
            return out
    return None


_n_p0 = _normalize(RUNDAILY, "build_p0_tasks_html")
_r_p0 = _normalize(REGEN, "build_p0_tasks_html")
_n_dr = _normalize(RUNDAILY, "substitute_dr_tokens")
_r_dr = _normalize(REGEN, "substitute_dr_tokens")
ck("S5.1 build_p0_tasks_html 兩邊輸入正規化後相同", _n_p0 == _r_p0,
   f"run_daily={_n_p0}  regenerate={_r_p0}")
ck("S5.2 substitute_dr_tokens 兩邊輸入正規化後相同", _n_dr == _r_dr,
   f"run_daily={_n_dr}  regenerate={_r_dr}")
ck("S5.3 build_p0_tasks_html 輸入＝(排程, 待處理卡, snapshot, 今天)",
   _r_p0 == ["file:schedule_events.json", "file:pending_decisions.json", "file:snapshot.json", "today"],
   str(_r_p0))
ck("S5.4 substitute_dr_tokens 輸入＝(html, snapshot.penetration)",
   _r_dr == ["html", "penetration"] and _n_dr == _r_dr, f"run_daily={_n_dr}  regenerate={_r_dr}")

# 同輸入實測：以檔案實際內容組出兩邊的輸入，必須得到同一份輸出
_in_a = asm.build_p0_tasks_html(asm.load_events(BASE), asm.load_pending(BASE), _snap, _today)
_in_b = asm.build_p0_tasks_html(asm.load_events(BASE), asm.load_pending(BASE), _snap, _today)
ck("S5.5 同輸入實測：兩次組裝 md5 相同", _md5(_in_a) == _md5(_in_b), _md5(_in_a)[:12])
ck("S5.6 組裝完全不依賴呼叫端（無隱含全域狀態）",
   _md5(asm.build_p0_tasks_html(list(_events), list(_pending), json.loads(json.dumps(_snap)), _today)) == _md5(_in_a))
_n_em = _normalize(RUNDAILY, "build_emergency_block")
_r_em = _normalize(REGEN, "build_emergency_block")
ck("S5.7 build_emergency_block 兩邊輸入正規化後相同", _n_em == _r_em,
   f"run_daily={_n_em}  regenerate={_r_em}")
ck("S5.8 build_emergency_block 輸入＝(BASE, snapshot.json, 今天)",
   _r_em == ["name:BASE", "file:snapshot.json", "today"], str(_r_em))
# R4：S5.7/S5.8 只比「來源 token」，比不出 today 的「值」。兩 producer 的 today 來源本就不同
#   （regenerate＝牆鐘日 `TODAY = dt.today()`；run_daily＝`TODAY = _snap_date`）
#   → 改為斷言「管線不變量存在」：regenerate 必須先滾日（_roll_day_to_today）才組裝，
#     使 snapshot.date == TODAY；run_daily 的 TODAY 必須來自 snapshot。不變量消失即 FAIL。
_regen_src, _run_src = rd(REGEN), rd(RUNDAILY)
_roll_pos = _regen_src.find("_roll_day_to_today(TODAY)")
_em_pos = _regen_src.find("build_emergency_block as _asm_em")
ck("S5.9 regenerate 先滾日才組緊急應變（R4 不變量：snapshot.date == TODAY）",
   0 <= _roll_pos < _em_pos, f"_roll_day_to_today@{_roll_pos} < 組裝@{_em_pos}")
ck("S5.10 run_daily 的 TODAY 來源＝snapshot date（與滾日後同值）",
   re.search(r"^TODAY\s*=\s*_snap_date\b", _run_src, re.M) is not None
   and re.search(r'_snap_date\s*=\s*_json\.load\(open\(BASE / "snapshot\.json"', _run_src) is not None)


# ═══════════ S4. 負向對照 ═══════════
print("\n[S4] 負向對照（把私有實作塞回去 → 閘門必須抓到）")
# 2026-10-07 CIO 要求：S1 改白名單式後，必須證明它真的抓得到「未知新檔」與「變數名繞過」
_negroot = Path(tempfile.gettempdir()) / "inc289_gate_neg"
if _negroot.exists():
    shutil.rmtree(_negroot, ignore_errors=True)
_negroot.mkdir(parents=True, exist_ok=True)
for _f in ("daily_report_assembly.py", "regenerate_report.py", "run_daily.py"):
    shutil.copy(BASE / _f, _negroot / _f)
# 注入 1：未知 producer（私有 __DR_ 取代 ＋ 私有決策追蹤章）
io.open(_negroot / "evil_producer.py", "w", encoding="utf-8", newline="").write(
    "def build(h, pen):\n"
    "    h = h.replace(\"__DR_TW_GAP__\", \"-999.9pp\")\n"
    "    h += '\\n<p>\U0001f4cb \u57f7\u884c\u4e2d\u51b3\u7b56\u8ffd\u8e2a</p>'\n"
    "    return h\n")
# 注入 1b-1d（INC-291 R2/R3）：私有緊急應變組裝的三種變體
#   1b）含 emoji 的原樣式；1c）**去 emoji**（R3：標記不得綁 emoji）；1d）formatter 單引號／位置引數
_EMOJI = "\U0001f4c5 "
io.open(_negroot / "evil_emergency.py", "w", encoding="utf-8", newline="").write(
    "def build():\n"
    "    return '<p>" + _EMOJI + _EM_KEY + "\uff1a2026-01-01</p>'\n")
io.open(_negroot / "evil_noemoji.py", "w", encoding="utf-8", newline="").write(
    "def build(x):\n"
    "    return f'<span>" + _EM_KEY + "\uff1a{x}</span>'\n")
io.open(_negroot / "evil_fmt.py", "w", encoding="utf-8", newline="").write(
    "def build(t):\n"
    "    return _format_content_to_html(t, content_type='" + _EM_CT_KEY + "')\n")
# 注入 1e（INC-291 R1）：子目錄放「同名檔」——舊設計以 basename 判白名單 → 全豁免
_nested = _negroot / "deep" / "nested"
_nested.mkdir(parents=True, exist_ok=True)
io.open(_nested / "daily_report_assembly.py", "w", encoding="utf-8", newline="").write(
    "def build(h):\n"
    "    return h.replace('__DR_TW_GAP__', '-999.9pp')\n")
# 注入 1f（INC-291 R2）：同名掃描器副本＋自行宣告 DETECTOR-ONLY → 不得藉自我豁免掩護私有 emit
io.open(_negroot / "verify_daily_report_single_producer.py", "w", encoding="utf-8", newline="").write(
    "# " + _SELF_MARK + "\n"
    "def build(x):\n"
    "    return f'<p>" + _EM_KEY + "\uff1a{x}</p>'\n")
# 注入 2：模板持有者用「變數名」繞過字面比對
_rdx = rd(_negroot / "run_daily.py")
_rdx = _rdx.replace("    daily_html = _asm_dr(daily_html, _pen)",
                    "    _tk = \"__DR_TW_GAP__\"\n"
                    "    daily_html = daily_html.replace(_tk, \"-999.9pp\")\n"
                    "    daily_html = _asm_dr(daily_html, _pen)")
io.open(_negroot / "run_daily.py", "w", encoding="utf-8", newline="").write(_rdx)
_neg_scan, _neg_n = scan_producers(_negroot)
print(f"  （負向鏡像：{_negroot}｜掃描 {_neg_n} 檔｜違規 {len(_neg_scan)} 筆）")
_tmp = Path(tempfile.gettempdir()) / "inc289_negative_control"
_tmp.mkdir(parents=True, exist_ok=True)
_div = rd(RUNDAILY).replace(
    '    daily_html = _asm_dr(daily_html, _pen)',
    '    daily_html = daily_html.replace("__DR_TW_GAP__", f"{_pen_total:,.0f}")\n'
    '    _p0_html += \'\\n<p>' + _EMIT + '\'')


def _static_violations(path):
    s = rd(path)
    return (len(re.findall(r'\.replace\(\s*["\']__DR_', s)) > 0) or (_EMIT_TPL in s)


_neg = _tmp / "run_daily.py"
io.open(_neg, "w", encoding="utf-8", newline="").write(_div)
_neg_hits = _static_violations(_neg)
ck("S4.1 負向樣本被判為違規（私有 __DR_ 取代／私有決策追蹤章）", _neg_hits,
   "S1.4/S1.5 這類檢查會在負向樣本上 FAIL")
ck("S4.2 正向檔（現行 run_daily.py）未被誤判", not _static_violations(RUNDAILY))
ck("S4.3 負向樣本與正向檔不同", _md5(_div) != _md5(rd(RUNDAILY)))

ck("S4.4 白名單掃描抓到「注入的未知 producer」（CIO 對抗點 A 的缺口已補）",
   any("evil_producer.py" in v[0] for v in _neg_scan), str(_neg_scan[:4]))
ck("S4.5 白名單掃描抓到「變數名繞過」形式的私有取代（CIO 對抗點 B 的缺口已補）",
   any("run_daily.py" in v[0] and "模板持有者" in v[1] for v in _neg_scan), str(_neg_scan[:4]))
ck("S4.6 對照組：同一份掃描器對正本 repo 判 0 違規（非全盤誤報）", not _repo_viol, str(_repo_viol[:3]))
ck("S4.7 白名單掃描抓到「私有緊急應變區塊組裝」（原樣式，含 emoji）",
   any("evil_emergency.py" in v[0] for v in _neg_scan), str(_neg_scan[:5]))
ck("S4.8 抓到「去 emoji」變體（R3：標記不綁 emoji）",
   any("evil_noemoji.py" in v[0] for v in _neg_scan), str(_neg_scan[:5]))
ck("S4.9 抓到「單引號／位置引數」formatter 變體（R3：AST 判定，非字面比對）",
   any("evil_fmt.py" in v[0] for v in _neg_scan), str(_neg_scan[:5]))
ck("S4.10 抓到「子目錄同名檔」全豁免漏洞（R1：白名單改 rel 判定）",
   any("deep/nested/daily_report_assembly.py" in v[0] for v in _neg_scan), str(_neg_scan[:6]))
ck("S4.11 抓到「同名掃描器自我豁免」掩護私有 emit（R2：EM 檢查在豁免之前）",
   any("verify_daily_report_single_producer.py" in v[0] and "緊急應變" in v[1] for v in _neg_scan),
   str(_neg_scan[:6]))
ck("S4.12 對照組：正本 repo 緊急應變違規 0 筆、負向鏡像 ≥3 筆（非空洞亦非全盤誤報）",
   not any("緊急應變" in v[1] for v in _repo_viol)
   and sum(1 for v in _neg_scan if "緊急應變" in v[1]) >= 3,
   f"repo={sum(1 for v in _repo_viol if '緊急應變' in v[1])} neg={sum(1 for v in _neg_scan if '緊急應變' in v[1])}")

# ═══════════ 結果 ═══════════
print("\n" + "=" * 78)
print(f"結果：{len(PASS)} PASS / {len(FAIL)} FAIL / {len(SKIP)} SKIP")
if FAIL:
    print("FAIL：")
    for x in FAIL:
        print("  - " + x)
if SKIP:
    print("SKIP：")
    for x in SKIP:
        print("  - " + x)
print("=" * 78)
sys.exit(1 if FAIL else 0)
