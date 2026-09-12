#!/usr/bin/env python3
"""市場指標燈號面板（DAA v3｜2026-08-21 定版）— 日報 + 週報共用。
資料來自 macro_regime.py（load_latest：讀今日 JSON 或即時執行）：
主觸發：US30Y(即時) / 巴菲特 / VIX / CPI（後三者無源不觸發）
情境評分：科技重新定價 / 確定收益輪動 / 美元信用壓力 / 地緣風險
輸出：targetAllocation 數字 + 板塊輪動 + 質押比例 + 執行紀律
"""
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
import macro_regime  # 同目錄


def _score_light(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 70:
        return "🔴"
    if v >= 50:
        return "🟡"
    return "🟢"


def build_panel(snap: dict | None = None) -> str:
    """產出市場指標燈號面板 HTML（DAA v3）"""
    s = snap or json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
    r = macro_regime.load_latest()
    light = r["燈號"]
    main = r["主觸發"]
    aux = r["輔助因子"]
    reg = r["情境評分"]

    # 質押比例（2026-09-12：改讀 snapshot.cathay_pledge_0911 現行口徑；原讀 8/20 舊計畫 700萬/350萬 → 顯示過時）
    _cp = s.get("cathay_pledge_0911", {}) or {}
    _cp_pool = _cp.get("擔保池", {}) or {}
    pledge_amt = f"{(_cp.get('可貸金額') or 0)/10000:.0f}萬" if _cp.get("可貸金額") else "—"
    def _short(k):
        for _k2 in ("富達", "聯博", "貝萊德", "安聯", "第一金"):
            if _k2 in k:
                return _k2
        return k.split("-")[0][:4]
    collateral = (f"擔保池 {(_cp.get('額度_本金') or 0)/10000:.0f}萬"
                  f"（{'+'.join(_short(k) for k in _cp_pool if k != '合計')}）"
                  f"× {_cp.get('成數','—')}") if _cp else "—"
    ltv_now = round((_cp.get("可貸金額") or 0) / (_cp_pool.get("合計") or 1) * 100, 1) if _cp else 0
    ltv_light = "🟢 ≤53%"
    if ltv_now:
        ltv_light = "🟢" if ltv_now <= 53 else ("🟡" if ltv_now <= 58 else "🔴")

    # 美元曝險（2026-09-12：上限改讀 snapshot.usd_exposure_monitor.threshold = 60，原寫死 50/55）
    usd = (s.get("usd_exposure_monitor", {}) or {}).get("current", {}) or {}
    usd_pct = usd.get("合計", 0)
    _usd_cap = float((s.get("usd_exposure_monitor", {}) or {}).get("threshold") or 60)
    usd_light = "🔴" if usd_pct > _usd_cap else ("🟡" if usd_pct > _usd_cap - 5 else "🟢")
    _usd_txt = f"{usd_pct:.1f}% {usd_light}（上限 {_usd_cap:.0f}%）"

    # 科技穿透曝險（2026-09-12：目標 15%→20% 由 snapshot 讀；原寫死 → 顏色誤標）
    _tech_pct = ((s.get("penetration", {}) or {}).get("actual_pct", {}) or {}).get("美股市值型成長_科技")
    _tech_cap = float(((s.get("penetration", {}) or {}).get("targets", {}) or {}).get("科技曝險目標") or 20)
    _tech_txt = (f"{_tech_pct}% {'🟢' if _tech_pct <= _tech_cap else '🟡' if _tech_pct <= _tech_cap + 5 else '🔴'}"
                 f"（目標 ≤{_tech_cap:.0f}%）") if _tech_pct is not None else "—"
    _pt_tw = ((s.get("penetration", {}) or {}).get("targets", {}) or {}).get("台股市值型目標", 10)

    # targetAllocation 壓縮顯示
    alloc = r.get("targetAllocation", {}).get("rows", [])
    alloc_txt = " ｜ ".join(
        f"{row['資產']} {row['燈號偏移後'] if row['燈號偏移後'] is not None else row['建議金額(±)']}"
        for row in alloc
    )
    tilt = r.get("板塊輪動", [])
    tilt_txt = "；".join(f"{t['方向']} {t['偏移']}（{t['金額']:,}元）" for t in tilt)
    em = r.get("緊急應變")
    if em:
        em_light = "🔴" if em["應變分"] >= 70 else ("🟡" if em["應變分"] >= 50 else "🟢")
        em_txt = (f"⑧ 緊急應變：{em['source']}｜{em['generated_at']}｜應變分 {em['應變分']} {em_light}"
                  f"｜命中 {em['風險關鍵詞'][:4]}｜{em['建議節錄'][:70]}")
        if em["逾3日僅參考"]:
            em_txt += "（逾3日僅參考）"
    else:
        em_txt = "⑧ 緊急應變：—"

    rows = []
    rows.append(
        f"<div class='callout' style='margin-top:12px;border-left:3px solid "
        f"{'#22c55e' if '綠' in light else ('#f59e0b' if '黃' in light else '#ef4444')}'>"
    )
    rows.append(f"<h3>🚦 市場指標燈號面板（DAA v3｜2026-08-21 定版）｜目前：{light}</h3>")
    rows.append("<div style='font-size:12.5px;line-height:1.9'>")
    rows.append(
        f"<strong>① 主觸發：</strong>US30Y {main['US30Y']:.2f}% ｜ VIX {main['VIX']:.1f} ｜ "
        f"巴菲特 —｜CPI —（後三者待數據源，不觸發）<br/>"
    )
    rows.append(
        f"<strong>② 情境評分：</strong>科技重新定價 {reg['科技重新定價']['score']} {_score_light(reg['科技重新定價']['score'])} ｜ "
        f"確定收益輪動 {reg['確定收益輪動']['score']} {_score_light(reg['確定收益輪動']['score'])} ｜ "
        f"美元信用壓力 {reg['美元信用壓力']['score']} {_score_light(reg['美元信用壓力']['score'])} ｜ "
        f"地緣風險 {reg['地緣風險']['score']} {_score_light(reg['地緣風險']['score'])}<br/>"
    )
    rows.append(
        f"<strong>③ 輔助觀察：</strong>USD/TWD {aux['USD/TWD']:.2f} ｜ XAU {aux['XAU黃金']:.0f} "
        f"(20日{aux['黃金20日%']:+.1f}%) ｜ WTI {aux['WTI原油']:.1f} (20日{aux['WTI20日%']:+.1f}%) ｜ "
        f"GPR {'—' if aux['GPR地緣指數'] is None else aux['GPR地緣指數']} ｜ 席勒PE {aux['席勒PE']} ｜ "
        f"科技穿透 {_tech_txt} ｜ 美元曝險 {_usd_txt}<br/>"
    )
    rows.append(
        f"<strong>④ targetAllocation：</strong>{alloc_txt}<br/>"
    )
    rows.append(f"<strong>⑤ 板塊輪動：</strong>{tilt_txt}<br/>")
    rows.append(f"{em_txt}<br/>")
    rows.append(
        f"<strong>⑥ 質押比例：</strong>{collateral}｜可貸 {pledge_amt}｜LTV {ltv_now}% {ltv_light}｜"
        f"壓力情境：富達-30%＋聯博-20% → LTV 70% 💥<br/>"
    )
    rows.append(
        f"<strong>⑦ 執行紀律：</strong>動態偏移 ≤±10%｜±5pp 再平衡閾值｜週六正式評估｜"
        f"個人硬性約束 &gt; 市場訊號（台股≤{_pt_tw}%／質押≤{round((_cp.get('可貸金額') or 0)/(_cp.get('額度_本金') or 1)*100)}%／PI 執行案照舊／現金底線70萬／美元只控新增）"
    )
    rows.append("</div></div>")
    return "\n".join(rows)


if __name__ == "__main__":
    print(build_panel())
