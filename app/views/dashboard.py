"""Dashboard — the office landing screen.

Stat tiles up top, then a breakdown of the workforce by role and a live list of
who is online. Areas without a backend yet (stock, orders) render as muted
"not set up" tiles rather than a confident zero, so the screen never overstates
what the system knows.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.theme import ACCENT, INK_MUTED

REFRESH_MS = 30_000  # presence goes stale after 5 min; refresh well inside that.


class StatTile(QFrame):
    """A single headline number with a caption. Optionally clickable."""

    clicked = Signal()

    def __init__(self, caption, accent=False, clickable=False):
        super().__init__()
        self.setObjectName('StatTile')
        self.setProperty('accent', accent)
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

        self.value = QLabel('—', objectName='StatValue')
        self.caption = QLabel(caption, objectName='StatCaption')
        self.sub = QLabel('', objectName='StatSub')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(2)
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        layout.addWidget(self.sub)

    def mousePressEvent(self, event):
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set(self, value, sub='', alert=False):
        self.value.setText(str(value))
        self.sub.setText(sub)
        self.sub.setStyleSheet('color:#B3261E; font-weight:600;' if alert else '')
        self.value.setProperty('muted', False)
        self._repolish()

    def set_unavailable(self):
        self.value.setText('—')
        self.sub.setText(t('Not set up yet'))
        self.value.setProperty('muted', True)
        self._repolish()

    def set_caption(self, caption):
        self.caption.setText(caption)

    def _repolish(self):
        self.value.style().unpolish(self.value)
        self.value.style().polish(self.value)


class OnlineList(QFrame):
    """Live who's-online panel."""

    def __init__(self):
        super().__init__()
        self.setObjectName('Panel')
        self.heading = QLabel(t('Online now'), objectName='PanelHeading')
        self.rows = QVBoxLayout()
        self.rows.setSpacing(0)
        self.empty = QLabel(t('No one is online.'), objectName='Muted')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.heading)
        layout.addLayout(self.rows)
        layout.addWidget(self.empty)
        layout.addStretch()

    def set_users(self, users):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.empty.setVisible(not users)
        for user in users:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 6, 0, 6)
            line.setSpacing(8)

            dot = QLabel('●', objectName='OnlineDot')
            name = QLabel(user.get('full_name') or '—')
            name.setFont(_bold())
            role = QLabel(t(user.get('role_display') or ''), objectName='Muted')

            line.addWidget(dot)
            line.addWidget(name)
            line.addStretch()
            line.addWidget(role)
            self.rows.addWidget(row)

    def retranslate(self):
        self.heading.setText(t('Online now'))
        self.empty.setText(t('No one is online.'))


class RoleBreakdown(QFrame):
    """Active workers by role."""

    def __init__(self):
        super().__init__()
        self.setObjectName('Panel')
        self.heading = QLabel(t('Workforce'), objectName='PanelHeading')
        self.rows = QVBoxLayout()
        self.rows.setSpacing(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(self.heading)
        layout.addLayout(self.rows)
        layout.addStretch()

    def set_roles(self, roles):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for entry in roles:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 7, 0, 7)
            label = QLabel(t(entry.get('label') or ''))
            count = QLabel(str(entry.get('count', 0)))
            count.setFont(_bold())
            line.addWidget(label)
            line.addStretch()
            line.addWidget(count)
            self.rows.addWidget(row)

    def retranslate(self):
        self.heading.setText(t('Workforce'))


def _bold():
    font = QFont()
    font.setBold(True)
    return font


class DashboardView(QWidget):
    navigate = Signal(str)   # emitted when a tile should jump to a section

    def __init__(self, api):
        super().__init__()
        self.api = api
        self.setObjectName('Canvas')
        self._build()

        # Presence is only meaningful if kept fresh; poll on a timer.
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.reload)

    def _build(self):
        self.title = QLabel(t('Dashboard'), objectName='PageTitle')

        self.tile_workers = StatTile(t('Workers'))
        self.tile_online = StatTile(t('Online now'), accent=True)
        self.tile_clients = StatTile(t('Clients'))
        self.tile_profiles = StatTile(t('Catalog profiles'))
        self.tile_stock = StatTile(t('Stock'), clickable=True)
        self.tile_stock.clicked.connect(lambda: self.navigate.emit('stock'))
        self.tile_orders = StatTile(t('Orders'))

        self.tiles = [
            self.tile_workers, self.tile_online, self.tile_clients,
            self.tile_profiles, self.tile_stock, self.tile_orders,
        ]
        grid = QGridLayout()
        grid.setSpacing(14)
        for index, tile in enumerate(self.tiles):
            grid.addWidget(tile, 0, index)
            grid.setColumnStretch(index, 1)

        self.workforce = RoleBreakdown()
        self.online = OnlineList()
        panels = QHBoxLayout()
        panels.setSpacing(14)
        panels.addWidget(self.workforce, 1)
        panels.addWidget(self.online, 1)

        inner = QWidget(objectName='Canvas')
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        layout.addWidget(self.title)
        layout.addLayout(grid)
        layout.addLayout(panels)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # -- lifecycle --------------------------------------------------------

    def start(self):
        self.reload()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    # -- data -------------------------------------------------------------

    def reload(self):
        self.api.get('dashboard/', on_ok=self._on_stats, on_error=lambda _e: None)
        self.api.get('dashboard/online/', on_ok=self._on_online, on_error=lambda _e: None)

    def _on_stats(self, data):
        workers = data.get('workers', {})
        if workers.get('available'):
            self.tile_workers.set(workers.get('total', 0),
                                  t('%d active') % workers.get('active', 0))
            pending = workers.get('pending_password', 0)
            self.tile_online.set(
                workers.get('online', 0),
                t('%d awaiting password') % pending if pending else '',
            )
            self.workforce.set_roles(workers.get('by_role', []))

        clients = data.get('clients', {})
        if clients.get('available'):
            self.tile_clients.set(clients.get('total', 0),
                                  t('%d active') % clients.get('active', 0))

        catalog = data.get('catalog', {})
        if catalog.get('available'):
            self.tile_profiles.set(catalog.get('profiles', 0),
                                   t('%d series') % catalog.get('series', 0))

        stock = data.get('stock', {})
        if stock.get('available'):
            alerts = stock.get('alerts', 0)
            if alerts:
                self.tile_stock.set(stock.get('items', 0),
                                    t('%d need reorder') % alerts, alert=True)
            else:
                self.tile_stock.set(
                    stock.get('items', 0),
                    t('%d warehouses') % stock.get('warehouses', 0))
        else:
            self.tile_stock.set_unavailable()

        orders = data.get('orders', {})
        if orders.get('available'):
            self.tile_orders.set(orders.get('total', 0))
        else:
            self.tile_orders.set_unavailable()

    def _on_online(self, users):
        self.online.set_users(users or [])

    # -- i18n -------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Dashboard'))
        self.tile_workers.set_caption(t('Workers'))
        self.tile_online.set_caption(t('Online now'))
        self.tile_clients.set_caption(t('Clients'))
        self.tile_profiles.set_caption(t('Catalog profiles'))
        self.tile_stock.set_caption(t('Stock'))
        self.tile_orders.set_caption(t('Orders'))
        self.workforce.retranslate()
        self.online.retranslate()
        self.reload()
