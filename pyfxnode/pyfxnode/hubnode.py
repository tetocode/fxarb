import contextlib
import copy
import threading
import time
from collections import defaultdict
from queue import Queue, Empty
from typing import Tuple, Dict, DefaultDict, Any

from .account import Account
from .datanode import DataNode
from .price import Price
from .utils import unpack_from_bytes


class HubNode(DataNode):
    CONFIG_DEFAULTS = {
        'subscription_ttl': 10.0,
        'publish_interval': 0.3,
        'node_ttl': 10.0,
    }

    def __init__(self, name: str, address: Tuple[str, int]):
        super().__init__(name, address)

        self.accounts = {}  # type: Dict[str, Account]
        self._new_accounts = {}  # type: Dict[str, Account]
        self.prices = defaultdict(dict)  # type: DefaultDict[str, Dict[str, Price]]
        self._new_prices = defaultdict(dict)  # type: DefaultDict[str, Dict[str, Price]]

        self._data_q = Queue()

        self._subscribers = {}  # type: Dict[str, Any]
        self._subscribers_lock = threading.RLock()
        self._nodes = {}
        self._nodes_lock = threading.RLock()

        self.config = self.CONFIG_DEFAULTS.copy()

    def start(self):
        super().start()
        threading.Thread(target=self.handle_data_loop,
                         name='{}.handle_data_loop'.format(self.logger.name),
                         daemon=True).start()

    def get_config(self) -> dict:
        return self.config.copy()

    def update_config(self, **kwargs):
        self.info('config update by {}'.format(kwargs))
        self.config.update(**kwargs)

    def handle_data_loop(self):
        published_at = 0
        while self.is_running():
            try:
                with contextlib.suppress(Empty):
                    data = self._data_q.get(timeout=self.config['publish_interval'])
                    self.handle_data(data)
                if published_at + self.config['publish_interval'] <= time.time():
                    self.publish_data()
                    published_at = time.time()
            except Exception as e:
                self.exception(str(e))

    def handle_data(self, data: dict):
        for k, v_dict in data.items():
            if k == 'accounts':
                for name, v in v_dict.items():
                    account = Account(*v)
                    self.accounts[name] = account
                    self._new_accounts[name] = account
            elif k == 'prices':
                for name, instrument_v in v_dict.items():
                    for instrument, v in instrument_v.items():
                        price = Price(*v)
                        self.prices[name][instrument] = price
                        self._new_prices[name][instrument] = price

    def subscribe(self, name: str, address: Tuple[str, int]):
        address = tuple(address)
        with self._subscribers_lock:
            expired_at = time.time() + self.config['subscription_ttl']
            new_subscriber = False
            if name not in self._subscribers:
                new_subscriber = True
            self._subscribers.setdefault(name, {
                'init': True,
            }).update({'address': address, 'expired_at': expired_at})
            if new_subscriber:
                self.info('add subscriber {} {} expired_at={}'.format(name, address, expired_at))
                self.info('current subscribers {}'.format(self._subscribers))

    def get_subscribers(self):
        with self._subscribers_lock:
            return copy.deepcopy(self._subscribers)

    def publish_data(self):
        now = time.time()
        with self._subscribers_lock:
            for name, info in tuple(self._subscribers.items()):
                address = info['address']
                expired_at = info['expired_at']
                if expired_at < now:
                    self.warning('remove subscriber {} {}'.format(name, info))
                    self._subscribers.pop(name)
                elif info['init']:
                    # send all data
                    info.update(init=False)
                    self.pack_sendto({'accounts': self.accounts, 'prices': self.prices}, address)
                else:
                    if self._new_accounts or self._new_prices:
                        self.pack_sendto({'accounts': self._new_accounts,
                                          'prices': self._new_prices},
                                         address)
        self._new_accounts.clear()
        self._new_prices.clear()

    def notify_node(self, name: str, address: Tuple[str, int]):
        with self._nodes_lock:
            k = name
            self.debug('notify_node {} {}'.format(k, address))
            new_node = False
            if k not in self._nodes:
                new_node = True
            self._nodes[k] = (address, time.time() + self.config['node_ttl'])
            if new_node:
                self.info('new node {} {}'.format(k, address))
                self.info('current nodes {}'.format(self._nodes))

    def get_nodes(self):
        with self._nodes_lock:
            now = time.time()
            for k, v in tuple(self._nodes.items()):
                (address, expired_at) = v
                if expired_at < now:
                    self.warning('remove node {} {}'.format(k, address))
                    self._nodes.pop(k)
            return {k: v[0] for k, v in self._nodes.items()}

    def handle_udp(self, request, address):
        """handled by gevent.Greenlet"""
        data, _ = request
        data = unpack_from_bytes(data)
        self._data_q.put(data)
