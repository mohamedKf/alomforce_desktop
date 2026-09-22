"""Stock dialogs: record an in/out movement, and add a new holding."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.i18n import t
from app.views.catalog import maker_label, maker_name

# mode -> (title, movement_type, quantity label)
MOVE_MODES = {
    'receive': ('Receive stock', 'receipt', 'Bars received'),
    'pick': ('Pick / ship', 'pick', 'Bars picked'),
    'adjust': ('Adjust count', 'adjustment', 'Counted quantity'),
}


class MovementDialog(QDialog):
    """Receive, pick or adjust the amount on one stock item."""

    def __init__(self, api, item, mode, parent=None):
        super().__init__(parent)
        self.api = api
        self.item = item
        self.mode = mode
        self.current = item.get('quantity') or 0
        self.setModal(True)
        self.setMinimumWidth(380)
        title, self.mtype, qty_label = MOVE_MODES[mode]
        self.setWindowTitle(t(title))
        self._build(title, qty_label)

    def _build(self, title, qty_label):
        heading = QLabel(t(title), objectName='LoginTitle')
        # The maker is named only when it is not the one everybody assumes.
        number = str(self.item.get('number', ''))
        if maker := maker_name(self.item):
            number = f'{number} ({maker})'
        desc = QLabel(
            f"{number} · {self.item.get('finish') or '—'} · "
            f"{(self.item.get('length_mm') or 0) / 1000:g} m\n"
            f"{self.item.get('warehouse', '')} — {t('on hand')}: {self.current}",
            objectName='Muted')
        desc.setWordWrap(True)

        self.qty = QSpinBox()
        self.qty.setRange(0 if self.mode == 'adjust' else 1, 1_000_000)
        self.qty.setValue(self.current if self.mode == 'adjust' else 1)
        self.note = QLineEdit()

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow(t(qty_label), self.qty)
        form.addRow(t('Note'), self.note)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()
        self.save = QPushButton(t('Save'))
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.save.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addWidget(desc)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

    def _submit(self):
        qty = self.qty.value()
        if self.mode == 'adjust':
            delta = qty - self.current
            if delta == 0:
                self.accept()
                return
            payload = {'movement_type': 'adjustment', 'quantity': delta}
        else:
            payload = {'movement_type': self.mtype, 'quantity': qty}
        payload['note'] = self.note.text().strip()
        self.save.setEnabled(False)
        self.save.setText(t('Saving…'))
        self.api.post(f"stock/{self.item['id']}/move/", payload,
                      on_ok=lambda _p: self.accept(), on_error=self._on_error)

    def _on_error(self, error):
        self.save.setEnabled(True)
        self.save.setText(t('Save'))
        self.error.setText(error.message)
        self.error.show()


class AddStockDialog(QDialog):
    """Create a new holding: a profile in a finish and length at a location."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowTitle(t('Add stock item'))
        self._build()
        self._load_options()

    def _build(self):
        heading = QLabel(t('Add stock item'), objectName='LoginTitle')

        # Whose catalogue the number is from. Numbers repeat between makers,
        # so the holding is posted by key ("<maker>:<number>"). Hidden until
        # the server lists makers; an older backend takes the bare number.
        self.manufacturer_label = QLabel(t('Manufacturer'))
        self.manufacturer = QComboBox()
        self.manufacturer_label.hide()
        self.manufacturer.hide()
        self.profile = QLineEdit(placeholderText=t('Profile number, e.g. 04901'))
        self.warehouse = QComboBox()
        self.warehouse.currentIndexChanged.connect(self._load_locations)
        self.location = QComboBox()
        self.length = QComboBox()
        self.length.setEditable(True)
        for mm in (6000, 6500, 5800, 6400):
            self.length.addItem(f'{mm}', mm)
        self.finish = QComboBox()
        self.finish.setEditable(True)
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 1_000_000)
        self.minimum.setValue(10)
        self.initial = QSpinBox()
        self.initial.setRange(0, 1_000_000)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow(self.manufacturer_label, self.manufacturer)
        form.addRow(t('Profile'), self.profile)
        form.addRow(t('Warehouse'), self.warehouse)
        form.addRow(t('Location'), self.location)
        form.addRow(t('Length (mm)'), self.length)
        form.addRow(t('Color'), self.finish)
        form.addRow(t('Reorder level'), self.minimum)
        form.addRow(t('Opening quantity'), self.initial)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()
        self.save = QPushButton(t('Create'))
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.save.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(heading)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

    def _load_options(self):
        self.api.get('catalog/manufacturers/', on_ok=self._on_manufacturers,
                     on_error=lambda e: None)
        self.api.get('warehouses/', {'active': 'true'},
                     on_ok=self._on_warehouses, on_error=lambda e: None)
        self.api.get('stock/options/', on_ok=self._on_finishes, on_error=lambda e: None)

    def _on_manufacturers(self, payload):
        makers = [m for m in (payload or []) if m.get('is_active', True)]
        if not makers:
            return
        for maker in makers:
            self.manufacturer.addItem(maker_label(maker), maker['slug'])
        default = next((m for m in makers if m.get('is_default')), makers[0])
        self.manufacturer.setCurrentIndex(
            max(0, self.manufacturer.findData(default['slug'])))
        # One maker has nothing to choose; the key is still built from it.
        if len(makers) > 1:
            self.manufacturer_label.show()
            self.manufacturer.show()

    def _on_warehouses(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        for w in rows or []:
            self.warehouse.addItem(w['name'], w['id'])
        self._load_locations()

    def _on_finishes(self, payload):
        for finish in (payload or {}).get('finishes', []):
            self.finish.addItem(finish)
        self.finish.setCurrentText('')

    def _load_locations(self):
        wid = self.warehouse.currentData()
        self.location.clear()
        if wid is None:
            return
        self.api.get('locations/', {'warehouse': wid},
                     on_ok=self._on_locations, on_error=lambda e: None)

    def _on_locations(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        for loc in rows or []:
            self.location.addItem(loc['code'], loc['id'])

    def _submit(self):
        self.error.hide()
        number = self.profile.text().strip()
        if not number:
            return self._show(t('Enter a profile number.'))
        if self.location.currentData() is None:
            return self._show(t('Pick a location (add one on the warehouse first).'))
        try:
            length = int(self.length.currentText() or self.length.currentData())
        except (TypeError, ValueError):
            return self._show(t('Enter a valid length in millimetres.'))
        # A number typed with its maker ("extal:C90") is already a key.
        slug = self.manufacturer.currentData()
        key = number if ':' in number or not slug else f'{slug}:{number}'
        data = {
            'profile': key,
            'location': self.location.currentData(),
            'length_mm': length,
            'finish': self.finish.currentText().strip(),
            'minimum_quantity': self.minimum.value(),
            'initial_quantity': self.initial.value(),
        }
        self.save.setEnabled(False)
        self.save.setText(t('Saving…'))
        self.api.post('stock/', data, on_ok=lambda _p: self.accept(),
                      on_error=self._on_error)

    def _on_error(self, error):
        self.save.setEnabled(True)
        self.save.setText(t('Create'))
        payload = error.payload if isinstance(error.payload, dict) else {}
        if 'profile' in payload:
            self._show(t('No profile with that number.'))
        elif payload.get('non_field_errors'):
            self._show(t('This holding already exists (same profile, location, '
                         'length and color).'))
        else:
            self._show(error.message)

    def _show(self, message):
        self.error.setText(message)
        self.error.show()
