# Escalated Django — Docker demo (scaffold, not end-to-end)

Draft Django Postgres Docker demo.

`docker compose up --build` bootstraps a minimal Django project under `docker/host-app/` and installs the package (`pip install ./package-src`), then runs migrations and a `seed_demo` management command (not yet implemented).

**Not verified end-to-end.** Missing:

- `escalated.urls` inclusion in host `urls.py` (commented TODO)
- `seed_demo` management command in the host app
- `/demo` picker view + click-to-login view (cookie-based session auth)
- Any Inertia pipeline if the package expects it

See the PR body for the punch list.
