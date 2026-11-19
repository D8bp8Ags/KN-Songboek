# ADR-0006: Diátaxis, arc42 en ADR voor documentatie

- Status: aangenomen
- Datum: 2026-11-15

## Context
Documentatie moet zowel beginners (keyboardspelers) als ontwikkelaars (formaat, code) bedienen.

## Beslissing
`docs/` volgens Diátaxis (tutorials, how-to, referentie, uitleg); architectuur volgens ingekorte arc42; beslissingen als MADR-ADR's; CHANGELOG volgens Keep a Changelog; alles in git naast de code.

## Gevolgen
Elke tekst heeft één doel; wijzigingen aan code en docs gaan samen. Een samengevoegd document wordt gegenereerd met `tools/bundle_docs.py`.
