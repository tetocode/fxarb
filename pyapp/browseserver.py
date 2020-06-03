import logging
import os
import random
import re
import shutil
import sys
import time
from collections import defaultdict
from typing import List

import lxml.html
from docopt import docopt
from gevent.threading import Lock
from selenium.common.exceptions import TimeoutException

import env
import selepy
from rpcmixin import with_lock, new_account
from rpcserver import Slave


class BrowseServer(Slave):
    URL = None
    FRAME_LIST = ()

    def __init__(self, name, bind_address, *, master_address, driver_port: int):
        super().__init__(name, bind_address, master_address=master_address)
        self.driver = None
        self.driver_port = driver_port
        self.last_handle = None
        self.init_driver()
        self.disabled_until = time.time()
        self._lock = Lock()
        self.handle_to_url = {}  # type:Dict[str, str]

    def iter_windows(self, url_re):
        try:
            self.driver.set_page_load_timeout(1)
            driver = self.driver
            for handle in self.driver.window_handles:
                try:
                    self.switch_window(handle)
                    if re.search(url_re, driver.current_url):
                        self.logger.info('window found url_re:{} handle:{}'.format(url_re, handle))
                        yield handle
                except TimeoutException:
                    pass
            return None
        except Exception as e:
            self.last_handle = None
            self.logger.exception(str(e))
            raise

    def find_window(self, url_re, frame_list=()):
        for handle in self.iter_windows(url_re):
            self.switch_frame(frame_list=frame_list)
            return handle
        return None

    def switch_window(self, handle):
        self.last_handle = None
        self.driver.switch_to.window(handle)
        self.last_handle = handle
        return handle

    def switch_frame(self, frame_list=()):
        for frame in frame_list:
            self.driver.switch_to.frame(frame)
        return True

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
        self.logger.info('connect to driver port {}'.format(self.driver_port))
        self.driver = selepy.Chrome(args=['--user-data-dir={}'.format(profile_dir)],
                                    port=self.driver_port)
        time.sleep(5)

    def get_element_html(self, *, css_selector):
        e_list = self.driver.get_elements(css_selector=css_selector)
        if len(e_list) != 1:
            return ''
        html = e_list[0].get_attribute('innerHTML')
        return html or ''

    def get_element_dom(self, *, css_selector):
        html = self.get_element_html(css_selector=css_selector)
        return lxml.html.fromstring(html) if html else None

    def get_element_text(self, *, css_selector):
        dom = self.get_element_dom(css_selector=css_selector)
        return dom.text_content() if dom else ''

    def get_prices_impl(self):
        return []

    @with_lock(blocking=False, default_return=lambda: [])
    def get_prices(self) -> List[dict]:
        if time.time() < self.disabled_until:
            return []
        prices = []
        try:
            if self.last_handle or self.find_window(self.URL, frame_list=self.FRAME_LIST):
                prices = self.get_prices_impl()
                return prices
        except Exception as e:
            self.logger.exception(str(e))
            raise
        finally:
            if not prices:
                self.logger.info('window not found wait 10sec')
                self.disabled_until = time.time() + 10
                self.last_handle = None

    def get_market(self, instrument: str = None):
        return {}

    def get_accounts_impl(self, do_refresh: bool = False) -> List[dict]:
        return []

    @with_lock(blocking=True, default_return=lambda: [])
    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        try:
            return self.get_accounts_impl(do_refresh=do_refresh)
        except Exception as e:
            self.logger.exception(str(e))
            raise

    def start(self):
        super().start()


