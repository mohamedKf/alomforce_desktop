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
    QFrame,
    QHBoxLayout,
    QApplication,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
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
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)
        layout.addWidget(self._header())
        layout.addWidget(self._quantity_card())
        layout.addWidget(self._money_card())

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        self.ok = QPushButton(t('Save') if self.editing else t('Add'),
                              objectName='PrimaryButton')
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.ok.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        # Enter adds the line: this dialog is used dozens of times per order,
        # and reaching for the mouse each time is most of the work.
        self.ok.setDefault(True)
        self.ok.setAutoDefault(True)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.ok)
        layout.addLayout(buttons)

        self._on_mode()

    # -- the profile being added -----------------------------------------

    def _header(self):
        """What is being added, said once and clearly."""
        number = QLabel(str(self.src.get('number', '')), objectName='LoginTitle')
        desc = QLabel(self.src.get('description') or '', objectName='Muted')
        desc.setWordWrap(True)
        # A profile number is all digits, and Qt reads a label's direction from
        # its own text -- so in Hebrew the number drifted to the opposite edge
        # from the description under it. AlignLeading does not help here
        # because the label resolves it against its own detected direction, so
        # the side is chosen from the window's instead.
        # AlignAbsolute means "this physical side", so a Hebrew description in
        # an English window does not swing to the far edge from its number.
        edge = ((Qt.AlignRight if QApplication.isRightToLeft() else Qt.AlignLeft)
                | Qt.AlignAbsolute)
        for label in (number, desc):
            label.setAlignment(edge | Qt.AlignVCenter)

        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(number)
        box.addWidget(desc)

        # Series and catalogue weight, because the weight below is derived
        # from the latter and it should not look like it came from nowhere.
        facts = []
        if series := (self.src.get('series_code') or self.src.get('series')):
            facts.append(str(series))
        if per_m := self.src.get('weight_g_per_m'):
            facts.append(f'{_dec(per_m):g} {t("g/m")}')
        if facts:
            chips = QLabel('  ·  '.join(facts), objectName='CardHint')
            chips.setAlignment(edge | Qt.AlignVCenter)
            box.addWidget(chips)

        holder = QWidget()
        holder.setLayout(box)
        return holder

    # -- how much ---------------------------------------------------------

    def _quantity_card(self):
        card = QFrame(objectName='SettingsCard')

        self.bar_len = QSpinBox()
        self.bar_len.setRange(1, 100_000)
        self.bar_len.setValue(DEFAULT_BAR_MM)
        self.bar_len.setSuffix(f' {t("mm")}')
        self.bar_len.setMinimumWidth(130)
        self.bar_len.valueChanged.connect(self._recompute)

        # A segmented pair rather than two radios: it is a choice between two
        # ways of saying the same thing, and only one field applies at a time.
        self.mode_meters = QPushButton(t('Metres needed'), objectName='Segment')
        self.mode_bars = QPushButton(t('Number of bars'), objectName='Segment')
        for button in (self.mode_meters, self.mode_bars):
            button.setCheckable(True)
        self.mode_meters.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.mode_meters)
        group.addButton(self.mode_bars)
        self.mode_meters.toggled.connect(self._on_mode)
        modes = QHBoxLayout()
        modes.setSpacing(0)
        modes.addWidget(self.mode_meters)
        modes.addWidget(self.mode_bars)
        modes.addStretch()

        self.meters_needed = QDoubleSpinBox()
        self.meters_needed.setRange(0, 1_000_000)
        self.meters_needed.setDecimals(2)
        self.meters_needed.setSuffix(f' {t("m")}')
        self.meters_needed.valueChanged.connect(self._recompute)

        self.bars = QSpinBox()
        self.bars.setRange(0, 1_000_000)
        self.bars.setSuffix(f' {t("bars")}')
        self.bars.valueChanged.connect(self._recompute)

        # Only the field that matches the chosen mode is shown, so there is
        # never a greyed-out box inviting a click that does nothing.
        self.qty_stack = QStackedWidget()
        self.qty_stack.addWidget(self.meters_needed)
        self.qty_stack.addWidget(self.bars)
        self.qty_stack.setFixedHeight(self.meters_needed.sizeHint().height() + 2)

        fields = QFormLayout()
        fields.setSpacing(10)
        fields.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        fields.addRow(self._label(t('Bar length')), self.bar_len)
        fields.addRow(self._label(t('Enter by')), self._wrap(modes))
        fields.addRow(self._label(t('Amount')), self.qty_stack)

        # The whole-bar result, spelled out so the rounding is never a surprise.
        self.summary = QLabel('', objectName='SectionTitle')
        self.summary.setWordWrap(True)
        self.rounding_note = QLabel('', objectName='CardHint')
        self.rounding_note.setWordWrap(True)
        self.rounding_note.hide()

        result = QVBoxLayout()
        result.setSpacing(2)
        result.addWidget(self.summary)
        result.addWidget(self.rounding_note)
        result_box = QFrame(objectName='Panel')
        result_box.setLayout(result)
        result.setContentsMargins(12, 10, 12, 10)

        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(12)
        box.addWidget(QLabel(t('How much'), objectName='CardTitle'))
        box.addLayout(fields)
        box.addWidget(result_box)
        return card

    # -- what it costs ----------------------------------------------------

    def _money_card(self):
        card = QFrame(objectName='SettingsCard')

        self.weight = QDoubleSpinBox()
        self.weight.setRange(0, 1_000_000)
        self.weight.setDecimals(2)
        self.weight.setSuffix(f' {t("kg")}')
        self.weight.valueChanged.connect(self._on_weight_edited)
        self.weight_note = QLabel('', objectName='CardHint')
        self.weight_note.setWordWrap(True)

        weight_box = QVBoxLayout()
        weight_box.setSpacing(2)
        weight_box.addWidget(self.weight)
        weight_box.addWidget(self.weight_note)

        self.price = QDoubleSpinBox()
        self.price.setRange(0, 1_000_000)
        self.price.setDecimals(2)
        self.price.setPrefix('₪ ')
        self.price.valueChanged.connect(self._recompute)

        fields = QFormLayout()
        fields.setSpacing(10)
        fields.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        fields.addRow(self._label(t('Weight')), self._wrap(weight_box))
        fields.addRow(self._label(t('Price / kg')), self.price)

        # The number the customer is quoted, given the weight it deserves.
        self.total = QLabel('₪ 0.00', objectName='StatValue')
        total_box = QVBoxLayout()
        total_box.setContentsMargins(14, 10, 14, 10)
        total_box.setSpacing(0)
        total_box.addWidget(QLabel(t('Line total'), objectName='StatCaption'))
        total_box.addWidget(self.total)
        total_tile = QFrame(objectName='StatTile')
        total_tile.setProperty('accent', 'true')
        total_tile.setLayout(total_box)

        box = QVBoxLayout(card)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(12)
        box.addWidget(QLabel(t('Price'), objectName='CardTitle'))
        box.addLayout(fields)
        box.addWidget(total_tile)
        return card

    @staticmethod
    def _label(text):
        return QLabel(text, objectName='FieldLabel')

    @staticmethod
    def _wrap(layout):
        w = QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
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
        self.qty_stack.setCurrentIndex(0 if by_meters else 1)
        # Typing is the next thing anyone does after choosing how to measure.
        self.qty_stack.currentWidget().setFocus()
        self.qty_stack.currentWidget().selectAll()
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
        metre = t('m')
        self.summary.setText(
            f'{bars} {t("bars")} × {bar_m:g} {metre} = {total_m:g} {metre}')
        # The round-up is the one thing about this dialog that surprises
        # people, so it gets its own line rather than a parenthetical.
        needed = _dec(self.meters_needed.value())
        if self.mode_meters.isChecked() and needed > 0 and bars * bar_m > needed:
            over = (Decimal(bars) * bar_m - needed).quantize(Decimal('0.01'))
            # normalize() so 19.0 reads as 19 -- a trailing zero here looks
            # like precision the customer never asked for.
            self.rounding_note.setText(
                f'{t("rounded up from")} {needed.normalize():g} {metre} '
                f'({t("offcut")} {over.normalize():g} {metre})')
            self.rounding_note.show()
        else:
            self.rounding_note.hide()

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
