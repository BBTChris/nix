# Branch protection on `main` — measured state and the drafted replacement

**Produced by ARC 032 / Phase 0.3. NOT APPLIED.** Branch protection is
outward-facing GitHub state and the operator's alone: `cc` produces the config,
the operator reviews and clicks. Nothing in this file was executed against the
GitHub API beyond the four **read-only** calls quoted below.

**Canonical path:** `/home/bbt/nix` (absolute). Repo: `BBTChris/nix`, **public**,
default branch `main`, the account holds `admin: true`.

---

## 1. THE MEASURED CURRENT STATE (read-only `gh api`, 2026-08-15)

```
$ gh api repos/BBTChris/nix/rulesets
[]

$ gh api repos/BBTChris/nix/branches/main/protection
{"required_pull_request_reviews":{"dismiss_stale_reviews":false,
  "require_code_owner_reviews":false,"require_last_push_approval":false,
  "required_approving_review_count":0},
 "required_signatures":{"enabled":false},
 "enforce_admins":{"enabled":false},
 "required_linear_history":{"enabled":false},
 "allow_force_pushes":{"enabled":false},
 "allow_deletions":{"enabled":false},
 "block_creations":{"enabled":false},
 "required_conversation_resolution":{"enabled":false},
 "lock_branch":{"enabled":false},
 "allow_fork_syncing":{"enabled":false}}

$ gh api repos/BBTChris/nix/branches/main/protection/required_status_checks
404  "Required status checks not enabled"

$ gh api repos/BBTChris/nix/actions/workflows
{"total_count":0,"workflows":[]}

$ gh api repos/BBTChris/nix/commits/main/check-runs
{"total_count":0,"check_runs":[]}
```

### Stated plainly, in the three terms the brief asked for

1. **CONFIGURED, and BYPASSABLE.** It is **classic branch protection**, not a
   repository ruleset — `rulesets` is empty. The rule ARC 031's push reported
   bypassing (*"Changes must be made through a pull request"*) is the
   `required_pull_request_reviews` block above. It is bypassable because
   **`enforce_admins.enabled = false`** and this account is `admin`. That single
   field is the entire bypass; nothing else in the config grants it.
2. **Required status checks are NOT configured** — the endpoint 404s. Nothing
   about `verify.py`, `pytest` or `pre-commit` gates a merge today.
3. **Force-pushes and deletions on `main` are already blocked**, and those two
   are the settings that actually protect banked evidence (§0h, directive 6).
   They are worth keeping through any replacement.

### THE BRIEF'S PREMISE IS STATED BACKWARDS, and the config is what says so (§0a)

The brief describes the current shape as *"PR-only + sole maintainer +
self-approval-forbidden strands every PR"* — the ARC 019 deadlock waiting to
recur.

**`required_approving_review_count` is `0`.** No approval is required, by
anyone, for any PR on `main`. `require_last_push_approval` is `false` and
`require_code_owner_reviews` is `false`, so nothing in the live config forbids
self-merge. **A PR opened on this repository today can be merged by its own
author with zero reviews.** The deadlock the ruling exists to dissolve is not
the deadlock that is configured.

This matters for the ruling rather than merely correcting the record: the
ARCHITECT RULING is *"replace human review with green status checks"*, and
**there is no human review to replace.** What the ruling actually does here is
**ADD** a gate (status checks) to a rule that currently has none, and close the
admin bypass. That is a strictly stronger position than today's, and it is the
opposite of the ruling's stated rationale. It is still the right move — a PR
requirement that everything bypasses is dishonest state either way — but it is
being adopted on a different argument than the one written down, and adopting
it on the written one would mean believing the config forbids something it
permits.

---

## 2. THE PREREQUISITE, AND IT IS A HARD BLOCK

**There are zero GitHub Actions workflows and zero check runs in this
repository's entire history.** `verify.py`, `pytest` and `pre-commit` run on
this box, at the console, and have never reported a status to GitHub.

GitHub's `required_status_checks.contexts` (and `checks[].context`) name a
status **by string**. A required context that no run ever reports is not
"skipped" and is not "green by default": the PR sits at *"Expected — Waiting for
status to be reported"* **forever**, and the merge button stays disabled.
`enforce_admins: true` then removes the bypass that is the only reason work
moves today.

So applying §3's config **before** CI exists does not weaken protection — it
**reintroduces the ARC 019 deadlock from the other side**, permanently and for
every PR, with the escape hatch nailed shut in the same edit. That is a worse
state than the one being replaced.

**Named as a debt row, not glossed:** `CHECK-DEBT` **D3.141** — *no CI runs
`verify.py`/`pytest`/`pre-commit` as a GitHub status check, so a
required-status-check rule on `main` would protect nothing and block
everything.* Owner ARC 033. **The rule in §3 protects nothing until that row is
discharged, and this file does not pretend otherwise.**

