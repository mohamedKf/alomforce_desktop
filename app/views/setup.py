"""Setup — is this installation actually finished?

Most of what is wrong with a fresh deployment is not an error. It is a blank
field, and the thing it powers simply never happens: no mail server and the
accountant's monthly package is never sent, no image storage and every photo
the drivers take is written to a disk the next deploy throws away. Nothing
raises and nobody is told, so it surfaces weeks later as "we never got the
invoices".

This page says it out loud. The server (GET /api/setup/) does the judging and
sends the list worst-first, with what is missing, what stops working because of
it, and where to fix it; this only renders that, in the order given, and offers
to jump to the screen that fixes each one.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

# `where` names a place, not a URL: the server has no idea what this client's
# navigation looks like. Mapped here to the shell's own sections.
WHERE_SECTIONS = {
    'settings': ('settings', 'Settings'),
    'catalog': ('catalog', 'Catalog'),
    'users': ('users', 'Users'),
}

TICK = '✓'
WARNING = '⚠'


class SetupView(QWidget):
    """The readiness checklist. Office and managers only (the shell gates it)."""

    navigate = Signal(str)   # a section key, when a row offers to go and fix it

    def __init__(self, api, session, can_open=None):
        super().__init__()
        self.api = api
        self.session = session
        # Asked of the shell rather than assumed: an office user has no Users
        # page, and a button that leads nowhere is worse than a sentence.
        self._can_open = can_open or (lambda key: False)
        self.setObjectName('Canvas')
        self._build()

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel(t('Setup'), objectName='PageTitle')
        self.subtitle = QLabel(t('What still has to be set before this is a '
                                 'working installation.'), objectName='Muted')
        self.refresh_btn = QPushButton(t('Refresh'), objectName='Ghost')
        self.refresh_btn.clicked.connect(self.reload)

        heading = QHBoxLayout()
        heading.setSpacing(12)
        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(self.title)
        words.addWidget(self.subtitle)
        heading.addLayout(words, 1)
        heading.addWidget(self.refresh_btn, 0, Qt.AlignTop)

        # -- headline state --
        self.state = QLabel(t('Loading…'), objectName='SetupState')
        self.state.setWordWrap(True)
        self.counts = QLabel('', objectName='SetupCounts')
        self.counts.setWordWrap(True)
        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        headline = QFrame(objectName='Panel')
        head_box = QVBoxLayout(headline)
        head_box.setContentsMargins(18, 16, 18, 16)
        head_box.setSpacing(4)
        head_box.addWidget(self.state)
        head_box.addWidget(self.counts)
        head_box.addWidget(self.error)

        # -- the checks --
        self.items_box = QVBoxLayout()
        self.items_box.setContentsMargins(0, 0, 0, 0)
        self.items_box.setSpacing(0)
        items_panel = QFrame(objectName='Panel')
        items_wrap = QVBoxLayout(items_panel)
        items_wrap.setContentsMargins(18, 6, 18, 6)
        items_wrap.setSpacing(0)
        items_wrap.addLayout(self.items_box)

        # -- catalogues --
        self.cat_heading = QLabel(t('Catalogues'), objectName='PanelHeading')
        self.cat_box = QVBoxLayout()
        self.cat_box.setSpacing(0)
        self.cat_empty = QLabel(t('No catalogues are loaded.'), objectName='Muted')
        cat_panel = QFrame(objectName='Panel')
        cat_wrap = QVBoxLayout(cat_panel)
        cat_wrap.setContentsMargins(18, 16, 18, 16)
        cat_wrap.setSpacing(8)
        cat_wrap.addWidget(self.cat_heading)
        cat_wrap.addLayout(self.cat_box)
        cat_wrap.addWidget(self.cat_empty)

        inner = QWidget(objectName='Canvas')
        body = QVBoxLayout(inner)
        body.setContentsMargins(28, 24, 28, 24)
        body.setSpacing(16)
        body.addLayout(heading)
        body.addWidget(headline)
        body.addWidget(items_panel)
        body.addWidget(cat_panel)
        body.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # -- lifecycle -------------------------------------------------------

    def start(self):
        self.reload()

    # -- data ------------------------------------------------------------

    def reload(self):
        self.refresh_btn.setEnabled(False)
        self.api.get('setup/', on_ok=self._on_setup, on_error=self._on_error)

    def _on_setup(self, data):
        self.refresh_btn.setEnabled(True)
        self.error.setVisible(False)
        data = data if isinstance(data, dict) else {}
        self._render_state(data)
        self._render_items(data.get('items') or [])
        self._render_catalogues(data.get('catalogues') or [])

    def _on_error(self, error):
        self.refresh_btn.setEnabled(True)
        self.state.setText(t('The check could not be run.'))
        self.state.setProperty('state', 'pending')
        _repolish(self.state)
        self.counts.setText('')
        self.error.setText(error.message)
        self.error.setVisible(True)

    def _render_state(self, data):
        blocking = int(data.get('blocking') or 0)
        if data.get('ready'):
            self.state.setText(t('Ready to hand over'))
            self.state.setProperty('state', 'ready')
        elif blocking == 1:
            self.state.setText(t('One thing still to set up'))
            self.state.setProperty('state', 'pending')
        else:
            self.state.setText(
                t('{count} things still to set up').format(count=blocking))
            self.state.setProperty('state', 'pending')
        _repolish(self.state)

        parts = []
        for key, phrase in (('blocking', '{count} blocking'),
                            ('advised', '{count} advised'),
                            ('optional', '{count} optional')):
            count = int(data.get(key) or 0)
            if count:
                parts.append(t(phrase).format(count=count))
        self.counts.setText(' · '.join(parts) if parts
                            else t('Everything on the list is set.'))

    def _render_items(self, items):
        _clear(self.items_box)
        for index, item in enumerate(items):
            row = self._item_row(item)
            row.setProperty('last', index == len(items) - 1)
            self.items_box.addWidget(row)

    def _item_row(self, item):
        ok = bool(item.get('ok'))
        level = item.get('level') or 'optional'

        row = QFrame(objectName='SetupRow')
        mark = QLabel(TICK if ok else WARNING, objectName='SetupMark')
        # 'ok' is a level of its own here, so a passed check is green whatever
        # it would have cost had it failed.
        mark.setProperty('level', 'ok' if ok else level)
        mark.setFixedWidth(18)

        # The label, detail and consequence are written by the server and come
        # back in the language this client asked for, so they are shown as sent;
        # t() only covers the case of an older server answering in English.
        words = QVBoxLayout()
        words.setSpacing(2)
        words.addWidget(QLabel(t(item.get('label') or ''), objectName='SetupItem'))
        for text in (item.get('detail'), item.get('consequence')):
            if not text:
                continue
            line = QLabel(t(text), objectName='SetupDetail')
            line.setWordWrap(True)
            words.addWidget(line)

        top = QHBoxLayout(row)
        top.setContentsMargins(0, 11, 0, 11)
        top.setSpacing(10)
        top.addWidget(mark, 0, Qt.AlignTop)
        top.addLayout(words, 1)
        fix = self._fix_widget(item) if not ok else None
        if fix is not None:
            top.addWidget(fix, 0, Qt.AlignTop)
        return row

    def _fix_widget(self, item):
        """Where to go and fix this: a button when the shell has that page,
        otherwise the name of the place in words."""
        section = WHERE_SECTIONS.get(item.get('where'))
        if not section:
            # 'environment' and anything a future server adds: not a screen in
            # this app at all, so say where it does live.
            return QLabel(t('Set in the server environment.'),
                          objectName='SetupDetail')
        key, label = section
        if self._can_open(key):
            button = QPushButton(t('Go to {place}').format(place=t(label)),
                                 objectName='SmallGhost')
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.navigate.emit(k))
            return button
        return QLabel(t('Fix it in {place}.').format(place=t(label)),
                      objectName='SetupDetail')

    def _render_catalogues(self, catalogues):
        _clear(self.cat_box)
        self.cat_empty.setVisible(not catalogues)
        for entry in catalogues:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 5, 0, 5)
            line.setSpacing(8)
            line.addWidget(QLabel(entry.get('name') or entry.get('slug') or '—',
                                  objectName='SetupCatalogue'))
            line.addStretch()
            count = int(entry.get('profiles') or 0)
            line.addWidget(QLabel(
                t('{count} profiles').format(count=f'{count:,}'),
                objectName='SetupDetail'))
            self.cat_box.addWidget(row)

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Setup'))
        self.subtitle.setText(t('What still has to be set before this is a '
                                'working installation.'))
        self.refresh_btn.setText(t('Refresh'))
        self.cat_heading.setText(t('Catalogues'))
        self.cat_empty.setText(t('No catalogues are loaded.'))
        # Every row is the server's own wording, in the language it was asked
        # for; re-fetching is what translates them, not relabelling here.
        self.reload()


def _clear(layout):
    """Empty a layout, and take the widgets off the screen now.

    deleteLater() alone is not enough: until the event loop gets round to it
    the widget is still a child of the page and still paints where it last
    sat, so a refresh leaves the old row's tick floating beside the new one.
    Unparenting first removes it from the screen immediately; deleteLater
    still frees it.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())
            item.layout().deleteLater()


def _repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
