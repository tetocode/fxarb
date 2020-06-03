import json
import logging
import sys
import time
from collections import defaultdict

from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.webnode import WebNode


class Eraberugaika(WebNode):
    NAME = 'eraberu'
    CURRENCY_URL = 'https://trade.fxprime.com/eraberuGaika/servlet/api.trading.currency.CurrencyS'
    PRICE_URL = 'https://trade.fxprime.com/eraberuGaika/servlet/api.trading.rate.RateS'
    STREAM_PRICE_URL = 'https://trade.fxprime.com/eraberuGaikaHS/servlet/JsonApi/trading.rate.Rate'

    accounts = {
        NAME: Account(NAME),
    }

    currency_codes = {
        '007': 'NZD/JPY', '101': 'EUR/USD', '011': 'HKD/JPY', '008': 'CAD/JPY', '012': 'ZAR/JPY', '102': 'GBP/USD',
        '009': 'CHF/JPY', '301': 'EUR/AUD', '013': 'TRY/JPY', '002': 'EUR/JPY', '001': 'USD/JPY', '103': 'AUD/USD',
        '005': 'AUD/JPY', '302': 'GBP/AUD', '201': 'EUR/GBP', '010': 'SGD/JPY', '004': 'GBP/JPY', '104': 'NZD/USD',
    }

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response
        if req.method == 'POST':
            pass
        if req.pretty_url.startswith(self.CURRENCY_URL):
            pass
        elif req.pretty_url.startswith(self.PRICE_URL):
            pass
        elif req.pretty_url.startswith(self.STREAM_PRICE_URL):
            pass
        elif req.method == 'GET':
            res.stream = True

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.CURRENCY_URL):
                self.parse_currencies(res.text)
        elif req.method == 'POST':
            if req.pretty_url.startswith(self.PRICE_URL):
                pass
            elif req.pretty_url.startswith(self.STREAM_PRICE_URL):
                data = self.parse_stream_prices(res.text)
                self.push_data(**data)

    def parse_currencies(self, content: str):
        data = json.loads(content)
        self.currency_codes.clear()
        for info in data['detailList1']:
            code = info['currencyCd']
            instrument = info['currencyName4']
            self.currency_codes[code] = instrument
        self.info('#currencies_code={}'.format(self.currency_codes))

    def parse_stream_prices(self, content: str):
        data = json.loads(content)
        prices = {}
        for info in data['detailList1']:
            code = info['currencyCd']
            instrument = self.currency_codes.get(code)
            if not instrument:
                continue
            bid, ask = float(info['bid']), float(info['offer'])
            price = Price(self.NAME, instrument=instrument, bid=bid, ask=ask)
            prices.setdefault(self.NAME, {})[instrument] = price
        return dict(prices=prices)

    def parse_account(self, content: str):
        body = json.loads(content)
        info = body['accountInfo']
        equity = float(info['equity'])
        used_margin = float(info['position_margin'])
        profit_loss = equity - float(info['balance'])
        positions = defaultdict(int)
        for position in body['positionList']:
            currency = position['currencyPair']
            instrument = '{}/{}'.format(currency[:3], currency[-3:])
            amount = float(position['positionQty'])
            if position['buySell'] == '2':
                amount = -amount
            positions[instrument] += amount
        self.accounts[self.NAME] = Account(self.NAME, equity, profit_loss, used_margin, dict(positions))
        return dict(accounts=self.accounts)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
        Usage:
          {f} [options]

        Options:
          --bind IP_PORT  [default: 127.0.0.1:10104]
          --proxy IP_PORT  [default: 127.0.0.1:8084]
          --chrome IP_PORT  [default: 127.0.0.1:11004]
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

    node = Eraberugaika(Eraberugaika.NAME, address,
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
