from typing import Tuple

from .server import Server
from .tcpserver import TCPServer, TCPHandler
from .utils import get_unpacker, pack_to_bytes


class RPCServer(TCPServer):
    def __init__(self, address: Tuple[str, int], rpc_target: object, **kwargs):
        server = self

        super().__init__(address, handler=self.RPCHandler(self, rpc_target), **kwargs)

    class RPCHandler(TCPHandler):
        RECV_SIZE = 1024 ** 2

        def __init__(self, server: Server, rpc_target: object):
            super().__init__()
            self._server = server
            self._rpc_target = rpc_target

        def handle_tcp(self, request, address):
            unpacker = get_unpacker()
            while True:
                data = request.recv(self.RECV_SIZE)
                if not data:
                    self._server.info('connection {} closed'.format(address))
                    break

                unpacker.feed(data)
                try:
                    req = next(unpacker)
                except StopIteration:
                    continue

                (msg_id, msg_type, method, args, kwargs) = req

                try:
                    ret = getattr(self._rpc_target, method)(*args, **kwargs)
                except Exception as e:
                    self._server.exception('{}\n{}'.format(req, str(e)))
                    if msg_type == 1:
                        request.sendall(pack_to_bytes(dict(id=msg_id, error=str(e))))
                else:
                    if msg_type == 1:
                        request.sendall(pack_to_bytes(dict(id=msg_id, response=ret)))
