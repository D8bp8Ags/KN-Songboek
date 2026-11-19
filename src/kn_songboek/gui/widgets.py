"""Widgets of the main window: drag and drop between lists, the song and folder tables, the library
panel, the start-screen task buttons, the toast and the progress bar in the status bar."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QItemSelectionModel,
    QMimeData,
    QObject,
    QRect,
    QRectF,
    QRegularExpression,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDrag,
    QPainter,
    QPainterPath,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QSplitterHandle,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..formats.inf import NAME_LEN
from . import icons, style

if TYPE_CHECKING:
    from .qt_app import MainWindow

MIME = "application/x-kn-songboek-songs"
MIME_OTHER = "application/x-kn-songboek-other-songs"     # dragged from the second card
MIME_LIB = "application/x-kn-songboek-library"           # dragged from the library (indices into Library.songs)
MIME_FOLDER = "application/x-kn-songboek-folder"         # whole folders dragged in the folder list ("3;5;6")
MIME_LIB_FOLDERS = "application/x-kn-songboek-lib-folders"  # whole folders of a library card ("card\n3;5")


def _numbers(raw: str) -> List[int]:
    return [int(x) for x in raw.split(";") if x.strip().isdigit()]


def _folder_numbers(mime: QMimeData) -> List[int]:
    return _numbers(bytes(mime.data(MIME_FOLDER)).decode())


def _lib_folders(mime: QMimeData) -> Tuple[str, List[int]]:
    card, _, nums = bytes(mime.data(MIME_LIB_FOLDERS)).decode().partition("\n")
    return card, _numbers(nums)
# The yellow bar keeps its own colours in light and dark mode, so everything on it is styled explicitly
# (in dark mode the system would otherwise draw light text on the light yellow).


def _encode(slots) -> QMimeData:
    m = QMimeData()
    m.setData(MIME, QByteArray(";".join("%d:%d" % s for s in slots).encode()))
    return m


def _decode(mime: QMimeData, fmt: str = MIME):
    raw = bytes(mime.data(fmt)).decode()
    return [tuple(int(x) for x in part.split(":")) for part in raw.split(";") if part]


def _ours(e) -> bool:
    md = e.mimeData()
    return md.hasFormat(MIME) or md.hasFormat(MIME_OTHER) or md.hasFormat(MIME_LIB)


def _from_outside(e) -> bool:
    """Songs that are copied in (second card, library), never moved."""
    return e.mimeData().hasFormat(MIME_OTHER) or e.mimeData().hasFormat(MIME_LIB)


def _lib_indices(mime: QMimeData) -> List[int]:
    return [int(x) for x in bytes(mime.data(MIME_LIB)).decode().split(";") if x]


class _Worker(QObject):
    """Runs one job(progress) on a worker thread; reports progress and the end with signals, which Qt
    delivers on the GUI thread (queued connections)."""
    progressed = Signal(int, int, str)
    done = Signal()

    def __init__(self, job):
        super().__init__()
        self.job, self.result, self.error = job, None, None

    def run(self):
        try:
            self.result = self.job(lambda i, n, text: self.progressed.emit(int(i), int(n), str(text)))
        except BaseException as e:          # handed back to the GUI thread and raised there
            self.error = e
        self.done.emit()


def _claim_delete_key(widget_cls):
    """Let a widget handle Del/Backspace itself instead of the window's Delete action (which deletes
    songs): it accepts the ShortcutOverride so the key reaches its keyPressEvent."""
    base = widget_cls.event

    def event(self, e):
        if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            e.accept()
            return True
        return base(self, e)
    widget_cls.event = event
    return widget_cls


COPY_KEYS = Qt.AltModifier | Qt.ControlModifier       # Option or Cmd on macOS, Alt or Ctrl elsewhere


def wants_move(modifiers) -> bool:
    """Songs dropped on another folder are copied (the folders are set lists, a song may be in
    several); holding Option/Alt (or Ctrl/Cmd) moves them instead."""
    return bool(modifiers & COPY_KEYS)


def _accept(e, action) -> None:
    """Accept a drag with an explicit action, so the cursor shows what will really happen
    (a "+" only when copying) instead of whatever the platform proposed."""
    e.setDropAction(action)
    e.accept()


def _start_drag(view: QAbstractItemView, default=Qt.MoveAction) -> None:
    """Start a drag from an item view with our own default action. Qt's own startDrag prefers
    CopyAction when the model allows it, which made every drag show a "+"."""
    idx = view.selectedIndexes()
    if not idx:
        return
    drag = QDrag(view)
    drag.setMimeData(view.mimeData([]))
    drag.exec(Qt.CopyAction | Qt.MoveAction, default)


@_claim_delete_key
class SongListWidget(QListWidget):
    """Song list editor: accepts songs from the main table, reorders by dragging, Del removes."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win = win
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDropIndicatorShown(True)

    def mimeTypes(self):
        return ["application/x-kn-songboek-listrow"]

    def mimeData(self, items):
        m = QMimeData()
        m.setData("application/x-kn-songboek-listrow", QByteArray(str(self.row(items[0])).encode()))
        return m

    def startDrag(self, actions):
        items = self.selectedItems()
        if items:
            drag = QDrag(self)
            drag.setMimeData(self.mimeData(items))
            drag.exec(Qt.MoveAction, Qt.MoveAction)

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasFormat("application/x-kn-songboek-listrow"):
            _accept(e, Qt.MoveAction)              # reordering inside the list
        elif md.hasFormat(MIME):
            _accept(e, Qt.LinkAction)              # the song itself stays where it is
        else:
            e.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        md = e.mimeData()
        it = self.itemAt(e.position().toPoint())
        at = self.row(it) if it is not None else self.count()
        if md.hasFormat("application/x-kn-songboek-listrow"):
            self.win.presenter.move_in_song_list(int(bytes(md.data("application/x-kn-songboek-listrow")).decode()), at)
        elif md.hasFormat(MIME):
            self.win.presenter.add_to_song_list(_decode(md), at)
        e.setDropAction(Qt.IgnoreAction)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.win.presenter.remove_from_song_list([self.row(i) for i in self.selectedItems()])
        else:
            super().keyPressEvent(e)


class ClickLabel(QLabel):
    """A label that can be clicked (the card's name while composing: click to name the new card)."""
    clicked = Signal()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.cursor().shape() == Qt.PointingHandCursor:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


ICON_GAP = "\u2002"                # Qt puts a button's icon almost against its words ("→Verplaatsen")


def gap(text: str) -> str:
    """The words of a button with an icon, with a little room after the icon."""
    return ICON_GAP + text if text else text


