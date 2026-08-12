"""`nixbus` — the transport layer the risk spec locks in §10 and §12.7.

Three modules, and the split between them is the spec's own:

* `core_map` — §10's locked Process/Core Map, read as **running state**.
* `statebus` — §12.7's ZeroMQ PUB/SUB + snapshot-on-subscribe. **Everything
  stateful goes here.**
* `price_ring` — §12.7's *sole exception*: the capture.py -> Risk Engine price
  firehose on a single-writer shared-memory ring buffer. Prices only, never
  financial state.

The exception is narrow by construction and `checks/check_price_ring.py` proves
nothing else in the tree reaches for shared memory.
"""
