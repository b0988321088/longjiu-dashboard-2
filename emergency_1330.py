"""龍九台股緊急應變 13:00 — 刷新情報 + 彙整 + 三份產出"""
import os
import subprocess, sys, json, re
from pathlib import Path
from datetime import datetime, date
import requests # Added for Yahoo Finance API call

LJ = Path.home() / "Desktop" / "longjiu_system"
today = __import__("datetime").date.today().isoformat()

def run_step(label, cmd, timeout=120):
    ts = datetime.now().strftime("%H%M")
    print(f"[{ts}] {label}...", end=" ", flush=True)
    try:
        r = subprocess.run(cmd, cwd=str(LJ), capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            # 2026-09-29 CIO minor：rc=3 ＝ 推送閘門（未經審查/未落紀錄）刻意擋下，不是程式錯誤；
            # 原訊息一律印「失敗」→ 無法區分，還被當成管線壞掉。
            if r.returncode == 3:
                print("⏸ 待審（推送閘門擋下，非程式錯誤）")
            else:
                print(f"❌ 失敗\n{r.stderr[:200]}")
            return r.returncode
        out = r.stdout.strip()
        if out:
            for l in out.split("\\n")[-3:]:
                print(f"  {l}")
        print("✅")
        return 0
    except subprocess.TimeoutExpired:
        print("❌ 超時")
        return False

def fetch_etf_data(symbol):
    """從 Yahoo Finance 抓取 ETF 即時數據"""
    try:
        r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=5d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        c = [x for x in q.get("close",[]) if x]
        v = [x for x in q.get("volume",[]) if x]
        if len(c) < 2: return None
        return {"close": c[-1], "prev": c[-2], "change": c[-1]-c[-2],
                "pct": (c[-1]-c[-2])/c[-2]*100, "volume": v[-1]}
    except Exception as e:
        print(f"⚠️ 抓取 {symbol} 失敗: {e}")
        return None

def fetch_taiex():
    """從 Yahoo Finance 抓取即時台股指數"""
    try:
        r = requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?interval=1d&range=5d",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200: return None
        d = r.json()
        q = d["chart"]["result"][0]["indicators"]["quote"][0]
        c = [x for x in q.get("close",[]) if x]
        if len(c) < 2: return None
        return {"close": c[-1], "prev": c[-2], "change": c[-1]-c[-2],
                "pct": (c[-1]-c[-2])/c[-2]*100}
    except Exception as e:
        print(f"⚠️ 抓取台股指數失敗: {e}")
        return None

def generate_emergency_report(taiex_data=None, etf_0050_data=None, etf_00878_data=None):
    """產出緊急應變報告"""
    snap = json.loads((LJ / "snapshot.json").read_text("utf-8"))
    items = [("證券",snap.get("securities_total_market_value",0)),
             ("保單",snap.get("insurance_current_value",0)),
             ("基金",snap.get("fund_market_value",0)),
             ("現金",snap.get("cash_total",0))]
    total = sum(v for _,v in items)
    rows = "".join(f"<tr><th>{k}</th><td>{v:,}</td></tr>" for k,v in items)
    
    market_overview = ""
    if taiex_data:
        level = "🔴 重挫" if taiex_data["pct"] < -2 else ("🟠 下跌" if taiex_data["pct"] < -1 else "🟢 正常")
        market_overview += f'''
        <div class="alert {'' if taiex_data["pct"] >= -1 else 'alert-red'}">
            <h3>📈 市場概況：台股加權指數</h3>
            <p>{level}：{taiex_data["close"]:,.2f}點 ({taiex_data["change"]:+.2f} / {taiex_data["pct"]:+.2f}%)</p>
        </div>
        '''
    else:
        market_overview = '<div class="warn">⚠️ 即時台股資料無法取得，以下為本機最後記錄</div>'

    holdings_analysis = ""
    if taiex_data and (etf_0050_data or etf_00878_data):
        holdings_analysis += "<h3>📊 持股關聯分析</h3>"
        if etf_0050_data:
            impact_0050 = "受到較大影響" if etf_0050_data["pct"] < taiex_data["pct"] * 0.8 else "與大盤走勢一致"
            holdings_analysis += f"<p><b>0050.TW (元大台灣50)</b>: {etf_0050_data['close']:,.2f}點 ({etf_0050_data['change']:+.2f} / {etf_0050_data['pct']:+.2f}%)，{impact_0050}。</p>"
        if etf_00878_data:
            impact_00878 = "受到較大影響" if etf_00878_data["pct"] < taiex_data["pct"] * 0.8 else "與大盤走勢一致"
            holdings_analysis += f"<p><b>00878.TW (國泰永續高股息)</b>: {etf_00878_data['close']:,.2f}點 ({etf_00878_data['change']:+.2f} / {etf_00878_data['pct']:+.2f}%)，{impact_00878}。</p>"
        holdings_analysis += "<p><b>009816/00984A (上櫃+ETF)</b>: 由於資料無法即時抓取，請手動關注其相關新聞與走勢。</p>"

    buffett_advice = """
    <h3>🧠 巴菲特/蒙格式建議</h3>
    <ul>
        <li><b>安全邊際</b>：市場波動時，優質資產的價格可能被低估，這是建立安全邊際的好時機。評估您持股的內在價值，避免恐慌性拋售。</li>
        <li><b>管理費侵蝕</b>：長期持有 ETF 需注意管理費對複利效果的侵蝕。定期審視您的投資組合，確保費用合理。</li>
        <li><b>集中度風險</b>：檢視您的資產配置是否過於集中在某些類別或標的。分散投資可以降低單一事件的衝擊。</li>
    </ul>
    """

    action_recommendation = """
    <h3>💡 應變行動建議</h3>
    <ul>
        <li><b>減碼</b>：若資金有其他更高報酬的用途，或持股已達預設停利點，可考慮適度減碼。</li>
        <li><b>持有</b>：若持股仍符合長期投資策略，且資金無急用，建議繼續持有，避免追高殺低。</li>
        <li><b>加碼</b>：若優質資產因市場恐慌而出現明顯折價，且您有閒置資金，可考慮分批加碼。</li>
    </ul>
    """
    
    # 2026-09-03 血淚：極簡版 HTML 也不得覆寫完整版 — sync_all 的台股緊急應變步驟
    # 跑 emergency_1330.py 會用 stub 蓋掉 agent 產的 9.4KB 完整 HTML（JSON 有防護、HTML 沒有）
    _skip_html = False
    try:
        _jf_html = LJ / "data" / "emergency_llm_analysis.json"
        if _jf_html.exists():
            _old_html = json.loads(_jf_html.read_text(encoding="utf-8"))
            if len(str(_old_html.get("full_report", ""))) > 1500:
                _skip_html = True
    except Exception:
        pass
    if _skip_html:
        print("⏭️ 既有完整分析（full_report>1500），極簡版 HTML 跳過覆寫")

    html = f'''<!DOCTYPE html><html lang="zh-TW"><head><meta charset="utf-8">
    <title>🚨 台股緊急應變 {today}</title>
    <style>
    body{{font-family:-apple-system,sans-serif;max-width:800px;margin:20px auto;padding:0 15px;color:#1d1d1f}}

    h1{{color:#d32f2f;font-size:28px;text-align:center;margin-bottom:20px}}

    h3{{color:#424242;font-size:20px;margin-top:25px;margin-bottom:10px;border-bottom:1px solid #eeeeee;padding-bottom:5px}}

    .alert{{background:#ffebee;padding:15px 20px;border-radius:8px;margin:15px 0;font-size:17px;font-weight:600;border-left:5px solid #d32f2f;color:#d32f2f}}

    .alert-red{{background:#ffebee;border-color:#d32f2f;color:#d32f2f}}

    .warn{{background:#fff3e0;padding:15px 20px;border-radius:8px;margin:15px 0;border-left:5px solid #f57c00;color:#f57c00}}

    table{{width:100%;border-collapse:collapse;margin:15px 0}}

    th,td{{padding:12px;text-align:right;border-bottom:1px solid #e5e5ea}}

    th{{text-align:left;font-weight:600;background:#f9f9f9}}

    ul{{list-style-type:disc;margin-left:20px;padding-left:0}}

    li{{margin-bottom:8px;line-height:1.6}}

    b{{color:#333}}

    .meta{{font-size:14px;color:#6e6e73;margin-top:20px;padding-top:15px;border-top:1px solid #e5e5ea;text-align:center}}

    </style></head><body>
    <h1>🚨 台股緊急應變報告</h1>
    <p class="meta">產生時間：{datetime.now().strftime('%Y-%m-%d %H:%M')} ｜ 資料源：{('Yahoo Finance' if taiex_data else 'snapshot.json')}</p>
    {market_overview}
    {holdings_analysis}
    <h3>📊 資產配置</h3>
    <table><tr><th>資產類別</th><th>金額 TWD</th></tr>{rows}
    <tr><th>合計</th><td>{total:,}</td></tr></table>
    {buffett_advice}
    {action_recommendation}
    <p class="meta">⏰ 下次執行：下個交易日 13:00</p></body></html>'''
    if not _skip_html:
        (LJ / f"emergency_taiex_report_{today}.html").write_text(html, "utf-8")
        print(f"✅ 緊急應變報告已產出至 emergency_taiex_report_{today}.html")
    else:
        print(f"ℹ️ 保留既有 emergency_taiex_report_{today}.html（完整版）")
    # 同時存一份給 Railway 用的命名（LLM agent 版命名格式）
    # INC-134 穿透注入（2026-08-24 修正：13:00 台股版缺穿透真值 → check 失敗）
    # 2026-09-02 核准：改「即時重算」穿透（calc_penetration），不讀快取 actual_pct —
    # 快取在 sync_all 內由穿透報告步驟才寫入，順序顛倒時會用到上一輪舊值（9/2 實踩 3 次）
    try:
        import json as _json
        from update_all import calc_penetration as _calc_pen
        _snap = _json.loads((LJ / "snapshot.json").read_text(encoding="utf-8"))
        _tt = _snap.get("total_assets", 0)
        _pen = _calc_pen(_snap.get("cash_total", 0) or 0, _snap.get("insurance_total", 0) or 0,
                         _snap.get("securities_total_market_value", 0) or 0, _snap.get("fund_market", 0) or 0,
                         snap=_snap)
        _p = {k: (round(v / _tt * 100, 1) if _tt else 0) for k, v in _pen.items() if k != "_meta"}
        _pen_card = f"<h3>📊 資產穿透（{today}）</h3><p>總資產 <b>{_tt:,.0f}</b> TWD｜台股 {_p.get('台股市值型成長',0):.1f}%｜美股 {_p.get('美股市值型成長',0):.1f}%｜防守 {_p.get('防守型配息',0):.1f}%｜債券 {_p.get('債券',0):.1f}%｜現金 {_p.get('現金/安全網',0):.1f}%</p>"
        html = html.replace("</body>", _pen_card + "</body>")
    except Exception as _e:
        # fallback：讀快取 actual_pct（重算失敗時仍可用）
        try:
            import json as _json2
            _snap2 = _json2.loads((LJ / "snapshot.json").read_text(encoding="utf-8"))
            _pp = _snap2.get("penetration", {}).get("actual_pct", {})
            _tt = _snap2.get("total_assets", 0)
            _pen_card = f"<h3>📊 資產穿透（{today}）</h3><p>總資產 <b>{_tt:,.0f}</b> TWD｜台股 {_pp.get('台股市值型成長',0):.1f}%｜美股 {_pp.get('美股市值型成長',0):.1f}%｜防守 {_pp.get('防守型配息',0):.1f}%｜債券 {_pp.get('債券',0):.1f}%｜現金 {_pp.get('現金/安全網',0):.1f}%</p>"
            html = html.replace("</body>", _pen_card + "</body>")
        except Exception as _e2:
            print(f"⚠️ 穿透注入失敗: {_e2}")
    if not _skip_html:
        (LJ / f"emergency_report_{today}.html").write_text(html, "utf-8")
        print(f"✅ Railway 版已同步至 emergency_report_{today}.html")
    else:
        print(f"ℹ️ 保留既有 emergency_report_{today}.html（完整版）")


ts = datetime.now().strftime("%H%M")
print(f"\\n[{ts}] 🚨 台股緊急應變啟動")

# Main execution flow
run_step("刷新情報", [sys.executable, str(LJ / "daily_intel.py")], 60)
run_step("彙整情報", [sys.executable, str(LJ / "compile_intel.py")], 30)

taiex_realtime_data = fetch_taiex()
etf_0050_data = fetch_etf_data("0050.TW")
etf_00878_data = fetch_etf_data("00878.TW")
generate_emergency_report(taiex_realtime_data, etf_0050_data, etf_00878_data)

run_step("更新 snapshot", [sys.executable, "-c",
    f"import json; p=r'{LJ}/snapshot.json'; s=json.loads(open(p).read()); print('snapshot 已讀取')"], 15)

# 寫入緊急應變分析 JSON（供日報第5章讀取）
# 新增：動態讀取 buffett_cto_report，注入 LLM 分析
def _get_llm_analysis_snippet(today_str: str) -> str:
    cto_report_path = LJ / f"buffett_cto_report_{today_str}.md"
    if not cto_report_path.exists():
        return "LLM 分析報告缺失，請確認 buffett_cto_analyzer.py 已執行。"
    try:
        content = cto_report_path.read_text(encoding="utf-8")
        buffett_match = re.search(r"巴菲特式思考（動態穿透模型）\n(.*?)CTO 技術視角", content, re.DOTALL)
        cto_match = re.search(r"CTO 技術視角\n(.*?)再平衡", content, re.DOTALL)
        
        snippet = ""
        if buffett_match:
            snippet += "【巴菲特式思考】\n" + buffett_match.group(1).strip() + "\n\n"
        if cto_match:
            snippet += "【CTO 技術視角】\n" + cto_match.group(1).strip() + "\n\n"
            
        snippet = re.sub(r"• 主要偏離：💻 科技 不足 -[0-9.]+pp", "", snippet)
        snippet = re.sub(r"• 總投資部位：[0-9,]+ TWD", "", snippet)
        snippet = "\n".join(line.strip() for line in snippet.splitlines() if line.strip())
        return snippet.strip()
    except Exception as e:
        print(f"⚠️ 讀取/解析 buffett_cto_report_{today_str}.md 失敗: {e}")
        return "LLM 分析報告讀取失敗。"

today_str = date.today().isoformat()
cto_report_snippet = _get_llm_analysis_snippet(today_str)

_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
_snap = json.loads((LJ / "snapshot.json").read_text("utf-8"))
_sec = _snap.get("securities_total_market_value", 0)
_taiex_line = ""
if taiex_realtime_data:
    _taiex_line = f"加權指數：{taiex_realtime_data['close']:,.2f}（{taiex_realtime_data['change']:+.2f} / {taiex_realtime_data['pct']:+.2f}%）"
_0050_line = ""
if etf_0050_data:
    _0050_line = f"0050：{etf_0050_data['close']:,.2f}（{etf_0050_data['change']:+.2f} / {etf_0050_data['pct']:+.2f}%）"
_00878_line = ""
if etf_00878_data:
    _00878_line = f"00878：{etf_00878_data['close']:,.2f}（{etf_00878_data['change']:+.2f} / {etf_00878_data['pct']:+.2f}%）"
_write = True
_analysis = {
    "generated_at": _ts,
    "source": "台股緊急應變",
    "full_report": (
        f"🚨 龍九控股 — 台股緊急應變報告 🚨\n"
        f"📅 {_ts}\n\n"
        f"【一、市場概況】\n{_taiex_line}\n{_0050_line}\n{_00878_line}\n\n"
        f"【二、持倉關聯】\n證券市值 {_sec:,} TWD\n\n"
        f"【三、資產配置】\n{cto_report_snippet}\n\n"
        f"【四、應變建議】\n市場波動時保持理性，避免恐慌性交易。\n"
        f"數據來源：Yahoo Finance"
    ),
}

_prev_txt = ""
try:
    _prev = json.loads((LJ / "data" / "emergency_llm_analysis.json").read_text(encoding="utf-8"))
    _prev_txt = str((_prev or {}).get("full_report", ""))
except Exception:
    _prev_txt = ""
_new_txt = _analysis["full_report"]
# 2026-09-13 INC-169：極簡版（<1500）不得覆蓋既有較完整分析（sync_all/非盤中重跑時曾把
# 六大章節完整分析蓋成 225 字元極簡版 → 日報第八章緊急應變資料消失）
if _prev_txt and len(_prev_txt) > max(1500, len(_new_txt)) and "六大章節" not in _new_txt and len(_new_txt) < 1500:
    _write = False
    print(f"⏭️ 既有完整分析 {len(_prev_txt)} 字元 > 本次極簡版 {len(_new_txt)} 字元 → 不覆寫（INC-169 防呆）")
if _write:
    # 修改 full_report 內容，加入 LLM 分析摘要
    _analysis["full_report"] = (
        f"🚨 龍九控股 — 台股緊急應變報告 🚨\n"
        f"📅 {_ts}\n\n"
        f"【一、市場概況】\n{_taiex_line}\n{_0050_line}\n{_00878_line}\n\n"
        f"【二、持倉關聯】\n證券市值 {_sec:,} TWD\n\n"
        f"【三、資產配置】\n{cto_report_snippet}\n\n"
        f"【四、應變建議】\n市場波動時保持理性，避免恐慌性交易。\n"
        f"數據來源：Yahoo Finance"
    )
    (LJ / "data" / "emergency_llm_analysis.json").write_text(
        json.dumps(_analysis, ensure_ascii=False, indent=2), "utf-8")
    print("✅ 緊急應變分析已寫入 data/emergency_llm_analysis.json")
# 2026-08-06 修正：run_daily.py 有停滯風險（buffett_cto_analyzer），改 regenerate_report.py 一鍵管線（含校準/日報/差異/儀表板/驗證/推送）
# 2026-09-23（INC-240 補記，CIO 審查 REJECT 必修）：
#   ①日報步驟 300s → 600s。理由：regenerate_report.py 現在推送後會跑「線上連結逐條驗 200」
#     （`check_dashboard_sync.py --post-push`，內部總預算 240s 硬停）＋ 管線本身約 110s，
#     300s 會在 Pages 建置較慢時把驗證砍掉，變成「推了但沒驗」。
#   ②原本完全不理 run_step 的回傳值 → 逾時（TimeoutExpired 會印 ❌ 超時）之後腳本照樣印
#     「✅ 緊急應變完成」＝假成功。改為收集三個步驟結果，任一失敗就以非 0 結束。
# ── 2026-10-15 P0-3（使用者裁決）──────────────────────────────────────────────
#   裁決要旨：「未明確授權時，緊急流程只能產生報告及列出待處理清單；不得提交或推送。」
#   修法：發布相關步驟由**單一函式 publish_plan()** 決定，未授權時計畫內不得含任何
#   commit／push／發布步驟；執行前後再以 _plan_violations() 做 fail-closed 自檢，
#   並明確印出「已略過推送」的語意（略過 ≠ 失敗，rc 記 0）。
#   另：審查只掃本檔字面會漏掉子程序（daily_deploy.py 內部才會 commit／push），
#   故此處改為「計畫層」可驗證 —— 見 tools/test_emergency_no_commit.py E8/E9。
_COMMIT_ENABLED = os.environ.get("LJ_EMERGENCY_COMMIT", "0") == "1"

# 具發布副作用（commit／push／Telegram）的腳本清單；本清單＝守門依據，新增者必須登記。
_PUBLISH_CAPABLE = ("daily_deploy.py", "auto_push.py", "evening_sync.py", "artifact_commit.py",
                    "safe_update.py", "four_source_sync.py", "regenerate_report.py")
# 例外：支援 --no-push 降級為「只產出、不提交」的腳本（INC-210）
_NO_PUSH_CAPABLE = {"regenerate_report.py": "--no-push"}


def publish_plan(commit_enabled: bool, root: Path, python_exe: str) -> list[tuple[str, list[str], int]]:
    """緊急應變執行計畫（2026-10-15 P0-3 單一決定點；純函式，供測試直接驗證）。

    未授權（commit_enabled=False）→ 計畫內**不得含**任何 commit／push／發布步驟：
      ‧ regenerate_report.py 一律帶 --no-push（產生檔案、不 commit、不 push）
      ‧ daily_deploy.py（日報／index 的 commit＋push＋Telegram）整步不列入
    授權（True）→ 恢復舊行為（推送步驟納入；推送仍受 auto_push.py 閘門管轄）。
    """
    _report_cmd = [python_exe, str(root / "regenerate_report.py")]
    if not commit_enabled:
        _report_cmd.append("--no-push")
    _plan: list[tuple[str, list[str], int]] = [
        ("日報+儀表板", _report_cmd, 600),
        ("差異分析", [python_exe, str(root / "asset_diff_monitor.py")], 60),
    ]
    if commit_enabled:
        _plan.append(("推送", [python_exe, str(root / "daily_deploy.py")], 600))
    return _plan


def _plan_violations(plan: list[tuple[str, list[str], int]], commit_enabled: bool = False) -> list[str]:
    """回傳計畫中「未降級卻具發布副作用」的步驟（fail-closed 自檢）。

    commit_enabled=False（未授權）：計畫內**不得**含任何未降級的發布步驟 → 一律違規。
    commit_enabled=True（已授權）：允許 `_AUTHORIZED_WHEN_ENABLED` 內的發布步驟（授權即為
      明示允許）；其餘未降級者仍視為違規 —— 授權不得成為塞入未預期發布腳本的通道。
      （2026-10-15 CIO blocking：原版不分授權模式一律判違規，導致 LJ_EMERGENCY_COMMIT=1
        的授權路徑被自檢必擋、永遠無法執行。）
    """
    _AUTHORIZED_WHEN_ENABLED = {"daily_deploy.py", "regenerate_report.py"}
    _bad: list[str] = []
    for _label, _cmd, _to in plan:
        for _arg in _cmd:
            _base = Path(str(_arg)).name
            if _base not in _PUBLISH_CAPABLE:
                continue
            if _NO_PUSH_CAPABLE.get(_base) and _NO_PUSH_CAPABLE[_base] in _cmd:
                continue
            if commit_enabled and _base in _AUTHORIZED_WHEN_ENABLED:
                continue
            _bad.append(f"{_label}:{_base}")
    return _bad


_plan = publish_plan(_COMMIT_ENABLED, LJ, sys.executable)
_viol = _plan_violations(_plan, _COMMIT_ENABLED)
if _viol:
    print(f"❌ 發布計畫含未授權的發布步驟（{_viol}）→ 中止（fail-closed，未執行任何步驟）")
    sys.exit(1)
_rcs: dict = {}
for _label, _cmd, _timeout in _plan:
    _rcs[_label] = run_step(_label, _cmd, _timeout)
if not _COMMIT_ENABLED:
    # 明確語意：推送步驟「未列入」而非失敗（略過 ≠ 失敗）；產物與待處理清單仍照常輸出。
    print("⏸ 推送步驟已略過（未授權：LJ_EMERGENCY_COMMIT 未開啟）→ 本次只產出報告與待處理清單")
    _rcs["推送"] = 0

# 2026-10-14 根因修復（TD-20261014-02）：
#   本路徑順序＝regenerate（有提交出口）→ asset_diff_monitor（步驟2，產物無出口）
#   → daily_deploy（步驟2.8 再跑 buffett_cto_analyzer 重寫報告，但只推日報/index）
#   ⇒ asset_diff_history.json 與 buffett_cto_report_{today}.md 的寫入落在最後一次提交之後：
#      22:40 收工稽核判「已追蹤未提交」，22:00 晚報又因「執行前已 dirty」把它們排除 → 每晚結構性殘留。
#   修法：收尾就地提交自家兩檔（白名單 stage／無變更不 commit），推送走 auto_push.py 唯一出口。
#   模板同 wrappers/cost_watch_close.py（22:30 費用帳本日結）。
_OWN_FILES = ("asset_diff_history.json", f"buffett_cto_report_{today}.md")

# ── 2026-10-15 B1（§4）使用者裁決：緊急應變路徑**預設不提交** ──────────────────
#   裁決原文要旨：「緊急應變只產出、不提交、不推送、不發布；驗證排程產出報告時不會自行提交」。
#   故本檔最後的收尾提交改為 **預設關閉**：未在環境變數明示 LJ_EMERGENCY_COMMIT=1 時，
#   _commit_own() 只列出待提交清單、不執行任何 git 寫入（add／commit／push 皆不呼叫）。
#   ⚠️ 開啟旗標＝恢復舊行為，**不代表取得發布授權**（推送仍受 auto_push.py 閘門管轄）。
#   （2026-10-15 P0-3：旗標另由 publish_plan() 決定發布步驟；此處不再重複定義 `_COMMIT_ENABLED`
#     —— 單一定義點在檔案上方，避免兩處定義漂移。）


def _commit_own() -> int:
    """收尾補提交（**2026-10-15 B1／§4 起預設停用**）：只碰自家兩檔；無變更即靜默略過。

    未設 LJ_EMERGENCY_COMMIT=1 → 只列印待提交清單並回 0（不呼叫任何 git 寫入）。
    回傳值語意不變（0＝無事／完成，1＝失敗），故呼叫端的 rc 彙總邏輯不受影響。
    """
    _files = [f for f in _OWN_FILES if (LJ / f).exists()]
    if not _files:
        print("自家產物不存在，略過提交")
        return 0
    if not _COMMIT_ENABLED:
        print("⏸ 自家產物待提交（本路徑預設只產出、不提交；LJ_EMERGENCY_COMMIT 未開啟）："
              + "、".join(_files))
        return 0

    def g(*a):
        return subprocess.run(["git", *a], cwd=str(LJ), text=True, capture_output=True)

    if g("add", "--", *_files).returncode != 0:
        print("⚠️ git add 自家產物失敗 → 不提交（fail-closed）")
        return 1
    _foreign = sorted(set(x for x in g("diff", "--cached", "--name-only").stdout.split() if x) - set(_files))
    if _foreign:
        # 只用 pathspec commit → 不會帶走他班已 stage 的檔；此處僅揭露、不 abort（避免因此製造殘留）
        print(f"ℹ️ index 另有他班已 stage 檔（不隨本次提交）：{_foreign}")
    c = g("commit", "-m", f"data: 13:00 應變產物 {today}（資產差異歷史＋巴菲特CTO報告）", "--", *_files)
    out = ((c.stdout or "") + (c.stderr or "")).strip()
    if c.returncode != 0:
        if "nothing to commit" in out or "no changes added" in out:
            print("自家產物無變更，略過提交")
            return 0
        print(out)
        return 1
    print(out.splitlines()[0] if out else "已提交自家產物")
    return subprocess.run([sys.executable, str(LJ / "auto_push.py"),
                           "--script", "emergency_1330.py"], cwd=str(LJ)).returncode


_ok_own = _commit_own()

_rcs["產物補提交"] = _ok_own
_failed = [n for n, rc in _rcs.items() if rc not in (0, 3)]
_blocked = [n for n, rc in _rcs.items() if rc == 3]
if _blocked:
    print(f"\n⏸ [{datetime.now().strftime('%H%M')}] 待審未推送：{'、'.join(_blocked)}（rc=3 推送閘門，非失敗）")
if _failed:
    print(f"\n❌ [{datetime.now().strftime('%H%M')}] 緊急應變未完成（失敗步驟：{'、'.join(_failed)}）")
    sys.exit(1)
if _blocked:
    sys.exit(3)

print(f"\n✅ [{datetime.now().strftime('%H%M')}] 緊急應變完成")
