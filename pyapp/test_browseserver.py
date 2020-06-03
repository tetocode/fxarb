from browseserver import *
from rpcserver import *


def test_master_slave():
    import logging
    logging.basicConfig(level=logging.DEBUG)

    master_address = ('127.0.0.1', 10000)
    slave_address = ('0.0.0.0', 0)
    master = Master('master', master_address)
    slave = BrowseServer('slave', slave_address, master_address=master_address)

    spawns = []
    spawns.append(gevent.spawn(master.start))
    spawns.append(gevent.spawn(slave.start))

    slave.wait_started()
    client = Client(slave.bound_address)
    html = client.get_elements_html('#lst-ib')
    html = client.get_elements_html('form')

    master.stop()
    slave.stop()
    gevent.joinall(spawns)

if __name__ == '__main__':
    test_master_slave()
