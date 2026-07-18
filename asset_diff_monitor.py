"""
asset_diff_monitor.py — 資產每日變化差異監控
資料來源：Notion master_ledger（分類=快照）+ snapshot.json fallback
產出：asset_diff_YYYY-MM-DD.html + Telegram 摘要
"""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
import requests
from pathlib import Path
from datetime import datetime, date
from typing import Any
import webbrowser

# Load env
project_env = Path(__file__).resolve().parents[0] / ".env"
hermes_env = Path.home() / "AppData" / "Local" / "hermes" / ".env"
default_env = os.environ.get("DOTENV", str(project_env))
if not Path(default_env).exists() and hermes_env.exists():
    default_env = str(hermes_env)
from dotenv import load_dotenv
load_dotenv(default_env)

NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
BASE = "https://api.notion.com/v1"
HEADERS = {"Authorization": f"Bearer {NOTION_TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
MASTER_DB = "39dfc735-d433-8153-9712-c8a0ee0ec846"

HISTORY_FILE = Path("asset_diff_history.json")
SNAP_FILE = Path("snapshot.json")
OUT_HTML = Path(f"asset_diff_{date.today().isoformat()}.html")

ALERT_DROP_TWD = 100_000
ALERT_DROP_PCT = 2.0
ALERT_SEC_DROP_TWD = 50_000
WATCH_SEC_PCT = 3.0


def notion_get(path: str) -> dict:
    r = requests.get(f"{BASE}{path}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def notion_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=60)
    if r.status_code >= 400:
        print(f"HTTP {r.status_code} response: {r.text[:500]}")
    r.raise_for_status()
    return r.json()


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def notion_fetch_snapshots() -> list[dict]:
    """從 master_ledger 取回所有『快照』頁，依日期排序。"""
    if not NOTION_TOKEN:
        return []
    rows: list[dict] = []
    cursor = None
    while True:
        payload: dict[str, Any] = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        try:
            data = notion_post(f"/databases/{MASTER_DB}/query", payload)
        except Exception as e:
            print("⚠️ Notion query failed:", e)
            break
        for page in data.get("results", []):
            props = page.get("properties", {})
            title = ""
            try:
                title = props.get("資產名稱", {}).get("title", [{}])[0].get("plain_text", "")
            except Exception:
                pass
            if "快照" not in title:
                continue
            dt = ""
            try:
                dt = props.get("更新日期", {}).get("date", {}).get("start", "")
            except Exception:
                pass
            if not dt:
                continue
            note = ""
            try:
                note = props.get("備註", {}).get("rich_text", [{}])[0].get("plain_text", "")
            except Exception:
                pass
            rows.append({"date": dt, "title": title, "note": note})
        cursor = data.get("next_cursor")
        if not data.get("has_more"):
            break
    rows.sort(key=lambda x: x["date"])
    return rows


def parse_snapshot_note(note: str) -> dict:
    """把 master_ledger 備註的文字快照解析回数字。"""
    result: dict[str, Any] = {}
    parts = note.split("|")
    for part in parts:
        part = part.strip()
        if "總資產" in part:
            result["total_assets"] = float(part.split("總資產")[1].replace(",", "").split("（")[0].strip())
        elif "淨資產" in part:
            result["net_worth"] = float(part.split("淨資產")[1].replace(",", "").split("）")[0].strip())
        elif "證券" in part:
            result["securities_market"] = float(part.split("證券")[1].replace(",", "").strip())
        elif "保單" in part:
            result["insurance_total"] = float(part.split("保單")[1].replace(",", "").split("|")[0].strip())
    return result


def append_snapshot(snap: dict) -> dict:
    history = load_json(HISTORY_FILE)
    today = date.today().isoformat()
    entry = {
        "date": today,
        "total_assets": snap.get("total_assets", 0),
        "net_worth": snap.get("net_worth", 0),
        "insurance_total": snap.get("insurance_total", 0),
        "securities_cost": snap.get("securities_total", snap.get("securities_total_market_value", 0)),
        "securities_market": snap.get("securities_total_market_value", snap.get("securities_total", 0)),
    }
    history[today] = entry
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def compute_changes(history: dict) -> list[dict]:
    sorted_dates = sorted(history.keys())
    rows: list[dict] = []
    prev = None
    for d_str in sorted_dates:
        row = history[d_str]
        if prev is None:
            prev = row
            continue
        rows.append({
            "date": d_str,
            "total_assets": row["total_assets"],
            "net_worth": row["net_worth"],
            "insurance_total": row["insurance_total"],
            "securities_cost": row["securities_cost"],
            "securities_market": row["securities_market"],
            "d_total": row["total_assets"] - prev["total_assets"],
            "d_total_pct": (row["total_assets"] - prev["total_assets"]) / prev["total_assets"] * 100 if prev["total_assets"] else 0,
            "d_sec": row["securities_market"] - prev["securities_market"],
            "d_sec_pct": (row["securities_market"] - prev["securities_market"]) / prev["securities_market"] * 100 if prev["securities_market"] else 0,
            "d_ins": row["insurance_total"] - prev["insurance_total"],
        })
        prev = row
    return rows


def _color(x: float, inverse: bool = False) -> str:
    good = x >= 0
    if inverse:
        good = not good
    return "#16a34a" if good else "#dc2626"


def _svg_line(values: list[float], width: int = 600, height: int = 120, color: str = "#2563eb") -> str:
    if not values or len(values) < 2:
        return ""
    min_v = min(values)
    max_v = max(values)
    span = max_v - min_v if max_v != min_v else 1
    pad = 8
    w = width - pad * 2
    h = height - pad * 2
    step = w / (len(values) - 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = pad + h - ((v - min_v) / span) * h
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(f"L {p}" for p in pts)
    first = pts[0]
    return (
        f'<svg width="{width}" height="{height}" style="max-width:100%;height:auto;" viewBox="0 0 {width} {height}">'
        f'<polyline points="{first} {poly.replace("L ", "L")}" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{first.split(",")[0]}" cy="{first.split(",")[1]}" r="3" fill="{color}"/>'
        f'<circle cx="{pts[-1].split(",")[0]}" cy="{pts[-1].split(",")[1]}" r="3" fill="{color}"/>'
        f'</svg>'
    )


def build_snapshot_chart(rows: list[dict]) -> str:
    """最新資產結構快照圖（長條圖）。"""
    last = rows[-1] if rows else {}
    sec = last.get("securities_market", 0)
    ins = last.get("insurance_total", 0)
    # debt from snapshot
    snap = load_json(SNAP_FILE)
    total_liab = snap.get("total_liabilities", 22_000_000)
    ta = last.get("total_assets", 0)
    labels = ["證券市值", "保單現值", "總負債", "其他淨資產"]
    values = [sec, ins, total_liab, max(0, ta - sec - ins - total_liab)]
    colors = ["#2563eb", "#16a34a", "#dc2626", "#f59e0b"]
    max_v = max(values) if max(values) else 1
    bar_w = 60
    gap = 30
    chart_w = len(values) * (bar_w + gap) + 40
    chart_h = 140
    bars = []
    for i, (v, c) in enumerate(zip(values, colors)):
        x = 20 + i * (bar_w + gap)
        bar_h = (v / max_v) * (chart_h - 40)
        y = chart_h - 20 - bar_h
        label = f"{v/10000:.0f}萬" if v >= 10000 else f"{v:,.0f}"
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" rx="6" fill="{c}" opacity="0.9"/>'
            f'<text x="{x + bar_w/2}" y="{y - 6}" text-anchor="middle" font-size="11" fill="#374151">{label}</text>'
            f'<text x="{x + bar_w/2}" y="{chart_h - 4}" text-anchor="middle" font-size="11" fill="#6b7280">{labels[i]}</text>'
        )
    return (
        f'<svg width="{chart_w}" height="{chart_h}" style="max-width:100%;height:auto;" viewBox="0 0 {chart_w} {chart_h}">'
        + "".join(bars) + "</svg>"
    )


def build_html(rows: list[dict]) -> str:
    today = date.today().isoformat()
    last = rows[-1] if rows else None

    rows_html = []
    for r in rows[-7:]:
        d_total = r["d_total"]
        d_sec = r["d_sec"]
        badge = ""
        if d_total < -ALERT_DROP_TWD or r["d_total_pct"] < -ALERT_DROP_PCT or d_sec < -ALERT_SEC_DROP_TWD or abs(r["d_sec_pct"]) >= WATCH_SEC_PCT:
            badge = ' <span style="color:#dc2626;font-size:12px;">🚨 警示</span>'
        rows_html.append(
            "<tr>"
            f"<td>{r['date']}</td>"
            f"<td class=\"num\">{r['total_assets']:,.0f}</td>"
            f"<td class=\"num\" style=\"color:{_color(d_total)}\">{d_total:+,.0f}</td>"
            f"<td class=\"num\" style=\"color:{_color(r['d_total_pct'])}\">{r['d_total_pct']:+.2f}%</td>"
            f"<td class=\"num\">{r['insurance_total']:,.0f}</td>"
            f"<td class=\"num\" style=\"color:{_color(d_sec)}\">{d_sec:+,.0f}</td>"
            f"<td class=\"num\" style=\"color:{_color(r['d_sec_pct'])}\">{r['d_sec_pct']:+.2f}%</td>"
            f"</tr>{badge}"
        )

    alerts = []
    if last:
        checks = [("總資產", last["d_total"], last["d_total_pct"]), ("證券市值", last["d_sec"], last["d_sec_pct"]), ("保險", last["d_ins"], None)]
        for name, delta, pct in checks:
            if delta < -ALERT_DROP_TWD or (pct is not None and pct < -WATCH_SEC_PCT):
                pct_s = f"{pct:+.2f}%" if pct is not None else ""
                alerts.append(f"<li><b>{name}</b>：{delta:+,.0f}（{pct_s}）</li>")
    alerts_html = "\n".join(alerts) if alerts else "<li>✅ 今日無異常</li>"

    title = f"asset_diff_{today}"
    rows_joined = "".join(rows_html) if rows_html else '<tr><td colspan="7">尚無資料</td></tr>'
    alert_header = f"單日資產下跌 ≥ {ALERT_DROP_TWD:,.0f} / {ALERT_DROP_PCT:.1f}%；證券下跌 ≥ {ALERT_SEC_DROP_TWD:,.0f} / ±{WATCH_SEC_PCT:.1f}%"

    # Build charts from raw history so we have ≥2 points whenever possible
    raw_history = load_json(HISTORY_FILE)
    sorted_dates = sorted(raw_history.keys())
    if len(sorted_dates) >= 2:
        hist_rows = [raw_history[d] for d in sorted_dates[-14:]]
        sec_vals = [r.get("securities_market", 0) for r in hist_rows]
        ins_vals = [r.get("insurance_total", 0) for r in hist_rows]
        ta_vals = [r.get("total_assets", 0) for r in hist_rows]
        d_sec_vals = [r.get("securities_market", 0) - hist_rows[i-1].get("securities_market", 0) for i, r in enumerate(hist_rows) if i > 0]
        svg_sec = _svg_line(sec_vals, color="#2563eb")
        svg_ins = _svg_line(ins_vals, color="#16a34a")
        svg_ta = _svg_line(ta_vals, color="#7c3aed")
        svg_delta = _svg_line(d_sec_vals, color="#dc2626") if len(d_sec_vals) >= 2 else ""
        snapshot_chart = build_snapshot_chart(rows)
        charts_html = (
            '<div class="card"><h2>📈 資產類別趨勢（近 14 日）</h2>'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;">'
            '<div style="flex:1;min-width:280px;"><div class="text-sm">證券市值</div>' + svg_sec + '</div>'
            '<div style="flex:1;min-width:280px;"><div class="text-sm">保單現値</div>' + svg_ins + '</div>'
            '</div>'
            '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:12px;">'
            '<div style="flex:1;min-width:280px;"><div class="text-sm">總資產</div>' + svg_ta + '</div>'
            '<div style="flex:1;min-width:280px;"><div class="text-sm">證券日增減</div>' + (svg_delta or '<div class="text-sm">累計中</div>') + '</div>'
            '</div></div>'
            '<div class="card"><h2>📊 資產結構快照</h2>' + snapshot_chart + '</div>'
        )
    else:
        charts_html = '<div class="card"><h2>📈 資產類別趨勢</h2><div class="text-sm">累積第二天開始顯示趨勢圖</div></div>' 

    parts = [
        "<!DOCTYPE html><html lang=\"zh-TW\"><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">",
        f"<title>{title}</title><style>",
        "body{font-family:-apple-system,\"Helvetica Neue\",\"PingFang TC\",sans-serif;background:#f5f5f7;color:#1d1d1f;margin:0;padding:14px}",
        ".page{max-width:960px;margin:0 auto}",
        ".card{background:#fff;border-radius:12px;padding:16px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04)}",
        "h1{font-size:20px;font-weight:900;margin:0 0 6px}",
        "h2{font-size:17px;font-weight:800;margin:12px 0 8px}",
        ".table-wrap{overflow-x:auto}",
        "table{width:100%;border-collapse:collapse;font-size:15px}",
        "th{background:#f2f2f7;font-weight:700;text-align:left;padding:8px 10px;border-bottom:1px solid #e5e5ea}",
        "td{padding:8px 10px;border-bottom:1px solid #f2f2f7}",
        "td.num{text-align:right;font-variant-numeric:tabular-nums}",
        ".text-sm{font-size:13px;color:#6e6e73}",
        "pre{font-size:13px;line-height:1.8;white-space:pre-wrap}",
        "</style></head><body><div class=\"page\">",
        f"<div class=\"card\"><h1>📈 資產變化對照 {today}</h1><div class=\"text-sm\">資產監控 / 月趨勢 / 異常警示</div></div>",
        '<div class="card"><h2>資產變化對照（近 7 日）</h2><div class="table-wrap"><table><thead><tr>',
        "<th>日期</th><th class=\"num\">總資產</th><th class=\"num\">增減</th><th class=\"num\">%</th>",
        "<th class=\"num\">保單現値</th><th class=\"num\">證券增減</th><th class=\"num\">證券%</th></tr></thead><tbody>",
        rows_joined,
        "</tbody></table></div></div>",
        f'<div class="card"><h2>監控警示</h2><div class="text-sm\">{alert_header}</div><ul style="font-size:15px;line-height:1.8;">{alerts_html}</ul></div>',
        "</div></body></html>",
    ]
    return "".join(parts)


def build_telegram_text(rows: list[dict]) -> str:
    if not rows:
        return "📈 資產變化對照：尚無歷史紀錄"
    last = rows[-1]
    today_r = date.today().isoformat()
    flag = ""
    if last["d_total"] < 0 or last["d_sec"] < -ALERT_SEC_DROP_TWD:
        flag = "\n\n🚨 異常警示已觸發，請查看詳細 HTML。"
    return (
        f"📈 資產變化對照 {today_r}\n"
        f"總資產：{last['total_assets']:,.0f}（{last['d_total']:+,.0f} / {last['d_total_pct']:+.2f}%）\n"
        f"證券市值：{last['securities_market']:,.0f}（{last['d_sec']:+,.0f} / {last['d_sec_pct']:+.2f}%）\n"
        f"保單現値：{last['insurance_total']:,.0f}（{last['d_ins']:+,.0f}）"
        f"{flag}"
    )


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    # Fallback: Hermes home .env
    if (not token or not chat_id) and hermes_env.exists():
        from dotenv import dotenv_values
        cfg = dotenv_values(hermes_env)
        token = token or cfg.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = chat_id or cfg.get("TELEGRAM_CHAT_ID", "") or cfg.get("TELEGRAM_ALLOWED_USERS", "")
    if not token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN / CHAT_ID 未設定")
        return
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"📨 Telegram {resp.status}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ Telegram {e.code}: {body[:240]}")


def main() -> int:
    snap = load_json(SNAP_FILE)
    history = append_snapshot(snap)
    rows = compute_changes(history)
    if not rows:
        print("⚠️ 歷史資料不足，明日起開始產出差異對照表")
        return 0

    html = build_html(rows)
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"✅ HTML 已產出：{OUT_HTML}")

    tg = build_telegram_text(rows)
    send_telegram(tg)

    try:
        webbrowser.open(OUT_HTML.resolve().as_uri())
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
