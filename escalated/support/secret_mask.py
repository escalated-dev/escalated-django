"""
The placeholder an admin settings page shows for a stored secret.

The page learns only that a secret is set. Posting the placeholder back means
"keep the stored value"; anything else replaces it.
"""

import re

MASK = "********"

# Also matches the older "abc*****" form, so a settings tab opened before an
# upgrade does not overwrite the secret with its placeholder.
_MASKED = re.compile(r"^.{0,3}\*{3,}$")


def mask(value) -> str:
    """``MASK`` for a stored secret, ``""`` when none is set."""
    return "" if value is None or value == "" else MASK


def is_masked(value) -> bool:
    """True when ``value`` is a placeholder posted back, not a new secret."""
    return isinstance(value, str) and value != "" and _MASKED.fullmatch(value) is not None
