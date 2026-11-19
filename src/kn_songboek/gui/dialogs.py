"""The windows that open over the main window: help, the step window for the big jobs (FlowDialog),
export, "Meer…", folder picker, song contents, back-ups, about and duplicates."""
from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, List, Optional

from PySide6.QtCore import (
    QEventLoop,
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import backup
from . import icons, style
from .widgets import DOCS, HELP_CHAPTERS, MANUAL_FILES, GripSplitter, _chip_height, gap, manual_chapters, manual_for_this_computer, name_field  # noqa: F401

if TYPE_CHECKING:
    from .qt_app import MainWindow

SHOW_FOLDER = "btn_show_folder"                 # "Toon in Verkenner" on Windows (i18n.tr)

class HelpDialog(QDialog):
    """The ?-button: the chapters of the manual about this screen, with its pictures."""

    def __init__(self, win: "MainWindow", page: str):
        super().__init__(win)
        from PySide6.QtWidgets import QTextBrowser
        t = win.presenter.t
        self.setWindowTitle(t("help_title"))
        self.missing = t("help_missing")
        lay = QVBoxLayout(self)
        self.view = QTextBrowser(self)
        self.view.setOpenExternalLinks(True)
        lang = win.presenter.lang if win.presenter.lang in MANUAL_FILES else "nl"
        path = os.path.join(DOCS, MANUAL_FILES[lang])
        self.view.setSearchPaths([os.path.dirname(path)])      # the pictures: ../img/… from docs/nl or docs/en
        try:
            with open(path, encoding="utf-8") as fh:
                self.text = manual_for_this_computer(fh.read(), sys.platform.startswith("win"), lang)
        except OSError:
            self.text = ""
        self.show_part(HELP_CHAPTERS.get(page, []))
        lay.addWidget(self.view, 1)
        row = QHBoxLayout()
        whole = QPushButton(t("help_all"), self)
        whole.clicked.connect(lambda: self.show_part([]))
        close = QPushButton(t("close"), self)
        close.clicked.connect(self.accept)
        row.addWidget(whole)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)
        self.resize(style.px(820), style.px(640))

    def show_part(self, numbers) -> None:
        if not self.text:
            self.view.setPlainText(self.missing)
            return
        from PySide6.QtGui import QTextCursor
        self.view.setMarkdown(manual_chapters(self.text, numbers))
        # pictures at the window's width instead of full size
        doc = self.view.document()
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.isImageFormat():
                    img = fmt.toImageFormat()
                    img.setWidth(720)
                    cur = QTextCursor(doc)
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                    cur.setCharFormat(img)
                it += 1
            block = block.next()


class StepBadge(QWidget):
    """The round mark of one step in the step window: a number in a grey ring (still to come), a
    number on a blue disc (now) or a green tick in a green ring (done). Painted, so it follows light
    and dark and the text size."""

    def __init__(self, number: int, parent: QWidget):
        super().__init__(parent)
        self.number = number
        self.state = "todo"
        side = max(style.px(32), int(self.fontMetrics().height() * 1.8))
        self.setFixedSize(side, side)

    def set_state(self, state: str) -> None:
        self.state = state
        self.update()

    def paintEvent(self, _event) -> None:
        from PySide6.QtCore import QPointF, QRectF
        from PySide6.QtGui import QPainter, QPainterPath, QPen
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = 2.0 * self.width() / 32
        r = QRectF(self.rect()).adjusted(w, w, -w, -w)
        if self.state == "now":
            p.setPen(Qt.NoPen)
            p.setBrush(style.colour("accent"))
            p.drawEllipse(r)
            colour = style.colour("on_accent")
        else:
            colour = style.colour("ok" if self.state == "done" else "muted")
            p.setPen(QPen(colour, w))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r)
        if self.state == "done":                        # a tick, drawn: the same in every font
            s = self.width() / 32.0
            path = QPainterPath(QPointF(10.5 * s, 16.5 * s))
            path.lineTo(QPointF(14.5 * s, 20.5 * s))
            path.lineTo(QPointF(21.5 * s, 12 * s))
            pen = QPen(colour, w * 1.1)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)
        else:
            f = self.font()
            f.setBold(self.state == "now")
            f.setPixelSize(int(self.height() * 0.48))
            p.setFont(f)
            p.setPen(colour)
            p.drawText(r, Qt.AlignCenter, str(self.number))
        p.end()


