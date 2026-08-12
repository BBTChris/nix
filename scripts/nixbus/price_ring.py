"""§12.7's SOLE shared-memory exception: the capture.py -> Risk Engine firehose.

Authority: `docs/nics_risk_subsystem_spec_v1.3.md` §12.7 (*"Sole exception — the
price firehose: capture.py -> Risk Engine per-tick bars/prices stay on the
**shared-memory single-writer ring buffer** (§10) — even ZeroMQ overhead is too
much per tick. **Strictly one writer by construction; prices only, never
financial state.**"*), §10's transport asymmetry, §11's hot-path discipline.

## THE EXCEPTION IS NARROW, AND THE NARROWNESS IS ENFORCED ELSEWHERE

This file is the only place in Nix permitted to touch shared memory.
`checks/check_price_ring.py` sweeps the tracked tree by AST for every
shared-memory construct and FAILS naming any file outside a tiny allow-list.
That gate is the enforcement; this docstring is only the claim.

Three sentences of §12.7 are three properties here, and each is falsifiable:

1. **"Strictly one writer by construction."** The segment header carries the
   writer's PID. A second writer attaching while that PID is alive is REFUSED
   with the incumbent named. It is not a convention and not a comment.
2. **"Prices only, never financial state."** The slot is a fixed 32-byte C
   struct — `venue_ts_ns`, `price`, `size`, `symbol_id` — with no variable-length
   field and no room for anything else. A financial table cannot be smuggled
   through a struct that has nowhere to put it.
3. **A ring drops; a ring that drops silently is worse than useless.** The reader
   returns `(ticks, dropped)`. Overrun is COUNTED and reported, never absorbed —
   a Risk Engine that silently missed ticks is `debug.md`'s vacuity class on the
   hot path.

## Venue timestamps, not local ones

`venue_ts_ns` is §2A:106 invariant 4's venue-sourced stamp, carried as integer
nanoseconds so the wire has no float rounding at the point a monotonic-by-source
guard compares two of them. The ring adds NO clock of its own: a consumer that
wants to know how long a tick sat in the buffer must get that from the sequence
numbers, not from a local stamp this module would have had to invent.

## THE RESIDUAL, NAMED — atomicity under CPython

The publish protocol is the standard single-producer release-store: fill slot
`seq % capacity`, then store `write_seq = seq + 1`. A reader re-reads `write_seq`
after copying a slot and discards the copy if the slot could have been recycled
underneath it, which is what turns a torn read into a counted drop rather than a
bad price.

**What is NOT claimed:** CPython gives no memory-ordering guarantee for
`struct.pack_into` against a `memoryview` of shared memory. The store to
`write_seq` is a single aligned 8-byte write and is in practice not torn on
x86-64, and the GIL is not a cross-process barrier. The protection here is the
re-check, not an ordering guarantee — and the re-check is what is tested. When
the Risk Engine exists and this becomes a genuine cross-process hot path, the
correct instrument is a C-level acquire/release or an `atomics` primitive, and
`docs/CHECK-DEBT.md` carries the row rather than this docstring carrying a
reassurance.
"""

from __future__ import annotations

import dataclasses
import os
import struct
from multiprocessing import shared_memory
from pathlib import Path

#: `/dev/shm/<name>` is where Linux materialises a POSIX shared-memory segment.
#: Named so a gate can observe the segment's real existence rather than trusting
#: this module's report of it.
# nosec B108 - `/dev/shm` is the POSIX shared-memory MOUNT, not a scratch
# directory. B108's heuristic keys on the `/dev/shm` literal because it is a
# world-writable path, and the finding does not apply: this is not a temp file
# whose name an attacker could predict and pre-create — it is where
# `shm_open(3)` puts every segment on Linux, it is the one place a segment CAN
# be, and the module refuses any segment there whose header it does not
# recognise (`PriceRingWriter._claim_segment`). Named site, one constant.
SHM_DIR = Path("/dev/shm")  # nosec B108

