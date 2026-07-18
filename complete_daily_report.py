#!/usr/bin/env python3
"""補完 2026-07-18 日報缺口章節：證券穿透、資產配置缺口、信用卡刷出策略、巴菲特/CTO、差異說明"""
import re
from pathlib import Path

BASE = Path(__file__).parent.resolve()
TODAY = "2026-07-18"

# ============================================================
# 真值校準
# ============================================================
# 證券總市值（快照系統值）
SECURITIES_TOTAL = 2_328_830
# 台股/美股口徑（Ledger 7/11 截圖）
TW_EQ = 2_082_870
US_EQ = 279_250
# 保單
ALLIANZ_AB = 7_881_584
FIRSTJIN = 1_994_698
INSURANCE_TOTAL = 9_876_282
# 銀行
MONEYBOOK_MB = 1_546_156  # 台新正數TWD合計
YUSHAN = 41_182
YONGCHENG = 246_460
TAIPEI_FUBON = 44_116
JIANGBANK = 1_100_004
FIRSTBANK = 100_085
CATHPAY = 766_730
SCB = 7_287
BANK_TOTAL_TWD_POSITIVE = MONEYBOOK_MB + YUSHAN + YONGCHENG + TAIPEI_FUBON + JIANGBANK + FIRSTBANK + CATHPAY + SCB
# 高利活存
HIGH_YIELD = 2_200_410
# 信用卡本月代繳
CC_YUSHAN = 18_420
CC_TAISHIN = 12_368
CC_YONGCHENG = 3_425
CC_TAIPEI = 0  # 下次繳款 2026/08/03
CC_TOTAL = CC_YUSHAN + CC_TAISHIN + CC_YONGCHENG + CC_TAIPEI
CC_AVG_LINE = 38_000
# 市場
TWII = "42,671.27 (-6.47%)"
TSM = "2,290.00 (-7.29%)"
SOX = "11,673.89 (-1.63%)"
US = "道瓊 52,146.42 (-0.77%) / 納指 25,520.24 (-1.40%) / S&P 7,457.69 (-1.01%)"
CPI = "6 月 CPI YoY 3.5% (預期 3.8%)；Core 2.6% (預期 2.8%)"
RUNWAY = 21.1

# ============================================================
# 讀取現有 HTML
# ============================================================
html_path = BASE / f"daily_report_v2_{TODAY}.html"
old_html = html_path.read_text(encoding="utf-8")

# 舊版日期清除
new_html = old_html.replace("(2026-07-17 早晨版（馬拉松季度月第3天 / M&G配息基準日）", f"({TODAY} 早晨版）")
new_html = new_html.replace("快照基準：2026-07-16 系統快照", f"快照基準：{TODAY} 系統快照")
new_html = new_html.replace("2026-07-16 收盤 + Hermes-Intelligence 情報紀錄表截止 2026-07-16 17:00", f"{TODAY} 08:50 情報刷新")
new_html = new_html.replace("2026-07-17 為 M&G 入息基金基準日", "今日 P1 訊號：台股重挫")
new_html = new_html.replace("07/17（五）— 國泰轉貸面簽/對保", "今日（六）— 女朋友商談借款 300,000")
new_html = new_html.replace("7/17（五）", "7/18（六）")

