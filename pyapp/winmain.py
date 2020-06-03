import random
import sys
import threading

import time

import yaml
from PyQt5.QtGui import *
from docopt import docopt
from PyQt5.QtCore import *
from PyQt5.QtWidgets import *
from PIL import ImageGrab

#from pywinauto import Application
#from pywinauto.findwindows import find_window, find_windows
from win32 import win32gui

from collections import OrderedDict

yaml.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                     lambda loader, node: OrderedDict(loader.construct_pairs(node)))


class Window(QMainWindow):
    ROW_H = 24
    FONT_P = 15

    updated = pyqtSignal(list)

    def __init__(self, conf_file, width, height):
        super().__init__()
        self._conf_file = conf_file
        w = self
        w.resize(width, height)
        w.setCentralWidget(QWidget())
        lo = QVBoxLayout(w.centralWidget())

        self._labels = labels = ['title', 'x', 'y', 'w', 'h', 'i']
        col_n = len(labels)
        t = QTableWidget(0, col_n)
        for col in range(col_n):
            t.setColumnWidth(col, 80)
        t.setColumnWidth(0, 200)
        font = t.font()
        font.setPointSize(self.FONT_P)
        t.setFont(font)
        t.setHorizontalHeaderLabels(labels)
        t.horizontalHeader().setStretchLastSection(True)
        t.verticalHeader().hide()
        self._table = t
        lo.addWidget(t)

        self.load()

        # buttons
        bottom = QHBoxLayout()
        lo.addLayout(bottom)

        add_button = QPushButton('Add')
        bottom.addWidget(add_button)
        add_button.clicked.connect(self.add)

        arrange_button = QPushButton('Arrange')
        bottom.addWidget(arrange_button)
        arrange_button.clicked.connect(self.arrange)

        list_button = QPushButton('List')
        bottom.addWidget(list_button)
        list_button.clicked.connect(self.list_windows)

        load_button = QPushButton('Load')
        bottom.addWidget(load_button)
        load_button.clicked.connect(self.load)

        save_button = QPushButton('Save')
        bottom.addWidget(save_button)
        save_button.clicked.connect(self.save)

        self.updated.connect(self.update_table)

    @pyqtSlot()
    def add(self, **kwargs):
        row_n = self._table.rowCount()
        self._table.setRowCount(row_n + 1)
        for col, k in enumerate(self._labels):
            item = QTableWidgetItem()
            if col < 2:
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            elif col == 2:
                item.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self._table.setItem(row_n, col, QTableWidgetItem(kwargs.get(k)))

    @pyqtSlot()
    def arrange(self):
        config = []
        for row in range(self._table.rowCount()):
            d = OrderedDict()
            for col, k in enumerate(self._labels):
                x = self.get(row, col)
                if x:
                    d[k] = x
            if d.get('title'):
                config.append(d)
        import re
        windows = self.all_windows()
        for d in config:
            if d['title']:
                for handle, title in windows.items():
                    if re.match(d['title'], title):
                        rect = win32gui.GetWindowRect(handle)
                        x = int(d.get('x', rect[0]))
                        y = int(d.get('y', rect[1]))
                        w = int(d.get('w', rect[2] - rect[0]))
                        h = int(d.get('h', rect[3] - rect[1]))
                        win32gui.MoveWindow(handle, x, y, w, h, True)
    def all_windows(self):
        windows = {}

        def callback(handle, *args, **kwargs):
            title = win32gui.GetWindowText(handle)
            windows[handle] = title

        win32gui.EnumWindows(callback, None)
        return windows

    @pyqtSlot()
    def list_windows(self):
        windows = self.all_windows()
        for handle, title in windows.items():
            rect = win32gui.GetWindowRect(handle)
            print(handle, ', ', title, ', ', rect)

    @pyqtSlot()
    def load(self):
        try:
            config = []
            with open(self._conf_file, 'r') as f:
                config = yaml.load(f)
        except FileNotFoundError:
            pass
        self._table.setRowCount(0)
        for d in config:
            assert isinstance(d, dict)
            self.add(**d)

    @pyqtSlot()
    def save(self):
        config = []
        for row in range(self._table.rowCount()):
            d = OrderedDict()
            for col, k in enumerate(self._labels):
                x = self.get(row, col)
                d[k] = x or None
            if d['title']:
                config.append(d)
        with open(self._conf_file, 'w') as f:
            yaml.dump(config, f)

    def clear_table(self):
        for row in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                self.set(row, col, None)

    def set(self, row, column, s: str):
        self._table.item(row, column).setData(Qt.DisplayRole, s)

    def get(self, row, column):
        return str(self._table.item(row, column).data(Qt.DisplayRole))

    @pyqtSlot(list)
    def update_table(self, table_data):
        return
        for row in range(self._table.rowCount()):
            for col in range(self._table.columnCount()):
                self.set(row, col, table_data[row][col])

    def snapshot(self):
        img = ImageGrab.grab()


def snapshot():
    pass


def main():
    args = docopt("""
    Usage:
      {f} [options]

    Options:
      --size SIZE  [default: 640x600]
      --config CONFIG  [default: config.yaml]

    """.format(f=sys.argv[0]))
    width, height = args['--size'].split('x')
    width, height = int(width), int(height)
    conf_file = args['--config']

    app = QApplication(sys.argv[1:])

    w = Window(conf_file, width, height)

    def update():
        while True:
            w.updated.emit([[chr(random.randint(40, 50))] * 5] * 20)
            time.sleep(1)

    threading.Thread(target=update, daemon=True).start()
    w.snapshot()

    w.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
