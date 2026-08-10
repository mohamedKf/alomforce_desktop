"""Add or edit an income / expense invoice.

Income invoices can be linked to a client; expense invoices name a supplier
free-text. Money is entered as subtotal + VAT; the total fills in automatically
but can be overridden. A PDF or photo of the invoice can be attached.
"""

import os
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.forms import Field, validate_all

# Common categories per invoice direction (the values are English and stable;
# the dropdown shows them translated). Free text is still preserved on edit.
CATEGORIES = {
    'income': ['Sales', 'Service', 'Other'],
    'expense': ['Raw material', 'Fuel', 'Rent', 'Electricity', 'Tools',
                'Salaries', 'Maintenance', 'Shipping', 'Other'],
}



class InvoiceDialog(QDialog):
    def __init__(self, api, invoice=None, direction='income', order=None,
                 parent=None):
        super().__init__(parent)
        self.api = api
        self.invoice = invoice                       # None => add
        self.order = order                           # set when raised from an order
        self.direction = (invoice or {}).get('direction',
                                             'income' if order else direction)
        self._file_path = None
        self._clients_by_id = {}
        self.setModal(True)
        self.setMinimumWidth(460)
        is_income = self.direction == 'income'
        verb = t('Edit invoice') if invoice else (
            t('Add income invoice') if is_income else t('Add expense invoice'))
        self.setWindowTitle(verb)
        self._build()
        if invoice:
            self._load(invoice)
        else:
            # New income invoice: auto-fill the next number (INV-YYYY-NNNN).
            # Expense numbers come from the supplier, so they stay manual.
            if is_income:
                self.api.get('invoices/next_number/',
                             on_ok=self._on_next_number, on_error=lambda e: None)
            if order:
                self._prefill_from_order(order)
            elif is_income:
                self._load_clients()

    def _on_next_number(self, data):
        if isinstance(data, dict) and data.get('number') and not self.f_number.value():
            self.f_number.set_value(data['number'])

    # -- construction ----------------------------------------------------

    def _build(self):
        is_income = self.direction == 'income'
        self.heading = QLabel(
            t('Income invoice') if is_income else t('Expense invoice'),
            objectName='CardTitle')

        self.f_number = Field('Invoice number')
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)      # click to pick year / month / day
        self.date.setDisplayFormat('dd/MM/yyyy')
        self.date.setDate(QDate.currentDate())
        self.date.setButtonSymbols(QDateEdit.NoButtons)
        cal = self.date.calendarWidget()
        if cal is not None:
            cal.setGridVisible(True)

        # Income may link a client; expense names a supplier free-text.
        self.f_client = Field('Client', kind='combo', choices=[(None, '—')])
        self.f_party = Field('Supplier name' if not is_income else 'Party name')
        self.f_tax = Field('Party tax ID')
        cat_choices = [('', '—')] + [(c, c) for c in
                                     CATEGORIES.get(self.direction, [])]
        self.f_category = Field('Category', kind='combo', choices=cat_choices)

        # Money: enter the amount before VAT + the VAT rate; VAT ₪ and Total are
        # computed live, so changing the amount always updates the VAT.
        self.sp_subtotal = self._money()
        self.sp_vat_pct = self._money(maximum=100)
        self.sp_vat_pct.setValue(18.0)
        self.sp_vat = self._money()
        self.sp_vat.setReadOnly(True)
        self.sp_vat.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.sp_total = self._money()
        self.sp_total.setReadOnly(True)
        self.sp_total.setButtonSymbols(QDoubleSpinBox.NoButtons)
        self.sp_subtotal.valueChanged.connect(self._recompute)
        self.sp_vat_pct.valueChanged.connect(self._recompute)

        # Payment: how much has actually arrived; the balance is shown live and
        # the paid/unpaid status is derived from it on the server.
        self.sp_paid = self._money()
        self.lbl_remaining = QLabel('₪ 0.00', objectName='CardTitle')
        self.sp_paid.valueChanged.connect(self._recompute_remaining)

        self.f_notes = Field('Notes', kind='text')

        self.file_label = QLabel(t('No file attached'), objectName='CardHint')
        self.file_btn = QPushButton(t('Attach file…'), objectName='Ghost')
        self.file_btn.clicked.connect(self._pick_file)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_btn)
        file_row.addWidget(self.file_label, 1)

        self.error = QLabel('', objectName='FieldError')
        self.error.setWordWrap(True)
        self.error.hide()

        self.save_btn = QPushButton(t('Save'), objectName='PrimaryButton')
        self.save_btn.clicked.connect(self._save)
        cancel = QPushButton(t('Cancel'), objectName='Ghost')
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        # Sending only makes sense once the invoice exists (has an id / file).
        if self.invoice:
            self.email_btn = QPushButton(t('Email'), objectName='Ghost')
            self.email_btn.clicked.connect(self._send_email)
            self.whatsapp_btn = QPushButton(t('WhatsApp'), objectName='Ghost')
            self.whatsapp_btn.clicked.connect(self._send_whatsapp)
            actions.addWidget(self.email_btn)
            actions.addWidget(self.whatsapp_btn)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.heading)
        layout.addLayout(self._row(self.f_number, self._labeled(t('Issued at'), self.date)))
        if is_income:
            layout.addWidget(self.f_client)
        layout.addLayout(self._row(self.f_party, self.f_tax))
        layout.addWidget(self.f_category)
        layout.addLayout(self._row(
            self._labeled(t('Before VAT ₪'), self.sp_subtotal),
            self._labeled(t('VAT %'), self.sp_vat_pct),
            self._labeled(t('VAT ₪'), self.sp_vat),
            self._labeled(t('Total ₪'), self.sp_total)))
        # Payment tracking: amount paid + remaining balance.
        remaining_box = self._labeled(t('Remaining ₪'), self.lbl_remaining)
        layout.addLayout(self._row(
            self._labeled(t('Amount paid ₪'), self.sp_paid),
            remaining_box))
        layout.addWidget(self.f_notes)
        layout.addLayout(file_row)
        layout.addWidget(self.error)
        layout.addLayout(actions)

    def _money(self, maximum=100_000_000):
        s = QDoubleSpinBox()
        s.setRange(0, maximum)
        s.setDecimals(2)
        s.setMinimumHeight(36)
        return s

    @staticmethod
    def _labeled(label, widget):
        wrap = QWidget()
        box = QVBoxLayout(wrap)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        box.addWidget(QLabel(label, objectName='FieldLabel'))
        box.addWidget(widget)
        return wrap

    @staticmethod
    def _row(*widgets):
        row = QHBoxLayout()
        row.setSpacing(12)
        for w in widgets:
            (row.addLayout if not isinstance(w, QWidget) else row.addWidget)(w, 1)
        return row

    def _recompute(self, *_):
        """VAT ₪ = before-VAT amount × VAT%, Total = before-VAT + VAT — live."""
        subtotal = self.sp_subtotal.value()
        vat = round(subtotal * self.sp_vat_pct.value() / 100, 2)
        total = round(subtotal + vat, 2)
        for spin, value in ((self.sp_vat, vat), (self.sp_total, total)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._recompute_remaining()

    def _recompute_remaining(self, *_):
        remaining = max(0.0, self.sp_total.value() - self.sp_paid.value())
        self.lbl_remaining.setText(f'₪ {remaining:,.2f}')

    # -- clients ---------------------------------------------------------

    def _load_clients(self, selected=None):
        self.api.get('clients/', {'active': 'true'},
                     on_ok=lambda d: self._on_clients(d, selected),
                     on_error=lambda e: None)

    def _on_clients(self, payload, selected):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        # Keep each client's details so picking one can auto-fill the invoice.
        self._clients_by_id = {c['id']: c for c in (rows or [])}
        combo = self.f_client.input
        combo.blockSignals(True)
        combo.clear()
        combo.addItem('—', None)
        for c in rows or []:
            combo.addItem(c.get('name', ''), c['id'])
        combo.blockSignals(False)
        # Auto-fill party name / tax ID when a client is chosen.
        try:
            combo.currentIndexChanged.disconnect(self._on_client_selected)
        except (RuntimeError, TypeError):
            pass
        combo.currentIndexChanged.connect(self._on_client_selected)
        if selected:
            idx = combo.findData(selected)
            if idx >= 0:
                # Set programmatically without auto-filling, so an existing
                # invoice keeps its own stored party name / tax ID.
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

    def _on_client_selected(self, *_):
        """Fill party name and tax ID from the chosen client."""
        client = self._clients_by_id.get(self.f_client.value())
        if not client:
            return
        self.f_party.set_value(client.get('name'))
        self.f_tax.set_value(client.get('tax_id'))

    # -- load existing ---------------------------------------------------

    def _load(self, inv):
        self.f_number.set_value(inv.get('number'))
        if inv.get('issued_at'):
            self.date.setDate(QDate.fromString(inv['issued_at'], 'yyyy-MM-dd'))
        if self.direction == 'income':
            self._load_clients(inv.get('client'))
        self.f_party.set_value(inv.get('party_name'))
        self.f_tax.set_value(inv.get('party_tax_id'))
        # A saved category not in the standard list (old free text) is added so
        # it isn't lost on re-save.
        cat = inv.get('category') or ''
        combo = self.f_category.input
        if cat and combo.findData(cat) < 0:
            combo.addItem(t(cat), cat)
        self.f_category.set_value(cat)
        subtotal = float(inv.get('subtotal') or 0)
        total = float(inv.get('total') or 0)
        # Recover the VAT rate from the stored figures so editing stays live.
        pct = round((total / subtotal - 1) * 100, 2) if subtotal else 18.0
        self.sp_vat_pct.setValue(pct)
        self.sp_subtotal.setValue(subtotal)  # triggers _recompute (VAT + total)
        self.sp_paid.setValue(float(inv.get('amount_paid') or 0))
        self.f_notes.set_value(inv.get('notes'))
        if inv.get('file_url'):
            self.file_label.setText(t('File attached'))

    def _prefill_from_order(self, order):
        """Raised from an order: link it and default to the amount still owed.

        The before-VAT amount is what's left to invoice net of VAT; VAT and total
        recompute live, so editing the amount always keeps the VAT in step.
        """
        self._load_clients(order.get('client'))
        self.f_party.set_value(order.get('client_name'))
        try:
            remaining = float(order.get('remaining_to_invoice') or 0)
        except (TypeError, ValueError):
            remaining = 0.0
        vat_pct = float(order.get('vat_percent') or 18)
        self.sp_vat_pct.setValue(vat_pct)
        # remaining_to_invoice is a gross figure; store the net (before-VAT) part.
        subtotal = remaining / (1 + vat_pct / 100) if vat_pct else remaining
        self.sp_subtotal.setValue(round(subtotal, 2))  # _recompute fills VAT+total
        hint = QLabel(
            t('For order {number} — edit the amount to invoice part of it.')
            .format(number=order.get('number', '')), objectName='CardHint')
        hint.setWordWrap(True)
        self.layout().insertWidget(1, hint)

    # -- file ------------------------------------------------------------

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t('Choose an invoice file'), '',
            'Invoice (*.pdf *.png *.jpg *.jpeg *.webp)')
        if path:
            self._file_path = path
            self.file_label.setText(os.path.basename(path))

    # -- save ------------------------------------------------------------

    def _save(self):
        if not validate_all([self.f_party]) and not self.f_client.value():
            self.error.setText(t('Enter a party name or pick a client.'))
            self.error.show()
            return
        data = {
            'direction': self.direction,
            'number': self.f_number.value(),
            'client': self.f_client.value() if self.direction == 'income' else None,
            'order': (self.order or {}).get('id') or (self.invoice or {}).get('order'),
            'party_name': self.f_party.value(),
            'party_tax_id': self.f_tax.value(),
            'issued_at': self.date.date().toString('yyyy-MM-dd'),
            'category': self.f_category.value(),
            'subtotal': f'{self.sp_subtotal.value():.2f}',
            'vat': f'{self.sp_vat.value():.2f}',
            'total': f'{self.sp_total.value():.2f}',
            'amount_paid': f'{self.sp_paid.value():.2f}',
            'notes': self.f_notes.value(),
        }
        self.save_btn.setEnabled(False)
        self.save_btn.setText(t('Saving…'))
        if self.invoice:
            self.api.patch(f'invoices/{self.invoice["id"]}/', data,
                           on_ok=self._on_saved, on_error=self._on_error)
        else:
            self.api.post('invoices/', data,
                          on_ok=self._on_saved, on_error=self._on_error)

    def _on_saved(self, saved):
        # Attach the file (if any) once the invoice row exists.
        if self._file_path and isinstance(saved, dict) and saved.get('id'):
            self.api.upload(f'invoices/{saved["id"]}/', self._file_path,
                            field='file', method='PATCH',
                            on_ok=lambda _d: self.accept(),
                            on_error=self._on_error)
        else:
            self.accept()

    # -- send ------------------------------------------------------------

    def _send_email(self):
        from PySide6.QtWidgets import QInputDialog
        default = (self.invoice or {}).get('client_email') or ''
        to, ok = QInputDialog.getText(
            self, t('Email invoice'), t('Send to email address:'), text=default)
        if not ok or not to.strip():
            return
        self.email_btn.setEnabled(False)
        self.email_btn.setText(t('Sending…'))
        self.api.post(f'invoices/{self.invoice["id"]}/send_email/',
                      {'to': to.strip()},
                      on_ok=self._on_email_sent, on_error=self._on_send_error)

    def _on_email_sent(self, _data):
        self.email_btn.setEnabled(True)
        self.email_btn.setText(t('Email'))
        self.error.setObjectName('CardHint')
        self.error.setText(t('Invoice emailed.'))
        self.error.show()

    def _on_send_error(self, error):
        self.email_btn.setEnabled(True)
        self.email_btn.setText(t('Email'))
        self.error.setObjectName('FieldError')
        self.error.setText(error.message)
        self.error.show()

    def _send_whatsapp(self):
        # WhatsApp from the desktop can only carry text, so send a summary and a
        # note that the PDF follows by email. The number is optional.
        from urllib.parse import quote
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        inv = self.invoice or {}
        label = f"{inv.get('number') or ''}".strip()
        total = inv.get('total') or self.sp_total.value()
        party = inv.get('client_name') or inv.get('party_name') or ''
        text = t('Invoice {number} for {party}: ₪ {total}. The PDF follows by '
                 'email.').format(number=label, party=party, total=total)
        QDesktopServices.openUrl(QUrl(f'https://wa.me/?text={quote(text)}'))

    def _on_error(self, error):
        self.save_btn.setEnabled(True)
        self.save_btn.setText(t('Save'))
        self.error.setObjectName('FieldError')
        self.error.setText(error.message)
        self.error.show()
