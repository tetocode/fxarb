import json
import logging
import time
from collections import OrderedDict
from typing import Dict

import gevent
from gevent import Greenlet
from gevent import monkey as _monkey
from gevent.lock import RLock
from gevent.queue import Queue, Empty
from websocket import WebSocketApp

from chromepy.mixin import Network, Page, Input

_monkey.patch_all()


class Connection(Input, Page, Network, Greenlet):
    TIMEOUT = 10.0

    def __init__(self, ws_url: str, *, url: str, logger: logging.Logger = None):
        super().__init__()
        self.url = url
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._seq_no = 0  # type: int
        self._send_command_lock = RLock()
        self._response_queues = OrderedDict()  # type: Dict[int, Queue]
        self._event_q = Queue()
        self._ws = WebSocketApp(url=ws_url,
                                on_open=self.on_open,
                                on_close=self.on_close,
                                on_message=self.on_message,
                                on_error=self.on_error)

        self.start()
        self.wait_connected()
        gevent.spawn(self._run_event_loop)

    def _run(self):
        try:
            self._ws.run_forever()
        except Exception as e:
            self.logger.exception(str(e))
            self.safe_close()
        self.logger.info('run_forever finished.')

    def is_connected(self):
        return self._ws.sock and self._ws.sock.connected

    def wait_connected(self, timeout: float = 10.0) -> bool:
        start = time.time()
        while True:
            if self.is_connected():
                return True
            if time.time() - start >= timeout:
                break
            gevent.sleep(0.001)  # 1 msec
        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.safe_close()

    def safe_close(self):
        if self.is_connected():
            self._ws.close()

    def enable(self, *domains):
        for domain in domains:
            self.command('{}.enable'.format(domain))

    def disable(self, *domains):
        for domain in domains:
            self.command('{}.disable'.format(domain))

    def on_open(self, ws):
        self.logger.info('#on_open')

    def on_close(self, ws):
        self.logger.info('#on_close')
        for q in list(self._response_queues.values()):
            q.put(dict(error='no response by on_close'))

    def _send_command(self, data: dict):
        with self._send_command_lock:
            return self._ws.send(data)

    def command(self, method: str, **params) -> dict:
        self._seq_no += 1
        seq_no = self._seq_no
        data = dict(id=seq_no, method=method, params=params)

        q = Queue()
        self._response_queues[seq_no] = q
        try:
            self._send_command(json.dumps(data))
            return q.get(timeout=self.TIMEOUT)
        except Empty as e:
            if self.is_connected():
                self.logger.exception('method={} params={}\n{}'.format(method, params, str(e)))
                raise
            return dict(error='response timeout by disconnection')
        except Exception as e:
            self.logger.exception('method={} params={}\n{}'.format(method, params, str(e)))
            raise
        finally:
            del self._response_queues[seq_no]

    def _run_event_loop(self):
        try:
            func_tuples = [
                ('DOM', self.on_dom),
                ('Network', self.on_network),
                ('Page', self.on_page),
                ('', self.on_event),  # match all
            ]
            while self.is_connected():
                try:
                    data = self._event_q.get(timeout=1.0)
                    for _, func in func_tuples:
                        try:
                            func(data)
                        except Exception as e:
                            self.logger.exception(str(e))
                except Empty:
                    pass

        except Exception as e:
            self.logger.exception(str(e))
            raise
        finally:
            self.logger.info('event_loop finished')

    def on_event(self, data: dict):
        pass

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            if data.get('method'):
                self._event_q.put(data)
            elif data.get('id'):
                try:
                    q = self._response_queues[data['id']]
                    q.put(data)
                except KeyError:
                    pass
        except Exception as e:
            self.logger.exception(str(e))

    def on_error(self, ws, error):
        self.logger.info('#on_error {}'.format(error))
