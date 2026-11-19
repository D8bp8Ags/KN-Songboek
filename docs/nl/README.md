# Documentatie KN Songboek

Deze documentatie is ingedeeld volgens **Diátaxis**: vier soorten teksten, elk voor een ander moment.
De architectuurtekst volgt een ingekorte **arc42**-indeling, en beslissingen staan als **ADR**'s in
`decisions/`. Waarom deze keuze is gemaakt staat in [explanation/methodiek.md](explanation/methodiek.md).

**Gewoon het programma gebruiken?** Lees de [Handleiding](handleiding.md) (in English: [manual](../en/manual.md)): zonder technische kennis, met
afbeeldingen. De rest van deze documentatie is voor wie meer wil weten of eraan werkt.

| Ik wil… | Soort | Document |
|---------|-------|----------|
| het programma voor het eerst gebruiken | Tutorial | [tutorials/eerste-stappen.md](tutorials/eerste-stappen.md) |
| een concrete taak uitvoeren | How-to | [how-to/](how-to/songs-beheren.md) |
| exact opzoeken hoe iets in elkaar zit | Referentie | [reference/](reference/cli.md) |
| begrijpen waarom het zo werkt | Uitleg | [explanation/](explanation/architectuur.md) |

## Inhoud

**Tutorials**
- [Eerste stappen: een kaart veilig bekijken en één song hernoemen](tutorials/eerste-stappen.md)

**How-to's**
- [Een SD-kaart veilig kopiëren voordat je iets wijzigt](how-to/kaart-veilig-kopieren.md)
- [Songs hernoemen, verplaatsen, ordenen en verwijderen](how-to/songs-beheren.md)
- [Twee kaarten samenvoegen](how-to/kaarten-samenvoegen.md)
- [Back-ups maken en terugzetten](how-to/back-up-en-herstel.md)
- [Werken met de grafische versie](how-to/grafische-versie.md)
- [Werken met een kaartimage](how-to/kaartimage.md)
- [Al je kaarten in één bibliotheek](how-to/bibliotheek.md)

**Referentie**
- [Indeling van de SD-kaart en bestandsnamen](reference/sd-kaart.md)
- [KN7000MN.INF byte voor byte](reference/kn7000mn-inf.md)
- [Songbestanden en containers (J KD, LZSS, J K\1)](reference/songbestanden.md)
- [Opdrachtregel (CLI)](reference/cli.md)
- [Python-API (CardSession)](reference/api.md)

**Uitleg**
- [Architectuur en structuurplan (arc42-light)](explanation/architectuur.md)
- [Hoe het formaat is achterhaald, met bewijs per veld](explanation/reverse-engineering.md)
- [Gekozen methodiek: documentatie en CLI+GUI](explanation/methodiek.md)

**Beslissingen (ADR)**: [decisions/](decisions/README.md)

**Planning**: [../ROADMAP.md](../../ROADMAP.md) · **Wijzigingen**: [../CHANGELOG.md](../../CHANGELOG.md)

## Afspraken voor wie documentatie schrijft

- Eén document = één soort (Diátaxis). Een how-to legt niet uit waarom; daarvoor link je naar Uitleg.
- Elke bewering over het formaat noemt zijn bron (firmware-adres of document) en zijn zekerheid:
  **zeker** (in code gelezen), **afgeleid** (volgt uit code, niet getest op een keyboard), **open**.
- Documentatie staat naast de code in git en wordt in dezelfde wijziging bijgewerkt (docs-as-code).
- Taal: Nederlands voor documentatie, Engels voor code en codecommentaar.
