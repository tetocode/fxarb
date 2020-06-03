import json
import re
from typing import Dict

import gevent
import lxml.html
from chromepy import Connection

import timeutil
from engineserver import EngineServer, start_engine, EngineConnection, convert_instrument
from rpcmixin import new_account


class CustomConnection(EngineConnection):
    def __init__(self, *args, on_data, service: str, **kwargs):
        self.service = service
        self._on_data = on_data
        super().__init__(*args, **kwargs)
        self.update_frame_ids()

    def on_data(self, data: dict):
        self._on_data(self, data)


class Pfxnano(EngineServer):
    PRICE_TIMEOUT = 1.0
    KEYS = ('pfx', 'nano')
    PRICE_URLS = {
        'pfx': 'https://trade.moneypartners.co.jp/fxcwebpresen/MainFrame.do',
        'nano': 'https://trade2.moneypartners.co.jp/fxcwebpresen/MainFrame.do',
    }
    MARGIN_URLS = {
        'pfx': 'https://trade.moneypartners.co.jp/fxcwebpresen/UpdateMarginStatus.do',
        'nano': 'https://trade2.moneypartners.co.jp/fxcwebpresen/UpdateMarginStatus.do',
    }
    SIMPLE_URLS = {
        'nano': 'https://trade-nano1.moneypartners.co.jp/quick/app/simpleBoardHome',
    }
    STREAM_URLS = {
        'pfx': 'https://trade.moneypartners.co.jp/fxcbroadcast/rpc/FxCAjaxPushBsController?',
        'nano': 'https://trade2.moneypartners.co.jp/fxcbroadcast/rpc/FxCAjaxPushBsController?',
    }
    INSTRUMENTS = {
        'pfx': [
            'USD/JPY', 'EUR/USD', 'AUD/JPY',
            'NZD/JPY', 'GBP/JPY', 'EUR/JPY',
            'CHF/JPY', 'CAD/JPY', 'GBP/USD',
            'ZAR/JPY',
        ],
        'nano': [
            'USD/JPY', 'EUR/JPY', 'AUD/JPY',
            'EUR/USD', 'GBP/JPY', 'NZD/JPY',
            'ZAR/JPY', 'CHF/JPY',
        ],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._accounts = {k: new_account(k) for k in self.KEYS}
        self.update_accounts(list(self._accounts.values()))

        self.conn_factory = self.create_connection
        self.currencies = {}  # type: Dict[str, str]
        self.positions = {}

    def create_connection(self, *args, url: str, **kwargs):
        if url.startswith(self.PRICE_URLS['nano']) or url.startswith(self.SIMPLE_URLS['nano']):
            service = 'nano'
        else:
            service = 'pfx'
        return CustomConnection(*args, url=url, on_data=self.on_data, service=service, **kwargs)

    def on_account(self, service: str, content: str):
        # margin, equity
        if not content:
            return
        json_data = json.loads(re.sub('(\w+):', '"\\1":', re.sub('\s', '', content)))
        available = float(json_data['marginBuyingPower'].replace(',', ''))
        equity = float(json_data['netAsset'].replace(',', ''))
        margin = equity - available
        margin_ratio = (equity / margin * 100) if margin > 100 else 0
        pl = 0.0
        if service in self.positions:
            positions = self.positions[service]
            for instrument, d in positions.items():
                amount = d['amount']
                pl += d['pl']
                self._accounts[service]['positions'][instrument] = amount
        self._accounts[service].update(equity=equity, margin=margin,
                                       available=available, margin_ratio=margin_ratio, pl=pl)

        self.update_accounts(list(self._accounts.values()))

    def on_positions(self, service: str, conn: CustomConnection):
        html = conn.get_html(css_selector='.newOrderPanel')
        dom = lxml.html.fromstring(html)
        instrument = dom.cssselect('.selectBox.currencyPair span')[0].text_content()[:7]
        bid_amount = dom.cssselect('span[uifield="bidTotalAmount"]')[0].text_content().replace(',', '')
        ask_amount = dom.cssselect('span[uifield="askTotalAmount"]')[0].text_content().replace(',', '')
        bid_pl = dom.cssselect('span[uifield="bidEvaluationPl"]')[0].text_content().replace(',', '')
        ask_pl = dom.cssselect('span[uifield="askEvaluationPl"]')[0].text_content().replace(',', '')
        # text = dom.text_content()
        # text = re.sub('\s+', '', text)
        positions = {}
        positions[instrument] = {
            'amount': -float(bid_amount or 0) + float(ask_amount or 0),
            'pl': float(bid_pl) + float(ask_pl),
        }
        self.positions.setdefault(service, {}).update(positions)

    def on_prices(self):
        prices = []
        for conn in self.driver.connections():
            for service, price_url in self.PRICE_URLS.items():
                if conn.url.startswith(price_url):
                    prices += self._extract_prices(service, conn) or []
                gevent.sleep(0)
        self.update_prices(prices)

    def _extract_prices(self, service: str, conn: CustomConnection):
        key = ('id', 'rate')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            return
        html = conn.get_html(css_selector='#PriceList', node_id=node_id)
        if not html:
            self.logger.warn('#no #PriceList')
            return
        bid_str = '#bidCurrencyPrice{}'
        ask_str = '#askCurrencyPrice{}'
        dom = lxml.html.fromstring(html)
        prices = []
        now = timeutil.jst_now()
        for i, instrument in enumerate(self.INSTRUMENTS[service]):
            i += 1
            bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
            ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
            prices.append(dict(service=service, instrument=instrument, time=now, bid=bid, ask=ask))
        return prices

    def on_data(self, conn: CustomConnection, data: dict):
        method = data['method']  # type: str
        params = data['params']  # type: dict

        if method == 'Network.loadingFinished':
            url = data['url']
            request_id = params['requestId']
            for service, margin_url in self.MARGIN_URLS.items():
                if margin_url == url:
                    return self.on_account(service, conn.get_response_body(request_id))
        elif method == 'Network.dataReceived':
            return
            try:
                url = conn.request_urls[params['requestId']]
                for service, stream_url in self.STREAM_URLS.items():
                    if url.startswith(stream_url):
                        return self.on_prices(service, conn)
            except KeyError:
                pass

    def run_job(self, state: dict):
        i = 0
        while state['run']:
            i += 1
            try:
                self.on_prices()
                if i % 10 == 0:
                    for conn in self.driver.connections():  # type: CustomConnection
                        for service, simple_url in self.SIMPLE_URLS.items():
                            if simple_url in conn.url:
                                self.on_positions(service, conn)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(0.1)


if __name__ == '__main__':
    try:
        start_engine(Pfxnano, chrome_port=11000)
    except KeyboardInterrupt:
        pass
