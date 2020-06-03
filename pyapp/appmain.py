import itertools
import logging
import os
import random
import sqlite3
import statistics
import sys
import threading
from collections import defaultdict
from datetime import datetime, timedelta

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtMultimedia import *
from PyQt5.QtWidgets import *
from docopt import docopt

import timeutil


class Window(QMainWindow):
    ROW_H = 20
    FONT_P = 10

    updated = pyqtSignal(dict)

    def __init__(self, width, height, header_labels, rank, *, instruments):
        super().__init__()
        row_n = rank * 2 - 1
        self._instruments = instruments
        w = self
        w.resize(width, height)
        w.setCentralWidget(QWidget())
        w.centralWidget().setContentsMargins(0, 0, 0, 0)
        lo = QGridLayout(w.centralWidget())

        self._tables = tables = {}
        for i, instrument in enumerate(instruments):
            label = QLabel(instrument)
            label.setContentsMargins(0, 0, 0, 0)
            lo.addWidget(label, i, 0)

            column_n = len(header_labels)
            t = QTableWidget(row_n, column_n)
            t.setContentsMargins(0, 0, 0, 0)
            tables[instrument] = t
            t.setHorizontalHeaderLabels(header_labels)
            t.horizontalHeader().hide()
            t.horizontalHeader().setStretchLastSection(True)
            t.verticalHeader().hide()
            font = t.font()
            font.setPointSize(self.FONT_P)
            t.setFont(font)
            for row in range(row_n):
                t.setRowHeight(row, self.ROW_H)
                for col in range(column_n):
                    t.setColumnWidth(col, 80)
                    item = QTableWidgetItem()
                    if col < 2:
                        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    elif col == 2:
                        item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
                    else:
                        item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    t.setItem(row, col, item)
            self.clear_table(instrument)
            lo.addWidget(t, i, 1)
        self._tables = tables
        self.updated.connect(self.update_table)

    def get_instruments(self):
        return self._instruments

    def clear_table(self, instrument):
        table = self._tables[instrument]
        for row in range(table.rowCount()):
            for col in range(table.columnCount()):
                self.set(instrument, row, col, None)

    def set(self, instrument, row, column, item):
        minus = False
        if isinstance(item, float):
            if item < 0:
                minus = True
            if column == 2:
                item = '{:.2f}'.format(item)
            elif 'JPY' in instrument:
                item = '{:.4f}'.format(item)
            else:
                item = '{:.6f}'.format(item)
        self._tables[instrument].item(row, column).setData(Qt.DisplayRole, item)
        if minus:
            self._tables[instrument].item(row, column).setData(Qt.BackgroundRole, QBrush(Qt.green))
        else:
            self._tables[instrument].item(row, column).setData(Qt.BackgroundRole, None)

    @pyqtSlot(dict)
    def update_table(self, table_data):
        for instrument, data in table_data.items():
            if instrument not in self._tables:
                continue
            table = self._tables[instrument]
            for row in range(table.rowCount()):
                for col in range(table.columnCount()):
                    self.set(instrument, row, col, data[row][col])