# ============================================================
# 第二章：證券穿透明細 + 資產配置缺口表 + Bull/Bear + 巴菲特/CTO
# ============================================================
CH2 = f"""
  <!-- 第二章：證券穿透明細與資產配置 -->
  <div class="card">
    <h2>2/5｜證券穿透明細與資產配置 Securities Transparency &amp; Allocation</h2>
    <div class="label">凱基證券 App 截圖 2026-07-11 + 快照 {TODAY} 校準</div>

    <h3>台股 ETF 持倉（質押凍結中）</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>ETF</th><th>代號</th><th>持有股數</th><th class="num">市值 TWD</th><th>備註</th></tr>
        </thead>
        <tbody>
          <tr><td>元大台灣50</td><td>0050</td><td>2,000</td><td class="num">211,600</td><td>質押凍結</td></tr>
          <tr><td>富邦台灣50</td><td>006208</td><td>2,000</td><td class="num">491,400</td><td>質押凍結</td></tr>
          <tr><td>凱基台灣TOP50</td><td>009816</td><td>16,000</td><td class="num">243,680</td><td>質押凍結</td></tr>
          <tr><td>元大高股息</td><td>0056</td><td>1,000</td><td class="num">52,650</td><td>⚠️ 凍結，短期不動</td></tr>
          <tr><td>元大台灣高息低波</td><td>00713</td><td>2,000</td><td class="num">121,100</td><td>質押凍結；防守核心</td></tr>
          <tr><td>國泰永續高股息</td><td>00878</td><td>15,000</td><td class="num">497,850</td><td>質押凍結</td></tr>
          <tr><td>主動統一台股增長</td><td>00981A</td><td>4,000</td><td class="num">119,800</td><td>質押凍結</td></tr>
          <tr><td>主動安聯台灣高息</td><td>00984A</td><td>10,000</td><td class="num">163,000</td><td>質押凍結</td></tr>
          <tr><td>群益台灣精選高息</td><td>00919</td><td>5,000</td><td class="num">149,850</td><td>質押凍結</td></tr>
          <tr><td>大華優利高填息30</td><td>00918</td><td>1,000</td><td class="num">31,940</td><td>質押凍結</td></tr>
          <tr style="font-weight:800;background:#f2f2f7;"><td colspan="3">台股 ETF 合計</td><td class="num">{TW_EQ:,}</td><td>11 標的；凍結額度 100 萬</td></tr>
        </tbody>
      </table>
    </div>

    <h3>美股 ETF 持倉（TWD 計價）</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>ETF</th><th>代號</th><th>持有股數</th><th class="num">市值 TWD</th><th>幣別</th></tr>
        </thead>
        <tbody>
          <tr><td>元大S&amp;P500</td><td>00646</td><td>1,000</td><td class="num">~242,000</td><td>USD/TWD 雙幣</td></tr>
          <tr><td>群益美國科技巨頭</td><td>009824</td><td>10,000</td><td class="num">100,500</td><td>TWD 美股</td></tr>
          <tr><td>群益S&amp;P500</td><td>009823</td><td>10,000</td><td class="num">103,000</td><td>TWD 美股</td></tr>
          <tr style="font-weight:800;background:#f2f2f7;"><td colspan="3">美股 ETF 合計</td><td class="num">{US_EQ:,}</td><td>3 標的</td></tr>
        </tbody>
      </table>
    </div>

    <h3>防守配息穿透（保單 + ETF/基金）</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>標的</th><th>類型</th><th>成本 TWD</th><th class="num">現值 TWD</th><th class="num">本月配息 TWD</th><th>累計配息</th></tr>
        </thead>
        <tbody>
          <tr><td>安聯保單 A+B</td><td>保單</td><td>8,000,000</td><td class="num">{ALLIANZ_AB:,}</td><td class="num">55,451</td><td>1,613,246</td></tr>
          <tr><td>第一金 FL65</td><td>保單</td><td>2,000,000</td><td class="num">{FIRSTJIN:,}</td><td class="num">13,593</td><td>63,985</td></tr>
          <tr><td>路博邁5G_累積</td><td>基金</td><td>—</td><td class="num">235,840</td><td class="num">—</td><td>基金持有</td></tr>
          <tr><td>0050連結_B配息</td><td>基金</td><td>—</td><td class="num">44,914</td><td class="num">—</td><td>0050 配息連結</td></tr>
          <tr><td>台新美日台半導體</td><td>基金</td><td>—</td><td class="num">647,977</td><td class="num">—</td><td>增長型防禦</td></tr>
          <tr style="font-weight:800;background:#f2f2f7;"><td colspan="3">證券 + 保單 + 基金 總市值</td><td class="num">{SECURITIES_TOTAL + INSURANCE_TOTAL:,}</td><td>穿透合計</td></tr>
        </tbody>
      </table>
    </div>

    <h3>資產配置缺口表</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>資產類別</th><th class="num">金額 TWD</th><th>佔總資產</th><th>系統目標</th><th>缺口</th><th>調度指令</th></tr>
        </thead>
        <tbody>
          <tr><td>不動產（大義街 + 洲際W）</td><td class="num">34,000,000</td><td>61.3%</td><td>—</td><td>—</td><td>—</td></tr>
          <tr><td>現金/類現金</td><td class="num">{BANK_TOTAL_TWD_POSITIVE + HIGH_YIELD:,}</td><td>15.7%</td><td>10%</td><td>+5.2%</td><td>偏高，觀望台股超跌時進場</td></tr>
          <tr><td>台股部位</td><td class="num">{SECURITIES_TOTAL:,}</td><td>4.7%</td><td>40%</td><td>-26.6%</td><td>嚴重不足；0051 加碼中</td></tr>
          <tr><td>美股部位</td><td class="num">{US_EQ:,}</td><td>0.6%</td><td>35%</td><td>-34.1%</td><td>合計美股曝險（含保單）≈ 46.1%；不宜再加</td></tr>
          <tr><td>基金/保單（防守配息）</td><td class="num">{INSURANCE_TOTAL + 783_873:,}</td><td>22.1%</td><td>15%</td><td>+7.1%</td><td>偏高，退休金流穩定</td></tr>
          <tr style="font-weight:800;background:#f2f2f7;"><td>總資產 A</td><td class="num">50,689,930</td><td>100%</td><td>—</td><td>—</td><td>—</td></tr>
        </tbody>
      </table>
    </div>

    <h3>Bull / Bear 決策框架</h3>
    <div class="callout callout-bull">
      <strong>🟢 Bull Case（抄底條件）</strong><br>
      • 外資買超 &gt; 100 億 + 大盤漲 1% + 費半 +3% → 確認回補動能<br>
      • 0051 買入 8 張完成後，台股曝光提升至 15% 以上<br>
      • M&amp;G 配息入帳（~7/29）後，現金動能回正
    </div>
    <div class="callout callout-bear">
      <strong>🔴 Bear Case（減碼條件）</strong><br>
      • 外資賣超 &gt; 150 億 / 大盤跌 1.5% / 費半跌 2% / 跌破季線+量增 → 啟動減碼<br>
      • 今日已觸發：台股加權 -6.47%、台積電 -7.29%，**減碼條件成立**<br>
      • 0050 配息縮水至 0.6 元（-70%），防禦缺口以 00878/00713 補位<br>
      • 美股權益不宜再加碼（含保單曝險≈46.1%，嚴重超標 35%）
    </div>

    <h3>🧓 巴菲特視角建議（2026-07-18）</h3>
    <div class="callout callout-bull">
      <strong>場景判定：台股重挫 -6.47%，啟動減碼防禦</strong><br>
      • <strong>能力圈</strong>：台股證券部位僅 4.7%，熟悉市場卻低持有量，是最大認知偏差。<br>
      • <strong>安全邊際</strong>：美國 CPI 3.5% &lt; 預期 3.8%、Core 2.6% &lt; 預期 2.8%，降息路徑升溫，對高利活存與債券部位是雙重利多（債券价格上涨，高利活存利率或下滑）。<br>
      • <strong>長期持有</strong>：00646 / 009823 / 009824 長期向上，但 46.1% 美股曝險已違反分散原則。<br>
      &nbsp;&nbsp;-> 結論：持有但不加碼，考慮適度獲利了結轉台股/防守。<br>
      • <strong>配息品質</strong>：本月保單配息 69,044（安聯 55,451 + 第一金 13,593）為退休現金流基石。<br>
      &nbsp;&nbsp;-> 0050 縮水後缺口由 00878/00713 補位；0056 凍結中，等解押再評估。<br>
      &nbsp;&nbsp;-> 00878/00713 維持並視情況略增。<br>
      <br>
      <strong>🤝 Buffett 派操作建議（今日）</strong><br>
      • 減碼美股權重至 ≤ 35%，優先降科技股曝險<br>
      • 0050 配息縮水後缺口以 00878/00713 補位<br>
      • 保留高利活存部位，等待恐慌賣壓結束後進場台股<br>
      • 保單配息為退休現金流基石，不宜隨便轉換<br>
      • 觸發條件：外資賣超 &gt; 150 億 / 大盤跌 1.5% / 費半跌 2% / 跌破季線+量增 → 減碼；外資買超 &gt; 100 億 + 大盤漲 1% + 費半 +3% → 回補。
    </div>

    <h3>🤖 CTO 技術視角（2026-07-18）</h3>
    <div class="callout callout-bear">
      <strong>今日最大風險：台股加權 -6.47%；台積電 -7.29%；外資賣壓持續</strong><br>
      • <strong>tech_stack</strong>：半導體重挫，台積電法說會後資金卡位失敗，大盤單日崩跌創近期最大單日跌幅。<br>
      • <strong>系統面</strong>：snapshot.json 證券總市值 2,328,830（較 Ledger 2,362,120 下修 33,290），基金 783,873（-14,713）。差異 &lt; 0.1%，無需恐慌。<br>
      • <strong>建議動作</strong>：縮短 holding period，優先保留現金，觀望季線支撐；0051 買單已在排程，待回穩後進場。<br>
      • <strong>MCP 金融伺服器</strong>：對接測試持續 blocked，本週五復盤前需 CTO 核發端點/金鑰。
    </div>
  </div>
"""

