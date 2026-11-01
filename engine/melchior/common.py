"""Names, modes and scopes shared by Melchior's programs (design 22.13; plan 9, items 1 and 2)."""
from __future__ import annotations

MELCHIOR = "melchior.magi"
SOURCE_DIR = "agents/melchior"
MODES = ("preview", "live", "off")
MODEL_MODES = ("off", "preview", "live")
_RANK = {"off": 0, "preview": 1, "live": 2}
# Every scope does the program part; `all` adds every kind of model task, the next four only their own kind, and
# `probe` the two permission probes. In this version `referrals` and `rulings` have no work yet. The checks of
# Balthasar's drafts (insight-check) come with Balthasar's own plan (plan 9, item 22), and with them their scope.
MODEL_KINDS = ("evidence", "referrals", "rulings")
SCOPES = {"all": ("program", *MODEL_KINDS), "program": ("program",), "evidence": ("program", "evidence"),
          "referrals": ("program", "referrals"), "rulings": ("program", "rulings"),
          "probe": ("program", "probe")}


def resolve_mode(value: str | None) -> str:
    """The repository variable MELCHIOR_MODE; unset means preview (design 22.13)."""
    mode = (value or "").strip().lower() or "preview"
    if mode not in MODES:
        raise ValueError(f"MELCHIOR_MODE must be one of {', '.join(MODES)}, not {value!r}")
    return mode


def resolve_model_mode(value: str | None, program_mode: str, event: str | None) -> str:
    """The repository variable MELCHIOR_MODEL_MODE: unset, empty or off means off. The result is never higher than
    MELCHIOR_MODE, and preview asks the model only in a run started by hand (workflow_dispatch)."""
    mode = (value or "").strip().lower() or "off"
    if mode not in MODEL_MODES:
        raise ValueError(f"MELCHIOR_MODEL_MODE must be one of {', '.join(MODEL_MODES)}, not {value!r}")
    if _RANK[mode] > _RANK.get(program_mode, 0):
        mode = program_mode if program_mode in _RANK else "off"
    if mode == "preview" and event != "workflow_dispatch":
        return "off"
    return mode
