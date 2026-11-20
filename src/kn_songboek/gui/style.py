"""Comfortable sizes for people who do not use a computer every day (ADR-0008, UX point 2).

Bigger letters, taller rows and buttons that are easy to hit. Apple asks for at least 44 points for
anything you click; list rows are a little lower (about 34) so a folder of 20 slots still fits.
Applied once to the whole application, so every window and dialog gets it.
"""
from __future__ import annotations

BASE_POINT_SIZE = 15            # macOS default is 13, most Linux desktops 10-11
ROW_HEIGHT = 34                 # rows in song and library tables
BUTTON_HEIGHT = 34

# Weergave › Lettergrootte: everything (letters, rows, buttons) grows with it. Chosen before the window
# is built (set_text_size), because many parts take their size from the letters when they are made.
TEXT_SIZES = {"normal": 1.0, "large": 1.15, "xlarge": 1.3}
_scale = 1.0


def set_text_size(name: str) -> None:
    global _scale
    _scale = TEXT_SIZES.get(name, 1.0)


def px(n: int) -> int:
    """A size in pixels, grown with the chosen text size."""
    return int(round(n * _scale))


def row_height() -> int:
    return px(ROW_HEIGHT)


def _sizes() -> str:
    """Sizes at "Normaal"; sheet() grows them with the chosen text size."""
    return """
QPushButton { min-height: %(button)dpx; padding: 2px 14px; }
QListView::item { min-height: %(row)dpx; padding: 0 6px; }
QTreeView::item { min-height: %(tree)dpx; }
QLineEdit, QComboBox, QSpinBox { min-height: %(field)dpx; }
QTabBar::tab { min-height: %(field)dpx; padding: 4px 14px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }
""" % {"button": BUTTON_HEIGHT, "row": ROW_HEIGHT - 6, "tree": ROW_HEIGHT - 10, "field": 30}


def sheet(text: str) -> str:
    """A style sheet with every size in px grown with the chosen text size (Weergave › Lettergrootte).
    The one way to write a style sheet in this app: the app's own and any widget's (setStyleSheet).
    1px lines stay 1px."""
    import re
    return re.sub(r"(?<![\w.])(\d+)px", lambda m: "%dpx" % (px(int(m.group(1))) if int(m.group(1)) > 1 else 1), text)

# Our own colours, one set for a light and one for a dark system setting (macOS: System Settings >
# Appearance). Everything else (windows, lists, plain buttons) follows the system by itself. Each pair
# of text and background has a contrast of at least 4.5:1 (WCAG AA), also in dark mode.
LIGHT = {
    "accent": "#1f6fd1", "accent_hover": "#185bb0", "on_accent": "#ffffff", "accent_text": "#1a5fb4",
    "ok": "#237a3d", "warn": "#e08a00", "bad": "#d33a2c", "meter_ok": "#2e9d4f",
    "note_bg": "#e3efff", "note_border": "#9cc2f2", "note_text": "#10325c",
    "draft_bg": "#fff3c4", "draft_border": "#e0b030", "draft_text": "#3a3000",
    "off_bg": "#e9dca4", "off_text": "#6b5c14",
    "toast_bg": "#2b2b2b", "toast_text": "#ffffff", "toast_link": "#8cc4ff",
    "drop": "#f2b600",
    "lib_bg": "#eaf2ec", "lib_border": "#a9c9b1", "card_bg": "#e9eff8", "card_border": "#a7bddb",
    "band_top": "#1d3557", "band_bottom": "#274b7a", "band_text": "#ffffff", "band_sub": "#c4d5ee",
    "task_bg": "#ffffff", "task_border": "#d6d6d6", "task_hover": "#f5f8fc",
    "task1": "#1f6fd1", "task1_bg": "#e3efff", "task2": "#237a3d", "task2_bg": "#e3f3e7",
    "task3": "#b86e00", "task3_bg": "#fff1d6",
}
DARK = {
    "accent": "#2f74d0", "accent_hover": "#4a8ae0", "on_accent": "#ffffff", "accent_text": "#7ab4ff",
    "ok": "#5cc97a", "warn": "#f0a030", "bad": "#ff6b5e", "meter_ok": "#3fb862",
    "note_bg": "#1c2c43", "note_border": "#3a5f8f", "note_text": "#dce9ff",
    "draft_bg": "#3b3215", "draft_border": "#9a7d22", "draft_text": "#ffeaa8",
    "off_bg": "#4a4228", "off_text": "#c9b98a",
    "toast_bg": "#ececec", "toast_text": "#1a1a1a", "toast_link": "#0a58c2",
    "drop": "#ffcf33",
    "lib_bg": "#1f2b23", "lib_border": "#3f6b4b", "card_bg": "#1d2533", "card_border": "#3d5a85",
    "band_top": "#13233a", "band_bottom": "#1c3556", "band_text": "#ffffff", "band_sub": "#b3c7e6",
    "task_bg": "#2a2a2a", "task_border": "#444444", "task_hover": "#323842",
    "task1": "#5e9eee", "task1_bg": "#1c2c43", "task2": "#5cc97a", "task2_bg": "#1d3324",
    "task3": "#f0a030", "task3_bg": "#3b2e15",
}