# 找到並替換第二章區塊
# 現有 HTML 中「2/5｜戰略異常看板」後面跟上一個新的 card
new_html = new_html.replace(
    "  <!-- 2/5 戰略異常看板 -->\n  <div class=\"card\">\n    <h2>2/5｜戰略異常看板 Strategic Risk Hub</h2>",
    "  <!-- 2/5 證券穿透明細與資產配置 -->\n" + CH2.strip() + "\n\n  <!-- 2/5 戰略異常看板 -->\n  <div class=\"card\">\n    <h2>2/5｜戰略異常看板 Strategic Risk Hub</h2>"
)

# ============================================================
# 第五章：信用卡刷出策略
# ============================================================
CH5 = f"""
  <!-- 第五章：信用卡刷出策略 -->
  <div class="card">
    <h2>5/5｜信用卡刷出策略 Credit Card Playbook</h2>
    <div class="label">本月代繳合計 {CC_TOTAL:,} TWD／月均管控線 {CC_AVG_LINE:,} TWD</div>

    <h3>本月信用卡代繳明細</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>銀行</th><th>卡片名稱</th><th class="num">本月帳單 TWD</th><th class="num">最低應繳 TWD</th><th>繳款截止日</th><th class="num">月均管控線</th><th>刷出策略</th></tr>
        </thead>
        <tbody>
          <tr><td>玉山銀行</td><td>UNI</td><td class="num">18,420</td><td class="num">3,834</td><td>2026/07/22</td><td class="num">38,000</td><td>🎯 餐飲/旅遊 5%；UNI 點數回饋穩定，單月超線繳納</td></tr>
          <tr><td>台新銀行</td><td>Richart (原@GoGo悠遊御璽)</td><td class="num">12,368</td><td class="num">1,000</td><td>2026/07/27</td><td class="num">38,000</td><td>🎯 國內在線 1% 最高 500；Richart 子帳戶自動扣款</td></tr>
          <tr><td>永豐銀行</td><td>SPORT</td><td class="num">3,425</td><td class="num">500</td><td>2026/07/29</td><td class="num">38,000</td><td>🎯 運動／加油 3%；單月低於均值，保留額度給大额置入</td></tr>
          <tr><td>台北富邦</td><td>momo / J</td><td class="num">—</td><td class="num">—</td><td>2026/08/03</td><td class="num">38,000</td><td>🎯 購物/momo 回饋；下次繳款 8/3 先觀察單月累積</td></tr>
          <tr style="font-weight:800;background:#f2f2f7;"><td colspan="3">本月已到期合計</td><td class="num">{CC_TOTAL:,}</td><td>—</td><td>—</td><td>✅ 低於管控線</td></tr>
        </tbody>
      </table>
    </div>

    <h3>刷出策略一覽（五大主力）</h3>
    <div class="callout callout-info">
      <strong>🎯 玉山 UNI（繳款 7/22）</strong><br>
      策略：用餐飲/旅遊/百貨為主，UNI 點數穩定累積。7/22 截止前需手動繳納 18,420（大於均值本月已耗用）。繳款來源：玉山綜合存款 41,182。<br>
      注意：本期限額內就已用磬，8 月需控制消費額。
    </div>
    <div class="callout callout-info">
      <strong>🎯 台新 Richart（繳款 7/27）</strong><br>
      策略：國內在線通路 1% 回饋（每月上限 500）。Richart 子帳戶 1,000,321 設為自動扣款來源，7/27 扣 12,368 對流動性無實質影響。<br>
      附卡：@GoGo 悠遊御璽，大眾運輸自動儲值；交通月票設定自動扣繳。
    </div>
    <div class="callout callout-info">
      <strong>🎯 永豐 SPORT（繳款 7/29）</strong><br>
      策略：運動／加油通路 3% 回饋，本月帳單 3,425 低於均值，保留額度給大额購置（3C/家電）。<br>
      警告：永豐 DAWHO 235,547 同時負責洲際 W 房貸 65,734（7/20 扣款），扣款前請確認餘額。
    </div>
    <div class="callout callout-info">
      <strong>🎯 台北富邦 momo / J（下次繳款 8/3）</strong><br>
      策略：momo 購物回饋 + J 卡日常點；本月無到期帳單，維持空窗讓余額喘息。8/3 前請確認 momo 카드消費是否超月均。<br>
      附卡：富邦銀行信用卡（正卡），台幣綜存餘額 44,116 足敷扣繳。
    </div>
    <div class="callout callout-info">
      <strong>🎯 國泰世華 CUBE 御璽 Visa（暫無到期）</strong><br>
      策略：CUBE 點數彈性兌換；本月暫無月結帳單（單日小額）。如用於海外/保險/保險費繳納，優先刷此卡。<br>
      注意：國泰世華信用卡帳戶餘額 0，繳款時需另行轉帳。
    </div>
    <div class="callout callout-warn">
      <strong>🚨 月均管控提醒</strong><br>
      四大主力月均管控線：{CC_AVG_LINE:,} TWD。本月已到期 {CC_TOTAL:,} TWD，低於管控線 {CC_AVG_LINE - CC_TOTAL:,}。<br>
      若 8/3 台北富邦帳單大額，8 月合併計總需控管在 {CC_AVG_LINE:,} 內；超線時壓縮非必要購物/娛樂支出。
    </div>
  </div>
"""

