import pickle
from typing import List, Union

from PyQt5.QtCore import *
from PyQt5.QtWidgets import *

from model import ConfigurableMixin


class Splitter(ConfigurableMixin, QSplitter):
    def splitter_pos(self, index: int):
        pos = 0
        for i, size in enumerate(self.sizes()):
            if i >= index:
                break
            pos += size
        else:
            raise Exception('overflow {}'.format(index))
        return pos

    @pyqtSlot(int, int)
    def update_splitter_position(self, pos, index):
        if pos != self.splitter_pos(index):
            self.moveSplitter(pos, index)

    def sync_splitter_pos(self, from_splitter: QSplitter):
        if self is not from_splitter:
            from_splitter.splitterMoved.connect(self.update_splitter_position)


class TableView(ConfigurableMixin, QTableWidget):
    FONT_P = 8
    ROW_H = 14

    def __init__(self, row: int = 0, labels: List[str] = None, *, name: str):
        labels = tuple(labels or [])
        super().__init__(0, len(labels), name=name)
        self.labels = labels

        self.resize_row(row)
        self.setContentsMargins(0, 0, 0, 0)
        self.setHorizontalHeaderLabels(labels)

        # set font
        font = self.font()
        font.setPointSize(self.FONT_P)
        self.setFont(font)
        font = self.verticalHeader().font()
        font.setPointSize(self.FONT_P - 2)
        self.verticalHeader().setFont(font)

    def sync_horizontal_header(self, from_table: QTableWidget):
        from_table.horizontalHeader().sectionResized.connect(self.update_horizontal_section_size)

    @pyqtSlot(int, int, int)
    def update_horizontal_section_size(self, index: int, old_size: int, new_size: int):
        header = self.horizontalHeader()
        if header.sectionSize(index) != new_size:
            header.resizeSection(index, new_size)

    @pyqtSlot()
    def dump_items(self, config: dict = None):
        config = self.config if config is None else config
        items = []
        for row in range(self.rowCount()):
            d = {}
            for label, col in zip(self.labels, range(self.columnCount())):
                item = self.item(row, col)
                if item:
                    bg = item.data(Qt.BackgroundRole)
                    d = dict(row=row, col=col, text=item.text(), flags=item.flags(),
                             checked=item.checkState(),
                             bg=bg)
            items.append(d)
        config['items'] = pickle.dumps(items)

    @pyqtSlot()
    def load_items(self, config: dict = None):
        config = self.config if config is None else config
        items = config.setdefault('items', [])
        if items:
            items = pickle.loads(items)
            for d in items:
                row = d['row']
                self.resize_row(row + 1)
                self.set_item(row, d['col'], value=d['text'], flags=d['flags'], checked=d['checked'], bg=d['bg'])

    def new_item(self, row: int, col: int) -> QTableWidgetItem:
        return QTableWidgetItem()

    def resize_row(self, row_n: int):
        current_row_n = self.rowCount()
        self.setRowCount(row_n)
        for row in range(current_row_n, row_n):
            self.setRowHeight(row, self.ROW_H)
            for col in range(len(self.labels)):
                self.setItem(row, col, self.new_item(row, col))

    def set_widget(self, row: int, col: Union[int, str], widget: QWidget):
        if isinstance(col, str):
            try:
                col = self.labels.index(col)
            except ValueError:
                return False
        if row >= self.rowCount() or col >= self.columnCount():
            return False
        self.setCellWidget(row, col, widget)
        return True

    def set_item(self, row: int, col: Union[int, str], value=None, bg=None, flags=None, checked=None, widget=None):
        if isinstance(col, str):
            try:
                col = self.labels.index(col)
            except ValueError:
                return False
        if row >= self.rowCount() or col >= self.columnCount():
            return False
        if not self.item(row, col):
            self.setItem(row, col, QTableWidgetItem())
        if value is not None:
            self.item(row, col).setData(Qt.DisplayRole, value)

        flags = flags if flags is not None else Qt.ItemIsEnabled
        self.item(row, col).setData(Qt.BackgroundRole, bg)
        self.item(row, col).setData(Qt.DisplayRole, value)
        self.item(row, col).setFlags(flags)
        if checked is not None:
            self.item(row, col).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        if widget is not None:
            self.setCellWidget(row, col, widget)
        return True


class DoubleSpinBox(ConfigurableMixin, QDoubleSpinBox):
    def __init__(self, *, value: float = None, min: float = None, max: float = None, decimals: int = None,
                 single_step: float = None, suffix: str = None, name: str):
        super().__init__(name=name)
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
