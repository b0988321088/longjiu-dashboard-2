"""dividend_caliber.py — 配息分類「單一口徑」正典（2026-09-23 定案）。

背景：同一條分類規則曾同時存在 4 份副本（build_dashboard / build_investment_performance /
run_daily / dividend_tracker），各自漂移 → 8 月 58 元（安聯基金被算成保單）與
7 月 22,459 元（「ETF＋基金合計」被當成股票實收）兩次口徑事故。
本檔為唯一實作，任何報表／追蹤器一律呼叫 bucket_of()，禁止各自再寫一份。

回傳值（正典桶）
  'etf'    ETF／證券配息（條目名以 "ETF" 開頭）
  'ins'    保單配息（名稱含「保單」「第一金」，或含「安聯」但名稱不含「基金」）
  'fund'   基金配息（其餘含「基金」／「配息」／「撥回」者）
  'oneoff' 一次性（台灣特品現金股息等；不計入常態三桶）

顯示對照（各頁維持既有口徑，本檔不改變任一頁現況）
  儀表板三桶      etf→etf、ins→ins、fund→fund、oneoff→other（另列，不計入三桶）
  投資績效頁/月報  etf→股票、oneoff→股票、ins→保單、fund→基金
  日報 run_daily   etf/oneoff→ETF 桶、ins→保單、fund→基金
  配息 breakdown   etf→etf、ins→(安聯/第一金)、fund→fund、oneoff→oneoff（另計，不進三桶）

⚠️ 順序有意義（勿調換）：先認「一次性」→ 再認 ETF 樣式 → 再認保單（先看代號樣式）→
最後才認「基金」。舊版把「安聯」判斷放最前面，會讓「基金配息 安聯收益AMg7」被歸保單。
"""

# 一次性條目（不計入常態三桶；各報表依上表對照顯示）
ONEOFF_KEYS = ("台灣特品", "現金股息")

# 台股 ETF 代碼（Moneybook 原始明細辨識用；見 classify_mb_memo）
ETF_CODES = ("00981a", "00713", "00918", "00919", "0050", "006208", "00878", "00888",
             "00984a", "00983d", "009823", "009824", "0056", "00646")


def bucket_of(name) -> str:
    """配息條目名 → 正典桶（'etf' / 'ins' / 'fund' / 'oneoff'）。"""
    n = str(name or "")
    if "台灣特品" in n or "現金股息" in n:
        return "oneoff"
    if n.startswith("ETF"):
        return "etf"
    # 保單：先認代號樣式（保單／第一金），再看「安聯但名稱不含基金」
    if ("保單" in n) or ("第一金" in n) or ("安聯" in n and "基金" not in n):
        return "ins"
    if ("基金" in n) or ("配息" in n) or ("撥回" in n):
        return "fund"
    return "oneoff"


def classify_mb_memo(memo) -> str:
    """Moneybook 原始明細描述 → 正典桶（供 dividend_tracker 記錄命名用）。

    Moneybook 的 ETF 配息寫成「媒體轉入 - 基金配息00981afund」，沒有 "ETF" 字樣，
    只能靠代碼辨識；但同名含「連結」（如「基金配息 元大0050連結A」＝ETF 連結基金）
    是真基金配息，不得誤判為 ETF。
    """
    import re
    m = str(memo or "")
    if "台灣特品" in m or "現金股息" in m:
        return "oneoff"
    for code in ETF_CODES:
        if re.search(code + r"(?!連結)", m, re.IGNORECASE):
            return "etf"
    return bucket_of(m)
