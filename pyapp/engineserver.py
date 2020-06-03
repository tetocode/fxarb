import copy
import logging
import os
import re
import shutil
import sys
from collections import OrderedDict
from typing import Dict
from typing import List

import gevent
from chromepy import Connection, ChromeDriver
from docopt import docopt

import env
import timeutil
from rpcserver import Slave


class EngineConnection(Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_urls = OrderedDict()  # type: Dict[str, str]
        self.enable('DOM', 'Network')

    def on_event(self, data: dict):
        method = data['method']
        params = data['params']
        if len(self.request_urls) > 100:
            self.request_urls.popitem(last=False)
        if method == 'Network.requestWillBeSent':
            self.request_urls[params['requestId']] = params['request']['url']
        elif method == 'Network.loadingFinished':
            try:
                data['url'] = self.request_urls.pop(params['requestId'])
            except KeyError:
                return
        self.on_data(data)

    def on_data(self, data: dict):
        pass


class EngineServer(Slave):
    PRICE_TIMEOUT = 1.0

    def __init__(self, name, bind_address, *, master_address, port: int):
        super().__init__(name, bind_address, master_address=master_address)
        self.driver = None  # type: ChromeDriver
        self.chrome_port = port
        self.conn_factory = Connection
        self.prices = []
        self.accounts = []

    def _init_driver(self):
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
        self.logger.info('conn_factory:{}'.format(self.conn_factory))
        self.driver = ChromeDriver(logger=self.logger,
                                   profile_dir=profile_dir,
                                   remote_port=self.chrome_port,
                                   connection_factory=self.conn_factory)
        gevent.sleep(1)
        self.logger.info('ChromeDriver launched')

    def init_driver(self):
        if self.driver:
            return
        self.logger.info('connect to chrome port {}'.format(self.chrome_port))
        self.logger.info('conn_factory:{}'.format(self.conn_factory))
        self.driver = ChromeDriver(logger=self.logger,
                                   profile_dir=None,
                                   remote_port=self.chrome_port,
                                   connection_factory=self.conn_factory)
        gevent.sleep(1)
        self.logger.info('ChromeDriver launched')

    def update_prices(self, prices: List[dict]):
        self.prices = prices

    def update_accounts(self, accounts: List[dict]):
        self.accounts = accounts

    def get_prices(self) -> List[dict]:
        now = timeutil.jst_now()
        prices = []
        for price in self.prices:
            if (now - price['time']).total_seconds() < self.PRICE_TIMEOUT:
                price = copy.deepcopy(price)
                price['time'] = str(price['time'])
                prices.append(price)
        return prices

    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        return self.accounts

    def refresh(self):
        pass

    def run_job(self, state: dict):
        while state['run']:
            list(self.driver.connections())
            gevent.sleep(1.0)

    def start(self):
        self.init_driver()
        from pprint import pprint
        pprint(self.driver.get_endpoints())

        state = {'run': True}
        cor = gevent.spawn(lambda: self.run_job(state))
        super().start()
        state['run'] = False
        cor.join()


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
    pair = re.sub('／', '/', pair)
    for ja, en in map.items():
        pair = re.sub(ja, en, pair)
    if len(pair) != 6:
        pair = pair[:3] + '/' + pair[-3:]
    return pair


def start_engine(engine_factory: EngineServer, *, chrome_port: int):
    logging.basicConfig(level=logging.WARN, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --master IP_PORT  [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
    """.format(f=sys.argv[0]))
    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))

    name = engine_factory.__name__.lower()
    server = engine_factory(name=name, bind_address=bind_address, master_address=master_address, port=chrome_port)
    assert server
    server.start()