class Click(BrowseServer):
    URL = 'https://fx.click-sec.com/neo/web/trade'
    MARKET_URL = 'https://fx.click-sec.com/neo/web/speed-order.htm'

    def get_prices_impl(self) -> List[dict]:
        prices = []
        service = self.name
        e_list = self.driver.get_elements(css_selector='#ratePanelPanel')
        if len(e_list) != 1:
            return []
        html = e_list[0].get_attribute('innerHTML')
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        replace_spaces = re.compile('\s')
        for e in dom.cssselect('.ratePanel-box'):
            instrument = e.cssselect('.product-pulldown-name')[0].text_content()
            instrument = replace_spaces.sub('', instrument)
            bid = e.cssselect('.ratePanel-box-bid.pointer')[0].text_content()
            ask = e.cssselect('.ratePanel-box-ask.pointer')[0].text_content()
            bid, ask = float(replace_spaces.sub('', bid)), float(replace_spaces.sub('', ask))
            prices.append(dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask))
        self.get_market()
        return prices

    def get_market(self, instrument: str = None) -> dict:
        handle = self.find_window(self.MARKET_URL)
        if not handle:
            return {}
        service = self.name
        dom = self.get_element_dom(css_selector='#outermost-frame')
        if not dom:
            return {}
        replace_spaces = re.compile('\s')
        e = dom
        instrument = e.cssselect('#current-selection')[0].text_content()
        instrument = replace_spaces.sub('', instrument)
        bid = e.cssselect('#bid-button')[0].text_content()
        ask = e.cssselect('#ask-button')[0].text_content()
        bid, ask = float(replace_spaces.sub('', bid)), float(replace_spaces.sub('', ask))
        d = dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask)
        return d

    def get_account_impl(self) -> List[dict]:
        if not self.find_window('https://fx.click-sec.com/neo/web/trade'):
            return []

        return []


