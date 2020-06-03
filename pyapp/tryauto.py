import json
import re
from collections import defaultdict
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


class Tryauto(EngineServer):
    PRICE_TIMEOUT = 1.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)

    def on_account(self, conn:CustomConnection):
        key = ('id', 'triautocontent')
        node_id = conn.frame_ids.get(key)
        if not node_id:
            self.logger.warn('#no key={}'.format(key))
            return

        account = {}
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
            '証拠金預託額': 'balance',
            '有効証拠金額': 'equity',
            '評価損益': 'pl',
            '必要証拠金': 'margin',
            '発注可能額': 'available',
        }
        for word, key in map.items():
            m = re.search('{}.*?([-,.0-9]+)'.format(word), text)
            if m:
                account[key] = float(m.group(1))
        if 'margin' in account and 'equity' in account:
            if account['margin'] > 0:
                account['margin_ratio'] = account['equity'] / account['margin'] * 100.0
            else:
                account['margin_ratio'] = 0.0
        self.account.update(account)
        self.update_accounts([self.account])

    def on_prices(self, content: str):
        prices = []
        now = timeutil.jst_now()
        for k, v in json.loads(content)['rateMap'].items():
            instrument = '{}/{}'.format(k[:3], k[-3:])
            bid, ask = float(v['bid']), float(v['ask'])
            d = dict(service=self.name, instrument=instrument, time=now, bid=bid, ask=ask)
            prices += [d]
        self.update_prices(prices)

    def on_positions(self,  content: str):
        body = json.loads(content)
        self.account_info = info = body['accountInfo']
        equity = float(info['equity'])
        margin = float(info['position_margin'])
        pl = equity - float(info['balance'])
        positions = defaultdict(int)
        self.position_list = body['positionList']
        for position in body['positionList']:
            currency = position['currencyPair']
            instrument = '{}/{}'.format(currency[:3], currency[-3:])
            amount = float(position['positionQty'])
            if position['buySell'] == '2':
                amount = -amount
            positions[instrument] += amount
        self.account = new_account(self.name, equity=equity, pl=pl, margin=margin,
                                   positions=dict(**positions))
        self.logger.info('account: {}'.format(self.account))
        self.update_accounts([self.account])

    def on_data(self, conn: CustomConnection, data: dict):
        method = data['method']  # type: str
        params = data['params']  # type: dict

        if method == 'Network.loadingFinished':
            url = data['url']
            request_id = params['requestId']
            if url.startswith('https://triauto.invast.jp/TriAuto/user/api/getHomeRateMap.do'):
                return self.on_prices(conn.get_response_body(request_id))
            if url.startswith('https://triauto.invast.jp/TriAuto/user/api/getContainerAccountInfo.do'):
                return self.on_positions(conn.get_response_body(request_id))

    def run_job(self, state: dict):
        while state['run']:
            try:
                for conn in self.driver.connections():  # type: CustomConnection
                    if conn.url == 'https://triauto.invast.jp/TriAuto/user/index.do':
                        self.on_account(conn)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


if __name__ == '__main__':
    try:
        start_engine(Tryauto, chrome_port=11001)
    except KeyboardInterrupt:
        pass
