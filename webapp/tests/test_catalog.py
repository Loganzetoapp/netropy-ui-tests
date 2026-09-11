"""Unit tests for webapp/catalog.py — pure AST parsing, no pytest suite
dependency, no browser. Run with:
    pytest --confcutdir=webapp webapp/tests/test_catalog.py -v
(--confcutdir keeps this from picking up the repo-root conftest.py, which
is for the real Playwright suite and would otherwise try to write a
results/history entry for these unit tests too.)
"""
from pathlib import Path

from webapp.catalog import discover_groups, _group_label, _is_combined_suite_file


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_group_label_single_number():
    assert _group_label("t1_auth") == "T1 — Auth"


def test_group_label_multi_number():
    assert _group_label("t10_t12_lifecycle") == "T10/T12 — Lifecycle"


def test_group_label_multi_word():
    assert _group_label("t3_port_management") == "T3 — Port Management"


def test_combined_suite_exact_match_excluded():
    assert _is_combined_suite_file("t1_auth_all", "t1_auth") is True


def test_combined_suite_false_positive_not_excluded():
    # test_t7_frame_size_apply_to_all.py — a real, distinct test, not a
    # combined-suite file, despite ending in "_all".
    assert _is_combined_suite_file("t7_frame_size_apply_to_all", "t7_streams") is False


def test_discover_groups_end_to_end(tmp_path):
    tests_root = tmp_path / "tests"

    _write(
        tests_root / "t1_auth" / "test_t1_valid_login.py",
        '''"""T1 — valid login lands on dashboard.

More detail here.
"""
import pytest


@pytest.mark.hardware_free
@pytest.mark.smoke
def test_t1_valid_login(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t1_auth" / "test_t1_auth_all.py",
        '''"""T1 — combined suite, should not appear."""
import pytest


@pytest.mark.hardware_free
def test_t1_valid_login(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t7_streams" / "test_t7_frame_size_apply_to_all.py",
        '''"""T7 — frame size apply-to-all sticks per row."""
import pytest


@pytest.mark.hardware_free
def test_t7_frame_size_apply_to_all_then_per_row_edit_sticks(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t10_t12_lifecycle" / "test_t10_t12_lifecycle_arp.py",
        '''"""T10/T12 — ARP lifecycle."""
import pytest


@pytest.mark.stateful
def test_t10_t12_lifecycle_arp(dashboard):
    pass
''',
    )
    _write(
        tests_root / "t9_network_profiles" / "test_t9_quarantined_thing.py",
        '''"""T9 — a known-flaky test, should not appear."""
import pytest


@pytest.mark.hardware_free
@pytest.mark.quarantine
def test_t9_quarantined_thing(dashboard):
    pass
''',
    )

    groups = discover_groups(tests_root, repo_root=tmp_path)
    labels = {g.label for g in groups}
    assert labels == {"T1 — Auth", "T7 — Streams", "T10/T12 — Lifecycle"}

    t1 = next(g for g in groups if g.id == "t1_auth")
    assert [f.path for f in t1.files] == ["tests/t1_auth/test_t1_valid_login.py"]
    assert t1.files[0].short_description == "T1 — valid login lands on dashboard."
    entry = t1.files[0].tests[0]
    assert entry.nodeid == "tests/t1_auth/test_t1_valid_login.py::test_t1_valid_login"
    assert entry.markers == ["hardware_free", "smoke"]
    assert entry.safety_marker == "hardware_free"

    # t9's only test is quarantined -> zero visible tests -> group excluded
    assert "t9_network_profiles" not in {g.id for g in groups}
