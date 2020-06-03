import copy
import json
import logging
import time
from collections import OrderedDict
from typing import Set

from gevent import Greenlet
from gevent.lock import RLock
from gevent.threading import Lock
from websocket import WebSocketApp

from .dom import DOM
from .domain import Domain
from .eventhandler import EventHandlerBase
from .network import Network
from .page import Page


class DomainHandler(Greenlet):
    def __init__(self, ws_url: str, *, name: str = None):
        super().__init__(daemon=True)
        self.logger = logging.getLogger(name or self.__class__.__name__)

        self._ws = WebSocketApp(url=ws_url,
                                on_open=self.on_open,
                                on_close=self.on_close,
                                on_message=self.on_message,
                                on_error=self.on_error)
        self.dom = DOM(command_func=self.command)
        self.input = Domain(command_func=self.command, name='Input')
        self.network = Network(command_func=self.command)
        self.page = Page(command_func=self.command)
        self.target = Domain(command_func=self.command, name='Target')

        self._domain_map = {
            'DOM': self.dom,
            'Input': self.input,
            'Network': self.network,
            'Page': self.page,
            'Target': self.target,
        }

        self._seq_no = 0
        self._send_command_lock = RLock()
        self._response_queues = OrderedDict()
        self._event_handlers = set()  # type: Set[EventHandlerBase]

        self.start()

    def _run(self):
        try:
            self._ws.run_forever()
        except Exception as e:
            self.logger.exception(str(e))

    def register_event_handler(self, event_handler: EventHandlerBase):
        self._event_handlers.add(event_handler)

    def unregister_event_handler(self, event_handler: EventHandlerBase):
        self._event_handlers.discard(event_handler)

    def _send_command(self, data: dict):
        with self._send_command_lock:
            self._seq_no += 1
            data.update(id=self._seq_no)
            return self._ws.send(data)

    def command(self, method: str, *, callback=None, **params) -> dict:
        data = dict(id=None, method=method, params=copy.deepcopy(params))

        if callback:
            self._callbacks[self._seq_no] = callback
            self.send_command(json.dumps(data))
            return seq_no
        else:
            ev = threading.Event()
            ret = None

            def default_callback(command_res):
                nonlocal ret
                ret = command_res
                ev.set()

            self._callbacks[seq_no] = default_callback
            self.send_command(json.dumps(data))
            ev.wait()
            return ret

    def is_connected(self):
        return self._ws.sock and self._ws.sock.connected

    def wait_connected(self, timeout: float = 10.0):
        assert timeout > 0
        step = 0.01
        for _ in range(int(timeout / step)):
            if self.is_connected():
                break
            time.sleep(step)
        assert self.is_connected()

    def on_open(self, ws):
        self.logger.info('#on_open')

    def on_close(self, ws):
        self.logger.info('#on_close')

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('method'):
                event = dict(handler=self, data=data)
                for domain in self._domain_map.values():
                    domain.on_event(event)

                for event_handler in self._event_handlers.copy():
                    event_handler.send_event(event)
            elif data.get('id'):
                try:
                    callback = self._callbacks.pop(data['id'])
                except KeyError:
                    pass
                else:
                    callback(data)
        except Exception as e:
            self.logger.exception(str(e))

    def on_error(self, ws, error):
        self.logger.info('#on_error {}'.format(error))
