"""KN Songboek -- read and edit the Technics SX-KN7000 SD-card music database.

Layers (outer may import inner, never the other way round):
    cli/, gui/         front ends (adapters)
    core/              use cases: CardSession, views, errors
    storage/           where bytes live (directory, memory, later FAT image)
    formats/           pure byte formats (INF, containers, card layout)
"""
__version__ = "0.2.0"

# The name people see (windows, menus, About, the .app/.exe) and the name of the folders for back-ups.
APP_NAME = "KN Songboek"

# The project's own home page, shown in About. Empty: no link is shown.
__url__ = "https://github.com/D8bp8Ags/KN-Songboek"
