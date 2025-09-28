from dataclasses import dataclass
from typing import ClassVar

from wallbox_control.modbus import (
    ModbusFunctionCode,
    WallboxInstrument,
)


@dataclass
class WallboxChargingState:
    state: str
    description_car: str
    description_wb: str


WALLBOX_CHARGING_STATES = {
    2: WallboxChargingState("A1", "No vehicle plugged", "None"),
    3: WallboxChargingState("A2", "No vehicle plugged", "Allows charging"),
    4: WallboxChargingState(
        "B1", "Vehicle plugged without charging request", "Doesn't allow charging"
    ),
    5: WallboxChargingState(
        "B2", "Vehicle plugged without charging request", "Allows charging"
    ),
    6: WallboxChargingState(
        "C1", "Vehicle plugged with charging request", "Doesn't allow charging"
    ),
    7: WallboxChargingState(
        "C2", "Vehicle plugged with charging request", "Allows charging"
    ),
    8: WallboxChargingState("derating", "None", "None"),
    9: WallboxChargingState("E", "None", "None"),
    10: WallboxChargingState("F", "None", "None"),
    11: WallboxChargingState("Error", "None", "None"),
}


def fit_uint16(value: int) -> int:
    if value < 0:
        value = 0
    elif value > 65_535:
        value = 65_535
    return value


class _PropIndexer(type):
    def __new__(cls, name, bases, attrs, **kwargs):
        cls = super().__new__(cls, name, bases, attrs, **kwargs)
        own_props = {n: o for n, o in attrs.items() if isinstance(o, property)}

        cls.OWN_GETTERS = tuple(n for n, p in own_props.items() if p.fget is not None)
        cls.OWN_SETTERS = tuple(
            n for n, p in own_props.items() if p.fget and p.fset is not None
        )

        return cls


