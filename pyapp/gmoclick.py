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
        self._on_data = on_data
        super().__init__(*args, **kwargs)
        self.update_frame_ids()

    def on_data(self, data: dict):
        self._on_data(self, data)


class Gmoclick(EngineServer):
    PRICE_TIMEOUT = 1.0
    PRICE_URL = 'https://fx.click-sec.com/neo/web/trade'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)
        self.currencies = {}  # type: Dict[str, str]

    def on_account(self, conn: CustomConnection):
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
            m = re.search('{}.*?([-,.0-9]+)'.format(word), text)
            if m:
                try:
                    account[key] = d[key] = float(m.group(1))
                except ValueError:
                    pass
        account['equity'] = account['balance'] + account['pl']

        if 'margin_ratio' in d:
            account['margin'] = account['equity'] / (d['margin_ratio'] / 100)
        else:
            account['margin'] = account['equity']
        account['available'] = account['equity'] - account['margin']
        self.account = account
        self.update_accounts([self.account])

    def on_prices(self):
        for conn in self.driver.connections():
            gevent.sleep(0)
            if conn.url != self.PRICE_URL:
                continue
            html = conn.get_html(css_selector='#rateListPanel')
            if not html:
                return
            dom = lxml.html.fromstring(html)
            prices = []
            now = timeutil.jst_now()
            for tr in dom.cssselect('tr.rateList-tbody'):
                text = tr.cssselect('.product-pulldown-name')[0].text_content()
                text += tr.cssselect('.rateList-tbody-bid')[0].text_content()
                text += tr.cssselect('.rateList-tbody-ask')[0].text_content()
                text = re.sub('\s+', ' ', text)
                m = re.search('(?P<instrument>\w+/\w+) (?P<bid>[.\d]+) (?P<ask>[.\d]+)', text)
                if m:
                    d = m.groupdict()
                    prices += [dict(service=self.name, instrument=d['instrument'],
                                    time=now, bid=float(d['bid']), ask=float(d['ask']))]
                gevent.sleep(0.0)
            return self.update_prices(prices)

    def on_positions(self, content: str):
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
            return
            url = data['url']
            request_id = params['requestId']
            if url == 'https://gaikaex.net/quote.txt':
                return self.on_prices(conn.get_response_body(request_id))
            if self.currencies and url.startswith('https://gaikaex.net/servlet/lzca.pc.cht200.servlet.CHt20003?'):
                return self.on_positions(conn.get_response_body(request_id))

    def run_job(self, state: dict):
        while state['run']:
            try:
                self.on_prices()
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(0.1)


if __name__ == '__main__':
    try:
        start_engine(Gmoclick, chrome_port=11005)
    except KeyboardInterrupt:
        pass
