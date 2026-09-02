"""תשלומים — what the order costs, what it is made of, and what has been paid.

Three questions in one place, because a customer asks them together: what do I
owe, how much of that is the 7000 series, and what have I already paid.

The cheque is the awkward one. Israeli construction runs on post-dated
cheques, so a cheque handed over today may not be money until March. The
totals say both — received, and actually cleared — because a yard that spends
against an uncleared cheque is borrowing without knowing it.
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

METHODS = [('cash', 'Cash'), ('cheque', 'Cheque'),
           ('transfer', 'Bank transfer'), ('card', 'Card'), ('other', 'Other')]
PAYMENT_COLUMNS = ['Date', 'Amount', 'Method', 'Invoice', 'Reference',
                   'Banked on', 'Recorded by']
BREAKDOWN_COLUMNS = ['Series', 'Lines', 'Weight kg', 'Cost']


def _dec(value):
    try:
        text = str(value).strip()
        return Decimal(text) if text else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _num(value):
    amount = _dec(value)
    if amount is None:
        return ''
    text = f'{amount:f}'
    return (text.rstrip('0').rstrip('.') if '.' in text else text) or '0'


def _money(value):
    return f'₪ {_dec(value) or Decimal("0"):,.2f}'


class PaymentDialog(QDialog):
    """Record money in: how much, how, and when it is actually money."""

    def __init__(self, api, order_id, balance=None, payment=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.order_id = order_id
        self.payment = payment
        self.balance = _dec(balance) or Decimal('0')
        self.saved = None
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setWindowTitle(t('Edit payment') if payment else t('New payment'))
        self._build()
        if payment:
            self._fill(payment)

    def _build(self):
        self.amount = QDoubleSpinBox()
        self.amount.setRange(0.01, 100_000_000)
        self.amount.setDecimals(2)
        self.amount.setPrefix('₪ ')
        # The balance, because paying it off is the common case.
        self.amount.setValue(float(self.balance) if self.balance > 0 else 0.01)

        self.method = QComboBox()
        for value, label in METHODS:
            self.method.addItem(t(label), value)
        self.method.currentIndexChanged.connect(self._on_method)

        self.paid_on = QDateEdit()
        self.paid_on.setCalendarPopup(True)
        self.paid_on.setDisplayFormat('yyyy-MM-dd')
        self.paid_on.setDate(QDate.currentDate())

        self.due_on = QDateEdit()
        self.due_on.setCalendarPopup(True)
        self.due_on.setDisplayFormat('yyyy-MM-dd')
        self.due_on.setDate(QDate.currentDate())
        self.due_label = QLabel(t('Banked on'), objectName='FieldLabel')

        self.reference = QLineEdit(
            placeholderText=t('Cheque number, transfer reference'))
        self.note = QLineEdit()

        # The paperwork, on the same form and optional. Plenty of a yard's
        # takings never get invoiced -- cash over the counter, a deposit
        # against work not started -- and a form that demands an invoice
        # number before it will record money means the money goes unrecorded.
        self.issue_invoice = QCheckBox(t('Also issue an invoice for this'))
        self.issue_invoice.toggled.connect(self._on_invoice)
        self.invoice_number = QLineEdit(placeholderText=t('Invoice number'))
        self.invoice_label = QLabel(t('Invoice number'), objectName='FieldLabel')

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow(t('Amount'), self.amount)
        form.addRow(t('Method'), self.method)
        form.addRow(t('Paid on'), self.paid_on)
        form.addRow(self.due_label, self.due_on)
        form.addRow(t('Reference'), self.reference)
        form.addRow(t('Note'), self.note)
        form.addRow('', self.issue_invoice)
        form.addRow(self.invoice_label, self.invoice_number)

        self.hint = QLabel('', objectName='CardHint')
        self.hint.setWordWrap(True)
        # Said plainly, because the alternative -- invoicing the whole order
        # when a deposit is paid -- is what made an order read as fully
        # invoiced off one part payment.
        self.invoice_hint = QLabel(
            t('The invoice is written for this amount, VAT included — not '
              'for the whole order.'), objectName='CardHint')
        self.invoice_hint.setWordWrap(True)
        self.invoice_hint.hide()
        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(
            t('Save') if self.payment else t('Record payment'))
        self.buttons.accepted.connect(self._submit)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.invoice_hint)
        layout.addWidget(self.hint)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self._on_method()
        self._on_invoice(False)

    def _on_invoice(self, wanted):
        self.invoice_number.setVisible(bool(wanted))
        self.invoice_label.setVisible(bool(wanted))
        self.invoice_hint.setVisible(bool(wanted))
        # Editing an existing payment does not re-raise its paperwork.
        if self.payment:
            self.issue_invoice.setVisible(False)
            self.invoice_number.setVisible(False)
            self.invoice_label.setVisible(False)
            self.invoice_hint.setVisible(False)

    def _on_method(self):
        """Only a cheque waits to be banked."""
        cheque = self.method.currentData() == 'cheque'
        self.due_on.setVisible(cheque)
        self.due_label.setVisible(cheque)
        self.hint.setText(
            t('A post-dated cheque counts as paid, but not as cleared until '
              'the date it can be banked.') if cheque else '')

    def _fill(self, payment):
        self.amount.setValue(float(_dec(payment.get('amount')) or 0))
        if (index := self.method.findData(payment.get('method'))) >= 0:
            self.method.setCurrentIndex(index)
        if payment.get('paid_on'):
            self.paid_on.setDate(
                QDate.fromString(payment['paid_on'], 'yyyy-MM-dd'))
        if payment.get('due_on'):
            self.due_on.setDate(
                QDate.fromString(payment['due_on'], 'yyyy-MM-dd'))
        self.reference.setText(payment.get('reference') or '')
        self.note.setText(payment.get('note') or '')
        self._on_method()

    def _submit(self):
        self.error.hide()
        cheque = self.method.currentData() == 'cheque'
        payload = {
            'amount': f'{self.amount.value():.2f}',
            'method': self.method.currentData(),
            'paid_on': self.paid_on.date().toString('yyyy-MM-dd'),
            # Cleared on the spot unless it is a cheque waiting to be banked.
            'due_on': (self.due_on.date().toString('yyyy-MM-dd')
                       if cheque else None),
            'reference': self.reference.text().strip(),
            'note': self.note.text().strip(),
        }
        if not self.payment and self.issue_invoice.isChecked():
            payload['issue_invoice'] = True
            payload['invoice_number_in'] = self.invoice_number.text().strip()
        self.buttons.setEnabled(False)
        if self.payment:
            self.api.patch(
                f"orders/{self.order_id}/payments/{self.payment['id']}/",
                payload, on_ok=self._done, on_error=self._failed)
        else:
            self.api.post(f'orders/{self.order_id}/payments/', payload,
                          on_ok=self._done, on_error=self._failed)

    def _done(self, row):
        self.saved = row
        self.accept()

    def _failed(self, error):
        self.buttons.setEnabled(True)
        payload = getattr(error, 'payload', None)
        if isinstance(payload, dict):
            for field in ('due_on', 'amount', 'paid_on', 'method'):
                if payload.get(field):
                    self.error.setText(str(payload[field][0]))
                    self.error.show()
                    return
        self.error.setText(getattr(error, 'message', str(error)))
        self.error.show()


class OrderPayments(QWidget):
    """The money side of one order."""

    def __init__(self, api, order_id=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.order_id = order_id
        self.payments = []
        self.totals = {}
        self.setObjectName('Canvas')
        self._build()
        self.reload()

    def _build(self):
        self.title = QLabel(t('Payments'), objectName='SectionTitle')
        self.new_btn = QPushButton(t('New payment'), objectName='PrimaryButton')
        self.edit_btn = QPushButton(t('Edit'), objectName='Ghost')
        self.remove_btn = QPushButton(t('Remove'), objectName='Ghost')
        self.new_btn.clicked.connect(self._new)
        self.edit_btn.clicked.connect(self._edit)
        self.remove_btn.clicked.connect(self._remove)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.remove_btn)
        header.addWidget(self.edit_btn)
        header.addWidget(self.new_btn)

        # What is owed, big, because it is the question being asked.
        self.balance = QLabel('', objectName='PageTitle')
        self.balance.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.money = QLabel('', objectName='CardHint')
        self.money.setWordWrap(True)
        summary = QFrame(objectName='Card')
        summary_box = QVBoxLayout(summary)
        summary_box.setContentsMargins(16, 12, 16, 12)
        summary_box.setSpacing(4)
        summary_box.addWidget(self.balance)
        summary_box.addWidget(self.money)

        self.breakdown = QTableWidget(0, len(BREAKDOWN_COLUMNS))
        self.breakdown.setHorizontalHeaderLabels(
            [t(c) for c in BREAKDOWN_COLUMNS])
        self.breakdown.verticalHeader().setVisible(False)
        self.breakdown.setShowGrid(False)
        self.breakdown.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.breakdown.setMaximumHeight(170)
        head = self.breakdown.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(BREAKDOWN_COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        self.table = QTableWidget(0, len(PAYMENT_COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in PAYMENT_COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.currentCellChanged.connect(lambda *_: self._refresh_enabled())
        self.table.doubleClicked.connect(self._edit)
        pay_head = self.table.horizontalHeader()
        pay_head.setSectionResizeMode(3, QHeaderView.Stretch)
        for column in (0, 1, 2, 4, 5):
            pay_head.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(summary)
        layout.addWidget(QLabel(t('What it is made of'), objectName='FieldLabel'))
        layout.addWidget(self.breakdown)
        layout.addWidget(QLabel(t('Payments'), objectName='FieldLabel'))
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        self._refresh_enabled()

    # -- data -------------------------------------------------------------

    def set_order(self, order_id):
        self.order_id = order_id
        self._refresh_enabled()
        self.reload()

    def reload(self):
        if self.order_id is None:
            return
        self.api.get(f'orders/{self.order_id}/payments/',
                     on_ok=self._on_data, on_error=self._on_error)

    def _on_data(self, payload):
        payload = payload or {}
        self.payments = payload.get('payments') or []
        self.totals = payload.get('totals') or {}
        breakdown = payload.get('breakdown') or []

        self.balance.setText(
            t('Paid in full') if self.totals.get('is_paid')
            else f"{t('Balance due')}  {_money(self.totals.get('balance'))}")
        received = _dec(self.totals.get('paid')) or Decimal('0')
        cleared = _dec(self.totals.get('cleared')) or Decimal('0')
        parts = [f"{t('Total')} {_money(self.totals.get('total'))}",
                 f"{t('Paid')} {_money(received)}"]
        # Only worth saying when they differ, which means a cheque is waiting.
        if cleared != received:
            parts.append(f"{t('Cleared')} {_money(cleared)}")
        self.money.setText('     ·     '.join(parts))

        self.breakdown.setRowCount(len(breakdown))
        for row, item in enumerate(breakdown):
            values = [item.get('name') or '', str(item.get('lines') or 0),
                      _num(item.get('weight_kg')), _money(item.get('subtotal'))]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if column:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.breakdown.setItem(row, column, cell)

        self.table.setRowCount(len(self.payments))
        for row, item in enumerate(self.payments):
            banked = item.get('due_on') or ''
            if banked and not item.get('is_cleared'):
                banked = f'{banked}  ({t("not yet")})'
            values = [item.get('paid_on') or '', _money(item.get('amount')),
                      t(item.get('method_display') or ''),
                      # Blank means money taken with no paperwork, which is
                      # ordinary rather than something missing.
                      item.get('invoice_number') or '—',
                      item.get('reference') or '', banked,
                      item.get('recorded_by_name') or '']
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                if column == 1:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, cell)

        self.status.setText('' if self.payments else t('Nothing paid yet.'))
        self.status.setVisible(not self.payments)
        self._refresh_enabled()

    def _on_error(self, error):
        self.status.setText(getattr(error, 'message', str(error)))
        self.status.show()

    def _selected(self):
        row = self.table.currentRow()
        return self.payments[row] if 0 <= row < len(self.payments) else None

    def _refresh_enabled(self):
        has_order = self.order_id is not None
        self.new_btn.setEnabled(has_order)
        picked = self._selected() is not None
        self.edit_btn.setEnabled(picked)
        self.remove_btn.setEnabled(picked)
        if not has_order:
            self.status.setText(t('Save the order first.'))
            self.status.show()

    # -- actions ----------------------------------------------------------

    def _new(self):
        if self.order_id is None:
            return
        dialog = PaymentDialog(self.api, self.order_id,
                               balance=self.totals.get('balance'), parent=self)
        if dialog.exec():
            self.reload()

    def _edit(self, *_):
        payment = self._selected()
        if not payment:
            return
        dialog = PaymentDialog(self.api, self.order_id, payment=payment,
                               parent=self)
        if dialog.exec():
            self.reload()

    def _remove(self):
        payment = self._selected()
        if not payment:
            return
        confirm = QMessageBox.question(
            self, t('Remove payment'),
            t('Remove this payment of {amount}?')
            .replace('{amount}', _money(payment.get('amount'))),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.api.delete(f"orders/{self.order_id}/payments/{payment['id']}/",
                        on_ok=lambda _p: self.reload(), on_error=self._on_error)

    def retranslate(self):
        self.title.setText(t('Payments'))
        self.new_btn.setText(t('New payment'))
        self.edit_btn.setText(t('Edit'))
        self.remove_btn.setText(t('Remove'))
        self.table.setHorizontalHeaderLabels([t(c) for c in PAYMENT_COLUMNS])
        self.breakdown.setHorizontalHeaderLabels(
            [t(c) for c in BREAKDOWN_COLUMNS])
