"""PyPI rejects any Requires-Dist that is a direct URL reference (`name @ url`).

A single one -- even inside an extra -- makes `twine upload` / the publish
action fail with `400 Can't have direct dependency`.
"""

import os
import sys

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    tomllib = pytest.importorskip("tomli")

PYPROJECT = os.path.join(os.path.dirname(__file__), "..", "..", "pyproject.toml")


def _project():
    with open(PYPROJECT, "rb") as fh:
        return tomllib.load(fh)["project"]


def _all_requirements():
    project = _project()
    yield from project.get("dependencies", [])
    for reqs in project.get("optional-dependencies", {}).values():
        yield from reqs


def test_no_direct_url_references_in_dependencies():
    offenders = [req for req in _all_requirements() if "@" in req or "://" in req]
    assert offenders == []


def test_locale_extra_installs_standalone_package():
    extra = _project().get("optional-dependencies", {}).get("locale", [])
    assert any(req.replace(" ", "").startswith("escalated-locale>=") for req in extra)
