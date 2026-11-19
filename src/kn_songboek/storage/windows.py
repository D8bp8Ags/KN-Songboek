"""The few things Windows does differently for an SD card or a diskette: a drive is a letter (E:\\), its
name is the volume label, renaming and ejecting go through the system, and an empty floppy drive must
not pop up "There is no disk in the drive". Everything here is a no-op elsewhere, and never raises:
a card that cannot be named or ejected is still a card."""
from __future__ import annotations

import os
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")


def is_drive_root(path: str) -> bool:
    """'E:\\', 'E:' or 'E:/' (not a folder on it)."""
    p = path.rstrip("\\/")
    return len(p) == 2 and p[1] == ":" and p[0].isalpha()


def drive_label(path: str) -> str:
    """The volume label of a drive root on Windows ('' if none or not Windows)."""
    if not (WINDOWS and is_drive_root(path)):
        return ""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(261)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(path[0] + ":\\"), buf, len(buf), None, None, None, None, 0)
        return buf.value.strip() if ok else ""
    except Exception:
        return ""


def display_name(path: str) -> str:
    """What to call a card or folder: the volume label of a Windows drive ('KN7000 (E:)'), else the
    folder's own name (on macOS the mount folder is already the card's name)."""
    if is_drive_root(path):
        label = drive_label(path)
        letter = path[0].upper() + ":"
        return "%s (%s)" % (label, letter) if label else letter
    return os.path.basename(os.path.normpath(path)) or path


def set_drive_label(path: str, name: str) -> bool:
    if not (WINDOWS and is_drive_root(path)):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetVolumeLabelW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(path[0] + ":\\"), ctypes.c_wchar_p(name)))
    except Exception:
        return False


def eject_drive(path: str) -> bool:
    """Ask Windows to eject a removable drive (as "Uitwerpen" in Verkenner). True if it is gone."""
    if not (WINDOWS and is_drive_root(path)):
        return False
    letter = path[0].upper() + ":"
    script = "(New-Object -comObject Shell.Application).Namespace(17).ParseName('%s').InvokeVerb('Eject')" % letter
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                       capture_output=True, timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return not os.path.exists(letter + "\\")


def no_error_dialogs() -> None:
    """Looking at an empty floppy or card reader must not show Windows' "no disk" message box."""
    if not WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x8000)  # type: ignore[attr-defined]
    except Exception:
        pass


def show_in_explorer(path: str) -> bool:
    """Explorer with the file selected."""
    if not WINDOWS or not os.path.exists(path):
        return False
    try:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return True
    except OSError:
        return False


def own_taskbar_icon(app_id: str = "kn-songboek.app") -> None:
    """Without this the taskbar shows Python's icon instead of the app's own."""
    if not WINDOWS:
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
    except Exception:
        pass
