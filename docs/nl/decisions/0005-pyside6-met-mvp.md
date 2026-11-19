# ADR-0005: PySide6 met Model-View-Presenter

- Status: aangenomen
- Datum: 2026-11-15

## Context
De gebruiker wil een grafische schil. Er zijn 99 mappen × 20 songs; slepen, zoeken en undo zijn gewenst.

## Beslissing
PySide6 (Qt, LGPL). De view (`qt_app.py`) bevat alleen opmaak en koppeling; de presenter (`presenter.py`) bevat alle beslissingen en is zonder scherm getest.

## Gevolgen
Native uiterlijk op Windows/macOS/Linux. Installatie ongeveer 70 MB; daarom optioneel (`pip install kn-songboek[gui]`). Een andere schil (web, Tk) kan dezelfde presenter of direct de kern gebruiken.
