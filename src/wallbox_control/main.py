import logging
import threading
import time
from contextlib import contextmanager
from typing import Any

from gpiozero import Button

from wallbox_control.error_handling import install_global_exception_logging
from wallbox_control.limits import (
    CurrentLimitManager,
    HardwareInputLimiter,
    LimitDecision,
)
from wallbox_control.wallbox import Wallbox


class WallboxController:
    """
    Thread-safe controller for wallbox operations with automatic keepalive.

    This controller wraps the Wallbox class to provide thread-safe access to all
    wallbox properties and automatically sends keepalive messages every 10 seconds.
    """

    def __init__(self, port: str, address: int, keepalive_interval: float = 10.0):
        """
        Initialize the wallbox controller.

        Args:
            port: Serial port path
            address: Modbus slave address of the wallbox
            keepalive_interval: Keepalive interval in seconds (max 10 seconds)
        """
        self.wallbox = Wallbox(port, address)
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._keepalive_interval = min(
            keepalive_interval, 10.0
        )  # Ensure max 10 seconds
        self._keepalive_thread: threading.Thread | None = None
        self._stop_keepalive = threading.Event()
        self._running = False

        # Store available properties for introspection
        self.GETTERS = self.wallbox.OWN_GETTERS
        self.SETTERS = self.wallbox.OWN_SETTERS

        # Configure logging
        self.logger = logging.getLogger(__name__)
        self._limit_manager = CurrentLimitManager()
        self._hardware_limiter = HardwareInputLimiter()
        self._last_limit_decision: LimitDecision | None = None
        self._last_applied_current: float | None = None

    @contextmanager
    def _thread_safe_access(self):
        """Context manager for thread-safe access to the wallbox."""
        with self._lock:
            yield

    def start(self):
        """Start the controller and begin keepalive messages."""
        with self._lock:
            if self._running:
                return

            self._running = True
            self._stop_keepalive.clear()

            # Start keepalive thread
            self._keepalive_thread = threading.Thread(
                target=self._keepalive_worker, daemon=True, name="WallboxKeepalive"
            )
            self._keepalive_thread.start()
            self.logger.info(
                "WallboxController started with keepalive interval: %.1fs",
                self._keepalive_interval,
            )

    def stop(self):
        """Stop the controller and halt keepalive messages."""
        with self._lock:
            if not self._running:
                return

            self._running = False
            self._stop_keepalive.set()

            if self._keepalive_thread and self._keepalive_thread.is_alive():
                self._keepalive_thread.join(timeout=2.0)

            self.logger.info("WallboxController stopped")

    def _keepalive_worker(self):
        """Background thread that sends keepalive messages."""
        while not self._stop_keepalive.is_set():
            try:
                with self._thread_safe_access():
                    # Send keepalive by reading the modbus register layout version
                    version = self.wallbox.modbus_register_layout_version
                    self.logger.debug("Keepalive sent, version: %s", version)
            except Exception:
                self.logger.exception("Keepalive failed")

            # Wait for the specified interval or until stop is requested
            self._stop_keepalive.wait(self._keepalive_interval)

    def _apply_decision(self, decision: LimitDecision) -> float | None:
        target = decision.applied_current
        if target is None:
            return None

        if self._last_applied_current is not None and abs(self._last_applied_current - target) < 0.05:
            return target

        origin = decision.origin or "unknown"
        try:
            self.wallbox.max_current = target
            self._last_applied_current = target
            log_level = logging.INFO if decision.overridden else logging.DEBUG
            self.logger.log(
                log_level,
                "Max current updated to %.1fA (source=%s)",
                target,
                origin,
            )
            return target
        except Exception:
            self._last_applied_current = None
            self.logger.exception(
                "Failed to apply max current decision from %s", origin
            )
            return None

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    def __del__(self):
        """Destructor to ensure cleanup."""
        self.stop()

    # Thread-safe property accessors - Read-only properties
    def get_modbus_register_layout_version(self) -> str:
        """Get the Modbus register layout version (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.modbus_register_layout_version

    def get_charging_state(self):
        """Get the current charging state (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.charging_state

    def get_l1_rms(self) -> float:
        """Get the RMS voltage of L1 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.L1_rms

    def get_l2_rms(self) -> float:
        """Get the RMS voltage of L2 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.L2_rms

    def get_l3_rms(self) -> float:
        """Get the RMS voltage of L3 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.L3_rms

    def get_pcb_temperature(self) -> float:
        """Get the PCB temperature (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.pcb_temperature

    def get_voltage_l1(self) -> float:
        """Get the voltage of L1 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.voltage_L1

    def get_voltage_l2(self) -> float:
        """Get the voltage of L2 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.voltage_L2

    def get_voltage_l3(self) -> float:
        """Get the voltage of L3 (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.voltage_L3

    def get_ext_lock_state(self) -> bool:
        """Get the external lock state (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.ext_lock_state

    def get_power_overall(self) -> int:
        """Get the overall power (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.power_overall

    def get_energy_since_power_on(self) -> int:
        """Get the energy consumed since power on in VAh (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.energy_since_power_on

    def get_energy_since_installation(self) -> int:
        """Get the energy consumed since installation in VAh (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.energy_since_installation

    def get_hardware_max_current(self) -> int:
        """Get the hardware maximum current (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.hardware_max_current

    def get_hardware_min_current(self) -> int:
        """Get the hardware minimum current (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.hardware_min_current

    def get_modbus_timeout(self) -> int:
        """Get the Modbus timeout in milliseconds (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.modbus_timeout

    def set_modbus_timeout(self, value: int) -> bool:
        """Set the Modbus timeout in milliseconds (thread-safe)."""
        with self._thread_safe_access():
            self.wallbox.modbus_timeout = value
            return True

    def get_standby_control(self) -> bool:
        """Get the standby control state (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.standby_control

    def set_standby_control(self, value: bool) -> bool:
        """Set the standby control state (thread-safe)."""
        with self._thread_safe_access():
            self.wallbox.standby_control = value
            return True

    def get_remote_lock(self) -> bool:
        """Get the remote lock state (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.remote_lock

    def set_remote_lock(self, value: bool) -> bool:
        """Set the remote lock state (thread-safe)."""
        with self._thread_safe_access():
            self.wallbox.remote_lock = value
            return True

    def get_max_current(self) -> float:
        """Get the maximum current in Amperes (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.max_current

    def set_max_current(self, value: float) -> bool:
        """Set the maximum current in Amperes (thread-safe)."""
        decision = self.request_manual_max_current(value)
        return decision.applied_current == value and not decision.overridden

    def request_manual_max_current(self, value: float) -> LimitDecision:
        """Request a manual maximum current and apply current limits."""
        with self._thread_safe_access():
            decision = self._limit_manager.request_manual(value)
            self._last_limit_decision = decision
            applied = self._apply_decision(decision)
            decision.applied_current = applied
            return decision

    def update_hardware_inputs(self, gpio13_high: bool, gpio14_high: bool) -> LimitDecision:
        """Update the hardware input override state and apply resulting limits."""
        with self._thread_safe_access():
            snapshot = self._hardware_limiter.evaluate(gpio13_high, gpio14_high)
            decision = self._limit_manager.apply_override_snapshot(snapshot)
            self._last_limit_decision = decision
            applied = self._apply_decision(decision)
            decision.applied_current = applied
            return decision

    def get_limit_debug(self) -> dict[str, Any]:
        """Return internal current limit debug information."""
        with self._thread_safe_access():
            return self._limit_manager.debug_snapshot()

    def get_failsafe_current(self) -> float:
        """Get the failsafe current in Amperes (thread-safe)."""
        with self._thread_safe_access():
            return self.wallbox.failsafe_current

    def set_failsafe_current(self, value: float) -> bool:
        """Set the failsafe current in Amperes (thread-safe)."""
        with self._thread_safe_access():
            self.wallbox.failsafe_current = value
            return True

    # Generic property access methods
    def get_property(self, property_name: str):
        """Get any wallbox property by name (thread-safe)."""
        if property_name not in self.GETTERS:
            raise AttributeError(
                f"Property '{property_name}' is not a readable property"
            )

        with self._thread_safe_access():
            return getattr(self.wallbox, property_name)

    def set_property(self, property_name: str, value) -> bool:
        """Set any wallbox property by name (thread-safe)."""
        if property_name not in self.SETTERS:
            raise AttributeError(
                f"Property '{property_name}' is not a writable property"
            )

        with self._thread_safe_access():
            setattr(self.wallbox, property_name, value)
            return True

    def get_all_properties(self) -> dict:
        """Get all readable properties as a dictionary (thread-safe)."""
        result = {}
        with self._thread_safe_access():
            for prop_name in self.GETTERS:
                try:
                    result[prop_name] = getattr(self.wallbox, prop_name)
                except Exception as e:
                    result[prop_name] = f"Error: {e}"
            result["current_limit"] = self._limit_manager.debug_snapshot()
        return result


def gpio_worker(wallbox_controller: WallboxController):
    logger = logging.getLogger("GPIO_worker")

    try:
        button1 = Button("GPIO13", pull_up=False)
        button2 = Button("GPIO14", pull_up=False)
    except Exception:
        logger.exception("Failed to initialize GPIO buttons")
        return

    last_state_1 = None
    last_state_2 = None
    last_target: float | None = None
    logger.info("Started GPIO worker")

    while True:
        try:
            time.sleep(0.5)
            state1 = button1.is_pressed
            state2 = button2.is_pressed

            if last_state_1 == state1 and last_state_2 == state2:
                continue
            last_state_1 = state1
            last_state_2 = state2

            try:
                decision = wallbox_controller.update_hardware_inputs(state1, state2)
                target = decision.applied_current
                if target != last_target:
                    formatted = f"{target:.1f}" if target is not None else "n/a"
                    logger.info(
                        "Hardware inputs -> %sA (GPIO13=%s, GPIO14=%s)",
                        formatted,
                        state1,
                        state2,
                    )
                    last_target = target
            except Exception:
                logger.exception("Failed to set wallbox current")

        except Exception:
            logger.exception("GPIO worker error")
            time.sleep(1.0)  # Wait before retrying to prevent rapid error loops


def main():
    # Configure logging to see keepalive messages
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    install_global_exception_logging(logging.getLogger(__name__))

    logger = logging.getLogger(__name__)

    try:
        # Create controller
        controller = WallboxController(
            port="/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG018W3B-if00-port0", address=1, keepalive_interval=8.0
        )
        controller.start()
        logger.info("Wallbox controller started successfully")
    except Exception:
        logger.exception("Failed to initialize wallbox controller")
        return

    try:
        # Start GPIO worker thread
        gpio_worker_thread = threading.Thread(
            target=gpio_worker, args=(controller,), daemon=True
        )
        gpio_worker_thread.start()
        logger.info("GPIO worker thread started")
    except Exception:
        logger.exception("Failed to start GPIO worker thread")
        controller.stop()
        return

    try:
        # Start web server worker thread
        from wallbox_control.webserver import web_server_worker

        web_worker_thread = threading.Thread(
            target=web_server_worker, args=(controller, "0.0.0.0", 8000), daemon=True
        )
        web_worker_thread.start()
        logger.info("Web server worker thread started")
    except Exception:
        logger.exception("Failed to start web server worker thread")
        controller.stop()
        return

    try:
        # Keep main thread alive
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        logging.info("\nShutting down...")
        controller.stop()
    except Exception:
        logging.getLogger(__name__).exception("Unexpected error in main loop")
        controller.stop()
        raise


if __name__ == "__main__":
    main()
