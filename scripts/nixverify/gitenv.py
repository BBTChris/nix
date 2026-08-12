"""One scrubbed environment for every `git` subprocess in this tree (D3.22).

## The defect, measured twice, one layer apart

`git` honours `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE`, `GIT_COMMON_DIR` and
their relatives **ahead of `-C` and ahead of `cwd`**. `pre-commit` exports them
into every hook it runs, and so does `git` itself into every hook, rebase and
filter. A caller that believes it is talking about the repository named on its
command line is, under those variables, talking about whatever started the hook.

Both instances in this project were measured, not anticipated:

* **ARC 025.** A sub-agent's own test suite ran `git init` / `git add -A` inside
  a throwaway repo under `tmp_path` while `pre-commit` had `GIT_INDEX_FILE`
  exported. Git wrote the throwaway tree into the *worktree's real index* —
  every tracked file staged as deleted.
* **One layer up, and worse.** A sub-agent's `git init` under an inherited
  `GIT_DIR` set `core.bare=true` on `/home/bbt/nix` and **bared the canonical
  repository** (`sessions/SESSION.md:1514`). ARC 026 exists because of it.

## Why ONE helper and not a copy per site

Doctrine C.9: *extend an instrument that already owns a property; never build a
second.* Before this module there were three private spellings of the scrub —
`check_canonical_tree._git_env` (six variables), `check_artifact_gate_coverage
.git_env` (nine), `check_hook_suite._clean_git_env` (every `GIT_*`) — and
`scripts/runtime_gate.py` had none at all while being the one program `pre-commit`
invokes on every commit. Three spellings of one rule is the `avg_price` shape: they
had already diverged by three variables, and nothing would have told anyone which
was right.

**The check contract's standalone-execution guarantee (§4.2) is not weakened by
this.** A check is a plugin *and* a standalone executable; `checks/_preamble.py`
puts `scripts/` on `sys.path` on both paths, which is exactly how every check
already imports `nixverify.contract`. A check that could not import this module
could not import its own `CheckResult` either.

## The scrub is a SUPERSET of the known selectors, deliberately

`scrubbed_env` removes **every** variable whose name begins with `GIT_`, not just
the ones in `SELECTORS`. `check_hook_suite` already did that, and narrowing it to
a named list to build this helper would have *weakened a live instrument* to make
a refactor tidy. `SELECTORS` is therefore documentation-plus-assertion — the list
the committed test proves is covered — and never the mechanism. New git releases
add repository-selecting variables; a prefix rule inherits them, a list does not.

Nothing this project runs under `git` needs a `GIT_*` variable to answer: the
production callers ask `ls-files`, `log`, `show`, `rev-parse`, `worktree list`,
`config --get`, `diff` and `hash-object`. Fixtures that must *commit* pass an
identity through `extra`, after the scrub, where it is visible.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

#: The repository-selecting variables, named so a test can prove they are gone.
#: **Not the mechanism** — see the module docstring. `GIT_DIR`, `GIT_WORK_TREE`
#: and `GIT_INDEX_FILE` are the three that were measured doing damage; the rest
#: select objects, namespaces or path resolution and would produce a subtler
#: version of the same wrong answer.
SELECTORS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CEILING_DIRECTORIES",
    "GIT_PREFIX",
)

#: The rule actually applied. Everything `GIT_`-prefixed goes.
PREFIX = "GIT_"


def scrubbed_env(
    env: Mapping[str, str] | None = None,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """`env` (default `os.environ`) with every `GIT_*` variable removed.

    `extra` is applied AFTER the scrub, so a caller that genuinely needs a git
    variable — a fixture supplying `GIT_AUTHOR_NAME` to make `git commit` work
    in a throwaway repository — states it at the call site instead of inheriting
    it invisibly from whatever launched the process. That is the whole point:
    the environment stops being ambient and becomes an argument.
    """
    source = os.environ if env is None else env
    out = {k: v for k, v in source.items() if not k.startswith(PREFIX)}
    if extra:
        out.update(extra)
    return out
