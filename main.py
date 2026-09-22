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
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from app import i18n, reporting, theme
from app.api import DEFAULT_BASE_URL, ApiClient
from app.session import Session
from app.views.dialogs import ChangePasswordDialog
from app.views.login import LoginView
from app.views.shell import Shell

API_BASE_URL = os.environ.get('ALOMFORCE_API', DEFAULT_BASE_URL)


def resource_path(rel):
    """Absolute path to a bundled resource, in dev and in a PyInstaller build.

    PyInstaller unpacks data files under sys._MEIPASS; in dev they sit next to
    this file. Using this keeps the app runnable from wherever the built binary
    is placed, without any hardcoded install location.
    """
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


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
        reporting.set_user(None)
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
        # The same call brings the Sentry DSN. Cached for the next start, and
        # started now for the first run, which had nothing cached at launch.
        reporting.apply_config(self.api.config)
        reporting.set_user(self.session.user)
        self.shell.apply_session()
        # And the published release, if there is one newer than this build. Said
        # once per version as a strip over the pages, never as a dialog.
        self.shell.apply_update_notice((self.api.config or {}).get('update'))
        self.stack.setCurrentWidget(self.shell)

    def _enter_login(self):
        self.stack.setCurrentWidget(self.login)
        self.login.focus_first_field()

    def ensure_server_configured(self):
        """On first run there is no server link yet; prompt for it up front so
        the sign-in screen isn't a dead end. Called once after the window shows."""
        if not self.api.is_configured() and self.stack.currentWidget() is self.login:
            self.login.prompt_for_server()

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
    # Before anything that can fail: the cached DSN from the last run, and the
    # hooks that turn a silent traceback into a report and a word to the user.
    reporting.bootstrap()
    app = QApplication(sys.argv)
    app.setApplicationName('AlomForce')
    app.setOrganizationName('AlomForce')
    icon = QIcon(resource_path(os.path.join('app', 'assets', 'alomforce.png')))
    if not icon.isNull():
        app.setWindowIcon(icon)
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    # First run has no server link yet — prompt for it after the window is up.
    window.ensure_server_configured()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
