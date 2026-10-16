#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""結構健檢月報推播（每月 1 日）— no_agent，零 LLM。

stdout 即 Telegram 訊息本文（cron 直接投遞；空輸出＝不發送，本支固定有輸出）。

資料源與口徑**完全重用** build_structural_health.py（import 觸發它現產 HTML，
故報告連結永遠指向本輪最新檔），不在本檔重寫任何計算 —— 避免兩份口徑漂移。
"""
import contextlib
import io
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
PAGES = "https://b0988321088.github.io/longjiu-dashboard-2"


def fmt(v):
    if v is None:
        return "—"
    return f"{int(round(float(v))):,}"


def wan(v):
    if v is None:
        return "—"
    return f"{float(v) / 10000:,.1f}萬"


# ── 重用產生器的計算（它會順手把 HTML 重產，維持連結指向最新） ──
_buf = io.StringIO()
try:
    with contextlib.redirect_stdout(_buf):
        import build_structural_health as B
except Exception as e:  # noqa: BLE001
    print(f"⚠️ 結構健檢月報產生失敗：{type(e).__name__}: {str(e)[:160]}\n"
          f"（報告連結：{PAGES}/ ）")
    sys.exit(0)   # 不讓 cron 記 error；訊息本身即為告警

snap_date = str(B.snap.get("date") or B.TODAY)
url = f"{PAGES}/structural_health_{B.TODAY.replace('-', '')}.html"

# ── 燈號 ──
def _lvl(pct, cfg, invert=True):
    if pct is None:
        return "⚪"
    y, r = cfg.get("黃", 65), cfg.get("紅", 70)
    return "🔴" if pct >= r else ("🟡" if pct >= y else "🟢")


usd = B.usd
usd_lv = _lvl(usd, B.usd_cfg)
ltv_v = B.ltv.get("LTV_pct")
ltv_lv = "🔴" if (ltv_v or 0) > (B.ltv.get("追繳參考_pct") or 70) else (
    "🟡" if (ltv_v or 0) > (B.ltv.get("政策停止線_pct") or 53) else "🟢")
gate_lv = "🔴" if B.gate.get("risk_warning") else "🟢"
debt_lv = "🟢" if B.high_cost_debt == 0 else "🔴"
cov_lv = "🟢" if (B.cov_cons or 0) >= 100 else "🔴"

L = []
L.append(f"🏥 財務結構健檢（每月檢核）")
L.append(f"資料快照 {snap_date}｜定錨 {B.BL['date']}（{B.BL.get('label','調整前')}）")
L.append("")
L.append(f"▸ 負債成本：加權 {B.wa_rate:.2f}%（定錨 {B.BL['weighted_debt_rate_pct']:.2f}%）")
L.append(f"▸ 高息負債：{fmt(B.high_cost_debt)} {debt_lv}（原 4.0%／3.92% 共 500 萬）")
L.append(f"▸ 資產配置：美股 {B.A['美股市值型']:.1f}%（目標 {B.T['美股市值型']:.0f}）"
         f"｜台股 {B.A['台股市值型']:.1f}%（{B.T['台股市值型']:.0f}）"
         f"｜債券 {B.A['債券']:.1f}%（{B.T['債券']:.0f}）"
         f"｜科技 {B.A['科技']:.1f}%（≤{B.T['科技']:.0f}）")
L.append(f"▸ 現金流覆蓋：{B.cov_cons:.1f}% {cov_lv}（常態 {B.cov_norm:.1f}%）"
         f"｜可動用 {wan(B.allowable)}・乾粉 {wan(B.dp_dry)}")
L.append(f"▸ 風險哨兵：美元曝險 {usd:.1f}% {usd_lv}｜質押 LTV {ltv_v:.2f}% {ltv_lv}"
         f"｜US30Y {B.gate.get('value')}% {gate_lv}")
L.append("")

_todo = [f for f in B.focus if str(f[1]) != "無待辦紅黃燈"]
if _todo:
    L.append(f"⚠️ 待處理 {len(_todo)} 項")
    for _ic, _t, _d in _todo[:4]:
        _short = _d.split("→")[0].strip()
        if len(_short) > 46:
            _short = _short[:45] + "…"
        L.append(f"• {_ic} {_t}：{_short}")
else:
    L.append("✅ 各項指標均在門檻內——維持現行紀律即可。")
L.append("")
L.append(f"📄 完整報告：{url}")
L.append("📌 今天 12:00 真值日，順手把四類截圖丟給龍九即可完成校正。")

print("\n".join(L))
