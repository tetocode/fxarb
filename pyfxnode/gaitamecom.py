import csv
import logging
import re
import sys
import threading
import time
from io import StringIO

import lxml.html
import pychrome
from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.utils import jst_now_aware
from pyfxnode.webnode import WebNode


class Gaitamecom(WebNode):
    NAME = 'gaitamecom'
    RATE_URL = 'https://tradefx.gaitame.com/webpublisher/RateServlet'
    ACCOUNT_URL = 'https://tradefx.gaitame.com/webserviceapi/accountDetail.do'
    POSITION_URL = 'https://tradefx.gaitame.com/webserviceapi/possumDetailA.do'
    GAITAMECOM_URL = 'https://tradefx.gaitame.com/pcweb/gneo/trade.html'

    accounts = {
        NAME: Account(NAME),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        threading.Thread(target=lambda: self.poll_chrome(5.0), daemon=True).start()
        self.refresh_flag = False

    def poll_chrome(self, interval: float):
        if not self.chrome:
            self.warning('no chrome driver')
            return
        while True:
            try:
                for conn in self.chrome.connections(re.escape(self.GAITAMECOM_URL)):
                    self.on_positions(conn, self.refresh_flag)
                self.refresh_flag = False
            except Exception as e:
                self.exception(str(e))
            time.sleep(interval)

    def on_positions(self, conn: pychrome.Connection, refresh: bool):
        if refresh:
            self.refresh_flag = False
            self.info('refresh')
            conn.click(css_selector='#uforex1_id_byCurrencyPairListHome_MyTable a.btnUpdate')
            self.info('refresh clicked')

        # if not chrome.url.startswith(self.GAITAMECOM_URL):
        #            return
        html = conn.get_html(css_selector='#uforex1_id_byCurrencyPairListHome_MyTable')
        if not html:
            return
        dom = lxml.html.fromstring(html)
        positions = {}
        for tr in dom.cssselect('table tr'):
            text = tr.text_content()
            text = re.sub('\s+', ' ', text).replace(',', '')
            m = re.search(
                '(?P<instrument>[A-Z]+/[A-Z]+) [A-Z]+ (?P<bid_amount>\d+) \d+ [.\d]+ (?P<ask_amount>\d+)',
                text)
            if not m:
                continue
            d = m.groupdict()
            positions[d['instrument']] = (int(d['ask_amount']) - int(d['bid_amount'])) * 1000
        # self.account['positions'] = positions
        #        self.account['positions'].update(self.streaming_positios)
        #        self.update_accounts([self.account])
        self.accounts[self.NAME] = self.accounts[self.NAME].replace(positions=positions)
        self.push_data(accounts=self.accounts)

    def refresh(self):
        self.refresh_flag = True

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        # res = flow.response
        if req.method == 'POST':
            if req.pretty_url.startswith(self.RATE_URL):
                pass
            elif req.pretty_url.startswith(self.ACCOUNT_URL):
                pass
            elif req.pretty_url.startswith(self.POSITION_URL):
                pass

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'POST':
            if req.pretty_url.startswith(self.RATE_URL):
                data = self.parse_prices(res.text)
                self.push_data(**data)
            elif req.pretty_url.startswith(self.ACCOUNT_URL):
                data = self.parse_account(content=res.text)
                self.push_data(**data)
            elif req.pretty_url.startswith(self.POSITION_URL):
                data = self.parse_stream_positions(content=res.text)
                self.push_data(**data)

    def parse_prices(self, content: str) -> dict:
        # rate
        """
        ,
        20
        USDJPY,112.643,112.646,112.485,112.885,112.405,0.100,112.543,,0
        EURJPY,118.840,118.846,118.671,118.890,118.506,0.108,118.732,,0
        """
        if not content:
            return {}
        prices = {}
        now = jst_now_aware()
        for row in csv.reader(StringIO(content)):
            if len(row) < 3:
                continue
            instrument = row[0][:3] + '/' + row[0][-3:]
            bid = float(row[1])
            ask = float(row[2])
            price = Price(self.NAME, instrument=instrument, time=now, bid=bid, ask=ask)
            prices.setdefault(self.NAME, {})[instrument] = price
        return dict(prices=prices)

    def parse_account(self, content: str) -> dict:
        """
        ,
        1740422,1737422,510000,0,-3000,340.67,1227422,1227422,-3000,0,0,1020000,510000,7.17,0,0,0,0,0
        """
        if not content:
            return {}
        for row in csv.reader(StringIO(content)):
            if len(row) < 7:
                continue
            try:
                margin_ratio = float(row[5])
            except ValueError:
                margin_ratio = 0
            self.accounts[self.NAME] = self.accounts[self.NAME].replace(equity=float(row[1]), used_margin=float(row[2]),
                                                                        profit_loss=float(row[4]))
        # self.account.update(balance=float(row[0]),
        #                                equity=float(row[1]),
        #                                used_margin=float(row[2]),
        #                                profit_loss=float(row[4]),
        #                                margin_ratio=margin_ratio,
        #                                available=float(row[6]),
        #                                online=True)
        return dict(accounts=self.accounts)

    def parse_stream_positions(self, content: str) -> dict:
        """
        ,
        1
        AUDJPY,150,0,83.153,0.000,510000,-3450,0,0,0,-3450,0
        """
        if not content:
            return {}
        positions = {}
        for row in csv.reader(StringIO(content)):
            if len(row) < 5:
                continue
            instrument = row[0][:3] + '/' + row[0][-3:]
            buy_amount = int(row[1]) * 1000
            sell_amount = int(row[2]) * 1000
            amount = buy_amount - sell_amount
            positions[instrument] = amount
        self.accounts[self.NAME].positions.update(positions)
        return dict(accounts=self.accounts)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
            Usage:
              {f} [options]

            Options:
              --bind IP_PORT  [default: 127.0.0.1:10103]
              --proxy IP_PORT  [default: 127.0.0.1:8083]
              --chrome IP_PORT  [default: 127.0.0.1:11003]
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

    node = Gaitamecom(Gaitamecom.NAME, address,
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
