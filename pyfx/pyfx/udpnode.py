import pickle
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from socketserver import ThreadingUDPServer, DatagramRequestHandler
from typing import Tuple, Any

import gevent
from gevent.server import DatagramServer

from .nodeabc import NodeABC


class _UDPNode(ThreadingUDPServer, NodeABC):
    POOL_SIZE = 20

    def __init__(self, address=None, handler=None, pool_size: float = None):
        address = address or self.DEFAULT_ADDRESS
        handler = handler or (lambda *_: None)

        def _handle(data, address):
            deserialized = self.deserialize(data)
            handler(deserialized, address)

        class UDPHandler(DatagramRequestHandler):
            def handle(self):
                _handle(self.request[0], self.request[1])

            def finish(self):
                pass

        super().__init__(address, UDPHandler)
        self.pool = ThreadPoolExecutor(max_workers=pool_size)

        def run():
            self.serve_forever()

        self._thread = threading.Thread(target=run, daemon=True)

    def process_request(self, request, client_address):
        self.pool.submit(self.process_request_thread, request, client_address)

    def is_running(self):
        return self._thread.is_alive()

    @property
    def bind_address(self) -> Tuple[str, int]:
        return self.server_address

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout: float = None):
        self.shutdown()
        self.join(timeout=timeout)
        return self

    def join(self, timeout: float = None):
        self._thread.join(timeout=timeout)

    def sendto(self, data: Any, address: Tuple[str, int]):
        serialized = self.serialize(data)
        assert len(serialized) <= 1100, '{}'.format(data)
        self.socket.sendto(serialized, address)

    def serialize(self, obj: Any):
        return pickle.dumps(obj)

    def deserialize(self, obj: Any):
        return pickle.loads(obj)


class UDPNode(NodeABC):
    def __init__(self, bind_address: Tuple[str, int] = None, handler=None):
        bind_address = bind_address or self.DEFAULT_ADDRESS
        handler = handler or (lambda data, address: None)

        def handle(data: bytes, address: Tuple[str, int]):
            deserialized = self.deserialize(data)
            handler(deserialized, address)

        super().__init__()
        self._bind_address = bind_address
        self._server = None  # type: DatagramServer
        self._stop = False

        def run():
            self._tls.gevent = True
            self._server = DatagramServer(self.bind_address, handle)
            self._server.start()
            while self.is_running() and not self._stop:
                gevent.sleep(0.5)
            self._server.stop()

        self._thread = threading.Thread(target=run, daemon=True)
        self._tls = threading.local()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def is_running(self):
        if self._server:
            return self._server.started
        return False

    @property
    def bind_address(self) -> Tuple[str, int]:
        if self._server:
            return self._server.address
        return self._bind_address

    def start(self):
        self._thread.start()
        n = 1000
        for _ in range(n):
            if self.is_running():
                return self
            time.sleep(1.0 / n)
        self.stop()
        raise Exception('start timeouted 1.0sec')

    def stop(self, timeout: float = None):
        self._stop = True
        self.join(timeout=timeout)
        return self

    def join(self, timeout: float = None):
        self._thread.join(timeout=timeout)

    def sendto(self, data: Any, address: Tuple[str, int]):
        serialized = self.serialize(data)
        assert len(serialized) <= 4096, 'len={} {}'.format(len(serialized), data)
        try:
            _ = self._tls.gevent
            self._server.sendto(serialized, address)
        except AttributeError:
            self._socket.sendto(serialized, address)

    def serialize(self, obj: Any):
        return pickle.dumps(obj)

    def deserialize(self, obj: Any):
        return pickle.loads(obj)
