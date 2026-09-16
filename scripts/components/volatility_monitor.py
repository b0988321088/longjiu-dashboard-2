import json, io
from pathlib import Path
from datetime import date
BASE = Path(__file__).parent.resolve()
SNAPSHOT = BASE / "snapshot.json"
def get_asset_diff_history():
    try:
        return json.load(io.open(BASE / "asset_diff_history.json", encoding="utf-8"))
    except Exception: return {}
def inv(r): return (r.get("securities_market",0) or 0)+(r.get("fund_market",0) or 0)+(r.get("insurance_current",0) or 0)
def make_volatility_report() -> str:
    d=get_asset_diff_history()
    if not d: return "<p class='text-xs text-slate-400'>⚠️ 無歷史資產差異資料</p>"
    R={r["date"]:r for r in d.values()}
    today=date.today().isoformat()
    cur=R.get(today)
    if not cur: return "<p class='text-xs text-slate-400'>⚠️ 今日無資產快照，無法計算波動</p>"
    report_parts=[]
    report_parts.append(f"<h4 class=\"text-md font-bold text-white\">📊 投資波動損失檢視（{today}）</h4>")
    report_parts.append("<div class='grid grid-cols-1 md:grid-cols-2 gap-4'>")

    periods = {
        "近2交易日": "2026-09-14",
        "近6交易日": "2026-09-08",
        "近15交易日": "2026-09-01",
        "近30交易日": "2026-08-17",
    }
    monthly_dividend = json.load(io.open(SNAPSHOT, encoding="utf-8")).get("monthly_dividend", 109687)

    for label, d0 in periods.items():
        prev_data = R.get(d0)
        if not prev_data: continue

        delta_total = cur["total_assets"] - prev_data["total_assets"]
        delta_invest = inv(cur) - inv(prev_data)
        delta_pct_total = (delta_total / prev_data["total_assets"]) * 100
        delta_pct_invest = (delta_invest / inv(prev_data)) * 100

        report_parts.append(f"<div class='bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2'>")
        report_parts.append(f"<span class='text-xs font-bold text-red-400'>{label}</span>")
        report_parts.append(f"<ul class='text-xs text-slate-300 space-y-1.5 list-disc pl-4'>")
        report_parts.append(f"<li>總資產 {delta_total:+, .0f} TWD ({delta_pct_total:+.2f}%)</li>")
        report_parts.append(f"<li>投資部位 {delta_invest:+, .0f} TWD ({delta_pct_invest:+.2f}%)</li>")
        if monthly_dividend > 0:
            report_parts.append(f"<li>約 {abs(delta_invest) / monthly_dividend:.1f} 個月配息</li>")
        report_parts.append(f"</ul>")
        report_parts.append(f"</div>")
    report_parts.append("</div>")

    # 最壞情境
    report_parts.append(f"<div class='luxury-card p-6 space-y-4'>")
    report_parts.append(f"<h4 class=\"text-md font-bold text-white\">🚨 最壞情境模擬：市場再跌 5%</h4>")
    report_parts.append(f"<ul class='text-xs text-slate-300 space-y-1.5 list-disc pl-4'>")
    report_parts.append(f"<li>總投資部位預估損失：{inv(cur) * 0.05:,.0f} TWD</li>")
    report_parts.append(f"<li>其中保單資產預估損失：{cur.get('insurance_current',0) * 0.05:,.0f} TWD</li>")
    report_parts.append(f"</ul>")
    report_parts.append(f"</div>")

    return "\n".join(report_parts)
