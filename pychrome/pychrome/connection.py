import json
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from threading import RLock

from typing import Dict
from websocket import WebSocketApp

from pychrome.mixin import Network, Page, Input


class Connection(Input, Page, Network):
    TIMEOUT = 10.0

    def __init__(self, ws_url: str, *, logger: logging.Logger = None):
        super().__init__()
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._seq_no = 0  # type: int
        self._seq_no_lock = RLock()
        self._response_queues = OrderedDict()  # type: Dict[int, Queue]
        self._ws = WebSocketApp(url=ws_url,
                                on_open=self.on_open,
                                on_close=self.on_close,
                                on_message=self.on_message,
                                on_error=self.on_error)

        self._thread_pool = ThreadPoolExecutor()
        threading.Thread(target=self.run, daemon=True).start()
        self.wait_connected()

    def run(self):
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
            time.sleep(0.001)  # 1 msec
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
            res = self.command('{}.enable'.format(domain))
            self.logger.debug('{}.enable res={}'.format(domain, res))

    def disable(self, *domains):
        for domain in domains:
            self.command('{}.disable'.format(domain))

    def on_open(self, ws):
        self.logger.info('#on_open')

    def on_close(self, ws):
        self.logger.info('#on_close')
        for q in list(self._response_queues.values()):
            q.put(dict(error='no response by on_close'))

    def command(self, method: str, **params) -> dict:
        with self._seq_no_lock:
            self._seq_no += 1
            seq_no = self._seq_no

        data = dict(id=seq_no, method=method, params=params)

        q = Queue()
        self._response_queues[seq_no] = q
        try:
            self.logger.debug('#command={} id={} params={}'.format(method, seq_no, params))
            self._ws.send(json.dumps(data))
            res = q.get(timeout=self.TIMEOUT)
            self.logger.debug('#RES:command={} id={} res={}'.format(method, seq_no, res))
            return res
        except Empty as e:
            if self.is_connected():
                self.logger.exception('ERR:command={} id={} params={}\n{}'.format(method, seq_no, params, str(e)))
                raise
            return dict(error='response timeout by disconnection')
        except Exception as e:
            self.logger.exception('method={} params={}\n{}'.format(method, params, str(e)))
            raise
        finally:
            del self._response_queues[seq_no]

    def on_event(self, data: dict):
        pass

    def on_message(self, ws, message):
        future = self._thread_pool.submit(self._on_message, ws, message)

    def _on_message(self, ws, message):
        self.logger.debug('on_message message={}'.format(message))
        func_tuples = [
            ('DOM', self.on_dom),
            ('Network', self.on_network),
            ('Page', self.on_page),
            ('', self.on_event),  # match all
        ]
        try:
            data = json.loads(message)
            if data.get('method'):
                for _, func in func_tuples:
                    try:
                        func(data)
                    except Exception as e:
                        self.logger.exception(str(e))
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
