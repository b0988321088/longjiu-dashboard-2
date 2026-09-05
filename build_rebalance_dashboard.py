# -*- coding: utf-8 -*-
"""build_rebalance_dashboard.py — 龍九再平衡儀表板（2026-08-22）
深色指揮中心主題，內容：五桶穿透圖/雷達燈號/動作建議/產業穿透/乾粉/質押/風險紅線/里程碑。
資料全部動態讀 snapshot.json + radar_state.json，每週六可重跑。
輸出：rebalance_dashboard_{date}.html
"""
import json, os
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = date.today().isoformat()
_WD = "一二三四五六日"[date.fromisoformat(TODAY).weekday()]  # 2026-09-03 修：星期動態算，勿寫死週六

def load(p, default=None):
    try:
        return json.loads((BASE / p).read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}

GICS_COLORS = {
    "資訊科技": "#3b82f6", "金融": "#22c55e", "醫療保健": "#f43f5e", "核心消費": "#f59e0b",
    "非核心消費": "#eab308", "工業": "#64748b", "能源": "#8b5cf6", "公用事業": "#14b8a6",
    "不動產": "#ec4899", "通訊服務": "#06b6d4", "原物料": "#a16207", "固收/現金": "#94a3b8",
}

def build_summary_md(s, radar, apct, atwd, tgt, buckets, radar_cards, actions, sec_rows, dry_cur, risk_rows, ms_html, emg_html, total, cash, monthly_inc, monthly_exp, surplus, usd_pct, tech, us30y):
    """再平衡評估（文字版 md）— 與儀表板同源，每日自動更新（2026-08-22）"""
    lines = [
        f"# 🔄 龍九再平衡評估（{TODAY}）",
        "",
        f"> 資料：snapshot.json（資料日期 {s.get('date','—')}）+ radar_state.json + data/emergency_llm_analysis.json",
        "",
        "## 一、五桶偏離 vs 目標（修正後口徑）",
        "",
        "| 桶 | 現況 | 目標 | 偏離 | 動作 |",
        "|---|---|---|---|---|",
    ]
    action_map = {"台股": "✅ 慢慢買", "美股": "⏸ 逢彈減", "防守": "🟢 已足", "債券": "⏸ 等利率", "現金": "🟢 底線制"}
    for name, act, t, twd, _c in buckets:
        gap = act - t
        lines.append(f"| {name} | {act:.1f}% | {t}% | {gap:+.1f}pp | {action_map.get(name, '—')} |")

    lines += ["", "## 二、機構流向雷達", ""]
    for k in ["台股", "黃金", "原油", "美債10年", "台幣"]:
        v = radar.get("signals", {}).get(k, {})
        locked = "（🔒LOCKED）" if v.get("locked") else ""
        lines.append(f"- {v.get('color','⚪')} {k}{locked}: {v.get('note','—')}")

    # 二之二、政策面標註（2026-09-05：動態讀 新聞* 鍵，不再鎖死 8/29 舊新聞名）
    _pn = radar.get("policy_notes") or {}
    if _pn:
        _news_keys = [k for k in _pn if str(k).startswith("新聞")]
        _nums = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
        lines += ["", "## 二之二、政策面", ""]
        lines.append(f"> {_pn.get('來源','')}（{_pn.get('記錄時間','')}）")
        for _i, k in enumerate(_news_keys):
            v = _pn.get(k, {})
            if v:
                _n = _nums[_i] if _i < len(_nums) else f"{_i+1}. "
                lines.append(f"- **{_n}{str(k).split('_',1)[-1]}**：{v.get('內容','')}")
                lines.append(f"  - 影響：{v.get('對資產影響','')}")
        if _pn.get("原油綜合判斷"):
            lines.append(f"- 🛢️ **原油綜合判斷**：{_pn['原油綜合判斷']}")
        if _pn.get("債券升息敏感度"):
            lines.append(f"- 💵 **債券升息敏感度**：{_pn['債券升息敏感度']}")

    # 二之一、資金訊號 × 投資狀況 × 動作（2026-08-23 核准：對照表嵌評估開頭）
    sig_action = {
        "台股": ("台股（7.2% 低配 -2.8pp）", "✅ 慢慢買：每週 1.5-2萬 0050/006208（單筆≤5萬）"),
        "黃金": ("避險衛星（黃金≤5%）", "⏸ PI 後 131萬分3批 50/30/20；勿追高（今 +4.4%）"),
        "原油": ("避險衛星（石油≤2%）", "⛔ 凍結：COT 機構撤離，延後建倉"),
        "美債10年": ("債券（22.6% vs 目標25%）", "⏸ 等 US30Y<5.30% 才新增"),
        "台幣": ("全資產（匯率）", "⚪ 中性：台幣走升，台股順勢加分"),
    }
    lines += ["", "## 二之一、資金訊號 × 投資狀況 × 動作", "",
              "| 資金訊號 | 流向 | 影響資產（現況） | 建議動作 |", "|---|---|---|---|"]
    for k in ["台股", "黃金", "原油", "美債10年", "台幣"]:
        v = radar.get("signals", {}).get(k, {})
        color = v.get("color", "⚪")
        _a, _act = sig_action.get(k, ("—", "—"))
        _note = v.get("note", "—").split("—")[0].strip()[:20]
        lines.append(f"| {color} {k} | {_note} | {_a} | {_act} |")

    lines += ["", "## 三、緊急應變重點（併入再平衡）", ""]
    try:
        _em = load("data/emergency_llm_analysis.json", {})
        _fr = _em.get("full_report", "")
        _i = _fr.find("六、風控檢查")
        if _i > -1:
            lines.append(_fr[_i:_i+700])
        lines.append(f"（來源：{_em.get('generated_at','')[:16]}）")
    except Exception:
        lines.append("無緊急應變資料")

    lines += ["", "## 四、動作建議（執行紀律）", ""]
    for name, light, desc, tag in actions:
        lines.append(f"- **{name}**（{tag}）：{desc}")

    lines += ["", "## 五、🎯 本週交易計畫（明確買什麼）", ""]
    try:
        _rot = s.get("rotation_recommendation", {})
        for p in _rot.get("交易計畫", []):
            if p.get("金額", 0) > 0:
                lines.append(f"- 買 **{p['標的']}** {p['金額']:,} 元｜{p['節奏']}（{p['理由']}）")
    except Exception:
        pass

    # 五之二、產業深度討論（2026-08-23：只對有動作產業 ✅/⏸/🔴，LLM 質化）
    try:
        _dd = s.get("sector_deep_dive", {})
        if _dd:
            lines += ["", "## 五之二、💬 產業深度討論（僅有動作產業）", ""]
            for _ind, _txt in _dd.items():
                lines.append(f"### {_ind}\n{_txt}")
    except Exception:
        pass

    lines += ["", "## 六、乾粉與風險紅線", ""]
    lines.append(f"- 當前乾粉：{dry_cur:,}（現金 − 70萬底線）｜9月：台股 12-24萬分批 + 黃金 131萬預留（PI後）＋ 石油 0（Locked）＋ 債券 0（等利率）")
    for name, val, limit, triggered in [
        ("US30Y", f"{us30y:.2f}%" if us30y else "—", "≥5.30%", us30y and us30y >= 5.30),
        ("美元曝險", f"{usd_pct:.0f}%", "紅線 50%", usd_pct > 50),
        ("高科技", f"{tech:.1f}%", "紅線 30%", tech > 30),
        ("現金底線", f"{cash:,}", "≥70萬", cash < 700000),
    ]:
        st = "🔴 觸發" if triggered else "🟢 安全"
        lines.append(f"- {name} {val}（{limit}）：{st}")

    lines += ["", "## 七、里程碑時程", ""]
    for d, t2, lv in [("8/24（一）", "保單轉換 300萬 決策（科技→債，T+4 截止）", "high"),
                      ("8/31", "安聯B 贖回（補現金 + 抵借款 100萬）", "mid"),
                      ("9/3 前", "PI 認列 → 質押 350萬@2.77% 還債", "high"),
                      ("9月中", "富達/聯博首次配息入帳 → 更新配息基準", "mid"),
                      ("10月", "洲際W 轉貸國泰（要求全額吸收規費）＋ 標案", "mid")]:
        lines.append(f"- {d}：{t2}")

    lines += ["", "## 八、結論", f"**本週動作：只有「台股慢慢買」是主動項（每週 1.5-2萬 × 8-12 週），其餘全數按兵不動。**",
              "最大等待：8/24 保單轉換決策 → 9/3 PI → 質押還債（4.2%→2.77%）。", ""]
    out = BASE / f"rebalance_summary_{TODAY}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 再平衡評估已產出: {out}")
    return out