class PfxNano(BrowseServer):
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
    URLS = {
        'pfx': 'https://trade.moneypartners.co.jp/fxcwebpresen/MainFrame.do',
        'nano': 'https://trade2.moneypartners.co.jp/fxcwebpresen/MainFrame.do',
    }
    MARKET_URLS = {
        'pfx': 'https://trade-pfx1.moneypartners.co.jp/quick/app/home',
        'nano': 'https://trade-nano1.moneypartners.co.jp/quick/app/home',
    }

    def __init__(self, *args, pfx=True, nano=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.disabled_untils = defaultdict(float)
        self.last_handles = defaultdict(str)
        self.enabled = dict(pfx=pfx, nano=nano)
        self.refresh_powers = defaultdict(float)

    def _get_prices_impl(self, service: str, instruments: List[str]) -> List[dict]:
        bid_str = '#bidCurrencyPrice{}'
        ask_str = '#askCurrencyPrice{}'
        results = []
        e_list = self.driver.get_elements(css_selector='#PriceList')
        if len(e_list) != 1:
            return []
        html = e_list[0].get_attribute('innerHTML')
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        for i, instrument in enumerate(instruments):
            i += 1
            bid = float(dom.cssselect(bid_str.format(i))[0].text_content())
            ask = float(dom.cssselect(ask_str.format(i))[0].text_content())
            results.append(dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask))
        return results

    @with_lock(blocking=False, default_return=lambda: [])
    def get_prices(self) -> List[dict]:
        prices_all = []
        for key, url in random.sample(list(self.URLS.items()), len(self.URLS)):
            if not self.enabled[key]:
                continue
            service = key
            key = ('prices', key)
            if time.time() < self.disabled_untils[key]:
                continue
            prices = []
            try:
                handle = self.last_handles[key]
                if handle:
                    # if handle != self.last_handle:
                    self.switch_window(handle)
                    self.switch_frame(['rate'])
                    # self.driver.switch_to.window(handle)
                    # self.driver.switch_to.frame('rate')
                    prices = self._get_prices_impl(service, self.INSTRUMENTS[service])
                    self.last_handle = handle
            finally:
                if not prices:
                    self.logger.info('{} get_prices: window not found wait 10sec'.format(key))
                    self.disabled_untils[key] = time.time() + 10
                    self.last_handles[key] = self.find_window(url, ['rate'])
            prices_all += prices
        return prices_all

    def get_market(self, instrument: str = None):
        prices_all = []
        for key, url in random.sample(list(self.MARKET_URLS.items()), len(self.MARKET_URLS)):
            if not self.enabled[(key, 'market')]:
                continue
            if time.time() < self.disabled_untils[(key, '.market')]:
                continue
            prices = []
            try:
                if self.find_window(url):
                    dom = self.get_element_dom(css_selector='#workspace .orderPanel')
                    instrument = dom.cssselect('.currencyPair')[0].text_content()[:7]
                    bid = dom.cssselect('.bid.button div')[0].text_content()
                    ask = dom.cssselect('.ask.button div')[0].text_content()
                    print(dict(instrument=instrument, service=key, bid=float(bid), ask=float(ask)))
            finally:
                if not prices:
                    self.disabled_untils[(key, '.market')] = time.time() + 10
            prices_all += prices
        return prices_all

    def will_refresh(self, service: str):
        N = 1000
        x = random.random() * N
        print('#', service, x)
        if x < 1:
            # self.refresh_powers[service] = 0.0
            return True
        return False

    def _get_accounts_impl(self, service: str, do_refresh: bool = False):
        self.driver.switch_to.frame('header')
        html = self.get_element_html(css_selector='#marginstatusinfo')
        if not html:
            print('no header html')
            return {}
        dom = lxml.html.fromstring(html)
        text = re.sub('[\s]+', ' ', dom.text_content())
        text = re.sub(',', '', text)
        m = re.search('実効レバレッジ： ([-.0-9]+)倍 取引余力： ([-.0-9]+)円 純資産： ([-.0-9]+)円 証拠金維持率： ([-.0-9]*)', text)
        if not m:
            return {}
        leverage = float(m.group(1))
        available = float(m.group(2))
        equity = float(m.group(3))
        margin_rate = float(m.group(4) or 0)
        margin = equity - available

        account = new_account(service, equity=equity, margin=margin)

        self.driver.switch_to.default_content()
        self.driver.switch_to.frame('main')

        # refresh position
        if do_refresh or self.will_refresh(service):
            print('click')
            self.driver.get_element(css_selector='input.button', value='更新').click()

        html = self.get_element_html(css_selector='#grid2')
        dom = lxml.html.fromstring(html)
        positions = {}
        pl = 0
        for th, dom in zip(dom.cssselect('tr th a'), dom.cssselect('tr.total')):
            text = th.text_content()
            instrument = re.sub('\s', '', text)
            text = dom.text_content()
            text = re.sub('\s+', ' ', text)
            text = re.sub(',', '', text)
            m = re.search('\((.+?)\) ([-0-9]+)', text)
            if m:
                positions[instrument] = int(m.group(1))
                pl += int(m.group(2))
        account.update(pl=pl, positions=positions)
        return account

    @with_lock(blocking=True, default_return=lambda: [])
    def get_accounts(self, do_refresh: bool = False) -> List[dict]:
        try:
            accounts_all = []
            for key, url in random.sample(list(self.URLS.items()), len(self.URLS)):
                if not self.enabled[key]:
                    continue
                service = key
                key = ('account', key)
                if time.time() < self.disabled_untils[key]:
                    continue
                account = {}
                try:
                    handle = self.last_handles[key]
                    if handle:
                        self.driver.switch_to.window(handle)
                        account = self._get_accounts_impl(service=service)
                        self.last_handle = handle
                finally:
                    if not account:
                        self.logger.info('{} get_accounts: window not found wait 10sec'.format(key))
                        self.disabled_untils[key] = time.time() + 10
                        self.last_handles[key] = self.find_window(url, ['main'])
                if account:
                    accounts_all.append(account)
            return accounts_all
        except Exception as e:
            self.logger.exception(str(e))
            raise


