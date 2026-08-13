# -*- coding: utf-8 -*-
"""台股緊急應變 2026-08-14 — LLM 分析 → data/emergency_llm_analysis.json + emergency_report_2026-08-14.html"""
import json, datetime, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
TODAY = "2026-08-14"
GEN_AT = "2026-08-14 13:16"

FULL_REPORT = """【一、市場概況】
台股（8/10 收盤即時）：加權指數 44,894.06（+668.15，+1.51%），早盤一度漲逾 700 點直逼 45,000 大關、站穩季線；「6 千金」齊亮燈，台達電等權值股領漲，櫃買指數同步走強（+2.7%）。台積電 2,385（+0.63%）。今日為強漲日而非重挫，緊急應變機制例行啟動，確認無系統性風險。
美股（8/7 收）：道瓊 54,036.93（+0.28%）/ 納指 26,690.62（+1.30%）/ S&P 500 7,757.64（+0.62%）/ 費半 12,356.79（+2.56%）。
亞股：日經早盤 +1,324 點（AI/半導體領漲）；韓股連 7 週跌後，散戶資金轉戰美股 AI/半導體。
債市與恐慌：US30Y 5.22%（FRED 8/6 最新）、US10Y 4.69%、10Y-2Y 利差 0.44pp；VIX 14.9，情緒平靜。

【二、重大事件分析】
1. 美國 7 月非農優於預期 → 費半強彈 +2.56%，台指夜盤狂飆逾 700 點（TechNews/CNA，高可信）。就業韌性緩解衰退疑慮，風險資產全面受惠。
2. 台積電 × 索尼合資 1 兆日圓（約 63.2 億美元）生產下一代影像感測器、2029 年量產（日經/中央社，高可信）。台積電再添長期訂單能見度，AI 邏輯 + 感測雙引擎，直接支撐台股權值。
3. 美股「壞消息不斷卻越漲越勇」：資金湧入半導體 ETF、高收益債與比特幣，美銀牛熊指標升至 2021 年以來高點（鉅亨網，中高）。風險偏好全面回溫，惟 CMoney 示警槓桿 ETF 與日內行情失控風險升溫，追高需克制。
4. SK 海力士單週大跌 15% 後，里昂證券稱「最壞情況已過」、股東回報更清晰，維持跑贏大盤（Yahoo/CLSA，中高）。記憶體庫存去化近尾聲的領先訊號。
5. 美國 6 月 CPI 3.5%（低於預期 3.8%）、核心 2.6%：通膨降溫路徑未變；惟 Fed 官員鷹派言論使高利率環境未解，長天期殖利率高檔為結構性逆風。

【三、持倉關聯分析】
台股市值型成長 1,556,969 TWD：0050 收 103.85（+0.97%），台積電權重約五成，TSMC-Sony 利多 + 大盤強漲直接受惠；006208 同邏輯。帳面獲利豐厚，維持持有、不追高。
防守型配息 3,056,792 TWD：00878 33.29（+1.46%）、00919 與大盤同步走強，除權息旺季配息流正常，續持。
美股市值型成長 5,940,503 TWD：費半 +2.56%、S&P 續創高，淨值受惠；惟佔比 35.3% 超標，不追高、逢反彈分批減碼。
債券 2,984,511 TWD（00983D 等）：US30Y 5.22% 仍在 5.20% 防禦線上方 → 維持底倉、暫緩新增。
保單基金（安聯 AI 收益成長/貝萊德科技）：費半強彈 + 日股 AI 半導體大漲，淨值短線受惠；AI 資本開支長線邏輯不變，hold。
現金/安全網 3,289,381 TWD（19.5%）：緩衝充足，高於 6 個月生活費底線。

【四、資產配置透視】
資料：snapshot.json penetration.actual_twd（2026-08-14）｜臨時階段目標：美股 30 / 台股 23.5 / 防守 19 / 債券 13 / 現金 14.5。
- 台股市值型成長：1,556,969 TWD / 9.3% / 目標 23.5% / -14.2pp（最終 SAA 15%）
- 美股市值型成長：5,940,503 TWD / 35.3% / 目標 30% / +5.3pp
- 防守型配息：3,056,792 TWD / 18.2% / 目標 19% / -0.8pp
- 債券：2,984,511 TWD / 17.7% / 目標 13% / +4.7pp
- 現金/安全網：3,289,381 TWD / 19.5% / 目標 14.5% / +5.0pp
總投資部位 16,828,156 TWD。解讀：台股低配屬「逐步架構」預期內（8 月初主動降台股槓桿），非缺口失控；現金+債券超標 = 防禦緩衝充足，靜待 8/15 國泰撥款後依 B 方案執行再平衡。

【五、巴菲特/蒙格式建議】
台股 9.3% vs 臨時目標 23.5%：低配屬預期，僅回檔小單分批低吸（單筆 ≤5 萬）、不強迫貼齊；今日強漲日更不追高。
美股 35.3% 超標 5.3pp：不急砍，逢反彈分批減碼收斂至 30%。
防守 18.2% 合理（第一優先維持）；債券 17.7% 超標，不新增。
兩條底線：現金 ≥85 萬；US30Y 無連 3 日 <5.20% 不開放市值大額進場。
「別人貪婪我恐懼」：牛熊指標升至 2021 年高點，紀律優先、以時間換空間。

【六、風控檢查】
US30Y 5.22%（FRED 8/6）：高於 5.20% 防禦線 → 模式A 防禦持續（不新增債券、00983D 維持底倉）；低於 5.30% 凍結紅線（差距僅 8bp）→ 債券未凍結，列首要監控指標。
VIX 14.9：無恐慌，市場未定性為系統性風險。
國泰核貸：8/15 撥款 1,200 萬 @2.6%（地政設定 8/7 完成寄回）→ 撥款後先清償 800 萬高息債 → 買 500 萬債券（B方案）→ 餘 400 萬分批部署；同步申請專業投資人（3,000 萬門檻，缺口 178 萬可併配偶）。
其他：三筆永豐房貸正常、大義街已清償；四大信用卡列管正常；配息 SOP hold（無 30 分鐘轉換風險）。
總結：今日強漲、無新風險；維持「防禦為先、分批再平衡」總基調，重點監控 US30Y 與 8/15 撥款後資金紀律。"""

