"""Sign-in screen.

A two-panel layout: a branded panel on one side, the form on the other — the
shape logistics apps use because it reads as a product rather than a dialog. In
RTL the two panels swap sides, which Qt handles from the window's layout
direction.

One field for the identifier: staff type an ID number, clients type a phone.
The backend resolves either, so the desktop never has to ask which.

The server address is reachable from here as well as from Settings. Settings
sits behind the login, so a machine pointed at the wrong server could otherwise
never be corrected from inside the app -- you would have to sign in to fix the
thing preventing you from signing in.
"""

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from app import i18n
from app.i18n import t


class ServerDialog(QDialog):
    """Edit the backend address without being signed in.

    Deliberately the same three steps Settings uses -- probe, apply to the live
    client, persist to QSettings -- so the two entry points cannot drift into
    saving the address differently.
    """

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(t('Server connection'))
        self.setMinimumWidth(430)

        hint = QLabel(
            t('Where this computer finds the AlomForce server.'),
            objectName='CardHint',
        )
        hint.setWordWrap(True)

        # Show the plain address. '/api' is an implementation detail of the
        # client, and _save() re-appends it, so putting it in the box only
        # invites someone to paste a second one after it.
        current = self.api.base_url.rstrip('/')
        if current.endswith('/api'):
            current = current[:-4]
        self.address = QLineEdit(current)
        self.address.setPlaceholderText('https://alomforce-production.up.railway.app')
        self.address.setMinimumHeight(38)
        self.address.setClearButtonEnabled(True)

        self.status = QLabel('', objectName='CardHint')
        self.status.setWordWrap(True)

        self.save_btn = QPushButton(t('Test and save'), objectName='PrimaryButton')
        self.save_btn.setMinimumHeight(38)
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)

        cancel = QPushButton(t('Cancel'), objectName='Ghost')
        cancel.setMinimumHeight(38)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(10)
        layout.addWidget(QLabel(t('Backend address'), objectName='FieldLabel'))
        layout.addWidget(self.address)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addSpacing(6)
        layout.addLayout(buttons)

        self.address.returnPressed.connect(self._save)

    def _save(self):
        from app.api import ApiClient

        url = self.address.text().strip()
        if not url:
            self.status.setText(t('Enter a server address.'))
            return

        self.save_btn.setEnabled(False)
        self.save_btn.setText(t('Testing…'))
        # Probe blocks the UI thread, but its timeout is 8s and the dialog has
        # nothing else to do while it waits -- same trade-off Settings makes.
        ok = ApiClient.probe(url)
        self.save_btn.setEnabled(True)
        self.save_btn.setText(t('Test and save'))

        if not ok:
            self.status.setText(t("Couldn't reach that server."))
            return

        base = url.rstrip('/')
        if not base.endswith('/api'):
            base += '/api'
        self.api.set_base_url(base)
        QSettings('AlomForce', 'AlomForce').setValue('server_url', base)
        self.accept()


