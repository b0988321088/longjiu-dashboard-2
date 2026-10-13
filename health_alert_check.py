#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""health_alert_check.py — 健康度紅線監控（2026-09-05 建立；2026-10-10 A 案修正）

每日 09:10 cron（no_agent）執行：算健康度五維度，只有「惡化／越線」才輸出（→ TG），
平穩時空輸出（靜默）。state 檔記上次狀態避免每天重複吵。

── 2026-10-10 A 案（使用者裁決 APPROVE：限施工與驗收，不含提交/推送/發布）──
本次只修正「政策／計分／推播」三層不一致中的**推播層**。

🔴 立即行動（真值缺口／融資風險；維持原判準，未變動）
     LTV > 50（口徑1 借/擔保品）｜現金 < 現金底線｜覆蓋率 < 100%｜防禦維度 < 40%

🟡 持續觀察（本次修正重點）
     美元曝險 ≥ 黃色門檻 → 🟡 觀察提示
     美元曝險 ≥ 高曝險觀察線 → 🟡 觀察提示（文案升級，**仍不升級為紅色危機**）
     60%（目標值）本身**不是紅線**，不觸發任何提示
     advisory_only 語意：只產生觀察提示，不觸發交易、不觸發危機紅燈

     門檻單一來源＝thresholds_2026_0915.美元曝險_pct，讀取入口 usd_advisory.policy()
     （2026-10-07 裁決②③）。來源缺失或無效 → 明確報「資料異常」，
     **不靜默套用任何舊門檻／預設值**。

❌ 已移除：「健康分數 < 60」警報
     依據 2026-10-02 裁示「取消 B 級與健康度分數敘事」——分數本身不再是推播觸發條件。
     （標題仍印當日分數供總覽，但不再作為觸發依據。）

⚠️ 同型觀察項（本次**刻意未動**，留待 B 案審查）
     `FLOOR_FALLBACK` 現金底線仍寫死 700000，與 snapshot 現值等值故無行為差異；
     單一來源化屬 hardening，且屬「健康度計分政策」範圍（B 案 HOLD），故不動。
