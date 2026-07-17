# 一人公司自主強化：全實相監控自駕模式 Implementation Plan

> **For Hermes:** 此計畫為一人公司（龍九控股）資產自主強化完整藍圖。執行時按 Task N 逐步完成，每完成一個 Task 即 commit。

**Goal:** 建立一套能 24/7 自主監控資產、對比其他理財機器人、動態平衡投資組合的系統，讓執行長從 70% 技術微操中解脫，回歸純粹戰略裁決。

**Architecture:** 在現有 team chain 基礎上（Hermes + Notion + Gemini + daily_deploy.py），新增三大模組。**市場定位差異**：台灣 robo-advisor 只能給建議無法自動執行，且以「資產增值」為核心；龍九追求「被動現金流覆蓋支出」，並擁有獨特的 T+4 配息接力、除息日排程、Rule-based 自動再平衡能力。每日 08:00、每週五 17:00 自動執行。

**Tech Stack:** Python + Notion API + Gemini 2.5 Flash + Yahoo Finance + GitHub Pages + Telegram Bot + daily_intel.py 擴充

---

## 當前期限：2026-07-18 ~ 2026-07-25（P0）
**Exit 條件：** 1) 外部對標模組產出第一份對比報告 2) 資產防禦審計 cron 首次成功執行

### 市場定位差異（Market Positioning）

| 維度 | 台灣 robo-advisor | 龍九控股自駕系統 |
|------|-------------------|------------------|
| 核心目標 | 資產增值（growth-first） | 被動現金流覆蓋支出（cash-flow-first） |
| 自動化範圍 | 建議 only，下單需人按 | 建議自動產出，可接自動下單 |
| 配息處理 | 不在 scpoe | T+4 配息接力、除息日排程 |
| 截圖依賴 | 投資人自行上傳持倉截圖 | Yahoo Finance API + Moneybook CSV → 減少截圖 |
| 再平衡 | 選定的 portfolio 才自動 | rule-based，不呼叫 LLM 也跑 |
| 情報偵察 | 靜態組合輪動 | daily_intel.py 即時市場情報 |
| 費用 | 管理費 0.5%-1.5% | 零管理費（自有系統） |

**結論**：龍九的 positioning 是「退休現金流 OS」而非「growth robo-advisor」，這是我們不對標 00878/0050 報酬，而是對標「Coverage Ratio + Runway + 配息效率」的原因。

### Task 1：建立 Asset Moat Monitor 模組

**Objective:** 建立 `asset_moat_monitor.py`，每日計算資產護城河指標（Runway、beta 曝險、集中度風險、配息覆蓋率）

**Files:**
- Create: `C:/Users/bot/Desktop/龍九系統/asset_moat_monitor.py`
- Modify: `C:/Users/bot/Desktop/龍九系統/snapshot.json` → 確認包含所有必要欄位

**Step 1：Write failing test**

```python
# tests/test_asset_moat.py
def test_runway_calculation():
    monitor = AssetMoatMonitor()
    snapshot = {
        "total_assets": 50689930,
        "monthly_expense": 141958,
        "liquid_assets": 3071343,
        "passive_income": 160100,
    }
    moat = monitor.compute(snapshot)
    assert moat["runway_months"] > 0
    assert moat["runway_months"] < 500  # 合理範圍

def test_beta_exposure():
    monitor = AssetMoatMonitor()
    snapshot = {
        "securities": {"0050": 2000000, "006208": 500000, "etf_bond": 1000000},
    }
    moat = monitor.compute(snapshot)
    assert "semiconductor_exposure" in moat
    assert moat["semiconductor_exposure"] >= 0
```

**Step 2：Run test to verify failure**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest tests/test_asset_moat.py -v`
Expected: FAIL — module not defined

**Step 3：Write minimal implementation**

```python
# asset_moat_monitor.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AssetMoatMonitor:
    semiconductor_keywords = ["0050", "006208", "2330", "台積"]

    def compute(self, snapshot: dict) -> dict:
        total_assets = snapshot.get("total_assets", 0)
        monthly_expense = snapshot.get("monthly_expense", 1)
        liquid_assets = snapshot.get("liquid_assets", 0)
        passive_income = snapshot.get("passive_income", 0)

        runway = total_assets / monthly_expense if monthly_expense else 0
        liquid_runway = liquid_assets / monthly_expense if monthly_expense else 0
        coverage_ratio = passive_income / monthly_expense if monthly_expense else 0
        debt_ratio = snapshot.get("debt_ratio", 0)

        # 半導體曝險估算
        securities = snapshot.get("securities", {})
        semi_exposure = 0
        for name, value in securities.items():
            if any(k in name for k in self.semiconductor_keywords):
                semi_exposure += value
        total_securities = sum(securities.values()) if securities else 1
        semi_pct = semi_exposure / total_securities * 100 if total_securities else 0

        return {
            "runway_months": round(runway, 1),
            "liquid_runway_months": round(liquid_runway, 1),
            "coverage_ratio": round(coverage_ratio, 2),
            "debt_ratio_pct": round(debt_ratio * 100, 1),
            "semiconductor_exposure_pct": round(semi_pct, 1),
            "alert": self._alert(coverage_ratio, semi_pct, debt_ratio),
        }

    def _alert(self, coverage, semi_pct, debt_ratio):
        alerts = []
        if coverage < 1.0:
            alerts.append("RED: passive income < monthly expense")
        if semi_pct > 70:
            alerts.append("YELLOW: semiconductor exposure > 70%")
        if debt_ratio > 0.5:
            alerts.append("RED: debt ratio > 50%")
        return alerts
