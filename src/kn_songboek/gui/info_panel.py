"""The panel on the right with everything about one song: its facts, registrations (Knoppen / Lijst),
styles, pads, own sounds, picture and files."""
from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Dict, List, Optional

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import i18n, icons, style
from .widgets import GripSplitter, _chip_height, gap, name_field  # noqa: F401

if TYPE_CHECKING:
    from .qt_app import MainWindow

class _BankList(QWidget):
    """Lijst: one label per bank heading and per button, so folding a button open or shut lays out only
    that button again (one label for everything took seconds once many buttons were open)."""

    def __init__(self, parent: QWidget, on_link):
        super().__init__(parent)
        self.on_link = on_link
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)
        self.labels: List[QLabel] = []
        self.by_key: Dict[tuple, QLabel] = {}

    def fill(self, rows) -> None:
        """rows: [(key (bank, button) or None for a heading or the footer, html)]."""
        while len(self.labels) < len(rows):
            lab = QLabel(self)
            lab.setWordWrap(True)
            lab.setTextFormat(Qt.RichText)
            lab.linkActivated.connect(self.on_link)
            self.lay.addWidget(lab)
            self.labels.append(lab)
        self.by_key = {}
        for lab, (key, html) in zip(self.labels, rows):
            lab.setContentsMargins(style.px(12) if key else 0, 0 if key else style.px(6), 0, 0)
            lab.setText(html)
            lab.show()
            if key is not None:
                self.by_key[key] = lab
        for lab in self.labels[len(rows):]:
            lab.hide()
            lab.clear()

    def has(self, key) -> bool:
        return key in self.by_key

    def set_button(self, key, html: str) -> None:
        self.by_key[key].setText(html)

    def text(self) -> str:
        return "".join(lab.text() for lab in self.labels if not lab.isHidden())


