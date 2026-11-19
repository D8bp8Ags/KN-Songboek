"""KN Songboek command line. A thin adapter: parse arguments, call CardSession, print results.

Follows the Command Line Interface Guidelines (clig.dev): subcommands, --help everywhere,
--json for scripts, --dry-run for anything that writes, exit code 0/1/2, errors on stderr.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict

from .. import __version__
from ..core import CardSession, KN7Error
from ..core import backup as bk
from ..core import cards as cd
from ..core import duplicates as dup
from ..core import library as lb
from ..core import repair as rp
from ..formats import container
from ..storage import open_storage


def _open(args) -> CardSession:
    return CardSession.open(open_storage(args.card))


def _finish(args, s: CardSession, msg: str) -> int:
    if args.dry_run:
        print("dry run, nothing written. Planned:")
        for op in s.pending:
            print("  " + str(op))
        return 0
    s.preflight()
    if not args.no_backup:
        print("back-up: %s" % bk.make_backup(s.storage, args.backup_dir, args.keep))
    n = s.save()
    print("%s (%d file operation(s); database written to KN7000MN.INF and .BAK)" % (msg, n))
    return 0


def _kb(n):
    return "unknown" if n is None else "%d KB" % (n // 1024)


def cmd_show(args):
    d = _open(args).song_details(args.folder, args.song)
    if args.json:
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return 0
    print("%02d/%02d  %s" % (d["folder"], d["song"], d["name"]))
    for ext, f in d["files"].items():
        print("  %-4s %8s  %s" % (ext, "missing" if f["bytes"] is None else f["bytes"], f["path"]))
    seq = d["sequencer"]
    if not seq:
        print("  sequencer: no recorded song" if "SQT" in d["files"] else "  sequencer: no SQT file")
    for q in seq:
        if q.get("rhythm"):
            print("  sequencer song %d: rhythm %s, time signature %s"
                  % (q["index"], q["rhythm"], q["meter"] or "unknown (style not on the card)"))
        if not q["tracks"]:
            print("  sequencer song %d: settings only, no recorded events" % q["index"])
            continue
        print("  sequencer song %d: %s  (%s)  tempo %s, %d beats, %d notes"
              % (q["index"], q["name"] or "-", q["model"], q["tempo"] or "?", q["beats"], q["notes"]))
        for t in q["tracks"]:
            print("    track %2d: %5d events, %5d notes%s" % (t["track"], t["events"], t["notes"],
                                                            "" if t["complete"] else "  (not fully read)"))
    if "sequencer_error" in d:
        print("  sequencer: could not read (%s)" % d["sequencer_error"])
    _print_contents(d)
    if args.picture:
        bmp = _open(args).home_page_bmp(args.folder, args.song)
        if bmp is None:
            print("  no home page picture")
        else:
            with open(args.picture, "wb") as f:
                f.write(bmp)
            print("  home page picture written to %s" % args.picture)
    return 0


def _print_contents(d):
    _print_memories(d)
    for st in d.get("styles", []):
        var = [v for v in st["variations"] if v]
        print("  composer style %d: %s%s" % (st["number"], st["name"] or "-",
                                             "  (%s)" % ", ".join(var) if var else ""))
    _print_pads(d)
    snd = d.get("sounds")
    if snd:
        print("  sound edit (%s): %s; drum kit %s" % (snd["model"], ", ".join(n for n in snd["sounds"] if n),
                                                     snd["drum_kit"] or "-"))
    hp = d.get("home_page")
    if hp:
        print("  home page picture: %dx%d" % (hp["width"], hp["height"]))
    for ext, e in d.get("errors", {}).items():
        print("  %s: could not read (%s)" % (ext, e))


def _print_memories(d):
    for b in d.get("panel_memories", []):
        print("  panel memory bank %d: %s" % (b["number"], b["name"] or "-"))
        for m in b["memories"]:
            print("    %d  %-16s %s" % (m["number"], m["name"] or "-", "tempo %d" % m["tempo"] if m["tempo"] else ""))


def _print_pads(d):
    for b in (d["pads"]["banks"] if d.get("pads") else []):
        names = [p["name"] or "user pad %d" % p["user"] if p["user"] else "built-in" for p in b["pads"]]
        print("  pad bank %d: %s: %s" % (b["number"], b["name"] or "-", ", ".join(names)))


def _runs(entries):
    """'A16 A2 B17-B999': consecutive numbers of one kind shortened to a range."""
    out, i = [], 0
    while i < len(entries):
        j = i
        while j + 1 < len(entries) and entries[j + 1] == (entries[i][0], entries[j][1] + 1):
            j += 1
        k, n = entries[i]
        out.append("%s%d" % (k, n) if j - i < 2 else "%s%d-%s%d" % (k, n, k, entries[j][1]))
        out += ["%s%d" % entries[x] for x in range(i + 1, j + 1)] if 0 < j - i < 2 else []
        i = j + 1
    return " ".join(out)


def cmd_sdsound(args):
    d = _open(args).sd_sound()
    if args.json:
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return 0
    if not d["names"] and not d["order"] and not d["midi"]:
        print("no SD_SOUND folder on this card")
        return 0
    print("SD_SOUND.TKM")
    for i, n in enumerate(d["names"], 1):
        print("  %2d  %s" % (i, n or "(empty)"))
    if d["order"]:
        print("SD_SOUND.PLM  %d entries: %s" % (len(d["order"]), _runs(d["order"])))
    print("MIDI files    %s" % (len(d["midi"]) or "none"))
    for p in d["midi"]:
        print("  " + p)
    return 0


def cmd_info(args):
    s = _open(args)
    songs = sum(f.used for f in s.folders())
    info = {"card": s.storage.describe(), "database": s.loaded_from, "folders": len(s.folders()),
            "songs": songs, "free_bytes": s.storage.free_bytes(), "writable": s.storage.writable(),
            "backups": os.path.join(args.backup_dir or bk.default_backup_dir(), bk.card_label(s.storage))}
    if args.json:
        print(json.dumps(info, indent=2))
        return 0
    print("card       %s" % info["card"])
    print("database   %s" % info["database"])
    print("songs      %d in %d folder(s)" % (songs, info["folders"]))
    print("free       %s%s" % (_kb(info["free_bytes"]), "" if info["writable"] else "  (write-protected)"))
    print("back-ups   %s" % info["backups"])
    return 0


def cmd_backup(args):
    s = _open(args)
    print(bk.make_backup(s.storage, args.backup_dir, args.keep))
    return 0


def cmd_backups(args):
    st = open_storage(args.card)
    folder = os.path.join(args.backup_dir or bk.default_backup_dir(), bk.card_label(st))
    items = bk.list_backups(folder)
    if args.json:
        print(json.dumps([asdict(b) for b in items], indent=2))
        return 0
    for n, b in enumerate(items, 1):
        print("%2d  %s  %4d songs  %s" % (n, b.created.replace("T", " "), b.songs, b.path))
    if not items:
        print("no back-ups in %s" % folder)
    return 0


def cmd_repair(args):
    st = open_storage(args.card)
    db, rep = rp.rebuild(st)
    if args.json:
        print(json.dumps(asdict(rep), indent=2, ensure_ascii=False))
    else:
        for f, s, n in rep.added:
            print("add      %02d/%02d  %s" % (f, s, n))
        for f, s, n in rep.removed:
            print("remove   %02d/%02d  %s  (files are gone)" % (f, s, n))
        for f, s, n in rep.changed:
            print("update   %02d/%02d  %s  (file types)" % (f, s, n))
        for p in rep.conflicts:
            print("conflict %s" % p)
        for p in rep.unknown_files:
            print("ignored  %s" % p)
    if rep.nothing_to_do:
        print("database matches the files, nothing to repair")
        return 0
    if args.dry_run:
        print("dry run, nothing written")
        return 0
    s = CardSession(st, db, "repair")
    s.preflight()
    if not args.no_backup:
        print("back-up: %s" % bk.make_backup(st, args.backup_dir, args.keep))
    s.save()
    print("database rebuilt: %d added, %d removed, %d updated" % (len(rep.added), len(rep.removed), len(rep.changed)))
    return 0


def cmd_restore(args):
    st = open_storage(args.card)
    src = args.backup
    if src.isdigit():                      # number from `kn-songboek-cli backups`
        folder = os.path.join(args.backup_dir or bk.default_backup_dir(), bk.card_label(st))
        items = bk.list_backups(folder)
        if not 1 <= int(src) <= len(items):
            raise KN7Error("there is no back-up number %s (see `kn-songboek-cli backups`)" % src)
        src = items[int(src) - 1].path
    plan = bk.restore_plan(st, src)
    if args.dry_run:
        print("dry run, nothing written. Restoring %s would:" % src)
        for line in plan:
            print("  " + line)
        return 0
    if not args.no_backup:
        print("back-up of the current state: %s" % bk.make_backup(st, args.backup_dir, args.keep))
    n = bk.restore(st, src)
    print("restored %s (%d file operation(s))" % (src, n))
    return 0


def cmd_ls(args):
    s = _open(args)
    folders = s.folders(include_empty=args.all)
    if args.json:
        print(json.dumps([asdict(f) for f in folders], indent=2, ensure_ascii=False))
        return 0
    for f in folders:
        print("TFLD%03d  %-16s  (%d)" % (f.folder, f.name, f.used))
        for x in f.songs:
            print("    %02d  %-16s  %s" % (x.song, x.name, " ".join(x.types)))
    return 0


def cmd_search(args):
    hits = _open(args).search(args.text)
    if args.json:
        print(json.dumps([asdict(h) for h in hits], indent=2, ensure_ascii=False))
    for h in hits if not args.json else []:
        print("%02d/%02d  %s" % (h.folder, h.song, h.name))
    return 0


def cmd_check(args):
    issues = _open(args).validate()
    if args.json:
        print(json.dumps([asdict(i) for i in issues], indent=2))
    else:
        for i in issues:
            print(i)
        print("%d issue(s)" % len(issues))
        if issues:
            print("tip: `kn-songboek-cli repair --dry-run KAART` shows how the database would be rebuilt from the files")
    return 1 if any(i.severity == "error" for i in issues) else 0


def cmd_favorites(args):
    s = _open(args)
    for n, (name, items) in enumerate(s.favorites(), 1):
        if name or any(items):
            txt = ["-" if not it else ("SMF#%d" % (it[1] + 1) if it[0] == "smf" else "%d/%d" % (it[1] + 1, it[2] + 1))
                   for it in items]
            print("%02d %-16s %s" % (n, name, " ".join(txt)))
    for n, pl in enumerate(s.playlists(), 1):
        if pl:
            print("list %d: %s" % (n, " ".join("%d/%d" % p for p in pl)))
    return 0


def cmd_rename_song(args):
    s = _open(args)
    s.rename_song(args.folder, args.song, args.name)
    return _finish(args, s, "renamed")


def cmd_rename_folder(args):
    s = _open(args)
    s.rename_folder(args.folder, args.name)
    return _finish(args, s, "renamed")


def cmd_move(args, copy=False):
    s = _open(args)
    n = s.move_song(args.folder, args.song, args.to_folder, args.to_song, copy=copy)
    return _finish(args, s, "%s to TFLD%03d song %02d" % ("copied" if copy else "moved", args.to_folder, n))


def cmd_swap(args):
    s = _open(args)
    s.swap_songs(args.folder, args.a, args.b)
    return _finish(args, s, "swapped")


def cmd_move_folder(args):
    s = _open(args)
    s.move_folder(args.folder, args.to_folder)
    return _finish(args, s, "folder moved")


def cmd_insert_folder(args):
    s = _open(args)
    n = s.insert_folder(args.folder, args.before)
    return _finish(args, s, "folder %d is now folder %d" % (args.folder, n))


def cmd_delete(args):
    s = _open(args)
    s.delete_song(args.folder, args.song)
    return _finish(args, s, "deleted")


def _slot(text):
    try:
        f, s = text.split("/")
        return int(f), int(s)
    except ValueError:
        raise argparse.ArgumentTypeError("expected MAP/SONG, e.g. 3/12") from None


def cmd_set_favorite(args):
    s = _open(args)
    s.set_favorite(args.bank, args.pos, None if args.song == "-" else _slot(args.song))
    return _finish(args, s, "favourite set")


def cmd_rename_bank(args):
    s = _open(args)
    s.rename_favorite_bank(args.bank, args.name)
    return _finish(args, s, "renamed")


def cmd_songlist(args):
    s = _open(args)
    s.set_song_list(args.list, [_slot(x) for x in args.songs])
    return _finish(args, s, "song list %d set (%d songs)" % (args.list, len(args.songs)))


def cmd_duplicates(args):
    groups = dup.find_duplicates(_open(args))
    if args.json:
        print(json.dumps([dict(asdict(g), saving=g.saving) for g in groups], indent=2, ensure_ascii=False))
        return 0
    if not groups:
        print("no songs stored more than once")
        return 0
    for g in groups:
        where = ", ".join("%d/%d" % sl for sl in g.slots)
        if g.kind == "identical":
            print("%-16s  %d identical copies: %s  (%s freed by keeping one)" % (g.name, len(g.slots), where, _kb(g.saving)))
        else:
            print("%-16s  same name, different content: %s" % (g.name, where))
    print("tip: `kn-songboek-cli dedupe CARD F/S` keeps song F/S, deletes its identical copies and points "
          "favourites and song lists at it")
    return 0


def cmd_dedupe(args):
    s = _open(args)
    keep = _slot(args.keep)
    group = next((g for g in dup.find_duplicates(s) if g.kind == "identical" and keep in g.slots), None)
    if group is None:
        print("%d/%d has no identical copies" % keep)
        return 1
    n = s.merge_duplicates(keep, group.slots, args.song_list)
    return _finish(args, s, "kept %d/%d, removed %d copies" % (keep + (n,)))


def _tempo_range(text):
    try:
        lo, _, hi = text.partition("-")
        return int(lo) if lo else None, int(hi) if hi else (int(lo) if not _ else None)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a tempo or a range, e.g. 120 or 100-140") from None


def _lib_rows(lib, songs):
    return [{"name": x.name, "cards": x.cards, "where": [c.where for c in x.copies], "types": list(x.extensions),
             "tempo": x.tempo, "recorded": x.recorded, "bytes": x.size} for x in songs]


def cmd_cards(args):
    found = cd.find_cards()
    if args.json:
        print(json.dumps([asdict(c) for c in found], indent=2, ensure_ascii=False))
        return 0
    words = {cd.KN7000: "KN7000 card", cd.EMPTY: "empty", cd.OTHER: "other"}
    for c in found:
        extra = ", %d song(s)" % c.songs if c.kind == cd.KN7000 else ""
        print("%-20s %s%s  (%s)" % (c.name, words[c.kind], extra, c.path))
    if not found:
        print("no cards found")
    return 0


def _library_add(args):
    card = open_storage(args.card)
    if not args.update and not args.name:
        raise KN7Error("give the name on the card's label, or use --update")
    name = args.name
    if args.update:
        match = cd.match_library(card, args.library)
        if not match:
            raise KN7Error("this card is not in the library yet; give it a name")
        name = name or match[0][0]
        print("updating %s (%d%% of the songs in common)" % (match[0][0], round(100 * match[0][2])))
    folder = cd.archive_card(card, args.library, name, replace=args.update)
    print("copied to %s" % folder)
    return 0


def cmd_library(args):
    if args.libcmd == "add":
        return _library_add(args)
    lib = lb.Library.open(args.library)
    try:
        if args.libcmd == "copy":
            return _library_copy(args, lib)
        if args.libcmd in ("copy-folder", "copy-list"):
            return _library_copy_part(args, lib)
        if args.libcmd == "search" or args.details:
            lib.fill_details()
        if args.libcmd == "search":
            lo, hi = args.tempo if args.tempo else (None, None)
            songs = lib.search(args.text, args.card, args.recorded, lo, hi)
        else:
            songs = lib.songs
        if args.json:
            print(json.dumps(_lib_rows(lib, songs), indent=2, ensure_ascii=False))
            return 0
        for x in songs:
            extra = ""
            if x.checked:
                extra = "  %s bpm  %s" % (x.tempo or "?", "recorded" if x.recorded else "")
            print("%-16s  %s%s" % (x.name, ", ".join(c.where for c in x.copies), extra.rstrip()))
        print("%d song(s), %d card(s)%s" % (len(songs), len(lib.cards),
                                          "; skipped: " + ", ".join(p.path for p in lib.problems) if lib.problems else ""))
        return 0
    finally:
        lib.close()


def _library_copy_part(args, lib):
    label, _, n = args.source.rpartition(":")
    card = next((c for c in lib.cards if c.label == label), None)
    if card is None or not n.isdigit():
        raise KN7Error("no card %r in the library (use LABEL:NUMBER, see `library ls`)" % label)
    s = _open(args)
    if args.libcmd == "copy-folder":
        r = s.import_folder(card.session, int(n), args.to_folder)
        return _finish(args, s, "folder %s copied to folder %d (%d songs)" % (n, r["folder"], r["copied"]))
    r = s.import_song_list(card.session, int(n), args.to_list, args.to_folder, None, args.reuse)
    return _finish(args, s, "song list %s copied to song list %d (folder %s; %d copied, %d reused)"
                   % (n, r["list"], r["folder"], r["copied"], r["reused"]))


def _library_copy(args, lib):
    s = _open(args)
    done = 0
    for src in args.songs:
        label, _, slot = src.rpartition(":")
        f, so = _slot(slot)
        song = next((x for x in lib.songs if any(c.card.label == label and (c.folder, c.song) == (f, so)
                                                  for c in x.copies)), None)
        if song is None:
            raise KN7Error("no song %s in the library (use LABEL:FOLDER/SONG, see `library ls`)" % src)
        lb.copy_into(s, song, args.to_folder)
        done += 1
    return _finish(args, s, "%d song(s) copied into folder %d" % (done, args.to_folder))


def cmd_import(args):
    s = _open(args)
    other = CardSession.open(open_storage(args.other, read_only=True))
    n = s.import_from(other, args.folder, args.song, args.to_folder, args.to_song)
    return _finish(args, s, "imported to TFLD%03d song %02d" % (args.to_folder, n))


def cmd_merge(args):
    s = _open(args)
    other = CardSession.open(open_storage(args.other, read_only=True))
    done = s.merge_from(other)
    for a, b, c, d in done:
        print("%d/%d -> %d/%d" % (a, b, c, d))
    return _finish(args, s, "merged %d song(s)" % len(done))


def cmd_unpack(args):
    data = open(args.file, "rb").read()
    c = container.parse(data, os.path.splitext(args.file)[1])
    for i, p in enumerate(c.parts, 1):
        out = "%s.p%d" % (args.file, i)
        with open(out, "wb") as fh:
            fh.write(p)
        print("%s: %d bytes (%s)" % (out, len(p), c.kind))
    return 0


def cmd_format(args):
    CardSession.create(open_storage(args.card))
    print("empty music database written")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kn-songboek-cli", description="Technics SX-KN7000 SD music database tool")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--log", metavar="FILE", help="append every file operation to FILE")
    ap.add_argument("--backup-dir", metavar="DIR", help="where back-ups go (default: %s)" % bk.default_backup_dir())
    ap.add_argument("--keep", type=int, default=10, metavar="N", help="back-ups to keep per card (default 10, 0 = all)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def card(p, write=False):
        p.add_argument("card", help="SD card root, or a folder holding a copy of it")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if write:
            p.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
            p.add_argument("--no-backup", action="store_true", help="skip the automatic back-up before writing")
        return p

    card(sub.add_parser("ls", help="list folders and songs")).add_argument("--all", action="store_true")
    p = card(sub.add_parser("search", help="find songs by name")); p.add_argument("text")
    card(sub.add_parser("check", help="compare the database with the files"))
    card(sub.add_parser("favorites", help="favourite banks and song lists"))
    p = card(sub.add_parser("rename-song"), True); p.add_argument("folder", type=int); p.add_argument("song", type=int); p.add_argument("name")
    p = card(sub.add_parser("rename-folder"), True); p.add_argument("folder", type=int); p.add_argument("name")
    for name in ("move", "copy"):
        p = card(sub.add_parser(name), True)
        for a in ("folder", "song", "to_folder"):
            p.add_argument(a, type=int)
        p.add_argument("to_song", type=int, nargs="?")
    p = card(sub.add_parser("move-folder", help="put a whole folder on another number (swaps if that one is in use)"), True)
    p.add_argument("folder", type=int); p.add_argument("to_folder", type=int)
    p = card(sub.add_parser("insert-folder", help="put a folder in front of another; the folders in between shift one place"), True)
    p.add_argument("folder", type=int); p.add_argument("before", type=int, help="folder number to go in front of (100 = after the last)")
    p = card(sub.add_parser("swap", help="swap two songs in a folder"), True)
    for a in ("folder", "a", "b"):
        p.add_argument(a, type=int)
    p = card(sub.add_parser("delete"), True); p.add_argument("folder", type=int); p.add_argument("song", type=int)
    p = card(sub.add_parser("set-favorite", help="put a song on a favourite button (SONG '-' clears it)"), True)
    p.add_argument("bank", type=int, help="1..40"); p.add_argument("pos", type=int, help="1..9"); p.add_argument("song", help="MAP/SONG or -")
    p = card(sub.add_parser("rename-bank", help="rename a favourite bank"), True); p.add_argument("bank", type=int); p.add_argument("name")
    p = card(sub.add_parser("songlist", help="replace song list 1..3 with the given songs"), True)
    p.add_argument("list", type=int); p.add_argument("songs", nargs="*", help="MAP/SONG ...")
    p = card(sub.add_parser("import", help="copy one song from another card"), True)
    p.add_argument("other")
    for a in ("folder", "song", "to_folder"):
        p.add_argument(a, type=int)
    p.add_argument("to_song", type=int, nargs="?")
    p = card(sub.add_parser("merge", help="copy all songs of another card into free slots"), True); p.add_argument("other")
    card(sub.add_parser("repair", help="rebuild the database from the song files on the card"), True)
    p = card(sub.add_parser("show", help="one song: its files and the recorded sequencer song")); p.add_argument("folder", type=int); p.add_argument("song", type=int)
    p.add_argument("--picture", metavar="FILE.bmp", help="also write the home page picture to this file")
    card(sub.add_parser("sdsound", help="what the SD_SOUND folder holds (TKM names, PLM order, MIDI files)"))
    card(sub.add_parser("duplicates", help="songs stored more than once (identical files or same name)"))
    p = card(sub.add_parser("dedupe", help="keep one song, delete its identical copies, repoint favourites/lists"), True)
    p.add_argument("keep", metavar="F/S", help="the copy to keep, e.g. 3/12")
    p.add_argument("--song-list", type=int, choices=(1, 2, 3), help="also add the kept song to this song list")
    lp = sub.add_parser("library", help="all cards in one folder: list, search, copy onto a card")
    lsub = lp.add_subparsers(dest="libcmd", required=True)
    p = lsub.add_parser("ls", help="every song once, with the cards it is on")
    p.add_argument("library", help="folder holding card copies (one subfolder per card) and images")
    p.add_argument("--details", action="store_true", help="also read tempo and recording (slower)")
    p.add_argument("--json", action="store_true")
    p = lsub.add_parser("search", help="find songs by name, card, recording, tempo")
    p.add_argument("library")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--card", metavar="LABEL", help="only songs on this card (as `library ls` shows it)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--recorded", dest="recorded", action="store_const", const=True, help="only songs with a recording")
    g.add_argument("--not-recorded", dest="recorded", action="store_const", const=False)
    p.add_argument("--tempo", type=_tempo_range, metavar="BPM[-BPM]", help="e.g. 120 or 100-140")
    p.add_argument("--json", action="store_true")
    p.set_defaults(details=True)
    p = lsub.add_parser("add", help="copy a whole card into the library, named after its label")
    p.add_argument("library")
    p.add_argument("card")
    p.add_argument("name", nargs="?", help="the name on the card's label (folder name in the library)")
    p.add_argument("--update", action="store_true",
                   help="replace the library copy this card matches (old copy goes to the back-ups)")
    p = lsub.add_parser("copy", help="copy library songs onto a card (dry-run, back-up as usual)")
    p.add_argument("library")
    p.add_argument("card", help="the card to put the songs on")
    p.add_argument("to_folder", type=int)
    p.add_argument("songs", nargs="+", metavar="LABEL:F/S", help='e.g. "Kaart 01:3/5"')
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-backup", action="store_true")
    for name, what in (("copy-folder", "a whole folder (same places and name) into an empty folder"),
                       ("copy-list", "a whole song list: its songs into an empty folder, plus a song list")):
        p = lsub.add_parser(name, help="copy %s of a library card onto a card" % what)
        p.add_argument("library")
        p.add_argument("card")
        p.add_argument("source", metavar="LABEL:N", help='e.g. "Kaart 01:3" (folder 3 or song list 3)')
        p.add_argument("--to-folder", type=int, help="target folder (default: the first empty one)")
        if name == "copy-list":
            p.add_argument("--to-list", type=int, choices=(1, 2, 3), help="target song list (default: first empty)")
            p.add_argument("--reuse", action="store_true", help="do not copy songs that are already on the card")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--no-backup", action="store_true")
    p = sub.add_parser("cards", help="SD cards in the computer: KN7000, empty or other")
    p.add_argument("--json", action="store_true")
    card(sub.add_parser("info", help="card summary: songs, free space, write protection"))
    card(sub.add_parser("backup", help="zip the card's KN7000 folder to the back-up folder"))
    card(sub.add_parser("backups", help="list the back-ups of this card"))
    p = card(sub.add_parser("restore", help="put a back-up back on the card"), True)
    p.add_argument("backup", help="zip file, or its number from `kn-songboek-cli backups`")
    p = sub.add_parser("unpack", help="decode a J KD / J K\\1 file"); p.add_argument("file")
    p = sub.add_parser("format", help="write an empty database"); p.add_argument("card")
    return ap


HANDLERS = {
    "ls": cmd_ls, "search": cmd_search, "check": cmd_check, "favorites": cmd_favorites,
    "rename-song": cmd_rename_song, "rename-folder": cmd_rename_folder,
    "move": cmd_move, "copy": lambda a: cmd_move(a, copy=True), "swap": cmd_swap, "move-folder": cmd_move_folder, "insert-folder": cmd_insert_folder,
    "delete": cmd_delete, "merge": cmd_merge, "unpack": cmd_unpack, "format": cmd_format,
    "set-favorite": cmd_set_favorite, "rename-bank": cmd_rename_bank, "songlist": cmd_songlist,
    "import": cmd_import, "duplicates": cmd_duplicates, "library": cmd_library, "cards": cmd_cards, "dedupe": cmd_dedupe, "repair": cmd_repair, "info": cmd_info, "show": cmd_show, "sdsound": cmd_sdsound, "backup": cmd_backup, "backups": cmd_backups, "restore": cmd_restore,
}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.log:
        h = logging.FileHandler(args.log, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger = logging.getLogger("kn_songboek")
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
    try:
        return HANDLERS[args.cmd](args)
    except KN7Error as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except OSError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
