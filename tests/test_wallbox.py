from unittest.mock import MagicMock

import pytest

from wallbox_control.wallbox import (
    WALLBOX_CHARGING_STATES,
    ModbusFunctionCode,
    Wallbox,
)


@pytest.fixture()
def wallbox() -> Wallbox:
    instance = object.__new__(Wallbox)
    instance._read_register = MagicMock()
    instance._read_32bit_from_registers = MagicMock()
    instance._write_register = MagicMock(return_value=True)
    return instance


def test_modbus_register_layout_version_valid(wallbox: Wallbox):
    wallbox._read_register.return_value = 123

    assert wallbox.modbus_register_layout_version == "1.2.3"
    wallbox._read_register.assert_called_once_with(4, ModbusFunctionCode.READ_INPUT_REGISTER)


def test_modbus_register_layout_version_invalid(wallbox: Wallbox):
    wallbox._read_register.return_value = 99

    with pytest.raises(ValueError, match="Unsupported Modbus register layout version"):
        _ = wallbox.modbus_register_layout_version


def test_charging_state_known_value(wallbox: Wallbox):
    wallbox._read_register.return_value = 5

    state = wallbox.charging_state

    assert state is WALLBOX_CHARGING_STATES[5]
    wallbox._read_register.assert_called_once_with(5, ModbusFunctionCode.READ_INPUT_REGISTER)


def test_charging_state_unknown_value_raises(wallbox: Wallbox):
    wallbox._read_register.return_value = 999

    with pytest.raises(ValueError, match="Unknown charging state"):
        _ = wallbox.charging_state


def test_pcb_temperature_handles_twos_complement(wallbox: Wallbox):
    wallbox._read_register.return_value = 0xFF9C

    assert wallbox.pcb_temperature == pytest.approx(-10.0, rel=1e-6)


def test_ext_lock_state_boolean_translation(wallbox: Wallbox):
    wallbox._read_register.return_value = 0
    assert wallbox.ext_lock_state is True

    wallbox._read_register.return_value = 1
    assert wallbox.ext_lock_state is False

    wallbox._read_register.return_value = 3
    with pytest.raises(ValueError, match="Unknown external lock state"):
        _ = wallbox.ext_lock_state


def test_energy_since_power_on_reads_combined_registers(wallbox: Wallbox):
    wallbox._read_32bit_from_registers.return_value = 123456

    assert wallbox.energy_since_power_on == 123456
    wallbox._read_32bit_from_registers.assert_called_once_with(
        15, 16, ModbusFunctionCode.READ_INPUT_REGISTER
    )


def test_energy_since_installation_reads_combined_registers(wallbox: Wallbox):
    wallbox._read_32bit_from_registers.return_value = 987654

    assert wallbox.energy_since_installation == 987654
    wallbox._read_32bit_from_registers.assert_called_once_with(
        17, 18, ModbusFunctionCode.READ_INPUT_REGISTER
    )


def test_hardware_current_bounds_enforced(wallbox: Wallbox):
    wallbox._read_register.return_value = 8
    assert wallbox.hardware_max_current == 8

    wallbox._read_register.return_value = 20
    with pytest.raises(ValueError, match="Invalid hardware max current"):
        _ = wallbox.hardware_max_current

    wallbox._read_register.return_value = 5
    with pytest.raises(ValueError, match="Invalid hardware min current"):
        _ = wallbox.hardware_min_current


def test_modbus_timeout_roundtrip(wallbox: Wallbox):
    wallbox._read_register.return_value = 250
    assert wallbox.modbus_timeout == 250

    wallbox._write_register.return_value = True
    wallbox.modbus_timeout = 500
    wallbox._write_register.assert_called_with(257, 500)


def test_setters_validate_ranges(wallbox: Wallbox):
    wallbox._write_register.return_value = True

    wallbox.max_current = 16.0
    wallbox._write_register.assert_called_with(261, 160)

    with pytest.raises(ValueError, match="Invalid max current"):
        wallbox.max_current = 5.0

    wallbox.failsafe_current = 10.0
    wallbox._write_register.assert_called_with(262, 100)

    with pytest.raises(ValueError, match="Invalid failsafe current"):
        wallbox.failsafe_current = 25.0


def test_standby_control_state_validation(wallbox: Wallbox):
    wallbox._read_register.return_value = 0
    assert wallbox.standby_control is True

    wallbox._read_register.return_value = 4
    assert wallbox.standby_control is False

    wallbox._read_register.return_value = 2
    with pytest.raises(ValueError, match="Unknown standby control state"):
        _ = wallbox.standby_control

    wallbox._write_register.return_value = True
    wallbox.standby_control = True
    wallbox._write_register.assert_called_with(258, 0)


def test_remote_lock_state_validation(wallbox: Wallbox):
    wallbox._read_register.return_value = 0
    assert wallbox.remote_lock is True

    wallbox._read_register.return_value = 1
    assert wallbox.remote_lock is False

    wallbox._read_register.return_value = 2
    with pytest.raises(ValueError, match="Unknown remote lock state"):
        _ = wallbox.remote_lock

    wallbox._write_register.return_value = True
    wallbox.remote_lock = True
    wallbox._write_register.assert_called_with(259, 0)

