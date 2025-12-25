from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LimitSource(str, Enum):
    HARDWARE_INPUT = "hardware_inputs"
    MANUAL_REQUEST = "manual_request"


@dataclass(slots=True)
class LimitSnapshot:
    source: LimitSource
    enforced: bool
    current_amps: float | None
    description: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.value,
            "enforced": self.enforced,
            "current_amps": self.current_amps,
            "description": self.description,
            "details": self.details,
        }


@dataclass(slots=True)
class LimitDecision:
    applied_current: float | None
    origin: str | None
    overridden: bool
    snapshots: dict[str, dict[str, Any]]


class CurrentLimitManager:
    def __init__(self) -> None:
        self._snapshots: dict[LimitSource, LimitSnapshot] = {}
        self._manual_request: float | None = None
        self._last_decision: LimitDecision | None = None

    def request_manual(self, value: float | None) -> LimitDecision:
        self._manual_request = value
        description = "Manual request active" if value is not None else "Manual request cleared"
        snapshot = LimitSnapshot(
            source=LimitSource.MANUAL_REQUEST,
            enforced=value is not None,
            current_amps=value,
            description=description,
        )
        self._snapshots[LimitSource.MANUAL_REQUEST] = snapshot
        return self._resolve()

    def apply_override_snapshot(self, snapshot: LimitSnapshot) -> LimitDecision:
        self._snapshots[snapshot.source] = snapshot
        return self._resolve()

    def clear_source(self, source: LimitSource) -> LimitDecision:
        self._snapshots.pop(source, None)
        if source == LimitSource.MANUAL_REQUEST:
            self._manual_request = None
        return self._resolve()

    def _resolve(self) -> LimitDecision:
        # Get hardware limit (maximum allowed current)
        hardware_limits = [
            snap
            for snap in self._snapshots.values()
            if snap.source != LimitSource.MANUAL_REQUEST and snap.enforced and snap.current_amps is not None
        ]

        # Get manual request (desired current)
        manual_snap = self._snapshots.get(LimitSource.MANUAL_REQUEST)
        manual_current = manual_snap.current_amps if manual_snap and manual_snap.enforced else None

        # Determine applied current based on hardware limit and manual request
        if hardware_limits and manual_current is not None:
            # Both hardware limit and manual request exist
            hw_max = min(snap.current_amps for snap in hardware_limits)
            applied_current = min(manual_current, hw_max)
            origin = LimitSource.MANUAL_REQUEST.value
            overridden = manual_current > hw_max  # Manual is overridden if it exceeds hardware limit
        elif hardware_limits:
            # Only hardware limit exists, no manual request
            applied_current = min(snap.current_amps for snap in hardware_limits)
            origin = next(
                snap.source.value
                for snap in hardware_limits
                if snap.current_amps == applied_current
            )
            overridden = False
        elif manual_current is not None:
            # Only manual request exists, no hardware limit
            applied_current = manual_current
            origin = LimitSource.MANUAL_REQUEST.value
            overridden = False
        else:
            # No limits at all
            applied_current = None
            origin = None
            overridden = False

        decision = LimitDecision(
            applied_current=applied_current,
            origin=origin,
            overridden=overridden,
            snapshots={src.value: snap.as_dict() for src, snap in self._snapshots.items()},
        )
        self._last_decision = decision
        return decision

    def last_decision(self) -> LimitDecision | None:
        return self._last_decision

    def debug_snapshot(self) -> dict[str, Any]:
        decision = self._last_decision
        return {
            "manual_request": self._manual_request,
            "decision": {
                "applied_current": decision.applied_current if decision else None,
                "origin": decision.origin if decision else None,
                "overridden": decision.overridden if decision else False,
            },
            "sources": {src.value: snap.as_dict() for src, snap in self._snapshots.items()},
        }


class HardwareInputLimiter:
    def __init__(self, pin_label: str = "GPIO6") -> None:
        self._pin_label = pin_label
        self._last_inputs: tuple[bool] | None = None

    def evaluate(self, first_high: bool) -> LimitSnapshot:
        self._last_inputs = (first_high,)

        if not first_high:
            current = 16.0
            mode = "normal_charge"
            description = "Hardware override: input 1 LOW -> 16A"
        else:
            current = 6.0
            mode = "reduced_charge"
            description = "Hardware override: input 1 HIGH -> 6A"

        return LimitSnapshot(
            source=LimitSource.HARDWARE_INPUT,
            enforced=True,
            current_amps=current,
            description=description,
            details={
                "inputs": {
                    self._pin_label: first_high,
                },
                "mode": mode,
            },
        )

    def last_inputs(self) -> tuple[bool, bool] | None:
        return self._last_inputs
