"""Clients screen — the office manages client businesses here.

A searchable table; double-click a row (or Add client) to open the full editor
with the map. The mirror image of the Users screen, but for businesses.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.client_dialog import ClientDialog
from app.views.client_statement import ClientStatementView

SEARCH_DEBOUNCE_MS = 300


class ClientModel(QAbstractTableModel):
    COLUMNS = [
        ('name', 'Business name'),
        ('city', 'City'),
        ('tax_id', 'Tax ID'),
        ('phone', 'Phone'),
        ('contact_count', 'Contacts'),
        ('location', 'Location'),
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
            if key == 'location':
                placed = row.get('latitude') is not None and row.get('longitude') is not None
                return t('On map') if placed else t('—')
            if key == 'contact_count':
                return str(row.get('contact_count') or 0)
            return row.get(key) or '—'
        if role == Qt.FontRole and key == 'name':
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.ForegroundRole and key == 'location':
            placed = row.get('latitude') is not None and row.get('longitude') is not None
            return QColor('#2f6fb0') if placed else QColor('#9aa5b1')
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class ClientsView(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.total = 0
        self.setObjectName('Canvas')
        self._build()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.reload)

    def _build(self):
        self.title = QLabel(t('Clients'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')
        self.add_btn = QPushButton(t('Add client'))
        self.add_btn.clicked.connect(self._add)
        self.docs_btn = QPushButton(t('Documents'), objectName='Ghost')
        self.docs_btn.setEnabled(False)
        self.docs_btn.clicked.connect(self._open_selected_statement)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addWidget(self.docs_btn)
        header.addWidget(self.add_btn)

        self.search = QLineEdit(placeholderText=t('Search clients'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(lambda: self._debounce.start())

        filters = QHBoxLayout()
        filters.addWidget(self.search)
        filters.addStretch()

        self.model = ClientModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._open_statement)
        self.table.selectionModel().selectionChanged.connect(self._on_selection)

        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(ClientModel.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        # Page 0: the list. Page 1: a single client's documents statement.
        list_page = QWidget()
        list_layout = QVBoxLayout(list_page)
        list_layout.setContentsMargins(28, 24, 28, 20)
        list_layout.setSpacing(16)
        list_layout.addLayout(header)
        list_layout.addLayout(filters)
        list_layout.addWidget(self.status)
        list_layout.addWidget(self.table, 1)

        self.statement = ClientStatementView(self.api)
        self.statement.back_requested.connect(self._show_list)
        self.statement.edit_requested.connect(self._edit_from_statement)

        self.stack = QStackedWidget()
        self.stack.addWidget(list_page)
        self.stack.addWidget(self.statement)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

    # -- data ------------------------------------------------------------

    def reload(self):
        params = {}
        if text := self.search.text().strip():
            params['search'] = text
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('clients/', params, on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else len(rows)
        self.model.set_rows(rows)
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No clients yet.'))
        self.count.setText(f'{self.total:,} {t("clients")}')

    def _on_error(self, error):
        self.model.set_rows([])
        self.status.setText(error.message)
        self.status.show()
        self.count.setText('')

    # -- actions ---------------------------------------------------------

    def _add(self):
        dialog = ClientDialog(self.api, parent=self)
        if dialog.exec():
            self.reload()

    def _on_selection(self, *_):
        self.docs_btn.setEnabled(self.table.selectionModel().hasSelection())

    def _open_statement(self, index):
        row = self.model.row_at(index)
        if row:
            self.statement.load(row)
            self.stack.setCurrentIndex(1)

    def _open_selected_statement(self):
        index = self.table.currentIndex()
        if index.isValid():
            self._open_statement(index)

    def _show_list(self):
        self.stack.setCurrentIndex(0)

    def _edit_from_statement(self, client):
        if not client:
            return
        dialog = ClientDialog(self.api, client=client, parent=self)
        if dialog.exec():
            self.reload()
            # Refresh the open statement with any renamed/updated details.
            self.statement.load(client)

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Clients'))
        self.search.setPlaceholderText(t('Search clients'))
        self.add_btn.setText(t('Add client'))
        self.docs_btn.setText(t('Documents'))
        self.count.setText(f'{self.total:,} {t("clients")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(ClientModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
        self.statement.retranslate()
