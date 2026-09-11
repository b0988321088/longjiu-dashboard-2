# -*- coding: utf-8 -*-
"""一次性修正過期字串（PI 9/10 認列／2.77%／9/3 PI／9/1 保單轉換）。
使用 default_api.patch 進行更穩健的替換。"""

import sys, ast
from pathlib import Path
from hermes_tools import patch

BASE = Path(r"C:\Users\bot\Desktop\longjiu_system")

EDITS = [
 # ── A. institutional_flow.py（雷達週計畫 → 儀表板行動卡） ──
 ("institutional_flow.py",
  'lines.append(f"⏸️ 台股（{_tw5:.1f}% vs 目標10%）→ 觀望：等 PI 質押款到位（9/10 認列→銀行 2-4 週）+ Fed 9/11 CPI/9/16 定調；僅大跌 -5% 才小單 ≤5萬")',
  'lines.append(f"⏸️ 台股觀望（{_tw5:.1f}% vs 目標10%）→ 等質押撥款(9/11簽約→2-4週)+Fed 9/11 CPI / 9/16 FOMC；僅大跌 -5% 才小單 ≤5萬")', 1),
 ("institutional_flow.py",
  '        # ⑧ 保單轉換（9/1 已全數送出 — 追蹤入帳）\n'
  '        lines.append("✅ 保單轉換 9/1 已送出（安聯 PIMCO +50萬、貝萊德科技A10 90萬→摩根月配）→ 追蹤 9/8 除息 T+4 入帳")\n'
  '        # ⑨ 負債/質押\n'
  '        lines.append("🔍 9/10 PI 認列 → 質押350萬@2.77% 撥款（銀行 2-4 週）到位後才啟動後續部署；到位前全面觀望（唯一推進 = PI/質押流程）")',
  '        # ⑧ 保單轉換（9/10 安聯＋第一金同步轉入 M&G入息）\n'
  '        lines.append("✅ 保單轉換 9/10 送出（安聯＋第一金同步轉入 M&G入息A美元避險月配，T+4 預期 9/16 生效）；9/1 安聯 PIMCO+50萬、貝萊德科技A10 90萬→摩根 已完成")\n'
  '        # ⑨ 負債/質押\n'
  '        lines.append("🔍 質押：PI 已核定（9/8 國泰，原預期 9/10）→ 9/11(五)13:00 板橋國泰簽約 700萬池(富達600+聯博100)×50% = 350萬@2.8% 固定（撥款 2-4 週、US30Y<5.30 gate）到位後才啟動後續部署；到位前全面觀望")', 1),

 # ── B. build_dashboard.py（儀表板） ──
 ("build_dashboard.py",
  '_plan.append(f"台股慢慢買 0050/006208 每週1.5-2萬（缺口 -{10-_pen2.get(\'台股市值型成長\',7.5):.1f}pp）")',
  '_plan.append(f"⏸️ 台股觀望（缺口 -{10-_pen2.get(\'台股市值型成長\',7.5):.1f}pp）：等質押撥款(9/11簽約→2-4週)+Fed 9/11 CPI / 9/16 FOMC")', 1),
 ("build_dashboard.py",
  '_plan.append("9/2 保單轉換截止（PIMCO120+M&G80-100+醫療50+黃金30）；8/26已轉80萬 8/30生效")',
  '_plan.append("✅ 保單轉換 9/10 送出（安聯＋第一金同步）→ 轉入 M&G入息A美元避險月配，T+4 9/16 生效")', 1),
 ("build_dashboard.py",
  '_plan.append("PI 核可(9/10)→質押350萬還債；9/3 起追銀行進度")',
  '_plan.append("🔍 質押：PI 已核定(9/8)→9/11(五)13:00 板橋國泰簽約 700萬池×50%=350萬@2.8%固定（撥款2-4週）")', 1),

 # ── C. build_rebalance_dashboard.py ──
 ("build_rebalance_dashboard.py",
  '("9/3 前", "PI 認列 → 質押 350萬@2.77% 還債", "high"),',
  '("9/11", "板橋國泰質押簽約：350萬@2.8% 還安聯300+元大50", "high"),', 2),
 ("build_rebalance_dashboard.py",
  '"最大等待：8/24 保單轉換決策 → 9/3 PI → 質押還債（4.2%→2.77%）。", ""]',
  '"最大等待：9/11(五)13:00 板橋國泰質押簽約 → 撥款 2-4 週 → 還債（4.2%→2.8%）。", ""]', 1),
 ("build_rebalance_dashboard.py",
  '_plan_lines.append("🔴 9/2 前：保單轉換截止（PIMCO120+M&G80-100+醫療50+黃金30）→ 8/26已轉80萬 8/30生效，剩餘本週內完成")',
  '_plan_lines.append("✅ 保單轉換 9/10 送出（安聯＋第一金同步）→ 轉入 M&G入息A美元避險月配，T+4 預期 9/16 生效")', 1),
 ("build_rebalance_dashboard.py",
  '_plan_lines.append("🔍 9/10 PI 認列 → 質押350萬@2.77% 還安聯300+元大50（高息→低息，月省利息；不受 Gate 限制）")',
  '_plan_lines.append("🔍 質押：PI 已核定（9/8）→ 9/11(五)13:00 板橋國泰簽約 700萬池×50%=350萬@2.8%固定（撥款2-4週）→ 還安聯300+元大50（高息→低息；不受 Gate 限制）")', 1),
 ("build_rebalance_dashboard.py",
  'ltv_txt = "未質押（9/3 PI 後 350萬@2.77%）"',
  'ltv_txt = "未質押（9/11 簽約後 350萬@2.8%）"', 1),
 ("build_rebalance_dashboard.py",
  '8/24 轉換/9/3 PI 前保留緩衝',
  '保單轉換/質押撥款前保留緩衝', 1),

 # ── D. build_rebalance_report.py ──
 ("build_rebalance_report.py",
  '_plan_items.append("🔍 9/10 PI 認列 → 質押350萬@2.77% 還安聯300+元大50（高息→低息，月省利息；不受 Gate 限制）")',
  '_plan_items.append("🔍 質押：PI 已核定（9/8）→ 9/11(五)13:00 板橋國泰簽約 700萬池×50%=350萬@2.8%固定（撥款2-4週）→ 還安聯300+元大50（高息→低息；不受 Gate 限制）")', 1),
 ("build_rebalance_report.py",
  '8/20 定案：富達600萬+MMF600萬→PI認列2週→質押300萬@2.77%還安聯4.2%→MMF轉10月標案預備金',
  '9/9 定案：700萬池(富達600+聯博100)×50%→質押350萬@2.8%固定→還安聯300萬@4.2%+元大50萬@3.92%；MMF 500萬→150萬還款＋350萬標案預備金', 1),

 # ── E. build_penetration_report.py ──
 ("build_penetration_report.py",
  'PI 富達質押 350萬@2.77% 尚未撥款（9/10 認列後送件）；',
  'PI 質押 350萬@2.8% 尚未撥款（PI 已核定 9/8；9/11 板橋國泰簽約後送件、撥款 2-4 週）；', 1),

 # ── F. build_final.py ──
 ("build_final.py",
  '9/10 PI 認列後質押 350 萬@2.77% 償還',
  '9/11 質押簽約後 350 萬@2.8% 償還', 1),
 ("build_final.py",
  '利息成本 4%+ → 2.77%',
  '利息成本 4%+ → 2.8%', 1),
 ("build_final.py",
  "'📅 9/10：PI 認列 → 質押 350 萬 @2.77% 還安聯 300 + 元大 50'",
  "'📅 9/11(五)13:00：板橋國泰質押簽約 → 350 萬@2.8% 還安聯 300 + 元大 50（撥款 2-4 週）'", 1),
 ("build_final.py",
  "'1️⃣ 【您】9/10 PI 認列後 → 質押 350 萬 @2.77%（國泰）'",
  "'1️⃣ 【您】9/11(五)13:00 板橋國泰質押簽約 → 350 萬@2.8%（帶身分證+印鑑）'", 1),
 ("build_final.py",
  '還安聯 300 萬 + 元大 50 萬 → 保單借貸成本 4%+ 降至 2.77%',
  '還安聯 300 萬 + 元大 50 萬 → 保單借貸成本 4%+ 降至 2.8%', 1),
 ("build_final.py",
  '9/10 質押 350 萬@2.77% 再降成本',
  '9/11 質押 350 萬@2.8% 再降成本', 1),

 # ── G. build_retirement_plan.py ──
 ("build_retirement_plan.py", 'PI 質押 350萬@2.77% 還安聯300@4.2%+元大50@3.92%',
  'PI 質押 350萬@2.8% 還安聯300@4.2%+元大50@3.92%', 1),
 ("build_retirement_plan.py", '（PI 質押 350萬@2.77% 還安聯/元大）',
  '（PI 質押 350萬@2.8%（9/11 簽約）還安聯/元大）', 1),

 # ── H. build_weekly_report.py ──
 ("build_weekly_report.py",
  '<tr><td>PI 認列後（~9/3）</td><td>質押富達 5成 300萬@2.77% → 還安聯保單借貸 300萬@4.2%</td>',
  '<tr><td>2026-09-11（五）</td><td>板橋國泰質押簽約：700萬池×50%=350萬@2.8% 固定 → 還安聯保單借貸 300萬@4.2%（撥款 2-4 週）</td>', 1),
 ("build_weekly_report.py",
  '<tr><td>PI 認列後</td><td>MMF 600萬 → 10月標案預備金 5-600萬（流動性保留）</td>',
  '<tr><td>2026-09-11 後</td><td>MMF 500萬 → 還款 150萬＋10月標案預備金 350萬（流動性保留）</td>', 1),
 ("build_weekly_report.py",
  '＋MMF 600萬（PI認列2週）→ 質押300萬@2.77%還安聯300萬@4.2% → MMF轉10月標案預備金',
  '＋MMF 500萬 → 9/9 定案：700萬池(富達600+聯博100)×50%=質押350萬@2.8%固定 → 還安聯300萬@4.2%+元大50萬@3.92%；MMF 餘350萬=10月標案預備金', 1),
 ("build_weekly_report.py",
  '<li><b>8/20 定案</b>：質押富達 5成 300萬@2.77%（PI 認列後執行）',
  '<li><b>9/9 定案</b>：質押 350萬@2.8% 固定（700萬池×50%，9/11 簽約執行）', 1),

 # ── I. build_audit_dashboard.py ──
 ("build_audit_dashboard.py",
  '<li><b>9/3 PI 認證</b>（2 週到期）：質押 350萬@2.77%（先拿書面）→ 還安聯 300萬 + 元大 50萬；同步避險衛星建倉 131萬（00635U 黃金 105萬 + 00642U 石油 26萬，台幣計價、逢回檔 ≤20萬/次）</li>',
  '<li><b>9/11 質押簽約</b>（13:00 板橋國泰）：700萬池(富達600+聯博100)×50% = 350萬@2.8%（先拿書面鎖率）→ 還安聯 300萬 + 元大 50萬（撥款 2-4 週）；避險衛星 00635U 黃金 ~105萬 延後（華許放鷹+金價偏高，等回檔）</li>', 1),

 # ── J. run_daily.py（槓桿風控輸出） ──
 ("run_daily.py", '_pledge_loan = 3000000', '_pledge_loan = 3500000', 1),
 ("run_daily.py", '_pledge_rate = 0.0277', '_pledge_rate = 0.028', 1),
 ("run_daily.py", '_pledge_collateral = 6000000', '_pledge_collateral = 7000000', 1),
 ("run_daily.py", '質押層（富達 300萬×2.77%暫定）', '質押層（富達600+聯博100 池×50%=350萬@2.8%固定）', 1),
 ("run_daily.py", '＋質押 300萬（富達擔保，基金無到期日）', '＋質押 350萬（富達600+聯博100 擔保，基金無到期日）', 1),

 # ── K. pending_decisions.json（儀表板交易計畫來源） ──
 ("pending_decisions.json",
  '等 PI 認列(9/10)→質押撥款(2-4週)到位',
  '等質押簽約(9/11)→撥款(2-4週)到位', 1),
 ("pending_decisions.json",
  '質押2.77%/保單借貸4.2%/永豐2.5% 已鎖不受影響',
  '質押2.8%/保單借貸4.2%/永豐2.5% 已鎖不受影響', 1),
 ("pending_decisions.json",
  '質押 350萬@2.77%（富達600+聯博100 擔保池 ×50%，PI 9/8 已核定）',
  '質押 350萬@2.8%（富達600+聯博100 擔保池 ×50%，PI 9/8 已核定）', 1),
 ("pending_decisions.json",
  '✅ 9/1 已送出：安聯 PIMCO +50萬 + 貝萊德科技A10 90萬→摩根月配（9/8 除息 T+4 內）',
  '✅ 9/1 已送出：安聯 PIMCO +50萬 + 貝萊德科技A10 90萬→摩根月配（9/8 除息 T+4 內）；9/10 安聯再轉換送出 → 轉入 M&G入息A(美元避險月配)F（轉出標的/金額待補），T+4 預期 9/16 生效', 1),
 ("pending_decisions.json",
  '質押富達 350萬@2.77% → 還安聯300萬@4.2% + 元大50萬@3.92%',
  '質押 350萬@2.8%（700萬池×50%）→ 還安聯300萬@4.2% + 元大50萬@3.92%', 1),
 ("pending_decisions.json",
  '✅ PI 已核定（9/8 國泰通知，原預期 9/10）→ 簽約細節待定（這幾天）→ 銀行書面(成數50%/利率2.77%/預警/追繳) → 質押 350萬@2.77% 還安聯300萬+元大50萬；還債實際 10 月初',
  '✅ PI 已核定（9/8 國泰通知，原預期 9/10）→ 9/11(五)13:00 板橋國泰質押簽約（帶身分證+印鑑）→ 銀行書面(成數50%/利率2.8%/預警/追繳) → 質押 350萬@2.8% 固定（700萬池×50%）還安聯300萬+元大50萬；撥款 2-4 週、還債實際 10 月初（US30Y<5.30 gate）', 1),

 # ── L. dashboard_decisions.json ──
 ("dashboard_decisions.json",
  '✅ 9/1 已送出：安聯 PIMCO +50萬 + 貝萊德科技A10 90萬→摩根月配（9/8 除息 T+4 內）',
  '✅ 9/1 已送出：安聯 PIMCO +50萬 + 貝萊德科技A10 90萬→摩根月配（9/8 除息 T+4 內）；9/10 安聯再轉換送出 → 轉入 M&G入息A(美元避險月配)F（轉出標的/金額待補），T+4 預期 9/16 生效', 1),
 ("dashboard_decisions.json",
  '質押富達 350萬@2.77% → 還安聯300萬@4.2% + 元大50萬@3.92%',
  '質押 350萬@2.8%（700萬池×50%）→ 還安聯300萬@4.2% + 元大50萬@3.92%', 1),
 ("dashboard_decisions.json",
  '✅ PI 已核定（9/8 國泰通知，原預期 9/10）→ 簽約細節待定（這幾天）→ 銀行書面(成數50%/利率2.77%/預警/追繳) → 質押 350萬@2.77% 還安聯300萬+元大50萬；還債實際 10 月初',
  '✅ PI 已核定（9/8 國泰通知，原預期 9/10）→ 9/11(五)13:00 板橋國泰質押簽約（帶身分證+印鑑）→ 銀行書面(成數50%/利率2.8%/預警/追繳) → 質押 350萬@2.8% 固定（700萬池×50%）還安聯300萬+元大50萬；撥款 2-4 週、還債實際 10 月初（US30Y<5.30 gate）', 1),
 ("dashboard_decisions.json",
  '等 PI 認列(9/10)→質押撥款(2-4週)到位',
  '等質押簽約(9/11)→撥款(2-4週)到位', 1),

 # ── M. index_template.html（index.html 模板） ──
 ("index_template.html",
  '9/3 PI 認證 → 質押 350萬還安聯/元大；',
  '9/11(五)13:00 板橋國泰質押簽約（350萬@2.8%固定）；', 1),
 ("index_template.html",
  '9/10 第一金保單轉換送出（FJ33 100% → M&G入息A美元避險月配，T+4 9/16 生效）',
  '9/10 安聯＋第一金保單轉換送出（同步轉入 M&G入息A美元避險月配，T+4 9/16 生效）', 1),
 ("index_template.html",
  '＋600萬MMF（PI認列2週）→ 質押富達5成300萬@2.77%還安聯300萬@4.2% → MMF轉10月標案預備金5-600萬',
  '＋500萬MMF → 9/9 定案：700萬池(富達600+聯博100)×50%=質押350萬@2.8%固定 → 還安聯300萬@4.2%+元大50萬@3.92%；MMF 餘350萬轉10月標案預備金', 1),
]

