import csv
import json
import logging
import os
import re
import shutil
import sys
import threading
import time
from collections import OrderedDict
from collections import defaultdict
from io import StringIO
from typing import Dict
from typing import List

import lxml.html
from chromedriver import ChromeClient
from chromedriver import ChromeDriver
from chromedriver.eventhandler import EventHandlerBase
from docopt import docopt

import env
from rpcmixin import new_account
from rpcserver import Slave


class ChromeServer(Slave):
    def __init__(self, name, bind_address, *, master_address, port: int):
        super().__init__(name, bind_address, master_address=master_address)
        self.driver = None  # type: ChromeDriver
        self.chrome_port = port
        self.client_factory = ChromeClient

    def init_driver(self):
        if self.driver:
            return
        home_dir = env.get_home_dir()
        if env.is_posix():
            default_profile_dir = '{}/.config/chromium'.format(home_dir)
        elif env.is_windows():
            default_profile_dir = '{}/AppData/Local/Google/Chrome/User Data'.format(home_dir)
        else:
            raise Exception('unknown os.name {}'.format(os.name))

        profile_dir = os.path.join(env.get_desktop_dir(), 'chrome_profiles', self.name)
        if not os.path.exists(profile_dir):
            shutil.copytree(default_profile_dir, profile_dir)

        self.logger.info('PROFILE_DIR {}'.format(profile_dir))
        self.logger.info('connect to chrome port {}'.format(self.chrome_port))
        self.logger.info('client_factory:{}'.format(self.client_factory))
        self.driver = ChromeDriver(name=self.name,
                                   profile_dir=profile_dir,
                                   remote_port=self.chrome_port)
        time.sleep(1)
        self.logger.info('ChromeDriver launched')

    def get_prices(self) -> List[dict]:
        return []

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return []

    def get_client(self, endpoint: dict):
        return self.driver.get_client(id=endpoint['id'], client_factory=self.client_factory)

    def run_job(self, state: dict):
        while state['run']:
            for endpoint in self.driver._get_endpoints():
                self.get_client(endpoint)
            time.sleep(1.0)

    def start(self):
        self.init_driver()
        from pprint import pprint
        pprint(self.driver.get_endpoints())

        state = {'run': True}
        thread = threading.Thread(daemon=True, target=self.run_job, args=(state,))
        #        spawn = gevent.spawn(lambda: self.run_job(state))
        thread.start()
        super().start()
        state['run'] = False
        #        spawn.join()
        thread.join()


