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

# What the server will make a link for. The first two hang off an order;
# an invoice is its own record, so it has its own endpoint.
ORDER_KINDS = ('quote', 'delivery_note')
KINDS = ORDER_KINDS + ('invoice',)


def send_by_whatsapp(api, record_id, kind, on_done=None, on_error=None):
    """Ask the server for the share link and hand it to WhatsApp.

    `record_id` is an order for a quote or a delivery note, and an invoice for
    an invoice. on_done gets the share payload once WhatsApp has been opened;
    on_error gets an ApiError -- the server's own message on a 4xx, which says
    why (no file on the invoice, not a quote any more, and so on).
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

    if kind in ORDER_KINDS:
        path, params = f'orders/{record_id}/share/', {'kind': kind}
    else:
        path, params = f'invoices/{record_id}/share/', None
    api.get(path, params, on_ok=opened, on_error=on_error or (lambda _e: None))
