import time
from queue import Queue, Empty

import pytest

from pyfxnode.datanode import DataNode
from pyfxnode.hubnode import HubNode
from pyfxnode.price import Price
from pyfxnode.rpcclient import RPCClient
from pyfxnode.udpserver import UDPServer, UDPHandler
from pyfxnode.utils import unpack_from_bytes


def test_hub_node():
    hub = HubNode('hub', ('127.0.0.1', 0))
    hub.update_config(publish_interval=0.1, subscription_ttl=0.5)
    c = DataNode('data', ('127.0.0.1', 0), hub_addresses=[hub.server_address])

    q = Queue()

    class Handler(UDPHandler):
        def handle_udp(self, request, address):
            data, sock = request
            unpacked = unpack_from_bytes(data)
            print('unpacked=', unpacked, address)
            q.put(unpacked)

    sub = UDPServer(('127.0.0.1', 0), Handler())
    sub.start()

    hub.start()
    c.start()

    try:
        price = Price('X', 'USD/JPY', 100, 101)
        c.push_data(prices={'X': {'USD/JPY': price}})
        rpc = RPCClient(hub.server_address)
        rpc.request('subscribe', 'sub', sub.server_address)
        subscribers = rpc.request('get_subscribers')
        assert len(subscribers) == 1
        assert q.get(timeout=0.5)['prices']['X']['USD/JPY'] == list(price)

        subscribers = rpc.request('get_subscribers')
        assert subscribers['sub']['init'] is False
        with pytest.raises(Empty):
            q.get(timeout=0.5)
        print(rpc.request('get_subscribers'), time.time())
        assert len(rpc.request('get_subscribers')) == 0
    finally:
        c.stop()
        c.join()
        hub.stop()
        hub.join()
        sub.stop()
        sub.join()
