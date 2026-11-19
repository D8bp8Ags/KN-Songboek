"""PySide6 main window. Only layout and wiring; behaviour is in presenter.py.

The window opens on a start screen that asks "Wat wil je doen?" with one big button per task
(ADR-0008). The work page has a top bar (back to start, undo, "Meer…"), a yellow bar while changes are
not on the card yet, and below it the library (when composing) and the card.

Card layout: folders on the left (drop songs here to copy them, hold Option/Alt (or Ctrl) to move), the 20 slots of
the selected folder on the right (drag to reorder, F2 or double-click to rename, multi-select),
a search field above, the undo history in a side panel and free space in the status bar.
"""
from __future__ import annotations

import os
from html import escape
import sys
from typing import List, Optional, Tuple

from PySide6.QtCore import (
    QEvent,
    QEventLoop,
    QMarginsF,
    QRectF,
    QSettings,
    QSize,
    QSizeF,
    Qt,
    QThread,
    QTimer,
)
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QKeySequence,
    QPageLayout,
    QPageSize,
    QPainter,
    QPalette,
    QPdfWriter,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core import KN7Error
from ..formats.inf import NAME_LEN
from . import icons, style
from .i18n import LANGUAGES
from .dialogs import (  # noqa: F401  (also imported from here by tests and tools)
    AboutDialog, BackupsDialog, DuplicatesDialog, ExportDialog, FlowDialog, FolderPickerDialog, HelpDialog, IntroDialog,
    MoreDialog)
from .info_panel import (  # noqa: F401  (also imported from here by tests and tools)
    InfoPanel)
from .widgets import (  # noqa: F401  (also imported from here by tests and tools)
    BusyBar, ButtonRow, ClickLabel, EmptySlotDelegate, FavoriteTable, FolderList, GripSplitter, LibraryPanel, PanelHead, MIME, MIME_FOLDER, MIME_LIB, MIME_OTHER, OtherSongTable, ShrinkButton, SongListWidget, SongTable, TaskButton, Toast, _Worker, _encode, fit_columns_once, gap, get_name, manual_chapters, name_field, user_columns, volume_field, wants_move)
from .presenter import Actions, FolderRow, MainPresenter, SongRow


