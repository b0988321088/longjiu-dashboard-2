# -*- coding: utf-8 -*-
"""台股緊急應變完整版渲染器（通用自動版，2026-09-03 建立）
從 data/emergency_llm_analysis.json 渲染兩版 HTML：
  emergency_report_{date}.html (Railway 版) + emergency_taiex_report_{date}.html (GitHub 版)
日期自動取自 JSON 的 generated_at → 13:00 cron 寫完 JSON 後直接跑本檔，
把 emergency_1330 stub 換成完整版（9/3 13:00 stub 殘留事故的根治；9/1 同案用日期版修過一次）
含 INC-134 穿透注入（任何產生 emergency_report_{today}.html 的腳本都必須含穿透卡）
用法：python gen_emergency_taiex_auto.py
"""
import json, re, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT_IN_JSON = BASE / "data" / "emergency_llm_analysis.json"
DEFAULT_OUT_DIR = BASE
TODAY = datetime.date.today().isoformat()
NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

CSS = """
:root{--bg:#0b0f17;--card:#131a26;--line:#1f2937;--txt:#e5e7eb;--mut:#9ca3af;--up:#34d399;--down:#f87171;--acc:#60a5fa;--gold:#fbbf24;--warn:#fb923c;}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--txt);font-family:"Segoe UI","PingFang TC","Microsoft JhengHei",sans-serif;padding:24px;line-height:1.75;}
.wrap{max-width:1020px;margin:0 auto;}
.hd{border:1px solid var(--line);border-radius:14px;padding:22px 26px;background:linear-gradient(135deg,#101828,#0b0f17);margin-bottom:18px;}
.hd h1{font-size:24px;letter-spacing:1px;color:#fff;}
.hd .sub{color:var(--mut);font-size:13px;margin-top:6px;}
.badge{display:inline-block;background:#7c3aed33;border:1px solid #7c3aed;color:#c4b5fd;border-radius:20px;padding:2px 12px;font-size:12px;margin-left:8px;vertical-align:middle;}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0;}
.kpi{flex:1;min-width:148px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-align:center;}
.kpi .v{font-size:19px;font-weight:700;margin-top:2px;}
.kpi .l{color:var(--mut);font-size:12px;}
.up{color:var(--up);} .down{color:var(--down);} .flat{color:var(--mut);} .warn{color:var(--warn);}
.sec{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 24px;margin-bottom:16px;}
.sec h2{font-size:18px;color:var(--acc);border-left:4px solid var(--acc);padding-left:10px;margin-bottom:12px;}
.sec p{margin:6px 0;}
.alert{background:#f8717133;border:1px solid #f87171;color:#fca5a5;border-radius:10px;padding:10px 14px;margin:10px 0;font-weight:600;}
.pen{background:linear-gradient(135deg,#101828,#131a26);border:1px solid var(--gold);border-radius:14px;padding:16px 22px;margin:14px 0 18px;color:var(--gold);}
.pen h3{font-size:15px;margin-bottom:6px;color:var(--gold);}
.pen p{font-size:13px;color:var(--txt);}
.foot{color:var(--mut);font-size:12px;text-align:center;margin-top:24px;}
"""


def load_report(path=None):
    p = Path(path) if path else DEFAULT_IN_JSON
    if not p.is_file():
        raise SystemExit(f"[FAIL] 找不到分析 JSON：{p}")
    d = json.loads(p.read_text(encoding="utf-8"))
    gen = d.get("generated_at") or NOW
    return gen, d.get("full_report", ""), d.get("market_snapshot", {}), str(d.get("source", ""))


def label_from_source(source: str):
    """INC-214b：標題／副標依「分析標的」（JSON source 欄位）決定，不依產出時段。

    13:00 gate 與 21:30 固定班共用同一支渲染器；手動補跑／延遲／跨時段執行時，
    用小時分白會把美股分析標成台股（2026-09-18 實踩）。回傳 (標的, 副標)。
    """
    s = source or ""
    if "美股" in s:
        return "美股", "分析標的：美股開盤"
    if "台股" in s:
        return "台股", "分析標的：台股盤中"
    return "", "分析標的：未標示（source 缺漏）"


