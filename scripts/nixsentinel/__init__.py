"""`nixsentinel` — the last-resort deadman (§12.1, §10 Core 4–5 shared pool).

A SEPARATE PACKAGE, and the separation is the safety property rather than
tidiness. §12.1 requires the Sentinel to be *"deliberately dumb, dependency-
minimal, [on a] separate code path (minimal common-mode failure)"*, and it fires
precisely when the Risk Engine is dead. A module living under `nixrisk/` would
share that package's import graph, so a defect that killed the Limiter — a bad
import, a config parse, a shared cache invariant — would take the Sentinel with
it. That is the definition of a common-mode failure, and §12.1 names avoiding it
as the reason this component exists in the shape it does.

**It is the ONE exception to §14's `execution of any flatten is Limiter-only`,
and the exception is narrow.** It flattens and it alerts. It does not arbitrate,
size, gate, reserve, publish a picture, or write Plane 1 directly — it writes a
local append-only marker that cold-start replays (§12.1's sole-writer fix).
Nothing else in this tree gains flatten authority by the fact that this package
holds it.

`seam.py` is the FROZEN interface, landed in ARC 034 Phase 0.6 before any
implementation, so the watchdog, the marker writer and the cold-start replay can
be built against a settled boundary. See its docstring for the synchronous /
asynchronous declaration and its reasoning — which DIVERGES from §2A's async
default, deliberately, and says why.
"""
