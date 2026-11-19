# Referentie: opdrachtregel

```
kn-songboek-cli [--log BESTAND] [--backup-dir MAP] [--keep N] <opdracht> <kaart> [argumenten] [--json] [--dry-run] [--no-backup]
python -m kn_songboek …            # zonder installatie, vanuit src/
```

`<kaart>` is de hoofdmap van een SD-kaart of van een kopie ervan. Mappen tellen van 1 tot 99, songs van 1 tot 20,
net als op het scherm van het keyboard.

| Opdracht | Doet | Schrijft? |
|----------|------|:--------:|
| `ls KAART [--all]` | mappen en songs tonen | nee |
| `search KAART TEKST` | songs zoeken op naam | nee |
| `check KAART` | database tegen bestanden controleren | nee |
| `favorites KAART` | favorietenbanken en songlijsten tonen | nee |
| `rename-song KAART M S NAAM` | song hernoemen (max. 16 tekens) | ja |
| `rename-folder KAART M NAAM` | map hernoemen | ja |
| `move KAART M S NAAR_M [NAAR_S]` | song verplaatsen (zonder NAAR_S: eerste vrije plaats) | ja |
| `copy KAART M S NAAR_M [NAAR_S]` | song kopiëren | ja |
| `swap KAART M A B` | twee plaatsen in een map omwisselen | ja |
| `move-folder KAART M N` | hele map (naam en 20 plaatsen) naar nummer N; is N in gebruik, dan ruilen de mappen | ja |
| `insert-folder KAART M N` | map M vóór map N zetten (100 = achteraan); de mappen ertussen schuiven één plaats op | ja |
| `delete KAART M S` | song en zijn bestanden verwijderen | ja |
| `set-favorite KAART BANK POS M/S` | song op favorietknop POS (1-9) van BANK (1-40); `-` wist hem | ja |
| `rename-bank KAART BANK NAAM` | favorietenbank hernoemen | ja |
| `songlist KAART N [M/S …]` | songlijst N (1-3) vervangen door deze songs (max. 20) | ja |
| `import KAART ANDERE_KAART M S NAAR_M [NAAR_S]` | één song van een andere kaart kopiëren | ja |
| `merge KAART ANDERE_KAART` | alle songs van een andere kaart toevoegen in vrije plaatsen | ja |
| `repair KAART` | database opnieuw opbouwen uit de songbestanden (namen uit de vorige database) | ja |
| `show KAART M S [--json] [--picture F.bmp]` | één song: bestanden met grootte, ritme en maatsoort, de opgenomen sequencersong (sporen, tempo, tellen, noten), panel memories (banken, namen, tempo), composer-stijlen, pads, eigen klanken; `--picture` schrijft de homepage-afbeelding weg | nee |
| `sdsound KAART [--json]` | de map SD_SOUND: de 16 namen uit SD_SOUND.TKM, de volgorde uit SD_SOUND.PLM en de MIDI-bestanden | nee |
| `duplicates KAART [--json]` | songs die meer dan eens op de kaart staan (identieke bestanden, of zelfde naam met andere inhoud) | nee |
| `dedupe KAART M/S [--song-list N]` | M/S houden, de identieke kopieën verwijderen; favorieten en songlijsten wijzen daarna naar M/S | ja |
| `cards [--json]` | de kaarten die nu in de computer zitten: KN7000-kaart (met aantal songs), leeg of iets anders | nee |
| `library add MAP KAART [NAAM] [--update]` | een hele kaart in de bibliotheek bewaren onder NAAM (het etiket); `--update` vervangt de kopie die bij deze kaart hoort (herkend aan de songs; de oude kopie gaat naar de back-ups) | nee (alleen in de bibliotheek) |
| `library ls MAP [--details]` | alle songs van alle kaarten in MAP, identieke één keer, met waar ze staan | nee |
| `library search MAP [TEKST] [--card LABEL] [--recorded\|--not-recorded] [--tempo 100-140]` | zoeken in de bibliotheek | nee |
| `library copy MAP KAART NAAR_M LABEL:M/S …` | songs uit de bibliotheek op een kaart zetten (bijv. `"Kaart 01:3/5"`) | ja |
| `library copy-folder MAP KAART LABEL:M [--to-folder N]` | een hele map van een bibliotheekkaart naar een lege map | ja |
| `library copy-list MAP KAART LABEL:N [--to-list N] [--to-folder N] [--reuse]` | een songlijst: de songs in volgorde naar een lege map, plus een songlijst | ja |
| `info KAART` | aantal songs, vrije ruimte, schrijfbeveiliging, map met back-ups | nee |
| `backup KAART` | back-up maken (zip van `PRIVATE/TECHNICS/KN7000`) | nee (alleen in de back-upmap) |
| `backups KAART` | back-ups van deze kaart tonen, nieuwste eerst | nee |
| `restore KAART ZIP\|NR` | back-up terugzetten (eerst een back-up van de huidige stand) | ja |
| `unpack BESTAND` | `J KD`/`J K\1`-bestand uitpakken naar `BESTAND.p1` (`.p2`) | nee (alleen naast het bestand) |
| `format KAART` | lege database aanmaken | ja |

**Opties**

- `--json`: uitvoer als JSON, voor scripts.
- `--dry-run`: toont welke bestanden verplaatst, gekopieerd of verwijderd zouden worden, schrijft niets.
- `--no-backup`: geen automatische back-up vóór het schrijven.
- `--log BESTAND`: elke bestandsoperatie met tijd toevoegen aan BESTAND (vóór de opdracht zetten).
- `--backup-dir MAP`, `--keep N`: waar back-ups komen en hoeveel er per kaart blijven (standaard 10).
- `--version`, `-h/--help`.

**Exitcodes**: 0 = gelukt; 1 = `check` vond fouten; 2 = fout (melding op stderr).

**Opslaan**: eerst controleren (schrijfbeveiliging, vrije ruimte), dan een back-up, dan de bestandsoperaties,
dan de database (INF, teruglezen, BAK), net als het keyboard. Zie [back-ups](../how-to/back-up-en-herstel.md).
