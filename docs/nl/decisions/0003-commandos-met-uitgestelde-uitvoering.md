# ADR-0003: bewerkingen als commando's, uitvoeren bij opslaan

- Status: aangenomen
- Datum: 2026-11-15

## Context
v0.1 schreef bij elke bewerking direct naar de kaart. Een GUI vraagt undo, een CLI vraagt dry-run, en een half uitgevoerde bewerking kan een kaart beschadigen.

## Beslissing
Elke bewerking neemt een snapshot van de database (54 KB), wijzigt het geheugen en plant bestandsoperaties. `save()` voert alles in volgorde uit en schrijft dan de database zoals het keyboard (INF, teruglezen, BAK).

## Gevolgen
Undo, dry-run en voortgang zijn eenvoudig. Nadeel: als een bestandsoperatie halverwege faalt, moet `check` de rest tonen; een herstelfunctie staat op de roadmap.
