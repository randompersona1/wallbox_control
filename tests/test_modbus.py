from unittest.mock import MagicMock

import pytest

from wallbox_control.modbus import ModbusFunctionCode, WallboxInstrument


def _make_instrument() -> WallboxInstrument:
    instrument = object.__new__(WallboxInstrument)
    instrument.read_register = MagicMock()
    instrument.write_register = MagicMock()
    return instrument


def test_read_register_success():
    instrument = _make_instrument()
    instrument.read_register.return_value = 42

    result = instrument._read_register(1, ModbusFunctionCode.READ_HOLDING_REGISTER)

    assert result == 42
    instrument.read_register.assert_called_once_with(1, 0, ModbusFunctionCode.READ_HOLDING_REGISTER.value)


def test_read_register_wraps_exception():
    instrument = _make_instrument()
    instrument.read_register.side_effect = ValueError("boom")

    with pytest.raises(RuntimeError, match="Failed to read register 1"):
        instrument._read_register(1, ModbusFunctionCode.READ_INPUT_REGISTER)


def test_write_register_roundtrip_success():
    instrument = _make_instrument()
    instrument.read_register.return_value = 10

    succeeded = instrument._write_register(8, 10)

    assert succeeded is True
    instrument.write_register.assert_called_once_with(8, 10, 0, 6)


def test_write_register_wraps_exception():
    instrument = _make_instrument()
    instrument.write_register.side_effect = OSError("fail")

    with pytest.raises(RuntimeError, match="Failed to write value 5 to register 8"):
        instrument._write_register(8, 5)

