import os
import json
import csv
import re
from pathlib import Path
from datetime import datetime

# Load env
project_env = Path(__file__).resolve().parents[1] / ".env"
hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
for p in [project_env, hermes_env]:
    if p.exists():
        os.environ["DOTENV"] = str(p)
        break

from dotenv import load_dotenv
load_dotenv(os.environ.get("DOTENV", ""))

NOTION_API_KEY = os.getenv("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

REPO = Path(__file__).resolve().parents[0]
DB_MAP = json.loads((REPO / "notion_db_ids.json").read_text(encoding="utf-8"))
TODAY = datetime.now().strftime("%Y-%m-%d")


def ns_get(path: str) -> dict:
    import requests
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


def ns_post(path: str, payload: dict, method: str = "") -> dict:
    import requests
    # PATCH for updates, POST for queries/creates
    if method == "PATCH" or "/pages/" in path and "?" not in path:
        r = requests.patch(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=60)
    else:
        r = requests.post(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=60)
    if r.status_code >= 400:
        print(f"HTTP {r.status_code} response: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def to_num(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        v = v.replace(",", "").strip()
        try:
            return float(v)
        except ValueError:
            return None
    return None


def fmt_num(v):
    if v is None:
        return "0"
    if isinstance(v, float) and v == int(v):
        return f"{int(v):,}"
    return f"{v:,.2f}"


class NotionIngester:
    def __init__(self, dry_run=False):
        self.dry = dry_run

    def _find_existing_page(self, db_id: str, title_prop: str, title_value: str, date_value: str = "") -> dict | None:
        """查詢同一 DB 內是否有同名 page，供 upsert 使用（以 title 比對即可）。"""
        if self.dry:
            return None
        payload = {
            "filter": {
                "property": title_prop,
                "title": {"contains": title_value},
            },
            "page_size": 1,
        }
        try:
            data = ns_post(f"/databases/{db_id}/query", payload)
            pages = data.get("results", [])
            return pages[0] if pages else None
        except Exception:
            return None

    def _update(self, page_id: str, props: dict) -> dict | None:
        if self.dry:
            return {"id": page_id, "archived": False}
        payload = {"properties": props}
        return ns_post(f"/pages/{page_id}", payload, method="PATCH")

    def _create_or_update(self, db_id: str, props: dict, markdown: str = "", date_value: str = TODAY):
        title_map = ["資產名稱", "項目", "Name", "事件名稱", "基金名稱", "保單名稱"]
        title_prop = next((k for k in title_map if k in props), "")
        title_value = ""
        if title_prop in props:
            try:
                title_value = props[title_prop]["title"][0]["text"]["content"]
            except Exception:
                pass
        existing = self._find_existing_page(db_id, title_prop, title_value, date_value)
        if existing:
            return self._update(existing["id"], props)
        payload = {"parent": {"database_id": db_id}, "properties": props}
        if markdown:
            payload["markdown"] = markdown
        return ns_post("/pages", payload)

    def ingest_master_ledger(self, snapshot: dict):
        db_id = DB_MAP["master_ledger"]
        rows = []
        asset_map = {
            "保單現值": snapshot.get("insurance_total"),
            "台股市值": snapshot.get("securities_total"),
            "基金市值": snapshot.get("funds_total"),
            "流動資產": snapshot.get("liquid_assets"),
        }
        for name, value in asset_map.items():
            if value is not None:
                rows.append({
                    "資產名稱": {"title": [{"text": {"content": f"{name}（snapshot）"}}]},
                    "即時餘額": {"number": value},
                    "分類": {"select": {"name": "資產"}},
                    "SSoT來源": {"select": {"name": "snapshot.json"}},
                    "更新日期": {"date": {"start": TODAY}},
                })

        for bucket_name, bucket_val in [
            ("配息收入（保守估）", snapshot.get("dividend_income")),
            ("房租收入", snapshot.get("rent_income")),
            ("利息收入", snapshot.get("interest_income")),
            ("非獎金月收入", snapshot.get("non_bonus_income")),
            ("月支出", snapshot.get("monthly_expense")),
        ]:
            if bucket_val is not None:
                rows.append({
                    "資產名稱": {"title": [{"text": {"content": bucket_name}}]},
                    "即時餘額": {"number": bucket_val},
                    "分類": {"select": {"name": "現金流"}},
                    "SSoT來源": {"select": {"name": "snapshot.json"}},
                    "更新日期": {"date": {"start": TODAY}},
                })

        # 銀行資產（Moneybook 真值）
        bank_assets = snapshot.get("bank_assets_moneybook")
        if bank_assets is not None:
            rows.append({
                "資產名稱": {"title": [{"text": {"content": "銀行資產（Moneybook 正數）"}}]},
                "即時餘額": {"number": bank_assets},
                "分類": {"select": {"name": "資產"}},
                "SSoT來源": {"select": {"name": "Moneybook_帳戶"}},
                "更新日期": {"date": {"start": TODAY}},
                "備註": {"rich_text": [{"text": {"content": snapshot.get("bank_assets_memo", "")}}]},
            })

        for row in rows:
            self._create_or_update(db_id, row)

    def ingest_fund_station(self, funds: list[dict]):
        db_id = DB_MAP["fund_station"]
        for f in funds:
            props = {
                "基金名稱": {"title": [{"text": {"content": f.get("name", "未命名")}}]},
                "持有單位": {"number": f.get("units")},
                "淨值": {"number": f.get("nav")},
                "配息頻率": {"select": {"name": f.get("frequency", "月配")}},
                "除息日": {"date": {"start": f.get("ex_date", TODAY)}},
                "下次配息日": {"date": {"start": f.get("next_payout", TODAY)}},
                "基金公司": {"rich_text": [{"text": {"content": f.get("company", "")}}]},
            }
            self._create_or_update(db_id, props)

    def ingest_policy_vault(self, policies: list[dict], db_asset_id: str, db_cashflow_id: str):
        for p in policies:
            asset_val = p.get("surrender_value")
            if asset_val is not None:
                self._create_or_update(db_asset_id, {
                    "資產名稱": {"title": [{"text": {"content": p.get("name", "保單")}}]},
                    "即時餘額": {"number": asset_val},
                    "分類": {"select": {"name": "保單"}},
                    "SSoT來源": {"select": {"name": "Company_Ledger"}},
                    "成本基準": {"number": p.get("cost_basis")},
                    "更新日期": {"date": {"start": TODAY}},
                })
            monthly_payout = p.get("monthly_payout")
            if monthly_payout is not None:
                self._create_or_update(db_cashflow_id, {
                    "項目": {"title": [{"text": {"content": f"{p.get('name')} 配息"}}]},
                    "金額": {"number": monthly_payout},
                    "類型": {"select": {"name": "保單配息"}},
                    "方向": {"select": {"name": "收入"}},
                    "日期": {"date": {"start": TODAY}},
                    "狀態": {"status": {"name": "進行中"}},
                })

    def ingest_collateral_hub(self, loans: list[dict]):
        db_id = DB_MAP["debt_cashflow"]
        for loan in loans:
            props = {
                "項目": {"title": [{"text": {"content": loan.get("name", "貸款")}}]},
                "金額": {"number": abs(loan.get("balance", 0))},
                "類型": {"select": {"name": "貸款"}},
                "方向": {"select": {"name": "負債" if loan.get("active", True) else "清償"}},
                "日期": {"date": {"start": TODAY}},
                "狀態": {"status": {"name": "進行中" if loan.get("active") else "已完成"}},
                "備註": {"rich_text": [{"text": {"content": loan.get("memo", "")}}]},
            }
            self._create_or_update(db_id, props)

    def ingest_ops_logs(self, events: list[dict]):
        db_id = DB_MAP["ops_logs"]
        for ev in events:
            props = {
                "事件名稱": {"title": [{"text": {"content": ev.get("name", "未命名")}}]},
                "來源系統": {"select": {"name": ev.get("source", "Hermes")}},
                "執行狀態": {"select": {"name": ev.get("status", "待處理")}},
                "事件分類": {"select": {"name": ev.get("category", "未分類")}},
                "CIO摘要": {"rich_text": [{"text": {"content": ev.get("summary", "")}}]},
            }
            link = (ev.get("link") or "").strip()
            if link:
                props["關聯頁面"] = {"url": link}
            self._create_or_update(db_id, props)

    def ingest_asset_investment(self, assets):
        db_id = DB_MAP.get("asset_investment")
        if not db_id:
            return
        # asset_investment DB schema 只有 Name 欄位
        for asset in assets:
            if isinstance(asset, dict):
                name = asset.get("name", "")
            else:
                name = str(asset)
            if not name:
                continue
            props = {"Name": {"title": [{"text": {"content": name}}]}}
            self._create_or_update(db_id, props)


def load_snapshot():
    snapshot_path = REPO / "snapshot.json"
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    return {}


def load_moneybook_accounts():
    account_paths = [
        Path("C:/Users/bot/AppData/Local/hermes/cache/documents") / "doc_7f2cdffd6ca1_Moneybook_帳戶_20260714_1.csv",
        REPO / "Moneybook" / "account.csv",  # fallback
    ]
    for p in account_paths:
        if p.exists():
            break
    else:
        return None, ""
    bank_assets = 0.0
    details = []
    with open(p, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            currency = row.get("幣別", "").strip()
            amt = float(row.get("帳戶金額", "0") or "0")
            account_name = row.get("帳戶名稱", "")
            if currency == "TWD" and amt > 0 and "信用卡" not in account_name:
                bank_assets += amt
                details.append((row.get("機構名稱"), account_name, amt))
    return bank_assets, details


def load_moneybook_details():
    detail_paths = [
        Path("C:/Users/bot/AppData/Local/hermes/cache/documents") / "doc_4e6c8d47a6db_Moneybook_明細_20260714_1.csv",
        REPO / "Moneybook" / "detail.csv",
    ]
    for p in detail_paths:
        if p.exists():
            break
    else:
        return 0, 0
    fund_keywords = ['基金', 'ETF', '00981', '00919', '00918', '00713', '摩根', '貝萊德', '聯博', '施羅德', '路博邁']
    policy_keywords = ['安聯', '第一金人壽']
    policy_div = 0.0
    etf_div = 0.0
    seen = set()
    with open(p, encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            post_date = row.get("入帳日", "")
            if not post_date.startswith("2026/07"):
                continue
            desc = row.get("明細描述", "")
            cat = row.get("分類", "")
            currency = row.get("幣別", "").strip()
            amt = float(row.get("金額", "0") or "0")
            if currency != "TWD" or amt <= 0:
                continue
            is_fund = any(k in desc for k in fund_keywords) or "媒體轉入 - 基金配息" in desc
            is_policy = any(k in desc for k in policy_keywords) or "保單配息" in cat
            key = (desc, amt)
            if key in seen:
                continue
            seen.add(key)
            if is_fund:
                etf_div += amt
            if is_policy and not is_fund and ("轉帳存入" in desc or "保單配息" in cat):
                policy_div += amt
    return policy_div, etf_div


def parse_ledger_loans():
    ledger_path = REPO / "Company_Ledger.md"
    if not ledger_path.exists():
        return []
    text = ledger_path.read_text(encoding="utf-8")
    loans = []
    # Extract 負債 sections via regex or markdown table scanning
    # We'll hardcode known entries from the ledger as per user rules
    loans = [
        {
            "name": "星展房貸（大義街）- 一般+理財型",
            "balance": 8_800_000,
            "active": True,
            "memo": "一般房貸4.8M+理財型4.0M；轉貸中（7/17面簽）",
        },
        {
            "name": "永豐房貸（洲際W）",
            "balance": 6_000_000,
            "active": True,
            "memo": "永豐銀行房貸",
        },
        {
            "name": "永豐週轉金",
            "balance": 7_000_000,
            "active": True,
            "memo": "永豐銀行週轉金",
        },
        {
            "name": "凱基證券質押借款",
            "balance": 1_000_000,
            "active": True,
            "memo": "證券質押凍結額度100萬",
        },
        {
            "name": "保單質押借款",
            "balance": 4_000_000,
            "active": True,
            "memo": "第一金/安聯保單質押",
        },
    ]
    return loans


def load_daily_report_cio():
    report_path = REPO / f"daily_report_v2_{TODAY}.md"
    if not report_path.exists():
        return "今日日報未找到，無 CIO 摘要。"
    text = report_path.read_text(encoding="utf-8")
    # Extract key CIO-related items for summary
    lines = text.splitlines()
    summary_parts = []
    for line in lines:
        if "CIO" in line or "M&G" in line or "MCP" in line or "Railway" in line or "0050" in line or "配息" in line:
            summary_parts.append(line.strip())
    if not summary_parts:
        return "今日日報未發現明確 CIO 摘要。"
    return " | ".join(summary_parts[:10])


def default_funds(snapshot):
    funds_total = snapshot.get("funds_total") or snapshot.get("fund_market_value") or 0
    funds = []
    if funds_total <= 0:
        return []
    # Split into representative funds if list known, else single aggregated entry
    funds.append({
        "name": "總基金持倉（快照）",
        "units": 1,
        "nav": funds_total,
        "frequency": "月配",
        "ex_date": TODAY,
        "next_payout": TODAY,
        "company": "混合",
    })
    return funds


def default_policies(snapshot):
    # Use actual policy names from snapshot + ledger
    policies = []
    anl_a = snapshot.get("ANL_A") or snapshot.get("allianz_ab_current_value") or 0
    anl_b = snapshot.get("ANL_B") or snapshot.get("firstjin_fl65_current_value") or 0
    fj33 = snapshot.get("FIRST_GOLD") or snapshot.get("firstjin_current_value") or 0
    if anl_a:
        policies.append({
            "name": "安聯保單 A（QL186）",
            "surrender_value": anl_a,
            "cost_basis": 5_000_000,
            "monthly_payout": snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("配息_保守估_月均", 0) / 2,  # approximate split
        })
    if anl_b:
        policies.append({
            "name": "安聯保單 B（QL184）",
            "surrender_value": anl_b,
            "cost_basis": 3_000_000,
            "monthly_payout": snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("配息_保守估_月均", 0) / 2,
        })
    if fj33:
        policies.append({
            "name": "第一金保單 FL65",
            "surrender_value": fj33,
            "cost_basis": 2_000_000,
            "monthly_payout": snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("配息_保守估_月均", 0) / 3,
        })
    if not policies:
        policies.append({
            "name": "保單合併",
            "surrender_value": snapshot.get("insurance_total"),
            "cost_basis": snapshot.get("insurance_total"),
            "monthly_payout": snapshot.get("dividend_income"),
        })
    return policies


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只顯示將寫入的資料，不呼叫 Notion API")
    args = parser.parse_args()

    snapshot = load_snapshot()
    ingester = NotionIngester(dry_run=args.dry_run)

    print("=== Notion Ingest Start ===")
    print(f"snapshot keys: {list(snapshot.keys())[:10]}...")

    # Compute Moneybook true values
    bank_assets, account_details = load_moneybook_accounts()
    if bank_assets is None:
        bank_assets = snapshot.get("moneybook_total", 0)

    policy_div, etf_div = load_moneybook_details()

    # Override snapshot fields with computed true values
    snapshot["bank_assets_moneybook"] = bank_assets
    snapshot["bank_assets_memo"] = f"正數TWD帳戶合計 {bank_assets:,.0f}"
    snapshot["dividend_income"] = snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("配息_保守估_月均", policy_div + etf_div)
    snapshot["rent_income"] = snapshot.get("rent_monthly_actual")
    snapshot["interest_income"] = snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("利息收入")
    snapshot["non_bonus_income"] = snapshot.get("monthly_income")
    snapshot["monthly_expense"] = snapshot.get("monthly_expense")

    income = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("income", {})
    expense = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("expense", {})
    moneybook = {
        "dividend_income": snapshot["dividend_income"],
        "rent_income": snapshot.get("rent_monthly_actual"),
        "interest_income": income.get("利息收入"),
        "non_bonus_income": snapshot.get("monthly_income"),
        "monthly_expense": snapshot.get("monthly_expense"),
    }

    print(f"真值：銀行資產(正數TWD)={bank_assets:,.0f}")
    print(f"真值：保單配息(7月)={policy_div:,.0f}，ETF/基金配息(7月)={etf_div:,.0f}")
    print(f"真值：配息收入(採用)={snapshot['dividend_income']:,.0f}")
    print(f"真值：房租收入={snapshot.get('rent_monthly_actual',0):,.0f}")
    print(f"真值：利息收入={snapshot.get('interest_income',0):,.0f}")
    print(f"真值：月支出={snapshot.get('monthly_expense',0):,.0f}")

    # Anomaly checks
    if bank_assets < 0:
        print("⚠️ 警告：銀行資產為負數！")
    if snapshot["dividend_income"] == 0:
        print("⚠️ 警告：配息收入為 0！")
    diff = abs(bank_assets - snapshot.get("moneybook_total", 0))
    if diff > 2000:
        print(f"⚠️ 警告：Moneybook 正數合計與 snapshot.moneybook_total 差異 {diff:,.0f}")

    ingester.ingest_master_ledger({**snapshot, **moneybook})
    ingester.ingest_fund_station(default_funds(snapshot))
    ingester.ingest_policy_vault(default_policies(snapshot), DB_MAP["master_ledger"], DB_MAP["debt_cashflow"])
    ingester.ingest_collateral_hub(parse_ledger_loans())
    cio_summary = load_daily_report_cio()
    ingester.ingest_ops_logs([
        {
            "name": f"notion_ingest daily + CIO Summary {TODAY}",
            "source": "Hermes",
            "status": "完成",
            "category": "同步",
            "summary": cio_summary,
            "link": f"daily_report_v2_{TODAY}.md",
        }
    ])
    asset_names = [
        "凱基證券 台股持倉",
        "安聯人壽 QL184",
        "安聯人壽 QL186",
        "第一金 壽險保單",
        "鉅亨基金 持倉",
        "將來銀行 Digital Savings",
        "第一銀行 iLEO",
        "星展銀行 活期儲蓄",
        "Moneybook 流動現金",
        "房租收入（大義街1樓）",
        "台電薪水（月）",
    ]
    ingester.ingest_asset_investment(asset_names)
    print("=== Notion Ingest Done ===")


if __name__ == "__main__":
    main()
