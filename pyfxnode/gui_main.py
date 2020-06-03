import contextlib
import copy
import itertools
import logging
import random
import socket
import sys
import threading
import time
from collections import OrderedDict, defaultdict, deque
from datetime import timedelta
from queue import Queue
from typing import Tuple, Dict, Type, Sequence, Any, List, Union, Set, Optional, DefaultDict

import yaml
from PyQt5 import Qt
from PyQt5.QtCore import *
from PyQt5.QtGui import QCloseEvent, QBrush
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import *
from docopt import docopt

from pyfxnode.account import Account
from pyfxnode.datanode import DataNode
from pyfxnode.dummyserver import DummyServer
from pyfxnode.hubnode import HubNode
from pyfxnode.price import Price
from pyfxnode.utils import unpack_from_bytes, jst_now_aware, JST


class DoubleSpinBoxUI(QDoubleSpinBox):
    def __init__(self, *,
                 value: float = None, min: float = None, max: float = None, decimals: int = None,
                 single_step: float = None, suffix: str = None):
        super().__init__()
        if value is not None:
            self.setValue(value)
        if min is not None:
            self.setMinimum(min)
        if max is not None:
            self.setMaximum(max)
        if decimals is not None:
            self.setDecimals(decimals)
        if single_step is not None:
            self.setSingleStep(single_step)
        if suffix is not None:
            self.setSuffix(suffix)


class ComboBoxUI(QComboBox):
    def __init__(self, items: Sequence[str]):
        super().__init__()

        for item in items:
            self.addItem(item)


def get_pip_scale(instrument: str) -> int:
    if 'JPY' in instrument.upper():
        return 100
    else:
        return 10000


def get_float_format(instrument: str) -> str:
    if 'JPY' in instrument.upper():
        return '{:.4f}'
    return '{:.6f}'


class TableUI(QTableWidget):
    FONT_P = 8
    ROW_H = 14

    def __init__(self, header: Sequence[str]):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.setColumnCount(len(header))
        self.setHorizontalHeaderLabels(header)
        self.header = header

        # set font
        font = self.font()
        font.setPointSize(self.FONT_P)
        self.setFont(font)
        font = self.verticalHeader().font()
        font.setPointSize(self.FONT_P - 2)
        self.verticalHeader().setFont(font)

    def set_data(self, rows: Sequence[Union[List[Any], Dict[str, Any]]]):
        row_n = len(rows)
        current_row_n = self.rowCount()
        if current_row_n != row_n:
            self.setRowCount(0)
        self.setRowCount(row_n)
        for row in range(row_n):
            self.setRowHeight(row, self.ROW_H)

        data_set = []  # type: List[Tuple[int, int, dict]]
        for i, row in enumerate(rows):
            if isinstance(row, dict):
                for k, v in row.items():
                    j = self.header.index(k)
                    if not isinstance(v, dict):
                        v = {'value': v}
                    data_set.append((i, j, v))
            else:
                assert isinstance(row, (list, tuple))
                for j, v in enumerate(row):
                    if not isinstance(v, dict):
                        v = {'value': v}
                    data_set.append((i, j, v))
        for i, j, v in data_set:
            r = self.set_cell(i, j, **v)

    def set_cell(self, row: int, col: int, value=None, bg=None, flags=None, checked=None, widget=None):
        if row >= self.rowCount() or col >= self.columnCount():
            return False
        if not self.item(row, col):
            self.setItem(row, col, QTableWidgetItem())

        flags = flags if flags is not None else Qt.ItemIsEnabled
        self.item(row, col).setData(Qt.BackgroundRole, bg)
        self.item(row, col).setData(Qt.DisplayRole, value)
        self.item(row, col).setFlags(flags)
        if checked is not None:
            self.item(row, col).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        if widget is not None:
            self.setCellWidget(row, col, widget)
        return True


