import copy
import itertools
import logging
import random
import statistics
import sys
from collections import defaultdict
from datetime import timedelta, datetime
from typing import List, Tuple, Union, Optional, Set

import gevent
from PyQt5.QtCore import *
from PyQt5.QtGui import QBrush
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtGui import QResizeEvent
from PyQt5.QtMultimedia import QSound
from PyQt5.QtWidgets import *
from docopt import docopt
from gsocketpool.pool import Pool

import env
import serviceclient
import timeutil
from model import Config
from rpcserver import Master


class TableView(QTableWidget):
    FONT_P = 10
    ROW_H = 18

    def __init__(self, row: int = 0, labels: List[str] = None, *, config: Config):
        labels = tuple(labels or [])
        super().__init__(0, len(labels))
        self.config = config
        self.labels = labels

        self.resize_row(row)
        self.setContentsMargins(0, 0, 0, 0)
        self.setHorizontalHeaderLabels(labels)
        # self.horizontalHeader().setStretchLastSection(True)

        # set font
        font = self.font()
        font.setPointSize(self.FONT_P)
        self.setFont(font)
        font = self.verticalHeader().font()
        font.setPointSize(self.FONT_P - 2)
        self.verticalHeader().setFont(font)

    def new_item(self, row: int, col: int) -> QTableWidgetItem:
        return QTableWidgetItem()

    def resize_row(self, row_n: int):
        current_row_n = self.rowCount()
        self.setRowCount(row_n)
        for row in range(current_row_n, row_n):
            self.setRowHeight(row, self.ROW_H)
            for col in range(len(self.labels)):
                self.setItem(row, col, self.new_item(row, col))

    def set_item(self, row: int, col: Union[int, str], value=None, bg=None, flags=None):
        if isinstance(col, str):
            try:
                col = self.labels.index(col)
            except ValueError:
                return False
        if row >= self.rowCount() or col >= self.columnCount():
            return False
        if value is not None:
            self.item(row, col).setData(Qt.DisplayRole, value)

        flags = flags if flags is not None else Qt.ItemIsEnabled
        self.item(row, col).setData(Qt.BackgroundRole, bg)
        self.item(row, col).setData(Qt.DisplayRole, value)
        self.item(row, col).setFlags(flags)
        return True


class PriceTable(TableView):
    def __init__(self, row=0, *, config: Config):
        labels = ['bidder', 'bid', 'sp', 'ask', 'asker']
        super().__init__(row=row, labels=labels, config=config)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setColumnWidth(0, 60)
        self.setColumnWidth(1, 70)
        self.setColumnWidth(2, 50)
        self.setColumnWidth(3, 70)
        self.setColumnWidth(4, 60)

    def new_item(self, row: int, col: int) -> QTableWidgetItem:
        item = QTableWidgetItem()
        if col < 2:
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        elif col == 2:
            item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
        else:
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setFlags(Qt.ItemIsEnabled)
        return item


class InstrumentComboBox(QComboBox):
    def __init__(self, instrument=None, *, instruments: Config, config: Config):
        instrument = instrument or 'USD/JPY'
        super().__init__()
        self.config = config
        instruments.data_changed.connect(self.update_instruments)
        self.update_instruments(instruments)
        self.setCurrentText(instrument)

    @pyqtSlot(object)
    def update_instruments(self, instruments):
        current = self.currentText()
        self.clear()
        self.addItems(sorted(instruments))
        self.setCurrentText(current)


def get_pip_scale(instrument: str) -> int:
    if 'JPY' in instrument.upper():
        return 100
    else:
        return 10000