class ShrinkButton(QPushButton):
    """A button that never makes the window wider than the screen: when there is not enough room for
    its whole text, a button with an icon shows only the icon, one without is shortened with "…";
    the full text is always the tooltip.
    Without this a row of buttons with big letters made the window about 1600 points wide, wider
    than a laptop screen, so the panels could no longer be dragged."""

    def __init__(self, parent=None, min_width: int = 56):
        super().__init__(parent)
        self._full = ""
        self._min = min_width
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)     # wants its full text, can do with less

    def setText(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self.updateGeometry()
        self._fit()

    def text(self) -> str:
        return self._full

    def full_width(self) -> int:
        """The width the button needs to show its whole text."""
        icon = self.iconSize().width() + style.px(8) if not self.icon().isNull() else 0
        return self.fontMetrics().horizontalAdvance(self._full) + icon + style.px(34)   # 14 + 14 padding, borders

    words_always = False                 # True: never shorter than its whole text (e.g. Ongedaan maken)

    def minimumSizeHint(self) -> QSize:
        return QSize(self.full_width() if self.words_always else self._min, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        return QSize(self.full_width(), super().sizeHint().height())

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        self._fit()

    def _fit(self) -> None:
        icon = self.iconSize().width() + style.px(8) if not self.icon().isNull() else 0
        room = self.width() - icon - style.px(34)
        if self.width() >= self.full_width():
            shown = self._full
        elif icon:                       # a half word ("Verplaatse…") reads worse than the icon alone
            shown = ""
        else:
            shown = self.fontMetrics().elidedText(self._full, Qt.ElideRight, max(room, 0))
        if icon:
            shown = gap(shown)
        if QPushButton.text(self) != shown:
            QPushButton.setText(self, shown)


class ButtonRow(QWidget):
    """ShrinkButtons side by side, or two per row when their whole text does not fit next to each
    other: whole words ("Verplaatsen naar…") instead of half ones. Only when two per row is still too
    narrow do the buttons stay in one row and fall back to their icon (with the text as tooltip)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self.rows = [QHBoxLayout(), QHBoxLayout()]
        for r in self.rows:
            lay.addLayout(r)
        self.buttons: List[ShrinkButton] = []
        self._cols = 0
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)     # never taller than its rows

    def add(self, button: "ShrinkButton") -> None:
        self.buttons.append(button)
        self._cols = 0
        self._place(len(self.buttons))

    def _place(self, cols: int) -> None:
        if cols == self._cols:
            return
        self._cols = cols
        for b in self.buttons:
            for r in self.rows:
                r.removeWidget(b)
        for i, b in enumerate(self.buttons):
            self.rows[min(i // cols, 1)].addWidget(b)
        self.layout().setSpacing(style.px(6) if cols < len(self.buttons) else 0)
        self.layout().invalidate()
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        # the same as one row, whatever is shown now: otherwise two rows would let the panel get
        # narrower, and then back to one row it would be too narrow for its buttons
        gap = max(self.rows[0].spacing(), 0)
        width = sum(b.minimumSizeHint().width() for b in self.buttons) + gap * max(len(self.buttons) - 1, 0)
        return QSize(width, super().minimumSizeHint().height())

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        n = len(self.buttons)
        if not n:
            return
        gap = max(self.rows[0].spacing(), 0)
        w = [b.full_width() for b in self.buttons]
        half = (n + 1) // 2
        need_one = sum(w) + gap * (n - 1)
        need_two = max(sum(w[i:i + half]) for i in range(0, n, half)) + gap * (half - 1)
        # two rows only when that brings the words back; else one row (of icons): no taller for nothing
        self._place(half if need_one > self.width() >= need_two else n)


def user_columns(table: QTableWidget, widths: Dict[int, int]) -> None:
    """Every column can be made wider or narrower by dragging its edge in the header (double-click
    the edge fits the column to its text); the last column takes the room that is left. The widths
    the user chooses are kept (MainWindow saves them) and are not reset when the list is filled again."""
    h = table.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.Interactive)
    h.setStretchLastSection(True)
    h.setMinimumSectionSize(44)
    h.setHighlightSections(False)
    for c, w in widths.items():
        h.resizeSection(c, w)
    table.setProperty("kn_songboek_fitted", False)


def fit_columns_once(table: QTableWidget, columns) -> None:
    """Fit the given columns to their text the first time the table has rows, never after that,
    so a width the user dragged stays."""
    if table.property("kn_songboek_fitted") or table.rowCount() == 0:
        return
    for c in columns:
        table.resizeColumnToContents(c)
    table.setProperty("kn_songboek_fitted", True)


@_claim_delete_key
class FavoriteTable(QTableWidget):
    """The 9 buttons of one favourite bank; drop a song on a row, Del clears it."""

    def __init__(self, win: "MainWindow"):
        super().__init__(9, 1, win)
        self.win = win
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.horizontalHeader().hide()
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setVerticalHeaderLabels([str(i) for i in range(1, 10)])
        style.comfortable_rows(self)

    def dragEnterEvent(self, e):
        _accept(e, Qt.LinkAction) if e.mimeData().hasFormat(MIME) else e.ignore()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, e):
        row = self.rowAt(e.position().toPoint().y())
        slots = _decode(e.mimeData()) if e.mimeData().hasFormat(MIME) else []
        if row >= 0 and slots:
            for i, slot in enumerate(slots[:9 - row]):
                self.win.presenter.set_favorite(row + 1 + i, slot)
        e.setDropAction(Qt.IgnoreAction)
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.currentRow() >= 0:
            self.win.presenter.set_favorite(self.currentRow() + 1, None)
        else:
            super().keyPressEvent(e)


class OtherSongTable(QTableWidget):
    """Songs of the second card: drag source only."""

    def __init__(self, win: "MainWindow"):
        super().__init__(0, 2, win)
        self.win = win
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        style.comfortable_rows(self)

    def mimeTypes(self):
        return [MIME_OTHER]

    def mimeData(self, items):
        slots = []
        for r in sorted({i.row() for i in self.selectedIndexes()}):
            it = self.item(r, 1)
            if it is not None and it.flags() & Qt.ItemIsDragEnabled:
                slots.append(it.data(Qt.UserRole))
        m = QMimeData()
        m.setData(MIME_OTHER, QByteArray(";".join("%d:%d" % s for s in slots).encode()))
        return m

    def startDrag(self, actions):
        _start_drag(self, Qt.CopyAction)


class GripHandle(QSplitterHandle):
    """A splitter handle that can be seen: a thin line with three dots in the middle, blue under the
    mouse, with a resize cursor. Double-click puts the panels back to their usual widths."""

    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(Qt.WA_Hover)
        self.setMouseTracking(True)
        self._hover = False

    def event(self, ev):
        if ev.type() in (QEvent.HoverEnter, QEvent.HoverLeave):
            self._hover = ev.type() == QEvent.HoverEnter
            self.update()
        return super().event(ev)

    def mouseDoubleClickEvent(self, ev):
        sp = self.splitter()
        if getattr(sp, "default_sizes", None):
            sp.setSizes(sp.default_sizes)

    def paintEvent(self, ev):
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = style.colour("accent") if self._hover else style.colour("muted")
        line = QColor(c)
        line.setAlpha(255 if self._hover else 70)
        r = self.rect()
        vertical_bar = self.orientation() == Qt.Horizontal          # panels side by side: a vertical bar
        if vertical_bar:
            p.fillRect(r.center().x(), r.top() + 4, 1 + self._hover, r.height() - 8, line)
        else:
            p.fillRect(r.left() + 4, r.center().y(), r.width() - 8, 1 + self._hover, line)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        for i in (-8, 0, 8):
            if vertical_bar:
                p.drawEllipse(r.center().x() - 2, r.center().y() + i - 2, 5, 5)
            else:
                p.drawEllipse(r.center().x() + i - 2, r.center().y() - 2, 5, 5)
        p.end()


def _chip_height(b: QPushButton) -> None:
    """One line of text plus padding, fixed: the macOS style reports a smaller height than it paints,
    so rows of chips in a grid would overlap."""
    b.ensurePolished()
    b.setFixedHeight(b.fontMetrics().lineSpacing() + style.px(14))


class GripSplitter(QSplitter):
    """QSplitter with GripHandle: wide enough to grab, never collapses a panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.default_sizes = None
        self.setHandleWidth(10)
        self.setChildrenCollapsible(False)
        # while dragging only a line moves; the panels are laid out once, on release. The info panel holds
        # long wrapped texts (all registrations) and laying them out at every pixel made dragging lag.
        self.setOpaqueResize(False)

    def createHandle(self):
        h = GripHandle(self.orientation(), self)
        h.setToolTip(getattr(self, "tip", ""))
        return h

    def set_tip(self, text: str) -> None:
        self.tip = text
        for i in range(1, self.count()):
            self.handle(i).setToolTip(text)


@_claim_delete_key
class FolderList(QListWidget):
    """Folders 1..99; accepts dropped songs, and folders can be dragged to another place. Several
    folders can be chosen (Cmd/Shift-click) and dragged together."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win = win
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragEnabled(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)   # a long name ends in "…" instead
        self.setTextElideMode(Qt.ElideRight)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        # Empty folders are folded away behind one row at the end ("94 lege mappen"), so the folders
        # in use stand out. While something is dragged they are shown, so they still work as targets.
        self.show_empty = False
        self._peeking = False
        self.toggle_item: Optional[QListWidgetItem] = None
        self.itemClicked.connect(lambda it: it is self.toggle_item and self.set_show_empty(not self.show_empty))

    @staticmethod
    def is_folder(item: Optional[QListWidgetItem]) -> bool:
        return item is not None and item.data(Qt.UserRole) is not None

    def fit_width(self) -> None:
        """The list cannot be made narrower than its longest line, so every folder name stays readable
        (names are at most 16 characters). The "…" stays as a fallback for a very small window."""
        fm = self.fontMetrics()
        widest = max((fm.horizontalAdvance(self.item(i).text()) for i in range(self.count())
                      if self.is_folder(self.item(i))), default=0)
        extra = 2 * self.frameWidth() + self.verticalScrollBar().sizeHint().width() + 24   # item padding + margin
        self.setMinimumWidth(min(widest + extra, style.px(360)))

    def set_show_empty(self, on: bool) -> None:
        self.show_empty = on
        self.apply_folding()

    def apply_folding(self) -> None:
        """Hide the empty folders unless they are wanted (toggle, a drag, or the folder shown now)."""
        show = self.show_empty or self._peeking
        hidden = 0
        for i in range(self.count()):
            it = self.item(i)
            if not self.is_folder(it):
                continue
            hide = not show and not it.data(Qt.UserRole + 2) and it is not self.currentItem()
            it.setHidden(hide)
            hidden += not it.data(Qt.UserRole + 2)
        if self.toggle_item is not None:
            t = self.win.presenter.t
            self.toggle_item.setText(t("folders_hide_empty") if self.show_empty else t("folders_show_empty", n=hidden))
            self.toggle_item.setHidden(hidden == 0)

    def _peek(self, on: bool) -> None:
        if on != self._peeking:
            self._peeking = on
            self.apply_folding()

    def keyPressEvent(self, e):
        # Del, or the Mac "delete" key (Backspace): the chosen folders go (after one question)
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.win.presenter.session is not None:
            self.win.presenter.delete_folders(self.chosen_folders())
            return
        super().keyPressEvent(e)

    def chosen_folders(self) -> List[int]:
        """The folder numbers that are chosen, in order; the current one when it is not among them."""
        item = self.currentItem()
        chosen = sorted(it.data(Qt.UserRole) for it in self.selectedItems() if self.is_folder(it) and not it.isHidden())
        if self.is_folder(item) and item.data(Qt.UserRole) not in chosen:
            return [item.data(Qt.UserRole)]
        return chosen

    def startDrag(self, actions):
        chosen = self.chosen_folders()
        if not chosen or self.win.presenter.session is None:
            return
        m = QMimeData()
        m.setData(MIME_FOLDER, QByteArray(";".join(map(str, chosen)).encode()))
        d = QDrag(self)
        d.setMimeData(m)
        d.exec(Qt.MoveAction, Qt.MoveAction)
        # The drag may end anywhere (or be cancelled): reset the view so no folder stays marked and
        # the mouse button is not taken as still held (selection following the pointer, seen on macOS).
        self._clear_drop()
        self.setState(QAbstractItemView.NoState)
        self.viewport().update()

    @staticmethod
    def _folder_drag(e) -> bool:
        return e.mimeData().hasFormat(MIME_FOLDER)

    @staticmethod
    def _lib_folder_drag(e) -> bool:
        return e.mimeData().hasFormat(MIME_LIB_FOLDERS)

    def _wanted(self, e) -> bool:
        return _ours(e) or self._folder_drag(e) or self._lib_folder_drag(e)

    @staticmethod
    def drop_action(e):
        if e.mimeData().hasFormat(MIME_FOLDER):
            return Qt.MoveAction
        if _from_outside(e) or e.mimeData().hasFormat(MIME_LIB_FOLDERS):
            return Qt.CopyAction                   # from the second card or the library: always a copy
        return Qt.MoveAction if wants_move(e.modifiers()) else Qt.CopyAction

    # Drop feedback is only painted (paintEvent), never stored in the items: the item data stays
    # untouched, so nothing can stay highlighted after a drop, a cancelled drag or a refresh.
    # This follows Qt's own drop indicator (on an item: a box, between items: a line).
    _target: Optional[int] = None                  # row the cursor is over
    _insert_before: Optional[int] = None           # folder number to insert in front of (line)
    _dragging_folder = False
    _dragging_n = 1                                # how many folders are dragged

    def _insert_target(self, item: QListWidgetItem, y: int) -> Optional[int]:
        """Where a dragged folder goes, like reordering a playlist: over a folder in use it is put
        in between (the folder number to insert before: upper half = in front of it, lower half =
        after it). Only the middle of an empty folder means "move into this empty folder" (None);
        several folders always go in between, as a block."""
        r = self.visualItemRect(item)
        n = item.data(Qt.UserRole)
        if not item.data(Qt.UserRole + 2) and self._dragging_n == 1:
            edge = max(3, r.height() // 4)
            if r.top() + edge <= y <= r.bottom() - edge:
                return None
        return n if y < r.center().y() else n + 1

    def _show_drop(self, item: Optional[QListWidgetItem], before: Optional[int] = None, action=None) -> None:
        """Where a drop would land (None: nowhere) and what it would do, in the status bar."""
        row = self.row(item) if item is not None else None
        if (row, before) != (self._target, self._insert_before):
            self._target, self._insert_before = row, before
            if item is not None:
                self.scrollToItem(item)
            self.viewport().update()
        bar = self.win.statusBar()
        if item is None:
            bar.clearMessage()
        elif before is not None:
            n = self._dragging_n
            bar.showMessage(self.win.presenter.t("drop_insert_n", n=n) if n > 1 else self.win.presenter.t("drop_insert"))
        elif self._dragging_lib:
            t, n = self.win.presenter.t, self._dragging_n
            free = not item.data(Qt.UserRole + 2)
            bar.showMessage(t("drop_lib_folders", n=n, folder=item.data(Qt.UserRole + 1)) if free
                            else t("drop_lib_folders_free", n=n))
        else:
            key = "drop_copy" if action == Qt.CopyAction else "drop_folder" if self._dragging_folder else "drop_move"
            bar.showMessage(self.win.presenter.t(key, folder=item.data(Qt.UserRole + 1)))

    _dragging_lib = False                          # whole folders from the library

    def _clear_drop(self) -> None:
        self._show_drop(None)
        self._dragging_folder = self._dragging_lib = False
        self._dragging_n = 1

    def drop_rect(self):
        """(kind, rect) of the painted drop feedback, or None: "box" on a folder, "line" between two."""
        if self._target is None or self.item(self._target) is None:
            return None
        r = self.visualItemRect(self.item(self._target))
        if self._insert_before is None:
            return "box", r.adjusted(1, 0, -2, -1)
        y = r.top() if self._insert_before == self.item(self._target).data(Qt.UserRole) else r.bottom() + 1
        return "line", r.adjusted(0, y - r.top() - 1, 0, y - r.bottom() + 1)

    def paintEvent(self, e):
        super().paintEvent(e)
        got = self.drop_rect()
        if got is None:
            return
        from PySide6.QtGui import QPainter, QPen
        kind, r = got
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.Antialiasing)
        colour = style.colour("drop")
        if kind == "box":
            fill = QColor(colour)
            fill.setAlpha(90)
            p.setBrush(fill)
            p.setPen(QPen(colour, 2))
            p.drawRoundedRect(r, 4, 4)
        else:
            y = r.center().y()
            p.setPen(QPen(colour, 3))
            p.drawLine(8, y, self.viewport().width() - 4, y)
            p.setBrush(colour)
            p.drawEllipse(2, y - 3, 6, 6)
        p.end()

    def dragEnterEvent(self, e):
        self._dragging_folder = self._folder_drag(e)
        self._dragging_lib = self._lib_folder_drag(e)
        self._dragging_n = (len(_folder_numbers(e.mimeData())) if self._dragging_folder else
                            len(_lib_folders(e.mimeData())[1]) if self._dragging_lib else 1) or 1
        if self._wanted(e):
            self._peek(True)
            _accept(e, self.drop_action(e))
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        item = self.itemAt(e.position().toPoint()) if self._wanted(e) else None
        if not self.is_folder(item):
            item = None
        if item is None:
            self._show_drop(None)
            e.ignore()
            return
        action = self.drop_action(e)
        before = self._insert_target(item, e.position().toPoint().y()) if self._folder_drag(e) else None
        self._show_drop(item, before, action)
        _accept(e, action)

    def dragLeaveEvent(self, e):
        self._clear_drop()
        self._peek(False)
        e.accept()

    def dropEvent(self, e):
        before = self._insert_before
        self._clear_drop()
        item = self.itemAt(e.position().toPoint())
        QTimer.singleShot(0, lambda: self._peek(False))     # after the presenter has redrawn the list
        if not self.is_folder(item) or not self._wanted(e):
            e.ignore()
            return
        if self._folder_drag(e) and before is not None:
            self.win.presenter.insert_folders(_folder_numbers(e.mimeData()), before)
        elif self._folder_drag(e):
            self.win.presenter.move_folder(_folder_numbers(e.mimeData())[0], item.data(Qt.UserRole))
        elif self._lib_folder_drag(e):
            card, folders = _lib_folders(e.mimeData())
            free = not item.data(Qt.UserRole + 2)
            self.win.presenter.copy_library_folders(card, folders, item.data(Qt.UserRole) if free else None)
        elif e.mimeData().hasFormat(MIME_LIB):
            self.win.presenter.import_from_library(_lib_indices(e.mimeData()), item.data(Qt.UserRole))
        elif e.mimeData().hasFormat(MIME_OTHER):
            self.win.presenter.import_from_other(_decode(e.mimeData(), MIME_OTHER), item.data(Qt.UserRole))
        else:
            copy = not wants_move(e.modifiers())
            self.win.presenter.move_songs(_decode(e.mimeData()), item.data(Qt.UserRole), copy)
        e.setDropAction(Qt.IgnoreAction)
        e.accept()


NAME_MAX = 16                    # what the keyboard can show (core.session.check_name)


def name_field(edit: QLineEdit) -> QLineEdit:
    """Typing stops at 16 characters and only takes what the keyboard can show (plain letters,
    digits and punctuation), so the "too long" message is only a safety net."""
    edit.setMaxLength(NAME_MAX)
    edit.setValidator(QRegularExpressionValidator(QRegularExpression("[ -~]*"), edit))
    return edit


def volume_field(edit: QLineEdit) -> QLineEdit:
    """An SD card's name: typing stops at 11 characters, takes only what a FAT label allows and is
    shown in capitals while typing, so what you see is what the card gets."""
    from ..core.cards import VOLUME_MAX
    edit.setMaxLength(VOLUME_MAX)
    edit.setValidator(QRegularExpressionValidator(QRegularExpression('[^"*+,./:;<=>?\\[\\]|\\\\]*'), edit))

    def upper(text: str) -> None:
        pos = edit.cursorPosition()
        edit.setText("".join(c for c in text.upper() if " " <= c <= "~"))
        edit.setCursorPosition(pos)
    edit.textEdited.connect(upper)
    return edit


def get_name(parent, title: str, label: str, text: str = ""):
    """QInputDialog.getText for a song, folder or bank name, with name_field's limits."""
    dlg = QInputDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setLabelText(label)
    dlg.setInputMode(QInputDialog.TextInput)
    name_field(dlg.findChild(QLineEdit))
    dlg.setTextValue(text[:NAME_MAX])
    ok = dlg.exec() == QDialog.Accepted
    return dlg.textValue(), ok


class EmptySlotDelegate(QStyledItemDelegate):
    """An empty slot is a light dashed box instead of the word "(leeg)": the place is there, like on
    the keyboard, but it does not shout. Editing a name is limited like name_field."""

    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            name_field(editor)
        return editor

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        if index.flags() & Qt.ItemIsDragEnabled:
            return
        from PySide6.QtGui import QPen
        painter.save()
        c = style.colour("muted")
        c.setAlpha(150)
        pen = QPen(c, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(option.rect.adjusted(4, 6, -6, -6), 4, 4)
        painter.restore()


@_claim_delete_key
class SongTable(QTableWidget):
    """The 20 slots of one folder (or search hits); drag source and drop target."""

    def __init__(self, win: "MainWindow"):
        super().__init__(0, 4, win)
        self.win = win
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditKeyPressed | QAbstractItemView.DoubleClicked)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDropIndicatorShown(True)
        self.verticalHeader().hide()
        fm = self.fontMetrics()
        self.name_width = max(fm.horizontalAdvance("Zomeravond 12345"), fm.averageCharWidth() * NAME_LEN) + 30
        self.name_want = self.name_width                 # what the user (or the default) wants for Naam
        self._fitting = False
        user_columns(self, {2: self.name_width})
        self.horizontalHeader().sectionResized.connect(self._resized)
        self.setAlternatingRowColors(True)
        style.comfortable_rows(self)
        self.setItemDelegateForColumn(2, EmptySlotDelegate(self))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self.fit_name)             # after the viewport has its new size

    def _resized(self, col: int, _old: int, new: int) -> None:
        if col == 2 and not self._fitting:               # dragged by the user (or restored): remember it,
            self.name_want = max(new, self.name_width)   # but never less than a whole 16-letter name

    def fit_name(self) -> None:
        """The columns never run past the right edge (no sideways scrolling): when the table is narrower
        than its columns, the Naam column gives way first to the Bestanden column, then as little as it
        must. When there is room again it grows back to the width wanted, so it never stays narrow."""
        h = self.horizontalHeader()
        cols = [c for c in range(self.columnCount()) if not self.isColumnHidden(c)]
        if not cols or self.isColumnHidden(2):
            return
        last = cols[-1]
        others = sum(h.sectionSize(c) for c in cols if c not in (2, last))
        room = self.viewport().width() - others - (h.minimumSectionSize() if last != 2 else 0)
        width = max(min(self.name_want, room), h.minimumSectionSize())
        if h.sectionSize(2) != width:
            self._fitting = True
            try:
                h.resizeSection(2, width)
            finally:
                self._fitting = False

    def keyPressEvent(self, e):
        # The Mac "delete" key is Backspace, which the Delete action (Del) does not catch.
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.state() != QAbstractItemView.EditingState:
            self.win._delete()
            return
        super().keyPressEvent(e)

    def mimeTypes(self):
        return [MIME]

    def mimeData(self, items):
        return _encode(self.win.selected_slots())

    def startDrag(self, actions):
        _start_drag(self, Qt.MoveAction)

    @staticmethod
    def drop_action(e):
        # within a folder a drop always moves/swaps; songs from the second card are copied
        return Qt.CopyAction if _from_outside(e) else Qt.MoveAction

    def dragEnterEvent(self, e):
        _accept(e, self.drop_action(e)) if _ours(e) and not self.win.presenter.query else e.ignore()

    def dragMoveEvent(self, e):
        ok = _ours(e) and not self.win.presenter.query and self.rowAt(e.position().toPoint().y()) >= 0
        _accept(e, self.drop_action(e)) if ok else e.ignore()

    def dropEvent(self, e):
        if not _ours(e) or self.win.presenter.query:
            e.ignore()
            return
        row = self.rowAt(e.position().toPoint().y())
        if row < 0:
            e.ignore()
            return
        dst = self.item(row, 2).data(Qt.UserRole)
        if e.mimeData().hasFormat(MIME_LIB):
            free = not (self.item(row, 2).flags() & Qt.ItemIsDragEnabled)
            self.win.presenter.import_from_library(_lib_indices(e.mimeData()), dst[0], dst[1] if free else None)
            e.setDropAction(Qt.IgnoreAction)
            e.accept()
            return
        if e.mimeData().hasFormat(MIME_OTHER):
            free = not (self.item(row, 2).flags() & Qt.ItemIsDragEnabled)
            self.win.presenter.import_from_other(_decode(e.mimeData(), MIME_OTHER), dst[0], dst[1] if free else None)
            e.setDropAction(Qt.IgnoreAction)
            e.accept()
            return
        slots = _decode(e.mimeData())
        if len(slots) == 1:
            self.win.presenter.drop_on_slot(slots[0], dst)
        elif all(f == dst[0] for f, _ in slots):        # several songs within their folder: a new place
            self.win.presenter.reorder_songs(slots, dst)
        else:
            self.win.presenter.move_songs(slots, dst[0])
        e.setDropAction(Qt.IgnoreAction)      # the presenter moved the data; Qt must not remove rows
        e.accept()


class LibraryTable(QTableWidget):
    """All songs of the library; drag source only. Row data: index into Library.songs."""

    def __init__(self, win: "MainWindow"):
        super().__init__(0, 5, win)
        self.win = win
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().hide()
        self.setAlternatingRowColors(True)
        user_columns(self, {0: 300})
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.AscendingOrder)
        style.comfortable_rows(self)

    def mimeTypes(self):
        return [MIME_LIB]

    def selected_indices(self) -> List[int]:
        rows = sorted({i.row() for i in self.selectedIndexes()})
        return [self.item(r, 0).data(Qt.UserRole) for r in rows if self.item(r, 0) is not None]

    def mimeData(self, items):
        m = QMimeData()
        m.setData(MIME_LIB, QByteArray(";".join(str(i) for i in self.selected_indices()).encode()))
        return m

    def startDrag(self, actions):
        _start_drag(self, Qt.CopyAction)


