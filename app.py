"""龍九控股 資產護城河儀表板（本地動態版）"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import streamlit as st

st.set_page_config(page_title="龍九控股 Dashboard", layout="wide", page_icon="🧭")

BASE = Path(__file__).parent.resolve()
SNAPSHOT_PATH = BASE / "snapshot.json"
MOAT_REPORT_PATH = BASE / "moat_report_2026-07-18.json"
DAILY_ANALYSIS_PATH = BASE / "daily_analysis.json"
DECISIONS_PATH = BASE / "dashboard_decisions.json"


# ===== helpers =====

@st.cache_data
def load_json(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if data else fallback
    except Exception:
        return fallback


def fmt_twd(v: float) -> str:
    if v >= 1_0000_0000:
        return f"{v/1_0000_0000:.2f} 億"
    if v >= 1_0000:
        return f"{v/1_0000:.1f} 萬"
    return f"{v:,.0f}"


def save_decision(key: str, action: str, item: str) -> None:
    decisions = load_json(DECISIONS_PATH, {"decisions": []})
    decisions.setdefault("decisions", []).append({
        "timestamp": datetime.now().isoformat(),
        "key": key,
        "action": action,
        "item": item,
    })
    DECISIONS_PATH.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")


# ===== fallback data =====

FALLBACK_SNAPSHOT = {
    "total_assets": 50689930,
    "total_liabilities": 22000000,
    "net_worth": 28689930,
    "monthly_expense": 141958,
    "monthly_income": 218102,
    "rent_monthly_actual": 80100,
    "high_yield_savings_total": 3071343,
    "debt_ratio": "43.4%",
    "funds_breakdown": {
        "路博邁5G_累積": 235840,
        "路博邁5G_月配": 87790,
        "0050連結_A不配息": 103415,
        "0050連結_B配息": 44914,
        "統一奔騰": 83279,
        "台中銀台灣優惠": 46264,
        "台新美日台半導體": 647977,
    },
}

FALLBACK_MOAT = {
    "runway_months": 357.1,
    "liquid_runway_months": 15.5,
    "coverage_ratio": 0.5643,
    "debt_ratio_pct": 43.4,
    "semiconductor_exposure_pct": 63.7,
    "alert": ["RED: passive income < monthly expense"],
}

FALLBACK_ANALYSIS = {
    "date": "2026-07-18",
    "market": {"summary": "台股 -5.4%，費半 -4.3%，AI 需求疑慮升溫"},
    "buffett": {"recommendation": "半導體曝險偏高，建議分批減碼台積電相關"},
    "cto": {"risk": "半導體集中度 >70%，波動率上升"},
}


# ===== sidebar =====

with st.sidebar:
    st.markdown("## 🧭 龍九控股")
    page = st.radio(
        "頁面",
        ["Home", "Moat", "Audit", "Decision", "Intel"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    st.caption(f"資料日期：{datetime.now().strftime('%Y-%m-%d')}")
    st.caption("真值優先：MB > snapshot.json")
    st.markdown("---")
    st.caption("本地動態儀表板 v1.0\n資料來源：snapshot.json\n真值等级：MB > snapshot")


# ===== Home =====

if page == "Home":
    st.markdown("## 🏠 資產護城河總覽")
    snapshot = load_json(SNAPSHOT_PATH, FALLBACK_SNAPSHOT)
    moat_report = load_json(MOAT_REPORT_PATH, {"moat": FALLBACK_MOAT})
    moat = moat_report.get("moat", FALLBACK_MOAT)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("總資產", fmt_twd(snapshot.get("total_assets", 0)))
    with col2:
        st.metric("淨資產", fmt_twd(snapshot.get("net_worth", 0)))
    with col3:
        st.metric("Runway", f"{moat.get('runway_months', 0):.1f} 月")
    with col4:
        coverage = moat.get("coverage_ratio", 0)
        st.metric("被動覆蓋率", f"{coverage:.1%}", delta=f"{'🔴' if coverage < 1.0 else '🟢'}")

    st.markdown("---")
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Liquid Runway", f"{moat.get('liquid_runway_months', 0):.1f} 月")
    with col6:
        st.metric("負債比", f"{moat.get('debt_ratio_pct', 0):.1f}%")
    with col7:
        semi = moat.get("semiconductor_exposure_pct", 0)
        st.metric("半導體曝險", f"{semi:.1f}%", delta=f"{'🔴' if semi > 70 else '🟢'}")
    with col8:
        alerts = moat.get("alert", [])
        st.metric("Alerts", len(alerts), delta=f"{'🔴' if alerts else '🟢'}")

    st.markdown("---")
    st.markdown("### 資產配置")
    allocation = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    for name, pct in allocation.items():
        st.progress(pct / 100, text=f"{name}: {pct}%")

    st.markdown("---")
    st.markdown("### Balancer 建議")
    balancer = moat_report.get("balancer", {})
    actions = balancer.get("actions", [])
    if actions:
        for a in actions:
            st.warning(f"[{a.get('priority','')}] {a.get('action','')}：{a.get('target','')} — {a.get('reason','')}")
    else:
        st.success("目前資產結構健康，無需再平衡")

# ===== Moat =====

elif page == "Moat":
    st.markdown("## ⛱️ 資產護城河指標")
    moat_report = load_json(MOAT_REPORT_PATH, {"moat": FALLBACK_MOAT})
    moat = moat_report.get("moat", FALLBACK_MOAT)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Runway 月數")
        runway = moat.get("runway_months", 0)
        liquid_runway = moat.get("liquid_runway_months", 0)
        st.bar_chart({"總 Runway": runway, "Liquid Runway": liquid_runway})

    with c2:
        st.markdown("### 覆蓋率 vs 負債比")
        coverage = moat.get("coverage_ratio", 0)
        debt = moat.get("debt_ratio_pct", 0) / 100
        st.bar_chart({"coverage_ratio": coverage, "debt_ratio": debt})

    st.markdown("---")
    st.markdown("### 半導體曝險")
    semi = moat.get("semiconductor_exposure_pct", 0)
    threshold = 70.0
    delta_color = "inverse" if semi > threshold else "normal"
    st.metric("半導體曝險", f"{semi:.1f}%", delta=f"threshold {threshold}%", delta_color=delta_color)

    st.markdown("---")
    st.markdown("### Alerts")
    alerts = moat.get("alert", [])
    if alerts:
        for a in alerts:
            st.error(a)
    else:
        st.success("無 alerts")

# ===== Audit =====

elif page == "Audit":
    st.markdown("## 🗓️ 每週資產防禦審計")
    st.info("首次審計：2026-07-24（五）17:00")
    st.markdown("### 審計規則")
    st.markdown("1. master_ledger 與 snapshot.json 數值對位")
    st.markdown("2. fund_station 相較上週五的增減")
    st.markdown("3. Runway / Coverage / Debt 的趨勢")
    st.markdown("4. ops_logs 歷史矛盾偵測")
    st.markdown("---")
    st.markdown("### 最近審計")
    st.markdown("- 7/24 待首次執行")
    st.markdown("- 往後每週五 17:00 自動執行")

# ===== Decision =====

elif page == "Decision":
    st.markdown("## 🎯 決策閘門（Human-in-the-loop）")
    moat_report = load_json(MOAT_REPORT_PATH, {"balancer": {}})
    balancer = moat_report.get("balancer", {})
    actions = balancer.get("actions", [])

    if not actions:
        st.success("目前無待決策事項")
    else:
        for idx, a in enumerate(actions, 1):
            with st.expander(f"[{a.get('priority','')}] {a.get('action','')} — {a.get('target','')}", expanded=True):
                st.write(f"**原因**：{a.get('reason','')}")
                st.write(f"**幅度**：{a.get('amount_pct', 0)}%")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("✅ 核准", key=f"approve_{idx}"):
                        save_decision(f"action_{idx}", "approved", a.get("action", ""))
                        st.success(f"已核准：{a.get('action','')}")
                with col_b:
                    if st.button("⏸️ 延後", key=f"reject_{idx}"):
                        save_decision(f"action_{idx}", "deferred", a.get("action", ""))
                        st.warning(f"已延後：{a.get('action','')}")

    st.markdown("---")
    st.markdown("### 決策歷史")
    decisions = load_json(DECISIONS_PATH, {"decisions": []}).get("decisions", [])
    if decisions:
        for d in decisions[-10:]:
            st.write(f"- {d['timestamp'][:19]}：{d['action']} {d['item']}")
    else:
        st.info("尚無決策記錄")

# ===== Intel =====

elif page == "Intel":
    st.markdown("## 🌍 市場情報總覽")
    daily_analysis = load_json(DAILY_ANALYSIS_PATH, FALLBACK_ANALYSIS)
    intel = daily_analysis.get("intel", [])
    if intel:
        for item in intel[-5:]:
            ts = item.get("timestamp", "")
            title = item.get("title", "")
            with st.expander(f"{ts[:19]} — {title}"):
                for kp in item.get("key_points", []):
                    st.write(f"- {kp}")
    else:
        st.info("尚無情報")

    st.markdown("---")
    st.markdown("### 市場信号")
    signals = daily_analysis.get("signals", {})
    if signals:
        for k, v in signals.items():
            st.write(f"- {k}: {v}")
    else:
        st.info("尚無信号")
