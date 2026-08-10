"""API client for the AlomForce backend.

Every call runs on a worker thread. Qt repaints on the main thread only, so a
blocking request would freeze the window -- and on a warehouse network a slow
request is the normal case, not the exception. Callers get results back through
signals.

    api.get('catalog/listings/', {'series': '7000'},
            on_ok=self.populate, on_error=self.show_error)
"""

import json
import os
import threading
from urllib.parse import urlencode

import requests
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

DEFAULT_BASE_URL = 'http://127.0.0.1:8000/api/'
TIMEOUT = 20


class ApiError(Exception):
    """A request that failed, with a message worth showing a user."""

    def __init__(self, message, status=None, payload=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.payload = payload or {}


class _Signals(QObject):
    ok = Signal(object)
    error = Signal(object)


class _Call(QRunnable):
    """One HTTP request, executed on the thread pool."""

    def __init__(self, client, method, path, params=None, data=None, auth=True):
        super().__init__()
        self.client = client
        self.method = method
        self.path = path
        self.params = params
        self.data = data
        self.auth = auth
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.ok.emit(self.client.request_sync(
                self.method, self.path, self.params, self.data, self.auth
            ))
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:                      # noqa: BLE001
            self.signals.error.emit(ApiError(str(exc)))


class _UploadCall(QRunnable):
    """A multipart file upload, executed on the thread pool."""

    def __init__(self, client, path, file_path, field='image', method='POST'):
        super().__init__()
        self.client = client
        self.path = path
        self.file_path = file_path
        self.field = field
        self.method = method
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.ok.emit(
                self.client.upload_sync(self.path, self.file_path, self.field,
                                        method=self.method)
            )
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:                      # noqa: BLE001
            self.signals.error.emit(ApiError(str(exc)))


class _GeocodeCall(QRunnable):
    """Resolve an address to coordinates, off the UI thread.

    Mapbox when a token is set (better for Israeli addresses), else the free OSM
    Nominatim service as a fallback.
    """

    def __init__(self, http, query, token=''):
        super().__init__()
        self.http = http
        self.query = query
        self.token = token
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.ok.emit(
                self._mapbox() if self.token else self._nominatim())
        except Exception as exc:                      # noqa: BLE001
            self.signals.error.emit(ApiError(str(exc)))

    def _mapbox(self):
        from urllib.parse import quote
        resp = self.http.get(
            f'https://api.mapbox.com/geocoding/v5/mapbox.places/'
            f'{quote(self.query)}.json',
            params={'access_token': self.token, 'limit': 1,
                    'country': 'il', 'language': 'he'},
            timeout=TIMEOUT,
        )
        feats = resp.json().get('features', []) if resp.ok else []
        if not feats:
            return None
        lng, lat = feats[0]['center']
        return {'lat': float(lat), 'lng': float(lng),
                'display_name': feats[0].get('place_name', '')}

    def _nominatim(self):
        resp = self.http.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': self.query, 'format': 'json', 'limit': 1,
                    'countrycodes': 'il', 'accept-language': 'he'},
            headers={'User-Agent': 'AlomForce-Desktop/1.0'},
            timeout=TIMEOUT,
        )
        data = resp.json() if resp.ok else []
        if not data:
            return None
        return {'lat': float(data[0]['lat']), 'lng': float(data[0]['lon']),
                'display_name': data[0].get('display_name', '')}


class _BinaryCall(QRunnable):
    """A raw byte fetch (an image), executed on the thread pool."""

    def __init__(self, client, url):
        super().__init__()
        self.client = client
        self.url = url
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.ok.emit(self.client.fetch_binary_sync(self.url))
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:                      # noqa: BLE001
            self.signals.error.emit(ApiError(str(exc)))


class _PdfCall(QRunnable):
    """Download an authenticated PDF to a temp file, off the UI thread."""

    def __init__(self, client, path, filename):
        super().__init__()
        self.client = client
        self.path = path
        self.filename = filename
        self.signals = _Signals()

    @Slot()
    def run(self):
        try:
            self.signals.ok.emit(
                self.client.download_pdf_sync(self.path, self.filename))
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:                      # noqa: BLE001
            self.signals.error.emit(ApiError(str(exc)))


