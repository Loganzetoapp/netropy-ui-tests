"""Static, AST-based discovery of the Playwright test suite for the web
dashboard. Never imports or invokes pytest — this only reads source
files, so opening the dashboard can't reserve a port or touch the box by
itself.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = REPO_ROOT / "tests"

SAFETY_MARKERS = {"hardware_free", "stateful"}
_AREA_TOKEN_RE = re.compile(r"^t\d+$")


@dataclass
class TestEntry:
    nodeid: str
    name: str
    markers: list[str]

    @property
    def safety_marker(self) -> Optional[str]:
        for m in self.markers:
            if m in SAFETY_MARKERS:
                return m
        return None


@dataclass
class TestFile:
    path: str
    short_description: str
    full_description: str
    tests: list[TestEntry] = field(default_factory=list)


@dataclass
class TestGroup:
    id: str
    label: str
    files: list[TestFile] = field(default_factory=list)

    @property
    def run_all_nodeids(self) -> list[str]:
        return [t.nodeid for f in self.files for t in f.tests]


def _group_label(dirname: str) -> str:
    """'t10_t12_lifecycle' -> 'T10/T12 — Lifecycle'; 't1_auth' -> 'T1 — Auth'."""
    tokens = dirname.split("_")
    numbers = []
    i = 0
    while i < len(tokens) and _AREA_TOKEN_RE.match(tokens[i]):
        numbers.append(tokens[i].upper())
        i += 1
    rest = " ".join(t.capitalize() for t in tokens[i:])
    prefix = "/".join(numbers) if numbers else dirname.upper()
    return f"{prefix} — {rest}" if rest else prefix


def _is_combined_suite_file(file_stem: str, dirname: str) -> bool:
    """True only for an exact '<dirname>_all' stem — a loose '_all.py'
    suffix check would also match genuinely distinct tests like
    test_t7_frame_size_apply_to_all.py (its own name, not the
    combined-suite convention)."""
    return file_stem == f"{dirname}_all"


def _decorator_marker_name(node: ast.expr) -> Optional[str]:
    """@pytest.mark.hardware_free -> 'hardware_free' (bare attribute);
    @pytest.mark.xfail(...) -> 'xfail' (a call wrapping the same
    attribute chain)."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute):
        if target.value.attr == "mark":
            return target.attr
    return None


def _parse_file(path: Path, repo_root: Path) -> Optional[TestFile]:
    tree = ast.parse(path.read_text(), filename=str(path))
    docstring = ast.get_docstring(tree) or ""
    if not docstring:
        return None
    short = docstring.strip().splitlines()[0].strip()

    tests: list[TestEntry] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        markers = [
            m for m in (_decorator_marker_name(dec) for dec in node.decorator_list) if m
        ]
        if "quarantine" in markers:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        tests.append(
            TestEntry(nodeid=f"{rel_path}::{node.name}", name=node.name, markers=markers)
        )

    if not tests:
        return None

    return TestFile(
        path=path.relative_to(repo_root).as_posix(),
        short_description=short,
        full_description=docstring.strip(),
        tests=tests,
    )


def discover_groups(
    tests_root: Path = TESTS_ROOT, repo_root: Path = REPO_ROOT
) -> list[TestGroup]:
    groups: list[TestGroup] = []
    for dir_path in sorted(p for p in tests_root.iterdir() if p.is_dir()):
        dirname = dir_path.name
        if dirname.startswith("__"):
            continue
        files: list[TestFile] = []
        for file_path in sorted(dir_path.glob("test_*.py")):
            file_stem = file_path.stem[5:] if file_path.stem.startswith("test_") else file_path.stem
            if _is_combined_suite_file(file_stem, dirname):
                continue
            parsed = _parse_file(file_path, repo_root)
            if parsed:
                files.append(parsed)
        if files:
            groups.append(TestGroup(id=dirname, label=_group_label(dirname), files=files))
    return groups
