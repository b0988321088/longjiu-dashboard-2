"""links_config.py — 儀表板連結設定的【唯一來源】（2026-09-22 建立）

## 為什麼要有這支（實際事故）
`update_dashboard_links._LINK_PATTERNS`（只改 href、不整頁重建）與
`build_dashboard._link_map`（整頁重建時注入連結）原本各自維護一份清單，
新增按鈕時漏改一邊 → 那顆按鈕就永遠停在舊檔（`rebalance_eval_` 就是這樣壞掉的，
而且沒人看得出來，因為另一份清單「看起來有涵蓋」）。

改成兩邊都從這裡生成後，漏改不再是「跨檔同步」問題，而是單檔自洽問題。

## 兩張表
- `PREFIX_RULES`：檔名前綴 → (副檔名, 顯示規則)。給「只刷新 href」用。
- `PLACEHOLDER_PREFIX`：模板佔位符 → 檔名前綴。給整頁重建用（glob = 前綴 + `*` + 副檔名）。
- `PLACEHOLDER_FIXED`：非「前綴+副檔名」形式的固定檔名／特殊圖樣。

## 新增一顆按鈕時（三處，缺一就會被 check_dashboard_sync 第 11 項擋下）
1. `index_template.html` 放 `<a href="__XX__">`
2. 本檔的 `PREFIX_RULES` 加前綴
3. 本檔的 `PLACEHOLDER_PREFIX` 加佔位符 → 前綴
"""
import datetime
import re
from pathlib import Path

# 檔名前綴 → (副檔名, 顯示規則)；rule="month" 表示標籤要帶（N月）
PREFIX_RULES = {
    "daily_report_v2_": (".html", None),
    "asset_diff_": (".html", None),
    "rebalance_dashboard_": (".html", None),
    "rebalance_eval_": (".html", None),
    "audit_dashboard_": (".html", None),
    "ceo_dashboard_": (".html", None),
    "dynamic_weekly_review_": (".html", None),
    "monthly_report_": (".html", None),
    "radar_report_": (".html", None),
    "penetration_report_": (".html", None),
    "structural_health_": (".html", None),
    "weekly_report_": (".html", None),
    "dynamic_monthly_review_": (".html", "month"),
    "emergency_report_": (".html", None),
    "retirement_plan_": (".html", None),
    "rebalance_summary_": (".md", None),
    "buffett_cto_report_": (".md", None),
    "industry_penetration_": (".png", None),
    "risk_factor_penetration_": (".png", None),
    "tender_intel_": (".html", None),  # 2026-11-03 標案情報（對手分析＋報價基準）
    "stress_test_": (".html", None),   # 2026-11-06 股災壓力測試
    "national_fund_": (".html", None),  # 2026-11-07 國安基金護盤（機制＋買超清單）
}

# 模板佔位符 → 檔名前綴（glob 由前綴+副檔名推導）
PLACEHOLDER_PREFIX = {
    "__NATFUND__": "national_fund_",
    "__RADAR_REPORT__": "radar_report_",
    "__ASSET_DIFF__": "asset_diff_",
    "__BUFFETT_MD__": "buffett_cto_report_",
    "__DAILY_REPORT__": "daily_report_v2_",
    "__CEO_DASH__": "ceo_dashboard_",
    "__AUDIT_DASH__": "audit_dashboard_",
    "__EMERGENCY__": "emergency_report_",
    "__INDUSTRY_PNG__": "industry_penetration_",
    "__PEN_REPORT__": "penetration_report_",
    "__STRUCT_HEALTH__": "structural_health_",
    "__REBALANCE_DASH__": "rebalance_dashboard_",
    "__REBALANCE_EVAL__": "rebalance_eval_",
    "__REBALANCE_MD__": "rebalance_summary_",
    "__RISK_PNG__": "risk_factor_penetration_",
    "__WEEKLY__": "weekly_report_",
    "__WEEKLY_REVIEW__": "dynamic_weekly_review_",
    "__MONTHLY_REVIEW__": "dynamic_monthly_review_",
    "__MONTHLY_REPORT__": "monthly_report_",
    "__RETIREMENT_HTML__": "retirement_plan_",
    "__TENDER_INTEL__": "tender_intel_",  # 2026-11-03 標案情報
    "__STRESS_REPORT__": "stress_test_",   # 2026-11-06 股災壓力測試
    # 2026-09-22 移除 __RATE_HIKE_REPORT__（使用者核准）：模板「升息情境」按鈕已撤，
    # 產生器 build_rate_hike_dashboard.py 亦在 cleanup_utils.STALE_PY 淘汰名單內。
}

