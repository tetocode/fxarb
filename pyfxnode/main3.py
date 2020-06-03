import copy
import csv
import itertools
import logging
import random
import socket
import statistics
import sys
import threading
from collections import OrderedDict
from collections import defaultdict
from datetime import timedelta, datetime
from typing import List, Tuple, Union, Optional, Dict

import gevent
import pytz
from PyQt5.QtCore import *
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import *
from docopt import docopt
from gevent import monkey as _monkey
from gsocketpool.pool import Pool
from pyfx.hubnode import HubNode

import env
import serviceclient
import timeutil
import yamlutil
from globalsignal import GlobalSignal
from model import Config, ConfigurableMixin
from qt5util import TableView, Splitter, DoubleSpinBox
from rpcmixin import new_account

_monkey.patch_all()


class InstrumentComboBox(ConfigurableMixin, QComboBox):
    DEFAULT_INSTRUMENTS = (
        '', 'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'EUR/USD', 'GBP/USD', 'AUD/USD', 'TRY/JPY', 'ZAR/JPY', '')

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
    class RateView(TableView):
        def __init__(self, *, name: str):
            labels = ['bid_amount', 'bidder', 'bid', 'sp', 'ask', 'asker', 'ask_amount']
            super().__init__(labels=labels, name=name)
            self.setContentsMargins(0, 0, 0, 0)
            self.instrument = ''
            self.row_unmatch = 0
            self.setHorizontalHeaderLabels([''] * len(self.labels))
            font = self.horizontalHeader().font()
            font.setPointSize(1)
            self.horizontalHeader().setFont(font)
            self.verticalHeader().hide()
            GlobalSignal().update_prices.connect(self.update_prices)

        @pyqtSlot(str)
        def update_instrument(self, instrument: str):
            self.instrument = instrument

        @pyqtSlot(list)
        def update_prices(self, prices: List[dict] = ()):
            prices = list(filter(lambda x: x['instrument'] == self.instrument, prices))
            config = Config()
            disabled = set()  # config.disabled_services
            account_positions = defaultdict(lambda: defaultdict(int))
            for service, account in config.accounts.items():
                for instrument, amount in account['positions'].items():
                    account_positions[service][instrument] = amount
            pip_scale = get_pip_scale(self.instrument)

            bids = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: -x['bid']))
            asks = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: x['ask']))
            row_n = max(len(bids), len(asks)) * 2 - 1 + 1
            if self.rowCount() != row_n:
                if self.rowCount() > row_n:
                    self.row_unmatch += 1
                    print('#row_unmatch:', list(sorted(map(lambda x: x['service'], bids))))
                    if self.row_unmatch >= 10:
                        self.resize_row(row_n)
                else:
                    self.resize_row(row_n)
                    self.row_unmatch = 0
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
            bid_amount = 0
            ask_amount = 0
            # set bids
            for i, d in enumerate(bids[:rank]):
                bid = d['bid']
                sp = (min_ask - bid) * pip_scale
                bg = QBrush(Qt.green) if sp < 0 else None
                self.set_item(center + i, 'sp', '{:.2f}'.format(sp), bg=bg)
                amount = get_amount(service=d['service'], instrument=self.instrument)
                bg = QBrush(Qt.green) if amount > 0 else None
                self.set_item(center + i, 'bidder', d['service'], bg=bg)
                self.set_item(center + i, 'bid', float_format.format(bid))
                amount = account_positions[d['service']][self.instrument]
                if amount and amount != 0:
                    self.set_item(center + i, 'bid_amount', '{:,d}'.format(int(amount)), bg=bg)
                    bid_amount += amount
            # set asks
            for i, d in enumerate(asks[:rank]):
                ask = d['ask']
                sp = (ask - max_bid) * pip_scale
                bg = QBrush(Qt.green) if sp < 0 else None
                self.set_item(center - i, 'sp', '{:.2f}'.format(sp), bg=bg)
                amount = get_amount(service=d['service'], instrument=self.instrument)
                bg = QBrush(Qt.green) if amount < 0 else None
                self.set_item(center - i, 'asker', d['service'], bg=bg)
                self.set_item(center - i, 'ask', float_format.format(ask))
                amount = account_positions[d['service']][self.instrument]
                if amount and amount != 0:
                    self.set_item(center - i, 'ask_amount', '{:,d}'.format(int(amount)), bg=bg)
                    ask_amount += amount
            self.set_item(row_n - 1, 'bid_amount', '{:,d}'.format(int(bid_amount)))
            self.set_item(row_n - 1, 'ask_amount', '{:,d}'.format(int(ask_amount)))

    @pyqtSlot(str)
    def select_instrument(self, instrument: str):
        self.instrument = instrument
        fltr = Config().filters.setdefault(instrument, {})
        self.open_spread_spin.setValue(fltr.get('open_spread', 1.0))
        self.close_spread_spin.setValue(fltr.get('close_spread', 0.5))
        self.open_duration_spin.setValue(fltr.get('open_duration', 2.0))
        self.close_duration_spin.setValue(fltr.get('close_duration', 2.0))
        self.rate_view.update_instrument(instrument)

    @pyqtSlot(float)
    def update_open_spread(self, value: float):
        fltr = Config().filters.setdefault(self.instrument, {})
        fltr['open_spread'] = value

    @pyqtSlot(float)
    def update_close_spread(self, value: float):
        fltr = Config().filters.setdefault(self.instrument, {})
        fltr['close_spread'] = value

    @pyqtSlot(float)
    def update_open_duration(self, value: float):
        fltr = Config().filters.setdefault(self.instrument, {})
        fltr['open_duration'] = value

    @pyqtSlot(float)
    def update_close_duration(self, value: float):
        fltr = Config().filters.setdefault(self.instrument, {})
        fltr['close_duration'] = value

    def __init__(self, *, name: str):
        super().__init__(name=name)

        self.instrument = ''

        self.setContentsMargins(0, 0, 0, 0)

        instrument_combo = InstrumentComboBox(name=name + '.instrument_combo')
        instrument_combo.setContentsMargins(0, 0, 0, 0)
        open_spread_spin = DoubleSpinBox(value=1.0, min=0.0, max=9.99, decimals=2, single_step=0.01, suffix=' pips',
                                         name=name + '.open_spread')
        close_spread_spin = DoubleSpinBox(value=0.5, min=0.0, max=9.99, decimals=2, single_step=0.01, suffix=' pips',
                                          name=name + '.close_spread')
        open_duration_spin = DoubleSpinBox(value=2.0, min=0.0, max=9.99, decimals=1, single_step=0.1, suffix=' s',
                                           name=name + '.open_duration')
        close_duration_spin = DoubleSpinBox(value=2.0, min=0.0, max=9.99, decimals=1, single_step=0.1, suffix=' s',
                                            name=name + '.close_duration')
        rate_view = self.RateView(name=name + '.rate_view')
        rate_view.setContentsMargins(0, 0, 0, 0)

        # signal slot connect
        instrument_combo.activated[str].connect(self.select_instrument)
        open_spread_spin.valueChanged.connect(self.update_open_spread)
        open_duration_spin.valueChanged.connect(self.update_open_duration)
        close_duration_spin.valueChanged.connect(self.update_close_duration)
        close_spread_spin.valueChanged.connect(self.update_close_spread)

        # layout
        lo = QGridLayout()
        lo.setSpacing(0)
        lo.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lo)

        lo.addWidget(instrument_combo, 1, 0)
        lo.addWidget(open_spread_spin, 1, 1)
        lo.addWidget(open_duration_spin, 1, 2)
        lo.addWidget(close_spread_spin, 1, 3)
        lo.addWidget(close_duration_spin, 1, 4)
        lo.addWidget(rate_view, 2, 0, 1, 5)
        lo.setRowStretch(2, 1)

        self.instrument_combo = instrument_combo
        self.open_spread_spin = open_spread_spin
        self.close_spread_spin = close_spread_spin
        self.open_duration_spin = open_duration_spin
        self.close_duration_spin = close_duration_spin
        self.rate_view = rate_view


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
        mute = QCheckBox('M')
        mute.setChecked(self.config.setdefault('mute', False))
        check = QCheckBox('C')
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
        bid_positions = defaultdict(int, **config.accounts.get(b, {}).get('positions', {}))
        ask_positions = defaultdict(int, **config.accounts.get(a, {}).get('positions', {}))
        if bid_positions[instrument] <= 0 or ask_positions[instrument] >= 0:
            sp_threshold = config.filters.get(instrument, {}).get('open_spread', 3.0)
            duration_threshold = timedelta(seconds=config.filters.get(instrument, {}).get('open_duration', 4.0))
        else:
            sp_threshold = config.filters.get(instrument, {}).get('close_spread', 3.0)
            duration_threshold = timedelta(seconds=config.filters.get(instrument, {}).get('close_duration', 4.0))

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
                    sp_min = statistics.median(sp_list)  # min(sp_list)
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
        labels = ['signaled_time', 'instrument', 'bidder', 'bid', 'asker', 'ask', 'sp']
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
        selected = Config().selected_instruments
        disabled = Config().disabled_services
        for signal in signals:
            b, a = signal['bidder'], signal['asker']
            instrument = signal['instrument']
            # if instrument not in selected or b in disabled or a in disabled:
            if b in disabled or a in disabled:
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
            # return x['instrument'] in selected and x['bidder'] not in disabled and x['asker'] not in disabled
            return x['bidder'] not in disabled and x['asker'] not in disabled

        signals = list(filter(is_valid, reversed(self.signals)))[:self.MAX_ROW_N]

        self.resize_row(min(self.MAX_ROW_N, len(signals)))
        for row, signal in enumerate(signals):
            flags = None
            b, a = signal['bidder'], signal['asker']
            if b in disabled or a in disabled:
                flags = Qt.NoItemFlags
            signal = signal.copy()
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
                        d['signaled_time'] = d['time'].astimezone(timeutil.TOKYO).strftime('%Y-%m-%d %H:%M:%S%Z')
                        d['sp'] = '{:.2f}'.format(d['sp'])
                        signals.append(d)
        GlobalSignal().update_signals.emit(signals)
        GlobalSignal().update_spreads.emit(spreads)


