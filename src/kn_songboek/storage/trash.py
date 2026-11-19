"""Move a file or folder to the Trash (macOS), Recycle Bin (Windows) or the desktop's trash (Linux).

Never deletes for good: if the system will not take it, nothing happens and the caller says so,
so the person can still drag it away themselves and get it back from the bin.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import subprocess
import sys


def move_to_trash(path: str) -> bool:
    """True when `path` is gone from its place and sits in the bin."""
    if not os.path.lexists(path):
        return False
    path = os.path.abspath(path)
    if sys.platform == "darwin":
        ok = _mac(path) or _mac_finder(path)
    elif os.name == "nt":
        ok = _windows(path)
    else:
        ok = _linux(path)
    return ok and not os.path.lexists(path)


def _mac(path: str) -> bool:
    """NSFileManager trashItemAtURL: the item can be put back from the Trash ("Zet terug")."""
    try:
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc") or "libobjc.dylib")
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        send = objc.objc_msgSend

        def call(obj, sel, *args, argtypes=(), restype=ctypes.c_void_p):
            send.restype = restype
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, *argtypes]
            return send(obj, objc.sel_registerName(sel), *args)

        cls = objc.objc_getClass
        text = call(cls(b"NSString"), b"stringWithUTF8String:", path.encode("utf-8"), argtypes=[ctypes.c_char_p])
        url = call(cls(b"NSURL"), b"fileURLWithPath:", text, argtypes=[ctypes.c_void_p])
        manager = call(cls(b"NSFileManager"), b"defaultManager")
        return bool(call(manager, b"trashItemAtURL:resultingItemURL:error:", url, None, None,
                         argtypes=[ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p], restype=ctypes.c_bool))
    except Exception:
        return False


def _mac_finder(path: str) -> bool:
    """Second way, through Finder (macOS may first ask whether the app may use Finder)."""
    quoted = path.replace("\\", "\\\\").replace('"', '\\"')
    return _run(["osascript", "-e", 'tell application "Finder" to delete (POSIX file "%s")' % quoted])


def _windows(path: str) -> bool:
    kind = "DeleteDirectory" if os.path.isdir(path) else "DeleteFile"
    quoted = path.replace("'", "''")
    script = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
              "[Microsoft.VisualBasic.FileIO.FileSystem]::%s('%s', 'OnlyErrorDialogs', 'SendToRecycleBin')"
              % (kind, quoted))
    return _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])


def _linux(path: str) -> bool:
    return _run(["gio", "trash", path])


def _run(cmd) -> bool:
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(cmd, capture_output=True, timeout=60, creationflags=flags).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False
