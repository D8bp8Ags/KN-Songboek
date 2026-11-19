# ADR-0004: licentie en gebruik van bronnen

- Status: voorgesteld (MIT), definitieve keuze bij de eigenaar
- Datum: 2026-11-15, bijgewerkt 2026-11-15

## Context
Het formaat is gevonden met behulp van openbare documentatie onder GPL-3, met hulpscripts onder GPL-3.
Code daaruit overnemen zou KN Songboek verplichten tot GPL-3. Kennis van een formaat
(offsets, velden, algoritmes) is geen code: die mogen we vrij gebruiken om zelf code te schrijven.

## Beslissing
KN Songboek schrijft **alle** formaatcode zelf, op basis van de beschrijving van het formaat en eigen metingen op
echte kaarten. Er wordt geen GPL-code gekopieerd of vertaald. Dat geldt ook voor de lastige
onderdelen:

- **LZSS-encoder die byte-identiek is aan Technics**: zelf geschreven naar de beschrijving (Okumura-LZSS met
  N=8192, F=10, startpositie 0x1FF6). Okumura's LZSS.C uit 1989 is zelf public domain, dus ook die als
  referentie gebruiken legt geen licentie op.
- **SQT-parser** (en PMT, CMP, MSP): zelf geschreven naar de veldbeschrijvingen in de documentatie en
  gecontroleerd op echte bestanden.

Daarmee blijft de licentiekeuze vrij. Voorstel: KN Songboek onder **MIT** uitbrengen.

## Gevolgen
- Iets meer werk dan kopiëren, maar geen licentieverplichtingen en volledige controle over de code.
- Wie bijdraagt, plakt geen code uit de GPL-projecten; in reviews letten we daarop.
- Alleen als later toch GPL-code nodig blijkt, moet het hele project GPL-3 worden. Dat is nu niet voorzien.
