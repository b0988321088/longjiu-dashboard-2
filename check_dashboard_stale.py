#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_dashboard_stale.py — 產出檔 index.html 的「舊值殘留」掃描（單一入口）

2026-09-30 改版（根因：字面黑名單跟不上真值變動）：
  ① 字面清單從程式碼搬到資料檔 `data/dashboard_stale_tokens.json`（active / retired），
     新增或退休只改資料，不必動程式。
  ② 命中「現行真值」時不再 FAIL：真值字面由 snapshot 派生（見 truth_tokens()），
     判定為「清單過時」→ 印 ⚠️ 並提示 `--retire-obsolete` 可自動退休。
     實踩：實收覆蓋率升到 144% 撞到舊字面「144%」→ sync_all 最後一步中止
     （值本身是活的顯示值，卻被當成殘留）。
  ③ `--retire-obsolete`：把「清單過時」的字面從 active 移到 retired（含日期/理由），
     寫回 JSON，idempotent。

判準（只排除「不渲染 / 已歸檔」的區塊，不放寬真正的顯示值與 JS 硬編碼）：
  HTML 註解 `<!-- -->`、JS 註解 `/* */`、`<details class="cio-old">` 歸檔區 → 排除；
  其餘照掃（**含 <script> 內 JS 陣列/fallback 硬編碼**）。

用法：python check_dashboard_stale.py [index.html] [--retire-obsolete]
退出碼：0 = 乾淨（含「清單過時」）；1 = 有真殘留（附落點與上下文）
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
TARGET = BASE / (ARGS[0] if ARGS else "index.html")
RETIRE = "--retire-obsolete" in sys.argv
TOKENS_FILE = BASE / "data" / "dashboard_stale_tokens.json"

# 資料檔缺失時的安全網（僅保底；實際清單以 data/dashboard_stale_tokens.json 為準）
DEFAULT_ACTIVE = [
    "35,583", "63,027", "2,723,839", "7,753,544", "88,507", "109,645",
    "143.9%", "144%", "199,960", "62,969", "5,103,722", "1,889,388", "11,499,725",
    "1,089,462", "5,917,259", "5,798,988", "3,735,174", "7,764,551", "14.3%", "-0.7pp",
    "799,612", "815,066", "20260821_1", "20260829_1", "772,607", "123,607", "27,738",
    "499,316", "458,343", "20,776", "6,960", "0 TWD（應收 2,100）",
    "753,388", "138,627", "243,434", "225,918",
]

RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RE_JS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
RE_CIO_OLD = re.compile(r'<details[^>]*class="cio-old".*?</details>', re.S)


def _load_tokens() -> dict:
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))
        except Exception as e:  # 壞檔不得讓檢查靜默變鬆
            print(f"⚠️ 讀取 {TOKENS_FILE.name} 失敗（改用內建清單）：{e}")
    return {"active": list(DEFAULT_ACTIVE), "retired": []}


def _opts(v: float):
    """同一個數值的常見顯示寫法（千分位／％）。"""
    outs = {f"{v:,.0f}", f"{v:.0f}", f"{v:,.1f}", f"{v:.1f}", str(round(v))}
    for f in ("{:.0f}%", "{:.1f}%", "{:,.1f}%"):
        try:
            outs.add(f.format(v))
        except Exception:
            pass
    return outs


