import functools
import logging
from contextlib import suppress
from typing import Dict, Any, Union
from typing import Tuple

import gevent

from .rpcnode import RPCNode, rpc_method
from .udpnode import UDPNode, UDPNode


class ClusterNode(RPCNode):
    NOTIFY_INTERVAL = 5.0

    def __init__(self, name: str, bind_address: Tuple[str, int] = None, *, nodes: Dict[str, Tuple[str, int]]):
        bind_address = bind_address or self.DEFAULT_ADDRESS
        super().__init__(bind_address=bind_address)
        self.name = name
        nodes = nodes or {}
        self._initial_nodes = nodes.copy()
        self._nodes = nodes.copy()
        self._udp_server = None  # type: UDPNode
        self._tasks = []
        self._logger = logging.getLogger('{}.{}'.format(self.__class__.__name__, name))

        self.add_task(self.run_notify_nodes, self.NOTIFY_INTERVAL)
        self.info('initialized.')

    def _run_loop(self):
        self._launch_server()
        self._udp_server = UDPNode(self.bind_address, self.handle_udp)
        self._udp_server.start()
        for task in self._tasks:
            self.info('run task name={}.'.format(task.__name__))
            gevent.spawn(task)
        while self.is_running():
            gevent.sleep(0.5)

    def stop(self, timeout: float = None):
        super().stop(timeout=timeout)
        if isinstance(self._udp_server, UDPNode):
            self._udp_server.stop(timeout=timeout)
        return self

    def join(self, timeout: float = None):
        super().join(timeout=timeout)
        if isinstance(self._udp_server, UDPNode):
            self._udp_server.join(timeout=timeout)

    def add_task(self, task, retry_interval: float = None):
        f = task
        if retry_interval is not None:
            @functools.wraps(task)
            def run_loop():
                while self.is_running():
                    try:
                        f()
                    except Exception as e:
                        self.exception(str(e))
                    gevent.sleep(retry_interval)

            task = run_loop
        self._tasks.append(task)

    def sendto(self, data: Any, address: Union[Tuple[str, int], str]):
        if isinstance(address, str):
            address = self._nodes[address]
        self._udp_server.sendto(data, address)

    def handle_udp(self, data: Any, address: Tuple[str, int]):
        pass

    def rpc(self, address: Union[Tuple[str, int], str]):
        if isinstance(address, str):
            address = self._nodes[address]
        return super().rpc(address)

    @rpc_method
    def notify_nodes(self, nodes: Dict[str, Tuple[str, int]]):
        before_nodes = self._nodes.copy()
        nodes[self.name] = self.bind_address
        self._nodes.update(nodes)
        after_nodes = self._nodes.copy()
        if before_nodes != after_nodes:
            self.info('# notify_nodes nodes={} -> {}'.format(before_nodes, after_nodes))

    def run_notify_nodes(self):
        nodes = self._nodes.copy()
        nodes[self.name] = self.bind_address
        self.debug('# run_notify_nodes nodes={}'.format(nodes))
        for name, address in tuple(self._nodes.items()):
            try:
                if name != self.name:
                    self.rpc(address).notify_nodes(nodes)
            except ConnectionError as e:
                self.exception(str(e))
                with suppress(KeyError):
                    if name not in self._initial_nodes:
                        del self._nodes[name]