class InfoPanel(QFrame):
    """Right of the songs: everything about the chosen song in one place, nothing left out. At the top
    the short facts (where, rhythm, time, tempo, chords, favourites…). Below them sections that fold:
    Registraties (choose bank A, B, C (1-10) and see its 8 buttons as on the panel, click one for its
    rhythm, tempo, chords and sounds; or "Lijst": every bank below each other, to compare), the
    recording, composer styles, pads (6 blocks per bank, own pads green), own sounds, the home page
    picture and the files. The details are read a moment after the click, so arrowing through a
    folder stays quick. Folded sections, the chosen view and bank stay as they are for the next song."""

    SECTIONS = ("banks", "recording", "styles", "pads", "sounds", "picture", "files", "errors")

    def __init__(self, win: "MainWindow"):
        super().__init__(win)
        self.win = win
        self.setObjectName("info")
        self.setMinimumWidth(style.px(260))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        body = QWidget(self.scroll)
        self.body = body
        self.scroll.setWidget(body)
        self.scroll.viewport().installEventFilter(self)   # keep the content as wide as the panel: text wraps
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(style.px(14), 4, style.px(10), style.px(10))
        self.title = QLabel(body)
        f = self.title.font()
        f.setBold(True)
        f.setPointSize(int(f.pointSize() * 1.15))
        self.title.setFont(f)
        self.title.setWordWrap(True)
        self.lay.addWidget(self.title)
        self._build_renamed(body)
        self.grid = QLabel(body)
        self.grid.setWordWrap(True)
        self.grid.setTextFormat(Qt.RichText)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.lay.addWidget(self.grid)
        settings = getattr(win, "settings", None)
        self.settings = settings
        closed = settings.value("info/closed", "") if settings is not None else ""
        self.closed = set(str(closed).split(",")) - {""}
        self.view = str(settings.value("info/view", "buttons")) if settings is not None else "buttons"
        # "Eenvoudig" (default): what a player needs; "Uitgebreid": every value read, also the unsure ones
        self.detailed = settings is not None and str(settings.value("info/detail", "0")) == "1"
        self.bank = 0                                    # chosen bank (index), kept for the next song
        self.button = 0                                  # chosen button (index)
        self.unfolded = set()                            # (bank, button) opened in Lijst, for this song
        self.data: Optional[dict] = None
        self.sections = {}
        for key in self.SECTIONS:
            self.sections[key] = self._section(body, key)
        self._build_banks()
        self.lay.addStretch(1)
        self.slot = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(60)                 # arrowing on: only the song you stop at is read
        self.timer.timeout.connect(self._load_details)
        self._hide_sections()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Resize and obj is self.scroll.viewport():
            self.body.setFixedWidth(obj.width())
        return False

    # ---------------------------------------------------------------- building blocks
    def _section(self, parent, key: str) -> dict:
        """A heading that folds (▾ / ▸) with a count on the right, and its content below."""
        box = QWidget(parent)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, style.px(8), 0, 0)
        v.setSpacing(4)
        line = QFrame(box)
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("infoline")
        v.addWidget(line)
        head = QHBoxLayout()
        btn = QToolButton(box)
        btn.setObjectName("infohead")
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setCheckable(True)
        btn.setChecked(key not in self.closed)
        btn.setArrowType(Qt.DownArrow if btn.isChecked() else Qt.RightArrow)
        f = btn.font()
        f.setBold(True)
        btn.setFont(f)
        count = QLabel(box)
        style.mark(count, role="muted")
        head.addWidget(btn)
        head.addStretch(1)
        head.addWidget(count)
        v.addLayout(head)
        content = QWidget(box)
        cv = QVBoxLayout(content)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(4)
        text = QLabel(content)
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        cv.addWidget(text)
        v.addWidget(content)
        content.setVisible(btn.isChecked())
        btn.toggled.connect(lambda on, k=key: self._fold(k, on))
        self.lay.addWidget(box)
        return {"box": box, "head": btn, "count": count, "content": content, "layout": cv, "text": text}

    def _fold(self, key: str, on: bool) -> None:
        s = self.sections[key]
        s["head"].setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        s["content"].setVisible(on)
        (self.closed.discard if on else self.closed.add)(key)
        if self.settings is not None:
            self.settings.setValue("info/closed", ",".join(sorted(self.closed)))

    def _build_banks(self) -> None:
        """Registraties: bank choice and view switch, the 8 buttons with the chosen one's details, or
        the list of every bank."""
        s = self.sections["banks"]
        cv, parent = s["layout"], s["content"]
        s["text"].hide()
        row = QHBoxLayout()                              # the view choice on its own line
        row.setSpacing(4)
        self.bank_buttons: List[QPushButton] = []
        row.addStretch(1)
        self.view_buttons = {}
        for key in ("buttons", "list"):
            b = QPushButton(parent)
            b.setObjectName("viewchip")
            b.setCheckable(True)
            b.setChecked(self.view == key)
            b.clicked.connect(lambda _=False, k=key: self._set_view(k))
            self.view_buttons[key] = b
            _chip_height(b)
            row.addWidget(b)
        cv.addLayout(row)
        self.bank_box = QWidget(parent)                  # bank letters, 7 per line (a full set has 13)
        self.bank_grid = QGridLayout(self.bank_box)
        self.bank_grid.setContentsMargins(0, 0, 0, 0)
        self.bank_grid.setSpacing(4)
        self.bank_grid.setColumnStretch(7, 1)
        cv.addWidget(self.bank_box)
        self.bank_line = QLabel(parent)
        style.mark(self.bank_line, role="muted")
        self.bank_line.setWordWrap(True)
        cv.addWidget(self.bank_line)
        self.pad_grid = QWidget(parent)
        g = QGridLayout(self.pad_grid)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(4)
        self.mem_buttons: List[QPushButton] = []
        for i in range(8):
            b = QPushButton(self.pad_grid)
            b.setObjectName("regbtn")
            b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, n=i: self._choose_button(n))
            g.addWidget(b, i // 4, i % 4)
            self.mem_buttons.append(b)
        self._size_buttons()
        cv.addWidget(self.pad_grid)
        self.detail = QLabel(parent)
        self.detail.setObjectName("regdetail")
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.RichText)
        cv.addWidget(self.detail)
        self.bank_list = _BankList(parent, self._open_memory)
        cv.addWidget(self.bank_list)

    def _build_renamed(self, parent) -> None:
        """A renamed song (not on the card yet): what it was called, and a button that puts that back."""
        box = QFrame(parent)
        box.setObjectName("renamed")
        v = QVBoxLayout(box)
        v.setContentsMargins(style.px(10), style.px(8), style.px(10), style.px(8))
        v.setSpacing(2)
        self.renamed_head = QLabel(box)
        f = self.renamed_head.font()
        f.setBold(True)
        self.renamed_head.setFont(f)
        self.renamed_before = QLabel(box)
        self.renamed_old = QLabel(box)
        self.renamed_old.setFont(self.title.font())
        self.renamed_old.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.renamed_button = QPushButton(box)
        self.renamed_button.clicked.connect(self._restore_name)
        for w in (self.renamed_head, self.renamed_before, self.renamed_old):
            v.addWidget(w)
        row = QHBoxLayout()
        row.setContentsMargins(0, style.px(4), 0, 0)
        row.addWidget(self.renamed_button)
        row.addStretch(1)
        v.addLayout(row)
        box.hide()
        self.renamed = box
        self.lay.addWidget(box)

    def _show_renamed(self, slot) -> None:
        p = self.win.presenter
        old = p.old_name(slot) if slot is not None and hasattr(p, "old_name") else ""
        if old:
            t = p.t
            self.renamed_head.setText(t("renamed_head"))
            self.renamed_before.setText(t("renamed_before"))
            self.renamed_old.setText(old)
            self.renamed_button.setText(gap(t("btn_restore_name")))
            self.renamed_button.setIcon(icons.icon("undo"))
        self.renamed.setVisible(bool(old))
        if old:
            QTimer.singleShot(0, self._fit_width)          # the panel is never narrower than the button

    def _restore_name(self) -> None:
        if self.slot is not None:
            self.win.presenter.restore_old_name(self.slot)

    def _size_buttons(self) -> None:
        """Two lines of text (number and name) plus room for padding and border. A fixed height, because
        the macOS style reports a one-line height for a button and the rows then overlap."""
        for b in self.mem_buttons:
            b.ensurePolished()
            b.setFixedHeight(2 * b.fontMetrics().lineSpacing() + style.px(18))

    # ---------------------------------------------------------------- showing a song
    def _fit_width(self) -> None:
        """The panel is never narrower than what is in it: a button's settings table, the pad rows and
        a heading with its count cannot wrap, and were cut off at the right edge ("Mod.Blue", "klank ban")."""
        lay = self.body.layout()
        if lay is None:
            return
        lay.activate()
        need = lay.minimumSize().width() + self.scroll.verticalScrollBar().sizeHint().width() + 4
        if need != self.minimumWidth():
            self.setMinimumWidth(max(style.px(260), need))

    def show_info(self, info, slot=None) -> None:
        t = self.win.presenter.t
        self.slot = slot if info is not None else None
        self.data = None
        self._hide_sections()
        self._show_renamed(self.slot)
        if info is None:
            self.title.setText("")
            self.grid.setText("<span style='color:gray'>%s</span>" % escape(t("info_none")))
            self.timer.stop()
            return
        name, rows = info
        self.title.setText(name)
        self.grid.setText("<table cellspacing=0 cellpadding=3>%s</table>" % "".join(
            "<tr><td style='color:gray; padding-right:10px'>%s</td><td>%s</td></tr>" % (escape(a), escape(b))
            for a, b in rows))
        if slot is not None:
            self.timer.start()

    def _hide_sections(self) -> None:
        for s in self.sections.values():
            s["box"].hide()

    def _load_details(self) -> None:
        p = self.win.presenter
        if self.slot is None or p.session is None:
            return
        data = p.song_panel(self.slot)
        if data is None:
            return
        if getattr(self, "_unfold_slot", None) != self.slot:
            self.unfolded, self._unfold_slot = set(), self.slot   # another song: the list starts folded
        self.data = data
        self._fill(data)

    def _fill(self, d: dict) -> None:
        t = self.win.presenter.t
        heads = {"banks": t("sec_banks"), "recording": t("cont_sequencer"), "styles": t("cont_styles"),
                 "pads": t("panel_pads_head"), "sounds": t("panel_sounds_head"), "picture": t("cont_home_page"),
                 "files": t("cont_files"), "errors": t("panel_errors")}
        for key, s in self.sections.items():
            s["head"].setText(heads[key])
        self.sections["sounds"]["head"].setToolTip(t("panel_sounds_tip"))
        if d["banks"]:
            self._fill_banks(d)
        if d["recording"]:
            self._text("recording", "<br>".join(escape(x) for x in d["recording"]), str(len(d["recording"])))
        if d["styles"]:
            self._fill_styles(d["styles"])
        if d["pads"]:
            self._fill_pad_section(d["pads"])
        if d["has_sounds"]:
            self._fill_sounds(d)
        if d["bmp"]:
            self._fill_picture(d["bmp"])
        if self.detailed:
            self._files(d)
        if d["errors"]:
            self._text("errors", "".join("<div><b>%s</b><br>%s</div>" % (escape(h), escape(e)) for h, e in d["errors"]),
                       str(len(d["errors"])))

    def _fill_banks(self, d: dict) -> None:
        t, banks, s = self.win.presenter.t, d["banks"], self.sections["banks"]
        s["count"].setText(d["saved"].split(" (")[0])
        s["count"].setToolTip(t("sec_saved", how=d["saved"]))
        self.bank = min(self.bank, len(banks) - 1)
        self._fill_bank_buttons(banks)
        self._show_banks()
        s["box"].show()

    def _fill_styles(self, styles) -> None:
        c = style.colours()
        html = "".join("<div><span style='color:%s'>%d</span>&nbsp;&nbsp;%s%s</div>" % (
            c["muted"], n, escape(name),
            "<div style='color:%s; margin-left:16px'>%s</div>" % (c["muted"], escape(", ".join(v))) if v else "")
            for n, name, v in styles)
        self._text("styles", html, str(len(styles)))

    def _fill_pad_section(self, pads) -> None:
        t, c = self.win.presenter.t, style.colours()
        own = [(b["name"], n, name) for b in pads for n, mine, name in b["pads"] if mine]
        self._fill_pads(pads)
        legend = "<div style='color:%s'>%s</div>" % (c["muted"], escape(t("panel_pads_legend")))
        names = "".join("<div>%s</div>" % escape(t("panel_pad_own", bank=bn, n=n, name=name)) for bn, n, name in own)
        self._text("pads", legend + names, t("panel_pads_count", banks=len(pads), own=len(own)))

    def _fill_sounds(self, d: dict) -> None:
        t, c = self.win.presenter.t, style.colours()
        lines = ["<div><span style='color:%s'>%d</span>&nbsp;&nbsp;%s</div>" % (c["muted"], i, escape(n))
                 for i, n in d["own_sounds"]]
        lines.append("<div>%s</div>" % escape(t("cont_drum_kit", name=d["drum_kit"] or "-")))
        self._text("sounds", "".join(lines), str(len(d["own_sounds"])) + " " + t("panel_drum_extra"))

    def _fill_picture(self, bmp: bytes) -> None:
        pm = QPixmap()
        s = self.sections["picture"]
        if pm.loadFromData(QByteArray(bmp), "BMP"):
            s["text"].setPixmap(pm)
            s["count"].setText("")
            s["box"].show()

    def set_detailed(self, on: bool) -> None:
        """Eenvoudig or Uitgebreid; the song shown is shown again."""
        self.detailed = on
        if self.settings is not None:
            self.settings.setValue("info/detail", "1" if on else "0")
        if self.data:
            self.sections["files"]["box"].setVisible(on)
            if on:
                self._files(self.data)
            self._show_banks()

    def _files(self, d: dict) -> None:
        t = self.win.presenter.t
        c = style.colours()
        self._text("files", "<table cellspacing=0 cellpadding=2>%s</table>" % "".join(
            "<tr><td style='padding-right:8px'><b>%s</b></td><td align=right style='color:%s; padding-right:10px'>%s</td>"
            "<td>%s</td></tr>" % (escape(e), c["muted"], escape(z).replace(" ", "&nbsp;"),
                                  escape(t("file_" + e) if i18n.has_key("file_" + e) else t("file_unknown")))
            for e, z in d["files"]), str(len(d["files"])))

    def _fill_pads(self, banks) -> None:
        """The pad banks as a grid of real labels (not an HTML table, which re-flowed visibly each time
        the section was folded open): name, then 6 blocks, own pads green."""
        s = self.sections["pads"]
        old = s.get("grid")
        if old is not None:
            s["layout"].removeWidget(old)
            old.deleteLater()
        c = style.colours()
        box = QWidget(s["content"])
        g = QGridLayout(box)
        g.setContentsMargins(0, 0, 0, 4)
        g.setHorizontalSpacing(3)
        g.setVerticalSpacing(3)
        for r, b in enumerate(banks):
            name = QLabel("%d %s" % (b["number"], b["name"]), box)
            name.setWordWrap(True)                      # a long bank name goes on two lines, never cut off
            g.addWidget(name, r, 0)
            for i, (n, mine, pad_name) in enumerate(b["pads"]):
                cell = QLabel(str(n), box)
                cell.setAlignment(Qt.AlignCenter)
                cell.setFixedWidth(cell.fontMetrics().horizontalAdvance("0") + style.px(14))
                cell.setStyleSheet("background:%s; color:%s; border-radius:2px;" % (
                    c["ok"] if mine else c["line"], c["on_accent"] if mine else c["text"]))
                if pad_name:
                    cell.setToolTip(pad_name)
                g.addWidget(cell, r, 1 + i)
        g.setColumnStretch(0, 1)
        s["layout"].insertWidget(s["layout"].indexOf(s["text"]), box)
        s["grid"] = box

    def _text(self, key: str, html: str, count: str) -> None:
        s = self.sections[key]
        s["text"].setText(html)
        s["count"].setText(count)
        s["box"].show()

    # ---------------------------------------------------------------- Registraties
    def _fill_bank_buttons(self, banks) -> None:
        for b in self.bank_buttons:
            self.bank_grid.removeWidget(b)
            b.deleteLater()
        self.bank_buttons = []
        parent = self.sections["banks"]["content"]
        for i, b in enumerate(banks):
            btn = QPushButton(b["label"], parent)
            btn.setObjectName("bankchip")
            btn.setCheckable(True)
            btn.setProperty("empty", not b["used"])
            btn.setMinimumWidth(style.px(36))
            _chip_height(btn)
            btn.setToolTip(b["name"] or "")
            btn.clicked.connect(lambda _=False, n=i: self._choose_bank(n))
            self.bank_grid.addWidget(btn, i // 7, i % 7)
            self.bank_buttons.append(btn)

    def _set_view(self, key: str) -> None:
        self.view = key
        if self.settings is not None:
            self.settings.setValue("info/view", key)
        self._show_banks()

    def _open_memory(self, href: str) -> None:
        """A button in the list clicked: its settings fold open beneath it (or shut again), in place."""
        _m, bank, button = href.split(":")
        key = (int(bank), int(button))
        self.unfolded ^= {key}
        self.bank, self.button = key                     # Knoppen shows the same button when chosen
        m = self.data["banks"][key[0]]["memories"][key[1]] if self.data else None
        if m is None or not self.bank_list.has(key):
            self._show_banks()
            return
        html, _u = self._memory_html(m, key[1], link=href, unfolded=key in self.unfolded)
        self.bank_list.set_button(key, html)             # only this button is laid out again

    def _choose_bank(self, n: int) -> None:
        self.bank = n
        self._show_banks()

    def _choose_button(self, n: int) -> None:
        self.button = n
        self._show_banks()

    def _show_banks(self) -> None:
        if not self.data or not self.data["banks"]:
            return
        QTimer.singleShot(0, self._fit_width)              # another button or the list: maybe wider
        t = self.win.presenter.t
        c = style.colours()
        banks = self.data["banks"]
        listing = self.view == "list"
        for k, b in self.view_buttons.items():
            b.setText(t("view_" + k))
            b.setToolTip(t("view_tip"))
            b.setChecked(k == self.view)
        for i, b in enumerate(self.bank_buttons):
            b.setChecked(i == self.bank and not listing)
        self.bank_box.setVisible(not listing)
        for w in (self.bank_line, self.pad_grid, self.detail):
            w.setVisible(not listing)
        self.bank_list.setVisible(listing)
        if listing:            # every filled button, made by the same code as Knoppen; settings only when unfolded
            rows, unsure = [], False
            for bi, b in enumerate(banks):
                rows.append((None, "<b>%s</b>" % escape(self._bank_text(b))))
                for i, m in enumerate(b["memories"]):
                    if m.get("filled", bool(m["name"])):
                        html, u = self._memory_html(m, i, link="mem:%d:%d" % (bi, i),
                                                    unfolded=(bi, i) in self.unfolded)
                        unsure |= u
                        rows.append(((bi, i), html))
            rows.append((None, "<div style='color:%s'>%s</div>%s" % (
                c["muted"], escape(t("panel_list_more")), self._legends(unsure))))
            self.bank_list.fill(rows)
            return
        bank = banks[self.bank]
        self.bank_line.setText(self._bank_text(bank))
        for i, b in enumerate(self.mem_buttons):
            m = bank["memories"][i] if i < len(bank["memories"]) else None
            filled = bool(m and m.get("filled", bool(m["name"])))
            name = (m["name"] or t("panel_no_name")) if filled and m else t("panel_empty_button")
            b.setText("%d\n%s" % (i + 1, name))
            b.setToolTip(name)
            b.setProperty("empty", not filled)
            b.setChecked(i == self.button)
            b.style().unpolish(b)
            b.style().polish(b)
        self._size_buttons()
        m = bank["memories"][self.button] if self.button < len(bank["memories"]) else None
        if not m or not m.get("filled", bool(m["name"])):
            self.detail.setText("<b>%s</b>" % escape(t("panel_button", n=self.button + 1, name=t("panel_empty_button"))))
            return
        html, unsure = self._memory_html(m, self.button)
        self.detail.setText(html + self._legends(unsure))

    def _memory_html(self, m: dict, index: int, link: str = "", unfolded: bool = False):
        """One registration button as HTML, for both Knoppen and Lijst, so the two always show the same.
        With a link (the list) the title folds the settings groups open and shut; folded is the default,
        as all settings of all buttons at once would be millions of characters. Returns (html, a value
        not sure)."""
        t = self.win.presenter.t
        c = style.colours()
        rows = [(t("info_rhythm"), m["rhythm"]), (t("info_tempo"), str(m["tempo"]) if m["tempo"] else ""),
                (t("info_chord"), m["chord"])]
        rows += [(long, "%s <span style='color:%s'>· %s</span>" % (escape(kind), c["muted"], t("panel_volume", v=v)))
                 for _p, long, kind, v in m["sounds"]]
        groups = [] if link and not unfolded else (m.get("settings" if self.detailed else "basic") or [])
        unsure = any(not sure for _g, items in groups for _l, _v, sure in items)
        more = "".join(
            "<div style='margin-top:6px'><b>%s</b></div><div>%s</div>" % (escape(head), " &nbsp;·&nbsp; ".join(
                "<span style='color:%s'>%s</span>&nbsp;<span style='color:%s'>%s</span>" % (
                    c["muted"] if sure else c["warn"], escape(label).replace(" ", "&nbsp;"),
                    c["text"] if sure else c["warn"], escape(value).replace(" ", "&nbsp;"))
                for label, value, sure in items))
            for head, items in groups)
        title = escape(t("panel_button", n=index + 1, name=m["name"] or t("panel_no_name")))
        if link:               # a clear fold marker, so it is seen to be clickable
            title = "<a href='%s' style='color:%s; text-decoration:none'>%s&nbsp;%s</a>" % (
                link, c["accent_text"], "\u25be" if unfolded else "\u25b8", title)
        html = "<b>%s</b><table cellspacing=0 cellpadding=2>%s</table>%s" % (
            title,
            "".join("<tr><td style='color:%s; padding-right:10px'>%s</td><td>%s</td></tr>"
                    % (c["muted"], escape(a), b if "<span" in b else escape(b)) for a, b in rows if b), more)
        return html, unsure

    def _legends(self, unsure: bool) -> str:
        c, t = style.colours(), self.win.presenter.t
        return "<div style='color:%s; margin-top:8px'>%s</div>%s" % (
            c["muted"], escape(t("panel_sounds_legend")),
            "<div style='color:%s; margin-top:4px'>%s</div>" % (c["warn"], escape(t("panel_unsure_legend")))
            if unsure else "")

    def _bank_text(self, b: dict) -> str:
        t = self.win.presenter.t
        if not b["used"]:
            return t("panel_bank_empty", bank=b["label"])
        return t("panel_bank_line", bank=b["label"], name=b["name"] or t("panel_no_name"), n=b["used"],
                 named=b.get("named", b["used"]))
