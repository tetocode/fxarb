import threading
from queue import Queue

from pyfxnode.datanode import DataNode
from pyfxnode.price import Price
from pyfxnode.utils import unpack_from_bytes


def test_data_node():
    q = Queue()

    class TestClient(DataNode):
        pass

    class TestServer(DataNode):
        def handle_udp(self, request, address):
            data, sock = request
            unpacked = unpack_from_bytes(data)
            q.put(unpacked)

        def notify_node(self, *args, **kwargs):
            pass

        def echo(self, message: str):
            return message

    s = TestServer('server', ('127.0.0.1', 0))
    print('#', s.server_address)

    c = TestClient('data0', ('127.0.0.1', 0), hub_addresses=[s.udp_address])

    s.start()
    c.start()

    price = Price('X', 'USD/JPY', 100, 101)
    prices = {'X': {'USD/JPY': price}}
    c.push_data(prices=prices)
    data = q.get(timeout=1)
    assert len(data) == 1
    assert 'prices' in data
    assert 'X' in data['prices']
    assert 'USD/JPY' in data['prices']['X']
    assert Price(*data['prices']['X']['USD/JPY']) == price
    with c.rpc_connection(s.rpc_address) as conn:
        assert conn.request('echo', b'hello') == b'hello'

    c.stop()
    s.stop()
    c.join()
    s.join()
    print(threading.enumerate())
