"""Visual theme — a single Qt style sheet applied to the whole app.

Deliberately restrained: this is a tool people use all day, so the palette is
mostly neutral with one accent colour, and density is tuned for reading long
tables of profile numbers rather than for looking impressive in a screenshot.
"""

# Steel blue accent, picked to sit naturally next to aluminium product photos.
ACCENT = '#2F6F8F'
ACCENT_DARK = '#245972'
ACCENT_LIGHT = '#E8F1F6'
# A lighter accent that stays legible on the dark brand panel.
ACCENT_ON_DARK = '#5AA9CC'

INK = '#1C2530'
INK_MUTED = '#6B7785'
LINE = '#DDE3E9'
SURFACE = '#FFFFFF'
CANVAS = '#F5F7F9'
DANGER = '#B3261E'

FONT_STACK = '"Segoe UI", "Helvetica Neue", "Arial", "Noto Sans Hebrew", sans-serif'

STYLESHEET = f"""
* {{
    font-family: {FONT_STACK};
    color: {INK};
}}

QWidget#Canvas       {{ background: {CANVAS}; }}
QWidget#Surface      {{ background: {SURFACE}; }}

/* Dialogs carry the app's own light background, so they read correctly even
   when macOS is in dark mode (otherwise the dark system window shows through
   behind our dark form text). */
QDialog {{ background: {CANVAS}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

/* ---------- Sidebar ---------- */

QWidget#Sidebar {{
    background: {INK};
    border: none;
}}
QLabel#Brand {{
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 600;
    padding: 22px 20px 6px 20px;
}}
QLabel#BrandSub {{
    color: #8A96A3;
    font-size: 11px;
    padding: 0 20px 18px 20px;
}}

/* The notification bell, top of the sidebar beside the wordmark. Flat until
   pointed at, so an empty bell is quiet and a badged one is the only thing
   drawing the eye up there. */
QPushButton#Bell {{
    background: transparent;
    border: none;
    border-radius: 8px;
    font-size: 15px;
}}
QPushButton#Bell:hover  {{ background: rgba(255, 255, 255, 0.10); }}
QPushButton#Bell:pressed {{ background: rgba(255, 255, 255, 0.16); }}

QPushButton#NavButton {{
    color: #C3CBD4;
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 11px 16px;
    margin: 2px 10px;
    font-size: 13.5px;
    text-align: left;
}}
QPushButton#NavButton:hover  {{ background: #29323D; color: #FFFFFF; }}
QPushButton#NavButton:checked{{ background: {ACCENT}; color: #FFFFFF; font-weight: 600; }}

QLabel#UserName {{ color: #FFFFFF; font-size: 13px; font-weight: 600; }}
QLabel#UserRole {{ color: #8A96A3; font-size: 11px; }}

QPushButton#SignOut {{
    color: #C3CBD4;
    background: transparent;
    border: 1px solid #3A4552;
    border-radius: 6px;
    padding: 7px 12px;
    font-size: 12px;
}}
QPushButton#SignOut:hover {{ background: #29323D; color: #FFFFFF; }}

/* ---------- Header ---------- */

QLabel#PageTitle  {{ font-size: 21px; font-weight: 600; }}
QLabel#PageCount  {{ color: {INK_MUTED}; font-size: 13px; }}

/* ---------- Inputs ---------- */

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QAbstractSpinBox {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 8px 11px;
    font-size: 13px;
    min-height: 18px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QAbstractSpinBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QDateEdit:disabled {{
    background: {CANVAS}; color: {INK_MUTED};
}}
QLineEdit::placeholder {{ color: {INK_MUTED}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE};
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {INK};
    outline: none;
}}
/* Spin buttons: keep them light so the arrows are visible on any OS theme. */
QSpinBox::up-button, QDoubleSpinBox::up-button, QAbstractSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button, QAbstractSpinBox::down-button {{
    background: {CANVAS}; border: none; width: 18px;
}}

/* Radio buttons and checkboxes — keep their labels readable in dark mode. */
QRadioButton, QCheckBox {{ color: {INK}; font-size: 13px; spacing: 6px; }}

/* Calendar popup for the date picker. */
QCalendarWidget QWidget {{ background: {SURFACE}; color: {INK}; }}
QCalendarWidget QAbstractItemView {{
    background: {SURFACE}; color: {INK};
    selection-background-color: {ACCENT}; selection-color: #FFFFFF;
    outline: none;
}}
QCalendarWidget QToolButton {{ color: {INK}; background: transparent; }}
QCalendarWidget QToolButton:hover {{ background: {ACCENT_LIGHT}; border-radius: 4px; }}
QCalendarWidget QMenu {{ background: {SURFACE}; color: {INK}; }}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {ACCENT}; }}
QCalendarWidget QToolButton#qt_calendar_prevmonth,
QCalendarWidget QToolButton#qt_calendar_nextmonth,
QCalendarWidget QToolButton#qt_calendar_monthbutton,
QCalendarWidget QToolButton#qt_calendar_yearbutton {{ color: #FFFFFF; }}

/* Table widgets (used by the order editor) match the styled table views. */
QTableWidget {{
    background: {SURFACE};
    color: {INK};
    border: 1px solid {LINE};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {INK};
    font-size: 13px;
}}
QTableWidget::item {{ padding: 8px 10px; border-bottom: 1px solid #EFF2F5; }}

/* ---------- Buttons ---------- */

QPushButton {{
    background: {ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover    {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ background: #A9BAC5; }}

QPushButton#Ghost {{
    background: transparent;
    color: {INK_MUTED};
    border: 1px solid {LINE};
}}
QPushButton#Ghost:hover {{ background: {CANVAS}; color: {INK}; }}

/* ---------- Table ---------- */

QTableView {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: {ACCENT_LIGHT};
    selection-color: {INK};
    font-size: 13px;
}}
QTableView::item {{ padding: 9px 10px; border-bottom: 1px solid #EFF2F5; }}
QHeaderView::section {{
    background: {CANVAS};
    color: {INK_MUTED};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 10px;
    font-size: 11.5px;
    font-weight: 600;
    text-transform: uppercase;
}}
QTableCornerButton::section {{ background: {CANVAS}; border: none; }}

QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #C6CED6; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #AEB8C2; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* ---------- Dashboard ---------- */

QFrame#StatTile {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QFrame#StatTile[accent="true"] {{
    background: {ACCENT};
    border: none;
}}
QLabel#StatValue {{ font-size: 30px; font-weight: 700; }}
QLabel#StatValue[muted="true"] {{ color: {INK_MUTED}; font-weight: 500; font-size: 24px; }}
QLabel#StatCaption {{ color: {INK_MUTED}; font-size: 12.5px; }}
QLabel#StatSub {{ color: {INK_MUTED}; font-size: 11.5px; }}

QFrame#StatTile[accent="true"] QLabel#StatValue,
QFrame#StatTile[accent="true"] QLabel#StatCaption,
QFrame#StatTile[accent="true"] QLabel#StatSub {{ color: #FFFFFF; }}
QFrame#StatTile[accent="true"] QLabel#StatCaption,
QFrame#StatTile[accent="true"] QLabel#StatSub {{ color: #DCEAF1; }}

QFrame#Panel {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QLabel#PanelHeading {{ font-size: 14px; font-weight: 600; }}
QLabel#OnlineDot {{ color: #2E9E5B; font-size: 12px; }}

/* ---------- Login ---------- */

QWidget#LoginRoot {{ background: {SURFACE}; }}

/* Branded panel */
QWidget#BrandPanel {{
    background: qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 #22303F, stop:1 {INK});
}}
QLabel#BrandMark {{
    color: {ACCENT_ON_DARK};
    font-size: 40px;
}}
QLabel#BrandWordmark {{
    color: #FFFFFF;
    font-size: 30px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#BrandTagline {{
    color: #A9B7C4;
    font-size: 15px;
    line-height: 150%;
}}
QLabel#BrandFooter {{
    color: #63707D;
    font-size: 12px;
}}

/* Form side */
QWidget#FormPanel {{ background: {CANVAS}; }}

QFrame#LoginCard {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
QLabel#LoginTitle {{ font-size: 23px; font-weight: 700; }}
QLabel#LoginHint  {{ color: {INK_MUTED}; font-size: 13px; }}
QLabel#FieldLabel {{ color: {INK}; font-size: 12.5px; font-weight: 600; }}

QFrame#LoginCard QLineEdit {{
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 0 12px;
    font-size: 14px;
    background: {SURFACE};
}}
QFrame#LoginCard QLineEdit:focus {{
    border: 1.5px solid {ACCENT};
    background: #FCFDFE;
}}

QPushButton#PrimaryButton {{
    background: {ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    font-size: 14.5px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover    {{ background: {ACCENT_DARK}; }}
QPushButton#PrimaryButton:pressed  {{ background: #1D4A5F; }}
QPushButton#PrimaryButton:disabled {{ background: #A9BAC5; }}

QComboBox#LangSelect {{
    background: transparent;
    border: 1px solid {LINE};
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 12.5px;
    color: {INK_MUTED};
}}
QComboBox#LangSelect:hover {{ border: 1px solid {ACCENT}; }}

QLabel#Error      {{ color: {DANGER}; font-size: 12.5px; }}
QLabel#Muted      {{ color: {INK_MUTED}; font-size: 13px; }}

/* ---------- Forms: labels, sections, inline validation ---------- */

QLabel#FieldLabel {{ color: {INK_MUTED}; font-size: 12px; font-weight: 600; }}
QLabel#FieldError {{ color: {DANGER}; font-size: 11.5px; }}
QLabel#FieldWarn  {{ color: #8A6D1F; font-size: 11.5px; }}
QLabel#SectionTitle {{
    color: {INK};
    font-size: 13px;
    font-weight: 700;
    padding-top: 2px;
}}
QFrame#SectionRule {{ background: {LINE}; max-height: 1px; min-height: 1px; border: none; }}

/* Settings cards: a titled white panel grouping related fields. */
QFrame#SettingsCard {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 12px;
}}
/* A notification in the list. Unread is tinted rather than given a side
   border, so it looks the same in Hebrew as in English. */
QFrame#NotificationCard {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 10px;
}}
QFrame#NotificationCard[unread="true"] {{
    background: {ACCENT_LIGHT};
    border-color: #CFE0EA;
}}

QLabel#CardTitle {{ color: {INK}; font-size: 15px; font-weight: 700; }}
QLabel#CardHint  {{ color: {INK_MUTED}; font-size: 12.5px; }}
QLabel#CardIcon  {{ font-size: 17px; }}

/* Compact numeric cells in the salary calculator grid. Tighter padding than a
   normal input so seven digits fit, with a soft fill that lifts on focus. */
QAbstractSpinBox#CalcCell {{
    padding: 4px 8px;
    min-height: 22px;
    background: {CANVAS};
    border: 1px solid {LINE};
    border-radius: 6px;
    font-size: 13px;
}}
QAbstractSpinBox#CalcCell:focus {{ background: {SURFACE}; border: 1px solid {ACCENT}; }}
QAbstractSpinBox#CalcCell:hover  {{ border: 1px solid {ACCENT_LIGHT}; }}

/* Headline figure cards (e.g. client statement totals). */
QFrame#StatCard {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 12px;
    min-width: 200px;
}}
QLabel#StatCaption {{ color: {INK_MUTED}; font-size: 12px; }}
QLabel#StatValue   {{ color: {ACCENT}; font-size: 24px; font-weight: 800; }}
QLabel#StatNote    {{ color: {INK_MUTED}; font-size: 11.5px; }}

/* Company-logo preview box in Settings. */
QLabel#LogoPreview {{
    border: 1px dashed {LINE};
    border-radius: 8px;
    background: {CANVAS};
    color: {INK_MUTED};
    font-size: 11.5px;
    padding: 4px;
}}

/* Live connection status line in Settings. */
QLabel#ConnStatus {{ font-size: 12.5px; font-weight: 600; color: {INK_MUTED}; }}
QLabel#ConnStatus[state="ok"]       {{ color: #2E7D32; }}
QLabel#ConnStatus[state="bad"]      {{ color: {DANGER}; }}
QLabel#ConnStatus[state="checking"] {{ color: {INK_MUTED}; }}

/* Segmented toggle (e.g. Payslips | Calculator). */
QPushButton#Segment {{
    background: {SURFACE};
    color: {INK_MUTED};
    border: 1px solid {LINE};
    padding: 8px 20px;
    font-weight: 600;
}}
QPushButton#Segment:first-child {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QPushButton#Segment:last-child  {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; border-left: none; }}
QPushButton#Segment:checked {{ background: {ACCENT}; color: #FFFFFF; border-color: {ACCENT}; }}

/* Compact ghost button for dense table-cell actions. */
QPushButton#SmallGhost {{
    background: transparent;
    color: {ACCENT};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12px;
    font-weight: 600;
    min-height: 0;
}}
QPushButton#SmallGhost:hover {{ background: {ACCENT_LIGHT}; }}
QPushButton#SmallGhost:disabled {{ color: #A9BAC5; }}

/* A field flagged invalid gets a red border; warned gets amber. */
QLineEdit[state="invalid"], QComboBox[state="invalid"],
QPlainTextEdit[state="invalid"] {{ border: 1px solid {DANGER}; }}
QLineEdit[state="warn"], QComboBox[state="warn"],
QPlainTextEdit[state="warn"] {{ border: 1px solid #C79A2E; }}
QLineEdit:focus[state="invalid"], QComboBox:focus[state="invalid"] {{ border: 1px solid {DANGER}; }}

QPlainTextEdit {{
    background: {SURFACE};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {ACCENT};
}}
QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
"""
