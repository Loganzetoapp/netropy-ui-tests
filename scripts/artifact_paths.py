"""Shared naming convention for per-test artifact folders (screenshots).

Used on both ends: conftest.py's `page` fixture *writes* a screenshot here
on failure (pytest-playwright's own equivalent mechanism only activates
through its own page/context fixtures, which this repo's custom
auth-replay `page` fixture bypasses — see conftest.py for the full story),
and collect_run.py *reads* it back to link into the results dashboard.
Since both ends are this repo's own code, they only need to agree with
each other — not with any other tool's naming convention — so a small
stdlib-only slugify is enough; no reason to depend on python-slugify (or
anything else) just for this.
"""
import re


def slugify(text: str) -> str:
    """'tests/t6_x/test_y.py::test_z[chromium]' -> 'tests-t6-x-test-y-py-test-z-chromium'.
    Lowercase, any run of non-alphanumeric characters collapsed to one
    hyphen, leading/trailing hyphens trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
