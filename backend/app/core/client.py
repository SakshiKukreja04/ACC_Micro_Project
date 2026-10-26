"""Anonymous reader identity.

The frontend generates a random UUID once and stores it in localStorage; it is sent as the
X-Client-Id header. No login, no personal data — privacy-first personalization.
"""
import re

from fastapi import Header, HTTPException, status

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def get_client_id(x_client_id: str | None = Header(default=None)) -> str:
    if not x_client_id or not _CLIENT_ID_RE.match(x_client_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid X-Client-Id header (8-64 chars, letters/digits/-/_) is required.",
        )
    return x_client_id


def get_optional_client_id(x_client_id: str | None = Header(default=None)) -> str | None:
    if x_client_id and _CLIENT_ID_RE.match(x_client_id):
        return x_client_id
    return None
