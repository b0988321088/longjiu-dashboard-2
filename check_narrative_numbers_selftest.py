#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_narrative_numbers_selftest.py — 內文數字守門的回歸自測（唯讀，不寫任何檔）

用途：收工稽核第 13 類會「先跑本檔再實掃」。守門本身被改壞（合法值集合漏掉某個
派生口徑、或比對被放寬成永遠通過）時，同一晚就會亮紅燈，而不是等下一次誤報才發現。

為什麼要有它（2026-09-25 教訓）：
  第 13 類自 2026-09-23 上線後，3 天內被「合法派生口徑不足」觸發 4 次
  （科技分母 → 現金派生 → 引擎偏移 → 偏移後目標值/建議金額）。
  每次都是同一種病：集合落後於內文會引用的口徑。修法是「補集合 + 補案例」，
  本檔就是把那些案例固定下來，防止回歸。

判準：正向案例必須放行、負向案例必須擋下；任一不符 → exit 1。
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import check_narrative_numbers as C  # noqa: E402

# (內文片段, 應放行?, 說明)
CASES: list[tuple[str, bool, str]] = [
    # ── 引擎口徑（2026-09-25 補洞；2026-10-23 改為動態生成）──
    # 原本寫死 9/25 當天的引擎值（債券 +5pp／美股 -8pp／債券 30%／美股 22%／衛星 7%），
    # 引擎戰術偏移一歸零（2026-10-23 全列 0pp＝紅線解除後不加不減）就讓自測假失敗，
    # 收工稽核顯示成「內文守門自測失敗（守門本身有問題）」——但守門是好的，壞的是案例。
    # 這與 9/26 現金、9/29 穿透同一個坑，故改由下方 _engine_cases() 現讀最新
    # macro_regime_*.json 生成，正向與負向案例都跟著引擎走。
    # ── 避險衛星覆蓋（2026-09-25 B 批；修前這些標籤根本不存在＝從未被掃）──
    # 衛星／避險衛星的正負向案例同樣改由 _engine_cases() 動態生成（見下方）。
    ("黃金 5%", True, "刻意未註冊黃金標籤（會與金價 2,400 碰撞）→ 不掃"),
    ("衛星 +183.1萬", True, "萬為單位無千分位 → 金額型態不成立，不掃"),
    # ── known limitation：空集合＝該口徑不掃（既有設計，非本批引入）──
    # build_allowed 對每個標籤只補「它有來源」的口徑（LABEL_GICS 來源的標籤通常只有 pct），
    # scan_text 對空集合一律跳過比對。本批新增的「移除＋警示」只涵蓋 _engine_calibers
    # 新建的標籤；既有標籤的空集合（金融／資訊科技 無 twd、衛星／避險衛星 無 gap、
    # 現金 無 gap/off …）仍是不掃的。下面兩條把行為固定下來 —— 任何「改成會掃」的
    # 變動都必須是刻意的，不能順手改掉。
    ("金融 1,234,567", True, "known limitation：金融 無 twd 集合 → 金額不掃"),
    ("現金 5pp", True, "known limitation：現金 gap/off 皆空 → pp 不掃"),
    # ── 穿透真值（既有）──
    # 2026-09-29：原寫死 9 月舊穿透值（債券 +3.7pp／+4.7pp、科技 15.3%、防守 17.3%）
    #   → 真值日後案例落後、自測假失敗（與 2026-09-26 現金案例同一個坑）。
    #   改由下方 _pen_cases() 動態讀 snapshot.penetration 生成，守門強度不變。
    ("科技 17.5%", False, "負向：INC-245 原始案例（模型自行推算）"),
    # ── 現金派生口徑（INC-244）──
    # 2026-09-26：原寫死 861,818/161,818（9 月舊現金）→ 現金一更新就讓自測假失敗
    #   （是「案例落後」不是「守門壞掉」）。改由下方 _cash_cases() 動態讀 snapshot 生成。
    ("現金 1,200,000", False, "負向：合計底線 1,200,000 已於 2026-09-27 取消（追繳緩衝作廢）→ 必須擋下"),
    ("現金 999,999", False, "負向：不存在的現金金額"),
    # ── 守門不該掃的型態（零假陽性合約）──
    ("高科技/半導體 17.5%", True, "複合詞不掃（刻意不比）"),
    ("防守合併 68.5%", True, "中介詞句子不掃"),
    ("科技目標 ≤20%", True, "中介詞句子不掃"),
]


