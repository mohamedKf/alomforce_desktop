"""Client statement — a sub-page of the Clients screen.

Everything a client has bought: one row per document (an order note and a
delivery note per order; invoices come later). Filter by document type and by
month/year; the summary shows what the client bought in the selected period and
their all-time total. The "Open" button downloads and opens that document's PDF.
"""

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import month_label, t

COLUMNS = ['Date', 'Document', 'Type', 'Status', 'Weight kg', 'Amount ₪', 'Signed', '']


def _money(value):
    try:
        return f'₪ {Decimal(str(value)):,.2f}'
    except Exception:                                     # noqa: BLE001
        return '—'


class _StatCard(QFrame):
    """A single headline figure: big value, a caption above, a note below."""

    def __init__(self, caption):
        super().__init__(objectName='StatCard')
        self.caption = QLabel(caption, objectName='StatCaption')
        self.value = QLabel('—', objectName='StatValue')
        self.note = QLabel('', objectName='StatNote')
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(2)
        box.addWidget(self.caption)
        box.addWidget(self.value)
        box.addWidget(self.note)

    def set(self, value, note=''):
        self.value.setText(value)
        self.note.setText(note)


class ClientStatementView(QWidget):
    back_requested = Signal()
    edit_requested = Signal(dict)

    def __init__(self, api, session=None):
        super().__init__()
        self.api = api
        self.session = session
        self.client = None
        self.setObjectName('Canvas')
        self._build()

    # -- construction ----------------------------------------------------

    def _build(self):
        self.back_btn = QPushButton('←  ' + t('Clients'), objectName='Ghost')
        self.back_btn.clicked.connect(self.back_requested)
        self.title = QLabel('', objectName='PageTitle')
        self.edit_btn = QPushButton(t('Edit client'), objectName='Ghost')
        self.edit_btn.clicked.connect(
            lambda: self.edit_requested.emit(self.client or {}))

        top = QHBoxLayout()
        top.addWidget(self.back_btn)
        top.addSpacing(10)
        top.addWidget(self.title)
        top.addStretch()
        top.addWidget(self.edit_btn)

        # summary cards
        self.card_period = _StatCard(t('Bought this period'))
        self.card_total = _StatCard(t('All-time total'))
        self.card_owes = _StatCard(t('Owes now'))
        cards = QHBoxLayout()
        cards.setSpacing(14)
        cards.addWidget(self.card_period, 1)
        cards.addWidget(self.card_total, 1)
        cards.addWidget(self.card_owes, 1)
        cards.addStretch(1)

        # filters
        self.type_combo = QComboBox()
        self.type_combo.addItem(t('All documents'), None)
        self.type_combo.addItem(t('Order note'), 'order_note')
        self.type_combo.addItem(t('Delivery note'), 'delivery_note')
        self.month_combo = QComboBox()
        self.month_combo.addItem(t('All months'), None)
        for m in range(1, 13):
            self.month_combo.addItem(month_label(m), m)
        self.year_combo = QComboBox()
        self.year_combo.addItem(t('All years'), None)
        this_year = date.today().year
        for y in range(this_year, this_year - 7, -1):
            self.year_combo.addItem(str(y), y)
        for combo in (self.type_combo, self.month_combo, self.year_combo):
            combo.currentIndexChanged.connect(self.reload)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(QLabel(t('Show'), objectName='FieldLabel'))
        filters.addWidget(self.type_combo)
        filters.addSpacing(8)
        filters.addWidget(self.month_combo)
        filters.addWidget(self.year_combo)
        filters.addStretch()

        # table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in range(len(COLUMNS)):
            if c != 1:
                head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        # Pin the actions column so the stretchy Document column can't clip the
        # Open button against the right edge.
        head.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Fixed)
        self.table.setColumnWidth(len(COLUMNS) - 1, 92)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(top)
        layout.addLayout(cards)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)

    # -- data ------------------------------------------------------------

    def load(self, client):
        """Open the statement for a client (called by the Clients screen)."""
        self.client = client
        self.title.setText(client.get('name', ''))
        self.reload()

    def reload(self, *_):
        if not self.client:
            return
        params = {}
        if tv := self.type_combo.currentData():
            params['type'] = tv
        if mv := self.month_combo.currentData():
            params['month'] = mv
        if yv := self.year_combo.currentData():
            params['year'] = yv
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get(f'clients/{self.client["id"]}/statement/', params,
                     on_ok=self._on_data, on_error=self._on_error)

    def _on_data(self, data):
        summary = data.get('summary', {})
        self.card_period.set(
            _money(summary.get('period_total')),
            t('%d orders') % (summary.get('period_orders') or 0))
        self.card_total.set(
            _money(summary.get('grand_total')),
            t('%d orders') % (summary.get('grand_orders') or 0))
        owes = summary.get('outstanding')
        self.card_owes.set(_money(owes), t('unpaid invoices'))
        try:
            self.card_owes.value.setStyleSheet(
                'color:#B3261E;' if Decimal(str(owes)) > 0 else 'color:#2E7D32;')
        except Exception:                                 # noqa: BLE001
            pass

        docs = data.get('documents', [])
        self.table.setRowCount(0)
        for doc in docs:
            self._add_row(doc)
        if docs:
            self.status.hide()
        else:
            self.status.setText(t('No documents for this filter.'))
            self.status.show()

    def _add_row(self, doc):
        r = self.table.rowCount()
        self.table.insertRow(r)

        def cell(text, align=Qt.AlignLeft):
            item = QTableWidgetItem(text)
            item.setTextAlignment(int(align | Qt.AlignVCenter))
            return item

        self.table.setItem(r, 0, cell(doc.get('date', '—')))
        num = cell(doc.get('number', '—'))
        font = num.font()
        font.setBold(True)
        num.setFont(font)
        self.table.setItem(r, 1, num)
        self.table.setItem(r, 2, cell(t(doc.get('type_display', '')) or '—'))
        self.table.setItem(r, 3, cell(t(doc.get('status_display', '')) or '—'))
        self.table.setItem(r, 4, cell(doc.get('weight', '—'), Qt.AlignRight))
        amount = doc.get('amount')
        self.table.setItem(r, 5, cell(_money(amount) if amount is not None else '—',
                                      Qt.AlignRight))

        # signed status (delivery notes only)
        signed = doc.get('signed')
        if signed is None:
            sitem = cell('—', Qt.AlignCenter)
        elif signed:
            sitem = cell('✓ ' + t('Signed'), Qt.AlignCenter)
            sitem.setForeground(QColor('#2E7D32'))
        else:
            sitem = cell(t('Unsigned'), Qt.AlignCenter)
            sitem.setForeground(QColor('#B3261E'))
        self.table.setItem(r, 6, sitem)

        open_btn = QPushButton(t('Open'), objectName='SmallGhost')
        open_btn.setMinimumWidth(64)
        open_btn.clicked.connect(
            lambda _=False, d=doc, b=open_btn: self._open_pdf(d, b))
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(4, 3, 8, 3)
        wl.addStretch()
        wl.addWidget(open_btn)
        self.table.setCellWidget(r, 7, wrap)

    # -- open the document PDF -------------------------------------------

    def _open_pdf(self, doc, button):
        kind = doc.get('type')
        path = f'orders/{doc["order_id"]}/{kind}/'
        filename = f'{doc.get("number", "document")}_{kind}.pdf'
        button.setEnabled(False)
        button.setText(t('Opening…'))
        self.api.download_pdf(
            path, filename,
            on_ok=lambda fp, b=button: self._pdf_ready(fp, b),
            on_error=lambda e, b=button: self._pdf_failed(e, b))

    def _pdf_ready(self, file_path, button):
        button.setEnabled(True)
        button.setText(t('Open'))
        QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))

    def _pdf_failed(self, error, button):
        button.setEnabled(True)
        button.setText(t('Open'))
        self.status.setText(error.message)
        self.status.show()

    def _on_error(self, error):
        self.table.setRowCount(0)
        self.status.setText(error.message)
        self.status.show()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.back_btn.setText('←  ' + t('Clients'))
        self.edit_btn.setText(t('Edit client'))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        if self.client:
            self.reload()
