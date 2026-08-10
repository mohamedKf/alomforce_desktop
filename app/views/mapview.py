"""Map screen — the shop, the warehouses and every located client on one map.

Read-only: it plots what /api/map/ returns. Placing a client happens in the
client editor; this is the overview.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.i18n import t
from app.views.mapwidget import MapWidget


def _dot(color):
    return (f'<span style="color:{color};font-size:16px;">●</span>')


class MapView(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self._loaded = False
        self.setObjectName('Canvas')
        self._build()

    def _build(self):
        self.title = QLabel(t('Map'), objectName='PageTitle')
        self.refresh_btn = QPushButton(t('Refresh'), objectName='Ghost')
        self.refresh_btn.clicked.connect(self.reload)

        legend = QLabel(
            f'{_dot("#d1495b")} {t("Shop")}   '
            f'{_dot("#e08e2b")} {t("Warehouse")}   '
            f'{_dot("#2f6fb0")} {t("Client")}',
            objectName='Muted',
        )
        legend.setTextFormat(Qt.RichText)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(16)
        header.addWidget(legend)
        header.addStretch()
        header.addWidget(self.refresh_btn)

        self.map = MapWidget(token=self.api.mapbox_token)
        self.status = QLabel('', objectName='Muted')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self.status)
        layout.addWidget(self.map, 1)

    def start(self):
        """Called when the section is shown; load once."""
        if not self._loaded:
            self._loaded = True
            self.reload()

    def reload(self):
        self.status.setText(t('Loading…'))
        self.status.show()
        self.api.get('map/', on_ok=self._on_data, on_error=self._on_error)

    def _on_data(self, data):
        markers = []
        shop = data.get('shop') or {}
        if shop.get('latitude') is not None and shop.get('longitude') is not None:
            markers.append({
                'lat': float(shop['latitude']), 'lng': float(shop['longitude']),
                'type': 'shop',
                'label': f"<b>{shop.get('name', '')}</b><br>{shop.get('address', '')}",
            })
        for w in data.get('warehouses', []):
            markers.append({
                'lat': float(w['latitude']), 'lng': float(w['longitude']),
                'type': 'warehouse',
                'label': f"<b>{w.get('name', '')}</b><br>{w.get('city', '')}",
            })
        for c in data.get('clients', []):
            markers.append({
                'lat': float(c['latitude']), 'lng': float(c['longitude']),
                'type': 'client',
                'label': f"<b>{c.get('name', '')}</b><br>{c.get('city', '')}"
                         f"<br>{c.get('phone', '')}",
            })
        self.map.set_markers(markers)
        n = len(data.get('clients', []))
        if markers:
            self.status.hide()
        else:
            self.status.setText(t('Nothing placed on the map yet.'))
        self.count = n

    def _on_error(self, error):
        self.status.setText(error.message)
        self.status.show()

    def retranslate(self):
        self.title.setText(t('Map'))
        self.refresh_btn.setText(t('Refresh'))
