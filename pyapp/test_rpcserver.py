from rpcserver import *


def test_master_slave():
    import logging
    logging.basicConfig(level=logging.DEBUG)

    master_address = ('127.0.0.1', 10000)
    slave_address = ('0.0.0.0', 0)
    master = Master('master', master_address)
    slave = Slave('slave', slave_address, master_address=master_address)

    m = gevent.spawn(master.start)
    client = Client(master_address)
    assert client.get_registered() == {}

    slave.POLL_INTERVAL = 0.01
    s = gevent.spawn(slave.start)

    gevent.sleep(0.1)
    assert client.get_registered() == {'slave': slave.bound_address}
    slave.stop()

    gevent.sleep(0.1)
    client.unregister('slave')
    assert client.get_registered() == {}

    master.stop()
    gevent.joinall([m, s])
