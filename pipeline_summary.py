# -*- coding: utf-8 -*-
"""pipeline_summary.py — 產線跑完後把「五章摘要」推回 Telegram（2026-10-21 使用者核准）

為什麼要有這一支：
    手動執行 morning_deploy.py 時，輸出只落在 stdout／logs/morning_*.log；
    Telegram 通知是 cron job 發的，手動代跑不會觸發 → 使用者只看得到「RC=0」，
    實際日報內容沒送到面前（2026-10-21 實踩）。

用法：
    python pipeline_summary.py              # 只印出（不推播）
    python pipeline_summary.py --send       # 印出並推播
    python pipeline_summary.py --send --rc 0
    python morning_deploy.py --notify       # 產線跑完自動推播（預設關，cron 不帶此旗標）

資料來源一律讀真值檔（snapshot.json／macro_regime_*.json／pending_engine），
不寫死任何金額；缺鍵就顯示「—」，不臆測。
"""
from __future__ import annotations

import glob
import json
import re
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = BASE / "snapshot.json"
ENV = Path.home() / "AppData" / "Local" / "hermes" / ".env"
TG_LIMIT = 3800          # Telegram 單則上限 4096，留安全邊界


def _n(v, unit: str = "") -> str:
    """整數千分位；None／非數字 →「—」（不猜）。"""
    try:
        return f"{int(round(float(v))):,}" + unit
    except (TypeError, ValueError):
        return "—"


def _pct(v) -> str:
    try:
        return f"{float(v):+.1f}pp"
    except (TypeError, ValueError):
        return "—"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _macro() -> dict:
    files = sorted(glob.glob(str(BASE / "macro_regime_*.json")))
    return _load(Path(files[-1])) if files else {}


def _pending_line() -> str:
    try:
        import pending_engine as pe
        return pe.pending_line()
    except Exception as e:  # 摘要不得因 pending 壞掉而整則消失
        return f"📌 Pending：（讀取失敗：{type(e).__name__}）"


def _trigger(v) -> str:
    """主觸發可能是字串或 {指標: 值} 的 dict → 壓成可讀字串（不印原始 dict）。"""
    if isinstance(v, dict):
        parts = []
        for k, x in list(v.items()):
            if x is None:
                continue  # 缺值不印 None（沒資料就不假裝有）
            try:
                parts.append(f"{k} {float(x):.2f}")
            except (TypeError, ValueError):
                parts.append(f"{k} {x}")
            if len(parts) >= 3:
                break
        return "、".join(parts) or "—"
    return str(v or "—")


_TGT_KEY = {"台股市值型成長": "台股市值型目標", "美股市值型成長": "美股市值型目標",
            "防守型配息": "配息型目標", "債券": "債券型目標", "現金/安全網": "現金目標"}