class FlowDialog(QDialog):
    """One window with numbered steps for the big, rare jobs (put on card, keep in library, check the
    card, back-ups): (1) Welke kaart ─ (2) Op kaart zetten ─ (3) Klaar on a light band at the top, with
    "Stap 2 van 3" under it. Done steps get a green tick. The presenter asks its questions as usual;
    while a flow is open the main window shows them here, one at a time, with big buttons (Annuleren
    on the left, the next step on the right). While the computer works, the parts of the job are listed
    and ticked off, with "Haal de kaart er nog niet uit" under the bar; it ends with a large tick
    instead of a message box. Closing the window cancels, like the Annuleren buttons."""

    def __init__(self, win: "MainWindow", title: str, steps):
        super().__init__(win)
        self.win = win
        self.setWindowTitle(title)
        self.setWindowModality(Qt.ApplicationModal)
        self.steps = list(steps)                        # [(key, label)]
        self.step = 0
        self._answer = None
        self._loop: Optional[QEventLoop] = None
        self._poll: Optional[QTimer] = None
        self.bar: Optional[QProgressBar] = None
        self.phase_labels: List[QLabel] = []
        self.phases: List = []
        self.hold: Optional[QLabel] = None
        self.finish_button: Optional[QPushButton] = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        band = QFrame(self)
        band.setObjectName("stephead")
        bl = QVBoxLayout(band)
        bl.setContentsMargins(style.px(28), style.px(18), style.px(28), style.px(18))
        head = QLabel(title, band)
        f = head.font()
        f.setBold(True)
        f.setPointSize(int(f.pointSize() * 1.4))
        head.setFont(f)
        bl.addWidget(head)
        bl.addSpacing(style.px(12))
        row = QHBoxLayout()
        row.setSpacing(style.px(10))
        self.step_labels: List[QLabel] = []
        self.badges: List[StepBadge] = []
        for i, (_key, label) in enumerate(self.steps):
            if i:
                line = QFrame(band)
                line.setFrameShape(QFrame.HLine)
                style.mark(line, role="line")
                row.addWidget(line, 1)
            badge = StepBadge(i + 1, band)
            lab = QLabel(label, band)
            self.badges.append(badge)
            self.step_labels.append(lab)
            row.addWidget(badge)
            row.addWidget(lab)
        bl.addLayout(row)
        lay.addWidget(band)
        page = QWidget(self)
        self.page_lay = QVBoxLayout(page)
        self.page_lay.setContentsMargins(style.px(28), style.px(14), style.px(28), style.px(22))
        self.step_note = QLabel(page)                  # "Stap 2 van 3"
        style.mark(self.step_note, role="muted")
        self.page_lay.addWidget(self.step_note)
        self.body = QWidget(page)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, style.px(10), 0, 0)
        self.page_lay.addWidget(self.body, 1)
        lay.addWidget(page, 1)
        self.resize(style.px(680), style.px(470))
        self._paint_steps()

    # -- the step header
    def goto(self, key: str) -> None:
        keys = [k for k, _ in self.steps]
        if key in keys:
            self.step = keys.index(key)
            self._paint_steps()

    def _paint_steps(self) -> None:
        for i, (badge, lab) in enumerate(zip(self.badges, self.step_labels)):
            state = "done" if i < self.step else "now" if i == self.step else "todo"
            badge.set_state(state)
            style.mark(lab, step=state)
        n = len(self.steps)
        self.step_note.setText(self.win.presenter.t("step_of", i=min(self.step + 1, n), n=n))

    # -- the body: one question at a time
    def _clear(self) -> None:
        if self._poll is not None:
            self._poll.stop()
            self._poll.deleteLater()
            self._poll = None
        self.bar = None
        self.hold = None
        self.phase_labels, self.phases = [], []
        old = self.body
        self.body = QWidget(old.parentWidget())
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, style.px(10), 0, 0)
        self.page_lay.replaceWidget(old, self.body)
        old.hide()
        old.deleteLater()

    def _text(self, text: str, big: bool = False) -> QLabel:
        """A text in the body. big: the question of this step, its first line large and bold,
        the rest (what is in the reader now, how a card goes in) in plain letters under it."""
        head, _sep, rest = text.partition("\n") if big else (text, "", "")
        rest = rest.lstrip("\n")
        lab = QLabel(head, self.body)
        lab.setWordWrap(True)
        if big:
            f = lab.font()
            f.setPointSize(int(f.pointSize() * 1.3))
            f.setBold(True)
            lab.setFont(f)
        self.body_lay.addWidget(lab)
        if rest:
            self.body_lay.addSpacing(style.px(4))
            more = QLabel(rest, self.body)
            more.setWordWrap(True)
            self.body_lay.addWidget(more)
        return lab

    def _button(self, text: str, value, primary: bool = False, tall: bool = False) -> QPushButton:
        b = QPushButton(text, self.body)
        if tall:
            b.setMinimumHeight(style.px(58))
            b.setStyleSheet(style.sheet("QPushButton { text-align: left; padding: 8px 16px; }"))
        if primary:
            b.setDefault(True)
            style.mark(b, role="primary")
        b.clicked.connect(lambda _=False: self._give(value))
        return b

    def _cancel_row(self, *buttons: QPushButton) -> None:
        """Annuleren on the left, the way forward on the right (the blue one last)."""
        row = QHBoxLayout()
        cancel = QPushButton(self.win.presenter.t("btn_cancel"), self.body)
        cancel.clicked.connect(lambda _=False: self._give(None))
        row.addWidget(cancel)
        row.addStretch(1)
        for b in buttons:
            row.addWidget(b)
        self.body_lay.addLayout(row)

    def _give(self, value) -> None:
        self._answer = value
        if self._loop is not None:
            self._loop.quit()

    def _wait(self):
        self._answer = None
        if not self.isVisible():
            self.show()
        self._loop = QEventLoop()
        self._loop.exec()
        self._loop = None
        return self._answer

    def reject(self) -> None:                            # Esc or the window's close button: cancel
        self._give(None)
        super().reject()

    def ask(self, text: str, buttons: List[str], poll=None) -> Optional[int]:
        self._clear()
        self._text(text, big=True)
        self.body_lay.addStretch(1)
        made = [self._button(b, i, primary=(i == 0)) for i, b in enumerate(buttons)]
        self._cancel_row(*reversed(made))
        if poll is not None:                             # e.g. go on by itself once the card is put in
            self._poll = QTimer(self)
            self._poll.timeout.connect(lambda: poll() and self._give(0))
            self._poll.start(1500)
        return self._wait()

    def choose(self, text: str, options: List[str]) -> Optional[int]:
        self._clear()
        self._text(text, big=True)
        for i, o in enumerate(options):
            self.body_lay.addWidget(self._button(o, i, tall=True))
        self.body_lay.addStretch(1)
        self._cancel_row()
        return self._wait()

    def confirm(self, text: str) -> bool:
        self._clear()
        self._text(text, big=True)
        self.body_lay.addStretch(1)
        self._cancel_row(self._button(self.win.presenter.t("btn_continue"), True, primary=True))
        return bool(self._wait())

    def ask_text(self, text: str, default: str = "", name: bool = False) -> Optional[str]:
        self._clear()
        self._text(text, big=True)
        edit = QLineEdit(default, self.body)
        if name:
            name_field(edit)
        edit.setMinimumHeight(style.px(40))
        f = edit.font()
        f.setPointSize(int(f.pointSize() * 1.2))
        edit.setFont(f)
        self.body_lay.addWidget(edit)
        self.body_lay.addStretch(1)
        ok = self._button(self.win.presenter.t("btn_next"), True, primary=True)
        edit.returnPressed.connect(ok.click)
        self._cancel_row(ok)
        edit.setFocus()
        return edit.text() if self._wait() else None

    def busy(self, text: str, phases=(), hold: str = "") -> None:
        """The computer works: what it does, the parts of the job as a list (ticked off as they are
        done), a bar, and what must stay in ("Haal de kaart er nog niet uit.")."""
        self._clear()
        self._text(text, big=True)
        self.phases = list(phases)
        if self.phases:
            self.body_lay.addSpacing(style.px(6))
        for _key, label in self.phases:
            lab = QLabel(label, self.body)
            self.phase_labels.append(lab)
            self.body_lay.addWidget(lab)
        self._paint_phases(0)
        self.body_lay.addSpacing(style.px(10))
        self.bar = QProgressBar(self.body)
        self.bar.setObjectName("busybar")
        self.bar.setFixedHeight(style.px(10))
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.body_lay.addWidget(self.bar)
        if hold:
            self.body_lay.addSpacing(style.px(8))
            self.hold = self._text(hold)
            style.mark(self.hold, role="muted")
        self.body_lay.addStretch(1)
        if not self.isVisible():
            self.show()

    def _paint_phases(self, now: int) -> None:
        for i, ((_key, label), lab) in enumerate(zip(self.phases, self.phase_labels)):
            if i < now:
                lab.setText("\u2713  " + label)
                style.mark(lab, step="done")
            elif i == now:
                lab.setText("\u25cf  " + label + "\u2026")
                style.mark(lab, step="busy")
            else:
                lab.setText("\u25cb  " + label)
                style.mark(lab, step="todo")

    def progress(self, i: int, n: int, text: str) -> None:
        if i < 0:                                       # a new part of the job has started (n: its number)
            self._paint_phases(n)
            if self.bar is not None:
                self.bar.setRange(0, 0)
            return
        if self.bar is not None:
            self.bar.setRange(0, max(n, 1))
            self.bar.setValue(min(i, max(n, 1)))

    def finish(self, text: str, other: str = "") -> bool:
        """The last step: a big tick, what was done, and "Klaar". With other, a second button next to
        it (e.g. "Nog een kaart met dezelfde songs"); True when that one was chosen."""
        self._clear()
        self.step = len(self.steps) - 1                 # the steps before ticked, "Klaar" is where we are
        self._paint_steps()
        warn = "\n⚠" in text                            # a check found something: no big green tick
        tick = QLabel("⚠" if warn else "✓", self.body)
        f = tick.font()
        f.setPointSize(int(f.pointSize() * 4))
        f.setBold(True)
        tick.setFont(f)
        tick.setAlignment(Qt.AlignCenter)
        style.mark(tick, role="warn" if warn else "ok")
        self.body_lay.addWidget(tick)
        from html import escape
        self.setMinimumWidth(style.px(620))                       # room for a whole sentence per line
        paras = text.split("\n\n")
        head = paras[0].split("\n")                     # what happened, big; a line under it smaller
        lab = self._text(head[0], big=True)
        lab.setAlignment(Qt.AlignCenter)
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
        if head[1:]:
            sub = self._text("\n".join(head[1:]))
            sub.setAlignment(Qt.AlignCenter)
            style.mark(sub, role="muted")
        self.body_lay.addSpacing(8)
        for para in paras[1:]:                          # e.g. kept in the library, with its checks
            box = QFrame(self.body)
            box.setObjectName("donebox")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(style.px(14), style.px(10), style.px(14), style.px(10))
            rows = []
            for k, line in enumerate(para.split("\n")):
                colour = style.colour("warn").name() if line.startswith("\u26a0") else style.colour("text").name()
                weight = "bold" if k == 0 and not line.startswith(("\u2713", "\u26a0")) else "normal"
                rows.append("<div style='color:%s; font-weight:%s; margin-bottom:2px'>%s</div>"
                            % (colour, weight, escape(line) or "&nbsp;"))
            inner = QLabel("".join(rows), box)
            inner.setWordWrap(True)
            inner.setTextFormat(Qt.RichText)
            bl.addWidget(inner)
            self.body_lay.addWidget(box)
            inner.setMinimumHeight(inner.heightForWidth(style.px(500)))     # wrapped lines stay whole (box is at least 500 wide)
        self.body_lay.addStretch(1)
        row = QHBoxLayout()
        if other:                                       # an offer, on the left; Klaar stays where it always is
            row.addWidget(self._button(other, "other"))
        row.addStretch(1)
        self.finish_button = self._button(self.win.presenter.t("btn_done"), True, primary=True)
        row.addWidget(self.finish_button)
        self.body_lay.addSpacing(10)
        self.body_lay.addLayout(row)
        self.adjustSize()
        return self._wait() == "other"


