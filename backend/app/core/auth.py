"""Shared-token auth + the cost-cap exception.

require_token gates all /api routes when API_TOKEN is set (it's a no-op when unset, so
local/dev/tests stay open). CapExceeded is raised by the usage service and mapped to 429.
"""

import secrets

from fastapi import Header, HTTPException

from app.core.config import get_settings
from app.core.logging import log


async def require_token(authorization: str | None = Header(default=None)) -> None:
    token = get_settings().api_token
    if not token:  # auth disabled
        return
    if not authorization or not secrets.compare_digest(authorization, f"Bearer {token}"):
        log.warning("auth.denied")
        raise HTTPException(status_code=401, detail="invalid or missing access token")


class CapExceeded(Exception):
    """Raised when a daily paid-operation cap would be exceeded."""

    def __init__(self, kind: str, remaining: int):
        self.kind = kind
        self.remaining = remaining
        super().__init__(f"daily {kind} cap reached ({remaining} remaining today)")
