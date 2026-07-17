"""
龍九系統最小穩定版 telegram_parser.py
功能：
1. 將 Hermes 收到的 Telegram 會計相關訊息，轉譯成結構化會計字典
2. 在 Company_Ledger.md 對應區段追加紀錄
3. 將解析事件逐行 append 寫入 logs/telegram_events.jsonl

設計原則：最小可執行、regex 為主、無外部重型相依。
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

APP_NAME = "longjiu-telegram-parser"
WORKSPACE = Path("C:/Users/bot/Desktop/龍九系統")
LEDGER_PATH = WORKSPACE / "Company_Ledger.md"
LOG_PATH = WORKSPACE / "logs" / "telegram_events.jsonl"


def ensure_log_path() -> Path:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    return LOG_PATH


def append_jsonl(record: Dict[str, Any]) -> None:
    ensure_log_path()
    record.setdefault("app", APP_NAME)
    record.setdefault("logged_at", datetime.utcnow().isoformat(timespec="seconds") + "Z")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_number(text: str) -> float:
    cleaned = (
        text.strip()
        .replace(",", "")
        .replace("，", "")
        .replace("元", "")
        .replace("塊", "")
    )
    # 約略容錯：若尾碼含 TWD/台幣/新台幣，先統一拿掉
    cleaned = re.sub(r"(TWD|台幣|新台幣)$", "", cleaned.strip()).strip()
    # 先把中文單位與數字一起拆：500萬 → 500 + 萬
    # 這裡維持原邏輯：使用者可輸入 500 萬 或 500萬
    multiplier = 1.0
    if cleaned.endswith("億"):
        multiplier, cleaned = 1e8, cleaned[:-1]
    elif cleaned.endswith("萬"):
        multiplier, cleaned = 1e4, cleaned[:-1]
    elif cleaned.endswith("張"):
        cleaned = cleaned[:-1]
    elif cleaned.endswith("股"):
        cleaned = cleaned[:-1]
    cleaned = cleaned.strip()
    if not cleaned:
        return 0.0
    return float(cleaned) * multiplier


def extract_number_and_unit(text: str):
    m = re.search(r"([0-9,，]+(?:\.[0-9]+)?)([張股萬億]?)\s*(?:TWD)?", text)
    if not m:
        return None, None
    raw_number, unit = m.group(1), m.group(2)
    number = normalize_number(raw_number + (unit if unit else ""))
    return number, unit or "TWD"


def parse_loan_repayment(message: str) -> Optional[Dict[str, Any]]:
    # 7/13 星展結清繳款 4,893,529 TWD
    m = re.match(r"(\d{1,2}/\d{1,2})\s*(.+?)\s*(?:結清|還款|繳款|清償)?\s*([0-9,，]+\s*TWD)", message, re.IGNORECASE)
    if not m:
        return None
    date_str, entity, amount_str = m.group(1), m.group(2).strip(), m.group(3)
    amount = normalize_number(amount_str)
    return {
        "type": "loan_repayment",
        "event_date": date_str,
        "entity": entity,
        "amount": amount,
        "currency": "TWD",
        "source_message": message,
    }


def parse_fund_transfer(message: str) -> Optional[Dict[str, Any]]:
    # 轉貸撥款 500 萬
    m = re.search(r"(?:轉貸|轉帳|匯款|撥款)\s*([0-9,，]+(?:\.[0-9]+)?\s*[萬億]?)", message, re.IGNORECASE)
    if not m:
        return None
    amount = normalize_number(m.group(1))
    return {
        "type": "fund_transfer",
        "amount": amount,
        "currency": "TWD",
        "source_message": message,
    }


def parse_buy_etf(message: str) -> Optional[Dict[str, Any]]:
    # 加碼台股0051 8張
    m = re.match(r"(?:加碼|買進|買|增持|加倉)\s*(?:台股)?\s*([0-9A-Za-z]{3,6})\s*([0-9,，]+)\s*張?", message, re.IGNORECASE)
    if not m:
        return None
    symbol, shares_str = m.group(1).upper(), m.group(2)
    shares = normalize_number(shares_str)
    return {
        "type": "buy_etf",
        "symbol": symbol,
        "shares": int(shares),
        "currency": "TWD",
        "source_message": message,
    }


def parse_pledge(message: str) -> Optional[Dict[str, Any]]:
    # 0056質押100萬凍結
    m = re.match(r"([0-9A-Za-z]{3,6})\s*(?:質押|质押)\s*([0-9,，]+)\s*(?:萬|TWD)?\s*(凍結|解除)?", message, re.IGNORECASE)
    if not m:
        return None
    symbol, amount_str, status = m.group(1).upper(), m.group(2), m.group(3) or "unknown"
    amount = normalize_number(amount_str + ("萬" if "萬" in message else ""))
    return {
        "type": "pledge",
        "symbol": symbol,
        "amount": amount,
        "status": status,
        "currency": "TWD",
        "source_message": message,
    }


def append_ledger_record(record: Dict[str, Any]) -> None:
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"Company_Ledger.md 不存在：{LEDGER_PATH}")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = ""
    rtype = record.get("type")
    if rtype == "loan_repayment":
        row = f"| {now} | 結清繳款 | {record['entity']} | {record['event_date']} | {int(record['amount']):,} TWD | telegram_parser |\n"
    elif rtype == "fund_transfer":
        row = f"| {now} | 轉貸撥款 | — | — | {int(record['amount']):,} TWD | telegram_parser |\n"
    elif rtype == "buy_etf":
        row = f"| {now} | 買進台股ETF | {record['symbol']} | {record['shares']:,} 張 | — | telegram_parser |\n"
    elif rtype == "pledge":
        row = f"| {now} | 質押/解質 | {record['symbol']} | {record['status']} | {int(record['amount']):,} TWD | telegram_parser |\n"
    else:
        row = f"| {now} | {rtype} | — | — | — | telegram_parser |\n"

    # 寫入 Company_Ledger.md 尾部
    with open(LEDGER_PATH, "a", encoding="utf-8") as f:
        f.write("\n")
        f.write(f"### telegram_parser 追加紀錄 {now}\n")
        f.write("| 時間 | 分類 | 標的/銀行 | 日期/張數 | 金額 | 來源 |\n")
        f.write("|------|------|-----------|-----------|------|------|\n")
        f.write(row)


def parse_telegram_message(message: str) -> Dict[str, Any]:
    if not message or not message.strip():
        raise ValueError("訊息不可為空")

    record: Optional[Dict[str, Any]] = None
    parsers = [parse_loan_repayment, parse_fund_transfer, parse_buy_etf, parse_pledge]
    for parser in parsers:
        try:
            record = parser(message)
        except Exception:
            record = None
        if record:
            break

    if not record:
        record = {
            "type": "unknown",
            "source_message": message,
            "amount": None,
            "currency": None,
        }

    event = {
        "source": "telegram",
        "message": message,
        "parsed": record,
        "status": "success" if record.get("type") != "unknown" else "unparsed",
    }
    append_jsonl(event)
    try:
        if record.get("type") != "unknown":
            append_ledger_record(record)
    except Exception as ledger_err:
        event["status"] = "partial"
        event["ledger_error"] = str(ledger_err)
        append_jsonl(event)

    return event


if __name__ == "__main__":
    samples = [
        "轉貸撥款 500 萬",
        "7/13 星展結清繳款 4,893,529 TWD",
        "加碼台股0051 8張",
        "0056質押100萬凍結",
        "0000",  # invalid sample that should produce parseable fallback
    ]
    for text in samples:
        result = parse_telegram_message(text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
