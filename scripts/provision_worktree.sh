#!/usr/bin/env bash
# Provision a linked git worktree that can actually pass the commit gates.
#
# WHY THIS EXISTS (ARC 020 finding 9, fixed once in ARC 021).
# `state/` is gitignored (D1.16 — it holds the hardware UUID and credential JSON)
# and `.venv/` is gitignored too. A fresh `git worktree add` therefore lands a tree
# with NEITHER. `check_node_identity` reads `state/node_identity.json` and fails;
# the Stage 3 runtime hook needs `.venv/bin/python` and cannot start. Both ARC 020
# sub-agents hit this independently and each invented its own repair, which is a
# standing tax on every multi-agent arc and a source of two divergent fixes for one
# problem. This script is the single repair, applied at dispatch.
#
# The link is a SYMLINK back to the primary tree, deliberately:
#   - copying `state/` would duplicate credential material into a second directory
#     with a different lifetime, and D1.16's whole subject is that it lives in one
#     place under 0600
#   - copying `.venv/` costs disk and drifts the moment a pin changes
#   - both targets are gitignored, so the symlinks cannot be committed and cannot
#     reach a diff
#
# BASE IS EXPLICIT AND VERIFIED, NEVER DEFAULTED (ARC 019 finding: all three
# worktrees were provisioned from `main` rather than session HEAD, silently). This
# script refuses to guess: pass the base, and it prints what it actually resolved
# and asserts the new worktree's HEAD matches.
#
# Usage: scripts/provision_worktree.sh <branch-name> <base-ref> [worktree-path]

set -euo pipefail

if [[ $# -lt 2 ]]; then
	echo "usage: $0 <branch-name> <base-ref> [worktree-path]" >&2
	exit 2
fi

BRANCH="$1"
BASE_REF="$2"
PRIMARY="$(git rev-parse --show-toplevel)"
WT_PATH="${3:-${PRIMARY}/../nix-wt-${BRANCH}}"

# Resolve the base BEFORE creating anything, and print it. A base that does not
# resolve is an error here rather than a surprise three commits later.
BASE_SHA="$(git -C "${PRIMARY}" rev-parse --verify "${BASE_REF}^{commit}")"
echo "primary tree : ${PRIMARY}"
echo "base ref     : ${BASE_REF}"
echo "base sha     : ${BASE_SHA}"
echo "branch       : ${BRANCH}"
echo "worktree     : ${WT_PATH}"

git -C "${PRIMARY}" worktree add -b "${BRANCH}" "${WT_PATH}" "${BASE_SHA}"

WT_ABS="$(cd "${WT_PATH}" && pwd)"

# --- the fix itself -------------------------------------------------------
# Both targets are gitignored in the primary tree, so these symlinks are
# invisible to git in the worktree too.
for gitignored in state .venv; do
	if [[ ! -e "${PRIMARY}/${gitignored}" ]]; then
		echo "FATAL: ${PRIMARY}/${gitignored} does not exist in the primary tree" >&2
		exit 1
	fi
	rm -rf "${WT_ABS:?}/${gitignored}"
	ln -s "${PRIMARY}/${gitignored}" "${WT_ABS}/${gitignored}"
	echo "linked       : ${gitignored} -> ${PRIMARY}/${gitignored}"
done

# --- prove the provisioning worked, do not assume it ----------------------
# The point of the script is that the worktree can pass the gates that ARC 020
# found it failing. So run those two specific things, here, and fail loudly.
WT_HEAD="$(git -C "${WT_ABS}" rev-parse HEAD)"
if [[ "${WT_HEAD}" != "${BASE_SHA}" ]]; then
	echo "FATAL: worktree HEAD ${WT_HEAD} != requested base ${BASE_SHA}" >&2
	exit 1
fi
echo "verified     : worktree HEAD == requested base (${WT_HEAD})"

if [[ ! -x "${WT_ABS}/.venv/bin/python" ]]; then
	echo "FATAL: .venv/bin/python not executable through the link" >&2
	exit 1
fi

(cd "${WT_ABS}" && ./.venv/bin/python checks/check_node_identity.py >/dev/null 2>&1) ||
	{
		echo "FATAL: check_node_identity still fails in the provisioned worktree" >&2
		exit 1
	}
echo "verified     : check_node_identity passes inside the worktree"
echo "PROVISIONED OK"