class _ProbeCall(QRunnable):
    """Check whether a server answers at a URL, off the UI thread.

    Never raises -- always emits `ok` with a result dict so the Settings page
    can show status without a try/except. A 401 counts as reachable (the server
    is there, just asking for auth), which is the normal state before sign-in.
    """

    def __init__(self, url, timeout=6):
        super().__init__()
        self.url = url
        self.timeout = timeout
        self.signals = _Signals()

    @Slot()
    def run(self):
        import time
        root = self.url.rstrip('/')
        if root.endswith('/api'):
            root = root[:-4]
        target = root + '/api/'
        started = time.perf_counter()
        try:
            r = requests.get(target, timeout=self.timeout)
            ms = int((time.perf_counter() - started) * 1000)
            self.signals.ok.emit({'ok': True, 'status': r.status_code,
                                  'ms': ms, 'url': target})
        except requests.Timeout:
            self.signals.ok.emit({'ok': False, 'reason': 'timeout',
                                  'url': target})
        except requests.RequestException:
            self.signals.ok.emit({'ok': False, 'reason': 'unreachable',
                                  'url': target})


class ApiClient(QObject):
    def __init__(self, session, base_url=DEFAULT_BASE_URL):
        super().__init__()
        self.session = session
        self.base_url = base_url.rstrip('/') + '/'
        self.server_error = None    # set if the base URL couldn't be reached
        self.pool = QThreadPool.globalInstance()
        self._http = requests.Session()
        # Client config from the backend (the Mapbox token). Loaded once at
        # sign-in via load_config(); empty until then, which the map treats as
        # "use OpenStreetMap".
        self.mapbox_token = ''
        # Serialises token refresh. When the access token expires, every page's
        # in-flight request hits 401 at once; without this each would fire its
        # own /auth/refresh/, and that storm of concurrent refreshes is what
        # was intermittently blanking the whole app. With the lock, the first
        # 401 refreshes and the rest reuse the new token.
        self._refresh_lock = threading.Lock()
        # Strong references to in-flight calls. A QRunnable deletes itself once
        # run() returns, which can collect the signal object before its queued
        # cross-thread signal reaches the main thread -- the callback then never
        # fires and the view sits on "Loading…" forever. Holding each call until
        # a result has been delivered is what prevents that.
        self._active = set()

    # -- async -----------------------------------------------------------

    def get(self, path, params=None, on_ok=None, on_error=None, auth=True):
        self._dispatch('GET', path, params=params, on_ok=on_ok,
                       on_error=on_error, auth=auth)

    def post(self, path, data=None, on_ok=None, on_error=None, auth=True):
        self._dispatch('POST', path, data=data, on_ok=on_ok,
                       on_error=on_error, auth=auth)

    def patch(self, path, data=None, on_ok=None, on_error=None, auth=True):
        self._dispatch('PATCH', path, data=data, on_ok=on_ok,
                       on_error=on_error, auth=auth)

    def upload(self, path, file_path, field='image', on_ok=None, on_error=None,
               method='POST'):
        """Send a file as multipart/form-data (e.g. a profile image or invoice).

        method defaults to POST (create); pass 'PATCH' to attach a file to an
        existing resource without touching its other fields.
        """
        self._start(_UploadCall(self, path, file_path, field, method),
                    on_ok, on_error)

    def delete(self, path, on_ok=None, on_error=None):
        """DELETE a resource (e.g. clear the company logo)."""
        self._dispatch('DELETE', path, on_ok=on_ok, on_error=on_error)

    def fetch_binary(self, url, on_ok=None, on_error=None):
        """GET raw bytes off the UI thread — used to load catalog thumbnails.

        The URL is public (local /media/ in development, a Cloudinary CDN later),
        so this carries no auth header.
        """
        self._start(_BinaryCall(self, url), on_ok, on_error)

    def geocode(self, query, on_ok=None, on_error=None):
        """Resolve an address to {lat, lng, display_name} (or None)."""
        self._start(_GeocodeCall(self._http, query, self.mapbox_token),
                    on_ok, on_error)

    def download_pdf(self, path, filename, on_ok=None, on_error=None):
        """Download an authenticated PDF to a temp file; on_ok gets the path."""
        self._start(_PdfCall(self, path, filename), on_ok, on_error)

    def load_config(self):
        """Fetch client config (Mapbox token) synchronously. Best-effort."""
        try:
            data = self.request_sync('GET', 'config/')
            self.mapbox_token = (data or {}).get('mapbox_token', '') or ''
        except ApiError:
            self.mapbox_token = ''

    def set_base_url(self, url):
        """Point the client at a different backend (applied to the next call)."""
        self.base_url = url.rstrip('/') + '/'

    @staticmethod
    def probe(url):
        """True if the server answers at url (a 401 still means it's there)."""
        root = url.rstrip('/')
        if root.endswith('/api'):
            root = root[:-4]
        try:
            r = requests.get(root + '/api/', timeout=8)
            return r.status_code > 0
        except requests.RequestException:
            return False

    def check_connection(self, url, on_result):
        """Probe `url` off the UI thread; on_result gets a status dict.

        Result: {'ok': True, 'status': int, 'ms': int, 'url': str} when the
        server answers, else {'ok': False, 'reason': 'timeout'|'unreachable'}.
        Used by Settings to test a server without saving or changing anything.
        """
        call = _ProbeCall(url)
        call.setAutoDelete(False)
        self._active.add(call)
        call.signals.ok.connect(on_result)
        call.signals.ok.connect(lambda *_: self._active.discard(call))
        self.pool.start(call)

    def _dispatch(self, method, path, params=None, data=None,
                  on_ok=None, on_error=None, auth=True):
        self._start(_Call(self, method, path, params, data, auth), on_ok, on_error)

    def _start(self, call, on_ok, on_error):
        # Qt must not free the runnable behind Python's back; this object's
        # lifetime is managed by self._active instead.
        call.setAutoDelete(False)

        if on_ok:
            call.signals.ok.connect(on_ok)
        if on_error:
            call.signals.error.connect(on_error)

        # Released only after a result has been handed to the callbacks above.
        # Connected last so it runs after them.
        self._active.add(call)
        call.signals.ok.connect(lambda *_: self._active.discard(call))
        call.signals.error.connect(lambda *_: self._active.discard(call))

        self.pool.start(call)

    # -- sync (runs on the worker thread) ---------------------------------

    def request_sync(self, method, path, params=None, data=None,
                     auth=True, _retry=True):
        url = self.base_url + path.lstrip('/')
        used_access = self.session.access
        headers = {'Accept': 'application/json'}
        if auth and used_access:
            headers['Authorization'] = f'Bearer {used_access}'

        try:
            response = self._http.request(
                method, url, params=params, json=data,
                headers=headers, timeout=TIMEOUT,
            )
        except requests.Timeout:
            raise ApiError('The server took too long to respond.')
        except requests.ConnectionError:
            raise ApiError(
                f'Cannot reach the server at {self.base_url}.\n'
                'Is the backend running?'
            )

        # An expired access token is the normal case for a long-running desktop
        # session, so refresh once and replay rather than bouncing the user to
        # the login screen mid-task.
        if response.status_code == 401 and auth and _retry and self.session.refresh:
            if self._ensure_refreshed(used_access):
                return self.request_sync(method, path, params, data, auth, _retry=False)

        if response.status_code == 204 or not response.content:
            return None

        try:
            payload = response.json()
        except json.JSONDecodeError:
            raise ApiError(f'Unexpected response from server ({response.status_code}).')

        if response.ok:
            return payload

        raise ApiError(self._describe(payload, response.status_code),
                       status=response.status_code, payload=payload)

    def upload_sync(self, path, file_path, field='image', _retry=True,
                    method='POST'):
        url = self.base_url + path.lstrip('/')
        used_access = self.session.access
        headers = {'Accept': 'application/json'}
        if used_access:
            headers['Authorization'] = f'Bearer {used_access}'

        try:
            with open(file_path, 'rb') as fh:
                response = self._http.request(
                    method, url,
                    files={field: (os.path.basename(file_path), fh)},
                    headers=headers, timeout=TIMEOUT,
                )
        except requests.Timeout:
            raise ApiError('The server took too long to respond.')
        except requests.ConnectionError:
            raise ApiError(
                f'Cannot reach the server at {self.base_url}.\n'
                'Is the backend running?'
            )
        except OSError as exc:
            raise ApiError(str(exc))

        if response.status_code == 401 and _retry and self.session.refresh:
            if self._ensure_refreshed(used_access):
                return self.upload_sync(path, file_path, field, _retry=False,
                                        method=method)

        if response.status_code == 204 or not response.content:
            return None
        try:
            payload = response.json()
        except json.JSONDecodeError:
            raise ApiError(f'Unexpected response from server ({response.status_code}).')
        if response.ok:
            return payload
        raise ApiError(self._describe(payload, response.status_code),
                       status=response.status_code, payload=payload)

    def fetch_binary_sync(self, url):
        try:
            response = self._http.get(url, timeout=TIMEOUT)
        except requests.Timeout:
            raise ApiError('The server took too long to respond.')
        except requests.ConnectionError:
            raise ApiError('Could not load the image.')
        if not response.ok:
            raise ApiError(f'Image request failed ({response.status_code}).')
        return response.content

    def download_pdf_sync(self, path, filename, _retry=True):
        """GET an authenticated endpoint's bytes, save to a temp file, return it.

        Used for the order and delivery-note PDFs, which need the auth header
        (unlike the public /media/ images).
        """
        import os
        import tempfile

        url = self.base_url + path.lstrip('/')
        used_access = self.session.access
        headers = {'Accept': 'application/pdf'}
        if used_access:
            headers['Authorization'] = f'Bearer {used_access}'
        try:
            response = self._http.get(url, headers=headers, timeout=TIMEOUT)
        except requests.Timeout:
            raise ApiError('The server took too long to respond.')
        except requests.ConnectionError:
            raise ApiError(f'Cannot reach the server at {self.base_url}.')
        if response.status_code == 401 and _retry and self.session.refresh:
            if self._ensure_refreshed(used_access):
                return self.download_pdf_sync(path, filename, _retry=False)
        if not response.ok:
            raise ApiError(f'Could not build the PDF ({response.status_code}).')
        folder = tempfile.mkdtemp(prefix='alomforce_pdf_')
        full = os.path.join(folder, filename)
        with open(full, 'wb') as fh:
            fh.write(response.content)
        return full

    def _ensure_refreshed(self, stale_access):
        """Refresh the access token once, even under a storm of concurrent 401s.

        Every worker that saw the same expired token funnels through one lock.
        The first performs the refresh; the rest wake to find the token already
        changed and reuse it instead of hammering /auth/refresh/ in parallel --
        the concurrent refreshes were themselves failing and blanking the app.
        """
        with self._refresh_lock:
            if self.session.access != stale_access:
                # Another worker refreshed while we waited on the lock.
                return True
            return self._refresh_token()

    def _refresh_token(self):
        try:
            response = self._http.post(
                self.base_url + 'auth/refresh/',
                json={'refresh': self.session.refresh},
                timeout=TIMEOUT,
            )
        except requests.RequestException:
            return False

        if not response.ok:
            return False
        body = response.json()
        self.session.update_access(body.get('access'))
        # If the server rotates refresh tokens, adopt the new one; otherwise the
        # next refresh would present a spent token and fail.
        if body.get('refresh'):
            self.session.refresh = body['refresh']
            self.session.save()
        return True

    @staticmethod
    def _describe(payload, status):
        """Turn a DRF error body into one readable line."""
        if isinstance(payload, dict):
            for key in ('detail', 'error', 'message'):
                if key in payload:
                    return str(payload[key])
            parts = []
            for field, errors in payload.items():
                if isinstance(errors, (list, tuple)):
                    parts.append(f'{field}: {"; ".join(str(e) for e in errors)}')
                else:
                    parts.append(f'{field}: {errors}')
            if parts:
                return '\n'.join(parts)
        return f'Request failed ({status}).'

    # -- auth -------------------------------------------------------------

    def login(self, identifier, password, on_ok=None, on_error=None):
        self.post('auth/login/',
                  {'identifier': identifier, 'password': password},
                  on_ok=on_ok, on_error=on_error, auth=False)
