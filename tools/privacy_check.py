"""Privacy check: nothing private and no card data may leave this computer (for example to GitHub).

    python tools/privacy_check.py              check the files in this folder that git tracks (now)
    python tools/privacy_check.py --history    check every commit, file and commit message of all branches
    python tools/privacy_check.py --install    install it as git pre-push hook: every push is checked first
    python tools/privacy_check.py --pre-push   (used by the hook) check exactly the commits being pushed

It looks for:
  * card and diskette data: song files (SQT, PMT, LSW, ...), KN7000MN.INF/BAK, TFLDnnn folders, card images,
    zips, and the database signature inside any binary file;
  * personal things: home folders (/Volumes/<disk>, /Users/<name>, C:\\Users\\<name>), copies of cards,
    e-mail addresses, files that keep paths (.coverage, .venv);
  * names of other programs and outside sources that must not be mentioned, names of AI tools (also in
    commit messages, author names and e-mail addresses, and inside pictures) and the app's old name;
  * hidden information in pictures: PNG files may only hold the picture itself (no text, camera or
    content-credential chunks);
  * your own words from the file .privacy-words next to this repository's README (one per line, for example
    your name, the name of the keyboard owner, card names). That file is never pushed (.gitignore).

Exit code 0 = clean, 1 = something found (the push is stopped). Nothing is changed, only reported.
Uses only the Python standard library and git.
"""
from __future__ import annotations

import codecs
import os
import re
import subprocess
import sys
from typing import Iterable, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = "tools/privacy_check.py"
SKIP = {SELF, "tests/test_privacy_check.py"}           # these two must name the patterns they look for
WORDS_FILE = ".privacy-words"
ZERO = "0" * 40

# ---------------------------------------------------------------------------- rules
# Paths (relative, with /) that may not be in the repository at all.
SONG_EXT = ("SQT", "PMT", "CMP", "MSP", "TM", "EFC", "LSW", "SQF", "SEQ", "ACT", "AST", "CST", "PLM", "TKM",
            "XAP", "CDF", "SDB")
BAD_PATHS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("kaartbestand (song)", re.compile(r"(^|/)[^/]+\.(%s)$" % "|".join(SONG_EXT), re.I)),
    ("muziekdatabase van een kaart", re.compile(r"(^|/)KN\d{4}MN\.(INF|BAK)$", re.I)),
    ("map van een kaart", re.compile(r"(^|/)(TFLD\d{3}|PRIVATE/TECHNICS|SD_SOUND)(/|$)", re.I)),
    ("kaart- of diskette-image", re.compile(r"\.(img|ima|dmg|iso|bin|vfd|dsk)$", re.I)),
    ("archief (kan kaarten bevatten)", re.compile(r"\.(zip|7z|rar|tar|gz|tgz)$", re.I)),
    ("bestand met eigen paden", re.compile(r"(^|/)(\.coverage|\.venv|htmlcov|\.DS_Store|.*\.egg-info)(/|$)")),
    ("opslagbestand van KN Songboek", re.compile(r"(^|/)(KNSONGBK\.JOB|[^/]+\.LCK|OEFENEN\.TXT)$", re.I)),
    ("eigen woordenlijst", re.compile(r"(^|/)\.privacy-words$")),
]

# Names that must not appear, written in ROT13 so that this file does not mention them itself.
OTHER_PROGRAMS = "FQ-Rkcybere,FQRkcybere,FQRKCYBE,ZQOP,Xrl Fbsg,XrlFbsg,Fbat Znantre,FbatZnantre,Qngn Onfr Pbairegre,grpuavpfxa7000"
OUTSIDE_SOURCES = "Nedhrbybtvn,grpuavpf-ebzf,grpuavpf-qbpf,qvfnfz"
AI_TOOLS = "Pynhqr,Naguebcvp"
OLD_NAME = "xa7xqo"


def _names(rot13: str) -> "re.Pattern[str]":
    names = codecs.decode(rot13, "rot13").split(",")
    return re.compile("|".join(re.escape(n) for n in names), re.I)


