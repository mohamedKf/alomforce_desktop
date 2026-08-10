"""Choose how much of a picked profile to add to an order.

Aluminium is sold in whole bars, so a length is always rounded UP to complete
bars: 19 m of a 6 m profile is 4 bars (24 m), never 3⅙. You enter either the
metres the customer needs (rounded up for you) or a bar count directly; weight
and price follow, both overridable.
"""

import math
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

DEFAULT_BAR_MM = 6000


def _dec(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0')


class OrderQtyDialog(QDialog):
    """Returns a line dict in `result_line` on accept.

    `source` is a catalog listing row (adding) or an existing order line (editing).
    """

    def __init__(self, api, source, editing=False, parent=None):
        super().__init__(parent)
        self.api = api
        self.src = source
        self.editing = editing
        self.result_line = None
        self._weight_auto = True
        self._suppress = False
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setWindowTitle(t('Edit line') if editing else t('Add to order'))
        self._build()
        self._prefill()

    # -- construction ----------------------------------------------------

    def _build(self):
        number = self.src.get('number', '')
        desc = self.src.get('description') or ''
        heading = QLabel(f'{number}', objectName='LoginTitle')
        sub = QLabel(desc, objectName='Muted')
        sub.setWordWrap(True)

        self.bar_len = QSpinBox()
        self.bar_len.setRange(1, 100_000)
        self.bar_len.setValue(DEFAULT_BAR_MM)
        self.bar_len.setSuffix(' mm')
        self.bar_len.valueChanged.connect(self._recompute)

        self.mode_meters = QRadioButton(t('By metres needed'))
        self.mode_bars = QRadioButton(t('By number of bars'))
        self.mode_meters.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.mode_meters)
        group.addButton(self.mode_bars)
        self.mode_meters.toggled.connect(self._on_mode)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_meters)
        mode_row.addWidget(self.mode_bars)
        mode_row.addStretch()

        self.meters_needed = QDoubleSpinBox()
        self.meters_needed.setRange(0, 1_000_000)
        self.meters_needed.setDecimals(2)
        self.meters_needed.setSuffix(' m')
        self.meters_needed.valueChanged.connect(self._recompute)

        self.bars = QSpinBox()
        self.bars.setRange(0, 1_000_000)
        self.bars.valueChanged.connect(self._recompute)

        # The whole-bar result, spelled out so the rounding is never a surprise.
        self.summary = QLabel('', objectName='SectionTitle')
        self.summary.setWordWrap(True)

        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 1_000_000)
        self.weight.setDecimals(2)
        self.weight.setSuffix(' kg')
        self.weight.valueChanged.connect(self._on_weight_edited)
        self.weight_note = QLabel('', objectName='Muted')

        self.price = QDoubleSpinBox()
        self.price.setRange(0, 1_000_000)
        self.price.setDecimals(2)
        self.price.setPrefix('₪ ')
        self.price.valueChanged.connect(self._recompute)

        self.total = QLabel('₪ 0.00', objectName='SectionTitle')

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow(t('Bar length'), self.bar_len)
        form.addRow(t('Enter by'), self._wrap(mode_row))
        form.addRow(t('Metres needed'), self.meters_needed)
        form.addRow(t('Number of bars'), self.bars)
        form.addRow('', self.summary)
        form.addRow(t('Weight'), self.weight)
        form.addRow('', self.weight_note)
        form.addRow(t('Price / kg'), self.price)
        form.addRow(t('Line total'), self.total)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()
        self.ok = QPushButton(t('Save') if self.editing else t('Add'))
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.ok.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.ok)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(sub)
        layout.addSpacing(4)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addLayout(buttons)
        self._on_mode()

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    # -- prefill ---------------------------------------------------------

    def _prefill(self):
        price = self.src.get('price_per_kg')
        if price is not None:
            self.price.setValue(float(price))
        if self.editing:
            if self.src.get('length_mm'):
                self.bar_len.setValue(int(self.src['length_mm']))
            if self.src.get('quantity'):
                self.mode_bars.setChecked(True)
                self.bars.setValue(int(self.src['quantity']))
            else:
                self.mode_meters.setChecked(True)
                self.meters_needed.setValue(float(self.src.get('total_length_m') or 0))
            if self.src.get('weight_kg_override') is not None:
                self._weight_auto = False
                self._suppress = True
                self.weight.setValue(float(self.src['weight_kg_override']))
                self._suppress = False
                self.weight_note.setText(t('Overridden'))
        self._recompute()

    # -- computation -----------------------------------------------------

    def _on_mode(self, *_):
        by_meters = self.mode_meters.isChecked()
        self.meters_needed.setEnabled(by_meters)
        self.bars.setEnabled(not by_meters)
        self._recompute()

    def _bar_len_m(self):
        return _dec(self.bar_len.value()) / Decimal(1000)

    def _bars_count(self):
        """Whole bars: rounded up from the metres needed, or entered directly."""
        bar_m = self._bar_len_m()
        if bar_m <= 0:
            return 0
        if self.mode_meters.isChecked():
            needed = _dec(self.meters_needed.value())
            if needed <= 0:
                return 0
            return math.ceil(needed / bar_m)
        return int(self.bars.value())

    def _recompute(self, *_):
        bars = self._bars_count()
        bar_m = self._bar_len_m()
        total_m = (Decimal(bars) * bar_m).quantize(Decimal('0.01'))
        # Spell out the whole-bar result, showing the round-up when it happened.
        if self.mode_meters.isChecked():
            needed = _dec(self.meters_needed.value())
            rounded = bars * bar_m > needed and needed > 0
            self.summary.setText(
                f'{bars} {t("bars")} × {bar_m:g} m = {total_m:g} m'
                + (f'  ({t("rounded up from")} {needed:g} m)' if rounded else ''))
        else:
            self.summary.setText(f'{bars} {t("bars")} × {bar_m:g} m = {total_m:g} m')

        if self._weight_auto:
            per_m = self.src.get('weight_g_per_m')
            if per_m:
                auto = (_dec(per_m) / Decimal(1000) * total_m).quantize(Decimal('0.01'))
                self._suppress = True
                self.weight.setValue(float(auto))
                self._suppress = False
                self.weight_note.setText(t('Auto from catalog weight'))
            else:
                self.weight_note.setText(t('No catalog weight — enter it'))
        self._total_m = total_m
        self._bars = bars
        self._update_total()

    def _on_weight_edited(self, _v):
        if not self._suppress:
            self._weight_auto = False
            self.weight_note.setText(t('Overridden'))
        self._update_total()

    def _update_total(self):
        total = (_dec(self.weight.value()) * _dec(self.price.value())).quantize(Decimal('0.01'))
        self.total.setText(f'₪ {total:,.2f}')

    # -- submit ----------------------------------------------------------

    def _submit(self):
        self.error.hide()
        if getattr(self, '_bars', 0) <= 0:
            self.error.setText(t('Enter the metres needed, or a number of bars.'))
            self.error.show()
            return
        weight = _dec(self.weight.value())
        price = _dec(self.price.value())
        line = {
            'profile': self.src.get('number'),
            'number': self.src.get('number'),
            'description': self.src.get('description') or '',
            'series': self.src.get('series_code') or self.src.get('series'),
            'weight_g_per_m': self.src.get('weight_g_per_m'),
            'length_mm': self.bar_len.value(),
            'quantity': self._bars,
            'total_length_m': f'{self._total_m:.2f}',
            'price_per_kg': f'{price:.2f}',
            'weight_kg_override': (None if self._weight_auto else f'{weight:.2f}'),
            '_weight': f'{weight:.2f}',
            '_total': f'{(weight * price):.2f}',
        }
        self.result_line = line
        self.accept()
