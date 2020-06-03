from typing import Tuple, Dict

from .clusternode import ClusterNode, rpc_method
from .handlerproxy import HandlerProxy


class AgentNode(HandlerProxy, ClusterNode):
    def __init__(self, name: str, bind_address: Tuple[str, int] = None,
                 *,
                 hub_name: str, nodes: Dict[str, Tuple[str, int]], **kwargs):
        super().__init__(name, bind_address, account=True, price=True, spread=True, nodes=nodes, **kwargs)
        assert hub_name in nodes
        self.hub_name = hub_name

    def push(self, **data):
        self.handle(**data)
        self.sendto(data, self.hub_name)

    @rpc_method
    def refresh(self):
        pass

    @rpc_method
    def submit_buy(self, instrument: str, qty: int) -> bool:
        raise NotImplementedError()

    @rpc_method
    def submit_sell(self, instrument: str, qty: int) -> bool:
        raise NotImplementedError()
