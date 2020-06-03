from datetime import datetime

import gevent
from pytest import mark
import pytz
from gevent.queue import Queue

from pyfx.agentnode import AgentNode
from pyfx.udpnode import UDPNode
from pyfx.hubnode import HubNode
from pyfx.pricehandler import Price


# logging.basicConfig(level=logging.DEBUG)

@mark.skip
def test_benchmark():
    Node.NOTIFY_INTERVAL = 0.1

    class Subscriber(UDPNode):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.q = Queue()

        def handle_push(self, **data):
            self.q.put(data)

    hub_address = ('127.0.0.1', 10000)
    sub_address = ('127.0.0.1', 10001)
    nodes = {
        'hub': hub_address,
        'sub': sub_address,
    }
    hub = HubNode('hub', nodes=nodes)
    sub = Subscriber('sub', nodes=nodes)
    agent = AgentNode('agent', hub_name='hub', nodes=nodes)

    hub.start()
    sub.start()
    agent.start()

    with sub.connection('hub') as conn:
        conn.rpc_subscribe('sub')
    gevent.sleep(1.0)

    now = datetime.utcnow().replace(tzinfo=pytz.utc)
    prices = [Price('pub', 'USD/JPY', now, 99.9, 100.0)]

    N = 100
    start = datetime.utcnow()
    for i in range(N):
        agent.push(prices=prices)
        if i % 100 == 0:
            gevent.sleep(1.0 / 10e12)

    for i in range(N):
        assert isinstance(sub.q.get(timeout=1.0), dict)
    elapsed = (datetime.utcnow() - start).total_seconds()
    print('#', 'total:', elapsed, '1:', elapsed / N, 'rps:', N / elapsed)

    hub.stop().join()
    sub.stop().join()
    agent.stop().join()
