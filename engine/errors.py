"""Error codes and the error record returned to proposers (spec 7.3)."""
from __future__ import annotations

from dataclasses import dataclass

E_PARSE = "E_PARSE"
E_IDENTITY = "E_IDENTITY"
E_FORBIDDEN = "E_FORBIDDEN"
E_RATE_LIMIT = "E_RATE_LIMIT"
E_SCHEMA = "E_SCHEMA"
E_SEMANTIC = "E_SEMANTIC"
E_PRICE = "E_PRICE"
E_PRICE_STALE = "E_PRICE_STALE"
E_INTERNAL = "E_INTERNAL"

RETRYABLE = {
    E_PARSE: True,
    E_IDENTITY: False,
    E_FORBIDDEN: False,
    E_RATE_LIMIT: True,
    E_SCHEMA: True,
    E_SEMANTIC: True,
    E_PRICE: True,
    E_PRICE_STALE: False,
    E_INTERNAL: False,
}


@dataclass(frozen=True)
class MagiError:
    code: str
    path: str
    message: str

    @property
    def retryable(self) -> bool:
        return RETRYABLE[self.code]

    def to_dict(self) -> dict:
        return {"code": self.code, "path": self.path, "message": self.message, "retryable": self.retryable}