# 非「前綴+*+副檔名」形式的特殊圖樣
PLACEHOLDER_FIXED = {
    "__DECISION_CARD__": "*_card_*.html",       # 保單轉換卡等：檔名不固定前綴
    "__REFINANCE_PPTX__": "grand_pivot_deck.pptx",  # 固定檔名（無日期）
    "__COST_PAGE__": "cost.html",               # AI 費用頁（固定檔名：永遠指向最新，不產生舊檔）
    "__MTD_PAGE__": "mtd_performance.html",     # 本月績效頁（固定檔名：每日重產，永遠最新）
    "__PERF_MONTHLY__": "performance_monthly.html",  # 投資績效｜月度比較（固定檔名，2026-10-03 新增）
}


def link_patterns():
    """給 update_dashboard_links 用：(前綴, 副檔名, 規則) 清單（保持插入順序）。"""
    return [(p, ext, rule) for p, (ext, rule) in PREFIX_RULES.items()]


def build_link_map():
    """給 build_dashboard 用：佔位符 → glob 圖樣。

    2026-09-22 審查修正（fail-loud）：前綴若不在 PREFIX_RULES，以前會靜默回退成 .html
    → 對 .md/.png 類（__BUFFETT_MD__ / __REBALANCE_MD__ / __INDUSTRY_PNG__ / __RISK_PNG__）
    會悄悄產生錯誤圖樣、連結靜默壞掉。改為直接 raise，讓錯誤在產出階段就炸出來。
    """
    _missing = sorted({p for p in PLACEHOLDER_PREFIX.values() if p not in PREFIX_RULES})
    if _missing:
        raise KeyError(
            "PLACEHOLDER_PREFIX 使用的前綴未定義於 PREFIX_RULES（會產生錯誤 glob）: "
            + ", ".join(_missing)
        )
    m = {}
    for ph, prefix in PLACEHOLDER_PREFIX.items():
        ext = PREFIX_RULES[prefix][0]
        m[ph] = f"{prefix}*{ext}"
    m.update(PLACEHOLDER_FIXED)
    return m


def all_placeholder_keys():
    return set(PLACEHOLDER_PREFIX) | set(PLACEHOLDER_FIXED)


# ── 今日交付物連結（2026-11-10 新增：單一連結判準）────────────────────────────
# 為什麼要有：`data_closeout_commit.py`（22:38 收尾）與 `_audit_closeout.py`（22:40 稽核）
# 原本都只把 `index.html` 的 href 當「正式交付物」清單。但當日報表常只被「當日日報」連到，
# 而且寫成 Pages 絕對 URL（`https://<帳號>.github.io/<repo>/x.html`）→ 兩支都掃不到
# → 台股版緊急報告每晚漏收、線上 404，隔天早上才手動補（2026-11-06、11-09 實例）。
# 這裡把「誰算交付物」收斂成單一函式：首頁連結 ∪ 今日報表內的當日連結。
PAGES_ABS_MARKERS = ("b0988321088.github.io/longjiu-dashboard-2",)


def normalize_link(u: str) -> str:
    """href → repo 相對路徑；外部站點、mailto、javascript、錨點、目錄一律回空字串。"""
    u = str(u or "").split("#")[0].split("?")[0].strip()
    if not u or u.startswith(("#", "mailto:", "javascript:", "tel:")):
        return ""
    for m in PAGES_ABS_MARKERS:
        if u.startswith(("https://" + m, "http://" + m)):
            u = u.split(m, 1)[1].lstrip("/")
            break
    if u.startswith(("http://", "https://", "//")):
        return ""
    while u.startswith("./"):
        u = u[2:]
    if not u or u.endswith("/"):
        return ""
    return u


def html_links(path) -> set:
    """讀一個本機 HTML，回傳正規化後的相對連結集合（讀不到回空集合，不拋錯）。"""
    try:
        html = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return {n for n in (normalize_link(h) for h in re.findall(r'href="([^"]+)"', html)) if n}


def today_deliverable_links(base=".", date_str: str | None = None) -> set:
    """今日正式交付物的相對路徑集合。

    ＝ `index.html` 的全部連結 ∪ 檔名含當日日期的報表內的「檔名含當日日期」連結。
    後者只收含日期戳的目標：無日期戳的檔（cost.html、index.html…）是長期資產，
    不是每晚變動的交付物；把它們全拉進來會讓候選集暴增並誤收暫存檔。
    """
    b = Path(base)
    date_str = date_str or datetime.date.today().isoformat()
    out = set(html_links(b / "index.html"))
    for rep in sorted(b.glob(f"*_{date_str}.html")):
        for link in html_links(rep):
            if date_str in Path(link).name:
                out.add(link)
    return out


if __name__ == "__main__":
    print(f"前綴 {len(PREFIX_RULES)} 組｜佔位符 {len(all_placeholder_keys())} 個")
    for ph, pat in sorted(build_link_map().items()):
        print(f"  {ph:24s} → {pat}")
