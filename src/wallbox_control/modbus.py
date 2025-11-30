import logging
import time
from enum import Enum

import minimalmodbus
import serial

DEFAULT_BAUDRATE = 19200
DEFAULT_BYTESIZE = 8
DEFAULT_STOPBITS = 1
DEFAULT_PARITY = minimalmodbus.serial.PARITY_EVEN
WRITE_HOLDING_REGISTER = 6
MAX_RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY = 0.5  # seconds


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
        self._serial_port = serial_port
        self._slave_address = slave_address
        super().__init__(serial_port, slave_address)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._configure_serial()

    def _configure_serial(self) -> None:
        """Configure serial port parameters for the wallbox"""
        self.serial.baudrate = DEFAULT_BAUDRATE
        self.serial.bytesize = DEFAULT_BYTESIZE
        self.serial.parity = DEFAULT_PARITY
        self.serial.stopbits = DEFAULT_STOPBITS
        self.mode = minimalmodbus.MODE_RTU

    def _reconnect_serial(self) -> bool:
        """
        Attempt to reconnect the serial port.

        Returns:
            True if reconnection successful, False otherwise
        """
        try:
            # Close existing connection if it exists
            if hasattr(self, 'serial') and self.serial and self.serial.is_open:
                try:
                    self.serial.close()
                except Exception:
                    pass  # Ignore errors when closing a potentially broken connection

            # Wait a moment for the device to stabilize
            time.sleep(RECONNECT_DELAY)

            # Create a new serial connection
            self.serial = serial.Serial(
                port=self._serial_port,
                baudrate=DEFAULT_BAUDRATE,
                bytesize=DEFAULT_BYTESIZE,
                parity=DEFAULT_PARITY,
                stopbits=DEFAULT_STOPBITS,
                timeout=1.0
            )
            self.mode = minimalmodbus.MODE_RTU

            self.logger.info("Successfully reconnected to serial port %s", self._serial_port)
            return True

        except Exception as exc:
            self.logger.error("Failed to reconnect serial port: %s", exc)
            return False

    def _execute_with_reconnect(self, operation, *args, **kwargs):
        """
        Execute a Modbus operation with automatic reconnection on serial port errors.

        Args:
            operation: The operation function to execute
            *args: Positional arguments for the operation
            **kwargs: Keyword arguments for the operation

        Returns:
            The result of the operation

        Raises:
            RuntimeError: If operation fails after all reconnection attempts
        """
        last_exception = None

        for attempt in range(MAX_RECONNECT_ATTEMPTS):
            try:
                return operation(*args, **kwargs)

            except (OSError, serial.SerialException) as exc:
                # These exceptions indicate serial port issues that might be fixable with reconnection
                last_exception = exc

                if attempt < MAX_RECONNECT_ATTEMPTS - 1:
                    self.logger.warning(
                        "Serial port error on attempt %d/%d: %s - attempting reconnection",
                        attempt + 1,
                        MAX_RECONNECT_ATTEMPTS,
                        exc
                    )

                    if not self._reconnect_serial():
                        self.logger.error("Reconnection failed on attempt %d/%d", attempt + 1, MAX_RECONNECT_ATTEMPTS)
                        continue
                else:
                    self.logger.error(
                        "Serial port error persists after %d attempts: %s",
                        MAX_RECONNECT_ATTEMPTS,
                        exc
                    )

            except Exception:
                # For other exceptions, don't retry
                raise

        # If we get here, all retry attempts failed
        raise RuntimeError(
            f"Failed to execute operation after {MAX_RECONNECT_ATTEMPTS} attempts"
        ) from last_exception

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
            return self._execute_with_reconnect(
                self.read_register,
                register_address,
                0,
                function_code.value
            )
        except Exception as exc:
            logger = getattr(
                self,
                "logger",
                logging.getLogger(f"{__name__}.{self.__class__.__name__}"),
            )
            logger.exception(
                "Failed to read register %s with function %s", register_address, function_code
            )
            raise RuntimeError(
                f"Failed to read register {register_address}: {exc}"
            ) from exc

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
        def _read_both_registers():
            high_value = self.read_register(high_register, 0, function_code.value)
            low_value = self.read_register(low_register, 0, function_code.value)
            return (high_value << 16) + low_value

        try:
            return self._execute_with_reconnect(_read_both_registers)
        except Exception as exc:
            logger = getattr(
                self,
                "logger",
                logging.getLogger(f"{__name__}.{self.__class__.__name__}"),
            )
            logger.exception(
                "Failed to read 32-bit register pair (%s, %s) with function %s",
                high_register,
                low_register,
                function_code,
            )
            raise RuntimeError(
                f"Failed to read 32-bit value from registers {high_register},{low_register}: {exc}"
            ) from exc

    def _write_register(self, register_address: int, value: int) -> bool:
        """
        Write a value to a register using the specified value type.

        Args:
            register_address: The register address to write to
            value: The ModbusValue containing both the value and type information
        """
        def _write_and_verify():
            self.write_register(register_address, value, 0, WRITE_HOLDING_REGISTER)
            v = self.read_register(
                register_address, 0, ModbusFunctionCode.READ_HOLDING_REGISTER.value
            )
            if v != value:
                message = (
                    f"Verification mismatch after writing register {register_address}: "
                    f"expected {value}, read back {v}"
                )
                raise RuntimeError(message)
            return True

        try:
            return self._execute_with_reconnect(_write_and_verify)
        except Exception as exc:
            logger = getattr(
                self,
                "logger",
                logging.getLogger(f"{__name__}.{self.__class__.__name__}"),
            )
            logger.exception(
                "Failed to write register %s with value %s", register_address, value
            )
            raise RuntimeError(
                f"Failed to write value {value} to register {register_address}: {exc}"
            ) from exc
