import copy
import csv
import itertools
import logging
import random
import re
import statistics
import sys
from collections import OrderedDict
from collections import defaultdict
from datetime import timedelta
from typing import List, Tuple, Union, Optional, Set, Dict

import gevent
from PyQt5.QtCore import *
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import *
from docopt import docopt
from gsocketpool.pool import Pool

import env
import serviceclient
import timeutil
import yamlutil
from globalsignal import GlobalSignal
from model import Config, ConfigurableMixin
from qt5util import TableView, Splitter
from rpcmixin import new_account
from rpcserver import Master


class InstrumentComboBox(ConfigurableMixin, QComboBox):
    DEFAULT_INSTRUMENTS = ('', 'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'NZD/JPY', '')

    def __init__(self, instrument: str = '', *, name: str):
        super().__init__(name=name)
        self.addItem(instrument)
        self.setCurrentText(instrument)
        self.update_instruments(Config().instruments)
        GlobalSignal().update_instruments.connect(self.update_instruments)

    @pyqtSlot(set)
    def update_instruments(self, instruments: set):
        current = self.currentText()
        self.clear()
        instruments = list(self.DEFAULT_INSTRUMENTS) + list(sorted(instruments))
        instruments = OrderedDict(zip(instruments, instruments)).keys()
        self.addItems(instruments)
        self.setCurrentText(current)


class ServiceComboBox(ConfigurableMixin, QComboBox):
    def __init__(self, service: str = '', *, name: str):
        super().__init__(name=name)
        self.addItem(service)
        self.setCurrentText(service)
        GlobalSignal().update_services.connect(self.update_services)

    @pyqtSlot(set)
    def update_services(self, services: set):
        current = self.currentText()
        self.clear()
        self.addItems([''] + list(sorted(services)))
        self.setCurrentText(current)


def get_pip_scale(instrument: str) -> int:
    if 'JPY' in instrument.upper():
        return 100
    else:
        return 10000


def get_amount(service: str, instrument: str) -> int:
    return Config().accounts.get(service, {}).get('positions', {}).get(instrument, 0)


def get_float_format(instrument: str) -> str:
    if 'JPY' in instrument.upper():
        return '{:.4f}'
    return '{:.6f}'


class FilterView(ConfigurableMixin, QWidget):
    class ServiceView(TableView):
        def __init__(self, *args, name: str, **kwargs):
            labels = ('service', 'sell', 'buy', 'disabled')
            super().__init__(labels=labels, name=name)
            self.setContentsMargins(0, 0, 0, 0)
            self.verticalHeader().hide()
            self.instrument = ''

            font = self.horizontalHeader().font()
            # font.setPointSize(5)
            self.horizontalHeader().setFont(font)

            GlobalSignal().update_services.connect(self.update_services)
            GlobalSignal().update_filters.connect(self.update_filters)
            GlobalSignal().update_disabled_services.connect(self.update_disabled_services)
            self.cellClicked.connect(self.cell_clicked)

        @pyqtSlot(str)
        def update_instrument(self, instrument: str):
            self.instrument = instrument
            self.update_filters()

        @pyqtSlot(set)
        def update_services(self, services: Set[str]):
            self.update_filters()

        @pyqtSlot(set)
        def update_disabled_services(self, services: Set[str]):
            self.update_filters()

        @pyqtSlot(dict)
        def update_filters(self, filters: dict = None):
            config = Config()
            filters = filters or config.filters
            _filter = filters.get(self.instrument, {})
            _filter = defaultdict(set, **_filter)
            services = config.services
            disabled = config.disabled_services
            self.setRowCount(len(services))
            for row, service in enumerate(sorted(services)):
                self.setRowHeight(row, self.ROW_H)
                self.set_item(row, 'service', value=service, flags=Qt.ItemIsEnabled)
                self.set_item(row, 'sell', checked=service in _filter['sells'],
                              flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.set_item(row, 'buy', checked=service in _filter['buys'],
                              flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.set_item(row, 'disabled', checked=service in disabled,
                              flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)

        @pyqtSlot(int, int)
        def cell_clicked(self, row: int, col: int):
            label = self.labels[col]  # type: str
            if label not in ('sell', 'buy', 'disabled'):
                return
            config = Config()
            service = self.item(row, self.labels.index('service')).text()
            checked = True if self.item(row, col).checkState() == Qt.Checked else False
            if not self.instrument:
                return
            filters = config.filters.setdefault(self.instrument, {})
            if label == 'disabled':
                if checked:
                    config.disabled_services.add(service)
                else:
                    config.disabled_services.discard(service)
            else:
                if checked:
                    filters.setdefault(label + 's', set()).add(service)
                else:
                    filters.setdefault(label + 's', set()).discard(service)
            config.update_filters()

    class TabBar(ConfigurableMixin, QTabBar):
        def __init__(self, name: str):
            super().__init__(name=name)

            add_tab = QPushButton('+')
            add_tab.setMaximumWidth(24)
            self.setExpanding(False)
            self.addTab('')
            self.setTabButton(0, 1, add_tab)
            self.setTabsClosable(True)
            self.setMovable(True)
            add_tab.clicked.connect(self.add_tab)
            self.tabCloseRequested.connect(self.close_tab)
            GlobalSignal().update_spreads.connect(self.update_spreads)

        @pyqtSlot(int)
        def close_tab(self, index: int):
            self.removeTab(index)

        @pyqtSlot()
        def add_tab(self):
            count = self.count()
            index = self.insertTab(count - 1, '')
            self.setCurrentIndex(index)

        def rename_current_tab(self, name: str):
            index = self.currentIndex()
            if index >= self.count() - 1:
                return
            self.setTabText(index, name)
            selected = set(filter(str, [self.tabText(i) for i in range(self.count())]))
            Config().selected_instruments.clear()
            Config().selected_instruments.update(selected)
            Config().update_selected_instruments(selected)

        @pyqtSlot(list)
        def update_spreads(self, spreads: List[dict]):
            disabled = Config().disabled_services
            instruments = set([x['instrument'] for x in
                               filter(lambda x: x['bidder'] not in disabled and x['asker'] not in disabled, spreads)])
            for i in range(self.count()):
                text = self.tabText(i)
                if text in instruments:
                    self.setTabTextColor(i, Qt.green)
                else:
                    self.setTabTextColor(i, Qt.black)

    class RateView(TableView):
        def __init__(self, *, name: str):
            labels = ['bidder', 'bid', 'sp', 'ask', 'asker']
            super().__init__(labels=labels, name=name)
            self.setContentsMargins(0, 0, 0, 0)
            self.instrument = ''
            self.setHorizontalHeaderLabels([''] * len(self.labels))
            font = self.horizontalHeader().font()
            font.setPointSize(1)
            self.horizontalHeader().setFont(font)
            self.verticalHeader().hide()
            GlobalSignal().update_prices.connect(self.update_prices)

        @pyqtSlot(str)
        def update_instrument(self, instrument: str):
            self.instrument = instrument

        @pyqtSlot(dict)
        def update_prices(self, prices: List[dict] = ()):
            prices = list(filter(lambda x: x['instrument'] == self.instrument, prices))
            config = Config()
            disabled = config.disabled_services
            accounts = config.accounts
            pip_scale = get_pip_scale(self.instrument)

            bids = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: -x['bid']))
            asks = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: x['ask']))
            row_n = max(len(bids), len(asks)) * 2 - 1
            if self.rowCount() != row_n:
                self.resize_row(row_n)
            rank = (self.rowCount() + 1) // 2
            center = rank - 1
            if not bids or not asks:
                self.clear()
                return
            for row in range(self.rowCount()):
                for col in range(self.columnCount()):
                    self.set_item(row, col)

            float_format = get_float_format(self.instrument)
            max_bid = bids[0]['bid']
            min_ask = asks[0]['ask']
            # set bids
            for i, d in enumerate(bids[:rank]):
                bid = d['bid']
                sp = (min_ask - bid) * pip_scale
                bg = QBrush(Qt.green) if sp < 0 else None
                self.set_item(center + i, 'sp', '{:.2f}'.format(sp), bg=bg)
                amount = get_amount(service=d['service'], instrument=self.instrument)
                bg = QBrush(Qt.green) if amount < 0 else None
                self.set_item(center + i, 'bidder', d['service'], bg=bg)
                self.set_item(center + i, 'bid', float_format.format(bid))
            # set asks
            for i, d in enumerate(asks[:rank]):
                ask = d['ask']
                sp = (ask - max_bid) * pip_scale
                bg = QBrush(Qt.green) if sp < 0 else None
                self.set_item(center - i, 'sp', '{:.2f}'.format(sp), bg=bg)
                amount = get_amount(service=d['service'], instrument=self.instrument)
                bg = QBrush(Qt.green) if amount > 0 else None
                self.set_item(center - i, 'asker', d['service'], bg=bg)
                self.set_item(center - i, 'ask', float_format.format(ask))

    class AccountsView(TableView):
        def __init__(self, name: str):
            labels = ['E', 'service', 'time', 'equity', 'pl', 'margin', 'amount']
            super().__init__(labels=labels, name=name)
            self.instrument = ''
            self.cellClicked.connect(self.cell_clicked)
            GlobalSignal().update_accounts.connect(self.update_accounts)
            GlobalSignal().update_prices.connect(self.update_prices)
            self.services = set()

        @pyqtSlot(str)
        def update_instrument(self, instrument: str):
            self.instrument = instrument
            self.update_accounts()

        @pyqtSlot(int, int)
        def cell_clicked(self, row: int, col: int):
            label = self.labels[col]  # type: str
            if label not in ('E',):
                return
            disabled = Config().disabled_services
            checked = self.item(row, col).checkState() == Qt.Checked
            service = self.item(row, self.labels.index('service')).data(Qt.DisplayRole)
            if checked:
                disabled.discard(service)
            else:
                disabled.add(service)
            Config().update_filters()

        @pyqtSlot(list)
        def update_prices(self, prices: List[dict]):
            self.services.update(set([x['service'] for x in prices]))

        @pyqtSlot(list)
        def update_accounts(self, accounts: List[dict] = None):
            accounts = accounts or {}
            config = Config()
            disabled = config.disabled_services
            self.resize_row(len(self.services))

            serivce_accounts = {a['service']: a for a in accounts}

            for row, service in enumerate(sorted(self.services)):
                d = serivce_accounts.get(service, new_account(service, equity=-1))
                self.set_item(row, 'E', checked=d['service'] not in disabled,
                              flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.set_item(row, 'service', value=d['service'])
                self.set_item(row, 'time', value=d['time'])
                self.set_item(row, 'equity', value='{:.1f}'.format(d['equity']))
                self.set_item(row, 'pl', value='{:.1f}'.format(d['pl']))
                self.set_item(row, 'margin', value='{:.1f}'.format(d['margin']))
                amount = d['positions'].get(self.instrument, 0)
                self.set_item(row, 'amount', value='{}'.format(amount))
                config.accounts.setdefault(d['service'], {}).update(d)

            return

    def change_tab(self, index: int):
        text = self.tab_bar.tabText(index)
        m = re.match('^(\w+/\w+)', text)
        if m:
            instrument = m.group(1)
        else:
            instrument = ''
        self.instrument_combo.setCurrentText(instrument)
        self.instrument_combo.activated[str].emit(instrument)

    @pyqtSlot(str)
    def select_instrument(self, instrument: str):
        self.tab_bar.rename_current_tab(instrument)
        fltr = Config().filters.setdefault(instrument, {})
        self.spread_spin.setValue(fltr.get('spread', 9.9))
        self.duration_spin.setValue(fltr.get('duration', 9.9))
        self.service_view.update_instrument(instrument)
        self.rate_view.update_instrument(instrument)
        self.accounts_view.update_instrument(instrument)

    @pyqtSlot(float)
    def update_spread(self, value: float):
        tab = self.current_tab()
        if not tab:
            return
        fltr = Config().filters.setdefault(tab, {})
        fltr['spread'] = value

    @pyqtSlot(float)
    def update_duration(self, value: float):
        tab = self.current_tab()
        if not tab:
            return
        fltr = Config().filters.setdefault(tab, {})
        fltr['duration'] = value

    def current_tab(self) -> str:
        return self.tab_bar.tabText(self.tab_bar.currentIndex())

    def __init__(self, *, name: str):
        super().__init__(name=name)

        self.setContentsMargins(0, 0, 0, 0)

        tab_bar = self.TabBar(name=name + '.tab_bar')
        instrument_combo = InstrumentComboBox(name=name + '.instrument_combo')
        instrument_combo.setContentsMargins(0, 0, 0, 0)
        spread_spin = QDoubleSpinBox()
        spread_spin.setValue(9.99)
        spread_spin.setMinimum(0.0)
        spread_spin.setMaximum(9.99)
        spread_spin.setDecimals(2)
        spread_spin.setSingleStep(0.05)
        spread_spin.setSuffix(' pips')
        duration_spin = QDoubleSpinBox()
        duration_spin.setValue(9.9)
        duration_spin.setMinimum(0.00)
        duration_spin.setMaximum(99.9)
        duration_spin.setDecimals(1)
        duration_spin.setSingleStep(0.1)
        duration_spin.setSuffix(' s')
        service_view = self.ServiceView(name=name + '.service_view')
        service_view.setContentsMargins(0, 0, 0, 0)
        rate_view = self.RateView(name=name + '.rate_view')
        rate_view.setContentsMargins(0, 0, 0, 0)
        accounts_view = self.AccountsView(name=name + '.accounts_view')
        accounts_view.setContentsMargins(0, 0, 0, 0)

        # signal slot connect
        tab_bar.currentChanged.connect(self.change_tab)
        instrument_combo.activated[str].connect(self.select_instrument)
        spread_spin.valueChanged.connect(self.update_spread)
        duration_spin.valueChanged.connect(self.update_duration)

        # layout
        lo = QGridLayout()
        lo.setSpacing(0)
        lo.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lo)

        lo.addWidget(tab_bar, 0, 0, 1, 3)
        lo.addWidget(instrument_combo, 1, 0)
        lo.addWidget(spread_spin, 1, 1)
        lo.addWidget(duration_spin, 1, 2)
        lo.addWidget(rate_view, 2, 0, 1, 3)
        lo.setRowStretch(2, 1)
        lo.addWidget(accounts_view, 3, 0, 1, 3)

        self.tab_bar = tab_bar
        self.instrument_combo = instrument_combo
        self.spread_spin = spread_spin
        self.duration_spin = duration_spin
        self.service_view = service_view
        self.rate_view = rate_view
        self.accounts_view = accounts_view


