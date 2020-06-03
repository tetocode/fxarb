import json
import logging
import re
import sys
import threading
import time
from collections import defaultdict

import lxml.html
import pychrome
from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.utils import jst_now_aware
from pyfxnode.webnode import WebNode


class Triauto(WebNode):
    NAME = 'triauto'
    ACCOUNT_URL = 'https://triauto.invast.jp/TriAuto/user/api/getContainerAccountInfo.do'
    RATE_URL = 'https://triauto.invast.jp/TriAuto/user/api/getHomeRateMap.do'
    INDEX_URL = 'https://triauto.invast.jp/TriAuto/user/index.do'

    accounts = {
        NAME: Account(NAME),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        threading.Thread(target=lambda: self.poll_chrome(5.0), daemon=True).start()

    def poll_chrome(self, interval: float):
        if not self.chrome:
            self.warning('no chrome driver')
            return
        while True:
            try:
                for conn in self.chrome.connections(re.escape(self.INDEX_URL)):
                    self.on_account(conn)
            except Exception as e:
                self.exception(str(e))
            time.sleep(interval)

    def on_account(self, conn: pychrome.Connection):
        key = ('id', 'triautocontent')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            conn.get_html_all('frame,iframe')
            time.sleep(3)
            return

        # if stop_loading:
        #    print('#', conn.command('Page.stopLoading'))

        html = conn.get_html(css_selector='table table', node_id=node_id)
        dom = lxml.html.fromstring(html)
        text = dom.text_content()
        text = re.sub('\s+', ' ', text).replace(',', '')
        """
        証拠金預託額	1,534,876円
有効証拠金額	1,498,226円 (146.88%)
評価損益	-36,650円
証拠金不足額	0円
必要証拠金	1,020,000円
発注証拠金	0円
発注可能額	478,226円

        """
        map = {
            # '証拠金預託額': 'balance',
            '有効証拠金額': 'equity',
            '評価損益': 'profit_loss',
            '必要証拠金': 'used_margin',
            # '発注可能額': 'available',
        }
        d = {}
        for word, key in map.items():
            m = re.search('{}.*?([-,.0-9]+)'.format(word), text)
            if m:
                d[key] = float(m.group(1))
        self.accounts[self.NAME] = self.accounts[self.NAME].replace(**d)
        self.push_data(accounts=self.accounts)

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response
        if req.pretty_url.startswith(self.ACCOUNT_URL):
            pass
        elif req.pretty_url.startswith(self.RATE_URL):
            pass
        else:
            res.stream = True

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.RATE_URL):
                data = self.parse_prices(res.text)
                if data:
                    self.push_data(**data)
            elif req.pretty_url.startswith(self.ACCOUNT_URL):
                data = self.parse_account(res.text)
                if data:
                    self.push_data(**data)

    def parse_prices(self, content: str):
        prices = {}
        now = jst_now_aware()
        for k, v in json.loads(content)['rateMap'].items():
            instrument = '{}/{}'.format(k[:3], k[-3:])
            bid, ask = float(v['bid']), float(v['ask'])
            price = Price(self.NAME, instrument=instrument, time=now, bid=bid, ask=ask)
            prices.setdefault(self.NAME, {})[instrument] = price
        return dict(prices=prices)

    def parse_account(self, content: str):
        print('content={}'.format(content))
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
        print(self.accounts)
        return dict(accounts=self.accounts)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
        Usage:
          {f} [options]

        Options:
          --bind IP_PORT  [default: 127.0.0.1:10101]
          --proxy IP_PORT  [default: 127.0.0.1:8081]
          --chrome IP_PORT  [default: 127.0.0.1:11001]
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

    node = Triauto(Triauto.NAME, address,
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
