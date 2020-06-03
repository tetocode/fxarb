import contextlib
import socket
import sys
import time
from queue import Queue, Empty

from pyfxnode.udpserver import UDPServer, UDPHandler


def test_udp_server_gevent():
    class TestUDPHandler(UDPHandler):
        def handle_udp(self, request, address):
            _data, _socket = request
            _socket.sendto(_data, address)

    s = UDPServer(('127.0.0.1', 0), TestUDPHandler(), backend='gevent')

    s.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(10):
        message = 'hello {}'.format(i).encode('utf-8')
        sock.sendto(message, s.server_address)
        data = sock.recv(1024)
        assert data == message

    print(sock.getsockname())
    s.sendto(b'hello', sock.getsockname())
    received, from_address = sock.recvfrom(1024)
    assert received == b'hello'
    assert from_address == s.server_address

    s.stop()
    s.join()


def test_udp_server_thread():
    class TestUDPHandler(UDPHandler):
        def handle_udp(self, request, address):
            _data, _socket = request
            _socket.sendto(_data, address)

    s = UDPServer(('127.0.0.1', 0), TestUDPHandler())

    s.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(10):
        message = 'hello {}'.format(i).encode('utf-8')
        sock.sendto(message, s.server_address)
        data = sock.recv(1024)
        assert data == message

    print(sock.getsockname())
    s.sendto(b'hello', sock.getsockname())
    received, from_address = sock.recvfrom(1024)
    assert received == b'hello'
    assert from_address == s.server_address

    s.stop()
    s.join()


def test_benchmark():
    q = Queue()

    class TestUDPHandler(UDPHandler):
        def __init__(self, n: int):
            self.c = 0
            self.n = n

        def handle_udp(self, request, address):
            self.c += 1
            if self.c >= self.n:
                q.put(True)

    n = 10000

    handlers = [
        TestUDPHandler(n),
        TestUDPHandler(n),
    ]
    for i, (name, s) in enumerate([
        ('gevent', UDPServer(('127.0.0.1', 0), handlers[0], backend='gevent')),
        ('thread', UDPServer(('127.0.0.1', 0), handlers[1]))
    ]):
        s.start()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            at = time.time()
            for _ in range(n):
                sock.sendto(b'hello', s.server_address)
            with contextlib.suppress(Empty):
                q.get(timeout=0.1)
            total = time.time() - at
            print('#', handlers[i].c, n, name, total, total / handlers[i].c, file=sys.stderr)

        s.stop()
        s.join()