def main():
    failed_patches = []
    for f, old, new, expected_count in EDITS:
        file_path = BASE / f
        # 2026-09-10 防呆：old 常是 new 的前綴（如 decisions 的 status 追加），
        # 重跑時 patch 會再追加一次 → 內容重複 2-3 份。已含 new 即視為套用過，跳過。
        if new and new in file_path.read_text(encoding="utf-8"):
            print(f"⏭️  {f} (已套用，跳過)")
            continue
        result = patch(path=str(file_path), old_string=old, new_string=new, replace_all=(expected_count > 1))
        if not result["success"]:
            failed_patches.append((f, old[:60], result["error"]))
        else:
            # Verify the patch by checking content.count(new) if expected_count > 0, or old_string not in content otherwise
            content = file_path.read_text(encoding="utf-8")
            actual_count = content.count(new) if new else content.count(old)
            if new and actual_count != expected_count:
                failed_patches.append((f, old[:60], f"Expected {expected_count} matches for new string, got {actual_count}"))
            elif not new and old in content:
                failed_patches.append((f, old[:60], "Expected old string to be deleted, but it's still present"))
            else:
                print(f"✅ {f} (patched)")

    if failed_patches:
        print("❌ 修正失敗的項目：")
        for f, s, err in failed_patches:
            print(f"   {f} :: {s} :: {err}")
        sys.exit(1)

    # 語法檢查
    bad = []
    for f, _, _, _ in EDITS:
        if f.endswith(".py"):
            try:
                ast.parse(Path(BASE, f).read_text(encoding="utf-8"))
            except SyntaxError as ex:
                bad.append((f, ex))
        elif f.endswith(".json"):
            import json
            try:
                json.loads(Path(BASE, f).read_text(encoding="utf-8"))
            except Exception as ex:
                bad.append((f, ex))
    print("🔎 語法檢查：", "全數通過" if not bad else bad)
    if bad:
        sys.exit(2)

main()
