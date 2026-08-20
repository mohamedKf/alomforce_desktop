"""Orders screen — list of client orders; open one to edit or print."""

from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import month_name, t
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
        # Both requests are independent of the order list itself, so they run
        # alongside the reload the shell triggers rather than blocking it.
        self.load_filter_options()

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

        # Year, month and client. The year list comes from the orders that
        # exist rather than a fixed range, so it is never half empty and never
        # runs out.
        self.year = QComboBox()
        self.year.setMinimumWidth(120)
        self.year.addItem(t('All years'), None)
        self.year.currentIndexChanged.connect(self.reload)

        self.month = QComboBox()
        self.month.setMinimumWidth(140)
        self._fill_months()
        self.month.currentIndexChanged.connect(self.reload)

        # Editable so a long client list can be typed at instead of scrolled.
        self.client_filter = QComboBox()
        self.client_filter.setMinimumWidth(200)
        self.client_filter.setEditable(True)
        self.client_filter.setInsertPolicy(QComboBox.NoInsert)
        self.client_filter.completer().setCompletionMode(
            QCompleter.PopupCompletion)
        self.client_filter.completer().setFilterMode(Qt.MatchContains)
        self.client_filter.addItem(t('All clients'), None)
        self.client_filter.currentIndexChanged.connect(self.reload)

        self.clear_btn = QPushButton(t('Clear filters'), objectName='Ghost')
        self.clear_btn.clicked.connect(self._clear_filters)

        filters = QHBoxLayout()
        filters.addWidget(self.search)
        filters.addWidget(self.status)
        filters.addWidget(self.client_filter)
        filters.addWidget(self.year)
        filters.addWidget(self.month)
        filters.addWidget(self.clear_btn)
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

    def _fill_months(self):
        """All months, then the twelve, named in the current language."""
        self.month.blockSignals(True)
        keep = self.month.currentData()
        self.month.clear()
        self.month.addItem(t('All months'), None)
        for number in range(1, 13):
            self.month.addItem(month_name(number), number)
        if keep is not None:
            self.month.setCurrentIndex(self.month.findData(keep))
        self.month.blockSignals(False)

    def load_filter_options(self):
        """Fill the year and client pickers. Failures leave them as 'All'."""
        self.api.get('orders/years/', on_ok=self._on_years,
                     on_error=lambda _e: None)
        self.api.get('clients/', {'active': 'true'}, on_ok=self._on_clients,
                     on_error=lambda _e: None)

    def _on_years(self, payload):
        keep = self.year.currentData()
        self.year.blockSignals(True)
        self.year.clear()
        self.year.addItem(t('All years'), None)
        for y in payload.get('years', []):
            self.year.addItem(str(y), y)
        if keep is not None and (idx := self.year.findData(keep)) >= 0:
            self.year.setCurrentIndex(idx)
        self.year.blockSignals(False)

    def _on_clients(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        keep = self.client_filter.currentData()
        self.client_filter.blockSignals(True)
        self.client_filter.clear()
        self.client_filter.addItem(t('All clients'), None)
        for c in (rows or []):
            self.client_filter.addItem(c['name'], c['id'])
        if keep is not None and (idx := self.client_filter.findData(keep)) >= 0:
            self.client_filter.setCurrentIndex(idx)
        self.client_filter.blockSignals(False)

    def _clear_filters(self):
        for widget in (self.status, self.year, self.month, self.client_filter):
            widget.blockSignals(True)
            widget.setCurrentIndex(0)
            widget.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.reload()

    def reload(self):
        params = {}
        if text := self.search.text().strip():
            params['search'] = text
        if status := self.status.currentData():
            params['status'] = status
        if (client := self.client_filter.currentData()) is not None:
            params['client'] = client
        if (year := self.year.currentData()) is not None:
            params['year'] = year
        if (month := self.month.currentData()) is not None:
            params['month'] = month
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
            # "None yet" and "none this March" are different problems, and
            # only one of them is solved by clearing a filter.
            self.status_label.setText(
                t('No orders match these filters.') if self._filtering()
                else t('No orders yet.'))
            self.status_label.show()
        self.count.setText(f'{self.total:,} {t("orders")}')

    def _filtering(self):
        """Is anything actually narrowing the list right now?"""
        return bool(self.search.text().strip()
                    or self.status.currentData()
                    or self.client_filter.currentData() is not None
                    or self.year.currentData() is not None
                    or self.month.currentData() is not None)

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
        self.clear_btn.setText(t('Clear filters'))
        self.count.setText(f'{self.total:,} {t("orders")}' if self.total else '')

        # The pickers hold translated text, so they are rebuilt rather than
        # relabelled -- keeping whatever was selected.
        self.status.blockSignals(True)
        chosen = self.status.currentData()
        self.status.clear()
        for value, label in STATUSES:
            self.status.addItem(t(label), value)
        self.status.setCurrentIndex(max(self.status.findData(chosen), 0))
        self.status.blockSignals(False)

        self._fill_months()
        self.year.setItemText(0, t('All years'))
        self.client_filter.setItemText(0, t('All clients'))

        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(OrderModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
