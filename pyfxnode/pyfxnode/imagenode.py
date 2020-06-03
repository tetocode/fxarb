from typing import Tuple, Iterable

from .datanode import DataNode


class ImageNode(DataNode):
    def __init__(self, name: str, address: Tuple[str, int], *,
                 hub_addresses: Iterable[Tuple[str, int]]):
        super().__init__(name, address, hub_addresses=hub_addresses)

    def refresh(self):
        pass

    def reload(self):
        pass