class MainWindow(QMainWindow):
    def __init__(self, settings: Optional[QSettings] = None, presenter: Optional[MainPresenter] = None):
        """presenter: the one of a window being rebuilt (another text size): the open card, the library
        and every change not on the card yet carry over."""
        super().__init__()
        self.settings = settings or QSettings("kn-songboek", "kn-songboek")
        style.set_text_size(str(self.settings.value("text_size", "normal")))    # before anything is built
        style.apply(QApplication.instance())
        lang = str(self.settings.value("language", "nl"))
        if presenter is not None:
            self.presenter = presenter
            presenter.view = self
        else:
            self.presenter = MainPresenter(self, lang=lang if lang in LANGUAGES else "nl")
        self.presenter.runner = self.run_busy
        style.on_change(self._colours_changed)            # the system switched between light and dark
        self._busy_running = False
        self.flow: Optional[FlowDialog] = None          # the step window of a running job
        self._filling = False
        self.error_count = 0

        self.search = QLineEdit(self)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.presenter.set_search)
        self.folders = FolderList(self)
        self.folders.currentItemChanged.connect(self._folder_changed)
        self.folders.itemDoubleClicked.connect(lambda it: FolderList.is_folder(it) and self._rename_folder())
        self.folders.new_button = QPushButton(self)
        self.folders.new_button.clicked.connect(self._new_folder)
        left = QWidget(self)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.folders, 1)
        ll.addWidget(self.folders.new_button)
        self.songs = SongTable(self)
        self.songs.itemChanged.connect(self._song_edited)
        right = QWidget(self)
        lay = QVBoxLayout(right)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.search)
        self.empty_hint = QLabel(self)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(style.sheet("QLabel { padding: 6px 2px; }"))
        style.mark(self.empty_hint, role="muted")
        self.empty_hint.hide()
        lay.addWidget(self.empty_hint)
        lay.addWidget(self.songs)
        lay.addWidget(self._build_action_bar())
        self.split = GripSplitter(self)
        self.split.addWidget(left)
        self.split.addWidget(right)
        self.info = InfoPanel(self)
        self.split.addWidget(self.info)
        # names are at most 16 characters, so folders and songs need a fixed width: room to spare goes to
        # the info panel
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 0)
        self.split.setStretchFactor(2, 1)
        self.split.setChildrenCollapsible(False)                   # no panel can be dragged away
        self.split.setSizes([style.px(300), style.px(640), style.px(260)])
        self.split.default_sizes = [300, 640, 260]
        # right: a welcome page until a card is open, then the card
        self.welcome = QWidget(self)
        wl = QVBoxLayout(self.welcome)
        self.welcome_text = QLabel(self.welcome)
        self.welcome_text.setWordWrap(True)
        self.welcome_text.setAlignment(Qt.AlignCenter)
        wl.addStretch(1)
        wl.addWidget(self.welcome_text)
        self.welcome_buttons = {}
        for key in ("open",):
            b = QPushButton(self.welcome)
            b.setMinimumHeight(style.px(36))
            self.welcome_buttons[key] = b
            wl.addWidget(b)
        wl.addStretch(2)
        self.card_stack = QStackedWidget(self)
        self.card_stack.addWidget(self.welcome)
        self.card_stack.addWidget(self.split)
        self.library_panel = LibraryPanel(self)
        QTimer.singleShot(0, self._restore_columns)
        self.main_split = GripSplitter(self)
        self.main_split.addWidget(self.library_panel)
        # the card side gets a heading too while the library is beside it: two sides, each named
        self.card_side = QFrame(self)                   # its own colour, like the library's: two sides
        self.card_side.setObjectName("cardpanel")
        cs = QVBoxLayout(self.card_side)
        cs.setContentsMargins(style.px(10), style.px(8), style.px(10), style.px(10))
        self.card_head = PanelHead(self.card_side)
        cs.addWidget(self.card_head)
        cs.addWidget(self.card_stack, 1)
        self.main_split.addWidget(self.card_side)
        self.main_split.setChildrenCollapsible(False)
        self.main_split.setStretchFactor(0, 1)
        self.main_split.setStretchFactor(1, 1)
        self.main_split.setSizes([style.px(520), style.px(640)])
        self.main_split.default_sizes = [520, 640]
        self.start_page = self._build_start_page()
        self.work_page = QWidget(self)
        wl2 = QVBoxLayout(self.work_page)
        wl2.addLayout(self._build_top_bar())
        wl2.addWidget(self._build_tip_bar())
        wl2.addWidget(self._build_lock_bar())
        wl2.addWidget(self._build_draft_bar())
        wl2.addWidget(self.main_split, 1)
        self.pages = QStackedWidget(self)
        self.pages.addWidget(self.start_page)
        self.pages.addWidget(self.work_page)
        central = QWidget(self)
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.pages, 1)
        self.setCentralWidget(central)
        self.toast = Toast(self, central)
        self._detail_timer = QTimer(self)
        self._detail_timer.setInterval(0)
        self._detail_timer.timeout.connect(self._fill_details)

        self.history = QListWidget(self)
        self.history.itemClicked.connect(lambda it: self.presenter.undo_to(it.data(Qt.UserRole)))
        self.dock = QDockWidget(self)
        self.dock.setObjectName("history")
        self.dock.setWidget(self.history)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self._build_lists_dock()
        self._build_other_dock()
        self.dock.hide()                    # history and lists are under "Meer…" (ADR-0008)
        self.lists_dock.hide()
        self.space = QLabel(self)
        self.busy_bar = BusyBar(self)
        self.statusBar().addWidget(self.busy_bar, 1)
        self.statusBar().addPermanentWidget(self.space)

        self._build_actions()
        for key, b in self.welcome_buttons.items():
            b.clicked.connect(self.acts[key].trigger)
        self._build_more_menu()
        self.retranslate()
        self.set_icons()
        self.resize(style.px(1280), style.px(720))
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.presenter.refresh()

    # ------------------------------------------------------------------ start screen, top bar, draft bar
    def _build_start_page(self) -> QWidget:
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(style.px(60), style.px(40), style.px(60), style.px(40))
        self.start_title = QLabel(w)
        f = self.start_title.font()
        f.setPointSize(f.pointSize() * 2)
        f.setBold(True)
        self.start_title.setFont(f)
        self.start_title.setAlignment(Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(self.start_title)
        lay.addSpacing(20)
        self.task_buttons = {}
        for key, method in self.presenter.TASKS:
            b = TaskButton(w)
            b.clicked.connect(lambda _=False, m=method: self._task(m))
            self.task_buttons[key] = b
            lay.addWidget(b)
        lay.addSpacing(10)                              # small, under the three tasks: not a fourth task
        # Practising: a bar that says so, what is in the practice card reader, and the hand that puts a card in
        self.practice_box = QFrame(w)
        self.practice_box.setObjectName("practice")
        pb = QVBoxLayout(self.practice_box)
        self.practice_text = QLabel(self.practice_box)
        self.practice_text.setWordWrap(True)
        self.practice_reader = QLabel(self.practice_box)
        f = self.practice_reader.font()
        f.setBold(True)
        self.practice_reader.setFont(f)
        prow = QHBoxLayout()
        self.practice_swap = QPushButton(self.practice_box)
        self.practice_swap.clicked.connect(lambda: self.presenter.swap_practice_card())
        self.practice_stop = QPushButton(self.practice_box)
        self.practice_stop.clicked.connect(lambda: self.presenter.stop_practice())
        prow.addWidget(self.practice_swap)
        prow.addStretch(1)
        prow.addWidget(self.practice_stop)
        pb.addWidget(self.practice_text)
        pb.addWidget(self.practice_reader)
        pb.addLayout(prow)
        self.practice_box.hide()
        lay.insertWidget(1, self.practice_box)          # above the question: you see it first
        self.practice_button = QPushButton(w)
        self.practice_button.setObjectName("link")
        self.practice_button.setCursor(Qt.PointingHandCursor)
        self.practice_button.clicked.connect(lambda: self.presenter.start_practice())
        lay.addWidget(self.practice_button, 0, Qt.AlignCenter)
        lay.addStretch(2)
        return w

    def _build_top_bar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.back_button = QPushButton(self)
        self.back_button.clicked.connect(self.go_start)
        # Which task, and which card: the card name is what the user knows from the label on the card.
        self.page_title = QLabel(self)                  # the task, small and grey
        style.mark(self.page_title, role="muted")
        self.card_title = ClickLabel(self)              # the card's name, big; click to name a new card
        self.card_title.clicked.connect(lambda: self.presenter.name_new_card())
        f = self.card_title.font()
        f.setBold(True)
        f.setPointSize(int(f.pointSize() * 1.35))
        self.card_title.setFont(f)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.page_title)
        titles.addWidget(self.card_title)
        # How full the card is: a bar for the 99 x 20 places and "14 songs in 5 mappen · 28.9 GB vrij"
        self.meter = QProgressBar(self)
        self.meter.setObjectName("meter")
        self.meter.setTextVisible(False)
        self.meter.setFixedHeight(style.px(10))
        self.meter.setMinimumWidth(style.px(120))
        self.fullness = QLabel(self)
        self.fullness.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meter = QVBoxLayout()
        meter.setContentsMargins(0, 0, 0, 0)
        meter.setSpacing(2)
        meter.addWidget(self.fullness)
        meter.addWidget(self.meter)
        self.meter_box = QWidget(self)
        self.meter_box.setLayout(meter)
        self.meter_box.setMinimumWidth(style.px(180))
        self.fullness.setMinimumHeight(2 * self.fullness.fontMetrics().lineSpacing() + 2)
        self.undo_button = ShrinkButton(self, 56)       # always in words: Opnieuw gives way first
        self.undo_button.words_always = True
        self.redo_button = ShrinkButton(self, 56)       # "Opnieuw": the undone step back again
        self.more_button = QPushButton(self)
        self.help_button = QPushButton(self)
        self.help_button.setFixedWidth(style.px(44))
        self.help_button.clicked.connect(lambda: HelpDialog(self, self.presenter.page).exec())
        bar.addWidget(self.back_button)
        bar.addSpacing(12)
        bar.addLayout(titles)
        bar.addStretch(1)
        bar.addWidget(self.meter_box)
        bar.addSpacing(12)
        bar.addWidget(self.undo_button)
        bar.addWidget(self.redo_button)
        bar.addWidget(self.more_button)
        bar.addWidget(self.help_button)
        return bar

    def _build_action_bar(self) -> QWidget:
        """Buttons for the chosen songs, so nothing needs dragging (drag still works too)."""
        self.action_bar = ButtonRow(self)               # whole words, two per row when it is narrow
        self.selected_label = QLabel(self.action_bar)
        self.song_buttons = {}
        self.selected_label.hide()                      # the highlighted rows already show what is chosen
        for key, slot in (("btn_move", lambda: self._move(False)), ("btn_copy", lambda: self._move(True)),
                          ("btn_rename", self._rename), ("btn_delete", self._delete)):
            b = ShrinkButton(self.action_bar)
            b.setEnabled(False)                         # until a song is chosen
            b.clicked.connect(slot)
            self.song_buttons[key] = b
            self.action_bar.add(b)
        self.action_bar.hide()
        self.songs.itemSelectionChanged.connect(self._selection_changed)
        self.songs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.songs.customContextMenuRequested.connect(self._song_menu)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folder_menu)
        return self.action_bar

    def _selection_changed(self) -> None:
        n = len(self.selected_slots())
        # the bar always stays (greyed out with nothing chosen), so the list does not jump up and down
        self.action_bar.setVisible(self.presenter.session is not None)
        self._fit_action_bar()
        self.selected_label.setText(self.presenter.t("selected_n", n=n))
        for key in ("btn_move", "btn_copy", "btn_delete"):
            self.song_buttons[key].setEnabled(n > 0)
        self.song_buttons["btn_rename"].setEnabled(n == 1)
        self._song_acts()
        info = None
        if n == 1 and self.info.isVisibleTo(self) and not self._filling:
            slot = self.selected_slots()[0]
            try:
                info = self.presenter.song_info(slot, banks=False)
            except (KN7Error, OSError, ValueError, KeyError):   # an unreadable song file: just show less
                info = None
        self.info.show_info(info, self.selected_slots()[0] if info is not None else None)
        self._update_fav_put()

    def _update_fav_put(self) -> None:
        """The button says which song goes on which button: "Zet DANSEN op knop 3"."""
        if not hasattr(self, "fav_put"):
            return
        t, p = self.presenter.t, self.presenter
        slots = self.selected_slots()
        row = max(self.fav_table.currentRow(), 0) + 1
        name = ""
        if len(slots) == 1 and p.session is not None:
            song = p.session.db.song(slots[0][0] - 1, slots[0][1] - 1)
            name = song.name if song.used else ""
        self.fav_put.setEnabled(bool(name))
        self.fav_put.setText(t("fav_put", name=name, n=row) if name else t("fav_put_none"))

    def _fit_action_bar(self) -> None:
        """Nothing to fit any more: the song's details are in the info panel (the menu still opens
        them in a window of their own)."""

    def _song_menu(self, pos) -> None:
        if not self.selected_slots():
            return
        m = QMenu(self)
        for key in ("move", "copy", "rename", "delete"):
            m.addSeparator() if key is None else m.addAction(self.acts[key])
        m.exec(self.songs.viewport().mapToGlobal(pos))

    def _folder_menu(self, pos) -> None:
        if self.presenter.session is None:
            return
        m = QMenu(self)
        if FolderList.is_folder(self.folders.itemAt(pos)):
            m.addAction(self.acts["rename_folder"])
        m.addAction(self.presenter.t("btn_new_folder"), self._new_folder)
        chosen = self.folders.chosen_folders()
        if FolderList.is_folder(self.folders.itemAt(pos)) and chosen:
            m.addSeparator()
            m.addAction(self.presenter.t("folders_delete", n=len(chosen)),
                        lambda: self.presenter.delete_folders(chosen))
        m.exec(self.folders.viewport().mapToGlobal(pos))

    def _build_tip_bar(self) -> QFrame:
        """A tip the first time a screen is shown; "Begrepen" puts it away for good."""
        self.tip = QFrame(self)
        self.tip.setObjectName("tip")
        lay = QHBoxLayout(self.tip)
        lay.setContentsMargins(style.px(14), style.px(6), style.px(10), style.px(6))
        self.tip_icon = QLabel(self.tip)
        self.tip_text = QLabel(self.tip)
        self.tip_text.setWordWrap(True)
        self.tip_ok = QPushButton(self.tip)
        self.tip_ok.clicked.connect(self._tip_seen)
        lay.addWidget(self.tip_icon, 0, Qt.AlignTop)
        lay.addWidget(self.tip_text, 1)
        lay.addWidget(self.tip_ok)
        self.tip.hide()
        return self.tip

    def _build_lock_bar(self) -> QFrame:
        """Stays while the card is write-protected; "Opnieuw kijken" checks again after unlocking."""
        self.lock_bar = QFrame(self)
        self.lock_bar.setObjectName("draft")
        lay = QHBoxLayout(self.lock_bar)
        lay.setContentsMargins(style.px(14), style.px(6), style.px(10), style.px(6))
        self.lock_text = QLabel(self.lock_bar)
        self.lock_text.setWordWrap(True)
        self.lock_again = QPushButton(self.lock_bar)
        self.lock_again.clicked.connect(lambda: self.presenter.refresh())
        lay.addWidget(self.lock_text, 1)
        lay.addWidget(self.lock_again)
        self.lock_bar.hide()
        return self.lock_bar

    def show_locked(self, text: str) -> None:
        self.lock_text.setText(text)
        self.lock_again.setText(self.presenter.t("btn_check_again"))
        self.lock_bar.setVisible(bool(text) and self.presenter.page == "organize")

    def _show_tip(self, page: str) -> None:
        seen = str(self.settings.value("tip_seen_" + page, "")) == "1"
        if page in ("organize", "compose") and not seen:
            self.tip_text.setText(self.presenter.t("tip_" + page))
            self.tip.setProperty("page", page)
            self.tip.show()
        else:
            self.tip.hide()

    TASK_ICONS = {"task_organize": "card", "task_compose": "card_new", "task_archive": "library"}
    SONG_ICONS = {"btn_move": "move", "btn_copy": "copy", "btn_rename": "rename", "btn_delete": "remove"}

    def set_icons(self) -> None:
        """A picture next to the words where it helps to find a button again (see gui/icons.py).
        Drawn in the text colour, so again after the system switches between light and dark."""
        c = style.colours()
        for key, b in self.task_buttons.items():
            b.set_picture(self.TASK_ICONS.get(key, "card"))
        for key, b in self.song_buttons.items():
            b.setIcon(icons.icon(self.SONG_ICONS[key]))
        for b in [*self.song_buttons.values(), self.back_button, self.undo_button, self.redo_button,
                  self.folders.new_button,
                  self.put_button, self.library_panel.filter_button, self.library_panel.add_button,
                  self.library_panel.remove_card, self.library_panel.rename_card, self.library_panel.copy_part]:
            b.setIconSize(QSize(style.px(20), style.px(20)))     # grows with Weergave › Lettergrootte
        self.back_button.setIcon(icons.icon("back"))
        self.undo_button.setIcon(icons.icon("undo"))
        self.redo_button.setIcon(icons.icon("redo"))
        self.folders.new_button.setIcon(icons.icon("folder_new"))
        self.library_panel.remove_card.setIcon(icons.icon("remove"))
        self.library_panel.rename_card.setIcon(icons.icon("rename"))
        self.bank_rename.setIcon(icons.icon("rename"))
        self.library_panel.copy_part.setIcon(icons.icon("put_in_folder"))
        white, accent = QColor(c["on_accent"]), QColor(c["accent"])
        self.put_button.setIcon(icons.icon("put_on_card", white, accent))
        self.tip_icon.setPixmap(icons.pixmap("tip", 22, QColor(c["note_text"])))
        search = icons.icon("search")
        for field in (self.search, self.library_panel.search):
            for a in field.actions():
                if a.objectName() == "search_icon":
                    field.removeAction(a)
            a = field.addAction(search, QLineEdit.LeadingPosition)
            a.setObjectName("search_icon")
        self.library_panel.filter_button.setIcon(icons.icon("filter"))
        self.library_panel.add_button.setIcon(icons.icon("put_in_folder"))

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.ShowToParent, QEvent.HideToParent) and obj in getattr(self, "_ticks", {}):
            action, on = self._ticks[obj], e.type() == QEvent.ShowToParent
            if action.isChecked() != on:
                action.blockSignals(True)
                action.setChecked(on)
                action.blockSignals(False)
        return super().eventFilter(obj, e)

    def _colours_changed(self) -> None:
        """Grey list rows take their colour when they are filled: fill them again. Icons too."""
        self.set_icons()
        if not self._busy_running:
            self.presenter.refresh()

    def _tip_seen(self) -> None:
        self.settings.setValue("tip_seen_" + str(self.tip.property("page")), "1")
        self.tip.hide()

    def _build_draft_bar(self) -> QFrame:
        self.draft = QFrame(self)
        self.draft.setObjectName("draft")
        lay = QHBoxLayout(self.draft)
        lay.setContentsMargins(style.px(14), style.px(8), style.px(14), style.px(8))
        self.draft_text = QLabel(self.draft)
        f = self.draft_text.font()
        f.setBold(True)
        self.draft_text.setFont(f)
        self.put_button = QPushButton(self.draft)
        self.put_button.setMinimumHeight(style.px(40))
        self.put_button.clicked.connect(self._put_on_card)
        lay.addWidget(self.draft_text, 1)
        lay.addWidget(self.put_button)
        self.draft.hide()
        return self.draft

    def _build_more_menu(self) -> None:
        self.undo_button.clicked.connect(self.acts["undo"].trigger)
        self.redo_button.clicked.connect(self.acts["redo"].trigger)
        self.more_button.clicked.connect(lambda: MoreDialog(self).exec())

    def _task(self, method: str) -> None:
        if method == "start_archive":
            self._archive()
        else:
            if method == "start_compose" and self.presenter.library is None:
                lib = self.library_folder()             # first the library: a new card can start from a kept one
                if lib:
                    self.open_library(lib)
            getattr(self.presenter, method)()

    def go_start(self) -> bool:
        return self.presenter.leave()

    def _in_flow(self, title_key: str, steps, job):
        """Run job() with its questions, progress and 'Klaar' in one step window (FlowDialog)."""
        t = self.presenter.t
        if self.flow is not None:
            return job()
        self.flow = FlowDialog(self, t(title_key), [(k, t(k)) for k in steps])
        try:
            return job()
        finally:
            self.flow.hide()
            self.flow.deleteLater()
            self.flow = None

    def _put_on_card(self) -> None:
        steps = ["step_card", "step_write", "step_done"] if self.presenter.composing else ["step_write", "step_done"]
        ok = self._in_flow("btn_put_on_card", steps, self.presenter.put_on_card)
        if ok and self.presenter.card_path and not self.presenter.practice:
            self.settings.setValue("last_card", self.presenter.card_path)

    def show_practice(self, reader: str) -> None:
        """Practising (reader: what is in the practice card reader), or not ("")."""
        on = self.presenter.practice
        self.practice_box.setVisible(on)
        self.practice_button.setVisible(not on)
        self.practice_reader.setText(reader)

    def library_folder(self) -> Optional[str]:
        """The library; the first time, propose Documents/KN7000 Bibliotheek. Practising: its own."""
        from ..core.cards import default_library
        if self.presenter.practice:
            return self.presenter.world.library
        path = str(self.settings.value("last_library", "") or "")
        if path and os.path.isdir(path):
            return path
        t = self.presenter.t
        a = self.ask(t("choose_library") + "\n\n" + default_library(), [t("btn_ok_default"), t("btn_choose_folder")])
        if a is None:
            return None
        if a == 1:
            path = self.pick_dir(t("choose_library"), os.path.expanduser("~"), t("btn_pick_library"))
            if not path:
                return None
        else:
            path = default_library()
            os.makedirs(path, exist_ok=True)
        self.settings.setValue("last_library", path)
        return path

    def _archive(self) -> None:
        lib = self.library_folder()
        if lib is None:
            return
        folder = self._in_flow("task_archive", ["step_find", "step_name", "step_keep", "step_done"],
                               lambda: self.presenter.start_archive(lib))
        if folder and self.presenter.library is not None:
            self.open_library(lib)                              # show the new card in the library

    def show_page(self, page: str) -> None:
        t = self.presenter.t
        self.toast.hide()
        self._show_tip(page)
        self.pages.setCurrentIndex(0 if page == "start" else 1)
        self._library_beside(page == "compose" or self.acts["library"].isChecked())
        # putting a card together: the library is always there, so its on/off is grey (and not in Meer…)
        self.acts["library"].setEnabled(page != "compose")
        self.acts["start"].setEnabled(page != "start")         # already at the start: nothing to go back to
        self.info.setVisible(page != "start" and self.acts["info_panel"].isChecked())
        self.songs.setColumnHidden(3, page == "compose")    # room for the library's song names
        self.songs.fit_name()
        if page != "start":                                 # a new card is all empty folders: show them all
            self.folders.set_show_empty(page == "compose")
        self._save_splits()
        if page == "compose":
            self.split.default_sizes = [210, 420, 230]
            self.main_split.default_sizes = [760, 520]
        else:
            self.split.default_sizes = self._organize_sizes()
        if page != "start":
            self._split_page = "compose" if page == "compose" else "organize"
            self._restore_splits(force=True)
        self.page_title.setText((t("practice_bar") if self.presenter.practice else t({"organize": "task_organize", "compose": "task_compose"}.get(page, "start_question"))))
        if page == "compose" and self.presenter.library is None:
            lib = self.library_folder()
            if lib:
                self.open_library(lib)

    def show_intro(self, title: str, intro: str, points, button: str) -> None:
        IntroDialog(self, title, intro, points, button).exec()

    def show_done(self, text: str, other: str = "") -> bool:
        """"Klaar", with one extra choice when other is given (True when that was chosen)."""
        if self.flow is not None:
            return self.flow.finish(text, other)
        box = QMessageBox(QMessageBox.Information, APP_NAME, text, QMessageBox.Ok, self)
        extra = box.addButton(other, QMessageBox.ActionRole) if other else None
        box.exec()
        return extra is not None and box.clickedButton() is extra

    def _card_poll(self, text: str):
        """While "put the card in" is shown: a check that the card is there now (then the step goes on).
        It goes on only once a card or diskette has been put in: one that was still in when the question
        came (a diskette that did not eject) does not count until it has been out."""
        from ..core import cards
        t = self.presenter.t
        known = {t("no_kn7000_card"): (cards.KN7000,), t("no_target_card"): (cards.KN7000, cards.EMPTY),
                 t("no_floppy"): (cards.FLOPPY,), t("no_card_or_floppy"): (cards.KN7000, cards.FLOPPY)}
        # lines may be added to the question (what is in it now; practising: how a card goes in), so it is
        # known by its first paragraph
        kinds = next((k for q, k in known.items() if text.startswith(q.partition("\n\n")[0])), None) \
            or tuple(getattr(self.presenter, "waiting_for", ()) or ()) or None
        if kinds is None:
            return None

        def present() -> bool:
            try:
                return any(c.kind in kinds for c in self.presenter.find_cards())
            except OSError:
                return False
        state = {"was_out": not present()}

        def poll() -> bool:
            if present():
                return state["was_out"]
            state["was_out"] = True
            return False
        return poll

    def ask(self, text: str, buttons: List[str]) -> Optional[int]:
        if self.flow is not None:
            poll = self._card_poll(text)
            if poll:
                self.flow.goto("step_find")
                self.flow.goto("step_card")
            else:
                self.flow.goto("step_name")
            return self.flow.ask(text, buttons, poll)
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setText(text)
        made = [box.addButton(b, QMessageBox.AcceptRole) for b in buttons]
        cancel = box.addButton(self.presenter.t("btn_cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(made[0])
        box.setEscapeButton(cancel)
        box.exec()
        clicked = box.clickedButton()
        return made.index(clicked) if clicked in made else None

    def ask_text(self, text: str, default: str = "", name: bool = False) -> Optional[str]:
        if self.flow is not None:
            self.flow.goto("step_name")
            return self.flow.ask_text(text, default, name)
        if name:
            value, ok = get_name(self, APP_NAME, text, default)
            return value if ok else None
        value, ok = QInputDialog.getText(self, APP_NAME, text, text=default)
        return value if ok else None

    def ask_volume_name(self, text: str, default: str = "") -> Optional[str]:
        """The new card's name, limited to what an SD card can be called."""
        dlg = QInputDialog(self)
        dlg.setWindowTitle(APP_NAME)
        dlg.setLabelText(text)
        dlg.setInputMode(QInputDialog.TextInput)
        volume_field(dlg.findChild(QLineEdit))
        dlg.setTextValue(default)
        return dlg.textValue() if dlg.exec() else None

    def pick_dir(self, title: str, start: str, accept: str) -> str:
        """Choose a folder. The button says what happens ("Kopie hier maken"), not the system's "Open":
        on a Mac the title of this window is not shown, so the button is what the user reads."""
        dlg = QFileDialog(self, title, start)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setLabelText(QFileDialog.Accept, accept)
        if dlg.exec() != QDialog.Accepted or not dlg.selectedFiles():
            return ""
        return dlg.selectedFiles()[0]

    def pick_folder(self, text: str) -> Optional[str]:
        path = self.pick_dir(text, str(self.settings.value("last_card", "")), self.presenter.t("btn_pick_card"))
        return path or None

    # ------------------------------------------------------------------ long work off the GUI thread
    # which step of the step window a job belongs to (the first of these that the window has)
    BUSY_STEPS = {"saving": ("step_write", "step_keep", "step_repair"), "archiving": ("step_write", "step_keep"),
                  "reading_floppy": ("step_keep",), "restoring": ("step_restore",), "backing_up": ("step_backup",),
                  "copying_library": ("step_copy",)}

    def run_busy(self, text: str, job, phases=(), hold: str = ""):
        """Run job(progress) on a worker thread and wait for it without freezing the window: a local
        event loop keeps painting and shows a progress window, but ignores clicks and keys so nothing
        can change the card while the job runs. Returns the job's result or raises its exception."""
        if self._busy_running or QThread.currentThread() is not self.thread():
            return job(None)                                    # nested: already on the worker
        self._busy_running = True
        t = self.presenter.t
        if self.flow is not None:
            for key, steps in self.BUSY_STEPS.items():
                if text == t(key):
                    keys = [k for k, _ in self.flow.steps]
                    first = next((k for k in steps if k in keys), None)
                    if first:
                        self.flow.goto(first)
            self.flow.busy(text, phases, hold)
        else:
            self.busy_bar.start(text)
        details = self._detail_timer.isActive()             # the job may read the same library files
        self._detail_timer.stop()
        thread = QThread()
        worker = _Worker(job)
        worker.moveToThread(thread)
        loop = QEventLoop()
        worker.progressed.connect(self._busy_progress)
        worker.done.connect(loop.quit)
        thread.started.connect(worker.run)
        thread.start()
        loop.exec(QEventLoop.ExcludeUserInputEvents)
        thread.quit()
        thread.wait()
        self._busy_running = False
        if details and self.presenter.library is not None:
            self._detail_timer.start()
        self.busy_bar.hide()
        if worker.error is not None:
            raise worker.error
        return worker.result

    def _busy_progress(self, i: int, n: int, text: str) -> None:
        if self._busy_running and (self.flow is not None or i >= 0):     # i < 0: a part of the job begins
            (self.flow or self.busy_bar).progress(i, n, text)

    def _build_lists_dock(self):
        p = self.presenter
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        self.tabs = QTabWidget(w)
        self.tabs.setDocumentMode(True)                    # no frame around the page: nothing to stick out of
        fav = QWidget(self.tabs)
        fl = QVBoxLayout(fav)
        fl.setContentsMargins(0, style.px(10), 0, 0)
        row = QHBoxLayout()
        self.bank_box = QComboBox(fav)
        self.bank_box.currentIndexChanged.connect(lambda i: i >= 0 and not self._filling and p.select_bank(i + 1))
        self.bank_rename = ShrinkButton(fav, 44)          # a narrow side panel: then only its pencil
        self.bank_rename.clicked.connect(self._rename_bank)
        row.addWidget(self.bank_box)
        row.addWidget(self.bank_rename, 1)
        fl.addLayout(row)
        self.fav_table = FavoriteTable(self)
        self.fav_table.currentCellChanged.connect(lambda *_: self._update_fav_put())
        fl.addWidget(self.fav_table)
        frow = QVBoxLayout()
        self.fav_put = QPushButton(fav)
        self.fav_put.clicked.connect(self._fav_put)
        self.fav_clear = QPushButton(fav)
        self.fav_clear.clicked.connect(lambda: self.fav_table.currentRow() >= 0
                                       and p.set_favorite(self.fav_table.currentRow() + 1, None))
        frow.addWidget(self.fav_put)
        frow.addWidget(self.fav_clear)
        fl.addLayout(frow)
        self.tabs.addTab(fav, "")
        sl = QWidget(self.tabs)
        ll = QVBoxLayout(sl)
        ll.setContentsMargins(0, style.px(10), 0, 0)
        self.list_box = QComboBox(sl)
        self.list_box.addItems(["1", "2", "3"])
        self.list_box.currentIndexChanged.connect(lambda i: i >= 0 and p.select_song_list(i + 1))
        ll.addWidget(self.list_box)
        self.song_list = SongListWidget(self)
        ll.addWidget(self.song_list)
        lrow = QVBoxLayout()
        self.list_add = QPushButton(sl)
        self.list_add.clicked.connect(lambda: self.selected_slots() and p.add_to_song_list(self.selected_slots()))
        self.list_remove = QPushButton(sl)
        self.list_remove.clicked.connect(lambda: p.remove_from_song_list(
            [self.song_list.row(i) for i in self.song_list.selectedItems()]))
        lrow.addWidget(self.list_add)
        lrow.addWidget(self.list_remove)
        ll.addLayout(lrow)
        self.tabs.addTab(sl, "")
        lay.addWidget(self.tabs)
        w.setMinimumWidth(style.px(320))
        self.lists_dock = QDockWidget(self)
        self.lists_dock.setObjectName("lists")
        self.lists_dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, self.lists_dock)
        self.tabifyDockWidget(self.dock, self.lists_dock)
        self.dock.raise_()

    def _build_other_dock(self):
        p = self.presenter
        w = QWidget(self)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        self.other_label = QLabel(w)
        self.other_label.setWordWrap(True)
        self.other_folder = QComboBox(w)
        self.other_folder.currentIndexChanged.connect(
            lambda i: i >= 0 and not self._filling and p.select_other_folder(self.other_folder.itemData(i)))
        self.other_songs = OtherSongTable(self)
        lay.addWidget(self.other_label)
        lay.addWidget(self.other_folder)
        lay.addWidget(self.other_songs)
        self.other_dock = QDockWidget(self)
        self.other_dock.setObjectName("other")
        self.other_dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, self.other_dock)
        self.other_dock.hide()

    def _fav_put(self) -> None:
        slots = self.selected_slots()
        row = max(self.fav_table.currentRow(), 0)
        if slots:
            self.presenter.set_favorite(row + 1, slots[0])

    def _rename_bank(self):
        p = self.presenter
        if p.session is None:
            return
        cur = p.session.db.favorites[p.bank - 1].name
        name, ok = get_name(self, p.t("act.rename_bank"), p.t("new_name"), cur)
        if ok:
            p.rename_bank(name)

    def _open_other(self):
        path = self.pick_dir(self.presenter.t("act.open_other"), str(self.settings.value("last_other", "")),
                             self.presenter.t("btn_pick_card"))
        if path and self.presenter.open_other(path):
            self.settings.setValue("last_other", path)
            self.other_dock.show()
            self.other_dock.raise_()

    # ------------------------------------------------------------------ actions and menus
    def _build_actions(self):
        p = self.presenter
        spec = [
            ("open", QKeySequence.Open, self._open),
            ("open_library", None, self._open_library),
            ("save", QKeySequence.Save, self._save),
            ("backups", None, self._backups), ("export_csv", None, self._export_csv),
            ("copy_library", None, self._copy_library),
            ("export_pdf", None, self._export_pdf), ("quit", QKeySequence.Quit, self.close),
            ("undo", QKeySequence.Undo, self._undo), ("redo", QKeySequence.Redo, self._redo),
            ("rename", "F2", self._rename), ("delete", [QKeySequence.Delete, "Ctrl+Backspace"], self._delete),
            # Cmd+M is "minimise" on a Mac: moving songs is Shift+Cmd+M
            ("move", "Ctrl+Shift+M", lambda: self._move(False)), ("copy", "Ctrl+Shift+C", lambda: self._move(True)),
            ("find", QKeySequence.Find, self._find), ("select_all", QKeySequence.SelectAll, self._select_all),
            ("new_folder", "Ctrl+Shift+N", self._new_folder),
            ("rename_folder", "Shift+F2", self._rename_folder),
            ("check", None, self._check), ("repair", None, p.repair), ("check_card", "Ctrl+K", self._check_card),
            ("duplicates", None, self._duplicates),
            ("open_other", "Ctrl+Shift+O", self._open_other), ("close_other", None, p.close_other),
            ("lists", "Ctrl+L", lambda: None), ("history", None, lambda: None),     # on/off, see below
            ("library", "Ctrl+Shift+L", self._toggle_library), ("start", QKeySequence.Back, self.go_start),
            ("info_panel", "Ctrl+I", self._toggle_info), ("info_detail", None, self.info_detail),
            ("text_bigger", QKeySequence.ZoomIn, lambda: self._step_text_size(1)),
            ("text_smaller", QKeySequence.ZoomOut, lambda: self._step_text_size(-1)),
            ("put_on_card", None, self._put_on_card),
            ("help", QKeySequence.HelpContents, lambda: HelpDialog(self, self.presenter.page).exec()),
            ("about", None, lambda: AboutDialog(self).exec()),
        ]
        self.acts = {}
        for key, shortcut, slot in spec:
            a = QAction(self)
            if isinstance(shortcut, list):
                a.setShortcuts([QKeySequence(k) for k in shortcut])
            elif shortcut:
                a.setShortcut(shortcut)
            a.triggered.connect(slot)
            self.acts[key] = a
        self.acts["library"].setCheckable(True)
        for key in ("info_panel", "info_detail"):
            self.acts[key].setCheckable(True)
        self.acts["info_panel"].setChecked(str(self.settings.value("info/visible", "1")) == "1")
        self.acts["info_detail"].setChecked(self.info.detailed)
        self.acts["about"].setMenuRole(QAction.AboutRole)       # macOS: in the app menu, as usual there
        # "Wat ik gedaan heb" and "Favorieten en songlijsten" switch their panel on and off, with a tick
        for key, dock in (("history", self.dock), ("lists", self.lists_dock)):
            a = self.acts[key]
            a.setCheckable(True)
            a.toggled.connect(lambda on, d=dock: (d.show(), d.raise_()) if on else d.hide())
            dock.installEventFilter(self)               # the tick follows the panel (also its own cross)
        self._ticks = {self.dock: self.acts["history"], self.lists_dock: self.acts["lists"]}
        self.acts["save"].triggered.disconnect()
        self.acts["save"].triggered.connect(self._put_on_card)     # Cmd+S = "Op kaart zetten"
        mb = self.menuBar()
        self.menus = {}
        # Bestand: cards in and out. Bewerken: changing songs. Weergave: panels on/off (with a tick).
        # Extra: looking into songs, and help when something is wrong. One way for each thing: "Kaart doet
        # raar?" checks and offers the repair, so "check" and "repair" are not listed on their own.
        for key, names in [("file", ["start", None, "open", "open_library", "copy_library", None, "save",
                                     None, "open_other", "close_other", None, "export_pdf", "export_csv", None, "quit"]),
                           ("edit", ["undo", "redo", None, "find", "select_all", None, "rename", "move", "copy",
                                     "delete", None, "new_folder", "rename_folder"]),
                           ("view", ["library", "lists", "history", None, "info_panel", "info_detail"]),
                           ("tools", ["duplicates", None, "check_card", "backups"])]:
            m = mb.addMenu("")
            for n in names:
                if n is None:
                    m.addSeparator()
                else:
                    m.addAction(self.acts[n])
            self.menus[key] = m
        self.menus["textsize"] = self.menus["view"].addMenu("")      # Weergave › Lettergrootte
        group = QActionGroup(self)
        self.size_acts = {}
        now = str(self.settings.value("text_size", "normal"))
        for key in style.TEXT_SIZES:
            a = self.menus["textsize"].addAction("")
            a.setCheckable(True)
            a.setChecked(key == now)
            group.addAction(a)
            a.triggered.connect(lambda _=False, k=key: self._set_text_size(k))
            self.size_acts[key] = a
        self.menus["textsize"].addSeparator()
        self.menus["textsize"].addAction(self.acts["text_bigger"])
        self.menus["textsize"].addAction(self.acts["text_smaller"])
        self.menus["language"] = mb.addMenu("")
        langs = QActionGroup(self)                        # a tick at the language in use, like Lettergrootte
        self.lang_acts = {}
        for code, label in LANGUAGES.items():
            a = self.menus["language"].addAction(label)
            a.setCheckable(True)
            a.setChecked(code == self.presenter.lang)
            langs.addAction(a)
            a.triggered.connect(lambda _=False, c=code: self._set_language(c))
            self.lang_acts[code] = a
        self.menus["help"] = mb.addMenu("")
        self.menus["help"].addAction(self.acts["help"])
        self.menus["help"].addAction(self.acts["about"])

    def _toggle_info(self, on: bool) -> None:
        """Weergave > Informatie over de song: the panel on the right on or off (remembered)."""
        self.settings.setValue("info/visible", "1" if on else "0")
        self.info.setVisible(on and self.presenter.page != "start")

    def info_detail(self, on: bool) -> None:
        """Weergave > Uitgebreide informatie: every value read, or only what a player needs (remembered)."""
        self.info.set_detailed(on)

    def _toggle_library(self, on: bool) -> None:
        if self.presenter.page == "compose":
            self.acts["library"].setChecked(True)
            return
        if on and self.presenter.library is None:
            lib = self.library_folder()
            if lib:
                self.open_library(lib)
        self._library_beside(on)

    def _library_beside(self, on: bool) -> None:
        """The library on the left, and then both sides with a heading of their own."""
        self.library_panel.setVisible(on)
        self.card_head.setVisible(on)

    def retranslate(self) -> None:
        for sp in self.findChildren(GripSplitter):
            sp.set_tip(self.presenter.t("splitter_tip"))
        t = self.presenter.t
        for key, a in self.acts.items():
            a.setText(t("act." + key))
        for key, m in self.menus.items():
            m.setTitle(t("menu." + key))
        for key, a in self.size_acts.items():
            a.setText(t("textsize." + key))
        self.search.setPlaceholderText(t("search"))
        self.folders.new_button.setText(gap(t("btn_new_folder")))
        for key, b in self.song_buttons.items():
            b.setText(t(key))                           # shortened with "…" only when there is no room
        self.empty_hint.setText(t("folder_empty_hint"))
        self.folders.apply_folding()
        self.library_panel.retranslate(t)
        self.card_head.set_text(t("card_head"), t("card_head_info"))
        self.welcome_text.setText(t("welcome"))
        self.start_title.setText(t("start_question"))
        self.practice_button.setText(t("practice_link"))
        self.practice_text.setText(t("practice_banner"))
        self.practice_swap.setText(t("btn_practice_swap"))
        self.practice_stop.setText(t("btn_practice_stop"))
        for key, b in self.task_buttons.items():
            b.setText(t(key) + "\n" + t(key + "_info"))
        self.back_button.setText(gap(t("btn_back")))
        self.more_button.setText(t("btn_more"))
        self.help_button.setText(t("btn_help"))
        self.help_button.setToolTip(t("help_title"))
        self.tip_ok.setText(t("btn_got_it"))
        self.undo_button.setText(t("act.undo"))
        self.redo_button.setText(t("act.redo"))
        self.put_button.setText(gap(t("btn_put_on_card")))
        self.page_title.setText((t("practice_bar") if self.presenter.practice else t({"organize": "task_organize", "compose": "task_compose"}.get(self.presenter.page, "start_question"))))
        for key, b in self.welcome_buttons.items():
            b.setText(t("act." + key))
        self.dock.setWindowTitle(t("history"))
        self.lists_dock.setWindowTitle(t("lists"))
        self.other_dock.setWindowTitle(t("other"))
        self.tabs.setTabText(0, t("favorites"))
        self.tabs.setTabText(1, t("song_lists"))
        self.bank_rename.setText(t("btn_rename_bank"))    # the same words as for a song
        self._update_fav_put()
        self.fav_clear.setText(t("btn_remove_short"))
        self.list_add.setText(t("list_add"))
        self.list_remove.setText(t("btn_remove_short"))
        for i in range(3):
            self.list_box.setItemText(i, t("song_list_n", n=i + 1))

    def _set_text_size(self, key: str) -> None:
        """Weergave › Lettergrootte: seen at once. Every part takes its size from the letters when it is
        built, so the window is built again; the open card, the library and changes not on the card yet
        stay (they live in the presenter)."""
        if key == str(self.settings.value("text_size", "normal")):
            return
        self.settings.setValue("text_size", key)
        self.rebuild()

    def rebuild(self) -> "MainWindow":
        """A new window in the place of this one, with the same presenter. Gives the new window."""
        self._keep_layout()
        p = self.presenter
        new = MainWindow(self.settings, presenter=p)
        new.restoreGeometry(self.saveGeometry())
        for key in ("library", "info_panel", "lists", "history"):
            if key in self.acts and key in new.acts and self.acts[key].isCheckable():
                new.acts[key].setChecked(self.acts[key].isChecked())
        p.runner = new.run_busy
        if p.page != "start":
            new.show_page(p.page)
        p.refresh()
        if p.library is not None:
            p.show_library()
            new.fill_library_details_later()
        if self.isVisible():
            new.show()
        self._rebuilt = True
        self.close()
        self.deleteLater()
        return new

    def _step_text_size(self, step: int) -> None:
        """Cmd+plus / Cmd+minus: one text size bigger or smaller."""
        keys = list(style.TEXT_SIZES)
        now = str(self.settings.value("text_size", "normal"))
        i = max(0, min(len(keys) - 1, (keys.index(now) if now in keys else 0) + step))
        self.size_acts[keys[i]].setChecked(True)
        self._set_text_size(keys[i])

    def _find(self) -> None:
        """Cmd+F: to a search field. Putting a card together: the library's (that is where songs are
        looked for), unless you are working on the card's side; else the card's."""
        if self.presenter.page == "start":
            return
        lp, focus = self.library_panel, QApplication.focusWidget()
        on_card = focus is not None and self.card_side.isAncestorOf(focus)
        in_library = lp.isVisible() and (focus is not None and lp.isAncestorOf(focus)
                                         or self.presenter.page == "compose" and not on_card)
        field = lp.search if in_library else self.search
        field.setFocus()
        field.selectAll()

    def _select_all(self) -> None:
        """Cmd+A: everything in the list you are working in: the library's songs, the folders, or (when
        no list has the keyboard) the songs in the folder shown. A text field being typed in keeps its own."""
        here = QApplication.focusWidget()
        if isinstance(here, QAbstractItemView) and here.selectionMode() == QAbstractItemView.ExtendedSelection:
            here.selectAll()
            return
        if here is not None and self.library_panel.isAncestorOf(here):
            self.library_panel.table.setFocus()         # the library's search field or its card list
            self.library_panel.table.selectAll()
            return
        if self.presenter.page != "start" and self.presenter.session is not None:
            self.songs.setFocus()
            self.songs.selectAll()

    def _set_language(self, code):
        self.settings.setValue("language", code)
        self.presenter.set_language(code)

    # ------------------------------------------------------------------ MainView protocol
    def show_folders(self, rows: List[FolderRow], current: int) -> None:
        self._filling = True
        self.folders._target = self.folders._insert_before = None
        self.folders.clear()
        t = self.presenter.t
        for r in rows:
            if r.used or r.name:
                it = QListWidgetItem("%02d  %s  (%d)" % (r.folder, r.name or t("noname"), r.used))
            else:
                it = QListWidgetItem("%02d  %s" % (r.folder, t("folder_unused")))   # short: fits a narrow list
            it.setData(Qt.UserRole, r.folder)
            it.setData(Qt.UserRole + 1, "%02d %s" % (r.folder, r.name or t("noname")))
            it.setData(Qt.UserRole + 2, bool(r.used or r.name))        # in use: a folder drag inserts
            if not r.used:
                it.setForeground(style.colour("muted"))
            self.folders.addItem(it)
            if r.folder == current:
                self.folders.setCurrentItem(it)
        if rows:
            tg = QListWidgetItem()
            tg.setFlags(Qt.ItemIsEnabled)                               # clickable, not selectable or a target
            tg.setForeground(style.colour("muted"))
            self.folders.addItem(tg)
            self.folders.toggle_item = tg
        else:
            self.folders.toggle_item = None
        self.folders.apply_folding()
        self.folders.fit_width()
        self.folders.new_button.setVisible(bool(rows))
        self._filling = False

    def show_songs(self, rows: List[SongRow], search_mode: bool) -> None:
        self._filling = True
        t = self.presenter.t
        self.empty_hint.setVisible(bool(rows) and not search_mode and not any(r.used for r in rows))
        if self.presenter.composing:                    # "the card is empty" only when no folder has a song
            s = self.presenter.session
            card_empty = s is None or not any(x.used for f in s.db.folders for x in f.songs)
            key = "compose_empty_hint" if card_empty else "compose_folder_empty_hint"
        else:
            key = "folder_empty_hint"
        self.empty_hint.setText(t(key))
        self.songs.setHorizontalHeaderLabels([t("col.folder"), t("col.song"), t("col.name"), t("col.types")])
        self.songs.setColumnHidden(0, not search_mode)
        self.songs.fit_name()
        shown = (self.presenter.session, self.presenter.folder, search_mode and self.presenter.query)
        if shown != getattr(self, "_songs_shown", None):    # another folder: what was chosen in the last one
            self._songs_shown = shown                       # does not stay chosen on the same row numbers
            self.songs.clearSelection()
        self.songs.setRowCount(len(rows))
        for i, r in enumerate(rows):
            cells = ["%02d" % r.folder, "%02d" % r.song, r.name if r.used else "", r.types]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDropEnabled
                if r.used:
                    flags |= Qt.ItemIsDragEnabled
                    if c == 2:
                        flags |= Qt.ItemIsEditable
                else:
                    it.setForeground(style.colour("muted"))
                it.setFlags(flags)
                it.setData(Qt.UserRole, (r.folder, r.song))
                self.songs.setItem(i, c, it)
        fit_columns_once(self.songs, (0, 1))
        self._filling = False
        self._selection_changed()

    def show_history(self, done: List[str], undone: List[str]) -> None:
        self.history.clear()
        start = QListWidgetItem(self.presenter.t("history_start"))
        start.setData(Qt.UserRole, 0)
        self.history.addItem(start)
        for i, label in enumerate(done, 1):
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, i)
            self.history.addItem(it)
        self.history.setCurrentRow(len(done))
        for j, label in enumerate(undone, len(done) + 1):
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, j)
            it.setForeground(style.colour("muted"))
            self.history.addItem(it)

    def show_favorites(self, banks: List[str], bank: int, items: List[str]) -> None:
        self._filling = True
        if self.bank_box.count() != len(banks):
            self.bank_box.clear()
            self.bank_box.addItems(banks)
        else:
            for i, b in enumerate(banks):
                self.bank_box.setItemText(i, b)
        self.bank_box.setCurrentIndex(bank - 1)
        for i, text in enumerate(items):
            self.fav_table.setItem(i, 0, QTableWidgetItem(text))
        self._filling = False

    def show_song_list(self, n: int, rows) -> None:
        self.song_list.clear()
        for i, (_slot, label) in enumerate(rows, 1):
            self.song_list.addItem("%2d.  %s" % (i, label))

    def show_other(self, title: str, folders: List[FolderRow], current: int, songs: List[SongRow]) -> None:
        self._filling = True
        self.other_label.setText(title)
        self.other_folder.clear()
        for r in folders:
            if r.used or r.folder == current:
                self.other_folder.addItem("%02d  %s  (%d)" % (r.folder, r.name, r.used), r.folder)
        idx = self.other_folder.findData(current)
        self.other_folder.setCurrentIndex(idx)
        self.other_songs.setRowCount(len(songs))
        for i, r in enumerate(songs):
            for c, text in enumerate(["%02d" % r.song, r.name if r.used else self.presenter.t("empty")]):
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | (Qt.ItemIsDragEnabled if r.used else Qt.NoItemFlags))
                if not r.used:
                    it.setForeground(style.colour("muted"))
                it.setData(Qt.UserRole, (r.folder, r.song))
                self.other_songs.setItem(i, c, it)
        self.other_songs.resizeColumnToContents(0)
        if not title:
            self.other_dock.hide()
        self._filling = False

    def show_library(self, title: str, cards: List[str], rows) -> None:
        self._filling = True
        self.library_panel.show(title, cards, rows)
        self._filling = False
        self._export_acts()

    def _export_acts(self) -> None:
        """A song list can be made of the open card or of the library: either is enough."""
        if hasattr(self, "acts"):
            p = self.presenter
            on = p.session is not None or p.library is not None
            for key in ("export_csv", "export_pdf"):
                self.acts[key].setEnabled(on)

    def _open_library(self):
        t = self.presenter.t
        path = self.pick_dir(t("act.open_library"), str(self.settings.value("last_library", "")), t("btn_pick_library"))
        if path:
            self.open_library(path)

    def open_library(self, path: str) -> bool:
        ok = self.presenter.open_library(path)
        if ok and not self.presenter.practice:          # practising: its own library, not remembered
            self.settings.setValue("last_library", path)
        return ok

    def fill_library_details_later(self) -> None:
        """Read tempo, time signature and recording of the library songs bit by bit, after every
        (re)opening of the library: also after renaming or removing a card, keeping one, practising."""
        self._detail_timer.start()

    def _fill_details(self):
        if not self.presenter.fill_library_details():
            self._detail_timer.stop()

    def show_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def _undo(self) -> None:
        """Undo, and offer "Opnieuw" at the bottom (so a wrong undo is one click away from fixed)."""
        s = self.presenter.session
        before = len(s.history()) if s else 0
        self.presenter.undo()
        s = self.presenter.session
        if s and len(s.history()) < before and s.redo_history():
            self.toast.show_text(self.presenter.t("undone", what=s.redo_history()[0]), redo=True)

    def _redo(self) -> None:
        s = self.presenter.session
        before = len(s.history()) if s else 0
        self.presenter.redo()
        s = self.presenter.session
        if s and len(s.history()) > before:
            self.toast.show_text(self.presenter.t("redone", what=s.history()[-1]))

    def notify(self, text: str) -> None:
        self.toast.show_text(text)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            self.toast.place()
        self._fit_action_bar()

    def show_space(self, text: str) -> None:
        self.space.setText(text)

    def show_header(self, name: str, text: str, used: int, total: int) -> None:
        naming = self.presenter.composing                # a new card: its name can be chosen here
        self.card_title.setText(name + ("  \u270e" if naming else ""))
        self.card_title.setCursor(Qt.PointingHandCursor if naming else Qt.ArrowCursor)
        self.card_title.setToolTip(self.presenter.t("card_name_tip") if naming else "")
        self.card_title.setVisible(bool(name))
        self.meter_box.setVisible(total > 0)
        self.fullness.setText(text)
        self.meter_box.setMinimumWidth(max(style.px(180), self.fullness.sizeHint().width() + style.px(8)))    # never cut off
        self.meter.setRange(0, max(total, 1))
        self.meter.setValue(min(used, total))
        tip = self.presenter.t("meter_tip", used=used, total=total)
        self.meter_box.setToolTip(tip)
        # green while there is room, orange from 80 %, red from 95 %
        share = used / total if total else 0
        style.mark(self.meter, level="ok" if share < 0.8 else "warn" if share < 0.95 else "full")

    def show_error(self, text: str) -> None:
        self.error_count += 1
        self.error_box(text).exec()

    def error_box(self, text: str) -> QMessageBox:
        """What happened and what to do first; the details for a helper smaller and grey under it."""
        box = QMessageBox(QMessageBox.Warning, APP_NAME, text, QMessageBox.Ok, self.flow or self)
        head, sep, help_ = text.rpartition("\n\n")
        if sep and help_.startswith(self.presenter.t("help_details").split("{")[0]):
            box.setText(head)
            box.setInformativeText("<small style='color:gray'>%s</small>" % escape(help_))
        return box

    def set_title(self, text: str) -> None:
        self.setWindowTitle(text)

    def _song_acts(self) -> None:
        """The menu items for songs do what the buttons under the list do, and are grey at the same
        moments: nothing chosen, nothing to do (they used to stay clickable and then did nothing)."""
        if not hasattr(self, "acts"):                   # still being built
            return
        on = self.presenter.session is not None
        n = len(self.selected_slots()) if on else 0
        for key in ("move", "copy", "delete"):
            self.acts[key].setEnabled(n > 0)
        self.acts["rename"].setEnabled(n == 1)
        self.acts["rename_folder"].setEnabled(on and self.presenter.folder is not None)
        for key in ("find", "new_folder"):
            self.acts[key].setEnabled(on)
        self.acts["select_all"].setEnabled(on or self.presenter.library is not None)

    def set_actions(self, a: Actions) -> None:
        t = self.presenter.t
        for key in ("backups", "export_csv", "export_pdf", "rename", "rename_folder", "move", "copy",
                    "delete", "check", "repair", "check_card", "open_other", "close_other", "lists", "duplicates"):
            self.acts[key].setEnabled(a.card)
        self._export_acts()
        for key in ("check", "repair", "check_card"):      # a new card is not on a card yet: nothing to check
            self.acts[key].setEnabled(a.card and not a.composing)
        self.acts["save"].setEnabled(a.save)
        self.acts["put_on_card"].setEnabled(a.save)
        self.action_bar.setVisible(a.card)
        self.draft.setVisible(a.card and (a.pending > 0 or a.composing))
        if a.composing:
            self.draft_text.setText(t("draft_new") if a.pending else t("draft_new_empty"))
        else:
            self.draft_text.setText(t("draft_bar", n=a.pending))
        self.put_button.setEnabled(a.pending > 0)
        self.put_button.setToolTip("" if a.pending else t("compose_empty"))
        self.undo_button.setEnabled(a.undo)
        self.redo_button.setEnabled(a.redo)
        self.undo_button.setToolTip(a.undo_text)
        self.redo_button.setToolTip(a.redo_text)
        self.card_stack.setCurrentIndex(1 if a.card else 0)
        self.library_panel._update_part_button()
        self.acts["undo"].setEnabled(a.undo)
        self.acts["redo"].setEnabled(a.redo)
        self.acts["undo"].setText(t("act.undo") + (": " + a.undo_text if a.undo_text else ""))
        self.acts["redo"].setText(t("act.redo") + (": " + a.redo_text if a.redo_text else ""))
        self._song_acts()

    def choose(self, text: str, options: List[str]):
        if self.flow is not None:
            return self.flow.choose(text, options)
        item, ok = QInputDialog.getItem(self, APP_NAME, text, options, 0, False)
        return options.index(item) if ok and item in options else None

    def confirm(self, text: str) -> bool:
        if self.flow is not None:
            return self.flow.confirm(text)
        return QMessageBox.question(self, APP_NAME, text) == QMessageBox.Yes

    # ------------------------------------------------------------------ helpers
    def selected_slots(self):
        out = []
        for r in sorted({i.row() for i in self.songs.selectedIndexes()}):
            it = self.songs.item(r, 2)
            if it is not None and it.flags() & Qt.ItemIsDragEnabled:
                out.append(it.data(Qt.UserRole))
        return out

    def select_folders(self, folders) -> None:
        """Choose these folders in the folder list (after several moved or were copied in together)."""
        want = set(folders)
        self._filling = True
        for i in range(self.folders.count()):
            it = self.folders.item(i)
            if FolderList.is_folder(it):
                it.setSelected(it.data(Qt.UserRole) in want)
        self._filling = False

    def select_slots(self, slots) -> None:
        """Select these songs in the list (after they moved, the selection goes with them)."""
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        want = {tuple(x) for x in slots}
        sel = QItemSelection()
        for r in range(self.songs.rowCount()):
            it = self.songs.item(r, 2)
            if it is not None and tuple(it.data(Qt.UserRole) or ()) in want:
                sel.select(self.songs.model().index(r, 0), self.songs.model().index(r, self.songs.columnCount() - 1))
        self.songs.selectionModel().select(sel, QItemSelectionModel.ClearAndSelect)

    def _folder_changed(self, cur, _prev):
        if FolderList.is_folder(cur) and not self._filling:
            self.search.blockSignals(True)
            self.search.clear()
            self.search.blockSignals(False)
            self.presenter.select_folder(cur.data(Qt.UserRole))
            self.library_panel._update_add_button()

    def _song_edited(self, item: QTableWidgetItem):
        if self._filling or item.column() != 2:
            return
        f, s = item.data(Qt.UserRole)
        self.presenter.rename_song(f, s, item.text())

    def _open(self):
        path = self.pick_dir(self.presenter.t("act.open"), str(self.settings.value("last_card", "")),
                             self.presenter.t("btn_pick_card"))
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        if self.presenter.start_organize(path) and not self.presenter.practice:
            self.settings.setValue("last_card", path)

    def _save(self):
        self.presenter.save()

    def _rename(self):
        slots = self.selected_slots()
        if not slots:
            return
        if not self.presenter.query:
            self.songs.editItem(self.songs.item(slots[0][1] - 1, 2))
            return
        f, s = slots[0]
        p = self.presenter
        name, ok = get_name(self, p.t("act.rename"), p.t("new_name"))
        if ok:
            p.rename_song(f, s, name)

    def _new_folder(self):
        p = self.presenter
        if p.session is None:
            return
        name = self.ask_text(p.t("new_folder_name"), name=True)
        if name is not None:
            p.new_folder(name)

    def _rename_folder(self):
        p = self.presenter
        if p.session is None:
            return
        cur = p.session.db.folders[p.folder - 1].name
        name, ok = get_name(self, p.t("act.rename_folder"), p.t("new_name"), cur)
        if ok:
            p.rename_folder(p.folder, name)

    def _move(self, copy: bool):
        slots = self.selected_slots()
        if not slots:
            return
        p = self.presenter
        dlg = FolderPickerDialog(self, p.t("pick_copy_title" if copy else "pick_move_title"),
                                 p.folder_choices(0 if copy else p.folder))
        if dlg.exec() != QDialog.Accepted or dlg.folder() is None:
            return
        f = dlg.folder()
        if f == 0:                                          # "+ Nieuwe map…"
            name = self.ask_text(p.t("new_folder_name"), name=True)
            f = p.new_folder(name) if name is not None else None
            if f is None:
                return
        p.move_songs(slots, f, copy)

    def _delete(self):
        """Weghalen: the chosen songs; with the folder list in use (or several folders chosen and no
        song), the chosen folders with everything in them."""
        folders = self.folders.chosen_folders()
        slots = self.selected_slots()
        if folders and (self.folders.hasFocus() or (len(folders) > 1 and not slots)):
            self.presenter.delete_folders(folders)
            return
        self.presenter.delete_songs(slots)

    def _check(self):
        issues = self.presenter.check()
        QMessageBox.information(self, self.presenter.t("act.check"),
                                "\n".join(issues[:50]) or self.presenter.t("no_issues"))

    def _duplicates(self):
        rows = self.presenter.find_duplicates()
        if rows is None:
            return
        if not rows:
            QMessageBox.information(self, self.presenter.t("act.duplicates"), self.presenter.t("dups_none"))
            return
        DuplicatesDialog(self, rows).exec()

    def _copy_library(self):
        """Meer… › Kopie van de bibliotheek maken: choose the USB stick or disk, then copy with checks."""
        p, t = self.presenter, self.presenter.t
        if p.library is None:
            p.copy_library()                            # says that there is no library yet
            return
        start = str(self.settings.value("last_copy", "") or ("/Volumes" if sys.platform == "darwin" else ""))
        target = self.pick_dir(t("copy_pick"), start, t("btn_pick_copy"))
        if not target:
            return
        if self._in_flow("act.copy_library", ["step_copy", "step_done"], lambda: p.copy_library(target)):
            self.settings.setValue("last_copy", target)

    def _check_card(self):
        """Kaart doet raar?: Nakijken ─ Herstellen ─ Klaar in one step window."""
        return self._in_flow("act.check_card", ["step_check", "step_repair", "step_done"], self.presenter.check_card)

    def _backups(self):
        p = self.presenter
        dlg = BackupsDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        path = dlg.path()
        if dlg.action == "now":
            self._in_flow("btn_backup_now", ["step_backup", "step_done"], p.make_backup_now)
        elif dlg.action == "here" and path:
            self._in_flow("backup_restore_title", ["step_sure", "step_restore", "step_done"], lambda: p.restore(path))
        elif dlg.action == "new" and path:
            p.restore_as_new_card(path)
        elif dlg.action == "library" and path:
            self._in_flow("backup_library_title", ["step_name", "step_keep", "step_done"],
                          lambda: p.restore_to_library(path, dlg.library_name()))

    def _export_csv(self):
        self._export("csv")

    def _export_pdf(self):
        self._export("pdf")

    def _export(self, kind: str) -> None:
        """Ask what goes in the song list (remembered for next time), then where to save it."""
        p, t = self.presenter, self.presenter.t
        dlg = ExportDialog(self, kind)
        if dlg.exec() != QDialog.Accepted:
            return
        dlg.remember(self.settings)
        c = dlg.choice()
        kind = c["format"]                              # one window for both: the file is the only difference
        name, filt = ("songlijst.csv", "CSV (*.csv)") if kind == "csv" else ("songlijst.pdf", "PDF (*.pdf)")
        path, _ = QFileDialog.getSaveFileName(self, t("act.export_" + kind), name, filt)
        if not path:
            return
        lib, view = c["source"] != "card", c["source"] == "view"
        if kind == "csv":
            if lib:
                p.export_library_csv(path, c["fields"], by_name=c["by_name"], filtered=view)
            else:
                p.export_csv(path, c["fields"], c["folder"], by_name=c["by_name"], skip_empty=c["skip_empty"])
            return
        fit = list_fit(c["big"], c["landscape"])     # the columns get the room the page has
        if lib:
            html = p.library_list_html(c["fields"], c["by_name"], view, c["page"], title=c["title"], fit=fit)
        else:
            html = p.song_list_html(c["fields"], c["folder"], c["page"], skip_empty=c["skip_empty"],
                                    by_name=c["by_name"], title=c["title"], fit=fit)
        if html is not None:
            export_pdf(html, path, date=p.today_text() if c["date"] else "",
                       pages=t("pdf_page") if c["pages"] else "", big=c["big"], landscape=c["landscape"],
                       pt=p.list_font)
            self.show_status(t("exported", path=path))

    def closeEvent(self, ev):
        if getattr(self, "_rebuilt", False):            # a new window took over (rebuild): nothing is lost
            ev.accept()
            return
        s = self.presenter.session
        if s and (s.dirty or self.presenter.composing) and not self.confirm(self.presenter.t("confirm_quit")):
            ev.ignore()
            return
        self._keep_layout()
        ev.accept()

    def _keep_layout(self) -> None:
        self.settings.setValue("geometry", self.saveGeometry())
        self._save_splits()
        for key, table in self._column_tables():
            self.settings.setValue(key, table.horizontalHeader().saveState())

    def _organize_sizes(self) -> List[int]:
        """Folders and songs as wide as their longest possible name (NAME_LEN characters), the rest for
        the info panel."""
        fm = self.songs.fontMetrics()
        name = max(fm.horizontalAdvance("Zomeravond 12345"), fm.averageCharWidth() * NAME_LEN)
        folders = fm.horizontalAdvance("99  ") + name + fm.horizontalAdvance("  (20)") + 50
        songs = max(fm.horizontalAdvance("Nr"), fm.horizontalAdvance("00")) + 30 + name + 30 + 40
        if not self.songs.isColumnHidden(3):            # the file types: LSW PMT SQT CMP TM and so on
            songs += fm.horizontalAdvance("LSW PMT SQT CMP TM EFC") + 20
        total = sum(self.split.sizes()) or 1200
        return [folders, songs, max(total - folders - songs, 300)]

    def _save_splits(self) -> None:
        """The panel widths the user dragged to, per kind of page (organising and composing differ)."""
        page = getattr(self, "_split_page", None)
        if page and self.split.isVisible():
            self.settings.setValue("splits/%s/card" % page, ",".join(map(str, self.split.sizes())))
            if self.library_panel.isVisible():
                self.settings.setValue("splits/%s/main" % page, ",".join(map(str, self.main_split.sizes())))

    def _restore_splits(self, force: bool = False) -> None:
        """The saved panel widths of this kind of page; else (when force) the defaults."""
        page = self._split_page
        for sp, key in ((self.split, "card"), (self.main_split, "main")):
            saved = str(self.settings.value("splits/%s/%s" % (page, key), "") or "")
            try:
                sizes = [int(x) for x in saved.split(",")] if saved else []
            except ValueError:
                sizes = []
            if len(sizes) == sp.count() and all(x > 0 for x in sizes):
                sp.setSizes(sizes)
            elif force:
                sp.setSizes(sp.default_sizes)

    def _column_tables(self):
        return [("columns/songs", self.songs), ("columns/library", self.library_panel.table)]

    def _restore_columns(self) -> None:
        """The column widths of last time (see user_columns)."""
        for key, table in self._column_tables():
            state = self.settings.value(key)
            if state and table.horizontalHeader().restoreState(state):
                table.setProperty("kn_songboek_fitted", True)
        h = self.songs.horizontalHeader()                # a Naam saved while squeezed does not stay squeezed
        self.songs.name_want = max(h.sectionSize(2), self.songs.name_width)
        self.songs.fit_name()


