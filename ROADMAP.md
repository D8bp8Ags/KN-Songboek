# Roadmap KN Songboek

Afvinken: zet `[x]` zodra een item klaar én getest is, en noteer de versie. Elk item verwijst waar mogelijk naar
de documentatie of code. Volgorde binnen een fase is de aanbevolen volgorde.

Legenda: **[x]** klaar · **[ ]** te doen · *(?)* hangt af van iets dat nog uitgezocht moet worden

---

## Fase 0: onderzoek en fundament (v0.1–v0.2) ✅

- [x] Indeling SD-kaart en bestandsnamen — `docs/nl/reference/sd-kaart.md`
- [x] `KN7000MN.INF` volledig beschreven (alle 0xD620 bytes) — `docs/nl/reference/kn7000mn-inf.md`
- [x] Songlijsten (0xBFE0), TM/EFC-containers, SQF/SEQ/ACT uitgezocht (v0.2)
- [x] Containers `J KD`, `J K\1`, `JK \0` en LZSS beschreven en geïmplementeerd — `formats/container.py`
- [x] Lagenstructuur formats → storage → core → cli/gui (ADR-0001, -0002)
- [x] Bewerkingen als commando's met undo, dry-run en uitvoeren bij opslaan (ADR-0003)
- [x] Opslaan zoals het keyboard: INF schrijven, teruglezen, BAK als tweede kopie
- [x] CLI: ls, search, check, favorites, rename-song/-folder, move, copy, swap, delete, merge, unpack, format,
      `--json`, `--dry-run`, exitcodes — `docs/nl/reference/cli.md`
- [x] GUI-schets (PySide6 + MVP-presenter): boom, hernoemen, verplaatsen, verwijderen, undo, opslaan, check
- [x] Documentatie volgens Diátaxis + arc42 + ADR's; roadmap; changelog
- [x] 25 tests (formaten, sessie, CLI, presenter, Qt-rooktest offscreen)

## Fase 1: valideren op echte kaarten (v0.3) — **hoogste prioriteit**

- [x] Kopie van een echte KN7000-kaart verzamelen *(15-11-2026: eerste kaart, 358 songs; meer kaarten blijft welkom)*
- [ ] `kn-songboek-cli ls` vergelijken met het SD LOAD-scherm van het keyboard (namen, nummers, mappen)
- [x] `kn-songboek-cli check` op de echte kaart: 0 fouten *(na correctie bestandsnaam `<ss><base>`)*
- [x] Byte-trouw: `MusicDatabase.from_bytes(x).to_bytes() == x` op de echte INF en BAK, ook na het herbouwen van de index
- [ ] Tekenset bevestigen: welke tekens kan het keyboard in namen invoeren *(echte kaart: alleen ASCII)*
- [x] Lege namen: nullen; namen zijn opgevuld met spaties, `_` of nullen door elkaar
- [x] LZSS-decoder op echte bestanden testen *(alle 2672 bestanden; ook `JK D` (EFC) en KN6000 `I KD` (deflate))*
- [x] Hele map slepen zoals in een afspeellijst (op de lijn: ertussen zetten, op een lege map: verhuizen)
- [ ] Hernoemen, verplaatsen, verwijderen op een kopie → kaart in het keyboard → laden werkt
- [ ] Favorieten en songlijsten op het keyboard controleren na een verplaatsing
- [x] Bevindingen in de referentie bijwerken (zekerheid "afgeleid" → "zeker")
- [x] Test tegen een lokale kaartkopie zonder de kaart te committen: `KN_SONGBOEK_REAL_CARD=… pytest` (`tests/test_real_card.py`)
- [x] SD_SOUND.PLM / .TKM ontleden (SD-SOUND-lijst) *(namen en volgorde; betekenis nog bevestigen met MIDI-bestanden)*
- [ ] Floppy-ondersteuning (KN7000 leest ook diskettes) *(later, op verzoek van de gebruiker)*

## Fase 2: veiligheid en robuustheid (v0.4)