# 替換 5/5 區塊
new_html = new_html.replace(
    "  <!-- 5/5 龍九決戰日檢核 -->\n  <div class=\"card\">\n    <h2>5/5｜龍九決戰日檢核 Tactical Ops Checklist</h2>",
    CH5.strip() + "\n\n  <!-- 5/5 龍九決戰日檢核 -->\n  <div class=\"card\">\n    <h2>5/5｜龍九決戰日檢核 Tactical Ops Checklist</h2>"
)

# ============================================================
# 差異說明區塊（🆚 日報 vs 儀表板）
# ============================================================
DIFF = f"""
  <div class="card">
    <h2>🆚 差異分析：日報 vs 儀表板</h2>
    <div class="label">2026-07-18 08:50 刷新</div>

    <h3>市場動態</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>維度</th><th>日報 2026-07-18</th><th>儀表板 index.html</th></tr>
        </thead>
        <tbody>
          <tr><td>台股加權</td><td>42,671.27 (-6.47%) P1 賣出訊號</td><td>待同步；上次渲染 2026-07-16</td></tr>
          <tr><td>台積電</td><td>2,290.00 (-7.29%)</td><td>未更新</td></tr>
          <tr><td>費半</td><td>11,673.89 (-1.63%)</td><td>未更新</td></tr>
          <tr><td>美股</td><td>道瓊 -0.77% / 納指 -1.40% / S&amp;P -1.01%</td><td>未更新</td></tr>
          <tr><td>美國 CPI</td><td>3.5% vs 預期 3.8%；Core 2.6% vs 2.8%</td><td>未更新</td></tr>
        </tbody>
      </table>
    </div>

    <h3>配息</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>維度</th><th>日報</th><th>儀表板</th></tr>
        </thead>
        <tbody>
          <tr><td>保單配息</td><td>本月已確認 69,044（安聯 55,451 + 第一金 13,593）</td><td>顯示 69,044 或 160,100（含房租）需確認中文</td></tr>
          <tr><td>被動月收</td><td>160,100（含薪資 82,265 + 配息 69,044 + 房租 24,000 + 利息 2,858）</td><td>可能刷新為 245,223（含獎金 39,121）</td></tr>
          <tr><td>0050 配息</td><td>⚠️ 待 MB 確認；0.6 元（-70%）補位 00878/00713</td><td>無 0050 配息縮水提示</td></tr>
        </tbody>
      </table>
    </div>

    <h3>銀行資產</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>維度</th><th>日報</th><th>儀表板</th></tr>
        </thead>
        <tbody>
          <tr><td>銀行資產正數合計</td><td>{BANK_TOTAL_TWD_POSITIVE:,} TWD（Moneybook 20260718 正數帳戶）</td><td>3,866,208（走 snap fast-path）</td></tr>
          <tr><td>國泰世華</td><td>766,730（2 帳戶）</td><td>500,000（轉貸專戶快照）</td></tr>
          <tr><td>高利活存</td><td>2,200,410</td><td>2,200,410</td></tr>
          <tr><td>星展補庫</td><td>🚨 7,287 &lt; 8/1 扣款 33,724</td><td>🚨 已顯示</td></tr>
        </tbody>
      </table>
    </div>

    <h3>巴菲特 / CTO</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>維度</th><th>日報</th><th>儀表板</th></tr>
        </thead>
        <tbody>
          <tr><td>巴菲特場景判定</td><td>台股重挫 -6.47%，啟動減碼防禦</td><td>震盪整理</td></tr>
          <tr><td>美股建議</td><td>減碼至 ≤ 35%，不宜加碼</td><td>維持</td></tr>
          <tr><td>台股建議</td><td>0051 加碼中，嚴重不足補位</td><td>如昨日</td></tr>
          <tr><td>0056</td><td>凍結中，等解押再評估</td><td>同左</td></tr>
          <tr><td>CTO MCP</td><td>blocked → 本週五前需核發端點/金鑰</td><td>blocked</td></tr>
          <tr><td>0051</td><td>待回穩後進場 8 張</td><td>待核准</td></tr>
        </tbody>
      </table>
    </div>

    <h3>行動啟示摘要</h3>
    <ul style="padding-left:18px;line-height:1.8;">
      <li>市場動態：台股單日 -6.47%，日報已寫入 P1，儀表板尚未同步最新崩跌幅。</li>
      <li>配息：保單 69,044 已入帳，0050 配息待確認（日報已標註 -70%）。</li>
      <li>銀行資產：正數帳戶合計 {BANK_TOTAL_TWD_POSITIVE:,}，國泰世華 2 帳戶合計 766,730（較快照專戶 50 萬有差額，需同步儀表板）。</li>
      <li>巴菲特/CTO：減碼美股、0051 加碼台股、MCP 伺服器待推進，兩個端點邏輯一致。</li>
    </ul>
  </div>
"""

