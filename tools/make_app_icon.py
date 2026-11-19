"""Write the app icon (gui/icons.py APP_ICON_SVG) as PNG files, e.g. for a macOS .icns later.

    python3 tools/make_app_icon.py [out_dir]      (default: build/icon)
"""
import os
import sys

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from kn_songboek.gui.icons import APP_ICON_SVG  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join("build", "icon")
    os.makedirs(out, exist_ok=True)
    QGuiApplication.instance() or QGuiApplication([])
    renderer = QSvgRenderer(QByteArray(APP_ICON_SVG.encode()))
    with open(os.path.join(out, "kn-songboek.svg"), "w") as f:
        f.write(APP_ICON_SVG)
    for size in (16, 32, 64, 128, 256, 512, 1024):
        img = QImage(size, size, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        renderer.render(p, QRectF(0, 0, size, size))
        p.end()
        img.save(os.path.join(out, "kn-songboek_%d.png" % size))
    print("written to", out)


if __name__ == "__main__":
    main()