# Colour only where it means something: blue (accent) for the one thing to do next (Op kaart zetten,
# the OK of a question), yellow for "not on the card yet", orange for "look out / not sure", green and
# red on the fullness meter. The tip's "Begrepen" only closes a tip, so it stays quiet.
COLOURS = """
*[role="muted"] { color: %(muted)s; }
*[role="primary"], QFrame#draft QPushButton {
    background: %(accent)s; color: %(on_accent)s; font-weight: bold; border: none; border-radius: 6px;
    padding: 6px 20px; }
*[role="primary"]:hover, QFrame#draft QPushButton:hover {
    background: %(accent_hover)s; }
QFrame#tip QPushButton {
    background: transparent; color: %(note_text)s; border: 1px solid %(note_border)s; border-radius: 6px;
    padding: 6px 20px; }
QFrame#tip QPushButton:hover { background: %(note_border)s; }
QFrame#draft QPushButton:disabled { background: %(off_bg)s; color: %(off_text)s; }
QFrame#tip { background: %(note_bg)s; border: 1px solid %(note_border)s; border-radius: 6px; }
QFrame#tip QLabel { color: %(note_text)s; background: transparent; }
QFrame#draft { background: %(draft_bg)s; border: 1px solid %(draft_border)s; border-radius: 4px; }
QFrame#draft QLabel { color: %(draft_text)s; background: transparent; }
QFrame#renamed { background: %(draft_bg)s; border: 1px solid %(draft_border)s; border-radius: 6px; }
QFrame#renamed QLabel { color: %(draft_text)s; background: transparent; border: none; }
QFrame#toast { background: %(toast_bg)s; border-radius: 10px; }
QFrame#toast QLabel { color: %(toast_text)s; background: transparent; }
QFrame#toast QPushButton { color: %(toast_link)s; background: transparent; border: none; font-weight: bold;
    padding: 4px 8px; }
QFrame#toast QPushButton:hover { color: %(toast_text)s; }
QFrame#info { border-left: 1px solid %(line)s; }
QPushButton#link { border: none; background: transparent; color: %(accent_text)s; text-decoration: underline;
    min-height: 0; padding: 4px 8px; }
QPushButton#link:hover { color: %(text)s; }
QFrame#libpanel { background: %(lib_bg)s; border: 1px solid %(lib_border)s; border-radius: 8px; }
QFrame#libpanel QLabel, QFrame#libpanel QCheckBox { background: transparent; }
QFrame#cardpanel { background: %(card_bg)s; border: 1px solid %(card_border)s; border-radius: 8px; }
QFrame#cardpanel QLabel, QFrame#cardpanel QCheckBox { background: transparent; }
QFrame#startband { border: none; background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
    stop:0 %(band_top)s, stop:1 %(band_bottom)s); }
QFrame#startband QLabel { background: transparent; color: %(band_text)s; }
QFrame#startband QLabel[role="sub"] { color: %(band_sub)s; }
QPushButton#task { background: %(task_bg)s; border: 1px solid %(task_border)s; border-radius: 14px;
    text-align: left; padding: 0; }
QPushButton#task:hover { background: %(task_hover)s; }
QPushButton#task:pressed { background: %(task1_bg)s; }
QPushButton#task[task="2"]:pressed { background: %(task2_bg)s; }
QPushButton#task[task="3"]:pressed { background: %(task3_bg)s; }
QPushButton#task QLabel { background: transparent; color: %(text)s; }
QLabel#libsummary { color: %(muted)s; }
QFrame#practice { background: %(draft_bg)s; border: 2px solid %(warn)s; border-radius: 8px; }
QFrame#practice QLabel { color: %(draft_text)s; background: transparent; border: none; }
QFrame#donebox { border: 1px solid %(line)s; border-radius: 6px; }
QFrame#donebox QLabel { border: none; background: transparent; }
QFrame[role="line"] { color: %(line)s; }
QLabel[step="done"], QLabel[role="ok"] { color: %(ok)s; }
QLabel[role="warn"] { color: %(warn)s; }
QLabel[step="now"] { color: %(accent_text)s; font-weight: bold; }
QLabel[step="todo"] { color: %(muted)s; }
QLabel[step="busy"] { color: %(text)s; font-weight: bold; }
QFrame#stephead { background: %(band)s; border: none; border-bottom: 1px solid %(line)s; }
QFrame#stephead QLabel { background: transparent; }
QTabBar::tab { background: transparent; color: %(muted)s; border: none; border-bottom: 3px solid transparent;
    margin: 0 4px; }
QTabBar::tab:hover { color: %(text)s; }
QTabBar::tab:selected { color: %(text)s; font-weight: bold; border-bottom: 3px solid %(accent)s; }
QMainWindow::separator { width: 10px; height: 10px; background: transparent; }
QMainWindow::separator:hover { background: %(accent)s; }
QProgressBar#busybar { border: none; border-radius: 3px; background: %(line)s; }
QProgressBar#busybar::chunk { border-radius: 3px; background: %(accent)s; }
QProgressBar#meter { border: none; border-radius: 5px; background: %(line)s; }
QProgressBar#meter::chunk { border-radius: 5px; background: %(meter_ok)s; }
QProgressBar#meter[level="warn"]::chunk { background: %(warn)s; }
QProgressBar#meter[level="full"]::chunk { background: %(bad)s; }
QFrame#infoline { color: %(line)s; }
QToolButton#infohead { border: none; background: transparent; font-weight: bold; padding: 2px 0; }
QPushButton#bankchip, QPushButton#viewchip { background: %(chip)s; color: %(text)s; border: none;
    border-radius: 5px; padding: 2px 10px; min-height: 24px; font-weight: bold; }
QPushButton#bankchip:checked, QPushButton#viewchip:checked { background: %(accent)s; color: %(on_accent)s; }
QPushButton#bankchip[empty="true"] { color: %(muted)s; font-weight: normal; }
QPushButton#regbtn { background: %(chip)s; color: %(text)s; border: 1px solid transparent; border-radius: 5px;
    padding: 4px 6px; min-height: 40px; text-align: left; font-size: %(regbtn)dpx; }
QPushButton#regbtn:checked { background: %(note_bg)s; color: %(note_text)s; border: 1px solid %(accent)s; }
QPushButton#regbtn[empty="true"] { color: %(muted)s; }
QLabel#regdetail { border: 1px solid %(line)s; border-radius: 6px; padding: 6px 8px; }
"""

