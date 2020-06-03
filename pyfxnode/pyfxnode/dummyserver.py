from typing import Tuple

from .server import Server


class DummyServer(Server):
    @property
    def server_address(self) -> Tuple[str, int]:
        return '0.0.0.0', 0

    def join(self, timeout: float = None):
        return

    def start(self):
        return

    def stop(self, timeout: float = None):
        return

    def is_running(self) -> bool:
        return False