class AccountsView(TableView):
    def __init__(self, name: str):
        labels = ['E', 'service', 'equity', 'pl', 'margin_ratio', 'available']
        super().__init__(labels=labels, name=name)
        self.instrument = ''
        self.bank = 0.0
        self.cellClicked.connect(self.cell_clicked)
        GlobalSignal().update_accounts.connect(self.update_accounts)
        GlobalSignal().update_prices.connect(self.update_prices)
        self.services = set()

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
        self.resize_row(len(self.services) + 1)

        serivce_accounts = {a['service']: a for a in accounts}

        equity_total = 0
        pl_total = 0
        amount_total = 0
        positive_amount_total = 0
        for row, service in enumerate(sorted(self.services)):
            d = serivce_accounts.get(service, new_account(service, equity=-1))
            self.set_item(row, 'E', checked=d['service'] not in disabled,
                          flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            self.set_item(row, 'service', value=d['service'])
            self.set_item(row, 'equity', value='{:,d}'.format(int(d['equity'])))
            equity_total += int(d['equity'])
            self.set_item(row, 'pl', value='{:,d}'.format(int(d['pl'])))
            pl_total += int(d['pl'])
            self.set_item(row, 'margin_ratio', value='{:,.2f} %'.format(d.get('margin_ratio', 0)))
            self.set_item(row, 'available', value='{:,d}'.format(int(d.get('available', 0))))
            # amount = d['positions'].get(self.instrument, 0)
            # self.set_item(row, 'amount', value='{:d} k'.format(int(amount / 1000)))
            # amount_total += int(amount)
            # if amount > 0:
            #    positive_amount_total += int(amount)
            config.accounts.setdefault(d['service'], {}).update(d)
        equity_total += int(self.bank)
        self.set_item(len(self.services), 'equity', value='{:,d}'.format(equity_total))
        self.set_item(len(self.services), 'pl', value='{:,d}'.format(pl_total))
        # self.set_item(len(self.services), 'amount',
        #              value='{:d}({:d}) k'.format(amount_total // 1000, positive_amount_total // 1000))
        return

    @pyqtSlot(float)
    def update_bank(self, value: float):
        self.bank = value


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
        for i in range(3):
            filter_view = FilterView(name=name + '.filter_view_{}'.format(i))
            splitter.addWidget(filter_view)

        # accounts view
        accounts_view = AccountsView(name=name + '.accounts_view')
        splitter.addWidget(accounts_view)

        w = QWidget()
        splitter.addWidget(w)

        # spread intrval
        def update_interval(value: float):
            Config()['interval'] = value

        spread_interval = DoubleSpinBox(name='spread_interval',
                                        value=0.5,
                                        min=0.01, max=3.0, decimals=2, single_step=0.01)
        spread_interval.valueChanged.connect(update_interval)

        # bank view
        bank = DoubleSpinBox(name='tobank', value=0.0, min=-10000000, max=10000000, decimals=0, single_step=1000)
        bank.valueChanged.connect(accounts_view.update_bank)

        # reload button
        reload_button = QPushButton('Reload')
        reload_button.clicked.connect(lambda: GlobalSignal().reload.emit())

        # refresh button
        refresh_button = QPushButton('Refresh')
        refresh_button.clicked.connect(lambda: GlobalSignal().refresh.emit())

        lo = QHBoxLayout()
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(reload_button)
        lo.addWidget(refresh_button)
        lo.addWidget(bank)
        lo.addWidget(spread_interval)
        w.setLayout(lo)

        # sound player
        player = SoundPlayer(name=name + '.sound_player')
        # splitter.addWidget(player)
        lo.addWidget(player)

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


def modify_buf_size(sock, send_buf_size, recv_buf_size):
    # バッファサイズの変更
    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_SNDBUF,
        send_buf_size)
    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_RCVBUF,
        recv_buf_size)
    bufsize = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
    print('SEND Buffer size [After]:%d' % bufsize)
    bufsize = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
    print('RECV Buffer size [After]:%d' % bufsize)


