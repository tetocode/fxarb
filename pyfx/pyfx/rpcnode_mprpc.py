import binascii
import functools
import pickle
import threading
import time
from typing import Dict, Tuple, Any

import gevent
import gevent.monkey
import gsocketpool.pool
from gevent.server import StreamServer
from mprpc import RPCServer, RPCPoolClient

from .nodeabc import NodeABC


def rpc_method(f):
    @functools.wraps(f)
    def wrapper(self: 'RPCNode', *args):
        args = tuple(map(self.deserialize, args))
        return self.serialize(f(self, *args))

    return wrapper


class RPCRequest:
    def __init__(self, pool: gsocketpool.Pool, serializer=None, deserializer=None):
        self._pool = pool
        self._serializer = serializer or (lambda x: x)
        self._deserializer = deserializer or (lambda x: x)
        self._lock = threading.RLock()

    def __getattr__(self, item: str):
        def request(*args):
            serialized_args = tuple(map(self._serializer, args))
            conn = None
            try:
                with self._pool.connection() as conn:
                    # client = msgpackrpc.Client(msgpackrpc.Address(*self._address))
                    return self._deserializer(conn.call(item, *serialized_args))
            except:
                if conn:
                    self._pool.drop(conn)
                raise

        return request


class RPCNode(RPCServer, NodeABC):
    CONNECTION_TIMEOUT = 5.0

    def __init__(self, bind_address: Tuple[str, int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bind_address = bind_address or self.DEFAULT_ADDRESS
        self._bind_address = bind_address
        self._server = None  # type: StreamServer
        self._tls = threading.local()

        def run():
            self._server = server = StreamServer(bind_address, self)
            server.start()
            while self.is_running():
                gevent.sleep(0.5)

        self._thread = threading.Thread(target=run, daemon=True)

    @property
    def _pools(self) -> Dict[Tuple[str, int], gsocketpool.Pool]:
        try:
            return self._tls.pools
        except AttributeError:
            self._tls.pools = {}
        return self._tls.pools

    def is_running(self) -> bool:
        return self._server.started if self._server else False

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
        # self.stop()
        raise Exception('start timeouted 1.0sec')

    def stop(self, timeout: float = None):
        if self._server:
            self._server.stop(timeout=timeout)
        return self

    def join(self, timeout: float = None):
        self._thread.join(timeout=timeout)

    def _create_pool(self, remote_address: Tuple[str, int]) -> gsocketpool.Pool:
        try:
            return self._pools[remote_address]
        except KeyError:
            pass
        pool = gsocketpool.Pool(RPCPoolClient,
                                dict(host=remote_address[0],
                                     port=remote_address[1],
                                     timeout=self.CONNECTION_TIMEOUT,
                                     keep_alive=True))
        self._pools[remote_address] = pool
        return pool

    def rpc(self, remote_address: Tuple[str, int]):
        pool = self._create_pool(remote_address)
        return RPCRequest(pool, serializer=self.serialize, deserializer=self.deserialize)

    def serialize(self, obj: Any):
        return binascii.b2a_hex(pickle.dumps(obj))

    def deserialize(self, obj: Any):
        return pickle.loads(binascii.a2b_hex(obj))
