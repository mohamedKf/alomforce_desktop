"""The "an update is available" notice.

The provider publishes a release on the server; every client that signs in is
told about it in passing, because otherwise a yard stays on the build it was
installed with until somebody telephones.

Deliberately a slim strip at the top of the shell rather than a dialog: the
office opens this app to finish an order, and a modal in front of that is
something people learn to click away without reading. Dismissing it remembers
the version, so it asks once per release and not once per morning.
"""

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app import APP_VERSION
from app.i18n import t

# Remembered per machine, alongside the saved language and server address.
DISMISSED_KEY = 'update_dismissed_version'


def _parts(value):
    """A version as a list of numbers, or None when it is not one."""
    text = str(value or '').strip()
    if not text:
        return None
    numbers = []
    for bit in text.split('.'):
        if not bit.isdigit():
            return None
        numbers.append(int(bit))
    return numbers or None


def is_newer(published, current=APP_VERSION):
    """True when `published` is strictly higher than `current`.

    Compared segment by segment as numbers: '1.10.0' is newer than '1.9.0',
    which a plain string comparison gets backwards. Anything that will not
    parse -- a missing value, a null, a build tag like '1.2.0-rc1' -- counts as
    "no update", since nagging a whole office about a release that may not
    exist is worse than missing one.
    """
    new, have = _parts(published), _parts(current)
    if not new or not have:
        return False
    width = max(len(new), len(have))
    new = new + [0] * (width - len(new))
    have = have + [0] * (width - len(have))
    return new > have


class UpdateBanner(QFrame):
    """The strip itself. Hidden until told there is something to say."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('UpdateBanner')
        self._version = ''
        self._url = ''
        self._notes = ''
        self.setVisible(False)

        self.title = QLabel('', objectName='UpdateTitle')
        self.notes = QLabel('', objectName='UpdateNotes')
        self.notes.setWordWrap(True)
        self.download = QPushButton(t('Download'), objectName='UpdateDownload')
        self.download.setCursor(Qt.PointingHandCursor)
        self.download.clicked.connect(self._open)
        self.close_btn = QPushButton('✕', objectName='BannerClose')
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip(t('Dismiss'))
        self.close_btn.clicked.connect(self._dismiss)

        words = QVBoxLayout()
        words.setSpacing(0)
        words.addWidget(self.title)
        words.addWidget(self.notes)

        row = QHBoxLayout(self)
        row.setContentsMargins(20, 8, 12, 8)
        row.setSpacing(12)
        row.addWidget(QLabel('⬆', objectName='UpdateMark'), 0, Qt.AlignTop)
        row.addLayout(words, 1)
        row.addWidget(self.download, 0, Qt.AlignVCenter)
        row.addWidget(self.close_btn, 0, Qt.AlignTop)

    # -- data ------------------------------------------------------------

    def apply(self, update):
        """Decide whether to appear, from /api/config/'s `update` block.

        `update` is {'desktop': {...} | None, 'android': {...} | None} — or
        absent entirely on an older server. A null desktop release means the
        provider has published nothing, and then this says nothing at all: an
        "you are up to date" line every morning is noise, not news.
        """
        release = update.get('desktop') if isinstance(update, dict) else None
        if not isinstance(release, dict):
            self.setVisible(False)
            return

        version = str(release.get('version') or '').strip()
        if not is_newer(version):
            self.setVisible(False)
            return
        if self._dismissed() == version:
            self.setVisible(False)
            return

        self._version = version
        self._url = str(release.get('url') or '').strip()
        self._notes = str(release.get('notes') or '').strip()
        # Nothing to open without a link; the version alone is still worth
        # saying, so the strip stays and only the button goes.
        self.download.setVisible(bool(self._url))
        self._retext()
        self.setVisible(True)

    @staticmethod
    def _settings():
        return QSettings('AlomForce', 'AlomForce')

    def _dismissed(self):
        return str(self._settings().value(DISMISSED_KEY) or '')

    def _dismiss(self):
        if self._version:
            self._settings().setValue(DISMISSED_KEY, self._version)
        self.setVisible(False)

    def _open(self):
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))

    # -- i18n ------------------------------------------------------------

    def _retext(self):
        self.title.setText(
            t('Version {version} is available').format(version=self._version))
        # The provider's own words when there are any; otherwise say which
        # build this is, which is the next thing anyone asks.
        self.notes.setText(
            self._notes
            or t('You are running {version}.').format(version=APP_VERSION))

    def retranslate(self):
        self.download.setText(t('Download'))
        self.close_btn.setToolTip(t('Dismiss'))
        if self._version:
            self._retext()
