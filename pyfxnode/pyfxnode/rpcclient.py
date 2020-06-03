import logging
from typing import Tuple

from socketpool import TcpConnector
from socketpool.util import load_backend

from .loggermixin import LoggerMixin
from .utils import pack_to_bytes, get_unpacker


class RPCClient(LoggerMixin, TcpConnector):
    RECV_SIZE = 1024 ** 2

    def __init__(self, address: Tuple[str, int], *, logger: logging.Logger = None, **kwargs):
        self._pool = None
        new_kwargs = kwargs.copy()
        if 'backend_mod' not in new_kwargs:
            new_kwargs['backend_mod'] = load_backend('thread')
        super().__init__(address[0], address[1], logger=logger, **new_kwargs)
        self._msg_id = 0

    def rpc(self, msg_type: int, method: str, *args, **kwargs):
        self._msg_id += 1
        msg_id = self._msg_id

        self.debug('rpc msg_id={} msg_type={} method={} args={} kwargs={} {} -> {}'.format(
            msg_id, msg_type, method, args, kwargs,
            self._s.getsockname(),
            (self.host, self.port),
        ))

        params = (msg_id, msg_type, method, args, kwargs)
        data = pack_to_bytes(params)
        self.sendall(data)

        if msg_type == 1:
            unpacker = get_unpacker()
            while True:
                data = self.recv(self.RECV_SIZE)
                if not data:
                    break

                unpacker.feed(data)
                try:
                    res = next(unpacker)
                    if 'error' in res:
                        raise Exception(res['error'])
                    return res['response']

                except StopIteration:
                    continue
            raise Exception('no response for {}'.format(params))

    def matches(self, **match_options):
        return match_options['address'] == (self.host, self.port)

    def handle_exception(self, exception):
        self.invalidate()
        raise exception

    def request(self, method: str, *args, **kwargs):
        return self.rpc(1, method, *args, **kwargs)

    def notify(self, method: str, *args, **kwargs):
        return self.rpc(2, method, *args, **kwargs)

    def sendall(self, data: bytes):
        return self._s.sendall(data)

    def close(self):
        self.invalidate()
