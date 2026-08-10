"""Sign-in screen.

A two-panel layout: a branded panel on one side, the form on the other — the
shape logistics apps use because it reads as a product rather than a dialog. In
RTL the two panels swap sides, which Qt handles from the window's layout
direction.

One field for the identifier: staff type an ID number, clients type a phone.
The backend resolves either, so the desktop never has to ask which.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
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
