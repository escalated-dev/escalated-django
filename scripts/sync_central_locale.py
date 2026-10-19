"""Re-vendor the central gettext catalogues from an escalated-locale tag.

Usage:
    python scripts/sync_central_locale.py v0.1.8

Shallow-clones https://github.com/escalated-dev/escalated-locale at the given
tag, replaces escalated/_central_locale/locale/ with the tag's
packages/pypi/escalated_locale/locale/<lang>/LC_MESSAGES/django.{po,mo}
files, and records the tag and commit in escalated/_central_locale/SOURCE.
Commit the result; the catalogues are never edited here by hand.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/escalated-dev/escalated-locale.git"
SOURCE_SUBDIR = Path("packages/pypi/escalated_locale/locale")
TARGET = Path(__file__).resolve().parent.parent / "escalated" / "_central_locale"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tag", help="escalated-locale git tag, e.g. v0.1.8")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        checkout = Path(tmp) / "escalated-locale"
        subprocess.run(
            [
                "git",
                "-c",
                "advice.detachedHead=false",
                "clone",
                "--quiet",
                "--depth",
                "1",
                "--branch",
                args.tag,
                REPO_URL,
                str(checkout),
            ],
            check=True,
        )
        commit = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()

        source = checkout / SOURCE_SUBDIR
        if not source.is_dir():
            raise SystemExit(f"{SOURCE_SUBDIR} not found at {args.tag}")

        dest = TARGET / "locale"
        if dest.exists():
            shutil.rmtree(dest)

        copied = 0
        for path in sorted(source.glob("*/LC_MESSAGES/django.*")):
            if path.suffix not in (".po", ".mo"):
                continue
            out = dest / path.relative_to(source)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
            copied += 1

    (TARGET / "SOURCE").write_text(f"{REPO_URL} {args.tag} {commit}\n", encoding="utf-8", newline="\n")
    print(f"Vendored {copied} files from escalated-locale {args.tag} ({commit}) into {dest}")


if __name__ == "__main__":
    main()