class SoundPlayer(ConfigurableMixin, QWidget):
    def __init__(self, *, name: str):
        super().__init__(name=name)
        self.sounds = self.config.setdefault('sounds', {
            'signal_open': {
                'file': './signal_open.wav',
                'loop': 1,
            },
            'signal_close': {
                'file': './signal_close.wav',
                'loop': 3,
            },
        })
        self.q_sounds = {}

        test_button = QPushButton('sound test')
        test_button.setContentsMargins(0, 0, 0, 0)
        mute = QCheckBox('Mute')
        mute.setChecked(self.config.setdefault('mute', False))
        check = QCheckBox('CloseOnly')
        check.setChecked(self.config.setdefault('close_only', False))

        def check_clicked_slot(key):
            @pyqtSlot(bool)
            def check_clicked(b):
                self.config[key] = b

            return check_clicked

        test_button.clicked.connect(
            lambda: self.play('signal_open') if not self.config['close_only'] else self.play('signal_close'))
        mute.clicked.connect(check_clicked_slot('mute'))
        check.clicked.connect(check_clicked_slot('close_only'))

        lo = QHBoxLayout()
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addStretch()
        lo.addWidget(test_button)
        lo.addWidget(mute)
        lo.addWidget(check)
        self.setLayout(lo)
        GlobalSignal().play_sound.connect(self.play)

    @pyqtSlot(str)
    def play(self, name: str):
        if self.config.get('mute'):
            return
        if name == 'signal_open' and self.config.get('close_only'):
            return
        sound = self.sounds.get(name)
        if not sound:
            return
        q = self.q_sounds.get(name)
        finished = False
        if not q:
            self.q_sounds[name] = q = QSound(sound['file'])
            finished = True
        if q.isFinished() or finished:
            q.setLoops(sound['loop'])
            q.play()


