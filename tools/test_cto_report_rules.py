#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/test_cto_report_rules.py — B1／R3 報告輸出規則守門（2026-10-15）

驗證行為（用**當日真實缺陷字串**當輸入）：
  C1 凍結禁令：原文字缺「不得加碼／承接額度凍結」→ 程式必須補回固定句（不得依賴 LLM）。
  C2 紅線配對：「科技桶 24.5% 逼近紅線 15%」主語混淆 → 改寫為程式真值配對
     「高科技 X%（紅線 15%）」；且「紅線 N%」的 N 必等於程式門檻（錯值被覆寫）。
  C3 ETF 標籤：「核心消費（XLV …）」→ 標籤改為 XLV 的真值「醫療」；同時提到
     金融/原物料等其他標籤時不得被誤改。
  C4 單一來源一致性：SECTOR_LABELS 必須等於 institutional_flow.py 的 SECTOR_ETFS
     （以 AST 讀取，禁止只靠人工同步）。

負向自測：每個規則都附「未修正樣本」，證明斷言確實抓得到缺陷。
全程離線（純函式，不呼叫模型、不讀寫 repo 檔）。
執行：python -X utf8 tools/test_cto_report_rules.py
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PASS = FAIL = 0


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


# 2026-10-15 實際報告字串（缺陷現場）
REAL_RISK = ("今日最大風險：SOX -4.30%、加權 -2.99%，科技桶 24.5% 逼近紅線 15%（高科技14.4%），"
             "且法人狂賣科技 -284M、台積電 -38M、市值型 -51M，動能全面轉弱。")
REAL_ACTION = ("建議動作：①美股逢彈減碼科技≤20萬/次，壓回 36.2%→30%。②防守合併 65.7% 已足，勿追。"
               "③乾粉優先核心消費（XLV 最強 +2.1pp），避開金融、原物料、不動產。④台股僅≤5萬。")


def main() -> int:
    m = _load("cto_probe", ROOT / "buffett_cto_analyzer.py")
    TECH_EXP, TECH_CAP = 14.4, 15.0

    # ---- C1 交易授權紀律 ---------------------------------------------------
    print("C1 交易授權紀律由程式強制（原文字缺 → 補回固定句；舊凍結句移除）")
    check("負向：原文字確實缺紀律", not any(mk in REAL_RISK for mk in m._BAN_MARKERS),
          str(m._BAN_MARKERS))
    _t, _fx = m._enforce_report_rules(REAL_RISK, tech_exp=TECH_EXP, tech_cap=TECH_CAP)
    check("補回交易授權句", "條件成立不等於交易授權" in _t and "未收到本人明確指令前不得買進" in _t, _t[-140:])
    check("修正清單有記錄", any("交易授權" in f for f in _fx), str(_fx))
    # 已有紀律時不得重複追加
    _t2, _fx2 = m._enforce_report_rules(
        "紀律提醒：台股分批進場條件已成立，但條件成立不等於交易授權；維持逐批下令，未收到本人明確指令前不得買進。",
        tech_exp=TECH_EXP, tech_cap=TECH_CAP)
    check("已有紀律時不重複追加", _t2.count("條件成立不等於交易授權") == 1, _t2)
    # 舊凍結句必須被替換，不能與新口徑並存
    _t3, _fx3 = m._enforce_report_rules(
        "紀律提醒：承接額度凍結未解前，不得加碼、不得新增部位。", tech_exp=TECH_EXP, tech_cap=TECH_CAP)
    check("舊凍結句被移除並改寫", "承接額度凍結未解前" not in _t3 and "條件成立不等於交易授權" in _t3, _t3)

    # ---- C2 紅線配對 -------------------------------------------------------
    print("C2 紅線數字與主語配對以程式真值為準")
    _t, _fx = m._enforce_report_rules(REAL_RISK, tech_exp=TECH_EXP, tech_cap=TECH_CAP)
    check("主語混淆被改寫（不再出現『科技桶 24.5% … 逼近紅線』）",
          "科技桶 24.5%" not in _t, _t[:120])
    check("改寫為程式配對『高科技 14.4%（紅線 15%）』", "高科技 14.4%（紅線 15%）" in _t, _t[:140])
    check("修正清單記錄主語混淆", any("主語混淆" in f for f in _fx), str(_fx))
    check("負向對照：錯的紅線數字必被覆寫",
          "紅線 30%" not in m._enforce_report_rules("高科技 20.0%（紅線 30%）", tech_exp=TECH_EXP,
                                                    tech_cap=TECH_CAP)[0])
    _fx_num = m._enforce_report_rules("高科技 14.4%（紅線 15%）", tech_exp=TECH_EXP,
                                      tech_cap=TECH_CAP)[1]
    check("正確紅線數字不被更動", not any(("紅線數字" in f or "主語混淆" in f) for f in _fx_num),
          str(_fx_num))

    # ---- C3 ETF 標籤 -------------------------------------------------------
    print("C3 ETF 標籤以 SECTOR_LABELS 真值為準")
    _t, _fx = m._enforce_report_rules(REAL_ACTION, tech_exp=TECH_EXP, tech_cap=TECH_CAP)
    check("XLV 標籤被改正為『醫療』", "醫療（XLV" in _t or "醫療(XLV" in _t, _t[:160])
    check("不再把 XLV 稱作核心消費", "核心消費（XLV" not in _t, _t[:160])
    check("修正清單記錄標籤改正", any("XLV" in f for f in _fx), str(_fx))
    check("負向對照：不誤改其他標籤（金融／原物料／不動產仍在）",
          all(w in _t for w in ("金融", "原物料", "不動產")), _t[:200])
    _fx_lb = m._enforce_report_rules("核心消費（XLP +1.0pp）", tech_exp=TECH_EXP,
                                     tech_cap=TECH_CAP)[1]
    check("正確標籤不被動（XLP＝核心消費）", not any("標籤" in f for f in _fx_lb), str(_fx_lb))

    # ---- C4 單一來源一致性 -------------------------------------------------
    print("C4 SECTOR_LABELS 必須等於 institutional_flow.SECTOR_ETFS")
    src = (ROOT / "institutional_flow.py").read_text(encoding="utf-8")
    found = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SECTOR_ETFS" for t in node.targets):
            found = ast.literal_eval(node.value)
    check("能以 AST 取得 institutional_flow.SECTOR_ETFS", isinstance(found, dict), str(type(found)))
    check("兩表完全一致", found == m.SECTOR_LABELS,
          f"差異：{ {k: (found.get(k), m.SECTOR_LABELS.get(k)) for k in set(found or {}) ^ set(m.SECTOR_LABELS) if (found or {}).get(k) != m.SECTOR_LABELS.get(k)} }")

    print("\n" + "=" * 54)
    print(f"測試結果：{PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