"""
import json
import sys
from pathlib import Path

REPO = Path(r"C:/Users/bot/Desktop/longjiu_system")
sys.path.insert(0, str(REPO))
import datetime  # noqa: E402

USD_SRC = "thresholds_2026_0915.美元曝險_pct"
FLOOR_FALLBACK = 700000  # 見檔頭「同型觀察項」：A 案不變更現金底線來源


def usd_thresholds(snap):
    """美元曝險三級門檻 (目標, 黃, 紅)；來源缺失或無效一律回 None。

    單一來源＝usd_advisory.policy()（2026-10-07 裁決②：唯一讀取入口，其他模組不得各自讀
    snapshot）。回 None 代表呼叫端**必須**報資料異常，不得套用任何預設值或舊門檻。
    """
    try:
        from usd_advisory import policy as _policy
        p = _policy(snap) or {}
    except Exception:
        return None
    g, y, r = p.get("目標"), p.get("黃"), p.get("紅")
    if any(v is None for v in (g, y, r)):
        return None
    try:
        g, y, r = float(g), float(y), float(r)
    except (TypeError, ValueError):
        return None
    if not (0 < g <= y <= r <= 100):
        return None
    return g, y, r


def classify(ltv, cash, floor, cov, defense, usd, th):
    """純函式：五維度 + 曝險門檻 → (red, observe, data_err) 三個 list[str]。

    抽出來是為了讓 A 案的驗收情境可被單元測試窮盡（不依賴 snapshot 現值）。
    任一維度缺真值（None）時該維度不判——原版以 `.get(k, 0)` 把缺值當 0，
    會讓「LTV 缺真值」靜默變成「不告警」，此處改為缺值即不判（fail-safe 顯示）。
    """
    red, observe, data_err = [], [], []

    if ltv is not None and ltv > 50:
        red.append(f"LTV {ltv:.1f}% > 50（銀行監看線）")
    if cash is not None and floor is not None and cash < floor:
        red.append(f"現金 {cash:,.0f} < 底線 {floor:,.0f}")
    if cov is not None and cov < 100:
        red.append(f"覆蓋率 {cov:.0f}% < 100%")
    if defense is not None and defense < 40:
        red.append(f"防禦維度 {defense:.1f}% < 40%")

    if th is None:
        data_err.append(
            f"美元曝險門檻來源缺失或無效（{USD_SRC}）"
            "→ 本次不套用任何舊門檻、不產生曝險提示"
        )
    elif usd is not None:
        _g, _y, _r = th
        if usd >= _r:
            observe.append(
                f"美元曝險 {usd:.1f}% ≥ 高曝險觀察線 {_r:.0f}%（僅顯示、不觸發資產調整）"
            )
        elif usd >= _y:
            observe.append(
                f"美元曝險 {usd:.1f}% 位於黃色觀察區 {_y:.0f}~{_r:.0f}%（僅顯示、不觸發資產調整）"
            )
        # usd < 黃：不觸發。60%（目標值）不是紅線，不產生任何提示。
    return red, observe, data_err


def main():
    snap = json.loads((REPO / "snapshot.json").read_text(encoding="utf-8"))
    try:
        from report_components import render_health_score
        d = render_health_score(snap)
    except Exception as e:
        print(f"⚠️ 健康度計算失敗: {e}")
        return
    state_p = REPO / "health_alert_state.json"
    try:
        last = json.loads(state_p.read_text(encoding="utf-8"))
    except Exception:
        last = {}
    now = datetime.date.today().isoformat()

    ltv = d.get("LTV")
    usd = d.get("曝險")
    cash = d.get("現金")
    cov = d.get("覆蓋")
    defense = d.get("防禦")
    score = d.get("分數")

    red, observe, data_err = classify(
        ltv=ltv, cash=cash, floor=FLOOR_FALLBACK, cov=cov, defense=defense,
        usd=usd, th=usd_thresholds(snap),
    )

    worsen = []
    ls = last.get("score")
    ll = last.get("light")
    if ls is not None and score is not None and score <= ls - 5:
        worsen.append(f"總分 {ls}→{score}（-{ls - score}）")
    if ll and ll != d.get("燈號") and (d.get("燈號") == "🔴" or (d.get("燈號") == "🟡" and ll == "🟢")):
        worsen.append(f"燈號 {ll}→{d.get('燈號')}")

    # 寫回 state（含平穩日，讓 baseline 推進）
    def _r(v, nd=1):
        return round(v, nd) if isinstance(v, (int, float)) else None
    state_p.write_text(json.dumps({
        "date": now, "score": score, "light": d.get("燈號"),
        "LTV": _r(ltv), "曝險": _r(usd), "現金": _r(cash, 0),
        "覆蓋": _r(cov, 0), "防禦": _r(defense),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    if red or observe or worsen or data_err:
        lines = [f"🩺 健康度提醒（{now}）：{score}/100 {d.get('燈號')}"]
        for a in red:
            lines.append(f"🔴 {a}")
        for a in observe:
            lines.append(f"🟡 {a}")
        for w in worsen:
            lines.append(f"⚠️ {w}")
        for e in data_err:
            lines.append(f"⚠️ {e}")

        def _fmt(v, nd=0, pct=True):
            if not isinstance(v, (int, float)):
                return "缺真值"
            return f"{v:,.{nd}f}" + ("%" if pct else "")

        lines.append(
            "明細：覆蓋 " + _fmt(cov) + " / 防禦 " + _fmt(defense, 1)
            + " / 曝險 " + _fmt(usd, 1) + " / 現金 " + _fmt(cash, 0, pct=False)
            + " / LTV " + _fmt(ltv, 1)
        )
        print("\n".join(lines))
    # 平穩 → 空輸出（no_agent 靜默）


if __name__ == "__main__":
    main()
