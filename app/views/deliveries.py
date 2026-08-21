"""Deliveries screen — what has arrived, who took it, and the signed note.

Not the order list filtered to delivered: that answers "what did we sell", and
this answers "did it get there, and who signed for it". The signature, the
name and phone of whoever received it, and the delivery note are the record
the office reaches for when a client says a bar is missing -- and none of that
is visible on the order list without opening each order in turn.

Dated by arrival rather than by order date. An order placed in March and
delivered in August is an August delivery, and looking for it under March is
how people lose an afternoon.
"""

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
from app.views.order_dialog import OrderDialog, _open_file

SEARCH_DEBOUNCE_MS = 300


class DeliveryModel(QAbstractTableModel):
    COLUMNS = [
        ('number', 'Order'),
        ('client_name', 'Client'),
        ('delivered_on', 'Delivered'),
        ('recipient_name', 'Signed by'),
        ('recipient_phone', 'Phone'),
        ('total_weight_kg', 'Weight kg'),
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
            if key == 'delivered_on':
                # Date and time to the minute: two deliveries to the same
                # client on one day are told apart by the hour, not the date.
                return (row.get('delivered_on') or '').replace('T', ' ')[:16]
            if key == 'total_weight_kg':
                try:
                    return f"{float(row.get('total_weight_kg') or 0):g}"
                except (TypeError, ValueError):
                    return '—'
            if key == 'recipient_name':
                # An unsigned delivery is a real state, not missing data.
                return row.get('recipient_name') or t('Not signed')
            return row.get(key) or '—'
        if role == Qt.FontRole and key == 'number':
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ForegroundRole and key == 'recipient_name':
            if not row.get('recipient_name'):
                return QColor('#B45309')
        if role == Qt.TextAlignmentRole and key == 'total_weight_kg':
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class DeliveriesView(QWidget):
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
        self.load_filter_options()

    def _build(self):
        self.title = QLabel(t('Deliveries'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')
        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()

        self.search = QLineEdit(placeholderText=t('Search deliveries'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(lambda: self._debounce.start())

        self.client_filter = QComboBox()
        self.client_filter.setMinimumWidth(200)
        self.client_filter.setEditable(True)
        self.client_filter.setInsertPolicy(QComboBox.NoInsert)
        self.client_filter.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.client_filter.completer().setFilterMode(Qt.MatchContains)
        self.client_filter.addItem(t('All clients'), None)
        self.client_filter.currentIndexChanged.connect(self.reload)

        self.year = QComboBox()
        self.year.setMinimumWidth(120)
        self.year.addItem(t('All years'), None)
        self.year.currentIndexChanged.connect(self.reload)

        self.month = QComboBox()
        self.month.setMinimumWidth(140)
        self._fill_months()
        self.month.currentIndexChanged.connect(self.reload)

        self.clear_btn = QPushButton(t('Clear filters'), objectName='Ghost')
        self.clear_btn.clicked.connect(self._clear_filters)

        filters = QHBoxLayout()
        for widget in (self.search, self.client_filter, self.year, self.month,
                       self.clear_btn):
            filters.addWidget(widget)
        filters.addStretch()

        self.model = DeliveryModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._open_order)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        # Acting on the selected row. Disabled until something is selected,
        # rather than hidden, so the actions are discoverable from the start.
        self.note_btn = QPushButton(t('Delivery note'))
        self.note_btn.clicked.connect(self._open_note)
        self.open_btn = QPushButton(t('Open order'), objectName='Ghost')
        self.open_btn.clicked.connect(lambda: self._open_order(None))
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.open_btn)
        actions.addWidget(self.note_btn)
        self._on_selection()

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
        layout.addLayout(actions)

    # -- filters ----------------------------------------------------------

    def _fill_months(self):
        self.month.blockSignals(True)
        keep = self.month.currentData()
        self.month.clear()
        self.month.addItem(t('All months'), None)
        for number in range(1, 13):
            self.month.addItem(month_name(number), number)
        if keep is not None and (idx := self.month.findData(keep)) >= 0:
            self.month.setCurrentIndex(idx)
        self.month.blockSignals(False)

    def load_filter_options(self):
        # delivered=true: the years that have deliveries, not the years that
        # have orders -- the two differ as soon as anything is outstanding.
        self.api.get('orders/years/', {'delivered': 'true'},
                     on_ok=self._on_years, on_error=lambda _e: None)
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
        for widget in (self.client_filter, self.year, self.month):
            widget.blockSignals(True)
            widget.setCurrentIndex(0)
            widget.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.reload()

    def _filtering(self):
        return bool(self.search.text().strip()
                    or self.client_filter.currentData() is not None
                    or self.year.currentData() is not None
                    or self.month.currentData() is not None)

    # -- loading ----------------------------------------------------------

    def reload(self):
        params = {'done': 'true'}
        if text := self.search.text().strip():
            params['search'] = text
        if (client := self.client_filter.currentData()) is not None:
            params['client'] = client
        if (year := self.year.currentData()) is not None:
            params['year'] = year
        if (month := self.month.currentData()) is not None:
            params['month'] = month
        self.status_label.setText(t('Loading…'))
        self.status_label.show()
        self.api.get('orders/deliveries/', params, on_ok=self._on_rows,
                     on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload if isinstance(payload, list) else payload.get('results', [])
        self.total = len(rows)
        self.model.set_rows(rows)
        if rows:
            self.status_label.hide()
        else:
            self.status_label.setText(
                t('No deliveries match these filters.') if self._filtering()
                else t('Nothing delivered yet.'))
            self.status_label.show()
        self.count.setText(f'{self.total:,} {t("delivered")}')
        self._on_selection()

    def _on_error(self, error):
        self.model.set_rows([])
        self.status_label.setText(getattr(error, 'message', str(error)))
        self.status_label.show()
        self._on_selection()

    # -- acting on a row --------------------------------------------------

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        return self.model.row_at(rows[0]) if rows else None

    def _on_selection(self, *_):
        has = self._selected() is not None
        self.note_btn.setEnabled(has)
        self.open_btn.setEnabled(has)

    def _open_order(self, index):
        row = self.model.row_at(index) if index is not None else self._selected()
        if not row:
            return
        dialog = OrderDialog(self.api, self.session, order=row, parent=self)
        dialog.exec()
        self.reload()

    def _open_note(self):
        """Fetch the signed delivery note and hand it to the system viewer."""
        row = self._selected()
        if not row:
            return
        self.note_btn.setEnabled(False)
        self.note_btn.setText(t('Opening…'))

        def done(path):
            self._reset_note_btn()
            _open_file(path)

        def failed(error):
            self._reset_note_btn()
            self.status_label.setText(getattr(error, 'message', str(error)))
            self.status_label.show()

        self.api.download_pdf(f'orders/{row["id"]}/delivery_note/',
                              f'{row.get("number", "delivery")}_delivery.pdf',
                              on_ok=done, on_error=failed)

    def _reset_note_btn(self):
        self.note_btn.setEnabled(self._selected() is not None)
        self.note_btn.setText(t('Delivery note'))

    def retranslate(self):
        self.title.setText(t('Deliveries'))
        self.search.setPlaceholderText(t('Search deliveries'))
        self.clear_btn.setText(t('Clear filters'))
        self.note_btn.setText(t('Delivery note'))
        self.open_btn.setText(t('Open order'))
        self.count.setText(f'{self.total:,} {t("delivered")}' if self.total else '')
        self._fill_months()
        self.year.setItemText(0, t('All years'))
        self.client_filter.setItemText(0, t('All clients'))
        self.model.headerDataChanged.emit(Qt.Horizontal, 0,
                                          len(DeliveryModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
