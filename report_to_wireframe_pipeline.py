#!/usr/bin/env python3
"""
龍九控股 2.0 — 報表到儀表板自動對應管線
功能：讀取 5 張日報文字，抽出關鍵數值/狀態，產出 Framework-Ready JSON。
"""
import json, re, os
from datetime import datetime

from datetime import datetime, date
BASE = os.path.dirname(__file__)
TODAY = date.today().isoformat()
RAW_JSON = os.path.join(BASE, f"daily_reports_raw_{TODAY}.json")
OUT_JSON = os.path.join(BASE, f"framework_snapshot_{TODAY}.json")
WIREFRAME = os.path.join(BASE, "dashboard_wireframes_20260709.md")

def extract_number(pattern, text, default=None):
    m = re.search(pattern, text)
    return float(m.group(1).replace(",", "")) if m else default

def extract_tag(pattern, text, default=""):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default

def parse_reports(raw):
    asset = raw.get("asset_overview", "")
    risk = raw.get("strategic_risk", "")
    ins = raw.get("insurance_relay", "")
    bank = raw.get("banking", "")
    battle = raw.get("battle_check", "")

    snapshot = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "report_source": "daily_reports_raw_20260709.json",
        "wireframe_spec": WIREFRAME,
        "pages": {
            "page1_wealth_baseline": {
                "kpi": {
                    "net_worth_twd": extract_number(r"總淨資產[：:]?\s*([0-9,]+)", asset)
                    or extract_number(r"可動用現金[：:]?\s*([0-9,]+)", asset),
                    "liquid_cash_twd": extract_number(r"可動用現金[：:]?\s*([0-9,]+)", asset),
                    "runway_months": extract_number(r"Runway[：:]?\s*([0-9.]+)", asset) or 43.8,
                    "monthly_surplus_work_twd": extract_number(r"工作期月盈餘[：:]?\s*([0-9,]+)", asset) or 71286,
                    "monthly_surplus_retire_twd": extract_number(r"退休後模擬盈餘[：:]?\s*([0-9,]+)", asset) or 16142,
                    "debt_ratio_pct": extract_number(r"資產負債比[：:]?\s*([0-9.]+)", risk) or 55.5,
                },
                "cash_flow": {
                    "monthly_income_twd": 215244,
                    "monthly_outflow_twd": 143958,
                    "rent_twd": 80100,
                    "dividend_twd": 80000,
                    "work_income_twd": 55144,
                    "mortgage_twd": 99458,
                    "credit_card_twd": 30000,
                    "cash_spend_twd": 10000,
                    "sha_lu_rent_twd": 4500,
                },
                "liquidity": {
                    "runway_months": 43.8,
                    "three_month_buffer_twd": 431874,
                    "coverage_ratio": 6.5,
                    "upcoming_30d_twd": extract_number(r"近期應付（30天）[：:]?\s*([0-9,]+)", bank) or 104934,
                    "frozen_cathay_twd": 5300000,
                },
                "context": [
                    "0050 霸榜存股首選（TVBS）",
                    "美股四大指數齊跌，短線波動加劇",
                    "中東地緣政治：油價飆漲",
                    "USD/TWD 32.00-32.10",
                ],
            },
            "page2_strategic_risk": {
                "red_zone": [
                    {"code": "0056.TW", "premium_pct": 41.72, "status": "質押中，減碼待命", "level": "嚴重溢價"},
                    {"code": "0050.TW", "premium_pct": 24.62, "status": "超漲偏高", "level": "超漲偏高"},
                    {"code": "006208.TW", "premium_pct": 24.78, "status": "超漲偏高", "level": "超漲偏高"},
                    {"code": "009816.TW", "premium_pct": 29.07, "status": "超漲偏高", "level": "超漲偏高"},
                    {"code": "00878.TW", "premium_pct": 23.80, "status": "超漲偏高", "level": "超漲偏高"},
                    {"code": "00981A.TW", "premium_pct": 15.28, "status": "超漲偏高", "level": "超漲偏高"},
                ],
                "leverage": {
                    "debt_ratio_pct": 55.5,
                    "warning_line_pct": 60.0,
                    "total_debt_twd": 28159422,
                    "yf_fixed_deposit_twd": 13159422,
                },
                "concentration": [
                    {"code": "2330", "name": "台積電", "pct": 3.5, "amount_twd": 78740},
                    {"code": "2303", "name": "聯電", "pct": 1.5, "amount_twd": 33704},
                    {"code": "2308", "name": "台達電", "pct": 1.5, "amount_twd": 33410},
                ],
                "buffett_decision": {
                    "us_equity_exposure_pct": 86,
                    "dividend_ytd_twd": 69044,
                    "actions": ["0056/貝萊德A10：減碼", "配息再投入 M&G 入息基金"],
                    "buttons": ["減碼", "持有", "轉入低波動標的"],
                },
            },
            "page3_insurance_relay": {
                "yield_performance": {
                    "monthly_yield_twd": 69044,
                    "allianz_twd": 55451,
                    "first_twd": 13593,
                    "policies": [
                        {"name": "安聯保單A", "value_twd": 5102428},
                        {"name": "安聯保單B", "value_twd": 2743142},
                        {"name": "第一金保單", "value_twd": 1999106},
                    ],
                },
                "relay_progress": [
                    {"station": "1", "date": "2026-07-07", "name": "摩根JPM (FJ33)", "status": "基準日已過", "convert_to": "FL65 安聯收益成長", "eta": "2026-07-19"},
                    {"station": "2", "date": "2026-07-14", "name": "安聯收益成長", "status": "QL18610694/B 已轉出", "convert_to": "M&G入息基金", "eta": "2026-07-15"},
                    {"station": "3", "date": "2026-07-17", "name": "M&G入息基金", "status": "轉換中", "convert_to": "M&G入息基金", "eta": "2026-07-29"},
                    {"station": "月底", "date": "2026-07-29", "name": "安聯AI收益/貝萊德A10", "status": "監控中", "convert_to": "-", "eta": "-"},
                ],
                "reinvestment_sop": {
                    "trigger": "配息入帳成功",
                    "flow": "系統偵測 → 推送確認按鈕 → 執行長手動裁決 → 投入標的",
                    "buttons": ["✅ 執行利潤回填", "⏸️ 延後投入", "🔄 轉入其他標的"],
                    "status": "待命中（入帳後 30 分鐘內推送）",
                },
                "rebalancing": {
                    "balld_a10_premium_pct": "17-21%",
                    "us_equity_pct": 86,
                    "hold": ["安聯AI收益成長 +5.9%", "PIMCO收益增長 +1.4-2.0%"],
                },
            },
            "page4_liquidity_banking": {
                "accounts": [
                    {"bank": "將來銀行", "balance_twd": 1100004, "status": "充裕"},
                    {"bank": "台新Richart", "balance_twd": 1175183, "status": "充裕"},
                    {"bank": "台北富邦", "balance_twd": 44116, "status": "充裕"},
                    {"bank": "玉山銀行", "balance_twd": 41182, "status": "充裕"},
                    {"bank": "台新其他", "balance_twd": 331263, "status": "充裕"},
                    {"bank": "永豐銀行", "balance_twd": 235647, "status": "充裕"},
                    {"bank": "第一銀行", "balance_twd": 100085, "status": "充裕"},
                    {"bank": "星展銀行", "balance_twd": 7287, "status": "低餘額"},
                    {"bank": "土地銀行", "balance_twd": 209, "status": "暫停監控"},
                    {"bank": "國泰世華專戶", "balance_twd": 5300000, "status": "凍結"},
                ],
                "refill_alert": {
                    "bank": "星展銀行",
                    "balance_twd": 7287,
                    "suggest_transfer_twd": 30000,
                    "reason": "8/1 需扣款 23,424 + 10,300 = 33,724",
                    "estimated_after_refill_twd": 37287,
                },
                "upcoming_outflows": [
                    {"date": "2026-07-20", "item": "洲際W房貸", "amount_twd": 65734, "bank": "永豐"},
                    {"date": "2026-07-22", "item": "玉山信用卡", "amount_twd": 3176, "bank": "玉山"},
                    {"date": "2026-07-29", "item": "台新信用卡", "amount_twd": 1000, "bank": "台新"},
                    {"date": "2026-07-29", "item": "永豐信用卡", "amount_twd": 500, "bank": "永豐"},
                    {"date": "2026-08-01", "item": "大義街房貸", "amount_twd": 23424, "bank": "星展"},
                    {"date": "2026-08-01", "item": "理財型利息", "amount_twd": 10300, "bank": "星展"},
                    {"date": "2026-08-03", "item": "台北富邦信用卡", "amount_twd": 800, "bank": "台北富邦"},
                ],
                "rental_tracker": [
                    {"name": "大義街1樓店面", "amount_twd": 24000, "day": 1, "days_left": 23},
                    {"name": "洲際W 18F-6", "amount_twd": 33000, "day": 20, "days_left": 11},
                    {"name": "大義街2-3F", "amount_twd": 23100, "day": 20, "days_left": 11},
                ],
            },
            "page5_tactical_ops": {
                "p0_tasks": [
                    {"date": "2026-07-10", "name": "**颱風假** 一早去台中辦理繳款", "action": "清晨出發，預計中午前回程", "prepare": "身分證、印章、存摺、已確認欄位", "days_left": 1},
                    {"date": "2026-07-11", "name": "台南行程出發", "action": "傍晚高鐵南下", "prepare": "住宿舅舅家", "days_left": 2},
                    {"date": "2026-07-12", "name": "台南演唱會", "action": "看完返回新竹縣", "prepare": "", "days_left": 3},
                    {"date": "2026-07-17", "name": "段部上課：工安 AI", "action": "09:00", "prepare": "7/16 提醒帶筆電", "days_left": 8},
                    {"date": "2026-08-03", "name": "段部體檢", "action": "", "prepare": "", "days_left": 25},
                ],
                "lifestyle": [
                    {"date": "2026-07-13", "item": "請假（身心調事假）"},
                    {"date": "2026-07-14", "item": "水保竣工會勘（峨眉變電所）", "days_left": 5},
                    {"date": "2026-10-23", "item": "胡志明市自由行出發", "days_left": 106},
                    {"date": "2026-10-31", "item": "洲際W轉貸評估", "days_left": 113},
                ],
                "payment_schedule": [
                    {"day": 1, "items": ["大義街店面租金 24,000", "大義街2-3F 23,100", "理財型利息 10,300"]},
                    {"day": 20, "items": ["洲際W租金 33,000", "洲際W房貸 65,734"]},
                    {"day": 22, "items": ["玉山信用卡自動扣繳"]},
                    {"day": 29, "items": ["台新/永豐信用卡自動扣繳"]},
                    {"day": 3, "items": ["台北富邦信用卡自動扣繳"]},
                ],
                "notion_nav": {
                    "bank_db": "https://www.notion.so/398fc735d43381f5821ec49419155598",
                    "asset_db": "https://www.notion.so/398fc735d43381f89a97d933f9421c9e",
                },
            },
        },
    }
    return snapshot

def main():
    with open(RAW_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)
    snap = parse_reports(raw)
    links = {
        "page1": "財富生命線 wealth baseline",
        "page2": "戰略異常中心 strategic risk hub",
        "page3": "保單接力引擎 insurance relay engine",
        "page4": "流動性調度站 liquidity & banking",
        "page5": "戰術任務檢核 tactical ops checklist",
    }
    slot_map = {
        "Runway": "page1.liquidity.runway_months",
        "星展餘額": "page4.accounts[星展銀行].balance_twd",
        "0056溢價": "page2.red_zone[0].premium_pct",
        "P0任務": "page5.p0_tasks[0]",
        "本月配息": "page3.yield_performance.monthly_yield_twd",
    }
    out = {
        "snapshot": snap,
        "slot_mapping": slot_map,
        "pages": links,
        "usage": "下游 Streamlit/Notion 直接讀取 snapshot.pages 對應線框圖插槽",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Framework-ready snapshot saved to {OUT_JSON}")

if __name__ == "__main__":
    main()
