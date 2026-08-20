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
    QButtonGroup,
    QDialog,
    QFrame,
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

    # Wide and tall enough that the badge sits in a corner the bell does not
    # occupy. At 40x34 the badge landed on top of the centred bell and hid it.
    SIZE = (46, 38)
    BADGE_H = 16

    def __init__(self, parent=None):
        super().__init__('🔔', parent, objectName='Bell')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(*self.SIZE)
        self.setFlat(True)
        self._unread = 0
        self.setToolTip(t('Notifications'))
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
        width = 22 if len(label) > 1 else self.BADGE_H
        # Hard into the top corner, clear of the glyph in the middle.
        x, y = self.width() - width, 0
        painter.drawEllipse(x, y, width, self.BADGE_H)
        painter.setPen(QColor('white'))
        font = painter.font()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(x, y, width, self.BADGE_H, Qt.AlignCenter, label)
        painter.end()


class NotificationsPanel(QDialog):
    """The list itself, opened from the bell."""

    read_changed = Signal()

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        # Unread is the working list: reading something takes it off the list,
        # so what remains is what still wants attention. Earlier ones are kept
        # rather than deleted -- "I have dealt with it" and "it never happened"
        # are different things, and the second is not ours to decide.
        self.unread_only = True
        self.setWindowTitle(t('Notifications'))
        self.setMinimumSize(440, 500)

        self.tab_unread = QPushButton(t('Unread'), objectName='Segment')
        self.tab_all = QPushButton(t('Earlier'), objectName='Segment')
        for tab in (self.tab_unread, self.tab_all):
            tab.setCheckable(True)
        self.tab_unread.setChecked(True)
        tabs = QButtonGroup(self)
        tabs.setExclusive(True)
        tabs.addButton(self.tab_unread)
        tabs.addButton(self.tab_all)
        self.tab_unread.toggled.connect(self._on_tab)
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        tab_row.addWidget(self.tab_unread)
        tab_row.addWidget(self.tab_all)
        tab_row.addStretch()

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
        layout.setSpacing(10)
        layout.addWidget(QLabel(t('Notifications'), objectName='LoginTitle'))
        layout.addLayout(tab_row)
        layout.addWidget(self.status)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

        self.load()

    def _on_tab(self, *_):
        self.unread_only = self.tab_unread.isChecked()
        # Nothing to mark when looking at what is already read.
        self.mark_btn.setVisible(self.unread_only)
        self.load()

    def load(self):
        params = {'unread': 'true'} if self.unread_only else None
        self.api.get('notifications/', params, on_ok=self._show,
                     on_error=self._failed)

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
            self.status.setText(t('Nothing unread.') if self.unread_only
                                else t('Nothing yet.'))
            self.status.show()
            return
        self.status.hide()
        for row in rows:
            self.list_layout.insertWidget(self.list_layout.count() - 1,
                                          self._row(row))

    def _row(self, row):
        unread = not row.get('read_at')
        card = QFrame(objectName='NotificationCard')
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

        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(title)
        text.addWidget(body)
        text.addWidget(when)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 8, 10)
        layout.addLayout(text, 1)
        if unread:
            # One per row rather than only Mark all: the office reads three of
            # these and wants the fourth left standing.
            done = QPushButton('✓', objectName='SmallGhost')
            done.setToolTip(t('Mark as read'))
            done.setFixedWidth(34)
            done.setCursor(Qt.PointingHandCursor)
            done.clicked.connect(lambda _=False, r=row, c=card: self._mark_one(r, c))
            layout.addWidget(done, 0, Qt.AlignTop)
        return card

    def _mark_one(self, row, card):
        """Mark this one read and take it off the list."""
        note_id = row.get('id')
        if note_id is None:
            return
        card.setEnabled(False)

        def done(_payload):
            self.read_changed.emit()
            if self.unread_only:
                # It no longer belongs on this list, so it goes now rather
                # than on the next reload.
                self.list_layout.removeWidget(card)
                card.deleteLater()
                self._show_empty_if_needed()
            else:
                self.load()

        def failed(_error):
            card.setEnabled(True)

        self.api.post('notifications/mark_read/', {'ids': [note_id]},
                      on_ok=done, on_error=failed)

    def _show_empty_if_needed(self):
        """The stretch is always there, so one child means the list is empty."""
        if self.list_layout.count() <= 1:
            self.status.setText(t('Nothing unread.') if self.unread_only
                                else t('Nothing yet.'))
            self.status.show()

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
