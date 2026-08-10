"""Invoices — income and expense records for the accountant's books.

Income / Expense toggle at the top; each side lists its invoices for the chosen
month and year with running totals. Add an invoice by hand (or attach its PDF /
photo). Scanning, legal generation and sending to the accountant come later.
"""

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import month_label, t
from app.views.invoice_dialog import InvoiceDialog

COLUMNS = ['Date', 'Number', 'Party', 'Tax ID', 'Category', 'Total ₪',
           'Status', 'Source', '']


def _money(value):
    try:
        return f'₪ {Decimal(str(value)):,.2f}'
    except Exception:                                     # noqa: BLE001
        return '—'


class _StatCard(QFrame):
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


class InvoicesView(QWidget):
    def __init__(self, api, session=None):
        super().__init__()
        self.api = api
        self.session = session
        self.direction = 'income'
        self.setObjectName('Canvas')
        self._build()
        self.reload()

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel(t('Invoices'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        self.tab_income = QPushButton(t('Income'), objectName='Segment')
        self.tab_expense = QPushButton(t('Expense'), objectName='Segment')
        for b in (self.tab_income, self.tab_expense):
            b.setCheckable(True)
        self.tab_income.setChecked(True)
        self._tabs = QButtonGroup(self)
        self._tabs.addButton(self.tab_income, 0)
        self._tabs.addButton(self.tab_expense, 1)
        self._tabs.idClicked.connect(self._switch)
        toggle = QHBoxLayout()
        toggle.setSpacing(0)
        toggle.addWidget(self.tab_income)
        toggle.addWidget(self.tab_expense)

        self.add_btn = QPushButton(t('Add invoice'))
        self.add_btn.clicked.connect(self._add)
        self.accountant_btn = QPushButton(t('To accountant'), objectName='Ghost')
        self.accountant_btn.clicked.connect(self._to_accountant)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addLayout(toggle)
        header.addSpacing(12)
        header.addWidget(self.accountant_btn)
        header.addWidget(self.add_btn)

        # summary cards
        self.card_income = _StatCard(t('Income this period'))
        self.card_expense = _StatCard(t('Expenses this period'))
        self.card_net = _StatCard(t('Net'))
        cards = QHBoxLayout()
        cards.setSpacing(14)
        for c in (self.card_income, self.card_expense, self.card_net):
            cards.addWidget(c, 1)
        cards.addStretch(1)

        # filters
        self.month = QComboBox()
        self.month.addItem(t('All months'), None)
        for m in range(1, 13):
            self.month.addItem(month_label(m), m)
        self.year = QComboBox()
        self.year.addItem(t('All years'), None)
        this_year = date.today().year
        for y in range(this_year, this_year - 7, -1):
            self.year.addItem(str(y), y)
        self.year.setCurrentIndex(1)  # default to the current year
        self.search = QLineEdit(placeholderText=t('Search number, party or tax ID'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        for w in (self.month, self.year):
            w.currentIndexChanged.connect(self.reload)
        self.search.returnPressed.connect(self.reload)
        self.search.textChanged.connect(self._maybe_clear)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(QLabel(t('Show'), objectName='FieldLabel'))
        filters.addWidget(self.month)
        filters.addWidget(self.year)
        filters.addSpacing(8)
        filters.addWidget(self.search)
        filters.addStretch()

        # table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._edit_current)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in range(len(COLUMNS)):
            if c != 2:
                head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Fixed)
        self.table.setColumnWidth(len(COLUMNS) - 1, 84)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addLayout(cards)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)

    # -- data ------------------------------------------------------------

    def _switch(self, index):
        self.direction = 'expense' if index == 1 else 'income'
        self.reload()

    def _params(self):
        params = {'direction': self.direction}
        if m := self.month.currentData():
            params['month'] = m
        if y := self.year.currentData():
            params['year'] = y
        if text := self.search.text().strip():
            params['search'] = text
        return params

    def reload(self, *_):
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('invoices/', self._params(),
                     on_ok=self._on_rows, on_error=self._on_error)
        summary_params = {k: v for k, v in self._params().items()
                          if k in ('month', 'year')}
        self.api.get('invoices/summary/', summary_params,
                     on_ok=self._on_summary, on_error=lambda e: None)

    def _maybe_clear(self, text):
        if not text:
            self.reload()

    def _on_summary(self, data):
        income = data.get('income_total')
        expense = data.get('expense_total')
        self.card_income.set(_money(income),
                             t('%d invoices') % (data.get('income_count') or 0))
        self.card_expense.set(_money(expense),
                              t('%d invoices') % (data.get('expense_count') or 0))
        net = data.get('net')
        self.card_net.set(_money(net))
        try:
            self.card_net.value.setStyleSheet(
                'color:#2E7D32;' if Decimal(str(net)) >= 0 else 'color:#B3261E;')
        except Exception:                                 # noqa: BLE001
            pass

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self._rows = rows
        self.table.setRowCount(0)
        for inv in rows:
            self._add_row(inv)
        total = payload.get('count', len(rows)) if isinstance(payload, dict) else len(rows)
        self.count.setText(f'{total:,} {t("invoices")}')
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No invoices for this filter.'))
            self.status.show()

    def _add_row(self, inv):
        r = self.table.rowCount()
        self.table.insertRow(r)

        def cell(text, align=Qt.AlignLeft):
            item = QTableWidgetItem(text)
            item.setTextAlignment(int(align | Qt.AlignVCenter))
            return item

        self.table.setItem(r, 0, cell(inv.get('issued_at', '—')))
        num = cell(inv.get('number') or '—')
        font = num.font()
        font.setBold(True)
        num.setFont(font)
        self.table.setItem(r, 1, num)
        party = inv.get('client_name') or inv.get('party_name') or '—'
        self.table.setItem(r, 2, cell(party))
        self.table.setItem(r, 3, cell(inv.get('party_tax_id') or '—'))
        self.table.setItem(r, 4, cell(t(inv.get('category')) if inv.get('category') else '—'))
        self.table.setItem(r, 5, cell(_money(inv.get('total')), Qt.AlignRight))

        status = inv.get('status')
        sitem = cell(t(inv.get('status_display', '')) or '—', Qt.AlignCenter)
        sitem.setForeground(QColor('#2E7D32') if status == 'paid' else QColor('#B3661E'))
        self.table.setItem(r, 6, sitem)
        self.table.setItem(r, 7, cell(t(inv.get('source_display', '')) or '—',
                                      Qt.AlignCenter))

        if inv.get('file_url'):
            btn = QPushButton(t('File'), objectName='SmallGhost')
            btn.setMinimumWidth(56)
            btn.clicked.connect(lambda _=False, u=inv['file_url']:
                                QDesktopServices.openUrl(QUrl(u)))
            wrap = QWidget()
            wl = QHBoxLayout(wrap)
            wl.setContentsMargins(4, 3, 8, 3)
            wl.addStretch()
            wl.addWidget(btn)
            self.table.setCellWidget(r, 8, wrap)

    # -- actions ---------------------------------------------------------

    def _add(self):
        dialog = InvoiceDialog(self.api, direction=self.direction, parent=self)
        if dialog.exec():
            self.reload()

    def _edit_current(self, index):
        row = index.row()
        if 0 <= row < len(getattr(self, '_rows', [])):
            dialog = InvoiceDialog(self.api, invoice=self._rows[row], parent=self)
            if dialog.exec():
                self.reload()

    # -- accountant package ---------------------------------------------

    def _to_accountant(self):
        """Pick a month/year, then email or download the accountant ZIP
        (salary sheet + combined income/expense PDFs + the invoice files)."""
        today = date.today()
        dlg = QDialog(self)
        dlg.setWindowTitle(t('Send to accountant'))
        month = QComboBox()
        for m in range(1, 13):
            month.addItem(month_label(m), m)
        month.setCurrentIndex((self.month.currentData() or today.month) - 1)
        year = QSpinBox()
        year.setRange(2020, 2100)
        year.setValue(self.year.currentData() or today.year)
        row = QHBoxLayout()
        row.addWidget(QLabel(t('Month'), objectName='FieldLabel'))
        row.addWidget(month)
        row.addWidget(year)
        buttons = QDialogButtonBox()
        email_b = buttons.addButton(t('Email accountant'), QDialogButtonBox.AcceptRole)
        save_b = buttons.addButton(t('Download ZIP'), QDialogButtonBox.ActionRole)
        buttons.addButton(t('Cancel'), QDialogButtonBox.RejectRole)
        box = QVBoxLayout(dlg)
        box.setContentsMargins(22, 20, 22, 18)
        box.setSpacing(14)
        box.addWidget(QLabel(t('Bundle all invoices and the salary sheet for the '
                               'month, for the accountant.'), objectName='CardHint'))
        box.addLayout(row)
        box.addWidget(buttons)
        email_b.clicked.connect(lambda: dlg.done(2))
        save_b.clicked.connect(lambda: dlg.done(3))
        buttons.rejected.connect(dlg.reject)
        choice = dlg.exec()
        y, m = year.value(), month.currentData()
        if choice == 2:
            self._email_accountant(y, m)
        elif choice == 3:
            self._download_accountant(y, m)

    def _email_accountant(self, year, month):
        self.status.setText(t('Sending to accountant…'))
        self.status.show()
        self.api.post('invoices/email_accountant/', {'year': year, 'month': month},
                      on_ok=lambda d: self._accountant_sent(d),
                      on_error=self._on_error)

    def _accountant_sent(self, data):
        to = data.get('to', '') if isinstance(data, dict) else ''
        QMessageBox.information(self, t('Send to accountant'),
                                t('Sent to %s.') % to)
        self.status.hide()

    def _download_accountant(self, year, month):
        name = f'accountant_{year}_{month:02d}.zip'
        self.api.download_pdf(
            f'invoices/accountant_zip/?year={year}&month={month}', name,
            on_ok=lambda path: QDesktopServices.openUrl(
                QUrl.fromLocalFile(path.rsplit('/', 1)[0])),
            on_error=self._on_error)

    def _on_error(self, error):
        self.table.setRowCount(0)
        self.status.setText(error.message)
        self.status.show()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Invoices'))
        self.add_btn.setText(t('Add invoice'))
        self.tab_income.setText(t('Income'))
        self.tab_expense.setText(t('Expense'))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.reload()