def _cash_cases() -> list[tuple[str, bool, str]]:
    """2026-09-26：動態生成「現金派生口徑」案例（讀 snapshot）。

    原本寫死當期現金與乾粉值 → 每次現金入帳就讓自測亮紅燈，看起來像守門壞掉，
    實際只是案例落後。改為動態，維持同樣的守門強度（值仍須落在合法集合內）。
    """
    import json
    try:
        _s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    _cash = int(_s.get("cash_total") or 0)
    if not _cash:
        return []
    _floor = int(((_s.get("cash_floor_rule") or {}).get("cash_floor")) or 0)
    _out = [("現金 %s" % format(_cash, ","), True, "現金原值（動態）")]
    if _floor and _cash > _floor:
        _out.append(("現金 %s" % format(_cash - _floor, ","), True, "乾粉＝現金 − 生活底線（動態）"))
    # 2026-10-01：可動用現金口徑（cash_layers.unrestricted_cash）——內文寫「現金 853,675
    #   守住底線 70 萬」時指的是可動用現金（指定用途款不列現金），與穿透桶『現金/安全網』不同。
    #   同樣動態讀 snapshot，避免現金一動就假失敗。
    _liq = int(((_s.get("cash_layers") or {}).get("available")
                or (_s.get("cash_layers") or {}).get("unrestricted_cash")) or 0)
    if _liq:
        _out.append(("現金 %s" % format(_liq, ","), True, "可動用現金＝cash_layers.unrestricted_cash（動態）"))
        if _floor and _liq > _floor:
            _out.append(("現金 %s" % format(_liq - _floor, ","), True, "可動用緩衝＝可動用現金 − 生活底線（動態）"))
    return _out


CASES += _cash_cases()


def _live_engine() -> dict:
    """2026-10-23：讀最新 macro_regime_YYYY-MM-DD.json，回傳 {標籤: {'pct':set,'off':set}}。

    選檔規則刻意與 check_narrative_numbers._engine_calibers 一致（只認日期命名、取最新
    日期、日期不合法跳過），否則自測驗的口徑會與守門實際採用的那一套不同 → 自測通過
    但實掃誤報（或反之），比沒有自測更危險。
    """
    import datetime
    import json
    import re as _re
    _files: list[tuple[str, Path]] = []
    for _p in BASE.glob("macro_regime_*.json"):
        _m = _re.fullmatch(r"macro_regime_(\d{4}-\d{2}-\d{2})\.json", _p.name)
        if not _m:
            continue
        try:
            datetime.date.fromisoformat(_m.group(1))
        except ValueError:
            continue
        _files.append((_m.group(1), _p))
    if not _files:
        return {}
    _files.sort()
    try:
        _data = json.loads(_files[-1][1].read_text(encoding="utf-8"))
    except Exception:
        return {}
    _out: dict[str, dict[str, set]] = {}
    for _row in ((_data.get("targetAllocation") or {}).get("rows") or []):
        _name = str(_row.get("資產", "")).strip()
        if _name not in C.ENGINE_ROWS:
            continue
        _t, _off = _row.get("target"), _row.get("燈號偏移後")
        for _lab in C.ENGINE_ROWS[_name]:
            _spec = _out.setdefault(_lab, {"pct": set(), "off": set()})
            if isinstance(_t, (int, float)) and isinstance(_off, (int, float)):
                _spec["off"].add(round(float(_off) - float(_t), 1))
                _spec["pct"].add(round(float(_off), 1))
            if isinstance(_t, (int, float)):
                _spec["pct"].add(round(float(_t), 1))
    return _out


def _pp(v: float) -> str:
    """有號 pp 字串（守門解析用）：4 → '+4.0'、0 → '+0.0'、-8 → '-8.0'。"""
    return f"{float(v):+.1f}"


def _num(v: float) -> str:
    """百分比數字：25.0 → '25'、36.3 → '36.3'。"""
    return f"{round(float(v), 1):g}"


