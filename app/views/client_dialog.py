"""Add or edit a client business, its contact person, and its location.

The one place clients are created. Business details and the contact person on the
left in labelled sections with inline validation, a map on the right. When adding
a client the contact can be given app access in the same step: they sign in with
their phone number, and the starting password *is* that phone number.
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views import forms
from app.views.dialogs import BUSINESS_TYPES, field_row
from app.views.forms import Field, section, validate_all
from app.views.mapwidget import MapWidget


class ClientDialog(QDialog):
    def __init__(self, api, client=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.client = client                 # None => add, dict => edit
        self.lat = None
        self.lng = None
        self._created_client_id = None        # set once the client row exists
        self.setModal(True)
        self.setMinimumSize(900, 660)
        self.setWindowTitle(t('Edit client') if client else t('Add client'))
        self._build()
        if client:
            self._load(client)

    # -- construction ----------------------------------------------------

    def _build(self):
        self.f_name = Field('Business name', required_field=True)
        self.f_type = Field('Business type', kind='combo', choices=BUSINESS_TYPES)
        self.f_legal = Field('Registered legal name')
        self.f_tax = Field('Tax ID')
        self.f_regnum = Field('Company registration number')
        self.f_first = Field('First name')
        self.f_last = Field('Last name')
        self.f_phone = Field('Phone', validators=[forms.phone])
        self.f_email = Field('Email', validators=[forms.email])
        self.f_website = Field('Website')
        self.f_address = Field('Address')
        self.f_city = Field('City')
        self.f_postal = Field('Postal code')
        self.f_delivery = Field('Delivery address')
        # A link shared out of any map app. The server reads the point from it
        # and moves the pin -- but only when the link itself changed, so
        # dragging the pin afterwards is not undone by the next save.
        self.f_maplink = Field('Map link')
        self.f_notes = Field('Notes', kind='text')

        self.fields = [self.f_name, self.f_type, self.f_legal, self.f_tax,
                       self.f_regnum, self.f_first, self.f_last, self.f_phone,
                       self.f_email, self.f_website, self.f_address, self.f_city,
                       self.f_postal, self.f_delivery, self.f_maplink,
                       self.f_notes]
        self.error_map = {
            'name': self.f_name, 'tax_id': self.f_tax, 'phone': self.f_phone,
            'email': self.f_email, 'website': self.f_website,
        }

        form = QVBoxLayout()
        form.setContentsMargins(0, 0, 8, 0)
        form.setSpacing(9)
        form.addWidget(section('Business'))
        form.addWidget(self.f_name)
        form.addLayout(field_row(self.f_type, self.f_tax))
        form.addWidget(self.f_legal)
        form.addWidget(self.f_regnum)
        form.addWidget(section('Contact person'))
        form.addLayout(field_row(self.f_first, self.f_last))
        form.addLayout(field_row(self.f_phone, self.f_email))
        form.addWidget(self.f_website)

        # App-login account -- offered only when creating a new client.
        self.account_check = None
        if self.client is None:
            form.addWidget(section('App login'))
            self.account_check = QCheckBox(t('Create a login account for this client'))
            self.account_check.setChecked(True)
            self.account_check.toggled.connect(self._sync_account_note)
            self.account_note = QLabel(
                t('They sign in with the phone number above; the starting '
                  'password is that phone number.'),
                objectName='Muted')
            self.account_note.setWordWrap(True)
            form.addWidget(self.account_check)
            form.addWidget(self.account_note)

        form.addWidget(section('Address'))
        form.addWidget(self.f_address)
        form.addLayout(field_row(self.f_city, self.f_postal))
        form.addWidget(self.f_delivery)
        form.addWidget(self.f_maplink)
        form.addWidget(self.f_notes)
        form.addStretch()

        inner = QWidget()
        inner.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setFixedWidth(400)

        # -- map side --
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
        hint = QLabel(t('Click "Find on map", then drag the pin to fine-tune.'),
                      objectName='Muted')
        hint.setWordWrap(True)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(maphead)
        right.addWidget(self.map, 1)
        right.addWidget(hint)

        title = QLabel(t('Edit client') if self.client else t('Add client'),
                       objectName='LoginTitle')

        body = QHBoxLayout()
        body.setSpacing(20)
        body.addWidget(scroll)
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

    def _sync_account_note(self, on):
        self.account_note.setEnabled(on)

    # -- data ------------------------------------------------------------

    def _load(self, c):
        self.f_name.set_value(c.get('name'))
        self.f_type.set_value(c.get('business_type'))
        self.f_legal.set_value(c.get('legal_name'))
        self.f_tax.set_value(c.get('tax_id'))
        self.f_regnum.set_value(c.get('business_number'))
        first, _, last = (c.get('contact_name') or '').partition(' ')
        self.f_first.set_value(first)
        self.f_last.set_value(last)
        self.f_phone.set_value(c.get('phone'))
        self.f_email.set_value(c.get('email'))
        self.f_website.set_value(c.get('website'))
        self.f_address.set_value(c.get('address'))
        self.f_city.set_value(c.get('city'))
        self.f_postal.set_value(c.get('postal_code'))
        self.f_delivery.set_value(c.get('delivery_address'))
        self.f_maplink.set_value(c.get('location_url'))
        self.f_notes.set_value(c.get('notes'))
        if c.get('latitude') is not None and c.get('longitude') is not None:
            self._set_coords(float(c['latitude']), float(c['longitude']), center=True)

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

    def _creating_account(self):
        return self.account_check is not None and self.account_check.isChecked()

    def _submit(self):
        self.error.hide()
        if not validate_all(self.fields):
            return
        if self._creating_account() and not self._contact_ready():
            return

        data = {
            'name': self.f_name.value(),
            'business_type': self.f_type.value(),
            'legal_name': self.f_legal.value(),
            'tax_id': self.f_tax.value(),
            'business_number': self.f_regnum.value(),
            'contact_name': f'{self.f_first.value()} {self.f_last.value()}'.strip(),
            'phone': self.f_phone.value(),
            'email': self.f_email.value(),
            'website': self.f_website.value(),
            'address': self.f_address.value(),
            'city': self.f_city.value(),
            'postal_code': self.f_postal.value(),
            'delivery_address': self.f_delivery.value(),
            'location_url': self.f_maplink.value(),
            'notes': self.f_notes.value(),
            'latitude': str(self.lat) if self.lat is not None else None,
            'longitude': str(self.lng) if self.lng is not None else None,
        }
        self._busy(True)
        # An existing id means the client row is already saved (edit, or a retry
        # after the contact step failed) -- update it rather than make a second.
        cid = self._created_client_id or (self.client and self.client['id'])
        if cid:
            self.api.patch(f'clients/{cid}/', data,
                           on_ok=lambda p: self._after_client(cid),
                           on_error=self._on_error)
        else:
            self.api.post('clients/', data,
                          on_ok=lambda p: self._after_client(p.get('id') if isinstance(p, dict) else None),
                          on_error=self._on_error)

    def _contact_ready(self):
        """The login account needs a name and phone; flag what's missing."""
        ok = True
        for field in (self.f_first, self.f_last, self.f_phone):
            if not field.value():
                field._paint('invalid', t('Required for the login account.'))
                ok = False
        return ok

    def _after_client(self, cid):
        self._created_client_id = cid
        if self._creating_account() and cid:
            phone = self.f_phone.value()
            self.api.post('staff/contacts/', {
                'first_name': self.f_first.value(),
                'last_name': self.f_last.value(),
                'phone': phone,
                'email': self.f_email.value(),
                'client': cid,
                'password': phone,
                'must_change_password': False,
            }, on_ok=lambda _p: self.accept(), on_error=self._on_contact_error)
        else:
            self.accept()

    def _on_error(self, error):
        self._busy(False)
        if not self._route_field_errors(error):
            self._show_error(error.message)

    def _on_contact_error(self, error):
        # The client saved; only the login account failed. Keep the dialog open
        # so it can be fixed -- a re-submit updates the client and retries.
        self._busy(False)
        self._route_field_errors(error)
        self._show_error(
            t('The client was saved, but the login account was not created:')
            + ' ' + error.message)

    def _route_field_errors(self, error):
        payload = error.payload if isinstance(error.payload, dict) else {}
        routed = False
        for key, field in self.error_map.items():
            if key in payload:
                msgs = payload[key]
                text = '; '.join(str(m) for m in msgs) if isinstance(msgs, list) else str(msgs)
                field._paint('invalid', text)
                routed = True
        return routed

    def _busy(self, busy):
        self.save.setEnabled(not busy)
        self.save.setText(t('Saving…') if busy else t('Save'))

    def _show_error(self, message):
        self.error.setText(message)
        self.error.show()
