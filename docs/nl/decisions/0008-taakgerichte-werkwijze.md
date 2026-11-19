# ADR-0008: Taakgerichte werkwijze voor gebruikers zonder computerervaring

- Status: aangenomen
- Datum: 2026-11-15

## Context

De belangrijkste gebruiker speelt op een KN7000, heeft weinig computerervaring, gebruikt een paar SD-kaarten
in het keyboard en heeft daarnaast veel diskettes met muziek gekocht. Hij gebruikt de 99 mappen zelf als
setlists, dus dubbele songs zijn gewoon.

Het programma kon al veel (bibliotheek, tweede kaart, favorieten, songlijsten, inhoud, back-ups, images),
maar liet alles tegelijk zien: een werkbalk met acht knoppen, drie zijpanelen, technische woorden als
"image" en "database". Wie niet weet wat een map of een back-up is, weet niet waar hij moet beginnen, en
"Opslaan" zegt niet dat er iets op de kaart gebeurt.

## Beslissing

**Het programma begint met de vraag "Wat wil je doen?"** en drie grote knoppen. Elke knop is een taak, niet
een functie:

1. **Kaart bekijken en ordenen**: het programma zoekt zelf de KN7000-kaart die in de computer zit. Is er
   één, dan gaat hij open; zijn er meer, dan kiest de gebruiker uit de namen; is er geen, dan zegt het
   programma dat hij de kaart erin moet doen (en kan hij alsnog zelf een map kiezen).
2. **Nieuwe kaart samenstellen**: links de bibliotheek, rechts een nieuwe lege kaart in het geheugen. Songs
   of hele mappen sleep je naar rechts; een meter toont hoe vol de kaart is. **Op kaart zetten** vraagt welke
   SD-kaart het moet worden en waarschuwt als daar al songs op staan (die worden eerst bewaard in een back-up).
3. **Kaart bewaren in bibliotheek**: één klik kopieert de kaart die in de computer zit naar de
   bibliotheekmap, onder een naam die de gebruiker kiest. Is er nog geen bibliotheek, dan stelt het programma
   eenmalig een map voor (`Documenten/KN7000 Bibliotheek`).

**De kaartjes blijven leidend, de bibliotheek is een spiegel** (ADR-0007 blijft gelden: één submap per
kaart, geen database):

- **Naam = etiket.** Bij bewaren vraagt het programma "Wat staat er op het etiket van deze kaart?" en gebruikt
  dat als naam van de map in de bibliotheek ("Kaart bruiloften").
- **Bijwerken in plaats van bijhouden.** Zit er een kaart in die al in de bibliotheek staat, dan vraagt het
  programma "Kaart bruiloften bijwerken in de bibliotheek?". Herkennen gebeurt zonder index of merkbestand: een
  kaart hoort bij een bibliotheekmap als de meeste songs (naam, bestandstypen en groottes uit de INF) gelijk
  zijn; bij twijfel wint de map met de meeste overeenkomsten, en de gebruiker bevestigt altijd. Bijwerken
  vervangt de kopie; de oude kopie gaat eerst naar de back-ups.
- **"Waar staat dit nummer?"** Zoeken toont bij elke song op welke kaart (later: welke diskette) en in welke
  map/plaats hij staat, zodat de gebruiker het fysieke kaartje kan pakken.
- **Diskettes als doosjes.** Een diskette (of een stapel) wordt later ook een submap in de bibliotheek, op
  dezelfde manier als een kaart: één manier van denken voor alles.

De taken zijn een lijst in de code (titel, uitleg, actie), zodat een vierde taak **Diskettes overzetten**
later toegevoegd kan worden zonder het scherm opnieuw te ontwerpen.

**Wijzigingen zijn een concept.** Zolang er iets veranderd is, staat er een gele balk: "3 wijzigingen nog niet
op de kaart" met de knop **Op kaart zetten**. Die doet wat eerst "Opslaan" heette: controleren, back-up maken,
schrijven, en daarna "Klaar, je kunt de kaart eruit halen" (op de Mac wordt de kaart meteen netjes
uitgeworpen). Cmd/Ctrl+Z werkt altijd. Terug naar het startscherm met wijzigingen vraagt: op kaart zetten,
weggooien of annuleren.

**Minder op het hoofdscherm, niets weg.** Favorieten en songlijsten, dubbele songs, inhoud van een song,
images, back-up terugzetten, kaart controleren en herstellen, tweede kaart, PDF-lijst en taal staan onder
**Meer…**. De zijpanelen (geschiedenis, favorieten, tweede kaart) zijn standaard dicht. Op het scherm staan
geen woorden als image, database, INF of LSW.

**De logica zit in de kern, niet in het scherm** (ADR-0001, ADR-0005): `core/cards.py` vindt aangesloten
kaarten (macOS `/Volumes`, Linux `/media` en `/run/media`, Windows-stationsletters), herkent of een kaart
een KN7000-kaart, leeg of iets anders is, kopieert een kaart naar de bibliotheek, zet een in het geheugen
samengestelde kaart op een echte kaart, en werpt een kaart uit. De CLI kan dezelfde functies gebruiken.

## Gevolgen

- Een nieuwe gebruiker ziet drie keuzes in plaats van een werkbalk; de bestaande functies blijven bereikbaar.
- "Op kaart zetten" van een nieuwe kaart vervangt de KN7000-songs op de gekozen kaart. Daarom altijd eerst een
  waarschuwing en een back-up; andere bestanden op de kaart blijven staan.
- Kaartdetectie hangt af van het besturingssysteem. Tests gebruiken een vervangende map via de omgevings-
  variabele `KN_SONGBOEK_VOLUMES`.
- De handleiding beschrijft de drie taken in plaats van de menu's.

## Aanvulling: de schermen na het startscherm (2026-11-15)

Na een UX-voorstel (hedendaagse patronen uit Apple HIG, Material en NN/g) zijn de vervolgschermen op dezelfde
manier eenvoudiger gemaakt. Technische woorden (bestandstypen, paden) mogen blijven staan.

- **Groot en rustig**: letters 15 pt, regels en knoppen van ongeveer 34 punten (`gui/style.py`); lege mappen
  ingeklapt achter één regel, lege plaatsen als lichte stippelvakjes; bovenin de naam van de kaart en een meter
  voor de 99 × 20 plaatsen.
- **Klikken in plaats van slepen**: elke sleepactie heeft ook een knop of menu (Verplaatsen naar…, + Zet in map,
  Gekozen song op deze knop…). Slepen blijft werken.
- **Ongedaan maken in plaats van "weet je het zeker?"**: na een bewerking een balkje met **Ongedaan maken**;
  weghalen vraagt niets meer, want alles is een concept tot **Op kaart zetten**.
- **Stappen voor de spannende taken**: Op kaart zetten en Kaart bewaren lopen in één venster met genummerde
  stappen en eindigen met een groot vinkje. De presenter is niet veranderd: het venster vangt dezelfde
  vragen (`ask`, `choose`, `confirm`, `ask_text`, `show_done`) op zolang de stappen open zijn.
- **Meer…** is een pagina met tegels; de eerste keer een tip per scherm; **?** toont het hoofdstuk van de
  handleiding over dat scherm.
