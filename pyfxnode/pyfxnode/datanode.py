import logging
import socket
import threading
import time
from typing import Tuple, Any, Dict, Union, Iterable

import socketpool

from .rpcclient import RPCClient
from .rpcserver import RPCServer
from .server import Server
from .udpserver import UDPServer, UDPHandler
from .utils import pack_to_bytes


class DataNode(UDPHandler, Server):
    def __init__(self, name: str, address: Tuple[str, int], *,
                 hub_addresses: Iterable[Tuple[str, int]] = None,
                 logger: logging.Logger = None,
                 servers: Dict[str, Server] = None):
        logger = logger or logging.getLogger('{}.{}'.format(self.__class__.__name__, name))
        super().__init__(logger=logger)
        self.name = name
        hub_addresses = tuple(hub_addresses or [])
        self._hub_addresses = hub_addresses

        self._udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._rpc_pools = {}  # type: Dict[Tuple[str, int], socketpool.ConnectionPool]

        servers = servers or {}  # type: Dict[str, Union[RPCServer, UDPServer]]
        self.rpc_server = RPCServer(address, self, logger=logging.getLogger('{}.rpc'.format(self.logger.name)))
        self.udp_server = UDPServer(self.rpc_server.server_address, self,
                                    logger=logging.getLogger('{}.udp'.format(self.logger.name)))
        servers['rpc'] = self.rpc_server
        servers['udp'] = self.udp_server
        self._servers = servers

    @property
    def rpc_address(self) -> Tuple[str, int]:
        return self.rpc_server.server_address

    @property
    def udp_address(self) -> Tuple[str, int]:
        return self.udp_server.server_address

    def pack_sendto(self, obj: Any, address: Tuple[str, int]):
        data = pack_to_bytes(obj)
        self.udp_server.sendto(data, address)

    def push_data(self, **data):
        assert self._hub_addresses, 'hub_addresses not set'
        for hub_address in self._hub_addresses:
            self.pack_sendto(data, hub_address)

    def rpc_connection(self, address: Tuple[str, int]) -> RPCClient:
        if address not in self._rpc_pools:
            self._rpc_pools[address] = socketpool.ConnectionPool(RPCClient, options=dict(address=address))
        return self._rpc_pools[address].connection()

    @property
    def server_address(self) -> Tuple[str, int]:
        return self.rpc_address

    def join(self, timeout: float = None):
        for server in self._servers.values():
            server.join(timeout)

    def start(self):
        for server in self._servers.values():
            server.start()
        threading.Thread(target=self.run_notify_node_loop,
                         name='{}.run_notify_node_loop'.format(self.logger.name),
                         daemon=True).start()

    def run_notify_node_loop(self):
        for hub_address in self._hub_addresses:
            pool = socketpool.ConnectionPool(RPCClient, options=dict(address=hub_address))
            try:
                while self.is_running():
                    try:
                        with pool.connection() as conn:  # type: RPCClient
                            conn.notify('notify_node', self.name, self.rpc_address)
                    except Exception as e:
                        self.exception(str(e) + ' by {}'.format(hub_address))
                    time.sleep(3)
            finally:
                pool.release_all()

    def stop(self, timeout: float = None):
        for server in self._servers.values():
            server.stop(timeout)
        for pool in self._rpc_pools.values():
            pool.release_all()

    def is_running(self) -> bool:
        for server in self._servers.values():
            if server.is_running():
                return True
        return False