class PriceView(QWidget):
    def __init__(self, *, config: Config, enabled_instruments: Set[str]):
        super().__init__()
        self.config = config
        self.setContentsMargins(0, 0, 0, 0)

        lo = QGridLayout()
        self.setLayout(lo)
        lo.setContentsMargins(0, 0, 0, 0)

        price_view = config.setdefault('price_view', [])
        if not price_view:
            ranking = 4
            price_view.append(dict(instrument='USD/JPY', ranking=ranking))
            price_view.append(dict(instrument='EUR/JPY', ranking=ranking))
            price_view.append(dict(instrument='GBP/JPY', ranking=ranking))
            price_view.append(dict(instrument='AUD/JPY', ranking=ranking))
        for x in price_view:
            enabled_instruments.add(x['instrument'])

        self.items = []
        for i, conf in enumerate(price_view):
            combo = InstrumentComboBox(conf['instrument'], instruments=config['instruments'], config=config)

            def get_activated(_combo, i):
                @pyqtSlot(int)
                def activated(index):
                    if not isinstance(index, int):
                        return
                    price_view[i]['instrument'] = _combo.itemText(index)
                    enabled_instruments.clear()
                    for x in price_view:
                        enabled_instruments.add(x['instrument'])
                return activated

            combo.activated.connect(get_activated(combo, i))
            table = PriceTable(conf['ranking'] * 2 - 1, config=config)
            lo.addWidget(combo, i, 0)
            lo.addWidget(table, i, 1)

            self.items.append((combo, table))

    @pyqtSlot(dict)
    def update_prices(self, prices: List[dict]):
        # List[dict] -> Dict[instrument, dict]
        instrument_prices = defaultdict(list)
        for price in prices:
            instrument_prices[price['instrument']].append(price)
        for i, (combo, table) in enumerate(self.items):
            instrument = combo.currentText()
            if instrument not in instrument_prices:
                continue
            self._update(table, instrument_prices[instrument], instrument=instrument,
                         pip_scale=get_pip_scale(instrument))

    def _update(self, table: PriceTable, prices: List[dict], instrument: str, pip_scale: int):
        disabled = self.config.setdefault('disabled_services', set())
        bids = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: -x['bid']))
        asks = list(sorted(filter(lambda x: x['service'] not in disabled, prices), key=lambda x: x['ask']))
        rank = (table.rowCount() + 1) // 2
        center = rank - 1
        if not bids or not asks:
            return

        def get_float_format(instrument: str) -> str:
            if 'JPY' in instrument.upper():
                return '{:.4f}'
            return '{:.6f}'

        float_format = get_float_format(instrument)
        max_bid = bids[0]['bid']
        min_ask = asks[0]['ask']
        # set bids
        for i, d in enumerate(bids[:rank]):
            bid = d['bid']
            sp = (min_ask - bid) * pip_scale
            bg = QBrush(Qt.green) if sp < 0 else None
            table.set_item(center + i, 'sp', '{:.2f}'.format(sp), bg=bg)
            table.set_item(center + i, 'bidder', d['service'])
            table.set_item(center + i, 'bid', float_format.format(bid))
        # set asks
        for i, d in enumerate(asks[:rank]):
            ask = d['ask']
            sp = (ask - max_bid) * pip_scale
            bg = QBrush(Qt.green) if sp < 0 else None
            table.set_item(center - i, 'sp', '{:.2f}'.format(sp), bg=bg)
            table.set_item(center - i, 'ask', float_format.format(ask))
            table.set_item(center - i, 'asker', d['service'])


class SoundPlayer:
    def __init__(self, *, root_config: Config):
        self.root_config = root_config
        self.sounds = root_config.setdefault('sounds', {
            'signal_open': {
                'file': './signal_open.wav',
                'loop': 1
            },
            'signal_close': {
                'file': './signal_close.wav',
                'loop': 3
            },
        })
        self.q_sounds = {}

    def play(self, name):
        if self.root_config.get('mute'):
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


