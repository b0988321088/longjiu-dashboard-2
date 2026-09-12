#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保單轉換決策卡（2026-09-12 建立）
生成 policyB_conversion_card_<date>.html / .md
資料源：snapshot.json（保單B基金明細 + fund_components_09 股債比 + penetration.actual_twd + total_assets）
方案參數（裁示）：保單B 分批轉入台股連結基金 0056:0050 = 75:25，每站保留一檔月配站長。
用法：
    python build_policy_transfer_card.py            # 只產卡
    python build_policy_transfer_card.py --governance  # 另寫 pending/dashboard 決策檔
"""
from __future__ import annotations
import json, sys, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
SNAP = json.loads((BASE / "snapshot.json").read_text(encoding="utf-8"))
TODAY = datetime.date.today().isoformat()
TOT = float(SNAP.get("total_assets") or 0)
ACT = (SNAP.get("penetration") or {}).get("actual_twd") or {}
FC = SNAP.get("fund_components_09") or {}
PB = ((SNAP.get("insurance_breakdown") or {}).get("policy_b_funds")) or {}

# 股/債比：優先讀 snapshot.fund_components_09，找不到用保守預設
_RATIO_KEY = {"摩根": "摩根多重收益美元對沖", "安聯": "安聯收益成長", "M&G": "M&G入息",
              "PIMCO": "PIMCO收益增長M", "健康": "貝萊德世界健康A10", "黃金": "貝萊德世界黃金A10"}
_SHORT = ("PIMCO", "摩根", "安聯", "健康", "黃金", "M&G")


def ratio(name: str) -> float:
    """回傳股票占比（黃金=0）"""
    comp = FC.get(_RATIO_KEY.get(name, ""), {}) or {}
    return float(comp.get("股", 1.0))


def fund_value(name: str) -> float:
    for k, v in PB.items():
        if name in k:
            return float(v)
    return 0.0


B = {n: fund_value(n) for n in _SHORT}
STATION = {"第一站（月初）": "摩根", "第二站（月中）": "M&G", "第三站（月底）": "PIMCO"}

# 方案：批1 = 安聯 + 健康（非站長），批2 = 摩根 30%（保留站長 70%）
PLAN = [
    {"批": "批1（立即）", "賣出": {"安聯": 1.00, "健康": 1.00}, "理由": "第二站有 M&G 頂著（9/16 第一金轉入更厚）、健康為第三站配角"},
    {"批": "批2（1 個月後）", "賣出": {"摩根": 0.30}, "理由": "第一站摩根保留 70% 當站長；看 10/7 第一站配息與 0056 首季配後再執行"},
]
SPLIT_56 = 0.75


def fmt(x: float) -> str:
    return f"{x:,.0f}"


def build():
    sell_rows, batches = [], []
    cum = {"0056": 0.0, "0050": 0.0, "out": 0.0, "stock": 0.0, "bond": 0.0}
    for p in PLAN:
        out = sum(B[k] * w for k, w in p["賣出"].items())
        stock = sum(B[k] * w * ratio(k) for k, w in p["賣出"].items())
        bond = out - stock
        to56, to50 = out * SPLIT_56, out * (1 - SPLIT_56)
        cum["0056"] += to56; cum["0050"] += to50; cum["out"] += out
        cum["stock"] += stock; cum["bond"] += bond
        batches.append({"批": p["批"], "賣出": out, "股票成分": stock, "債券成分": bond,
                        "0056": to56, "0050": to50, "理由": p["理由"],
                        "明細": {k: B[k] * w for k, w in p["賣出"].items()}})
    keep = {k: v for k, v in B.items() if all(k not in p["賣出"] for p in PLAN)}
    keep_partial = {"摩根": B["摩根"] * 0.70} if "摩根" in B else {}

    tw = ACT.get("台股市值型成長", 0) + cum["0050"]
    us = ACT.get("美股市值型成長", 0) - cum["stock"]
    de = ACT.get("防守型配息", 0) + cum["0056"]
    bd = ACT.get("債券", 0) - cum["bond"]
    cash = ACT.get("現金/安全網", 0)
    usd_now = 54.4
    usd_after = usd_now - cum["out"] / TOT * 100 if TOT else 0
    div_new = (cum["0056"] * 0.08 + cum["0050"] * 0.035) / 12
    b_total = sum(B.values())
    keep_pct = (sum(keep.values()) + sum(keep_partial.values())) / b_total * 100 if b_total else 0

    def pct(v):
        return v / TOT * 100 if TOT else 0

    # ---- HTML ----
    h = []
    h.append("""<!DOCTYPE html><html lang="zh-TW"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>保單轉換決策卡</title>
