"""מסמכים — every document belonging to one order, in one place.

An order accumulates paper from both directions. The fabrication drawing comes
in, and a fitter may photograph the customer's own cutting list at the counter.
Going out there is the order note, the price quote and the delivery note. Those
used to be buttons on three different screens, which is how a workshop ends up
cutting to last week's revision.

So they are listed together, split by where they came from. The ones the system
makes are never stored — each is rendered from the order when it is opened, so
it cannot be stale and cannot be lost to a storage outage. The ones people
attach are files, and only those can be removed.

The preview is the point of the page. A bar schedule is identified by looking
at it, not by reading "PRO1.BAR.pdf", and opening each one in an external
viewer to find the right sheet is the thing this replaces.
"""

import os
import subprocess
import sys

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

KINDS = [('drawing', 'Drawing'), ('other', 'Other')]
FILTER = 'Documents (*.pdf *.png *.jpg *.jpeg *.webp *.heic)'

# The order the sections read in, and what each is called. Anything the server
# sends that is not listed here still gets a group of its own, at the end.
SECTIONS = [
    ('generated', 'Made by AlomForce'),
    ('drawing', 'Drawings'),
    ('other', 'Other documents'),
]

MUTED = QColor('#6b7280')
IMAGE_SUFFIXES = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')


def open_file(path):
    if sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    elif os.name == 'nt':
        os.startfile(path)                             # noqa: E1101
    else:
        subprocess.Popen(['xdg-open', path])


def _preview_pixmap(path, width):
    """The first page of a document, as a picture.

    PDFs go through QtPdf; a photographed sheet is already an image. Anything
    that will not render returns None and the pane says so rather than showing
    an empty white box that reads as a blank document.
    """
    lower = str(path).lower()
    if lower.endswith(IMAGE_SUFFIXES):
        pixmap = QPixmap(str(path))
        return None if pixmap.isNull() else pixmap
    if not lower.endswith('.pdf'):
        return None
    try:
        from PySide6.QtPdf import QPdfDocument
    except ImportError:
        return None
    document = QPdfDocument()
    if document.load(str(path)) != QPdfDocument.Error.None_:
        return None
    if document.pageCount() < 1:
        return None
    size = document.pagePointSize(0)
    if size.width() <= 0:
        return None
    height = int(width * size.height() / size.width())
    image = document.render(0, QSize(int(width), height))
    if isinstance(image, QImage) and not image.isNull():
        return QPixmap.fromImage(image)
    return None