class Signaler(ConfigurableMixin, QObject):
    def __init__(self, instrument: str, bidder: str, asker: str, *, name: str):
        super().__init__(name=name)
        self.key = (instrument, bidder, asker)
        self.instrument = instrument
        self.bidder = bidder
        self.asker = asker

        self.history = []
        self.last_sp = 0  # type: Union[int, float]
        self.last_received = timeutil.jst_now()
        self.last_signaled = timeutil.jst_now()

    def opposite_key(self) -> Tuple[str, str, str]:
        return self.key[0], self.key[2], self.key[1]

    def clear(self):
        self.history.clear()
        self.last_sp = 0
        self.last_received = timeutil.jst_now()
        self.last_signaled = timeutil.jst_now()

    def judge(self, bid_data: dict, ask_data: dict) -> Optional[dict]:
        instrument = self.instrument
        b, a = bid_data['service'], ask_data['service']
        next_received = max(bid_data['time'], ask_data['time'])
        assert bid_data['instrument'] == ask_data['instrument']
        if int((bid_data['time'] - ask_data['time']).total_seconds()) >= 0.5:
            self.history.clear()
            return
        config = Config()
        sp_threshold = config.filters.get(instrument, {}).get('spread', 0.5)
        duration_threshold = timedelta(seconds=config.filters.get(instrument, {}).get('duration', 4.0))
        try:
            timeout = timedelta(seconds=1)  # self.config['timeout'])
            if next_received - self.last_received >= timeout:
                self.history.clear()
                return

            pip_scale = get_pip_scale(instrument)
            sp = (bid_data['bid'] - ask_data['ask']) * pip_scale
            d = copy.deepcopy(bid_data)
            d.update(direction=(b, a), bidder=b, asker=a, ask=ask_data['ask'], sp=sp, time=next_received,
                     bid_data=bid_data, ask_data=ask_data, signaled=False)

            if sp < sp_threshold:
                self.history.clear()
                if sp >= 0.1:
                    return d
                return
            self.history.append(d)

            duration = next_received - self.history[0]['time']
            if duration >= duration_threshold:
                self.history = list(filter(lambda x: next_received - x['time'] <= duration_threshold * 2, self.history))
                if len(self.history) >= 2:
                    sp_list = list(map(lambda x: x['sp'], self.history))
                    sp_min = min(sp_list)
                    sp_stdev = statistics.stdev(sp_list)
                    bid_list = list(map(lambda x: x['bid_data']['bid'], self.history))
                    ask_list = list(map(lambda x: x['ask_data']['ask'], self.history))
                    bid_stdev = statistics.stdev(bid_list)
                    ask_stdev = statistics.stdev(ask_list)
                    if sp_stdev > 0.5:
                        logging.warning(
                            'too volatile. sp_stdev:{}, sp_threshold:{}, instrument:{}, {} -> {}'.format(sp_stdev,
                                                                                                         sp_threshold,
                                                                                                         instrument, b,
                                                                                                         a))
                        return
                    if bid_stdev * 2 / bid_list[-1] * 100 > 0.03:
                        logging.warning(
                            'too volatile. bid_stdev:{}, instrument:{}, {} -> {}'.format(bid_stdev, instrument, b, a))
                        return
                    if ask_stdev * 2 / ask_list[-1] * 100 > 0.03:
                        logging.warning(
                            'too volatile. ask_stdev:{}, instrument:{}, {} -> {}'.format(ask_stdev, instrument, b, a))
                        return
                    if sp_min > self.last_sp + 0.01 or (
                                    timeutil.jst_now() - self.last_signaled >= timedelta(minutes=1)):
                        self.last_sp = sp_min
                        d.update(sp=self.last_sp, signaled=True)
                        self.last_signaled = timeutil.jst_now()
                        return copy.deepcopy(d)
        finally:
            self.last_received = next_received


