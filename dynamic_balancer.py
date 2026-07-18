"""Dynamic Balancer — 根據 moat monitor 產出再平衡建議 (Task 3)"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class DynamicBalancer:
    SEMI_THRESHOLD = 70.0
    COVERAGE_THRESHOLD = 1.0
    DEBT_THRESHOLD = 50.0
    rules: dict[str, Any] = field(default_factory=dict)

    def suggest(self, allocation: dict[str, float], signals: dict[str, Any]) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        semi = signals.get("semiconductor_exposure_pct", 0)
        coverage = signals.get("coverage_ratio", 1.0)
        debt = signals.get("debt_ratio_pct", 0)

        if semi > self.SEMI_THRESHOLD:
            actions.append({
                "action": "REDUCE_TECH",
                "target": "TW tech / 0050 / 006208",
                "amount_pct": 3.0,
                "reason": f"半導體曝險 {semi:.1f}% > 70% 上限",
                "priority": "P1",
            })

        if coverage < self.COVERAGE_THRESHOLD:
            actions.append({
                "action": "INCREASE_DIVIDEND",
                "target": "配息型 ETF / 債券型基金",
                "amount_pct": 2.0,
                "reason": f"被動收入覆蓋率 {coverage:.1%} < 100%",
                "priority": "P0",
            })

        if debt > self.DEBT_THRESHOLD:
            actions.append({
                "action": "DELEVERAGE",
                "target": "債務調度、暫緩新部位",
                "amount_pct": 0,
                "reason": f"負債比 {debt:.1f}% > 50%",
                "priority": "P0",
            })

        return {"actions": actions, "allocation": allocation}

    def apply_rules_from_file(self, rule_path: str) -> list[dict[str, Any]]:
        path = Path(rule_path)
        if not path.exists():
            return []
        rules = json.loads(path.read_text(encoding="utf-8"))
        return rules.get("auto_actions", [])
