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


class Gaitamejp(EngineServer):
    PRICE_TIMEOUT = 1.0
    PRICE_URL = 'https://login.gaitamejapan.com/fxcrichpresen/webrich/app/home?'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)
        self.currencies = {}  # type: Dict[str, str]

    def on_account(self, conn: CustomConnection):
        if not conn.url.startswith(self.PRICE_URL):
            return
        html = conn.get_html(css_selector='#workspace .marginStatusBarPanel')
        if not html:
            return
        dom = lxml.html.fromstring(html)
        text = dom.text_content()
        text = re.sub('\s+', ' ', text).replace(',', '')
        # 証拠金維持率 - % 建玉可能額 510765 円 純資産 510765 円 総損益合計 0 円
        map = {
            '純資産': 'equity',
            '総損益合計': 'pl',
            '証拠金維持率': 'margin_ratio',
            '建玉可能額': 'available',
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
        account['balance'] = account['equity'] - account['pl']

        if 'margin_ratio' in d:
            account['margin'] = account['equity'] / (d['margin_ratio'] / 100)
        else:
            account['margin'] = account['equity']
        self.account = account
        self.update_accounts([self.account])

    def on_prices(self, conn: CustomConnection):
        if not conn.url.startswith(self.PRICE_URL):
            return
        html = conn.get_html(css_selector='#workspaceContainer .rateBoxContainerPanel')
        if not html:
            return
        dom = lxml.html.fromstring(html)
        prices = []
        now = timeutil.jst_now()
        for dom in dom.cssselect('.rateBoxPanel'):
            instrument = re.sub('\s+', '', dom.cssselect('div[uifield="currencyPairSelect"] span')[0].text_content())
            bid = re.sub('\s+', '', dom.cssselect('.pricePanel.bid .price')[0].text_content())
            ask = re.sub('\s+', '', dom.cssselect('.pricePanel.ask .price')[0].text_content())
            prices.append(dict(service=self.name, instrument=instrument, time=now, bid=float(bid), ask=float(ask)))
        self.update_prices(prices)

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
        return
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
        i = 0
        while state['run']:
            i += 1
            try:
                for conn in self.driver.connections():
                    self.on_prices(conn)
                    if i % 10 == 0:
                        self.on_account(conn)
                    gevent.sleep(0)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(0.1)


if __name__ == '__main__':
    try:
        start_engine(Gaitamejp, chrome_port=11006)
    except KeyboardInterrupt:
        pass