class PriceUI(QWidget):
    DEFAULT_INSTRUMENTS = ('USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'EUR/USD', 'GBP/USD', 'AUD/USD')

    def __init__(self, prefix: str, config: DefaultDict[str, dict]):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self.config = config

        checkbox = GUINode.new_object('{}.{}'.format(prefix, 'check'), QCheckBox)  # type: QCheckBox

        def clicked(checked: bool):
            config[self.instrument]['checked'] = checked

        checkbox.clicked.connect(clicked)

        instruments = GUINode.new_object('{}.{}'.format(prefix, 'instruments'), ComboBoxUI, self.DEFAULT_INSTRUMENTS)
        instruments.setContentsMargins(0, 0, 0, 0)

        open_spread_spin = GUINode.new_object(
            '{}.{}'.format(prefix, 'open_spread_spin'),
            DoubleSpinBoxUI,
            value=1.0, min=0.0, max=9.99, decimals=2, single_step=0.01, suffix=' pips')
        close_spread_spin = GUINode.new_object(
            '{}.{}'.format(prefix, 'close_spread_spin'),
            DoubleSpinBoxUI,
            value=0.4, min=0.0, max=9.99, decimals=2, single_step=0.01, suffix=' pips')
        open_period_spin = GUINode.new_object(
            '{}.{}'.format(prefix, 'open_period_spin'),
            DoubleSpinBoxUI,
            value=2.0, min=0.0, max=9.99, decimals=1, single_step=0.1, suffix=' s')
        close_period_spin = GUINode.new_object(
            '{}.{}'.format(prefix, 'close_period_spin'),
            DoubleSpinBoxUI,
            value=1.0, min=0.0, max=9.99, decimals=1, single_step=0.1, suffix=' s')

        def change_instrument(instrument: str):
            try:
                params = config[instrument]
                checkbox.setChecked(params['checked'])
                close_spread_spin.setValue(params['close_spread'])
                open_spread_spin.setValue(params['open_spread'])
                open_period_spin.setValue(params['open_period'])
                close_period_spin.setValue(params['close_period'])
            except KeyError as e:
                logging.exception(str(e))
                pass

        def change_value_func(k: str, spin: DoubleSpinBoxUI):
            def change_value(_: float):
                params = config[instruments.currentText()]
                params[k] = spin.value()

            return change_value

        instruments.activated[str].connect(change_instrument)
        open_spread_spin.valueChanged.connect(change_value_func('open_spread', open_spread_spin))
        close_spread_spin.valueChanged.connect(change_value_func('close_spread', close_spread_spin))
        open_period_spin.valueChanged.connect(change_value_func('open_period', open_period_spin))
        close_period_spin.valueChanged.connect(change_value_func('close_period', close_period_spin))

        price_table = GUINode.new_object('{}.{}'.format(prefix, 'price'), TableUI,
                                         ['bid_qty', 'bidder', 'bid', 'sp', 'ask', 'asker', 'ask_qty'])
        price_table.verticalHeader().hide()
        font = price_table.horizontalHeader().font()
        font.setPointSize(2)
        price_table.horizontalHeader().setFont(font)
        price_table.setHorizontalHeaderLabels([''] * len(price_table.header))

        # layout
        lo = QGridLayout()
        lo.setSpacing(0)
        lo.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lo)

        checkbox.setContentsMargins(0, 0, 0, 0)
        checkbox.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        lo.addWidget(checkbox, 1, 0)
        lo.addWidget(instruments, 1, 1)
        lo.addWidget(open_spread_spin, 1, 2)
        lo.addWidget(open_period_spin, 1, 3)
        lo.addWidget(close_spread_spin, 1, 4)
        lo.addWidget(close_period_spin, 1, 5)
        lo.addWidget(price_table, 2, 0, 1, 6)
        lo.setRowStretch(2, 1)

        self.instruments = instruments
        self.open_spread_spin = open_spread_spin
        self.close_spread_spin = close_spread_spin
        self.open_period_spin = open_period_spin
        self.close_period_spin = close_period_spin
        self.price_table = price_table

        price_table.cellClicked.connect(self.cell_clicked)

    @property
    def instrument(self) -> str:
        return self.instruments.currentText()

    def check_enabled(self, name: str):
        return self.config[self.instrument][name]

    @pyqtSlot(int, int)
    def cell_clicked(self, row: int, col: int):
        item = self.price_table.item(row, col)
        flags = item.flags()
        if not (flags & Qt.ItemIsUserCheckable):
            return
        checked = item.checkState()
        name = item.text()
        checked = checked == Qt.Checked
        self.config[self.instrument][name] = checked
        logging.info('instrument={} name={} checked={}'.format(self.instrument, name, checked))

    def on_data(self, data: dict):
        accounts = data.get('accounts', {})
        instrument = self.instruments.currentText()
        prices = []
        for name, instrument_prices in data.get('prices', {}).items():
            if instrument in instrument_prices:
                prices.append(instrument_prices[instrument])

        if not prices:
            self.price_table.set_data([])
            return

        bid_prices = list(sorted(prices, key=lambda x: -x.bid))
        bid_max = bid_prices[0].bid
        ask_prices = list(sorted(prices, key=lambda x: -x.ask))
        ask_min = ask_prices[-1].ask
        bid_padding = [None] * (len(ask_prices) - 1)
        ask_padding = [None] * (len(bid_prices) - 1)
        bid_qty_total = 0
        ask_qty_total = 0
        rows = []
        for bid_price, ask_price in zip(bid_padding + bid_prices, ask_prices + ask_padding):
            bidder = bid_price.name if bid_price else ''
            asker = ask_price.name if ask_price else ''
            bid_qty = 0
            if bidder in accounts:
                bid_qty = accounts[bidder].positions.get(instrument, 0)
            ask_qty = 0
            if asker in accounts:
                ask_qty = accounts[asker].positions.get(instrument, 0)
            if bid_price is None:
                sp = ask_price.ask - bid_max
            elif ask_price is None:
                sp = ask_min - bid_price.bid
            else:
                sp = ask_price.ask - bid_price.bid
            bid_qty_total += bid_qty
            ask_qty_total += ask_qty
            rows.append({
                'bid_qty': {
                    'value': format_num(bid_qty) if bid_qty else '',
                    'bg': QBrush(Qt.green) if bid_qty and bid_qty > 0 else None,
                },
                'bidder': {
                    'value': bidder,
                    'checked': self.config[self.instrument].get(bidder, False) if bidder else None,
                    'flags': (Qt.ItemIsEnabled | Qt.ItemIsUserCheckable) if bidder else Qt.ItemIsEnabled,
                },
                'bid': format_price(instrument, bid_price.bid) if bid_price else '',
                'sp': {
                    'value': format_sp(sp * get_pip_scale(instrument)),
                    'bg': QBrush(Qt.green) if sp < 0 else None,
                },
                'ask': format_price(instrument, ask_price.ask) if ask_price else '',
                'asker': {
                    'value': asker,
                    'checked': self.config[self.instrument].get(asker, False) if asker else None,
                    'flags': (Qt.ItemIsEnabled | Qt.ItemIsUserCheckable) if asker else Qt.ItemIsEnabled,
                },
                'ask_qty': {
                    'value': format_num(ask_qty) if ask_qty else '',
                    'bg': QBrush(Qt.green) if ask_qty and ask_qty < 0 else None,
                }
            })
        rows.append({
            'bid_qty': format_num(bid_qty_total),
            'ask_qty': format_num(ask_qty_total),
        })
        self.price_table.set_data(rows)
        return


