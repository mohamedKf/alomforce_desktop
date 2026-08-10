"""View and edit one payslip: hours, base/overtime, adjustment lines, total.

Generated slips arrive with the hours and pay filled from the worker's clocked
shifts; every field is editable while the slip is a draft. Finalising locks it;
a manager can reopen. Print opens the payslip PDF.
"""

import os
import subprocess
import sys
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import month_name, t


def _dec(v):
    try:
        return Decimal(str(v or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


def _open_file(path):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    elif os.name == 'nt':
        os.startfile(path)                             # noqa: E1101
    else:
        subprocess.Popen(['xdg-open', path])


class PayslipDialog(QDialog):
    def __init__(self, api, payslip, session=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.payslip = payslip
        self.pid = payslip['id']
        self.session = session
        self.setModal(True)
        self.setMinimumSize(560, 640)
        self.setWindowTitle(t('Payslip'))
        self._build()
        self._load(payslip)

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel('', objectName='LoginTitle')
        self.subtitle = QLabel('', objectName='Muted')

        self.f_days = QSpinBox()
        self.f_days.setRange(0, 366)
        self.f_reg = self._hours_spin()
        self.f_ot125 = self._hours_spin()
        self.f_ot150 = self._hours_spin()
        self.f_base = self._money_spin()
        self.f_ot_pay = self._money_spin()
        for w in (self.f_days, self.f_reg, self.f_ot125, self.f_ot150,
                  self.f_base, self.f_ot_pay):
            w.valueChanged.connect(self._recompute_total)

        form = QFormLayout()
        form.setSpacing(9)
        form.addRow(t('Days worked'), self.f_days)
        form.addRow(t('Regular hours'), self.f_reg)
        form.addRow(t('Overtime 125% hours'), self.f_ot125)
        form.addRow(t('Overtime 150% hours'), self.f_ot150)
        form.addRow(t('Base pay'), self.f_base)
        form.addRow(t('Overtime pay'), self.f_ot_pay)

        # adjustments table
        adj_header = QHBoxLayout()
        adj_header.addWidget(QLabel(t('Adjustments'), objectName='SectionTitle'))
        adj_header.addStretch()
        self.add_adj = QPushButton(t('Add line'), objectName='Ghost')
        self.remove_adj = QPushButton(t('Remove'), objectName='Ghost')
        self.add_adj.clicked.connect(lambda: self._add_adj_row('', 0))
        self.remove_adj.clicked.connect(self._remove_adj_row)
        adj_header.addWidget(self.remove_adj)
        adj_header.addWidget(self.add_adj)

        self.adj_table = QTableWidget(0, 2)
        self.adj_table.setHorizontalHeaderLabels([t('Label'), t('Amount (₪)')])
        self.adj_table.verticalHeader().setVisible(False)
        self.adj_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.adj_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.adj_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.adj_table.setFixedHeight(140)
        self.adj_table.itemChanged.connect(self._recompute_total)
        self.adj_hint = QLabel(t('Positive to add (bonus), negative to deduct (advance).'),
                               objectName='Muted')

        self.note = QPlainTextEdit(placeholderText=t('Notes'))
        self.note.setFixedHeight(52)

        self.total_label = QLabel('₪ 0.00', objectName='SectionTitle')
        total_row = QHBoxLayout()
        total_row.addWidget(QLabel(t('Total pay'), objectName='FieldLabel'))
        total_row.addStretch()
        total_row.addWidget(self.total_label)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        # buttons
        self.print_btn = QPushButton(t('Print PDF'), objectName='Ghost')
        self.reopen_btn = QPushButton(t('Reopen'), objectName='Ghost')
        self.finalise_btn = QPushButton(t('Finalise'))
        self.save_btn = QPushButton(t('Save'))
        self.close_btn = QPushButton(t('Close'), objectName='Ghost')
        self.print_btn.clicked.connect(self._print)
        self.reopen_btn.clicked.connect(self._reopen)
        self.finalise_btn.clicked.connect(self._finalise)
        self.save_btn.clicked.connect(self._save)
        self.close_btn.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.print_btn)
        buttons.addWidget(self.reopen_btn)
        buttons.addStretch()
        buttons.addWidget(self.close_btn)
        buttons.addWidget(self.save_btn)
        buttons.addWidget(self.finalise_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addSpacing(6)
        layout.addLayout(form)
        layout.addLayout(adj_header)
        layout.addWidget(self.adj_table)
        layout.addWidget(self.adj_hint)
        layout.addWidget(self.note)
        layout.addLayout(total_row)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

    @staticmethod
    def _hours_spin():
        s = QDoubleSpinBox()
        s.setRange(0, 1000)
        s.setDecimals(2)
        s.setSuffix(' h')
        return s

    @staticmethod
    def _money_spin():
        s = QDoubleSpinBox()
        s.setRange(0, 1_000_000)
        s.setDecimals(2)
        s.setPrefix('₪ ')
        return s

    # -- load ------------------------------------------------------------

    def _load(self, p):
        month = int(p.get('month') or 0)
        self.title.setText(
            f"{p.get('worker_name', '')} — {month_name(month)} {p.get('year')}")
        basis = {'hourly': 'By hour', 'daily': 'By day', 'monthly': 'Monthly salary'}.get(
            p.get('pay_basis'), '')
        self.subtitle.setText(
            f"{t(basis)} · {p.get('source_display', '')} · {p.get('status_display', '')}")
        self.f_days.setValue(int(p.get('days_worked') or 0))
        self.f_reg.setValue(float(p.get('regular_hours') or 0))
        self.f_ot125.setValue(float(p.get('overtime_125_hours') or 0))
        self.f_ot150.setValue(float(p.get('overtime_150_hours') or 0))
        self.f_base.setValue(float(p.get('base_pay') or 0))
        self.f_ot_pay.setValue(float(p.get('overtime_pay') or 0))
        self.adj_table.blockSignals(True)
        self.adj_table.setRowCount(0)
        for adj in p.get('adjustments', []):
            self._add_adj_row(adj.get('label', ''), float(adj.get('amount') or 0))
        self.adj_table.blockSignals(False)
        self.note.setPlainText(p.get('note') or '')
        self._recompute_total()
        self._apply_locked(p.get('is_final', False))

    def _apply_locked(self, is_final):
        editable = not is_final
        for w in (self.f_days, self.f_reg, self.f_ot125, self.f_ot150,
                  self.f_base, self.f_ot_pay, self.adj_table, self.note,
                  self.add_adj, self.remove_adj):
            w.setEnabled(editable)
        self.save_btn.setVisible(editable)
        self.finalise_btn.setVisible(editable)
        is_manager = (self.session.role if self.session else None) == 'manager'
        self.reopen_btn.setVisible(is_final and is_manager)

    # -- adjustments -----------------------------------------------------

    def _add_adj_row(self, label, amount):
        row = self.adj_table.rowCount()
        self.adj_table.insertRow(row)
        self.adj_table.setItem(row, 0, QTableWidgetItem(label))
        amt = QTableWidgetItem(f'{amount:g}')
        amt.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.adj_table.setItem(row, 1, amt)
        self._recompute_total()

    def _remove_adj_row(self):
        row = self.adj_table.currentRow()
        if row >= 0:
            self.adj_table.removeRow(row)
            self._recompute_total()

    def _adjustments(self):
        out = []
        for r in range(self.adj_table.rowCount()):
            label_item = self.adj_table.item(r, 0)
            amt_item = self.adj_table.item(r, 1)
            label = label_item.text().strip() if label_item else ''
            amount = _dec(amt_item.text() if amt_item else 0)
            if label:
                out.append({'label': label, 'amount': f'{amount:.2f}'})
        return out

    def _recompute_total(self, *_):
        adj = sum((_dec(a['amount']) for a in self._adjustments()), Decimal('0'))
        total = (_dec(self.f_base.value()) + _dec(self.f_ot_pay.value()) + adj)
        self.total_label.setText(f'₪ {total:,.2f}')

    # -- save / actions --------------------------------------------------

    def _payload(self):
        return {
            'days_worked': self.f_days.value(),
            'regular_hours': f'{_dec(self.f_reg.value()):.2f}',
            'overtime_125_hours': f'{_dec(self.f_ot125.value()):.2f}',
            'overtime_150_hours': f'{_dec(self.f_ot150.value()):.2f}',
            'base_pay': f'{_dec(self.f_base.value()):.2f}',
            'overtime_pay': f'{_dec(self.f_ot_pay.value()):.2f}',
            'adjustments': self._adjustments(),
            'note': self.note.toPlainText().strip(),
        }

    def _save(self, on_done=None):
        self.error.hide()
        self.save_btn.setEnabled(False)
        self.api.patch(f'payslips/{self.pid}/', self._payload(),
                       on_ok=lambda p: self._on_saved(p, on_done),
                       on_error=self._on_error)

    def _on_saved(self, payslip, on_done):
        self.payslip = payslip
        self.save_btn.setEnabled(True)
        if on_done:
            on_done()
        else:
            self.accept()

    def _finalise(self):
        # Save edits first, then lock.
        self._save(on_done=lambda: self.api.post(
            f'payslips/{self.pid}/finalise/', {},
            on_ok=lambda _p: self.accept(), on_error=self._on_error))

    def _reopen(self):
        self.api.post(f'payslips/{self.pid}/reopen/', {},
                      on_ok=lambda _p: self.accept(), on_error=self._on_error)

    def _print(self):
        self.print_btn.setEnabled(False)
        self.print_btn.setText(t('Opening…'))
        self.api.download_pdf(
            f'payslips/{self.pid}/pdf/', f'payslip_{self.pid}.pdf',
            on_ok=self._on_pdf, on_error=self._on_pdf_err)

    def _on_pdf(self, path):
        _open_file(path)
        self.print_btn.setEnabled(True)
        self.print_btn.setText(t('Print PDF'))

    def _on_pdf_err(self, error):
        self.print_btn.setEnabled(True)
        self.print_btn.setText(t('Print PDF'))
        self._show_error(error.message)

    def _on_error(self, error):
        self.save_btn.setEnabled(True)
        self._show_error(error.message)

    def _show_error(self, message):
        self.error.setText(message)
        self.error.show()