def _engine_cases() -> list[tuple[str, bool, str]]:
    """2026-10-23：動態生成「引擎口徑」案例（讀最新引擎檔，不寫死任何數字）。

    覆蓋三種合法派生口徑：①戰術偏移（含『偏移後』前綴寫法、含無號寫法）
    ②偏移後目標值 ③負向對照組（集合外的值必須擋下）。
    引擎偏移全為 0 的日子（紅線解除後不加不減）仍會生成 "+0.0pp" 案例 —— 0 必須
    被視為合法，否則守門會在「引擎不動」的日子誤檔正常內文。
    """
    _cal = _live_engine()
    if not _cal:
        return []
    _out: list[tuple[str, bool, str]] = []
    for _lab in ("台股", "美股", "防守型配息", "債券", "避險衛星", "衛星"):
        _spec = _cal.get(_lab)
        if not _spec:
            continue
        _pcts = sorted(_spec["pct"])
        _offs = sorted(_spec["off"], key=abs)
        if _pcts and max(_pcts) > 0:
            _v = max(_pcts)
            _out.append((f"{_lab} {_num(_v)}%", True, f"引擎偏移後目標值（動態 {_num(_v)}%）"))
            _out.append((f"{_lab} {_num(_v + 11.3)}%", False, "負向：不存在的目標值"))
        if _offs:
            _o = max(_offs, key=abs)
            _out.append((f"{_lab} {_pp(_o)}pp", True, "引擎戰術偏移（動態）"))
            _out.append((f"{_lab} {_num(abs(_o))}pp", True, "引擎戰術偏移（內文寫成無號幅度）"))
            _out.append((f"偏移後{_lab} {_pp(_o)}pp", True, "引擎偏移口徑（偏移後＝動態值）"))
            if _o:
                _out.append((f"偏移後{_lab} {_pp(-_o)}pp", False, "負向：方向相反 → 擋"))
            _out.append((f"{_lab} {_pp(abs(_o) + 11.3)}pp", False, "負向：不存在的偏移"))
    return _out


def _pen_cases() -> list[tuple[str, bool, str]]:
    """2026-09-29：動態生成「穿透真值／現況缺口」案例（讀 snapshot.penetration）。

    原本寫死 9 月值（美股 +9.5pp、債券 +3.7/+4.7pp、科技 15.3%、防守 17.3%）
    → 真值日更新穿透後，案例落後使自測假失敗（看起來像守門壞掉）。
    動態生成維持同樣守門強度：值仍須落在守門算出的合法集合內才算放行。
    """
    import json
    try:
        _s = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return []
    _pct = ((_s.get("penetration") or {}).get("actual_pct") or {})
    _out: list[tuple[str, bool, str]] = []
    _tg = ((_s.get("penetration") or {}).get("targets") or {})
    _us = _pct.get("美股市值型成長")
    _tg_us = _tg.get("美股市值型", 30)
    if isinstance(_us, (int, float)):
        _gap = round(_us - float(_tg_us), 1)
        _out.append((f"超標：美股 +{_gap}pp", True, "現況缺口口徑（動態）"))
        _out.append((f"超標：美股 -{_gap}pp", False, "負向：超標必為正缺口，寫成負 → 擋"))
        # 2026-10-23：鄰句回歸案例原本寫死「債券 +5pp」（9/25 引擎值）→ 引擎歸零即假失敗。
        # 改讀引擎當日偏移，切段邏輯仍被鎖住。
        _bd_off_set = ((_live_engine().get("債券") or {}).get("off")) or {0.0}
        _bd_off = sorted(_bd_off_set, key=abs)[-1]
        _out.append((f"美股超標 {_gap}pp、債券 {_pp(_bd_off)}pp", True,
                     "切段：鄰句『超標』不得污染債券的引擎值"))
    _bd = _pct.get("債券")
    _tg_bd = _tg.get("債券", 25)
    if isinstance(_bd, (int, float)):
        _out.append((f"債券 {_bd - float(_tg_bd):+.1f}pp", True, "現況缺口（佔總資產分母，動態）"))
    _tech = _pct.get("美股市值型成長_科技")
    if isinstance(_tech, (int, float)):
        _out.append((f"科技 {_tech}%", True, "穿透真值（動態）"))
    _defe = _pct.get("防守型配息")
    if isinstance(_defe, (int, float)):
        _out.append((f"防守型配息 {_defe}%", True, "穿透真值（動態）"))
    # 回歸 V-B（2026-09-25）：口徑為引擎偏移、但該標籤 off 為空（科技不在 ENGINE_ROWS）
    # → 退回聯集比對、不得靜默跳過。原寫死 5pp（會隨穿透真值漂移），改取遠離任何集合的值。
    _out.append(("偏移後科技 +99.9pp", False, "回歸 V-B：該標籤 off 為空 → 退回聯集擋下"))
    return _out