_listeners: list = []


def _mix(a, b, share: float):
    from PySide6.QtGui import QColor
    return QColor(round(a.red() * (1 - share) + b.red() * share),
                  round(a.green() * (1 - share) + b.green() * share),
                  round(a.blue() * (1 - share) + b.blue() * share))


def is_dark(app=None) -> bool:
    """True when the system (and so the window background) is dark."""
    from PySide6.QtGui import QGuiApplication, QPalette
    app = app or QGuiApplication.instance()
    if app is None:
        return False
    return app.palette().color(QPalette.Window).lightness() < 128


def colours(app=None) -> dict:
    """The colour set for the current system setting, plus 'muted' (secondary text) and 'line'
    taken from the system's own text and background colours, so they fit any theme."""
    from PySide6.QtGui import QGuiApplication, QPalette
    app = app or QGuiApplication.instance()
    c = dict(DARK if is_dark(app) else LIGHT)
    if app is not None:
        pal = app.palette()
        text, window = pal.color(QPalette.WindowText), pal.color(QPalette.Window)
        c["text"] = text.name()
        c["muted"] = _mix(text, window, 0.42).name()           # still 4.5:1 on the window, light and dark
        c["line"] = _mix(text, window, 0.78).name()
        c["chip"] = _mix(text, window, 0.9).name()
        c["band"] = pal.color(QPalette.Base).name()           # the step window's top band (white in light)
    else:
        c["muted"], c["line"], c["text"], c["chip"] = "#6e6e6e", "#cfcfcf", "#000000", "#e6e6e6"
        c["band"] = "#ffffff"
    return c


def colour(name: str):
    """One of the colours as a QColor (for list items and painting)."""
    from PySide6.QtGui import QColor
    return QColor(colours()[name])


def on_change(callback) -> None:
    """Call callback() after the system switches between light and dark."""
    _listeners.append(callback)


def _restyle(app) -> None:
    text = sheet(_sizes() + COLOURS % dict(colours(app), regbtn=13))
    if app.styleSheet() != text:
        app.setStyleSheet(text)
        for cb in list(_listeners):
            try:
                cb()
            except RuntimeError:                               # its window is gone
                _listeners.remove(cb)


