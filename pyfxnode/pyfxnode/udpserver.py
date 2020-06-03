import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from socketserver import BaseRequestHandler, ThreadingUDPServer as _ThreadingUDPServer
from typing import Tuple, Optional, Union

import gevent
from gevent.server import DatagramServer

from .server import Server


class UDPHandler:
    def handle_udp(self, request, address):
        pass


class GeventUDPServer(Server):
    @property
    def server_address(self) -> Optional[Tuple[str, int]]:
        return self._address

    def start(self):
        self._started = True

    def join(self, timeout: float = None):
        self._thread.join(timeout)

    def stop(self, timeout: float = None):
        self._stop = True

    def is_running(self) -> bool:
        return not self._stop

    def __init__(self, address: Tuple[str, int], handler: UDPHandler, logger: logging.Logger = None, *args, **kwargs):
        super().__init__(*args, logger=logger, **kwargs)
        self._address = None
        self._started = False
        self._stop = False
        self._server = None

        def run():
            def handle(data: bytes, _address: Tuple[str, int]):
                handler.handle_udp((data, server.socket), _address)

            self._server = server = DatagramServer(address, handle)
            server.init_socket()
            self._address = server.address
            self.info('bind at udp:{}'.format(server.address))
            while not self._started:
                gevent.sleep(0.2)
            server.start()

            while not self._stop:
                gevent.sleep(0.5)
            server.stop(1)
            self.info('stopped')

        self._thread = threading.Thread(target=run, name=self.logger.name, daemon=True)
        self._thread.start()
        while not self._address:
            time.sleep(0.2)

    def udp_socket(self) -> socket.socket:
        return getattr(self._server.socket, '_sock')


class ThreadUDPServer(Server):
    @property
    def server_address(self) -> Tuple[str, int]:
        return self._server.server_address

    def start(self):
        self._thread.start()

    def join(self, timeout: float = None):
        self._thread.join(timeout)

    def stop(self, timeout: float = None):
        self._server.shutdown()

    def is_running(self) -> bool:
        return self._thread.is_alive()

    def __init__(self, address, handler: UDPHandler, logger: logging.Logger = None,
                 pool_size: float = None):
        super().__init__(logger=logger)

        class Handler(BaseRequestHandler):
            def handle(self):
                handler.handle_udp(self.request, self.client_address)

        self._server = self._UDPServer(address, Handler, pool_size=pool_size)
        self.info('bind at udp:{}'.format(self.server_address))

        def run():
            try:
                self._server.serve_forever(poll_interval=0.5)
                self.info('stopped')
            except Exception as e:
                self.exception(str(e))
                raise

        self._thread = threading.Thread(target=run, name=self.logger.name, daemon=True)

    def udp_socket(self) -> socket.socket:
        return self._server.socket

    class _UDPServer(_ThreadingUDPServer):
        daemon_threads = True

        def __init__(self, *args, pool_size: int = None, **kwargs):
            super().__init__(*args, **kwargs)
            self._thread_pool = ThreadPoolExecutor(pool_size)

        def server_bind(self):
            if self.server_address[1] == 0:
                super().server_bind()
            else:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind(self.server_address)

        def process_request(self, request, client_address):
            self._thread_pool.submit(self.process_request_thread, request, client_address)


class UDPServer(Server):
    def __init__(self, address, handler: UDPHandler, logger: logging.Logger = None,
                 backend: str = None, pool_size: float = None):

        self._server = None  # type: Union[GeventUDPServer, ThreadUDPServer]
        if backend == 'gevent':
            self._server = GeventUDPServer(address, handler, logger)
        else:
            self._server = ThreadUDPServer(address, handler, logger, pool_size=pool_size)

        super().__init__(logger=logger)

    def is_running(self):
        return self._server.is_running()

    @property
    def server_address(self) -> Tuple[str, int]:
        return self._server.server_address

    def start(self):
        self._server.start()

    def stop(self, timeout: float = None):
        self._server.stop(timeout)

    def join(self, timeout: float = None):
        self._server.join(timeout)

    def udp_socket(self) -> socket.socket:
        return self._server.udp_socket()

    def sendto(self, data: bytes, address: Tuple[str, int]):
        return self.udp_socket().sendto(data, address)
