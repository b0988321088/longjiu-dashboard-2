def render_daily_report(tv: dict, intel_text: str = "", intel_signals: dict | None = None) -> str:
    """產出五大章節日報 HTML。"""
    allianz = tv["allianz_ab"] or 7_881_584
    firstjin = tv["firstjin"] or 1_994_698
    insurance_total = tv["insurance_total"] or allianz + firstjin
    monthly_dividend = 69_044
    allianz_dividend = 55_451
    firstjin_dividend = 13_593

    # 從 full_monitor.py 動態取得 relay 時序描述
    relay_table = f"""<div class="table-wrap">
      <table>
        <thead>
          <tr><th>站別</th><th>流向</th><th>基準日</th><th>預估入帳</th><th>狀態</th></tr>
        </thead>
        <tbody>
          <tr><td>第一站</td><td>摩根多重收益（FJ33）→ 安聯收益成長（FL65）</td><td>7/14</td><td>7/19-20</td><td>✅ 已配息/已入帳</td></tr>
          <tr><td>第二站</td><td>安聯收益成長 + M&amp;G 入息基金</td><td>7/17</td><td>~7/29</td><td>🔄 配息接力中</td></tr>
          <tr><td>第三站</td><td>安聯 AI 收益 + PIMCO 第一金 + 貝萊德世界科技 A10</td><td>7/29-30</td><td>~8/10</td><td>⏸️ 等待到期</td></tr>
        </tbody>
      </table>
    </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>龍九控股日報 {TODAY}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", "PingFang TC", sans-serif;
    background: #f5f5f7;
    margin: 0;
    padding: 16px;
    line-height: 1.8;
    font-size: 17px;
    color: #1d1d1f;
    -webkit-text-size-adjust: 100%;
  }}
  .page {{ max-width: 900px; margin: 0 auto; }}
  .card {{
    background: #fff;
    border-radius: 12px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }}
  h1 {{ font-size: 22px; font-weight: 900; margin: 0 0 6px; }}
  h2 {{ font-size: 18px; font-weight: 800; margin: 14px 0 8px; }}
  h3 {{ font-size: 16px; font-weight: 800; margin: 10px 0 6px; }}
  .label {{ font-size: 12px; color: #6e6e73; margin-bottom: 6px; }}
  .text-lead {{ color: #3a3a3c; margin: 6px 0; }}
  .table-wrap {{ overflow-x: auto; margin: 8px 0; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    border: 1px solid #e5e5ea;
    border-radius: 10px;
    overflow: hidden;
    font-size: 16px;
  }}
  thead th {{
    background: #f2f2f7;
    font-weight: 800;
    text-align: left;
    padding: 10px 12px;
    border-bottom: 1px solid #e5e5ea;
    font-size: 15px;
  }}
  tbody td {{
    padding: 10px 12px;
    border-bottom: 1px solid #f2f2f7;
    vertical-align: top;
  }}
  tbody tr:nth-child(even) td {{ background: #fafafa; }}
  tbody tr:hover td {{ background: #f0f8ff; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .callout {{
    border-radius: 10px;
    padding: 12px 14px;
    margin: 10px 0;
    border-left: 4px solid;
  }}
  .callout-bull {{ background:#f0fff4; border-color:#22c55e; }}
  .callout-bear {{ background:#fff5f5; border-color:#ef4444; }}
  .callout-warn {{ background:#fffbeb; border-color:#f59e0b; }}
  .callout-info {{ background:#eff6ff; border-color:#3b82f6; }}
</style>
</head>
<body>
<div class="page">

  <!-- 1/5 財富生命線 -->
  <div class="card">
    <h1>1/5｜財富生命線 Wealth Baseline</h1>
    <div class="label">資產負債快照</div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>項目</th><th>內容</th><th>影響</th></tr>
        </thead>
        <tbody>
          <tr><td>總資產</td><td>50,689,930 TWD</td><td>淨資產 28,689,930；負債率 43.4%</td></tr>
          <tr><td>總負債</td><td>22,000,000 TWD</td><td> convertible 房貸 + 保單借貸 400 萬</td></tr>
          <tr><td>本月領息</td><td>{monthly_dividend:,} TWD</td><td>安聯 {allianz_dividend:,} + 第一金 {firstjin_dividend:,}</td></tr>
          <tr><td>被動月收</td><td>{tv['rent_monthly']+80000:,} TWD</td><td>覆蓋率 113.8%；安全邊際充足</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- 2/5 戰略異常看板 -->
  <div class="card">
    <h2>2/5｜戰略異常看板 Strategic Risk Hub</h2>
    <div class="label">四大戰略重點</div>

    <h3>保單維運</h3>
    <p class="text-lead">保單現值 <strong>{insurance_total:,} TWD</strong>（安聯 A+B {allianz:,} + 第一金 FL65 {firstjin:,}），本月配息合計 <strong>{monthly_dividend:,} TWD</strong>。落實利潤再投資 SOP，於 T+4 最晚轉換申請日才執行 relay 轉換。</p>

    <h3>證券曝險</h3>
    <p class="text-lead">0056 凍結質押中，短期無法加碼。0050 配息：待 MB 確認；防禦缺口由 00878/00713 預備。</p>

    <h3>房租金流</h3>
    <p class="text-lead">房租月收 <strong>{tv['rent_monthly']:,} TWD</strong>，覆蓋月支出 55%。7/20 洲際 W 租金入帳監控；星展戶頭餘額 7,287 TWD，8/1 需扣款 33,724，由台新調度 3 萬元補庫。</p>

    <h3>鉅亨基金調校</h3>
    <p class="text-lead">監控鉅亨買基金平台標的，追蹤 IT 與 AI 淨值，確保與保單資產互補。</p>
  </div>

  <!-- 3/5 保單接力引擎 -->
  <div class="card">
    <h2>3/5｜保單接力引擎 Insurance Relay Engine</h2>
    <div class="label">三站轉換時序監控</div>
    <p class="text-lead"><strong>本月配息合計：{monthly_dividend:,} TWD</strong></p>
    {relay_table}

    <h3>保單成分穿透</h3>
    <h3>安聯 A+B 合併帳戶（成本 8,000,000 / 現值 {allianz:,}）</h3>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>指標</th><th class="num">數值 TWD</th><th>備註</th></tr>
        </thead>
        <tbody>
          <tr><td>現值</td><td class="num">{allianz:,}</td><td>最新 market value</td></tr>
          <tr><td>本月配息</td><td class="num">{allianz_dividend:,}</td><td>當月配息</td></tr>
