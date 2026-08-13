#!/usr/bin/env python3
"""
monitor.py - Claude Code arc monitor TUI  (Nix / node02)

Read-only observer for a Claude Code job running in another terminal.
Reports phase, per-agent progress, ETAs, and 5h/weekly usage-limit pressure.

Stdlib only. Python 3.10+.  Ubuntu 26.04 LTS.

DOCTRINE
  Every gauge names its basis and sample size. A number with no denominator
  prints N/A, never a guess. Missing inputs fail LOUD (red DISCOVERY panel),
  never silently degrade to a green "0 problems" reading.

Usage:
  ./monitor.py                     # autodiscover
  ./monitor.py --pid 41822         # pin to a PID
  ./monitor.py --rate 2.0          # 2s repaint
  ./monitor.py --repo ~/nix        # repo root
  ./monitor.py --once              # single frame to stdout, no curses (CI/debug)
  ./monitor.py --selftest          # run internal consistency checks and exit
Hotkeys: q quit | + - rate | p pause | r force full probe | a ascii toggle
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from bisect import bisect_left
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_DIR = Path(os.path.expanduser("~/.config/nixmon"))
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "plan": "max5x",
    "weekly_reset_weekday": 4,        # Mon=0 .. Fri=4
    "weekly_reset_hour": 20,
    "weekly_reset_minute": 0,
    "rate": 1.0,
    "slow_probe_every": 5,            # paints between expensive probes
    "repo": "~/nix",
    "arc_dir": "~/nix/downloads",
    "claude_home": "~/.claude",
    "usage_snapshot": "~/.claude/nix-usage.json",
    "stall_seconds": 90,
    "ascii": False,
    # Calibration: high-water weighted-token marks observed at lockout.
    # Empty => bars render UNCALIBRATED (no percentage shown).
    "calib_5h": [],
    "calib_weekly": [],
    "seen_lockouts": [],
    # Seeds: denominators back-solved from a /usage reading (authoritative).
    "seed_5h": None,        # {"denom": float, "at": epoch}
    "seed_weekly": None,
    # Priors are placeholders only. Deliberately biased LOW (i.e. the bar reads
    # HIGH and warns early) because a prior biased the other way produces false
    # comfort, which is the worse failure. Always labelled PRIOR, never CALIB.
    # Max 5x, sonnet-weighted, heavy cache reads: order 3-5M wt per 5h window.
    "prior_5h": 3_500_000,
    "prior_weekly": 105_000_000,
}

# Weighted-token model. Proxy for quota consumption, not an official figure.
# Anthropic does not publish a local denominator; see README note.
MODEL_WEIGHT = {"opus": 5.0, "sonnet": 1.0, "haiku": 0.25, "unknown": 1.0}
TOK_WEIGHT = {
    "input_tokens": 1.0,
    "cache_creation_input_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
    "output_tokens": 5.0,
}

CTX_LIMIT = 200_000        # floor; auto-raised if observed usage exceeds it
CTX_TIERS = (200_000, 500_000, 1_000_000)
FIVE_HOURS = 5 * 3600
MIN_SPAN = 120.0        # s; below this no rate-derived ETA is credible
AGENT_IDLE_CUTOFF = 900.0   # s; sidechains quieter than this are shown ENDED
AGENT_SHOW_WINDOW = 1800.0  # s; agents with no activity in this window are
                            # HISTORY, not current — dropped from the panel


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            disk = json.loads(CONFIG_PATH.read_text())
            if isinstance(disk, dict):
                cfg.update({k: v for k, v in disk.items() if k in DEFAULT_CONFIG})
        except (json.JSONDecodeError, OSError):
            cfg["_config_error"] = f"unreadable: {CONFIG_PATH}"
    return cfg


def save_config(cfg: dict) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        out = {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG}
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(out, indent=2))
        tmp.replace(CONFIG_PATH)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# /proc probes  (no external deps; ps/ss not required)
# ---------------------------------------------------------------------------

# task-progress-bar --status-line emits e.g.:
#   Tasks [████░░░░░░] 30/61 (~16h 19m left) | ✓30 ⟳7 ○24
_TPB_COUNT = re.compile(r'(\d+)\s*/\s*(\d+)')
_TPB_ETA = re.compile(r'~\s*([0-9hms\s]+?)\s+left', re.I)
_TPB_TRIO = re.compile(r'\u2713\s*(\d+).*?\u27f3\s*(\d+).*?\u25cb\s*(\d+)')
_ETA_UNIT = re.compile(r'(\d+)\s*([hms])', re.I)


def _parse_tpb_eta(txt):
    total = 0
    for num, unit in _ETA_UNIT.findall(txt):
        u = unit.lower()
        total += int(num) * (3600 if u == 'h' else 60 if u == 'm' else 1)
    return float(total) if total else None


# Default location the claude-hud plugin writes its usage snapshot to, if the
# user set display.externalUsageWritePath. Overridable via --usage-snapshot.
USAGE_SNAPSHOT_DEFAULT = os.path.expanduser("~/.claude/nix-usage.json")
# Mirror the plugin's own freshness gate (externalUsageFreshnessMs default 5min):
# a stale snapshot is worse than none, so we ignore anything older than this.
USAGE_SNAPSHOT_MAX_AGE = 300.0     # <= this: shown live, no tag
USAGE_SNAPSHOT_STALE_MAX = 3600.0  # 5min..1hr: shown with a stale age tag;
#                                    older than this the value is dropped entirely.


def read_usage_snapshot(path=None, now=None):
    """Read claude-hud's external usage snapshot (real 5h/7d subscriber %).

    The snapshot is written by the claude-hud plugin from Claude Code's own
    stdin rate_limits (the authoritative server-computed numbers). We only read
    it - never write, never call the API - so there is zero quota cost. Returns
    a dict with fivehour/sevenday percentages + reset epochs, or None if the
    file is missing, malformed, or staler than the plugin's freshness window.
    Never raises.
    """
    import json as _json
    path = path or USAGE_SNAPSHOT_DEFAULT
    now = now if now is not None else time.time()
    try:
        with open(path, "r") as fh:
            d = _json.load(fh)
    except (OSError, ValueError):
        return None

    def _epoch(s):
        # ISO-8601 -> epoch seconds; tolerate trailing Z.
        if not isinstance(s, str) or not s:
            return None
        try:
            from datetime import datetime
            return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None

    ua = _epoch(d.get("updated_at"))
    if ua is None or (now - ua) > USAGE_SNAPSHOT_STALE_MAX:
        return None  # missing, unparseable, or too old to trust even labeled

    def _win(w):
        if not isinstance(w, dict):
            return (None, None)
        p = w.get("used_percentage")
        pct = float(p) if isinstance(p, (int, float)) else None
        return (pct, _epoch(w.get("resets_at")))

    fh_pct, fh_reset = _win(d.get("five_hour"))
    sd_pct, sd_reset = _win(d.get("seven_day"))
    if fh_pct is None and sd_pct is None:
        return None
    return {"five_pct": fh_pct, "five_reset": fh_reset,
            "seven_pct": sd_pct, "seven_reset": sd_reset,
            "updated_at": ua, "age": now - ua}


def read_task_progress(tasks_dir=None):
    """Read done/total/eta from `task-progress-bar --status-line`.

    This is Claude Code's own zero-token progress tracker (a PostToolUse hook on
    TodoWrite/TaskUpdate). It already computes done/total and an EMA-based ETA,
    so the monitor reads it rather than reconstructing a rate. Returns a dict or
    None if the tool is absent / emits nothing parseable. Never raises.
    """
    exe = shutil.which('task-progress-bar')
    if not exe:
        return None
    cmd = [exe, '--status-line']
    if tasks_dir:
        cmd += ['--tasks-dir', tasks_dir]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except (subprocess.SubprocessError, OSError):
        return None
    line = (r.stdout or '').strip()
    if not line:
        return None
    m = _TPB_COUNT.search(line)
    if not m:
        return None
    done, total = int(m.group(1)), int(m.group(2))
    out = {'done': done, 'total': total, 'raw': line[:200], 'eta': None,
           'in_progress': None, 'pending': None}
    me = _TPB_ETA.search(line)
    if me:
        out['eta'] = _parse_tpb_eta(me.group(1))
    mt = _TPB_TRIO.search(line)
    if mt:
        out['done'] = int(mt.group(1))
        out['in_progress'] = int(mt.group(2))
        out['pending'] = int(mt.group(3))
    return out


CLOCK_TICKS = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
PAGE_SIZE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _read(p: str) -> str | None:
    try:
        with open(p, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except (OSError, UnicodeDecodeError):
        return None


def boot_time() -> float:
    txt = _read("/proc/stat") or ""
    for line in txt.splitlines():
        if line.startswith("btime "):
            try:
                return float(line.split()[1])
            except (ValueError, IndexError):
                break
    return time.time()


_BOOT = boot_time()


def proc_table() -> dict[int, dict]:
    """Snapshot of all readable processes: pid -> {ppid,state,cmd,rss,start,utime}."""
    out: dict[int, dict] = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return out
    for e in entries:
        if not e.isdigit():
            continue
        pid = int(e)
        stat = _read(f"/proc/{pid}/stat")
        if not stat:
            continue
        # comm may contain spaces/parens; split on the LAST ')'
        try:
            rp = stat.rindex(")")
            comm = stat[stat.index("(") + 1:rp]
            fields = stat[rp + 2:].split()
            ppid = int(fields[1])
            utime = (int(fields[11]) + int(fields[12])) / CLOCK_TICKS
            starttime = int(fields[19]) / CLOCK_TICKS
            rss = int(fields[21]) * PAGE_SIZE
            state = fields[0]
        except (ValueError, IndexError):
            continue
        cmdline = _read(f"/proc/{pid}/cmdline") or ""
        cmd = cmdline.replace("\x00", " ").strip() or f"[{comm}]"
        out[pid] = {
            "pid": pid, "ppid": ppid, "comm": comm, "cmd": cmd,
            "state": state, "rss": rss, "cpu_time": utime,
            "start": _BOOT + starttime,
        }
    return out


CC_PATTERNS = (
    re.compile(r"(^|/)claude(\s|$)"),
    re.compile(r"@anthropic-ai/claude-code"),
    re.compile(r"/\.claude/local/"),
    re.compile(r"claude-code"),
)


def find_cc_pids(table: dict[int, dict]) -> list[int]:
    """Candidate Claude Code main processes, best-guess first."""
    hits = []
    for pid, p in table.items():
        cmd = p["cmd"]
        if any(pat.search(cmd) for pat in CC_PATTERNS):
            # exclude the monitor itself and obvious greps
            if "monitor.py" in cmd or cmd.startswith("grep") or "pgrep" in cmd:
                continue
            hits.append(pid)
    # Prefer the oldest (a long-running arc), then lowest pid for stability.
    hits.sort(key=lambda pid: (table[pid]["start"], pid))
    return hits


def descendants(table: dict[int, dict], root: int) -> list[dict]:
    kids: dict[int, list[int]] = {}
    for pid, p in table.items():
        kids.setdefault(p["ppid"], []).append(pid)
    out, stack = [], list(kids.get(root, []))
    seen = {root}
    while stack:
        pid = stack.pop()
        if pid in seen:
            continue
        seen.add(pid)
        if pid in table:
            out.append(table[pid])
            stack.extend(kids.get(pid, []))
    out.sort(key=lambda p: p["start"])
    return out


# --- sockets: map pid fds -> inode -> /proc/net/tcp rows ------------------

TCP_ESTABLISHED = "01"


def _net_tcp_rows() -> dict[str, tuple[str, int]]:
    """inode -> (state, remote_port)."""
    rows: dict[str, tuple[str, int]] = {}
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        txt = _read(path)
        if not txt:
            continue
        for line in txt.splitlines()[1:]:
            f = line.split()
            if len(f) < 10:
                continue
            try:
                rport = int(f[2].split(":")[1], 16)
            except (ValueError, IndexError):
                continue
            rows[f[9]] = (f[3], rport)
    return rows


def socket_state(pid: int) -> dict:
    """Count ESTABLISHED :443 sockets held by pid (proxy for API connection)."""
    res = {"tls443": 0, "total": 0, "readable": False}
    fddir = f"/proc/{pid}/fd"
    try:
        fds = os.listdir(fddir)
    except OSError:
        return res                      # not our process / no permission
    res["readable"] = True
    inodes = []
    for fd in fds:
        try:
            tgt = os.readlink(f"{fddir}/{fd}")
        except OSError:
            continue
        if tgt.startswith("socket:["):
            inodes.append(tgt[8:-1])
    if not inodes:
        return res
    rows = _net_tcp_rows()
    for ino in inodes:
        row = rows.get(ino)
        if not row:
            continue
        res["total"] += 1
        if row[0] == TCP_ESTABLISHED and row[1] == 443:
            res["tls443"] += 1
    return res


def io_counters(pid: int) -> dict:
    txt = _read(f"/proc/{pid}/io")
    if not txt:
        return {}
    out = {}
    for line in txt.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            try:
                out[k.strip()] = int(v)
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# Transcript (JSONL) ingestion  -- incremental, byte-offset based
# ---------------------------------------------------------------------------

def _parse_ts(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        # heuristics: ms vs s
        return float(v) / 1000.0 if v > 1e11 else float(v)
    if isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def _model_family(model: str | None) -> str:
    m = (model or "").lower()
    for fam in ("opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return "unknown"


def weighted(usage: dict, model: str | None) -> float:
    if not isinstance(usage, dict):
        return 0.0
    raw = 0.0
    for k, w in TOK_WEIGHT.items():
        v = usage.get(k)
        if isinstance(v, (int, float)):
            raw += float(v) * w
    return raw * MODEL_WEIGHT[_model_family(model)]


LIMIT_HIT_RE = re.compile(
    r"(usage limit reached|rate.?limit|limit will reset|429)", re.I
)


class Transcript:
    """Incrementally tails every session JSONL under ~/.claude/projects."""

    def __init__(self, claude_home: Path):
        self.home = claude_home
        self.projects = claude_home / "projects"
        self.todos = claude_home / "todos"
        self.offsets: dict[str, int] = {}
        self.inodes: dict[str, int] = {}
        # events: (ts, wtok, model, kind, session, payload)
        self.events: list[dict] = []
        self.ts_index: list[float] = []
        self.sessions: dict[str, dict] = {}
        self.parse_errors = 0
        self.files_seen = 0
        self.last_scan = 0.0
        self.discovery_error: str | None = None

    # -- discovery ---------------------------------------------------------
    def check(self) -> str | None:
        if not self.home.exists():
            self.discovery_error = f"NOT FOUND: {self.home}"
        elif not self.projects.exists():
            self.discovery_error = f"NOT FOUND: {self.projects}"
        else:
            self.discovery_error = None
        return self.discovery_error

    def _files(self) -> list[Path]:
        if not self.projects.exists():
            return []
        try:
            return sorted(self.projects.rglob("*.jsonl"))
        except OSError:
            return []

    # -- ingest ------------------------------------------------------------
    def scan(self) -> None:
        self.check()
        files = self._files()
        self.files_seen = len(files)
        new = []
        for fp in files:
            key = str(fp)
            try:
                st = fp.stat()
            except OSError:
                continue
            # rotation / truncation guard
            prev_ino = self.inodes.get(key)
            if prev_ino is not None and prev_ino != st.st_ino:
                self.offsets[key] = 0
            self.inodes[key] = st.st_ino
            off = self.offsets.get(key, 0)
            if st.st_size < off:
                off = 0                       # truncated / rewritten
                self.offsets[key] = 0         # persist the rewind
            if st.st_size == off:
                continue
            try:
                with open(fp, "rb") as fh:
                    fh.seek(off)
                    chunk = fh.read(st.st_size - off)
            except OSError:
                continue
            # only consume complete lines
            cut = chunk.rfind(b"\n")
            if cut == -1:
                continue
            self.offsets[key] = off + cut + 1
            for line in chunk[:cut].split(b"\n"):
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line.decode("utf-8", "replace"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self.parse_errors += 1
                    continue
                ev = self._to_event(rec, fp)
                if ev:
                    new.append(ev)
        if new:
            self.events.extend(new)
            self.events.sort(key=lambda e: e["ts"])
            self.ts_index = [e["ts"] for e in self.events]
        self.last_scan = time.time()

    def _to_event(self, rec: dict, fp: Path) -> dict | None:
        if not isinstance(rec, dict):
            return None
        ts = _parse_ts(rec.get("timestamp") or rec.get("ts"))
        if ts is None:
            return None
        sid = rec.get("sessionId") or fp.stem
        msg = rec.get("message") if isinstance(rec.get("message"), dict) else {}
        model = msg.get("model") or rec.get("model")
        usage = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
        wt = weighted(usage, model)

        tools, texts, limit_hit = [], [], False
        content = msg.get("content")
        if isinstance(content, list):
            for blk in content:
                if not isinstance(blk, dict):
                    continue
                bt = blk.get("type")
                if bt == "tool_use":
                    tools.append({
                        "name": blk.get("name", "?"),
                        "input": blk.get("input") if isinstance(blk.get("input"), dict) else {},
                    })
                elif bt in ("text", "thinking"):
                    t = blk.get("text") or blk.get("thinking") or ""
                    if isinstance(t, str):
                        texts.append(t)
                elif bt == "tool_result":
                    c = blk.get("content")
                    if isinstance(c, str):
                        texts.append(c)
                    elif isinstance(c, list):
                        for sub in c:
                            if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                texts.append(sub["text"])
        elif isinstance(content, str):
            texts.append(content)

        blob = "\n".join(texts)
        if blob and LIMIT_HIT_RE.search(blob[:4000]):
            limit_hit = True

        # context size: prefer explicit, else input+cache as a floor
        ctx = 0
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            v = usage.get(k)
            if isinstance(v, (int, float)):
                ctx += int(v)

        sess = self.sessions.setdefault(sid, {
            "id": sid, "file": str(fp), "first": ts, "last": ts,
            "wtok": 0.0, "ctx": 0, "sidechain": bool(rec.get("isSidechain")),
            "tools": 0, "last_tool": None, "msgs": 0, "parent": rec.get("parentUuid"),
        })
        sess["last"] = max(sess["last"], ts)
        sess["first"] = min(sess["first"], ts)
        sess["wtok"] += wt
        sess["msgs"] += 1
        sess["sidechain"] = sess["sidechain"] or bool(rec.get("isSidechain"))
        if ctx:
            sess["ctx"] = max(sess["ctx"], ctx)
        if tools:
            sess["tools"] += len(tools)
            sess["last_tool"] = tools[-1]["name"]

        return {
            "ts": ts, "wtok": wt, "model": model, "session": sid,
            "type": rec.get("type") or msg.get("role") or "?",
            "tools": tools, "ctx": ctx, "limit_hit": limit_hit,
            "text": blob[:2000], "sidechain": bool(rec.get("isSidechain")),
        }

    # -- queries -----------------------------------------------------------
    def since(self, t0: float) -> list[dict]:
        i = bisect_left(self.ts_index, t0)
        return self.events[i:]

    def wtok_since(self, t0: float) -> float:
        return sum(e["wtok"] for e in self.since(t0))

    def last_event_ts(self) -> float | None:
        return self.ts_index[-1] if self.ts_index else None

    def last_tool_call(self) -> tuple[float, str] | None:
        for e in reversed(self.events):
            if e["tools"]:
                return e["ts"], e["tools"][-1]["name"]
        return None

    def limit_hits(self) -> list[float]:
        return [e["ts"] for e in self.events if e["limit_hit"]]

    # -- todos -------------------------------------------------------------
    def read_todos(self) -> list[dict]:
        """One entry per todo file (agent). Denominator is agent-authored."""
        out = []
        if not self.todos.exists():
            return out
        try:
            files = sorted(self.todos.glob("*.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return out
        for fp in files[:24]:
            try:
                data = json.loads(fp.read_text())
                mt = fp.stat().st_mtime
            except (OSError, json.JSONDecodeError):
                self.parse_errors += 1
                continue
            items = data if isinstance(data, list) else data.get("todos", [])
            if not isinstance(items, list) or not items:
                continue
            done = sum(1 for i in items
                       if isinstance(i, dict) and i.get("status") == "completed")
            active = next((i.get("content") or i.get("activeForm", "")
                           for i in items
                           if isinstance(i, dict) and i.get("status") == "in_progress"), None)
            out.append({
                "file": fp.name, "stem": fp.stem, "mtime": mt,
                "done": done, "total": len(items), "active": active,
            })
        return out


# ---------------------------------------------------------------------------
# Usage limits
# ---------------------------------------------------------------------------

def five_hour_window(ts_index: list[float], now: float) -> tuple[float | None, float | None]:
    """
    Returns (anchor, reset_at) for the active rolling 5h window, or (None, None)
    if no window is currently open (i.e. a fresh allowance).

    Model: the window anchors on the first message sent after any >=5h gap and
    rolls from there. Documented behaviour: window starts at first prompt.
    """
    if not ts_index:
        return None, None
    anchor = ts_index[0]
    for t in ts_index:
        if t >= anchor + FIVE_HOURS:
            anchor = t
    reset = anchor + FIVE_HOURS
    if now >= reset:
        return None, None
    return anchor, reset


def weekly_window(cfg: dict, now: float) -> tuple[float, float]:
    """
    Weekly cap resets at a FIXED account-specific wall-clock time (local tz),
    not on a rolling 7-day sum. Returns (period_start, next_reset).
    """
    wd = int(cfg["weekly_reset_weekday"])
    hh = int(cfg["weekly_reset_hour"])
    mm = int(cfg["weekly_reset_minute"])
    dt = datetime.fromtimestamp(now).astimezone()
    cand = dt.replace(hour=hh, minute=mm, second=0, microsecond=0)
    delta = (wd - cand.weekday()) % 7
    cand = cand + timedelta(days=delta)
    if cand.timestamp() <= now:
        cand = cand + timedelta(days=7)
    nxt = cand.timestamp()
    return nxt - 7 * 86400, nxt


class Gauge:
    """A bar whose percentage exists only when a real denominator exists."""

    __slots__ = ("used", "denom", "basis", "n", "spread", "seeded_at")

    def __init__(self, used: float, denom: float | None,
                 basis: str, n: int = 0, spread: float = 0.0):
        self.used, self.denom = used, denom
        self.basis, self.n, self.spread = basis, n, spread
        self.seeded_at = None

    @property
    def pct(self) -> float | None:
        if not self.denom or self.denom <= 0:
            return None
        return 100.0 * self.used / self.denom

    @property
    def calibrated(self) -> bool:
        """True when the denominator came from a real observation, not a guess."""
        return self.basis in ("calib", "seed")

    def basis_label(self, now: float) -> str:
        if self.basis == "calib":
            return "calib n=%d" % self.n
        if self.basis == "seed":
            age = (now - self.seeded_at) if self.seeded_at else None
            return "seed " + (fmt_dur(age, True) + " old" if age else "")
        return "PRIOR"


def build_gauge(used: float, samples: list, prior: float, label: str,
                seed: dict | None = None) -> Gauge:
    """Denominator precedence: observed lockouts > /usage seed > prior.

    Lockout samples are ground truth (the cap actually fired). A seed is
    back-solved from an authoritative /usage reading but ages. A prior is a
    placeholder and is never presented as a measurement.
    """
    vals = [float(v) for v in samples
            if isinstance(v, (int, float)) and v > 0]
    if vals:
        denom = sum(vals) / len(vals)
        lo, hi = min(vals), max(vals)
        spread = 100.0 * (hi - lo) / denom / 2 if denom else 0.0
        return Gauge(used, denom, "calib", len(vals), spread)
    if isinstance(seed, dict):
        d = seed.get("denom")
        if isinstance(d, (int, float)) and d > 0:
            g = Gauge(used, float(d), "seed", 1, 0.0)
            g.seeded_at = seed.get("at")
            return g
    return Gauge(used, prior if prior > 0 else None, "prior", 0, 0.0)


# ---------------------------------------------------------------------------
# Arc file / repo
# ---------------------------------------------------------------------------

RUN_SUMMARY_RE = re.compile(
    r"===\s*RUN SUMMARY\s*:(?P<name>[^,]+),\s*Estimated run time\s*:\s*"
    r"(?P<eta>[^,]+),\s*completes\s*(?P<pct>[^=]*)===", re.I)
DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours|m|min|mins|minute|minutes)", re.I)
CHECK_RE = re.compile(r"check_[a-z0-9_]+\.py", re.I)
CRITERION_RE = re.compile(r"^\s*(?:[-*]\s*\[[ xX]\]|SC-?\d+[.:)]|\d+\.\s)", re.M)


def parse_duration(text: str) -> float | None:
    total, found = 0.0, False
    for num, unit in DURATION_RE.findall(text):
        u = unit.lower()
        total += float(num) * (3600 if u.startswith("h") else 60)
        found = True
    return total if found else None


def read_arc(arc_dir: Path) -> dict:
    info = {"path": None, "name": None, "budget": None, "checks": [],
            "criteria": 0, "mtime": None, "error": None}
    if not arc_dir.exists():
        info["error"] = f"NOT FOUND: {arc_dir}"
        return info
    try:
        mds = [p for p in arc_dir.glob("*.md")
               if p.name.upper() not in ("RESULTS.MD", "SESSION.MD")]
        mds.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as exc:
        info["error"] = f"UNREADABLE: {exc}"
        return info
    if not mds:
        info["error"] = f"NO ARC .md IN {arc_dir}"
        return info
    fp = mds[0]
    try:
        txt = fp.read_text(errors="replace")
        info["mtime"] = fp.stat().st_mtime
    except OSError as exc:
        info["error"] = f"UNREADABLE: {fp.name} ({exc})"
        return info
    info["path"] = str(fp)
    info["name"] = fp.stem
    m = RUN_SUMMARY_RE.search(txt)
    if m:
        info["name"] = m.group("name").strip() or info["name"]
        info["budget"] = parse_duration(m.group("eta"))
    else:
        info["error"] = "no ===RUN SUMMARY=== line in arc file"
    info["checks"] = sorted(set(CHECK_RE.findall(txt)))
    info["criteria"] = len(CRITERION_RE.findall(txt))
    return info


def git_probe(repo: Path) -> dict:
    out = {"ok": False, "modified": 0, "ins": 0, "dels": 0,
           "last": None, "last_age": None, "branch": None, "error": None}
    if not (repo / ".git").exists():
        out["error"] = f"NOT A GIT REPO: {repo}"
        return out
    if not shutil.which("git"):
        out["error"] = "git not on PATH"
        return out

    def run(args, timeout=4):
        # -c safe.directory=* lets the probe read a repo git would otherwise
        # reject for "dubious ownership" (common when the monitor runs as a
        # different user than the repo owner). Read-only; changes nothing.
        base = ["git", "-c", "safe.directory=" + str(repo),
                "-c", "safe.directory=*", "-C", str(repo)]
        try:
            r = subprocess.run(base + args, capture_output=True, text=True,
                               timeout=timeout)
            if r.returncode == 0:
                return r.stdout
            run.last_err = (r.stderr or "").strip().splitlines()
            return None
        except (subprocess.SubprocessError, OSError) as e:
            run.last_err = [str(e)]
            return None
    run.last_err = []

    st = run(["status", "--porcelain"])
    if st is None:
        # surface the actual reason (first line) instead of a blank failure
        why = run.last_err[0] if run.last_err else "unknown error"
        # Bare repo / no working tree is a distinct, actionable failure: the
        # monitor is pointed at a .git dir or a bare mirror, not the checkout.
        low = why.lower()
        if "work tree" in low or "bare" in low:
            bare = run(["rev-parse", "--is-bare-repository"])
            top = run(["rev-parse", "--show-toplevel"])
            if top and top.strip():
                out["error"] = "repo has no worktree here; checkout at " + top.strip()
            else:
                out["error"] = ("BARE REPO at %s - point --repo at the working "
                                "checkout, not the .git dir" % repo)
        else:
            out["error"] = "git status failed: " + why[:60]
        return out
    out["ok"] = True
    out["modified"] = len([l for l in st.splitlines() if l.strip()])
    ds = run(["diff", "--shortstat", "HEAD"]) or ""
    mi = re.search(r"(\d+) insertion", ds)
    md = re.search(r"(\d+) deletion", ds)
    out["ins"] = int(mi.group(1)) if mi else 0
    out["dels"] = int(md.group(1)) if md else 0
    lg = run(["log", "-1", "--format=%s|%ct"])
    if lg and "|" in lg:
        subj, _, ct = lg.strip().rpartition("|")
        out["last"] = subj
        try:
            out["last_age"] = time.time() - int(ct)
        except ValueError:
            pass
    br = run(["rev-parse", "--abbrev-ref", "HEAD"])
    out["branch"] = br.strip() if br else None
    return out


def file_stat(p: Path) -> dict:
    try:
        st = p.stat()
        return {"exists": True, "mtime": st.st_mtime,
                "age": time.time() - st.st_mtime, "size": st.st_size}
    except OSError:
        return {"exists": False, "mtime": None, "age": None, "size": 0}


# ---------------------------------------------------------------------------
# State assembly
# ---------------------------------------------------------------------------

PHASE_DEAD = "DEAD"
PHASE_NOPROC = "NO PROCESS"
PHASE_TOOL = "EXECUTING TOOL"
PHASE_WAIT = "THINKING / API WAIT"
PHASE_STREAM = "STREAMING RESPONSE"
PHASE_IDLE = "IDLE - awaiting input"
PHASE_STALL = "STALLED"
PHASE_COMPACT = "LIKELY COMPACTING"
PHASE_DONE = "ARC COMPLETE"

INTERESTING = ("pytest", "python", "python3", "git", "ruff", "mypy", "bandit",
               "npm", "node", "rg", "grep", "make", "verify.py", "pip", "sh", "bash")
# Short-lived helpers spawned by Claude Code hooks/statusline. They flit in and
# out every keystroke and must never be reported as the active tool (this is why
# PHASE showed "task-progress-bar"/"2.1.231" garbage).
NOISE_PROCS = ("task-progress-bar", "statusline", "status-line")


class Monitor:
    def __init__(self, cfg: dict, args):
        self.cfg = cfg
        self.args = args
        self.repo = Path(os.path.expanduser(cfg["repo"])).resolve(strict=False)
        self.arc_dir = Path(os.path.expanduser(cfg["arc_dir"]))
        self.claude_home = Path(os.path.expanduser(cfg["claude_home"]))
        self.usage_snapshot_path = os.path.expanduser(
            getattr(args, "usage_snapshot", None) or cfg["usage_snapshot"])
        self.tx = Transcript(self.claude_home)
        self.pid: int | None = args.pid
        self.pinned = args.pid is not None
        self.start = time.time()
        self.slow_cache: dict = {}
        self.slow_tick = 0
        self.prev_io: dict = {}
        self.prev_cpu: tuple[float, float] | None = None
        self.agent_done: dict[str, float] = {}   # stem -> elapsed at completion
        self.agent_first_seen: dict[str, float] = {}  # stem -> first observed ts
        self.seen_limit_hits: set[int] = {
            int(v) for v in (cfg.get("seen_lockouts") or [])
            if isinstance(v, (int, float))}
        self.notes: list[str] = []
        self.arc_start_hint: float | None = None
        self.session_md = self.repo / "sessions" / "SESSION.md"

    # -- calibration -------------------------------------------------------
    def harvest_calibration(self) -> None:
        """On an observed limit-hit, bank the weighted total as a real denominator.

        Lockout timestamps are persisted so a monitor restart cannot re-bank the
        same event and silently inflate the calibration sample count.
        """
        dirty = False
        for ts in self.tx.limit_hits():
            key = int(ts)
            if key in self.seen_limit_hits:
                continue
            self.seen_limit_hits.add(key)
            dirty = True
            anchor, _ = five_hour_window(
                [t for t in self.tx.ts_index if t <= ts], ts)
            if anchor is None:
                continue
            used = sum(e["wtok"] for e in self.tx.events
                       if anchor <= e["ts"] <= ts)
            if used > 0:
                self.cfg["calib_5h"] = (self.cfg.get("calib_5h") or [])[-4:] + [used]
                self.notes.append(
                    f"calibrated 5h denom from lockout @{fmt_clock(ts)}")
        if dirty:
            self.cfg["seen_lockouts"] = sorted(self.seen_limit_hits)[-32:]
            save_config(self.cfg)

    # -- main --------------------------------------------------------------
    def collect(self, force_slow: bool = False) -> dict:
        now = time.time()
        s: dict = {"now": now, "notes": [], "discovery": [], "cfg": self.cfg}

        table = proc_table()

        # --- process ------------------------------------------------------
        if self.pinned and self.pid not in table:
            s["discovery"].append(f"pinned PID {self.pid} not running")
            self.pid = None
        if not self.pinned:
            cands = find_cc_pids(table)
            if self.pid not in table:
                self.pid = cands[0] if cands else None
            s["cc_candidates"] = len(cands)

        proc = table.get(self.pid) if self.pid else None
        s["pid"] = self.pid
        s["proc"] = proc
        if proc:
            s["uptime"] = now - proc["start"]
            if self.arc_start_hint is None:
                self.arc_start_hint = proc["start"]
            cpu_now = (proc["cpu_time"], now)
            if self.prev_cpu and now > self.prev_cpu[1]:
                s["cpu_pct"] = 100.0 * (cpu_now[0] - self.prev_cpu[0]) / (now - self.prev_cpu[1])
            else:
                s["cpu_pct"] = None
            self.prev_cpu = cpu_now
            kids = descendants(table, self.pid)
            s["children"] = kids
            def _noise(k):
                blob = (k["cmd"] + " " + k["comm"]).lower()
                return any(n in blob for n in NOISE_PROCS)
            real_kids = [k for k in kids if not _noise(k)]
            s["active_child"] = next(
                (k for k in reversed(real_kids)
                 if any(tok in k["cmd"].split(" ")[0] or tok in k["comm"]
                        for tok in INTERESTING)),
                real_kids[-1] if real_kids else None)
            s["sock"] = socket_state(self.pid)
            io = io_counters(self.pid)
            pio = self.prev_io.get(self.pid, {})
            s["io_delta"] = {k: io.get(k, 0) - pio.get(k, 0) for k in io} if pio else {}
            self.prev_io[self.pid] = io
        else:
            s.update(uptime=None, cpu_pct=None, children=[], active_child=None,
                     sock={"tls443": 0, "total": 0, "readable": False}, io_delta={})

        # --- transcript ---------------------------------------------------
        self.tx.scan()
        if self.tx.discovery_error:
            s["discovery"].append(f"transcript {self.tx.discovery_error}")
        if not self.tx.events and not self.tx.discovery_error:
            s["discovery"].append(
                f"transcript: 0 events from {self.tx.files_seen} jsonl file(s)")
        # self.harvest_calibration()  # DISABLED: misfires on non-lockout text,
        # produces false "calibrated 5h denom from lockout" lines and a bogus %.

        last_ts = self.tx.last_event_ts()
        s["last_event_age"] = (now - last_ts) if last_ts else None
        lt = self.tx.last_tool_call()
        s["last_tool"] = lt[1] if lt else None
        s["last_tool_age"] = (now - lt[0]) if lt else None
        s["jsonl_files"] = self.tx.files_seen

        # --- context ------------------------------------------------------
        # The main conversation holds the real context; sub-agent sidechains
        # carry almost none. Selecting by newest-activity alone picks a tiny
        # sub-agent; selecting by newest NON-sidechain skips CC's live session
        # when it carries isSidechain records (observed: reported 50% vs the
        # real 80%). So pick the recently-active session with the LARGEST ctx.
        main_sess = None
        if self.tx.sessions:
            # Largest ctx = the main conversation. Sub-agent sidechains never
            # accumulate meaningful context, so ctx is a reliable discriminator
            # regardless of the sidechain flag or which session logged most
            # recently. Tie-break on recency.
            main_sess = max(self.tx.sessions.values(),
                            key=lambda v: (v["ctx"], v["last"]))
        s["cur_session"] = main_sess["id"][:8] if main_sess else None
        s["cur_model"] = _model_family(
            next((e["model"] for e in reversed(self.tx.events)
                  if e.get("model") and e["session"] == (main_sess["id"] if main_sess else None)),
                 None)) if main_sess else None
        s["ctx_used"] = main_sess["ctx"] if main_sess else 0
        # Never render a >100% context bar: if observed usage exceeds the
        # assumed tier, the assumption is wrong, not the measurement.
        s["ctx_limit"] = next((c for c in CTX_TIERS if s["ctx_used"] <= c),
                              CTX_TIERS[-1])

        # --- limits -------------------------------------------------------
        anchor, reset5 = five_hour_window(self.tx.ts_index, now)
        used5 = self.tx.wtok_since(anchor) if anchor else 0.0
        wk_start, wk_reset = weekly_window(self.cfg, now)
        usedw = self.tx.wtok_since(wk_start)
        s["g5"] = build_gauge(used5, self.cfg.get("calib_5h") or [],
                              float(self.cfg["prior_5h"]), "5h",
                              self.cfg.get("seed_5h"))
        s["gw"] = build_gauge(usedw, self.cfg.get("calib_weekly") or [],
                              float(self.cfg["prior_weekly"]), "week",
                              self.cfg.get("seed_weekly"))
        s["reset5"] = reset5
        s["anchor5"] = anchor
        s["reset_week"] = wk_reset

        # burn rate over trailing 30m (falls back to window mean)
        win = 1800.0
        recent = self.tx.wtok_since(now - win)
        span = min(win, now - anchor) if anchor else win
        s["burn"] = (recent / span * 3600.0) if span > 0 else 0.0
        s["cap_eta"] = None
        s["cap_over"] = False
        if s["burn"] > 0:
            headroom = []
            for g in (s["g5"], s["gw"]):
                if not g.denom:
                    continue
                rem = g.denom - g.used
                if rem > 0:
                    headroom.append(rem / s["burn"] * 3600.0)
                else:
                    s["cap_over"] = True
            if s["cap_over"]:
                s["cap_eta"] = 0.0
            elif headroom:
                s["cap_eta"] = min(headroom)

        # --- todos / agents -----------------------------------------------
        todos = self.tx.read_todos()
        s["todos"] = todos
        s["agents"] = self.build_agents(todos, now, proc.get("start") if proc else None)
        s["has_sessions"] = bool(self.tx.sessions)
        s["task_progress"] = self.slow_cache.get("task_progress")
        s["usage_snapshot"] = self.slow_cache.get("usage_snapshot")
        s["parse_errors"] = self.tx.parse_errors   # after ALL parsing

        # --- slow probes ---------------------------------------------------
        self.slow_tick += 1
        every = max(1, int(self.cfg["slow_probe_every"]))
        if force_slow or self.slow_tick % every == 1 or not self.slow_cache:
            self.slow_cache = {
                "task_progress": read_task_progress(),
                "usage_snapshot": read_usage_snapshot(self.usage_snapshot_path),
                "git": git_probe(self.repo),
                "arc": read_arc(self.arc_dir),
                "results": file_stat(self.arc_dir / "RESULTS.md"),
                "session": file_stat(self.session_md),
                "at": now,
            }
        s.update(self.slow_cache)
        if s["arc"].get("error"):
            s["discovery"].append(f"arc: {s['arc']['error']}")
        if s["git"].get("error"):
            s["discovery"].append(f"git: {s['git']['error']}")

        # --- progress + ETA -------------------------------------------------
        s["progress"] = self.progress(s, now)
        s["phase"] = self.phase(s, now)
        s["notes"] = self.notes[-3:]
        return s

    # -- agents ------------------------------------------------------------
    def build_agents(self, todos: list[dict], now: float,
                     proc_start: float | None = None) -> list[dict]:
        # Horizon: an agent is "current" only if it was active within
        # AGENT_SHOW_WINDOW. A running process cannot own a sidechain that last
        # logged before the process itself started, so floor the horizon at
        # proc_start. Without this, every historical Task session across the
        # whole transcript surfaces here as a days-old ENDED "agent".
        horizon = now - AGENT_SHOW_WINDOW
        if proc_start is not None and proc_start > horizon:
            horizon = proc_start
        rows = []
        for t in todos:
            if t["mtime"] < horizon:
                continue
            elapsed = now - t["mtime"]
            complete = t["total"] > 0 and t["done"] == t["total"]
            if complete and t["stem"] not in self.agent_done:
                self.agent_done[t["stem"]] = elapsed
            # first time we ever saw this agent's todo: anchor its elapsed. This
            # under-measures if it began before the monitor started, so the
            # per-agent ETA is "since observed", not claimed exact.
            seen = self.agent_first_seen.setdefault(t["stem"], now)
            worked = now - seen
            eta = None
            if t["total"] and 0 < t["done"] < t["total"] and worked >= MIN_SPAN:
                eta = (t["total"] - t["done"]) / (t["done"] / worked)
            rows.append({
                "id": t["stem"][:8], "done": t["done"], "total": t["total"],
                "active": t["active"], "idle": elapsed, "complete": complete,
                "ended": False, "last_tool": None, "kind": "todo",
                "eta": eta, "worked": worked,
            })
        sidechains = [v for v in self.tx.sessions.values()
                      if v["sidechain"] and v["last"] >= horizon]
        # most-recent activity first, so live agents lead and stale ones are gone
        for sess in sorted(sidechains, key=lambda v: v["last"], reverse=True):
            idle = now - sess["last"]
            # sibling-prior ETA: once >=1 parallel agent has finished, the median
            # finished runtime predicts a still-running opaque sub-agent.
            sib = sorted(self.agent_done.values())
            eta = None
            if idle <= AGENT_IDLE_CUTOFF and sib:
                med = sib[len(sib) // 2]
                eta = max(0.0, med - (sess["last"] - sess["first"]))
            rows.append({
                "id": sess["id"][:8], "done": 0, "total": 0, "active": None,
                "idle": idle, "complete": False,
                "ended": idle > AGENT_IDLE_CUTOFF,
                "last_tool": sess["last_tool"], "kind": "sidechain",
                "elapsed": sess["last"] - sess["first"], "wtok": sess["wtok"],
                "eta": eta, "worked": sess["last"] - sess["first"],
            })
        return rows[:8]

    # -- ETA engines -------------------------------------------------------
    def progress(self, s: dict, now: float) -> dict:
        p: dict = {}
        # Arc elapsed != process uptime. `cc` may have been running for hours
        # across several arcs; the current arc began no earlier than the moment
        # its file was written to the arc dir. Taking the later of the two
        # anchors stops a long-lived process from inflating the span (and thus
        # deflating every rate derived from it).
        proc_start = s["proc"]["start"] if s.get("proc") else None
        arc_mtime = s["arc"].get("mtime")
        if proc_start and arc_mtime:
            arc_start, basis = max(proc_start, arc_mtime), (
                "arc file" if arc_mtime >= proc_start else "proc start")
        elif proc_start:
            arc_start, basis = proc_start, "proc start"
        elif arc_mtime:
            arc_start, basis = arc_mtime, "arc file"
        else:
            arc_start, basis = self.start, "monitor start"
        elapsed = max(0.0, now - arc_start)
        p["elapsed"] = elapsed
        p["elapsed_basis"] = basis
        p["arc_start"] = arc_start

        # Clock 1: declared budget
        budget = s["arc"].get("budget")
        p["budget"] = budget
        p["budget_rem"] = (budget - elapsed) if budget else None
        p["over_budget"] = bool(budget and elapsed > budget)

        # Clock 2: gate / criteria burn-down
        checks = s["arc"].get("checks") or []
        total_gates = len(checks)
        passed = pre_existing = 0
        for c in checks:
            for cand in (self.repo / "checks" / c, self.repo / c):
                try:
                    mt = cand.stat().st_mtime
                except OSError:
                    continue
                # Existence alone proves nothing: a check file left by an
                # EARLIER arc would otherwise be scored as this arc's work,
                # showing progress for gates nobody wrote. Only a file touched
                # at or after the arc anchor counts as landed.
                if mt >= arc_start - 2.0:
                    passed += 1
                else:
                    pre_existing += 1
                break
        p["gates"] = (passed, total_gates)
        p["gates_pre"] = pre_existing
        p["gate_eta"] = None
        p["gate_basis"] = "none"
        # A rate needs a credible observation span. Below MIN_SPAN any quotient
        # is an artifact of the monitor's own start time, not of the arc.
        credible = elapsed >= MIN_SPAN and s.get("proc") is not None
        if total_gates and passed > 0 and credible and passed < total_gates:
            rate = passed / elapsed
            p["gate_eta"] = (total_gates - passed) / rate if rate > 0 else None
            p["gate_basis"] = "FIRM" if passed >= 3 else "WIDE"
        elif total_gates and not credible:
            p["gate_basis"] = "warming" if s.get("proc") else "no proc"

        # Clock 3: todo burn-down over the CURRENT job's real span. The span is
        # measured from the earliest agent we have observed (self-scoped to this
        # run), NOT from the arc-file mtime, which can be stale or point at the
        # wrong arc. This is what makes a whole-job ETA actually appear.
        # Prefer Claude Code's own task-progress-bar hook (done/total + EMA ETA).
        # It is the authoritative, zero-token source and needs no rate warmup.
        tp = s.get("task_progress")
        if tp and tp.get("total"):
            done, total = tp["done"], tp["total"]
            p["todos"] = (done, total)
            p["todo_eta"] = tp.get("eta") if done < total else None
            p["job_span"] = MIN_SPAN  # source is authoritative; not span-gated
            p["eta_source"] = "task-progress-bar"
        else:
            done = sum(t["done"] for t in s["todos"])
            total = sum(t["total"] for t in s["todos"])
            p["todos"] = (done, total)
            p["todo_eta"] = None
            seens = [v for v in self.agent_first_seen.values()]
            job_span = (now - min(seens)) if seens else 0.0
            p["job_span"] = job_span
            if total and done and done < total and job_span >= MIN_SPAN:
                p["todo_eta"] = (total - done) / (done / job_span)
            p["eta_source"] = "observed"

        # Clock 4: sibling prior across finished parallel agents
        finished = sorted(self.agent_done.values())
        p["sibling_eta"] = None
        if finished:
            med = finished[len(finished) // 2]
            running = [a for a in s["agents"] if not a["complete"] and a["kind"] == "todo"]
            if running:
                p["sibling_eta"] = max(0.0, med - min(a["idle"] for a in running))
        p["sibling_n"] = len(finished)

        # headline = todos (self-authored denominator) if we have it, else the
        # tightest of the remaining measured clocks
        if p["todo_eta"]:
            src = "tpb" if p.get("eta_source") == "task-progress-bar" else "obs"
            p["eta"], p["eta_basis"] = p["todo_eta"], "%s %d/%d" % (src, done, total)
        else:
            cands = [(v, k) for k, v in (("gates", p["gate_eta"]),
                                         ("siblings", p["sibling_eta"])) if v]
            if cands:
                v, k = min(cands)
                p["eta"], p["eta_basis"] = v, k
            else:
                p["eta"], p["eta_basis"] = None, None
        return p

    # -- phase -------------------------------------------------------------
    def phase(self, s: dict, now: float) -> tuple[str, str]:
        res_age = s["results"]["age"]
        ses_age = s["session"]["age"]
        fresh_done = (res_age is not None and res_age < 120 and
                      ses_age is not None and ses_age < 300)
        if not s["proc"]:
            if fresh_done:
                return PHASE_DONE, "RESULTS.md + SESSION.md both fresh"
            if s.get("cc_candidates", 0) == 0:
                return PHASE_NOPROC, "no Claude Code process found"
            return PHASE_DEAD, "process gone, no completion markers"

        stall_t = float(self.cfg["stall_seconds"])
        child = s["active_child"]
        ev_age = s["last_event_age"]
        sock = s["sock"]["tls443"]
        ctx_frac = s["ctx_used"] / CTX_LIMIT if s["ctx_used"] else 0.0
        io = s["io_delta"] or {}
        io_moving = (io.get("read_bytes", 0) + io.get("write_bytes", 0)) > 0

        if child:
            age = now - child["start"]
            if age > stall_t and not io_moving and (ev_age or 0) > stall_t:
                return PHASE_STALL, f"{child['comm']} {fmt_dur(age)}, no io/events"
            return PHASE_TOOL, f"{child['comm']}: {short_cmd(child['cmd'], 46)}"

        if ev_age is not None and ev_age < 6 and sock:
            return PHASE_STREAM, f"{sock} TLS conn, transcript live"
        if sock:
            if ctx_frac > 0.85 and (ev_age or 0) > 45:
                return PHASE_COMPACT, f"ctx {ctx_frac:.0%}, {fmt_dur(ev_age)} silent"
            return PHASE_WAIT, f"{sock} TLS ESTAB :443, no child procs"
        if ev_age is not None and ev_age > stall_t:
            if fresh_done:
                return PHASE_DONE, "completion markers written"
            return PHASE_IDLE, f"no socket, {fmt_dur(ev_age)} since last event"
        return PHASE_WAIT, "no child, no socket yet"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_dur(sec: float | None, short: bool = False) -> str:
    if sec is None:
        return "--"
    sec = max(0.0, float(sec))
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m" if short else f"{h:02d}:{m:02d}:{s:02d}"
    if m:
        return f"{m}m{s:02d}s" if short else f"{m:02d}:{s:02d}"
    return f"{s}s"


def fmt_clock(ts: float | None) -> str:
    if ts is None:
        return "--:--"
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def fmt_reset(ts: float | None, now: float) -> str:
    if ts is None:
        return "n/a"
    dt = datetime.fromtimestamp(ts)
    rem = ts - now
    day = "" if rem < 86400 and dt.day == datetime.fromtimestamp(now).day else dt.strftime("%a ")
    return f"{day}{dt.strftime('%H:%M')} ({fmt_dur(rem, True)})"


def fmt_tok(v: float | None) -> str:
    if v is None:
        return "--"
    for unit, div in (("G", 1e9), ("M", 1e6), ("k", 1e3)):
        if abs(v) >= div:
            return f"{v/div:.1f}{unit}"
    return f"{v:.0f}"


def short_cmd(cmd: str, width: int) -> str:
    cmd = " ".join(cmd.split())
    if len(cmd) <= width:
        return cmd
    head = cmd.split(" ")[0].split("/")[-1]
    tail = cmd[-(width - len(head) - 4):]
    return f"{head} ..{tail}"


def clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: max(0, width - 1)] + "\u2026"


# ---------------------------------------------------------------------------
# Renderer  (pure: state -> list[list[(text, attr)]])
# ---------------------------------------------------------------------------

BOX_U = {"h": "\u2500", "v": "\u2502", "tl": "\u250c", "tr": "\u2510",
         "bl": "\u2514", "br": "\u2518", "lt": "\u251c", "rt": "\u2524",
         "f": "\u2588", "e": "\u2592", "dot": "\u25cf", "chk": "\u2713",
         "arw": "\u25b8", "warn": "\u26a0"}
BOX_A = {"h": "-", "v": "|", "tl": "+", "tr": "+", "bl": "+", "br": "+",
         "lt": "+", "rt": "+", "f": "#", "e": ".", "dot": "*", "chk": "v",
         "arw": ">", "warn": "!"}

A_DIM, A_NORM, A_HDR = "dim", "norm", "hdr"
A_OK, A_WARN, A_CRIT, A_INFO, A_ACCENT = "ok", "warn", "crit", "info", "accent"
# NIX wordmark, transcribed verbatim from /etc/update-motd.d/99-nix-banner
# (U+2588 FULL BLOCK glyphs, exact spacing). 24 cols x 6 rows.
NIX_LOGO = [
    '██      ██ ██ ██      ██',
    '████    ██ ██   ██  ██  ',
    '██  ██  ██ ██     ██    ',
    '██    ████ ██     ██    ',
    '██      ██ ██   ██  ██  ',
    '██      ██ ██ ██      ██',
]
_LOGO_W = max(len(r) for r in NIX_LOGO)
# Per-column gradient stops sampled off the reference artwork (pos%, R, G, B),
# copied from the banner's GRAD_STOPS. Amber -> orange -> pink -> magenta.
_LOGO_STOPS = [
    (0, 240, 144, 32), (18, 240, 112, 32), (50, 240, 64, 112),
    (68, 240, 64, 160), (85, 240, 64, 208), (100, 240, 64, 240),
]


def _logo_rgb(pos):
    """Interpolate the banner gradient at pos (0..100) -> (r,g,b)."""
    pos = max(0, min(100, pos))
    stops = _LOGO_STOPS
    pp, pr, pg, pb = stops[0]
    for sp, sr, sg, sb in stops:
        if pos <= sp:
            span = sp - pp
            if span <= 0:
                return sr, sg, sb
            f = pos - pp
            return (pr + (sr - pr) * f // span,
                    pg + (sg - pg) * f // span,
                    pb + (sb - pb) * f // span)
        pp, pr, pg, pb = sp, sr, sg, sb
    return stops[-1][1:]


# Precompute one truecolor SGR per column (logo width is fixed).
_LOGO_COL_SGR = []
for _c in range(_LOGO_W):
    _r, _g, _b = _logo_rgb(_c * 100 // (_LOGO_W - 1) if _LOGO_W > 1 else 0)
    _LOGO_COL_SGR.append("\033[1;38;2;{};{};{}m".format(_r, _g, _b))


class Renderer:
    def __init__(self, ascii_mode: bool = False):
        self.b = BOX_A if ascii_mode else BOX_U
        self.ascii = ascii_mode

    # -- primitives --------------------------------------------------------
    def bar(self, frac: float | None, width: int) -> str:
        # Splash-style: [████▒▒▒▒] - solid fill, medium-shade track, in brackets.
        # Brackets consume 2 cols so the inner cell count is width-2.
        if width <= 2:
            return ""
        inner = width - 2
        track = self.b["e"]           # medium shade so an unfilled bar is visible
        if frac is None:
            return "[" + track * inner + "]"
        n = max(0, min(inner, int(round(frac * inner))))
        return "[" + self.b["f"] * n + track * (inner - n) + "]"

    def rule(self, w: int, left: str, right: str, label: str = "",
             attr: str = A_DIM) -> list:
        """Returns a ROW (list of segments). Callers must use out.append()."""
        if label:
            lab = f" {label} "
            fill = max(0, w - 2 - len(lab))
            mid = lab + self.b["h"] * fill
        else:
            mid = self.b["h"] * max(0, w - 2)
        return [(left + mid[: max(0, w - 2)] + right, attr)]

    @staticmethod
    def fit(segs: list, width: int) -> tuple[list, int]:
        """Cumulatively clip a segment list to at most `width` chars.

        This is the SINGLE width guarantee for the frame. Per-field clipping is
        cosmetic; without a row-level fit, N fields each <= width can still sum
        past it and blow the box at narrow terminals.
        """
        out, used = [], 0
        for text, attr in segs:
            if used >= width:
                break
            take = width - used
            if len(text) <= take:
                out.append((text, attr))
                used += len(text)
            else:
                out.append((text[:take], attr))
                used = width
        return out, used

    def row(self, w: int, segs: list) -> list:
        inner = max(0, w - 2)
        segs, used = self.fit(segs, inner)
        return ([(self.b["v"], A_DIM)] + segs +
                [(" " * (inner - used), A_NORM), (self.b["v"], A_DIM)])

    # -- panels ------------------------------------------------------------
    def logo_row(self, r: int) -> list:
        """One row of the NIX wordmark. Block cells carry a per-column raw SGR
        (truecolor gradient from the banner); the char used is the box "fill"
        glyph so it also degrades under --ascii. Empty rows pad to logo width."""
        if r >= len(NIX_LOGO):
            return [(" " * _LOGO_W, A_NORM)]
        row = NIX_LOGO[r].ljust(_LOGO_W)
        glyph = "\u2588" if not self.ascii else "#"  # solid block, matches banner
        segs = []
        for x, ch in enumerate(row):
            if ch == "\u2588" or ch == "#":
                segs.append((glyph, ("\x1b" + _LOGO_COL_SGR[x][1:]) if not self.ascii
                             else A_ACCENT))
            else:
                segs.append((" ", A_NORM))
        # coalesce spaces for compactness
        out, run = [], ""
        for txt, attr in segs:
            if attr == A_NORM and out and out[-1][1] == A_NORM:
                out[-1] = (out[-1][0] + txt, A_NORM)
            else:
                out.append((txt, attr))
        return out

    def render(self, s: dict, w: int, h: int) -> list:
        w = max(60, w)
        b, out = self.b, []
        now = s["now"]
        cfg = s["cfg"]

        # header ------------------------------------------------------------
        rate = cfg["rate"]
        host = os.uname().nodename[:12]
        title = f"NIX MONITOR v{VERSION}"
        clock = datetime.fromtimestamp(now).strftime("%H:%M:%S")
        right = f"{clock} {rate:g}s{' PAUSED' if s.get('paused') else ''}"
        out.append(self.rule(w, b["tl"], b["tr"], f"{title} \u00b7 {host}"))
        arc = s["arc"]
        pid_s = f"PID {s['pid']}" if s["pid"] else "PID --"
        sess_id = s.get("cur_session")
        model = s.get("cur_model") or "?"
        ph, why = s["phase"]
        pattr = {PHASE_STALL: A_CRIT, PHASE_DEAD: A_CRIT, PHASE_NOPROC: A_CRIT,
                 PHASE_DONE: A_OK, PHASE_IDLE: A_WARN,
                 PHASE_COMPACT: A_WARN}.get(ph, A_INFO)

        # The header text lines (built once), placed to the RIGHT of the logo.
        text_rows = [
            [(clip(arc.get("name") or "no arc", 24), A_ACCENT),
             ("  ", A_NORM), (f"{pid_s:<11}", A_NORM),
             (f"up {fmt_dur(s.get('uptime')):<9}", A_NORM), (right, A_DIM)],
        ]
        if sess_id:
            text_rows.append([
                ("session ", A_DIM), (sess_id, A_ACCENT),
                ("  model ", A_DIM), (model, A_INFO), ("  ", A_NORM),
                (f"ctx {fmt_tok(s['ctx_used'])}/{fmt_tok(s.get('ctx_limit') or CTX_LIMIT)}", A_DIM)])
        text_rows.append([
            ("PHASE ", A_DIM), (b["arw"] + " ", pattr), (f"{ph}", pattr),
            (": ", A_DIM), (why, A_NORM)])

        # Logo occupies the left gutter; header text sits beside it. Only when
        # the terminal is wide enough (else fall back to plain stacked header).
        logo_cols = _LOGO_W + 2   # glyph width + a small gutter
        if w >= 92:
            nrows = max(len(NIX_LOGO), len(text_rows))
            # vertically center the (shorter) text block against the logo
            pad_top = (len(NIX_LOGO) - len(text_rows)) // 2
            for i in range(len(NIX_LOGO)):
                lseg = self.logo_row(i)
                ti = i - pad_top
                tseg = text_rows[ti] if 0 <= ti < len(text_rows) else []
                lseg_fit, lused = self.fit([(" ", A_NORM)] + lseg, logo_cols)
                gap = logo_cols - lused
                inner = max(0, w - 2)
                body, bused = self.fit(lseg_fit + [(" " * (gap + 1), A_NORM)] + tseg,
                                       inner)
                out.append([(b["v"], A_DIM)] + body
                           + [(" " * (inner - bused), A_NORM), (b["v"], A_DIM)])
        else:
            for tr in text_rows:
                out.append(self.row(w, [(" ", A_NORM)] + tr))

        # discovery failures --------------------------------------------------
        if s["discovery"]:
            out.append(self.rule(w, b["lt"], b["rt"], "DISCOVERY", A_CRIT))
            for d in s["discovery"][:4]:
                out.append(self.row(w, [(" " + b["warn"] + " ", A_CRIT),
                                        (clip(d, w - 6), A_CRIT)]))

        # two-column: progress | limits ---------------------------------------
        lw = (w - 3) // 2
        rw = w - 3 - lw
        out.append(self.rule(w, b["lt"], b["rt"], ""))
        left = self._progress_col(s, lw)
        rightc = self._limits_col(s, rw, now)
        for i in range(max(len(left), len(rightc))):
            lseg, lused = self.fit(left[i] if i < len(left) else [], lw)
            rseg, rused = self.fit(rightc[i] if i < len(rightc) else [], rw)
            out.append([(b["v"], A_DIM)] + lseg + [(" " * (lw - lused), A_NORM),
                       (b["v"], A_DIM)] + rseg + [(" " * (rw - rused), A_NORM),
                       (b["v"], A_DIM)])

        # (no usage-cap collision banner: real cap state is not knowable locally)

        # agents ---------------------------------------------------------------
        out.append(self.rule(w, b["lt"], b["rt"], "AGENTS"))
        agents = s["agents"]
        if not agents:
            msg = (" no agents active in this run"
                   if s.get("has_sessions") else " no todo/sidechain state found")
            out.append(self.row(w, [(msg, A_DIM)]))
        for a in agents[: max(1, h - 22)]:
            ended = a.get("ended")
            mark = b["chk"] if a["complete"] else ("-" if ended else b["dot"])
            mattr = A_OK if a["complete"] else (A_DIM if ended else A_INFO)
            if a["kind"] == "todo":
                cnt = f"{a['done']}/{a['total']}"
                bw = 10
                frac = a["done"] / a["total"] if a["total"] else None
                mid = self.bar(frac, bw)
            else:
                cnt = f"{fmt_tok(a.get('wtok'))}wt"
                mid = " " * 10
            stalled = (not a["complete"] and not ended and
                       a["idle"] > float(s["cfg"]["stall_seconds"]))
            eta = a.get("eta")
            if ended:
                tail = "ENDED " + fmt_dur(a["idle"], True) + " ago"
            elif stalled:
                tail = f"STALL {fmt_dur(a['idle'], True)}"
            else:
                label = clip(a["active"] or a["last_tool"] or "-", 18)
                tail = (f"~{fmt_dur(eta, True)} left  {label}" if eta is not None
                        else f"running  {label}")
            out.append(self.row(w, [
                (f" {mark} ", mattr), (f"{a['id']:<9}", A_NORM),
                (f"{cnt:>7} ", A_NORM), (mid, A_INFO),
                (f" {fmt_dur(a['idle'], True):>6} ", A_DIM),
                (clip(tail, max(0, w - 42)), A_CRIT if stalled else A_NORM),
            ]))

        # repo ------------------------------------------------------------------
        out.append(self.rule(w, b["lt"], b["rt"], "REPO / ARTIFACTS"))
        g = s["git"]
        if g.get("ok"):
            out.append(self.row(w, [
                (f" {g['modified']:>3} modified  ", A_NORM),
                (f"+{g['ins']}/-{g['dels']}", A_INFO),
                (f"  [{g.get('branch') or '?'}]  ", A_DIM),
                (clip("last: " + (g.get("last") or "-"), max(0, w - 40)), A_DIM),
            ]))
        else:
            out.append(self.row(w, [(" git: ", A_DIM),
                                    (clip(g.get("error") or "unavailable", w - 8), A_WARN)]))
        for lab, st in (("RESULTS.md", s["results"]), ("SESSION.md", s["session"])):
            if st["exists"]:
                fresh = st["age"] < 300
                out.append(self.row(w, [
                    (f" {lab:<11}", A_NORM),
                    (f"{fmt_dur(st['age'], True):>8} old  ", A_OK if fresh else A_DIM),
                    (f"{st['size']:>7} B", A_DIM),
                ]))
            else:
                out.append(self.row(w, [(f" {lab:<11}", A_NORM),
                                        ("MISSING", A_CRIT)]))

        # footer -------------------------------------------------------------
        if s.get("notes"):
            for n in s["notes"][-2:]:
                out.append(self.row(w, [(" * ", A_OK), (n, A_OK)]))
        foot = (f"q quit  +/- rate  p pause  r probe  a ascii  \u00b7  "
                f"jsonl {s['jsonl_files']} files, {s['parse_errors']} parse err")
        out.append(self.rule(w, b["bl"], b["br"], clip(foot, w - 6)))
        return out[:h] if h > 0 else out

    def _progress_col(self, s: dict, w: int) -> list:
        p, out = s["progress"], []
        bw = max(6, min(12, w - 26))
        out.append([(" PROGRESS", A_HDR)])
        # gates
        gp, gt = p["gates"]
        if gt:
            pre = p.get("gates_pre") or 0
            out.append([(" gates    ", A_NORM),
                        (self.bar(gp / gt, bw), A_INFO),
                        (f" {gp}/{gt} {gp / gt * 100:.0f}% ", A_NORM),
                        (f"{p['gate_basis']}", A_DIM),
                        (f" ({pre} pre)" if pre else "", A_DIM)])
        else:
            out.append([(" gates    ", A_NORM), (self.bar(None, bw), A_DIM),
                        (" N/A no denominator", A_WARN)])
        # tasks (Claude Code task-progress-bar) - authoritative; else plain todos
        tp = s.get("task_progress")
        td, tt = p["todos"]
        if tp and tp.get("total"):
            done, total = tp["done"], tp["total"]
            frac = done / total if total else None
            out.append([(" tasks    ", A_NORM), (self.bar(frac, bw), A_INFO),
                        (f" {done}/{total}" + (f" {frac * 100:.0f}%" if frac is not None else ""),
                         A_NORM)])
            ip = tp.get("in_progress")
            pd = tp.get("pending")
            if ip is not None and pd is not None:
                out.append([("          ", A_NORM),
                            (f"{self.b['chk']}{done} ", A_OK),
                            (f"{self.b['arw']}{ip} ", A_INFO),
                            (f"{self.b['e']}{pd}", A_DIM)])
        elif tt:
            out.append([(" todos    ", A_NORM), (self.bar(td / tt, bw), A_INFO),
                        (f" {td}/{tt} {td / tt * 100:.0f}%", A_NORM)])
        # context
        cu, cl = s["ctx_used"], s.get("ctx_limit") or CTX_LIMIT
        cf = cu / cl if cu else None
        cattr = A_CRIT if (cf or 0) > 0.9 else A_WARN if (cf or 0) > 0.75 else A_OK
        out.append([(" context  ", A_NORM), (self.bar(cf, bw), cattr),
                    (f" {fmt_tok(cu)}/{fmt_tok(cl)}", cattr),
                    (f" {cf * 100:.0f}%" if cf is not None else "", cattr)])
        # whole-job ETA (time remaining)
        if p["eta"]:
            out.append([(" JOB left ", A_NORM),
                        (f"{fmt_dur(p['eta'], True)} ", A_ACCENT),
                        (f"[{p['eta_basis']}]", A_DIM)])
        else:
            reason = ("N/A (span < %ds)" % int(MIN_SPAN)
                      if p.get("job_span", 0) < MIN_SPAN
                      else "N/A (no progress signal)")
            out.append([(" JOB left ", A_NORM), (reason, A_WARN)])
        # declared budget from the arc file, shown as a secondary reference
        if p.get("budget"):
            rem = p["budget"] - p["elapsed"]
            out.append([("  vs arc  ", A_DIM),
                        (("OVER +" + fmt_dur(-rem, True)) if rem < 0
                         else fmt_dur(rem, True) + " of budget", A_DIM)])
        out.append([(f" elapsed  {fmt_dur(p['elapsed'])} ", A_DIM),
                    (f"[{p.get('elapsed_basis', '?')}]", A_DIM)])
        return [[(clip(t, w), a) for t, a in row] for row in out]

    def _limits_col(self, s: dict, w: int, now: float) -> list:
        # Real 5h/weekly subscriber usage comes ONLY from the claude-hud plugin
        # snapshot (it persists Claude Code's own stdin rate_limits). When that
        # snapshot is present and fresh we show real, server-computed bars. When
        # it isn't, we show the measured token burn + reset clock and point at
        # CC's statusline - never a fabricated percentage.
        out = []
        bw = max(6, min(12, w - 30))
        snap = s.get("usage_snapshot")
        fresh = snap and snap.get("age", 0) <= USAGE_SNAPSHOT_MAX_AGE
        if snap and fresh:
            src = "  (usage: claude-hud snapshot)"
        elif snap:
            src = "  (usage: snapshot, stale)"
        else:
            src = "  (usage: see CC statusline)"
        out.append([(" LIMITS", A_HDR), (src if w >= 44 else "", A_DIM)])
        # a dim age tag appended to a stale bar so the number is never mistaken
        # for live; percentages here move slowly so a labelled 60% ·12m is useful.
        stale_tag = ""
        if snap and not fresh:
            stale_tag = " \u00b7" + fmt_dur(snap.get("age", 0), True)
        for lab, g, reset, pct, sreset in (
                ("5h", s["g5"], s["reset5"],
                 snap["five_pct"] if snap else None, snap and snap["five_reset"]),
                ("week", s["gw"], s["reset_week"],
                 snap["seven_pct"] if snap else None, snap and snap["seven_reset"])):
            if pct is not None:
                frac = min(1.0, pct / 100.0)
                base = (A_CRIT if pct >= 90 else A_WARN if pct >= 80
                        else A_INFO if pct >= 60 else A_OK)
                attr = base if fresh else A_DIM   # dim the whole row when stale
                out.append([(f" {lab:<5}", A_NORM), (self.bar(frac, bw), attr),
                            (f" {pct:.0f}%{stale_tag}", attr)])
                r = sreset if sreset else reset
                if r is not None:
                    out.append([("       reset ", A_DIM), (fmt_reset(r, now), A_NORM)])
            else:
                # no snapshot value -> honest token count, no fabricated bar
                out.append([(f" {lab:<5}", A_NORM),
                            (f" {fmt_tok(g.used)}wt used", A_DIM)])
                if reset is not None:
                    out.append([("       reset ", A_DIM), (fmt_reset(reset, now), A_NORM)])
        out.append([(f" burn  {fmt_tok(s['burn'])}wt/h", A_DIM)])
        if not snap:
            out.append([(" real 5h/weekly %: Claude Code statusline", A_DIM)])
        return [[(clip(t, w), a) for t, a in row] for row in out]


# ---------------------------------------------------------------------------
# Curses driver
# ---------------------------------------------------------------------------

def run_tui(mon: Monitor, cfg: dict) -> int:
    import curses

    def main(stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        pairs = {}
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
                bg = -1
            except curses.error:
                bg = curses.COLOR_BLACK
            spec = [(A_NORM, curses.COLOR_WHITE), (A_DIM, curses.COLOR_YELLOW),
                    (A_HDR, curses.COLOR_CYAN), (A_OK, curses.COLOR_GREEN),
                    (A_WARN, curses.COLOR_YELLOW), (A_CRIT, curses.COLOR_RED),
                    (A_INFO, curses.COLOR_CYAN), (A_ACCENT, curses.COLOR_MAGENTA)]
            for i, (name, col) in enumerate(spec, start=1):
                try:
                    curses.init_pair(i, col, bg)
                    pairs[name] = curses.color_pair(i)
                except curses.error:
                    pairs[name] = curses.A_NORMAL
            pairs[A_HDR] |= curses.A_BOLD
            pairs[A_CRIT] |= curses.A_BOLD
        attr_of = lambda a: pairs.get(a, curses.A_NORMAL)
        # Dynamic truecolor for logo gradient. Attr strings that start with ESC
        # are raw SGR ("\x1b[1;38;2;R;G;Bm"); map each unique color to its own
        # curses pair when the terminal can do it, else fall back to magenta.
        _dyn = {}
        _can_rgb = curses.has_colors() and getattr(curses, "can_change_color", lambda: False)() and curses.COLORS >= 256
        import re as _re
        _rgb_re = _re.compile(r"38;2;(\d+);(\d+);(\d+)")
        _next_slot = [max(1, len(pairs)) + 1]

        def _attr_for(a):
            if not (isinstance(a, str) and a.startswith("\x1b")):
                return pairs.get(a, curses.A_NORMAL)
            if a in _dyn:
                return _dyn[a]
            m = _rgb_re.search(a)
            if not m or not _can_rgb:
                _dyn[a] = pairs.get(A_ACCENT, curses.A_NORMAL) | curses.A_BOLD
                return _dyn[a]
            r, g, b = (int(v) for v in m.groups())
            try:
                slot = _next_slot[0]; _next_slot[0] += 1
                if slot >= curses.COLORS or slot >= curses.COLOR_PAIRS:
                    raise curses.error
                curses.init_color(slot, r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)
                curses.init_pair(slot, slot, bg)
                _dyn[a] = curses.color_pair(slot) | curses.A_BOLD
            except curses.error:
                _dyn[a] = pairs.get(A_ACCENT, curses.A_NORMAL) | curses.A_BOLD
            return _dyn[a]

        rend = Renderer(bool(cfg["ascii"]))
        paused = False
        last_collect = 0.0
        state = None
        force = True
        bell_at = 0.0

        while True:
            now = time.time()
            if not paused and (now - last_collect >= float(cfg["rate"]) or force):
                try:
                    state = mon.collect(force_slow=force)
                except Exception as exc:              # never let a probe kill the TUI
                    state = {"fatal": f"{type(exc).__name__}: {exc}"}
                last_collect, force = now, False
            if state is not None:
                state["paused"] = paused

            h, w = stdscr.getmaxyx()
            stdscr.erase()
            if state and "fatal" in state:
                try:
                    stdscr.addnstr(0, 0, "COLLECT FAILED: " + state["fatal"],
                                   w - 1, attr_of(A_CRIT))
                except curses.error:
                    pass
            elif state:
                lines = rend.render(state, w, h)
                for y, segs in enumerate(lines):
                    if y >= h:
                        break
                    x = 0
                    for text, a in segs:
                        if x >= w - 1:
                            break
                        try:
                            stdscr.addnstr(y, x, text, max(0, w - 1 - x),
                                           _attr_for(a))
                        except curses.error:
                            pass
                        x += len(text)
                # audible warning once per 60s at >=90%
                g5 = state.get("g5")
                if g5 is not None and (g5.pct or 0) >= 90 and now - bell_at > 60:
                    curses.beep()
                    bell_at = now
            stdscr.refresh()

            # input --------------------------------------------------------
            deadline = time.time() + min(0.25, float(cfg["rate"]))
            while time.time() < deadline:
                try:
                    ch = stdscr.getch()
                except curses.error:
                    ch = -1
                if ch == -1:
                    time.sleep(0.03)
                    continue
                if ch in (ord("q"), ord("Q"), 27):
                    return 0
                if ch in (ord("+"), ord("=")):
                    cfg["rate"] = min(30.0, round(float(cfg["rate"]) + 0.5, 1))
                    save_config(cfg)
                elif ch in (ord("-"), ord("_")):
                    cfg["rate"] = max(0.5, round(float(cfg["rate"]) - 0.5, 1))
                    save_config(cfg)
                elif ch in (ord("p"), ord("P")):
                    paused = not paused
                elif ch in (ord("r"), ord("R")):
                    force = True
                elif ch in (ord("a"), ord("A")):
                    cfg["ascii"] = not cfg["ascii"]
                    rend = Renderer(bool(cfg["ascii"]))
                    save_config(cfg)
                elif ch == curses.KEY_RESIZE:
                    pass
                break

    try:
        return curses.wrapper(main) or 0
    except KeyboardInterrupt:
        return 0


# ---------------------------------------------------------------------------
# Plain / selftest modes
# ---------------------------------------------------------------------------

def run_once(mon: Monitor, cfg: dict, width: int | None = None) -> int:
    s = mon.collect(force_slow=True)
    w = width or shutil.get_terminal_size((100, 40)).columns
    rend = Renderer(bool(cfg["ascii"]))
    for segs in rend.render(s, w, 10_000):
        parts = []
        for txt, a in segs:
            if isinstance(a, str) and a.startswith("\x1b"):
                parts.append(a + txt + "\x1b[0m")
            else:
                parts.append(txt)
        sys.stdout.write("".join(parts) + "\n")
    return 0


def selftest() -> int:
    """Internal consistency checks. Exit 0 PASS / 1 FAIL."""
    fails = []

    def chk(name, cond, detail=""):
        if not cond:
            fails.append(f"{name}: {detail}")

    # 5h window
    t0 = 1_700_000_000.0
    ts = [t0, t0 + 60, t0 + 120]
    a, r = five_hour_window(ts, t0 + 200)
    chk("5h anchor", a == t0, f"{a}")
    chk("5h reset", r == t0 + FIVE_HOURS, f"{r}")
    a, r = five_hour_window(ts, t0 + FIVE_HOURS + 1)
    chk("5h expired", a is None and r is None, f"{a},{r}")
    ts2 = [t0, t0 + FIVE_HOURS + 10, t0 + FIVE_HOURS + 20]
    a, _ = five_hour_window(ts2, t0 + FIVE_HOURS + 30)
    chk("5h reanchor", a == t0 + FIVE_HOURS + 10, f"{a}")
    chk("5h empty", five_hour_window([], t0) == (None, None))

    # weekly: Friday 20:00 local
    cfg = dict(DEFAULT_CONFIG)
    for probe in (datetime(2026, 8, 13, 9, 0), datetime(2026, 8, 14, 19, 59),
                  datetime(2026, 8, 14, 20, 1), datetime(2026, 8, 16, 3, 0)):
        st, nx = weekly_window(cfg, probe.timestamp())
        d = datetime.fromtimestamp(nx)
        chk("weekly weekday", d.weekday() == 4, f"{d}")
        chk("weekly hour", (d.hour, d.minute) == (20, 0), f"{d}")
        chk("weekly future", nx > probe.timestamp(), f"{d}")
        chk("weekly span", abs((nx - st) - 7 * 86400) < 1, f"{nx-st}")

    # gauge honesty
    g = build_gauge(100.0, [], 0, "x")
    chk("no denom -> no pct", g.pct is None)
    g = build_gauge(50.0, [], 200.0, "x")
    chk("prior pct", abs(g.pct - 25.0) < 1e-9 and not g.calibrated)
    g = build_gauge(50.0, [100.0, 200.0], 999, "x")
    chk("calib pct", abs(g.pct - 33.333) < 0.01 and g.calibrated and g.n == 2)
    g = build_gauge(25.0, [], 999, "x", {"denom": 100.0, "at": 1.0})
    chk("seed used over prior", abs(g.pct - 25.0) < 1e-9 and g.basis == "seed")
    chk("seed counts as calibrated", g.calibrated)
    g = build_gauge(25.0, [50.0], 999, "x", {"denom": 100.0, "at": 1.0})
    chk("calib beats seed", g.basis == "calib" and abs(g.pct - 50.0) < 1e-9)
    g = build_gauge(25.0, [], 999, "x", {"denom": 0})
    chk("bad seed falls back to prior", g.basis == "prior")
    g = build_gauge(25.0, [], 999, "x", "not a dict")
    chk("junk seed tolerated", g.basis == "prior")
    chk("basis_label prior", build_gauge(1, [], 9, "x").basis_label(0) == "PRIOR")

    # weighted tokens
    w1 = weighted({"input_tokens": 1000, "output_tokens": 100}, "claude-opus-4")
    w2 = weighted({"input_tokens": 1000, "output_tokens": 100}, "claude-sonnet-4")
    chk("opus weight", abs(w1 - w2 * 5.0) < 1e-6, f"{w1} {w2}")
    chk("bad usage", weighted(None, "opus") == 0.0)
    chk("junk usage", weighted({"input_tokens": "x"}, "opus") == 0.0)

    # duration parsing
    chk("dur 45m", parse_duration("45m") == 2700)
    chk("dur 1h30m", parse_duration("1h30m") == 5400)
    chk("dur 2 hours", parse_duration("2 hours") == 7200)
    chk("dur none", parse_duration("soon") is None)

    # timestamp parsing
    chk("ts iso-Z",
        _parse_ts("2026-08-13T12:00:00Z") ==
        datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc).timestamp())
    chk("ts iso naive->utc",
        _parse_ts("2026-08-13T12:00:00") ==
        datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc).timestamp())
    chk("ts none", _parse_ts(None) is None)
    chk("ts junk", _parse_ts("not a date") is None)
    chk("ts epoch s", _parse_ts(1_700_000_000) == 1_700_000_000.0)
    chk("ts epoch ms", _parse_ts(1_700_000_000_000) == 1_700_000_000.0)

    # formatting
    chk("fmt_dur none", fmt_dur(None) == "--")
    chk("fmt_dur neg", fmt_dur(-5) == "0s")
    chk("fmt_tok", fmt_tok(1_500_000) == "1.5M")
    chk("clip", clip("abcdef", 4) == "abc\u2026")
    chk("clip 0", clip("abc", 0) == "")

    if fails:
        for f in fails:
            print("FAIL " + f)
        return 1
    print("SELFTEST PASS")
    return 0


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Claude Code arc monitor")
    ap.add_argument("--pid", type=int, help="pin to a PID instead of autodiscovery")
    ap.add_argument("--rate", type=float, help="repaint interval seconds")
    ap.add_argument("--repo", help="repo root (default ~/nix)")
    ap.add_argument("--arc-dir", help="arc/RESULTS dir (default ~/nix/downloads)")
    ap.add_argument("--claude-home", help="default ~/.claude")
    ap.add_argument("--usage-snapshot",
                    help="claude-hud external usage json (real 5h/7d usage)")
    ap.add_argument("--weekly", help="weekly reset, e.g. 'Fri 20:00'")
    ap.add_argument("--seed-5h", type=float, metavar="PCT",
                    help="anchor the 5h denominator from a /usage reading "
                         "(run /usage in the Claude Code pane, pass the %% shown)")
    ap.add_argument("--seed-week", type=float, metavar="PCT",
                    help="anchor the weekly denominator from a /usage reading")
    ap.add_argument("--clear-calib", action="store_true",
                    help="discard all learned denominators and seeds")
    ap.add_argument("--ascii", action="store_true", help="ASCII box drawing")
    ap.add_argument("--once", action="store_true", help="one frame to stdout")
    ap.add_argument("--width", type=int, help="width for --once")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    cfg = load_config()
    if args.rate:
        cfg["rate"] = max(0.2, args.rate)
    for k, v in (("repo", args.repo), ("arc_dir", args.arc_dir),
                 ("claude_home", args.claude_home)):
        if v:
            cfg[k] = v
    if args.ascii:
        cfg["ascii"] = True
    if args.weekly:
        days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        m = re.match(r"\s*([A-Za-z]{3})\w*\s+(\d{1,2}):(\d{2})", args.weekly)
        if m and m.group(1).lower() in days:
            cfg["weekly_reset_weekday"] = days.index(m.group(1).lower())
            cfg["weekly_reset_hour"] = int(m.group(2))
            cfg["weekly_reset_minute"] = int(m.group(3))
            save_config(cfg)
        else:
            print(f"bad --weekly '{args.weekly}'; expected e.g. 'Fri 20:00'",
                  file=sys.stderr)
            return 2

    if args.clear_calib:
        cfg.update(calib_5h=[], calib_weekly=[], seed_5h=None,
                   seed_weekly=None, seen_lockouts=[])
        save_config(cfg)
        print("calibration cleared")
        return 0

    mon = Monitor(cfg, args)

    if args.seed_5h is not None or args.seed_week is not None:
        s = mon.collect(force_slow=True)
        for pct, used_key, key, lab in (
                (args.seed_5h, "g5", "seed_5h", "5h"),
                (args.seed_week, "gw", "seed_weekly", "weekly")):
            if pct is None:
                continue
            if not 0.5 <= pct <= 100.0:
                print(f"--seed-{lab}: need a percentage in 0.5..100, got {pct}",
                      file=sys.stderr)
                return 2
            used = s[used_key].used
            if used <= 0:
                print(f"--seed-{lab}: no measured usage in the current window "
                      f"yet; cannot back-solve a denominator", file=sys.stderr)
                return 2
            denom = used / (pct / 100.0)
            cfg[key] = {"denom": denom, "at": time.time()}
            print(f"seeded {lab}: {fmt_tok(used)}wt = {pct}%  ->  "
                  f"denominator {fmt_tok(denom)}wt")
        save_config(cfg)
        return 0

    if args.once or not sys.stdout.isatty():
        return run_once(mon, cfg, args.width)
    return run_tui(mon, cfg)


if __name__ == "__main__":
    sys.exit(main())
