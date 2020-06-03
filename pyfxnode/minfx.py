import json
import logging
import re
import sys

import time
from docopt import docopt
from mitmproxy.http import HTTPFlow

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.utils import jst_now_aware
from pyfxnode.webnode import WebNode


class Minfx(WebNode):
    NAME = 'minfx'
    PRICE_URL = 'https://fxlive.min-fx.tv/fxcbroadcast/rpc/FxCPullBsController?'

    accounts = {
        NAME: Account(NAME),
    }

    def handle_response(self, flow: HTTPFlow):
        req = flow.request
        res = flow.response

        if req.method == 'GET':
            if req.pretty_url.startswith(self.PRICE_URL):
                data = self.parse_prices(res.text)
                self.push_data(accounts=self.accounts, **data)

    def parse_prices(self, content: str) -> dict:
        """
        var priceList = {"timestamp":"1492609861707","requestId":"1492609827340",
            "priceList":[
                {"timestamp":"2017/04/19 22:51:00",
                 "suspend":"false","change":"0.589","high":"109.082","convRate":"1","low":"108.385",
                    "ask":{"price":"109.053","fractionPips":1,"priceId":"303064890002331733A",
                           "head":"109","tail":"053","dealable":true},
                    "currencyPair":"USD/JPY","bid":{"price":"109.050","fractionPips":1,"priceId":"303064890002331733B",
                                                    "head":"109","tail":"050","dealable":true
                    }
                },
                {"timestamp":"2017/04/19 22:51:00",
                 "suspend":"false","change":"0.433","high":"116.972","convRate":"1","low":"116.278"
                ,"ask":{"price":"116.827","fractionPips":1,"priceId":"303064920001696275A",
                        "head":"116","tail":"827","dealable":true},
                "currencyPair":"EUR/JPY","bid":{"price":"116.821","fractionPips":1,"priceId":"303064920001696275B",
                        "head":"116","tail":"821","dealable":true}},
                        ...
            ]};if (window.top.pullBsController) window.top.pullBsController.fire(priceList);
        """
        try:
            if not content:
                return {}
            m = re.search('var priceList = (.*?);', content)
            if not m:
                print('not m')
                return {}
            prices = {}
            now = jst_now_aware()
            data = json.loads(m.group(1))
            for price_info in data.get('priceList', []):
                instrument = price_info['currencyPair']
                ask = float(price_info['ask']['price'])
                bid = float(price_info['bid']['price'])
                price = Price(self.NAME, instrument=instrument, time=now, bid=bid, ask=ask)
                prices.setdefault(self.NAME, {})[instrument] = price
            return dict(prices=prices)
        except Exception as e:
            self.error(content and content[:100])
            self.exception(str(e))
        return {}


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
                Usage:
                  {f} [options]

                Options:
                  --bind IP_PORT  [default: 127.0.0.1:10109]
                  --proxy IP_PORT  [default: 127.0.0.1:8089]
                  --chrome IP_PORT  [default: 127.0.0.1:11009]
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

    node = Minfx(Minfx.NAME, address,
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
