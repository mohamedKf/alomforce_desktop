"""Modal dialogs: forced password change, and adding workers and clients."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views import forms
from app.views.forms import Field, section, validate_all

ROLE_CHOICES = [
    ('warehouse', 'Warehouse worker'),
    ('driver', 'Delivery driver'),
    ('office', 'Office'),
    ('manager', 'Manager'),
]

LANGUAGE_CHOICES = [('he', 'Hebrew'), ('en', 'English'), ('ar', 'Arabic')]

PAY_BASIS_CHOICES = [
    ('hourly', 'By hour'),
    ('daily', 'By day'),
    ('monthly', 'Monthly salary'),
]
# The rate field's label depends on the pay basis.
PAY_RATE_LABEL = {
    'hourly': 'Hourly rate (₪)',
    'daily': 'Daily rate (₪)',
    'monthly': 'Monthly salary (₪)',
}
# Which API field the single rate value maps to, per basis.
PAY_RATE_KEY = {
    'hourly': 'hourly_rate',
    'daily': 'daily_rate',
    'monthly': 'monthly_salary',
}


def eye_icon():
    """A minimal eye glyph for the password reveal toggle."""
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor('#8A96A3')))
    painter.drawEllipse(4, 6, 12, 8)
    painter.setBrush(QColor('#8A96A3'))
    painter.drawEllipse(8, 8, 4, 4)
    painter.end()
    return QIcon(pixmap)


def add_reveal(line_edit):
    """Add a click-to-reveal toggle to a password field."""
    line_edit.setEchoMode(QLineEdit.Password)
    action = line_edit.addAction(eye_icon(), QLineEdit.TrailingPosition)
    action.setCheckable(True)
    action.toggled.connect(
        lambda shown: line_edit.setEchoMode(
            QLineEdit.Normal if shown else QLineEdit.Password)
    )
    return action


def field_row(*fields):
    """Lay several fields side by side, equal width."""
    box = QHBoxLayout()
    box.setSpacing(14)
    for field in fields:
        box.addWidget(field, 1)
    return box

BUSINESS_TYPES = [
    ('osek_murshe', 'Osek Murshe'),
    ('osek_patur', 'Osek Patur'),
    ('company', 'Company Ltd'),
    ('partnership', 'Partnership'),
    ('nonprofit', 'Non-profit'),
]


class BaseFormDialog(QDialog):
    """Shared plumbing: a form, an error line, and a submit that talks to the API."""

    title_text = ''
    submit_text = 'Save'

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setModal(True)
        self.setMinimumWidth(430)
        self.setWindowTitle(t(self.title_text))

        self.form = QFormLayout()
        self.form.setSpacing(11)
        self.form.setLabelAlignment(Qt.AlignLeft)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.submit = QPushButton(t(self.submit_text))
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.submit.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.submit)

        title = QLabel(t(self.title_text), objectName='LoginTitle')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 20)
        layout.setSpacing(14)
        layout.addWidget(title)
        self.build(layout)
        layout.addLayout(self.form)
        layout.addWidget(self.error)
        layout.addSpacing(4)
        layout.addLayout(buttons)

    def build(self, layout):
        """Subclasses add any intro text before the form."""

    def payload(self):
        raise NotImplementedError

    def endpoint(self):
        raise NotImplementedError

    def _submit(self):
        data = self.payload()
        if data is None:
            return
        self.error.hide()
        self._set_busy(True)
        self.api.post(self.endpoint(), data,
                      on_ok=self._on_ok, on_error=self._on_error)

    def _on_ok(self, _payload):
        self._set_busy(False)
        self.accept()

    def _on_error(self, error):
        self._set_busy(False)
        self.error.setText(error.message)
        self.error.show()
        self.adjustSize()

    def _set_busy(self, busy):
        self.submit.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.submit.setText(t('Saving…') if busy else t(self.submit_text))

    def _require(self, fields):
        """Return True if every named field has a value, else flag the gap."""
        for widget, label in fields:
            if not widget.text().strip():
                self.error.setText(f'{t(label)}: {t("This field is required.")}')
                self.error.show()
                widget.setFocus()
                return False
        return True


class ChangePasswordDialog(BaseFormDialog):
    """Shown when a manager-set password must be replaced.

    Not cancellable: the API refuses every other endpoint until this is done,
    so letting it be dismissed would leave the user in an app where nothing
    works and no explanation on screen.
    """

    title_text = 'Choose your password'
    submit_text = 'Save password'

    def __init__(self, api, parent=None):
        super().__init__(api, parent)
        self.cancel.hide()
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)

    def build(self, layout):
        hint = QLabel(
            t('Your account was created with a temporary password. '
              'Choose your own before continuing.'),
            objectName='LoginHint',
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.current = QLineEdit(echoMode=QLineEdit.Password)
        self.new = QLineEdit(echoMode=QLineEdit.Password)
        self.confirm = QLineEdit(echoMode=QLineEdit.Password)
        self.form.addRow(t('Current password'), self.current)
        self.form.addRow(t('New password'), self.new)
        self.form.addRow(t('Confirm password'), self.confirm)

    def endpoint(self):
        return 'auth/change-password/'

    def payload(self):
        if not self._require([
            (self.current, 'Current password'),
            (self.new, 'New password'),
        ]):
            return None
        if self.new.text() != self.confirm.text():
            self.error.setText(t('Passwords do not match.'))
            self.error.show()
            return None
        return {'current_password': self.current.text(), 'password': self.new.text()}

    def reject(self):
        """Ignore Escape — this dialog has to be completed."""


class AddWorkerDialog(QDialog):
    """Create or edit a worker account, in sections with inline validation.

    `worker` (a staff row dict) switches the dialog to edit mode: fields are
    prefilled, the ID number is locked, the password field becomes an optional
    reset, and saving PATCHes instead of creating.
    """

    def __init__(self, api, worker=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.worker = worker
        self.editing = worker is not None
        self.setModal(True)
        self.setMinimumSize(560, 640)
        self.setWindowTitle(t('Edit worker') if self.editing else t('Add worker'))
        self._build()
        if self.editing:
            self._load(worker)

    def _build(self):
        self.f_id = Field('ID number', required_field=True,
                          validators=[forms.id_number],
                          warn=forms.id_checksum_warning, placeholder='9 digits')
        self.f_first = Field('First name', required_field=True)
        self.f_last = Field('Last name', required_field=True)
        self.f_phone = Field('Phone', required_field=True, validators=[forms.phone])
        self.f_email = Field('Email', validators=[forms.email])
        self.f_address = Field('Address')
        self.f_role = Field('Role', kind='combo', required_field=True,
                            choices=ROLE_CHOICES)
        self.f_lang = Field('Language', kind='combo', choices=LANGUAGE_CHOICES)
        self.f_hired = Field('Hire date', placeholder='YYYY-MM-DD',
                             validators=[forms.date_iso])
        self.f_dob = Field('Date of birth', placeholder='YYYY-MM-DD',
                           validators=[forms.date_iso])
        self.f_econtact = Field('Emergency contact')
        self.f_ephone = Field('Emergency phone', validators=[forms.phone])
        password_required = not self.editing
        self.f_password = Field(
            'Starting password', required_field=password_required,
            placeholder=('Leave blank to keep unchanged' if self.editing
                         else 'They change it on first sign-in'))
        add_reveal(self.f_password.input)

        # -- payroll --
        self.f_paybasis = Field('Pay basis', kind='combo', choices=PAY_BASIS_CHOICES)
        self.f_rate = Field('Hourly rate (₪)', validators=[forms.number])
        self.f_dailyhours = Field('Regular hours / day', validators=[forms.number])
        self.f_dailyhours.set_value('8')
        self.ot_check = QCheckBox(t('Pay overtime (Israeli law: 125% / 150%)'))
        self.ot_check.setChecked(True)
        self.f_paybasis.input.currentIndexChanged.connect(self._sync_rate_label)

        self.fields = [self.f_id, self.f_first, self.f_last, self.f_phone,
                       self.f_email, self.f_address, self.f_role, self.f_lang,
                       self.f_hired, self.f_dob, self.f_econtact, self.f_ephone,
                       self.f_password, self.f_rate, self.f_dailyhours]
        self.error_map = {
            'id_number': self.f_id, 'first_name': self.f_first,
            'last_name': self.f_last, 'phone': self.f_phone,
            'email': self.f_email, 'role': self.f_role,
            'password': self.f_password, 'hired_on': self.f_hired,
            'date_of_birth': self.f_dob,
        }

        self.sections = [
            section('Identity'), section('Contact'),
            section('Employment'), section('Payroll'),
            section('Emergency contact (optional)'), section('Access'),
        ]
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 8, 0)
        content.setSpacing(9)
        content.addWidget(self.sections[0])
        content.addWidget(self.f_id)
        content.addLayout(field_row(self.f_first, self.f_last))
        content.addWidget(self.sections[1])
        content.addLayout(field_row(self.f_phone, self.f_email))
        content.addWidget(self.f_address)
        content.addWidget(self.sections[2])
        content.addLayout(field_row(self.f_role, self.f_lang))
        content.addLayout(field_row(self.f_hired, self.f_dob))
        content.addWidget(self.sections[3])
        content.addLayout(field_row(self.f_paybasis, self.f_rate))
        content.addWidget(self.f_dailyhours)
        content.addWidget(self.ot_check)
        content.addWidget(self.sections[4])
        content.addLayout(field_row(self.f_econtact, self.f_ephone))
        content.addWidget(self.sections[5])
        content.addWidget(self.f_password)
        content.addStretch()

        inner = QWidget()
        inner.setLayout(content)
        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        title = QLabel(t('Edit worker') if self.editing else t('Add worker'),
                       objectName='LoginTitle')
        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self._submit_label = t('Save') if self.editing else t('Create worker')
        self.submit = QPushButton(self._submit_label)
        self.cancel = QPushButton(t('Cancel'), objectName='Ghost')
        self.submit.clicked.connect(self._submit)
        self.cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addWidget(self.error, 1)
        buttons.addWidget(self.cancel)
        buttons.addWidget(self.submit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 22, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

    def _sync_rate_label(self, *_):
        basis = self.f_paybasis.value() or 'hourly'
        self.f_rate.label.setText(t(PAY_RATE_LABEL[basis]))

    def _load(self, w):
        self.f_id.set_value(w.get('id_number'))
        self.f_id.input.setReadOnly(True)
        self.f_first.set_value(w.get('first_name'))
        self.f_last.set_value(w.get('last_name'))
        self.f_phone.set_value(w.get('phone'))
        self.f_email.set_value(w.get('email'))
        self.f_address.set_value(w.get('address'))
        self.f_role.set_value(w.get('role'))
        self.f_lang.set_value(w.get('language'))
        self.f_hired.set_value(w.get('hired_on'))
        self.f_dob.set_value(w.get('date_of_birth'))
        self.f_econtact.set_value(w.get('emergency_contact'))
        self.f_ephone.set_value(w.get('emergency_phone'))
        basis = w.get('pay_basis') or 'hourly'
        self.f_paybasis.set_value(basis)
        self._sync_rate_label()
        self.f_rate.set_value(w.get(PAY_RATE_KEY[basis]))
        self.f_dailyhours.set_value(w.get('daily_regular_hours') or '8')
        self.ot_check.setChecked(w.get('overtime_enabled', True))

    def _submit(self):
        self.error.hide()
        if not validate_all(self.fields):
            return
        basis = self.f_paybasis.value() or 'hourly'
        data = {
            'first_name': self.f_first.value(),
            'last_name': self.f_last.value(),
            'phone': self.f_phone.value(),
            'email': self.f_email.value(),
            'address': self.f_address.value(),
            'role': self.f_role.value(),
            'language': self.f_lang.value(),
            'emergency_contact': self.f_econtact.value(),
            'emergency_phone': self.f_ephone.value(),
            # Payroll: send all three rate fields (the unused ones cleared) so
            # switching a worker's basis doesn't leave a stale rate behind.
            'pay_basis': basis,
            'hourly_rate': None,
            'daily_rate': None,
            'monthly_salary': None,
            'overtime_enabled': self.ot_check.isChecked(),
        }
        rate = self.f_rate.value().replace(',', '.')
        data[PAY_RATE_KEY[basis]] = rate or None
        if self.f_dailyhours.value():
            data['daily_regular_hours'] = self.f_dailyhours.value().replace(',', '.')
        if self.f_hired.value():
            data['hired_on'] = self.f_hired.value()
        if self.f_dob.value():
            data['date_of_birth'] = self.f_dob.value()

        self._set_busy(True)
        if self.editing:
            # A blank password on edit means "keep the current one".
            if self.f_password.value():
                self._reset_password_then_save(data)
            else:
                self.api.patch(f'staff/{self.worker["id"]}/', data,
                               on_ok=self._on_ok, on_error=self._on_error)
        else:
            data['id_number'] = self.f_id.value()
            data['password'] = self.f_password.value()
            self.api.post('staff/', data, on_ok=self._on_ok, on_error=self._on_error)

    def _reset_password_then_save(self, data):
        # Reset the password, then patch the rest of the details.
        self.api.post(f'staff/{self.worker["id"]}/reset_password/',
                      {'password': self.f_password.value()},
                      on_ok=lambda _p: self.api.patch(
                          f'staff/{self.worker["id"]}/', data,
                          on_ok=self._on_ok, on_error=self._on_error),
                      on_error=self._on_error)

    def _on_ok(self, _payload):
        self.accept()

    def _on_error(self, error):
        self._set_busy(False)
        payload = error.payload if isinstance(error.payload, dict) else {}
        routed = False
        for key, field in self.error_map.items():
            if key in payload:
                msgs = payload[key]
                text = '; '.join(str(m) for m in msgs) if isinstance(msgs, list) else str(msgs)
                field._paint('invalid', text)
                routed = True
        if not routed:
            self.error.setText(error.message)
            self.error.show()

    def _set_busy(self, busy):
        self.submit.setEnabled(not busy)
        self.cancel.setEnabled(not busy)
        self.submit.setText(t('Saving…') if busy else self._submit_label)