class SignalLogView(TableView):
    MAX_LOG_N = 10000
    MAX_ROW_N = 999

    def __init__(self, *, name: str):
        labels = ['signaled_time', 'instrument', 'bidder', 'asker', 'sp']
        super().__init__(labels=labels, name=name)
        self.signalers = {}
        self.signals = []

        GlobalSignal().update_prices.connect(self.update_prices)
        GlobalSignal().update_signals.connect(self.update_signals)
        GlobalSignal().update_filters.connect(self.refresh_log)

    def get_signaler(self, instrument: str, bidder: str, asker: str):
        key = (instrument, bidder, asker)
        if key not in self.signalers:
            self.signalers[key] = Signaler(instrument, bidder, asker,
                                           name='{}.{}_{}_{}'.format(self.name, instrument, bidder, asker))
        return self.signalers[key]

    @pyqtSlot(list)
    def update_signals(self, signals: List[dict]):
        filters = Config().filters
        selected = Config().selected_instruments
        disabled = Config().disabled_services
        for signal in signals:
            b, a = signal['bidder'], signal['asker']
            if signal['instrument'] not in selected or b in disabled or a in disabled:
                pass
            else:
                bidder_amount = get_amount(signal['bidder'], signal['instrument'])
                asker_amount = get_amount(signal['asker'], signal['instrument'])
                if bidder_amount > 0 and asker_amount < 0:
                    signal['bg'] = QBrush(Qt.green)
                    GlobalSignal().play_sound.emit('signal_close')
                else:
                    GlobalSignal().play_sound.emit('signal_open')
            self.signals.append(signal)
            self.refresh_log()

    @pyqtSlot()
    def refresh_log(self):
        self.signals = self.signals[-self.MAX_LOG_N:]
        disabled = Config().disabled_services
        selected = Config().selected_instruments

        def is_valid(x):
            return x['instrument'] in selected and x['bidder'] not in disabled and x['asker'] not in disabled

        signals = list(filter(is_valid, reversed(self.signals)))[:self.MAX_ROW_N]

        self.resize_row(min(self.MAX_ROW_N, len(signals)))
        for row, signal in enumerate(signals):
            flags = None
            b, a = signal['bidder'], signal['asker']
            if b in disabled or a in disabled:
                flags = Qt.NoItemFlags
            for k, v in signal.items():
                self.set_item(row, k, v, flags=flags, bg=signal['bg'])

    @pyqtSlot(list)
    def update_prices(self, prices: List[dict]):
        instrument_service_prices = defaultdict(lambda: defaultdict(list))
        for price in prices:
            instrument_service_prices[price['instrument']][price['service']].append(price)
        signals = []  # type: List[dict]
        spreads = []  # type: List[dict]
        for instrument, service_prices in instrument_service_prices.items():
            service_pairs = sorted(itertools.permutations(service_prices.keys(), 2), key=str)
            for b, a in service_pairs:
                bid_data, ask_data = service_prices[b][-1], service_prices[a][-1]
                signaler = self.get_signaler(instrument, b, a)
                d = signaler.judge(bid_data=bid_data, ask_data=ask_data)
                if d:
                    spreads.append(d)  # minus spread
                    if d['signaled']:
                        d['signaler'] = signaler
                        d['bg'] = None
                        d['signaled_time'] = d['time'].strftime('%Y-%m-%d %H:%M:%S.%f%Z')
                        d['sp'] = '{:.2f}'.format(d['sp'])
                        signals.append(d)
        GlobalSignal().update_signals.emit(signals)
        GlobalSignal().update_spreads.emit(spreads)