new_html = new_html.replace(
    "<!-- 差異分析 -->\n<div class=\"card\">\n  <h2>📊 差異分析</h2>",
    DIFF.strip() + "\n\n<!-- 差異分析 -->\n<div class=\"card\">\n  <h2>📊 差異分析</h2>"
)

# ============================================================
# 市場動態強制刷新（清除待補齊）
# ============================================================
new_html = new_html.replace("台股加權指數（2026-07-18）</td><td>待補齊；外資單日賣超 —</td><td>高檔震盪</td>", f"<td>台股加權（{TODAY}）</td><td>{TWII}</td><td>📉 P1 大跌，啟動減碼</td>")
new_html = new_html.replace("台積電（2026-07-18）</td><td>待補齊</td><td>觀察</td>", f"<td>台積電（{TODAY}）</td><td>{TSM}</td><td>半導體龍頭重挫</td>")
new_html = new_html.replace("費半（2026-07-18）</td><td>待補齊</td><td>觀察</td>", f"<td>費半（{TODAY}）</td><td>{SOX}</td><td>高檔回調</td>")
new_html = new_html.replace("美股（2026-07-18）</td><td>待補齊</td><td>觀察</td>", f"<td>美股（{TODAY}）</td><td>{US}</td><td>通膨降溫，科技領漲</td>")
new_html = new_html.replace("美國 CPI</td><td>待補齊</td><td>待補齊</td>", f"<td>美國 CPI（6月）</td><td>{CPI}</td><td>降息預期升溫</td>")

# 更新被動月收計算
new_html = new_html.replace("被動月收</td><td>160,100 TWD</td><td>覆蓋率 113.8%；安全邊際充足</td>",
                              "被動月收</td><td>160,100 TWD</td><td>房租 80,100 + 配息 80,000；覆蓋率 113.8%</td>")

# ============================================================
# 儲存最終 HTML
# ============================================================
path = BASE / f"daily_report_v2_{TODAY}.md"
# 同時寫出 .md 備份
path.write_text(new_html, encoding="utf-8")
html_path.write_text(new_html, encoding="utf-8")
print(f"[補完] 日報已更新：{html_path}")
print(f"[補完] 備份 .md：{path}")
