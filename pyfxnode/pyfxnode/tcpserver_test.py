import socket

from pyfxnode.tcpserver import TCPServer, TCPHandler


def test_tcp_server():
    class TestTCPHandler(TCPHandler):
        def handle_tcp(self, request, address):
            _data = request.recv(1024)
            print(address)
            request.sendall(_data)

    s = TCPServer(('127.0.0.1', 0), TestTCPHandler())

    s.start()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(s.server_address)
    sock.send(b'hello')
    data = sock.recv(1024)
    assert data == b'hello'

    s.stop()
    s.join()
