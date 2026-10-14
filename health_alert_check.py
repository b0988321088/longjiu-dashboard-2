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


def classify(ltv, cash, floor, cov, defense, usd, th, pools=None, ltv_grades=None):
    """純函式：五維度 + 曝險門檻 + 質押池 LTV → (red, observe, data_err) 三個 list[str]。

    抽出來是為了讓 A 案的驗收情境可被單元測試窮盡（不依賴 snapshot 現值）。
    任一維度缺真值（None）時該維度不判——原版以 `.get(k, 0)` 把缺值當 0，
    會讓「LTV 缺真值」靜默變成「不告警」，此處改為缺值即不判（fail-safe 顯示）。

    2026-10-14 第 0 批 R1（使用者裁決）：
      - **LTV 紅線門檻改讀 ltv_grades**（thresholds_2026_0915.ltv分級_pct.單池上限），
        禁硬編碼 50；門檻不可得 → 報資料異常且不判（**不得默認綠燈**）。
      - `ltv` 參數語意＝**單池最差 LTV**（由 sot_targets.pledge_pools 逐池取得），
        不再傳稀釋後的全體質押率（原口徑把分母含保單＋證券 → 銀行監看線永遠不觸發）。
      - `pools`＝sot_targets.pledge_pools() 結果：**各池分別判定**，不得以加總平均取代。
    """
    red, observe, data_err = [], [], []

    _cap = None
    if isinstance(ltv_grades, dict):
        _cap = ltv_grades.get("單池上限")
        if not isinstance(_cap, (int, float)):
            _cap = None
    if ltv is not None:
        if _cap is None:
            data_err.append(
                "LTV 門檻來源缺失或無效（thresholds_2026_0915.ltv分級_pct.單池上限）"
                "→ 本次不判 LTV（不得默認綠燈）"
            )
        elif ltv > _cap:
            red.append(f"LTV {ltv:.1f}% > 單池上限 {_cap:g}%（銀行監看線）")

    # 質押池逐池判定（各池分別判定；不得以加總平均或取平均取代）
    for _p in (pools or []):
        _nm = _p.get("池名") or "質押池"
        _g, _v = _p.get("分級"), _p.get("ltv_pct")
        if _g == "追繳":
            red.append(f"{_nm} LTV {_v}% ≥ 追繳線（契約層級重大風險）")
        elif _g == "禁新增質押":
            red.append(f"{_nm} LTV {_v}% ≥ 黃上限（禁止新增質押）")
        elif _g == "超限":
            red.append(f"{_nm} LTV {_v}% > 單池上限（已超核定成數）")
        elif _g == "未定義區間":
            observe.append(f"{_nm} LTV {_v}% 介於綠上限與單池上限之間"
                           "（門檻未定義動作，僅顯示）")
        elif _g == "unverified" and (_p.get("借款_twd") or 0) > 0:
            data_err.append(f"{_nm} 無法判定 LTV（{_p.get('說明') or '真值不足'}）")

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

    ltv = d.get("LTV")          # 稀釋後全體質押率：僅供顯示，不參與紅線判定
    usd = d.get("曝險")
    cash = d.get("現金")
    cov = d.get("覆蓋")
    defense = d.get("防禦")
    score = d.get("分數")

    # 質押池逐池 LTV（2026-10-14 第 0 批 R1）：門檻讀 SoT、各池分別判定、fail-closed
    try:
        import sot_targets as _st
        pools = _st.pledge_pools(snap)
        ltv_grades_d = _st.ltv_grades(snap)
    except Exception as e:      # 取不到 → 不得默認綠燈；交由 classify 報資料異常
        pools, ltv_grades_d = [], {}
        print(f"⚠️ 質押池 LTV 計算失敗（{type(e).__name__}: {e}）→ 本次不判 LTV",
              file=sys.stderr)
    _judged = [p["ltv_pct"] for p in pools
               if p.get("ltv_pct") is not None and p.get("分級") != "無借款"]
    ltv_single = max(_judged) if _judged else None

    red, observe, data_err = classify(
        ltv=None, cash=cash, floor=FLOOR_FALLBACK, cov=cov, defense=defense,
        usd=usd, th=usd_thresholds(snap), pools=pools, ltv_grades=ltv_grades_d,
    )
    # ltv 參數傳 None＝判定唯一來源改為 pools（逐池）；若仍傳單池概值，
    # 同一池會被概值與逐池各報一次（重複推播）。ltv 參數保留供無 pools 明細時使用。

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
        "LTV": _r(ltv), "LTV單池最差": _r(ltv_single, 2), "曝險": _r(usd),
        "現金": _r(cash, 0), "覆蓋": _r(cov, 0), "防禦": _r(defense),
        "質押池": [{"池名": p.get("池名"), "LTV": p.get("ltv_pct"),
                    "分級": p.get("分級"), "真值": p.get("真值")} for p in pools],
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