class Signaler:
    def __init__(self, *, config: Config):
        config = config.setdefault('signaler', dict(
            timeout=1.0,
            duration=5,
            sp_threshold_ratio=0.4,
        ))
        self.config = config
        self.last_received = timeutil.jst_now()
        self.history = []
        self.last_sp = 0  # type: Union[int, float]
        self.initialized = False
        self.key = None
        self.key_tuple = None
        self.duration = timedelta()
        self.last_signaled = datetime.min

    def init(self, instrument: str, b: str, a: str):
        if self.initialized:
            return
        self.initialized = True
        self.key_tuple = instrument, b, a
        self.key = '({}, {}, {})'.format(*self.key_tuple)
        x = self.config.setdefault(self.key, {})
        x.setdefault('enabled', True)
        x.setdefault('opened', False)
        x.setdefault('not_closed', False)

    def opposite_key(self):
        return '({}, {}, {})'.format(self.key_tuple[0], self.key_tuple[2], self.key_tuple[1])

    @property
    def enabled(self):
        if not self.initialized:
            return True
        return self.config[self.key]['enabled']

    @enabled.setter
    def enabled(self, value):
        if not self.initialized:
            return
        self.config[self.key]['enabled'] = value

    @property
    def opened(self):
        if not self.initialized:
            return False
        return self.config[self.key]['opened']

    @opened.setter
    def opened(self, value):
        if not self.initialized:
            return
        self.config[self.key]['opened'] = value
        self.config.setdefault(self.opposite_key(), {})['not_closed'] = value

    @property
    def not_closed(self):
        if not self.initialized:
            return False
        return self.config[self.key]['not_closed']

    @not_closed.setter
    def not_closed(self, value):
        if not self.initialized:
            return
        self.config[self.key]['not_closed'] = value
        self.config.setdefault(self.opposite_key(), {})['opened'] = value

    def clear(self):
        self.last_received = timeutil.jst_now()
        self.history.clear()
        self.last_sp = 0
        self.duration = timedelta()

    def judge(self, instrument: str, bidder: dict, asker: dict, duration_threshold: int = None) -> Optional[dict]:
        b, a = bidder['service'], asker['service']
        self.init(instrument, b, a)
        next_received = max(bidder['time'], asker['time'])
        assert bidder['instrument'] == asker['instrument']
        if int((bidder['time'] - asker['time']).total_seconds()) >= 1.0:
            self.history.clear()
            return
        try:
            middle = sum([bidder['bid'], asker['ask']]) / 2
            sp_threshold = middle * self.config['sp_threshold_ratio'] / 10000 * get_pip_scale(instrument)
            timeout = timedelta(seconds=self.config['timeout'])
            if next_received - self.last_received >= timeout:
                self.history.clear()
                return

            pip_scale = get_pip_scale(instrument)
            sp = (bidder['bid'] - asker['ask']) * pip_scale
            d = copy.deepcopy(bidder)
            d.update(direction=(b, a), bidder=b, asker=a, ask=asker['ask'], sp=sp, time=next_received,
                     bid_data=bidder, ask_data=asker)

            if sp < sp_threshold:
                self.history.clear()
                if sp > 0:
                    return d, None
                return
            self.history.append(d)

            duration_threshold = duration_threshold or timedelta(seconds=self.config['duration'])
            duration = next_received - self.history[0]['time']
            if duration >= duration_threshold:
                sp_list = list(map(lambda x: x['sp'], self.history))
                sp_min = min(sp_list)
                sp_stdev = statistics.stdev(sp_list)
                self.history = list(filter(lambda x: next_received - x['time'] <= duration_threshold * 2, self.history))
                bid_list = list(map(lambda x: x['bid_data']['bid'], self.history))
                ask_list = list(map(lambda x: x['ask_data']['ask'], self.history))
                bid_stdev = statistics.stdev(bid_list)
                ask_stdev = statistics.stdev(ask_list)
                if sp_stdev > 0.5:
                    logging.warning(
                        'too volatile. sp_stdev:{}, sp_threshold:{}, instrument:{}, {} -> {}'.format(sp_stdev,
                                                                                                     sp_threshold,
                                                                                                     instrument, b, a))
                    return d, None
                if bid_stdev * 2 / bid_list[-1] * 100 > 0.03:
                    logging.warning(
                        'too volatile. bid_stdev:{}, instrument:{}, {} -> {}'.format(bid_stdev, instrument, b, a))
                    return d, None
                if ask_stdev * 2 / ask_list[-1] * 100 > 0.03:
                    logging.warning(
                        'too volatile. ask_stdev:{}, instrument:{}, {} -> {}'.format(ask_stdev, instrument, b, a))
                    return d, None
                if sp_min > self.last_sp + 0.01 or (timeutil.jst_now() - self.last_signaled >= timedelta(minutes=1)):
                    self.last_sp = sp_min
                    d2 = copy.deepcopy(d)
                    d2.update(sp=self.last_sp, not_closed=self.not_closed)
                    self.last_signaled = timeutil.jst_now()
                    return d, d2
        finally:
            self.last_received = next_received