- [x] Automatische back-up vóór elke save: zip van `PRIVATE/TECHNICS/KN7000` met datum, instelbaar aantal (CLI en GUI)
- [x] `restore`-opdracht: back-up terugzetten (plus `backup`, `backups`)
- [x] Herstel na een onderbroken save: `check` wijst op `repair`; terugzetten kan met `restore`
- [x] `repair`: database opnieuw opbouwen uit de bestanden op de kaart *(namen uit de vorige database; KN7000-songbestanden bevatten geen naam, KN6000-songs wel)*
- [x] Weigeren als de kaart schrijfbeveiligd is of te weinig vrije ruimte heeft (`preflight`)
- [x] Logging naar bestand (`--log`), met elke uitgevoerde bestandsoperatie
- [x] Vrije ruimte tonen (`kn-songboek-cli info`)

## Fase 3: GUI volwaardig (v0.5)

- [x] Hoofdvenster: links mappen, rechts songs (tabel), zoekbalk, statusbalk met vrije ruimte
- [x] Slepen en neerzetten: song naar andere map/plaats; volgorde binnen een map
- [x] Inline hernoemen (F2) met controle op 16 tekens en toegestane tekens (voorlopig gewone ASCII)
- [x] Meerdere songs tegelijk selecteren en verplaatsen/verwijderen
- [x] Undo/redo-geschiedenis zichtbaar *(eigen redo in `CardSession` plus geschiedenispaneel; geen QUndoStack nodig)*
- [x] Voortgangsvenster bij opslaan
- [x] Favorieten- en songlijsteditor (GUI-paneel en CLI `set-favorite`, `rename-bank`, `songlist`)
- [x] Tweede kaart naast de eerste openen en songs overslepen (CLI: `import`, `merge`)
- [x] Songlijst exporteren naar PDF en CSV
- [x] Nederlands en Engels *(eenvoudige teksttabel in `gui/i18n.py`, testbaar zonder Qt)*
- [x] Instellingen onthouden (laatste kaart, vensterstand, taal)
- [x] Back-ups terugzetten en database herstellen vanuit het menu
- [x] Bij slepen de doelmap oplichten en in de statusbalk tonen wat loslaten doet (verplaatsen of kopiëren)
- [x] Dubbele songs opsporen (zelfde song in meerdere mappen) en voorstellen ze te vervangen door één song
      plus een favoriet of songlijst *(scheelt ruimte en slots; aanpassingen gelden dan overal)*

## Fase 4: inhoud van songs (v0.6–v0.8)

