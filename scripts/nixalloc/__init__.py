"""`nixalloc` — the Allocator (§2, §10 Core 3), the PERMISSIVE side.

It sizes and it PROPOSES. It never gates, never reserves, never places, and
never writes canonical state (§2's authority split). Every number it reads
comes from the Limiter's published financial-picture snapshot through a
private read-only mirror (§12.7); it holds no copy of balance it maintains
itself, because a second maintainer of the same figure is a second authority
however read-only it claims to be.

`seam.py` is the FROZEN consumer-side interface: the mirror port, the
proposal it emits, the ranking-table READ port whose writer does not exist
yet (§6.6 is the Scoring process, R5), and the correlation buckets. It is
landed before any implementation so the mirror consumer, the sizing pathway
and the caps can be built independently against a settled boundary — see its
module docstring for the synchronous/asynchronous declaration and its
reasoning.

WHY THIS PACKAGE IMPORTS `nixrisk.seam` RATHER THAN RESTATING IT. The
snapshot the Allocator mirrors is the Limiter's own `FinancialPicture`, field
for field, under the Limiter's own version stamp. A parallel definition here
would be a second declaration of one wire contract, free to drift a field name
or a unit without any instrument noticing — the exact "second authority"
failure `directory_structure.md` states for `risks/`, one package over. There
is one definition and this package consumes it.
"""
