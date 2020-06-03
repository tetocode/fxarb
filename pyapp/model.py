import copy
from collections.abc import MutableMapping
from typing import Set, Dict, List

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

import borg
from globalsignal import GlobalSignal


class Config(borg.Borg, MutableMapping):
    _shared_state = dict(_initialized=False)

    def __init__(self):
        if not self._initialized:
            super().__init__()
            self._dict = dict()
            self._signals = GlobalSignal()
            self._initialized = True

    def __getitem__(self, item):
        return self._dict[item]

    def __setitem__(self, key, value):
        self._dict[key] = value

    def __delitem__(self, key):
        del self._dict[key]

    def __iter__(self):
        return iter(self._dict)

    def __len__(self):
        return len(self._dict)

    def __str__(self):
        return str(self._dict)

    def __repr__(self):
        return repr(self._dict)

    def __getattr__(self, item: str):
        if item.startswith('update_'):
            data_str = item[len('update_'):]

            def update(*args):
                if not args:
                    args = (copy.deepcopy(getattr(self, data_str)),)
                return getattr(self._signals, item).emit(*args)

            return update
        else:
            return getattr(self._signals, item)

    @property
    def filters(self) -> Dict[str, dict]:
        return self.setdefault('filters', {})

    @property
    def instruments(self) -> Set[str]:
        return self.setdefault('instruments', {'USD/JPY', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY'})

    @property
    def selected_instruments(self) -> Set[str]:
        return self.setdefault('selected_instruments', set())

    @property
    def services(self) -> Set[str]:
        return self.setdefault('services', set())

    @property
    def disabled_services(self) -> Set[str]:
        return self.setdefault('disabled_services', set())

    @property
    def accounts(self) -> Dict[str, dict]:
        return self.setdefault('accounts', {})

class ConfigurableMixin:
    def __init__(self, *args, name, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        if name:
            GlobalSignal().dump_config.connect(self.dump_config)
            GlobalSignal().load_config.connect(self.load_config)

    @property
    def config(self):
        if self.name:
            return Config().setdefault(self.name, {})
        else:
            return {}

    @pyqtSlot()
    def dump_config(self, config: dict = None):
        config = self.config if config is None else config
        if isinstance(self, QMainWindow):
            config['x'] = self.pos().x()
            config['y'] = self.pos().y()
            config['width'] = self.width()
            config['height'] = self.height()
        if isinstance(self, QHeaderView):
            config['sizes'] = [self.sectionSize(i) for i in range(self.count())]
        if isinstance(self, QTableWidget):
            ConfigurableMixin.dump_config(self.horizontalHeader(), config.setdefault('horizontal_header', {}))
            ConfigurableMixin.dump_config(self.verticalHeader(), config.setdefault('vertical_header', {}))
        if isinstance(self, QComboBox):
            config['selected_text'] = self.currentText()
        if isinstance(self, QSplitter):
            config['sizes'] = self.sizes()
        if isinstance(self, QDoubleSpinBox):
            config['value'] = self.value()
            config['min'] = self.minimum()
            config['max'] = self.maximum()
            config['decimals'] = self.decimals()
            config['single_step'] = self.singleStep()
            config['suffix'] = self.suffix()
        if isinstance(self, QTabBar):
            config['tabs'] = list(filter(str, [self.tabText(i) for i in range(self.count())]))
            config['tab_i'] = self.currentIndex()

    @pyqtSlot()
    def load_config(self, config: dict = None):
        config = self.config if config is None else config
        if isinstance(self, QMainWindow):
            x, y = config.get('x'), config.get('y')
            if x is not None and y is not None:
                self.move(x, y)
            w, h = config.get('width'), config.get('height')
            if w is not None and h is not None:
                self.resize(w, h)
        if isinstance(self, QHeaderView):
            for i, size in enumerate(config.get('sizes', [])):
                self.resizeSection(i, size)
        if isinstance(self, QTableWidget):
            ConfigurableMixin.load_config(self.horizontalHeader(), config.setdefault('horizontal_header', {}))
            ConfigurableMixin.load_config(self.verticalHeader(), config.setdefault('vertical_header', {}))
        if isinstance(self, QComboBox):
            self.addItem(config.get('selected_text', ''))
            self.setCurrentText(config.get('selected_text', ''))
            self.activated[str].emit(self.currentText())
        if isinstance(self, QSplitter):
            if config.get('sizes'):
                self.setSizes(config['sizes'])
        if isinstance(self, QDoubleSpinBox):
            if config.get('value') is not None:
                self.setValue(config.get('value'))
            if config.get('min') is not None:
                self.setMinimum(config.get('min'))
            if config.get('max') is not None:
                self.setMaximum(config.get('max'))
            if config.get('decimals') is not None:
                self.setDecimals(config.get('decimals'))
            if config.get('single_step') is not None:
                self.setSingleStep(config.get('single_step'))
            if 'suffix' in config:
                self.setSuffix(config['suffix'])
        if isinstance(self, QTabBar):
            for i, text in enumerate(config.get('tabs', [])):
                self.insertTab(i, text)
            self.setCurrentIndex(config.get('tab_i', 0))
