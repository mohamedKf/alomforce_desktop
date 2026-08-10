"""Stock screen — the catalog view, but for physical holdings.

Same table shape as the catalog (thumbnail, profile, description, series) plus
the two things stock is about: the finish (colour) and the amount on hand, with
extra filters for colour, warehouse and availability. Read-only for now; taking
stock in and out comes later.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPixmap
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
from app.views.stock_dialogs import AddStockDialog, MovementDialog

PAGE_SIZE = 50
SEARCH_DEBOUNCE_MS = 300
THUMB_H = 40
THUMB_W = 72

STATUS_COLOR = {'out': '#B3261E', 'low': '#8A6D1F', 'in': '#2E7D32'}


def _status(row):
    qty = row.get('quantity') or 0
    if qty <= 0:
        return 'out'
    if row.get('needs_reorder'):
        return 'low'
    return 'in'


class StockModel(QAbstractTableModel):
    COLUMNS = [
        ('image', 'Image'),
        ('number', 'Profile'),
        ('description', 'Description'),
        ('series', 'Series'),
        ('finish', 'Color'),
        ('length', 'Length'),
        ('quantity', 'Amount'),
        ('warehouse', 'Warehouse'),
        ('status', 'Status'),
    ]

    def __init__(self):
        super().__init__()
        self.rows = []
        self._thumbs = {}

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set_thumb(self, url, pixmap):
        self._thumbs[url] = pixmap
        for r, row in enumerate(self.rows):
            if row.get('section_image') == url:
                idx = self.index(r, 0)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])

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

        if role == Qt.DecorationRole and key == 'image':
            return self._thumbs.get(row.get('section_image'))
        if role == Qt.DisplayRole:
            return self._display(row, key)
        if role == Qt.FontRole and key in ('number', 'quantity'):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.TextAlignmentRole and key in ('length', 'quantity'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and key in ('quantity', 'status'):
            return QColor(STATUS_COLOR[_status(row)])
        return None

    @staticmethod
    def _display(row, key):
        if key == 'image':
            return None
        if key == 'series':
            return ', '.join(row.get('series_codes') or []) or '—'
        if key == 'finish':
            return row.get('finish') or '—'
        if key == 'length':
            mm = row.get('length_mm')
            return f'{mm / 1000:g} m' if mm else '—'
        if key == 'quantity':
            return str(row.get('quantity') or 0)
        if key == 'status':
            return {'out': t('Out of stock'), 'low': t('Low'),
                    'in': t('In stock')}[_status(row)]
        return row.get(key) or '—'

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class StockView(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.page = 1
        self.total = 0
        self._request_id = 0
        self._role_data = []
        self._thumb_requested = set()
        self.setObjectName('Canvas')
        self._build()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.reload)

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel(t('Stock'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        self.receive_btn = QPushButton(t('Receive'), objectName='Ghost')
        self.pick_btn = QPushButton(t('Pick'), objectName='Ghost')
        self.adjust_btn = QPushButton(t('Adjust'), objectName='Ghost')
        self.add_btn = QPushButton(t('Add stock item'))
        self.receive_btn.clicked.connect(lambda: self._move('receive'))
        self.pick_btn.clicked.connect(lambda: self._move('pick'))
        self.adjust_btn.clicked.connect(lambda: self._move('adjust'))
        self.add_btn.clicked.connect(self._add_stock)
        for btn in (self.receive_btn, self.pick_btn, self.adjust_btn):
            btn.setEnabled(False)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addWidget(self.receive_btn)
        header.addWidget(self.pick_btn)
        header.addWidget(self.adjust_btn)
        header.addSpacing(8)
        header.addWidget(self.add_btn)

        self.search = QLineEdit(placeholderText=t('Search profiles'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self._on_search_typed)

        self.series = QComboBox()
        self.role = QComboBox()
        self.finish = QComboBox()
        self.warehouse = QComboBox()
        self.availability = QComboBox()
        for combo in (self.series, self.role, self.finish, self.warehouse,
                      self.availability):
            combo.setMinimumWidth(130)
            combo.currentIndexChanged.connect(self.reload_from_first_page)

        self.clear = QPushButton(t('Clear filters'), objectName='Ghost')
        self.clear.clicked.connect(self._clear_filters)

        filters = QHBoxLayout()
        filters.setSpacing(9)
        for widget in (self.search, self.series, self.role, self.finish,
                       self.warehouse, self.availability):
            filters.addWidget(widget)
        filters.addWidget(self.clear)
        filters.addStretch()

        self.model = StockModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(THUMB_H + 8)
        self.table.setIconSize(QSize(THUMB_W, THUMB_H))

        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # image
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # number
        head.setSectionResizeMode(2, QHeaderView.Stretch)            # description
        for column in range(3, len(StockModel.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)
        self.table.selectionModel().selectionChanged.connect(self._update_actions)
        self.table.doubleClicked.connect(lambda _i: self._move('receive'))

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        self.prev = QPushButton('‹', objectName='Ghost')
        self.next = QPushButton('›', objectName='Ghost')
        self.page_label = QLabel('', objectName='Muted')
        self.prev.setFixedWidth(40)
        self.next.setFixedWidth(40)
        self.prev.clicked.connect(lambda: self._step_page(-1))
        self.next.clicked.connect(lambda: self._step_page(1))
        pager = QHBoxLayout()
        pager.addStretch()
        pager.addWidget(self.prev)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addLayout(pager)

    # -- filter options --------------------------------------------------

    def load_filter_options(self):
        for combo, label in ((self.series, 'All series'), (self.role, 'All types'),
                              (self.finish, 'All colors'),
                              (self.warehouse, 'All warehouses')):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(t(label), None)
            combo.blockSignals(False)
        self.availability.blockSignals(True)
        self.availability.clear()
        for value, label in ((None, 'Any amount'), ('in', 'In stock'),
                             ('low', 'Low'), ('out', 'Out of stock')):
            self.availability.addItem(t(label), value)
        self.availability.blockSignals(False)

        self.api.get('catalog/series/', on_ok=self._on_series, on_error=self._on_error)
        self.api.get('catalog/listings/roles/', on_ok=self._on_roles,
                     on_error=self._on_error)
        self.api.get('stock/options/', on_ok=self._on_options, on_error=self._on_error)

    def _on_series(self, payload):
        self.series.blockSignals(True)
        for item in payload or []:
            self.series.addItem(item['code'], item['code'])
        self.series.blockSignals(False)

    def _on_roles(self, payload):
        self._role_data = [i for i in (payload or []) if i.get('count')]
        self._fill_roles()

    def _fill_roles(self):
        selected = self.role.currentData()
        self.role.blockSignals(True)
        self.role.clear()
        self.role.addItem(t('All types'), None)
        for item in self._role_data:
            self.role.addItem(t(item['label']), item['value'])
        if selected:
            self.role.setCurrentIndex(max(0, self.role.findData(selected)))
        self.role.blockSignals(False)

    def _on_options(self, payload):
        payload = payload or {}
        self.finish.blockSignals(True)
        for finish in payload.get('finishes', []):
            self.finish.addItem(finish, finish)
        self.finish.blockSignals(False)
        self.warehouse.blockSignals(True)
        for wh in payload.get('warehouses', []):
            self.warehouse.addItem(wh['name'], wh['id'])
        self.warehouse.blockSignals(False)

    # -- data ------------------------------------------------------------

    def _on_search_typed(self):
        self.page = 1
        self._debounce.start()

    def reload_from_first_page(self):
        self.page = 1
        self.reload()

    def reload(self):
        params = {'page': self.page}
        if text := self.search.text().strip():
            params['search'] = text
        if series := self.series.currentData():
            params['series'] = series
        if role := self.role.currentData():
            params['role'] = role
        if finish := self.finish.currentData():
            params['finish'] = finish
        if warehouse := self.warehouse.currentData():
            params['warehouse'] = warehouse
        if availability := self.availability.currentData():
            params['availability'] = availability

        self._request_id += 1
        request_id = self._request_id
        self._set_status(t('Loading…'))
        self.api.get('stock/', params,
                     on_ok=lambda p: self._on_rows(p, request_id),
                     on_error=lambda e: self._on_error(e, request_id))

    def _on_rows(self, payload, request_id=None):
        if request_id is not None and request_id != self._request_id:
            return
        rows = payload.get('results', []) if isinstance(payload, dict) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else 0
        self.model.set_rows(rows)
        if rows:
            self.status.hide()
        else:
            self._set_status(t('No stock matches these filters.'))
        self.count.setText(f'{self.total:,} {t("items")}')
        self._update_pager()
        self._load_thumbs()

    def _on_error(self, error, request_id=None):
        if request_id is not None and request_id != self._request_id:
            return
        self.model.set_rows([])
        self._set_status(error.message)
        self.count.setText('')

    def _set_status(self, message):
        self.status.setText(message)
        self.status.show()

    # -- thumbnails ------------------------------------------------------

    def _load_thumbs(self):
        for row in self.model.rows:
            url = row.get('section_image')
            if not url or url in self.model._thumbs or url in self._thumb_requested:
                continue
            self._thumb_requested.add(url)
            self.api.fetch_binary(
                url,
                on_ok=lambda data, u=url: self._on_thumb(u, data),
                on_error=lambda _e, u=url: self._thumb_requested.discard(u))

    def _on_thumb(self, url, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.model.set_thumb(url, pixmap.scaled(
                THUMB_W, THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # -- paging ----------------------------------------------------------

    def _page_count(self):
        return max(1, -(-self.total // PAGE_SIZE))

    def _step_page(self, delta):
        target = self.page + delta
        if 1 <= target <= self._page_count():
            self.page = target
            self.reload()

    def _update_pager(self):
        pages = self._page_count()
        self.page_label.setText(f'{self.page} / {pages}')
        self.prev.setEnabled(self.page > 1)
        self.next.setEnabled(self.page < pages)
        visible = self.total > PAGE_SIZE
        for widget in (self.prev, self.next, self.page_label):
            widget.setVisible(visible)

    def _clear_filters(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        for combo in (self.series, self.role, self.finish, self.warehouse,
                      self.availability):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.reload_from_first_page()

    # -- actions ---------------------------------------------------------

    def _selected_row(self):
        index = self.table.currentIndex()
        return self.model.row_at(index) if index.isValid() else None

    def _update_actions(self, *_):
        has = self._selected_row() is not None
        for btn in (self.receive_btn, self.pick_btn, self.adjust_btn):
            btn.setEnabled(has)

    def _move(self, mode):
        row = self._selected_row()
        if not row:
            return
        if MovementDialog(self.api, row, mode, self).exec():
            self.reload()

    def _add_stock(self):
        if AddStockDialog(self.api, self).exec():
            self.reload()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Stock'))
        self.receive_btn.setText(t('Receive'))
        self.pick_btn.setText(t('Pick'))
        self.adjust_btn.setText(t('Adjust'))
        self.add_btn.setText(t('Add stock item'))
        self.search.setPlaceholderText(t('Search profiles'))
        self.clear.setText(t('Clear filters'))
        for combo, label in ((self.series, 'All series'), (self.role, 'All types'),
                             (self.finish, 'All colors'),
                             (self.warehouse, 'All warehouses')):
            if combo.count():
                combo.setItemText(0, t(label))
        self._fill_roles()
        self.count.setText(f'{self.total:,} {t("items")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(StockModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
