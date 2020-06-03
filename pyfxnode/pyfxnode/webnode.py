import logging
from typing import Tuple, Iterable

import pychrome

from .datanode import DataNode
from .proxyserver import ProxyServer, ProxyHandler


class WebNode(ProxyHandler, DataNode):
    def __init__(self, name: str, address: Tuple[str, int], *,
                 proxy_address: Tuple[str, int] = None,
                 chrome_address: Tuple[str, int] = None,
                 hub_addresses: Iterable[Tuple[str, int]]):
        servers = {}
        if proxy_address:
            servers['proxy'] = ProxyServer(proxy_address, self,
                                           logger=logging.getLogger(
                                               '{}.{}.proxy'.format(self.__class__.__name__, name)))
        super().__init__(name, address, hub_addresses=hub_addresses, servers=servers)

        self.chrome = None  # type: pychrome.Driver
        if chrome_address:
            self.chrome = pychrome.Driver(address=chrome_address,
                                          logger=logging.getLogger(
                                              '{}.{}.chrome'.format(self.__class__.__name__, name)))

    def refresh(self):
        pass

    def reload(self):
        pass
