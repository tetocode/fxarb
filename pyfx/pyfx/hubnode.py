from contextlib import suppress
from typing import Tuple, Dict, Any

from gevent.queue import Queue as gQueue, Empty

from .clusternode import ClusterNode, rpc_method
from .handlerproxy import HandlerProxy


class HubNode(HandlerProxy, ClusterNode):
    Q_BLOCK_TIMEOUT = 1.0

    def __init__(self, name: str, bind_address: Tuple[str, int] = None,
                 *,
                 nodes: Dict[str, Tuple[str, int]] = None):
        assert name in nodes
        super().__init__(name, bind_address, account=True, price=True, spread=True, nodes=nodes)
        self._pub_q = gQueue()
        self._subscribers = set()

        self.add_task(self.run_publish, .0)

    def handle_udp(self, data: Any, address: Tuple[str, int]):
        if isinstance(data, dict):
            self.handle(**data)
            self._pub_q.put(data)

    def run_publish(self):
        with suppress(Empty):
            data = self._pub_q.get(timeout=self.Q_BLOCK_TIMEOUT)  # type: dict
            for remote_name in tuple(self._subscribers):
                if remote_name not in self._nodes:
                    self._subscribers.remove(remote_name)
                try:
                    self.rpc(remote_name).publish(data)
                except Exception as e:
                    self.exception(str(e))

    @rpc_method
    def subscribe(self, name):
        self._subscribers.add(name)

    @rpc_method
    def unsubscribe(self, name):
        with suppress(KeyError):
            self._subscribers.remove(name)