- [x] SQT uitlezen: songnaam, sporen, tempo, tellen, noten *(CLI `show`, `CardSession.song_details`)*
- [ ] SQT → Standard MIDI File exporteren *(gewenst door de gebruiker, later)*
- [ ] CMP-begeleidingspatronen → MIDI exporteren
- [x] PMT: panel memories tonen *(banken, namen, tempo; ritmenaam nog niet)*
- [x] CMP: styles tonen *(namen en variatienamen)*
- [ ] CMP: styles los exporteren/importeren tussen songs
- [x] MSP: pads tonen *(banken en eigen pads; namen van vaste pads nog niet)*
- [x] TM: eigen klanken tonen
- [x] HMP: homepage-afbeelding tonen *(niet getest op een echt bestand)*
- [ ] HMP: homepage-afbeelding vervangen
- [ ] AST/CST: custom styles beheren in `CUSTOM\`
- [x] Encoder die byte-identiek is aan Technics (Okumura-LZSS, N=8192, F=10), zelf geschreven (ADR-0004) *(alle bestanden van een echte kaart gelijk)*

## Fase 4b: songbibliotheek (ADR-0007)

Doel: alle kaarten van een gebruiker in één map, één doorzoekbare lijst, en daaruit een nieuwe kaart samenstellen.
Geen database of index: alles wordt live van de kaarten gelezen.

- [x] Bibliotheekmap inlezen: elke submap met `KN7000MN.INF` of elk imagebestand is een kaart (tot 3 niveaus diep)
- [x] Eén lijst van alle songs met kaart, map/plaats, bestandstypen
- [x] Identieke songs één keer tonen met "op kaart 3, 7, 12" (eerst op grootte, dan byte voor byte)
- [x] Tempo en "opgenomen of niet" uit het SQT-bestand, op de achtergrond aangevuld
- [x] Zoeken en filteren: naam, kaart, opgenomen ja/nee, tempo van-tot
- [x] Nieuwe kaart samenstellen: slepen van de bibliotheek (links) naar een lege of bestaande kaart (rechts),
      met controle op vrije plaatsen en ruimte; daarna gewoon opslaan met back-up
- [x] Bibliotheek als startscherm van de app; eenvoudig genoeg voor iemand zonder technische kennis
- [x] Een hele map of songlijst van een kaart in één keer kopiëren (map = setlist; dubbele songs mogen)
- [x] CLI: `library ls`, `library search`, `library copy`
- [x] Maatsoort tonen: uit het ritme in de panel memory (ingebouwde ritmetabel of de eigen CMP van de song);
      CLI `show`, kolom "Maat" in de bibliotheek *(CUSTOM-styles staan niet op de kaart: maat onbekend)*
- [ ] Ritmenaam tonen in de bibliotheek en zoeken/filteren op maat (bijv. alle walsen)
- [ ] Diskettes in de bibliotheek (na diskette-ondersteuning in fase 5)

## Fase 4c: eenvoudige werkwijze (ADR-0008)

Doel: iemand zonder computerervaring kan zonder uitleg een kaart ordenen, een nieuwe kaart maken en een kaart
bewaren.

- [x] Kern: aangesloten kaarten vinden en herkennen (KN7000, leeg, anders), kaart naar bibliotheek kopiëren,
      samengestelde kaart op een kaart zetten (met waarschuwing en back-up), kaart uitwerpen
- [x] Startscherm "Wat wil je doen?" met drie taken, uitbreidbaar met diskettes
- [x] Ordenen: gele conceptbalk "N wijzigingen nog niet op de kaart", knop **Op kaart zetten**, daarna
      "Klaar, je kunt de kaart eruit halen"
- [x] Samenstellen: bibliotheek links, nieuwe kaart rechts, meter hoe vol de kaart is
- [x] Kaart bewaren in de bibliotheek met één klik; naam = etiket van de kaart
- [x] Kaart die al in de bibliotheek staat herkennen (op inhoud) en vragen "Bijwerken?"
- [x] Zoeken toont per song op welke kaart en in welke map hij staat
- [x] Menu **Meer…** voor favorieten, songlijsten, dubbele songs, inhoud, images, back-ups, controleren;
      zijpanelen standaard dicht, geen technische woorden
- [x] Handleiding en schermafbeeldingen bijwerken

## Fase 5: meer bronnen en distributie (v0.9–v1.0)

- [x] FAT-image direct lezen/schrijven (`FatImageStorage`, FAT12/16/32, met of zonder partitietabel), zonder kaart te koppelen
- [ ] Diskettes (KN7000-floppy, FAT12) lezen en songs naar SD overzetten
- [ ] HD-AE5000-back-ups importeren (formaat staat in openbare documentatie)
- [ ] SD-SOUND (SMF) beheren: map vaststellen, lijst van 999, afspeellijsten
- [ ] Installeerbare pakketten: PyPI, Windows-installer (PyInstaller), macOS-app
- [x] Alle controles in één opdracht: `tools/check.py` (ruff, mypy op formats/storage, tests) *(lokaal; geen GitHub)*
- [x] Privacycontrole vóór elke push: `tools/privacy_check.py --install` (pre-push hook)
- [ ] CI op GitHub Actions: tests op Windows/macOS/Linux *(pas als het project op GitHub komt)*
- [x] Documentatiewebsite (MkDocs Material) uit `docs/` *(`mkdocs build` → `site/`, werkt ook zonder webserver)*
- [ ] v1.0: alle kaartfuncties compleet + inhoudsweergave

## Doorlopend

- [ ] Elke wijziging: tests + docs bijwerken + CHANGELOG-regel
- [ ] Nieuwe ontdekkingen over het formaat: bron en zekerheid in de referentie
- [ ] Nieuwe beslissingen: ADR toevoegen