class LibraryParts(QListWidget):
    """The folders and song lists of the chosen library card. Several folders can be chosen
    (Cmd/Shift-click) and dragged together onto the card, or added with the button below."""

    def __init__(self, panel: "LibraryPanel"):
        super().__init__(panel)
        self.panel = panel
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)

    def chosen_folders(self) -> List[int]:
        """Folder numbers of the chosen rows that are folders (not "Alle songs" or a song list)."""
        rows = sorted({self.row(it) for it in self.selectedItems()})
        out = []
        for r in rows:
            data = self.panel.part.itemData(r)
            if data and data.startswith("folder:"):
                out.append(int(data.split(":")[1]))
        return out

    def startDrag(self, actions):
        card, folders = self.panel.card.currentData(), self.chosen_folders()
        if not card or not folders:
            return
        m = QMimeData()
        m.setData(MIME_LIB_FOLDERS, QByteArray(("%s\n%s" % (card, ";".join(map(str, folders)))).encode()))
        d = QDrag(self)
        d.setMimeData(m)
        d.exec(Qt.CopyAction, Qt.CopyAction)


class PanelHead(QWidget):
    """The heading of a side of the window: "Bibliotheek" or "SD-kaart", big, with one line on what it is."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("panelhead")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, style.px(4))
        lay.setSpacing(0)
        self.name = QLabel(self)
        f = self.name.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.25)
        self.name.setFont(f)
        self.info = QLabel(self)
        self.info.setWordWrap(True)
        style.mark(self.info, role="muted")
        lay.addWidget(self.name)
        lay.addWidget(self.info)

    def set_text(self, name: str, info: str) -> None:
        self.name.setText(name)
        self.info.setText(info)


class LibraryPanel(QFrame):
    """Left side of the window: the library, its search and filters (ADR-0007). A panel of its own colour
    with its own heading, so it is clearly not the SD card: songs are chosen here, nothing changes here."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.setObjectName("libpanel")
        self.win = win
        self.head = PanelHead(self)
        self.title = QLabel(self)
        self.title.setWordWrap(True)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.filter_button = QPushButton(self)          # tempo and "only recorded" are folded away
        self.filter_button.setCheckable(True)
        self.search = QLineEdit(self)
        self.search.setClearButtonEnabled(True)
        self.card = QComboBox(self)
        self.part = QComboBox(self)                 # a folder or song list of the chosen card (the model)
        self.part.hide()
        # The chosen card as on the keyboard: its folders 01..99 in a list, the songs of a folder numbered
        self.parts = LibraryParts(self)
        self.parts.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.parts.setTextElideMode(Qt.ElideRight)
        self.parts.setMinimumWidth(style.px(170))
        self.parts.setMaximumWidth(style.px(240))
        self.parts.currentRowChanged.connect(lambda r: r >= 0 and self.part.setCurrentIndex(r))
        self.parts.itemSelectionChanged.connect(self._update_part_button)
        self.copy_part = ShrinkButton(self, 100)
        self.copy_part.clicked.connect(self._copy_part)
        self.rename_card = ShrinkButton(self, 44)         # give the chosen library card another name
        self.rename_card.clicked.connect(self._rename_card)
        self.remove_card = ShrinkButton(self, 44)        # take the chosen card out of the library (to the bin)
        self.remove_card.clicked.connect(self._remove_card)
        self.recorded = QCheckBox(self)
        self.not_on_card = QCheckBox(self)               # only while a card is open next to the library
        self.damaged = QCheckBox(self)
        self.meter_lbl = QLabel(self)
        self.meter = QComboBox(self)
        self.source = QComboBox(self)
        self.spread = QComboBox(self)
        self.tempo_lbl = QLabel(self)
        self.tmin, self.tmax = QSpinBox(self), QSpinBox(self)
        for sb in (self.tmin, self.tmax):
            sb.setRange(0, 300)
            sb.setSpecialValueText("–")
        self.table = LibraryTable(win)
        self.table.doubleClicked.connect(lambda _: self._add())
        self.table.itemSelectionChanged.connect(self._update_add_button)
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        self.add_button = ShrinkButton(self, 120)             # put the chosen songs in the folder shown on the right
        self.add_button.clicked.connect(self._add)
        # nothing in the library yet: say so, with the way to fill it
        self.empty = QWidget(self)
        el = QVBoxLayout(self.empty)
        self.empty_text = QLabel(self.empty)
        self.empty_text.setWordWrap(True)
        self.empty_text.setAlignment(Qt.AlignCenter)
        self.empty_button = ShrinkButton(self.empty, 120)
        self.empty_button.clicked.connect(win._archive)
        el.addStretch(1)
        el.addWidget(self.empty_text)
        el.addWidget(self.empty_button)
        el.addStretch(2)
        top = QHBoxLayout()
        top.addWidget(self.title, 1)
        top.addWidget(self.filter_button)
        self.filters = QWidget(self)
        filt = QGridLayout(self.filters)
        filt.setContentsMargins(0, 0, 0, 0)
        checks = QHBoxLayout()
        for w in (self.not_on_card, self.recorded, self.damaged):
            checks.addWidget(w)
        checks.addStretch(1)
        filt.addLayout(checks, 0, 0, 1, 2)
        tempo = QHBoxLayout()
        for w in (self.tempo_lbl, self.tmin, QLabel("–", self), self.tmax):
            tempo.addWidget(w)
        tempo.addStretch(1)
        filt.addLayout(tempo, 1, 0)
        meter = QHBoxLayout()
        meter.addWidget(self.meter_lbl)
        meter.addWidget(self.meter, 1)
        filt.addLayout(meter, 1, 1)
        filt.addWidget(self.source, 2, 0)
        filt.addWidget(self.spread, 2, 1)
        self.filters.hide()
        self.filter_button.toggled.connect(self.filters.setVisible)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.px(10), style.px(8), style.px(10), style.px(10))
        lay.addWidget(self.head)
        lay.addLayout(top)
        lay.addWidget(self.search)
        lay.addWidget(self.filters)
        lay.addWidget(self.card)                            # the card list: always the full width
        self.card_row = ButtonRow(self)                     # the chosen kept card itself (only with one chosen)
        for b in (self.rename_card, self.remove_card):
            self.card_row.add(b)
        lay.addWidget(self.card_row)
        browse = QHBoxLayout()
        browse.addWidget(self.parts)
        browse.addWidget(self.table, 1)
        lay.addLayout(browse, 1)
        self.no_rows = QLabel(self)                         # filters on and nothing left: say so, not an empty list
        self.no_rows.setWordWrap(True)
        self.no_rows.setProperty("role", "muted")
        self.no_rows.hide()
        lay.addWidget(self.no_rows)
        lay.addWidget(self.empty, 1)
        lay.addWidget(self.add_button)                      # to the card: the chosen songs, or a whole folder
        lay.addWidget(self.copy_part)
        lay.addWidget(self.hint)
        self.search.textChanged.connect(self.apply)
        self.card.currentIndexChanged.connect(self._card_changed)
        self.part.currentIndexChanged.connect(self.apply)
        self.recorded.toggled.connect(self.apply)
        self.not_on_card.toggled.connect(self.apply)
        self.damaged.toggled.connect(self.apply)
        for box in (self.meter, self.source, self.spread):
            box.currentIndexChanged.connect(self.apply)
        self.tmin.valueChanged.connect(self.apply)
        self.tmax.valueChanged.connect(self.apply)

    def apply(self, *_):
        if self.win._filling:
            return
        self.win.presenter.set_library_filter(self.search.text(), self.card.currentData(),
                                              True if self.recorded.isChecked() else None,
                                              self.tmin.value() or None, self.tmax.value() or None,
                                              self._part_key(), meter=self.meter.currentData(),
                                              spread=self.spread.currentData(), source=self.source.currentData(),
                                              damaged=True if self.damaged.isChecked() else None,
                                              not_on_card=not self.not_on_card.isHidden() and self.not_on_card.isChecked())
        self._update_part_button()

    def _fill_meters(self) -> None:
        """The time signatures known so far; the chosen one stays chosen."""
        p = self.win.presenter
        chosen = p.lib_filter.get("meter")
        meters = p.library_meters()
        if chosen and chosen not in meters:
            meters.append(chosen)
        have = [self.meter.itemData(i) for i in range(self.meter.count())]
        if have == [None] + meters:
            return
        self.meter.blockSignals(True)
        self.meter.clear()
        self.meter.addItem(p.t("lib_meter_all"), None)
        for m in meters:
            self.meter.addItem(m, m)
        i = self.meter.findData(chosen)
        self.meter.setCurrentIndex(i if i >= 0 else 0)
        self.meter.blockSignals(False)

    def _part_key(self):
        data = self.part.currentData()
        if not data:
            return None
        kind, n = data.split(":")
        return kind, int(n)

    def _card_changed(self, *_):
        if self.win._filling:
            return
        self.win._filling = True
        self.fill_parts()
        self.win._filling = False
        self.apply()

    def fill_parts(self, sync: bool = True) -> None:
        t = self.win.presenter.t
        self.part.clear()
        self.part.addItem(t("lib_all_songs"), None)
        for key, label in self.win.presenter.library_parts(self.card.currentData()):
            self.part.addItem(label, "%s:%d" % key)          # strings: findData cannot match tuples
        texts = [self.part.itemText(i) for i in range(self.part.count())]
        self.parts.blockSignals(True)
        if [self.parts.item(i).text() for i in range(self.parts.count())] != texts:
            self.parts.clear()                  # only when the list changed: a rebuild forgets a Shift-click's start
            self.parts.addItems(texts)
        if sync:                                # show() points it at the part shown after this
            self._sync_parts_row()
        self.parts.blockSignals(False)
        self.parts.setVisible(self.card.currentData() is not None)
        self.card_row.setVisible(self.card.currentData() is not None)    # only about one chosen card
        self._update_part_button()

    def _sync_parts_row(self) -> None:
        """Point the folder list at the part shown. Folders chosen with Shift or Cmd stay chosen."""
        lst, r = self.parts, self.part.currentIndex()
        if r < 0 or r >= lst.count():
            return
        if lst.currentRow() != r or not lst.selectedItems():      # chosen elsewhere: that row only
            lst.setCurrentRow(r)
        else:                                                       # the click itself already chose
            lst.selectionModel().setCurrentIndex(lst.model().index(r, 0), QItemSelectionModel.NoUpdate)

    def _update_part_button(self) -> None:
        """"Hele map 02 WALSEN toevoegen aan je kaart": only when a folder or song list is chosen."""
        p = self.win.presenter
        key = self._part_key()
        many = self.parts.chosen_folders()
        if len(many) > 1:                                      # several folders chosen: all of them
            self.copy_part.setVisible(p.session is not None)
            self.copy_part.setText(p.t("btn_copy_folders", n=len(many)))
            self._update_add_button()
            return
        self.copy_part.setVisible(key is not None and p.session is not None)
        if key is not None:
            text = self.part.currentText()                     # "01  FEEST  (4)", "Songlijst 1 (3 songs)"
            label = " ".join((text.rsplit("  (", 1) if key[0] == "folder" else text.rsplit(" (", 1))[0].split())
            if key[0] == "list":
                label = label[:1].lower() + label[1:]          # "Hele songlijst 1 …"
            self.copy_part.setText(p.t("btn_copy_folder" if key[0] == "folder" else "btn_copy_list", part=label))
        self._update_add_button()

    def _update_add_button(self) -> None:
        p = self.win.presenter
        n = len(self.table.selected_indices())
        if p.session is None:
            self.add_button.setEnabled(False)
            return
        f = p.session.db.folders[p.folder - 1]
        self.add_button.setText(p.t("btn_add_to_folder", n=p.folder, name=f.name or p.t("noname")))
        self.add_button.setEnabled(n > 0)

    def _add(self) -> None:
        p = self.win.presenter
        idx = self.table.selected_indices()
        if idx and p.session is not None:
            p.import_from_library(idx, p.folder)

    def _copy_part(self):
        many = self.parts.chosen_folders()
        if len(many) > 1:
            self.win.presenter.copy_library_folders(self.card.currentData(), many)
            return
        key = self._part_key()
        if key is not None:
            self.win.presenter.copy_library_part(self.card.currentData(), key)

    def _rename_card(self):
        label = self.card.currentData()
        if label:
            self.win.presenter.rename_library_card(label)

    def _remove_card(self):
        label = self.card.currentData()
        if label:
            self.win.presenter.remove_library_card(label)

    def retranslate(self, t) -> None:
        self.filter_button.setText(gap(t("btn_filter")))
        self.remove_card.setText(t("act.lib_remove"))
        self.rename_card.setText(t("act.lib_rename"))
        self.rename_card.setToolTip(t("tip_lib_rename"))
        self.remove_card.setToolTip(t("tip_lib_remove"))
        self.empty_text.setText(t("lib_empty"))
        self.empty_button.setText(t("task_archive"))
        self.search.setPlaceholderText(t("lib_search"))
        self.recorded.setText(t("lib_recorded"))
        self.not_on_card.setText(t("lib_not_on_card"))
        self.not_on_card.setToolTip(t("tip_lib_not_on_card"))
        self.damaged.setText(t("lib_damaged_only"))
        self.meter_lbl.setText(t("lib_meter"))
        self.tempo_lbl.setText(t("lib_tempo"))
        for box, items in ((self.source, (("lib_source_all", None), ("lib_source_card", "card"),
                                          ("lib_source_floppy", "floppy"))),
                           (self.spread, (("lib_spread_all", None), ("lib_spread_one", "one"),
                                          ("lib_spread_more", "more")))):
            keep = box.currentIndex()
            box.blockSignals(True)
            box.clear()
            for key, data in items:
                box.addItem(t(key), data)
            box.setCurrentIndex(max(keep, 0))
            box.blockSignals(False)
        self._fill_meters()
        self.hint.setText(t("lib_hint"))
        self.head.set_text(t("lib_head"), t("lib_head_info"))
        self._update_part_button()
        if self.part.count():
            self.part.setItemText(0, t("lib_all_songs"))
            self.parts.item(0).setText(t("lib_all_songs"))
        self.table.setHorizontalHeaderLabels([t("col.name"), t("col.tempo"), t("col.meter"), t("col.recorded"),
                                              t("col.cards")])
        if self.card.count():
            self.card.setItemText(0, t("lib_all_cards"))

    def show(self, title: str, cards: List[str], rows) -> None:
        t = self.win.presenter.t
        self.title.setText(title)
        self._fill_meters()
        self.not_on_card.setVisible(self.win.presenter.session is not None)
        f = self.win.presenter.lib_filter                       # folded away but on: the button says so
        n = sum(1 for k in ("recorded", "tempo_min", "tempo_max", "meter", "spread", "source", "damaged",
                            "not_on_card") if f.get(k))
        t = self.win.presenter.t
        self.filter_button.setText(gap(t("btn_filter_n", n=n) if n else t("btn_filter")))
        current = self.win.presenter.lib_filter.get("card")    # the presenter says which card is shown
        self.card.clear()
        self.card.addItem(t("lib_all_cards"), None)
        for c in cards:
            self.card.addItem(c, c)
        i = self.card.findData(current)
        self.card.setCurrentIndex(i if i >= 0 else 0)
        part = self.win.presenter.lib_filter.get("part")
        part = "%s:%d" % part if part else None
        self.fill_parts(sync=False)
        j = self.part.findData(part)
        self.part.setCurrentIndex(j if j >= 0 else 0)
        self.parts.blockSignals(True)
        self._sync_parts_row()
        self.parts.blockSignals(False)
        self._update_part_button()
        tb = self.table
        shown = repr(sorted(self.win.presenter.lib_filter.items(), key=lambda kv: kv[0]))
        if shown != getattr(self, "_shown", None):      # another folder, card or search: other songs, so
            self._shown = shown                         # the rows chosen before do not stay chosen
            tb.clearSelection()
        tb.setSortingEnabled(False)
        tb.setRowCount(len(rows))
        self.no_rows.setText(t("lib_no_rows_filter") if n else t("lib_no_rows"))
        self.no_rows.setVisible(not rows and bool(cards))
        for r, row in enumerate(rows):
            tip = row.where
            if row.inside:                                      # a diskette set: which songs it is for
                tip += "\n\n" + t("lib_inside", n=len(row.inside)) + "\n" + "\n".join(row.inside)
            if row.damaged:                                     # a file that does not unpack: orange, said
                tip = t("lib_damaged", files=", ".join(row.damaged)) + "\n\n" + tip
            for c, text in enumerate([row.name, row.tempo, row.meter, row.recorded, row.cards]):
                it = QTableWidgetItem()
                it.setData(Qt.EditRole, int(text) if c == 1 and text.isdigit() else text)   # tempo sorts as a number
                it.setData(Qt.UserRole, row.index)
                it.setToolTip(tip)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                if row.damaged:
                    if c == 0:
                        it.setData(Qt.EditRole, text + "  ⚠")       # behind the name: sorting stays by name
                    it.setForeground(QBrush(style.colour("warn")))
                tb.setItem(r, c, it)
        tb.setSortingEnabled(self.part.currentData() is None)    # a folder or list keeps its own order
        tb.setColumnHidden(4, self.part.currentData() is not None)   # "Op kaart": a folder of one card says it all
        numbered = any(row.slot for row in rows)
        tb.verticalHeader().setVisible(numbered)                # "01".."20" as on the keyboard
        if numbered:
            tb.setVerticalHeaderLabels([row.slot for row in rows])
        fit_columns_once(tb, (1, 2, 3))
        none = not cards
        self.empty.setVisible(none)
        for wdg in (tb, self.search, self.card, self.filter_button, self.add_button):
            wdg.setVisible(not none)
        self.hint.setVisible(bool(rows))
        self._update_add_button()


