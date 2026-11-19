# Referentie: Python-API

Voor scripts en voor wie een eigen front-end bouwt. Alle nummers zijn 1-based.

```python
from kn_songboek.core import CardSession
from kn_songboek.storage import DirectoryStorage

s = CardSession.open(DirectoryStorage("/Volumes/KN7000"))
for f in s.folders():
    print(f.folder, f.name, [x.name for x in f.songs])

s.rename_song(1, 2, "MY WAY")
s.move_song(1, 2, to_folder=5)          # -> nieuw songnummer
print(s.pending)                        # geplande bestandsoperaties
s.undo()                                # laatste stap terug
s.save()                                # pas nu verandert er iets op de kaart
```

## `CardSession`

| Methode | Beschrijving |
|---------|--------------|
| `open(storage)` / `create(storage)` | kaart openen (INF, anders BAK) / lege database aanmaken |
| `folders(include_empty=False)` | lijst `FolderView(folder, name, songs)` |
| `song(m, s)`, `search(tekst)` | `SongView(folder, song, name, types, files)` |
| `favorites()`, `playlists()` | favorietenbanken en de 3 songlijsten |
| `validate()` | lijst `Issue(severity, message, folder, song)` |
| `rename_song`, `rename_folder`, `move_song`, `swap_songs`, `delete_song`, `import_song`, `merge_from` | bewerkingen; veranderen alleen het geheugen |
| `pending` | geplande `FileOp`s |
| `undo()`, `redo()`, `history()`, `redo_history()`, `dirty`, `can_redo` | ongedaan maken en opnieuw doen |
| `on_change(callback)` | melding na elke wijziging (voor een GUI) |
| `preflight()`, `bytes_needed()` | schrijfbeveiliging en vrije ruimte controleren (gebeurt ook in `save`) |
| `save(progress=None)` | alles uitvoeren en database schrijven; logt naar logger `kn_songboek` |

Fouten zijn subklassen van `KN7Error` (`NoDatabase`, `SlotError`, `NothingToUndo`).

## Opslag (`kn_songboek.storage`)

`DirectoryStorage(pad)` voor een gekoppelde kaart of een kopie; `FatImageStorage(bestand, read_only=False)` voor
een kaartimage (FAT12/16/32, met of zonder partitietabel); `MemoryStorage()` voor tests. `open_storage(pad)`
kiest zelf: een bestand wordt een image, een map een `DirectoryStorage`. Een eigen opslag hoeft alleen het `Storage`-protocol te implementeren: `read`, `write`, `exists`,
`listdir`, `move`, `copy`, `remove`, `describe`, `isdir`, `size`, `free_bytes`, `writable`.

## Back-ups (`kn_songboek.core.backup`)

| Functie | Doet |
|---------|------|
| `make_backup(storage, backup_dir=None, keep=10)` | zip van `PRIVATE/TECHNICS/KN7000`, geeft het pad terug |
| `list_backups(map)` | `BackupInfo`s van één kaart, nieuwste eerst |
| `restore_plan(storage, zip)` / `restore(storage, zip)` | terugzetten (eerst bekijken / uitvoeren) |
| `default_backup_dir()` | standaardmap per besturingssysteem, of `$KN_SONGBOEK_BACKUP_DIR` |

## Formaten (`kn_songboek.formats`)

`inf.MusicDatabase.from_bytes/to_bytes`, `container.parse`, `container.lzss_decode/lzss_encode`,
`layout.song_path`. Deze laag doet geen bestandstoegang.
