"""An in-memory card, for tests and for previews in the GUI."""
from __future__ import annotations

from typing import Dict, List, Optional


class MemoryStorage:
    def __init__(self, files: Optional[Dict[str, bytes]] = None, capacity: Optional[int] = None,
                 read_only: bool = False):
        self.files: Dict[str, bytes] = {}
        self.capacity = capacity
        self.read_only = read_only
        for k, v in (files or {}).items():
            self.write(k, v)

    @staticmethod
    def _k(path: str) -> str:
        return "/".join(x for x in path.upper().split("/") if x)

    def read(self, path: str) -> bytes:
        return self.files[self._k(path)]

    def write(self, path: str, data: bytes) -> None:
        self.files[self._k(path)] = bytes(data)

    def exists(self, path: str) -> bool:
        k = self._k(path)
        return k in self.files or any(f.startswith(k + "/") for f in self.files)

    def listdir(self, path: str) -> List[str]:
        k = self._k(path)
        pre = k + "/" if k else ""
        return sorted({f[len(pre):].split("/")[0] for f in self.files if f.startswith(pre)})

    def move(self, src: str, dst: str) -> None:
        self.files[self._k(dst)] = self.files.pop(self._k(src))

    def copy(self, src: str, dst: str) -> None:
        self.files[self._k(dst)] = self.files[self._k(src)]

    def remove(self, path: str) -> None:
        del self.files[self._k(path)]

    def describe(self) -> str:
        return "<memory>"

    def isdir(self, path: str) -> bool:
        k = self._k(path)
        return any(f.startswith(k + "/") for f in self.files)

    def size(self, path: str) -> int:
        return len(self.files[self._k(path)])

    def free_bytes(self) -> Optional[int]:
        if self.capacity is None:
            return None
        return self.capacity - sum(len(v) for v in self.files.values())

    def total_bytes(self) -> Optional[int]:
        return self.capacity

    def writable(self) -> bool:
        return not self.read_only
