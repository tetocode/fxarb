import random
import re
from datetime import datetime
from typing import Tuple, List

import gevent
import gsocketpool.pool
import lxml.html
from gevent.lock import RLock
from gsocketpool.pool import Pool

from rpcserver import PoolClient


class BrowsePoolClient(PoolClient):
    def __init__(self, server_address: Tuple[str, int], *args, **kwargs):
        super().__init__(server_address, *args, **kwargs)
        self.methods = [
            self.get_prices_pfx,
            self.get_prices_nano,
            self.get_prices_try,
        ]
        self.pfx_handle = ''
        self.nano_handle = ''
        self.try_handle = ''
        self.pool = Pool(PoolClient, dict(name=self.name, server_address=server_address))

        lock = RLock()

        def find_pfx():
            pool = gsocketpool.pool.Pool(PoolClient, dict(name=self.name, server_address=server_address))
            while not self.pfx_handle:
                with lock:
                    with pool.connection() as client:
                        self.pfx_handle = client.find_window('パートナーズFX$')
                gevent.sleep(10)

        def find_nano():
            pool = gsocketpool.pool.Pool(PoolClient, dict(name=self.name, server_address=server_address))
            while not self.nano_handle:
                with lock:
                    with pool.connection() as client:
                        self.nano_handle = client.find_window('パートナーズFX nano')
                gevent.sleep(10)

        def find_try():
            pool = gsocketpool.pool.Pool(PoolClient, dict(name=self.name, server_address=server_address))
            while not self.try_handle:
                with lock:
                    with pool.connection() as client:
                        self.try_handle = client.find_window('レート')
                gevent.sleep(10)

        gevent.spawn(find_pfx)
        gevent.spawn(find_nano)
        gevent.spawn(find_try)

    def get_prices(self, now: datetime) -> List[dict]:
        results = []

        def get(_method):
            nonlocal results
            with self.pool.connection() as c:
                results += _method(c, now)

        spawns = []
        for method in random.sample(self.methods, len(self.methods)):
            spawns.append(gevent.spawn(get, method))
        gevent.joinall(spawns, timeout=1)
        return results

    def get_prices_mnp(self, client, now: datetime, service: str, instruments: List[str],
                       handle: str, frame: str) -> List[dict]:
        bid_str = '#bidCurrencyPrice{}'
        ask_str = '#askCurrencyPrice{}'
        results = []
        html = ''.join(client.get_elements_html('#PriceList', handle, frame))
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        for i, instrument in enumerate(instruments):
            i += 1
            bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
            ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
            results.append(dict(service=service, time=now, instrument=instrument, bid=bid, ask=ask))
        return results

    def get_prices_pfx(self, client, now: datetime) -> List[dict]:
        if not self.pfx_handle:
            return []
        instruments = [
            'USD/JPY', 'EUR/USD', 'AUD/JPY',
            'NZD/JPY', 'GBP/JPY', 'EUR/JPY',
            'CHF/JPY', 'CAD/JPY', 'GBP/USD',
            'ZAR/JPY',
        ]
        return self.get_prices_mnp(client, now, 'pfx', instruments, self.pfx_handle, 'rate')

    def get_prices_nano(self, client, now: datetime) -> List[dict]:
        if not self.nano_handle:
            return []

        instruments = [
            'USD/JPY', 'EUR/JPY', 'AUD/JPY',
            'EUR/USD', 'GBP/JPY', 'NZD/JPY',
            'ZAR/JPY', 'CHF/JPY',
        ]
        return self.get_prices_mnp(client, now, 'nano', instruments, self.nano_handle, 'rate')

    def get_prices_try(self, client, now: datetime) -> List[dict]:
        service = 'try'
        if not self.try_handle:
            return []
        results = []
        html = ''.join(client.get_elements_html('#rateList2', self.try_handle))
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        replace_spaces = re.compile('[^A-Z/]')
        for e in dom.cssselect('.currencyPair'):
            instrument = e.cssselect('td')[0].text_content()
            instrument = replace_spaces.sub('', instrument)
            bid = e.cssselect('td.bid')[0].text_content()
            ask = e.cssselect('td.ask')[0].text_content()
            bid, ask = float(bid), float(ask)
            results.append(dict(service=service, time=now, instrument=instrument, bid=bid, ask=ask))
        return results


class CapturePoolClient(PoolClient):
    def __init__(self, server_address: Tuple[str, int], *args, **kwargs):
        super().__init__(server_address, *args, **kwargs)

    def get_prices(self) -> List[dict]:
        try:
            return self.call('get_prices')
        except Exception as e:
            self.logger.exception(str(e))


def get_pool(name: str, address: Tuple[str, int]) -> gsocketpool.pool.Pool:
    #service, typ = name.split('.')
    #if typ == 'browse':
    #    return gsocketpool.pool.Pool(BrowsePoolClient, dict(name=name, server_address=address))
    #if typ == 'capture':
    #    return gsocketpool.pool.Pool(CapturePoolClient, dict(name=name, server_address=address))
    return gsocketpool.pool.Pool(CapturePoolClient, dict(name=name, server_address=address))