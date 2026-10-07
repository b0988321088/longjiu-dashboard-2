# -*- coding: utf-8 -*-
"""INC-289 閘門：日報是否只有一套 canonical producer。

驗的不是「今天這份 HTML 看起來恢復了」，而是**正式發布來源只有一套實作**——
否則下一次排程仍可能再產出「有章／沒章」兩種版本。

四個面向：
  S1 唯一實作：兩個 producer 都必須呼叫 daily_report_assembly；不得各自實作
  S2 呼叫契約：AST 檢查兩邊呼叫同一函式、參數來源一致；同一輸入兩次呼叫逐位元相同
  S3 真實輸入產出：決策追蹤章存在、列數 == 卡片數、洲際W轉貸計數一致、缺口欄＝pp、無 __DR_ 殘留
  S4 負向對照：把私有實作塞回暫存副本 → 閘門必須 FAIL（證明閘門非空洞）

唯讀：只讀 repo 檔＋寫 %TEMP% 暫存副本。rc=0 全過、rc=1 有 FAIL。
用法：python tools/verify_daily_report_single_producer.py [--report <html>]
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
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
REQUIRED_API = ("build_schedule_rows", "build_p0_tasks_html", "substitute_dr_tokens", "build_decision_rows")
_MARKER = "執行中決策追蹤"
# 只認「會被寫進 HTML 的那一行」，註解／docstring 提到這串字不算私有實作
_EMIT = '📋 執行中決策追蹤</p>'
_EMIT_TPL = '<p style="margin-top:12px;font-weight:700;color:#3b82f6">' + _EMIT

print("=" * 78)
print("INC-289 閘門：日報單一 canonical producer")
print("=" * 78)

# ═══════════ S1. 唯一實作 ═══════════
print("\n[S1] 唯一實作（兩個 producer 都必須走共用模組）")
ck("S1.1 daily_report_assembly.py 存在", SHARED.exists(), str(SHARED))
src_shared = rd(SHARED) if SHARED.exists() else ""
_shared_tree = ast.parse(src_shared) if src_shared else None
_shared_defs = {n.name for n in ast.walk(_shared_tree) if isinstance(n, ast.FunctionDef)} if _shared_tree else set()
ck("S1.2 共用模組提供完整 API", all(a in _shared_defs for a in REQUIRED_API),
   "缺：" + str([a for a in REQUIRED_API if a not in _shared_defs]))

for tag, path in (("regenerate_report.py", REGEN), ("run_daily.py", RUNDAILY)):
    s = rd(path)
    tree = ast.parse(s)
    # 由共用模組匯入的名稱
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "") == "daily_report_assembly":
            imported |= {a.name for a in node.names}
    ck(f"S1.3 {tag} 自共用模組匯入組裝 API",
       len(imported & set(REQUIRED_API)) >= 3, "匯入：" + str(sorted(imported)))
    # 不得自行做 __DR_ 取代
    n_local_dr = len(re.findall(r'\.replace\(\s*["\']__DR_', s))
    ck(f"S1.4 {tag} 無私有 __DR_*__ 取代", n_local_dr == 0, f"命中 {n_local_dr} 處")
    # 不得自行產生決策追蹤章
    ck(f"S1.5 {tag} 無私有「執行中決策追蹤」實作", _EMIT_TPL not in s, f"命中 {s.count(_EMIT_TPL)} 處")
    # 必須真的呼叫（非只有 import）
    ck(f"S1.6 {tag} 實際呼叫組裝函式",
       ("_asm_p0(" in s and "_asm_dr(" in s) or ("build_p0_tasks_html(" in s and "substitute_dr_tokens(" in s))
ck("S1.7 共用模組是「執行中決策追蹤」唯一出處（emit 字串僅 1 處）",
   src_shared.count(_EMIT_TPL) == 1, f"命中 {src_shared.count(_EMIT_TPL)} 處")

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


def _today_exprs():
    return {"TODAY", "__import__('datetime').date.today().isoformat()",
            "date.today().isoformat()", "dt.today().isoformat()",
            "(datetime.date.today()).isoformat()"}


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


# ═══════════ S4. 負向對照 ═══════════
print("\n[S4] 負向對照（把私有實作塞回去 → 閘門必須抓到）")
_tmp = Path(tempfile.gettempdir()) / "inc289_negative_control"
_tmp.mkdir(parents=True, exist_ok=True)
_div = rd(RUNDAILY).replace(
    '    daily_html = _asm_dr(daily_html, _pen)',
    '    daily_html = daily_html.replace("__DR_TW_GAP__", f"{_pen_total:,.0f}")\n'
    '    _p0_html += \'\\n<p>📋 執行中決策追蹤</p>\'')


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
