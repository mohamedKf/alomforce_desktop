"""The bell, and the list behind it.

The desktop has no push channel, so it asks. Every notification the server
sends is written down as a row, and this polls for the unread count on a timer
and fetches the list only when somebody actually opens the panel -- the count
is the cheap query, the list is not.

The interval is deliberately unhurried. This is an office tool showing that a
delivery was signed or a worker clocked in; nobody needs it within the second,
and a tighter poll would be one request per user per few seconds, all day, for
information that changes a handful of times an hour.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

POLL_SECONDS = 45


class BellButton(QPushButton):
    """A bell with an unread badge painted on it."""

    opened = Signal()

    def __init__(self, parent=None):
        super().__init__('🔔', parent, objectName='Bell')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(40, 34)
        self.setFlat(True)
        self._unread = 0
        self.clicked.connect(self.opened.emit)

    def set_unread(self, count):
        if count == self._unread:
            return
        self._unread = count
        self.setToolTip(
            t('{n} unread').replace('{n}', str(count)) if count else t('Notifications'))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._unread:
            return
        # A count, or 9+ -- the exact number stops being useful past a glance.
        label = '9+' if self._unread > 9 else str(self._unread)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#D9534F'))
        width = 20 if len(label) > 1 else 16
        painter.drawEllipse(self.width() - width - 2, 2, width, 16)
        painter.setPen(QColor('white'))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.width() - width - 2, 2, width, 16,
                         Qt.AlignCenter, label)
        painter.end()


class NotificationsPanel(QDialog):
    """The list itself, opened from the bell."""

    read_changed = Signal()

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle(t('Notifications'))
        self.setMinimumSize(420, 480)

        self.status = QLabel(t('Loading…'), objectName='CardHint')
        self.status.setAlignment(Qt.AlignCenter)

        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()

        holder = QWidget()
        holder.setLayout(self.list_layout)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(holder)
        scroll.setFrameShape(QScrollArea.NoFrame)

        self.mark_btn = QPushButton(t('Mark all as read'), objectName='Ghost')
        self.mark_btn.clicked.connect(self._mark_all)
        close = QPushButton(t('Close'), objectName='Ghost')
        close.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.mark_btn)
        buttons.addStretch()
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.addWidget(QLabel(t('Notifications'), objectName='LoginTitle'))
        layout.addWidget(self.status)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

        self.load()

    def load(self):
        self.api.get('notifications/', on_ok=self._show, on_error=self._failed)

    def _failed(self, error):
        self.status.setText(getattr(error, 'message', str(error)))
        self.status.show()

    def _show(self, payload):
        rows = payload.get('results', payload) if isinstance(payload, dict) else payload
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rows:
            self.status.setText(t('Nothing yet.'))
            self.status.show()
            return
        self.status.hide()
        for row in rows:
            self.list_layout.insertWidget(self.list_layout.count() - 1,
                                          self._row(row))

    def _row(self, row):
        unread = not row.get('read_at')
        card = QWidget(objectName='NotificationCard')
        # Unread is carried by a property so the stylesheet can mark it,
        # rather than by hand-set colours here.
        card.setProperty('unread', unread)

        title = QLabel(row.get('title', ''))
        title.setWordWrap(True)
        title.setStyleSheet(
            'font-weight: 700;' if unread else 'font-weight: 500; color: #6B7785;')
        body = QLabel(row.get('body', ''))
        body.setWordWrap(True)
        body.setStyleSheet('color: #6B7785; font-size: 12px;')
        when = QLabel((row.get('created_at') or '').replace('T', ' ')[:16])
        when.setStyleSheet('color: #9AA6B2; font-size: 11px;')

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(when)
        return card

    def _mark_all(self):
        self.mark_btn.setEnabled(False)

        def done(_payload):
            self.mark_btn.setEnabled(True)
            self.read_changed.emit()
            self.load()

        self.api.post('notifications/mark_read/', {}, on_ok=done,
                      on_error=lambda e: self.mark_btn.setEnabled(True))


class NotificationWatcher:
    """Keeps a BellButton's badge current."""

    def __init__(self, api, bell):
        self.api = api
        self.bell = bell
        self.timer = QTimer(bell)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(POLL_SECONDS * 1000)
        self.refresh()

    def refresh(self):
        # A failure here is not worth showing anyone: the badge simply does
        # not move until the next tick.
        self.api.get('notifications/unread_count/',
                     on_ok=lambda p: self.bell.set_unread(int(p.get('unread', 0))),
                     on_error=lambda _e: None)

    def stop(self):
        self.timer.stop()