class TaskButton(QPushButton):
    """A big start-screen button: the task in bold, the explanation below it, wrapped to the width
    (a plain button cannot wrap, which made the window wider than a laptop screen with big letters).
    Each task has a colour of its own (number 1-3: blue, green, orange): a stripe on the left, the
    picture in a soft circle of that colour and an arrow on the right, so the three are told apart at a glance."""

    PICTURE = 64                                        # the circle; the picture inside it is about half

    def __init__(self, parent: QWidget, number: int = 1):
        super().__init__(parent)
        self._text = ""
        self._picture = "card"
        self.number = number
        self.setObjectName("task")
        self.setProperty("task", str(number))
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(style.sheet("QPushButton { min-height: 100px; }"))      # the app style sheet would win otherwise
        outer = QHBoxLayout(self)
        outer.setContentsMargins(style.px(30), style.px(14), style.px(22), style.px(14))
        outer.setSpacing(style.px(20))
        self.picture = QLabel(self)                     # the task as a picture, so it is found again at a glance
        self.picture.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.picture.setFixedSize(style.px(self.PICTURE), style.px(self.PICTURE))
        outer.addWidget(self.picture, 0, Qt.AlignVCenter)
        lay = QVBoxLayout()
        lay.setSpacing(4)
        outer.addLayout(lay, 1)
        self.head = QLabel(self)
        f = self.head.font()
        f.setBold(True)
        f.setPointSize(int(f.pointSize() * 1.3))
        self.head.setFont(f)
        self.info = QLabel(self)
        self.info.setWordWrap(True)
        self.arrow = QLabel(self)                       # "go on here", in the task's colour
        self.arrow.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.arrow.setFixedSize(style.px(28), style.px(28))
        for lab in (self.head, self.info):
            lab.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(lab)
        outer.addWidget(self.arrow, 0, Qt.AlignVCenter)

    def setText(self, text: str) -> None:              # "title\nexplanation"
        self._text = text
        head, _, info = text.partition("\n")
        self.head.setText(head)
        self.info.setText(info)

    def text(self) -> str:
        return self._text

    def set_picture(self, name: str) -> None:
        """The picture in its coloured circle, and the arrow; again after a switch between light and dark."""
        self._picture = name
        colour, soft = style.colour("task%d" % self.number), style.colour("task%d_bg" % self.number)
        size, scale = style.px(self.PICTURE), 2
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(soft)
        p.drawEllipse(0, 0, size * scale, size * scale)
        inner = icons.pixmap(name, self.PICTURE * 34 // 64, colour, soft, scale)     # drawn at scale too
        off = (size * scale - inner.width()) // 2
        p.drawPixmap(QRect(off, off, inner.width(), inner.height()), inner)
        p.end()
        pm.setDevicePixelRatio(scale)
        self.picture.setPixmap(pm)
        self.arrow.setPixmap(icons.pixmap("chevron", 28, colour))

    STRIPE = 10                                         # the coloured stripe on the left

    def paintEvent(self, e):
        """The button (style sheet), then the stripe in the task's colour along its rounded left side."""
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), style.px(14), style.px(14))
        p.setClipRect(QRect(0, 0, style.px(self.STRIPE), self.height()))
        p.fillPath(path, style.colour("task%d" % self.number))
        p.end()

    def hasHeightForWidth(self) -> bool:                # the explanation wraps: taller when narrower
        return True

    def heightForWidth(self, w: int) -> int:
        m = self.layout().contentsMargins()
        text_w = w - m.left() - m.right() - self.picture.width() - self.arrow.width() - 2 * self.layout().spacing()
        need = m.top() + m.bottom() + 8 + self.head.sizeHint().height() + 4 + self.info.heightForWidth(max(text_w, 100))
        return max(style.px(100), need, self.picture.height() + m.top() + m.bottom())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        need = self.heightForWidth(self.width())
        if need != self.minimumHeight():
            self.setMinimumHeight(need)
        self.layout().setGeometry(self.rect())          # a button does not lay out its own children by itself


