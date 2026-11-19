"""Storage adapters: where the card's bytes live (a mounted card, a folder copy, a disk image)."""
import os

from .base import Storage  # noqa: F401
from .directory import DirectoryStorage  # noqa: F401
from .fatimage import FatImageStorage  # noqa: F401


def open_storage(path: str, read_only: bool = False) -> Storage:
    """A folder (the mounted card or a copy of it) or a disk image file (.img, .dmg, .iso ...)."""
    if os.path.isfile(path):
        return FatImageStorage(path, read_only=read_only)
    return DirectoryStorage(path)