CASES += _pen_cases()
CASES += _engine_cases()

# 案例數下限（2026-10-23）：_engine_cases() 讀不到引擎檔時會回空 → 引擎案例 38 條整批
# 消失（總數 59→21）卻仍「全綠」，這是最危險的假綠。故設兩道下限：總數與引擎案例數。
# 調整案例時同步維護，且只能上調不能下調（下調等於放寬守門）。
MIN_CASES = 45
MIN_ENGINE_CASES = 30

# ── 警示自測（2026-09-25 補）：引擎檔異狀必須出聲、正常檔不得有雜訊 ──
# 這層是「引擎口徑悄悄消失」的唯一可見點（症狀會顯示成內文數字對不上、指不到根因），
# 所以把它鎖進自測，而不是只靠人記得看 stderr。
_DEL = object()          # 代表「把這個鍵整個拿掉」


def _engine_rows():
    return [
        {"資產": "台股市值型成長", "target": 10, "燈號偏移後": 10, "建議金額(±)": 0},
        {"資產": "美股市值型成長", "target": 30, "燈號偏移後": 22, "建議金額(±)": 2092600},
        {"資產": "防守型配息", "target": 30, "燈號偏移後": 32, "建議金額(±)": 523150},
        {"資產": "債券", "target": 25, "燈號偏移後": 30, "建議金額(±)": 1307875},
        {"資產": "避險衛星合計(黃金+石油)", "target": 0, "燈號偏移後": 7, "建議金額(±)": 1831025},
    ]


def _payload(rows) -> str:
    import json
    return json.dumps({"targetAllocation": {"rows": rows}}, ensure_ascii=False)


def _mut(*specs) -> str:
    """以「完整 5 列」為基底，只突變指定列／欄位。

    為什麼一定要完整列（2026-09-25 獨立複審抓到的假信心）：
    先前版本「部分欄位型別錯」「欄位被改名」兩案例的 payload 只有單列債券 →
    光是缺少其餘 4 列就讓 _missing 分支先出聲、案例即判定通過；把 `if _partial:`
    整段刪掉，自測照樣印 38/38、exit 0。改為完整列＋單一突變後，每個分支才會被
    獨立觸發（已用變異測試雙向驗證：刪 _partial → FAIL、刪 _missing → FAIL）。
    """
    rows = _engine_rows()
    for asset, changes in specs:
        for row in rows:
            if row["資產"] == asset:
                for k, v in changes.items():
                    if v is _DEL:
                        row.pop(k, None)
                    else:
                        row[k] = v
    return _payload(rows)


class _FakeEngineFile:
    def __init__(self, payload: str, days_ago: int = 0, name: str | None = None) -> None:
        import datetime
        # 檔名日期用「今天往回推」動態產生。寫死日期的後果（獨立複審實測）：本自測會在
        # 幾天後自己過期 —— 檔齡警示把「不得出聲」的案例誤染紅，且同一案例隱性疊加兩個
        # 分支＝違反「完整輸入＋單一突變」原則。
        _d = datetime.date.today() - datetime.timedelta(days=days_ago)
        self.name = name or f"macro_regime_{_d:%Y-%m-%d}.json"
        self._payload = payload

    def read_text(self, **_kw) -> str:
        return self._payload


class _FakeBase:
    """files=[] 用來模擬「找不到任何日期命名的引擎檔」。"""

    def __init__(self, files) -> None:
        self._files = list(files)

    def glob(self, _pattern: str):
        return list(self._files)


_OK = _payload(_engine_rows())
_MISSING = _payload([r for r in _engine_rows() if r["資產"] != "債券"])
_PARTIAL = _mut(("債券", {"燈號偏移後": "30"}))
_RENAMED = _mut(("債券", {"燈號偏移後": _DEL, "偏移後": 30}))
_BAD3 = _mut(("債券", {"target": "底線制", "燈號偏移後": None, "建議金額(±)": "N/A"}))

