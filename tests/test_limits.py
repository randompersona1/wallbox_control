import pytest

from wallbox_control.limits import (
    CurrentLimitManager,
    HardwareInputLimiter,
    LimitDecision,
    LimitSnapshot,
    LimitSource,
)


@pytest.mark.parametrize(
    ("first_high", "second_high", "expected_current", "expected_mode"),
    [
        (True, True, 6.0, "reduced_charge"),  # Both HIGH -> 6A reduced charge
        (True, False, 0.0, "no_charge"),  # First HIGH only -> 0A no charge
        (False, True, 16.0, "normal_charge"),  # Second HIGH only -> 16A normal charge
        (False, False, 6.0, "reduced_charge"),  # Both LOW -> 6A reduced charge
    ],
)
def test_hardware_input_limiter_modes(first_high, second_high, expected_current, expected_mode):
    limiter = HardwareInputLimiter(("GPIO13", "GPIO14"))

    snapshot = limiter.evaluate(first_high, second_high)

    assert snapshot.source is LimitSource.HARDWARE_INPUT
    assert snapshot.enforced is True
    assert snapshot.current_amps == expected_current
    assert snapshot.details["mode"] == expected_mode
    assert snapshot.details["inputs"] == {"GPIO13": first_high, "GPIO14": second_high}


def test_current_limit_manager_manual_only():
    manager = CurrentLimitManager()

    decision = manager.request_manual(16.0)

    assert isinstance(decision, LimitDecision)
    assert decision.applied_current == 16.0
    assert decision.overridden is False
    assert decision.origin == LimitSource.MANUAL_REQUEST.value


def test_current_limit_manager_hardware_override_takes_precedence():
    manager = CurrentLimitManager()
    manager.request_manual(16.0)

    override_snapshot = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=6.0,
        description="Lower hardware limit",
    )

    decision = manager.apply_override_snapshot(override_snapshot)

    assert decision.applied_current == 6.0
    assert decision.origin == LimitSource.HARDWARE_INPUT.value
    assert decision.overridden is True
    assert decision.snapshots[LimitSource.HARDWARE_INPUT.value]["current_amps"] == 6.0


def test_clearing_override_restores_manual_request():
    manager = CurrentLimitManager()
    manager.request_manual(16.0)

    override_snapshot = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=6.0,
        description="Lower hardware limit",
    )
    manager.apply_override_snapshot(override_snapshot)

    decision = manager.clear_source(LimitSource.HARDWARE_INPUT)

    assert decision.applied_current == 16.0
    assert decision.overridden is False
    assert decision.origin == LimitSource.MANUAL_REQUEST.value


def test_debug_snapshot_contains_latest_decision_state():
    manager = CurrentLimitManager()
    manager.request_manual(10.0)

    snapshot = manager.debug_snapshot()

    assert snapshot["manual_request"] == 10.0
    assert snapshot["decision"]["applied_current"] == 10.0
    assert snapshot["decision"]["overridden"] is False
    assert snapshot["sources"][LimitSource.MANUAL_REQUEST.value]["current_amps"] == 10.0