class Gaitameweb(ChromeServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.prices = []
        parent = self

        class EventHandler(EventHandlerBase):
            def on_event(self, event: dict):
                parent.on_event(event)

        class Client(ChromeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.wait_connected()
                self.network.enable()
                self.register_event_handler(EventHandler())

        self.client_factory = Client
        self.clients = {}  # type: Dict[str, Client]

    def on_event(self, event: dict):
        try:
            handler = event['handler']  # type: ChromeClient
            data = event['data']  # type: dict
            method = data['method']  # type: str
            params = data['params']  # type: dict
            if method == 'Network.responseReceived':
                url = params['response']['url']  # type: str
                if url.startswith('https://tradefx.gaitame.com/webpublisher/RateServlet'):
                    # rate
                    """
                    ,
                    20
                    USDJPY,112.643,112.646,112.485,112.885,112.405,0.100,112.543,,0
                    EURJPY,118.840,118.846,118.671,118.890,118.506,0.108,118.732,,0
                    """
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        self.prices = []
                        return
                    prices = []
                    for row in csv.reader(StringIO(body)):
                        if len(row) < 3:
                            continue
                        instrument = row[0][:3] + '/' + row[0][-3:]
                        bid = float(row[1])
                        ask = float(row[2])
                        prices.append(dict(service=self.name, instrument=instrument, bid=bid, ask=ask))
                    self.prices = prices

                elif url.startswith('https://tradefx.gaitame.com/webserviceapi/accountDetail.do'):
                    """
                    ,
                    1740422,1737422,510000,0,-3000,340.67,1227422,1227422,-3000,0,0,1020000,510000,7.17,0,0,0,0,0
                    """
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        return
                    for row in csv.reader(StringIO(body)):
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
                        break
                elif url.startswith('https://tradefx.gaitame.com/webserviceapi/possumDetailA.do'):
                    """
                    ,
                    1
                    AUDJPY,150,0,83.153,0.000,510000,-3450,0,0,0,-3450,0
                    """
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        return
                    positions = {}
                    for row in csv.reader(StringIO(body)):
                        if len(row) < 5:
                            continue
                        instrument = row[0][:3] + '/' + row[0][-3:]
                        buy_amount = int(row[1]) * 1000
                        sell_amount = int(row[2]) * 1000
                        amount = buy_amount - sell_amount
                        positions[instrument] = amount
                    self.account['positions'] = positions

            else:
                return
        except Exception as e:
            self.logger.exception(str(e))
            print(event)

    def get_prices(self) -> List[dict]:
        return self.prices

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return [self.account]

    def run_job(self, state: dict):
        while state['run']:
            clients = {}
            for endpoint in self.driver._get_endpoints():
                clients[endpoint['url']] = self.get_client(endpoint)
            self.clients = clients
            time.sleep(1.0)


class Pfxnano(ChromeServer):
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

    class Client(ChromeClient):
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

        def __init__(self, ws_url: str, *args, event_handler, **kwargs):
            super().__init__(ws_url, *args, **kwargs)
            self.wait_connected()
            self.network.enable()
            self.dom.enable()
            self.register_event_handler(event_handler)

        def get_prices(self, url) -> List[dict]:
            for service, price_url in Pfxnano.PRICE_URLS.items():
                if price_url in url:
                    break
            else:
                return []
            assert service
            prices = []
            html = self.dom.get_html(css_selector='#PriceList')
            if not html:
                self.dom.switch_frame('#rate')
                html = self.dom.get_html(css_selector='#PriceList')
            if not html:
                return []
            bid_str = '#bidCurrencyPrice{}'
            ask_str = '#askCurrencyPrice{}'
            dom = lxml.html.fromstring(html)
            for i, instrument in enumerate(self.INSTRUMENTS[service]):
                i += 1
                bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
                ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
                prices.append(dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask))
            return prices

        def get_positions(self, url) -> Dict[str, dict]:
            for service, simple_url in Pfxnano.SIMPLE_URLS.items():
                if simple_url in url:
                    break
            else:
                return {}
            assert service
            positions = {}
            html = self.dom.get_html(css_selector='.newOrderPanel')
            dom = lxml.html.fromstring(html)
            instrument = dom.cssselect('.selectBox.currencyPair span')[0].text_content()[:7]
            bid_amount = dom.cssselect('span[uifield="bidTotalAmount"]')[0].text_content().replace(',', '')
            ask_amount = dom.cssselect('span[uifield="askTotalAmount"]')[0].text_content().replace(',', '')
            bid_pl = dom.cssselect('span[uifield="bidEvaluationPl"]')[0].text_content().replace(',', '')
            ask_pl = dom.cssselect('span[uifield="askEvaluationPl"]')[0].text_content().replace(',', '')
            # text = dom.text_content()
            # text = re.sub('\s+', '', text)
            positions[service] = {}
            positions[service][instrument] = {
                'amount': -float(bid_amount or 0) + float(ask_amount or 0),
                'pl': float(bid_pl) + float(ask_pl),
            }
            return positions

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.accounts = {k: new_account(k) for k in self.KEYS}

        class EventHandler(EventHandlerBase):
            def on_event(_self, event: dict):
                self.on_event(event)

        self.event_handler = EventHandler()
        self.client_factory = lambda *args, **kwargs: self.Client(*args, event_handler=self.event_handler, **kwargs)
        self.clients = {}  # type: Dict[str, Pfxnano.Client]

    def on_event(self, event: dict):
        try:
            handler = event['handler']  # type: ChromeClient
            data = event['data']  # type: dict
            method = data['method']  # type: str
            params = data['params']  # type: dict
            if method == 'Network.responseReceived':
                # margin, equity
                url = params['response']['url']  # type: str
                for k, margin_url in self.MARGIN_URLS.items():
                    if margin_url == url:
                        body = handler.network.get_response_body(params['requestId'])
                        if not body:
                            return
                        json_data = json.loads(re.sub('(\w+):', '"\\1":', re.sub('\s', '', body)))
                        available = float(json_data['marginBuyingPower'].replace(',', ''))
                        equity = float(json_data['netAsset'].replace(',', ''))
                        margin = equity - available
                        margin_ratio = (equity / margin * 100) if margin > 100 else 0
                        self.accounts[k].update(equity=equity, margin=margin,
                                                available=available, margin_ratio=margin_ratio)

            elif 'DOM' in method:
                pass
        except Exception as e:
            self.logger.exception(str(e))
            print(event)

    def get_prices(self) -> List[dict]:
        prices = []
        for url, client in self.clients.items():
            prices += client.get_prices(url)
        return prices

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return list(self.accounts.values())

    def get_accounts_bg(self):
        pl_dict = defaultdict(float)
        for url, client in self.clients.items():
            positions = client.get_positions(url)
            for service, position in positions.items():
                for instrument, position_detail in position.items():
                    self.accounts[service]['positions'][instrument] = position_detail['amount']
                    pl_dict[service] += position_detail['pl']
        for k, account in self.accounts.items():
            account['pl'] = pl_dict[k]

    def run_job(self, state: dict):
        while state['run']:
            clients = {}
            for endpoint in self.driver._get_endpoints():
                clients[endpoint['url']] = self.get_client(endpoint)
            self.clients = clients
            self.get_accounts_bg()
            time.sleep(1.0)


class Try(ChromeServer):
    URL = 'https://triauto.invast.jp/TriAuto/user/rate.do'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.prices = []
        self.position_list = []

        class EventHandler(EventHandlerBase):
            def on_event(_self, event: dict):
                self.on_event(event)

        class Client(ChromeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.wait_connected()
                self.network.enable()
                self.register_event_handler(EventHandler())

            def get_account(self, url: str) -> dict:
                try:
                    account = {}
                    if url != 'https://triauto.invast.jp/TriAuto/user/index.do':
                        return account

                    html = self.dom.get_html(css_selector='table table')
                    if not html:
                        self.dom.switch_frame('#triautocontent')
                        html = self.dom.get_html(css_selector='table table')
                    if not html:
                        return account
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
                    return account
                except Exception as e:
                    self.logger.exception(str(e))
                    return {}

        self.client_factory = Client
        self.clients = {}  # type: Dict[str, Client]

    def on_event(self, event: dict):
        try:
            handler = event['handler']  # type: ChromeClient
            data = event['data']
            method = data['method']
            params = data['params']
            if method == 'Network.responseReceived':
                url = params['response']['url']  # type: str
                if url.startswith('https://triauto.invast.jp/TriAuto/user/api/getHomeRateMap.do'):
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        self.prices = []
                        return
                    prices = []
                    for k, v in json.loads(body)['rateMap'].items():
                        instrument = '{}/{}'.format(k[:3], k[-3:])
                        bid, ask = float(v['bid']), float(v['ask'])
                        d = dict(service=self.name, instrument=instrument, bid=bid, ask=ask)
                        prices += [d]
                    self.prices = prices
                elif url.startswith('https://triauto.invast.jp/TriAuto/user/api/getContainerAccountInfo.do'):
                    body = json.loads(handler.network.get_response_body(params['requestId']))
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
            elif 'DOM' in method:
                pass
        except Exception as e:
            self.logger.exception(str(e))
            print(event)

    def get_client(self, endpoint: dict):
        return self.driver.get_client(id=endpoint['id'], client_factory=self.client_factory)

    def get_prices(self) -> List[dict]:
        return self.prices

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return [self.account]

    def get_accounts_bg(self):
        for url, client in self.clients.items():
            account = client.get_account(url)
            self.account.update(account)

    def run_job(self, state: dict):
        while state['run']:
            clients = {}
            for endpoint in self.driver._get_endpoints():
                clients[endpoint['url']] = self.get_client(endpoint)
            self.clients = clients

            self.get_accounts_bg()
            time.sleep(1.0)


class Yjfx(ChromeServer):
    URL = 'https://gaikaex.net/quote.txt'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.account = new_account(self.name)
        self.prices = []
        self.position_list = []
        self.currency_map = {}
        parent = self

        class EventHandler(EventHandlerBase):
            def on_event(_self, event: dict):
                self.on_event(event)

        class Client(ChromeClient):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.wait_connected()
                self.network.enable()
                self.dom.enable()
                self.register_event_handler(EventHandler())

            def update_currency_map(self, url: str):
                if parent.currency_map:
                    return
                if url != 'https://gaikaex.net/servlet/lzca.pc.cfr001.servlet.CFr00101':
                    return
                self.dom.switch_frame(to_default_content=True)
                self.dom.switch_frame('#priceboard')
                self.dom.switch_frame('iframe[name="CIf00301"]')
                html = self.dom.get_html('#priceBoard')
                if not html:
                    return
                dom = lxml.html.fromstring(html)
                map = {}
                for tr in dom.cssselect('tbody tr'):
                    id = tr.get('id')
                    td_list = tr.cssselect('.currencyPair')
                    if not td_list:
                        continue
                    instrument = convert_instrument(td_list[0].text_content())
                    map[id] = instrument
                parent.currency_map = map

                self.logger.info('#CURRENCY_MAP: {}'.format(parent.currency_map))

            def get_account(self, url: str) -> dict:
                try:
                    account = {}
                    if url != 'https://gaikaex.net/servlet/lzca.pc.cfr001.servlet.CFr00101':
                        return account

                    self.dom.switch_frame(to_default_content=True)
                    self.dom.switch_frame('#customerInfo_v2')
                    html = self.dom.get_html(css_selector='#left_navi')
                    if not html:
                        return account
                    dom = lxml.html.fromstring(html)
                    text = dom.text_content()
                    text = re.sub('\s+', ' ', text).replace(',', '')
                    map = {
                        '資産合計': 'balance',
                        '評価損益': 'pl',
                        '証拠金維持率': 'margin_ratio',
                    }
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
                    return account
                except Exception as e:
                    self.logger.exception(str(e))
                    return {}

        self.client_factory = Client
        self.clients = {}  # type: Dict[str, Client]

    def on_event(self, event: dict):
        try:
            handler = event['handler']  # type: ChromeClient
            data = event['data']  # type: dict
            method = data['method']  # type: str
            params = data['params']  # type: dict
            if method == 'Network.responseReceived':
                url = params['response']['url']  # type: str
                if url.startswith('https://gaikaex.net/quote.txt'):
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        return
                    """EUR/USD	1	1.07338	1.07343	0.00450	1.06888	1.07384	1.06836	-34	33	0	5	2"""
                    body = re.sub('\s+', ' ', body)
                    prices = []
                    for line in re.findall('[A-Z/]+ \S+ \S+ \S+', body):
                        l = re.findall('\S+', line)
                        instrument = l[0]
                        bid = float(l[2])
                        ask = float(l[3])
                        d = dict(service=self.name, instrument=instrument, bid=bid, ask=ask)
                        prices += [d]
                    self.prices = prices
                elif self.currency_map and url.startswith(
                        'https://gaikaex.net/servlet/lzca.pc.cht200.servlet.CHt20003?'):
                    body = handler.network.get_response_body(params['requestId'])
                    if not body:
                        return
                    positions = {}
                    for currency_id, position in json.loads(body)['data'].items():
                        instrument = self.currency_map[currency_id]
                        for _, position_detail in position.items():
                            buy_sell = position_detail.get('BUYSELL')
                            total = position_detail.get('TOTAL')
                            if buy_sell == 1:
                                total = -total
                            positions[instrument] = total
                    self.account['positions'] = positions

            else:
                return
        except Exception as e:
            self.logger.exception(str(e))
            print(event)

    def get_prices(self) -> List[dict]:
        return self.prices

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return [self.account]

    def get_accounts_bg(self):
        for url, client in self.clients.items():
            account = client.get_account(url)
            self.account.update(account)
            client.update_currency_map(url)

    def run_job(self, state: dict):
        while state['run']:
            clients = {}
            for endpoint in self.driver._get_endpoints():
                clients[endpoint['url']] = self.get_client(endpoint)
            self.clients = clients

            self.get_accounts_bg()
            time.sleep(1.0)


def convert_instrument(pair: str) -> str:
    map = OrderedDict(
        (('米ドル', 'USD'),
         ('ユーロ', 'EUR'),
         ('英ポンド', 'GBP'),
         ('ポンド', 'GBP'),
         ('豪ドル', 'AUD'),
         ('ニュージーランドドル', 'NZD'),
         ('NZドル', 'NZD'),
         ('ＮＺドル', 'NZD'),
         ('スウェーデンクローナ', 'SOK'),
         ('ノルウェークローネ', 'NOK'),
         ('ポーランドズロチ', 'PLN'),
         ('加ドル', 'CAD'),
         ('ｶﾅﾀﾞﾄﾞﾙ', 'CAD'),
         ('カナダドル', 'CAD'),
         ('カナダ', 'CAD'),
         ('スイスフラン', 'CHF'),
         ('ｽｲｽﾌﾗﾝ', 'CHF'),
         ('スイス', 'CHF'),
         ('トルコリラ', 'TRY'),
         ('南アフリカランド', 'ZAR'),
         ('南アランド', 'ZAR'),
         ('ランド', 'ZAR'),
         ('円', 'JPY'),
         ('人民元', 'CNH'),
         ('ウォン', 'KRW'),
         ('香港ドル', 'HKD'),
         ('シンガポールドル', 'SGD'),
         ('SGドル', 'SGD'),
         ('^ドル/', 'USD/'),
         ('/ドル$', '/USD'),)
    )
    orig_pair = pair
    pair = re.sub('／', '/', pair)
    for ja, en in map.items():
        pair = re.sub(ja, en, pair)
    if len(pair) != 6:
        pair = pair[:3] + '/' + pair[-3:]
    # assert len(pair) == 7, orig_pair
    return pair


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] NAME

    Options:
      --master IP_PORT  [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
      --port PORT     [default: 0]
    """.format(f=sys.argv[0]))
    name = args['NAME']
    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))
    port = int(args['--port'])

    service_map = {
        #        'click': Click,
        #        'nano': lambda *_args, **kwargs: PfxNano('pfxnano', *_args[1:], pfx=False, nano=True, **kwargs),
        #        'pfx': lambda *_args, **kwargs: PfxNano('pfxnano', *_args[1:], pfx=True, nano=False, **kwargs),
        'gaitameweb': (Gaitameweb, 11003),
        'pfxnano': (Pfxnano, 11000),
        'try': (Try, 11001),
        'yjfx': (Yjfx, 11002),
    }
    server, default_port = service_map[name]
    server = server(name, bind_address, master_address=master_address, port=port or default_port)
    assert server
    server.start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