#: Segment name for the production firehose. One ring, one writer (capture.py).
DEFAULT_RING = "nix_price_ring"

_MAGIC = b"NIXRING\x00"
_VERSION = 1

#: magic | version | capacity | slot_size | writer_pid | write_seq | reserved
_HEADER = struct.Struct("<8sIIIIQQ")
# pylint: disable-next=invalid-name
_HEADER_SIZE = _HEADER.size
#: Offset of `write_seq` inside the header: 8-byte aligned, written alone.
_WRITE_SEQ_OFFSET = 8 + 4 + 4 + 4 + 4
_SEQ = struct.Struct("<Q")

#: venue_ts_ns | price | size | symbol_id | 4 bytes padding == 32 bytes.
_SLOT = struct.Struct("<qddI4x")
# pylint: disable-next=invalid-name
SLOT_SIZE = _SLOT.size

#: Slots in the production ring. Power of two so `% capacity` is a mask, and
#: large enough that a Risk Engine pause of a few milliseconds does not drop.
DEFAULT_CAPACITY = 65536


class PriceRingError(RuntimeError):
    """A ring operation failed. Always carries what could not be done."""


@dataclasses.dataclass(frozen=True)
class Tick:
    """One price observation. Prices only — §12.7 permits nothing else here."""

    symbol_id: int
    price: float
    size: float
    venue_ts_ns: int
    seq: int