def main():
    # GICS 產業穿透（Phase 1：先重算再讀，確保儀表板數字最新）
    try:
        import industry_penetration as _ip
        _ip.main()
    except Exception:
        pass
    # 輪動引擎（Phase 3：資金流向 × 產業缺口 → 乾粉建議）
    try:
        import rotation_engine as _re
        _re.main()
    except Exception:
        pass
    # 產業深度討論（2026-08-23 折衷版：只對有動作產業 ✅/⏸/🔴，LLM 質化）
    try:
        import sector_deep_dive as _sdd
        _sdd.main()
    except Exception:
        pass
    s = load("snapshot.json", {})
    radar = load("radar_state.json", {})
    pen = s.get("penetration", {})
    apct, atwd, tgt = pen.get("actual_pct", {}), pen.get("actual_twd", {}), pen.get("targets", {})
    total = s.get("total_assets", 0)
    cash = s.get("cash_total", 0)
    monthly_inc = s.get("monthly_income", 225918)
    monthly_exp = s.get("monthly_expense", 162781)
    surplus = monthly_inc - monthly_exp
    coverage = monthly_inc / monthly_exp * 100 if monthly_exp else 0
    usd_pct = s.get("usd_exposure_pct", 64.0)
    tech = (s.get("industry_penetration", {}).get("產業", {}).get("資訊科技", {}).get("佔比")
            or s.get("sector_penetration", {}).get("高科技/半導體", {}).get("佔比_估", 17.5))  # 8/22 修正：以 GICS 21.1% 為主（與 GICS 區塊一致）
    us30y = load("us30y_state.json", {}).get("last_rate")

    # ── 五桶 ──
    buckets = [
        ("台股", apct.get("台股市值型成長", 0), tgt.get("台股市值型目標", 10), atwd.get("台股市值型成長", 0), "#3b82f6"),
        ("美股", apct.get("美股市值型成長", 0), tgt.get("美股市值型目標", 40), atwd.get("美股市值型成長", 0), "#ef4444"),
        ("防守", apct.get("防守型配息", 0), tgt.get("配息型目標", 20), atwd.get("防守型配息", 0), "#22c55e"),
        ("債券", apct.get("債券", 0), tgt.get("債券型目標", 25), atwd.get("債券", 0), "#f59e0b"),
        ("現金", apct.get("現金/安全網", 0), tgt.get("現金目標", 5), atwd.get("現金/安全網", 0), "#94a3b8"),
    ]
    bar_rows = ""
    for name, act, t, twd, color in buckets:
        gap = act - t
        w = min(act / 55 * 100, 100)
        tw = min(t / 55 * 100, 100)
        gap_cls = "green" if abs(gap) <= 2 else ("yellow" if abs(gap) <= 5 else "red")
        bar_rows += f"""
        <div class="bucket">
          <div class="bucket-head"><span class="bucket-name">{name}</span><span class="bucket-val">{act:.1f}% <small>/ 目標 {t}%</small></span><span class="gap {gap_cls}">{gap:+.1f}pp</span></div>
          <div class="bar-track"><div class="bar-fill" style="width:{w:.1f}%;background:{color}"></div><div class="bar-target" style="left:{tw:.1f}%"></div></div>
          <div class="bucket-twd">{twd/1e4:.0f} 萬</div>
        </div>"""

    # ── 雷達 ──
    radar_cards = ""
    sig_meta = {"台股": "#22c55e", "黃金": "#f59e0b", "原油": "#ef4444", "美債10年": "#3b82f6", "台幣": "#94a3b8"}
    for k in ["台股", "黃金", "原油", "美債10年", "台幣"]:
        v = radar.get("signals", {}).get(k, {})
        color = v.get("color", "⚪")
        locked = " 🔒LOCKED" if v.get("locked") else ""
        border = "#22c55e" if color.startswith("🟢") else ("#ef4444" if color.startswith("🔴") else ("#f59e0b" if color.startswith("🟡") else "#64748b"))
        radar_cards += f"""
        <div class="card rcard" style="border-top:3px solid {border}">
          <div class="r-signal">{color}</div>
          <div class="r-name">{k}{locked}</div>
          <div class="r-note">{v.get('note', '—')}</div>
        </div>"""

    # ── 政策面標註（2026-08-29：Jackson Hole 華許放鷹 + 美委石油協議 + 伊朗戰爭 SPR）──
    _pn = radar.get("policy_notes") or {}
    if _pn:
        _pn_html = f"""
        <div class="card" style="border:1px solid #f59e0b;background:linear-gradient(135deg,#1a1408,#131a26)">
          <h2>🏛️ 政策面</h2>
          <div style="font-size:11px;color:#9ca3af;margin-bottom:8px">{_pn.get('來源','')}（{_pn.get('記錄時間','')}）</div>"""
        _nums = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩"]
        for _i, k in enumerate([_kk for _kk in _pn if str(_kk).startswith("新聞")]):
            v = _pn.get(k, {})
            if v:
                _n = _nums[_i] if _i < len(_nums) else f"{_i+1}. "
                _pn_html += f"""
          <div style="margin-bottom:8px;padding:8px 10px;background:#0b0f17;border-radius:8px;border-left:3px solid #f59e0b">
            <div style="font-weight:700;font-size:12px;color:#fbbf24">{_n}{str(k).split('_',1)[-1]}</div>
            <div style="font-size:11px;color:#e5e7eb;margin-top:3px">{v.get('內容','')}</div>
            <div style="font-size:10px;color:#9ca3af;margin-top:3px">影響：{v.get('對資產影響','')}</div>
          </div>"""
        if _pn.get("原油綜合判斷"):
            _pn_html += f"""
          <div style="padding:8px 10px;background:#ef44441a;border-radius:8px;border-left:3px solid #ef4444;font-size:11px;color:#fca5a5;margin-top:4px">
            🛢️ 原油綜合判斷：{_pn['原油綜合判斷']}</div>"""
        if _pn.get("債券升息敏感度"):
            _pn_html += f"""
          <div style="padding:8px 10px;background:#3b82f61a;border-radius:8px;border-left:3px solid #3b82f6;font-size:11px;color:#93c5fd;margin-top:4px">
            💵 債券升息敏感度：{_pn['債券升息敏感度']}</div>"""
        _pn_html += "</div>"
    else:
        _pn_html = ""

    # ── 本週投資計劃（2026-08-29 v2：全資產面結論 — 五桶+衛星+負債+輪動+節點）──
    try:
        _pen4 = s.get("penetration", {}).get("actual_pct", {}) or {}
        _atwd4 = s.get("penetration", {}).get("actual_twd", {}) or {}
        _dry4 = s.get("乾粉執行_0926", {}).get("戰術乾粉總額", {}).get("當前", 0)
        _usd4 = s.get("usd_exposure_monitor", {}).get("current", {}).get("合計", 0)
        _hs4 = s.get("hedge_satellite", {}) or {}
        _rot4 = (s.get("rotation_recommendation", {}) or {}).get("建議", [{}])[0]
        _def4 = s.get("defensive_combined_metric", {}).get("佔比", 69.2)
        _tw = _pen4.get('台股市值型成長', 7.5); _us = _pen4.get('美股市值型成長', 43.4)
        _plan_lines = []
        # ① 台股（缺口）
        _plan_lines.append(f"🟢 台股（{_tw:.1f}% vs 目標10%，缺口 {_tw-10:+.1f}pp）→ 0050/006208 每週1.5-2萬慢慢買（外資連3買+台幣強升）")
        # ② 美股（超配）
        if _us > 45:
            _plan_lines.append(f"🔴 美股（{_us:.1f}% vs 目標40%，超配 {_us-40:+.1f}pp）→ 逢彈減碼 ≤20萬/次")
        else:
            _plan_lines.append(f"⏸️ 美股（{_us:.1f}% vs 目標40%）超配 {_us-40:+.1f}pp 未達減碼觸發（>45%）→ 續持")
        # ③ 防守（合併口徑）
        _plan_lines.append(f"⏸️ 防守（合併口徑 {_def4:.1f}% 已足）→ 凍結不追（00878/00713 不加碼）")
        # ④ 債券
        _plan_lines.append("⏸️ 債券 23.1% 接近目標25% → 等 US30Y<5.30% 才新增（華許升息1碼估 -0.5~-1.5%）")
        # ⑤ 現金/乾粉
        _plan_lines.append(f"💰 現金 22.1% → 底線70萬守；乾粉 {_dry4/10000:.1f}萬 優先「{_rot4.get('產業','—')}」（{_rot4.get('動作','')}）")
        # ⑥ 避險衛星
        if _hs4.get("黃金延後_0829"):
            _plan_lines.append("⏸️ 避險衛星：黃金A10 32萬 8/30 生效（保單內）；00635U ~105萬 延後（華許放鷹+金價偏高）→ 等回檔")
        else:
            _plan_lines.append(f"🟢 避險衛星：黃金現況 {_hs4.get('黃金現況',0):,} → PI 後 00635U 分批 ≤20萬/次")
        # ⑦ 美元曝險
        if _usd4 > 55:
            _plan_lines.append(f"🔴 美元曝險 {_usd4}% 超標（>55%）→ 美股減碼/美元定存到期轉台幣")
        else:
            _plan_lines.append(f"🟡 美元曝險 {_usd4}% （目標≤50%）→ 未達減碼閾值，續觀察")
        # ⑧ 保單轉換（9/2 截止）
        _plan_lines.append("🔴 9/2 前：保單轉換截止（PIMCO120+M&G80-100+醫療50+黃金30）→ 8/26已轉80萬 8/30生效，剩餘本週內完成")
        # ⑨ 負債/質押
        _plan_lines.append("🔍 9/3 PI 認列 → 質押350萬@2.77% 還安聯300+元大50（高息→低息，月省利息）")
        # ⑩ 產業輪動
        _plan_lines.append(f"📊 產業輪動：買「{_rot4.get('產業','—')}」（{_rot4.get('標的','')}）｜避開「公用事業」")
        _plan_html = "".join(f"<div style=\"margin-bottom:6px;font-size:11px;color:#d1fae5\">{p}</div>" for p in _plan_lines)
        _plan_html = f"""
        <div class="card" style="border:1px solid #10b981;background:linear-gradient(135deg,#06281a,#131a26)">
          <h2>📋 本週投資計劃（8/29 全資產面結論）</h2>
          {_plan_html}
        </div>"""
    except Exception as _e2:
        _plan_html = f"<div class='card'><h2>📋 本週投資計劃</h2><div style='font-size:11px;color:#f87171'>產生失敗: {_e2}</div></div>"

    # ── 動作建議（8/22：防守合併口徑動態讀）──
    _def_pct = s.get("defensive_combined_metric", {}).get("佔比", 69.5)
    actions = [
        ("台股慢慢買", "🟢🔥 順勢", "每週 1.5-2萬 0050/006208 × 8-12 週，單筆≤5萬；配息流+結餘", "✅ 主動"),
        ("美股逢彈減", "⏸ 等待", "44.0%→40%，費半弱不砍低點；反彈日減碼 ≤20萬/次達標即停", "被動"),
        ("債券補碼", "⏸ 等兩條件", "質押完成 + US30Y<5.30%；經理人代管不買單一純債ETF", "待命"),
        ("防守", "🟢 已足", f"合併口徑 {_def_pct}% 無缺口；勿被單看 4.2% 誤導", "不動作"),
        ("現金", "🟢 底線制", f"{cash:,} ≥ 70萬 ✅；MMF 500萬已指定標案/質押補救", "不動作"),
        ("石油衛星", "🔴 Locked", "COT 機構撤離（-175.6%）；維持延後建倉", "凍結"),
        ("黃金衛星", "🟢 順勢", "PI 後 131萬 分 3 批 50/30/20；台幣計價 00635U", "待PI"),
    ]
    action_cards = ""
    for name, light, desc, tag in actions:
        action_cards += f"""
        <div class="card acard">
          <div class="a-head"><b>{name}</b><span class="tag">{tag}</span></div>
          <div class="a-light">{light}</div>
          <div class="a-desc">{desc}</div>
        </div>"""

    # ── 產業穿透 ──
    sec_rows = ""
    for k in ["高科技/半導體", "金融/電信", "醫療/公用事業/不動產", "固收與現金", "實物避險-黃金", "實物避險-石油"]:
        v = s.get("sector_penetration", {}).get(k, {})
        if not v:
            continue
        amt = v.get("金額_估", v.get("金額", 0)) or 0
        pct = v.get("佔比_估", "—")
        st = v.get("狀態", "")
        sec_rows += f"<tr><td>{k}</td><td class='num'>{amt:,}</td><td class='num'>{pct}</td><td>{st}</td></tr>"

    # ── 乾粉 ──
    dry = s.get("乾粉執行_0926", {}).get("戰術乾粉總額", {})
    dry_cur = dry.get("當前", 0)

    # ── 質押 ──
    pledge = s.get("質押計畫", {})
    ltv_txt = "未質押（9/3 PI 後 350萬@2.77%）"

    # ── 本週乾粉輪動建議（Phase 3：讀 snapshot.rotation_recommendation + 交易計畫）──
    rot_html = ""
    try:
        rot = s.get("rotation_recommendation", {})
        if rot and rot.get("建議"):
            # 交易計畫（明確買什麼/金額/節奏）
            tp_rows = ""
            for p in rot.get("交易計畫", []):
                tp_rows += (f"<tr><td><b>{p['產業']}</b></td><td>{p['標的']}</td>"
                            f"<td class='num' style='color:#4ade80'>{p['金額']:,}</td>"
                            f"<td style='font-size:11px'>{p['節奏']}</td></tr>")
            rec_rows = ""
            for r in rot.get("建議", []):
                tgt_txt = f"目標 {r.get('目標')}%" if r.get("目標") else f"紅線 {r.get('紅線')}%"
                rec_rows += (f"<tr><td><b>{r['產業']}</b><br><span style='font-size:10px;color:var(--sub)'>{'、'.join(r.get('標的', []))}</span></td>"
                             f"<td class='num'>{r.get('現況', 0):.1f}%</td><td class='num'>{tgt_txt}</td>"
                             f"<td class='num'>{r.get('資金分數', 0):+d}</td><td>{r['動作']}</td></tr>")
            av_rows = ""
            for r in rot.get("避開", [])[:3]:
                av_rows += f"<tr><td>{r['產業']}</td><td class='num'>{r.get('現況',0):.1f}%</td><td>{r['動作']}</td><td style='font-size:10.5px'>{r['理由']}</td></tr>"
            # 產業深度討論（8/23：sector_deep_dive，只對有動作產業）
            dd_html = ""
            _dd = s.get("sector_deep_dive", {})
            for _ind, _txt in _dd.items():
                dd_html += (f"<div style='margin-top:8px;padding:8px 10px;background:#111a2e;border-radius:6px;"
                            f"border-left:3px solid #38bdf8'><b style='color:#7dd3fc'>💬 {_ind}</b><br>"
                            f"<span style='font-size:11.5px;color:var(--txt);line-height:1.6'>{_txt.replace(chr(10),'<br>')}</span></div>")
            dd_block = (f"<div style='margin-top:10px'><div style='font-size:12px;font-weight:700;color:#94a3b8'>💬 產業深度討論（LLM，僅有動作產業）</div>{dd_html}</div>"
                        if dd_html else "")
            rot_html = f"""
  <div class="card" style="margin-top:14px;border-left:4px solid #22c55e">
    <h2>🎯 本週交易計畫（{rot.get('日期','')}）</h2>
    <div style="font-size:13px;font-weight:800;color:#4ade80;margin-bottom:8px">{rot.get('總結','')}</div>
    <table><tr><th>產業</th><th>買什麼</th><th class="num">金額</th><th>節奏</th></tr>{tp_rows}</table>
    <div style="margin-top:8px"><div style="font-size:12px;font-weight:700;color:#94a3b8">📊 產業判斷</div>
    <table><tr><th>產業</th><th class="num">現況</th><th class="num">目標/紅線</th><th class="num">資金分</th><th>動作</th></tr>{rec_rows}</table></div>
    <div style="margin-top:8px"><div style="font-size:12px;font-weight:700;color:#94a3b8">⏸ 避開/暫緩</div>
    <table><tr><th>產業</th><th class="num">現況</th><th>動作</th><th>理由</th></tr>{av_rows}</table></div>
    {dd_block}
    <div style="font-size:10.5px;color:var(--sub);margin-top:6px">乾粉=現金−70萬底線+月盈餘50%；單筆≤5萬、分批；8/24 轉換/9/3 PI 前保留緩衝</div>
  </div>"""
    except Exception:
        rot_html = ""

    # ── 產業資金流向（Phase 2：讀 radar_state.sector_flow）──
    sflow_html = ""
    try:
        sf = radar.get("sector_flow", {})
        if sf:
            tw_rows = ""
            for b, v in sorted(sf.get("台股", {}).items(), key=lambda x: -x[1].get("法人淨買賣超", 0)):
                amt = v.get("法人淨買賣超", 0)
                if not amt:
                    continue
                icon = "🟢" if amt > 0 else ("🔴" if amt < 0 else "⚪")
                tw_rows += f"<tr><td>{b}</td><td class='num'>{amt/1e6:+.0f}百萬</td><td>{icon} {v.get('方向','')}</td></tr>"
            us_rows = ""
            for tk, v in sorted(sf.get("美股", {}).items(), key=lambda x: -(x[1].get("RS_vs_SPY") or -99)):
                rs = v.get("RS_vs_SPY")
                rs_txt = f"{rs:+.1f}pp" if rs is not None else "—"
                us_rows += f"<tr><td>{tk}</td><td class='num'>{v.get('動能%',0):+.1f}%</td><td class='num'>{rs_txt}</td></tr>"
            tw_sum = sf.get("台股總結", "")
            us_sum = sf.get("美股總結", "")
            sflow_html = f"""
  <div class="card" style="margin-top:14px;border-left:4px solid #8b5cf6">
    <h2>📡 產業資金流向（{sf.get('generated_at','')[:16]}）</h2>
    <div style="font-size:12px;color:#cbd5e1;margin-bottom:6px">{tw_sum}｜{us_sum}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div><div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:4px">🇹🇼 台股法人（產業桶）</div>
      <table><tr><th>產業桶</th><th class="num">法人淨買賣超</th><th>方向</th></tr>{tw_rows}</table></div>
      <div><div style="font-size:12px;font-weight:700;color:#94a3b8;margin-bottom:4px">🇺🇸 美股板塊（月動能 vs SPY）</div>
      <table><tr><th>板塊</th><th class="num">動能%</th><th class="num">RS</th></tr>{us_rows}</table></div>
    </div>
    <div style="font-size:10.5px;color:var(--sub);margin-top:6px">輪動邏輯：法人流入且產業低配 → 乾粉吸納目標（科技流出→高股息/醫療防禦）</div>
  </div>"""
    except Exception:
        sflow_html = ""

    # ── GICS 產業分布（Phase 1，2026-08-22：讀 snapshot.industry_penetration）──
    gics_html = ""
    try:
        _gics = s.get("industry_penetration", {})
        if _gics and _gics.get("產業"):
            _rows = ""
            for ind, v in sorted(_gics["產業"].items(), key=lambda x: -x[1]["金額"]):
                if v["金額"] <= 0:
                    continue
                color = GICS_COLORS.get(ind, "#94a3b8")
                _w = min(v["佔比"] / 50 * 100, 100)
                _rows += (f"<tr><td><span style='display:inline-block;width:8px;height:8px;border-radius:2px;"
                          f"background:{color};margin-right:5px'></span>{ind}</td>"
                          f"<td class='num'>{v['金額']:,}</td><td class='num'>{v['佔比']:.1f}%</td>"
                          f"<td style='min-width:90px'><div style='background:#0b1220;border-radius:4px;height:6px'>"
                          f"<div style='width:{_w:.0f}%;background:{color};height:100%;border-radius:4px'></div></div></td></tr>")
            _gics_png = BASE / f"industry_penetration_{TODAY}.png"
            _gics_img = ""
            if _gics_png.exists():
                import base64
                _gics_img = (f"<img src='data:image/png;base64,{base64.b64encode(_gics_png.read_bytes()).decode('ascii')}' "
                             f"style='width:100%;border-radius:8px;margin-top:8px'/>")
            gics_html = f"""
  <div class="card" style="margin-top:14px;border-left:4px solid #3b82f6">
    <h2>🏭 GICS 產業分布（{_gics.get('日期','')}）</h2>
    <table><tr><th>產業</th><th class="num">金額</th><th class="num">佔比</th><th>集中度</th></tr>{_rows}</table>
    <div style="margin-top:6px;padding:6px 10px;background:#0b1220;border-radius:8px;font-size:11.5px;color:#e2e8f0">
      🏠 <b>實體不動產另計：{_gics.get('實體不動產_另計',{}).get('金額',0):,}</b>
      （佔含不動產總資產 {_gics.get('實體不動產_另計',{}).get('佔比_含不動產',0):.0f}%）— 大義街+洲際W 兩間房，租金 80,100/月
    </div>
    {_gics_img}
    <div style="font-size:10.5px;color:var(--sub);margin-top:6px">{_gics.get('備註','')}</div>
  </div>"""
    except Exception:
        gics_html = ""

    # ── 緊急應變（2026-08-22 新增：併入最新緊急應變 LLM 分析，來源 data/emergency_llm_analysis.json）──
    emg_html = ""
    try:
        _em = load("data/emergency_llm_analysis.json", {})
        _fr = _em.get("full_report", "")
        _i = _fr.find("六、風控檢查")
        _seg = _fr[_i:_i+900] if _i > -1 else ""
        if not _seg:
            _seg = _fr[:600]
        _seg = _seg.replace("【", "<b>【").replace("】", "】</b>")
        # 緊急應變報告連結：glob 最新（週末不產出，勿硬編碼日期）
        _ers = sorted(BASE.glob("emergency_report_2*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
        _er_name = _ers[0].name if _ers else "emergency_report_2026-08-21.html"
        emg_html = f"""
  <div class="card" style="margin-top:14px;border-left:4px solid #f59e0b">
    <h2>🚨 緊急應變併入再平衡（{_em.get('generated_at','')[:16]}）</h2>
    <div style="font-size:12px;color:#cbd5e1;line-height:1.7">{_seg}</div>
    <div style="margin-top:8px;font-size:12px"><a href="https://b0988321088.github.io/longjiu-dashboard-2/{_er_name}" style="color:#f59e0b">📄 查看完整緊急應變報告 →</a></div>
  </div>"""
    except Exception:
        emg_html = ""

    # ── 里程碑（8/22：8/24 轉換讀 snapshot 確認版）──
    _p24 = s.get("cathay_disbursement", {}).get("plan_0820_final", {}).get("再平衡組合_聯博", {}).get("保單轉換_確認版_0822", {})
    _p24_txt = "保單轉換 300萬 執行（" + " + ".join(f"{k.split(' ')[0]} {v//10000}萬" for k, v in (_p24.get("標的", {}) or {}).items()) + "）" if _p24.get("標的") else "保單轉換 300萬 決策（科技→債，T+4 截止）"
    milestones = [
        ("8/24（一）", _p24_txt, "high"),
        ("8/31", "安聯B 贖回（補現金 + 抵借款 100萬）", "mid"),
        ("9/3 前", "PI 認列 → 質押 350萬@2.77% 還債", "high"),
        ("9月中", "富達/聯博首次配息 → 更新配息基準", "mid"),
        ("10月", "洲際W 轉貸國泰（要求全額吸收規費）＋ 標案", "mid")]
    ms_html = ""
    for d, t, lv in milestones:
        cls = "ms-high" if lv == "high" else "ms-mid"
        ms_html += f"<div class='ms {cls}'><span class='ms-date'>{d}</span><span class='ms-txt'>{t}</span></div>"

    # ── 風險紅線 ──
    risks = [
        ("US30Y 凍結線", f"{us30y:.2f}%" if us30y else "—", "≥5.30% 🔴", us30y and us30y >= 5.30),
        ("美元曝險", f"{usd_pct:.0f}%", "紅線 50%", usd_pct > 50),
        ("高科技", f"{tech:.1f}%", "紅線 30%", tech > 30),
        ("現金底線", f"{cash:,}", "≥70萬", cash < 700000),
        ("總質押 LTV", "完成後 20.4%", "安全值 ≤35%", False),
    ]
    risk_rows = ""
    for name, val, limit, triggered in risks:
        st = "🔴 觸發" if triggered else "🟢 安全"
        risk_rows += f"<tr><td>{name}</td><td class='num'>{val}</td><td class='num'>{limit}</td><td>{st}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>龍九再平衡儀表板 {TODAY}</title>
<style>
:root {{ --bg:#0f172a; --card:#1e293b; --line:#334155; --txt:#e2e8f0; --sub:#94a3b8; --grn:#22c55e; --red:#ef4444; --yel:#f59e0b; --blu:#3b82f6; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--txt); font-family:'Segoe UI','Microsoft JhengHei',sans-serif; padding:20px; }}
.wrap {{ max-width:1100px; margin:0 auto; }}
h1 {{ font-size:22px; font-weight:800; }}
.sub {{ color:var(--sub); font-size:13px; margin:4px 0 16px; }}
.kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:16px; }}
.kpi {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; }}
.kpi .k {{ color:var(--sub); font-size:11px; }}
.kpi .v {{ font-size:20px; font-weight:800; font-family:Consolas,monospace; }}
.kpi .v.red {{ color:var(--red); }} .kpi .v.green {{ color:var(--grn); }} .kpi .v.yellow {{ color:var(--yel); }}
.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
@media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
.card h2 {{ font-size:14px; font-weight:800; margin-bottom:10px; color:#f8fafc; }}
.bucket {{ margin-bottom:12px; }}
.bucket-head {{ display:flex; justify-content:space-between; font-size:12.5px; margin-bottom:4px; }}
.bucket-name {{ font-weight:700; }}
.gap {{ font-weight:800; }} .gap.green {{ color:var(--grn); }} .gap.yellow {{ color:var(--yel); }} .gap.red {{ color:var(--red); }}
.bar-track {{ position:relative; height:14px; background:#0b1220; border-radius:7px; }}
.bar-fill {{ height:100%; border-radius:7px; opacity:.85; }}
.bar-target {{ position:absolute; top:-3px; width:2px; height:20px; background:#fff; }}
.bucket-twd {{ font-size:11px; color:var(--sub); text-align:right; margin-top:2px; }}
.rcards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:10px; }}
.rcard {{ border-top:3px solid var(--line); }}
.r-signal {{ font-size:22px; }}
.r-name {{ font-weight:800; font-size:13px; margin:4px 0; }}
.r-note {{ font-size:11px; color:var(--sub); line-height:1.5; }}
.acards {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
.acard {{ border-left:3px solid var(--line); }}
.a-head {{ display:flex; justify-content:space-between; font-size:13px; }}
.tag {{ font-size:10px; background:#0b1220; border:1px solid var(--line); padding:1px 6px; border-radius:8px; color:var(--sub); }}
.a-light {{ font-size:11px; color:var(--sub); margin:3px 0; }}
.a-desc {{ font-size:12px; color:#cbd5e1; line-height:1.55; }}
table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
th {{ text-align:left; color:var(--sub); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--line); }}
td {{ padding:7px 8px; border-bottom:1px solid #263449; }}
.num {{ font-family:Consolas,monospace; text-align:right; }}
.drybar {{ display:flex; height:26px; border-radius:8px; overflow:hidden; margin:10px 0; font-size:11px; font-weight:700; color:#fff; }}
.drybar div {{ display:flex; align-items:center; justify-content:center; }}
.ms {{ display:flex; gap:10px; padding:8px 10px; border-radius:8px; margin-bottom:6px; font-size:12.5px; }}
.ms-high {{ background:#3f1d1d; border:1px solid #7f1d1d; }}
.ms-mid {{ background:#1e293b; border:1px solid var(--line); }}
.ms-date {{ font-weight:800; color:var(--yel); white-space:nowrap; }}
.foot {{ margin-top:16px; color:var(--sub); font-size:11px; text-align:center; }}
</style></head><body><div class="wrap">
<h1>🔄 龍九再平衡儀表板</h1>
<div class="sub">{TODAY}（週{_WD}）｜修正後 DAA 口徑 + 機構流向雷達｜本週動作：<b style="color:var(--grn)">台股慢慢買</b>，其餘按兵不動</div>

<div class="kpis">
  <div class="kpi"><div class="k">總資產（流動）</div><div class="v">{total:,}</div></div>
  <div class="kpi"><div class="k">現金</div><div class="v">{cash:,}</div></div>
  <div class="kpi"><div class="k">月盈餘</div><div class="v green">+{surplus:,}</div></div>
  <div class="kpi"><div class="k">收入/支出</div><div class="v">{monthly_inc:,} <small style="font-size:11px">/ {monthly_exp:,}</small></div></div>
  <div class="kpi"><div class="k">美元曝險</div><div class="v red">{usd_pct:.0f}%</div></div>
  <div class="kpi"><div class="k">高科技</div><div class="v yellow">{tech:.1f}%</div></div>
</div>

<div class="grid">
  <div class="card"><h2>📊 五桶穿透 vs 目標</h2>{bar_rows}</div>
  <div class="card"><h2>📡 機構流向雷達</h2><div class="rcards">{radar_cards}</div></div>
  {_pn_html}
  {_plan_html}
</div>

<div class="grid" style="margin-top:14px">
  <div class="card"><h2>🎯 動作建議（執行紀律）</h2><div class="acards">{action_cards}</div></div>
  <div class="card"><h2>🏭 產業別穿透（雙層 Micro）</h2>
    <table><tr><th>產業</th><th class="num">金額</th><th class="num">佔比</th><th>狀態</th></tr>{sec_rows}</table>
    <div style="font-size:11px;color:var(--sub);margin-top:8px">紅線：高科技 ≤30%（當前 {tech:.1f}%）｜輪動閥門：科技>30% 或雷達科技轉弱 → 乾粉轉金融/電信/醫療防禦</div>
  </div>
</div>

<div class="grid" style="margin-top:14px">
  <div class="card"><h2>💰 9月台幣乾粉分配</h2>
    <div class="drybar">
      <div style="width:38%;background:var(--blu)">台股 12-24萬</div>
      <div style="width:55%;background:var(--yel)">黃金 131萬（PI後）</div>
      <div style="width:0%;background:var(--red)"></div>
      <div style="width:7%;background:var(--sub)">其他</div>
    </div>
    <div style="font-size:12px;color:#cbd5e1;line-height:1.7">
      當前乾粉 <b>{dry_cur:,}</b>（現金 − 70萬底線）｜9月新增：月盈餘 6-11萬 + 台幣配息 + 8/31 贖回超底線部分<br>
      石油 🔴 Locked（0）｜債券 ⏸ 等質押+US30Y&lt;5.30%（0）
    </div>
  </div>
  <div class="card"><h2>🛡️ 質押 / 風險紅線</h2>
    <div style="font-size:12.5px;color:#cbd5e1;margin-bottom:8px">📌 {ltv_txt}</div>
    <table><tr><th>指標</th><th class="num">現值</th><th class="num">紅線</th><th>狀態</th></tr>{risk_rows}</table>
  </div>
</div>

{rot_html}

{sflow_html}

{gics_html}

{emg_html}

<div class="card" style="margin-top:14px"><h2>🗓 里程碑時程</h2>{ms_html}</div>

<div class="foot">資料來源：snapshot.json（{TODAY}）+ radar_state.json（機構流向雷達）｜build_rebalance_dashboard.py 動態生成</div>
</div></body></html>"""

    out = BASE / f"rebalance_dashboard_{TODAY}.html"
    out.write_text(html, encoding="utf-8")
    print(f"✅ 再平衡儀表板已產出: {out}（{len(html)//1024} KB）")

    # 再平衡評估（文字版）— 與儀表板同源
    build_summary_md(s, radar, apct, atwd, tgt, buckets, radar_cards, actions, sec_rows, dry_cur, risk_rows, ms_html, emg_html,
                     total, cash, monthly_inc, monthly_exp, surplus, usd_pct, tech, us30y)

if __name__ == "__main__":
    main()