class AccountUI(TableUI):
    def __init__(self, adjust: DoubleSpinBoxUI):
        labels = ['name', 'equity', 'pl', 'margin_ratio', 'available']
        super().__init__(header=labels)
        self.adjust = adjust
        self.cellClicked.connect(self.cell_clicked)
        self._enabled_accounts = set()
        self.verticalHeader().hide()

    @property
    def enabled_accounts(self) -> Set[str]:
        return self._enabled_accounts

    @enabled_accounts.setter
    def enabled_accounts(self, x):
        self._enabled_accounts = x

    @pyqtSlot(int, int)
    def cell_clicked(self, row: int, col: int):
        label = self.header[col]  # type: str
        if label not in ('name',):
            return
        checked = self.item(row, col).checkState() == Qt.Checked
        name = self.item(row, self.header.index('name')).data(Qt.DisplayRole)
        if checked:
            self.enabled_accounts.add(name)
        else:
            with contextlib.suppress(KeyError):
                self.enabled_accounts.remove(name)
        logging.info('account {} checked={}  enabled_accounts={}'.format(name, checked, self.enabled_accounts))

    def on_data(self, data: dict):
        accounts = data.get('accounts', {})  # type: Dict[str, Account]
        rows = []
        total = {
            'equity': 0,
            'pl': 0,
        }
        for name, account in sorted(accounts.items(), key=str):
            #         labels = ['E', 'name', 'equity', 'pl', 'margin_ratio', 'available']
            enabled = name in self.enabled_accounts
            equity = account.equity
            pl = account.profit_loss
            margin_ratio = '-'
            if account.used_margin > 0:
                margin_ratio = '{:.1f} %'.format(account.used_margin / account.equity * 100)
            available = '{}'.format(int(account.available_margin))
            row = {
                # 'E': {'checked': enabled, 'flags': Qt.ItemIsEnabled | Qt.ItemIsUserCheckable},
                'name': {
                    'value': name,
                    'checked': enabled,
                    'flags': Qt.ItemIsEnabled | Qt.ItemIsUserCheckable,
                },
                'equity': format_num(equity),
                'pl': format_num(pl),
                'margin_ratio': margin_ratio,
                'available': format_num(available),
            }
            total['equity'] += equity
            total['pl'] += pl
            rows.append(row)
        total['equity'] += self.adjust.value()
        total['equity'] = format_num(total['equity'])
        total['pl'] = format_num(total['pl'])
        rows.append(total)
        self.set_data(rows)


