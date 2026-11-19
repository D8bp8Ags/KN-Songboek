"""A card that is a disk image file (e.g. made with `dd` or Disk Utility), read and written directly.

Own implementation of FAT12/16/32 as described in Microsoft's "FAT: General Overview of On-Disk
Format" (fatgen103); no code copied (ADR-0004). Scope is what the KN7000 needs:
  * the image may be a whole card (MBR with a FAT partition) or a single volume ("superfloppy");
  * reading follows long file names for display, but everything the keyboard writes is 8.3, so new
    names must be valid 8.3 names (upper case is used on disk);
  * writes are ordered data -> FAT (all copies) -> directory entry, so an interrupted write leaves at
    worst lost clusters (which `fsck`/chkdsk reclaims), never a file pointing at garbage.
"""
from __future__ import annotations

import os
import struct
import time
from dataclasses import dataclass
from typing import BinaryIO, Dict, List, Optional, Tuple

FAT_PARTITION_TYPES = {0x01, 0x04, 0x06, 0x0B, 0x0C, 0x0E}
ATTR_RO, ATTR_HIDDEN, ATTR_SYSTEM, ATTR_VOLUME, ATTR_DIR, ATTR_ARCHIVE = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
ATTR_LFN = 0x0F
_VALID_83 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!#$%&'()-@^_`{}~")


class FatError(OSError):
    pass


@dataclass
class _Entry:
    name: str                  # long name if there is one, else "NAME.EXT"
    short: str                 # "NAME.EXT"
    attr: int
    cluster: int
    size: int
    dir_cluster: int           # directory holding the entry (0 = fixed FAT12/16 root)
    index: int                 # entry number inside that directory
    lfn_start: int             # first entry number of its long-name entries (== index if none)

    @property
    def is_dir(self) -> bool:
        return bool(self.attr & ATTR_DIR)


def short_name(name: str) -> bytes:
    """'KN7000MN.INF' -> b'KN7000MNINF'; raises FatError if it is not a valid 8.3 name."""
    up = name.upper()
    base, _, ext = up.partition(".")
    if not base or len(base) > 8 or len(ext) > 3 or "." in ext or not set(base + ext) <= _VALID_83:
        raise FatError("'%s' is not a valid 8.3 file name (the keyboard only uses 8.3 names)" % name)
    return base.ljust(8).encode("ascii") + ext.ljust(3).encode("ascii")


def _decode_short(raw: bytes) -> str:
    base = raw[:8].decode("latin-1").rstrip()
    if base and base[0] == "\x05":
        base = "\xe5" + base[1:]
    ext = raw[8:11].decode("latin-1").rstrip()
    return base + ("." + ext if ext else "")


