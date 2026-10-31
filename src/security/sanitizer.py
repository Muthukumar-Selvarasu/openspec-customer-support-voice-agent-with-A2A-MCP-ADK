"""Length cap and character whitelist. No cloud SDK."""

from __future__ import annotations

import re

ALLOWED_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?-'"
)

MAX_INPUT_LENGTH = 300

_FINAL_PATTERN = re.compile(r"^[a-zA-Z0-9\s.,!?()'-]*$")


def sanitize_input(text: str) -> str:
    """Return ``text`` with characters outside ``ALLOWED_CHARS`` removed.

    Raises ``ValueError`` when ``text`` is longer than ``MAX_INPUT_LENGTH``
    or the stripped result still fails the final character check.
    """
    if len(text) > MAX_INPUT_LENGTH:
        raise ValueError(f"Text exceeds {MAX_INPUT_LENGTH} characters")

    sanitized = "".join(char for char in text if char in ALLOWED_CHARS)
    if _FINAL_PATTERN.fullmatch(sanitized) is None:
        raise ValueError("Invalid characters detected after sanitization")
    return sanitized