# Text that may not appear in any file or commit message.
BAD_TEXT: List[Tuple[str, "re.Pattern[str]"]] = [
    ("eigen schijf", re.compile(r"/Volumes/[^/\s\"'`]+/[^\s\"'`]", re.I)),
    ("eigen thuismap", re.compile(r"/Users/(?!<|naam\b|name\b|\.\.\.)[A-Za-z]")),
    ("eigen thuismap (Windows)", re.compile(r"[A-Za-z]:\\\\?Users\\\\?(?!a\b|<|naam\b|name\b)[A-Za-z]{2,}")),
    ("kopie van een echte kaart", re.compile(r"SD-(kopie|test)-20\d\d", re.I)),
    ("e-mailadres", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!localhost\b|example\.(org|com)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("ander programma", _names(OTHER_PROGRAMS)),
    ("externe bron", _names(OUTSIDE_SOURCES)),
    ("naam van een AI-hulpmiddel", _names(AI_TOOLS)),
    ("oude naam van de app", _names(OLD_NAME)),
    ("medeauteur in een commit", re.compile(r"^\s*Co-Authored-By:", re.I)),
]
ALLOWED_EMAILS = {"noreply@github.com"}
# Names that may not be hidden inside binary files either (metadata of pictures, for example).
BAD_NAMES_IN_BYTES = [("naam van een AI-hulpmiddel", _names(AI_TOOLS)), ("oude naam van de app", _names(OLD_NAME)),
                      ("ander programma", _names(OTHER_PROGRAMS))]
# The only PNG chunks a picture needs; anything else (tEXt, iTXt, zTXt, eXIf, caBX, ...) can hide information.
PNG_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"pHYs", b"sRGB", b"gAMA", b"cHRM", b"iCCP", b"sBIT", b"bKGD"}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Inside binary files (pictures and the like): the card's database signature means real card data.
BAD_BYTES = [("muziekdatabase van een kaart", b"KN7000 SDDIR INF"), ("muziekdatabase van een kaart", b"KN6000 SDDIR INF")]


def png_extra_chunks(data: bytes) -> List[str]:
    """The chunk types of a PNG file that are not needed for the picture itself."""
    extra, i = [], len(PNG_MAGIC)
    while i + 8 <= len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        kind = data[i + 4:i + 8]
        if kind not in PNG_CHUNKS and kind.decode("latin-1") not in extra:
            extra.append(kind.decode("latin-1"))
        i += 12 + n
    return extra


def own_words(root: str = ROOT) -> List[str]:
    path = os.path.join(root, WORDS_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            return [w.strip() for w in f if w.strip() and not w.lstrip().startswith("#")]
    except OSError:
        return []


# ---------------------------------------------------------------------------- checks
def check_path(path: str) -> List[str]:
    return [why for why, rx in BAD_PATHS if rx.search(path)]


def check_text(text: str, words: Iterable[str] = ()) -> List[Tuple[int, str, str]]:
    """(line number, reason, what was found) for every problem in this text."""
    out = []
    lowered = [w.lower() for w in words]
    for n, line in enumerate(text.splitlines(), 1):
        for why, rx in BAD_TEXT:
            for m in rx.finditer(line):
                if why == "e-mailadres" and (m.group(0).lower() in ALLOWED_EMAILS or
                                             m.group(0).lower().endswith("@users.noreply.github.com")):
                    continue
                out.append((n, why, m.group(0)))
        for w, wl in zip(words, lowered):
            # the word itself, not part of a longer word ("Data" is not in "Database"; digits may follow)
            if re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(wl), line, re.I):
                out.append((n, "woord uit %s" % WORDS_FILE, w))
    return out


def check_blob(path: str, data: bytes, words: Iterable[str] = ()) -> List[str]:
    """Every problem in one file, as readable lines."""
    if path in SKIP:            # they name the patterns, but never your own words
        text = data.decode("utf-8", "replace")
        return ["%s:%d: %s: %s" % (path, n, why, found) for n, why, found in check_text(text, words)
                if why.startswith("woord uit")]
    problems = ["%s: %s" % (path, why) for why in check_path(path)]
    if b"\0" in data[:8000]:                                    # binary
        for why, sig in BAD_BYTES:
            if sig in data:
                problems.append("%s: %s (in de bytes)" % (path, why))
        text = data.decode("latin-1")
        for why, rx in BAD_NAMES_IN_BYTES:
            if rx.search(text):
                problems.append("%s: %s (in de bytes)" % (path, why))
        if data.startswith(PNG_MAGIC):
            extra = png_extra_chunks(data)
            if extra:
                problems.append("%s: verborgen informatie in het plaatje (%s); haal weg met tools/strip_png.py"
                                % (path, ", ".join(extra)))
        for w in words:
            if w.encode("utf-8") in data:
                problems.append("%s: woord uit %s (in de bytes)" % (path, WORDS_FILE))
        return problems
    text = data.decode("utf-8", "replace")
    for n, why, found in check_text(text, words):
        problems.append("%s:%d: %s: %s" % (path, n, why, found))
    return problems