class Wallbox(WallboxInstrument, metaclass=_PropIndexer):
    OWN_GETTERS: ClassVar[tuple[str, ...]]
    OWN_SETTERS: ClassVar[tuple[str, ...]]

    def __init__(self, serial_port, slave_address):
        super().__init__(serial_port, slave_address)
        # Keepalive command is modbus_register_layout_version
        self.keepalive_command = "modbus_register_layout_version"

    @property
    def modbus_register_layout_version(self) -> str:
        """Get the Modbus register layout version"""
        value = str(self._read_register(4, ModbusFunctionCode.READ_INPUT_REGISTER))
        if len(value) != 3:
            raise ValueError(f"Unsupported Modbus register layout version: {value}")
        return ".".join(value)

    @property
    def charging_state(self) -> WallboxChargingState:
        """Get the current charging state"""
        value = self._read_register(5, ModbusFunctionCode.READ_INPUT_REGISTER)
        if value not in WALLBOX_CHARGING_STATES:
            raise ValueError(f"Unknown charging state: {value}")
        return WALLBOX_CHARGING_STATES[value]

    @property
    def L1_rms(self) -> float:
        """Get the RMS voltage of L1"""
        return self._read_register(6, ModbusFunctionCode.READ_INPUT_REGISTER) / 10.0

    @property
    def L2_rms(self) -> float:
        """Get the RMS voltage of L2"""
        return self._read_register(7, ModbusFunctionCode.READ_INPUT_REGISTER) / 10.0

    @property
    def L3_rms(self) -> float:
        """Get the RMS voltage of L3"""
        return self._read_register(8, ModbusFunctionCode.READ_INPUT_REGISTER) / 10.0

    @property
    def pcb_temperature(self) -> float:
        """Get the PCB temperature"""
        value = self._read_register(9, ModbusFunctionCode.READ_INPUT_REGISTER)
        # The value is in two's complement format. We convert to a normal integer.
        if value >= 0x8000:
            value -= 0x10000
        return value / 10.0

    @property
    def voltage_L1(self) -> float:
        """Get the voltage of L1"""
        return self._read_register(10, ModbusFunctionCode.READ_INPUT_REGISTER)

    @property
    def voltage_L2(self) -> float:
        """Get the voltage of L2"""
        return self._read_register(11, ModbusFunctionCode.READ_INPUT_REGISTER)

    @property
    def voltage_L3(self) -> float:
        """Get the voltage of L3"""
        return self._read_register(12, ModbusFunctionCode.READ_INPUT_REGISTER)

    @property
    def ext_lock_state(self) -> bool:
        """Get the external lock state
        True if the external lock is engaged, False otherwise
        """
        value = self._read_register(13, ModbusFunctionCode.READ_INPUT_REGISTER)
        if value not in (0, 1):
            raise ValueError(f"Unknown external lock state: {value}")
        return not bool(value)

    @property
    def power_overall(self) -> int:
        """Get the overall power"""
        return self._read_register(14, ModbusFunctionCode.READ_INPUT_REGISTER)

    @property
    def hardware_max_current(self) -> int:
        """Get the hardware maximum current"""
        value = self._read_register(100, ModbusFunctionCode.READ_HOLDING_REGISTER)
        if value < 6 or value > 16:
            raise ValueError(f"Invalid hardware max current: {value}")
        return value

    @property
    def hardware_min_current(self) -> int:
        """Get the hardware minimum current"""
        value = self._read_register(101, ModbusFunctionCode.READ_HOLDING_REGISTER)
        if value < 6 or value > 16:
            raise ValueError(f"Invalid hardware min current: {value}")
        return value

    @property
    def modbus_timeout(self) -> int:
        """Get the Modbus timeout in milliseconds"""
        return self._read_register(257, ModbusFunctionCode.READ_HOLDING_REGISTER)

    @modbus_timeout.setter
    def modbus_timeout(self, value: int) -> bool:
        """Set the Modbus timeout in milliseconds"""
        return self._write_register(257, fit_uint16(value))

    @property
    def standby_control(self) -> bool:
        """Get the standby control state
        True if standby control is enabled, False otherwise
        """
        value = self._read_register(258, ModbusFunctionCode.READ_HOLDING_REGISTER)
        if value == 0:
            return True
        elif value == 4:
            return False
        else:
            raise ValueError(f"Unknown standby control state: {value}")

    @standby_control.setter
    def standby_control(self, value: bool) -> bool:
        """Set the standby control state
        True to enable standby control, False to disable
        """
        return self._write_register(258, 0 if value else 4)

    @property
    def remote_lock(self) -> bool:
        """Get the remote lock state
        True if locked, False if unlocked
        """
        value = self._read_register(259, ModbusFunctionCode.READ_HOLDING_REGISTER)
        if value in (0, 1):
            return not bool(value)
        else:
            raise ValueError(f"Unknown remote lock state: {value}")

    @remote_lock.setter
    def remote_lock(self, value: bool) -> bool:
        """Set the remote lock state
        True to lock, False to unlock
        """
        return self._write_register(259, 0 if value else 1)

    @property
    def max_current(self) -> float:
        """Get the maximum current in Amperes"""
        return self._read_register(261, ModbusFunctionCode.READ_HOLDING_REGISTER) / 10.0

    @max_current.setter
    def max_current(self, value: float) -> bool:
        """Set the maximum current in Amperes"""
        int_value = int(value * 10)
        if int_value != 0 and (int_value < 60 or int_value > 160):
            raise ValueError(f"Invalid max current: {value}")
        return self._write_register(261, fit_uint16(int_value))

    @property
    def failsafe_current(self) -> float:
        """Get the failsafe current in Amperes"""
        value = self._read_register(262, ModbusFunctionCode.READ_HOLDING_REGISTER)
        if (value >= 60 and value <= 160) or value == 0:
            return value / 10.0
        else:
            raise ValueError(f"Invalid failsafe current: {value}")

    @failsafe_current.setter
    def failsafe_current(self, value: float) -> bool:
        """Set the failsafe current in Amperes
        Set to 0 to disable failsafe current
        """
        int_value = int(value * 10)
        if (int_value < 60 or int_value > 160) and int_value != 0:
            raise ValueError(f"Invalid failsafe current: {value}")
        return self._write_register(262, fit_uint16(int_value))
