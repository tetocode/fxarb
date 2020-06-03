import logging
import re
import sys

import time
from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.webnode import WebNode


class Gaikaex(WebNode):
    NAME = 'gaikaEX'
    CURRENCY_URL = 'https://gaikaex.net/servlet/lzca.pc.cif003.servlet.CIf00301?'
    PRICE_URL = 'https://gaikaex.net/quote.txt'
    POSITION_URL = 'https://gaikaex.net/servlet/lzca.pc.cht200.servlet.CHt20003?'

    accounts = {
        NAME: Account(NAME),
    }

    currencies = {}

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response
        if req.pretty_url.startswith(self.PRICE_URL):
            pass
        elif req.pretty_url.startswith(self.CURRENCY_URL):
            pass
        elif req.pretty_url.startswith(self.POSITION_URL):
            pass
        else:
            res.stream = True

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.CURRENCY_URL):
                # self.parse_currencies(res.text)
                pass
            if req.pretty_url.startswith(self.POSITION_URL):
                pass
                # data = self.parse_account(res.text)
                # self.push(**data)
        if req.method == 'POST':
            if req.pretty_url.startswith(self.PRICE_URL):
                data = self.parse_prices(res.text)
                self.push_data(**data)

    def parse_prices(self, content: str) -> dict:
        """EUR/USD	1	1.07338	1.07343	0.00450	1.06888	1.07384	1.06836	-34	33	0	5	2"""
        body = re.sub('\s+', ' ', content)
        prices = {}
        for m in re.finditer('(?P<instrument>[A-Z/]+/[A-Z]+) \S+ (?P<bid>[.\d]+) (?P<ask>[.\d]+)', body):
            d = m.groupdict()
            instrument = d['instrument']
            bid = float(d['bid'])
            ask = float(d['ask'])
            price = Price(self.NAME, instrument, bid, ask)
            prices.setdefault(self.NAME, {})[instrument] = price
        return dict(prices=prices)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
        Usage:
          {f} [options]

        Options:
          --bind IP_PORT  [default: 127.0.0.1:10102]
          --proxy IP_PORT  [default: 127.0.0.1:8082]
          --chrome IP_PORT  [default: 127.0.0.1:11002]
          --hub IP_PORT  [default: 127.0.0.1:10000]
        """.format(f=sys.argv[0]))

    l = args['--bind'].split(':')
    address = (l[0], int(l[1]))

    l = args['--proxy'].split(':')
    proxy_address = (l[0], int(l[1]))

    l = args['--chrome'].split(':')
    chrome_address = (l[0], int(l[1]))

    hub_addresses = [(hub_address.split(':')[0], int(hub_address.split(':')[1])) for hub_address in
                     args['--hub'].split(',')]

    node = Gaikaex(Gaikaex.NAME, address,
                   proxy_address=proxy_address,
                   chrome_address=chrome_address,
                   hub_addresses=hub_addresses)
    try:
        node.start()
        while node.is_running():
            time.sleep(1)
    finally:
        node.stop()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
