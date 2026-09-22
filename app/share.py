"""Sending an order's paper to the client over WhatsApp.

WhatsApp on the desktop carries text only, so the server makes a public link
to the document and words the message; the app opens the ready wa.me link and
WhatsApp takes it from there, with the client's number already filled in when
one is on file.
"""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from app.api import ApiError
from app.i18n import t

# What the server will make a link for.
KINDS = ('quote', 'delivery_note')


def send_by_whatsapp(api, order_id, kind, on_done=None, on_error=None):
    """Ask the server for the share link and hand it to WhatsApp.

    on_done gets the share payload once WhatsApp has been opened; on_error
    gets an ApiError -- the server's own message on a 4xx, which says why
    (no phone, not a quote any more, and so on).
    """
    def opened(payload):
        url = (payload or {}).get('whatsapp_url') or ''
        if not url:
            if on_error:
                on_error(ApiError(t('The server sent no WhatsApp link.')))
            return
        QDesktopServices.openUrl(QUrl(url))
        if on_done:
            on_done(payload)

    api.get(f'orders/{order_id}/share/', {'kind': kind},
            on_ok=opened, on_error=on_error or (lambda _e: None))