# ---------------------------------------------------------------------------- git
def git(*args: str, root: str = ROOT, data: bool = False):
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout
    return out if data else out.decode("utf-8", "replace")


def check_commit(commit: str, words: List[str], root: str = ROOT, seen: Optional[set] = None) -> List[str]:
    """The files of one commit (each different file content once) plus its message and author."""
    seen = set() if seen is None else seen
    problems = []
    meta = git("show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", commit, root=root)
    for _n, why, found in check_text(meta, words):
        problems.append("commit %s (bericht/auteur): %s: %s" % (commit[:7], why, found))
    for line in git("ls-tree", "-r", "-z", commit, root=root).split("\0"):
        if not line:
            continue
        info, path = line.split("\t", 1)
        sha = info.split()[2]
        if (sha, path) in seen:
            continue
        seen.add((sha, path))
        if info.split()[1] != "blob":
            continue
        data = git("cat-file", "blob", sha, root=root, data=True)
        problems += ["commit %s: %s" % (commit[:7], p) for p in check_blob(path, data, words)]
    return problems


def check_commits(commits: List[str], root: str = ROOT) -> List[str]:
    words, seen, problems = own_words(root), set(), []
    for c in commits:
        problems += check_commit(c, words, root, seen)
    return problems


def check_tree(root: str = ROOT) -> List[str]:
    """The files git tracks, as they are now on disk (also before they are committed)."""
    words, problems = own_words(root), []
    for path in git("ls-files", "-z", "--cached", "--others", "--exclude-standard", root=root).split("\0"):
        full = os.path.join(root, path)
        if not path or not os.path.isfile(full):
            continue
        with open(full, "rb") as f:
            problems += check_blob(path, f.read(), words)
    return problems


def pushed_commits(lines: Iterable[str], root: str = ROOT) -> List[str]:
    """The commits a push sends: for each ref the commits the remote does not have yet."""
    commits: List[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) != 4 or parts[1] == ZERO:                 # deleting a branch sends nothing
            continue
        local, remote = parts[1], parts[3]
        rng = [local, "--not", "--remotes"] if remote == ZERO else ["%s..%s" % (remote, local)]
        for c in git("rev-list", *rng, root=root).split():
            if c not in commits:
                commits.append(c)
    return commits


HOOK = """#!/bin/sh
# Installed by tools/privacy_check.py --install: check every push for private info and card data.
exec python3 "$(git rev-parse --show-toplevel)/tools/privacy_check.py" --pre-push "$@"
"""


def install(root: str = ROOT) -> str:
    hooks = git("rev-parse", "--git-path", "hooks", root=root).strip()
    hooks = hooks if os.path.isabs(hooks) else os.path.join(root, hooks)
    os.makedirs(hooks, exist_ok=True)
    path = os.path.join(hooks, "pre-push")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(HOOK)
    os.chmod(path, 0o755)
    return path


def report(problems: List[str], what: str) -> int:
    if not problems:
        print("Privacycontrole (%s): niets gevonden." % what)
        return 0
    print("Privacycontrole (%s): %d probleem/problemen gevonden:" % (what, len(problems)))
    for p in problems:
        print("  " + p)
    print("Haal dit weg of pas het aan. Eigen woorden staan in %s (wordt nooit gepusht)." % WORDS_FILE)
    return 1


def main(argv: List[str]) -> int:
    if "--install" in argv:
        print("Geïnstalleerd: %s\nVanaf nu wordt elke push eerst gecontroleerd." % install())
        return 0
    if "--pre-push" in argv:
        code = report(check_commits(pushed_commits(sys.stdin.read().splitlines())), "wat gepusht wordt")
        if code:
            print("De push is gestopt.")
        return code
    if "--history" in argv:
        return report(check_commits(git("rev-list", "--all").split()), "hele geschiedenis")
    return report(check_tree(), "bestanden")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