def _pid_alive(pid: int) -> bool:
    """True when `pid` names a live process. `os.kill(pid, 0)` is the probe."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Someone else's process. It exists, which is the only question here.
        return True
    return True


def _attach(name: str, *, create: bool, size: int = 0) -> shared_memory.SharedMemory:
    """Open the segment. `track=False`: this module owns the lifetime, not the
    resource tracker, which would otherwise warn about a segment deliberately
    outliving the reader that attached to it."""
    try:
        return shared_memory.SharedMemory(
            name=name, create=create, size=size, track=False
        )
    except (OSError, ValueError) as exc:
        raise PriceRingError(f"shared segment {name!r}: {exc!r}") from exc


class PriceRingWriter:
    """capture.py's end. **The single writer**, enforced against the segment.

    `capacity` must be a power of two: the index is `seq & (capacity - 1)`, and a
    non-power-of-two would make the wrap arithmetic disagree with the reader's,
    which is a class of bug that shows up as impossible prices rather than as an
    error.
    """

    def __init__(
        self, name: str = DEFAULT_RING, capacity: int = DEFAULT_CAPACITY
    ) -> None:
        if capacity < 2 or capacity & (capacity - 1):
            raise PriceRingError(f"capacity {capacity} is not a power of two >= 2")
        self.name = name
        self.capacity = capacity
        self._seq = 0
        self.published = 0
        self._claim_segment()
        self._shm = _attach(name, create=True, size=_HEADER_SIZE + capacity * SLOT_SIZE)
        self._write_header()

    def _claim_segment(self) -> None:
        """Refuse a live incumbent; reclaim a dead one. Never silently coexists.

        FOUR states, and the fourth was a defect until it was named. Found by the
        sub-agent writing this module's unit tests, in review, before it could
        cost anything:

        * **no segment** — nothing to do.
        * **segment with a LIVE writer** — REFUSED, naming the PID. This is
          §12.7's *strictly one writer by construction*, and it holds when the
          incumbent is this same process too: a second `PriceRingWriter` on one
          ring is the same violation whoever opened it.
        * **segment with a DEAD writer** — a crashed capture.py leaves the
          segment behind (`/dev/shm` outlives the process). It is unlinked and
          recreated, because refusing here would mean a crash permanently
          disables the firehose until an operator ran `rm /dev/shm/...` — a
          blocking condition with no defined exit, which §12.8 forbids.
        * **segment that is NOT A PRICE RING AT ALL** — some other program's
          shared memory on the same name. **REFUSED.** The earlier version folded
          this into "dead writer" (`_incumbent` returned `(0, False)` for a bad
          magic *and* for a dead one) and then unlinked it, so this module could
          silently destroy data it had never identified. That is the one path in
          this file that deletes something, and it must not be reachable by
          anything but our own abandoned segment.
        """
        pid, alive, ours = self._incumbent()
        if pid is not None and not ours:
            raise PriceRingError(
                f"segment {self.name!r} exists and is NOT a v{_VERSION} price ring "
                "— refusing to unlink shared memory this module did not create. "
                "Pick another name, or remove it deliberately"
            )
        if alive:
            raise PriceRingError(
                f"segment {self.name!r} already has a LIVE writer pid={pid} — "
                "§12.7 requires STRICTLY ONE WRITER by construction, so this "
                "attach is refused rather than making the guarantee a convention"
            )
        if pid is not None:
            unlink_segment(self.name)

    def _incumbent(self) -> tuple[int | None, bool, bool]:
        """`(writer_pid, alive, is_price_ring)`; `(None, …)` when absent."""
        return _inspect(self.name)

    def _write_header(self) -> None:
        _HEADER.pack_into(
            self._shm.buf,
            0,
            _MAGIC,
            _VERSION,
            self.capacity,
            SLOT_SIZE,
            os.getpid(),
            0,
            0,
        )

    def publish(
        self, symbol_id: int, price: float, size: float, venue_ts_ns: int
    ) -> int:
        """Write one tick. Returns its sequence number. Never blocks, never drops
        on the write side — a full ring overwrites, and the READER reports it."""
        index = self._seq & (self.capacity - 1)
        _SLOT.pack_into(
            self._shm.buf,
            _HEADER_SIZE + index * SLOT_SIZE,
            int(venue_ts_ns),
            float(price),
            float(size),
            int(symbol_id),
        )
        self._seq += 1
        # Release store LAST: a reader must never see an advertised sequence for
        # a slot that has not been filled.
        _SEQ.pack_into(self._shm.buf, _WRITE_SEQ_OFFSET, self._seq)
        self.published += 1
        return self._seq - 1

    @property
    def write_seq(self) -> int:
        """Total ticks published since the segment was created."""
        return self._seq

    def close(self, *, unlink: bool = True) -> None:
        """Detach, and by default destroy the segment. Idempotent."""
        try:
            self._shm.close()
            if unlink:
                self._shm.unlink()
        except FileNotFoundError, BufferError, OSError:
            pass


class PriceRingReader:
    """The Risk Engine's end. Read-only, and it can say how much it missed."""

    def __init__(self, name: str = DEFAULT_RING, *, from_start: bool = False) -> None:
        self.name = name
        self._shm = _attach(name, create=False)
        magic, version, capacity, slot_size, self.writer_pid, write_seq, _ = (
            _HEADER.unpack_from(self._shm.buf, 0)
        )
        if magic != _MAGIC or version != _VERSION or slot_size != SLOT_SIZE:
            self._shm.close()
            raise PriceRingError(
                f"segment {name!r} is not a v{_VERSION} price ring "
                f"(magic={magic!r} version={version} slot_size={slot_size})"
            )
        self.capacity = capacity
        self.read_seq = 0 if from_start else write_seq
        self.dropped = 0
        self.torn = 0

    def _write_seq(self) -> int:
        return int(_SEQ.unpack_from(self._shm.buf, _WRITE_SEQ_OFFSET)[0])

    def _resync(self, write_seq: int) -> None:
        """Fast-forward past ticks the writer already recycled, COUNTING them."""
        behind = write_seq - self.read_seq
        if behind > self.capacity:
            self.dropped += behind - self.capacity
            self.read_seq = write_seq - self.capacity

    def poll(self, max_items: int = 4096) -> tuple[list[Tick], int]:
        """Drain up to `max_items` ticks. Returns `(ticks, dropped_this_call)`.

        `dropped_this_call` is not derivable from `len(ticks)` and is returned
        separately so a caller cannot get the ticks without being handed the
        gap — a consumer that ignores it has done so deliberately.
        """
        before = self.dropped
        write_seq = self._write_seq()
        self._resync(write_seq)
        ticks: list[Tick] = []
        while self.read_seq < write_seq and len(ticks) < max_items:
            tick = self._read_one(self.read_seq)
            self.read_seq += 1
            if tick is not None:
                ticks.append(tick)
            write_seq = self._write_seq()
            self._resync(write_seq)
        return ticks, self.dropped - before

    def _read_one(self, seq: int) -> Tick | None:
        """Copy one slot and DISCARD it if the writer could have recycled it."""
        index = seq & (self.capacity - 1)
        venue_ts_ns, price, size, symbol_id = _SLOT.unpack_from(
            self._shm.buf, _HEADER_SIZE + index * SLOT_SIZE
        )
        if self._write_seq() - seq > self.capacity:
            # The slot was overwritten between the release store we trusted and
            # this copy. The bytes in hand are a mix of two ticks.
            self.torn += 1
            self.dropped += 1
            return None
        return Tick(
            symbol_id=symbol_id,
            price=price,
            size=size,
            venue_ts_ns=venue_ts_ns,
            seq=seq,
        )

    def close(self) -> None:
        """Detach. Never unlinks — the reader does not own the segment."""
        try:
            self._shm.close()
        except BufferError, OSError:
            pass