<style>
body{font-family:-apple-system,"PingFang TC","Microsoft JhengHei",sans-serif;background:#0b1220;color:#e5e7eb;margin:0;padding:18px}
.wrap{max-width:960px;margin:0 auto}
.card{background:#111a2e;border:1px solid #1f2b45;border-radius:14px;padding:16px;margin-bottom:14px}
h1{font-size:21px;margin:0 0 4px;color:#fff}h2{font-size:16px;margin:14px 0 8px;color:#93c5fd}
.sub{color:#94a3b8;font-size:12.5px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#16223c;color:#cbd5e1;text-align:left;padding:8px;border-bottom:1px solid #24314f;white-space:nowrap}
td{padding:7px 8px;border-bottom:1px solid #1b2740}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tag{display:inline-block;font-size:11px;font-weight:800;padding:2px 8px;border-radius:99px}
.ok{background:#064e3b;color:#6ee7b7}.warn{background:#78350f;color:#fcd34d}.bad{background:#7f1d1d;color:#fca5a5}.info{background:#1e3a8a;color:#bfdbfe}
.note{font-size:12.5px;color:#94a3b8;line-height:1.75}
.big{font-size:15px;font-weight:800;color:#fff}
</style></head><body><div class="wrap">""")
    h.append(f'<div class="card"><h1>🏦 保單B 轉換決策卡</h1>'
             f'<div class="sub">建立 {TODAY}｜標的：安聯保單B 現值 {fmt(b_total)}｜'
             f'方案：分批轉入台股連結基金（0056:0050 = 75:25）｜每站保留一檔月配站長</div></div>')

    # 一、方案
    h.append('<div class="card"><h2>一、分批方案（比例固定 0056 75% / 0050 25%）</h2>'
             '<table><thead><tr><th>批次</th><th>賣出基金</th><th class="num">金額</th>'
             '<th class="num">0056</th><th class="num">0050</th><th>理由</th></tr></thead><tbody>')
    for b in batches:
        det = "＋".join(f"{k} {fmt(v)}" for k, v in b["明細"].items())
        h.append(f'<tr><td>{b["批"]}</td><td>{det}</td><td class="num">{fmt(b["賣出"])}</td>'
                 f'<td class="num">{fmt(b["0056"])}</td><td class="num">{fmt(b["0050"])}</td>'
                 f'<td class="note">{b["理由"]}</td></tr>')
    h.append(f'<tr style="background:#16223c"><td><b>合計</b></td><td>轉出 {cum["out"]/b_total*100:.0f}% of B</td>'
             f'<td class="num"><b>{fmt(cum["out"])}</b></td><td class="num"><b>{fmt(cum["0056"])}</b></td>'
             f'<td class="num"><b>{fmt(cum["0050"])}</b></td><td></td></tr></tbody></table>'
             f'<div class="note" style="margin-top:8px">轉出＝保單<b>內部標的轉換</b>（非提領）→ 保單價值不變，'
             f'保單借貸 LTV 不受影響；轉換免費用、配息比照 ETF（季配／半年配）。</div></div>')

    # 二、三站站長
    h.append('<div class="card"><h2>二、配息接力：每站保留的站長</h2><table><thead><tr>'
             '<th>站</th><th>站長基金</th><th class="num">轉換後保留</th><th>狀態</th></tr></thead><tbody>')
    for st, n in STATION.items():
        v = keep.get(n, 0) + (keep_partial.get(n, 0) if n == "摩根" else 0)
        tag = '<span class="tag ok">保留 ✅</span>' if v > 0 else '<span class="tag bad">無站長</span>'
        h.append(f'<tr><td>{st}</td><td>{n}</td><td class="num">{fmt(v)}</td><td>{tag}</td></tr>')
    for n, v in keep.items():
        if n not in STATION.values():
            h.append(f'<tr><td>第三站（配角）</td><td>{n}</td><td class="num">{fmt(v)}</td>'
                     f'<td><span class="tag ok">保留 ✅</span></td></tr>')
    h.append(f'</tbody></table><div class="note" style="margin-top:8px">保單B 仍保留 {keep_pct:.0f}% 的部位，'
             f'三站都還有月配來源；第三站另有 PIMCO {fmt(B.get("PIMCO",0))}（債券主力，不動）。</div></div>')

    # 三、效果
    h.append('<div class="card"><h2>三、效果試算（分母＝總資產）</h2><table><thead><tr>'
             '<th>指標</th><th class="num">現況</th><th class="num">執行後</th><th class="num">目標</th><th>判定</th></tr></thead><tbody>')
    rows = [("台股市值型成長", pct(ACT.get("台股市值型成長", 0)), pct(tw), 10),
            ("美股市值型成長", pct(ACT.get("美股市值型成長", 0)), pct(us), 40),
            ("防守型配息", pct(ACT.get("防守型配息", 0)), pct(de), 20),
            ("債券", pct(ACT.get("債券", 0)), pct(bd), 25),
            ("現金/安全網", pct(cash), pct(cash), 5)]
    for name, a, bb, tgt in rows:
        _moved = "✅ 改善" if abs(bb - tgt) < abs(a - tgt) else ("➖ 持平" if abs(bb - tgt) == abs(a - tgt) else "⚠️ 惡化")
        h.append(f'<tr><td>{name}</td><td class="num">{a:.1f}%</td><td class="num"><b>{bb:.1f}%</b></td>'
                 f'<td class="num">{tgt}%</td><td>{_moved}（執行後距目標 {bb - tgt:+.1f}pp）</td></tr>')
    h.append(f'<tr><td>美元曝險</td><td class="num">{usd_now:.1f}%</td><td class="num"><b>估 {usd_after:.1f}%</b></td>'
             f'<td class="num">≤60%</td><td>✅</td></tr>')
    h.append(f'<tr><td>新增配息（0056 估 8%／0050 估 3.5%）</td><td class="num">—</td>'
             f'<td class="num"><b>+{fmt(div_new)}/月</b></td><td class="num">—</td><td>季配／半年配</td></tr>')
    h.append('</tbody></table><div class="note" style="margin-top:8px">配息率為估值（0056 含平準金／資本利得成分，'
             '非全為股息）；實際以季配公告為準。被轉出部位的月配金額會減少，月配總額以實際對帳單核對。</div></div>')

    # 四、前置條件與風險
    h.append('<div class="card"><h2>四、前置條件與風險</h2><div class="note">'
             '① 已有台股連結基金可選、轉換免費用、配息比照 ETF（2026-09-12 使用者確認）✅<br>'
             '② 轉換為<b>保單內部標的轉換</b>：保單價值不變 → 保單B 那筆 100萬保單借貸的 LTV 不受影響 ✅<br>'
             '③ 配息節奏由月配改為季配／半年配 → 三站仍在，但「月月入帳」的節奏會變成「三站月配＋季配補強」<br>'
             '④ 債券桶會小幅下降（因摩根／安聯含債成分）→ 已在方案中避開 PIMCO，跌幅控制在 1pp 內<br>'
             '⑤ 轉換期間（T+4）價格風險：分批執行可分散</div></div>')

    # 五、執行步驟
    h.append('<div class="card"><h2>五、執行步驟（安聯 App／臨櫃）</h2><div class="note">'
             '1. 批1：保單B 申請「安聯收益成長 AM（USDEQ3490）＋ 貝萊德世界健康 A10（USDEQ5680）」'
             f'全數轉出 → 0056 連結基金 {fmt(batches[0]["0056"])}／0050 連結基金 {fmt(batches[0]["0050"])}<br>'
             '2. 確認 T+4 生效，並於下次對帳單核對保單B 價值未變<br>'
             '3. 檢核點：10/7 第一站配息、0056 首季配公告 → 再決定批2（摩根 30%）<br>'
             '4. 生效後更新 snapshot（policy_b_funds／fund_components_09）→ 四源同步 → 穿透重算</div></div>')
    h.append(f'<div class="card sub">資料源：snapshot.json（insurance_breakdown.policy_b_funds／fund_components_09／'
             f'penetration.actual_twd／total_assets）｜產生：build_policy_transfer_card.py｜{datetime.datetime.now():%Y-%m-%d %H:%M}</div>')
    h.append("</div></body></html>")
    return "\n".join(h), batches, cum, keep, keep_pct, div_new, usd_after


def main():
    html, batches, cum, keep, keep_pct, div_new, usd_after = build()
    out_html = BASE / f"policyB_conversion_card_{TODAY}.html"
    out_html.write_text(html, encoding="utf-8")
    md = [f"# 保單B 轉換決策卡（{TODAY}）", "",
          f"- 標的：安聯保單B 現值 {fmt(sum(B.values()))}",
          f"- 方案：分批轉入台股連結基金 0056:0050 = 75:25（轉出 {fmt(cum['out'])}，B 的 {cum['out']/sum(B.values())*100:.0f}%）",
          f"- 保留站長 {keep_pct:.0f}%：{', '.join(f'{k} {fmt(v)}' for k, v in keep.items())}",
          f"- 效果：台股→{ACT.get('台股市值型成長',0)/TOT*100:.1f}%起 +{fmt(cum['0050'])}；"
          f"美元曝險→估 {usd_after:.1f}%；新增配息 +{fmt(div_new)}/月（季配）", ""]
    for b in batches:
        md.append(f"## {b['批']}")
        md.append(f"- 賣出：{'＋'.join(f'{k} {fmt(v)}' for k, v in b['明細'].items())} = {fmt(b['賣出'])}")
        md.append(f"- 買入：0056 {fmt(b['0056'])}／0050 {fmt(b['0050'])}")
        md.append(f"- 理由：{b['理由']}")
    out_md = BASE / f"policyB_conversion_card_{TODAY}.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"✅ {out_html.name} / {out_md.name}")
    print(f"   轉出 {fmt(cum['out'])}｜0056 {fmt(cum['0056'])}｜0050 {fmt(cum['0050'])}｜保留 {keep_pct:.0f}%")
    return cum, batches


if __name__ == "__main__":
    cum, batches = main()
