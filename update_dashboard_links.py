"""update_dashboard_links.py — 刷新主儀表板 index.html「重要連結」區，指向各類最新檔案。

- 只更新 href 指向 + 月報月份標籤，**絕不刪除任何舊檔**（舊版報告保留在 repo 供回溯）。
- 日報/差異/週報/月報/穿透/緊急/再平衡/巴菲特/圖表 全部以「glob 掃描最新檔名」解析，
  解決 template 用 __TODAY__ 造成的壞連結（例：週日沒有週報 → 指向不存在的 8/23 週報）。
- 用法：python update_dashboard_links.py [--check]
  --check 只印出將更新的對應，不寫檔（驗證用）。

掛載點：regenerate_report.py（產完 index.html 後）與 daily_deploy.py（push 前）皆呼叫本腳本。
"""
from __future__ import annotations
import glob
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
INDEX = BASE / "index.html"

# (檔名前綴, 副檔名, 顯示規則)
_LINK_PATTERNS = [
    ("daily_report_v2_", ".html", None),
    ("asset_diff_", ".html", None),
    ("rebalance_dashboard_", ".html", None),
    ("penetration_report_", ".html", None),
    ("weekly_report_", ".html", None),
    ("dynamic_monthly_review_", ".html", "month"),
    ("emergency_report_", ".html", None),
    ("rebalance_summary_", ".md", None),
    ("buffett_cto_report_", ".md", None),
    ("industry_penetration_", ".png", None),
    ("risk_factor_penetration_", ".png", None),
]


def _latest(prefix: str, ext: str) -> str | None:
    """回傳目錄中符合 prefix*ext 的最新檔名（依檔名排序，YYYY-MM-DD 檔名自然排序=時間序）。"""
    pats = sorted(glob.glob(str(BASE / f"{prefix}*{ext}")))
    return Path(pats[-1]).name if pats else None


def _month_label(name: str) -> str:
    m = re.search(r"_(\d{4})-(\d{2})\.", name)
    return f"（{int(m.group(2))}月）" if m else ""


def refresh_links(html: str, verbose: bool = False) -> str:
    start = html.find("<!-- 🔗 重要連結")
    # 區塊結尾 = 下一個區塊註解（風險提示），比找 </div> 可靠（連結區內部有多層 div）
    end_marker = html.find("<!-- 🚨", start)
    end = end_marker if end_marker != -1 else html.find("</div>", start)
    if start == -1 or end == -1:
        print("⚠️ 找不到重要連結區塊，跳過")
        return html
    block = html[start:end]

    def _repl(m: re.Match) -> str:
        whole, href = m.group(0), m.group(1)
        name = Path(href).name
        for prefix, ext, rule in _LINK_PATTERNS:
            if name.startswith(prefix):
                latest = _latest(prefix, ext)
                if not latest:
                    return whole
                if latest == name and rule != "month":
                    return whole
                new = whole.replace(href, latest)
                if rule == "month":
                    new = re.sub(r"（\d+月）", _month_label(latest), new)
                if verbose:
                    print(f"  {name} → {latest}")
                return new
        return whole

    new_block = re.sub(r'href="([^"]+)"', _repl, block)
    return html[:start] + new_block + html[end:]


def main() -> int:
    check = "--check" in sys.argv
    html = INDEX.read_text(encoding="utf-8")
    new = refresh_links(html, verbose=True)
    if new == html:
        print("ℹ️ 重要連結已是最新，無變化")
        return 0
    if check:
        print("✅ --check 模式：不寫檔（上面為將更新的對應）")
        return 0
    INDEX.write_text(new, encoding="utf-8")
    print("✅ index.html 重要連結已刷新（舊檔保留）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