# === INC-134 動態覆蓋：穿透段用最新 snapshot（8/11 修正：禁止硬編碼舊值）===
def _refresh_penetration(report_text: str) -> str:
    """用 snapshot penetration 真值重建報告中穿透段落"""
    try:
        snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        pen = snap.get("penetration", {})
        atwd = pen.get("actual_twd", {})
        apct = pen.get("actual_pct", {})
        total = snap.get("total_assets", 0)
        targets = pen.get("targets", {})

        tw = atwd.get("台股市值型成長", 0); tw_p = apct.get("台股市值型成長", 0)
        us = atwd.get("美股市值型成長", 0); us_p = apct.get("美股市值型成長", 0)
        df = atwd.get("防守型配息", 0); df_p = apct.get("防守型配息", 0)
        bd = atwd.get("債券", 0); bd_p = apct.get("債券", 0)
        ca = atwd.get("現金/安全網", 0); ca_p = apct.get("現金/安全網", 0)

        tw_t = targets.get("台股市值型目標", 15); us_t = targets.get("美股市值型目標", 30)
        df_t = targets.get("配息型目標", 20); bd_t = targets.get("債券型目標", 20); ca_t = targets.get("現金目標", 15)

        lines = []
        lines.append(f"- 台股市值型成長：{tw:,.0f} TWD / {tw_p:.1f}% / 目標 {tw_t}% / {tw_p-tw_t:+.1f}pp（最終 SAA {tw_t}%）")
        lines.append(f"- 美股市值型成長：{us:,.0f} TWD / {us_p:.1f}% / 目標 {us_t}% / {us_p-us_t:+.1f}pp")
        lines.append(f"- 防守型配息：{df:,.0f} TWD / {df_p:.1f}% / 目標 {df_t}% / {df_p-df_t:+.1f}pp")
        lines.append(f"- 債券：{bd:,.0f} TWD / {bd_p:.1f}% / 目標 {bd_t}% / {bd_p-bd_t:+.1f}pp")
        lines.append(f"- 現金/安全網：{ca:,.0f} TWD / {ca_p:.1f}% / 目標 {ca_t}% / {ca_p-ca_t:+.1f}pp")
        lines.append(f"總投資部位 {total:,.0f} TWD。")
        pen_section = "\n".join(lines)

        import re as _re
        # INC-134 修正（2026-08-14）：匹配實際格式「台股市值型成長 1,556,969 TWD：...」
        # 舊 regex「- 台股市值型成長：...總投資部位」與實際格式不符 → 覆蓋不生效
        _pat = r"台股市值型成長\s+[\d,]+ TWD：.*?現金/安全網\s+[\d,]+ TWD.*?(?=\n|【|\Z)"
        _m = _re.search(_pat, report_text, flags=_re.S)
        if _m:
            report_text = report_text.replace(_m.group(0), pen_section)
        else:
            # fallback：舊格式
            report_text = _re.sub(
                r"- 台股市值型成長：.*?總投資部位 [\d,]+ TWD。",
                pen_section,
                report_text,
                flags=_re.S,
            )
        # INC-134 強化（8/11）：目標標題行也用 snapshot targets 動態（禁硬編碼臨時目標）
        _target_title = f"資料：snapshot.json penetration.actual_twd（{TODAY}）｜目標：台股 {tw_t} / 美股 {us_t} / 防守 {df_t} / 債券 {bd_t} / 現金 {ca_t}。"
        report_text = _re.sub(
            r"資料：snapshot\.json penetration\.actual_twd（[^）]*）｜.*?。",
            _target_title,
            report_text,
        )
        # 巴菲特建議段舊臨時目標 → 動態目標（8/11）
        report_text = _re.sub(
            r"台股 [\d.]+% vs 臨時目標 [\d.]+%",
            f"台股 {tw_p:.1f}% vs 目標 {tw_t}%",
            report_text,
        )
        report_text = _re.sub(
            r"美股 [\d.]+% 超標 [\d.]+pp",
            f"美股 {us_p:.1f}% 超標 {us_p-us_t:+.1f}pp",
            report_text,
        )
        return report_text
    except Exception:
        return report_text