class AppWindow(ConfigurableMixin, QMainWindow):
    def __init__(self, *, name: str):
        super().__init__(name=name)
        config = self.config
        Config().instruments.clear()
        Config().services.clear()

        self.setContentsMargins(0, 0, 0, 0)
        w = QWidget()
        w.setContentsMargins(0, 0, 0, 0)

        splitter = Splitter(Qt.Vertical, name=name + '.splitter')
        splitter.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(splitter)

        # filter view
        filter_view = FilterView(name=name + '.filter_view')
        splitter.addWidget(filter_view)

        # sound player
        player = SoundPlayer(name=name + '.sound_player')
        splitter.addWidget(player)

        # signal log view
        signal_log_view = SignalLogView(name=name + '.signal_log_view')
        # lo.addWidget(signal_log)
        splitter.addWidget(signal_log_view)

        # signal slot
        GlobalSignal().update_prices.connect(self.update_prices)

        # style sheet
        self.setStyleSheet('QSplitter::handle{background: white;}')
        return

    def closeEvent(self, e: QCloseEvent):
        GlobalSignal().dump_config.emit()
        config = Config()
        if config['auto_save']:
            yamlutil.save_yaml(dict(config), config['config_file'])
        e.accept()

    @pyqtSlot(list)
    def update_prices(self, prices: List[dict]):
        instruments = set()
        services = set()
        for x in prices:
            instruments.add(x['instrument'])
            services.add(x['service'])
        config = Config()
        if instruments.difference(config.instruments):
            config.instruments.update(instruments)
            config.update_instruments()
        if services.difference(config.services):
            config.services.update(services)
            config.update_services()


