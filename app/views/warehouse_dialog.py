"""Add or edit a warehouse: its details, its map pin, and its locations.

Same shape as the client dialog -- form and map -- plus a small locations list
(racks/bays) you can add to. Locations are add-only here: one that already holds
stock cannot simply be deleted.
"""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views import forms
from app.views.dialogs import field_row
from app.views.forms import Field, section, validate_all
from app.views.mapwidget import MapWidget


class WarehouseDialog(QDialog):
    def __init__(self, api, warehouse=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.warehouse = warehouse
        self.lat = None
        self.lng = None
        self._saved_id = None
        self._existing_codes = set()
        self.setModal(True)
        self.setMinimumSize(860, 560)
        self.setWindowTitle(t('Edit warehouse') if warehouse else t('Add warehouse'))
        self._build()
        if warehouse:
            self._load(warehouse)

    def _build(self):
        self.f_name = Field('Name', required_field=True)
        self.f_city = Field('City')
        self.f_address = Field('Address')
        self.fields = [self.f_name, self.f_city, self.f_address]

        form = QVBoxLayout()
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(9)
        form.addWidget(section('Warehouse'))
        form.addWidget(self.f_name)
        form.addLayout(field_row(self.f_city))
        form.addWidget(self.f_address)

        form.addWidget(section('Locations (racks / bays)'))
        self.loc_list = QListWidget()
        self.loc_list.setFixedHeight(120)
        self.loc_input = QLineEdit(placeholderText=t('e.g. A-01'))
        self.loc_add = QPushButton(t('Add'), objectName='Ghost')
        self.loc_add.clicked.connect(self._add_location)
        self.loc_input.returnPressed.connect(self._add_location)
        add_row = QHBoxLayout()
        add_row.addWidget(self.loc_input, 1)
        add_row.addWidget(self.loc_add)
        form.addWidget(self.loc_list)
        form.addLayout(add_row)
        form.addStretch()

        form_w = QWidget()
        form_w.setFixedWidth(360)
        form_w.setLayout(form)

        # -- map --
        self.find_btn = QPushButton(t('Find on map'), objectName='Ghost')
        self.find_btn.clicked.connect(self._geocode)
        self.coord_label = QLabel(t('No location set'), objectName='Muted')
        maphead = QHBoxLayout()
        maphead.addWidget(QLabel(t('Location'), objectName='SectionTitle'))
        maphead.addStretch()
        maphead.addWidget(self.coord_label)
        maphead.addWidget(self.find_btn)
        self.map = MapWidget(token=self.api.mapbox_token)
        self.map.picked.connect(self._on_pick)
        right = QVBoxLayout()
        right.addLayout(maphead)
        right.addWidget(self.map, 1)

        title = QLabel(t('Edit warehouse') if self.warehouse else t('Add warehouse'),
                       objectName='LoginTitle')
        body = QHBoxLayout()
        body.setSpacing(20)
        body.addWidget(form_w)
        body.addLayout(right, 1)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()
        self.save = QPushButton(t('Save'))
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.save.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.error, 1)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(body, 1)
        layout.addLayout(buttons)

    # -- data ------------------------------------------------------------

    def _load(self, w):
        self._saved_id = w['id']
        self.f_name.set_value(w.get('name'))
        self.f_city.set_value(w.get('city'))
        self.f_address.set_value(w.get('address'))
        if w.get('latitude') is not None and w.get('longitude') is not None:
            self._set_coords(float(w['latitude']), float(w['longitude']), center=True)
        self.api.get('locations/', {'warehouse': w['id']},
                     on_ok=self._on_locations, on_error=lambda e: None)

    def _on_locations(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        for loc in rows or []:
            self._existing_codes.add(loc['code'])
            self.loc_list.addItem(loc['code'])

    def _add_location(self):
        code = self.loc_input.text().strip()
        if not code:
            return
        existing = {self.loc_list.item(i).text() for i in range(self.loc_list.count())}
        if code not in existing:
            self.loc_list.addItem(code)
        self.loc_input.clear()

    def _geocode(self):
        query = ', '.join(p for p in (self.f_address.value(), self.f_city.value()) if p)
        if not query:
            self._show_error(t('Enter an address or city first.'))
            return
        self.find_btn.setEnabled(False)
        self.find_btn.setText(t('Searching…'))
        self.api.geocode(query, on_ok=self._on_geocode, on_error=self._on_geo_err)

    def _on_geocode(self, result):
        self.find_btn.setEnabled(True)
        self.find_btn.setText(t('Find on map'))
        if not result:
            self._show_error(t('Address not found — drop the pin manually.'))
            return
        self.error.hide()
        self._set_coords(result['lat'], result['lng'], center=True)

    def _on_geo_err(self, error):
        self.find_btn.setEnabled(True)
        self.find_btn.setText(t('Find on map'))
        self._show_error(error.message)

    def _on_pick(self, lat, lng):
        self._set_coords(lat, lng)

    def _set_coords(self, lat, lng, center=False):
        self.lat, self.lng = round(lat, 6), round(lng, 6)
        self.coord_label.setText(f'{self.lat:.5f}, {self.lng:.5f}')
        if center:
            self.map.enable_pick(self.lat, self.lng)

    # -- submit ----------------------------------------------------------

    def _submit(self):
        self.error.hide()
        if not validate_all(self.fields):
            return
        data = {
            'name': self.f_name.value(),
            'city': self.f_city.value(),
            'address': self.f_address.value(),
            'latitude': str(self.lat) if self.lat is not None else None,
            'longitude': str(self.lng) if self.lng is not None else None,
        }
        self.save.setEnabled(False)
        self.save.setText(t('Saving…'))
        wid = self._saved_id
        if wid:
            self.api.patch(f'warehouses/{wid}/', data,
                           on_ok=lambda p: self._after_warehouse(wid),
                           on_error=self._on_error)
        else:
            self.api.post('warehouses/', data,
                          on_ok=lambda p: self._after_warehouse(p.get('id') if isinstance(p, dict) else None),
                          on_error=self._on_error)

    def _after_warehouse(self, wid):
        self._saved_id = wid
        codes = [self.loc_list.item(i).text() for i in range(self.loc_list.count())]
        pending = [c for c in codes if c not in self._existing_codes]
        if not wid or not pending:
            self.accept()
            return
        self._pending = pending
        self._create_next_location()

    def _create_next_location(self):
        if not self._pending:
            self.accept()
            return
        code = self._pending.pop(0)
        self.api.post('locations/', {'warehouse': self._saved_id, 'code': code},
                      on_ok=lambda _p: self._create_next_location(),
                      on_error=self._on_error)

    def _on_error(self, error):
        self.save.setEnabled(True)
        self.save.setText(t('Save'))
        self._show_error(error.message)

    def _show_error(self, message):
        self.error.setText(message)
        self.error.show()