class SoundUI(QWidget):
    def __init__(self):
        super().__init__()
        self.sounds = {
            'signal_open': {
                'file': './signal_open.wav',
                'loop': 1,
            },
            'signal_close': {
                'file': './signal_close.wav',
                'loop': 3,
            },
        }
        self.q_sounds = {}

        self.test_button = QPushButton('Test')
        self.test_button.setContentsMargins(0, 0, 0, 0)
        self.mute_button = GUINode.new_object('sound_mute', QCheckBox, 'M')
        self.close_button = GUINode.new_object('sound_close', QCheckBox, 'C')

        def check_clicked_slot(key):
            @pyqtSlot(bool)
            def check_clicked(b):
                self.config[key] = b

            return check_clicked

        def play():
            print('clicked')
            if not self.close_button.isChecked():
                self.play_open()
            else:
                self.play_close()

        self.test_button.clicked.connect(play)

        lo = QHBoxLayout()
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addStretch()
        lo.addWidget(self.test_button)
        lo.addWidget(self.mute_button)
        lo.addWidget(self.close_button)
        self.setLayout(lo)

    def play_open(self):
        self.play('signal_open')

    def play_close(self):
        self.play('signal_close')

    def play(self, name: str):
        if self.mute_button.isChecked():
            return
        if name == 'signal_open' and self.close_button.isChecked():
            return
        sound = self.sounds.get(name)
        if not sound:
            return
        q = self.q_sounds.get(name)
        if not q:
            self.q_sounds[name] = q = QSound(sound['file'])
        if q.isFinished():
            q.setLoops(sound['loop'])
            q.play()


def format_num(num: float):
    return '{:,d}'.format(int(num))


def format_price(instrument: str, price: float) -> str:
    scale = get_pip_scale(instrument)
    if scale == 100:
        return '{:.4f}'.format(price)
    elif scale == 10000:
        return '{:.6f}'.format(price)
    assert False, scale


def format_sp(sp: float) -> str:
    return '{:.2f}'.format(sp)