DOCS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "docs"))
HELP_CHAPTERS = {"start": [1], "organize": [2, 3, 4, 5], "compose": [7]}


MANUAL_FILES = {"nl": "nl/handleiding.md", "en": "en/manual.md"}   # the manual in the language of the app


def manual_for_this_computer(text: str, windows: bool, lang: str = "nl") -> str:
    """The manual as the app shows it: only this computer's parts (<!-- mac --> / <!-- win --> blocks), no
    note that is only for the file (<!-- bestand -->), and on Windows its keys and names (Ctrl, Alt, Verkenner)
    instead of the Mac's."""
    import re
    drop = ("mac", "bestand") if windows else ("win", "bestand")
    for tag in drop:
        text = re.sub(r"<!-- %s -->.*?<!-- /%s -->\n?" % (tag, tag), "", text, flags=re.S)
    text = re.sub(r"<!-- /?(mac|win) -->\n?", "", text)
    if windows:
        names = (("Finder", "File Explorer"), ("Trash", "Recycle Bin")) if lang == "en" else (("Finder", "Verkenner"),)
        for mac, win in (("Cmd", "Ctrl"), ("Option", "Alt")) + names:
            text = re.sub(r"\b%s\b" % mac, win, text)
    return text


def manual_chapters(text: str, numbers) -> str:
    """The chapters "## 2. …" of the manual with these numbers (all of it for an empty list)."""
    if not numbers:
        return text
    parts = text.split("\n## ")
    keep = [p for p in parts[1:] if p.split(".", 1)[0].strip().isdigit() and int(p.split(".", 1)[0]) in numbers]
    return "\n\n".join("## " + p for p in keep)


