import json, io
from pathlib import Path
from datetime import date, timedelta
# 2026-09-16: Adjust BASE to point to the root of the longjiu_system directory
# Assuming scripts are run from the longjiu_system directory
BASE = Path(".").resolve()
SNAPSHOT = BASE / "snapshot.json"
def get_asset_diff_history():
    history_path = BASE / "asset_diff_history.json"
    print(f"[DEBUG] volatility_monitor: Attempting to read asset_diff_history from {history_path}")
    try:
        content = io.open(history_path, encoding="utf-8").read()
        print(f"[DEBUG] volatility_monitor: Raw content length {len(content)}")
        data = json.loads(content)
        print(f"[DEBUG] volatility_monitor: Parsed data keys {list(data.keys())[:5]}")
        return data
    except Exception as e:
        print(f"[DEBUG] volatility_monitor: Error reading asset_diff_history from {history_path}: {e}")
        return {}
def inv(r): return (r.get("securities_market",0) or 0)+(r.get("fund_market",0) or 0)+(r.get("insurance_current",0) or 0)
def make_volatility_report() -> str:
    d=get_asset_diff_history()
    if not d: 
        print("[DEBUG] volatility_monitor: No asset diff history data after function call.")
        return "<p class='text-xs text-slate-400'>⚠️ 無歷史資產差異資料</p>"
    
    R={r["date"]:r for r in d.values()}
    today=date.today().isoformat()
    cur=R.get(today)
    
    print(f"[DEBUG] volatility_monitor: Today is {today}. Asset diff for today exists: {cur is not None}.")
    if not cur: return "<p class='text-xs text-slate-400'>⚠️ 今日無資產快照，無法計算波動</p>"

    report_parts=[]
    report_parts.append(f"<h4 class=\"text-md font-bold text-white\">📊 投資波動損失檢視（{today}）</h4>")
    report_parts.append("<div class='grid grid-cols-1 md:grid-cols-2 gap-4'>")

    # 動態計算歷史日期
    all_dates = sorted([k for k in R.keys() if k <= today])
    periods_map = {
        "近2交易日": 2,
        "近6交易日": 6,
        "近15交易日": 15,
        "近30交易日": 30,
    }
    
    monthly_dividend_snapshot = json.load(io.open(SNAPSHOT, encoding="utf-8")).get("monthly_dividend")
    monthly_dividend = monthly_dividend_snapshot if monthly_dividend_snapshot is not None else 0 # 避免除以零

    for label, days_offset in periods_map.items():
        # 找到對應 `days_offset` 的日期
        # 從最新的日期開始往前數 `days_offset` 個交易日
        prev_date_idx = len(all_dates) - 1 - days_offset
        if prev_date_idx < 0: continue
        d0 = all_dates[prev_date_idx]

        prev_data = R.get(d0)
        if not prev_data: continue

        delta_total = cur["total_assets"] - prev_data["total_assets"]
        delta_invest = inv(cur) - inv(prev_data)
        # 避免除以零
        delta_pct_total = (delta_total / prev_data["total_assets"]) * 100 if prev_data["total_assets"] else 0
        delta_pct_invest = (delta_invest / inv(prev_data)) * 100 if inv(prev_data) else 0

        report_parts.append(f"<div class='bg-slate-900/40 p-4 rounded-xl border border-slate-800 space-y-2'>")
        report_parts.append(f"<span class='text-xs font-bold text-red-400'>{label}</span>")
        report_parts.append(f"<ul class='text-xs text-slate-300 space-y-1.5 list-disc pl-4'>")
        report_parts.append(f"<li>總資產 {delta_total:+,.0f} TWD ({delta_pct_total:+.2f}%)</li>") 
        report_parts.append(f"<li>投資部位 {delta_invest:+,.0f} TWD ({delta_pct_invest:+.2f}%)</li>") 
        if monthly_dividend > 0:
            report_parts.append(f"<li>約 {abs(delta_invest) / monthly_dividend:.1f} 個月配息</li>")
        else:
            report_parts.append(f"<li>月配息數據缺失或為零，無法計算相對波動</li>")
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
