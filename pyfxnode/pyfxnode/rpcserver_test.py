import pytest
import socketpool

from pyfxnode.rpcclient import RPCClient
from pyfxnode.rpcserver import RPCServer


class TestRPCServer:
    def echo(self, message: str):
        return 'reply ' + message

    def echo_args(self, *args):
        return args

    def echo_kwargs(self, **kwargs):
        return kwargs

    def echo_args_kwargs(self, *args, **kwargs):
        return args, kwargs

    def raise_str(self, message: str):
        raise Exception(message)


def test_rpc_server():
    s = RPCServer(('127.0.0.1', 0), TestRPCServer())
    s.start()

    try:
        c = RPCClient(s.server_address)

        res = c.request('echo', 'hello')
        assert res == 'reply hello', res

        res = c.notify('echo', 'hello')
        assert res is None

        args = [1, 2]
        res = c.request('echo_args', *args)
        assert res == args

        kwargs = dict(a=1, b=2)
        res = c.request('echo_kwargs', **kwargs)
        assert res == kwargs

        res = c.request('echo_args_kwargs', *args, **kwargs)
        assert res == [args, kwargs]

        with pytest.raises(Exception):
            c.request('raise_str', 'some error')

        c.close()
        assert not c.is_connected()
    finally:
        s.stop()
        s.join()


def test_rpc_server_pool():
    s = RPCServer(('127.0.0.1', 0), TestRPCServer())
    s.start()

    pool = socketpool.ConnectionPool(RPCClient, options=dict(address=s.server_address))
    try:

        for _ in range(10):
            with pool.connection() as c:
                res = c.request('echo', 'hello')
                assert res == 'reply hello', res
                assert c.is_connected()
            assert c.is_connected()

        with pytest.raises(Exception):
            with pool.connection() as c:
                c.request('raise_str', 'some error')

        assert not c.is_connected()

    finally:
        pool.release_all()
        s.stop()
        s.join()
