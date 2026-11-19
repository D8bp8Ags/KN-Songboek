from ..formats.text import Text  # noqa: F401  (re-exported: core raises Text messages)


class KN7Error(Exception):
    """Base class: every error a front end should show to the user. Raised with a Text, it has a key
    and values for the front end's own words; else key is "" and str(e) is all there is."""

    @property
    def key(self) -> str:
        return getattr(self.args[0], "key", "") if self.args else ""

    @property
    def values(self) -> dict:
        return getattr(self.args[0], "values", {}) if self.args else {}


class NoDatabase(KN7Error):
    """Neither KN7000MN.INF nor KN7000MN.BAK could be read."""


class SlotError(KN7Error):
    """A folder/song slot is empty, occupied, full or out of range."""


class NothingToUndo(KN7Error):
    pass


class InvalidName(KN7Error):
    """A song or folder name the keyboard cannot store or show. `name`, and `bad` (the characters that
    are not allowed) or empty when the name is too long, so a front end can say it in its own words."""

    def __init__(self, message: str, name: str = "", bad: str = ""):
        super().__init__(message)
        self.name, self.bad = name, bad
