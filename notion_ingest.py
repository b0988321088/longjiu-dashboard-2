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
        """查詢同一 DB 內是否有同名 page，供 upsert 使用（以 title 精準比對）。"""
        if self.dry:
            return None
        payload = {
            "filter": {
                "property": title_prop,
                "title": {"equals": title_value},
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

    def _create_or_update(self, db_id: str, props: dict, markdown: str = "", date_prop: str = "", date_value: str = TODAY):
        title_map = ["資產名稱", "項目", "Name", "事件名稱", "基金名稱", "保單名稱"]
        title_prop = next((k for k in title_map if k in props), "")
        title_value = ""
        if title_prop in props:
            try:
                title_value = props[title_prop]["title"][0]["text"]["content"]
            except Exception:
                pass
        existing = self._find_existing_page(db_id, title_prop, title_value, date_prop, date_value)
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
        REPO / "Moneybook" / "account.csv",  # fallback legacy
    ]
    # auto-discover latest Moneybook_帳戶_*.csv in Moneybook folder
    mb_dir = REPO / "Moneybook"
    found = sorted(mb_dir.glob("Moneybook_帳戶_*.csv"))
    if found:
        account_paths = [found[-1]] + account_paths
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
        REPO / "Moneybook" / "detail.csv",  # fallback legacy
    ]
    # auto-discover latest Moneybook_明細_*.csv in Moneybook folder
    mb_dir = REPO / "Moneybook"
    found = sorted(mb_dir.glob("Moneybook_明細_*.csv"))
    if found:
        detail_paths = [found[-1]] + detail_paths
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
            # exclude redemptions / fund sales which are not dividends
            if "贖回" in desc or "賣出基金" in cat or "賣出" in desc:
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


    def ingest_daily_asset_snapshot(self, snapshot: dict):
        db_id = DB_MAP.get("daily_asset_snapshots")
        if not db_id:
            print("[SKIP] daily_asset_snapshots DB ID not found.")
            return
        
        today_date = TODAY # Use the TODAY variable defined globally
        
        props = {
            "Date": {"date": {"start": today_date}},
            "Total Assets": {"number": to_num(snapshot.get("total_assets"))},
            "Securities": {"number": to_num(snapshot.get("securities_total"))},
            "Insurance": {"number": to_num(snapshot.get("insurance_current_value"))},
            "Funds": {"number": to_num(snapshot.get("fund_market_value"))},
            "Cash": {"number": to_num(snapshot.get("real_liquid_assets"))},
            "Snapshot ID": {"title": [{"text": {"content": f"Snapshot-{today_date}"}}]},
            "Source": {"select": {"name": "Hermes"}}, # Default source
            "Link": {"url": f"file://{REPO}/daily_report_v2_{today_date}.html"}, # Example link
        }
        # Filter out None values from properties before sending to Notion
        props_clean = {k: v for k, v in props.items() if v.get("number") is not None or v.get("date") is not None or v.get("title") is not None or v.get("select") is not None or v.get("url") is not None}

        print(f"[Notion] Ingesting Daily Asset Snapshot for {today_date}")
        self._create_or_update(db_id, props_clean, date_prop="Date", date_value=today_date)

    def ingest_decision_record(self, decision: dict):
        db_id = DB_MAP.get("major_decision_records")
        if not db_id:
            print("[SKIP] major_decision_records DB ID not found.")
            return

        title_content = decision.get("text", "Unknown Decision")
        if len(title_content) > 2000: # Notion title limit
            title_content = title_content[:1997] + "..."

        props = {
            "Decision": {"title": [{"text": {"content": title_content}}]},
            "Date": {"date": {"start": decision.get("approved_at", TODAY)[:10]}},
            "Context": {"rich_text": [{"text": {"content": decision.get("context", "")}}]},
            "Reasoning": {"rich_text": [{"text": {"content": decision.get("reasoning", "")}}]},
            "Outcome": {"rich_text": [{"text": {"content": decision.get("outcome", "")}}]},
            "Agent": {"select": {"name": decision.get("source", "Hermes").capitalize()}},
            "Tags": {"multi_select": [{"name": tag} for tag in decision.get("tags", [])]},
            "Link": {"url": decision.get("link", "")},
        }
        # Filter out empty strings for URL and rich_text if they cause issues
        props_clean = {}
        for k, v in props.items():
            if k == "Link" and not v["url"]:
                continue
            if k in ["Context", "Reasoning", "Outcome"] and not v["rich_text"][0]["text"]["content"].strip():
                continue
            props_clean[k] = v

        print(f"[Notion] Ingesting Decision Record: {title_content}")
        self._create_or_update(db_id, props_clean, date_prop="Date", date_value=decision.get("approved_at", TODAY)[:10])

    def ingest_analysis_result(self, analysis_result: dict):
        db_id = DB_MAP.get("agent_analysis_results")
        if not db_id:
            print("[SKIP] agent_analysis_results DB ID not found.")
            return

        title_content = analysis_result.get("title", "Unknown Analysis")
        if len(title_content) > 2000: # Notion title limit
            title_content = title_content[:1997] + "..."

        props = {
            "Title": {"title": [{"text": {"content": title_content}}]},
            "Date": {"date": {"start": analysis_result.get("date", TODAY)[:10]}},
            "Agent": {"select": {"name": analysis_result.get("agent", "Hermes").capitalize()}},
            "Analysis Type": {"select": {"name": analysis_result.get("analysis_type", "General").capitalize()}},
            "Summary": {"rich_text": [{"text": {"content": analysis_result.get("summary", "")}}]},
            "Raw Output Link": {"url": analysis_result.get("raw_output_link", "")},
            "Sentiment": {"select": {"name": analysis_result.get("sentiment", "Neutral").capitalize()}},
        }
        props_clean = {}
        for k, v in props.items():
            if k == "Raw Output Link" and not v["url"]:
                continue
            if k == "Summary" and not v["rich_text"][0]["text"]["content"].strip():
                continue
            props_clean[k] = v

        print(f"[Notion] Ingesting Analysis Result: {title_content}")
        self._create_or_update(db_id, props_clean, date_prop="Date", date_value=analysis_result.get("date", TODAY)[:10])


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
    # Use actual policy values from snapshot keys
    policies = []
    anl_a = snapshot.get("allianz_policy_a_value") or 0
    anl_b = snapshot.get("allianz_policy_b_value") or 0
    fj33 = snapshot.get("firstjin_current_value") or 0
    fl65 = snapshot.get("firstjin_fl65_current_value") or 0
    # Proportional split of total Moneybook policy dividends by surrender value
    total_policy_div = snapshot.get("dividend_income", 0)
    total_value = anl_a + anl_b + fj33 + fl65
    if total_value <= 0:
        total_value = snapshot.get("insurance_total", 0)
    if anl_a:
        policies.append({
            "name": "安聯保單 A（QL186）",
            "surrender_value": anl_a,
            "cost_basis": 5_000_000,
            "monthly_payout": round(total_policy_div * anl_a / total_value) if total_value else 0,
        })
    if anl_b:
        policies.append({
            "name": "安聯保單 B（QL184）",
            "surrender_value": anl_b,
            "cost_basis": 3_000_000,
            "monthly_payout": round(total_policy_div * anl_b / total_value) if total_value else 0,
        })
    if fl65:
        policies.append({
            "name": "第一金保單 FL65",
            "surrender_value": fl65,
            "cost_basis": 2_000_000,
            "monthly_payout": round(total_policy_div * fl65 / total_value) if total_value else 0,
        })
    if fj33:
        policies.append({
            "name": "第一金保單 FJ33",
            "surrender_value": fj33,
            "cost_basis": snapshot.get("insurance_total") or fj33,
            "monthly_payout": round(total_policy_div * fj33 / total_value) if total_value else 0,
        })
    if not policies:
        policies.append({
            "name": "保單合併",
            "surrender_value": snapshot.get("insurance_total"),
            "cost_basis": snapshot.get("insurance_total"),
            "monthly_payout": snapshot.get("dividend_income"),
        })
    return policies

