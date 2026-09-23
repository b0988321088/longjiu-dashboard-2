"""Asset Moat Monitor — 計算資產護城河指標（Task 1）"""
from __future__ import annotations



class AssetMoatMonitor:
    SEMI_THRESHOLD = 70.0
    DEBT_THRESHOLD = 50.0
    semiconductor_keywords = [
        "0050", "006208", "2330", "台積", "半導體", "electronics",
    ]

    def compute(self, snapshot: dict) -> dict:
        total_assets = snapshot.get("total_assets") or 0
        monthly_expense = snapshot.get("monthly_expense") or 1
        liquid_assets = (
            snapshot.get("liquid_assets")
            or snapshot.get("high_yield_savings_total")
            or snapshot.get("cash_total")
            or 0
        )
        if isinstance(liquid_assets, dict):
            liquid_assets = float(liquid_assets.get("total", 0) or liquid_assets.get("value", 0) or 0)
        raw_passive = snapshot.get("passive_income")
        if isinstance(raw_passive, dict):
            # 2026-09-23 INC-248：保守配息只認 fund_dividend_conservative。
            # 原退路 `or raw_passive["total"]` 語意未定義（可能是實收合計）→ 移除，缺值顯式警示以 0 計。
            passive_income = raw_passive.get("fund_dividend_conservative")
            if passive_income is None:
                print("[WARN] 護城河：passive_income.fund_dividend_conservative 缺值：保守配息以 0 計（不以 total／實收冒充）")
                passive_income = 0.0
        else:
            passive_income = raw_passive or 0
        passive_income = float(passive_income or 0)
        if not passive_income:
            print("[WARN] 護城河：保守配息為 0：維持 0 計（2026-09-23 INC-248 移除「房租常態＋當月實收配息」混口徑退路）")
        try:
            debt_ratio = float(str(snapshot.get("debt_ratio", "0")).replace("%", "")) / 100
        except (TypeError, ValueError):
            debt_ratio = 0.0

        runway = total_assets / monthly_expense if monthly_expense else 0
        liquid_runway = liquid_assets / monthly_expense if monthly_expense else 0
        coverage_ratio = passive_income / monthly_expense if monthly_expense else 0

        securities = snapshot.get("securities") or {}
        if not securities:
            page1 = snapshot.get("page1") or {}
            if isinstance(page1, dict):
                securities = page1.get("securities") or {}
        if not securities:
            funds = snapshot.get("funds_breakdown") or {}
            if isinstance(funds, dict):
                securities = funds
        semi_exposure = 0
        for name, value in securities.items():
            if isinstance(value, dict):
                value = float(value.get("value", 0) or value.get("market_value", 0) or 0)
            elif not isinstance(value, (int, float)):
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    value = 0
            if any(k in name for k in self.semiconductor_keywords):
                semi_exposure += value
        total_securities = 1
        for v in securities.values():
            if isinstance(v, dict):
                total_securities += float(v.get("value", 0) or v.get("market_value", 0) or 0)
            elif isinstance(v, (int, float)):
                total_securities += v
        semi_pct = semi_exposure / total_securities * 100 if total_securities else 0

        return {
            "runway_months": round(runway, 1),
            "liquid_runway_months": round(liquid_runway, 1),
            "coverage_ratio": round(coverage_ratio, 4),
            "debt_ratio_pct": round(debt_ratio * 100, 1),
            "semiconductor_exposure_pct": round(semi_pct, 1),
            "alert": self._alert(coverage_ratio, semi_pct, debt_ratio * 100),
        }

    def _alert(self, coverage: float, semi_pct: float, debt_pct: float) -> list[str]:
        alerts: list[str] = []
        if coverage < 1.0:
            alerts.append("RED: passive income < monthly expense")
        if semi_pct > self.SEMI_THRESHOLD:
            alerts.append("YELLOW: semiconductor exposure > 70%")
        if debt_pct > self.DEBT_THRESHOLD:
            alerts.append("RED: debt ratio > 50%")
        return alerts
