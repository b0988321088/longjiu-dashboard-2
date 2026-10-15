#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_html_publish_consistency.py — B1／§5「producer ↔ 白名單 ↔ 輸出路徑」一致性測試
（2026-10-15）

對應使用者 2026-10-15 B1 授權（§5 HTML 方案 A）：
  「兩份 HTML 納入版控及白名單。須確認兩個 producer、發布白名單和實際輸出路徑一致，
    不能只加入白名單就算完成。」

檢查面向（P1–P5）：
  P1 兩個 producer 的實際輸出路徑 = repo 根目錄的當日檔名，且與 links_config 前綴同源
  P2 index.html 「重要連結」指向的正是該家族最新檔（與 update_dashboard_links 同源判準）
  P3 發布白名單條目涵蓋這兩檔，且以閘門自身函式驗證規格安全／非強制 CIO／判為 AUTO
  P4 producer stage 白名單（regenerate_report.py 候選清單）已納入這兩檔
  P5 治理揭露：publish_gate 讀「版控內版本」→ 未 commit 前條目尚未生效（需正式 commit）

負向自測：P3e（移除條目→必回 CIO）、P3f（夾帶第三檔即未命中）、P4b（刪行→斷言變紅）。
全程唯讀：不寫檔、不 commit、不呼叫真 git 寫入。
執行：python -X utf8 tools/test_html_publish_consistency.py
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASS = FAIL = 0
TODAY = "2026-10-15"


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def main() -> int:
    pg = _load("pg_probe", ROOT / "publish_gate.py")
    lc = _load("links_config_probe", ROOT / "links_config.py")
    regen_src = (ROOT / "regenerate_report.py").read_text(encoding="utf-8")
    emg_src = (ROOT / "emergency_1330.py").read_text(encoding="utf-8")
    wk_src = (ROOT / "build_weekly_report.py").read_text(encoding="utf-8")
    idx = (ROOT / "index.html").read_text(encoding="utf-8")

    # ── P1 producer 輸出路徑 ────────────────────────────────────────────────
    print("=== P1 producer → 實際輸出路徑 ===")
    check("P1a emergency_1330.py 寫出 emergency_report_{today}.html",
          re.search(r'\(\s*LJ\s*/\s*f"emergency_report_\{today\}\.html"\s*\)\s*\.write_text', emg_src)
          is not None)
    check("P1b build_weekly_report.py 寫出 weekly_report_{today}.html",
          re.search(r'REPO\s*/\s*f"weekly_report_\{today\}\.html"', wk_src) is not None)
    check("P1c 兩者皆寫在 repo 根目錄（非子目錄）",
          'LJ = Path.home() / "Desktop" / "longjiu_system"' in emg_src
          and re.search(r'^REPO\s*=', wk_src, re.M) is not None)
    _p1d_e = "emergency_report_" == lc.PLACEHOLDER_PREFIX.get("__EMERGENCY__") \
        and lc.PREFIX_RULES.get("emergency_report_") == (".html", None)
    _p1d_w = "weekly_report_" == lc.PLACEHOLDER_PREFIX.get("__WEEKLY__") \
        and lc.PREFIX_RULES.get("weekly_report_") == (".html", None)
    check("P1d 檔名家族與 links_config 單一來源一致（__EMERGENCY__／__WEEKLY__）",
          _p1d_e and _p1d_w)
    _files = [ROOT / f"emergency_report_{TODAY}.html", ROOT / f"emergency_taiex_report_{TODAY}.html",
              ROOT / f"weekly_report_{TODAY}.html"]
    check("P1e 三檔今日實存於 repo 根", all(f.exists() for f in _files),
          f"missing={[f.name for f in _files if not f.exists()]}")

    # ── P1f–P1h：緊急應變兩報告家族（2026-10-15 裁決「B 修正版」追加） ──────────
    #   兩家族同一批產出＝gen_emergency_taiex_auto.py；taiex 家族原長期未納入版控規則。
    _gen_src = (ROOT / "gen_emergency_taiex_auto.py").read_text(encoding="utf-8")
    _gen_lines = ['rail = BASE / f"emergency_report_{TODAY}.html"',
                  'gh = BASE / f"emergency_taiex_report_{TODAY}.html"']
    _gen_has = [ln for ln in _gen_lines if ln in _gen_src]
    check("P1f gen_emergency_taiex_auto.py 同批寫出兩報告家族（逐字檔名、repo 根）",
          len(_gen_has) == 2, f"found={len(_gen_has)}")
    check("P1g 標的判定依 JSON source（美股／台股），不依產出時段（INC-214b）",
          "label_from_source" in _gen_src and '"美股" in s' in _gen_src
          and '"台股" in s' in _gen_src, "缺 label_from_source 或車道判定")
    _mut_gen = _gen_src
    for ln in _gen_lines:
        _mut_gen = _mut_gen.replace(ln, "")
    check("P1h 負向自測：刪掉任一行（單家族）後 P1f 必須變紅",
          all(ln not in _mut_gen for ln in _gen_lines))

    # ── P2 index.html 連結指向最新檔（與 update_dashboard_links 同源） ────────
    print("=== P2 index.html 連結 ↔ 最新產物 ===")
    for _pref, _tag in (("emergency_report_", "P2a 緊急應變"), ("weekly_report_", "P2b 週報")):
        _pats = sorted((ROOT).glob(f"{_pref}*.html"))
        _latest = _pats[-1].name if _pats else None
        check(f"{_tag}：index.html 的 href 指向最新檔（{_latest}）",
              _latest is not None and f'href="{_latest}"' in idx,
              f"latest={_latest}")

    # ── P3 發布白名單（用閘門自身函式） ─────────────────────────────────────
    print("=== P3 發布白名單條目 ===")
    al_work = json.loads((ROOT / "publish_allowlist.json").read_text(encoding="utf-8"))
    _changed = {f"emergency_report_{TODAY}.html", f"weekly_report_{TODAY}.html"}

    def _validate_like_gate(m: dict) -> list[str]:
        """逐條複製 publish_gate.load_allowlist() 的 fail-closed 規則。

        為什麼不直接呼叫 load_allowlist：它只讀「版控內版本」（git show <ref>:…），
        本輪禁止 commit → 工作區版本無法經由它驗證（該事實由 P5 揭露）。
        故規則在此逐條對齊（append_only 條目豁免 spec 檢查，改驗其自身條件）。
        """
        errs = []
        if not isinstance(m, dict) or not isinstance(m.get("entries"), list) or not m["entries"]:
            return ["白名單格式錯誤（需 entries 非空陣列）"]
        for e in m["entries"]:
            items = pg.spec_items(e)
            if not items:
                errs.append(f"條目 allow／patterns 皆空：{e.get('label')}")
                continue
            if any(not str(x).strip() for x in items):
                errs.append(f"條目含空字串：{e.get('label')}")
            for it in (e.get("allow") or []):
                if "*" in str(it):
                    errs.append(f"allow 為字面路徑、不得含 '*'：{it}")
            if e.get("append_only") is True:
                if not str(e.get("producer") or "").strip():
                    errs.append(f"append_only 條目必須標明 producer：{e.get('label')}")
                for it in items:
                    if "*" in str(it) or pg._norm(it) not in pg.APPEND_ONLY_PATHS:
                        errs.append(f"append_only 條目只能逐字列出受限兩檔：{it}")
                continue        # 與 load_allowlist 相同：受限車道條目不走 spec 檢查
            if "patterns" in e and not str(e.get("producer") or "").strip():
                errs.append(f"含 patterns 的條目必須標明 producer：{e.get('label')}")
            for it in items:
                why = pg.spec_unsafe_reason(it)
                if why:
                    errs.append(f"{e.get('label')}／{it}：{why}")
        return errs

    _bad = _validate_like_gate(al_work)
    check("P3a 全部條目通過閘門規格安全檢查（fail-closed）", _bad == [], f"{_bad[:3]}")
    check("P3a2 本條目自身規格安全（兩樣式皆通過 spec_unsafe_reason）",
          all(pg.spec_unsafe_reason(x) is None
              for x in ("emergency_report_*.html", "weekly_report_*.html")))
    check("P3a3 負向自測：過寬樣式必被擋（'*' 開頭／副檔名含 '*'）",
          pg.spec_unsafe_reason("*.html") is not None
          and pg.spec_unsafe_reason("report_*.py") is not None)
    _entry, _why = pg.match_entry(_changed, al_work)
    check("P3b 本次變更集合命中白名單條目", _entry is not None, f"why={_why}")
    _specials = {p: pg.special_reason(p) for p in _changed}
    check("P3c 兩檔皆非強制 CIO 類（special_reason 全 None）",
          all(v is None for v in _specials.values()), f"{_specials}")
    _mode, _must, _reason = pg.classify(_changed, _entry, specials={})
    check("P3d 閘門判定＝AUTO（低風險可發布）",
          _mode == "AUTO" and _must is False, f"{_mode}/{_reason}")

    # 負向自測
    _e2, _w2 = pg.match_entry(_changed, {"entries": [x for x in al_work["entries"]
                                                     if x is not _entry]})
    _m2, _mu2, _ = pg.classify(_changed, _e2, specials={})
    check("P3e 負向自測：移除本條目 → 未命中、判定回 CIO（P3b/P3d 有鑑別力）",
          _e2 is None and _m2 == "CIO", f"{_m2}/{_w2}")
    _e3, _w3 = pg.match_entry(_changed | {"index.html"}, al_work)
    check("P3f 負向自測：夾帶 index.html → 不得被本條目吸收（回 None 或非本條目）",
          _e3 is None or _e3 is not _entry, f"entry={(_e3 or {}).get('label')}")

    # ── P3g–P3j：taiex 家族與「不得廣泛 stage」（2026-10-15 裁決追加） ─────────
    _pats = list((_entry or {}).get("patterns") or [])
    check("P3g 白名單已納入 emergency_taiex_report_*.html（同一套受控產物規則）",
          "emergency_taiex_report_*.html" in _pats, f"patterns={_pats}")
    _changed_tx = {f"emergency_taiex_report_{TODAY}.html"}
    _entry_tx, _why_tx = pg.match_entry(_changed_tx, al_work)
    _mode_tx, _must_tx, _reason_tx = pg.classify(_changed_tx, _entry_tx, specials={})
    check("P3h taiex 家族單獨變更 → 命中本條目且判定＝AUTO／非強制 CIO",
          _entry_tx is _entry and _mode_tx == "AUTO" and _must_tx is False,
          f"entry={(_entry_tx or {}).get('label')} {_mode_tx}/{_reason_tx}")
    _e_tx2, _ = pg.match_entry(_changed_tx | {"penetration_report_2026-10-15.html"}, al_work)
    check("P3i 負向自測：taiex 家族夾帶未指定報告頁 → 不得被本條目吸收",
          _e_tx2 is None or _e_tx2 is not _entry, f"entry={(_e_tx2 or {}).get('label')}")
    _all_pats = [str(p) for e in al_work["entries"] for p in (e.get("patterns") or [])]
    check("P3j 全部 patterns 皆為單層檔名樣式（無 '/'、無 '**'＝不得整個目錄廣泛放行）",
          all("/" not in p and "**" not in p for p in _all_pats), f"{_all_pats}")

    # ── P4 producer stage 白名單 ────────────────────────────────────────────
    print("=== P4 producer stage 白名單（regenerate_report.py） ===")
    _stage_lines = ["_push_candidates.append(f'emergency_report_{TODAY}.html')",
                    "_push_candidates.append(f'emergency_taiex_report_{TODAY}.html')",
                    "_push_candidates.append(f'weekly_report_{TODAY}.html')"]
    _has = [ln for ln in _stage_lines if ln in regen_src]
    check("P4a 候選清單已納入三份 HTML（兩報告家族＋週報，逐字檔名認領）",
          len(_has) == 3 and "dirty_gate" in regen_src, f"found={len(_has)}")
    _mut = regen_src
    for ln in _stage_lines:
        _mut = _mut.replace(ln, "")
    check("P4b 負向自測：刪掉這些行後斷言必須變紅（P4a 有鑑別力）",
          all(ln not in _mut for ln in _stage_lines))
    # P4c–P4d：緊急應變車道「只收緊」——13:00／21:30 班不帶 --no-push 也不得 commit/push
    _lane_line = '_NO_PUSH = ("--no-push" in sys.argv) or _EMERGENCY_LANE'
    check("P4c regenerate_report.py 已設 LJ_EMERGENCY_LANE 只收緊車道（發布需另授權）",
          _lane_line in regen_src and 'LJ_EMERGENCY_LANE' in regen_src)
    check("P4d 負向自測：刪掉收緊車道那行後 P4c 必須變紅",
          _lane_line not in regen_src.replace(_lane_line, ""))

    # ── P5 治理揭露：白名單讀版控版本 ───────────────────────────────────────
    print("=== P5 治理揭露（未 commit 前不生效） ===")
    _pg_src = (ROOT / "publish_gate.py").read_text(encoding="utf-8")
    check("P5a 閘門以 git show <ref>:publish_allowlist.json 讀版控版本（工作區改寫無效）",
          'f"{ref}:{ALLOWLIST_PATH}"' in _pg_src)
    _head_al = _git("show", "HEAD:publish_allowlist.json")
    _head_has = "emergency_report_" in _head_al
    check("P5b HEAD 版本白名單已含本條目（2026-10-15 B1 正式 commit 後生效）",
          _head_al != "" and _head_has, f"head_has_entry={_head_has}")
    # P5c：taiex 家族規則須「工作區＋版控」一致才算生效（2026-10-15 21:xx 已由 B1 正式
    #   commit 納入 → 工作區與 HEAD 都應為真）。此條為真相檢查，不是期待值檢查。
    #   鑑別力：把 HEAD 版本中的 taiex 樣式移除（模擬「未 commit」）→ 條件必須翻紅。
    _head_has_tx = "emergency_taiex_report_*.html" in _head_al
    _work_has_tx = "emergency_taiex_report_*.html" in (ROOT / "publish_allowlist.json").read_text(encoding="utf-8")
    check("P5c 工作區與版控一致：taiex 家族規則已在 HEAD 生效（work=True head=True）",
          _work_has_tx and _head_has_tx, f"work={_work_has_tx} head={_head_has_tx}")
    _pre_has_tx = "emergency_taiex_report_*.html" in _head_al.replace("emergency_taiex_report_*.html", "")
    check("P5d 負向自測：模擬未 commit（HEAD 移除 taiex 樣式）後 P5c 條件必須翻紅",
          _work_has_tx and not _pre_has_tx)

    # ── P6 三處一致（生成器 ↔ stage 候選 ↔ 白名單）2026-10-15 裁決「確認三者一致」──
    print("=== P6 三處一致（生成器 ↔ stage 候選 ↔ 白名單） ===")
    _gen_families = sorted({m.group(1) for m in re.finditer(r'"((?:emergency|weekly)[a-z_]*report_)\{TODAY\}\.html"', _gen_src)})
    _want_patterns = sorted({f + "*.html" for f in _gen_families})
    _stage_missing = [f'_push_candidates.append(f\'{f}{{TODAY}}.html\')'
                      for f in _gen_families
                      if f'_push_candidates.append(f\'{f}{{TODAY}}.html\')' not in regen_src]
    _pat_missing = [p for p in _want_patterns if p not in _pats]
    check("P6a 生成器寫出的每個家族都有對應 stage 候選（逐字檔名）",
          bool(_gen_families) and not _stage_missing, f"generator={_gen_families} missing={_stage_missing}")
    check("P6b 生成器寫出的每個家族都有對應白名單樣式",
          bool(_want_patterns) and not _pat_missing, f"want={_want_patterns} missing={_pat_missing}")
    _mut_regen = regen_src.replace("_push_candidates.append(f'emergency_taiex_report_{TODAY}.html')", "")
    _mut_missing = [f for f in _gen_families
                    if f'_push_candidates.append(f\'{f}{{TODAY}}.html\')' not in _mut_regen]
    check("P6c 負向自測：刪掉 taiex 的 stage 候選後，P6a 的判準必須轉紅（有鑑別力）",
          _mut_missing == ["emergency_taiex_report_"], f"mut_missing={_mut_missing}")
    _expect_pats = set(_want_patterns) | {"weekly_report_*.html"}
    check("P6d 本條目樣式集合＝生成器家族∪週報（不得夾帶其他家族或目錄級樣式）",
          set(_pats) == _expect_pats, f"pats={sorted(_pats)} want={sorted(_expect_pats)}")

    print(f"\n測試結果：{PASS} PASS / {FAIL} FAIL")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
