"""Prepare delivery — capture what was loaded before the delivery note.

Per line: how much was loaded (metres), the load weight (kg), and a note for
anything short or missing. Saving updates the lines, then the delivery note can
be generated with the real loaded amounts.
"""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
)

from app.i18n import t

COLUMNS = ['Profile', 'Ordered m', 'Loaded m', 'Load weight kg', 'Note (missing/short)']


class DeliveryPrepDialog(QDialog):
    def __init__(self, api, order, parent=None):
        super().__init__(parent)
        self.api = api
        self.order = order
        self.order_id = order['id']
        self.rows = []
        self.setModal(True)
        self.setMinimumSize(720, 480)
        self.setWindowTitle(t('Prepare delivery'))
        self._build()
        self._fill(order.get('lines') or [])

    def _build(self):
        title = QLabel(
            t('Enter how much was loaded, the load weight, and any shortage.'),
            objectName='Muted')
        title.setWordWrap(True)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([t(c) for c in COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setDefaultSectionSize(44)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        head.setSectionResizeMode(4, QHeaderView.Stretch)
        for c in (1, 2, 3):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='CardHint')

        self.save_btn = QPushButton(t('Save loading'), objectName='PrimaryButton')
        self.save_btn.clicked.connect(self._save)
        close_btn = QPushButton(t('Close'), objectName='Ghost')
        close_btn.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(self.status)
        actions.addStretch()
        actions.addWidget(close_btn)
        actions.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.table, 1)
        layout.addLayout(actions)

    def _fill(self, lines):
        self.table.setRowCount(0)
        self.rows = []
        for line in lines:
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = f"{line.get('number', '')} · {line.get('description', '')}".strip(' ·')
            self.table.setCellWidget(r, 0, self._label(name, bold=True))
            self.table.setCellWidget(
                r, 1, self._label(f"{line.get('total_length_m', '')} m"))

            loaded = self._spin()
            # Default the loaded amount to the ordered length if not set yet.
            loaded.setValue(float(line.get('delivered_length_m')
                                  if line.get('delivered_length_m') is not None
                                  else line.get('total_length_m') or 0))
            weight = self._spin()
            weight.setValue(float(line.get('weight_kg_override')
                                  or line.get('effective_weight_kg') or 0))
            note = QLineEdit(str(line.get('shortage_note') or ''))
            note.setPlaceholderText(t('e.g. only 3 of 5 bars'))

            self.table.setCellWidget(r, 2, loaded)
            self.table.setCellWidget(r, 3, weight)
            self.table.setCellWidget(r, 4, note)
            self.rows.append({'id': line['id'], 'loaded': loaded,
                              'weight': weight, 'note': note})

    def _spin(self):
        s = QDoubleSpinBox()
        s.setRange(0, 1_000_000)
        s.setDecimals(2)
        s.setMinimumWidth(96)
        return s

    def _label(self, text, bold=False):
        lbl = QLabel(text)
        lbl.setContentsMargins(8, 0, 8, 0)
        if bold:
            lbl.setStyleSheet('font-weight:600;')
        return lbl

    def _save(self):
        # Save each line in turn via line_action; the last response has the order.
        self._pending = list(self.rows)
        self.save_btn.setEnabled(False)
        self.save_btn.setText(t('Saving…'))
        self._save_next()

    def _save_next(self):
        if not self._pending:
            self.save_btn.setEnabled(True)
            self.save_btn.setText(t('Save loading'))
            self.status.setText(t('Loading saved.'))
            self.accept()
            return
        row = self._pending.pop(0)
        data = {
            'line_id': row['id'],
            'delivered_length_m': f"{row['loaded'].value():.2f}",
            'weight_kg': f"{row['weight'].value():.2f}",
            'shortage_note': row['note'].text().strip(),
        }
        self.api.post(f'orders/{self.order_id}/line_action/', data,
                      on_ok=lambda _d: self._save_next(), on_error=self._on_error)

    def _on_error(self, error):
        self.save_btn.setEnabled(True)
        self.save_btn.setText(t('Save loading'))
        self.status.setText(error.message)
