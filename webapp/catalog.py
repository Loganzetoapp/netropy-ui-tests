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
# Directory-name words shown in capitals in a group label ("wan" -> "WAN").
_LABEL_ACRONYMS = {"wan", "tcp", "udp", "ip", "dns", "ntp", "api", "ui", "64b"}
# Fixtures that put the WAN emulator in a test's path.
_WAN_FIXTURES = {"wan_bench", "wan_page"}


@dataclass
class TestEntry:
    nodeid: str
    name: str
    markers: list[str]
    # The test function's own docstring ("" when it has none; the UI then
    # falls back to its file's).
    description: str = ""
    full_description: str = ""
    # Cases from @pytest.mark.parametrize: None when not parametrized, 0
    # when parametrized over something the AST can't count.
    param_count: Optional[int] = None
    uses_wan: bool = False

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
    # The area folder's __init__.py docstring: what the area covers.
    description: str = ""

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
    rest = " ".join(t.upper() if t in _LABEL_ACRONYMS else t.capitalize() for t in tokens[i:])
    prefix = "/".join(numbers) if numbers else dirname.upper()
    return f"{prefix} — {rest}" if rest else prefix


def _group_sort_key(dirname: str) -> tuple:
    """Areas in T-number order (T0, T1, ..., T9, T10/T12, T13), not text
    order (T0, T10, T13, T1). Folders with no T-number go last."""
    match = re.match(r"^t(\d+)", dirname)
    return (int(match.group(1)) if match else float("inf"), dirname)


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


def _first_paragraph(docstring: str) -> str:
    """The docstring up to its first blank line, on one line. Not just the
    first source line: that ends wherever the author's editor wrapped it
    ("...80 ms Port 4 -> 3. Real")."""
    paragraph = docstring.strip().split("\n\n", 1)[0]
    return " ".join(paragraph.split())


def _literal_len(node: ast.expr, module_lists: dict[str, int]) -> Optional[int]:
    """How many cases a parametrize argvalues expression holds: a literal
    list/tuple, or a module-level name bound to one (CASES = [...])."""
    if isinstance(node, (ast.List, ast.Tuple)):
        return len(node.elts)
    if isinstance(node, ast.Name):
        return module_lists.get(node.id)
    return None


def _param_count(func: ast.FunctionDef, module_lists: dict[str, int]) -> Optional[int]:
    """Product of the case counts of every @pytest.mark.parametrize on
    `func`; None if there are none, 0 if any can't be counted statically."""
    total = None
    for dec in func.decorator_list:
        if not (isinstance(dec, ast.Call) and _decorator_marker_name(dec) == "parametrize"):
            continue
        values = dec.args[1] if len(dec.args) > 1 else next(
            (k.value for k in dec.keywords if k.arg == "argvalues"), None
        )
        count = _literal_len(values, module_lists) if values is not None else None
        total = (total or 1) * (count or 0)
    return total


def _module_lists(tree: ast.Module) -> dict[str, int]:
    """{name: length} for module-level `NAME = [...]` / `NAME = (...)`."""
    lists = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.List, ast.Tuple)):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    lists[target.id] = len(node.value.elts)
    return lists


def _parse_file(path: Path, repo_root: Path) -> Optional[TestFile]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        # One bad file must never take down discovery (and therefore the
        # whole /api/catalog endpoint / dashboard) for every other file —
        # skip just this one and keep going.
        print(f"catalog: skipping {path} — syntax error: {exc}")
        return None
    docstring = ast.get_docstring(tree) or ""
    if not docstring:
        return None
    short = _first_paragraph(docstring)

    tests: list[TestEntry] = []
    module_lists = _module_lists(tree)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        markers = [
            m for m in (_decorator_marker_name(dec) for dec in node.decorator_list) if m
        ]
        if "quarantine" in markers:
            continue
        rel_path = path.relative_to(repo_root).as_posix()
        own_doc = (ast.get_docstring(node) or "").strip()
        tests.append(
            TestEntry(
                nodeid=f"{rel_path}::{node.name}",
                name=node.name,
                markers=[m for m in markers if m != "parametrize"],
                description=_first_paragraph(own_doc),
                full_description=own_doc,
                param_count=_param_count(node, module_lists),
                uses_wan=bool(_WAN_FIXTURES & {a.arg for a in node.args.args}),
            )
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
    dirs = sorted((p for p in tests_root.iterdir() if p.is_dir()), key=lambda p: _group_sort_key(p.name))
    for dir_path in dirs:
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
            groups.append(TestGroup(id=dirname, label=_group_label(dirname), files=files,
                                    description=_area_description(dir_path)))
    return groups


def _area_description(dir_path: Path) -> str:
    """The area folder's __init__.py docstring, or "" without one."""
    init = dir_path / "__init__.py"
    try:
        return (ast.get_docstring(ast.parse(init.read_text())) or "").strip()
    except (OSError, SyntaxError):
        return ""
