"""Making sure a client's ח.פ/ע.מ is known before a document needs it.

An Israeli tax invoice has to carry the customer's registration number. The
number belongs to the client, not to the document, so it is filled from the
client record wherever it is wanted — and when the record has not got one, it
is asked for once and written back, rather than being typed again on every
invoice or, worse, left blank on paper that has already gone out.

Asked at the moment it matters — raising an invoice, printing a quote — and
not before: a yard opens a client record to take a phone number and should not
be stopped by a field that only counts at invoicing time.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.i18n import t


class TaxIdDialog(QDialog):
    """Ask for a client's tax ID, and offer to keep it."""

    def __init__(self, client_name, parent=None):
        super().__init__(parent)
        self.value = ''
        self.remember = True
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setWindowTitle(t('Client tax ID'))

        heading = QLabel(
            t('{name} has no tax ID on file.').replace('{name}', client_name
                                                       or t('This client')),
            objectName='CardTitle')
        heading.setWordWrap(True)
        hint = QLabel(t('A tax invoice has to show the customer’s ח.פ / ע.מ.'),
                      objectName='CardHint')
        hint.setWordWrap(True)

        self.field = QLineEdit(placeholderText='515000148')
        self.field.setMaxLength(32)
        self.keep = QCheckBox(t('Save it on the client'))
        self.keep.setChecked(True)

        self.error = QLabel('', objectName='Error')
        self.error.setWordWrap(True)
        self.error.hide()

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                        | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(t('Use this'))
        # Not "cancel the invoice": a yard does sell to a private customer who
        # has no company number, and refusing to carry on would be wrong.
        self.buttons.button(QDialogButtonBox.Cancel).setText(
            t('Carry on without one'))
        self.buttons.accepted.connect(self._submit)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(10)
        layout.addWidget(heading)
        layout.addWidget(hint)
        layout.addWidget(self.field)
        layout.addWidget(self.keep)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)
        self.field.setFocus()

    def _submit(self):
        value = self.field.text().strip()
        # Digits, dashes and spaces as people write them; nothing else. Not a
        # checksum -- a wrong-but-plausible number is the office's to catch,
        # and refusing a valid one the app has not heard of is worse.
        cleaned = value.replace('-', '').replace(' ', '')
        if not cleaned:
            self.error.setText(t('Enter a number, or carry on without one.'))
            self.error.show()
            return
        if not cleaned.isdigit():
            self.error.setText(t('A tax ID is digits only.'))
            self.error.show()
            return
        self.value = cleaned
        self.remember = self.keep.isChecked()
        self.accept()


def ensure_tax_id(api, client_id, client_name, current, parent=None):
    """Return the tax ID to put on a document, asking for one if need be.

    Returns the number already on file when there is one — no dialog, nothing
    for the office to dismiss. Otherwise it asks; if the answer is to be kept,
    it is written back to the client so the question is asked once rather than
    on every invoice.

    Returns '' when the user chooses to carry on without one, which is a real
    answer: a private customer may not have a company number.
    """
    existing = (current or '').strip()
    if existing:
        return existing
    dialog = TaxIdDialog(client_name, parent=parent)
    if not dialog.exec():
        return ''
    if dialog.remember and client_id:
        # Best effort. The number is already going onto the document; failing
        # to also file it against the client is not a reason to stop.
        api.patch(f'clients/{client_id}/', {'tax_id': dialog.value},
                  on_ok=lambda _p: None, on_error=lambda _e: None)
    return dialog.value