def export_pdf(html: str, path: str, date: str = "", pages: str = "", big: bool = False,
               landscape: bool = False, pt: Optional[float] = None) -> None:
    """The song list as an A4 PDF. Under each page, small and grey: the date on the left and pages
    ("Pagina {n} van {total}") on the right, when given. big: larger letters, for the music stand.
    landscape: A4 on its side, for a list with many columns. pt: the letter size (list_fit chose it so the
    columns fit), else 11 or 15 (big)."""
    w = QPdfWriter(path)
    w.setPageSize(QPageSize(QPageSize.A4))
    w.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    w.setResolution(PDF_DPI)
    w.setPageMargins(QMarginsF(15, 15, 15, 12), QPageLayout.Millimeter)
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(w)          # sizes in points on paper, not on the screen
    font = QFont(doc.defaultFont())
    font.setPointSizeF(pt or (15 if big else 11))
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0)
    doc.setHtml(html)
    area = w.pageLayout().paintRectPixels(w.resolution())
    small = QFont(font)
    small.setPointSizeF(8)
    fm = QFontMetricsF(small, w)
    foot = fm.height() * 2.5 if (date or pages) else 0.0
    body = QSizeF(area.width(), area.height() - foot)
    doc.setPageSize(body)
    total = doc.pageCount()
    painter = QPainter(w)
    try:
        for i in range(total):
            if i:
                w.newPage()
            draw_page(painter, doc, i, body)
            if foot:
                painter.setFont(small)
                painter.setPen(QColor(110, 110, 110))     # paper is always white: no theme colour here
                line = QRectF(0, area.height() - fm.height(), area.width(), fm.height())
                painter.drawText(line, Qt.AlignLeft | Qt.AlignVCenter, date)
                painter.drawText(line, Qt.AlignRight | Qt.AlignVCenter, pages.format(n=i + 1, total=total))
    finally:
        painter.end()


