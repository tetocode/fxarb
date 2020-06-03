import logging
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from socketserver import ThreadingTCPServer, BaseRequestHandler
from typing import Tuple

from .server import Server


class TCPHandler:
    def handle_tcp(self, request, address):
        pass


class TCPServer(Server):
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

    def __init__(self, address, handler: TCPHandler, logger: logging.Logger = None,
                 pool_size: float = None):
        super().__init__(logger=logger)

        class Handler(BaseRequestHandler):
            def handle(self):
                handler.handle_tcp(self.request, self.client_address)

        self._server = self._TCPServer(address, Handler, pool_size=pool_size)
        self.info('bind at tcp:{}'.format(self.server_address))

        def run():
            try:
                self._server.serve_forever(poll_interval=0.5)
                self.info('stopped')
            except Exception as e:
                self.exception(str(e))
                raise

        self._thread = threading.Thread(target=run, name=self.logger.name, daemon=True)

    class _TCPServer(ThreadingTCPServer):
        daemon_threads = True

        def __init__(self, *args, pool_size: int = None, **kwargs):
            super().__init__(*args, **kwargs)
            self._thread_pool = ThreadPoolExecutor(pool_size or 100)

        def server_bind(self):
            if self.server_address[1] == 0:
                super().server_bind()
            else:
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.socket.bind(self.server_address)

        def process_request(self, request, client_address):
            self._thread_pool.submit(self.process_request_thread, request, client_address)
