"""
Host user primary keys.

Host user models may use integer, UUID or string primary keys, so a user id
that arrives as text (a form field, a macro or workflow action value) is
converted with the user model's own primary-key field rather than ``int()``.
"""

from django.contrib.auth import get_user_model


def user_pk(value):
    """``value`` as the host user model's primary key. Raises ``ValidationError`` when it cannot be one."""
    if isinstance(value, str):
        value = value.strip()
    return get_user_model()._meta.pk.to_python(value)
