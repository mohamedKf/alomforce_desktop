"""Requests — workers' clock-fix requests for a manager to approve or reject.

A worker who mis-clocked (wrong time, forgot to clock out, missed a day) raises
a request on the phone. Here the office/manager reviews the requested times and
reason, then approves (which applies them to the shift) or rejects.
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

COLUMNS = ['Worker', 'Date', 'Requested in', 'Requested out', 'Reason',
           'Status', '']

STATUS_COLORS = {
    'pending': '#B7791F',
    'approved': '#2E7D32',
    'rejected': '#B3261E',
}


def _time(iso):
    if not iso:
        return '—'
    try:
        return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M')
    except (ValueError, AttributeError):
        return iso


class RequestsView(QWidget):
    def __init__(self, api, session=None):
        super().__init__()
        self.api = api
        self.session = session
        self.total = 0
        self.filter = 'pending'
        self.setObjectName('Canvas')
        self._build()
        self.reload()

    def _build(self):
        self.title = QLabel(t('Requests'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        self.tab_pending = QPushButton(t('Pending'), objectName='Segment')
        self.tab_all = QPushButton(t('All'), objectName='Segment')
        for b in (self.tab_pending, self.tab_all):
            b.setCheckable(True)
        self.tab_pending.setChecked(True)
        self._tabs = QButtonGroup(self)
        self._tabs.addButton(self.tab_pending, 0)
        self._tabs.addButton(self.tab_all, 1)
        self._tabs.idClicked.connect(self._switch)
        toggle = QHBoxLayout()
        toggle.setSpacing(0)
        toggle.addWidget(self.tab_pending)
        toggle.addWidget(self.tab_all)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addLayout(toggle)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(4, QHeaderView.Stretch)
        for c in range(len(COLUMNS)):
            if c != 4:
                head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Fixed)
        self.table.setColumnWidth(len(COLUMNS) - 1, 176)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)

    def _switch(self, index):
        self.filter = 'all' if index == 1 else 'pending'
        self.reload()

    # -- data ------------------------------------------------------------

    def reload(self):
        params = {} if self.filter == 'all' else {'status': 'pending'}
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('corrections/', params, on_ok=self._on_rows,
                     on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else len(rows)
        self.table.setRowCount(0)
        for req in rows:
            self._add_row(req)
        self.count.setText(f'{self.total:,} {t("requests")}')
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No requests.'))
            self.status.show()

    def _add_row(self, req):
        r = self.table.rowCount()
        self.table.insertRow(r)

        def cell(text, align=Qt.AlignLeft):
            item = QTableWidgetItem(text)
            item.setTextAlignment(int(align | Qt.AlignVCenter))
            return item

        worker = cell(req.get('worker_name') or '—')
        font = worker.font()
        font.setBold(True)
        worker.setFont(font)
        self.table.setItem(r, 0, worker)
        self.table.setItem(r, 1, cell(req.get('work_date') or '—'))
        self.table.setItem(r, 2, cell(_time(req.get('requested_clock_in'))))
        self.table.setItem(r, 3, cell(_time(req.get('requested_clock_out'))))
        self.table.setItem(r, 4, cell(req.get('reason') or '—'))

        st = req.get('status')
        sitem = cell(t(req.get('status_display', '')) or '—', Qt.AlignCenter)
        sitem.setForeground(QColor(STATUS_COLORS.get(st, '#6B7785')))
        self.table.setItem(r, 5, sitem)

        if st == 'pending':
            approve = QPushButton(t('Approve'), objectName='SmallGhost')
            approve.setMinimumWidth(74)
            approve.clicked.connect(lambda _=False, i=req['id']: self._approve(i))
            reject = QPushButton(t('Reject'), objectName='SmallGhost')
            reject.setMinimumWidth(66)
            reject.clicked.connect(lambda _=False, i=req['id']: self._reject(i))
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(2, 4, 6, 4)
            wl.setSpacing(5)
            wl.addStretch()
            wl.addWidget(approve)
            wl.addWidget(reject)
            self.table.setCellWidget(r, 6, wrap)
        else:
            by = req.get('reviewed_by_name')
            if by:
                self.table.setCellWidget(r, 6, self._reviewed_label(by))

    def _reviewed_label(self, by):
        label = QLabel(t('by %s') % by, objectName='Muted')
        label.setAlignment(Qt.AlignCenter)
        label.setContentsMargins(6, 0, 6, 0)
        return label

    # -- actions ---------------------------------------------------------

    def _approve(self, request_id):
        self.api.post(f'corrections/{request_id}/approve/', {},
                      on_ok=lambda _d: self.reload(), on_error=self._on_error)

    def _reject(self, request_id):
        note, ok = QInputDialog.getText(
            self, t('Reject request'), t('Reason for rejecting (optional):'))
        if not ok:
            return
        self.api.post(f'corrections/{request_id}/reject/', {'review_note': note},
                      on_ok=lambda _d: self.reload(), on_error=self._on_error)

    def _on_error(self, error):
        self.status.setText(error.message)
        self.status.show()

    def retranslate(self):
        self.title.setText(t('Requests'))
        self.tab_pending.setText(t('Pending'))
        self.tab_all.setText(t('All'))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.reload()