```

**Step 4：Run test to verify pass**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest tests/test_asset_moat.py -v`
Expected: PASS (2 passed)

**Step 5：Commit**

```bash
git add asset_moat_monitor.py tests/test_asset_moat.py
git commit -m "feat: add AssetMoatMonitor (runway, beta exposure, coverage ratio)"
```

---

### Task 2：建立 External Comparator 模組

**Objective:** 建立 `external_comparator.py`，每日產出與外部理財機器人/大盤的對標報告

**Files:**
- Create: `C:/Users/bot/Desktop/龍九系統/external_comparator.py`
- Create: `C:/Users/bot/Desktop/龍九系統/comparator_benchmark.json`

**Step 1：Write failing test**

```python
# tests/test_comparator.py
def test_benchmark_comparison():
    comp = ExternalComparator()
    my_portfolio = {"twii_return_ytd": 5.2, "portfolio_return_ytd": 4.8}
    benchmark = {"twii_return_ytd": 5.2, "sox_return_ytd": 3.1}
    result = comp.compare(my_portfolio, benchmark)
    assert "beat" in result["verdict"].lower() or "underperform" in result["verdict"].lower()

def test_peer_comparison():
    comp = ExternalComparator()
    peers = [
        {"name": "元大00878", "dividend_yield": 6.5, "expense_ratio": 0.5},
        {"name": "元大0050", "dividend_yield": 1.8, "expense_ratio": 0.32},
    ]
    my_fund = {"dividend_yield": 3.2, "expense_ratio": 1.5}
    result = comp.compare_peers(my_fund, peers)
    assert result["rank"] >= 1
```

**Step 2：Run test to verify failure**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest tests/test_comparator.py -v`
Expected: FAIL

**Step 3：Write minimal implementation**

```python
# external_comparator.py
import json
from pathlib import Path
from typing import Any

BENCHMARK_PATH = Path(__file__).parent / "comparator_benchmark.json"

class ExternalComparator:
    def __init__(self):
        if BENCHMARK_PATH.exists():
            self.benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
        else:
            self.benchmark = {
                "twii_ytd_return": 5.2,
                "sox_ytd_return": 3.1,
                "peers": [
                    {"name": "元大00878", "dividend_yield": 6.5, "expense_ratio": 0.5},
                    {"name": "元大0050", "dividend_yield": 1.8, "expense_ratio": 0.32},
                    {"name": "凱基台股", "dividend_yield": 2.1, "expense_ratio": 0.68},
                ],
            }

    def compare(self, my: dict, benchmark: dict) -> dict:
        my_return = my.get("twii_return_ytd", 0)
        bench_return = benchmark.get("twii_return_ytd", 1)
        diff = my_return - bench_return
        verdict = "beat" if diff > 0 else "underperform" if diff < 0 else "par"
        return {
            "my_return": my_return,
            "benchmark_return": bench_return,
            "diff_pct": round(diff, 2),
            "verdict": verdict,
        }

    def compare_peers(self, my_fund: dict, peers: list[dict]) -> dict:
        my_yield = my_fund.get("dividend_yield", 0)
        my_expense = my_fund.get("expense_ratio", 0)
        ranked = sorted(peers, key=lambda x: x.get("dividend_yield", 0), reverse=True)
        better = [p for p in ranked if p.get("dividend_yield", 0) > my_yield]
        return {
            "my_dividend_yield": my_yield,
            "my_expense_ratio": my_expense,
            "peers_count": len(peers),
            "rank": len(better) + 1,
            "better_peers": [p["name"] for p in better[:3]],
        }
```

**Step 4：Run test**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest tests/test_comparator.py -v`
Expected: PASS

**Step 5：Commit**

```bash
git add external_comparator.py comparator_benchmark.json tests/test_comparator.py
git commit -m "feat: add ExternalComparator (benchmark + peer ranking)"
```