def truth_tokens() -> set:
    """現行真值字面（由 snapshot 派生，非人工維護）→ 命中者屬「清單過時」。"""
    toks = set()
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    except Exception:
        return toks
    for k in ("insurance_total", "securities_total_market_value", "cash_total", "total_assets",
              "total_liabilities", "monthly_dividend_total", "dividend_month_actual",
              "securities_unrealized_pnl", "rent_monthly_total", "rent_monthly_actual"):
        v = snap.get(k)
        if isinstance(v, (int, float)) and v:
            toks |= _opts(float(v))
    rc = snap.get("restricted_cash") or {}
    for v in (rc.get("金額"), (snap.get("cash_layers") or {}).get("unrestricted_cash"),
              (snap.get("passive_income") or {}).get("monthly_expense")):
        if isinstance(v, (int, float)) and v:
            toks |= _opts(float(v))
    try:  # 覆蓋率／跑道等派生口徑（單一來源：passive_caliber）
        import passive_caliber
        sc = passive_caliber.scenarios(snap)
        for sec in ("con", "act"):
            if isinstance(sc.get(sec), dict):
                for key in ("coverage", "runway_days"):
                    v = sc[sec].get(key)
                    if isinstance(v, (int, float)) and v:
                        toks |= _opts(float(v))
        # 顯示層常見組合：配息（保守／常態／實收）× 租金（常態／實收）／月支出
        exp = float(sc.get("expense") or 0)
        if exp:
            for d in (sc.get("div_con"), sc.get("div_norm"), sc.get("div_act")):
                for r in (sc.get("rent_norm"), sc.get("rent_act")):
                    if isinstance(d, (int, float)) and isinstance(r, (int, float)):
                        toks |= _opts((float(d) + float(r)) / exp * 100.0)
    except Exception:
        pass
    return toks


def scannable(html: str) -> str:
    """回傳「需要比對的區塊」＝原文扣除不渲染／已歸檔區塊。"""
    out = RE_CIO_OLD.sub(" ", html)
    out = RE_JS_COMMENT.sub(" ", out)
    out = RE_HTML_COMMENT.sub(" ", out)
    return out


def scan(html: str, active: list):
    """回傳 (真殘留, 清單過時)，元素為 (值, 上下文)。"""
    text = scannable(html)
    truth = truth_tokens()
    real, obsolete = [], []
    for v in active:
        for m in re.finditer(re.escape(v), text):
            ctx = text[max(0, m.start() - 70):m.start() + 40].replace("\n", " ")
            (obsolete if v in truth else real).append((v, ctx))
    return real, obsolete


def retire(obsolete: list) -> int:
    data = _load_tokens()
    toks = sorted({v for v, _ in obsolete})
    if not toks:
        return 0
    moved = 0
    for t in toks:
        if t in data.get("active", []):
            data["active"].remove(t)
            data.setdefault("retired", []).append(
                {"token": t, "retired_at": str(date.today()),
                 "reason": "命中現行真值（由 snapshot 派生）→ 已非舊值"})
            moved += 1
    TOKENS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"🔧 已退休 {moved} 個字面 → {TOKENS_FILE.name}（active {len(data.get('active', []))}｜"
          f"retired {len(data.get('retired', []))}）")
    return moved


def main() -> int:
    if not TARGET.exists():
        print(f"❌ 找不到 {TARGET.name}")
        return 1
    data = _load_tokens()
    active = data.get("active") or list(DEFAULT_ACTIVE)
    real, obsolete = scan(TARGET.read_text(encoding="utf-8", errors="replace"), active)
    if obsolete:
        toks = ", ".join(sorted({v for v, _ in obsolete}))
        print(f"⚠️ 清單過時 {len(obsolete)} 處（{TARGET.name}）：{toks} — 這些字面已是現行真值，"
              f"不是殘留；建議 `python check_dashboard_stale.py --retire-obsolete` 退休")
    if real:
        print(f"❌ 儀表板殘留舊值 {len(real)} 處（{TARGET.name}）：")
        for v, ctx in real[:12]:
            print(f"   - {v} @ ...{ctx}...")
        if len(real) > 12:
            print(f"   …其餘 {len(real) - 12} 處省略")
        print("   ℹ️ 只掃『會被渲染的區塊』（HTML/JS 註解、cio-old 歸檔區已排除）— "
              "若此值確實是活的顯示值，修法是讓它讀 snapshot，不是加豁免。")
        return 1
    if obsolete and RETIRE:
        retire(obsolete)
        active = _load_tokens().get("active") or active
    print(f"✅ 儀表板無真殘留舊值（{TARGET.name}｜掃描 {len(scannable(TARGET.read_text(encoding='utf-8', errors='replace'))):,} 字元，"
          f"字面清單 {len(active)} 項｜排除註解與 cio-old 歸檔區）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