WARN_CASES: list[tuple[str, list, bool, str | None, str | None]] = [
    # (說明, 合成引擎檔清單, 期望出聲?, 期望「不在 allowed」的標籤, 期望「在 allowed」的標籤)
    # 原則：要測「某分支會出聲」，必須讓其他分支不出聲（完整輸入＋單一突變）。
    ("完整引擎檔、檔齡 1 天（引擎跑之前的正常空窗）→ 不得出聲",
     [_FakeEngineFile(_OK, 1)], False, None, "債券"),
    ("整列缺列：拿掉債券列 → 該桶引擎口徑消失（_missing 分支）",
     [_FakeEngineFile(_MISSING)], True, None, None),
    ("部分欄位型別錯：債券 燈號偏移後→字串（_partial 分支，其餘 4 列完整）",
     [_FakeEngineFile(_PARTIAL)], True, None, None),
    ("欄位被改名：債券 燈號偏移後→偏移後（_partial 分支，其餘 4 列完整）",
     [_FakeEngineFile(_RENAMED)], True, None, None),
    ("壞 JSON", [_FakeEngineFile("{oops")], True, None, None),
    ("引擎檔過期 10 天：口徑可能落後，必須出聲", [_FakeEngineFile(_OK, 10)], True, None, None),
    ("檔齡 2 天＝漏跑一次（門檻邊界）→ 必須出聲", [_FakeEngineFile(_OK, 2)], True, None, None),
    # ── 舊分支補覆蓋（2026-09-25 複審指出這兩條原本沒有專屬案例）──
    # 關鍵不是「有沒有出聲」（_partial 已經會出聲），而是那個**行為**：新建卻補不到值的標籤
    # 必須被移出 allowed —— 空集合在 scan_text 內＝跳過比對＝靜默放行（假陰性）。
    ("三欄位全非數字：新建的 債券 標籤必須被移出 allowed（不得留空集合）",
     [_FakeEngineFile(_BAD3)], True, "債券", None),
    # ── 收尾批二：複審的 J_b1/J_b2/N1 三項各補專屬案例（2026-09-26）──
    ("找不到任何日期命名引擎檔（glob 回空）→ 必須出聲",
     [], True, None, None),
    ("壞日期檔名（2026-13-45）與合法檔並存 → 出聲，且合法檔口徑仍須生效",
     [_FakeEngineFile(_OK, 0), _FakeEngineFile(_OK, 0, name="macro_regime_2026-13-45.json")],
     True, None, "債券"),
    ("未來日期檔（今天 +30 天）→ 必須出聲，且仍照用該檔口徑",
     [_FakeEngineFile(_OK, -30)], True, None, "債券"),
]


def _warn_check(files) -> tuple[bool, str, dict]:
    """回傳 (是否對 stderr 出聲, 訊息, 補完後的 allowed)。"""
    import contextlib
    import io
    _allowed: dict = {}
    _buf = io.StringIO()
    with contextlib.redirect_stderr(_buf):
        C._engine_calibers(_allowed, base=_FakeBase(files))
    _msg = _buf.getvalue().strip()
    return bool(_msg), _msg, _allowed


def _eval_cases(allowed: dict, scan=None, verbose: bool = True) -> tuple[int, int]:
    """跑正向／負向案例，回傳 (fail 數, 案例數)。scan 可注入（變異測試用）。"""
    _scan = scan or C.scan_text
    fails = total = 0
    for text, expect_pass, note in CASES:
        total += 1
        hits = _scan(text, allowed, "SELFTEST")
        ok = (not hits) == expect_pass
        if not ok:
            fails += 1
        if verbose:
            print(f"{'PASS' if ok else 'FAIL'} | {'應放行' if expect_pass else '應擋下'} | {text} | {note}"
                  + ("" if ok else f" | hits={hits}"))
    return fails, total


def _mutation_checks(allowed: dict) -> list[tuple[str, bool, str]]:
    """2026-10-23：變異測試 —— 故意把守門弄壞，自測必須轉紅。

    為什麼必要：案例與實作若「同源」就會一起錯（自測全綠但守門已失效＝假綠）。
    唯一能證明自測有偵測力的方法是把受測邏輯逐一拿掉，看它會不會叫。
    全部在記憶體內完成，不寫檔、不改真值。
    """
    _out: list[tuple[str, bool, str]] = []
    _f1, _ = _eval_cases(allowed, scan=lambda *a, **k: [], verbose=False)
    _out.append(("M1 比對函式永遠放行（scan 回空）", _f1 > 0, f"轉紅 {_f1} 條"))
    _a2 = {k: v for k, v in allowed.items() if k not in _live_engine()}
    _f2, _ = _eval_cases(_a2, verbose=False)
    _out.append(("M2 引擎口徑整批未補入", _f2 > 0, f"轉紅 {_f2} 條"))
    _a3 = {k: {**v, "off": set()} for k, v in allowed.items()}
    _f3, _ = _eval_cases(_a3, verbose=False)
    _out.append(("M3 有號偏移 off 集合被清空", _f3 > 0, f"轉紅 {_f3} 條"))
    return _out


