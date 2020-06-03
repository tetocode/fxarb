import logging
import sys
from typing import Tuple

import gevent
from docopt import docopt
from gsocketpool import Pool

from rpcmixin import new_account
from rpcserver import Slave, PoolClient


class DataStub(Slave):
    def __init__(self, *, bind_address: Tuple[str, int], master_address: Tuple[str, int]):
        super().__init__(name='datastub', master_address=master_address, bind_address=bind_address)
        gevent.spawn(self.run_put_prices)
        gevent.spawn(self.run_put_accounts)

    def run_put_prices(self):
        while not self.stopped:
            try:
                pool = Pool(PoolClient, dict(name=self.name, server_address=self.master_address))
                while True:
                    prices = []
                    for service in ['click', 'nano', 'yjfx']:
                        for instrument in ['USD/JPY', 'AUD/JPY']:
                            prices.append(dict(service=service, instrument=instrument, bid=100.0, ask=100.0, time=None))
                    with pool.connection() as client:
                        client.put_prices(prices)
                    gevent.sleep(1.0)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)

    def run_put_accounts(self):
        while not self.stopped:
            try:
                pool = Pool(PoolClient, dict(name=self.name, server_address=self.master_address))
                while True:
                    accounts = []
                    for service in ['click', 'nano', 'yjfx']:
                        accounts.append(new_account(service, equity=100))
                    with pool.connection() as client:
                        client.put_accounts(accounts)
                    gevent.sleep(1.0)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --master IP_PORT    [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
    """.format(f=sys.argv[0]))

    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))

    node = DataStub(bind_address=bind_address, master_address=master_address)
    spawns = [gevent.spawn(node.start)]
    gevent.joinall(spawns)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