class ExportDialog(QDialog):
    """Before a song list is saved: one window for PDF and CSV (the same list; only the file differs).
    Which columns, all folders or the one shown, folder by folder or A to Z, and for the PDF how it
    looks (title, date, page numbers, large print, a new page per folder). The choice of last time is
    ticked; the title is proposed afresh. kind: the format chosen at the start ("pdf" or "csv")."""

    def __init__(self, win: "MainWindow", kind: str):
        super().__init__(win)
        p, t = win.presenter, win.presenter.t
        self.kind = kind
        st = win.settings
        self.setWindowTitle(t("exp_title"))
        saved = str(st.value("export/fields", "") or "")
        ticked = set(saved.replace("bank_a", "banks").split(",")) if saved else set(p.EXPORT_DEFAULT)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QVBoxLayout.SetFixedSize)    # as tall as the wrapped notes need: never squeezed
        lay.setContentsMargins(style.px(22), style.px(18), style.px(22), style.px(18))
        bold = QLabel(self).font()
        bold.setBold(True)
        fmt_head = QLabel(t("exp_format"), self)
        fmt_head.setFont(bold)
        lay.addWidget(fmt_head)
        fmt = QWidget(self)                              # its own radio group
        fl = QVBoxLayout(fmt)
        fl.setContentsMargins(0, 0, 0, 0)
        self.as_pdf = QRadioButton(t("exp_fmt_pdf"), fmt)
        self.as_csv = QRadioButton(t("exp_fmt_csv"), fmt)
        fl.addWidget(self.as_pdf)
        fl.addWidget(self.as_csv)
        (self.as_csv if kind == "csv" else self.as_pdf).setChecked(True)
        lay.addWidget(fmt)
        lay.addSpacing(6)
        # Of what: the open card, or (with a library) the whole library or what its filter shows.
        self.p = p
        box = QWidget(self)                              # its own radio group, apart from "Welke songs?"
        bl = QVBoxLayout(box)
        bl.setContentsMargins(0, 0, 0, 0)
        self.from_card = QRadioButton(p.export_source_what() if p.session is not None else "", box)
        self.from_lib = QRadioButton(p.library_export_text(), box)
        self.from_view = QRadioButton(p.library_export_text(True) if p.library_filtered() else "", box)
        for r in (self.from_card, self.from_lib, self.from_view):
            bl.addWidget(r)
        box.hide()
        if p.library is None:                            # only a card: say which one, nothing to choose
            self.source = QLabel(p.export_source(), self)
            self.source.setWordWrap(True)
            lay.addWidget(self.source)
            lay.addSpacing(6)
        else:
            from_head = QLabel(t("exp_from"), self)
            from_head.setFont(bold)
            lay.addWidget(from_head)
            box.show()
            lay.addWidget(box)
            lay.addSpacing(6)
        self.from_card.setVisible(p.library is not None and p.session is not None)
        self.from_lib.setVisible(p.library is not None)
        self.from_view.setVisible(p.library is not None and p.library_filtered())
        wanted = str(st.value("export/from", "card"))
        if p.session is not None and (p.library is None or wanted == "card"):
            self.from_card.setChecked(True)
        else:
            self.from_lib.setChecked(True)
        head = QLabel(t("exp_what"), self)
        f = head.font()
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        grid = QGridLayout()
        self.boxes = {}
        plain = [k for k, _ in p.EXPORT_FIELDS if k in p._PLAIN]
        slow = [k for k, _ in p.EXPORT_FIELDS if k not in p._PLAIN]
        labels = dict(p.EXPORT_FIELDS)
        for i, k in enumerate(plain):
            self.boxes[k] = QCheckBox(t(labels[k]), self)
            grid.addWidget(self.boxes[k], i // 3, i % 3)
        lay.addLayout(grid)
        self.lib_note = QLabel(t("exp_lib_note"), self)
        self.lib_note.setWordWrap(True)
        style.mark(self.lib_note, role="muted")
        lay.addWidget(self.lib_note)
        self.head_note = QLabel(t("exp_pdf_head"), self)
        self.head_note.setWordWrap(True)
        style.mark(self.head_note, role="muted")
        lay.addWidget(self.head_note)
        line = QFrame(self)
        line.setFrameShape(QFrame.HLine)
        style.mark(line, role="line")
        lay.addWidget(line)
        note = QLabel(t("exp_slow"), self)
        note.setWordWrap(True)
        style.mark(note, role="muted")
        lay.addWidget(note)
        grid2 = QGridLayout()
        for i, k in enumerate(k for k in slow if k != "set"):
            self.boxes[k] = QCheckBox(t(labels[k]), self)
            grid2.addWidget(self.boxes[k], i // 3, i % 3)
        lay.addLayout(grid2)
        grid2 = QGridLayout()                           # the diskette sets: a sentence, so a row of its own
        self.boxes["set"] = QCheckBox(t("exp_sets_box"), self)
        grid2.addWidget(self.boxes["set"], 0, 0)
        lay.addLayout(grid2)
        for k, b in self.boxes.items():
            b.setChecked(k in ticked)
        self.boxes["name"].setChecked(True)
        self.boxes["name"].setEnabled(False)             # a list without names says nothing

        def heading(key):
            lay.addSpacing(8)
            lab = QLabel(t(key), self)
            lab.setFont(f)
            lay.addWidget(lab)
            return lab

        def check(key, setting, default):
            box = QCheckBox(t(key), self)
            box.setChecked(str(st.value(setting, default)).lower() == "true")
            lay.addWidget(box)
            return box

        heading("exp_which")
        self.all = QRadioButton(t("exp_all"), self)
        self.one = QRadioButton(self)
        self.all.setChecked(True)
        lay.addWidget(self.all)
        folder = getattr(p, "folder", None)
        s = p.session
        if s is not None and folder:
            self.folder = folder
            self.one.setText(t("exp_one", n="%02d" % folder, name=s.db.folders[folder - 1].name or t("noname").strip("()")))
            lay.addWidget(self.one)
        else:
            self.folder = None
            self.one.hide()
        self.skip_empty = check("exp_skip_empty", "export/skip_empty", "true")

        heading("exp_order")
        order = QWidget(self)                            # its own group: apart from "Welke songs?"
        ol = QVBoxLayout(order)
        ol.setContentsMargins(0, 0, 0, 0)
        self.by_folder = QRadioButton(t("exp_order_folder"), order)
        self.by_name = QRadioButton(t("exp_order_name"), order)
        ol.addWidget(self.by_folder)
        ol.addWidget(self.by_name)
        lay.addWidget(order)
        (self.by_name if str(st.value("export/order", "")) == "name" else self.by_folder).setChecked(True)

        self.title = QLineEdit(p.list_title() if p.session is not None else t("exp_lib_title"), self)
        self._titles = {"card": p.list_title() if p.session is not None else "", "lib": t("exp_lib_title")}
        self.look_head = heading("exp_look")             # the PDF only: grey for a CSV
        row = QHBoxLayout()
        self.title_label = QLabel(t("exp_list_title"), self)
        row.addWidget(self.title_label)
        row.addWidget(self.title, 1)
        lay.addLayout(row)
        self.date = check("exp_date", "export/date", "true")
        self.pages = check("exp_pages", "export/pages", "true")
        self.big = check("exp_big", "export/big", "false")
        self.landscape = check("exp_landscape", "export/landscape", "false")
        self.page = check("exp_page", "export/page", "false")
        for w in (self.by_folder, self.by_name, self.one, self.all, self.from_card, self.from_lib, self.from_view,
                  self.as_pdf):
            w.toggled.connect(self._follow)
        self.from_card.toggled.connect(self._swap_title)
        self._follow()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.button(QDialogButtonBox.Ok).setText(t("exp_save"))
        bb.button(QDialogButtonBox.Cancel).setText(t("btn_cancel"))
        style.mark(bb.button(QDialogButtonBox.Ok), role="primary")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def library_chosen(self) -> bool:
        return not self.from_card.isChecked()

    def _swap_title(self, *_):
        """The proposed title follows the choice, unless it was typed over."""
        old, new = ("lib", "card") if self.from_card.isChecked() else ("card", "lib")
        if self.title.text().strip() == self._titles[old]:
            self.title.setText(self._titles[new])

    def _follow(self, *_):
        """Options that only mean something folder by folder (and for all folders) go grey otherwise;
        from the library, what it cannot read goes grey too."""
        lib = self.library_chosen()
        t = self.p.t
        per_folder = self.by_folder.isChecked()
        pdf = self.as_pdf.isChecked()
        self.kind = "pdf" if pdf else "csv"
        for w in (self.look_head, self.title_label, self.title, self.date, self.pages, self.big, self.landscape):
            w.setEnabled(pdf)
        self.page.setEnabled(per_folder and pdf)
        self.page.setText(t("exp_page_card" if lib else "exp_page"))
        self.by_folder.setText(t("exp_order_card" if lib else "exp_order_folder"))
        self.all.setEnabled(not lib)
        self.one.setEnabled(not lib)
        self.skip_empty.setEnabled(per_folder and not self.one.isChecked() and not lib)
        for k, b in self.boxes.items():
            if k != "name":
                b.setEnabled(not lib or k in self.p.LIB_FIELDS)
        self.lib_note.setVisible(lib)
        self.head_note.setEnabled(per_folder)

    def choice(self) -> dict:
        """What to make: fields (in list order), folder (None: all), by_name, and for the PDF title,
        date, pages, big, page (a new page per folder) and skip_empty."""
        lib = self.library_chosen()
        fields = [k for k, _ in self.win_fields() if self.boxes[k].isChecked()
                  and (not lib or k in self.p.LIB_FIELDS)]
        by_name = self.by_name.isChecked()
        source = "card" if not lib else ("view" if self.from_view.isChecked() else "library")
        return {"format": "pdf" if self.as_pdf.isChecked() else "csv", "source": source, "fields": fields, "folder": self.folder if self.one.isChecked() else None, "by_name": by_name,
                "title": self.title.text().strip(), "date": self.date.isChecked(),
                "pages": self.pages.isChecked(), "big": self.big.isChecked(), "landscape": self.landscape.isChecked(),
                "page": self.page.isChecked() and not by_name, "skip_empty": self.skip_empty.isChecked()}

    def remember(self, settings) -> None:
        """Keep the ticks for next time (the title belongs to this card, so it is not kept)."""
        c = self.choice()
        if not self.library_chosen():                   # library ticks greyed out: keep the card's ticks
            settings.setValue("export/fields", ",".join(c["fields"]))
        settings.setValue("export/from", "card" if c["source"] == "card" else "library")
        settings.setValue("export/order", "name" if c["by_name"] else "folder")
        for key in ("date", "pages", "big", "landscape", "skip_empty"):
            settings.setValue("export/" + key, c[key])
        settings.setValue("export/page", self.page.isChecked())

    def win_fields(self):
        return self.parent().presenter.EXPORT_FIELDS


class MoreDialog(QDialog):
    """"Meer…": everything that is not needed every day, as big tiles in a few groups instead of a long
    menu. A tile closes the window and does its job."""

    TILE_ICONS = {"lists": "star", "duplicates": "copy", "history": "history", "export_pdf": "printer",
                  "export_csv": "table", "open_other": "two_cards", "library": "library", "backups": "restore",
                  "check_card": "check", "copy_library": "library"}
    # The menu bar holds every command (macOS convention); "Meer…" only the ones a player uses now and then,
    # with the same names, so a tile and its menu item are recognisably the same thing. Opening a card
    # by hand, choosing the library, a second card alongside (needs two card readers) and the
    # language stay in the menu bar only.
    GROUPS = [("more_play", ["lists", "history", "duplicates"]),
              ("more_card", ["export_pdf", "export_csv", "library"]),
              ("more_help", ["backups", "copy_library", "check_card"])]

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        t = win.presenter.t
        self.win = win
        self.setWindowTitle(t("more_title"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.px(24), style.px(18), style.px(24), style.px(18))
        cols = QHBoxLayout()
        cols.setSpacing(style.px(18))
        self.tiles = {}
        for head, tiles in self.GROUPS:
            col = QVBoxLayout()
            col.addWidget(self._head(t(head)))
            for act in tiles:
                b = QPushButton(gap(t("act." + act)), self)
                b.setMinimumSize(style.px(230), style.px(64))
                b.setIcon(icons.icon(self.TILE_ICONS[act]))
                b.setIconSize(QSize(style.px(24), style.px(24)))
                b.setStyleSheet(style.sheet("QPushButton { text-align: left; padding: 8px 14px; }"))
                b.setMinimumWidth(max(style.px(230), b.sizeHint().width() + style.px(16)))     # never cut off the words
                b.setEnabled(win.acts[act].isEnabled())
                if act == "library" and win.presenter.page == "compose":
                    b.hide()                                # always beside the new card: nothing to switch
                b.clicked.connect(lambda _=False, a=act: self._run(a))
                self.tiles[act] = b
                col.addWidget(b)
            col.addStretch(1)
            cols.addLayout(col)
        lay.addLayout(cols, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close, self)
        close.button(QDialogButtonBox.Close).setText(t("close"))
        close.rejected.connect(self.reject)
        lay.addWidget(close)

    def _head(self, text: str) -> QLabel:
        lab = QLabel(text, self)
        f = lab.font()
        f.setBold(True)
        lab.setFont(f)
        style.mark(lab, role="muted")
        return lab

    def _run(self, act: str) -> None:
        self.accept()
        a = self.win.acts[act]
        if a.isCheckable():
            a.setChecked(not a.isChecked())
        else:
            a.trigger()


class FolderPickerDialog(QDialog):
    """"Verplaatsen naar…" / "Kopiëren naar…": the folders as a table (number, name, songs, free
    places) with big rows, instead of typing a number. A folder without a name shows in italics."""

    def __init__(self, win: "MainWindow", title: str, choices):
        super().__init__(win)
        t = win.presenter.t
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        head = QLabel(title, self)
        f = head.font()
        f.setBold(True)
        head.setFont(f)
        lay.addWidget(head)
        self.list = QTreeWidget(self)
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setUniformRowHeights(True)
        self.list.setHeaderLabels([t("col.folder"), t("col.name"), t("pick_col_songs"), t("pick_col_free")])
        noname = t("noname")
        for n, cells in choices:
            it = QTreeWidgetItem(cells)
            it.setData(0, Qt.UserRole, n)
            for c in (0, 2, 3):
                it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            if n == 0 or cells[1] == noname:            # "+ Nieuwe map…" and "(geen naam)": not a real name
                fi = it.font(1)
                fi.setItalic(True)
                it.setFont(1, fi)
            self.list.addTopLevelItem(it)
        hd = self.list.header()
        hd.setStretchLastSection(False)
        hd.setSectionResizeMode(QHeaderView.ResizeToContents)
        hd.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3):
            self.list.headerItem().setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
        self.list.setCurrentItem(self.list.topLevelItem(0))
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        bb.button(QDialogButtonBox.Cancel).setText(t("btn_cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(style.px(460), style.px(520))

    def folder(self) -> Optional[int]:
        it = self.list.currentItem()
        return None if it is None else it.data(0, Qt.UserRole)


class BackupsDialog(QDialog):
    """Back-ups of every card, the open card's first: what was on it (right), and where it can go back to:
    this card, a new card (then Op kaart zetten, onto any card) or the library. The choice is done()
    with the action, so MainWindow runs it after the dialog has closed."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win, p = win, win.presenter
        t = p.t
        self.action = None
        self.setWindowTitle(t("act.backups"))
        intro = QLabel(t("backups_intro"), self)
        intro.setWordWrap(True)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.contents = QTreeWidget(self)
        self.contents.setHeaderLabels([t("backup_contents")])
        split = GripSplitter(self)
        split.addWidget(self.tree)
        split.addWidget(self.contents)
        split.setSizes([style.px(330), style.px(330)])
        split.set_tip(t("splitter_tip"))
        can_restore = p.session is not None and not p.composing
        self.now_btn = QPushButton(icons.icon("restore"), gap(t("btn_backup_now")), self)
        self.now_btn.setEnabled(can_restore)
        self.now_btn.clicked.connect(lambda: self._done("now"))
        self.show_btn = QPushButton(t(SHOW_FOLDER), self)
        self.show_btn.clicked.connect(self._show_folder)
        top = QHBoxLayout()
        top.addWidget(self.now_btn)
        top.addStretch(1)
        top.addWidget(self.show_btn)
        self.here_btn = QPushButton(t("btn_restore_here"), self)
        self.here_btn.setToolTip(t("tip_restore_here"))
        self.here_btn.setVisible(can_restore)
        style.mark(self.here_btn, role="primary")
        self.new_btn = QPushButton(t("btn_restore_new"), self)
        self.new_btn.setToolTip(t("tip_restore_new"))
        self.lib_btn = QPushButton(t("btn_restore_library"), self)
        self.lib_btn.setToolTip(t("tip_restore_library"))
        self.here_btn.clicked.connect(lambda: self._done("here"))
        self.new_btn.clicked.connect(lambda: self._done("new"))
        self.lib_btn.clicked.connect(lambda: self._done("library"))
        close = QPushButton(t("close"), self)
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.here_btn)
        row.addWidget(self.new_btn)
        row.addWidget(self.lib_btn)
        row.addStretch(1)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addLayout(top)
        lay.addWidget(split, 1)
        lay.addLayout(row)
        self.tree.currentItemChanged.connect(lambda *_: self._update())
        self.tree.itemDoubleClicked.connect(lambda it, _c: self.path() and self._done("here" if can_restore else "new"))
        self.fill(p.backup_rows())
        self.resize(style.px(820), style.px(520))

    def fill(self, rows) -> None:
        t = self.win.presenter.t
        self.tree.clear()
        heads = {}
        first = None
        for r in rows:
            head = heads.get(r.group)
            if head is None:
                head = heads[r.group] = QTreeWidgetItem([r.group])
                f = head.font(0)
                f.setBold(True)
                head.setFont(0, f)
                head.setFlags(head.flags() & ~Qt.ItemIsSelectable)
                self.tree.addTopLevelItem(head)
                head.setExpanded(r.this_card or len(heads) <= 3)
            child = QTreeWidgetItem([r.label])
            child.setData(0, Qt.UserRole, r.path)
            child.setData(0, Qt.UserRole + 1, r.group.split("  (")[0] if r.library else "")
            child.setToolTip(0, r.path)
            head.addChild(child)
            first = first or child
        if not rows:
            empty = QTreeWidgetItem([t("no_backups")])
            empty.setFlags(Qt.NoItemFlags)
            self.tree.addTopLevelItem(empty)
            self.tree.setWordWrap(True)
        if first is not None:
            self.tree.setCurrentItem(first)
        self._update()

    def path(self) -> str:
        it = self.tree.currentItem()
        return (it.data(0, Qt.UserRole) or "") if it is not None else ""

    def library_name(self) -> str:
        it = self.tree.currentItem()
        return (it.data(0, Qt.UserRole + 1) or "") if it is not None else ""

    def _update(self) -> None:
        path = self.path()
        for b in (self.here_btn, self.new_btn, self.lib_btn):
            b.setEnabled(bool(path))
        self.contents.clear()
        if not path:
            self.contents.addTopLevelItem(QTreeWidgetItem([self.win.presenter.t("backup_contents_none")]))
            return
        for folder, songs in self.win.presenter.backup_contents(path):
            head = QTreeWidgetItem([folder])
            for n in songs:
                head.addChild(QTreeWidgetItem([n]))
            self.contents.addTopLevelItem(head)

    def _done(self, action: str) -> None:
        self.action = action
        self.accept()

    def _show_folder(self) -> None:
        path = self.path() or (self.win.presenter.backup_dir or backup.default_backup_dir())
        show_in_finder(path)


def show_in_finder(path: str) -> None:
    """Finder with the file selected (macOS); elsewhere the folder it is in."""
    import subprocess
    if sys.platform == "darwin" and os.path.exists(path):
        subprocess.Popen(["open", "-R", path])
        return
    from ..storage import windows
    if windows.show_in_explorer(path):
        return
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))


class IntroDialog(QDialog):
    """A short explanation before something new starts (Oefenen): a heading, one sentence, a few points
    with a tick, and one button to begin. Calmer than a message box with a warning sign."""

    def __init__(self, parent, title: str, intro: str, points, button: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(style.px(28), style.px(24), style.px(28), style.px(20))
        lay.setSpacing(style.px(10))
        head = QLabel(title, self)
        f = head.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.4)
        head.setFont(f)
        lay.addWidget(head)
        lead = QLabel(intro, self)
        lead.setWordWrap(True)
        lay.addWidget(lead)
        lay.addSpacing(style.px(4))
        for point in points:
            row = QHBoxLayout()
            row.setSpacing(style.px(10))
            tick = QLabel("✓", self)
            style.mark(tick, role="ok")
            tick.setAlignment(Qt.AlignTop)
            text = QLabel(point, self)
            text.setWordWrap(True)
            row.addWidget(tick, 0, Qt.AlignTop)
            row.addWidget(text, 1)
            lay.addLayout(row)
        lay.addSpacing(style.px(8))
        ok = QPushButton(button, self)
        style.mark(ok, role="primary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(ok)
        lay.addLayout(buttons)
        self.setFixedWidth(style.px(560))


def _show_folder(path: str) -> None:
    """Show a folder of the app's own in Finder / Explorer, making it first when it is not there yet."""
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    show_in_finder(path)


class AboutDialog(QDialog):
    """Over KN Songboek: what it is, its version, where the library and the back-ups are on this computer,
    and where the format knowledge comes from."""

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        from .. import __version__
        p = win.presenter
        t = p.t
        self.setWindowTitle(t("about_title"))
        pic = QLabel(self)
        pic.setPixmap(icons.pixmap("card", 64, style.colour("accent")))
        pic.setFixedSize(style.px(72), style.px(72))
        from .. import APP_NAME
        name = QLabel(APP_NAME, self)
        f = name.font()
        f.setPointSize(int(f.pointSize() * 1.8))
        f.setBold(True)
        name.setFont(f)
        version = QLabel(t("about_version", v=__version__), self)
        style.mark(version, role="muted")
        head = QVBoxLayout()
        head.addWidget(name)
        head.addWidget(version)
        top = QHBoxLayout()
        top.addWidget(pic, 0, Qt.AlignTop)
        top.addLayout(head, 1)
        what = QLabel(t("about_what"), self)
        what.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(what)
        from .. import __url__
        if __url__:
            link = QLabel('<a href="%s">%s</a>' % (__url__, __url__), self)
            link.setObjectName("about_link")
            link.setOpenExternalLinks(True)
            lay.addWidget(link)
        grid = QGridLayout()
        lib = win.settings.value("last_library", "") or p.library_path or ""
        places = [(t("about_library"), str(lib) or t("about_not_chosen")),
                  (t("about_backups"), p.backup_dir or backup.default_backup_dir())]
        for row, (label, path) in enumerate(places):
            lab = QLabel(label, self)
            style.mark(lab, role="muted")
            val = QLabel(path, self)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            grid.addWidget(lab, row, 0, Qt.AlignTop)
            grid.addWidget(val, row, 1)
            # the back-up folder is made with the first back-up; the button is there before that too
            if path and (os.path.isdir(path) or label == t("about_backups")):
                b = QPushButton(t(SHOW_FOLDER), self)
                b.clicked.connect(lambda _=False, x=path: _show_folder(x))
                grid.addWidget(b, row, 2, Qt.AlignTop)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        bb = QDialogButtonBox(QDialogButtonBox.Close, self)
        bb.button(QDialogButtonBox.Close).setText(t("close"))
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.setMinimumWidth(style.px(520))


class DuplicatesDialog(QDialog):
    """Groups of songs stored more than once; pick the copy to keep (presenter.merge_duplicates)."""

    def __init__(self, win: "MainWindow", rows):
        super().__init__(win)
        self.win, p = win, win.presenter
        t = p.t
        self.setWindowTitle(t("act.duplicates"))
        intro = QLabel(t("dups_intro"), self)
        intro.setWordWrap(True)
        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.list_box = QComboBox(self)
        self.list_box.addItem(t("dups_no_list"), None)
        for n in (1, 2, 3):
            self.list_box.addItem(t("song_list_n", n=n), n)
        self.keep_btn = QPushButton(t("dups_keep"), self)
        self.keep_btn.clicked.connect(self._keep)
        close = QPushButton(t("close"), self)
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addWidget(QLabel(t("dups_list"), self))
        row.addWidget(self.list_box)
        row.addStretch(1)
        row.addWidget(self.keep_btn)
        row.addWidget(close)
        lay = QVBoxLayout(self)
        lay.addWidget(intro)
        lay.addWidget(self.tree)
        lay.addLayout(row)
        self.tree.currentItemChanged.connect(lambda *_: self._update())
        self.fill(rows)
        self.resize(style.px(560), style.px(420))

    def fill(self, rows) -> None:
        t = self.win.presenter.t
        self.tree.clear()
        for r in rows:
            head = QTreeWidgetItem([t("dups_identical", name=r.name, n=len(r.slots), saving=r.saving) if r.identical
                                    else t("dups_same_name", name=r.name)])
            if not r.identical:
                head.setForeground(0, style.colour("muted"))
            for slot, label in zip(r.slots, r.labels):
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.UserRole, slot)
                child.setData(0, Qt.UserRole + 1, r.slots if r.identical else None)
                head.addChild(child)
            self.tree.addTopLevelItem(head)
            head.setExpanded(True)
        self._update()

    def _selected(self):
        it = self.tree.currentItem()
        if it is None or it.data(0, Qt.UserRole + 1) is None:
            return None
        return it.data(0, Qt.UserRole), it.data(0, Qt.UserRole + 1)

    def _update(self) -> None:
        self.keep_btn.setEnabled(self._selected() is not None)

    def _keep(self) -> None:
        sel = self._selected()
        if sel is None:
            return
        keep, slots = sel
        if self.win.presenter.merge_duplicates(tuple(keep), [tuple(x) for x in slots], self.list_box.currentData()):
            # the kept song is gone from the list; the card is not saved yet, so re-scan is not possible
            top = self.tree.currentItem().parent()
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(top))
            self._update()
