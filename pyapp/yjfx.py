import json
import re
from typing import Dict

import gevent
import lxml.html

import timeutil
from engineserver import EngineServer, start_engine, EngineConnection, convert_instrument
from rpcmixin import new_account


class CustomConnection(EngineConnection):
    def __init__(self, *args, on_data, **kwargs):
        self.instrument = None
        self._on_data = on_data
        super().__init__(*args, **kwargs)
        self.update_frame_ids()

    def on_data(self, data: dict):
        self._on_data(self, data)


class Yjfx(EngineServer):
    PRICE_TIMEOUT = 1.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)
        self.currencies = {}  # type: Dict[str, str]

    def on_currencies(self, conn: CustomConnection):
        if self.currencies:
            return
        key = ('name', 'CIf00301')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            return
        html = conn.get_html(css_selector='*', node_id=node_id)
        dom = lxml.html.fromstring(html)
        currencies = {}
        for tr in dom.cssselect('tbody tr'):
            id = tr.get('id')
            td_list = tr.cssselect('.currencyPair')
            if not td_list:
                continue
            instrument = convert_instrument(td_list[0].text_content())
            currencies[id] = instrument
        self.currencies = currencies
        self.logger.info('#currencies={}'.format(self.currencies))

    def on_account(self, conn:CustomConnection):
        key = ('id', 'customerInfo_v2')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            return
        html = conn.get_html(css_selector='*', node_id=node_id)
        dom = lxml.html.fromstring(html)
        text = dom.text_content()
        text = re.sub('\s+', ' ', text).replace(',', '')
        map = {
            '資産合計': 'balance',
            '評価損益': 'pl',
            '証拠金維持率': 'margin_ratio',
        }
        account = self.account
        d = {}
        for word, key in map.items():
            m = re.search('{} ([-,.0-9]+)'.format(word), text)
            if m:
                try:
                    account[key] = d[key] = float(m.group(1))
                except ValueError:
                    pass
        account['equity'] = account['balance'] + account['pl']

        if 'margin_ratio' in d:
            account['margin'] = account['equity'] / (d['margin_ratio'] / 100)
        else:
            account['margin'] = 0#account['equity']
            account['margin_ratio'] = 0.0
        account['available'] = account['equity'] - account['margin']
        self.account = account
        self.update_accounts([self.account])

    def on_prices(self, content: str):
        if not self.currencies:
            self.logger.warn('on_prices: no currencies')
            return
        """EUR/USD	1	1.07338	1.07343	0.00450	1.06888	1.07384	1.06836	-34	33	0	5	2"""
        body = re.sub('\s+', ' ', content)
        prices = []
        now = timeutil.jst_now()
        for m in re.finditer('(?P<instrument>[A-Z/]+/[A-Z]+) \S+ (?P<bid>[.\d]+) (?P<ask>[.\d]+)', body):
            d = m.groupdict()
            instrument = d['instrument']
            bid = float(d['bid'])
            ask = float(d['ask'])
            d = dict(service=self.name, instrument=instrument, time=now, bid=bid, ask=ask)
            prices += [d]
        self.update_prices(prices)

    def on_positions(self,  content: str):
        if not self.currencies:
            self.logger.warn('on_positions: no currencies')
            return
        positions = {}
        for currency_id, position in json.loads(content)['data'].items():
            instrument = self.currencies[currency_id]
            for _, position_detail in position.items():
                buy_sell = position_detail.get('BUYSELL')
                total = position_detail.get('TOTAL')
                if buy_sell == 1:
                    total = -total
                positions[instrument] = total
        self.account['positions'] = positions
        self.update_accounts([self.account])

    def on_data(self, conn: CustomConnection, data: dict):
        method = data['method']  # type: str
        params = data['params']  # type: dict

        if method == 'Network.loadingFinished':
            url = data['url']
            request_id = params['requestId']
            if url == 'https://gaikaex.net/quote.txt':
                return self.on_prices(conn.get_response_body(request_id))
            if self.currencies and url.startswith('https://gaikaex.net/servlet/lzca.pc.cht200.servlet.CHt20003?'):
                return self.on_positions(conn.get_response_body(request_id))

    def run_job(self, state: dict):
        while state['run']:
            try:
                for conn in self.driver.connections():  # type: CustomConnection
                    if conn.url == 'https://gaikaex.net/servlet/lzca.pc.cfr001.servlet.CFr00101':
                        self.on_currencies(conn)
                        self.on_account(conn)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


if __name__ == '__main__':
    try:
        start_engine(Yjfx, chrome_port=11002)
    except KeyboardInterrupt:
        pass
