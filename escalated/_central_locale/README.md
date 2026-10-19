# Vendored central catalogues

Generated. Do not edit by hand.

`locale/<lang>/LC_MESSAGES/django.{po,mo}` is a copy of
`packages/pypi/escalated_locale/locale/` from
[escalated-locale](https://github.com/escalated-dev/escalated-locale), which
stays the source of truth for translations. The exact tag and commit are in
`SOURCE`.

It exists because `escalated-locale` is not on PyPI and PyPI refuses packages
that depend on a git URL. `escalated.locale_paths.get_central_locale_path()`
uses this copy only when the `escalated_locale` package is not installed
(`pip install escalated-django[locale]`).

To refresh from a new escalated-locale tag:

    python scripts/sync_central_locale.py v0.1.9

Translation fixes go to escalated-locale, not here.
