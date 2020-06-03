import logging
from abc import ABC, abstractmethod
from typing import Tuple


class NodeABC(ABC):
    DEFAULT_ADDRESS = ('127.0.0.1', 0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = logging.getLogger('{}'.format(self.__class__.__name__))

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self._logger.critical(msg, *args, **kwargs)

    def fatal(self, msg: str, *args, **kwargs):
        self._logger.fatal(msg, *args, **kwargs)

    def exception(self, msg: str, *args, **kwargs):
        self._logger.exception(msg, *args, **kwargs)

    @abstractmethod
    def is_running(self) -> bool:
        pass

    @property
    @abstractmethod
    def bind_address(self) -> Tuple[str, int]:
        pass

    @abstractmethod
    def start(self) -> 'NodeABC':
        pass

    @abstractmethod
    def stop(self, timeout: float = None) -> 'NodeABC':
        pass

    @abstractmethod
    def join(self, timeout: float = None):
        pass