class SignalUI(TableUI):
    class SignalChecker:
        NO_SIGNAL_CONFIG_WARNINGS = {}

        def __init__(self, instrument: str, pair: Tuple[str, str], config: DefaultDict[str, dict]):
            self.instrument = instrument
            self.pair = pair
            self.config = config
            self.status = False
            self.sp_history = deque(maxlen=100)
            self.signaled_at = 0

        def update_price(self, x_price: Price, y_price: Price, close_flag: bool) -> Optional[dict]:
            params = self.config[self.instrument]
            try:
                if close_flag:
                    check_spread = params['close_spread']
                    check_period = params['close_period']
                else:
                    check_spread = params['open_spread']
                    check_period = params['open_period']
            except KeyError:
                if not self.NO_SIGNAL_CONFIG_WARNINGS.get(self.instrument):
                    self.NO_SIGNAL_CONFIG_WARNINGS[self.instrument] = True
                    logging.warning('instrument={} no signal config'.format(self.instrument))
                return None

            sp = (x_price.bid - y_price.ask) * get_pip_scale(self.instrument)
            if check_spread > sp:
                self.sp_history.clear()
                return None
            price_time = max(x_price.time, y_price.time)
            now = jst_now_aware()
            if now - price_time >= timedelta(seconds=5):
                self.sp_history.clear()
                return None

            if len(self.sp_history) > 0:
                if self.sp_history[-1]['time'] >= price_time:
                    return None
            self.sp_history.append({
                'time': price_time,
                'sp': sp,
            })
            period = self.sp_history[-1]['time'] - self.sp_history[0]['time']
            if period.total_seconds() >= check_period:
                if time.time() - self.signaled_at >= 10:
                    self.signaled_at = time.time()
                    self.sp_history.clear()
                    return {
                        'time': price_time.astimezone(JST).strftime('%Y%m%d %H:%M:%S JST'),
                        'instrument': self.instrument,
                        'bidder': x_price.name,
                        'bid': format_price(self.instrument, x_price.bid),
                        'asker': y_price.name,
                        'ask': format_price(self.instrument, y_price.ask),
                        'sp': format_sp(-sp),
                    }
            return None

    MAX_ROW_N = 50

    def __init__(self, account_ui: AccountUI, sound_ui: SoundUI, config: DefaultDict[str, dict]):
        labels = ['time', 'instrument', 'bidder', 'bid', 'asker', 'ask', 'sp']
        super().__init__(header=labels)
        font = self.horizontalHeader().font()
        font.setPointSize(5)
        self.horizontalHeader().setFont(font)

        self.account_ui = account_ui
        self.sound_ui = sound_ui
        self.config = config

        self.signal_checkers = {}
        self.trade_signals = deque(maxlen=self.MAX_ROW_N)

    @property
    def enabled_accounts(self) -> Set[str]:
        return self.account_ui.enabled_accounts

    def get_signal_checker(self, instrument: str, pair: Tuple[str, str]) -> SignalChecker:
        key = (instrument, pair)
        if key not in self.signal_checkers:
            self.signal_checkers[key] = self.SignalChecker(instrument, pair, self.config)
        return self.signal_checkers[key]

    def on_data(self, data: dict):
        accounts = data.get('accounts', {})
        instruments = set()
        all_prices = defaultdict(dict)
        for name, instrument_prices in data.get('prices', {}).items():
            for instrument, price in instrument_prices.items():
                instruments.add(instrument)
                all_prices[instrument][name] = price
        for instrument in instruments:
            prices = all_prices[instrument]
            names = tuple(prices.keys())
            for x, y in itertools.permutations(names, 2):
                if x == y:
                    continue
                checker = self.get_signal_checker(instrument, (x, y))

                close_flag = False
                try:
                    if accounts[x].positions[instrument] > 0 > accounts[y].positions[instrument]:
                        close_flag = True
                except KeyError:
                    pass

                trade_signal = checker.update_price(prices[x], prices[y], close_flag)
                if trade_signal:
                    try:
                        if close_flag:
                            self.sound_ui.play_close()
                        elif self.config[instrument].get('checked'):
                            if self.config[instrument].get(x) and self.config[instrument].get(y):
                                if x in self.enabled_accounts and y in self.enabled_accounts:
                                    self.sound_ui.play_open()
                    except KeyError:
                        pass
                    self.update_log(trade_signal, close_flag)

    def update_log(self, trade_signal: dict, close_flag: bool):
        if close_flag:
            trade_signal = {k: {'value': v, 'bg': QBrush(Qt.green)} for k, v in trade_signal.items()}
        self.trade_signals.appendleft(trade_signal)
        self.set_data(self.trade_signals)


