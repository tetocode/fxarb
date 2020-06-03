import binascii
import contextlib
import functools
import pickle
import threading
from collections import deque
from contextlib import suppress
from typing import Dict, Tuple, Any

import msgpackrpc
from mprpc.server import RPCServer

from .nodeabc import NodeABC


def rpc_method(f):
    @functools.wraps(f)
    def wrapper(self: 'RPCNode', *args):
        args = tuple(map(self.deserialize, args))
        return self.serialize(f(self, *args))

    return wrapper


class RPCClientPool:
    def __init__(self, address: Tuple[str, int], timeout: float = None, reconnect_limit: int = None):
        self._address = address

        params = {}
        if timeout:
            params['timeout'] = timeout
        if reconnect_limit:
            params['reconnect_limit'] = reconnect_limit
        self._factory = lambda: msgpackrpc.Client(msgpackrpc.Address(*address), **params)
        self._using = deque()
        self._pool = deque()

    @contextlib.contextmanager
    def client(self):
        client = None
        try:
            client = self.acquire()
            yield client
        finally:
            self.release(client)

    def release(self, client):
        try:
            self._using.remove(client)
            self._pool.append(client)
        except ValueError:
            pass

    def drop(self, client):
        with suppress(ValueError):
            self._pool.remove(client)

    def acquire(self):
        try:
            client = self._pool.popleft()
        except IndexError:
            client = self._factory()
        self._using.append(client)
        return client


class RPCRequest:
    def __init__(self, pool: RPCClientPool, method_type: str, serializer=None, deserializer=None):
        self._pool = pool
        self._method_type = method_type
        self._serializer = serializer
        self._deserializer = deserializer

    def __getattr__(self, item: str):
        def request(*args):
            serialized_args = tuple(map(self._serializer, args))
            client = None
            try:
                with self._pool.client() as client:
                    # client = msgpackrpc.Client(msgpackrpc.Address(*self._address))
                    return self._deserializer(getattr(client, self._method_type)(item, *serialized_args))
            except:
                if client:
                    self._pool.drop(client)
                raise

        return request


class RPCNode(RPCServer, NodeABC):
    RPC_TIMEOUT = 1.5
    RPC_RECONNECT_LIMIT = 2

    def __init__(self, bind_address: Tuple[str, int] = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        bind_address = bind_address or self.DEFAULT_ADDRESS
        self._pools = {}  # type: Dict[Tuple[str, int], RPCClientPool]
        self._server = None  # type: msgpackrpc.Server
        self._bind_address = bind_address

        def run():
            try:
                self._server = msgpackrpc.Server(self)
                self._server.listen(msgpackrpc.Address(*bind_address))
                self._server.start()
            except Exception as e:
                self.exception(str(e))

        self._thread = threading.Thread(target=run, daemon=True)

    def is_running(self) -> bool:
        return self._thread.is_alive()

    @property
    def bind_address(self) -> Tuple[str, int]:
        return self._bind_address

    def start(self):
        self._thread.start()

    def stop(self, timeout: float = None):
        self._server.stop()
        return self

    def join(self, timeout: float = None):
        self._thread.join(timeout=timeout)

    def _acquire_pool(self, remote_address: Tuple[str, int]) -> RPCClientPool:
        try:
            return self._pools[remote_address]
        except KeyError:
            pass
        pool = RPCClientPool(remote_address,
                             timeout=self.RPC_TIMEOUT,
                             reconnect_limit=self.RPC_RECONNECT_LIMIT)
        self._pools[remote_address] = pool
        return pool

    def _remove_pool(self, remote_address: Tuple[str, int]):
        with suppress(KeyError):
            self._pools.pop(remote_address)

    def rpc(self, remote_address: Tuple[str, int]):
        return RPCRequest(self._acquire_pool(remote_address), 'call', self.serialize, self.deserialize)

    def notify(self, remote_address: Tuple[str, int]):
        return RPCRequest(self._acquire_pool(remote_address), 'notify', self.serialize, self.deserialize)

    def serialize(self, obj: Any):
        return binascii.b2a_hex(pickle.dumps(obj))

    def deserialize(self, obj: Any):
        return pickle.loads(binascii.a2b_hex(obj))
