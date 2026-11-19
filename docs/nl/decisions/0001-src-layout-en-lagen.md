# ADR-0001: src-layout en vier lagen

- Status: aangenomen
- Datum: 2026-11-15

## Context
v0.1 was één plat pakket waarin bestandsoperaties, database en uitvoer door elkaar liepen.

## Beslissing
Code onder `src/kn_songboek` met de lagen formats → storage → core → cli/gui; buitenste lagen importeren binnenste, nooit andersom. Configuratie in `pyproject.toml`.

## Gevolgen
Tests draaien tegen de pakketcode; elke laag apart te testen; een tweede front-end kan zonder de kern te wijzigen.
