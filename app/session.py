"""Signed-in session state: tokens, user, language.

Tokens live in a file under the user's config directory rather than in the
project, so signing in survives a restart without putting credentials next to
the source. The password is never stored -- only the tokens the API issued.
"""

import json
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal


def _config_dir():
    base = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    path = Path(base) / 'AlomForce'
    path.mkdir(parents=True, exist_ok=True)
    return path


SESSION_FILE = _config_dir() / 'session.json'


class Session(QObject):
    """Holds the current user and tokens. Emits when either changes."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self.access = None
        self.refresh = None
        self.user = None
        self.client = None

    # -- state ---------------------------------------------------------

    @property
    def is_authenticated(self):
        return bool(self.access and self.user)

    @property
    def role(self):
        return (self.user or {}).get('role')

    @property
    def full_name(self):
        return (self.user or {}).get('full_name', '')

    @property
    def language(self):
        return (self.user or {}).get('language', 'en')

    def start(self, payload):
        """Adopt a successful login response."""
        self.access = payload.get('access')
        self.refresh = payload.get('refresh')
        self.user = payload.get('user')
        self.client = payload.get('client')
        self.save()
        self.changed.emit()

    def update_access(self, access):
        self.access = access
        self.save()

    def clear(self):
        self.access = self.refresh = self.user = self.client = None
        SESSION_FILE.unlink(missing_ok=True)
        self.changed.emit()

    # -- persistence ---------------------------------------------------

    def save(self):
        SESSION_FILE.write_text(json.dumps({
            'access': self.access,
            'refresh': self.refresh,
            'user': self.user,
            'client': self.client,
        }), encoding='utf-8')

    def load(self):
        """Restore a previous session. Returns True if one was found.

        The token may well be expired; the API client handles that by
        refreshing on the first 401 rather than checking up front.
        """
        if not SESSION_FILE.exists():
            return False
        try:
            data = json.loads(SESSION_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            SESSION_FILE.unlink(missing_ok=True)
            return False

        self.access = data.get('access')
        self.refresh = data.get('refresh')
        self.user = data.get('user')
        self.client = data.get('client')
        return self.is_authenticated
