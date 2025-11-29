from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, call

import pytest

from wallbox_control.limits import LimitDecision, LimitSource
from wallbox_control.main import WallboxController, gpio_worker


@dataclass
class _RecordedWallbox:
    OWN_GETTERS: tuple[str, ...] = ("max_current",)
    OWN_SETTERS: tuple[str, ...] = ("max_current",)

    def __post_init__(self) -> None:
        self.max_current_calls: list[float] = []
        self._max_current: float | None = None

    @property
    def max_current(self) -> float | None:
        return self._max_current

    @max_current.setter
    def max_current(self, value: float) -> None:
        self.max_current_calls.append(value)
        self._max_current = value


@pytest.fixture()
def fake_wallbox_factory(monkeypatch):
    instances: list[_RecordedWallbox] = []

    def factory(*_args, **_kwargs):
        wallbox = _RecordedWallbox()
        instances.append(wallbox)
        return wallbox

    monkeypatch.setattr("wallbox_control.main.Wallbox", factory)
    return instances


def test_manual_request_updates_wallbox(fake_wallbox_factory):
    controller = WallboxController("/dev/null", 1)
    wallbox = fake_wallbox_factory[-1]

    decision = controller.request_manual_max_current(16.0)

    assert decision.applied_current == 16.0
    assert decision.overridden is False
    assert wallbox.max_current_calls == [16.0]


def test_hardware_override_applies_lower_limit(fake_wallbox_factory):
    controller = WallboxController("/dev/null", 1)
    wallbox = fake_wallbox_factory[-1]
    controller.request_manual_max_current(16.0)

    decision = controller.update_hardware_inputs(True, True)

    assert decision.applied_current == 6.0
    assert decision.origin == LimitSource.HARDWARE_INPUT.value
    assert decision.overridden is True
    assert wallbox.max_current_calls == [16.0, 6.0]


def test_repeated_manual_request_avoids_duplicate_write(fake_wallbox_factory):
    controller = WallboxController("/dev/null", 1)
    wallbox = fake_wallbox_factory[-1]

    controller.request_manual_max_current(16.0)
    controller.request_manual_max_current(16.0)

    assert wallbox.max_current_calls == [16.0]


def test_gpio_worker_reacts_to_state_changes(monkeypatch):
    sequences = {
        "GPIO13": [False, True],
        "GPIO14": [False, False],
    }

    class DummyButton:
        def __init__(self, label: str, pull_up: bool = False) -> None:  # noqa: FBT001, FBT002
            self._label = label
            self._index = 0

        @property
        def is_pressed(self) -> bool:
            values = sequences[self._label]
            if self._index >= len(values):
                return values[-1]
            value = values[self._index]
            self._index += 1
            return value

    monkeypatch.setattr("wallbox_control.main.Button", DummyButton)

    sleep_calls = {"count": 0}

    def fake_sleep(_duration: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 3:
            raise KeyboardInterrupt

    monkeypatch.setattr("wallbox_control.main.time.sleep", fake_sleep)

    controller = MagicMock()
    controller.update_hardware_inputs = MagicMock(
        side_effect=[
            LimitDecision(applied_current=None, origin=None, overridden=False, snapshots={}),
            LimitDecision(
                applied_current=6.0,
                origin=LimitSource.HARDWARE_INPUT.value,
                overridden=True,
                snapshots={},
            ),
        ]
    )

    with pytest.raises(KeyboardInterrupt):
        gpio_worker(controller)

    assert controller.update_hardware_inputs.call_args_list == [
        call(False, False),
        call(True, False),
    ]

