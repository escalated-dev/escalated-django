"""Every page name this package renders resolves to a component.

Inertia resolving a name to nothing is not an error. The response is a 200, the
resolver returns undefined, Vue renders nothing, and the panel comes up blank --
which reads as a permissions problem or an empty dataset. Several screens
shipped that way across this portfolio before anyone noticed.

Neither repo's tests can see it alone: a view test asserts a status code, and
the frontend never hears the name. This is the comparison, against the manifest
the frontend package publishes and this repo vendors at
tests/fixtures/escalated-pages.json.

Adding a screen goes: component into the frontend, frontend release, refresh the
fixture, then render the name here. In that order, or it ships blank.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = Path(__file__).resolve().parent / "fixtures" / "escalated-pages.json"

# Names that render a blank panel today and are not fixed by renaming.
#
# Empty. The advanced reports were the whole of this list; they now render the
# screens the frontend ships, with the props those screens read. Anything added
# here needs the reason written against it, and the last test in this file fails
# if an entry stays after the screen is fixed.
#
# This list may shrink. It must never grow.
KNOWN_BLANK: set[str] = set()

PAGE_NAME = re.compile(r'"(Escalated/[A-Za-z0-9/_]+)"')


def shipped_pages():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["pages"]


def rendered_pages():
    """Page names rendered anywhere in the package, mapped to the files that
    render them, so a failure can name the file and not only the string."""
    found = {}

    for path in (ROOT / "escalated").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue

        for name in PAGE_NAME.findall(path.read_text(encoding="utf-8")):
            found.setdefault(name, set()).add(str(path.relative_to(ROOT)).replace("\\", "/"))

    return found


def explain(missing, rendered):
    lines = ["these page names have no component in @escalated-dev/escalated, so they render a blank panel:"]
    lines += [f"  {name}  ({', '.join(sorted(rendered[name]))})" for name in missing]
    lines += [
        "",
        "Either the name is wrong, or the component has not been released yet.",
        "If it has been: refresh tests/fixtures/escalated-pages.json from the package.",
    ]
    return "\n".join(lines)


def test_renders_only_page_names_the_frontend_ships():
    rendered = rendered_pages()
    shipped = shipped_pages()

    assert rendered, "found no page names at all, which means this test is not looking where it should"

    missing = sorted(name for name in rendered if name not in shipped and name not in KNOWN_BLANK)

    assert missing == [], explain(missing, rendered)


def test_the_manifest_is_present_and_looks_like_one():
    # A fixture gone missing or empty would make the test above pass by
    # comparing against nothing.
    assert MANIFEST.exists()

    shipped = shipped_pages()

    assert len(shipped) > 50
    assert all(name.startswith("Escalated/") for name in shipped)


def test_does_not_keep_excusing_names_that_have_been_fixed():
    # The exception list is a record of work still owed. Leaving an entry in it
    # after the screen is fixed is how the list stops meaning anything.
    rendered = rendered_pages()
    shipped = shipped_pages()

    stale = sorted(name for name in KNOWN_BLANK if name not in rendered or name in shipped)

    assert stale == [], (
        "these names are on the blank-screen exception list but no longer need to be, remove them:\n  "
        + "\n  ".join(stale)
    )
