"""Small form toolkit: labelled fields with inline validation, and sections.

A ``Field`` is a label + input + a line of red (error) or amber (warning) text
that appears right under the input. Errors block submit; warnings don't -- an
Israeli ID whose check digit looks off is flagged, not refused, because the
office sometimes has to enter an ID the algorithm dislikes.
"""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
_PHONE_RE = re.compile(r'^[\d\-\+\s()]{7,20}$')


# -- validators: return an error string, or None if fine ---------------------

def required(value):
    return None if str(value).strip() else t('This field is required.')


def email(value):
    v = value.strip()
    return None if not v or _EMAIL_RE.match(v) else t('Enter a valid email address.')


def phone(value):
    v = value.strip()
    return None if not v or _PHONE_RE.match(v) else t('Enter a valid phone number.')


def number(value):
    v = value.strip().replace(',', '.')
    if not v:
        return None
    try:
        float(v)
        return None
    except ValueError:
        return t('Enter a number.')


def date_iso(value):
    v = value.strip()
    if not v:
        return None
    import datetime
    try:
        datetime.date.fromisoformat(v)
        return None
    except ValueError:
        return t('Use the format YYYY-MM-DD.')


def id_number(value):
    v = value.strip()
    if not v:
        return None
    if not v.isdigit() or len(v) > 9:
        return t('Enter a valid ID number (up to 9 digits).')
    return None


def id_checksum_warning(value):
    """Non-blocking: the Israeli ID check-digit test."""
    v = value.strip()
    if not v.isdigit() or len(v) > 9:
        return None
    d = v.zfill(9)
    total = 0
    for i, ch in enumerate(d):
        n = int(ch) * (1 if i % 2 == 0 else 2)
        total += n if n < 10 else n - 9
    if total % 10 != 0:
        return t("This ID's check digit looks wrong — double-check it.")
    return None


# -- section header ----------------------------------------------------------

def section(title):
    """A section header: a bold title with a hairline rule beside it."""
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 6, 0, 2)
    row.setSpacing(10)
    label = QLabel(t(title), objectName='SectionTitle')
    rule = QFrame(objectName='SectionRule')
    rule.setFrameShape(QFrame.HLine)
    row.addWidget(label)
    row.addWidget(rule, 1)
    box.label = label
    box.title_key = title
    return box


# -- field -------------------------------------------------------------------

class Field(QWidget):
    """A labelled input with inline validation.

    kind: 'line' (default), 'combo', 'text'. Pass `choices` for a combo as a
    list of (value, label_key). `validators` are blocking; `warn` is not.
    """

    def __init__(self, label, kind='line', required_field=False,
                 validators=(), warn=None, placeholder='', choices=None):
        super().__init__()
        self.label_key = label
        self.required = required_field
        self.validators = list(validators)
        if required_field:
            self.validators = [required] + self.validators
        self.warn = warn
        self.kind = kind

        if kind == 'combo':
            self.input = QComboBox()
            for value, lbl in (choices or []):
                self.input.addItem(t(lbl), value)
        elif kind == 'text':
            self.input = QPlainTextEdit()
            self.input.setFixedHeight(56)
        else:
            self.input = QLineEdit()
            if placeholder:
                self.input.setPlaceholderText(t(placeholder))
        self.input.setMinimumHeight(0 if kind == 'text' else 38)

        self.label = QLabel(self._label_text(), objectName='FieldLabel')
        self.note = QLabel('', objectName='FieldError')
        self.note.setWordWrap(True)
        self.note.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        layout.addWidget(self.label)
        layout.addWidget(self.input)
        layout.addWidget(self.note)

        # Re-validate as the user fixes a flagged field, so the red clears live.
        signal = getattr(self.input, 'textChanged', None) \
            or getattr(self.input, 'currentIndexChanged', None)
        if signal:
            signal.connect(self._on_changed)

    def _label_text(self):
        star = ' *' if self.required else ''
        return t(self.label_key) + star

    # -- value -----------------------------------------------------------

    def value(self):
        if self.kind == 'combo':
            return self.input.currentData()
        if self.kind == 'text':
            return self.input.toPlainText().strip()
        return self.input.text().strip()

    def set_value(self, value):
        if self.kind == 'combo':
            idx = self.input.findData(value)
            if idx >= 0:
                self.input.setCurrentIndex(idx)
        elif self.kind == 'text':
            self.input.setPlainText(str(value or ''))
        else:
            self.input.setText(str(value or ''))

    def focus(self):
        self.input.setFocus()

    # -- validation ------------------------------------------------------

    def validate(self):
        """Run validators; paint state. Return True if it may be submitted."""
        value = self.value() if self.kind != 'combo' else (self.value() or '')
        for check in self.validators:
            error = check(str(value))
            if error:
                self._paint('invalid', error)
                return False
        if self.warn:
            warning = self.warn(str(value))
            if warning:
                self._paint('warn', warning)
                return True
        self._paint('', '')
        return True

    def _on_changed(self, *_):
        # Only clear an existing flag; don't nag before the first submit.
        if self.note.isVisible():
            self.validate()

    def _paint(self, state, message):
        self.input.setProperty('state', state or None)
        self.input.style().unpolish(self.input)
        self.input.style().polish(self.input)
        if message:
            self.note.setObjectName('FieldWarn' if state == 'warn' else 'FieldError')
            self.note.setText(message)
            self.note.style().unpolish(self.note)
            self.note.style().polish(self.note)
            self.note.show()
        else:
            self.note.hide()

    def retranslate(self):
        self.label.setText(self._label_text())


def validate_all(fields):
    """Validate every field; focus the first invalid one. Return True if ok."""
    ok = True
    first_bad = None
    for field in fields:
        if not field.validate():
            ok = False
            if first_bad is None:
                first_bad = field
    if first_bad is not None:
        first_bad.focus()
    return ok