PDF_DPI = 150
LIST_SIZES = (11.0, 9.5, 8.0)              # letter sizes a song list may use, largest first
LIST_SIZES_BIG = (15.0, 13.0, 11.0)
LIST_GAP = 26.0                            # room per column for its cell padding, in PDF pixels (measured)


def list_fit(big: bool = False, landscape: bool = False) -> List[Tuple[float, tuple]]:
    """For each letter size a printed song list may use (largest first): (size, (width, measure, gap)),
    with the width between the margins of A4 (15 mm each side) and measure(text, bold) the real width
    of a text in the font the PDF uses, so the columns get exactly the room the page has."""
    img = QImage(10, 10, QImage.Format_RGB32)
    img.setDotsPerMeterX(round(PDF_DPI / 0.0254))
    img.setDotsPerMeterY(round(PDF_DPI / 0.0254))
    width = ((297 if landscape else 210) - 30) / 25.4 * PDF_DPI
    out = []
    for pt in (LIST_SIZES_BIG if big else LIST_SIZES):
        font = QFont(QTextDocument().defaultFont())
        font.setPointSizeF(pt)
        bold = QFont(font)
        bold.setBold(True)
        plain_m, bold_m = QFontMetricsF(font, img), QFontMetricsF(bold, img)
        cache: dict = {}

        def measure(text: str, is_bold: bool = False, plain_m=plain_m, bold_m=bold_m, cache=cache) -> float:
            key = (text, is_bold)
            if key not in cache:
                cache[key] = (bold_m if is_bold else plain_m).horizontalAdvance(text)
            return cache[key]
        out.append((pt, (width * 0.99, measure, LIST_GAP)))
    return out


def draw_page(painter: QPainter, doc: QTextDocument, i: int, body: QSizeF) -> None:
    """Page i of doc, in black on the white paper. Not drawContents: that takes the text colour of
    the app, which is white in dark mode, so the PDF would look empty."""
    painter.save()
    painter.translate(0, -i * body.height())
    clip = QRectF(0, i * body.height(), body.width(), body.height())
    painter.setClipRect(clip)
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.clip = clip
    pal = QPalette()
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        pal.setColor(role, QColor(0, 0, 0))
    ctx.palette = pal
    doc.documentLayout().draw(painter, ctx)
    painter.restore()


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    from ..storage import windows
    windows.own_taskbar_icon()
    app = QApplication(argv)
    app.setApplicationName("kn-songboek")
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(icons.app_icon())
    w = MainWindow()
    if len(argv) > 1:                   # a card given on the command line: open it straight away
        w.open_path(argv[1])
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
