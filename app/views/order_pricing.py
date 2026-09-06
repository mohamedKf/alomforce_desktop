"""תמחור — what this customer pays for this job.

Aluminium is sold by the kilo at a price that moves with the metal and with
what the fabricator is worth to the shop, so it is settled per job rather than
held in a table. That is what this screen is: the list of what was ordered, a
box against each line, and somebody deciding.

What the customer paid last time is offered in its own column and copied
across on request. It is never applied on its own. An empty price stays empty
until a person fills it, because the alternative is a quote that gives the
metal away at zero and goes out over the shop's name.

The totals recompute as you type, so the office can see what a discount does
before committing to it. Nothing is sent until Save.
"""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QInputDialog,
    QMessageBox,
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

from app.i18n import t

COLUMNS = ['Profile', 'Weight kg', 'Last price', 'Price per kg',
           'Discount %', 'Line total']
PRICE_COL = 3
DISCOUNT_COL = 4

MUTED = QColor('#6b7280')
WARN = QColor('#b45309')


def _dec(value):
    try:
        text = str(value).strip()
        return Decimal(text) if text else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def _num(value):
    """A number as a person writes it: 50, not 50.00 — but 2.5 stays 2.5."""
    amount = _dec(value)
    if amount is None:
        return ''
    text = f'{amount:f}'
    return (text.rstrip('0').rstrip('.') if '.' in text else text) or '0'


def _money(value):
    return f'₪ {_dec(value) or Decimal("0"):,.2f}'


