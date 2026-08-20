"""The signed-in application shell: sidebar navigation and the page stack.

Which sections appear depends on the signed-in role. A warehouse worker has no
business opening the invoice screen, and hiding it is clearer than showing a
button that returns 403.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.views.catalog import CatalogView
from app.views.clients import ClientsView
from app.views.dashboard import DashboardView
from app.views.mapview import MapView
from app.views.invoices import InvoicesView
from app.views.orders import OrdersView
from app.views.requests import RequestsView
from app.views.salary import SalaryView
from app.views.settings import SettingsView
from app.views.stock import StockView
from app.views.users import UsersView
from app.views.warehouses import WarehousesView

# section key, label, roles allowed to see it
SECTIONS = [
    ('dashboard', 'Dashboard', {'manager', 'office'}),
    ('catalog', 'Catalog', {'manager', 'office', 'warehouse', 'driver', 'client'}),
    ('stock', 'Stock', {'manager', 'office', 'warehouse'}),
    ('warehouses', 'Warehouses', {'manager', 'office'}),
    ('orders', 'Orders', {'manager', 'office'}),
    ('clients', 'Clients', {'manager', 'office'}),
    ('map', 'Map', {'manager', 'office'}),
    ('invoices', 'Invoices', {'manager', 'office'}),
    ('deliveries', 'Deliveries', {'manager', 'office', 'driver'}),
    ('users', 'Users', {'manager'}),
    ('salary', 'Salary', {'manager', 'office'}),
    ('requests', 'Requests', {'manager', 'office'}),
    ('settings', 'Settings', {'manager', 'office'}),
]


class PlaceholderView(QWidget):
    """A section that exists in navigation but is not built yet.

    Better than omitting it: it shows what is coming without pretending the
    feature works.
    """

    def __init__(self, label):
        super().__init__()
        self.setObjectName('Canvas')
        self.label = label

        self.title = QLabel(t(label), objectName='PageTitle')
        self.body = QLabel(t('This section is not built yet.'), objectName='Muted')
        badge = QLabel(t('Coming soon'), objectName='Muted')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addWidget(badge)
        layout.addStretch()
        layout.addWidget(self.body, alignment=Qt.AlignCenter)
        layout.addStretch()

    def retranslate(self):
        self.title.setText(t(self.label))
        self.body.setText(t('This section is not built yet.'))


class Shell(QWidget):
    signed_out = Signal()
    language_changed = Signal(str)

    def __init__(self, api, session):
        super().__init__()
        self.api = api
        self.session = session
        self.pages = {}
        self.buttons = {}
        self.setObjectName('Canvas')
        self._build()

    def _build(self):
        self.sidebar = QWidget(objectName='Sidebar')
        self.sidebar.setFixedWidth(216)

        brand = QLabel('AlomForce', objectName='Brand')
        self.brand_sub = QLabel(t('Aluminium profiles'), objectName='BrandSub')

        self.nav_layout = QVBoxLayout()
        self.nav_layout.setSpacing(0)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        # Top of the sidebar, beside the wordmark. It used to sit at the very
        # bottom next to the sign-out button, which is the last place anyone
        # looks and the easiest to miss -- a badge is only useful where the eye
        # already goes.
        from app.views.notifications import BellButton, NotificationWatcher
        self.bell = BellButton()
        self.bell.opened.connect(self._open_notifications)
        self._watcher = NotificationWatcher(self.api, self.bell)

        self.user_name = QLabel('', objectName='UserName')
        self.user_role = QLabel('', objectName='UserRole')
        self.sign_out = QPushButton(t('Sign out'), objectName='SignOut')
        self.sign_out.clicked.connect(self.signed_out.emit)

        # The wordmark and the bell share the top row; the brand labels carry
        # their own padding, so the bell is nudged to sit on the wordmark line.
        wordmark = QVBoxLayout()
        wordmark.setSpacing(0)
        wordmark.addWidget(brand)
        wordmark.addWidget(self.brand_sub)
        masthead = QHBoxLayout()
        # Symmetric: a layout reverses widget order in RTL but keeps its
        # margins on the same physical sides, so a one-sided margin would put
        # the bell flush against the window edge in Hebrew. The wordmark keeps
        # its own padding, so this only affects the bell.
        masthead.setContentsMargins(14, 18, 14, 0)
        masthead.addLayout(wordmark, 1)
        masthead.addWidget(self.bell, alignment=Qt.AlignTop)

        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(0, 0, 0, 16)
        side.setSpacing(0)
        side.addLayout(masthead)
        side.addLayout(self.nav_layout)
        side.addStretch()
        side.addSpacing(10)
        identity = QHBoxLayout()
        identity.setContentsMargins(20, 0, 14, 0)
        names = QVBoxLayout()
        names.setSpacing(0)
        for widget in (self.user_name, self.user_role):
            names.addWidget(widget)
        identity.addLayout(names, 1)
        side.addLayout(identity)
        side.addSpacing(10)
        wrap = QHBoxLayout()
        wrap.setContentsMargins(14, 0, 14, 0)
        wrap.addWidget(self.sign_out)
        side.addLayout(wrap)

        self.stack = QStackedWidget()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)

    def _open_notifications(self):
        from app.views.notifications import NotificationsPanel

        panel = NotificationsPanel(self.api, self)
        panel.read_changed.connect(self._watcher.refresh)
        panel.exec()
        # Opening the list is not the same as reading it, so the badge is
        # refreshed rather than assumed to be zero.
        self._watcher.refresh()

    # -- session ---------------------------------------------------------

    def apply_session(self):
        """Rebuild navigation for the signed-in user's role."""
        self._clear_nav()

        role = self.session.role
        self.user_name.setText(self.session.full_name)
        self.user_role.setText((self.session.user or {}).get('role_display', ''))

        for key, label, roles in SECTIONS:
            if role not in roles:
                continue
            page = self._make_page(key, label)
            self.pages[key] = page
            self.stack.addWidget(page)

            button = QPushButton(t(label), objectName='NavButton')
            button.setCheckable(True)
            button.clicked.connect(lambda _, k=key: self._show(k))
            self.nav_group.addButton(button)
            self.nav_layout.addWidget(button)
            self.buttons[key] = button

        first = next(iter(self.pages), None)
        if first:
            self.buttons[first].setChecked(True)
            self._show(first)

    def _make_page(self, key, label):
        if key == 'dashboard':
            view = DashboardView(self.api)
            view.navigate.connect(self._navigate_to)
            return view
        if key == 'catalog':
            view = CatalogView(self.api, self.session)
            view.load_filter_options()
            view.reload()
            return view
        if key == 'stock':
            view = StockView(self.api)
            view.load_filter_options()
            view.reload()
            return view
        if key == 'warehouses':
            view = WarehousesView(self.api)
            view.reload()
            return view
        if key == 'orders':
            view = OrdersView(self.api, self.session)
            view.reload()
            return view
        if key == 'users':
            view = UsersView(self.api)
            view.reload()
            return view
        if key == 'clients':
            view = ClientsView(self.api)
            view.reload()
            return view
        if key == 'map':
            return MapView(self.api)
        if key == 'invoices':
            return InvoicesView(self.api, self.session)
        if key == 'requests':
            return RequestsView(self.api, self.session)
        if key == 'salary':
            return SalaryView(self.api, self.session)
        if key == 'settings':
            view = SettingsView(self.api, self.session)
            view.language_changed.connect(self.language_changed)
            return view
        return PlaceholderView(label)

    def _navigate_to(self, key):
        """Jump to a section from elsewhere (e.g. a dashboard tile)."""
        if key in self.buttons:
            self.buttons[key].setChecked(True)
            self._show(key)

    def _show(self, key):
        page = self.pages.get(key)
        if not page:
            return
        current = self.stack.currentWidget()
        if current is not page and hasattr(current, 'stop'):
            current.stop()
        self.stack.setCurrentWidget(page)
        if hasattr(page, 'start'):
            page.start()

    def _clear_nav(self):
        for button in list(self.buttons.values()):
            self.nav_group.removeButton(button)
            self.nav_layout.removeWidget(button)
            button.deleteLater()
        self.buttons.clear()

        for page in list(self.pages.values()):
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages.clear()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.sign_out.setText(t('Sign out'))
        for key, label, _roles in SECTIONS:
            if key in self.buttons:
                self.buttons[key].setText(t(label))
        for page in self.pages.values():
            if hasattr(page, 'retranslate'):
                page.retranslate()