---

### Task 3：建立 Dynamic Balancer 模組

**Objective:** 建立 `dynamic_balancer.py`，根據 moat monitor + external comparator 結果，產出投資組合動態平衡建議

**Files:**
- Create: `C:/Users/bot/Desktop/龍九系統/dynamic_balancer.py`
- Create: `C:/Users/bot/Desktop/龍九系統/balancer_rules.json`

**Step 1：Write failing test**

```python
def test_rebalance_suggestion():
    balancer = DynamicBalancer()
    current = {"TW": 7.2, "US": 46.1, "BOND": 33.8, "DEF": 18.5}
    signals = {"semiconductor_exposure_pct": 72, "coverage_ratio": 0.95}
    suggestion = balancer.suggest(current, signals)
    assert "actions" in suggestion
    assert len(suggestion["actions"]) > 0
```

**Step 2：Run test**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest -v -k "test_rebalance_suggestion"` → FAIL

**Step 3：Implementation**

```python
# dynamic_balancer.py
from dataclasses import dataclass
from typing import Any

@dataclass
class DynamicBalancer:
    rules: dict = field(default_factory=dict)

    def suggest(self, allocation: dict, signals: dict) -> dict:
        actions = []
        # Rule 1: semiconductor exposure > 70% → reduce
        semi = signals.get("semiconductor_exposure_pct", 0)
        if semi > 70:
            actions.append({
                "action": "REDUCE_TECH",
                "target": "TW tech / 0050",
                "amount_pct": 3.0,
                "reason": f"半導體曝險 {semi}% > 70% 上限",
                "priority": "P1",
            })
        # Rule 2: coverage < 1.0 → increase dividend
        coverage = signals.get("coverage_ratio", 1.0)
        if coverage < 1.0:
            actions.append({
                "action": "INCREASE_DIVIDEND",
                "target": "配息型 ETF / 債券型基金",
                "amount_pct": 2.0,
                "reason": f"被動收入覆蓋率 {coverage:.1%} < 100%",
                "priority": "P0",
            })
        # Rule 3: debt ratio > 50% → deleverage
        debt = signals.get("debt_ratio_pct", 0)
        if debt > 50:
            actions.append({
                "action": "DELEVERAGE",
                "target": "債務調度",
                "amount_pct": 0,
                "reason": f"負債比 {debt:.1f}% > 50%",
                "priority": "P0",
            })
        return {"actions": actions, "allocation": allocation}

    def apply_rules_from_file(self, rule_path: str) -> list[dict]:
        import json
        from pathlib import Path
        if not Path(rule_path).exists():
            return []
        rules = json.loads(Path(rule_path).read_text(encoding="utf-8"))
        return rules.get("auto_actions", [])
```

**Step 4：Run test**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python -m pytest -v -k "test_rebalance_suggestion"` → PASS

**Step 5：Commit**

```bash
git add dynamic_balancer.py balancer_rules.json tests/test_dynamic_balancer.py
git commit -m "feat: add DynamicBalancer (allocation rebalancing rules)"
```

---

### Task 4：整合至 daily_deploy.py

**Objective:** 將三個新模組整合進每日自動管線，產出 `weekly_asset_report_{date}.md`

**Files:**
- Modify: `C:/Users/bot/Desktop/龍九系統/daily_deploy.py:1-200` (integration point)

**Step 1：Add to imports**

```python
from asset_moat_monitor import AssetMoatMonitor
from external_comparator import ExternalComparator
from dynamic_balancer import DynamicBalancer
```

**Step 2：Add pipeline step after run_daily.py**

```python
# Inside main() 
snapshot = load_snapshot()

# 1. Moar Monitor
moat = AssetMoatMonitor()
moat_report = moat.compute(snapshot)

# 2. External Comparator
comp = ExternalComparator()
market = load_daily_analysis().get("market", {})
benchmark = {
    "twii_return_ytd": 5.2,
    "sox_return_ytd": 3.1,
}
comparison = comp.compare(
    {"twii_return_ytd": market.get("twii_ytd", 0)},
    benchmark,
)
peer_rank = comp.compare_peers(
    {"dividend_yield": snapshot.get("dividend_yield", 0), "expense_ratio": 1.5},
    comp.benchmark["peers"],
)

# 3. Dynamic Balancer
balancer = DynamicBalancer()
suggestion = balancer.suggest(
    current_allocation=snapshot.get("allocation", {}),
    signals=moat_report,
)

# 4. Inject into daily report
report_path = generate_weekly_asset_report(snapshot, moat_report, comparison, peer_rank, suggestion)
```

**Step 3：Run full pipeline**

Run: `cd C:/Users/bot/Desktop/龍九系統 && python daily_deploy.py`
Expected: Full pipeline passes (existing flow + new moat/comparator/balancer)