def split_sections(text):
    parts = re.split(r"(【[一二三四五六七八]、[^】]+】)", text)
    secs, cur_title, cur_body = [], None, []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if re.fullmatch(r"【[一二三四五六七八]、[^】]+】", p):
            if cur_title:
                secs.append((cur_title, cur_body))
            cur_title, cur_body = p, []
        else:
            cur_body.append(p)
    if cur_title:
        secs.append((cur_title, cur_body))
    return secs


def _fmt(v):
    if isinstance(v, (int, float)):
        return f"{v:,.2f}"
    return str(v)


def kpis_from_snapshot(snap):
    """相容兩種 market_snapshot 格式：dict（{value,chg,cls}）或扁平數值（TWII + TWII_chg_pct）。"""
    if not snap:
        return ""
    _pref = [("加權指數", "TWII"), ("台積電", "TSMC_2330"), ("費半", "SOX"),
             ("道瓊", "DJI"), ("S&P", "SPX"), ("納指", "IXIC"), ("US30Y", "US30Y")]
    parts = ['<div class="kpis">']
    for label, key in _pref:
        if key not in snap:
            continue
        v = snap[key]
        if isinstance(v, dict):  # 舊 kpi 結構
            cls = v.get("cls", "flat")
            parts.append(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{v.get("value","")}</div><div class="l">{v.get("chg","")}</div></div>')
        else:  # 扁平數值
            chg = snap.get(f"{key}_chg_pct")
            try:
                cls = "up" if float(chg) > 0 else ("down" if float(chg) < 0 else "flat")
                chg_s = f"{float(chg):+.2f}%"
            except (TypeError, ValueError):
                cls, chg_s = "flat", ("" if chg is None else str(chg))
            parts.append(f'<div class="kpi"><div class="l">{label}</div><div class="v {cls}">{_fmt(v)}</div><div class="l">{chg_s}</div></div>')
    parts.append("</div>")
    return "".join(parts)


def pen_card():
    """INC-134 穿透注入：穿透真值卡（snapshot.json penetration.actual_pct）"""
    try:
        _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _pp = _snap.get("penetration", {}).get("actual_pct", {})
        _tt = _snap.get("total_assets", 0)
        return (f'<div class="pen"><h3>📊 資產穿透（{TODAY}）</h3>'
                f'<p>總資產 <b>{_tt:,.0f}</b> TWD｜台股 {_pp.get("台股市值型成長",0):.1f}%｜'
                f'美股 {_pp.get("美股市值型成長",0):.1f}%｜防守 {_pp.get("防守型配息",0):.1f}%｜'
                f'債券 {_pp.get("債券",0):.1f}%｜現金 {_pp.get("現金/安全網",0):.1f}%</p></div>')
    except Exception as _e:
        print(f"⚠️ 穿透注入失敗: {_e}")
        return ""


def pledge_card():
    """質押壓力卡（2026-10-30）：整體與單池分開呈現，來源＝snapshot 派生欄位。"""
    try:
        _snap = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
        _c = _snap.get("cathay_pledge_0911") or {}
        ov = _c.get("LTV壓力情境") or {}
        sp = _c.get("單池壓力_20261030") or {}
        if not ov:
            return ""
        parts = [f'<div class="pen"><h3>🏦 質押壓力（整體三檔加總）</h3>',
                 f"<p>現況 <b>{ov.get('現況','')}</b>｜{ov.get('追繳線70%','')}</p>"]
        for k in ("跌20%", "跌30%", "跌35%"):
            if ov.get(k):
                parts.append(f"<p>{k}：{ov[k]}</p>")
        if ov.get("追繳公式"):
            parts.append(f"<p>追繳公式：{ov['追繳公式']}</p>")
        if ov.get("緩衝現況"):
            parts.append(f"<p>緩衝：{ov['緩衝現況']}</p>")
        parts.append("</div>")
        rows = (sp or {}).get("逐檔") or {}
        if rows:
            parts.append('<div class="pen"><h3>⚠️ 單池風險（與整體分開判定，E2 未解除）</h3>')
            if sp.get("結論"):
                parts.append(f"<p><b>{sp['結論']}</b></p>")
            for name, r in rows.items():
                parts.append(
                    f"<p>{name[:16]}：市值 {r['市值']:,.0f}／分配借款 {r['分配借款']:,.0f}｜"
                    f"單池跌30% <b>{r['單池跌30%_LTV_pct']:.2f}%</b>／"
                    f"同期加總 {r['同期加總_跌30%_pct']:.2f}%</p>")
            if sp.get("假設"):
                parts.append(f"<p>假設：{sp['假設']}</p>")
            parts.append("</div>")
        return "".join(parts)
    except Exception as _e:
        print(f"⚠️ 質押壓力卡注入失敗: {_e}")
        return ""


def render(kpis_html, sec_html, pen_html, title, sub):
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head><body><div class="wrap">
<div class="hd"><h1>{title}<span class="badge">緊急應變</span></h1>
<div class="sub">{sub}</div></div>
{kpis_html}
{pen_html}
{pledge_card()}
{sec_html}
<div class="foot">龍九控股內部報告｜僅供決策參考，非投資建議｜資料時間 {NOW} 台北｜Yahoo Finance chart API 即時 + daily_analysis briefing + us30y_state + snapshot.json 穿透數據</div>
</div></body></html>"""


def build(in_json=None, out_dir=None):
    global TODAY, NOW
    gen, report, snap, source = load_report(in_json)
    if gen and len(gen) >= 10:
        TODAY = gen[:10]
        NOW = gen
    secs = split_sections(report)
    n = len(report)
    print(f"[JSON] full_report len = {n} chars (generated_at={gen})")
    print(f"[標的] source={source!r} → {label_from_source(source)[0] or '(未標示)'}")
    assert n > 1500, f"full_report too short: {n}"
    _label, _sub_label = label_from_source(source)
    _title = f"{_label}緊急應變報告 {TODAY}｜龍九控股" if _label else f"緊急應變報告 {TODAY}｜龍九控股"
    _sub = f"資料時間 {NOW} 台北｜{_sub_label}｜完整分析（六大章節）"

    kpis_html = kpis_from_snapshot(snap)
    sec_html = "".join(
        f'<div class="sec"><h2>{title}</h2>' + "".join(f"<p>{p}</p>" for p in paras if p) + "</div>"
        for title, paras in secs)
    pen_html = pen_card()
    # 輸出位置：預設＝repo 根（與舊版逐位元相同）；--out-dir 時改寫到指定目錄（F1 第二階段）
    if out_dir:
        _od = Path(out_dir)
        _od.mkdir(parents=True, exist_ok=True)
    else:
        _od = None
    if _od is not None:
        rail = _od / f"emergency_report_{TODAY}.html"
        gh = _od / f"emergency_taiex_report_{TODAY}.html"
    else:
        rail = BASE / f"emergency_report_{TODAY}.html"
        gh = BASE / f"emergency_taiex_report_{TODAY}.html"
    rail.write_text(render(kpis_html, sec_html, pen_html, _title, _sub), encoding="utf-8")
    gh.write_text(render(kpis_html, sec_html, pen_html, _title, _sub), encoding="utf-8")
    print(f"[IN ] {Path(in_json) if in_json else DEFAULT_IN_JSON}")
    print(f"[OUT] {rail.parent}")
    print(f"[HTML] {rail.name} ({rail.stat().st_size:,} bytes)")
    print(f"[HTML] {gh.name} ({gh.stat().st_size:,} bytes)")
    print("[DONE]", NOW)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        description="緊急應變報告渲染（無參數時行為與舊版相同：讀 data/emergency_llm_analysis.json、寫 repo 根）")
    ap.add_argument("--in-json", default=None, help="分析 JSON 路徑（預設 data/emergency_llm_analysis.json）")
    ap.add_argument("--out-dir", default=None, help="輸出目錄（預設 repo 根；F1 交接請指向 staging）")
    a = ap.parse_args(argv)
    build(in_json=a.in_json, out_dir=a.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
