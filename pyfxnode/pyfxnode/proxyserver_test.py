import time

import pytest

from pyfxnode.proxyserver import ProxyServer, ProxyHandler


def test_proxy_server():
    s = ProxyServer(('127.0.0.1', 9000), ProxyHandler())

    s.start()
    time.sleep(1)
    s.stop()
    s.join()
