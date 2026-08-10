"""A Leaflet/OpenStreetMap map embedded with QtWebEngine.

Two jobs, one widget:
  - display mode  -- plot the shop, warehouses and clients as coloured pins;
  - pick mode     -- show one draggable pin and report where it lands, so the
                     client dialog can place a business by dragging.

JavaScript talks back to Python over a QWebChannel `bridge`; Python drives the
map with runJavaScript. Calls made before the page finishes loading are queued.
"""

import json

from PySide6.QtCore import QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

# Israel-ish default view, used until we have a real point to centre on.
DEFAULT_CENTER = (31.7, 35.0)
DEFAULT_ZOOM = 8

# Mapbox raster tiles (via the Styles API) when a token is set, else OSM.
_OSM_TILES = (
    "L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',"
    "{maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);"
)
_MAPBOX_TILES = (
    "L.tileLayer('https://api.mapbox.com/styles/v1/mapbox/streets-v12/tiles/512/"
    "{{z}}/{{x}}/{{y}}@2x?access_token={token}',"
    "{{tileSize:512, zoomOffset:-1, maxZoom:19,"
    " attribution:'© Mapbox © OpenStreetMap'}}).addTo(map);"
)

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>html,body,#map{height:100%;margin:0;background:#e9edf0}
.lbl{font:13px -apple-system,sans-serif}</style>
</head><body><div id="map"></div>
<script>
var map, pins, pick=null, pickMode=false;
function init(){
  map = L.map('map').setView([__CLAT__,__CLNG__], __CZOOM__);
  __TILELAYER__
  pins = L.layerGroup().addTo(map);
  map.on('click', function(e){ if(pickMode) place(e.latlng.lat, e.latlng.lng, true); });
  new QWebChannel(qt.webChannelTransport, function(ch){ window.bridge = ch.objects.bridge; });
}
var COLORS = {shop:'#d1495b', warehouse:'#e08e2b', client:'#2f6fb0'};
function setMarkers(list){
  pins.clearLayers();
  var b = [];
  list.forEach(function(m){
    var c = L.circleMarker([m.lat,m.lng],
      {radius:m.type=='shop'?10:8, color:'#fff', weight:2,
       fillColor:COLORS[m.type]||'#2f6fb0', fillOpacity:1});
    if(m.label) c.bindPopup('<div class="lbl">'+m.label+'</div>');
    pins.addLayer(c); b.push([m.lat,m.lng]);
  });
  if(b.length==1) map.setView(b[0], 14);
  else if(b.length>1) map.fitBounds(b, {padding:[40,40]});
}
function place(lat,lng,fromClick){
  if(pick){ pick.setLatLng([lat,lng]); }
  else {
    pick = L.marker([lat,lng],{draggable:true}).addTo(map);
    pick.on('dragend', function(e){ var p=e.target.getLatLng(); if(window.bridge) bridge.onPick(p.lat,p.lng); });
  }
  if(fromClick && window.bridge) bridge.onPick(lat,lng);
}
function enablePick(lat,lng){ pickMode=true; place(lat,lng,false); map.setView([lat,lng],15); }
function setView(lat,lng,z){ map.setView([lat,lng], z); }
window.onload = init;
</script></body></html>"""


class _Bridge(QObject):
    picked = Signal(float, float)

    @Slot(float, float)
    def onPick(self, lat, lng):
        self.picked.emit(lat, lng)


class MapWidget(QWebEngineView):
    """Leaflet map. Emits `picked(lat, lng)` while in pick mode."""

    picked = Signal(float, float)

    def __init__(self, token='', parent=None):
        super().__init__(parent)
        self._bridge = _Bridge()
        self._bridge.picked.connect(self.picked)
        self._channel = QWebChannel()
        self._channel.registerObject('bridge', self._bridge)
        self.page().setWebChannel(self._channel)

        self._ready = False
        self._queue = []
        self.loadFinished.connect(self._on_loaded)

        tiles = _MAPBOX_TILES.format(token=token) if token else _OSM_TILES
        html = (_HTML
                .replace('__TILELAYER__', tiles)
                .replace('__CLAT__', str(DEFAULT_CENTER[0]))
                .replace('__CLNG__', str(DEFAULT_CENTER[1]))
                .replace('__CZOOM__', str(DEFAULT_ZOOM)))
        self.setHtml(html, QUrl('https://alomforce.local/'))

    # -- python -> map ---------------------------------------------------

    def _run(self, js):
        if self._ready:
            self.page().runJavaScript(js)
        else:
            self._queue.append(js)

    def _on_loaded(self, ok):
        self._ready = True
        for js in self._queue:
            self.page().runJavaScript(js)
        self._queue = []

    def set_markers(self, markers):
        """markers: list of {lat, lng, type, label}."""
        self._run('setMarkers(%s)' % json.dumps(markers))

    def center(self, lat, lng, zoom=14):
        self._run('setView(%f, %f, %d)' % (float(lat), float(lng), zoom))

    def enable_pick(self, lat, lng):
        """Show a draggable pin at (lat, lng) and report where it moves."""
        self._run('enablePick(%f, %f)' % (float(lat), float(lng)))
