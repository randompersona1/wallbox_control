from dataclasses import dataclass
from enum import Enum
import queue

from wallbox import Wallbox


class CommandType(Enum):
    GET = "get"
    SET = "set"


@dataclass
class Command:
    command_type: CommandType
    parameter: str
    value: str = None
    return_value: str = None


class Controller:
    def __init__(self, port: str, address: int):
        self.wallbox = Wallbox(port, address)
        self.GETTERS = self.wallbox.OWN_GETTERS
        self.SETTERS = self.wallbox.OWN_SETTERS

        self.command_queue = queue.Queue()

    def read(self, command: Command):
        if command.parameter in self.GETTERS:
            self.command_queue.put(command)

    def write(self, command: Command):
        if command.parameter in self.SETTERS:
            self.command_queue.put(command)

    def run(self) -> None:
        while True:
            command = self.command_queue.get()


controller = Controller("/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_BG018W3B-if00-port0", 1)
print(controller.wallbox.OWN_GETTERS)
print(controller.wallbox.OWN_SETTERS)
