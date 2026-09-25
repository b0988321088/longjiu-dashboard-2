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
    # ── 引擎口徑（2026-09-25 新增補洞）──
    ("債券 +5pp", True, "引擎戰術偏移（燈號偏移後 − 目標）"),
    ("美股 -8pp", True, "引擎戰術偏移（負向）"),
    ("美股 8pp", True, "引擎戰術偏移（內文寫成減碼幅度）"),
    ("債券 30%", True, "引擎偏移後目標值"),
    ("美股 22%", True, "引擎偏移後目標值"),
    ("債券 +9pp", False, "負向：不存在的偏移"),
    ("美股 12%", False, "負向：不存在的目標值"),
    # ── 引擎偏移 vs 現況缺口的口徑分流（2026-09-25 B 批）──
    ("偏移後債券 +5pp", True, "引擎偏移口徑（偏移後＝+5）"),
    ("偏移後債券 -5pp", False, "負向：引擎是加碼 +5，寫成減碼 → 擋"),
    ("超標：美股 +9.5pp", True, "現況缺口口徑（超標＝+9.5）"),
    ("超標：美股 -9.5pp", False, "負向：超標必為正缺口，寫成負 → 擋"),
    ("美股超標 9.5pp、債券 +5pp", True, "切段：鄰句『超標』不得污染債券的引擎值"),
    # ── 獨立複審抓到的兩條迴歸（2026-09-25，固定下來不再退化）──
    ("美股超標 9pp 但債券 +5pp", True, "回歸 V-A2：無標點的整數 pp 鄰句不得污染口徑"),
    ("偏移後科技 5pp", False, "回歸 V-B：口徑為引擎偏移但該標籤 off 為空 → 退回聯集擋下，不得靜默跳過"),
    # ── 避險衛星覆蓋（2026-09-25 B 批；修前這些標籤根本不存在＝從未被掃）──
    ("衛星 7%", True, "避險衛星合計偏移後目標"),
    ("避險衛星 7%", True, "同上（長標籤寫法）"),
    ("衛星 5%", False, "負向：非衛星列任何口徑的值"),
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
    ("債券 +3.7pp", True, "現況缺口（佔總資產分母）"),
    ("債券 +4.7pp", True, "現況缺口（佔投資部位分母）"),
    ("科技 15.3%", True, "穿透真值"),
    ("防守型配息 17.3%", True, "穿透真值"),
    ("科技 17.5%", False, "負向：INC-245 原始案例（模型自行推算）"),
    # ── 現金派生口徑（INC-244）──
    ("現金 861,818", True, "現金原值"),
    ("現金 161,818", True, "乾粉＝現金 − 生活底線"),
    ("現金 1,200,000", True, "合計底線"),
    ("現金 999,999", False, "負向：不存在的現金金額"),
    # ── 守門不該掃的型態（零假陽性合約）──
    ("高科技/半導體 17.5%", True, "複合詞不掃（刻意不比）"),
    ("防守合併 68.5%", True, "中介詞句子不掃"),
    ("科技目標 ≤20%", True, "中介詞句子不掃"),
]

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


def main() -> int:
    snap = C._load(BASE / "snapshot.json") or {}
    allowed = C.build_allowed(snap)
    fails = 0
    for text, expect_pass, note in CASES:
        hits = C.scan_text(text, allowed, "SELFTEST")
        ok = (not hits) == expect_pass
        if not ok:
            fails += 1
        print(f"{'PASS' if ok else 'FAIL'} | {'應放行' if expect_pass else '應擋下'} | {text} | {note}"
              + ("" if ok else f" | hits={hits}"))
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

    # 印 gap（現況缺口）／off（引擎偏移）／pct 三集合：口徑拆分後 gap 不再含引擎值，
    # 只看 gap 會誤以為引擎口徑消失了（收工稽核第 13 類讀的就是這一行）。
    _total = len(CASES) + len(WARN_CASES)
    print(f"--- 內文守門自測：{_total - fails}/{_total} 通過"
          f"｜債券 gap={sorted(allowed['債券']['gap'])} off={sorted(allowed['債券']['off'])}"
          f" pct={sorted(allowed['債券']['pct'])}")
    if fails:
        print("❌ 自測未過 → 守門本身有問題，先修守門再談內文")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
