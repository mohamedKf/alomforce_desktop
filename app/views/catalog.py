"""Catalog browser.

Filters map one-to-one onto the API's query parameters, so the screen stays a
thin view over `/api/catalog/listings/`. Searching is debounced: typing
"04935" would otherwise fire five requests and render whichever came back last,
which is not necessarily the one for the full query.
"""

from PySide6.QtCore import (
    QAbstractTableModel,
    QLocale,
    QModelIndex,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QDoubleValidator, QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t

PAGE_SIZE = 50
SEARCH_DEBOUNCE_MS = 300

GLASS_CHOICES = [4, 6, 8, 10, 12, 16, 18, 20, 24, 28, 32, 40]

# Section-image thumbnails. Cross-sections are wide and short, so the row is
# sized to the image rather than the other way round.
THUMB_H = 40
THUMB_W = 72
IMAGE_FILTER = 'Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)'


class ListingModel(QAbstractTableModel):
    """Catalog rows. Columns are ordered the way someone reads a parts list:
    what it is, then what it does, then the numbers."""

    COLUMNS = [
        ('image', 'Image'),
        ('number', 'Profile'),
        ('description', 'Description'),
        ('series_code', 'Series'),
        ('role_display', 'Type'),
        ('glass', 'Glass'),
        ('track_count', 'Tracks'),
        ('weight', 'Weight'),
        ('price', 'Price/m'),
    ]

    def __init__(self):
        super().__init__()
        self.rows = []
        # section_image URL -> scaled QPixmap. Kept across reloads so paging
        # back to a page does not refetch every thumbnail.
        self._thumbs = {}

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def set_thumb(self, url, pixmap):
        """Store a loaded thumbnail and repaint any row that shows it."""
        self._thumbs[url] = pixmap
        for r, row in enumerate(self.rows):
            if row.get('section_image') == url:
                idx = self.index(r, 0)
                self.dataChanged.emit(idx, idx, [Qt.DecorationRole])

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return t(self.COLUMNS[section][1])
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        key = self.COLUMNS[index.column()][0]

        if role == Qt.DecorationRole and key == 'image':
            # None while the thumbnail is still loading (or absent); the cell
            # is simply blank until set_thumb repaints it.
            return self._thumbs.get(row.get('section_image'))
        if role == Qt.DisplayRole:
            if key == 'image':
                return None
            return self._display(row, key)
        if role == Qt.FontRole and key == 'number':
            font = QFont()
            font.setBold(True)
            return font
        if role == Qt.TextAlignmentRole and key in {'weight', 'track_count', 'glass'}:
            return int(Qt.AlignCenter)
        if role == Qt.TextAlignmentRole and key == 'price':
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    @staticmethod
    def _display(row, key):
        if key == 'glass':
            low, high = row.get('glass_min_mm'), row.get('glass_max_mm')
            if high is None:
                return '—'
            high = f'{float(high):g}'
            if low is None:
                return f'≤{high}'
            return f'{float(low):g}–{high}'

        if key == 'weight':
            weight = row.get('weight_g_per_m')
            return f'{weight:,}' if weight else '—'

        if key == 'price':
            # Priced by weight: shown only once the series has a price/kg set.
            price = row.get('price_per_m')
            return f'₪{float(price):,.2f}' if price is not None else '—'

        if key == 'track_count':
            return str(row['track_count']) if row.get('track_count') else '—'

        if key == 'role_display':
            # The API sends role labels in English; translate them here so the
            # column matches the rest of the window rather than sitting in a
            # second language mid-table.
            return t(row.get('role_display') or '') or '—'

        return row.get(key) or '—'

    def row_at(self, index):
        return self.rows[index.row()] if 0 <= index.row() < len(self.rows) else None


class CatalogView(QWidget):
    # Emitted in pick mode when a profile row is chosen (double-click or the
    # "Add to order" button). Carries the row dict.
    profile_picked = Signal(object)

    def __init__(self, api, session=None, pick_mode=False):
        super().__init__()
        self.api = api
        self.session = session
        # In pick mode the catalog is an item picker (for the order editor):
        # no price editing or image upload, and rows are added to the order.
        self._pick_mode = pick_mode
        # Managers may change a series' metal price and upload section images;
        # everyone else sees both read-only. The backend enforces this too.
        self._is_manager = (session.role if session else None) == 'manager' and not pick_mode
        self._can_edit_price = self._is_manager
        self.page = 1
        self.total = 0
        self._request_id = 0
        # Kept so the role filter can be rebuilt in a new language without
        # re-fetching it.
        self._role_data = []
        # code -> price_per_kg (as returned by the API), so the price editor can
        # prefill and reflect edits without refetching the series list.
        self._series_price = {}
        # section_image URLs already requested, so a thumbnail is fetched once
        # even as the same page is repainted.
        self._thumb_requested = set()
        self.setObjectName('Canvas')
        self._build()

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.reload)

    # -- construction ----------------------------------------------------

    def _build(self):
        self.title = QLabel(t('Catalog'), objectName='PageTitle')
        self.count = QLabel('', objectName='PageCount')

        # Managers attach a cross-section image to the selected profile. Stored
        # locally now; the same call reaches Cloudinary once it is configured.
        self.upload_btn = QPushButton(t('Upload image'))
        self.upload_btn.setEnabled(False)
        self.upload_btn.clicked.connect(self._upload_selected)

        # Pick mode: add the selected profile to the order.
        self.add_to_order_btn = QPushButton(t('Add to order'))
        self.add_to_order_btn.setEnabled(False)
        self.add_to_order_btn.clicked.connect(self._pick_selected)

        # Print a sheet of QR labels for the current filter (office/managers).
        self.qr_btn = QPushButton(t('Print QR labels'), objectName='Ghost')
        self.qr_btn.clicked.connect(self._print_qr_labels)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        if self._pick_mode:
            header.addWidget(self.add_to_order_btn)
            self.upload_btn.hide()
            self.qr_btn.hide()
        elif self._is_manager:
            header.addWidget(self.qr_btn)
            header.addWidget(self.upload_btn)
        else:
            self.upload_btn.hide()
            self.add_to_order_btn.hide()
            self.qr_btn.hide()

        self.search = QLineEdit(placeholderText=t('Search profiles'))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(240)
        self.search.textChanged.connect(self._on_search_typed)

        self.series = QComboBox()
        self.role = QComboBox()
        self.tracks = QComboBox()
        self.glass = QComboBox()
        for combo in (self.series, self.role, self.tracks, self.glass):
            combo.setMinimumWidth(140)
        # Changing the series also narrows the Type list and moves the price
        # editor onto that series, so it gets its own handler rather than the
        # plain reload the other filters use.
        self.series.currentIndexChanged.connect(self._on_series_changed)
        for combo in (self.role, self.tracks, self.glass):
            combo.currentIndexChanged.connect(self.reload_from_first_page)

        self.clear = QPushButton(t('Clear filters'), objectName='Ghost')
        self.clear.clicked.connect(self._clear_filters)

        # Per-series metal price. Managers type a price/kg for the selected
        # series and the whole price column recomputes from each row's weight.
        self.price_label = QLabel(t('₪/kg'))
        self.price_input = QLineEdit()
        self.price_input.setFixedWidth(90)
        self.price_input.setPlaceholderText(t('Pick a series'))
        validator = QDoubleValidator(0.0, 1_000_000.0, 2)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale(QLocale.C))
        self.price_input.setValidator(validator)
        self.price_input.editingFinished.connect(self._apply_price)
        self.price_input.setEnabled(False)

        filters = QHBoxLayout()
        filters.setSpacing(9)
        for widget in (self.search, self.series, self.role, self.tracks, self.glass):
            filters.addWidget(widget)
        filters.addWidget(self.clear)
        filters.addStretch()
        if self._can_edit_price:
            filters.addWidget(self.price_label)
            filters.addWidget(self.price_input)
        else:
            self.price_label.hide()
            self.price_input.hide()

        self.model = ListingModel()
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        # Rows are as tall as a thumbnail so section images are legible.
        self.table.verticalHeader().setDefaultSectionSize(THUMB_H + 8)
        self.table.setIconSize(QSize(THUMB_W, THUMB_H))
        self.table.selectionModel().selectionChanged.connect(
            self._update_upload_enabled
        )
        if self._pick_mode:
            self.table.doubleClicked.connect(lambda _i: self._pick_selected())
        elif self._is_manager:
            self.table.doubleClicked.connect(self._on_row_activated)

        head = self.table.horizontalHeader()
        head.setSectionResizeMode(0, QHeaderView.ResizeToContents)   # image
        head.setSectionResizeMode(1, QHeaderView.ResizeToContents)   # number
        head.setSectionResizeMode(2, QHeaderView.Stretch)            # description
        for column in range(3, len(ListingModel.COLUMNS)):
            head.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        head.setHighlightSections(False)

        self.status = QLabel('', objectName='Muted')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.hide()

        self.prev = QPushButton('‹', objectName='Ghost')
        self.next = QPushButton('›', objectName='Ghost')
        self.page_label = QLabel('', objectName='Muted')
        self.prev.setFixedWidth(40)
        self.next.setFixedWidth(40)
        self.prev.clicked.connect(lambda: self._step_page(-1))
        self.next.clicked.connect(lambda: self._step_page(1))

        pager = QHBoxLayout()
        pager.addStretch()
        pager.addWidget(self.prev)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(16)
        layout.addLayout(header)
        layout.addLayout(filters)
        layout.addWidget(self.status)
        layout.addWidget(self.table, 1)
        layout.addLayout(pager)

    # -- data ------------------------------------------------------------

    def load_filter_options(self):
        """Populate the filter dropdowns from the API, once."""
        self.series.blockSignals(True)
        self.series.clear()
        self.series.addItem(t('All series'), None)
        self.series.blockSignals(False)

        self.role.blockSignals(True)
        self.role.clear()
        self.role.addItem(t('All roles'), None)
        self.role.blockSignals(False)

        self.tracks.blockSignals(True)
        self.tracks.clear()
        self.tracks.addItem(t('Any tracks'), None)
        for n in range(1, 6):
            self.tracks.addItem(f'{n}', n)
        self.tracks.blockSignals(False)

        self.glass.blockSignals(True)
        self.glass.clear()
        self.glass.addItem(t('Any thickness'), None)
        for mm in GLASS_CHOICES:
            self.glass.addItem(f'{mm} mm', mm)
        self.glass.blockSignals(False)

        self.api.get('catalog/series/', on_ok=self._on_series, on_error=self._on_error)
        self.api.get('catalog/listings/roles/', on_ok=self._on_roles,
                     on_error=self._on_error)

    def _on_series(self, payload):
        self.series.blockSignals(True)
        for item in payload or []:
            family = item.get('family_name') or ''
            label = f"{item['code']} · {family}" if family else item['code']
            self.series.addItem(f"{label}  ({item['profile_count']})", item['code'])
            self._series_price[item['code']] = item.get('price_per_kg')
        self.series.blockSignals(False)

    # -- series selection: narrow roles, move the price editor ------------

    def _on_series_changed(self):
        """Series picked: refetch the roles that exist in it, then reload.

        The listing reload waits for the scoped roles so the Type filter and the
        rows never disagree -- otherwise a role the new series lacks would stay
        selected and the table would sit empty until the roles came back.
        """
        self.page = 1
        self._sync_price_editor()
        code = self.series.currentData()
        params = {'series': code} if code else None
        self.api.get('catalog/listings/roles/', params,
                     on_ok=self._on_roles_then_reload, on_error=self._on_roles_error)

    def _on_roles_then_reload(self, payload):
        self._on_roles(payload)
        self.reload()

    def _on_roles_error(self, error):
        # Couldn't scope the roles; keep the current list and still load rows.
        self.reload()

    # -- per-series price editing -----------------------------------------

    def _sync_price_editor(self):
        """Point the price field at the selected series and prefill its price."""
        if not self._can_edit_price:
            return
        code = self.series.currentData()
        enabled = bool(code)
        self.price_input.setEnabled(enabled)
        self.price_input.blockSignals(True)
        if enabled:
            price = self._series_price.get(code)
            self.price_input.setText('' if price in (None, '') else f'{float(price):g}')
            self.price_input.setPlaceholderText(t('Price/kg'))
        else:
            self.price_input.clear()
            self.price_input.setPlaceholderText(t('Pick a series'))
        self.price_input.blockSignals(False)

    def _apply_price(self):
        """Save the typed price/kg for the selected series, if it changed."""
        if not self._can_edit_price:
            return
        code = self.series.currentData()
        if not code:
            return
        text = self.price_input.text().strip().replace(',', '.')
        new_value = None if text == '' else text
        # editingFinished also fires on focus-out; skip a no-op PATCH.
        if self._price_equal(new_value, self._series_price.get(code)):
            return
        self.api.patch(f'catalog/series/{code}/price/',
                       {'price_per_kg': new_value},
                       on_ok=self._on_price_saved, on_error=self._on_error)

    def _on_price_saved(self, payload):
        code = payload.get('code')
        if code:
            self._series_price[code] = payload.get('price_per_kg')
        self._sync_price_editor()
        # Recompute the visible price column against the new price.
        self.reload()

    @staticmethod
    def _price_equal(a, b):
        fa = None if a in (None, '') else float(a)
        fb = None if b in (None, '') else float(b)
        return fa == fb

    def _on_roles(self, payload):
        self._role_data = [item for item in (payload or []) if item['count']]
        self._fill_roles()

    def _fill_roles(self):
        selected = self.role.currentData()
        self.role.blockSignals(True)
        self.role.clear()
        self.role.addItem(t('All roles'), None)
        for item in self._role_data:
            self.role.addItem(f"{t(item['label'])}  ({item['count']})", item['value'])
        if selected:
            self.role.setCurrentIndex(max(0, self.role.findData(selected)))
        self.role.blockSignals(False)

    def _on_search_typed(self):
        self.page = 1
        self._debounce.start()

    def reload_from_first_page(self):
        self.page = 1
        self.reload()

    def reload(self):
        params = {'page': self.page}
        if text := self.search.text().strip():
            params['search'] = text
        if series := self.series.currentData():
            params['series'] = series
        if role := self.role.currentData():
            params['role'] = role
        if tracks := self.tracks.currentData():
            params['tracks'] = tracks
        if glass := self.glass.currentData():
            params['glass'] = glass

        # Responses can arrive out of order, so stamp each request and ignore
        # anything that is not the newest -- otherwise a slow early query can
        # overwrite the results of a later, more specific one.
        self._request_id += 1
        request_id = self._request_id

        self._set_status(t('Loading…'))
        self.api.get(
            'catalog/listings/', params,
            on_ok=lambda payload: self._on_rows(payload, request_id),
            on_error=lambda error: self._on_error(error, request_id),
        )

    def _print_qr_labels(self):
        """Download and open a QR-label sheet for the current filter."""
        from urllib.parse import urlencode
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        params = {}
        if text := self.search.text().strip():
            params['search'] = text
        if series := self.series.currentData():
            params['series'] = series
        if role := self.role.currentData():
            params['role'] = role
        path = 'catalog/listings/qr_labels/'
        if params:
            path += '?' + urlencode(params)

        self.qr_btn.setEnabled(False)
        self.qr_btn.setText(t('Preparing…'))

        def done(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            self.qr_btn.setEnabled(True)
            self.qr_btn.setText(t('Print QR labels'))

        def failed(error):
            self.qr_btn.setEnabled(True)
            self.qr_btn.setText(t('Print QR labels'))
            self._set_status(error.message)

        self.api.download_pdf(path, 'qr_labels.pdf', on_ok=done, on_error=failed)

    def _on_rows(self, payload, request_id=None):
        if request_id is not None and request_id != self._request_id:
            return

        rows = payload.get('results', []) if isinstance(payload, dict) else []
        self.total = payload.get('count', len(rows)) if isinstance(payload, dict) else 0
        self.model.set_rows(rows)

        if not rows:
            self._set_status(t('No profiles match these filters.'))
        else:
            self.status.hide()

        self.count.setText(f'{self.total:,} {t("profiles")}')
        self._update_pager()
        self._update_upload_enabled()
        self._load_thumbs()

    def _on_error(self, error, request_id=None):
        if request_id is not None and request_id != self._request_id:
            return
        self.model.set_rows([])
        self._set_status(error.message)
        self.count.setText('')

    def _set_status(self, message):
        self.status.setText(message)
        self.status.show()

    # -- thumbnails & image upload ---------------------------------------

    def _load_thumbs(self):
        """Fetch each visible row's section image off the UI thread, once."""
        for row in self.model.rows:
            url = row.get('section_image')
            if not url or url in self.model._thumbs or url in self._thumb_requested:
                continue
            self._thumb_requested.add(url)
            self.api.fetch_binary(
                url,
                on_ok=lambda data, u=url: self._on_thumb(u, data),
                on_error=lambda _err, u=url: self._thumb_requested.discard(u),
            )

    def _on_thumb(self, url, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.model.set_thumb(
                url,
                pixmap.scaled(THUMB_W, THUMB_H, Qt.KeepAspectRatio,
                              Qt.SmoothTransformation),
            )

    def _selected_row(self):
        index = self.table.currentIndex()
        return self.model.row_at(index) if index.isValid() else None

    def _update_upload_enabled(self, *_):
        has = self._selected_row() is not None
        if self._is_manager:
            self.upload_btn.setEnabled(has)
        if self._pick_mode:
            self.add_to_order_btn.setEnabled(has)

    def _pick_selected(self):
        row = self._selected_row()
        if row:
            self.profile_picked.emit(row)

    def _on_row_activated(self, index):
        row = self.model.row_at(index)
        if row:
            self._upload_for_row(row)

    def _upload_selected(self):
        row = self._selected_row()
        if row:
            self._upload_for_row(row)

    def _upload_for_row(self, row):
        number = row.get('number')
        if not number:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, t('Choose section image'), '', t(IMAGE_FILTER)
        )
        if not path:
            return
        self._set_status(t('Uploading…'))
        self.api.upload(
            f'catalog/profiles/{number}/section_image/', path, 'image',
            on_ok=self._on_upload_done, on_error=self._on_error,
        )

    def _on_upload_done(self, payload):
        # The stored file may reuse a name we have already cached, so drop the
        # old thumbnail and reload so the new image is fetched fresh.
        url = payload.get('section_image') if isinstance(payload, dict) else None
        if url:
            self.model._thumbs.pop(url, None)
            self._thumb_requested.discard(url)
        self.status.hide()
        self.reload()

    # -- paging ----------------------------------------------------------

    def _page_count(self):
        return max(1, -(-self.total // PAGE_SIZE))

    def _step_page(self, delta):
        target = self.page + delta
        if 1 <= target <= self._page_count():
            self.page = target
            self.reload()

    def _update_pager(self):
        pages = self._page_count()
        self.page_label.setText(f'{self.page} / {pages}')
        self.prev.setEnabled(self.page > 1)
        self.next.setEnabled(self.page < pages)
        visible = self.total > PAGE_SIZE
        for widget in (self.prev, self.next, self.page_label):
            widget.setVisible(visible)

    def _clear_filters(self):
        for widget in (self.search,):
            widget.blockSignals(True)
            widget.clear()
            widget.blockSignals(False)
        for combo in (self.series, self.role, self.tracks, self.glass):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        # Back to "All series": restore the global role list, reset the price
        # editor, and reload -- the same path a real series change takes.
        self._on_series_changed()

    # -- i18n ------------------------------------------------------------

    def retranslate(self):
        self.title.setText(t('Catalog'))
        self.search.setPlaceholderText(t('Search profiles'))
        self.clear.setText(t('Clear filters'))
        self.price_label.setText(t('₪/kg'))
        self.upload_btn.setText(t('Upload image'))
        self.qr_btn.setText(t('Print QR labels'))
        self.add_to_order_btn.setText(t('Add to order'))
        # Placeholder depends on whether a series is selected; _sync sets the
        # right one in the current language.
        self._sync_price_editor()

        # The "All ..." entry of each filter is index 0 and holds no data, so
        # it can be relabelled in place without disturbing the user's current
        # selection.
        for combo, label in (
            (self.series, 'All series'),
            (self.role, 'All roles'),
            (self.tracks, 'Any tracks'),
            (self.glass, 'Any thickness'),
        ):
            if combo.count():
                combo.setItemText(0, t(label))

        self._fill_roles()

        self.count.setText(f'{self.total:,} {t("profiles")}' if self.total else '')

        if self.status.isVisible() and not self.model.rowCount():
            self.status.setText(t('No profiles match these filters.'))

        # Column headers and the translated role column both come from the
        # model, so redraw the whole view rather than just the header.
        self.model.headerDataChanged.emit(Qt.Horizontal, 0,
                                          len(ListingModel.COLUMNS) - 1)
        self.model.layoutChanged.emit()