class SignalLogView(TableView):
    MAX_LOG_N = 15

    def __init__(self, *, config: Config, enabled_instruments: Set[str]):
        labels = ['time', 'instrument', 'bidder', 'asker', 'sp', 'E', 'O', 'C']
        super().__init__(labels=labels, config=config)
        self.root_config = root_config = config
        self.config = config = config.setdefault('signal_log', {})
        self.resize_row(config.setdefault('max_log_n', self.MAX_LOG_N))
        self.enabled_instruments = enabled_instruments
        height = config.setdefault('height', 200)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.resize(0, height)

        width_list = config.setdefault('column_width', [150, 70, 50, 50, 40, 20, 20, 20])
        for i, width in enumerate(width_list):
            self.setColumnWidth(i, width)

        # signal
        self.signalers = defaultdict(lambda: Signaler(config=root_config))  # type: Dict[Tuple[str,str,str], Signaler]
        self.signals = []
        self.sound_player = SoundPlayer(root_config=root_config)

        self.signal_log_file = self.config.setdefault('signal_log_file', './signal_log.txt')

        # QSignal connect
        self.cellClicked.connect(self.cell_clicked)

    def resizeEvent(self, e: QResizeEvent):
        self.config['height'] = self.size().height()
        super().resizeEvent(e)

    def new_item(self, row: int, col: int) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        item.setFlags(Qt.ItemIsEnabled)
        return item

    @pyqtSlot(int, int)
    def cell_clicked(self, row: int, col: int):
        label = self.labels[col]
        if label not in 'EOC':
            return
        signaler = self.signals[row]['signaler']
        if label == 'E':
            signaler.enabled = self.item(row, col).checkState() == Qt.Checked
        if label == 'O':
            signaler.opened = self.item(row, col).checkState() == Qt.Checked
        if label == 'C':
            signaler.not_closed = self.item(row, col).checkState() == Qt.Checked
        self.add_signal(data={})

    def add_signal(self, data: dict):
        item_list = self.signals
        if data:
            item_list.append(dict(**data))
            if len(item_list) > self.config['max_log_n']:
                item_list.pop(0)

        for row, item in enumerate(item_list):
            signaler = item['signaler']
            flags = None
            if not signaler.enabled:
                flags = Qt.NoItemFlags
            for k, v in item.items():
                self.set_item(row, k, v, flags=flags, bg=item['bg'])
            # Enabled
            if signaler.enabled:
                self.set_item(row, 'E', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('E')).setCheckState(Qt.Checked)
            else:
                self.set_item(row, 'E', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('E')).setCheckState(Qt.Unchecked)
            # Opened
            if signaler.opened:
                self.set_item(row, 'O', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('O')).setCheckState(Qt.Checked)
            else:
                self.set_item(row, 'O', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('O')).setCheckState(Qt.Unchecked)
            # Not Closed
            if signaler.not_closed:
                self.set_item(row, 'C', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('C')).setCheckState(Qt.Checked)
            else:
                self.set_item(row, 'C', '', flags=Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                self.item(row, self.labels.index('C')).setCheckState(Qt.Unchecked)

    def update_prices(self, prices: List[dict]):
        disabled = self.root_config.setdefault('disabled_services', set())

        instrument_service_prices = defaultdict(lambda: defaultdict(list))
        for price in prices:
            instrument_service_prices[price['instrument']][price['service']].append(price)
        signals = []  # type:List[dict]
        import csv
        import os
        home_dir = env.get_desktop_dir()
        with open(os.path.join(home_dir, 'pyapp.csv'), 'a') as f:
            csv_writer = csv.writer(f)
            for instrument, service_prices in instrument_service_prices.items():
                service_pairs = sorted(itertools.permutations(service_prices.keys(), 2), key=str)
                for b, a in service_pairs:
                    bidder, asker = service_prices[b][0], service_prices[a][0]
                    signaler = self.signalers[(instrument, b, a)]
                    d = signaler.judge(instrument=instrument, bid_data=bidder, ask_data=asker,
                                       duration_threshold=(2 if a == b else None))
                    if d:
                        # minus spread
                        keys = ['time', 'instrument', 'bidder', 'asker', 'bid', 'ask', 'sp']
                        values = [d[0][k] for k in keys]
                        values[-1] = '{:.2f}'.format(values[-1])
                        csv_writer.writerow(values)

                    if d and d[1]:
                        d = d[1]
                        d['signaler'] = signaler
                        d['bg'] = None
                        d['time'] = d['time'].strftime('%Y-%m-%d %H:%M:%S%Z')
                        d['sp'] = '{:.2f}'.format(d['sp'])
                        with open(self.signal_log_file, 'a') as f:
                            f.write('{time},{instrument},{bidder},{asker},{bid},{ask},{sp},{not_closed}\n'.format(**d))
                        if d['bidder'] in disabled or d['asker'] in disabled:
                            continue
                        opposite = self.signalers[(instrument, a, b)]
                        opposite.clear()
                        if instrument in self.enabled_instruments:
                            if signaler.enabled:
                                if signaler.not_closed:
                                    self.sound_player.play('signal_close')
                                    d['bg'] = QBrush(Qt.green)
                                elif not self.root_config.get('not_closed_only_check'):
                                    self.sound_player.play('signal_open')
                            self.add_signal(d)
        return signals


class ConfigWindow(QMainWindow):
    def __init__(self, *args, root_config: Config):
        super().__init__(*args)
        self.closed = False
        self.root_config = root_config

        self.setCentralWidget(QWidget())
        lo = QGridLayout()
        self.centralWidget().setLayout(lo)
        lo.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QTextEdit()
        self.text_edit.setText(root_config.dumps_yaml())
        lo.addWidget(self.text_edit, 0, 0, 1, 2)
        load = QPushButton('Load')
        apply = QPushButton('Apply')
        lo.addWidget(load, 1, 0)
        lo.addWidget(apply, 1, 1)

        # signal&slot connect
        load.clicked.connect(lambda *_: self.load())
        apply.clicked.connect(lambda *_: self.apply())

    def load(self):
        text = self.root_config.dumps_yaml()
        self.text_edit.setText(text)

    def apply(self):
        text = self.text_edit.toPlainText()
        f_name = './tmp.yaml'
        with open(f_name, 'w') as f:
            f.write(text)
        config = Config(f_name)
        self.root_config.update(config)

    def closeEvent(self, e: QCloseEvent):
        self.closed = True
        e.accept()


class AppWindow(QMainWindow):
    def __init__(self, *, root_config: Config):
        super().__init__()
        self.root_config = root_config
        self.config = config = root_config.setdefault('window',
                                                      dict(x=200, y=200, width=440, height=800))

        self.move(config['x'], config['y'])
        self.resize(config['width'], config['height'])

        self.setContentsMargins(0, 0, 0, 0)
        w = QWidget()
        w.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Vertical)
        splitter.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(splitter)

        enabled_instruments = set()
        # Price View
        self.price_view = price_view = PriceView(config=root_config, enabled_instruments=enabled_instruments)
        # lo.addWidget(price_view)
        splitter.addWidget(price_view)

        # CheckBox
        mute = QCheckBox('Mute')
        mute.setChecked(root_config.setdefault('mute', False))
        check = QCheckBox('NotClosedOnly')
        check.setChecked(root_config.setdefault('not_closed_only_check', False))

        def check_clicked_slot(key):
            @pyqtSlot(bool)
            def check_clicked(b):
                root_config[key] = b

            return check_clicked

        mute.clicked.connect(check_clicked_slot('mute'))
        check.clicked.connect(check_clicked_slot('not_closed_only_check'))

        w = QWidget()
        w.setContentsMargins(0, 0, 0, 0)
        w.setLayout(QHBoxLayout())
        w.layout().setContentsMargins(0, 0, 0, 0)
        w.layout().addStretch()
        w.layout().addWidget(mute)  # , alignment=Qt.AlignRight)
        w.layout().addWidget(check)  # , alignment=Qt.AlignRight)

        splitter.addWidget(w)

        # Log Table
        self.signal_log = signal_log = SignalLogView(config=root_config, enabled_instruments=enabled_instruments)
        # lo.addWidget(signal_log)
        splitter.addWidget(signal_log)

        self.init_menu()
        self.config_window = None  # type: QMainWindow

    @pyqtSlot()
    def edit_config(self):
        if self.config_window and not self.config_window.closed:
            self.config_window.activateWindow()
            return
        self.config_window = ConfigWindow(root_config=self.root_config)
        self.config_window.show()

    def init_menu(self):
        config_action = QAction('&Edit', self)
        config_action.triggered.connect(self.edit_config)
        w = QMainWindow()
        w.resize(100, 100)
        w.show()

        menubar = self.menuBar()
        config_menu = menubar.addMenu('&Config')
        config_menu.addAction(config_action)

    def closeEvent(self, e: QCloseEvent):
        pos = self.pos()
        size = self.size()
        self.config['x'] = pos.x()
        self.config['y'] = pos.y()
        self.config['width'] = size.width()
        self.config['height'] = size.height()
        if self.root_config['auto_save']:
            self.root_config.save()
        else:
            print(self.root_config.dumps_yaml())
        if self.config_window:
            self.config_window.close()
        e.accept()

    @pyqtSlot(list)
    def update_prices(self, prices: List[dict]):
        self.price_view.update_prices(prices)
        self.signal_log.update_prices(prices)


