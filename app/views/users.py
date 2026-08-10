"""Users screen — managers add and manage workers and client contacts.

The only way an account comes into existence. There is no public signup; the
backend has no route for it.
"""

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
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
from app.views.dialogs import AddWorkerDialog

PAGE_SIZE = 50


class UserModel(QAbstractTableModel):
    COLUMNS = [
        ('name', 'Name'),
        ('identifier', 'ID / Phone'),
        ('role_display', 'Role'),
        ('phone', 'Phone'),
        ('status', 'Status'),
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
            if key == 'name':
                return row.get('full_name') or '—'
            if key == 'identifier':
                return row.get('id_number') or row.get('phone') or '—'
            if key == 'role_display':
                return t(row.get('role_display') or '')
            if key == 'status':
                if not row.get('is_active'):
                    return t('Inactive')
                if row.get('must_change_password'):
                    return t('Password not set')
                return t('Active')
            return row.get(key) or '—'

        if role == Qt.FontRole and key == 'name':
            font = QFont()
            font.setBold(True)
            return font

        # Anything not ready to work is worth spotting at a glance.
        if role == Qt.ForegroundRole and key == 'status':
            if not row.get('is_active'):
                return QColor('#B3261E')
            if row.get('must_change_password'):
                return QColor('#8A6D1F')
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class UsersView(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.total = 0
        self.setObjectName('Canvas')
        self._build()

    def _build(self):
        self.title = QLabel(t('Users'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        self.edit_btn = QPushButton(t('Edit'), objectName='Ghost')
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_selected)
        self.add_worker = QPushButton(t('Add worker'))
        self.add_worker.clicked.connect(self._add_worker)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addWidget(self.edit_btn)
        header.addWidget(self.add_worker)

        self.search = QLineEdit(placeholderText=t('Search users'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self.reload)

        self.role = QComboBox()
        self.role.setMinimumWidth(160)
        self.role.currentIndexChanged.connect(self.reload)

        filters = QHBoxLayout()
        filters.setSpacing(9)
        filters.addWidget(self.search)
        filters.addWidget(self.role)
        filters.addStretch()

        self.model = UserModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._edit)
        self.table.selectionModel().selectionChanged.connect(self._update_edit_enabled)

        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(UserModel.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)

        self._fill_roles()

    def _fill_roles(self):
        selected = self.role.currentData()
        self.role.blockSignals(True)
        self.role.clear()
        self.role.addItem(t('All roles'), None)
        for value, label in [
            ('manager', 'Manager'), ('office', 'Office'),
            ('warehouse', 'Warehouse worker'), ('driver', 'Delivery driver'),
            ('client', 'Client'),
        ]:
            self.role.addItem(t(label), value)
        if selected:
            self.role.setCurrentIndex(max(0, self.role.findData(selected)))
        self.role.blockSignals(False)

    # -- data -------------------------------------------------------------

    def reload(self):
        params = {}
        if text := self.search.text().strip():
            params['search'] = text
        if role := self.role.currentData():
            params['role'] = role

        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('staff/', params, on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', []) if isinstance(payload, dict) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else 0
        self.model.set_rows(rows)
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No users match these filters.'))
        self.count.setText(f'{self.total:,} {t("users")}')

    def _on_error(self, error):
        self.model.set_rows([])
        self.status.setText(error.message)
        self.status.show()
        self.count.setText('')

    # -- actions ----------------------------------------------------------

    def _add_worker(self):
        dialog = AddWorkerDialog(self.api, parent=self)
        if dialog.exec():
            self.reload()

    def _edit(self, index):
        self._open_editor(self.model.row_at(index))

    def _edit_selected(self):
        index = self.table.currentIndex()
        self._open_editor(self.model.row_at(index) if index.isValid() else None)

    def _open_editor(self, row):
        # Client contacts are managed on the Clients screen, not here.
        if not row or row.get('role') == 'client':
            return
        dialog = AddWorkerDialog(self.api, worker=row, parent=self)
        if dialog.exec():
            self.reload()

    def _update_edit_enabled(self, *_):
        row = None
        index = self.table.currentIndex()
        if index.isValid():
            row = self.model.row_at(index)
        self.edit_btn.setEnabled(bool(row) and row.get('role') != 'client')

    # -- i18n -------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Users'))
        self.search.setPlaceholderText(t('Search users'))
        self.edit_btn.setText(t('Edit'))
        self.add_worker.setText(t('Add worker'))
        self._fill_roles()
        self.count.setText(f'{self.total:,} {t("users")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0,
                                          len(UserModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