class OrderPricing(QWidget):
    """The pricing sheet for one order."""

    def __init__(self, api, order_id=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.order_id = order_id
        self.rows = []
        self.client = {}
        self.totals = {}
        self.setObjectName('Canvas')
        self._loading = False
        self._build()
        self.reload()

    def _build(self):
        self.title = QLabel(t('Pricing'), objectName='SectionTitle')
        self.fill_btn = QPushButton(t('Use last prices'), objectName='Ghost')
        self.quote_btn = QPushButton(t('Price quote PDF'), objectName='Ghost')
        self.send_btn = QPushButton(t('Send to client'), objectName='Ghost')
        self.save_btn = QPushButton(t('Save prices'), objectName='PrimaryButton')
        self.fill_btn.clicked.connect(self._fill_from_catalogue)
        self.quote_btn.clicked.connect(self._open_quote)
        self.send_btn.clicked.connect(self._send_quote)
        self.save_btn.clicked.connect(self._save)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.fill_btn)
        header.addWidget(self.quote_btn)
        header.addWidget(self.send_btn)
        header.addWidget(self.save_btn)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked
                                   | QAbstractItemView.SelectedClicked
                                   | QAbstractItemView.EditKeyPressed
                                   | QAbstractItemView.AnyKeyPressed)
        self.table.itemChanged.connect(self._cell_changed)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, len(COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)

        # The order's own discount, applied to the sum after each line has had
        # its own — which is what "and another two off the lot" means.
        self.discount = QDoubleSpinBox()
        self.discount.setRange(0, 100)
        self.discount.setDecimals(2)
        self.discount.setSuffix(' %')
        self.discount.setFixedWidth(110)
        self.discount.valueChanged.connect(self._recalculate)
        self.vat = QDoubleSpinBox()
        self.vat.setRange(0, 100)
        self.vat.setDecimals(2)
        self.vat.setSuffix(' %')
        self.vat.setFixedWidth(110)
        self.vat.valueChanged.connect(self._recalculate)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(t('Discount on the order'),
                                  objectName='FieldLabel'))
        controls.addWidget(self.discount)
        controls.addSpacing(18)
        controls.addWidget(QLabel(t('VAT'), objectName='FieldLabel'))
        controls.addWidget(self.vat)
        controls.addStretch()

        self.grand = QLabel('', objectName='PageTitle')
        self.grand.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.detail = QLabel('', objectName='CardHint')
        self.detail.setWordWrap(True)
        summary = QFrame(objectName='Card')
        summary_box = QVBoxLayout(summary)
        summary_box.setContentsMargins(16, 12, 16, 12)
        summary_box.setSpacing(4)
        summary_box.addWidget(self.grand)
        summary_box.addWidget(self.detail)

        # Said plainly rather than left for the quote to refuse: the office
        # should know what is missing while it still has the sheet open.
        self.warning = QLabel('', objectName='Error')
        self.warning.setWordWrap(True)
        self.warning.hide()

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.warning)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addLayout(controls)
        layout.addWidget(summary)

    # -- data --------------------------------------------------------------

    def set_order(self, order_id):
        self.order_id = order_id
        self.reload()

    def reload(self):
        if self.order_id is None:
            return
        self.status.setText(t('Loading…'))
        self.api.get(f'orders/{self.order_id}/pricing/',
                     on_ok=self._on_data, on_error=self._on_error)

    def _on_data(self, payload):
        payload = payload or {}
        self.rows = payload.get('lines') or []
        self.client = payload.get('client') or {}
        self.totals = payload.get('totals') or {}
        self.status.setText('' if self.rows else t('Nothing on this order yet.'))

        # Blocked while filling, or every cell written would be read back as
        # somebody typing and the table would fight the data it was given.
        self._loading = True
        try:
            self.discount.setValue(
                float(_dec(self.totals.get('discount_percent')) or 0))
            self.vat.setValue(float(_dec(self.totals.get('vat_percent')) or 0))
            self.table.setRowCount(len(self.rows))
            for row, line in enumerate(self.rows):
                self._fill_row(row, line)
        finally:
            self._loading = False
        self._recalculate()

    def _fill_row(self, row, line):
        # Led by what the workshop calls it -- the series number and what the
        # part does -- with the catalogue code after it. A fitter asks for
        # "1700 צד"; 05980 is what is printed on the rack label.
        head = '  '.join(part for part in (line.get('series_code'),
                                           line.get('name')) if part)
        name = f"{head or line.get('profile') or ''}"
        tail = '  ·  '.join(part for part in (line.get('profile'),
                                              line.get('series')) if part)
        if tail:
            name += f"      {tail}"
        # Priced by the kilo, so the quantity that matters is the weight.
        quantity = _num(line.get('weight_kg'))
        suggested = line.get('suggested_price')

        item = QTableWidgetItem(name)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item)

        cell = QTableWidgetItem(quantity)
        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 1, cell)

        # What this client paid last time, in its own column rather than
        # greyed into the price box. A number sitting in the box a person is
        # about to type in reads as a price somebody set, and half of them
        # would be left as they are.
        cell = QTableWidgetItem(_money(suggested) if suggested else '—')
        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cell.setForeground(QBrush(MUTED))
        self.table.setItem(row, 2, cell)

        price = _dec(line.get('price_per_kg')) or Decimal('0')
        cell = QTableWidgetItem('' if line.get('needs_a_price') else _num(price))
        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, PRICE_COL, cell)

        discount = _dec(line.get('discount_percent')) or Decimal('0')
        cell = QTableWidgetItem(_num(discount) if discount else '')
        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, DISCOUNT_COL, cell)

        cell = QTableWidgetItem('')
        cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.table.setItem(row, 5, cell)

    # -- arithmetic --------------------------------------------------------

    def _row_price(self, row):
        item = self.table.item(row, PRICE_COL)
        return _dec(item.text()) if item else None

    def _row_discount(self, row):
        item = self.table.item(row, DISCOUNT_COL)
        value = _dec(item.text()) if item else None
        if value is None:
            return Decimal('0')
        return min(max(value, Decimal('0')), Decimal('100'))

    def _cell_changed(self, item):
        if self._loading or item.column() not in (PRICE_COL, DISCOUNT_COL):
            return
        self._recalculate()

    def _recalculate(self):
        """The same sums the server does, so the screen and the quote agree.

        Refused mid-load. Setting the two spin boxes fires valueChanged, and
        that lands while `rows` holds the new lines but the table still holds
        the old cells -- totals written against a row that is not there yet,
        and every line read as unpriced.
        """
        if self._loading:
            return
        subtotal = Decimal('0.00')
        unpriced = []
        for row, line in enumerate(self.rows):
            price = self._row_price(row)
            base = _dec(line.get('weight_kg')) or Decimal('0')
            cell = self.table.item(row, 5)
            if price is None or price == 0:
                unpriced.append(line.get('profile') or '')
                if cell:
                    cell.setText('—')
                    cell.setForeground(QBrush(WARN))
                continue
            gross = (base * price).quantize(Decimal('0.01'))
            discount = self._row_discount(row)
            total = gross - (gross * discount / Decimal('100')
                             ).quantize(Decimal('0.01'))
            subtotal += total
            if cell:
                cell.setText(_money(total))
                cell.setForeground(QBrush(QColor('#111827')))

        order_discount = Decimal(str(self.discount.value()))
        discount_amount = (subtotal * order_discount
                           / Decimal('100')).quantize(Decimal('0.01'))
        net = subtotal - discount_amount
        vat = (net * Decimal(str(self.vat.value())) / Decimal('100')
               ).quantize(Decimal('0.01'))

        self.grand.setText(f"{t('Quote total')}  {_money(net + vat)}")
        parts = [f"{t('Subtotal')} {_money(subtotal)}"]
        if discount_amount:
            parts.append(f"{t('Discount')} -{_money(discount_amount)}")
        parts.append(f"{t('VAT')} {_money(vat)}")
        self.detail.setText('     ·     '.join(parts))

        if unpriced:
            self.warning.setText(
                f"{t('Still need a price')}: {', '.join(unpriced)}")
            self.warning.show()
        else:
            # Cleared, not just hidden: a stale message reappearing the next
            # time something unrelated shows this label is worse than none.
            self.warning.setText('')
            self.warning.hide()
        self.quote_btn.setEnabled(not unpriced and bool(self.rows))
        self.send_btn.setEnabled(not unpriced and bool(self.rows))

    def _fill_from_catalogue(self):
        """Copy last time's prices into the empty boxes — only the empty ones.

        A price somebody typed is a decision. Overwriting it with an old figure
        because a button was pressed would quietly undo it.
        """
        self._loading = True
        try:
            for row, line in enumerate(self.rows):
                suggested = _dec(line.get('suggested_price'))
                if suggested is None:
                    continue
                if self._row_price(row):
                    continue
                item = self.table.item(row, PRICE_COL)
                if item:
                    item.setText(_num(suggested))
        finally:
            self._loading = False
        self._recalculate()

    # -- saving ------------------------------------------------------------

    def _payload(self):
        lines = []
        for row, line in enumerate(self.rows):
            price = self._row_price(row)
            lines.append({
                'id': line.get('id'),
                'price_per_kg': '' if price is None else str(price),
                'discount_percent': str(self._row_discount(row)),
            })
        return {'lines': lines,
                'discount_percent': str(Decimal(str(self.discount.value()))),
                'vat_percent': str(Decimal(str(self.vat.value())))}

    def _save(self, *, then=None):
        if self.order_id is None:
            return
        self.save_btn.setEnabled(False)
        self.save_btn.setText(t('Saving…'))

        def done(payload):
            self.save_btn.setEnabled(True)
            self.save_btn.setText(t('Save prices'))
            self._on_data(payload)
            if then:
                then()

        def failed(error):
            self.save_btn.setEnabled(True)
            self.save_btn.setText(t('Save prices'))
            self._on_error(error)

        self.api.post(f'orders/{self.order_id}/pricing/', self._payload(),
                      on_ok=done, on_error=failed)

    def _open_quote(self):
        """Save first, then print.

        Otherwise the office types a price, prints, and hands the client a
        quote made from the figures before the edit.
        """
        self._ensure_tax_id()
        self._save(then=self._download_quote)

    def _ensure_tax_id(self):
        """The client's ח.פ / ע.מ, before a document carrying it goes out.

        Asked once and filed against the client, so the next quote and the
        invoice that follows both have it without anybody typing it again.
        """
        from app.views.tax_id_prompt import ensure_tax_id

        client = self.client or {}
        if not client.get('id') or (client.get('tax_id') or '').strip():
            return
        value = ensure_tax_id(self.api, client.get('id'), client.get('name'),
                              client.get('tax_id'), parent=self)
        if value:
            client['tax_id'] = value

    def _download_quote(self):
        self.quote_btn.setEnabled(False)
        self.quote_btn.setText(t('Opening…'))

        def done(path):
            self.quote_btn.setEnabled(True)
            self.quote_btn.setText(t('Price quote PDF'))
            _open_file(path)

        def failed(error):
            self.quote_btn.setEnabled(True)
            self.quote_btn.setText(t('Price quote PDF'))
            self._on_error(error)

        self.api.download_pdf(f'orders/{self.order_id}/quote/', 'quote.pdf',
                              on_ok=done, on_error=failed)

    # -- sending it --------------------------------------------------------

    def _send_quote(self):
        """Email the quote — after saying out loud where it is going.

        An email cannot be recalled, so the address and the total are put in
        front of the person pressing the button rather than assumed from the
        client record.
        """
        address, ok = QInputDialog.getText(
            self, t('Send to client'), t('Email address'),
            text=self.client.get('email') or '')
        address = (address or '').strip()
        if not ok or not address:
            return
        confirmed = QMessageBox.question(
            self, t('Send to client'),
            f"{t('Send this quote to')} {address}?\n\n"
            f"{self.client.get('name') or ''}\n"
            f"{self.grand.text()}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirmed != QMessageBox.Yes:
            return
        # Saved first, or the client is sent the figures from before the edit.
        self._save(then=lambda: self._post_send(address))

    def _post_send(self, address):
        self.send_btn.setEnabled(False)
        self.send_btn.setText(t('Sending…'))

        def done(payload):
            self.send_btn.setText(t('Send to client'))
            self.send_btn.setEnabled(True)
            QMessageBox.information(
                self, t('Send to client'),
                f"{t('Quote sent to')} {(payload or {}).get('to', address)}")

        def failed(error):
            self.send_btn.setText(t('Send to client'))
            self.send_btn.setEnabled(True)
            self._on_error(error)

        self.api.post(f'orders/{self.order_id}/send_quote/', {'to': address},
                      on_ok=done, on_error=failed)

    def _on_error(self, error):
        self.status.setText('')
        self.warning.setText(getattr(error, 'message', str(error)))
        self.warning.show()


def _open_file(path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