def test_notion_api_connectivity():
    print("\n=== Testing Notion API Connectivity ===")
    try:
        user_data = ns_get("/users/me")
        print(f'[OK] Connected to Notion as: {user_data.get("name", "Unknown User")} ({user_data.get("id")})')

        search_payload = {"query": "", "filter": {"property": "object", "value": "database"}}
        db_results = ns_post("/search", search_payload)
        print(f'[INFO] Found {len(db_results.get("results", []))} databases accessible to the token.')

        # Check if the placeholder IDs are still present, if so, prompt user for manual creation
        if any(DB_MAP.get(db_key) == "00000000-0000-0000-0000-000000000000" for db_key in ["daily_asset_snapshots", "major_decision_records", "agent_analysis_results"]):
            print("\n[ACTION REQUIRED] 請在 Notion 手動建立以下資料庫，並將其 ID 更新至 notion_db_ids.json：")
            print("1. Daily Asset Snapshots (資料庫名稱): Date (日期), Total Assets (數字), Securities (數字), Insurance (數字), Funds (數字), Cash (數字), Snapshot ID (標題), Source (選取), Link (網址)")
            print("2. Major Decision Records (資料庫名稱): Decision (標題), Date (日期), Context (文字), Reasoning (文字), Outcome (文字), Agent (選取), Tags (多重選取), Link (網址)")
            print("3. Agent Analysis Results (資料庫名稱): Title (標題), Date (日期), Agent (選取), Analysis Type (選取), Summary (文字), Raw Output Link (網址), Sentiment (選取)")
        else:
            print("[INFO] Notion 資料庫 ID 已設定，準備進行資料寫入。")

    except Exception as e:
        print(f"[ERROR] Notion API 連線測試失敗: {e}")
        print("請確認您的 NOTION_TOKEN 有效，並具有讀取/寫入頁面和資料庫的權限。")
    print("=== Notion API Connectivity Test End ===\n")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只顯示將寫入的資料，不呼叫 Notion API")
    args = parser.parse_args()

    # Run Notion API connectivity test
    test_notion_api_connectivity()
    
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
    # 配息 = 保單配息 + ETF/基金配息（從 Moneybook 明細拆解）
    snapshot["dividend_income"] = policy_div + etf_div
    # 房租收入 = snapshot 推導（MB 明細中房租多為支出）
    snapshot["rent_income"] = snapshot.get("passive_income", {}).get("rent_monthly", snapshot.get("rent_monthly_actual", 0))
    snapshot["interest_income"] = snapshot.get("page1", {}).get("actual_cash_flow", {}).get("income", {}).get("利息收入")
    snapshot["non_bonus_income"] = snapshot.get("monthly_income")
    snapshot["monthly_expense"] = snapshot.get("monthly_expense")

    income = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("income", {})
    expense = (snapshot.get("page1", {}) or {}).get("actual_cash_flow", {}).get("expense", {})
    moneybook = {
        "dividend_income": snapshot["dividend_income"],
        "rent_income": snapshot.get("rent_income"),
        "interest_income": income.get("利息收入"),
        "non_bonus_income": snapshot.get("monthly_income"),
        "monthly_expense": snapshot.get("monthly_expense"),
    }

    print(f"真值：銀行資產(正數TWD)={bank_assets:,.0f}")
    print(f"真值：保單配息(7月)={policy_div:,.0f}，ETF/基金配息(7月)={etf_div:,.0f}")
    print(f"真值：配息收入(採用)={snapshot['dividend_income']:,.0f}")
    print(f"真值：房租收入={snapshot.get('rent_income',0):,.0f}")
    print(f"真值：利息收入={snapshot.get('interest_income',0):,.0f}")
    print(f"真值：月支出={snapshot.get('monthly_expense',0):,.0f}")

    # Anomaly checks
    if bank_assets < 0:
        print("⚠️ 警告：銀行資產為負數！")
    if snapshot["dividend_income"] == 0:
        print("⚠️ 警告：配息收入為 0！")
    if snapshot.get("rent_income", 0) == 0:
        print("⚠️ 警告：房租收入為 0！")
    diff = abs(bank_assets - snapshot.get("moneybook_total", 0))
    if diff > 2000:
        print(f"⚠️ 警告：Moneybook 正數合計與 snapshot.moneybook_total 差異 {diff:,.0f}")

    ingester.ingest_master_ledger({**snapshot, **moneybook})
    ingester.ingest_fund_station(default_funds(snapshot))
    ingester.ingest_policy_vault(default_policies(snapshot), DB_MAP["master_ledger"], DB_MAP["debt_cashflow"])
    ingester.ingest_collateral_hub(parse_ledger_loans())

    # Ingest Daily Asset Snapshot
    ingester.ingest_daily_asset_snapshot(snapshot)

    # Ingest Major Decision Records from dashboard_decisions.json
    dec_file = REPO / "dashboard_decisions.json"
    if dec_file.exists():
        existing_decisions = json.loads(dec_file.read_text(encoding="utf-8"))
        for d in existing_decisions.get("decisions", []):
            # Add 'context', 'reasoning', 'outcome', 'tags', 'link' if not present in dashboard_decisions.json
            # For simplicity now, we assume these are empty if not explicitly available.
            decision_data = {
                "text": d.get("text", ""),
                "approved_at": d.get("approved_at", TODAY),
                "source": d.get("source", "Hermes"),
                "context": d.get("context", ""),
                "reasoning": d.get("reasoning", ""),
                "outcome": d.get("outcome", ""),
                "tags": d.get("tags", []),
                "link": d.get("link", ""),
            }
            ingester.ingest_decision_record(decision_data)

    # Ingest Agent Analysis Results (example: CIO summary)
    cio_summary_text = load_daily_report_cio() # Re-add this helper if needed, or get summary from relevant source
    if cio_summary_text and cio_summary_text != "今日日報未發現明確 CIO 摘要。" and cio_summary_text != "今日日報未找到，無 CIO 摘要。":
        analysis_data = {
            "date": TODAY,
            "title": f"CIO Daily Review Summary {TODAY}",
            "agent": "CIO",
            "analysis_type": "Daily Review",
            "summary": cio_summary_text,
            "raw_output_link": f"file://{REPO}/daily_report_v2_{TODAY}.md",
            "sentiment": "Neutral", # Placeholder
        }
        ingester.ingest_analysis_result(analysis_data)

    # Original ingest_ops_logs removed as analysis results will be handled by ingest_analysis_result
    # ingester.ingest_ops_logs([...]) # This call will be removed

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