class GUINode(DataNode):
    NAME = 'GUI'
    config = defaultdict(dict)
    objects = OrderedDict()  # type: OrderedDict Dict[str, QObject]

    class MainWindow(QMainWindow):
        def __init__(self, on_close, *args):
            super().__init__(*args)
            self.setWindowTitle('PyGUI')
            self._on_close = on_close

        def closeEvent(self, e: QCloseEvent):
            self._on_close()
            e.accept()

    def __init__(self, address: Tuple[str, int], publisher_address: Tuple[str, int], config_path: str):
        super().__init__(self.NAME, address)
        self._publisher_address = socket.gethostbyname(publisher_address[0]), publisher_address[1]
        self._config_path = config_path
        with contextlib.suppress(FileNotFoundError):
            with open(config_path, 'r') as f:
                self.config.update(yaml.load(f))
        self.data_q = Queue()
        self.accounts = {}
        self.prices = defaultdict(dict)

    @classmethod
    def new_object(cls, name: str, obj_type: Type[QObject], *args, **kwargs):
        obj = obj_type(*args, **kwargs)
        obj.setObjectName(name)
        cls.objects[name] = obj
        config = cls.config.get(name)
        if config:
            if isinstance(obj, QWidget):
                if 'pos' in config:
                    obj.move(config['pos'])
                if 'size' in config:
                    obj.resize(config['size'])
            if isinstance(obj, ComboBoxUI):
                if 'text' in config:
                    obj.setCurrentText(config['text'])
            if isinstance(obj, DoubleSpinBoxUI):
                if 'value' in config:
                    obj.setValue(config['value'])
            if isinstance(obj, TableUI):
                if 'column_widths' in config:
                    h_header = obj.horizontalHeader()
                    for i, width in enumerate(config['column_widths']):
                        h_header.resizeSection(i, width)
            if isinstance(obj, QCheckBox):
                if 'checked' in config:
                    obj.setChecked(config['checked'])
            if isinstance(obj, AccountUI):
                if 'enabled_accounts' in config:
                    obj.enabled_accounts = config['enabled_accounts']
            if isinstance(obj, QSplitter):
                if 'sizes' in config:
                    obj.setSizes(config['sizes'])
        return obj

    def on_close(self):
        for name, obj in self.objects.items():
            if isinstance(obj, QWidget):
                self.config[name]['pos'] = obj.pos()
                self.config[name]['size'] = obj.size()
            if isinstance(obj, ComboBoxUI):
                self.config[name]['text'] = obj.currentText()
            if isinstance(obj, DoubleSpinBoxUI):
                self.config[name]['value'] = obj.value()
            if isinstance(obj, TableUI):
                h_header = obj.horizontalHeader()
                widths = [h_header.sectionSize(i) for i in range(h_header.count())]
                self.config[name]['column_widths'] = widths
            if isinstance(obj, QCheckBox):
                self.config[name]['checked'] = obj.isChecked()
            if isinstance(obj, AccountUI):
                self.config[name]['enabled_accounts'] = obj.enabled_accounts
            if isinstance(obj, QSplitter):
                self.config[name]['sizes'] = obj.sizes()
        with open(self._config_path, 'w') as f:
            yaml.dump(self.config, f)

    def refresh(self):
        def refresh_all():
            with self.rpc_connection(self._publisher_address) as conn:
                nodes = conn.request('get_nodes')
                for name, address in nodes.items():
                    address = tuple(address)
                    print(name, address)
                    with self.rpc_connection(address) as node_conn:
                        node_conn.notify('refresh')

        threading.Thread(target=refresh_all, daemon=True).start()

    def reload(self):
        pass

    def subscribe_loop(self):
        while self.is_running():
            try:
                with self.rpc_connection(self._publisher_address) as conn:
                    conn.notify('subscribe', self.name, self.server_address)
            except Exception as e:
                self.exception(str(e))
                time.sleep(10)
            time.sleep(3)

    def start(self):
        super().start()
        threading.Thread(target=self.subscribe_loop, daemon=True).start()

        app = QApplication([])

        main_w = self.new_object('main_window', self.MainWindow, self.on_close)  # type: self.MainWindow

        main_w.setContentsMargins(0, 0, 0, 0)
        splitter = self.new_object('splitter', QSplitter, Qt.Vertical)  # type: QSplitter
        splitter.setContentsMargins(0, 0, 0, 0)
        main_w.setCentralWidget(splitter)

        price_ui_list = []  # type: List[PriceUI]
        for i in range(4):
            prefix = 'price[{}]'.format(i)
            price_ui = self.new_object(prefix, PriceUI, prefix, self.config)
            price_ui.setContentsMargins(0, 0, 0, 0)
            price_ui_list.append(price_ui)
            splitter.addWidget(price_ui_list[i])
        self.price_ui_list = price_ui_list

        update_interval = self.new_object('update_interval', DoubleSpinBoxUI,
                                          value=0.5,
                                          min=0.01, max=10.0, decimals=2, single_step=0.01)

        adjust = self.new_object('adjust', DoubleSpinBoxUI, value=0.0, min=-10000000, max=10000000, decimals=0,
                                 single_step=1000)

        # accounts
        account_ui = self.new_object('account', AccountUI, adjust)  # type: AccountUI
        splitter.addWidget(account_ui)
        self.account_ui = account_ui

        # reload button
        reload_button = QPushButton('Reload')
        reload_button.clicked.connect(self.reload)

        # refresh button
        refresh_button = QPushButton('Refresh')
        refresh_button.clicked.connect(self.refresh)

        lo = QHBoxLayout()
        lo.setContentsMargins(0, 0, 0, 0)
        lo.addWidget(reload_button)
        lo.addWidget(refresh_button)
        lo.addWidget(adjust)
        lo.addWidget(update_interval)
        w = QWidget()
        w.setLayout(lo)
        splitter.addWidget(w)

        # sound player
        sound_player = SoundUI()
        # splitter.addWidget(player)
        lo.addWidget(sound_player)

        # signal log view
        signals = self.new_object('signals', SignalUI, account_ui, sound_player, self.config)
        # lo.addWidget(signal_log)
        splitter.addWidget(signals)
        self.signals = signals

        # style sheet
        main_w.setStyleSheet('QSplitter::handle{background: white;}')

        if self.config[splitter.objectName()].get('sizes'):
            splitter.setSizes(self.config[splitter.objectName()]['sizes'])
        main_w.show()

        def update_interval_changed(value: float):
            self.info('update_interval changed to {}'.format(value))
            update_timer.setInterval(value * 1000)

        update_timer = QTimer()
        update_timer.setInterval(update_interval.value() * 1000)
        update_interval.valueChanged.connect(update_interval_changed)
        update_timer.timeout.connect(self.update_data)
        update_timer.start(update_interval.value() * 1000)

        status = app.exec_()
        self.stop()
        sys.exit(status)

    def update_data(self):
        prices = {}
        now = jst_now_aware()
        for name, instrument_v in copy.deepcopy(self.prices).items():
            for instrument, price in instrument_v.items():
                if price.time >= now - timedelta(seconds=10):
                    prices.setdefault(name, {})[instrument] = price
        data = {
            'accounts': copy.deepcopy(self.accounts),
            'prices': prices,
        }
        self.account_ui.on_data(data)
        for price_table in self.price_ui_list:
            price_table.on_data(data)
        self.signals.on_data(data)

    def handle_udp(self, request, address):
        data, _ = request
        unpacked = unpack_from_bytes(data)
        if isinstance(unpacked, dict):
            for k, v_dict in unpacked.items():
                if k == 'accounts':
                    for name, v in v_dict.items():
                        self.accounts[name] = Account(*v)
                if k == 'prices':
                    for name, instrument_v in v_dict.items():
                        for instrument, v in instrument_v.items():
                            self.prices[name][instrument] = Price(*v)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT    [default: :9999]
      --publisher IP_PORT  [default: hub:10000]
      --config FILE  [default: ./config.yaml]
      --demo
    """.format(f=sys.argv[0]))

    l = args['--bind'].split(':')
    bind_address = (l[0] or socket.gethostname(), int(l[1]))
    l = args['--publisher'].split(':')
    publisher_address = (l[0], int(l[1]))
    config_path = args['--config']

    if args['--demo']:
        publisher_address = ('127.0.0.1', 10000)
        hub = DemoHub('hub', publisher_address)
        hub.start()
        data_node = DemoData('data', ('127.0.0.1', 0), hub_addresses=[publisher_address])
        data_node.start()
    else:
        hub = DummyServer()
        data_node = DummyServer()

    try:
        node = GUINode(bind_address, publisher_address=publisher_address, config_path=config_path)
        node.start()  # event loop
    finally:
        hub.stop()
        data_node.stop()


class DemoHub(HubNode):
    pass


class DemoData(DataNode):
    def start(self):
        super().start()
        threading.Thread(target=self.push_loop, daemon=True).start()

    def push_loop(self):
        names = ['pfxnano', 'gaitamecom', 'triauto', 'minfx', 'minSys']
        instruments = ['USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', ]  # 'EUR/USD']
        accounts = {name: Account(name) for name in names}

        def update_accounts():
            for name, account in accounts.items():
                positions = account.positions
                instrument = random.choice(instruments)
                positions.setdefault(instrument, 0)
                positions[instrument] += (random.randint(0, 2) - 1) * 1000
                accounts[name] = account.replace(equity=random.random() * 1000000,
                                                 profit_loss=random.random() * 1000000,
                                                 used_margin=random.random() * 1000000,
                                                 positions=positions)

        def gen_prices():
            prices = defaultdict(dict)
            for name in names:
                for instrument in instruments:
                    prices[name][instrument] = Price(name, instrument, bid=100 + random.random() / 100,
                                                     ask=100 + random.random() / 100)
            return prices

        while self.is_running():
            try:
                self.push_data(accounts=accounts, prices=gen_prices())
                time.sleep(1)
                update_accounts()
            except Exception as e:
                self.exception(str(e))


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
