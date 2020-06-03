import json
import logging
import re
import sys
import threading
import time
from io import StringIO
from typing import Dict

import lxml.html
import pychrome
import yaml
from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.webnode import WebNode


class Pfxnano(WebNode):
    NAME = 'pfxnano'
    NANO_PRICE_URL = 'https://trade2.moneypartners.co.jp/fxcbroadcast/rpc/FxCAjaxPushBsController?'
    NANO_STREAM_URL = 'https://trade-nano1.moneypartners.co.jp/quick/socket.io/1/xhr-streaming/'
    NANO_MARGIN_URL = 'https://trade2.moneypartners.co.jp/fxcwebpresen/UpdateMarginStatus.do'
    NANO_SIMPLE_URL = 'https://trade-nano1.moneypartners.co.jp/quick/app/simpleBoardHome'

    PFX_PRICE_URL = 'https://trade.moneypartners.co.jp/fxcbroadcast/rpc/FxCAjaxPushBsController?'

    accounts = {
        'nano': Account('nano'),
        'pfx': Account('pfx'),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.position_pl = {}  # type: Dict[str, float]
        threading.Thread(target=lambda: self.poll_chrome(5.0), daemon=True).start()

    def poll_chrome(self, interval: float):
        if not self.chrome:
            self.warning('no chrome driver')
            return
        while True:
            try:
                for conn in self.chrome.connections(re.escape(self.NANO_SIMPLE_URL)):
                    self.on_positions(conn)
            except Exception as e:
                self.exception(str(e))
            time.sleep(interval)

    def on_positions(self, conn: pychrome.Connection):
        html = conn.get_html(css_selector='.newOrderPanel')
        dom = lxml.html.fromstring(html)
        instrument = dom.cssselect('.selectBox.currencyPair span')[0].text_content()[:7]
        bid_amount = dom.cssselect('span[uifield="bidTotalAmount"]')[0].text_content().replace(',', '')
        ask_amount = dom.cssselect('span[uifield="askTotalAmount"]')[0].text_content().replace(',', '')
        bid_pl = dom.cssselect('span[uifield="bidEvaluationPl"]')[0].text_content().replace(',', '')
        ask_pl = dom.cssselect('span[uifield="askEvaluationPl"]')[0].text_content().replace(',', '')
        # text = dom.text_content()
        # text = re.sub('\s+', '', text)
        positions = {
            instrument: -float(bid_amount or 0) + float(ask_amount or 0),
        }
        self.position_pl[instrument] = float(bid_pl) + float(ask_pl)
        #        positions[instrument] = {
        #            'amount': -float(bid_amount or 0) + float(ask_amount or 0),
        #            'pl': float(bid_pl) + float(ask_pl),
        #        }
        self.accounts['nano'].positions.update(positions)
        self.push_data(accounts=self.accounts)

    def handle_request(self, flow: HTTPFlow):
        pass

    def handle_request_header(self, flow: HTTPFlow):
        pass

    def handle_response_header(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.NANO_STREAM_URL):
                res.stream = True
            elif req.pretty_url.startswith(self.NANO_PRICE_URL):
                flow.response.stream = self.process_nano_chunks
            elif req.pretty_url.startswith(self.NANO_MARGIN_URL):
                pass
            elif req.pretty_url.startswith(self.PFX_PRICE_URL):
                flow.response.stream = self.process_pfx_chunks
            else:
                res.stream = True

    def process_nano_chunks(self, chunks):
        #        now = datetime.utcnow()
        #        with open('{}_{}_dump.txt'.format(self.NAME, now.strftime('%Y%m%dT%H%M%S%f')), 'w') as f:
        name = 'nano'
        chunk = b''
        for new_chunk in chunks:
            if not self.is_running():
                return
            try:
                chunk += new_chunk
                prices = {}
                split_chunks = chunk.split(b';;')
                for chunk in split_chunks[:-1]:
                    try:
                        d = json.loads(chunk.decode('utf-8'))  # type: dict
                        for price_data in d.get('priceList', []):
                            price_data = price_data['priceData']
                            bid = price_data['bid']
                            ask = price_data['ask']
                            # label = bid['priceId'], ask['priceId']
                            instrument = price_data['currencyPair']
                            price = Price(name, instrument, float(bid['price']), float(ask['price']))
                            prices.setdefault(name, {})[instrument] = price
                    except Exception as e:
                        self.exception('{}\nchunk={}'.format(str(e), chunk))
                chunk = split_chunks[-1]
                if prices:
                    self.push_data(prices=prices)
            except Exception as e:
                self.exception(str(e))
            yield new_chunk

    def process_pfx_chunks(self, chunks):
        #        now = datetime.utcnow()
        #        with open('{}_{}_dump.txt'.format(self.NAME, now.strftime('%Y%m%dT%H%M%S%f')), 'w') as f:
        name = 'pfx'
        chunk = b''
        for new_chunk in chunks:
            if not self.is_running():
                return
            try:
                chunk += new_chunk
                prices = {}
                split_chunks = chunk.split(b';;')
                for chunk in split_chunks[:-1]:
                    try:
                        d = json.loads(chunk.decode('utf-8'))  # type: dict
                        for price_data in d.get('priceList', []):
                            price_data = price_data['priceData']
                            bid = price_data['bid']
                            ask = price_data['ask']
                            # label = bid['priceId'], ask['priceId']
                            instrument = price_data['currencyPair']
                            price = Price(name, instrument, float(bid['price']), float(ask['price']))
                            prices.setdefault(name, {})[instrument] = price
                    except Exception as e:
                        self.exception('{}\nchunk={}'.format(str(e), chunk))
                chunk = split_chunks[-1]
                if prices:
                    self.push_data(prices=prices)
            except Exception as e:
                self.exception(str(e))
            yield new_chunk

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response
        if req.pretty_url.startswith(self.NANO_MARGIN_URL):
            data = self.parse_nano_margin(res.text)
            self.push_data(**data)

    def parse_nano_margin(self, content: str) -> dict:
        """
    {

    doUpdate:"true",

    marginBuyingPower:"540,032",

    netAssetRatio:"250.00%",

    netAsset:"900,032",

    leverage:"9.62",

        realtimeMarginStatusType:"marginstatusinfo"
    }
        """
        orig_content = content
        content = content.replace(':', ': ').replace('\t', '')
        d = yaml.load(StringIO(content))
        try:
            available_margin = float(d['marginBuyingPower'].replace(',', ''))
            equity = float(d['netAsset'].replace(',', ''))
            used_margin = equity - available_margin
            pl = sum(self.position_pl.values(), 0)
            self.accounts['nano'] = self.accounts['nano'].replace(equity=equity,
                                                                  used_margin=used_margin,
                                                                  profit_loss=pl)
        except Exception as e:
            self.exception(orig_content + '\n' + str(e))
        return dict(accounts=self.accounts)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT  [default: 127.0.0.1:10100]
      --proxy IP_PORT  [default: 127.0.0.1:8080]
      --chrome IP_PORT  [default: 127.0.0.1:11000]
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

    node = Pfxnano(Pfxnano.NAME, address,
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
