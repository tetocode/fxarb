import json
import re
from typing import Dict

import gevent
import lxml.html
from chromepy import Connection

import timeutil
from engineserver import EngineServer, start_engine, EngineConnection
from rpcmixin import new_account


class CustomConnection(EngineConnection):
    def __init__(self, *args, on_data, **kwargs):
        self.instrument = None
        self._on_data = on_data
        super().__init__(*args, **kwargs)
        self.update_frame_ids()

    def on_data(self, data: dict):
        self._on_data(self, data)


class Fxprime(EngineServer):
    PRICE_TIMEOUT = 2.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])
        parent = self

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)
        self.currencies = {}  # type: Dict[str, str]

    def on_currencies(self, content: str):
        data = json.loads(content)
        self.currencies.clear()
        for info in data['detailList1']:
            code = info['currencyCd']
            instrument = info['currencyName4']
            self.currencies[code] = instrument
        self.logger.info('#currencies_code={}'.format(self.currencies))

    def on_prices(self, content: str):
        if not self.currencies:
            self.logger.warn('no currenceis')
            return
        data = json.loads(content)
        prices = []
        now = timeutil.jst_now()
        for info in data['detailList1']:
            code = info['currencyCd']
            instrument = self.currencies.get(code)
            if not instrument:
                continue
            bid, ask = float(info['bid']), float(info['offer'])
            prices.append(dict(service=self.name, instrument=instrument, time=now, bid=bid, ask=ask))
        self.update_prices(prices)

    def on_streaming_prices(self, conn: CustomConnection, content: str):
        data = json.loads(content)
        prices = []
        now = timeutil.jst_now()
        instruments = set()
        for info in data['detailList1']:
            code = info['currencyCd']
            instrument = self.currencies.get(code)
            instruments.add(instrument)
            if not instrument:
                continue
            bid, ask = float(info['bid']), float(info['offer'])
            prices.append(dict(service=self.name, instrument=instrument, time=now, bid=bid, ask=ask))
            conn.instrument = instrument
        prices = list(filter(lambda x: x['instrument'] not in instruments, self.prices)) + prices
        self.update_prices(prices)

    def on_positions(self, conn: CustomConnection):
        content = conn.get_html('#output_high_speed_order_display')
        instrument = conn.instrument
        if not instrument:
            return
        dom = lxml.html.fromstring(content)
        bid_amount = int(float(dom.cssselect('#lbl_amount_bid_1')[0].text_content()) * 10000)
        ask_amount = int(float(dom.cssselect('#lbl_amount_offer_1')[0].text_content()) * 10000)
        self.account['positions'][instrument] = ask_amount - bid_amount
        self.update_accounts([self.account])

    def refresh(self):
        for conn in self.driver.connections():
            if not conn.url.startswith('https://trade.fxprime.com/eraberuGaika/servlet/control.top_frame.TopFrameS'):
                continue
            key = ('id', 'info_position')
            node_id = conn.frame_ids.get(key)
            if not node_id:
                self.logger.warn('#no key={}'.format(key))
                return
            conn.click(css_selector='input[value="更新"]', node_id=node_id)
            #conn.click(css_selector='#nav_global_gaika')
            break

    def on_account(self, conn: CustomConnection):
        key = ('id', 'info_account')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            return
        html = conn.get_html('*', node_id=node_id)
        dom = lxml.html.fromstring(html)
        text = dom.text_content()
        text = re.sub('\s+', ' ', text).replace(',', '')
        map = {
            '取引口座残高': 'balance',
            '評価損益': 'pl',
            '維持率': 'margin_ratio',
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

    def on_data(self, conn: CustomConnection, data: dict):
        method = data['method']  # type: str
        params = data['params']  # type: dict

        if method == 'Network.loadingFinished':
            url = data['url']
            request_id = params['requestId']
            if url == 'https://trade.fxprime.com/eraberuGaika/servlet/api.trading.currency.CurrencyS':
                return self.on_currencies(conn.get_response_body(request_id))
            if url == 'https://trade.fxprime.com/eraberuGaika/servlet/api.trading.rate.RateS':
                return self.on_prices(conn.get_response_body(request_id))
            if url == 'https://trade.fxprime.com/eraberuGaikaHS/servlet/JsonApi/trading.rate.Rate':
                return self.on_streaming_prices(conn, conn.get_response_body(request_id))

    def run_job(self, state: dict):
        url = 'https://trade.fxprime.com/eraberuGaikaHS/servlet/PageView/control.top_frame.TopFrame'
        while state['run']:
            try:
                for conn in self.driver.connections():  # type: CustomConnection
                    if conn.url == url:
                        self.on_positions(conn)
                    elif conn.url == 'https://trade.fxprime.com/eraberuGaika/servlet/control.top_frame.TopFrameS':
                        self.on_account(conn)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


if __name__ == '__main__':
    try:
        start_engine(Fxprime, chrome_port=11004)
    except KeyboardInterrupt:
        pass