class CSVLogger(QObject):
    def __init__(self, *, spread_log: str = None, signal_log: str = None):
        super().__init__()
        self.spread_log = spread_log
        self.signal_log = signal_log
        if spread_log:
            GlobalSignal().update_spreads.connect(self.update_spreads)
        if signal_log:
            GlobalSignal().update_signals.connect(self.update_signals)

    @pyqtSlot(list)
    def update_signals(self, signals: List[dict]):
        self.write(self.signal_log, signals)

    @pyqtSlot(list)
    def update_spreads(self, spreads: List[dict]):
        self.write(self.spread_log, spreads)

    def write(self, file_name: str, items: List[dict]):
        with open(file_name, 'a') as f:
            w = csv.writer(f)
            for d in items:
                keys = ['time', 'instrument', 'bidder', 'asker', 'bid', 'ask', 'sp']
                d = dict(**d)
                instrument = d['instrument']
                d['bid'] = get_float_format(instrument).format(d['bid'])
                d['ask'] = get_float_format(instrument).format(d['ask'])
                if isinstance(d['sp'], float):
                    d['sp'] = '{:.2f}'.format(d['sp'])
                values = [d[k] for k in keys]
                w.writerow(values)


class AppMaster(Master):
    def __init__(self, bind_address: Tuple[str, int]):
        super().__init__(name='appmaster', bind_address=bind_address)
        config = Config()

        self.window = AppWindow(name='appwindow')

        GlobalSignal().load_config.emit()
        GlobalSignal().call_lazy()

        self.window.show()
        self.pools = {}  # type: Dict[str, Pool]

        self.elapsed_list = []
        self.request_elapsed_list = []

        self.account_task = gevent.spawn(self.get_accounts)

    def __getattr__(self, item):
        return getattr(self.window, item)

    def run_loop(self):
        for key in self.get_registered().items():
            if key not in self.pools:
                pool = serviceclient.get_pool(*key)
                if pool:
                    self.pools[key] = pool
        for key in list(self.pools.keys()):
            if key[0] not in self.registered:
                del self.pools[key]

        self.get_prices()

    def get_accounts(self):
        import time
        next_refresh = time.time() + random.random() * 3600
        while True:
            #GlobalSignal().update_accounts.emit([])
            #gevent.sleep(10)
            #continue

            try:
                accounts = []

                do_refresh = False
                if time.time() >= next_refresh:
                    next_refresh = time.time() + random.random() * 3600
                    do_refresh = True

                def extend_accounts(_pool: Pool):
                    with _pool.connection() as client:
                        l = client.get_accounts() or []
                    accounts.extend(l)

                spawns = {key: gevent.spawn(lambda _pool: extend_accounts(_pool), pool)
                          for key, pool in random.sample(list(self.pools.items()), len(self.pools))}

                gevent.joinall(list(spawns.values()), timeout=1)
                is_timeout = False
                for key, spawn in spawns.items():
                    if not spawn.successful():
                        is_timeout = True
                        try:
                            del self.pools[key]
                        except KeyError:
                            pass
                        try:
                            del self.registered[key[0]]
                        except KeyError:
                            pass
                if accounts:
                    GlobalSignal().update_accounts.emit(accounts)
            except Exception as e:
                self.logger.exception(str(e))
            gevent.sleep(1)

    def get_prices(self):
        now = timeutil.jst_now()

        def extend_prices(_pool: Pool):
            with _pool.connection() as client:
                l = client.get_prices() or []
            for x in l:
                x['time'] = now
            prices.extend(l)

        prices = []
        spawns = {key: gevent.spawn(lambda _pool: extend_prices(_pool), pool)
                  for key, pool in random.sample(list(self.pools.items()), len(self.pools))}

        gevent.joinall(list(spawns.values()), timeout=1)
        is_timeout = False
        for key, spawn in spawns.items():
            if not spawn.successful():
                is_timeout = True
                try:
                    del self.pools[key]
                except KeyError:
                    pass
                try:
                    del self.registered[key[0]]
                except KeyError:
                    pass

        elapsed = timeutil.jst_now() - now
        self.request_elapsed_list.append(elapsed)
        if prices:
            GlobalSignal().update_prices.emit(prices)
        elapsed = timeutil.jst_now() - now
        self.elapsed_list.append(elapsed)
        N = 10
        if len(self.elapsed_list) >= N:
            request_total = sum(map(lambda x: x.total_seconds(), self.request_elapsed_list))
            total = sum(map(lambda x: x.total_seconds(), self.elapsed_list))
            self.logger.info('# elapsed:{:.3f}, request:{:.3f}({:.2f}%), 1loop: {:.3f}, request:{:.3f}'.format(
                total, request_total, request_total / total * 100, total / N, request_total / N))
            self.elapsed_list = []
            self.request_elapsed_list = []
        if is_timeout:
            self.logger.warn('#timeout sleep(3)')
            gevent.sleep(3)
        else:
            gevent.sleep(max((timedelta(milliseconds=200) - elapsed).total_seconds(), 0.05))


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT    [default: 127.0.0.1:10000]
      --config FILE  [default: ./appconfig.yaml]
      --not-auto-save
      --exit TIME  [default: 0500]
      --signal-log FILE
      --spread-log FILE
    """.format(f=sys.argv[0]))

    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))
    config_file = args['--config']
    auto_save = not bool(args['--not-auto-save'])
    exit_time = args['--exit']
    exit_hour, exit_minute = int(exit_time[:-2]), int(exit_time[-2:])
    signal_log = args['--signal-log']
    spread_log = args['--spread-log']

    app = QApplication([])

    _ = CSVLogger(spread_log=spread_log, signal_log=signal_log)

    config = Config()
    config.update(yamlutil.load_yaml(config_file, default={}))
    config['auto_save'] = auto_save
    config.setdefault('config_file', config_file)
    master = AppMaster(bind_address=bind_address)
    gevent.spawn(master.start)

    # on posix, supply prices
    def update_prices():
        services = {'click', 'gaitame', 'lion', 'pfx', 'nano', 'sbi', 'try', 'yjfx', 'noaccount'}
        instruments = ('USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY')
        prices = []
        accounts = []
        for service in services:
            positions = {}
            for i, instrument in enumerate(instruments):
                bid = 100 + i + random.random() * 0.8 / 100
                ask = 100 + i + random.random() * 0.2 / 100
                prices.append(dict(time=timeutil.jst_now(), service=service, instrument=instrument, bid=bid, ask=ask))
                positions[instrument] = random.randint(0, 3) * 1000 - 1000
            if service != 'noaccount':
                accounts += [new_account(service, positions=positions)]
        GlobalSignal().update_prices.emit(prices)
        GlobalSignal().update_accounts.emit(accounts)

    if env.is_posix():
        prices_timer = QTimer()
        prices_timer.timeout.connect(update_prices)
        prices_timer.start(500)

    idle_timer = QTimer()
    idle_timer.timeout.connect(lambda: gevent.sleep(0.02))
    idle_timer.start(0)

    def exit_at():
        now = timeutil.jst_now()
        if now.hour == exit_hour and (exit_minute <= now.minute):
            sys.exit(0)

    exit_timer = QTimer()
    exit_timer.timeout.connect(exit_at)
    exit_timer.start(1000 * 10)

    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