class Try(BrowseServer):
    URL = 'https://triauto.invast.jp/TriAuto/user/rate.do'

    def get_prices_impl(self) -> List[dict]:
        prices = []
        service = self.name
        e_list = self.driver.get_elements(css_selector='#rateList2')
        if len(e_list) != 1:
            return []
        html = e_list[0].get_attribute('innerHTML')
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        replace_spaces = re.compile('\s')
        for e in dom.cssselect('.currencyPair'):
            instrument = e.cssselect('td')[0].text_content()
            instrument = replace_spaces.sub('', instrument)
            bid = e.cssselect('td.bid')[0].text_content()
            ask = e.cssselect('td.ask')[0].text_content()
            bid, ask = float(bid), float(ask)
            prices.append(dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask))
        return prices

    def get_accounts_impl(self, do_refresh: bool = False) -> List[dict]:
        return []
        try:
            URL = 'https://triauto.invast.jp/TriAuto/user/index.do'
            if not self.find_window(url_re=URL, frame_list=['triautocontent']):
                return []
            text = self.get_element_text(css_selector='html')
            text = re.sub('[\s]+', ' ', text)
            text = re.sub(',', '', text)
            print('#', text)
            m = re.search(('証拠金預託額(\d+)円 有効証拠金額(\d+)円 \(([.\d]+)%\) 評価損益(\d+)円 証拠金不足額(\d+)円'
                           ' 必要証拠金(\d+)円 発注証拠金(\d+)円 発注可能額(\d+)円'), text)
            if not m:
                print('#not found')
                return []
            l = m.groups()
            account = new_account(service='try', equity=float(l[1]), pl=float(l[2]), margin=float(l[5]))
            return [account]
        finally:
            self.last_handle = None

class Yjfx(BrowseServer):
    INSTRUMENT_MAP = {
        'ドル/円': 'USD/JPY',
        'ユーロ/円': 'EUR/JPY',
        'ユーロ/ドル': 'EUR/USD',
        '豪ドル/円': 'AUD/JPY',
        'ＮＺドル/円': 'NZD/JPY',
        'ポンド/円': 'GBP/JPY',
        'ｽｲｽﾌﾗﾝ/円': 'CHF/JPY',
        'ｶﾅﾀﾞﾄﾞﾙ/円': 'CAD/JPY',
        'ポンド/ドル': 'GBP/USD',
        'ランド/円': 'ZAR/JPY',
    }
    URL = 'https://gaikaex.net/servlet/lzca.pc.cfr001.servlet.CFr00101'
    FRAME_LIST = ('priceboard', 'CIf00301')

    def get_prices_impl(self) -> List[dict]:
        prices = []
        service = self.name
        e_list = self.driver.get_elements(css_selector='#priceBoard tbody')
        if len(e_list) != 1:
            return []
        html = e_list[0].get_attribute('innerHTML')
        if not html:
            return []
        dom = lxml.html.fromstring(html)
        replace_spaces = re.compile('\s')
        for e in dom.cssselect('tr'):
            instrument = e.cssselect('.currencyPair')[0].text_content()
            instrument = replace_spaces.sub('', instrument)
            instrument = self.INSTRUMENT_MAP[instrument]
            bid = e.cssselect('.bid.order')[0].text_content()
            bid += e.cssselect('.bidSmall.order')[0].text_content()
            ask = e.cssselect('.ask.order')[0].text_content()
            ask += e.cssselect('.askSmall.order')[0].text_content()
            bid, ask = float(bid), float(ask)
            prices.append(dict(service=service, time=None, instrument=instrument, bid=bid, ask=ask))
        return prices

    def get_accounts_impl(self, do_refresh: bool = False) -> List[dict]:
        return []
        if not self.find_window(url_re=self.URL, frame_list=['main_v2']):
            return []

        if do_refresh:
            self.driver.get_element(css_selector='.contents_box2 .mb8 .tab_area2 .update').click()
        self.last_handle = None


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options] NAME

    Options:
      --master IP_PORT  [default: 127.0.0.1:10000]
      --bind IP_PORT    [default: 127.0.0.1:0]
      --driver PORT     [default: 9100]
    """.format(f=sys.argv[0]))
    name = args['NAME']
    l = args['--master'].split(':')
    master_address = (l[0], int(l[1]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))
    driver_port = int(args['--driver'])

    service_map = {
        'click': Click,
        'nano': lambda *_args, **kwargs: PfxNano('pfxnano', *_args[1:], pfx=False, nano=True, **kwargs),
        'pfx': lambda *_args, **kwargs: PfxNano('pfxnano', *_args[1:], pfx=True, nano=False, **kwargs),
        'pfxnano': PfxNano,
        'try': Try,
        'yjfx': Yjfx,
    }
    server = service_map[name]
    server = server(name, bind_address, master_address=master_address, driver_port=driver_port)
    assert server
    server.start()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
