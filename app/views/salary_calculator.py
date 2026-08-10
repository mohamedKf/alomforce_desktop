"""Salary calculator — a spreadsheet of workers for one month.

One row per worker, honouring that worker's pay basis (by hour / day / month),
loaded from their record. Enter (or load from the clock) the days and hours,
extra hours (125% / 150%), a car allowance and any other lump adjustment; the
Israeli-law total updates live. Per row: Calculate loads the worked hours from
the clock; the payslip button creates the month's payslip, or opens it if one
already exists.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import month_label, t
from app.views.payslip_dialog import PayslipDialog


class _CalcSpin(QDoubleSpinBox):
    """A grid spinbox that renders an empty (zero) value as a quiet dash.

    QSpinBox.specialValueText only fires at the field's minimum, so it can't
    dash a zero on a field that also allows negatives (the "Other" adjustment).
    Overriding textFromValue handles zero the same way whatever the range.
    """

    def textFromValue(self, value):
        if value == 0:
            return '—'
        return super().textFromValue(value)


OT1 = Decimal('1.25')
OT2 = Decimal('1.50')
MONTHLY_HOURS = Decimal('182')

COLUMNS = ['Worker', 'Basis', 'Rate ₪', 'Days', 'Reg h', '125% h', '150% h',
           'Car ₪', 'Other ₪', 'Total ₪', '']

BASIS_LABEL = {'hourly': 'Hour', 'daily': 'Day', 'monthly': 'Month'}


def _dec(v):
    try:
        return Decimal(str(v or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


class SalaryCalculatorPanel(QWidget):
    def __init__(self, api, session=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.session = session
        self.workers = []
        self.rows = []            # per-worker widget bundles
        self._existing = {}       # worker_id -> payslip dict for the period
        self._build()

    # -- construction ----------------------------------------------------

    def _build(self):
        self.month = QComboBox()
        for m in range(1, 13):
            self.month.addItem(month_label(m), m)
        self.year = QSpinBox()
        self.year.setRange(2020, 2100)
        today = date.today()
        self.year.setValue(today.year)
        self.month.setCurrentIndex(today.month - 1)
        self.month.currentIndexChanged.connect(self._load_existing)
        self.year.valueChanged.connect(self._load_existing)

        head = QHBoxLayout()
        head.addWidget(QLabel(t('Month'), objectName='FieldLabel'))
        head.addWidget(self.month)
        head.addWidget(self.year)
        head.addStretch()
        self.hint = QLabel('', objectName='Muted')
        head.addWidget(self.hint)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(50)
        headv = self.table.horizontalHeader()
        headv.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(COLUMNS)):
            headv.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        # The actions column holds two buttons. Pin it to a fixed width so the
        # stretchy Worker column can't squeeze it and clip the payslip label.
        headv.setSectionResizeMode(len(COLUMNS) - 1, QHeaderView.Fixed)
        self.table.setColumnWidth(len(COLUMNS) - 1, 216)
        headv.setHighlightSections(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(self.table, 1)

    # -- data ------------------------------------------------------------

    def set_workers(self, workers):
        self.workers = [w for w in (workers or []) if w.get('role') != 'client']
        self._build_rows()
        self._load_existing()

    def _spin(self, decimals=2, minimum=0, mn=64, mx=76):
        s = _CalcSpin(objectName='CalcCell')
        s.setRange(minimum, 10_000_000)
        s.setDecimals(decimals)
        # No spin arrows -- they steal width and clip the number. The field is
        # still typeable and scrollable; the arrows just add clutter here.
        s.setButtonSymbols(QDoubleSpinBox.NoButtons)
        s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s.setMinimumHeight(30)
        s.setMinimumWidth(mn)
        s.setMaximumWidth(mx)
        return s

    def _build_rows(self):
        self.table.setRowCount(0)
        self.rows = []
        for w in self.workers:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setCellWidget(r, 0, self._name_cell(w.get('full_name', '')))

            basis = w.get('pay_basis') or 'hourly'
            basis_label = QLabel(t(BASIS_LABEL.get(basis, 'Hour')))
            basis_label.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(r, 1, basis_label)

            rate = self._spin(mn=76, mx=94)          # up to a monthly salary
            rate.setValue(self._default_rate(w))
            days = QSpinBox(objectName='CalcCell')
            days.setRange(0, 366)
            days.setButtonSymbols(QSpinBox.NoButtons)
            days.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            days.setSpecialValueText('—')
            days.setMinimumHeight(30)
            days.setMinimumWidth(46)
            days.setMaximumWidth(54)
            reg = self._spin(decimals=1, mn=54, mx=64)    # hours: small numbers
            ot125 = self._spin(decimals=1, mn=54, mx=64)
            ot150 = self._spin(decimals=1, mn=54, mx=64)
            car = self._spin(mn=64, mx=78)
            other = self._spin(minimum=-10_000_000, mn=64, mx=78)
            for c, wdg in enumerate([rate, days, reg, ot125, ot150, car, other], start=2):
                self.table.setCellWidget(r, c, wdg)

            total = QLabel('—')
            total.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            total.setContentsMargins(8, 0, 8, 0)
            total.setMinimumWidth(90)
            total.setStyleSheet('font-weight:600;')
            self.table.setCellWidget(r, 9, total)

            # two buttons: Calculate (load hours from the clock) + payslip.
            calc_btn = QPushButton(t('Calculate'), objectName='SmallGhost')
            calc_btn.setMinimumWidth(76)
            pay_btn = QPushButton(t('Create payslip'), objectName='SmallGhost')
            pay_btn.setMinimumWidth(120)
            actions = QWidget()
            ah = QHBoxLayout(actions)
            ah.setContentsMargins(2, 4, 4, 4)
            ah.setSpacing(4)
            ah.addWidget(calc_btn)
            ah.addWidget(pay_btn)
            self.table.setCellWidget(r, 10, actions)

            bundle = {'worker': w, 'basis': basis, 'norm': _dec(w.get('daily_regular_hours') or 8),
                      'rate': rate, 'days': days, 'reg': reg, 'ot125': ot125,
                      'ot150': ot150, 'car': car, 'other': other, 'total': total,
                      'calc_btn': calc_btn, 'pay_btn': pay_btn}
            self.rows.append(bundle)
            calc_btn.clicked.connect(lambda _=False, b=bundle: self._calculate(b))
            pay_btn.clicked.connect(lambda _=False, b=bundle: self._payslip(b))
            for wdg in (rate, days, reg, ot125, ot150, car, other):
                wdg.valueChanged.connect(lambda _=0, b=bundle: self._recompute(b))
            self._recompute(bundle)

    def _name_cell(self, name):
        label = QLabel(name)
        label.setContentsMargins(10, 0, 6, 0)
        label.setStyleSheet('font-weight:600;')
        return label

    @staticmethod
    def _default_rate(w):
        basis = w.get('pay_basis') or 'hourly'
        if basis == 'daily':
            return float(w.get('daily_rate') or 0)
        if basis == 'monthly':
            return float(w.get('monthly_salary') or 0)
        return float(w.get('hourly_rate') or 0)

    def _load_existing(self, *_):
        self._existing = {}
        self.api.get('payslips/', {'year': self.year.value(),
                                   'month': self.month.currentData()},
                     on_ok=self._on_existing, on_error=lambda e: None)

    def _on_existing(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        for p in rows or []:
            if p.get('year') == self.year.value() and p.get('month') == self.month.currentData():
                self._existing[p['worker']] = p
        self.hint.setText(t('%d of %d workers have a payslip for this month.')
                          % (len(self._existing), len(self.rows)))
        for b in self.rows:
            self._sync_pay_button(b)

    def _sync_pay_button(self, b):
        has = self._existing.get(b['worker']['id']) is not None
        b['pay_btn'].setText(t('Show payslip') if has else t('Create payslip'))

    # -- compute (per pay basis) -----------------------------------------

    def _figures(self, b):
        rate = _dec(b['rate'].value())
        basis = b['basis']
        if basis == 'daily':
            base = _dec(b['days'].value()) * rate
            eff_hourly = rate / (b['norm'] or Decimal('8'))
        elif basis == 'monthly':
            base = rate
            eff_hourly = rate / MONTHLY_HOURS
        else:  # hourly
            base = _dec(b['reg'].value()) * rate
            eff_hourly = rate
        base = base.quantize(Decimal('0.01'))
        overtime = (_dec(b['ot125'].value()) * eff_hourly * OT1
                    + _dec(b['ot150'].value()) * eff_hourly * OT2).quantize(Decimal('0.01'))
        car = _dec(b['car'].value())
        other = _dec(b['other'].value())
        total = (base + overtime + car + other).quantize(Decimal('0.01'))
        return base, overtime, car, other, total

    def _recompute(self, b):
        _, _, _, _, total = self._figures(b)
        b['total'].setText('—' if total == 0 else f'₪ {total:,.2f}')

    # -- Calculate: load worked hours from the clock ---------------------

    def _calculate(self, b):
        b['calc_btn'].setEnabled(False)
        b['calc_btn'].setText(t('…'))
        self.api.get('attendance/payroll/', {
            'worker': b['worker']['id'],
            'month': f"{self.year.value():04d}-{self.month.currentData():02d}"},
            on_ok=lambda d: self._on_calculated(b, d),
            on_error=lambda e: self._reset_calc(b))

    def _on_calculated(self, b, data):
        self._reset_calc(b)
        # Fill the worked figures; the rate stays the worker's own.
        b['days'].setValue(int(data.get('days_worked') or 0))
        b['reg'].setValue(float(data.get('regular_hours') or 0))
        b['ot125'].setValue(float(data.get('overtime_125_hours') or 0))
        b['ot150'].setValue(float(data.get('overtime_150_hours') or 0))
        self._recompute(b)

    def _reset_calc(self, b):
        b['calc_btn'].setEnabled(True)
        b['calc_btn'].setText(t('Calculate'))

    # -- payslip: create or show -----------------------------------------

    def _payslip(self, b):
        existing = self._existing.get(b['worker']['id'])
        if existing:
            self.api.get(f'payslips/{existing["id"]}/',
                         on_ok=self._open_payslip, on_error=lambda e: None)
        else:
            self._create_payslip(b)

    def _create_payslip(self, b):
        base, overtime, car, other, total = self._figures(b)
        adjustments = []
        if car:
            adjustments.append({'label': t('Car allowance'), 'amount': f'{car:.2f}'})
        if other:
            adjustments.append({'label': t('Other'), 'amount': f'{other:.2f}'})
        data = {
            'worker': b['worker']['id'], 'year': self.year.value(),
            'month': self.month.currentData(), 'source': 'manual',
            'pay_basis': b['basis'], 'days_worked': b['days'].value(),
            'regular_hours': f"{_dec(b['reg'].value()):.2f}",
            'overtime_125_hours': f"{_dec(b['ot125'].value()):.2f}",
            'overtime_150_hours': f"{_dec(b['ot150'].value()):.2f}",
            'hourly_rate': f"{_dec(b['rate'].value()):.2f}",
            'base_pay': f'{base:.2f}', 'overtime_pay': f'{overtime:.2f}',
            'adjustments': adjustments,
        }
        b['pay_btn'].setEnabled(False)
        self.api.post('payslips/', data,
                      on_ok=lambda p: self._on_created(b, p),
                      on_error=lambda e: self._on_error(b, e))

    def _on_created(self, b, payslip):
        b['pay_btn'].setEnabled(True)
        self._existing[b['worker']['id']] = payslip
        self._sync_pay_button(b)
        PayslipDialog(self.api, payslip, self.session, self).exec()
        self._load_existing()

    def _on_error(self, b, error):
        b['pay_btn'].setEnabled(True)
        QMessageBox.warning(self, t('Payslip'), error.message)

    def _open_payslip(self, payslip):
        PayslipDialog(self.api, payslip, self.session, self).exec()
        self._load_existing()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        for b in self.rows:
            self._sync_pay_button(b)
            b['calc_btn'].setText(t('Calculate'))