class OrderAttachments(QWidget):
    """The documents page for one order."""

    def __init__(self, api, order_id=None, parent=None):
        super().__init__(parent)
        self.api = api
        self.order_id = order_id
        self.rows = []
        self._preview_path = None
        # Named, or it paints black: an unstyled QWidget has no ground of its
        # own, and this one is a whole page rather than a strip inside a card.
        self.setObjectName('Canvas')
        self.setAcceptDrops(True)
        self._build()
        self.reload()

    # -- layout ------------------------------------------------------------

    def _build(self):
        self.heading = QLabel(t('Documents'), objectName='SectionTitle')
        self.open_btn = QPushButton(t('Open'), objectName='Ghost')
        self.save_as_btn = QPushButton(t('Save a copy…'), objectName='Ghost')
        self.remove_btn = QPushButton(t('Remove'), objectName='Ghost')
        self.open_btn.clicked.connect(self._open)
        self.save_as_btn.clicked.connect(self._save_as)
        self.remove_btn.clicked.connect(self._remove)

        header = QHBoxLayout()
        header.addWidget(self.heading)
        header.addStretch()
        header.addWidget(self.save_as_btn)
        header.addWidget(self.remove_btn)
        header.addWidget(self.open_btn)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([t('Document'), t('Note'), t('Added')])
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(14)
        self.tree.setAlternatingRowColors(False)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(lambda *_: self._selection_changed())
        self.tree.itemDoubleClicked.connect(lambda *_: self._open())
        self.tree.setMinimumWidth(430)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, head.ResizeMode.Stretch)
        head.setSectionResizeMode(1, head.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(2, head.ResizeMode.ResizeToContents)

        # -- the preview pane
        self.preview = QLabel('', alignment=Qt.AlignCenter)
        self.preview.setMinimumWidth(360)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setObjectName('Preview')
        self.preview_title = QLabel('', objectName='FieldLabel')
        self.preview_title.setWordWrap(True)
        self.preview_detail = QLabel('', objectName='CardHint')
        self.preview_detail.setWordWrap(True)

        preview_card = QFrame(objectName='Card')
        preview_box = QVBoxLayout(preview_card)
        preview_box.setContentsMargins(14, 12, 14, 12)
        preview_box.setSpacing(6)
        preview_box.addWidget(self.preview_title)
        preview_box.addWidget(self.preview_detail)
        preview_box.addWidget(self.preview, 1)

        split = QHBoxLayout()
        split.setSpacing(14)
        split.addWidget(self.tree, 3)
        split.addWidget(preview_card, 2)

        # -- attaching
        self.kind = QComboBox()
        for value, label in KINDS:
            self.kind.addItem(t(label), value)
        self.note = QLineEdit(placeholderText=t('Which plan, e.g. +6.12'))
        self.attach_btn = QPushButton(t('Attach…'), objectName='PrimaryButton')
        self.attach_btn.clicked.connect(self._attach)

        self.drop_hint = QLabel(t('or drag files here'), objectName='CardHint')

        attach_row = QHBoxLayout()
        attach_row.addWidget(QLabel(t('Kind'), objectName='FieldLabel'))
        attach_row.addWidget(self.kind)
        attach_row.addWidget(self.note, 1)
        attach_row.addWidget(self.attach_btn)
        attach_row.addWidget(self.drop_hint)

        attach_card = QFrame(objectName='Card')
        attach_box = QVBoxLayout(attach_card)
        attach_box.setContentsMargins(14, 10, 14, 10)
        attach_box.addLayout(attach_row)

        self.status = QLabel('', objectName='CardHint')
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addLayout(split, 1)
        layout.addWidget(attach_card)
        layout.addWidget(self.status)
        self._refresh_enabled()

    # -- state --------------------------------------------------------------

    def set_order(self, order_id):
        """Called once a new order has been saved and finally has an id."""
        self.order_id = order_id
        self._refresh_enabled()
        self.reload()

    def _refresh_enabled(self):
        # There is nothing to attach a file to until the order exists.
        has_order = self.order_id is not None
        for widget in (self.attach_btn, self.kind, self.note):
            widget.setEnabled(has_order)
        row = self._selected()
        self.open_btn.setEnabled(bool(row))
        self.save_as_btn.setEnabled(bool(row))
        # A generated sheet is not a file; there is nothing to delete.
        self.remove_btn.setEnabled(bool(row and not row.get('generated')))
        if not has_order:
            self.status.setText(t('Save the order first, then attach the sheet.'))

    def reload(self):
        if self.order_id is None:
            return
        self.api.get(f'orders/{self.order_id}/attachments/',
                     on_ok=self._on_rows, on_error=self._on_error)

    def _on_rows(self, payload):
        self.rows = payload if isinstance(payload, list) else []
        # Keep the selection across a reload, or attaching a file throws the
        # user back to the top of the list every time.
        was = self._selected()
        # Signals off for the rebuild. Clearing the tree and adding rows both
        # change the current item, and the selection handler starts a download
        # for whatever is selected -- so a plain refresh would fire several
        # fetches against a tree it is still halfway through building.
        self.tree.blockSignals(True)
        self.tree.clear()

        groups = {}
        for row in self.rows:
            groups.setdefault(row.get('section') or 'other', []).append(row)
        order = [key for key, _label in SECTIONS]
        keys = ([key for key, _l in SECTIONS if key in groups]
                + [key for key in groups if key not in order])

        restore = None
        bold = QFont()
        bold.setBold(True)
        for key in keys:
            label = dict(SECTIONS).get(key, key)
            parent = QTreeWidgetItem([f'{t(label)}   ({len(groups[key])})'])
            parent.setFont(0, bold)
            parent.setFirstColumnSpanned(True)
            parent.setFlags(Qt.ItemIsEnabled)     # a heading, not a selection
            self.tree.addTopLevelItem(parent)
            for row in groups[key]:
                child = QTreeWidgetItem([
                    row.get('filename') or '',
                    row.get('note') or '',
                    self._added_text(row)])
                child.setData(0, Qt.UserRole, row)
                for column in (1, 2):
                    child.setForeground(column, QBrush(MUTED))
                parent.addChild(child)
                if was and self._same(was, row):
                    restore = child
            parent.setExpanded(True)

        if restore is not None:
            self.tree.setCurrentItem(restore)
        elif self.tree.topLevelItemCount():
            first = self.tree.topLevelItem(0)
            if first.childCount():
                self.tree.setCurrentItem(first.child(0))
        self.tree.blockSignals(False)
        # Asked for once, deliberately, now the tree is whole.
        self._selection_changed()
        self.status.setText('' if self.rows else t('Nothing attached yet.'))
        self._refresh_enabled()

    @staticmethod
    def _same(a, b):
        """Two rows are the same document. Generated ones have no id."""
        if a.get('id') or b.get('id'):
            return a.get('id') == b.get('id')
        return a.get('path') == b.get('path')

    @staticmethod
    def _added_text(row):
        if row.get('generated'):
            return t('always current')
        stamp = (row.get('uploaded_at') or '')[:10]
        who = row.get('uploaded_by_name') or ''
        return '  ·  '.join(part for part in (stamp, who) if part)

    def _on_error(self, error):
        self.status.setText(getattr(error, 'message', str(error)))

    def _selected(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item else None

    # -- the preview --------------------------------------------------------

    def _selection_changed(self):
        self._refresh_enabled()
        row = self._selected()
        if not row:
            self.preview_title.setText('')
            self.preview_detail.setText('')
            self.preview.setPixmap(QPixmap())
            self.preview.setText('')
            return
        self.preview_title.setText(row.get('filename') or '')
        # The server sends the kind in whatever language the request carried.
        # Translating here follows the app instead, which is what the person
        # looking at the screen has chosen.
        parts = [t(row.get('kind_display') or '')]
        if row.get('note'):
            parts.append(row['note'])
        self.preview_detail.setText('  ·  '.join(p for p in parts if p))
        self.preview.setPixmap(QPixmap())
        self.preview.setText(t('Loading…'))
        # Fetched rather than rendered from a storage URL: the bucket may be
        # private and its links expire, and the app already holds a token.
        self.api.download_pdf(
            self._path_for(row), row.get('filename') or 'document',
            on_ok=lambda path, r=row: self._render_preview(path, r),
            on_error=lambda e: self.preview.setText(t('No preview.')))

    def _render_preview(self, path, row):
        # A slow fetch can land after the user has moved on; drawing it then
        # would show one document under another's name.
        current = self._selected()
        if not current or not self._same(current, row):
            return
        self._preview_path = path
        width = max(240, self.preview.width() - 16)
        pixmap = _preview_pixmap(path, width)
        if pixmap is None:
            self.preview.setText(t('No preview.'))
            return
        if pixmap.width() > width:
            pixmap = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        height = max(200, self.preview.height() - 8)
        if pixmap.height() > height:
            pixmap = pixmap.scaledToHeight(height, Qt.SmoothTransformation)
        self.preview.setText('')
        self.preview.setPixmap(pixmap)

    def _path_for(self, row):
        """Where to fetch this document.

        The server sends a path with every row, so the screens do not have to
        know which route renders what.
        """
        path = (row.get('path') or '').lstrip('/')
        if path.startswith('api/'):
            path = path[4:]
        if path:
            return path
        # An older server that sends no path.
        return f"orders/{self.order_id}/attachments/{row['id']}/"

    # -- actions ------------------------------------------------------------

    def _attach(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, t('Attach a document'), '', t(FILTER))
        self._upload(paths)

    def _upload(self, paths):
        paths = [p for p in (paths or []) if p]
        if not paths or self.order_id is None:
            return
        self.status.setText(t('Uploading…'))
        self.attach_btn.setEnabled(False)
        self._pending = len(paths)
        for path in paths:
            self.api.upload(
                f'orders/{self.order_id}/attachments/', path, field='file',
                data={'kind': self.kind.currentData(),
                      'note': self.note.text().strip()},
                on_ok=self._attached, on_error=self._attach_failed)

    def _attached(self, _payload):
        self._pending = max(0, getattr(self, '_pending', 1) - 1)
        if self._pending:
            return
        self.attach_btn.setEnabled(True)
        self.status.setText('')
        self.note.clear()
        self.reload()

    def _attach_failed(self, error):
        self._pending = max(0, getattr(self, '_pending', 1) - 1)
        self.attach_btn.setEnabled(True)
        self._on_error(error)
        if not self._pending:
            self.reload()

    def _open(self):
        row = self._selected()
        if not row:
            return
        # Already fetched for the preview; no reason to ask for it twice.
        if self._preview_path and self._same(self._selected(), row):
            open_file(self._preview_path)
            return
        self.status.setText(t('Opening…'))
        self.open_btn.setEnabled(False)
        self.api.download_pdf(
            self._path_for(row), row.get('filename') or 'document.pdf',
            on_ok=self._show, on_error=self._open_failed)

    def _show(self, path):
        self.status.setText('')
        self.open_btn.setEnabled(True)
        open_file(path)

    def _open_failed(self, error):
        self.open_btn.setEnabled(True)
        self._on_error(error)

    def _save_as(self):
        """Put a copy somewhere the user chooses — to email, or to file."""
        row = self._selected()
        if not row:
            return
        target, _ = QFileDialog.getSaveFileName(
            self, t('Save a copy…'), row.get('filename') or 'document.pdf')
        if not target:
            return

        def write(path):
            try:
                with open(path, 'rb') as source, open(target, 'wb') as out:
                    out.write(source.read())
            except OSError as exc:
                self.status.setText(str(exc))
                return
            self.status.setText(f"{t('Saved')}  {target}")

        self.status.setText(t('Saving…'))
        self.api.download_pdf(
            self._path_for(row), row.get('filename') or 'document.pdf',
            on_ok=write, on_error=self._on_error)

    def _remove(self):
        row = self._selected()
        if not row:
            return
        if row.get('generated'):
            # Not a file. It is rendered from the order each time it is
            # opened, so there is nothing to delete.
            self.status.setText(t('This document is made from the order.'))
            return
        confirm = QMessageBox.question(
            self, t('Remove attachment'),
            t('Remove “{name}” from this order?')
            .replace('{name}', row.get('filename') or ''),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        self.api.delete(
            f"orders/{self.order_id}/attachments/{row['id']}/",
            on_ok=lambda _p: self.reload(), on_error=self._on_error)

    # -- dragging files on --------------------------------------------------

    def dragEnterEvent(self, event):
        if self.order_id is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()
                 if url.isLocalFile()]
        allowed = tuple(IMAGE_SUFFIXES) + ('.pdf', '.heic')
        keep = [p for p in paths if p.lower().endswith(allowed)]
        if not keep:
            self.status.setText(t('Only PDFs and photos can be attached.'))
            return
        event.acceptProposedAction()
        self._upload(keep)

    def retranslate(self):
        self.heading.setText(t('Documents'))
        self.attach_btn.setText(t('Attach…'))
        self.open_btn.setText(t('Open'))
        self.save_as_btn.setText(t('Save a copy…'))
        self.remove_btn.setText(t('Remove'))
        self.drop_hint.setText(t('or drag files here'))
        self.note.setPlaceholderText(t('Which plan, e.g. +6.12'))
        self.tree.setHeaderLabels([t('Document'), t('Note'), t('Added')])
