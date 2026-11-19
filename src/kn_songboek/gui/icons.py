"""Simple line icons, drawn in code (our own, MIT; no icon files or fonts needed).

Every icon sits next to a word, never alone: older users and people new to computers recognise a
picture faster once they know it, but a picture alone is a guess (Nielsen Norman Group, "Icon
Usability"). The icons follow the usual conventions (bin = remove, pencil = rename, two sheets = copy,
magnifier = search, curved arrow = undo) and take the text colour, so they fit light and dark.
Drawn on a 24 x 24 grid with a 2-unit pen, like most modern icon sets.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

P = QPainter


def _card(p: P, x: float = 5, y: float = 2, w: float = 14, h: float = 20) -> None:
    """An SD card: a rectangle with the top right corner cut off, and its contacts."""
    path = QPainterPath()
    path.moveTo(x + 1.5, y)
    path.lineTo(x + w - 4.5, y)
    path.lineTo(x + w, y + 4.5)
    path.lineTo(x + w, y + h - 1.5)
    path.quadTo(x + w, y + h, x + w - 1.5, y + h)
    path.lineTo(x + 1.5, y + h)
    path.quadTo(x, y + h, x, y + h - 1.5)
    path.lineTo(x, y + 1.5)
    path.quadTo(x, y, x + 1.5, y)
    p.drawPath(path)
    for i in range(3):
        cx = x + 3.5 + i * 2.8
        p.drawLine(QPointF(cx, y + 3), QPointF(cx, y + 6))


def _plus(p: P, cx: float, cy: float, r: float) -> None:
    p.drawLine(QPointF(cx - r, cy), QPointF(cx + r, cy))
    p.drawLine(QPointF(cx, cy - r), QPointF(cx, cy + r))


def _arrow(p: P, x1, y1, x2, y2, head: float = 4.5) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    a = math.atan2(y2 - y1, x2 - x1)
    for s in (-1, 1):
        b = a + math.pi + s * math.pi / 4
        p.drawLine(QPointF(x2, y2), QPointF(x2 + head * math.cos(b), y2 + head * math.sin(b)))


def _folder(p: P, x: float = 2, y: float = 5, w: float = 20, h: float = 15) -> None:
    path = QPainterPath()
    path.moveTo(x, y + 1.5)
    path.quadTo(x, y, x + 1.5, y)
    path.lineTo(x + 6, y)
    path.lineTo(x + 8, y + 2.5)
    path.lineTo(x + w - 1.5, y + 2.5)
    path.quadTo(x + w, y + 2.5, x + w, y + 4)
    path.lineTo(x + w, y + h - 1.5)
    path.quadTo(x + w, y + h, x + w - 1.5, y + h)
    path.lineTo(x + 1.5, y + h)
    path.quadTo(x, y + h, x, y + h - 1.5)
    path.closeSubpath()
    p.drawPath(path)


def card(p: P) -> None:
    _card(p)


def card_new(p: P) -> None:
    _card(p, 3, 2, 13, 19)
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(17.5, 17.5), 5.2, 5.2)
    p.setBrush(Qt.NoBrush)
    pen = QPen(p.pen())
    pen.setColor(_background())
    p.save()
    p.setPen(pen)
    _plus(p, 17.5, 17.5, 2.6)
    p.restore()


def library(p: P) -> None:
    """A box to keep things in (an archive box with a lid)."""
    p.drawRoundedRect(QRectF(2.5, 4, 19, 5), 1.2, 1.2)
    path = QPainterPath()
    path.moveTo(4, 9)
    path.lineTo(4, 19)
    path.quadTo(4, 20.5, 5.5, 20.5)
    path.lineTo(18.5, 20.5)
    path.quadTo(20, 20.5, 20, 19)
    path.lineTo(20, 9)
    p.drawPath(path)
    p.drawLine(QPointF(9.5, 13), QPointF(14.5, 13))


def put_on_card(p: P) -> None:
    """An arrow going down onto a card."""
    _card(p, 6, 9, 12, 13)
    _arrow(p, 12, 1.5, 12, 13.5, 4)


def back(p: P) -> None:
    _arrow(p, 20, 12, 4, 12, 6)


def undo(p: P) -> None:
    path = QPainterPath()
    path.moveTo(5, 9)
    path.lineTo(15, 9)
    path.cubicTo(18.9, 9, 21, 11.5, 21, 14.5)
    path.cubicTo(21, 17.5, 18.9, 20, 15, 20)
    path.lineTo(9, 20)
    p.drawPath(path)
    p.drawLine(QPointF(5, 9), QPointF(9, 5))
    p.drawLine(QPointF(5, 9), QPointF(9, 13))


def redo(p: P) -> None:
    """The undo arrow, mirrored."""
    p.save()
    p.translate(24, 0)
    p.scale(-1, 1)
    undo(p)
    p.restore()


def move(p: P) -> None:
    _arrow(p, 3, 12, 20, 12, 6)


def copy(p: P) -> None:
    p.drawRoundedRect(QRectF(8.5, 8.5, 12.5, 12.5), 2, 2)
    path = QPainterPath()
    path.moveTo(5, 15.5)
    path.lineTo(4.5, 15.5)
    path.quadTo(3, 15.5, 3, 14)
    path.lineTo(3, 4.5)
    path.quadTo(3, 3, 4.5, 3)
    path.lineTo(14, 3)
    path.quadTo(15.5, 3, 15.5, 4.5)
    path.lineTo(15.5, 5)
    p.drawPath(path)


def rename(p: P) -> None:
    """A pencil."""
    path = QPainterPath()
    path.moveTo(16, 3.5)
    path.lineTo(20.5, 8)
    path.lineTo(8.5, 20)
    path.lineTo(3.5, 20.5)
    path.lineTo(4, 15.5)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(13.5, 6), QPointF(18, 10.5))


def remove(p: P) -> None:
    """A bin."""
    p.drawLine(QPointF(3, 6), QPointF(21, 6))
    path = QPainterPath()
    path.moveTo(9, 6)
    path.lineTo(9, 3.5)
    path.lineTo(15, 3.5)
    path.lineTo(15, 6)
    p.drawPath(path)
    body = QPainterPath()
    body.moveTo(5.5, 6)
    body.lineTo(6.5, 19.5)
    body.quadTo(6.6, 21, 8, 21)
    body.lineTo(16, 21)
    body.quadTo(17.4, 21, 17.5, 19.5)
    body.lineTo(18.5, 6)
    p.drawPath(body)
    p.drawLine(QPointF(10, 10.5), QPointF(10, 16.5))
    p.drawLine(QPointF(14, 10.5), QPointF(14, 16.5))


def info(p: P) -> None:
    p.drawEllipse(QPointF(12, 12), 9.5, 9.5)
    p.drawLine(QPointF(12, 11), QPointF(12, 17))
    p.drawPoint(QPointF(12, 7.5))


def folder_new(p: P) -> None:
    _folder(p)
    _plus(p, 12, 13.5, 3.2)


def put_in_folder(p: P) -> None:
    _folder(p, 7, 6, 15, 13)
    _arrow(p, 1.5, 13.5, 13, 13.5, 3.8)


def search(p: P) -> None:
    p.drawEllipse(QPointF(10.5, 10.5), 6.5, 6.5)
    p.drawLine(QPointF(15.3, 15.3), QPointF(21, 21))


def filter(p: P) -> None:  # noqa: A001 - the name of the icon
    path = QPainterPath()
    path.moveTo(3, 4)
    path.lineTo(21, 4)
    path.lineTo(14, 12.5)
    path.lineTo(14, 19)
    path.lineTo(10, 21)
    path.lineTo(10, 12.5)
    path.closeSubpath()
    p.drawPath(path)


def tip(p: P) -> None:
    """A light bulb."""
    path = QPainterPath()
    path.moveTo(9, 17)
    path.cubicTo(9, 14.5, 5, 13, 5, 9)
    path.cubicTo(5, 5, 8.2, 2, 12, 2)
    path.cubicTo(15.8, 2, 19, 5, 19, 9)
    path.cubicTo(19, 13, 15, 14.5, 15, 17)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(9.5, 20), QPointF(14.5, 20))
    p.drawLine(QPointF(10.5, 22.5), QPointF(13.5, 22.5))


def star(p: P) -> None:
    path = QPainterPath()
    for i in range(10):
        r = 10 if i % 2 == 0 else 4.3
        a = -math.pi / 2 + i * math.pi / 5
        pt = QPointF(12 + r * math.cos(a), 12.8 + r * math.sin(a))
        path.moveTo(pt) if i == 0 else path.lineTo(pt)
    path.closeSubpath()
    p.drawPath(path)


def history(p: P) -> None:
    """A clock: what was done, and when."""
    p.drawEllipse(QPointF(12, 12), 9.5, 9.5)
    p.drawLine(QPointF(12, 6.5), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(16, 14.5))


def printer(p: P) -> None:
    p.drawRect(QRectF(7, 2.5, 10, 6))
    p.drawRoundedRect(QRectF(2.5, 8.5, 19, 9), 2, 2)
    p.drawRect(QRectF(7, 14, 10, 7.5))


def table(p: P) -> None:
    p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
    p.drawLine(QPointF(3, 9.5), QPointF(21, 9.5))
    p.drawLine(QPointF(3, 15), QPointF(21, 15))
    p.drawLine(QPointF(9.5, 4), QPointF(9.5, 20))


def two_cards(p: P) -> None:
    _card(p, 1.5, 4, 10, 15)
    _card(p, 12.5, 4, 10, 15)


def restore(p: P) -> None:
    """A circle arrow going back (back-up terugzetten)."""
    path = QPainterPath()
    path.arcMoveTo(QRectF(3, 3, 18, 18), 150)
    path.arcTo(QRectF(3, 3, 18, 18), 150, -300)
    p.drawPath(path)
    start = QPointF(12 + 9 * math.cos(math.radians(150)), 12 - 9 * math.sin(math.radians(150)))
    p.drawLine(start, start + QPointF(0, -5))
    p.drawLine(start, start + QPointF(5, 0.5))
    p.drawLine(QPointF(12, 8), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(14.5, 14))


def check(p: P) -> None:
    """A card with a tick: check the card (and repair it)."""
    _card(p, 3, 2, 13, 19)
    p.setBrush(p.pen().color())
    p.drawEllipse(QPointF(17.5, 17.5), 5.2, 5.2)
    p.setBrush(Qt.NoBrush)
    pen = QPen(p.pen())
    pen.setColor(_background())
    p.save()
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(15, 17.6)
    path.lineTo(16.9, 19.4)
    path.lineTo(20.1, 15.8)
    p.drawPath(path)
    p.restore()


def chevron(p: P) -> None:
    """"Go on here": the arrow at the right of a start-screen task."""
    pen = p.pen()
    pen.setWidthF(2.6)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(9, 5)
    path.lineTo(16, 12)
    path.lineTo(9, 19)
    p.drawPath(path)


DRAW: Dict[str, Callable[[P], None]] = {
    "card": card, "card_new": card_new, "library": library, "put_on_card": put_on_card, "back": back,
    "undo": undo, "redo": redo, "move": move, "copy": copy, "rename": rename, "remove": remove, "info": info,
    "folder_new": folder_new, "put_in_folder": put_in_folder, "search": search, "filter": filter, "tip": tip,
    "star": star, "history": history, "printer": printer, "table": table, "two_cards": two_cards,
    "restore": restore, "check": check, "chevron": chevron,
}

_bg: Optional[QColor] = None


def _background() -> QColor:
    return _bg if _bg is not None else QColor("white")


def text_colour() -> QColor:
    app = QGuiApplication.instance()
    return app.palette().color(QPalette.ButtonText) if app else QColor("black")


def pixmap(name: str, size: int = 20, colour: Optional[QColor] = None, background: Optional[QColor] = None,
           scale: int = 2) -> QPixmap:
    """The icon as a sharp picture (drawn at twice the size for Retina screens), size grown with the
    chosen text size (Weergave › Lettergrootte)."""
    from . import style
    return _draw(name, style.px(size), colour, background, scale)


def _draw(name: str, size: int, colour: Optional[QColor], background: Optional[QColor], scale: int) -> QPixmap:
    global _bg
    colour = colour or text_colour()
    app = QGuiApplication.instance()
    _bg = background or (app.palette().color(QPalette.Button) if app else QColor("white"))
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size * scale / 24.0, size * scale / 24.0)
    pen = QPen(colour, 2.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    DRAW[name](p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, colour: Optional[QColor] = None, background: Optional[QColor] = None) -> QIcon:
    ic = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64):              # plain pixels; Qt picks the size it needs
        ic.addPixmap(_draw(name, size, colour, background, 1))
    return ic


# The app's own icon: an SD card with music on it, above a keyboard, on the app's blue. Our own drawing
# (MIT), kept as SVG text so there is no image file to lose. tools/make_app_icon.py writes it out as
# PNG files for packaging.
APP_ICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024"><defs><linearGradient id="g" '
    'x1="0" y1="0" x2="0" y2="1">\n<stop offset="0" stop-color="#2f80e4"/><stop offset="1" '
    'stop-color="#174f9e"/></linearGradient></defs>\n<rect x="40" y="40" width="944" height="944" '
    'rx="210" fill="url(#g)"/><path d="M330,130 H605.3 L724,248.7 V660 Q724,690 694,690 H330 '
    'Q300,690 300,660 V160 Q300,130 330,130 Z" fill="#ffffff"/><rect x="345" y="165" width="34" '
    'height="95" rx="9" fill="#c9daf2"/><rect x="405" y="165" width="34" height="95" rx="9" '
    'fill="#c9daf2"/><rect x="465" y="165" width="34" height="95" rx="9" fill="#c9daf2"/><rect '
    'x="525" y="165" width="34" height="95" rx="9" fill="#c9daf2"/><g transform="translate(500,450) '
    'scale(0.8)" fill="#1f6fd1"><ellipse cx="-70" cy="120" rx="58" ry="44" transform="rotate(-20 '
    '-70 120)"/><ellipse cx="130" cy="90" rx="58" ry="44" transform="rotate(-20 130 90)"/><rect '
    'x="-20" y="-150" width="22" height="270"/><rect x="180" y="-180" width="22" height="270"/>'
    '<polygon points="-20,-150 202,-180 202,-110 -20,-80"/></g><rect x="144" y="720" width="98.3" '
    'height="200" rx="14" fill="#ffffff"/><rect x="250.3" y="720" width="98.3" height="200" rx="14" '
    'fill="#ffffff"/><rect x="356.6" y="720" width="98.3" height="200" rx="14" fill="#ffffff"/>'
    '<rect x="462.9" y="720" width="98.3" height="200" rx="14" fill="#ffffff"/><rect x="569.1" '
    'y="720" width="98.3" height="200" rx="14" fill="#ffffff"/><rect x="675.4" y="720" width="98.3" '
    'height="200" rx="14" fill="#ffffff"/><rect x="781.7" y="720" width="98.3" height="200" rx="14" '
    'fill="#ffffff"/><rect x="214.4" y="720" width="63.8" height="120" rx="8" fill="#10233f"/><rect '
    'x="320.7" y="720" width="63.8" height="120" rx="8" fill="#10233f"/><rect x="533.3" y="720" '
    'width="63.8" height="120" rx="8" fill="#10233f"/><rect x="639.5" y="720" width="63.8" '
    'height="120" rx="8" fill="#10233f"/><rect x="745.8" y="720" width="63.8" height="120" rx="8" '
    'fill="#10233f"/></svg>'
)


def app_icon() -> QIcon:
    """The window and Dock icon, sharp at every size."""
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        ic.addPixmap(pm)
    return ic
