"""Orders screen — list of client orders; open one to edit or print."""

from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.order_dialog import OrderDialog

SEARCH_DEBOUNCE_MS = 300

STATUS_COLOR = {
    'draft': '#6b7280', 'submitted': '#b45309', 'confirmed': '#2F6F8F',
    'picking': '#7c3aed', 'ready': '#0e7490', 'delivered': '#15803d',
    'cancelled': '#b91c1c',
}
STATUSES = [
    (None, 'All statuses'), ('draft', 'Draft'), ('submitted', 'Submitted'),
    ('confirmed', 'Confirmed'), ('picking', 'Picking'), ('ready', 'Ready'),
    ('delivered', 'Delivered'), ('cancelled', 'Cancelled'),
]


class OrderModel(QAbstractTableModel):
    COLUMNS = [
        ('number', 'Order'),
        ('client_name', 'Client'),
        ('ordered_at', 'Date'),
        ('total_weight_kg', 'Weight kg'),
        ('total', 'Total'),
        ('status_display', 'Status'),
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
        if role == Qt.DisplayRole:
            if key == 'ordered_at':
                return (row.get('ordered_at') or '')[:10]
            if key == 'total':
                return f"₪ {Decimal(row.get('total') or 0):,.2f}"
            if key == 'total_weight_kg':
                return f"{Decimal(row.get('total_weight_kg') or 0):g}"
            if key == 'status_display':
                return t(row.get('status_display') or '')
            return row.get(key) or '—'
        if role == Qt.FontRole and key in ('number', 'total'):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.TextAlignmentRole and key in ('total', 'total_weight_kg'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and key == 'status_display':
            return QColor(STATUS_COLOR.get(row.get('status'), '#6b7280'))
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class OrdersView(QWidget):
    def __init__(self, api, session=None):
        super().__init__()
        self.api = api
        self.session = session
        self.total = 0
        self.setObjectName('Canvas')
        self._build()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.reload)

    def _build(self):
        self.title = QLabel(t('Orders'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')
        self.add_btn = QPushButton(t('New order'))
        self.add_btn.clicked.connect(self._add)
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addWidget(self.add_btn)

        self.search = QLineEdit(placeholderText=t('Search orders'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(lambda: self._debounce.start())
        self.status = QComboBox()
        self.status.setMinimumWidth(160)
        for value, label in STATUSES:
            self.status.addItem(t(label), value)
        self.status.currentIndexChanged.connect(self.reload)
        filters = QHBoxLayout()
        filters.addWidget(self.search)
        filters.addWidget(self.status)
        filters.addStretch()

        self.model = OrderModel()
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
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status_label = QLabel('', objectName='Muted')
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addLayout(filters)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table, 1)

    def reload(self):
        params = {}
        if text := self.search.text().strip():
            params['search'] = text
        if status := self.status.currentData():
            params['status'] = status
        self.status_label.setText(t('Loading…'))
        self.status_label.show()
        self.api.get('orders/', params, on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else len(rows)
        self.model.set_rows(rows)
        if rows:
            self.status_label.hide()
        else:
            self.status_label.setText(t('No orders yet.'))
        self.count.setText(f'{self.total:,} {t("orders")}')

    def _on_error(self, error):
        self.model.set_rows([])
        self.status_label.setText(error.message)
        self.status_label.show()

    def _add(self):
        dialog = OrderDialog(self.api, self.session, parent=self)
        dialog.exec()
        self.reload()

    def _edit(self, index):
        row = self.model.row_at(index)
        if row:
            dialog = OrderDialog(self.api, self.session, order=row, parent=self)
            dialog.exec()
            self.reload()

    def retranslate(self):
        self.title.setText(t('Orders'))
        self.search.setPlaceholderText(t('Search orders'))
        self.add_btn.setText(t('New order'))
        self.count.setText(f'{self.total:,} {t("orders")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(OrderModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
