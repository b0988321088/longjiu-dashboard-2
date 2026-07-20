"""Asset Moat Monitor — 計算資產護城河指標（Task 1）"""
from __future__ import annotations

from typing import Any


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
            passive_income = float(raw_passive.get("fund_dividend_conservative", 0) or raw_passive.get("total", 0) or 0)
        else:
            passive_income = float(raw_passive or 0)
        if not passive_income:
            passive_income = float(snapshot.get("rent_monthly_actual", 0) or 0) + float(snapshot.get("fund_dividend_monthly", 0) or 0)
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