**Step 4：Commit**

```bash
git add daily_deploy.py
git commit -m "feat: integrate moat monitor + comparator + balancer into daily_deploy"
```

---

### Task 5：寫入 ops_logs + 推送 Telegram

**Objective:** 將 moat report + comparison 摘要自動寫入 Notion ops_logs

**Files:**
- Modify: `C:/Users/bot/Desktop/龍九系統/daily_deploy.py`

**Step 1：Add Notion ops_logs write**

```python
# After generating report
from notion_ingest import NotionIngester
ing = NotionIngester(dry_run=False)
ing.est_ops_logs([{
    "name": f"Asset Moat Daily {today}",
    "source": "Hermes",
    "status": "完成",
    "category": "資產監控",
    "summary": f"Runway={moat_report['runway_months']}m, "
               f"Coverage={moat_report['coverage_ratio']:.0%}, "
               f"SemiExp={moat_report['semiconductor_exposure_pct']:.0f}%, "
               f"Debt={moat_report['debt_ratio_pct']:.1f}%, "
               f"Alerts={', '.join(moat_report['alert'])}",
    "link": f"weekly_asset_report_{today}.md",
}])
```

**Step 2：Telegram push format**

```python
telegram_msg = f"""📊 龍九資產防禦監控 [{today}]

🔷 Runway: {moat_report['runway_months']} 個月（現金 runway {moat_report['liquid_runway_months']}）
🔷 被動覆蓋率: {moat_report['coverage_ratio']:.0%}
🔷 半導體曝險: {moat_report['semiconductor_exposure_pct']:.0f}%
🔷 負債比: {moat_report['debt_ratio_pct']:.1f}%
🔷 外部對標: {comparison['verdict']} ({comparison['diff_pct']:+.1f}pp)

⚡ 行動建議:
{chr(10).join([f"- {a['action']}: {a['target']} ({a['reason']})" for a in suggestion['actions'][:3]])}

🔗 完整報告: https://b0988321088.github.io/longjiu-dashboard-2/weekly_asset_report_{today}.html"""

send_telegram(telegram_msg)
```

**Step 3：Commit**

```bash
git add -A && git commit -m "feat: moat monitor ops_logs + Telegram push"
```

---

## Files Likely to Change

| File | Action | Purpose |
|------|--------|---------|
| `.hermes/plans/` | CREATE | 本計畫書 |
| `asset_moat_monitor.py` | CREATE | 資產護城河計算 |
| `external_comparator.py` | CREATE | 外部對標比對 |
| `dynamic_balancer.py` | CREATE | 動態平衡建議 |
| `comparator_benchmark.json` | CREATE | 外部 benchmark 數據 |
| `balancer_rules.json` | CREATE | 平衡規則配置 |
| `tests/test_asset_moat.py` | CREATE | moat monitor tests |
| `tests/test_comparator.py` | CREATE | comparator tests |
| `tests/test_dynamic_balancer.py` | CREATE | balancer tests |
| `daily_deploy.py` | MODIFY | 整合三個模組 |
| `daily_intel.py` | MODIFY | 情報關鍵字擴充（已完成） |
| `OPERATIONS_MANUAL.md` | MODIFY | 新增 SOP-007~SOP-009 |

## Validation / Exit Criteria

1. **每日 moat report：** `python daily_deploy.py` 成功產出 `weekly_asset_report_{date}.md`，Telegram 推送正常
2. **外部對標：** `external_comparator.py` 產出 beat/underperform  verdict
3. **動態平衡：** `dynamic_balancer.py` 在 coverage < 100% 時自動觸發 INCREASE_DIVIDEND 建議
4. **ops_logs 自動寫入：** Notion ops_logs 每日增加 Asset Moat 記錄
5. **Cron 穩定：** `daily_deploy.py` + `週五資產防禦審計` 連續 7 天無手動介入

## Risks & Tradeoffs

| 風險 | 緩解措施 |
|------|---------|
| Gemini API 用量暴增 | 限制 moat report 僅用 rule-based logic，不每次都呼叫 Gemini |
| Notion rate limit | retry + backoff 已內建於 notion_ingest.py |
| Snapshot 字段不足 | moat monitor 使用 defensive coding（.get() with defaults） |
| 外部 benchmark 數據延遲 | 使用 Yahoo Finance API 即時數據，web_search fallback |

## Open Questions

- [ ] 00878/009816 進場時機：等 7/21 0050 除息後確認配息真值再調整
- [ ] 轉貸進度：7/17 面簽後等核貸，資產數字會過渡期混亂，moat monitor 要有 fallback 邏輯
- [ ] 00713 替代方案評估：尚未納入 snapshot，需手動確認
