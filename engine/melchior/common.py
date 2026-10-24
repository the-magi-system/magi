"""Names, modes and scopes shared by Melchior's programs (design 22.13)."""
from __future__ import annotations

MELCHIOR = "melchior.magi"
SOURCE_DIR = "agents/melchior"
MODES = ("preview", "live", "off")
# Both scopes do the same work until the model tasks of design 22.9 arrive with a later protocol version.
SCOPES = {"all": ("program",), "program": ("program",)}


def resolve_mode(value: str | None) -> str:
    """The repository variable MELCHIOR_MODE; unset means preview (design 22.13)."""
    mode = (value or "").strip().lower() or "preview"
    if mode not in MODES:
        raise ValueError(f"MELCHIOR_MODE must be one of {', '.join(MODES)}, not {value!r}")
    return mode
