# Architectuur en structuurplan

*Indeling: ingekorte arc42 (secties 1–5, 8–12). Beslissingen staan uitgewerkt in [../decisions/](../decisions/README.md).*

## 1. Doel

Een modern, open programma om de muziekdatabase van een Technics SX-KN7000-SD-kaart
te bekijken en veilig te bewerken, eerst via de opdrachtregel, later via een grafische schil. Daarna de inhoud van
songs (SQT, PMT, CMP …) leesbaar en exporteerbaar maken.

**Kwaliteitsdoelen, in volgorde**

1. **Nooit een kaart beschadigen.** Niets schrijven voordat alles gepland is; back-up; teruglezen.
2. **Juistheid.** Elk veld heeft een bron in de firmware; tests op echte kaarten.
3. **Eén kern, meerdere schillen.** CLI en GUI doen precies hetzelfde, omdat ze dezelfde code aanroepen.
4. **Onderhoudbaar en testbaar** zonder keyboard en zonder scherm.

## 2. Randvoorwaarden

- Python 3.9+; de kern gebruikt alleen de standaardbibliotheek.
- GUI: PySide6 (Qt), optioneel te installeren (`pip install kn-songboek[gui]`).
- Windows, macOS en Linux. FAT is hoofdletterongevoelig, het bestandssysteem van de computer soms niet.
- Bron van kennis: openbare documentatie van de KN7000-firmware; wij kopiëren geen code (ADR-0004).

## 3. Context

```
  gebruiker ──► CLI / GUI ──► KN Songboek ──► SD-kaart (gekoppeld) of map met kopie of kaartimage
                                    └──► bibliotheek: een map met veel kaartkopieën (alleen lezen)
                                    └──► export: zip, MIDI, tekst
  keyboard ◄── SD-kaart
```

## 4. Oplossingsstrategie

**Ports and adapters** (hexagonale architectuur) met een **functionele kern**:

- de *formaten* zijn pure functies: bytes ↔ objecten;
- de *kern* (`CardSession`) bevat alle use cases en kent alleen een `Storage`-interface;
- *adapters* aan de buitenkant: opslag (map, geheugen, FAT-image) en front-ends (CLI, GUI);
- elke bewerking is een **commando** dat de database in het geheugen wijzigt en bestandsoperaties plant;
  `save()` voert ze in één keer uit. Dat geeft gratis *dry-run*, *undo* en een voortgangsbalk.

## 5. Bouwstenen (structuurplan)

```
src/kn_songboek/
├── formats/            laag 1: pure formaten, geen I/O
│   ├── inf.py          KN7000MN.INF  (MusicDatabase, Folder, Song, FavoriteBank)
│   ├── container.py    J KD / J K\1 / JK \0, LZSS
│   └── layout.py       paden en bestandsnamen op de kaart
├── storage/            laag 2: waar de bytes staan (port + adapters)
│   ├── base.py         Storage-protocol
│   ├── directory.py    gekoppelde kaart of map
│   └── memory.py       in het geheugen (tests, voorbeeld)
├── core/               laag 3: use cases
│   ├── session.py      CardSession: open, query, commando's, undo, save
│   ├── library.py      Library: alle kaarten in een map, live gelezen, zoeken, identieke songs (ADR-0007)
│   ├── views.py        FolderView, SongView, Issue (alleen-lezen, 1-based)
│   └── errors.py       KN7Error en subklassen
├── cli/main.py         front-end 1: argparse, --json, --dry-run, exitcodes
└── gui/                front-end 2
    ├── presenter.py    MVP-presenter, zonder Qt, getest
    ├── presenter_song.py  het deel van de presenter over één song (paneel, inhoud, feiten)
    ├── qt_app.py       PySide6-hoofdvenster (MainWindow): alleen opmaak en koppeling
    ├── widgets.py      lijsten, tabellen, bibliotheekpaneel, taakknoppen, voortgangsbalk
    ├── dialogs.py      vensters over het hoofdvenster (stappen, export, Meer…, back-ups, …)
    └── info_panel.py   het paneel met alles over één song
tests/                  per laag; GUI-presenter met een nep-view, Qt-rooktest offscreen
docs/                   nl/ (Nederlands: handleiding, Diátaxis, arc42, ADR's, img/), en/ (English manual, img/)
```