def _dos_now() -> Tuple[int, int]:
    t = time.localtime()
    return ((t.tm_hour << 11) | (t.tm_min << 5) | (t.tm_sec // 2),
            (((t.tm_year - 1980) & 0x7F) << 9) | (t.tm_mon << 5) | t.tm_mday)


class FatImageStorage:
    def __init__(self, path: str, read_only: bool = False):
        self.path = os.path.abspath(path)
        self.read_only = read_only or not os.access(self.path, os.W_OK)
        self.fh: BinaryIO = open(self.path, "rb" if self.read_only else "r+b")
        try:
            self._mount()
        except Exception:
            self.fh.close()                 # not an image we can use: do not leave the file open
            raise

    # ------------------------------------------------------------------ volume
    def _mount(self) -> None:
        sec0 = self._pread(0, 512)
        if len(sec0) < 512 or sec0[510:512] != b"\x55\xaa":
            raise FatError("%s is not a disk image (no boot signature)" % self.path)
        self.base = 0
        if not self._looks_like_bpb(sec0):
            for i in range(4):
                e = sec0[446 + 16 * i:462 + 16 * i]
                if e[4] in FAT_PARTITION_TYPES:
                    self.base = struct.unpack_from("<I", e, 8)[0] * 512
                    break
            else:
                raise FatError("%s has no FAT partition" % self.path)
        bs = self._pread(self.base, 512)
        if not self._looks_like_bpb(bs):
            raise FatError("%s: the partition does not hold a FAT file system" % self.path)
        (self.bps, self.spc, reserved, self.nfats, root_entries, total16, _media, fatsz16) = \
            struct.unpack_from("<HBHBHHBH", bs, 11)
        total32 = struct.unpack_from("<I", bs, 32)[0]
        fatsz = fatsz16 or struct.unpack_from("<I", bs, 36)[0]
        total = total16 or total32
        self.cluster_size = self.bps * self.spc
        self.fat_offset = self.base + reserved * self.bps
        self.fat_bytes = fatsz * self.bps
        root_sectors = (root_entries * 32 + self.bps - 1) // self.bps
        self.root_offset = self.fat_offset + self.nfats * self.fat_bytes
        self.root_entries = root_entries
        self.data_offset = self.root_offset + root_sectors * self.bps
        data_sectors = total - (reserved + self.nfats * fatsz + root_sectors)
        self.clusters = data_sectors // self.spc
        self.fat_type = 12 if self.clusters < 4085 else 16 if self.clusters < 65525 else 32
        self.root_cluster = struct.unpack_from("<I", bs, 44)[0] if self.fat_type == 32 else 0
        self.fsinfo = struct.unpack_from("<H", bs, 48)[0] if self.fat_type == 32 else 0
        self.fat = bytearray(self._pread(self.fat_offset, self.fat_bytes))
        self._eoc = {12: 0xFF8, 16: 0xFFF8, 32: 0x0FFFFFF8}[self.fat_type]

    @staticmethod
    def _looks_like_bpb(s: bytes) -> bool:
        bps = struct.unpack_from("<H", s, 11)[0]
        return (s[0] in (0xEB, 0xE9) and bps in (512, 1024, 2048, 4096)
                and s[13] in (1, 2, 4, 8, 16, 32, 64, 128) and s[16] in (1, 2))

    def _pread(self, off: int, n: int) -> bytes:
        self.fh.seek(off)
        return self.fh.read(n)

    def _pwrite(self, off: int, data: bytes) -> None:
        if self.read_only:
            raise FatError("%s is opened read-only" % self.path)
        self.fh.seek(off)
        self.fh.write(data)

    def close(self) -> None:
        self.fh.close()

    # ------------------------------------------------------------------ FAT
    def _get(self, n: int) -> int:
        if self.fat_type == 16:
            return struct.unpack_from("<H", self.fat, n * 2)[0]
        if self.fat_type == 32:
            return struct.unpack_from("<I", self.fat, n * 4)[0] & 0x0FFFFFFF
        v = struct.unpack_from("<H", self.fat, n + n // 2)[0]
        return v >> 4 if n & 1 else v & 0xFFF

    def _set(self, n: int, v: int) -> None:
        if self.fat_type == 16:
            struct.pack_into("<H", self.fat, n * 2, v & 0xFFFF)
        elif self.fat_type == 32:
            old = struct.unpack_from("<I", self.fat, n * 4)[0]
            struct.pack_into("<I", self.fat, n * 4, (old & 0xF0000000) | (v & 0x0FFFFFFF))
        else:
            o = n + n // 2
            old = struct.unpack_from("<H", self.fat, o)[0]
            new = (old & 0x000F) | ((v & 0xFFF) << 4) if n & 1 else (old & 0xF000) | (v & 0xFFF)
            struct.pack_into("<H", self.fat, o, new)

    def _flush_fat(self) -> None:
        for i in range(self.nfats):
            self._pwrite(self.fat_offset + i * self.fat_bytes, bytes(self.fat))
        if self.fat_type == 32 and self.fsinfo:
            off = self.base + self.fsinfo * self.bps
            info = bytearray(self._pread(off, 512))
            if info[:4] == b"RRaA":
                free = sum(1 for n in range(2, self.clusters + 2) if self._get(n) == 0)
                struct.pack_into("<II", info, 488, free, 0xFFFFFFFF)            # next-free hint: unknown
                self._pwrite(off, bytes(info))
        self.fh.flush()

    def _chain(self, first: int) -> List[int]:
        out, n, seen = [], first, set()
        while 2 <= n < self._eoc and n not in seen:
            if n >= self.clusters + 2:
                raise FatError("%s: cluster chain points outside the volume" % self.path)
            seen.add(n)
            out.append(n)
            n = self._get(n)
        return out

    def _alloc(self, count: int) -> List[int]:
        out = []
        for n in range(2, self.clusters + 2):
            if self._get(n) == 0:
                out.append(n)
                if len(out) == count:
                    break
        if len(out) < count:
            raise FatError("%s is full" % self.path)
        for a, b in zip(out, out[1:] + [None]):
            self._set(a, b if b is not None else 0x0FFFFFFF)
        return out

    def _free_chain(self, first: int) -> None:
        for n in self._chain(first):
            self._set(n, 0)

    def _coff(self, n: int) -> int:
        return self.data_offset + (n - 2) * self.cluster_size

    def _read_chain(self, first: int, size: Optional[int] = None) -> bytes:
        data = b"".join(self._pread(self._coff(n), self.cluster_size) for n in self._chain(first))
        return data if size is None else data[:size]

    # ------------------------------------------------------------------ directories
    def _dir_raw(self, cluster: int) -> bytes:
        if cluster == 0:
            return self._pread(self.root_offset, self.root_entries * 32)
        return self._read_chain(cluster)

    def _entry_offset(self, cluster: int, index: int) -> int:
        if cluster == 0:
            return self.root_offset + index * 32
        per = self.cluster_size // 32
        return self._coff(self._chain(cluster)[index // per]) + (index % per) * 32

    def _root(self) -> int:
        return self.root_cluster if self.fat_type == 32 else 0

    def _entries(self, cluster: int) -> List[_Entry]:
        raw = self._dir_raw(cluster)
        out: List[_Entry] = []
        lfn: Dict[int, str] = {}
        lfn_start = None
        for i in range(len(raw) // 32):
            e = raw[i * 32:(i + 1) * 32]
            if e[0] == 0:
                break
            if e[0] == 0xE5:
                lfn, lfn_start = {}, None
                continue
            if e[11] == ATTR_LFN:
                if lfn_start is None:
                    lfn_start = i
                part = (e[1:11] + e[14:26] + e[28:32]).decode("utf-16-le", "replace")
                lfn[e[0] & 0x1F] = part.split("\x00")[0]
                continue
            if e[11] & ATTR_VOLUME:
                lfn, lfn_start = {}, None
                continue
            short = _decode_short(e[:11])
            long = "".join(lfn[k] for k in sorted(lfn)).rstrip("￿") if lfn else ""
            hi = struct.unpack_from("<H", e, 20)[0] if self.fat_type == 32 else 0
            cl = (hi << 16) | struct.unpack_from("<H", e, 26)[0]
            out.append(_Entry(long or short, short, e[11], cl, struct.unpack_from("<I", e, 28)[0],
                              cluster, i, lfn_start if lfn_start is not None else i))
            lfn, lfn_start = {}, None
        return [x for x in out if x.short not in (".", "..")]

    @staticmethod
    def _parts(path: str) -> List[str]:
        return [x for x in path.replace("\\", "/").split("/") if x]

    def _find(self, cluster: int, name: str) -> Optional[_Entry]:
        up = name.upper()
        for e in self._entries(cluster):
            if e.name.upper() == up or e.short.upper() == up:
                return e
        return None

    def _lookup(self, path: str) -> Optional[_Entry]:
        parts = self._parts(path)
        cl, e = self._root(), None
        for i, p in enumerate(parts):
            e = self._find(cl, p)
            if e is None or (i < len(parts) - 1 and not e.is_dir):
                return None
            cl = e.cluster
        return e

    def _dir_cluster(self, path: str, create: bool) -> int:
        cl = self._root()
        for p in self._parts(path):
            e = self._find(cl, p)
            if e is None:
                if not create:
                    raise FileNotFoundError(path)
                cl = self._mkdir(cl, p)
            elif not e.is_dir:
                raise FatError("%s is a file, not a folder" % p)
            else:
                cl = e.cluster
        return cl

    def _free_slot(self, cluster: int) -> int:
        raw = self._dir_raw(cluster)
        for i in range(len(raw) // 32):
            if raw[i * 32] in (0, 0xE5):
                return i
        if cluster == 0:
            raise FatError("the root folder of %s is full" % self.path)
        chain = self._chain(cluster)
        new = self._alloc(1)[0]
        self._set(chain[-1], new)
        self._pwrite(self._coff(new), bytes(self.cluster_size))
        self._flush_fat()
        return len(chain) * (self.cluster_size // 32)

    def _put_entry(self, cluster: int, index: int, name11: bytes, attr: int, first: int, size: int) -> None:
        t, d = _dos_now()
        e = struct.pack("<11sBBBHHHHHHHI", name11, attr, 0, 0, t, d, d, (first >> 16) & 0xFFFF, t, d,
                        first & 0xFFFF, size)
        self._pwrite(self._entry_offset(cluster, index), e)

    def _mkdir(self, parent: int, name: str) -> int:
        n11 = short_name(name)
        cl = self._alloc(1)[0]
        block = bytearray(self.cluster_size)
        t, d = _dos_now()
        dot = parent if parent != self._root() else 0
        block[0:32] = struct.pack("<11sBBBHHHHHHHI", b".          ", ATTR_DIR, 0, 0, t, d, d, cl >> 16, t, d, cl & 0xFFFF, 0)
        block[32:64] = struct.pack("<11sBBBHHHHHHHI", b"..         ", ATTR_DIR, 0, 0, t, d, d, dot >> 16, t, d, dot & 0xFFFF, 0)
        self._pwrite(self._coff(cl), bytes(block))
        self._flush_fat()
        self._put_entry(parent, self._free_slot(parent), n11, ATTR_DIR, cl, 0)
        self.fh.flush()
        return cl

    def _delete_entry(self, e: _Entry) -> None:
        for i in range(e.lfn_start, e.index + 1):
            self._pwrite(self._entry_offset(e.dir_cluster, i), b"\xe5")

    def _split(self, path: str) -> Tuple[str, str]:
        parts = self._parts(path)
        if not parts:
            raise FatError("no file name in '%s'" % path)
        return "/".join(parts[:-1]), parts[-1]

    # ------------------------------------------------------------------ Storage protocol
    def read(self, path: str) -> bytes:
        e = self._lookup(path)
        if e is None or e.is_dir:
            raise FileNotFoundError(path)
        return self._read_chain(e.cluster, e.size) if e.size else b""

    def write(self, path: str, data: bytes) -> None:
        folder, name = self._split(path)
        n11 = short_name(name) if self._lookup(path) is None else None
        parent = self._dir_cluster(folder, create=True)
        old = self._find(parent, name)
        if old is not None and old.is_dir:
            raise FatError("%s is a folder" % path)
        need = (len(data) + self.cluster_size - 1) // self.cluster_size
        chain = self._alloc(need) if need else []
        for i, n in enumerate(chain):                       # 1. data
            chunk = data[i * self.cluster_size:(i + 1) * self.cluster_size]
            self._pwrite(self._coff(n), chunk.ljust(self.cluster_size, b"\0"))
        self._flush_fat()                                   # 2. FAT
        first = chain[0] if chain else 0
        if old is None:                                     # 3. directory entry
            assert n11 is not None                          # a new file always has its 8.3 name
            self._put_entry(parent, self._free_slot(parent), n11, ATTR_ARCHIVE, first, len(data))
        else:
            off = self._entry_offset(parent, old.index)
            e = bytearray(self._pread(off, 32))
            t, d = _dos_now()
            struct.pack_into("<HHHHI", e, 20, (first >> 16) & 0xFFFF, t, d, first & 0xFFFF, len(data))
            e[11] |= ATTR_ARCHIVE
            self._pwrite(off, bytes(e))
            if old.cluster:
                self._free_chain(old.cluster)               # 4. only now release the old data
                self._flush_fat()
        self.fh.flush()

    def exists(self, path: str) -> bool:
        return not self._parts(path) or self._lookup(path) is not None

    def listdir(self, path: str) -> List[str]:
        try:
            cl = self._dir_cluster(path, create=False)
        except (FileNotFoundError, FatError):
            return []
        return sorted(e.name for e in self._entries(cl))

    def move(self, src: str, dst: str) -> None:
        e = self._lookup(src)
        if e is None:
            raise FileNotFoundError(src)
        if e.is_dir:
            raise FatError("moving folders is not supported")
        if self._lookup(dst) is not None:
            self.remove(dst)
        folder, name = self._split(dst)
        n11 = short_name(name)
        parent = self._dir_cluster(folder, create=True)
        raw = self._pread(self._entry_offset(e.dir_cluster, e.index), 32)
        attr = raw[11]
        self._put_entry(parent, self._free_slot(parent), n11, attr, e.cluster, e.size)
        e = self._lookup(src)                               # entry numbers may have moved if same folder
        assert e is not None
        self._delete_entry(e)
        self.fh.flush()

    def copy(self, src: str, dst: str) -> None:
        self.write(dst, self.read(src))

    def remove(self, path: str) -> None:
        e = self._lookup(path)
        if e is None:
            raise FileNotFoundError(path)
        if e.is_dir:
            raise FatError("%s is a folder" % path)
        self._delete_entry(e)
        if e.cluster:
            self._free_chain(e.cluster)
            self._flush_fat()
        self.fh.flush()

    def describe(self) -> str:
        return self.path

    def isdir(self, path: str) -> bool:
        if not self._parts(path):
            return True
        e = self._lookup(path)
        return e is not None and e.is_dir

    def size(self, path: str) -> int:
        e = self._lookup(path)
        if e is None:
            raise FileNotFoundError(path)
        return e.size

    def free_bytes(self) -> Optional[int]:
        return sum(1 for n in range(2, self.clusters + 2) if self._get(n) == 0) * self.cluster_size

    def total_bytes(self) -> Optional[int]:
        return self.clusters * self.cluster_size

    def writable(self) -> bool:
        return not self.read_only
