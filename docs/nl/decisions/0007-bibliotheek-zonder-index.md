# ADR-0007: Songbibliotheek zonder database of index

- Status: aangenomen
- Datum: 2026-11-15

## Context

Een gebruiker heeft vaak tientallen SD-kaarten (en later diskettes) met songs. Hij wil in één keer zien
welke songs hij heeft, erin zoeken en een nieuwe kaart samenstellen uit songs van verschillende kaarten.
De gebruiker wil **niet afhankelijk zijn van een database of een JSON-index**: alles wat te weten is, staat al
op de kaarten zelf (namen in `KN7000MN.INF`, tempo en opname in de songbestanden). Het programma is bedoeld
voor iemand zonder technische kennis, dus het moet werken door alleen mappen neer te zetten.

## Beslissing

- **De bibliotheek is gewoon een map.** Elke kaartkopie staat in een eigen submap (de naam van de submap is
  de naam van de kaart), of als imagebestand (`.img`, `.dmg`, `.bin`, `.ima`). Een submap telt als kaart
  als er `PRIVATE/TECHNICS/KN7000/KN7000MN.INF` in staat; submappen mogen tot drie niveaus diep genest zijn
  (bijvoorbeeld `Bibliotheek/Jan/kaart 3`).
- **Alles wordt live gelezen** bij het openen, alleen-lezen, via de gewone `Storage`-adapters. Er wordt niets
  naast de kaarten weggeschreven. Wat in een sessie berekend is (tempo, opname, vingerafdruk), blijft alleen
  in het geheugen.
- **Snel eerst, details daarna.** Namen, mappen en bestandstypen komen uit de INF en staan er meteen.
  Tempo en "opgenomen of niet" komen uit het SQT-bestand en worden op de achtergrond aangevuld.
- **Identieke songs één keer tonen.** Kandidaten zijn songs met dezelfde bestandstypen en bestandsgroottes;
  alleen die worden byte voor byte vergeleken (SHA-1). Zo hoeft niet elke song gelezen te worden.
- **Een kaart samenstellen** gebruikt de bestaande `CardSession` van de doelkaart: songs uit de bibliotheek
  worden geïmporteerd zoals bij de tweede kaart, met controle op vrije plaatsen en ruimte, undo, back-up.
- **Diskettes** komen later als extra `Storage`-adapter; de bibliotheek hoeft daarvoor niet te veranderen.

## Gevolgen

- Geen index die verouderd raakt of stuk kan gaan: kaart erbij zetten of weghalen is genoeg.
- Openen van een grote bibliotheek kost tijd (gemeten: zie `docs/how-to/bibliotheek.md`), en de details
  worden per sessie opnieuw berekend.
- Labels, sterren en eigen notities vallen af: die hebben opslag nodig die niet op een kaart past. Kan later
  terugkomen als de gebruiker dat wil (dan met een nieuw ADR).
- Maatsoort staat niet als getal in een song: die volgt uit het gekozen ritme. Tonen kan pas als de
  ritmetabel van het keyboard bekend is; tot dan zoekt de bibliotheek op naam, kaart, opname en tempo.
