"""Asset Moat Monitor — 計算資產護城河指標（Task 1）"""
from __future__ import annotations

from typing import Any


class AssetMoatMonitor:
    semiconductor_keywords = [
        "0050", "006208", "2330", "台積", "半導體", "electronics",
    ]

    def compute(self, snapshot: dict) -> dict:
        total_assets = snapshot.get("total_assets") or 0
        monthly_expense = snapshot.get("monthly_expense") or 1
        liquid_assets = snapshot.get("liquid_assets") or 0
        passive_income = snapshot.get("passive_income") or 0
        debt_ratio = snapshot.get("debt_ratio") or 0

        runway = total_assets / monthly_expense if monthly_expense else 0
        liquid_runway = liquid_assets / monthly_expense if monthly_expense else 0
        coverage_ratio = passive_income / monthly_expense if monthly_expense else 0

        securities = snapshot.get("securities") or {}
        semi_exposure = 0
        for name, value in securities.items():
            if any(k in name for k in self.semiconductor_keywords):
                semi_exposure += value
        total_securities = sum(securities.values()) if securities else 1
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
        if semi_pct > 70:
            alerts.append("YELLOW: semiconductor exposure > 70%")
        if debt_pct > 50:
            alerts.append("RED: debt ratio > 50%")
        return alerts
