import os
import json
from pathlib import Path
from datetime import datetime

# Load env from project-root first, fallback to Hermes app dir
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
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def ns_post(path: str, payload: dict) -> dict:
    import requests
    r = requests.post(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=30)
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

    def _create(self, db_id: str, props: dict, markdown: str = "") -> dict | None:
        if self.dry:
            print(f"[dry-run] create in {db_id[:8]}... -> {props.get('資產名稱', props.get('項目', '...'))}")
            return {"id": "dry-run"}
        payload = {"parent": {"database_id": db_id}, "properties": props}
        if markdown:
            payload["markdown"] = markdown
        return ns_post("/pages", payload)

    def ingest_master_ledger(self, snapshot: dict):
        db_id = DB_MAP["master_ledger"]
        rows = []
        # Asset core from snapshot
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

        # Cashflow buckets
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
        for row in rows:
            self._create(db_id, row)

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
            self._create(db_id, props)

    def ingest_policy_vault(self, policies: list[dict], db_asset_id: str, db_cashflow_id: str):
        # Policies live partly in Master Ledger and partly in Debt/Cashflow per user's 5-table design
        for p in policies:
            asset_val = p.get("surrender_value")
            if asset_val is not None:
                self._create(db_asset_id, {
                    "資產名稱": {"title": [{"text": {"content": p.get("name", "保單")}}]},
                    "即時餘額": {"number": asset_val},
                    "分類": {"select": {"name": "保單"}},
                    "SSoT來源": {"select": {"name": "snapshot.json"}},
                    "成本基準": {"number": p.get("cost_basis")},
                    "更新日期": {"date": {"start": TODAY}},
                })
            monthly_payout = p.get("monthly_payout")
            if monthly_payout is not None:
                self._create(db_cashflow_id, {
                    "項目": {"title": [{"text": {"content": f"{p.get('name')} 配息"}}]},
                    "金額": {"number": monthly_payout},
                    "類型": {"select": {"name": "保單配息"}},
                    "方向": {"select": {"name": "收入"}},
                    "日期": {"date": {"start": TODAY}},
                    "狀態": {"select": {"name": "active"}},
                })

    def ingest_collateral_hub(self, loans: list[dict]):
        db_id = DB_MAP["debt_cashflow"]
        for loan in loans:
            self._create(db_id, {
                "項目": {"title": [{"text": {"content": loan.get("name", "貸款")}}]},
                "金額": {"number": abs(loan.get("balance", 0))},
                "類型": {"select": {"name": "貸款"}},
                "方向": {"select": {"name": "負債"}},
                "日期": {"date": {"start": TODAY}},
                "狀態": {"status": {"name": "進行中" if loan.get("active") else "已完成"}},
                "備註": {"rich_text": [{"text": {"content": loan.get("memo", "")}}]},
            })

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
            self._create(db_id, props)



    def ingest_asset_investment(self, assets: list[str]):
        db_id = DB_MAP.get("asset_investment")
        if not db_id:
            return
        for name in assets:
            if not name:
                continue
            self._create(db_id, {
                "Name": {"title": [{"text": {"content": name}}]},
            })

def load_snapshot():
    snapshot_path = REPO / "snapshot.json"
    if snapshot_path.exists():
        return json.loads(snapshot_path.read_text(encoding="utf-8"))
    return {}


def default_funds():
    # Default fund station data derived from known sources.
    return [
        {"name": "00981A 台股 ETF", "units": 0, "nav": 0, "frequency": "季配", "ex_date": TODAY, "next_payout": TODAY, "company": "元大"},
        {"name": "00984A 台股 ETF", "units": 0, "nav": 0, "frequency": "月配", "ex_date": TODAY, "next_payout": TODAY, "company": "富邦"},
    ]


def default_policies(snapshot: dict):
    policies = []
    for key in ["insurance_total", "ANL_A", "ANL_B", "FIRST_GOLD"]:
        value = snapshot.get(key)
        if value is not None:
            policies.append({
                "name": key,
                "surrender_value": value,
                "cost_basis": value,
                "monthly_payout": snapshot.get("dividend_income"),
            })
    return policies or [{"name": "保碼合併", "surrender_value": snapshot.get("insurance_total"), "monthly_payout": snapshot.get("dividend_income")}]


def default_loans():
    return [
        {"name": "國泰轉貸（新）", "balance": 0, "active": True, "memo": "7/17 面簽；利率 2.6%"},
        {"name": "原國泰房貸（待轉清）", "balance": 0, "active": False, "memo": "9/25 過期"},
    ]


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只顯示將寫入的資料，不呼叫 Notion API")
    args = parser.parse_args()

    snapshot = load_snapshot()
    ingester = NotionIngester(dry_run=args.dry_run)

    print("=== Notion Ingest Start ===")
    print(f"snapshot keys: {list(snapshot.keys())[:10]}...")

    income = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("income", {})
    expense = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("expense", {})
    moneybook = {
        "dividend_income": income.get("配息_保守估_月均"),
        "rent_income": snapshot.get("rent_monthly_actual"),
        "interest_income": income.get("利息收入"),
        "non_bonus_income": snapshot.get("monthly_income"),
        "monthly_expense": snapshot.get("monthly_expense"),
    }
    ingester.ingest_master_ledger({**snapshot, **moneybook})
    ingester.ingest_fund_station(default_funds())
    ingester.ingest_policy_vault(default_policies(snapshot), DB_MAP["master_ledger"], DB_MAP["debt_cashflow"])
    ingester.ingest_collateral_hub(default_loans())
    ingester.ingest_ops_logs([
        {"name": "notion_ingest daily", "source": "Hermes", "status": "完成", "category": "同步", "summary": f"五表自動灌流 {TODAY}", "link": ""}
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