def _drift_check(allowed: dict) -> list[str]:
    """自測現算的引擎集合必須是守門 allowed 的子集。

    兩邊各有一套選檔／解析邏輯（自測不 import 生產路徑的私有函式以免耦合），
    一旦漂移，自測會放行守門其實會擋的值 → 只有這裡能提早看到。
    """
    _bad: list[str] = []
    for _lab, _spec in _live_engine().items():
        _a = allowed.get(_lab) or {}
        for _k in ("pct", "off"):
            _miss = [v for v in _spec.get(_k, set()) if round(float(v), 1) not in (_a.get(_k) or set())]
            if _miss:
                _bad.append(f"{_lab}.{_k} 缺 {sorted(_miss)}")
    return _bad


def main() -> int:
    snap = C._load(BASE / "snapshot.json") or {}
    allowed = C.build_allowed(snap)
    fails, _n = _eval_cases(allowed)
    # ── 警示自測：合成引擎檔 → 確認「整列缺列／部分欄位改名」會出聲、正常檔不出聲 ──
    for note, files, expect_warn, absent, present in WARN_CASES:
        got, msg, al = _warn_check(files)
        ok = (got == expect_warn) and (absent is None or absent not in al) \
            and (present is None or present in al)
        if not ok:
            fails += 1
        _why = "" if ok else f" | 出聲={got}（期望 {expect_warn}）" + \
            (f"｜{absent} 仍在 allowed" if (absent and absent in al) else "") + \
            (f"｜{present} 不在 allowed（該檔口徑應生效）" if (present and present not in al) else "")
        print(f"{'PASS' if ok else 'FAIL'} | {'應出聲' if expect_warn else '不應出聲'} | 警示 | {note}"
              + (f" | {msg.splitlines()[0][:70]}" if msg else "") + _why)

    # ── 覆蓋率下限（2026-10-23）：案例因「讀不到引擎檔」整批消失時，自測會變少但全綠
    #    （＝假綠）。下限讓「覆蓋率下降」本身變紅燈，而不是等哪天真的誤擋才發現。
    _struct = 0
    _n_total = len(CASES)
    _n_engine = len(_engine_cases())
    if _n_total < MIN_CASES:
        _struct += 1
        print(f"FAIL | 覆蓋率下限 | 案例數 {_n_total} < 下限 {MIN_CASES}"
              f"（引擎檔讀不到？_engine_cases 回空？）")
    if _n_engine < MIN_ENGINE_CASES:
        _struct += 1
        print(f"FAIL | 引擎覆蓋下限 | 引擎案例 {_n_engine} 條 < 下限 {MIN_ENGINE_CASES}"
              f"（引擎口徑整批消失＝守門失去覆蓋但看起來全綠）")

    # ── 漂移檢查：自測現算的引擎集合必須都在守門 allowed 內 ──
    _drift = _drift_check(allowed)
    if _drift:
        _struct += 1
        print(f"FAIL | 口徑漂移 | 自測與守門不同步：{'；'.join(_drift[:4])}")

    # ── 變異測試：把守門弄壞，自測必須轉紅（證明有偵測力）──
    _mut = _mutation_checks(allowed)
    for _mnote, _mok, _mwhy in _mut:
        if not _mok:
            fails += 1
        print(f"{'PASS' if _mok else 'FAIL'} | 變異測試 | {_mnote} | {_mwhy}")

    # 印 gap（現況缺口）／off（引擎偏移）／pct 三集合：口徑拆分後 gap 不再含引擎值，
    # 只看 gap 會誤以為引擎口徑消失了（收工稽核第 13 類讀的就是這一行）。
    _total = len(CASES) + len(WARN_CASES) + len(_mut)
    print(f"--- 內文守門自測：{_total - fails}/{_total} 通過"
          f"｜債券 gap={sorted(allowed['債券']['gap'])} off={sorted(allowed['債券']['off'])}"
          f" pct={sorted(allowed['債券']['pct'])}")
    if fails or _struct:
        print(f"❌ 自測未過 → 守門本身有問題，先修守門再談內文"
              f"（案例失敗 {fails}｜結構檢查失敗 {_struct}）")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
