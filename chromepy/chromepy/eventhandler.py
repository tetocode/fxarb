import logging
import queue
from abc import ABCMeta, abstractmethod

from gevent import Greenlet


class EventHandlerBase(Greenlet, metaclass=ABCMeta):
    def __init__(self):
        super().__init__(daemon=True)
        self._q = queue.Queue()
        self.start()

    def _run(self):
        while True:
            event = self._q.get()
            try:
                self.on_event(event)
            except Exception as e:
                logging.exception(str(e))

    def send_event(self, event: dict):
        try:
            self._q.put(event)
            return True
        except Exception as e:
            logging.exception(str(e))
            raise

    @abstractmethod
    def on_event(self, event: dict):
        pass
