"""Build the double-clickable app with PyInstaller: KN Songboek.app on macOS, KN-Songboek.exe on Windows.

    python tools/build_app.py            build for this computer (macOS, Windows or Linux)
    python tools/build_app.py --zip      also pack the result into one file to download (in dist/)

Needs: pip install ".[gui]" pyinstaller pillow
The manual (docs/nl, docs/en, with pictures) goes into the app, so the ?-button works without the repository.
The result lands in dist/. GitHub builds it on every push (.github/workflows/build.yml).
"""
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
from kn_songboek import APP_NAME, __version__  # noqa: E402

FILE_NAME = APP_NAME.replace(" ", "-")          # KN-Songboek: no spaces in the downloaded file
BUNDLE_ID = "io.github.d8bp8ags.kn-songboek"


def make_icon(out_dir: str) -> str:
    """The app icon (gui/icons.py) as a 1024 px PNG; PyInstaller turns it into .icns or .ico (with Pillow)."""
    subprocess.run([sys.executable, os.path.join(ROOT, "tools", "make_app_icon.py"), out_dir], check=True,
                   env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
    return os.path.join(out_dir, "kn-songboek_1024.png")


def manual(data_sep: str) -> list:
    """--add-data for the manual in both languages and its pictures (gui/widgets.py MANUAL_FILES, DOCS)."""
    out = []
    for rel in ("nl/handleiding.md", "nl/img", "en/manual.md", "en/img"):
        src = os.path.join(ROOT, "docs", *rel.split("/"))
        dest = os.path.join("docs", *rel.split("/")) if os.path.isdir(src) else os.path.join("docs", rel.split("/")[0])
        out += ["--add-data", src + data_sep + dest]
    return out


def download_name() -> str:
    """The name of the file people download, e.g. KN-Songboek-0.2.0-macOS-AppleSilicon.zip."""
    if sys.platform == "darwin":
        kind = "macOS-AppleSilicon" if platform.machine() == "arm64" else "macOS-Intel"
        return "%s-%s-%s.zip" % (FILE_NAME, __version__, kind)
    if sys.platform.startswith("win"):
        return "%s-%s-Windows.exe" % (FILE_NAME, __version__)
    return "%s-%s-Linux.tar.gz" % (FILE_NAME, __version__)


def main(argv) -> int:
    build = os.path.join(ROOT, "build")
    dist = os.path.join(ROOT, "dist")
    shutil.rmtree(dist, ignore_errors=True)
    icon = make_icon(os.path.join(build, "icon"))
    data_sep = ";" if sys.platform.startswith("win") else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", APP_NAME if sys.platform == "darwin" else FILE_NAME,
           "--icon", icon,
           "--paths", os.path.join(ROOT, "src"),
           "--workpath", os.path.join(build, "pyinstaller"),
           "--specpath", build,
           "--distpath", dist,
           *manual(data_sep),
           # only what the app uses: keeps the download small
           "--exclude-module", "tkinter", "--exclude-module", "unittest", "--exclude-module", "pytest"]
    if sys.platform == "darwin":
        cmd += ["--osx-bundle-identifier", BUNDLE_ID]
    if sys.platform.startswith("win"):
        cmd += ["--onefile"]                    # one .exe: nothing to unpack, just double-click
    cmd.append(os.path.join(ROOT, "tools", "app_entry.py"))
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    if sys.platform == "darwin":
        set_plist(os.path.join(dist, APP_NAME + ".app"))
    if "--zip" in argv:
        out = os.path.join(dist, download_name())
        if sys.platform == "darwin":            # ditto keeps the app's signature and links intact
            subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                            os.path.join(dist, APP_NAME + ".app"), out], check=True)
        elif sys.platform.startswith("win"):
            shutil.copyfile(os.path.join(dist, FILE_NAME + ".exe"), out)
        else:
            subprocess.run(["tar", "-czf", out, "-C", dist, FILE_NAME], check=True)
        print("download:", out)
    return 0


def set_plist(app: str) -> None:
    """Version and display name in the app's Info.plist, sharp text on Retina screens, and re-sign the app
    (ad hoc, as PyInstaller does) because the plist changed."""
    import plistlib
    path = os.path.join(app, "Contents", "Info.plist")
    with open(path, "rb") as fh:
        info = plistlib.load(fh)
    info.update({"CFBundleDisplayName": APP_NAME, "CFBundleName": APP_NAME,
                 "CFBundleShortVersionString": __version__, "CFBundleVersion": __version__,
                 "NSHighResolutionCapable": True, "LSMinimumSystemVersion": "11.0"})
    with open(path, "wb") as fh:
        plistlib.dump(info, fh)
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
