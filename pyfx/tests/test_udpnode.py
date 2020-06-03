import random
from datetime import datetime
from queue import Queue

from pytest import mark

from pyfx.pricehandler import Price
from pyfx.udpnode import _UDPNode, UDPNode


@mark.skip
def test_udp_node():
    s_address = ('127.0.0.1', 10000)
    q = Queue()
    s = _UDPNode(s_address, lambda *args: q.put(args))
    c = _UDPNode(('127.0.0.1', 10001))

    s.start()
    c.start()

    def rand_time() -> datetime:
        return datetime(year=random.randint(2000, 2020),
                        month=random.randint(1, 12),
                        day=random.randint(1, 28),
                        hour=random.randint(0, 23),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                        microsecond=random.randint(0, 999999))

    prices = [
        Price('gaitamefx', 'USD/JPY', rand_time(), random.random(), random.random()),
        Price('zfx-express', 'EUR/JPY', rand_time(), random.random(), random.random()),
        Price('primeclick', 'GBP/JPY', rand_time(), random.random(), random.random()),
        Price('finalfx', 'AUD/JPY', rand_time(), random.random(), random.random()),
    ]

    c.sendto(prices, s.bind_address)
    d = q.get(timeout=0.1)
    assert len(d) == 2 and d[0] == prices

    s.stop().join()
    c.stop().join()


def test_gevent_udp_node():
    s_address = ('127.0.0.1', 10000)
    q = Queue()
    s = UDPNode(s_address, lambda *args: q.put(args))
    c = UDPNode(('127.0.0.1', 10001))

    s.start()
    c.start()

    def rand_time() -> datetime:
        return datetime(year=random.randint(2000, 2020),
                        month=random.randint(1, 12),
                        day=random.randint(1, 28),
                        hour=random.randint(0, 23),
                        minute=random.randint(0, 59),
                        second=random.randint(0, 59),
                        microsecond=random.randint(0, 999999))

    prices = [
        Price('gaitamefx', 'USD/JPY', rand_time(), random.random(), random.random()),
        Price('zfx-express', 'EUR/JPY', rand_time(), random.random(), random.random()),
        Price('primeclick', 'GBP/JPY', rand_time(), random.random(), random.random()),
        Price('finalfx', 'AUD/JPY', rand_time(), random.random(), random.random()),
    ]

    c.sendto(prices, s.bind_address)
    d = q.get(timeout=1.0)
    assert len(d) == 2 and d[0] == prices

    s.stop().join()
    c.stop().join()