class AppMaster(HubNode):
    def __init__(self, name, nodes):
        super().__init__(name, bind_address=nodes[name], nodes=nodes)
        self.config = Config()

        self.window = AppWindow(name='appwindow')

        GlobalSignal().load_config.emit()
        GlobalSignal().call_lazy()

        self.window.show()
        self.pools = {}  # type: Dict[str, Pool]

        self.elapsed_list = []
        self.request_elapsed_list = []

        self.do_reload = False
        self.do_refresh = False

        def on_reload():
            self.do_reload = True

        def on_refresh():
            def call():
                self.info('refresh start')
                for name, address in self._nodes.items():
                    if name == self.name:
                        continue
                    try:
                        self.info('refresh {}{}'.format(name, address))
                        self.rpc(address).refresh()
                    except Exception as e:
                        self.exception('refresh {}{} {}'.format(name, address, str(e)))

            threading.Thread(target=call, daemon=True).start()
            self.do_refresh = True

        GlobalSignal().reload.connect(on_reload)
        GlobalSignal().refresh.connect(on_refresh)
        import time
        self._last_tick = time.time()
        self._accounts = {}
        self._setsock = False
        self.run_notify_nodes = lambda: None

        def write_csv(file_name: str, flush_interval: float):
            now = datetime.now().date()
            with open(file_name + now.strftime('_%Y%m%d'), 'a') as f:
                w = csv.writer(f)
                flush_at = time.time()
                while True:
                    d = yield
                    if d:
                        keys = ['time', 'instrument', 'bidder', 'asker', 'bid', 'ask', 'sp']
                        d = dict(**d)
                        instrument = d['instrument']
                        d['time'] = d['time'].astimezone(timeutil.TOKYO)
                        d['bid'] = get_float_format(instrument).format(d['bid'])
                        d['ask'] = get_float_format(instrument).format(d['ask'])
                        if isinstance(d['sp'], float):
                            d['sp'] = '{:.2f}'.format(d['sp'])
                        values = [d[k] for k in keys]
                        w.writerow(values)
                    if time.time() - flush_at >= flush_interval:
                        f.flush()
                        flush_at = time.time()

        self.csv_writer = write_csv('./spread_log.csv', 10.0)
        self.csv_writer.send(None)
        self.last_spread_at = timeutil.jst_now()

    def __getattr__(self, item):
        return getattr(self.window, item)

    def handle_udp(self, data, address: Tuple[str, int]):
        if not self._setsock:
            modify_buf_size(self._udp_server._socket, 0x10000, 1024 ** 2 * 4)
            self._setsock = True
        assert isinstance(data, dict), '{}'.format(data)
        self.handle(**data)

        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        minus_spreads = []
        for (bidder, asker), instrument_spreads in self.spreads.items():
            for instrument, spreads in instrument_spreads.items():
                if spreads[-1].time > self.last_spread_at and get_pip_scale(spreads[-1].instrument) * (
                        - spreads[-1].sp) < -0.25:
                    minus_spreads.append(spreads[-1])
        self.last_spread_at = now
        for s in minus_spreads:
            d = dict(bidder=s.pair[0], asker=s.pair[1], instrument=s.instrument, time=s.time, bid=s.bid, ask=s.ask,
                     sp=get_pip_scale(s.instrument) * (-s.sp))
            self.csv_writer.send(d)

        import time
        if time.time() - self._last_tick <= self.config['interval']:
            return
        self._last_tick = time.time()

        if not minus_spreads:
            self.csv_writer.send(None)

        if 'accounts' in data:
            accounts = [account.to_dict() for account in self.accounts.values()]
            for account in accounts:
                account['service'] = account['name']
                account['pl'] = account['profit_loss']
                account['available'] = account['equity'] - account['used_margin']
                account['margin_ratio'] = (account['equity'] / account['used_margin']) * 100 if account[
                                                                                                    'used_margin'] > 0 else 0
            for account in accounts:
                self._accounts[account['name']] = account
            GlobalSignal().update_accounts.emit(list(self._accounts.values()))

        if 'prices' in data:
            _prices = []
            for service, instrument_prices in self.prices.items():
                for instrument, prices in instrument_prices.items():
                    if len(prices) > 0:
                        _prices.append(prices[-1].to_dict())
            [price.update(service=price['name']) for price in _prices]
            _prices = list(filter(lambda x: (now - x['time']).total_seconds() < 5, _prices))
            #
            #             print('#prices')
            GlobalSignal().update_prices.emit(_prices)
            # self.publish(data)

    def run_loop(self):
        return
        for key in self.get_registered().items():
            if key not in self.pools:
                pool = serviceclient.get_pool(*key)
                if pool:
                    self.pools[key] = pool
        # for key in list(self.pools.keys()):
        #    if key[0] not in self.registered:
        #        del self.pools[key]

        kvs = list(self.get_registered().items())
        for key in list(self.pools.keys()):
            if key not in kvs:
                del self.pools[key]

        self.get_prices()


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
    config.setdefault('interval', 0.5)
    master = AppMaster('@hub', nodes={'@hub': bind_address})
    gevent.spawn(master.start)

    # on posix, supply prices
    def update_prices():
        services = ['click', 'gaitame', 'lion', 'pfx', 'nano', 'sbi', 'try', 'yjfx', 'noaccount']
        instruments = ('USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY')
        prices = []
        accounts = []
        for service in services:
            positions = {}
            for i, instrument in enumerate(instruments):
                bid = 101 + i + random.random() * 0.8 / 100
                ask = 100 + i + random.random() * 0.2 / 100
                prices.append(dict(time=timeutil.jst_now(), service=service, instrument=instrument, bid=bid, ask=ask))
                if services.index(service) < len(services) / 2:
                    positions[instrument] = random.randint(0, 3) * 1000
                else:
                    positions[instrument] = random.randint(0, 3) * - 1000
            if service != 'noaccount':
                accounts += [new_account(service, positions=positions)]
        GlobalSignal().update_prices.emit(prices)
        GlobalSignal().update_accounts.emit(accounts)

    if env.is_posix() and False:
        prices_timer = QTimer()
        prices_timer.timeout.connect(update_prices)
        prices_timer.start(500)

    idle_timer = QTimer()
    idle_timer.timeout.connect(lambda: gevent.sleep(0.02))
    idle_timer.start(0)

    def exit_at():
        now = timeutil.jst_now()
        if now.hour == exit_hour and (exit_minute <= now.minute):
            pass
            # sys.exit(0)

    exit_timer = QTimer()
    exit_timer.timeout.connect(exit_at)
    exit_timer.start(1000 * 10)

    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
