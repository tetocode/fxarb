from PyQt5.QtCore import *

import borg


class Signals(QObject):
    # signals
    update_instruments = pyqtSignal(set)
    update_services = pyqtSignal(set)
    update_selected_instruments = pyqtSignal(set)
    update_disabled_services = pyqtSignal(set)
    update_accounts = pyqtSignal(list)
    update_filters = pyqtSignal(dict)
    update_prices = pyqtSignal(list)
    update_signals = pyqtSignal(list)
    update_spreads = pyqtSignal(list)
    play_sound = pyqtSignal(str)
    refresh = pyqtSignal()
    dump_config = pyqtSignal()
    load_config = pyqtSignal()


class GlobalSignal(borg.Borg):
    _shared_state = dict(_initialized=False)

    def __init__(self):
        if not self._initialized:
            super().__init__()
            self.lazy_list = []
            self._signals = Signals()
            self._initialized = True

    def __getattr__(self, item):
        return getattr(self._signals, item)

    def call_lazy(self):
        for f in self.lazy_list:
            f()
        self.lazy_list.clear()

    def add_lazy(self, f):
        self.lazy_list.append(f)