class Toast(QFrame):
    """A short message at the bottom of the window with "Ongedaan maken" next to it. It goes away by
    itself after a few seconds; nothing has to be clicked away (instead of "are you sure?" pop-ups)."""
    SECONDS = 7

    def __init__(self, win: "MainWindow", parent: QWidget):
        super().__init__(parent)
        self.win = win
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(style.px(18), style.px(8), style.px(10), style.px(8))
        self.text = QLabel(self)
        self.undo = QPushButton(self)                    # "Ongedaan maken", or "Opnieuw" right after an undo
        self.undo.clicked.connect(self._undo)
        self.redo_mode = False
        lay.addWidget(self.text, 1)
        lay.addSpacing(12)
        lay.addWidget(self.undo)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)
        self.hide()

    def show_text(self, text: str, redo: bool = False) -> None:
        self.text.setText(text)
        self.redo_mode = redo
        self.undo.setText(self.win.presenter.t("act.redo" if redo else "act.undo"))
        self.adjustSize()
        self.place()
        self.show()
        self.raise_()
        self.timer.start(self.SECONDS * 1000)

    def place(self) -> None:
        p = self.parentWidget()
        w = min(max(self.sizeHint().width(), 360), p.width() - 40)
        h = self.sizeHint().height()
        self.setGeometry((p.width() - w) // 2, p.height() - h - 36, w, h)

    def _undo(self) -> None:
        self.hide()
        self.win.acts["redo" if self.redo_mode else "undo"].trigger()


class BusyBar(QFrame):
    """Long work (writing a card, reading the library) shows its progress in the status bar at the
    bottom of the window: not in a separate little window, and not at the top, where it would push the
    whole screen down while it is there."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("busyline")                      # plain, like the rest of the status bar
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(style.px(10))
        self.text = QLabel(self)
        self.bar = QProgressBar(self)
        self.bar.setObjectName("busybar")
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(style.px(160), style.px(6))
        self.pct = QLabel(self)
        self.pct.setProperty("role", "muted")
        lay.addWidget(self.text)
        lay.addWidget(self.bar)
        lay.addWidget(self.pct)
        lay.addStretch(1)
        self.hide()

    def start(self, text: str) -> None:
        win = self.window()
        if isinstance(win, QMainWindow):
            win.statusBar().clearMessage()                  # a message would hide the bar
        self.text.setText(text)
        self.bar.setRange(0, 0)                             # moving until the first real progress
        self.pct.setText("")
        self.show()

    def progress(self, i: int, n: int, text: str) -> None:
        self.bar.setRange(0, max(n, 1))
        self.bar.setValue(min(i, max(n, 1)))
        self.pct.setText("%d%%" % (100 * min(i, n) // max(n, 1)))
        if text:
            self.bar.setToolTip(text.rsplit("/", 1)[-1])
