from enum import Enum

import minimalmodbus

DEFAULT_BAUDRATE = 19200
DEFAULT_BYTESIZE = 8
DEFAULT_STOPBITS = 1
DEFAULT_PARITY = minimalmodbus.serial.PARITY_EVEN
WRITE_HOLDING_REGISTER = 6


class ModbusFunctionCode(Enum):
    READ_HOLDING_REGISTER = 3
    READ_INPUT_REGISTER = 4


class WallboxInstrument(minimalmodbus.Instrument):
    """Wallbox Modbus interface for reading and writing wallbox parameters"""

    def __init__(self, serial_port: str, slave_address: int):
        """
        Initialize the Wallbox Modbus interface.

        Args:
            serial_port: Serial port path
            slave_address: Modbus slave address of the wallbox
        """
        super().__init__(serial_port, slave_address)
        self._configure_serial()

    def _configure_serial(self) -> None:
        """Configure serial port parameters for the wallbox"""
        self.serial.baudrate = DEFAULT_BAUDRATE
        self.serial.bytesize = DEFAULT_BYTESIZE
        self.serial.parity = DEFAULT_PARITY
        self.serial.stopbits = DEFAULT_STOPBITS
        self.mode = minimalmodbus.MODE_RTU

    def _read_register(
        self,
        register_address: int,
        function_code: ModbusFunctionCode,
    ) -> int:
        """
        Read a register using the specified container type.

        Args:
            register_address: The register address to read from
            function_code: The Modbus function code to use

        Returns:
            The value read from the register
        """
        try:
            return self.read_register(register_address, 0, function_code.value)
        except Exception as e:
            raise RuntimeError(
                f"Failed to read register {register_address}: {e}"
            ) from e

    def _read_32bit_from_registers(
        self,
        high_register: int,
        low_register: int,
        function_code: ModbusFunctionCode,
    ) -> int:
        """
        Read a 32-bit value from two 16-bit registers.
        
        Args:
            high_register: Register address containing the high 16 bits
            low_register: Register address containing the low 16 bits  
            function_code: The Modbus function code to use
            
        Returns:
            The 32-bit value constructed from the two registers
        """
        try:
            high_value = self.read_register(high_register, 0, function_code.value)
            low_value = self.read_register(low_register, 0, function_code.value)
            # Combine high and low bytes: high_byte * 2^16 + low_byte
            return (high_value << 16) + low_value
        except Exception as e:
            raise RuntimeError(
                f"Failed to read 32-bit value from registers {high_register},{low_register}: {e}"
            ) from e

    def _write_register(self, register_address: int, value: int) -> bool:
        """
        Write a value to a register using the specified value type.

        Args:
            register_address: The register address to write to
            value: The ModbusValue containing both the value and type information
        """
        try:
            self.write_register(register_address, value, 0, WRITE_HOLDING_REGISTER)
        except Exception as e:
            raise RuntimeError(
                f"Failed to write value {value} to register {register_address}: {e}"
            ) from e
        v = self._read_register(
            register_address, ModbusFunctionCode.READ_HOLDING_REGISTER
        )
        return v == value
