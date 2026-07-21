"""週報自動產生 — 從 INC 錯誤登記 + dashboard_decisions 自動生成"""
import json, os
from datetime import date, timedelta
from pathlib import Path

LJ = Path(os.path.expanduser("~/Desktop/龍九系統"))
TODAY = date.today()
MONDAY = TODAY - timedelta(days=TODAY.weekday())
WEEK_LABEL = f"{MONDAY} ~ {TODAY}"

def load_inc_errors() -> list:
    """從 error_register.md 解析本週 INC"""
    p = Path.home() / "AppData/Local/hermes/skills/software-development/longjiu-error-register/references/error_register.md"
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    incs = []
    current = {}
    for line in text.split("\n"):
        if line.startswith("## INC-"):
            if current:
                incs.append(current)
            current = {"id": line.split("## ")[1].strip()}
        elif line.strip().startswith("| **日期** |"):
            d = line.split("|")[2].strip()
            current["date"] = d
        elif line.strip().startswith("| **描述** |"):
            current["desc"] = line.split("|")[2].strip()[:80]
        elif line.strip().startswith("| **severity** |"):
            current["severity"] = line.split("|")[2].strip()
        elif line.strip().startswith("| **status** |"):
            current["status"] = line.split("|")[2].strip()
    if current:
        incs.append(current)
    return incs

def load_decisions() -> list:
    p = LJ / "dashboard_decisions.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    week_start = MONDAY.isoformat()
    return [x for x in d.get("decisions", []) if x.get("approved_at", "")[:10] >= week_start]

def weekly_report() -> str:
    incs = load_inc_errors()
    decs = load_decisions()
    
    report = f"📋 **龍九週報 {WEEK_LABEL}**\n\n"
    
    report += f"**✅ 本週核准：{len(decs)} 項**\n"
    for d in decs[-10:]:
        t = d.get("text", d.get("id", ""))[:60]
        report += f"  • {t}\n"
    
    report += f"\n**🔧 本週錯誤修復：{len(incs)} 筆**\n"
    p0 = [i for i in incs if i.get("severity") == "P0"]
    p1 = [i for i in incs if i.get("severity") == "P1"]
    if p0:
        report += f"  🔴 P0: {len(p0)} 筆\n"
        for i in p0[:3]:
            report += f"    • {i.get('id','')}: {i.get('desc','')[:50]}\n"
    if p1:
        report += f"  🟡 P1: {len(p1)} 筆\n"
        for i in p1[:3]:
            report += f"    • {i.get('id','')}: {i.get('desc','')[:50]}\n"
    
    # 待修
    open_items = [i for i in incs if i.get("status") == "open"]
    if open_items:
        report += f"\n**⚠️ 待修項目：{len(open_items)} 筆**\n"
        for i in open_items:
            report += f"  • {i.get('id','')}: {i.get('desc','')[:50]}\n"
    
    return report

if __name__ == "__main__":
    print(weekly_report())
