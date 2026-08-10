"""Salary screen — generate and manage monthly payslips."""

from datetime import date
from decimal import Decimal

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app import i18n
from app.i18n import month_label, month_name, t
from app.views.payslip_dialog import PayslipDialog
from app.views.salary_calculator import SalaryCalculatorPanel


class PayslipModel(QAbstractTableModel):
    COLUMNS = [
        ('worker_name', 'Worker'),
        ('period', 'Period'),
        ('total_hours', 'Hours'),
        ('total_pay', 'Total'),
        ('source_display', 'Source'),
        ('status_display', 'Status'),
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
            if key == 'period':
                return f"{month_name(int(row.get('month') or 0))} {row.get('year')}"
            if key == 'total_pay':
                return f"₪ {Decimal(row.get('total_pay') or 0):,.2f}"
            if key == 'total_hours':
                return f"{Decimal(row.get('total_hours') or 0):g}"
            if key == 'status_display':
                return t(row.get('status_display') or '')
            if key == 'source_display':
                return t(row.get('source_display') or '')
            return row.get(key) or '—'
        if role == Qt.FontRole and key in ('worker_name', 'total_pay'):
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.TextAlignmentRole and key in ('total_pay', 'total_hours'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and key == 'status_display':
            return QColor('#2E7D32') if row.get('status') == 'final' else QColor('#6B7785')
        return None

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class SalaryView(QWidget):
    def __init__(self, api, session=None):
        super().__init__()
        self.api = api
        self.session = session
        self.total = 0
        self._workers = []
        self.setObjectName('Canvas')
        self._build()
        self._load_workers()

    def _build(self):
        self.title = QLabel(t('Salary'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        # Payslips / Calculator toggle.
        self.tab_payslips = QPushButton(t('Payslips'), objectName='Segment')
        self.tab_calc = QPushButton(t('Calculator'), objectName='Segment')
        for b in (self.tab_payslips, self.tab_calc):
            b.setCheckable(True)
        self.tab_payslips.setChecked(True)
        self._tabs = QButtonGroup(self)
        self._tabs.setExclusive(True)
        self._tabs.addButton(self.tab_payslips, 0)
        self._tabs.addButton(self.tab_calc, 1)
        self._tabs.idClicked.connect(self._switch_tab)
        toggle = QHBoxLayout()
        toggle.setSpacing(0)
        toggle.addWidget(self.tab_payslips)
        toggle.addWidget(self.tab_calc)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        header.addLayout(toggle)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._payslips_page())
        self.calc_panel = SalaryCalculatorPanel(self.api, self.session)
        self.stack.addWidget(self.calc_panel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self.stack, 1)

    def _payslips_page(self):
        # generate controls
        self.gen_worker = QComboBox()
        self.gen_worker.setMinimumWidth(200)
        self.gen_month = QComboBox()
        for m in range(1, 13):
            self.gen_month.addItem(month_label(m), m)
        self.gen_year = QSpinBox()
        self.gen_year.setRange(2020, 2100)
        today = date.today()
        self.gen_year.setValue(today.year)
        self.gen_month.setCurrentIndex(today.month - 1)
        self.gen_btn = QPushButton(t('Generate payslip'))
        self.gen_btn.clicked.connect(self._generate)

        self.filter_worker = QComboBox()
        self.filter_worker.setMinimumWidth(180)
        self.filter_worker.currentIndexChanged.connect(self.reload)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(t('Show'), objectName='FieldLabel'))
        controls.addWidget(self.filter_worker)
        controls.addStretch()
        controls.addWidget(self.gen_worker)
        controls.addWidget(self.gen_month)
        controls.addWidget(self.gen_year)
        controls.addWidget(self.gen_btn)

        self.model = PayslipModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.doubleClicked.connect(self._open)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(PayslipModel.COLUMNS)):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        v.addLayout(controls)
        v.addWidget(self.status)
        v.addWidget(self.table, 1)
        return page

    def _switch_tab(self, index):
        self.stack.setCurrentIndex(index)

    # -- data ------------------------------------------------------------

    def _load_workers(self):
        self.api.get('staff/', on_ok=self._on_workers, on_error=lambda e: None)

    def _on_workers(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        self._workers = [w for w in (rows or []) if w.get('role') != 'client']
        for combo, first in ((self.gen_worker, None), (self.filter_worker, t('All workers'))):
            combo.blockSignals(True)
            combo.clear()
            if first is not None:
                combo.addItem(first, None)
            for w in self._workers:
                combo.addItem(w.get('full_name', ''), w['id'])
            combo.blockSignals(False)
        self.calc_panel.set_workers(self._workers)
        self.reload()

    def reload(self):
        params = {}
        if wid := self.filter_worker.currentData():
            params['worker'] = wid
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('payslips/', params, on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        rows = rows if isinstance(rows, list) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else len(rows)
        self.model.set_rows(rows)
        if rows:
            self.status.hide()
        else:
            self.status.setText(t('No payslips yet.'))
        self.count.setText(f'{self.total:,} {t("payslips")}')

    def _on_error(self, error):
        self.model.set_rows([])
        self.status.setText(error.message)
        self.status.show()

    # -- actions ---------------------------------------------------------

    def _generate(self):
        wid = self.gen_worker.currentData()
        if not wid:
            return
        data = {'worker': wid, 'year': self.gen_year.value(),
                'month': self.gen_month.currentData()}
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText(t('Generating…'))
        self.api.post('payslips/generate/', data,
                      on_ok=self._on_generated, on_error=self._on_gen_error)

    def _on_generated(self, payslip):
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText(t('Generate payslip'))
        dialog = PayslipDialog(self.api, payslip, self.session, self)
        dialog.exec()
        self.reload()

    def _on_gen_error(self, error):
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText(t('Generate payslip'))
        self.status.setText(error.message)
        self.status.show()

    def _open(self, index):
        row = self.model.row_at(index)
        if not row:
            return
        # Fetch the full payslip (with adjustments) before opening the editor.
        self.api.get(f'payslips/{row["id"]}/', on_ok=self._open_dialog,
                     on_error=self._on_error)

    def _open_dialog(self, payslip):
        dialog = PayslipDialog(self.api, payslip, self.session, self)
        dialog.exec()
        self.reload()

    def retranslate(self):
        self.title.setText(t('Salary'))
        self.gen_btn.setText(t('Generate payslip'))
        self.tab_payslips.setText(t('Payslips'))
        self.tab_calc.setText(t('Calculator'))
        self.calc_panel.retranslate()
        self.count.setText(f'{self.total:,} {t("payslips")}' if self.total else '')
        self.model.headerDataChanged.emit(Qt.Horizontal, 0, len(PayslipModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
