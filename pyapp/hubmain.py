import copy
import logging
import sys
import time
from collections import defaultdict
from datetime import timedelta
from typing import Tuple, Dict, List

import gevent
from docopt import docopt
from gsocketpool import Pool

import timeutil
from rpcserver import Master, PoolClient


class HubMaster(Master):
    def __init__(self, *, bind_address: Tuple[str, int], interval: float = 0.1):
        super().__init__(bind_address=bind_address, name='hubmain')

        self.accounts = defaultdict(dict)  # type: Dict[str, dict]
        self.prices = defaultdict(dict)  # type: Dict[str, Dict[str, dict]]
        self.subscribers = {}  # type: Dict[str, Pool]
        self.pools = {}  # type: Dict[str, Pool]
        self.subscriber_pools = {}  # type: Dict[str, Pool]
        self.interval = interval

        gevent.spawn(self.run_publish)

    def put_accounts(self, account_list: List[dict]):
        now = timeutil.jst_now()
        for account in account_list:
            account.update(time=now)
            self.accounts[account['service']] = account
        gevent.sleep(0.0)

    def put_prices(self, price_list: List[dict]):
        now = timeutil.jst_now()
        for price in price_list:
            price.update(time=now)
            self.prices[price['service']][price['instrument']] = price
        gevent.sleep(0.0)

    def subscribe(self, name: str, client_address: Tuple[str, int]):
        self.subscriber_pools[(name, client_address)] = Pool(PoolClient, dict(name=name, server_address=client_address))
        self.logger.info('subscribed from {}({})'.format(name, client_address))

    def run_publish(self):
        while not self.stopped:
            try:
                start_time = time.time()
                now = timeutil.jst_now()
                accounts = {}
                prices = {}
                for service, account in self.accounts.items():
                    account = copy.deepcopy(account)
#                    account.update(time=str(account['time']))
                    accounts[service] = account
                for service, instrument_price in self.prices.items():
                    for instrument, price in instrument_price.items():
                        if now - price['time'] < timedelta(seconds=1):
                            price = copy.deepcopy(price)
#                            price.update(time=str(price['time']))
                            prices.setdefault(service, {})[instrument] = price
                data = dict(accounts=accounts, prices=prices)
                gevent.sleep(0.0)
                for key, pool in list(self.subscriber_pools.items()):
                    try:
                        with pool.connection() as client:
                            client.put_data(data)
                    except Exception as e:
                        self.logger.warning('disconnected {}. exception:{}'.format(key, str(e)))
                        del self.subscriber_pools[key]
                    gevent.sleep(0.0)
            except Exception as e:
                self.logger.exception(str(e))
                gevent.sleep(1.0)
            else:
                elapsed = time.time() - start_time
                gevent.sleep(max(self.interval - elapsed, self.interval / 10))


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT    [default: 127.0.0.1:10000]
    """.format(f=sys.argv[0]))

    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))

    master = HubMaster(bind_address=bind_address)
    spawns = [gevent.spawn(master.start)]
    gevent.joinall(spawns)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
