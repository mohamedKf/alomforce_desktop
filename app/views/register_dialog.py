"""Create an account without having one.

Two kinds, because they are genuinely different people: a client registering
their company, and a manager who was given the register code. The manager
option only appears when the server reports a code is configured, so a
deployment with registration switched off does not advertise a door that does
not open.

The desktop is the office's tool, so the manager path matters most here -- it
is how the first manager gets into a fresh deployment, which previously needed
shell access to the server.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.i18n import t
from app.views.forms import Field, validate_all
from app.views import forms


class RegisterDialog(QDialog):
    """Signs the new account straight in; `payload` holds the login response."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.payload = None
        self.setWindowTitle(t('Create account'))
        self.setMinimumWidth(520)

        self.as_client = QRadioButton(t('Client'))
        self.as_manager = QRadioButton(t('Manager'))
        self.as_client.setChecked(True)
        self.as_client.toggled.connect(self._mode_changed)

        self.kind_row = QHBoxLayout()
        self.kind_row.addWidget(self.as_client)
        self.kind_row.addWidget(self.as_manager)
        self.kind_row.addStretch()

        self.f_business = Field('Business name')
        self.f_id = Field('ID number')
        self.f_code = Field('Register code')
        self.f_code.input.setEchoMode(QLineEdit.Password)
        self.f_first = Field('First name', required_field=True)
        self.f_last = Field('Last name', required_field=True)
        self.f_phone = Field('Phone', required_field=True, validators=[forms.phone])
        self.f_password = Field('Password', required_field=True)
        self.f_password.input.setEchoMode(QLineEdit.Password)
        self.f_confirm = Field('Repeat password', required_field=True)
        self.f_confirm.input.setEchoMode(QLineEdit.Password)

        self.fields = [self.f_first, self.f_last, self.f_phone,
                       self.f_password, self.f_confirm]

        self.hint = QLabel(t('Ask the business owner for the register code.'),
                           objectName='CardHint')
        self.hint.setWordWrap(True)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.save = QPushButton(t('Create account'))
        self.save.setCursor(Qt.PointingHandCursor)
        self.save.clicked.connect(self._submit)
        cancel = QPushButton(t('Cancel'), objectName='Ghost')
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(10)
        layout.addLayout(self.kind_row)
        layout.addWidget(self.f_business)
        layout.addWidget(self.f_id)
        layout.addWidget(self.f_code)
        layout.addWidget(self.hint)
        layout.addWidget(self.f_first)
        layout.addWidget(self.f_last)
        layout.addWidget(self.f_phone)
        layout.addWidget(self.f_password)
        layout.addWidget(self.f_confirm)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

        self._mode_changed()
        self._check_manager_option()

    # -- behaviour --------------------------------------------------------

    def _mode_changed(self):
        client = self.as_client.isChecked()
        self.f_business.setVisible(client)
        self.f_id.setVisible(not client)
        self.f_code.setVisible(not client)
        self.hint.setVisible(not client)
        self.error.hide()

    def _check_manager_option(self):
        """Hide the manager choice unless the server has a code configured.

        Only whether one exists is asked for; the code itself never leaves the
        server.
        """
        def seen(payload):
            enabled = bool((payload or {}).get('manager_registration'))
            self.as_manager.setVisible(enabled)
            if not enabled:
                self.as_client.setChecked(True)

        self.as_manager.setVisible(False)
        self.api.get('config/', on_ok=seen, on_error=lambda _e: None)

    def _submit(self):
        self.error.hide()
        if not validate_all(self.fields):
            return
        # Checked here rather than left to the server: a mistyped password that
        # is accepted locks the person out of the account they just made.
        if self.f_password.value() != self.f_confirm.value():
            self._fail(t('The two passwords do not match.'))
            return

        client = self.as_client.isChecked()
        if client and not self.f_business.value():
            self.f_business._paint('invalid', t('Enter your business name.'))
            return
        if not client and not (self.f_id.value() and self.f_code.value()):
            for field in (self.f_id, self.f_code):
                if not field.value():
                    field._paint('invalid', t('Required.'))
            return

        data = {
            'account': 'client' if client else 'manager',
            'first_name': self.f_first.value(),
            'last_name': self.f_last.value(),
            'phone': self.f_phone.value(),
            'password': self.f_password.value(),
        }
        if client:
            data['business_name'] = self.f_business.value()
        else:
            data['id_number'] = self.f_id.value()
            data['register_code'] = self.f_code.value()

        self.save.setEnabled(False)
        self.save.setText(t('Creating…'))
        self.api.post('auth/register/', data, auth=False,
                      on_ok=self._done, on_error=self._on_error)

    def _done(self, payload):
        self.payload = payload
        self.accept()

    def _on_error(self, error):
        self._fail(getattr(error, 'message', str(error)))

    def _fail(self, message):
        self.save.setEnabled(True)
        self.save.setText(t('Create account'))
        self.error.setText(message)
        self.error.show()
