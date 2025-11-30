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


def test_hardware_limit_caps_manual_request():
    """Hardware limit sets maximum, manual request is capped by it."""
    manager = CurrentLimitManager()
    manager.request_manual(16.0)

    # Hardware allows only 6A max
    override_snapshot = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=6.0,
        description="Hardware limit: 6A max",
    )

    decision = manager.apply_override_snapshot(override_snapshot)

    # Should apply 6A (capped by hardware), origin should be manual (since that's what's being limited)
    assert decision.applied_current == 6.0
    assert decision.origin == LimitSource.MANUAL_REQUEST.value
    assert decision.overridden is True  # Manual request is overridden by hardware cap
    assert decision.snapshots[LimitSource.HARDWARE_INPUT.value]["current_amps"] == 6.0


def test_manual_request_below_hardware_limit():
    """Manual request below hardware limit should be applied."""
    manager = CurrentLimitManager()

    # Hardware allows up to 16A
    override_snapshot = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=16.0,
        description="Hardware limit: 16A max",
    )
    manager.apply_override_snapshot(override_snapshot)

    # Manual request is lower at 12A
    decision = manager.request_manual(12.0)

    # Should apply 12A from manual request
    assert decision.applied_current == 12.0
    assert decision.origin == LimitSource.MANUAL_REQUEST.value
    assert decision.overridden is False  # Manual request is not being overridden


def test_hardware_limit_increase_allows_manual_request():
    """When hardware limit increases, manual request should be applied if within new limit."""
    manager = CurrentLimitManager()
    manager.request_manual(16.0)

    # Hardware initially allows only 6A
    hw_snapshot_6a = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=6.0,
        description="Hardware limit: 6A max",
    )
    decision = manager.apply_override_snapshot(hw_snapshot_6a)
    assert decision.applied_current == 6.0

    # Hardware limit increases to 16A
    hw_snapshot_16a = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=16.0,
        description="Hardware limit: 16A max",
    )
    decision = manager.apply_override_snapshot(hw_snapshot_16a)

    # Should now apply the full 16A manual request
    assert decision.applied_current == 16.0
    assert decision.origin == LimitSource.MANUAL_REQUEST.value
    assert decision.overridden is False


def test_clearing_hardware_limit_restores_manual_request():
    """Clearing hardware limit should restore full manual request."""
    manager = CurrentLimitManager()
    manager.request_manual(16.0)

    override_snapshot = LimitSnapshot(
        source=LimitSource.HARDWARE_INPUT,
        enforced=True,
        current_amps=6.0,
        description="Hardware limit: 6A max",
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
