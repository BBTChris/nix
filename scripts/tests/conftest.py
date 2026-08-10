"""Session-wide test fixtures.

`nixverify.loader.load_check` permanently appends a loaded check's directory
to `sys.path` (deliberately never removed — see loader.py's docstring on the
parallel-block race that a scoped try/finally would introduce). That is fine
in production, where the set of checks/ directories is small and fixed for
the process lifetime.

In the test session, though, `load_check` is routinely called against a
fresh `pytest` `tmp_path` per test, and the process is long-lived across the
whole run. Without cleanup, every such call leaves a `tmp_path` entry on
`sys.path` for the rest of the session — an unbounded accumulation that this
autouse fixture prevents by snapshotting and restoring `sys.path` around
every test.
"""

import sys
from collections.abc import Iterator

import pytest  # pylint: disable=import-error


@pytest.fixture(autouse=True)
def _restore_sys_path() -> Iterator[None]:
    """Snapshot sys.path before each test and restore it after.

    Prevents load_check's permanent, per-directory sys.path append (a
    deliberate production trade-off) from accumulating tmp_path entries
    across the test session.
    """
    before = list(sys.path)
    try:
        yield
    finally:
        sys.path[:] = before


@pytest.fixture(scope="session", autouse=True)
def _sys_path_session_baseline() -> Iterator[None]:
    """Regression guard: the whole session must end with sys.path unchanged.

    Complements the per-test `_restore_sys_path` fixture above — that one
    resets sys.path after each individual test; this one is the end-to-end
    check that nothing slipped past it across the full session, including
    tests written after this one that might forget the pattern.
    """
    baseline = list(sys.path)
    yield
    assert sys.path == baseline, "sys.path leaked entries across the test session"