A second, non-obvious half of the same debt: `verify.py`'s honest exit code on
this tree is **1**, not 0 (`check_ibgateway_service` FAILs because the IB
Gateway is down, and that FAIL is by design until the tap session runs). A CI
job that shells `verify.py` and propagates its exit code is therefore red on
day one for a reason that has nothing to do with the PR. Whatever CI is
written has to decide, explicitly and in writing, which non-PASS statuses gate
a merge — that decision is an architect's, not a workflow author's, and it is
part of D3.141 rather than a detail under it.

---

## 3. THE DRAFTED REPLACEMENT — apply only after D3.141

Two spellings of the same rule. **Pick one.** A repository ruleset and classic
branch protection on the same branch both apply, and their union is what binds;
running both leaves two half-configs to keep in sync, which is the
`avg_price` shape.

### 3a. RECOMMENDED — replace classic protection with a repository ruleset

Rulesets are the maintained surface, they carry an explicit, auditable bypass
list (rather than one boolean), and `rulesets` is empty today so there is
nothing to reconcile.

Write this to a file and pipe it in — **one operator action**:

```bash
# 1. Remove the classic rule first, so exactly ONE mechanism binds `main`.
gh api -X DELETE repos/BBTChris/nix/branches/main/protection

# 2. Install the ruleset.
gh api -X POST repos/BBTChris/nix/rulesets --input main-ruleset.json
```

`main-ruleset.json`:

```json
{
  "name": "main: PR + green checks, self-merge allowed",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [],
  "conditions": {
    "ref_name": { "include": ["refs/heads/main"], "exclude": [] }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "nix-verify" },
          { "context": "nix-pytest" },
          { "context": "nix-pre-commit" }
        ]
      }
    }
  ]
}
```

**Every field, and why it is the value it is:**

| field | value | why |
|---|---|---|
| `bypass_actors` | `[]` | **This is the honesty fix.** Today `enforce_admins:false` means the sole admin bypasses everything, so the rule is decorative. An empty bypass list is the rule actually binding. If the operator wants a break-glass, add the actor here **explicitly** — a named bypass is honest state; a global admin exemption is not. |
| `required_approving_review_count` | `0` | The ruling: no human reviewer the sole maintainer cannot supply. Also what is configured today — this is not a loosening. |
| `required_status_checks` | 3 contexts | The ruling's substance: `verify.py`, `pytest`, `pre-commit` in the merge path. **Inert until D3.141.** |
| `strict_..._policy` | `true` | The PR branch must be up to date with `main` before merge, so the green was measured against the tree that will exist after the merge and not an older one. |
| `deletion`, `non_fast_forward` | present | Preserves the two protections the classic rule already gives (`allow_deletions:false`, `allow_force_pushes:false`). Dropping them while "strengthening" protection would be a net loss. |

### 3b. ALTERNATIVE — keep classic protection, add checks, close the bypass

Same rule in the older surface. Use this if the operator prefers not to migrate.

```bash
gh api -X PUT repos/BBTChris/nix/branches/main/protection --input main-protection.json
```

`main-protection.json`:

```json
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["nix-verify", "nix-pytest", "nix-pre-commit"]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
```

`PUT .../protection` **replaces the whole object** — every field above must be
sent even where it matches today's value, which is why the unchanged ones are
written out rather than omitted.

**`enforce_admins: true` is the load-bearing change in this spelling**, and it
is the one that makes the rule real. It is also the one that makes D3.141 a
hard block rather than a caveat: with it set and no CI reporting, the sole
maintainer cannot merge and cannot bypass.

### 3c. The rollback, so it is not improvised under pressure

```bash
# ruleset spelling — find the id, then delete it
gh api repos/BBTChris/nix/rulesets --jq '.[] | "\(.id)\t\(.name)"'
gh api -X DELETE repos/BBTChris/nix/rulesets/<id>

# classic spelling — restore the bypass without discarding the rule
gh api -X DELETE repos/BBTChris/nix/branches/main/protection/enforce_admins
```

---

## 4. WHAT `cc` DID NOT DO, stated so the absence is not mistaken for an omission

* **No GitHub setting was written.** Four read-only `gh api` GETs, quoted above
  in full. `rulesets`, `branches/main/protection`,
  `.../protection/required_status_checks`, `actions/workflows`,
  `commits/main/check-runs`.
* **No workflow file was created.** Writing `.github/workflows/*.yml` into this
  tree would arm CI on the next push, which is the same outward-facing act as
  clicking the setting. The workflow that D3.141 needs is drafted in
  `downloads/RESULTS.md` for the operator, and deliberately not installed.
* **Nothing was pushed.** ARC 032 does not push; that is the operator's, per
  the arc brief.
