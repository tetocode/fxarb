import logging
import time

from pyfx.clusternode import ClusterNode
from pyfx.rpcnode import rpc_method

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s:%(name)s:%(levelname)s:%(message)s')


def test_cluster_node():
    class EchoNode(ClusterNode):
        NOTIFY_INTERVAL = 0.01

        @rpc_method
        def echo(self, msg: str):
            return msg

    s_address = ('127.0.0.1', 10000)
    nodes = {
        's': s_address,
    }

    s = EchoNode('s', s_address, nodes=nodes)
    c = EchoNode('c', nodes=nodes)

    s.start()
    c.start()

    nodes.update(c=c.bind_address)

    time.sleep(0.1)

    assert c._nodes == nodes
    assert c.rpc('s').echo('hello') == 'hello'

    s.stop().join()
    c.stop().join()