class LoginView(QWidget):
    logged_in = Signal(object)
    language_changed = Signal(str)

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.setObjectName('LoginRoot')
        self._build()

    # -- construction ----------------------------------------------------

    def _build(self):
        brand = self._brand_panel()
        form = self._form_panel()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(brand, 5)
        layout.addWidget(form, 6)

    def _brand_panel(self):
        panel = QWidget(objectName='BrandPanel')
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        mark = QLabel('◆', objectName='BrandMark')
        name = QLabel('AlomForce', objectName='BrandWordmark')
        tagline = QLabel(
            t('Aluminium profiles — stock, orders and delivery, in one place.'),
            objectName='BrandTagline',
        )
        tagline.setWordWrap(True)

        footer = QLabel(t('Built for the aluminium trade.'), objectName='BrandFooter')

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(52, 52, 52, 40)
        layout.setSpacing(0)
        layout.addWidget(mark)
        layout.addSpacing(18)
        layout.addWidget(name)
        layout.addSpacing(14)
        layout.addWidget(tagline)
        layout.addStretch()
        layout.addWidget(footer)

        self._tagline = tagline
        self._brand_footer = footer
        return panel

    def _form_panel(self):
        panel = QWidget(objectName='FormPanel')

        card = QFrame(objectName='LoginCard')
        card.setFixedWidth(360)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(15, 30, 45, 40))
        card.setGraphicsEffect(shadow)

        self.heading = QLabel(t('Sign in'), objectName='LoginTitle')
        self.subheading = QLabel(t('Welcome back. Please sign in to continue.'),
                                 objectName='LoginHint')
        self.subheading.setWordWrap(True)

        self.id_label = QLabel(t('ID number or phone'), objectName='FieldLabel')
        self.identifier = QLineEdit()
        self.identifier.setPlaceholderText(t('e.g. 012345678'))
        self.identifier.setClearButtonEnabled(True)
        self.identifier.setMinimumHeight(42)

        self.pw_label = QLabel(t('Password'), objectName='FieldLabel')
        self.password = QLineEdit()
        self.password.setPlaceholderText('••••••••')
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMinimumHeight(42)
        self._reveal = self.password.addAction(
            self._eye_icon(), QLineEdit.TrailingPosition
        )
        self._reveal.setCheckable(True)
        self._reveal.toggled.connect(self._toggle_reveal)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.submit = QPushButton(t('Sign in'), objectName='PrimaryButton')
        self.submit.setDefault(True)
        self.submit.setMinimumHeight(44)
        self.submit.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(38, 40, 38, 34)
        layout.setSpacing(0)
        layout.addWidget(self.heading)
        layout.addSpacing(6)
        layout.addWidget(self.subheading)
        layout.addSpacing(26)
        layout.addWidget(self.id_label)
        layout.addSpacing(6)
        layout.addWidget(self.identifier)
        layout.addSpacing(16)
        layout.addWidget(self.pw_label)
        layout.addSpacing(6)
        layout.addWidget(self.password)
        layout.addSpacing(12)
        layout.addWidget(self.error)
        layout.addSpacing(14)
        layout.addWidget(self.submit)

        # Language selector, tucked at the top-right of the form panel.
        self.language = QComboBox(objectName='LangSelect')
        for code, label in i18n.LANGUAGES.items():
            self.language.addItem(label, code)
        self.language.setCurrentIndex(self.language.findData(i18n.get_language()))
        self.language.setFixedWidth(120)
        self.language.currentIndexChanged.connect(
            lambda: self.language_changed.emit(self.language.currentData())
        )

        # Server address, reachable before signing in. Sits beside the card
        # rather than inside it, so it reads as a machine setting rather than
        # another thing to fill in to sign in.
        # Creating an account sits next to signing in, not buried: on a fresh
        # deployment this is the only way in, since the first manager cannot be
        # created by a manager who does not exist yet.
        self.register_btn = QPushButton(t('Create account'), objectName='Ghost')
        self.register_btn.setCursor(Qt.PointingHandCursor)
        self.register_btn.clicked.connect(self._open_register)

        self.server_btn = QPushButton(t('Server'), objectName='Ghost')
        self.server_btn.setCursor(Qt.PointingHandCursor)
        self.server_btn.clicked.connect(self._edit_server)

        self.server_hint = QLabel('', objectName='CardHint')
        self.server_hint.setAlignment(Qt.AlignCenter)
        self.server_hint.setWordWrap(True)
        self._refresh_server_hint()

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.server_btn)
        top.addWidget(self.register_btn)
        top.addStretch()
        top.addWidget(self.language)

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(30, 24, 30, 24)
        outer.addLayout(top)
        outer.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(card)
        row.addStretch()
        outer.addLayout(row)
        outer.addSpacing(12)
        outer.addWidget(self.server_hint)
        outer.addStretch()

        self.submit.clicked.connect(self._submit)
        self.identifier.returnPressed.connect(self._submit)
        self.password.returnPressed.connect(self._submit)
        return panel

    def _eye_icon(self):
        # Qt ships no eye icon by name, so draw a minimal one so the reveal
        # toggle reads as an eye rather than a mystery glyph.
        from PySide6.QtGui import QPainter, QPen, QPixmap

        pixmap = QPixmap(20, 20)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor('#8A96A3'))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawEllipse(6, 6, 8, 8)
        painter.setBrush(QColor('#8A96A3'))
        painter.drawEllipse(9, 9, 2, 2)
        painter.end()
        from PySide6.QtGui import QIcon
        return QIcon(pixmap)

    # -- behaviour -------------------------------------------------------

    def _toggle_reveal(self, shown):
        self.password.setEchoMode(QLineEdit.Normal if shown else QLineEdit.Password)

    def _refresh_server_hint(self):
        """Show which server a sign-in would go to.

        Worth the line of screen: 'wrong password' and 'right password, wrong
        server' look identical from here otherwise.
        """
        base = self.api.base_url.rstrip('/')
        if base.endswith('/api'):
            base = base[:-4]
        self.server_hint.setText(t('Server: {url}').replace('{url}', base))

    def _open_register(self):
        from app.views.register_dialog import RegisterDialog

        dialog = RegisterDialog(self.api, self)
        if dialog.exec() and dialog.payload:
            # Registration returns the same token pair as a login, so the app
            # can go straight in rather than asking for the details again.
            self.logged_in.emit(dialog.payload)

    def _edit_server(self):
        dialog = ServerDialog(self.api, self)
        if dialog.exec():
            self._refresh_server_hint()
            self.error.hide()

    def retranslate(self):
        self._tagline.setText(
            t('Aluminium profiles — stock, orders and delivery, in one place.')
        )
        self._brand_footer.setText(t('Built for the aluminium trade.'))
        self.heading.setText(t('Sign in'))
        self.subheading.setText(t('Welcome back. Please sign in to continue.'))
        self.id_label.setText(t('ID number or phone'))
        self.identifier.setPlaceholderText(t('e.g. 012345678'))
        self.pw_label.setText(t('Password'))
        self.submit.setText(t('Sign in'))
        self.server_btn.setText(t('Server'))
        self.register_btn.setText(t('Create account'))
        self._refresh_server_hint()

    def _submit(self):
        identifier = self.identifier.text().strip()
        password = self.password.text()
        if not identifier or not password:
            self._show_error(t('Enter your ID number and password.'))
            return

        self.error.hide()
        self._set_busy(True)
        self.api.login(identifier, password,
                       on_ok=self._on_ok, on_error=self._on_error)

    def _on_ok(self, payload):
        self._set_busy(False)
        self.password.clear()
        self.logged_in.emit(payload)

    def _on_error(self, error):
        self._set_busy(False)
        self._show_error(error.message)

    def _show_error(self, message):
        self.error.setText(message)
        self.error.show()

    def _set_busy(self, busy):
        self.submit.setEnabled(not busy)
        self.submit.setText(t('Signing in…') if busy else t('Sign in'))
        self.identifier.setEnabled(not busy)
        self.password.setEnabled(not busy)

    def focus_first_field(self):
        self.identifier.setFocus(Qt.OtherFocusReason)
