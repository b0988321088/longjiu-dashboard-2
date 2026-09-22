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
    "weekly_report_": (".html", None),
    "dynamic_monthly_review_": (".html", "month"),
    "emergency_report_": (".html", None),
    "retirement_plan_": (".html", None),
    "rebalance_summary_": (".md", None),
    "buffett_cto_report_": (".md", None),
    "industry_penetration_": (".png", None),
    "risk_factor_penetration_": (".png", None),
}

# 模板佔位符 → 檔名前綴（glob 由前綴+副檔名推導）
PLACEHOLDER_PREFIX = {
    "__RADAR_REPORT__": "radar_report_",
    "__ASSET_DIFF__": "asset_diff_",
    "__BUFFETT_MD__": "buffett_cto_report_",
    "__DAILY_REPORT__": "daily_report_v2_",
    "__CEO_DASH__": "ceo_dashboard_",
    "__AUDIT_DASH__": "audit_dashboard_",
    "__EMERGENCY__": "emergency_report_",
    "__INDUSTRY_PNG__": "industry_penetration_",
    "__PEN_REPORT__": "penetration_report_",
    "__REBALANCE_DASH__": "rebalance_dashboard_",
    "__REBALANCE_EVAL__": "rebalance_eval_",
    "__REBALANCE_MD__": "rebalance_summary_",
    "__RISK_PNG__": "risk_factor_penetration_",
    "__WEEKLY__": "weekly_report_",
    "__WEEKLY_REVIEW__": "dynamic_weekly_review_",
    "__MONTHLY_REVIEW__": "dynamic_monthly_review_",
    "__MONTHLY_REPORT__": "monthly_report_",
    "__RETIREMENT_HTML__": "retirement_plan_",
    # 2026-09-22 移除 __RATE_HIKE_REPORT__（使用者核准）：模板「升息情境」按鈕已撤，
    # 產生器 build_rate_hike_dashboard.py 亦在 cleanup_utils.STALE_PY 淘汰名單內。
}

# 非「前綴+*+副檔名」形式的特殊圖樣
PLACEHOLDER_FIXED = {
    "__DECISION_CARD__": "*_card_*.html",       # 保單轉換卡等：檔名不固定前綴
    "__REFINANCE_PPTX__": "grand_pivot_deck.pptx",  # 固定檔名（無日期）
}


def link_patterns():
    """給 update_dashboard_links 用：(前綴, 副檔名, 規則) 清單（保持插入順序）。"""
    return [(p, ext, rule) for p, (ext, rule) in PREFIX_RULES.items()]


def build_link_map():
    """給 build_dashboard 用：佔位符 → glob 圖樣。"""
    m = {}
    for ph, prefix in PLACEHOLDER_PREFIX.items():
        ext = PREFIX_RULES.get(prefix, (".html", None))[0]
        m[ph] = f"{prefix}*{ext}"
    m.update(PLACEHOLDER_FIXED)
    return m


def all_placeholder_keys():
    return set(PLACEHOLDER_PREFIX) | set(PLACEHOLDER_FIXED)


if __name__ == "__main__":
    print(f"前綴 {len(PREFIX_RULES)} 組｜佔位符 {len(all_placeholder_keys())} 個")
    for ph, pat in sorted(build_link_map().items()):
        print(f"  {ph:24s} → {pat}")
