import logging
import time
from queue import Queue
from typing import Tuple, Any

from pyfx import AgentNode
from pyfx import HubNode

logging.basicConfig(level=logging.DEBUG)


def test_hub_node():
    class TestHub(HubNode):
        NOTIFY_INTERVAL = 0.1

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.q = Queue()

        def handle_udp(self, data: Any, address: Tuple[str, int]):
            self.q.put(data)

    class TestAgent(AgentNode):
        NOTIFY_INTERVAL = 0.1

    hub_address = ('127.0.0.1', 10000)
    nodes = {
        '@hub': hub_address,
    }
    hub = TestHub('@hub', hub_address, nodes=nodes)
    agent = TestAgent('agent', hub_name='@hub', nodes=nodes)

    hub.start()
    time.sleep(0.5)
    agent.start()

    time.sleep(0.5)

    agent.push(x='abc')
    assert hub.q.get(timeout=1.0).get('x') == 'abc'

    hub.stop().join()
    agent.stop().join()
