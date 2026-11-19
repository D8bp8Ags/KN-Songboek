# ADR-0002: ports and adapters

- Status: aangenomen
- Datum: 2026-11-15

## Context
We willen werken op een gekoppelde kaart, een kopie in een map, een FAT-image, en in tests zonder schijf.

## Beslissing
De kern kent alleen het `Storage`-protocol. Adapters: `DirectoryStorage`, `MemoryStorage`, `FatImageStorage` (sinds 2026-11-15).

## Gevolgen
Nieuwe opslag = één klasse. Tests zijn snel en raken geen echte bestanden.
