"""AlomForce desktop — entry point.

Office application for stock, catalog, orders, clients, invoices and delivery
notes. Talks to the AlomForce Django backend over its REST API; it holds no
database of its own.

    python main.py
    ALOMFORCE_API=https://api.example.com/api/ python main.py
"""

import os
import sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from app import i18n, theme
from app.api import DEFAULT_BASE_URL, ApiClient
from app.session import Session
from app.views.dialogs import ChangePasswordDialog
from app.views.login import LoginView
from app.views.shell import Shell

API_BASE_URL = os.environ.get('ALOMFORCE_API', DEFAULT_BASE_URL)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('AlomForce')
        self.resize(1240, 780)
        self.setMinimumSize(960, 620)

        self.session = Session()
        # A server address saved from the Settings screen overrides the default.
        self._settings = QSettings('AlomForce', 'AlomForce')
        base = self._settings.value('server_url', API_BASE_URL)
        self.api = ApiClient(self.session, base)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login = LoginView(self.api)
        self.login.logged_in.connect(self._on_logged_in)
        self.login.language_changed.connect(self.set_language)
        self.login.language_changed.connect(self._remember_language)

        self.shell = Shell(self.api, self.session)
        self.shell.signed_out.connect(self._on_signed_out)
        self.shell.language_changed.connect(self.set_language)
        self.shell.language_changed.connect(self._remember_language)

        self.stack.addWidget(self.login)
        self.stack.addWidget(self.shell)

        # Start in the language the user last chose on this machine (falling back
        # to their account default), so the login screen is already localised.
        self.set_language(self._preferred_language())

        # A stored session skips the login screen. The token may be stale; the
        # API client refreshes on the first 401 rather than checking up front.
        if self.session.load():
            self._enter_app()
        else:
            self._enter_login()

    # -- navigation ------------------------------------------------------

    def _on_logged_in(self, payload):
        self.session.start(payload)
        self.set_language(self._preferred_language())
        self._enter_app()

    def _on_signed_out(self):
        self.session.clear()
        self._enter_login()

    def _enter_app(self):
        self.set_language(self._preferred_language())

        # The API refuses every other endpoint until this is done, so the shell
        # would load into a wall of 403s if it were skipped.
        if (self.session.user or {}).get('must_change_password'):
            dialog = ChangePasswordDialog(self.api, self)
            if not dialog.exec():
                self._on_signed_out()
                return
            self.session.user['must_change_password'] = False
            self.session.save()

        # Pull the Mapbox token before the shell builds its pages, so the map
        # widgets are created with it rather than falling back to OSM.
        self.api.load_config()
        self.shell.apply_session()
        self.stack.setCurrentWidget(self.shell)

    def _enter_login(self):
        self.stack.setCurrentWidget(self.login)
        self.login.focus_first_field()

    # -- i18n ------------------------------------------------------------

    def _preferred_language(self):
        """The language to show: this machine's saved choice wins, then the
        user's account default, then Hebrew (the app default). Language is a
        per-device UI setting, so a saved choice must survive login and restarts."""
        saved = self._settings.value('language')
        if saved in i18n.LANGUAGES:
            return saved
        return self.session.language or 'he'

    def _remember_language(self, code):
        self._settings.setValue('language', code)

    def set_language(self, code):
        if code == i18n.get_language():
            return
        i18n.set_language(code)
        # Qt propagates layout direction to every child widget, so Hebrew and
        # Arabic mirror the whole window -- sidebar to the right, tables and
        # text right-aligned -- without per-widget handling.
        direction = Qt.RightToLeft if i18n.is_rtl(code) else Qt.LeftToRight
        QApplication.instance().setLayoutDirection(direction)
        self.login.retranslate()
        self.shell.retranslate()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('AlomForce')
    app.setOrganizationName('AlomForce')
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
