"""`nixrisk` — the Risk Engine / Limiter (§10 Core 2).

The firewall and the exit brake. Nothing reaches the broker without it (§12.5),
and it is the sole writer of Plane-1 financial truth (§9).

`seam.py` is the FROZEN interface between the gate pass, the reservation ledger
and the financial picture. It is landed before any implementation exists so the
three can be built independently against a settled boundary — see its module
docstring for the synchronous/asynchronous declaration and its reasoning.
"""
