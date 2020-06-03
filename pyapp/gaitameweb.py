import csv
import json
import re
from collections import defaultdict
from io import StringIO
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


class Gaitameweb(EngineServer):
    PRICE_TIMEOUT = 2.5

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.update_accounts([self.account])
        self.streaming_positios = {}

        self.conn_factory = lambda *args, **kwargs: CustomConnection(*args, on_data=self.on_data, **kwargs)

    def on_account(self, content: str):
        """
        ,
        1740422,1737422,510000,0,-3000,340.67,1227422,1227422,-3000,0,0,1020000,510000,7.17,0,0,0,0,0
        """
        if not content:
            return
        for row in csv.reader(StringIO(content)):
            if len(row) < 7:
                continue
            try:
                margin_ratio = float(row[5])
            except ValueError:
                margin_ratio = 0
            self.account.update(balance=float(row[0]),
                                equity=float(row[1]),
                                margin=float(row[2]),
                                pl=float(row[4]),
                                margin_ratio=margin_ratio,
                                available=float(row[6]))
        self.update_accounts([self.account])

    def on_prices(self, content: str):
        # rate
        """
        ,
        20
        USDJPY,112.643,112.646,112.485,112.885,112.405,0.100,112.543,,0
        EURJPY,118.840,118.846,118.671,118.890,118.506,0.108,118.732,,0
        """
        if not content:
            return
        prices = []
        now = timeutil.jst_now()
        for row in csv.reader(StringIO(content)):
            if len(row) < 3:
                continue
            instrument = row[0][:3] + '/' + row[0][-3:]
            bid = float(row[1])
            ask = float(row[2])
            prices.append(dict(service=self.name, instrument=instrument, time=now, bid=bid, ask=ask))
        self.update_prices(prices)

    def on_positions(self, conn: CustomConnection):
        if not conn.url.startswith('https://tradefx.gaitame.com/pcweb/gneo/trade.html?'):
            return
        html = conn.get_html(css_selector='#uforex1_id_byCurrencyPairListHome_MyTable')
        if not html:
            return
        dom = lxml.html.fromstring(html)
        positions = {}
        for tr in dom.cssselect('table tr'):
            text = tr.text_content()
            text = re.sub('\s+', ' ', text).replace(',', '')
            m = re.search('(?P<instrument>[A-Z]+/[A-Z]+) [A-Z]+ (?P<bid_amount>\d+) \d+ [.\d]+ (?P<ask_amount>\d+)',
                          text)
            if not m:
                continue
            d = m.groupdict()
            positions[convert_instrument(d['instrument'])] = (int(d['ask_amount']) - int(d['bid_amount'])) * 1000
        self.account['positions'] = positions
        self.account['positions'].update(self.streaming_positios)
        self.update_accounts([self.account])

    def on_streaming_positions(self, content:str):
        """
        ,
        1
        AUDJPY,150,0,83.153,0.000,510000,-3450,0,0,0,-3450,0
        """
        if not content:
            return
        positions = {}
        for row in csv.reader(StringIO(content)):
            if len(row) < 5:
                continue
            instrument = row[0][:3] + '/' + row[0][-3:]
            buy_amount = int(row[1]) * 1000
            sell_amount = int(row[2]) * 1000
            amount = buy_amount - sell_amount
            positions[instrument] = amount
        self.streaming_positios.update(positions)
        self.account['positions'].update(positions)
        self.update_accounts([self.account])

    def on_data(self, conn: CustomConnection, data: dict):
        method = data['method']  # type: str
        params = data['params']  # type: dict

        if method == 'Network.loadingFinished':
            url = data['url']
            request_id = params['requestId']
            if url.startswith('https://tradefx.gaitame.com/webpublisher/RateServlet'):
                return self.on_prices(conn.get_response_body(request_id))
            elif url.startswith('https://tradefx.gaitame.com/webserviceapi/accountDetail.do'):
                return self.on_account(conn.get_response_body(request_id))
            elif url.startswith('https://tradefx.gaitame.com/webserviceapi/possumDetailA.do'):
                    return self.on_streaming_positions(conn.get_response_body(request_id))

    def refresh(self):
        self.streaming_positios.clear()
        for conn in self.driver.connections():
            if not conn.url.startswith('https://tradefx.gaitame.com/pcweb/gneo/trade.html?'):
                continue
            #conn.click(css_selector='#home_reload')
            conn.click(css_selector='#uforex1_id_byCurrencyPairListHome_MyTable a.btnUpdate')

    def run_job(self, state: dict):
        while state['run']:
            try:
                for conn in self.driver.connections():  # type: CustomConnection
                    self.on_positions(conn)
                    pass
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1.0)


if __name__ == '__main__':
    try:
        start_engine(Gaitameweb, chrome_port=11003)
    except KeyboardInterrupt:
        pass
