"""Settings — server connection, language, company details, image storage.

Server connection and language are desktop-client settings (persisted on this
machine); the company details and Cloudinary credentials live on the server and
apply to everyone.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import i18n
from app.i18n import t
from app.views import forms
from app.views.forms import Field


class SettingsView(QWidget):
    language_changed = Signal(str)
    server_changed = Signal(str)   # emitted with the new base URL when saved

    def __init__(self, api, session):
        super().__init__()
        self.api = api
        self.session = session
        self.setObjectName('Canvas')
        self._build()
        self._load_shop()
        self._load_cloudinary()
        # Show live connection status as soon as the page opens.
        self._test_connection()

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel(t('Settings'), objectName='PageTitle')
        subtitle = QLabel(t('Connection, language, company and image storage.'),
                          objectName='Muted')

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 14, 0)
        content.setSpacing(16)

        # -- server connection --
        self.server = QLineEdit(self.api.base_url.rstrip('/'))
        self.server.setPlaceholderText('http://192.168.1.10:8000')
        self.conn_status = QLabel(t('Checking connection…'), objectName='ConnStatus')
        self.conn_status.setWordWrap(True)
        self.server_status = QLabel('', objectName='CardHint')
        self.server_status.setWordWrap(True)
        self.test_btn = QPushButton(t('Test connection'), objectName='Ghost')
        self.test_btn.clicked.connect(self._test_connection)
        self.qr_btn = QPushButton(t('Show QR'), objectName='Ghost')
        self.qr_btn.clicked.connect(self._show_server_qr)
        self.server_btn = QPushButton(t('Test and save server'))
        self.server_btn.clicked.connect(self._save_server)
        server_body = QVBoxLayout()
        server_body.setSpacing(8)
        server_body.addWidget(QLabel(t('Backend address'), objectName='FieldLabel'))
        server_body.addWidget(self.server)
        server_body.addWidget(self.conn_status)
        server_body.addWidget(self.server_status)
        server_body.addLayout(
            self._action_row(self.qr_btn, self.test_btn, self.server_btn))
        content.addWidget(self._card('📡', 'Server connection',
                                     'Where this computer finds the AlomForce server.',
                                     server_body))

        # -- language --
        self.language = QComboBox()
        for code, label in i18n.LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(self.language.findData(i18n.get_language()))
        self.language.currentIndexChanged.connect(
            lambda: self.language_changed.emit(self.language.currentData()))
        lang_body = QVBoxLayout()
        lang_body.setSpacing(8)
        lang_body.addWidget(QLabel(t('App language'), objectName='FieldLabel'))
        lang_body.addWidget(self.language)
        content.addWidget(self._card('🌐', 'Language',
                                     'English, Hebrew or Arabic (RTL).', lang_body))

        # -- company / shop --
        self.f_name = Field('Business name')
        self.f_legal = Field('Registered legal name')
        self.f_tax = Field('Tax ID')
        self.f_phone = Field('Phone', validators=[forms.phone])
        self.f_email = Field('Email', validators=[forms.email])
        self.f_address = Field('Address')
        self.f_city = Field('City')
        self.shop_fields = [self.f_name, self.f_legal, self.f_tax, self.f_phone,
                            self.f_email, self.f_address, self.f_city]
        self.shop_status = QLabel('', objectName='CardHint')
        self.shop_btn = QPushButton(t('Save company details'))
        self.shop_btn.clicked.connect(self._save_shop)
        shop_body = QVBoxLayout()
        shop_body.setSpacing(8)
        shop_body.addWidget(self.f_name)
        shop_body.addLayout(self._row(self.f_tax, self.f_legal))
        shop_body.addLayout(self._row(self.f_phone, self.f_email))
        shop_body.addLayout(self._row(self.f_city, self.f_address))
        shop_body.addLayout(self._logo_row())
        shop_body.addWidget(self.shop_status)
        shop_body.addLayout(self._action_row(self.shop_btn))
        content.addWidget(self._card('🏢', 'Company details',
                                     'Appears on order and delivery documents.', shop_body))

        # -- cloudinary (managers only) --
        self._is_manager = (self.session.role if self.session else None) == 'manager'
        if self._is_manager:
            self.cl_cloud = Field('Cloudinary cloud name')
            self.cl_key = Field('Cloudinary API key')
            self.cl_secret = Field('Cloudinary API secret')
            self.cl_secret.input.setEchoMode(QLineEdit.Password)
            self.cl_secret.input.setPlaceholderText(
                t('Leave blank to keep the saved secret'))
            self.cl_status = QLabel('', objectName='CardHint')
            self.cl_status.setWordWrap(True)
            self.cl_btn = QPushButton(t('Save image storage'))
            self.cl_btn.clicked.connect(self._save_cloudinary)
            cl_body = QVBoxLayout()
            cl_body.setSpacing(8)
            cl_body.addLayout(self._row(self.cl_cloud, self.cl_key))
            cl_body.addWidget(self.cl_secret)
            cl_body.addWidget(self.cl_status)
            cl_body.addLayout(self._action_row(self.cl_btn))
            content.addWidget(self._card(
                '🖼', 'Image storage (Cloudinary)',
                'Leave blank for local disk; fill in to store profile images on '
                'Cloudinary.', cl_body))

            # -- accountant --
            self.ac_name = Field('Accountant name')
            self.ac_email = Field('Accountant email', validators=[forms.email])
            self.ac_phone = Field('Accountant phone', validators=[forms.phone])
            self.ac_status = QLabel('', objectName='CardHint')
            self.ac_btn = QPushButton(t('Save accountant'))
            self.ac_btn.clicked.connect(self._save_accountant)
            ac_body = QVBoxLayout()
            ac_body.setSpacing(8)
            ac_body.addWidget(self.ac_name)
            ac_body.addLayout(self._row(self.ac_email, self.ac_phone))
            ac_body.addWidget(self.ac_status)
            ac_body.addLayout(self._action_row(self.ac_btn))
            content.addWidget(self._card(
                '🧑‍💼', 'Accountant',
                'Where the books are sent — the income/expense invoices and the '
                'salary sheet.', ac_body))

            # -- OpenAI (invoice scanning) --
            self.oa_key = Field('OpenAI API key')
            self.oa_key.input.setEchoMode(QLineEdit.Password)
            self.oa_key.input.setPlaceholderText(t('Leave blank to keep the saved key'))
            self.oa_status = QLabel('', objectName='CardHint')
            self.oa_btn = QPushButton(t('Save OpenAI key'))
            self.oa_btn.clicked.connect(self._save_openai)
            oa_body = QVBoxLayout()
            oa_body.setSpacing(8)
            oa_body.addWidget(self.oa_key)
            oa_body.addWidget(self.oa_status)
            oa_body.addLayout(self._action_row(self.oa_btn))
            content.addWidget(self._card(
                '👁', 'Invoice scanning (OpenAI)',
                'Reads a photo of an invoice into the fields.', oa_body))

            # -- SMTP (accountant email) --
            self.smtp_host = Field('SMTP host')
            self.smtp_port = Field('SMTP port')
            self.smtp_user = Field('SMTP username')
            self.smtp_pass = Field('SMTP password')
            self.smtp_pass.input.setEchoMode(QLineEdit.Password)
            self.smtp_pass.input.setPlaceholderText(
                t('Leave blank to keep the saved password'))
            self.smtp_from = Field('From address', validators=[forms.email])
            self.smtp_tls = QCheckBox(t('Use TLS'))
            self.smtp_tls.setChecked(True)
            self.smtp_status = QLabel('', objectName='CardHint')
            self.smtp_btn = QPushButton(t('Save email'))
            self.smtp_btn.clicked.connect(self._save_smtp)
            smtp_body = QVBoxLayout()
            smtp_body.setSpacing(8)
            smtp_body.addLayout(self._row(self.smtp_host, self.smtp_port))
            smtp_body.addLayout(self._row(self.smtp_user, self.smtp_from))
            smtp_body.addWidget(self.smtp_pass)
            smtp_body.addWidget(self.smtp_tls)
            smtp_body.addWidget(self.smtp_status)
            smtp_body.addLayout(self._action_row(self.smtp_btn))
            content.addWidget(self._card(
                '✉️', 'Email (SMTP)',
                'Sends the accountant the zipped invoices and the salary sheet.',
                smtp_body))

            # -- Green Invoice (legal invoicing; wired later) --
            self.gi_key = Field('Green Invoice API key')
            self.gi_secret = Field('Green Invoice API secret')
            self.gi_secret.input.setEchoMode(QLineEdit.Password)
            self.gi_secret.input.setPlaceholderText(t('Leave blank to keep the saved secret'))
            self.gi_status = QLabel('', objectName='CardHint')
            self.gi_btn = QPushButton(t('Save Green Invoice'))
            self.gi_btn.clicked.connect(self._save_greeninvoice)
            gi_body = QVBoxLayout()
            gi_body.setSpacing(8)
            gi_body.addWidget(self.gi_key)
            gi_body.addWidget(self.gi_secret)
            gi_body.addWidget(self.gi_status)
            gi_body.addLayout(self._action_row(self.gi_btn))
            content.addWidget(self._card(
                '🧾', 'Legal invoicing (Green Invoice)',
                'For legal invoices and allocation (hakptsa) numbers. '
                'Connected later.', gi_body))

            # -- Mapbox (the map on the Deliveries screen) --
            # Shown in full rather than masked: a Mapbox pk. token is designed
            # to be embedded in client code, so hiding it would only make it
            # harder to check which token the map is actually using.
            self.mapbox = Field('Mapbox public token')
            self.mapbox.input.setPlaceholderText('pk.…')
            self.mapbox_status = QLabel('', objectName='CardHint')
            self.mapbox_status.setWordWrap(True)
            self.mapbox_btn = QPushButton(t('Save Mapbox token'))
            self.mapbox_btn.clicked.connect(self._save_mapbox)
            mapbox_body = QVBoxLayout()
            mapbox_body.setSpacing(8)
            mapbox_body.addWidget(self.mapbox)
            mapbox_body.addWidget(self.mapbox_status)
            mapbox_body.addLayout(self._action_row(self.mapbox_btn))
            content.addWidget(self._card(
                '🗺️', 'Map (Mapbox)',
                'Draws the client map. A MAPBOX_TOKEN environment variable '
                'overrides whatever is saved here.', mapbox_body))

        content.addStretch()

        inner = QWidget()
        inner.setLayout(content)
        inner.setMaximumWidth(620)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addWidget(subtitle)
        layout.addSpacing(10)
        layout.addWidget(scroll, 1)

    # -- card helpers ----------------------------------------------------

    def _card(self, icon, title, hint, body_layout):
        card = QFrame(objectName='SettingsCard')
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(QLabel(icon, objectName='CardIcon'))
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(QLabel(t(title), objectName='CardTitle'))
        h = QLabel(t(hint), objectName='CardHint')
        h.setWordWrap(True)
        titles.addWidget(h)
        head.addLayout(titles, 1)

        wrap = QVBoxLayout(card)
        wrap.setContentsMargins(18, 16, 18, 16)
        wrap.setSpacing(12)
        wrap.addLayout(head)
        wrap.addLayout(body_layout)
        return card

    @staticmethod
    def _row(*widgets):
        row = QHBoxLayout()
        row.setSpacing(12)
        for w in widgets:
            row.addWidget(w, 1)
        return row

    @staticmethod
    def _action_row(*buttons):
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        for b in buttons:
            row.addWidget(b)
        return row

    # -- company logo ----------------------------------------------------

    def _logo_row(self):
        self._logo_url = None
        self.logo_preview = QLabel(t('No logo'), objectName='LogoPreview')
        self.logo_preview.setFixedSize(148, 56)
        self.logo_preview.setAlignment(Qt.AlignCenter)

        self.logo_upload_btn = QPushButton(t('Upload logo…'), objectName='Ghost')
        self.logo_upload_btn.clicked.connect(self._pick_logo)
        self.logo_remove_btn = QPushButton(t('Remove'), objectName='Ghost')
        self.logo_remove_btn.clicked.connect(self._remove_logo)
        self.logo_remove_btn.setEnabled(False)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(QLabel(t('Company logo'), objectName='FieldLabel'))
        hint = QLabel(t('Shown at the top of order, delivery and payslip PDFs.'),
                      objectName='CardHint')
        hint.setWordWrap(True)
        right.addWidget(hint)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.logo_upload_btn)
        btns.addWidget(self.logo_remove_btn)
        btns.addStretch()
        right.addLayout(btns)

        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(self.logo_preview)
        row.addLayout(right, 1)
        return row

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, t('Choose a logo image'), '',
            'Images (*.png *.jpg *.jpeg *.webp)')
        if not path:
            return
        self.logo_upload_btn.setEnabled(False)
        self.logo_upload_btn.setText(t('Uploading…'))
        self.api.upload('shop/', path, field='logo',
                        on_ok=self._on_logo_uploaded, on_error=self._on_logo_error)

    def _on_logo_uploaded(self, data):
        self.logo_upload_btn.setEnabled(True)
        self.logo_upload_btn.setText(t('Upload logo…'))
        self.shop_status.setText(t('Logo updated.'))
        self._set_logo(data.get('logo') if isinstance(data, dict) else None)

    def _remove_logo(self):
        self.logo_remove_btn.setEnabled(False)
        self.logo_remove_btn.setText(t('Removing…'))
        self.api.delete('shop/', on_ok=self._on_logo_removed,
                        on_error=self._on_logo_error)

    def _on_logo_removed(self, _data):
        self.logo_remove_btn.setText(t('Remove'))
        self.shop_status.setText(t('Logo removed.'))
        self._set_logo(None)

    def _on_logo_error(self, error):
        self.logo_upload_btn.setEnabled(True)
        self.logo_upload_btn.setText(t('Upload logo…'))
        self.logo_remove_btn.setText(t('Remove'))
        self.logo_remove_btn.setEnabled(bool(self._logo_url))
        self.shop_status.setText(error.message)

    def _set_logo(self, url):
        self._logo_url = url
        self.logo_remove_btn.setEnabled(bool(url))
        if url:
            self.api.fetch_binary(url, on_ok=self._show_logo, on_error=lambda e: None)
        else:
            self.logo_preview.setPixmap(QPixmap())
            self.logo_preview.setText(t('No logo'))

    def _show_logo(self, data):
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            return
        self.logo_preview.setText('')
        self.logo_preview.setPixmap(pixmap.scaled(
            self.logo_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    # -- server QR (scanned by the phone to auto-fill the server) --------

    def _show_server_qr(self):
        url = self.server.text().strip()
        if not url:
            self.server_status.setText(t('Enter a server address first.'))
            return
        # Encode the base host:port (the phone appends /api itself), so a scan
        # doesn't end up with a doubled /api/api.
        base = url.rstrip('/')
        if base.endswith('/api'):
            base = base[:-4]
        url = base
        dialog = QDialog(self)
        dialog.setWindowTitle(t('Server QR code'))
        pix = self._qr_pixmap(url, 300)
        img = QLabel()
        img.setPixmap(pix)
        img.setAlignment(Qt.AlignCenter)
        caption = QLabel(t('Scan this in the phone app to connect.'),
                         objectName='CardHint')
        caption.setAlignment(Qt.AlignCenter)
        addr = QLabel(url, objectName='CardTitle')
        addr.setAlignment(Qt.AlignCenter)
        box = QVBoxLayout(dialog)
        box.setContentsMargins(24, 24, 24, 24)
        box.setSpacing(12)
        box.addWidget(addr)
        box.addWidget(img)
        box.addWidget(caption)
        dialog.exec()

    @staticmethod
    def _qr_pixmap(data, size):
        """Render `data` as a QR code QPixmap, drawing the matrix with Qt so no
        image library is needed."""
        import qrcode
        from PySide6.QtGui import QColor, QPainter, QPixmap

        qr = qrcode.QRCode(border=2,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(data)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        n = len(matrix)
        scale = max(1, size // n)
        dim = n * scale
        pix = QPixmap(dim, dim)
        pix.fill(QColor('white'))
        painter = QPainter(pix)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('black'))
        for y, row in enumerate(matrix):
            for x, on in enumerate(row):
                if on:
                    painter.drawRect(x * scale, y * scale, scale, scale)
        painter.end()
        return pix

    # -- server ----------------------------------------------------------

    def _test_connection(self, *, url=None, save_on_success=False):
        """Probe the server (no save) and show a live status line."""
        target = url or self.server.text().strip()
        if not target:
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText(t('Testing…'))
        self.conn_status.setText(t('Checking connection…'))
        self.conn_status.setProperty('state', 'checking')
        self._restyle(self.conn_status)
        self.api.check_connection(
            target, lambda res: self._on_connection(res, save_on_success))

    def _on_connection(self, res, save_on_success=False):
        self.test_btn.setEnabled(True)
        self.test_btn.setText(t('Test connection'))
        if res.get('ok'):
            self.conn_status.setText(
                t('Connected — server is up ({ms} ms).').format(ms=res.get('ms', 0)))
            self.conn_status.setProperty('state', 'ok')
        elif res.get('reason') == 'timeout':
            self.conn_status.setText(t('The server is not responding (timed out).'))
            self.conn_status.setProperty('state', 'bad')
        else:
            self.conn_status.setText(
                t('Cannot reach the server. Is the backend running?'))
            self.conn_status.setProperty('state', 'bad')
        self._restyle(self.conn_status)

    @staticmethod
    def _restyle(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _save_server(self):
        from app.api import ApiClient
        url = self.server.text().strip()
        if not url:
            return
        self.server_btn.setEnabled(False)
        self.server_btn.setText(t('Testing…'))
        # Probe runs on the UI thread but is quick (8s timeout); acceptable here.
        ok = ApiClient.probe(url)
        self.server_btn.setEnabled(True)
        self.server_btn.setText(t('Test and save server'))
        if not ok:
            self.server_status.setText(t("Couldn't reach that server."))
            return
        base = url.rstrip('/')
        if not base.endswith('/api'):
            base += '/api'
        self.api.set_base_url(base)
        from PySide6.QtCore import QSettings
        QSettings('AlomForce', 'AlomForce').setValue('server_url', base)
        self.server_changed.emit(base)
        self.server_status.setText(
            t('Saved. If you changed servers, sign out and back in.'))

    # -- shop ------------------------------------------------------------

    def _load_shop(self):
        self.api.get('shop/', on_ok=self._on_shop, on_error=lambda e: None)

    def _on_shop(self, data):
        self.f_name.set_value(data.get('name'))
        self.f_legal.set_value(data.get('legal_name'))
        self.f_tax.set_value(data.get('tax_id'))
        self.f_phone.set_value(data.get('phone'))
        self.f_email.set_value(data.get('email'))
        self.f_address.set_value(data.get('address'))
        self.f_city.set_value(data.get('city'))
        self._set_logo(data.get('logo'))

    def _save_shop(self):
        from app.views.forms import validate_all
        if not validate_all(self.shop_fields):
            return
        data = {
            'name': self.f_name.value(), 'legal_name': self.f_legal.value(),
            'tax_id': self.f_tax.value(), 'phone': self.f_phone.value(),
            'email': self.f_email.value(), 'address': self.f_address.value(),
            'city': self.f_city.value(),
        }
        self.shop_btn.setEnabled(False)
        self.shop_btn.setText(t('Saving…'))
        self.api.patch('shop/', data, on_ok=self._on_shop_saved,
                       on_error=self._on_shop_err)

    def _on_shop_saved(self, _data):
        self.shop_btn.setEnabled(True)
        self.shop_btn.setText(t('Save company details'))
        self.shop_status.setText(t('Company details saved.'))

    def _on_shop_err(self, error):
        self.shop_btn.setEnabled(True)
        self.shop_btn.setText(t('Save company details'))
        self.shop_status.setText(error.message)

    # -- cloudinary ------------------------------------------------------

    def _load_cloudinary(self):
        if not getattr(self, '_is_manager', False):
            return
        self.api.get('settings/', on_ok=self._on_cloudinary,
                     on_error=lambda e: None)

    def _on_cloudinary(self, data):
        self.cl_cloud.set_value(data.get('cloudinary_cloud_name'))
        self.cl_key.set_value(data.get('cloudinary_api_key'))
        backend = data.get('storage_backend', 'local')
        secret_set = data.get('cloudinary_secret_set')
        self.cl_status.setText(
            (t('Images are stored on Cloudinary.') if backend == 'cloudinary'
             else t('Images are stored on the server disk.'))
            + (' ' + t('(secret saved)') if secret_set else ''))
        # Accountant + integrations share the same settings payload.
        self.ac_name.set_value(data.get('accountant_name'))
        self.ac_email.set_value(data.get('accountant_email'))
        self.ac_phone.set_value(data.get('accountant_phone'))
        env = t('Set via Railway (environment).')
        self.oa_status.setText(
            env if data.get('openai_from_env')
            else (t('Key saved.') if data.get('openai_key_set')
                  else t('Not configured.')))
        self.smtp_host.set_value(data.get('smtp_host'))
        self.smtp_port.set_value(data.get('smtp_port'))
        self.smtp_user.set_value(data.get('smtp_user'))
        self.smtp_from.set_value(data.get('smtp_from'))
        self.smtp_tls.setChecked(bool(data.get('smtp_use_tls', True)))
        self.smtp_status.setText(
            env if data.get('smtp_from_env')
            else (t('Email is ready.') if data.get('smtp_ready')
                  else t('Not configured.')))
        self.gi_key.set_value(data.get('greeninvoice_api_key'))
        self.gi_status.setText(
            env if data.get('greeninvoice_from_env')
            else (t('Connected.') if data.get('greeninvoice_ready')
                  else t('Not configured.')))
        # Show the token actually in force, environment included, so the field
        # cannot claim one thing while the map uses another.
        self.mapbox.set_value(data.get('mapbox_effective') or '')
        from_env = data.get('mapbox_from_env')
        self.mapbox.input.setReadOnly(bool(from_env))
        self.mapbox_btn.setEnabled(not from_env)
        self.mapbox_status.setText(
            env if from_env
            else (t('Map token set.') if data.get('mapbox_effective')
                  else t('Not configured — the map will be blank.')))

    def _patch_settings(self, data, button, label, status):
        button.setEnabled(False)
        button.setText(t('Saving…'))

        def done(payload):
            button.setEnabled(True)
            button.setText(label)
            status.setText(t('Saved.'))
            self._on_cloudinary(payload)

        def failed(error):
            button.setEnabled(True)
            button.setText(label)
            status.setText(error.message)

        self.api.patch('settings/', data, on_ok=done, on_error=failed)

    def _save_accountant(self):
        from app.views.forms import validate_all
        if not validate_all([self.ac_email, self.ac_phone]):
            return
        self._patch_settings({
            'accountant_name': self.ac_name.value(),
            'accountant_email': self.ac_email.value(),
            'accountant_phone': self.ac_phone.value(),
        }, self.ac_btn, t('Save accountant'), self.ac_status)

    def _save_openai(self):
        if not self.oa_key.value():
            self.oa_status.setText(t('Enter a key first.'))
            return
        self._patch_settings({'openai_api_key': self.oa_key.value()},
                             self.oa_btn, t('Save OpenAI key'), self.oa_status)
        self.oa_key.set_value('')

    def _save_smtp(self):
        from app.views.forms import validate_all
        if not validate_all([self.smtp_from]):
            return
        data = {
            'smtp_host': self.smtp_host.value(),
            'smtp_port': self.smtp_port.value() or None,
            'smtp_user': self.smtp_user.value(),
            'smtp_from': self.smtp_from.value(),
            'smtp_use_tls': self.smtp_tls.isChecked(),
        }
        if self.smtp_pass.value():
            data['smtp_password'] = self.smtp_pass.value()
        self._patch_settings(data, self.smtp_btn, t('Save email'), self.smtp_status)
        self.smtp_pass.set_value('')

    def _save_greeninvoice(self):
        data = {'greeninvoice_api_key': self.gi_key.value()}
        if self.gi_secret.value():
            data['greeninvoice_api_secret'] = self.gi_secret.value()
        self._patch_settings(data, self.gi_btn, t('Save Green Invoice'),
                             self.gi_status)
        self.gi_secret.set_value('')

    def _save_mapbox(self):
        self._patch_settings({'mapbox_token': self.mapbox.value()},
                             self.mapbox_btn, t('Save Mapbox token'),
                             self.mapbox_status)

    def _save_cloudinary(self):
        data = {
            'cloudinary_cloud_name': self.cl_cloud.value(),
            'cloudinary_api_key': self.cl_key.value(),
        }
        # Only send the secret when the field was filled, so a blank keeps it.
        if self.cl_secret.value():
            data['cloudinary_api_secret'] = self.cl_secret.value()
        self.cl_btn.setEnabled(False)
        self.cl_btn.setText(t('Saving…'))
        self.api.patch('settings/', data, on_ok=self._on_cloudinary_saved,
                       on_error=self._on_cloudinary_err)

    def _on_cloudinary_saved(self, data):
        self.cl_btn.setEnabled(True)
        self.cl_btn.setText(t('Save image storage'))
        self.cl_secret.set_value('')
        self._on_cloudinary(data)

    def _on_cloudinary_err(self, error):
        self.cl_btn.setEnabled(True)
        self.cl_btn.setText(t('Save image storage'))
        self.cl_status.setText(error.message)

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Settings'))
