from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db.models import Q

from escalated.views import admin


@pytest.mark.parametrize(
    "field_names,expect_or",
    [
        ([], None),
        (["username"], None),
        (["is_agent"], "is_agent"),
        (["is_admin"], "is_admin"),
        (["is_agent", "is_admin"], "both"),
    ],
)
def test_skill_form_user_filter_q(field_names, expect_or):
    mocks = [SimpleNamespace(name=n) for n in field_names]

    with patch("escalated.views.admin.User._meta.get_fields", return_value=mocks):
        q = admin._skill_form_user_filter_q()

    if expect_or is None:
        assert q is None
        return

    assert q is not None
    if expect_or == "is_agent":
        assert q == Q(is_agent=True)
    elif expect_or == "is_admin":
        assert q == Q(is_admin=True)
    else:
        assert q == Q(is_agent=True) | Q(is_admin=True)
