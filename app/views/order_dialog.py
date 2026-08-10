"""Create or edit an order by browsing the catalog and adding profiles.

Pick a client, then use the catalog on the left exactly as on the Catalog page --
search, filter, thumbnails -- and "Add to order" a profile. You choose the bar
length and either the metres needed (rounded up to whole bars) or a bar count;
weight and price follow. The order panel on the right shows the lines and the
live money (subtotal, tier discount, VAT, total). PDFs open once saved.
"""

import os
import subprocess
import sys
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.catalog import CatalogView

# The order lifecycle, in flow order (matches the backend OrderStatus).
ORDER_STATUSES = [
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('confirmed', 'Confirmed'),
    ('picking', 'Picking'),
    ('ready', 'Ready for delivery'),
    ('out_for_delivery', 'Out for delivery'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
]
from app.views.order_qty_dialog import OrderQtyDialog

VAT_PERCENT = Decimal('18')


def _dec(v):
    try:
        return Decimal(str(v or 0))
    except Exception:                                  # noqa: BLE001
        return Decimal('0')


def _open_file(path):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    elif os.name == 'nt':
        os.startfile(path)                             # noqa: E1101
    else:
        subprocess.Popen(['xdg-open', path])


class OrderDialog(QDialog):
    def __init__(self, api, session=None, order=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.session = session
        self.order = order
        self.order_id = order['id'] if order else None
        self.lines = []
        self.discount_percent = Decimal('0')
        self.setModal(True)
        self.setMinimumSize(1180, 720)
        self.setWindowTitle(t('Edit order') if order else t('New order'))
        self._build()
        self._load_clients()
        if order:
            self._load(order)

    # -- construction ----------------------------------------------------

    def _build(self):
        title_text = (f"{t('Order')} {self.order['number']}" if self.order
                      else t('New order'))
        self.title = QLabel(title_text, objectName='LoginTitle')

        self.client = QComboBox()
        self.client.setMinimumWidth(260)
        self.client.currentIndexChanged.connect(self._on_client_changed)

        self.has_date = QCheckBox(t('Required by'))
        self.has_date.toggled.connect(lambda on: self.required_by.setEnabled(on))
        self.required_by = QDateEdit()
        self.required_by.setCalendarPopup(True)
        self.required_by.setDisplayFormat('yyyy-MM-dd')
        self.required_by.setDate(QDate.currentDate().addDays(7))
        self.required_by.setEnabled(False)

        # Status control: office/managers can move an order along (e.g. to
        # 'ready' so a driver picks it up).
        self.status_combo = QComboBox()
        for value, label in ORDER_STATUSES:
            self.status_combo.addItem(t(label), value)
        self.status_btn = QPushButton(t('Update status'), objectName='Ghost')
        self.status_btn.clicked.connect(self._update_status)

        top = QHBoxLayout()
        top.addWidget(QLabel(t('Client'), objectName='FieldLabel'))
        top.addWidget(self.client)
        top.addSpacing(20)
        top.addWidget(self.has_date)
        top.addWidget(self.required_by)
        top.addStretch()
        top.addWidget(QLabel(t('Status'), objectName='FieldLabel'))
        top.addWidget(self.status_combo)
        top.addWidget(self.status_btn)

        # -- left: catalog picker --
        self.catalog = CatalogView(self.api, self.session, pick_mode=True)
        self.catalog.profile_picked.connect(self._on_profile_picked)
        self.catalog.load_filter_options()
        self.catalog.reload()

        # -- right: order panel --
        self.edit_line_btn = QPushButton(t('Edit line'), objectName='Ghost')
        self.remove_line_btn = QPushButton(t('Remove'), objectName='Ghost')
        self.edit_line_btn.clicked.connect(self._edit_line)
        self.remove_line_btn.clicked.connect(self._remove_line)
        line_bar = QHBoxLayout()
        line_bar.addWidget(QLabel(t('Order lines'), objectName='SectionTitle'))
        line_bar.addStretch()
        line_bar.addWidget(self.remove_line_btn)
        line_bar.addWidget(self.edit_line_btn)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            t('Profile'), t('Bars'), t('Metres'), t('Weight kg'), t('Line total')])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in (1, 2, 3, 4):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._edit_line)

        self.lbl_subtotal = QLabel('₪ 0.00')
        self.lbl_discount = QLabel('—')
        self.lbl_vat = QLabel('₪ 0.00')
        self.lbl_weight = QLabel('0 kg')
        self.lbl_total = QLabel('₪ 0.00', objectName='SectionTitle')
        totals = QVBoxLayout()
        totals.setSpacing(3)
        for label, widget in ((t('Subtotal'), self.lbl_subtotal),
                              (t('Discount'), self.lbl_discount),
                              (t('VAT'), self.lbl_vat),
                              (t('Total weight'), self.lbl_weight),
                              (t('Total'), self.lbl_total)):
            row = QHBoxLayout()
            row.addWidget(QLabel(label, objectName='Muted'))
            row.addStretch()
            row.addWidget(widget)
            totals.addLayout(row)

        self.notes = QPlainTextEdit(placeholderText=t('Notes'))
        self.notes.setFixedHeight(60)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        right.addLayout(line_bar)
        right.addWidget(self.table, 1)
        right.addLayout(totals)
        right.addWidget(self.notes)
        right_w = QWidget()
        right_w.setFixedWidth(420)
        right_w.setLayout(right)

        body = QHBoxLayout()
        body.setSpacing(18)
        body.addWidget(self.catalog, 1)
        body.addWidget(right_w)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.order_pdf_btn = QPushButton(t('Order note PDF'), objectName='Ghost')
        self.prep_btn = QPushButton(t('Prepare delivery'), objectName='Ghost')
        self.prep_btn.clicked.connect(self._prepare_delivery)
        self.delivery_pdf_btn = QPushButton(t('Delivery note PDF'), objectName='Ghost')
        self.order_pdf_btn.clicked.connect(lambda: self._open_pdf('order_note', 'order'))
        self.delivery_pdf_btn.clicked.connect(lambda: self._open_pdf('delivery_note', 'delivery'))
        self.invoice_btn = QPushButton(t('Create invoice'), objectName='Ghost')
        self.invoice_btn.clicked.connect(self._create_invoice)
        self.save_btn = QPushButton(t('Save order'))
        self.cancel_btn = QPushButton(t('Close'), objectName='Ghost')
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn.clicked.connect(self.reject)
        self._sync_pdf_buttons()
        buttons = QHBoxLayout()
        buttons.addWidget(self.order_pdf_btn)
        buttons.addWidget(self.prep_btn)
        buttons.addWidget(self.delivery_pdf_btn)
        buttons.addWidget(self.invoice_btn)
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)

        # Invoicing status: how much of the order has been invoiced.
        self.invoicing_label = QLabel('', objectName='CardHint')
        self.invoicing_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addLayout(top)
        layout.addLayout(body, 1)
        layout.addWidget(self.error)
        layout.addWidget(self.invoicing_label)
        layout.addLayout(buttons)
        self._refresh_invoicing()

    # -- clients ---------------------------------------------------------

    def _load_clients(self):
        self.api.get('clients/', {'active': 'true'},
                     on_ok=self._on_clients, on_error=lambda e: None)

    def _on_clients(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        self._clients = {c['id']: c for c in (rows or [])}
        self.client.blockSignals(True)
        self.client.clear()
        self.client.addItem(t('Select a client'), None)
        for c in rows or []:
            self.client.addItem(c['name'], c['id'])
        self.client.blockSignals(False)
        if self.order:
            idx = self.client.findData(self.order['client'])
            if idx >= 0:
                self.client.setCurrentIndex(idx)

    def _on_client_changed(self):
        cid = self.client.currentData()
        client = getattr(self, '_clients', {}).get(cid)
        disc = client and client.get('tier_discount_percent')
        self.discount_percent = _dec(disc) if disc is not None else Decimal('0')
        self._refresh_totals()

    # -- lines -----------------------------------------------------------

    def _on_profile_picked(self, row):
        dialog = OrderQtyDialog(self.api, row, editing=False, parent=self)
        if dialog.exec() and dialog.result_line:
            self.lines.append(dialog.result_line)
            self._refresh_table()

    def _edit_line(self, *_):
        r = self.table.currentRow()
        if r < 0 or r >= len(self.lines):
            return
        dialog = OrderQtyDialog(self.api, self.lines[r], editing=True, parent=self)
        if dialog.exec() and dialog.result_line:
            self.lines[r] = dialog.result_line
            self._refresh_table()

    def _remove_line(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.lines):
            del self.lines[r]
            self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(len(self.lines))
        for r, line in enumerate(self.lines):
            values = [
                line.get('number', ''),
                str(line.get('quantity') or '—'),
                str(line.get('total_length_m', '')),
                line.get('_weight', ''),
                f"₪ {_dec(line.get('_total')):,.2f}",
            ]
            for c, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if c >= 1:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self._refresh_totals()

    def _refresh_totals(self):
        subtotal = sum((_dec(l.get('_total')) for l in self.lines), Decimal('0'))
        weight = sum((_dec(l.get('_weight')) for l in self.lines), Decimal('0'))
        discount = (subtotal * self.discount_percent / 100).quantize(Decimal('0.01'))
        net = subtotal - discount
        vat = (net * VAT_PERCENT / 100).quantize(Decimal('0.01'))
        total = net + vat
        self.lbl_subtotal.setText(f'₪ {subtotal:,.2f}')
        self.lbl_discount.setText(
            f'-₪ {discount:,.2f} ({self.discount_percent:g}%)' if discount else '—')
        self.lbl_vat.setText(f'₪ {vat:,.2f} ({VAT_PERCENT:g}%)')
        self.lbl_weight.setText(f'{weight:g} kg')
        self.lbl_total.setText(f'₪ {total:,.2f}')

    # -- load existing ---------------------------------------------------

    def _load(self, order):
        if order.get('required_by'):
            self.has_date.setChecked(True)
            self.required_by.setDate(QDate.fromString(order['required_by'], 'yyyy-MM-dd'))
        self.notes.setPlainText(order.get('notes') or '')
        self.discount_percent = _dec(order.get('discount_percent'))
        self.lines = []
        for l in order.get('lines', []):
            line = dict(l)
            line['_weight'] = str(l.get('effective_weight_kg') or '')
            line['_total'] = str(l.get('line_total') or '')
            self.lines.append(line)
        self._refresh_table()

    # -- save ------------------------------------------------------------

    def _payload(self):
        cid = self.client.currentData()
        if not cid:
            self._show_error(t('Pick a client first.'))
            return None
        if not self.lines:
            self._show_error(t('Add at least one line.'))
            return None
        lines = [{
            'profile': l['profile'],
            'series': l.get('series'),
            'total_length_m': l['total_length_m'],
            'price_per_kg': l['price_per_kg'],
            'length_mm': l.get('length_mm'),
            'quantity': l.get('quantity'),
            'weight_kg_override': l.get('weight_kg_override'),
        } for l in self.lines]
        data = {'client': cid, 'notes': self.notes.toPlainText().strip(), 'lines': lines}
        data['required_by'] = (self.required_by.date().toString('yyyy-MM-dd')
                               if self.has_date.isChecked() else None)
        # Save the chosen status with the order, so "Save order" persists it too
        # (not only the separate Update-status button).
        if self.order_id:
            data['status'] = self.status_combo.currentData()
        return data

    def _save(self):
        data = self._payload()
        if data is None:
            return
        self.error.hide()
        self.save_btn.setEnabled(False)
        self.save_btn.setText(t('Saving…'))
        if self.order_id:
            self.api.patch(f'orders/{self.order_id}/', data,
                           on_ok=self._on_saved, on_error=self._on_error)
        else:
            self.api.post('orders/', data,
                          on_ok=self._on_saved, on_error=self._on_error)

    def _on_saved(self, order):
        self.order = order
        self.order_id = order.get('id')
        self.title.setText(f"{t('Order')} {order.get('number', '')}")
        self._load(order)
        self.save_btn.setEnabled(True)
        self.save_btn.setText(t('Save order'))
        self._sync_pdf_buttons()
        self._refresh_invoicing()

    def _on_error(self, error):
        self.save_btn.setEnabled(True)
        self.save_btn.setText(t('Save order'))
        self._show_error(error.message)

    # -- pdf -------------------------------------------------------------

    def _sync_pdf_buttons(self):
        ready = self.order_id is not None
        self.order_pdf_btn.setEnabled(ready)
        self.prep_btn.setEnabled(ready)
        self.delivery_pdf_btn.setEnabled(ready)
        self.invoice_btn.setEnabled(ready)
        # Status control only makes sense once the order exists.
        self.status_combo.setEnabled(ready)
        self.status_btn.setEnabled(ready)
        current = (self.order or {}).get('status')
        if current:
            idx = self.status_combo.findData(current)
            if idx >= 0:
                self.status_combo.blockSignals(True)
                self.status_combo.setCurrentIndex(idx)
                self.status_combo.blockSignals(False)

    # -- status ----------------------------------------------------------

    def _update_status(self):
        if not self.order_id:
            return
        new_status = self.status_combo.currentData()
        self.status_btn.setEnabled(False)
        self.status_btn.setText(t('Saving…'))
        self.api.post(f'orders/{self.order_id}/set_status/',
                      {'status': new_status},
                      on_ok=self._on_status_updated, on_error=self._on_status_error)

    def _on_status_updated(self, order):
        self.status_btn.setEnabled(True)
        self.status_btn.setText(t('Update status'))
        # set_status returns a minimal payload; keep the status on our order.
        if isinstance(order, dict) and order.get('status'):
            self.order = {**(self.order or {}), **order}
        self._show_error('')

    def _on_status_error(self, error):
        self.status_btn.setEnabled(True)
        self.status_btn.setText(t('Update status'))
        self._show_error(error.message)

    # -- invoicing -------------------------------------------------------

    def _refresh_invoicing(self):
        """Show how much of the order has been invoiced, from the order data."""
        order = self.order or {}
        if not self.order_id:
            self.invoicing_label.setText(t('Save the order to invoice it.'))
            return
        total = Decimal(str(order.get('total') or 0))
        invoiced = Decimal(str(order.get('invoiced_total') or 0))
        remaining = Decimal(str(order.get('remaining_to_invoice') or 0))
        if order.get('is_fully_invoiced'):
            self.invoicing_label.setText(
                t('Fully invoiced — ₪ {inv} of ₪ {total}.').format(
                    inv=f'{invoiced:,.2f}', total=f'{total:,.2f}'))
            self.invoice_btn.setText(t('Add invoice'))
        else:
            self.invoicing_label.setText(
                t('Invoiced ₪ {inv} of ₪ {total} · ₪ {rem} left.').format(
                    inv=f'{invoiced:,.2f}', total=f'{total:,.2f}',
                    rem=f'{remaining:,.2f}'))
            self.invoice_btn.setText(t('Create invoice'))

    def _create_invoice(self):
        if not self.order_id:
            return
        from app.views.invoice_dialog import InvoiceDialog
        dialog = InvoiceDialog(self.api, order=self.order, parent=self)
        if dialog.exec():
            # Re-fetch the order so the invoiced/remaining figures update.
            self.api.get(f'orders/{self.order_id}/',
                         on_ok=self._on_order_refreshed, on_error=lambda e: None)

    def _on_order_refreshed(self, order):
        self.order = order
        self._refresh_invoicing()

    def _prepare_delivery(self):
        """Open the loading dialog (loaded metres, load weight, shortage note)."""
        if not self.order_id:
            return
        from app.views.delivery_prep_dialog import DeliveryPrepDialog
        # Fetch the fresh order (with lines) so the dialog has current data.
        self.api.get(f'orders/{self.order_id}/', on_ok=self._open_prep,
                     on_error=self._on_error)

    def _open_prep(self, order):
        from app.views.delivery_prep_dialog import DeliveryPrepDialog
        self.order = order
        dialog = DeliveryPrepDialog(self.api, order, self)
        dialog.exec()

    def _open_pdf(self, kind, suffix):
        if not self.order_id:
            return
        number = (self.order or {}).get('number', 'order')
        btn = self.order_pdf_btn if kind == 'order_note' else self.delivery_pdf_btn
        btn.setEnabled(False)
        btn.setText(t('Opening…'))
        self.api.download_pdf(
            f'orders/{self.order_id}/{kind}/', f'{number}_{suffix}.pdf',
            on_ok=lambda path: self._on_pdf(path, kind),
            on_error=lambda e: self._on_pdf_err(e, kind))

    def _on_pdf(self, path, kind):
        _open_file(path)
        self._reset_pdf_btn(kind)

    def _on_pdf_err(self, error, kind):
        self._reset_pdf_btn(kind)
        self._show_error(error.message)

    def _reset_pdf_btn(self, kind):
        if kind == 'order_note':
            self.order_pdf_btn.setEnabled(True)
            self.order_pdf_btn.setText(t('Order note PDF'))
        else:
            self.delivery_pdf_btn.setEnabled(True)
            self.delivery_pdf_btn.setText(t('Delivery note PDF'))

    def _show_error(self, message):
        self.error.setText(message)
        self.error.show()