**Afhankelijkheidsregel**: een buitenste laag mag een binnenste importeren, nooit andersom.
`formats` kent niets; `core` kent `formats` en het `Storage`-protocol; `cli` en `gui` kennen alleen `core`
(en `storage` om een kaart te openen). Zo kan de GUI later vervangen worden (bv. door een webinterface)
zonder de kern te raken.

**Beoordeling van de oude structuur (v0.1)**: één `card.py` mengde bestandsoperaties, databasewijzigingen en
opslaan; bewerkingen schreven direct naar de kaart; de CLI zat in hetzelfde pakket en printte zelf; er was geen
undo, geen dry-run en geen manier om een GUI te laten meeluisteren. Dat is in v0.2 opgelost met de lagen
hierboven.

## 6. Runtime: een song verplaatsen

1. Front-end roept `move_song(1, 2, 5)` aan.
2. Kern neemt een snapshot (voor undo), zoekt een vrije plaats, plant `move`-operaties per bestand,
   wijzigt de database in het geheugen, past favorieten en songlijsten aan, meldt `on_change`.
3. GUI ververst via de presenter; CLI met `--dry-run` toont `pending` en stopt.
4. `save()`: bestandsoperaties uitvoeren (met voortgang), oude INF als BAK, nieuwe INF schrijven,
   teruglezen, BAK = nieuwe kopie.

## 7. Runtime: de bibliotheek openen en een kaart samenstellen

1. `Library.open(map)` zoekt kaarten: submappen met `KN7000MN.INF` en imagebestanden. Elke kaart wordt
   alleen-lezen geopend met de gewone `Storage`-adapters; de songlijst komt uit haar eigen INF. Geen index.
2. De songs komen meteen in één lijst. Identieke songs worden samengevoegd: eerst op naam-onafhankelijke
   kandidaten (zelfde bestandstypen en groottes), dan byte voor byte vergeleken.
3. Op de achtergrond leest `Library.details()` per song het SQT-bestand: tempo (panel memory in het
   songrecord, tag `0x42`) en of er een opname in staat. De GUI vult de kolommen aan zodra ze bekend zijn.
4. Rechts staat een gewone `CardSession` (lege of bestaande kaart). Slepen uit de bibliotheek roept
   `import_song` aan met de kaart van herkomst als bron: dezelfde controles, undo, back-up en `save()` als altijd.

## 8. Concepten

- **Nummering**: intern 0-based (zoals de firmware), in de API en op het scherm 1-based (zoals het keyboard).
- **Byte-trouw**: niet-gewijzigde records worden byte voor byte teruggeschreven.
- **Hoofdletters**: kaartpaden zijn hoofdletterongevoelig; `DirectoryStorage` zoekt de echte schrijfwijze.
- **Atomisch schrijven**: eerst naar `.tmp`, `fsync`, dan hernoemen.
- **Foutafhandeling**: de kern gooit `KN7Error`; front-ends tonen de melding, nooit een stacktrace.

## 9. Beslissingen

Zie [../decisions/](../decisions/README.md): src-layout, ports & adapters, commando's met uitgestelde uitvoering,
PySide6 met MVP, licentie, Diátaxis/arc42, bibliotheek zonder index.

## 10. Kwaliteit

| Scenario | Maatregel |
|----------|-----------|
| Stroom valt weg tijdens save | atomisch schrijven; BAK blijft tot de nieuwe INF is teruggelezen |
| Gebruiker vergist zich | undo; dry-run; bevestiging in GUI; back-up (roadmap) |
| Onbekend veld in echte data | byte-trouwe round-trip; `check` meldt afwijkingen |
| Regressie | tests per laag, CI (roadmap) |

## 11. Risico's

- **Nog niet getest op een echte kaart.** Hoogste prioriteit in de roadmap.
- De LZSS-decoder is alleen getest op eigen data.
- Tekenset van namen (Latin-1 aangenomen) en gedrag bij lege namen nog te bevestigen.
- Volgorde van gelijke namen in de alfabetische index kan afwijken; het keyboard herstelt dit zelf.

## 12. Begrippen

| Term | Betekenis |
|------|-----------|
| INF | `KN7000MN.INF`, de muziekdatabase |
| map / folder | `TFLDnnn`, 1..99 |
| plaats / slot | positie van een song in een map, 1..20 |
| base | 6-tekens naamdeel van de songbestanden |
| typemasker | 14 bits: welke bestanden een song heeft |
| Technics-song | een groep bestanden (SQT, PMT, …) met één naam |
| SD-SOUND | Standard MIDI Files op de kaart |
