"""The Scoring process (risk spec §6.6) — sole writer of the ranking table.

`seam.py` is the frozen interface: the row shape, the publish side (owned by
this process alone), the consumers' read-only mirror, and the FCFS fallback.
Everything that computes an EMA lives behind it and nowhere else.
"""
