"""每日費用監控 — 查 DeepSeek 餘額 + 估算剩餘天數"""
import json, csv, os, subprocess, sys
from datetime import date, datetime
from pathlib import Path
from logging_config import get_logger
logger = get_logger("cost_monitor")

ENV = Path(os.path.expanduser("~/AppData/Local/hermes/.env"))
LJ = Path(os.path.expanduser("~/Desktop/longjiu_system"))
LOG = LJ / "cost_log.csv"
TODAY = str(date.today())

# 已知固定支出
MONTHLY_FIXED = {
    "Notion": 12.0,  # USD/月
}
# Gemini API 月費（從 Google AI Studio 手動查）
GEMINI_MONTHLY_COST_TWD = 80.58  # 2026-06-24~07-21
GEMINI_BALANCE_TWD = 315  # 2026-07-21 截圖餘額
GEMINI_TOPUP_DATE = "2026-07-08"  # 上次儲值 NT$400

def get_deepseek_balance() -> float | None:
    api_key = ""
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "DEEPSEEK_API_KEY" in line:
                api_key = line.split("=",1)[1].strip()
    if not api_key:
        return None
    try:
        # 2026-09-03 修正：cron 環境無 requests → 改 stdlib urllib（09:00 假警報 0.00 CNY 根因）
        import urllib.request
        req = urllib.request.Request("https://api.deepseek.com/user/balance",
            headers={"Authorization": f"Bearer {api_key}"})
        d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode())
        for bi in d["balance_infos"]:
            if bi["currency"] == "CNY":
                return float(bi["total_balance"])
        return 0.0
    except Exception:
        return None

def load_history() -> list:
    if LOG.exists():
        with open(LOG, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    return []

def save_entry(balance: float, daily_cost: float):
    history = load_history()
    today_exists = any(r.get("date") == TODAY for r in history)
    if today_exists:
        return  # 當天已記錄
    
    with open(LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not LOG.exists() or os.path.getsize(LOG) == 0:
            w.writerow(["date", "balance_cny", "daily_cost_cny", "note"])
        w.writerow([TODAY, f"{balance:.2f}", f"{daily_cost:.2f}", ""])

def estimate_days(balance: float, history: list) -> int:
    """根據近7天平均日耗估算剩餘天數"""
    recent = [float(r["daily_cost_cny"]) for r in history[-7:] if float(r["daily_cost_cny"]) > 0]
    if not recent:
        return 999
    avg = sum(recent) / len(recent)
    if avg <= 0:
        return 999
    return int(balance / avg)

# === 主流程 ===
balance = get_deepseek_balance()
if balance is None:
    # 2026-09-03：查詢失敗（無 key/無網路/API 錯誤）→ 保留上次記錄、不寫 0/999，避免假警報
    print("⚠️ DeepSeek 餘額查詢失敗（略過本次，保留上次記錄）")
    sys.exit(0)
history = load_history()

# 計算今日花費
prev_balance = float(history[-1]["balance_cny"]) if history else balance
daily_cost = max(prev_balance - balance, 0) if history else 0
# 2026-08-27：--no-log 模式（晨間批次用）只更新 daily_analysis.json，不寫 cost_log，
# 讓 09:00 ds_balance_alert 獨佔記錄時點（避免記錄時點漂移導致日耗歸因失準）
NO_LOG = "--no-log" in sys.argv
if not NO_LOG:
    save_entry(balance, daily_cost)

# 輸出報告
report = f"📊 **AI費用日報 {TODAY}**\n\n"
report += f"DeepSeek 餘額：**{balance:.2f} CNY**（約 {balance*4.2:.0f} 台幣）\n"
if daily_cost > 0:
    report += f"今日花費：**{daily_cost:.2f} CNY**（約 {daily_cost*4.2:.0f} 台幣）\n"
else:
    report += f"今日花費：無\n"

remaining = estimate_days(balance, history)
if remaining < 30:
    report += f"⚠️ 預估剩餘：**{remaining} 天**（低於30天，建議近期儲值）\n"
elif remaining < 90:
    report += f"📅 預估剩餘：**{remaining} 天**（約 {remaining//30} 個月）\n"
else:
    report += f"📅 預估剩餘：**{remaining} 天**（充足）\n"

report += f"\n歷史記錄：{len(history)} 天\n"
if history:
    week_total = sum(float(r["daily_cost_cny"]) for r in history[-7:] if float(r["daily_cost_cny"]) > 0)
    report += f"近7日總花費：{week_total:.2f} CNY\n"

# 每月固定支出
report += f"\n---\n📋 **每月固定支出：**\n"
for name, cost in MONTHLY_FIXED.items():
    report += f"  {name}: ${cost:.0f} USD/月（約 {cost*32:.0f} 台幣）\n"
report += f"  Gemini API: NT${GEMINI_MONTHLY_COST_TWD:.0f}/月（約 {GEMINI_MONTHLY_COST_TWD/32:.1f} USD）\n"

_total_twd = sum(MONTHLY_FIXED.values())*32 + GEMINI_MONTHLY_COST_TWD
report += f"\n🔮 **總月費估計：** ~{_total_twd:.0f} 台幣/月\n"
report += f"  （Notion ${MONTHLY_FIXED['Notion']:.0f} + Gemini NT${GEMINI_MONTHLY_COST_TWD:.0f} + DeepSeek流量）\n"

print(report)

# 寫入 daily_analysis.json 供日報使用
try:
    da = json.loads((LJ / "daily_analysis.json").read_text()) if (LJ / "daily_analysis.json").exists() else {}
    da["deepseek_cost"] = {"balance": balance, "daily_cost": daily_cost, "estimated_days": remaining}
    (LJ / "daily_analysis.json").write_text(json.dumps(da, ensure_ascii=False, indent=2))
except: pass