class Notifier(QMainWindow):
    ROW_H = 20
    FONT_P = 10
    SIGNAL_LOG_N = 20
    updated = pyqtSignal(list)

    def __init__(self, check_interval=1, log_remaining_time=30, seq_len=10, **instrument_sp):
        super().__init__()
        self.check_interval = check_interval
        self.log_remaining_time = log_remaining_time
        self.seq_len = seq_len
        self.instrument_sp = instrument_sp
        self.resize(440, 280)
        self.records = defaultdict(dict)

        self.signal_list = []

        labels = ['time', 'instrument', 'bidder', 'asker', 'sp']
        self._table = t = QTableWidget(self.SIGNAL_LOG_N, len(labels))
        t.setContentsMargins(0, 0, 0, 0)
        t.setHorizontalHeaderLabels(labels)
        # t.horizontalHeader().hide()
        t.horizontalHeader().setStretchLastSection(True)
        # t.verticalHeader().hide()
        self.setCentralWidget(t)
        font = t.font()
        font.setPointSize(self.FONT_P)
        t.setFont(font)
        for row in range(self.SIGNAL_LOG_N):
            t.setRowHeight(row, self.ROW_H)
            for col in range(len(labels)):
                t.setColumnWidth(col, 70)
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                t.setItem(row, col, item)
        t.setColumnWidth(0, 140)

        self.sound = QSound('./alert.wav')
        self.sound.setLoops(1)

        self.updated.connect(self.update_table)

    @pyqtSlot(list)
    def update_table(self, signaled):
        self.signal_list += signaled
        if len(self.signal_list) > self.SIGNAL_LOG_N:
            self.signal_list = self.signal_list[1:]
        for row, d in enumerate(self.signal_list + [dict()] * self.SIGNAL_LOG_N):
            if row >= self.SIGNAL_LOG_N:
                break
            dt = d.get('time')
            dt = dt and dt.strftime('%Y%m%d %H:%M:%S%Z')
            self._table.item(row, 0).setData(Qt.DisplayRole, dt)
            self._table.item(row, 1).setData(Qt.DisplayRole, d.get('instrument'))
            self._table.item(row, 2).setData(Qt.DisplayRole, d.get('direction', (None, None))[0])
            self._table.item(row, 3).setData(Qt.DisplayRole, d.get('direction', (None, None))[1])
            self._table.item(row, 4).setData(Qt.DisplayRole, d.get('sp'))

    def update(self, now: datetime, all_results: dict):
        instrument_services = defaultdict(set)
        for name, results in all_results.items():
            for instrument in results:
                instrument_services[instrument].add(name)

        signaled = []
        delta = timedelta(seconds=self.check_interval)
        for instrument, sp_threshold in self.instrument_sp.items():
            instrument = (instrument[:3] + '/' + instrument[-3:]).upper()
            if 'JPY' in instrument:
                multiply_rate = 100
            else:
                multiply_rate = 10000
            sp_threshold = sp_threshold / multiply_rate

            for a, b in itertools.combinations(instrument_services[instrument], 2):
                a, b = (a, b) if a < b else (b, a)
                a_bid = all_results[a][instrument]['bid']
                a_ask = all_results[a][instrument]['ask']
                b_bid = all_results[b][instrument]['bid']
                b_ask = all_results[b][instrument]['ask']
                direction = None
                if a_bid - b_ask >= sp_threshold:
                    sp = (a_bid - b_ask) * multiply_rate
                    direction = (a, b)
                elif b_bid - a_ask >= sp_threshold:
                    sp = (b_bid - a_ask) * multiply_rate
                    direction = (b, a)
                if not direction:
                    continue

                d = self.records[(a, b, instrument)]
                if d.get('direction') != direction:
                    d['sp_list'] = []
                if d.get('time') and now - d['time'] >= delta:
                    d['sp_list'] = []
                d['time'] = now
                d['direction'] = direction
                sp_list = d.setdefault('sp_list', [])
                sp_list.append(sp)
                if len(sp_list) >= self.seq_len:
                    median = statistics.median_low(sp_list)
                    if d.get('last_direction') != direction or median > d.get('median', 0):
                        d['median'] = median
                        signaled.append(dict(time=now, instrument=instrument, direction=direction, sp=median))
                    d['last_direction'] = direction
        self.updated.emit(signaled)

        if signaled:
            print('#SIGNAL')
            self.sound.play()
            with open('./signal-log.txt', 'a') as f:
                for d in signaled:
                    f.write('{time},{instrument},{direction},{sp:.2f}\n'.format(**d))

        return signaled


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s|%(name)s|%(levelname)s| %(message)s')
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --size SIZE  [default: 500x760]
      --train      [default: False]
      --database DATABASE  [default: db.sqlite3]
      --rank RANK  [default: 2]

    """.format(f=sys.argv[0]))
    width, height = args['--size'].split('x')
    width, height = int(width), int(height)
    train = args['--train']
    db = args['--database']
    rank = int(args['--rank'])

    instruments = ('USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'EUR/USD', 'GBP/USD', 'AUD/USD')

    stop = False
    services = {}
    excepted_recognition = {'click'}
    excepted_rank = {'mnp', 'sbi', 'click'}
    launched = False

    # train = input('train num[0-9] ')
    train = 0
    notifier = None

    def update():
        try:
            from capwin import get_services
            nonlocal services
            services = get_services()
            #            services = dict(filter(lambda x: x[0] == 'nano' or x[0] == 'mnp' or x[0] == 'try', services.items()))
            for s in services.values():
                s.find_window()
            for service in services.values():
                service.load_model()
            if int(train):
                for service in services.values():
                    service.train(epoch=int(train))
            for service in services.values():
                service.save_model()
            nonlocal launched
            launched = True

            last = timeutil.jst_now()
            db_last = timeutil.jst_now()
            conn = sqlite3.connect(db)
            # conn.execute("""CREATE TABLE IF NOT EXISTS pyapp
            # (time DATETIME, name TEXT, instrument TEXT, bid FLOAT, ask FLOAT,
            # PRIMARY KEY (time, name, instrument))""")
            cur = conn.cursor()
            tables = set()

            def create_table(name: str, instrument: str):
                table_name = '{}_{}'.format(name, instrument.replace('/', ''))
                if table_name not in tables:
                    cur.execute("""CREATE TABLE IF NOT EXISTS {}
                    (time DATETIME PRIMARY KEY, bid FLOAT, ask FLOAT)""".format(table_name))
                    tables.add(table_name)
                return table_name

            def insert(_time: datetime, _all_results: dict):
                for name, results in _all_results.items():
                    for instrument, d in results.items():
                        table_name = create_table(name, instrument)
                        cur.execute('INSERT INTO {} VALUES(?,?,?)'.format(table_name),
                                    (_time, d['bid'], d['ask']))

            while True:
                try:
                    time.sleep(0.02)
                    all_results = update_main(services)
                    now = timeutil.jst_now()
                    if notifier:
                        x_results = dict(filter(lambda x: x[0] not in excepted_rank, all_results.items()))
                        notifier.update(now, x_results)
                    if os.name == 'posix':
                        time.sleep(1)
                        continue
                    if (now - last).total_seconds() >= 600:
                        for s in services.values():
                            s.save()
                        last = timeutil.jst_now()
                    insert(now, all_results)
                    if (now - db_last).total_seconds() >= 5:
                        conn.commit()
                        db_last = timeutil.jst_now()
                except Exception as e:
                    logging.exception('{}'.format(str(e)))
                    time.sleep(1)
        except Exception as e:
            logging.exception('{}'.format(str(e)))
        finally:
            nonlocal stop
            stop = True

    def update_main(services):
        snap_failed = set()
        l = list(services.items())
        for name, service in random.sample(l, len(l)):
            try:
                service.snap()
            except Exception as e:
                logging.exception('{}\n{}'.format(name, str(e)))
                snap_failed.add(name)
        all_results = {}
        for name, service in services.items():
            if name in snap_failed:
                continue
            if name in excepted_recognition:
                continue
            try:
                results = {}
                for instrument, d in service.recognize().items():
                    try:
                        results[instrument] = dict(
                            instrument=d['instrument'],
                            bid=float(d['bid']),
                            ask=float(d['ask']),
                        )
                    except:
                        pass
                all_results[name] = results
            except Exception as e:
                logging.exception('{}\n{}'.format(name, str(e)))
                service.save()
        tables = {}
        center = rank - 1
        for instrument in w.get_instruments():
            table = [[''] * len(labels) for _ in range(rank * 2 - 1)]
            tables[instrument] = table
            bids = []
            asks = []
            for name, results in all_results.items():
                if name in snap_failed:
                    continue
                if name in excepted_recognition:
                    continue
                if name in excepted_rank:
                    continue
                if instrument in results:
                    bids.append((name, results[instrument]['bid']))
                    asks.append((name, results[instrument]['ask']))
            bids.sort(key=lambda x: -x[1])
            for i in range(rank):
                table[center + i][0] = bids[i][0]
                table[center + i][1] = bids[i][1]
            asks.sort(key=lambda x: x[1])
            for i in range(rank):
                table[center - i][4] = asks[i][0]
                table[center - i][3] = asks[i][1]
            for i in range(len(table)):
                if table[i][3]:  # ask
                    sp = table[i][3] - table[center][1]
                    if 'JPY' in instrument:
                        sp *= 100
                    else:
                        sp *= 10000
                    table[i][2] = sp
                else:  # bid
                    sp = table[center][3] - table[i][1]
                    if 'JPY' in instrument:
                        sp *= 100
                    else:
                        sp *= 10000
                    table[i][2] = sp
        w.updated.emit(tables)
        return all_results

    thread = threading.Thread(target=update, daemon=True)
    thread.start()

    while thread.is_alive():
        if launched:
            break
        import time
        time.sleep(0.1)

    if not thread.is_alive():
        sys.exit(-1)

    app = QApplication(sys.argv[1:])

    labels = ['bidder', 'bid', 'sp', 'ask', 'asker']
    w = Window(width, height, rank=rank, header_labels=labels, instruments=instruments)
    notifier = Notifier(seq_len=10, usdjpy=0.48, eurjpy=0.48, gbpjpy=0.501, audjpy=0.38, eurusd=0.5, gbpusd=0.5,
                        audusd=0.4)

    w.show()
    notifier.show()

    @pyqtSlot()
    def check_stop():
        if stop:
            raise Exception('stopped.')

    update_timer = QTimer()
    update_timer.timeout.connect(check_stop)
    update_timer.start(1000)
    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