def build(rc: int = 0, day: str | None = None) -> str:
    s = _load(SNAP)
    d = day or str(s.get("date") or date.today().isoformat())
    pen = s.get("penetration") or {}
    act, tgt, gap = pen.get("actual_pct") or {}, pen.get("targets") or {}, pen.get("gaps") or {}
    cl = s.get("cash_layers") or {}
    ins = s.get("insurance_breakdown") or {}
    m = _macro()

    L: list[str] = [f"📊 龍九日報 {d}（五章摘要）", ""]

    # 1／5 財富生命線
    L += ["1️⃣ 財富生命線",
          f"・總資產 {_n(s.get('total_assets'))}／總負債 {_n(s.get('total_liabilities'))}"
          f"／淨值 {_n(s.get('net_worth'))}",
          f"・負債比 {s.get('debt_ratio', '—')}%｜月收 {_n(s.get('monthly_income'))}"
          f"／月支出 {_n(s.get('monthly_expense'))}／月盈餘 {_n(s.get('working_surplus'))}",
          f"・證券 {_n(s.get('securities_total_market_value'))}／基金 {_n(s.get('fund_market_value'))}"
          f"／房租 {_n(s.get('rent_monthly_actual'))}／月",
          ""]

    # 2／5 戰略異常看板
    L += [f"2️⃣ 戰略異常看板（宏觀 {m.get('date', '—')}）",
          f"・燈號 {m.get('燈號', '—')}｜主觸發 {_trigger(m.get('主觸發'))}"]
    for k in ("台股市值型成長", "美股市值型成長", "防守型配息", "債券", "現金/安全網"):
        if k in act:
            t = tgt.get(_TGT_KEY.get(k, k + "目標"))
            g = gap.get(k)
            L.append(f"・{k} {act[k]}%" + (f"（目標 {t}，{_pct(g)}）" if t is not None and g is not None else ""))
    if pen.get("alert"):
        L.append(f"・⚠️ {pen['alert']}")
    L.append("")

    # 3／5 保單接力引擎
    L += ["3️⃣ 保單接力引擎",
          f"・保單現值合計 {_n(s.get('insurance_total'))}"
          + (f"（安聯A {_n(ins.get('policy_a_total'))}／安聯B {_n(ins.get('policy_b_total'))}）"
             if ins else ""),
          f"・最近更新 {str(s.get('last_insurance_update') or '—')[:16]}"]
    try:
        ev = _load(BASE / "schedule_events.json")
        items = ev if isinstance(ev, list) else (ev.get("events") or ev.get("items") or [])
        _kw = ("保單", "轉換", "接力", "質押", "配息", "截止")
        _future = sorted([x for x in items if str(x.get("date", "")) >= d], key=lambda x: x["date"])
        # 保單接力章優先列保單／轉換／截止類事件；沒有才退回最近的一般排程
        nxt = [x for x in _future if any(k in str(x.get("item", "")) for k in _kw)][:3] or _future[:2]
        for x in nxt:
            L.append(f"・{x['date']} {str(x.get('item', ''))[:34]}")
        if not nxt:
            L.append("・近期無排程事件")
    except Exception:
        L.append("・排程事件讀取失敗")
    L.append("")

    # 4／5 流動性調度站
    L += ["4️⃣ 流動性調度站",
          f"・帳上現金 {_n(cl.get('cash_total'))}＝可動用 {_n(cl.get('unrestricted_cash'))}"
          f"＋指定款 {_n((cl.get('restricted_cash') or {}).get('total'))}",
          f"・乾粉 {_n(cl.get('dry_powder'))}｜90 天缺口 {_n(cl.get('cash_shortfall'))}"
          f"｜可用信用額度 {_n(cl.get('credit_line_available'))}",
          ""]

    # 5／5 決戰日檢核
    L += ["5️⃣ 決戰日檢核", _pending_line(),
          f"・產線 rc={rc}" + ("（成功）" if rc == 0 else "（失敗／需人工，見日誌）"),
          ""]

    # 連結
    base = "https://b0988321088.github.io/longjiu-dashboard-2"
    for label, name in (("📰 日報", f"daily_report_v2_{d}.html"),
                        ("📈 差異", f"asset_diff_{d}.html"),
                        ("🔄 再平衡", f"rebalance_dashboard_{d}.html"),
                        ("📊 穿透", f"penetration_report_{d}.html")):
        L.append(f"{label}：{base}/{name}")
    L.append(f"🏠 儀表板：{base}/")
    return "\n".join(L)


def send(text: str) -> bool:
    """推播到 Telegram（token/chat_id 只從 repo 外的 .env 讀，不落任何檔案）。"""
    token = chat = ""
    try:
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_ALLOWED_USERS="):
                chat = line.split("=", 1)[1].strip().split(",")[0].strip()
    except Exception:
        return False
    if not (token and chat):
        return False
    ok = True
    for i in range(0, len(text), TG_LIMIT):
        chunk = text[i:i + TG_LIMIT]
        try:
            import urllib.parse
            import urllib.request
            data = urllib.parse.urlencode({"chat_id": chat, "text": chunk}).encode()
            with urllib.request.urlopen(
                    f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20) as r:
                ok = ok and (r.status == 200)
        except Exception:
            return False
    return ok


def send_summary(rc: int = 0) -> bool:
    text = build(rc=rc)
    return send(text)


if __name__ == "__main__":
    _rc = 0
    if "--rc" in sys.argv:
        try:
            _rc = int(sys.argv[sys.argv.index("--rc") + 1])
        except (IndexError, ValueError):
            _rc = 0
    _text = build(rc=_rc)
    print(_text)
    if "--send" in sys.argv:
        print("\n📨 推播" + ("成功" if send(_text) else "失敗（token/chat_id 或缺網路）"))
