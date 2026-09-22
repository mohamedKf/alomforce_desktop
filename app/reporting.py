"""Crash and error reporting through Sentry.

Nothing is baked into the build. The DSN comes from the server's /api/config/
and is cached in QSettings, so from the second start onwards Sentry is up
before anyone signs in; on the very first run it starts the moment the config
arrives after login. With no DSN -- an older server, a shop that has not set
one, or sentry-sdk not installed -- every function here is a no-op and the app
behaves exactly as it did before this module existed.

What is sent: the exception and its stack, the app version, the environment
the server named, and the user's numeric id and role. Never a name, an ID
number, a phone or an address; send_default_pii is off and the user is tagged
by id alone.
"""

import sys
import threading

from PySide6.QtCore import QSettings, QtMsgType, qInstallMessageHandler

from app import APP_VERSION

ORG, APP = 'AlomForce', 'AlomForce'
KEY_DSN = 'sentry_dsn'
KEY_ENVIRONMENT = 'sentry_environment'
RELEASE = f'alomforce-desktop@{APP_VERSION}'

_active = None                  # (dsn, environment) the client was started with
_hooks_installed = False
_previous_excepthook = None
_previous_qt_handler = None
_reported_endpoints = set()     # one message per endpoint per session
_lock = threading.Lock()
_dialog_open = False


def _sdk():
    """The sentry_sdk module, or None when it is not installed."""
    try:
        import sentry_sdk
    except ImportError:
        return None
    return sentry_sdk


def enabled():
    """True once a client has been started with a DSN."""
    return _active is not None


# -- starting ----------------------------------------------------------------

def init(dsn, environment=''):
    """Start the client, or restart it if the DSN or environment changed.

    Safe to call any number of times; a repeat with the same values is a
    no-op, and an empty DSN leaves whatever is running untouched.
    """
    global _active
    dsn = (dsn or '').strip()
    environment = (environment or '').strip()
    if not dsn or (dsn, environment) == _active:
        return
    sdk = _sdk()
    if sdk is None:
        return
    try:
        from sentry_sdk.integrations.excepthook import ExcepthookIntegration
        sdk.init(
            dsn=dsn,
            release=RELEASE,
            environment=environment or None,
            send_default_pii=False,
            traces_sample_rate=0,
            # Our own hook below does the capturing, and shows the person a
            # word about it; with the SDK's too every crash would land twice.
            disabled_integrations=[ExcepthookIntegration()],
        )
    except Exception:                                 # noqa: BLE001
        # A malformed DSN must not take the app down with it.
        return
    _active = (dsn, environment)


def bootstrap():
    """First thing in main(): start from the cached DSN and hook the crash paths."""
    settings = QSettings(ORG, APP)
    init(settings.value(KEY_DSN, '') or '', settings.value(KEY_ENVIRONMENT, '') or '')
    install_hooks()


def apply_config(config):
    """Adopt what /api/config/ said: cache the DSN for next start, start now.

    None means the config could not be fetched -- keep the cached value; an
    answer without a DSN means the server has none, so forget the cached one.
    """
    if config is None:
        return
    dsn = (config.get('sentry_dsn') or '').strip()
    environment = (config.get('sentry_environment') or '').strip()
    settings = QSettings(ORG, APP)
    if dsn:
        settings.setValue(KEY_DSN, dsn)
        settings.setValue(KEY_ENVIRONMENT, environment)
    else:
        settings.remove(KEY_DSN)
        settings.remove(KEY_ENVIRONMENT)
    init(dsn, environment)


def set_user(user):
    """Tag events with who was signed in: the numeric id and the role, nothing
    else. None (sign-out) clears the tag.

    Set on the global scope so a report from an API worker thread -- which
    has no isolation scope of its own -- still carries it.
    """
    sdk = _sdk()
    if sdk is None or not enabled():
        return
    scope = sdk.get_global_scope()
    if user and user.get('id') is not None:
        scope.set_user({'id': str(user['id'])})
        scope.set_tag('role', str(user.get('role') or ''))
    else:
        scope.set_user(None)
        scope.remove_tag('role')


# -- API failures -----------------------------------------------------------

def _endpoint(path):
    """'orders/12/share/' -> 'orders/{id}/share/', so one endpoint is one key."""
    path = (path or '').split('?', 1)[0].strip('/')
    return '/'.join('{id}' if part.isdigit() else part
                    for part in path.split('/')) + '/'


def report_api_failure(method, path, status, detail=''):
    """A 5xx from the server. Always a breadcrumb; a message once per
    endpoint per session, so a server that is down does not send a report
    for every retry of every page."""
    sdk = _sdk()
    if sdk is None or not enabled():
        return
    endpoint = _endpoint(path)
    sdk.add_breadcrumb(category='api', level='error',
                       message=f'{method} {endpoint} -> {status}',
                       data={'path': path, 'status': status})
    key = (method, endpoint)
    with _lock:
        if key in _reported_endpoints:
            return
        _reported_endpoints.add(key)
    with sdk.new_scope() as scope:
        scope.set_tag('endpoint', endpoint)
        scope.set_extra('status', status)
        scope.set_extra('path', path)
        if detail:
            scope.set_extra('detail', str(detail)[:500])
        scope.fingerprint = ['api-failure', method, endpoint, str(status)]
        sdk.capture_message(f'API {status} on {method} {endpoint}', level='error')


# -- crashes ------------------------------------------------------------------

def install_hooks():
    """Catch what would otherwise die silently.

    PySide runs a slot's unhandled exception through sys.excepthook and
    carries on, so without this a broken button just prints a traceback to a
    console nobody is watching. With it the exception is reported and the
    person sees one short dialog. Qt's own fatal messages go the same way.
    """
    global _hooks_installed, _previous_excepthook, _previous_qt_handler
    if _hooks_installed:
        return
    _hooks_installed = True
    _previous_excepthook = sys.excepthook
    sys.excepthook = _excepthook
    _previous_qt_handler = qInstallMessageHandler(_qt_message)


def _excepthook(exc_type, exc_value, tb):
    if not issubclass(exc_type, KeyboardInterrupt):
        reported = _capture(exc_value)
        if reported:
            _tell_the_user()
    (_previous_excepthook or sys.__excepthook__)(exc_type, exc_value, tb)


def _capture(exc):
    sdk = _sdk()
    if sdk is None or not enabled():
        return False
    try:
        sdk.capture_exception(exc)
        return True
    except Exception:                                 # noqa: BLE001
        return False


def _qt_message(mode, context, message):
    if mode == QtMsgType.QtFatalMsg:
        sdk = _sdk()
        if sdk is not None and enabled():
            try:
                sdk.capture_message(f'Qt fatal: {message}', level='fatal')
                sdk.flush(timeout=2)
            except Exception:                         # noqa: BLE001
                pass
    if _previous_qt_handler is not None:
        _previous_qt_handler(mode, context, message)
    else:
        # Installing a handler silences Qt's default one; keep the console
        # output people are used to.
        sys.stderr.write(f'{message}\n')


def _tell_the_user():
    """One short dialog: the app is still running and the fault is known.

    Only from the main thread, only while the window is up, and never a
    second one on top of the first.
    """
    global _dialog_open
    if _dialog_open or threading.current_thread() is not threading.main_thread():
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app.i18n import t
    except ImportError:
        return
    app = QApplication.instance()
    if app is None:
        return
    _dialog_open = True
    try:
        QMessageBox.warning(
            app.activeWindow(), t('An error was reported'),
            t('Something went wrong. The error has been reported and the '
              'app can carry on.'))
    except Exception:                                 # noqa: BLE001
        pass
    finally:
        _dialog_open = False
