"""Where things live on a KN7000 SD card, and how song files are named.

From program 941 (data_02.s strings, func_48560F53, func_4855F04E, func_4852F840, func_4852F882).
All paths are relative to the card root and use '/' as separator; storage adapters translate.
"""
from __future__ import annotations

from .inf import Song

KN7_DIR = "PRIVATE/TECHNICS/KN7000"
INF_PATH = KN7_DIR + "/KN7000MN.INF"
BAK_PATH = KN7_DIR + "/KN7000MN.BAK"
# Our own note at the card root while a save runs; it stays only when a save did not finish. The root
# is outside the keyboard's own folders, so the keyboard never trips over it.
JOB_PATH = "KNSONGBK.JOB"
CUSTOM_DIR = KN7_DIR + "/CUSTOM"
IMEXPORT_DIR = "IMEXPORT"
DCIM_DIR = "DCIM"
PLUGIN_DIR = "PRIVATE/TECHNICS/DATA"


def folder_dir(folder: int) -> str:
    """0-based folder -> 'PRIVATE/TECHNICS/KN7000/TFLD001'."""
    return "%s/TFLD%03d" % (KN7_DIR, folder + 1)


def default_base(folder: int) -> str:
    return "%03dKN7" % (folder + 1)


def song_filename(folder: int, song: int, entry: Song, ext: str) -> str:
    """'<ss><base6>.<EXT>', e.g. song 1 with base '009KN7' -> '01009KN7.LSW'.

    The two-digit song number comes first (checked against a real card, 2026-11-15). The base
    stays with the song when it moves, so TFLD017 can hold '01009KN7.*'."""
    return "%02d%s.%s" % (song + 1, entry.base or default_base(folder), ext.strip())


def song_path(folder: int, song: int, entry: Song, ext: str) -> str:
    return folder_dir(folder) + "/" + song_filename(folder, song, entry, ext)


def song_paths(folder: int, song: int, entry: Song) -> dict:
    """ext -> card path for every file the entry's type mask lists."""
    return {ext: song_path(folder, song, entry, ext) for ext in entry.extensions}
