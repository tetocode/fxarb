import json
import logging
import sys

import time
from docopt import docopt
from mitmproxy.http import HTTPFlow
from mitmproxy.websocket import WebSocketFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.utils import jst_now_aware
from pyfxnode.webnode import WebNode


class Minsys(WebNode):
    NAME = 'minSys'
    # WS_RATE_URL = 'wss://fxtrader.min-fx.tv/express/rest/realtime?'
    WS_RATE_URL = 'fxtrader.min-fx.tv:443/express/rest/realtime?'

    accounts = {
        NAME: Account(NAME),
    }

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response
        if req.pretty_url.startswith(self.WS_RATE_URL):
            pass
        else:
            res.stream = True

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        # res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.WS_RATE_URL):
                pass

    INSTRUMENT_CODES = {
        1: 'USD/JPY',
        2: 'EUR/JPY',
        3: 'GBP/JPY',
        4: 'AUD/JPY',
        5: 'NZD/JPY',
        6: 'CHF/JPY',
        7: 'CAD/JPY',
        8: 'ZAR/JPY',
        9: 'EUR/USD',
        10: 'GBP/USD',
        11: 'AUD/USD',
        12: 'NZD/USD',
        13: 'EUR/GBP',
        14: 'EUR/AUD',
        15: 'GBP/AUD',
        16: 'USD/CHF',
        17: 'EUR/CHF',
        18: 'GBP/CHF',
    }

    def handle_websocket_message(self, flow: WebSocketFlow):
        content = None
        try:
            addr = '{}{}'.format(flow.server_conn.address, flow.handshake_flow.request.path)
            if not addr.startswith(self.WS_RATE_URL):
                return
            content = flow.messages[-1].content  # type: bytes
            if not content:
                return
            message = json.loads(content.decode('utf-8'))
            if 'event' not in message and message['event'] != 'QUOTE':
                return
            data = message['data']
            prices = {}
            now = jst_now_aware()
            for quote in data:
                code = quote[1]
                if code not in self.INSTRUMENT_CODES:
                    continue
                instrument = self.INSTRUMENT_CODES[code]
                ask = float(quote[4])
                bid = float(quote[5])
                price = Price(self.NAME, instrument=instrument, time=now, bid=bid, ask=ask)
                prices.setdefault(self.NAME, {})[instrument] = price

            self.push_data(accounts=self.accounts, prices=prices)
        except Exception as e:
            self.exception(str(e) + 'message={}'.format(content))


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
                    Usage:
                      {f} [options]

                    Options:
                      --bind IP_PORT  [default: 127.0.0.1:10110]
                      --proxy IP_PORT  [default: 127.0.0.1:8090]
                      --chrome IP_PORT  [default: 127.0.0.1:11010]
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

    node = Minsys(Minsys.NAME, address,
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
