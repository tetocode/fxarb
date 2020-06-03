import logging
from abc import ABC, abstractmethod
from typing import Tuple

from .loggermixin import LoggerMixin


class Server(LoggerMixin, ABC):
    def __init__(self, *args, logger: logging.Logger = None, **kwargs):
        super().__init__(*args, logger=logger, **kwargs)

    @abstractmethod
    def is_running(self) -> bool:
        pass

    @property
    @abstractmethod
    def server_address(self) -> Tuple[str, int]:
        pass

    @abstractmethod
    def start(self):
        pass

    @abstractmethod
    def stop(self, timeout: float = None):
        pass

    @abstractmethod
    def join(self, timeout: float = None):
        pass