# Widget kinds that can get a font of their own from the system (on macOS: smaller letters for list
# headers, menus, tooltips, tabs, small print in message boxes…). They all get the app's letter size, so
# Weergave › Lettergrootte reaches every part of the window, not only the plain labels.
FONT_CLASSES = ("QWidget", "QAbstractItemView", "QListView", "QTreeView", "QTableView", "QHeaderView",
                "QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox", "QComboMenuItem",
                "QComboLineEdit", "QLineEdit", "QTextEdit", "QTextBrowser", "QLabel", "QGroupBox", "QTabBar",
                "QMenu", "QMenuBar", "QTipLabel", "QToolTip", "QStatusBar", "QDockWidget", "QDockWidgetTitle",
                "QMessageBox", "QMessageBoxLabel", "QDialogButtonBox", "QSmallFont", "QMiniFont", "QSpinBox",
                "QProgressBar", "QListWidget", "QTreeWidget", "QTableWidget")


def _fonts(app) -> None:
    """The one letter size of the app: the system's size, at least BASE_POINT_SIZE, grown with the chosen
    text size, set for the whole app and for every widget kind in FONT_CLASSES (and the tooltips)."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QToolTip
    system = app.property("kn_songboek_system_pt")
    if system is None:
        system = app.font().pointSizeF()
        app.setProperty("kn_songboek_system_pt", system)
    f = QFont(app.font())
    f.setPointSizeF(round(max(float(system), BASE_POINT_SIZE) * _scale))
    if app.font() != f:
        app.setFont(f)
    for cls in FONT_CLASSES:
        if app.font(cls) != f:
            app.setFont(f, cls)
    QToolTip.setFont(f)


def _grown_style(app):
    """The app's own style, with its small pictures (icons in fields and on buttons, check boxes, radio
    buttons, the arrows in lists) grown with the chosen text size, like the letters."""
    from PySide6.QtWidgets import QProxyStyle, QStyle, QStyleFactory
    grow = {QStyle.PM_SmallIconSize, QStyle.PM_ButtonIconSize, QStyle.PM_ListViewIconSize, QStyle.PM_TabBarIconSize,
            QStyle.PM_ToolBarIconSize, QStyle.PM_IndicatorWidth, QStyle.PM_IndicatorHeight,
            QStyle.PM_ExclusiveIndicatorWidth, QStyle.PM_ExclusiveIndicatorHeight, QStyle.PM_MessageBoxIconSize}

    class Grown(QProxyStyle):
        def pixelMetric(self, metric, option=None, widget=None):
            n = super().pixelMetric(metric, option, widget)
            return px(n) if metric in grow else n

    base = QStyleFactory.create(app.style().name()) if app.style().name() else None
    return Grown(base) if base else Grown()


def apply(app) -> None:
    """Set the bigger base font and the style sheet (sizes and colours) on a QApplication, and
    follow the system when it switches between light and dark (idempotent)."""
    if app is None or app.property("kn_songboek_comfort"):
        return
    from PySide6.QtCore import QEvent, QObject, QTimer
    _fonts(app)
    if _scale != 1.0:
        app._kn_songboek_style = _grown_style(app)          # kept: Python must not let go of it
        app.setStyle(app._kn_songboek_style)
    _restyle(app)
    app.setProperty("kn_songboek_comfort", True)

    # The system puts its own (smaller) letters back on lists, tables, labels and buttons when it changes
    # its look: macOS does this right after the app starts, and on light/dark. It tells the windows
    # (ThemeChange), not always the app itself, so every object's events are watched, and the sizes are
    # set again once, a moment later.
    events = (QEvent.ApplicationPaletteChange, QEvent.ThemeChange, QEvent.ApplicationFontChange)

    def again():
        app._kn_songboek_pending = False
        _fonts(app)
        _restyle(app)

    class _Watch(QObject):
        def eventFilter(self, obj, e):
            if e.type() in events and not getattr(app, "_kn_songboek_pending", False):
                app._kn_songboek_pending = True
                QTimer.singleShot(0, again)
            return False

    app._kn_songboek_watch = _Watch(app)
    app.installEventFilter(app._kn_songboek_watch)
    hints = app.styleHints()
    if hasattr(hints, "colorSchemeChanged"):
        hints.colorSchemeChanged.connect(lambda _s: QTimer.singleShot(0, lambda: (_fonts(app), _restyle(app))))


def mark(widget, **props) -> None:
    """Set style properties (role="primary", step="done", level="warn"…) and let the colours follow."""
    for k, v in props.items():
        widget.setProperty(k, v)
    st = widget.style()
    st.unpolish(widget)
    st.polish(widget)


def comfortable_rows(table) -> None:
    """Taller rows for a QTableWidget/QTableView."""
    table.verticalHeader().setDefaultSectionSize(row_height())
    table.verticalHeader().setMinimumSectionSize(row_height())