class AppMaster(Master):
    def __init__(self, bind_address: Tuple[str, int], *, config: Config, disabled: set):
        super().__init__(name='appmaster', bind_address=bind_address)
        self.config = config

        self.instruments = config.setdefault('instruments', {'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY',
                                                             'EUR/USD', 'GBP/USD', 'AUD/USD'})
        config['disabled_services'] = disabled
        self.window = AppWindow(root_config=config)
        self.window.show()
        self.pools = {}  # type: Dict[str, Pool]

        self.elapsed_list = []
        self.request_elapsed_list = []

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

        def extend_prices(_pool: Pool):
            with _pool.connection() as client:
                l = client.get_prices() or []
            for x in l:
                x['time'] = now
            prices.extend(l)

        now = timeutil.jst_now()
        prices = []
        spawns = {key: gevent.spawn(lambda _pool: extend_prices(_pool), pool)
                  for key, pool in random.sample(self.pools.items(), len(self.pools))}

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
        for price in prices:
            if price['instrument'] not in self.instruments:
                self.instruments.add(price['instrument'])
        elapsed = timeutil.jst_now() - now
        self.request_elapsed_list.append(elapsed)
        self.window.update_prices(prices)
        elapsed = timeutil.jst_now() - now
        self.elapsed_list.append(elapsed)
        N = 10
        if len(self.elapsed_list) >= N:
            total = sum(map(lambda x: x.total_seconds(), self.elapsed_list))
            print('# elapsed total:{}, N:{}, one:{}'.format(total, N, total / N))
            total = sum(map(lambda x: x.total_seconds(), self.request_elapsed_list))
            print('# request total:{}, N:{}, one:{}'.format(total, N, total / N))
            self.elapsed_list = []
            self.request_elapsed_list = []
        if is_timeout:
            gevent.sleep(3)
            print('#timeout sleep(3)')
        else:
            gevent.sleep(max((timedelta(milliseconds=500) - elapsed).total_seconds(), 0.1))
            # gevent.sleep(0.1)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --bind IP_PORT    [default: 127.0.0.1:10000]
      --config FILE  [default: ./appconfig.yaml]
      --auto-save
      --disabled SERVIES  [default: xxx]
      --exit TIME  [default: 0500]
    """.format(f=sys.argv[0]))
    l = args['--bind'].split(':')
    bind_address = (l[0], int(l[1]))
    config_file = args['--config']
    auto_save = bool(args['--auto-save'])
    disabled = set(args['--disabled'].split(','))
    exit_time = args['--exit']
    exit_hour, exit_minute = int(exit_time[:-2]), int(exit_time[-2:])

    app = QApplication([])

    config = Config(config_file)
    config.setdefault('auto_save', auto_save)
    master = AppMaster(bind_address=bind_address, config=config, disabled=disabled)
    gevent.spawn(master.start)

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