FULL_REPORT = _refresh_penetration(FULL_REPORT)


def main():
    # 1) JSON
    payload = {
        "generated_at": GEN_AT,
        "source": "台股緊急應變 cron (deepseek-v4-flash)",
        "full_report": FULL_REPORT,
    }
    out_json = BASE / "data" / "emergency_llm_analysis.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ JSON written: {out_json.name} | full_report len = {len(FULL_REPORT)} chars")

    # 2) 獨立 HTML（Railway/GitHub 版）
    CSS = """:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--mut:#8b949e;
--red:#f85149;--grn:#3fb950;--yel:#d29922;--blu:#58a6ff}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--tx);font-family:'Segoe UI','Noto Sans TC','Microsoft JhengHei',sans-serif;line-height:1.7;padding:24px}
.wrap{max-width:960px;margin:0 auto}
header{border:1px solid var(--line);border-radius:12px;padding:22px 26px;background:linear-gradient(135deg,#1a2332,#161b22);margin-bottom:20px}
header h1{font-size:25px;letter-spacing:1px}
header .sub{color:var(--mut);margin-top:6px;font-size:14px}
.alert-bar{margin:14px 0 4px;padding:10px 16px;border-radius:8px;background:rgba(63,185,80,.12);border:1px solid rgba(63,185,80,.4);font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 24px;margin-bottom:16px}
.card h2{font-size:18px;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--line);color:var(--blu)}
.card p{margin:6px 0;font-size:14.5px}
.card li{margin:5px 0;font-size:14.5px}
.kpi{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.kpi .box{flex:1;min-width:150px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.kpi .box .lbl{font-size:12px;color:var(--mut)} .kpi .box .val{font-size:19px;font-weight:700;margin-top:2px}
footer{color:var(--mut);font-size:12px;text-align:center;margin-top:22px}"""

    kpis = [
        ("台股加權", "44,894", "+1.51%", "var(--grn)"),
        ("台積電 2330", "2,385", "+0.63%", "var(--grn)"),
        ("費半 SOX", "12,357", "+2.56%", "var(--grn)"),
        ("S&P 500", "7,758", "+0.62%", "var(--grn)"),
        ("US30Y", "5.22%", "防禦5.20/紅線5.30", "var(--yel)"),
        ("VIX", "14.9", "平靜", "var(--grn)"),
    ]
    kpi_html = "".join(
        f"<div class='box'><div class='lbl'>{l}</div><div class='val' style='color:{c}'>{v}</div><div class='lbl'>{s}</div></div>"
        for l, v, s, c in kpis
    )

    # 依【X、】章節切分
    sections = re.split(r"(?=【[一二三四五六]、)", FULL_REPORT.strip())
    cards = []
    for sec in sections:
        if not sec.strip():
            continue
        head, _, body = sec.partition("\n")
        body_html = body.strip().replace("\n", "<br>")
        cards.append(f'<div class="card"><h2>{head}</h2><p>{body_html}</p></div>')

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🐉 龍九控股 — 台股緊急應變報告 {TODAY}</title>
<style>{CSS}</style></head><body><div class="wrap">
<header>
<h1>🐉 龍九控股 — 台股緊急應變報告</h1>
<div class="sub">📅 {GEN_AT}｜Chief Reporter + 台股危機應變官｜六大章節完整版｜資料：Yahoo Finance / FRED / Google News RSS</div>
<div class="alert-bar">📈 台股 +1.51% 強漲收 44,894（早盤漲逾 700 點挑戰 45,000）｜費半 +2.56%｜台積電×索尼 1 兆日圓影像感測器｜US30Y 5.22% 防禦模式｜無系統性風險</div>
</header>
<div class="kpi">{kpi_html}</div>
{''.join(cards)}
<footer>🐉 龍九控股 emergency response ｜ generated {GEN_AT} ｜ 數據來源：Yahoo Finance 即時、FRED DGS30/DGS10、Google News RSS（CNA/UDN/TechNews/鉅亨/日經/中央社）、snapshot.json</footer>
</div></body></html>"""

    out_html = BASE / f"emergency_report_{TODAY}.html"
    out_html.write_text(html, encoding="utf-8")
    print(f"✅ HTML written: {out_html.name} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
