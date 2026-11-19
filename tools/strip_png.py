"""Remove hidden information from PNG pictures: keep only the chunks the picture itself needs.

    python tools/strip_png.py docs/nl/img/*.png     strip these files in place (the picture stays the same)

Screenshots and exported pictures can carry text, camera or content-credential chunks. The privacy check
(tools/privacy_check.py) refuses PNG files with such chunks.
"""
from __future__ import annotations

import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from privacy_check import PNG_CHUNKS, PNG_MAGIC  # noqa: E402


def strip(data: bytes) -> bytes:
    if not data.startswith(PNG_MAGIC):
        return data
    out, i = [PNG_MAGIC], len(PNG_MAGIC)
    while i + 8 <= len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        if data[i + 4:i + 8] in PNG_CHUNKS:
            out.append(data[i:i + 12 + n])
        i += 12 + n
    return b"".join(out)


def main(paths: List[str]) -> int:
    for p in paths:
        with open(p, "rb") as f:
            data = f.read()
        clean = strip(data)
        if clean != data:
            with open(p, "wb") as f:
                f.write(clean)
            print("schoongemaakt: %s (%d bytes minder)" % (p, len(data) - len(clean)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
