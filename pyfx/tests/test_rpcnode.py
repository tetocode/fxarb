import logging
import time

from pyfx.rpcnode import RPCNode, rpc_method

logging.basicConfig(level=logging.DEBUG)


def test_rpc_node():
    class EchoServer(RPCNode):
        @rpc_method
        def echo(self, msg: str):
            return msg

    s_address = ('127.0.0.1', 10000)
    s = EchoServer(s_address)
    c = EchoServer()

    s.start()
    c.start()

    time.sleep(1.0)
    reply = c.rpc(s.bind_address).echo('hello')
    assert reply == 'hello'
    reply = s.rpc(c.bind_address).echo('hello2')
    assert reply == 'hello2'

    s.stop().join()
    c.stop().join()
