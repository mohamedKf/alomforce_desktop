"""Warehouses screen — list, add and edit warehouses (and their map pins)."""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.warehouse_dialog import WarehouseDialog


class WarehouseModel(QAbstractTableModel):
    COLUMNS = [
        ('name', 'Name'),
        ('city', 'City'),
        ('location_count', 'Locations'),
        ('map', 'On map'),
    ]

    def __init__(self):
        super().__init__()
        self.rows = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return t(self.COLUMNS[section][1])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.COLUMNS[index.column()][0]
        placed = row.get('latitude') is not None and row.get('longitude') is not None
        if role == Qt.DisplayRole:
            if key == 'map':
                return t('On map') if placed else t('—')
            if key == 'location_count':
                return str(row.get('location_count') or 0)
            return row.get(key) or '—'
        if role == Qt.FontRole and key == 'name':
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ForegroundRole and key == 'map':
            return QColor('#2f6fb0') if placed else QColor('#9aa5b1')
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class WarehousesView(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.total = 0
        self.setObjectName('Canvas')
        self._build()

    def _build(self):
        self.title = QLabel(t('Warehouses'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')
        self.add_btn = QPushButton(t('Add warehouse'))
        self.add_btn.clicked.connect(self._add)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addWidget(self.add_btn)

        self.model = WarehouseModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._edit)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(WarehouseModel.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)

    def reload(self):
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('warehouses/', on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self.total = len(rows)
        self.model.set_rows(rows)
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No warehouses yet.'))
        self.count.setText(f'{self.total:,} {t("warehouses")}')

    def _on_error(self, error):
        self.model.set_rows([])
        self.status.setText(error.message)
        self.status.show()

    def _add(self):
        if WarehouseDialog(self.api, parent=self).exec():
            self.reload()

    def _edit(self, index):
        row = self.model.row_at(index)
        if row and WarehouseDialog(self.api, warehouse=row, parent=self).exec():
            self.reload()

    def retranslate(self):
        self.title.setText(t('Warehouses'))
        self.add_btn.setText(t('Add warehouse'))
        self.count.setText(f'{self.total:,} {t("warehouses")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(WarehouseModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