def segment_exists(name: str = DEFAULT_RING) -> bool:
    """Is the segment materialised in `/dev/shm` right now? Kernel state."""
    return (SHM_DIR / name).exists()


def _inspect(name: str) -> tuple[int | None, bool, bool]:
    """`(writer_pid, alive, is_price_ring)` for a segment. Never raises.

    `pid is None` means the segment does not exist, which is a different fact
    from a segment whose header this module does not recognise — that one comes
    back `(0, False, False)` and is the state nothing may unlink.
    """
    try:
        shm = _attach(name, create=False)
    except PriceRingError:
        return None, False, False
    try:
        if shm.size < _HEADER_SIZE:
            return 0, False, False
        magic, version, _c, slot, pid, _w, _r = _HEADER.unpack_from(shm.buf, 0)
        if magic != _MAGIC or version != _VERSION or slot != SLOT_SIZE:
            return 0, False, False
        return pid, _pid_alive(pid), True
    finally:
        shm.close()


def unlink_segment(name: str) -> str:
    """Remove an abandoned price-ring segment. Returns '' or why it refused.

    **The only sanctioned way to clean up a ring from outside a live writer**,
    and it exists so that a caller needing to do so — a test's teardown, an
    operator script — does not have to reach for `multiprocessing.shared_memory`
    itself. §12.7 makes this module the SOLE shared-memory user in Nix, and a
    helper that forces every caller outside it to open a segment directly would
    have widened the exception by convenience. `checks/check_price_ring.py`
    enforces the narrowness, so this is not a stylistic preference.

    It refuses a segment that is not a v1 price ring, for the same reason
    `_claim_segment` does: this function deletes, and it may only delete
    something it has identified. A LIVE writer is NOT a refusal here — the
    caller may legitimately be cleaning up after a writer it owns — so the
    single-writer guarantee stays where it belongs, on the attach.
    """
    pid, _alive, ours = _inspect(name)
    if pid is None:
        return ""
    if not ours:
        return (
            f"{name!r} is not a v{_VERSION} price ring — refusing to unlink "
            "shared memory this module did not create"
        )
    try:
        stale = _attach(name, create=False)
    except PriceRingError as exc:
        return str(exc)
    try:
        stale.unlink()
    except (FileNotFoundError, OSError) as exc:
        return f"could not unlink {name!r}: {exc!r}"
    finally:
        stale.close()
    return ""
