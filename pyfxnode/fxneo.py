import logging
import re
import sys
import threading
import time

import lxml.html
import pychrome
from docopt import docopt

from pyfxnode.account import Account
from pyfxnode.price import Price
from pyfxnode.webnode import WebNode


class Fxneo(WebNode):
    NAME = 'fxneo'
    PRICE_URL = 'https://fx.click-sec.com/neo/web/trade'
    accounts = {
        NAME: Account(NAME),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        threading.Thread(target=lambda: self.poll_chrome(0.5), daemon=True).start()

    def poll_chrome(self, interval: float):
        if not self.chrome:
            self.warning('no chrome driver')
            return
        while True:
            try:
                for conn in self.chrome.connections(re.escape(self.PRICE_URL)):
                    self.on_prices(conn)
            except Exception as e:
                self.exception(str(e))
            time.sleep(interval)

    def on_prices(self, conn: pychrome.Connection):
        html = conn.get_html(css_selector='#rateListPanel')
        if not html:
            return
        dom = lxml.html.fromstring(html)
        prices = {}
        for tr in dom.cssselect('tr.rateList-tbody'):
            text = tr.cssselect('.product-pulldown-name')[0].text_content()
            text += tr.cssselect('.rateList-tbody-bid')[0].text_content()
            text += tr.cssselect('.rateList-tbody-ask')[0].text_content()
            text = re.sub('\s+', ' ', text)
            m = re.search('(?P<instrument>\w+/\w+) (?P<bid>[.\d]+) (?P<ask>[.\d]+)', text)
            if m:
                d = m.groupdict()
                price = Price(self.NAME, instrument=d['instrument'], bid=float(d['bid']), ask=float(d['ask']))
                prices.setdefault(self.NAME, {})[d['instrument']] = price
        self.push_data(prices=prices)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
            Usage:
              {f} [options]

            Options:
              --bind IP_PORT  [default: 127.0.0.1:10105]
              --proxy IP_PORT  [default: 127.0.0.1:8085]
              --chrome IP_PORT  [default: 127.0.0.1:11005]
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

    node = Fxneo(Fxneo.NAME, address,
                 # proxy_address=proxy_address,
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
