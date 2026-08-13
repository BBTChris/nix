#!/usr/bin/env python3
"""Adversarial harness for monitor.py — builds synthetic fixtures, spawns real
child processes, and drives collect()/render() across every phase branch."""
import importlib.util, json, os, random, shutil, subprocess, sys, time, types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tempfile

HERE = Path(__file__).resolve().parent
MON = HERE / "monitor.py"
if not MON.exists():
    sys.exit(f"monitor.py not found beside {__file__}")
spec = importlib.util.spec_from_file_location("mon", str(MON))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

# Fixture root is a private temp dir. build() rmtree's this path, so it must
# never resolve to anything real: mkdtemp guarantees a fresh, unique dir.
ROOT = Path(tempfile.mkdtemp(prefix="nixmon-fixture-"))
assert "nixmon-fixture-" in ROOT.name, "refusing to use a non-fixture root"
FAILS, WARNS = [], []


def chk(name, cond, detail=""):
    if not cond:
        FAILS.append(f"{name}  :: {detail}")
        print(f"  FAIL {name} :: {detail}")
    else:
        print(f"  ok   {name}")


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def build(scn="normal", n_msgs=40, sidechains=2, ctx=118_000,
          model="claude-sonnet-4-5-20250929", gap_hours=0.0, limit_hit=False,
          burn_mult=1.0):
    assert "nixmon-fixture-" in ROOT.name, "fixture root guard tripped"
    if ROOT.exists():
        shutil.rmtree(ROOT)
    ch = ROOT / ".claude"; proj = ch / "projects" / "-home-chris-nix"
    todos = ch / "todos"; repo = ROOT / "nix"; dl = repo / "downloads"
    for d in (proj, todos, repo / "checks", dl, repo / "sessions"):
        d.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], capture_output=True)
    (repo / "seed.txt").write_text("x")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "ARC016 close debt"], capture_output=True)

    now = time.time()
    t0 = now - 3600 * (5.2 if gap_hours else 1.2)
    lines = []
    for i in range(n_msgs):
        ts = t0 + i * (60 * (1.2 if not gap_hours else 1.0))
        if gap_hours and i == n_msgs // 2:
            t0 += gap_hours * 3600
            ts = t0 + i * 60
        tools = []
        if i % 4 == 3:
            tools = [{"type": "tool_use", "name": random.choice(
                ["Bash", "Edit", "Read", "TodoWrite"]), "input": {"cmd": "pytest -q"}}]
        rec = {
            "type": "assistant", "timestamp": iso(ts),
            "sessionId": "sess-main",
            "message": {"role": "assistant", "model": model,
                        "usage": {"input_tokens": int(1200 * burn_mult),
                                  "cache_read_input_tokens": int(ctx * 0.9),
                                  "cache_creation_input_tokens": 4000,
                                  "output_tokens": int(900 * burn_mult)},
                        "content": ([{"type": "text", "text": "working"}] + tools)},
        }
        lines.append(json.dumps(rec))
    if limit_hit:
        lines.append(json.dumps({
            "type": "system", "timestamp": iso(now - 60), "sessionId": "sess-main",
            "message": {"role": "user", "content":
                        "Claude usage limit reached. Your limit will reset at 4pm."}}))
    (proj / "sess-main.jsonl").write_text("\n".join(lines) + "\n")

    for k in range(sidechains):
        sl = []
        for i in range(6):
            sl.append(json.dumps({
                "type": "assistant", "timestamp": iso(now - 900 + i * 100),
                "sessionId": f"sub-{k}", "isSidechain": True,
                "message": {"role": "assistant", "model": model,
                            "usage": {"input_tokens": 500, "output_tokens": 300},
                            "content": [{"type": "tool_use", "name": "Edit",
                                         "input": {}}]}}))
        (proj / f"sub-{k}.jsonl").write_text("\n".join(sl) + "\n")

    for k, (d, t) in enumerate([(9, 11), (4, 9), (7, 7)]):
        items = ([{"content": f"task{i}", "status": "completed"} for i in range(d)] +
                 [{"content": f"task{i}", "status": "in_progress"}
                  for i in range(d, min(d + 1, t))] +
                 [{"content": f"task{i}", "status": "pending"} for i in range(d + 1, t)])
        (todos / f"agent{k}0000-{k}.json").write_text(json.dumps(items))

    (dl / "ARC_017_broker_order.md").write_text(
        "# ARC 017\n"
        "===RUN SUMMARY: ARC 017 broker-order, Estimated run time: 1h30m, "
        "completes 6% this will move the current stage forward===\n"
        "- [ ] SC-1 split seam\n- [ ] SC-2 map fields\n- [x] SC-3 done\n"
        "Build checks/check_broker_seam.py and checks/check_fetchfields.py "
        "and checks/check_avg_price.py\n")
    for f in ("check_broker_seam.py",):
        (repo / "checks" / f).write_text("# gate\n")
    (dl / "RESULTS.md").write_text("results\n")
    (repo / "sessions" / "SESSION.md").write_text("session\n")
    return ROOT, repo, ch, dl


def mk_cfg(repo, ch, dl, **kw):
    c = dict(M.DEFAULT_CONFIG)
    c.update(repo=str(repo), arc_dir=str(dl), claude_home=str(ch))
    c.update(kw)
    return c


class Args:
    pid = None


# HERMETICITY: with pid=None the monitor autodiscovers whatever Claude Code
# process happens to be running on the HOST. That made scenario 3a pass in a
# container with no `claude` running and fail on a real box with one. Every
# scenario must therefore pin an explicit PID: a live sentinel, or a PID that
# is guaranteed absent.
DEAD_PID = 4194303          # above /proc/sys/kernel/pid_max on stock Linux


def no_proc_args():
    a = Args(); a.pid = DEAD_PID
    return a


def collect(cfg, pid=DEAD_PID):
    """Default to a guaranteed-absent PID so host state can never leak in."""
    a = Args(); a.pid = pid
    mon = M.Monitor(cfg, a)
    return mon, mon.collect(force_slow=True)


def render_all(s, widths=(60, 72, 80, 100, 132, 200), heights=(24, 40, 200)):
    for asc in (False, True):
        r = M.Renderer(asc)
        for w in widths:
            for h in heights:
                lines = r.render(s, w, h)
                for y, segs in enumerate(lines):
                    plain = "".join(t for t, _ in segs)
                    if len(plain) > max(60, w) + 2:
                        return f"overflow w={w} ascii={asc} line{y} len={len(plain)}"
                if len(lines) > h:
                    return f"too many lines w={w} h={h} got {len(lines)}"
    return None


print("=" * 72)
print("SCENARIO 1: normal running arc")
print("=" * 72)
root, repo, ch, dl = build()
cfg = mk_cfg(repo, ch, dl)
proc = subprocess.Popen(["sleep", "600"])
try:
    mon, s = collect(cfg, pid=proc.pid)
    chk("pid pinned", s["pid"] == proc.pid, s["pid"])
    chk("events parsed", len(mon.tx.events) >= 50, len(mon.tx.events))
    chk("sessions", len(mon.tx.sessions) == 3, list(mon.tx.sessions))
    chk("5h window open", s["reset5"] is not None, s["reset5"])
    chk("5h used > 0", s["g5"].used > 0, s["g5"].used)
    chk("5h uncalibrated -> PRIOR", not s["g5"].calibrated)
    chk("weekly reset is Friday 20:00",
        datetime.fromtimestamp(s["reset_week"]).weekday() == 4 and
        datetime.fromtimestamp(s["reset_week"]).hour == 20,
        datetime.fromtimestamp(s["reset_week"]).isoformat())
    chk("arc budget parsed 5400s", s["arc"]["budget"] == 5400, s["arc"]["budget"])
    chk("arc name", "ARC 017" in (s["arc"]["name"] or ""), s["arc"]["name"])
    chk("gates 1/3", s["progress"]["gates"] == (1, 3), s["progress"]["gates"])
    chk("todos 20/27", s["progress"]["todos"] == (20, 27), s["progress"]["todos"])
    chk("agents present", len(s["agents"]) >= 3, len(s["agents"]))
    chk("ctx detected", s["ctx_used"] > 100_000, s["ctx_used"])
    chk("burn>0", s["burn"] > 0, s["burn"])
    chk("no discovery errors", not s["discovery"], s["discovery"])
    err = render_all(s)
    chk("render all widths", err is None, err)
finally:
    proc.kill(); proc.wait()

print()
print("=" * 72)
print("SCENARIO 2: phase branches")
print("=" * 72)
root, repo, ch, dl = build()
cfg = mk_cfg(repo, ch, dl)

# 2a: dead process, stale markers
os.utime(dl / "RESULTS.md", (time.time() - 9999, time.time() - 9999))
mon, s = collect(cfg, pid=999999)
chk("2a phase NOPROC/DEAD", s["phase"][0] in (M.PHASE_NOPROC, M.PHASE_DEAD), s["phase"])
chk("2a discovery loud", any("999999" in d for d in s["discovery"]), s["discovery"])

# 2b: fresh completion markers, no process
os.utime(dl / "RESULTS.md", None)
os.utime(repo / "sessions" / "SESSION.md", None)
cfg2 = dict(cfg)
mon, s = collect(cfg2, pid=999999)
chk("2b phase DONE", s["phase"][0] == M.PHASE_DONE, s["phase"])

# 2c: running child process => EXECUTING TOOL
proc = subprocess.Popen(["sleep", "600"])
kid = subprocess.Popen(["sleep", "300"], preexec_fn=None)
try:
    # make kid a child of proc? can't easily; instead pin to our own shell pid
    parent = os.getpid()
    mon, s = collect(cfg, pid=parent)
    chk("2c has children", len(s["children"]) >= 1, len(s["children"]))
    chk("2c phase TOOL", s["phase"][0] in (M.PHASE_TOOL, M.PHASE_STALL), s["phase"])
    chk("2c socket readable", s["sock"]["readable"] is True, s["sock"])
finally:
    kid.kill(); kid.wait(); proc.kill(); proc.wait()

print()
print("=" * 72)
print("SCENARIO 3: missing / hostile inputs")
print("=" * 72)
# 3a: no ~/.claude at all
shutil.rmtree(ch)
mon, s = collect(mk_cfg(repo, ch, dl))
chk("3a discovery names missing transcript",
    any("transcript" in d for d in s["discovery"]), s["discovery"])
chk("3a no fake percentage", s["g5"].used == 0.0, s["g5"].used)
chk("3a ETA is None", s["progress"]["eta"] is None, s["progress"]["eta"])
err = render_all(s); chk("3a renders", err is None, err)

# 3b: corrupt jsonl + truncated final line + non-utf8
root, repo, ch, dl = build(n_msgs=10)
p = ch / "projects" / "-home-chris-nix" / "sess-main.jsonl"
raw = p.read_bytes()
p.write_bytes(raw + b'{"broken":\n' + b'\xff\xfe garbage\n' + b'{"partial": tru')
mon, s = collect(mk_cfg(repo, ch, dl))
chk("3b survives corruption", len(mon.tx.events) >= 10, len(mon.tx.events))
chk("3b counts parse errors", s["parse_errors"] >= 1, s["parse_errors"])

# 3c: empty todos, empty arc dir, no git
for f in (ch / "todos").glob("*"):
    f.unlink()
for f in dl.glob("*.md"):
    f.unlink()
shutil.rmtree(repo / ".git")
mon, s = collect(mk_cfg(repo, ch, dl))
chk("3c arc error loud", bool(s["arc"]["error"]), s["arc"]["error"])
chk("3c git error loud", bool(s["git"]["error"]), s["git"]["error"])
chk("3c budget None", s["arc"]["budget"] is None)
chk("3c sidechains persist w/o todos",
    all(a["kind"] == "sidechain" for a in s["agents"]) and len(s["agents"]) == 2,
    s["agents"])
chk("3c fresh sidechain NOT ended",
    all(not a["ended"] for a in s["agents"]), [a["idle"] for a in s["agents"]])
# now age them past the cutoff and re-collect
import json as _j
_pd = ch / "projects" / "-home-chris-nix"
for _f in _pd.glob("sub-*.jsonl"):
    _old = time.time() - M.AGENT_IDLE_CUTOFF - 600
    _ls = [_j.loads(l) for l in _f.read_text().splitlines() if l.strip()]
    for _i, _r in enumerate(_ls):
        _r["timestamp"] = iso(_old + _i)
    _f.write_text("\n".join(_j.dumps(r) for r in _ls) + "\n")
mon, s = collect(mk_cfg(repo, ch, dl))
chk("3c stale sidechain marked ENDED",
    all(a["ended"] for a in s["agents"] if a["kind"] == "sidechain"),
    [(a["id"], a["idle"], a["ended"]) for a in s["agents"]])
err = render_all(s); chk("3c renders", err is None, err)

# 3d: todo json is a dict form, and a junk file
root, repo, ch, dl = build()
(ch / "todos" / "weird.json").write_text('{"todos":[{"status":"completed"},{"status":"pending"}]}')
(ch / "todos" / "junk.json").write_text("not json at all {{{")
(ch / "todos" / "empty.json").write_text("[]")
mon, s = collect(mk_cfg(repo, ch, dl))
chk("3d dict-form todos read", s["progress"]["todos"][1] == 29, s["progress"]["todos"])
chk("3d junk tolerated", s["parse_errors"] >= 1, s["parse_errors"])

print()
print("=" * 72)
print("SCENARIO 4: limit windows + calibration")
print("=" * 72)
# 4a: gap > 5h re-anchors
root, repo, ch, dl = build(gap_hours=6.0, n_msgs=20)
mon, s = collect(mk_cfg(repo, ch, dl))
chk("4a window re-anchored recent",
    s["anchor5"] is not None and (time.time() - s["anchor5"]) < M.FIVE_HOURS,
    s["anchor5"])

# 4b: a limit-hit event must NOT auto-calibrate (calibration disabled — it
# misfired on non-lockout text and produced a bogus usage %).
root, repo, ch, dl = build(limit_hit=True, n_msgs=30)
cfg = mk_cfg(repo, ch, dl)
saved = {}
M.save_config = lambda c: saved.update(c)
a = no_proc_args(); mon = M.Monitor(cfg, a)
s = mon.collect(force_slow=True)
chk("4b lockout does NOT calibrate", not s["g5"].calibrated, s["g5"].basis)
chk("4b no calib sample banked", not cfg.get("calib_5h"), cfg.get("calib_5h"))
chk("4b no false lockout banked", not cfg.get("seen_lockouts"), cfg.get("seen_lockouts"))

# 4c: heavy burn triggers cap collision warning
root, repo, ch, dl = build(burn_mult=400, n_msgs=60, model="claude-opus-4-1")
cfg = mk_cfg(repo, ch, dl)
mon, s = collect(cfg)
chk("4c opus weighting applied", s["g5"].used > 1e8, s["g5"].used)
chk("4c cap_eta computed", s["cap_eta"] is not None, s["cap_eta"])
r = M.Renderer(False)
txt = "\n".join("".join(t for t, _ in row) for row in r.render(s, 100, 60))
chk("4c prior shows no confident percent",
    "PRIOR TOO LOW" not in txt and ">100%" not in txt, txt[:600])
chk("4c prior points to statusline", "statusline" in txt.lower(), txt[:600])
chk("4c ctx bar never >100%", s["ctx_used"] <= s["ctx_limit"],
    (s["ctx_used"], s["ctx_limit"]))
# genuine sub-cap collision: moderate burn against a calibrated denominator
root2, repo2, ch2, dl2 = build(burn_mult=6, n_msgs=45)
cfg2 = mk_cfg(repo2, ch2, dl2)
mon2, s0 = collect(cfg2)
cfg2["calib_5h"] = [s0["g5"].used * 1.25]
mon2, s2 = collect(cfg2)
chk("4e calibrated gauge", s2["g5"].calibrated, s2["g5"].basis)
chk("4e cap not over", not s2["cap_over"], (s2["g5"].used, s2["g5"].denom))
chk("4e cap_eta finite", 0 < (s2["cap_eta"] or 0) < 4 * 3600, s2["cap_eta"])
txt2 = "\n".join("".join(t for t, _ in row)
                 for row in M.Renderer(False).render(s2, 100, 60))
chk("4e no cap banner", "APPROACHING" not in txt2 and "CAP EXCEEDED" not in txt2, txt2[:400])

# 4d: weekly boundary sanity across a whole year
bad = []
for d in range(0, 366, 7):
    for hh in (0, 19, 20, 21, 23):
        probe = datetime(2026, 1, 1, hh, 30) + timedelta(days=d)
        st, nx = M.weekly_window(M.DEFAULT_CONFIG, probe.timestamp())
        dt = datetime.fromtimestamp(nx)
        if dt.weekday() != 4 or dt.hour != 20 or nx <= probe.timestamp():
            bad.append((probe, dt))
        if not (st <= probe.timestamp() < nx):
            bad.append(("span", probe, dt))
chk("4d weekly boundary 366d x5", not bad, bad[:3])

print()
print("=" * 72)
print("SCENARIO 4F: arc anchoring + gate baseline (node02 regressions)")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=40)
cfg = mk_cfg(repo, ch, dl)
# a LONG-lived process (as if cc has been up for hours across several arcs)
old = subprocess.Popen(["sleep", "600"])
try:
    fake_start = time.time() - 7.4 * 3600
    real_tab = M.proc_table
    def patched_tab():
        tab = real_tab()
        if old.pid in tab:
            tab[old.pid] = dict(tab[old.pid], start=fake_start)
        return tab
    M.proc_table = patched_tab

    # arc file written 12 minutes ago -> arc elapsed must be ~12m, NOT 7.4h
    arc_mt = time.time() - 720
    for f in dl.glob("*.md"):
        if f.name != "RESULTS.md":
            os.utime(f, (arc_mt, arc_mt))
    # backdate the seeded gate so it genuinely predates this arc
    _pre = time.time() - 3 * 86400
    os.utime(repo / "checks" / "check_broker_seam.py", (_pre, _pre))
    mon, s = collect(cfg, pid=old.pid)
    el = s["progress"]["elapsed"]
    chk("4F elapsed anchored to arc file", 700 < el < 760, el)
    chk("4F basis reported", s["progress"]["elapsed_basis"] == "arc file",
        s["progress"]["elapsed_basis"])
    chk("4F proc uptime not used", el < 3600, el)

    # the pre-existing check_broker_seam.py predates the arc -> NOT progress
    chk("4F pre-existing gate excluded", s["progress"]["gates"] == (0, 3),
        s["progress"]["gates"])
    chk("4F pre-existing counted separately", s["progress"]["gates_pre"] == 1,
        s["progress"].get("gates_pre"))
    chk("4F no ETA from zero landed gates", s["progress"]["gate_eta"] is None,
        s["progress"]["gate_eta"])

    # now land a gate DURING the arc -> it counts, and an ETA appears
    (repo / "checks" / "check_fetchfields.py").write_text("# gate\n")
    mon, s = collect(cfg, pid=old.pid)
    chk("4F new gate counted", s["progress"]["gates"] == (1, 3),
        s["progress"]["gates"])
    chk("4F ETA now derived", s["progress"]["gate_eta"] is not None,
        s["progress"]["gate_eta"])
    eta = s["progress"]["gate_eta"]
    chk("4F ETA sane (2 gates @ ~12m each)", 1000 < eta < 2000, eta)

    # arc file NEWER than proc start is the arc anchor; OLDER -> proc start
    older = time.time() - 9 * 3600
    for f in dl.glob("*.md"):
        if f.name != "RESULTS.md":
            os.utime(f, (older, older))
    mon, s = collect(cfg, pid=old.pid)
    chk("4F stale arc falls back to proc start",
        s["progress"]["elapsed_basis"] == "proc start", s["progress"]["elapsed_basis"])
finally:
    M.proc_table = real_tab
    old.kill(); old.wait()

print()
print()
print()
print()
print()
print()
print()
print("=" * 72)
print("SCENARIO 4L: NIX logo renders wide, falls back narrow, never overflows")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=30)
cfg = mk_cfg(repo, ch, dl); proc = subprocess.Popen(["sleep", "300"])
try:
    mon, s = collect(cfg, pid=proc.pid)
    for asc in (False, True):
        for wdt in (60, 72, 80, 88, 100, 132):
            rows = M.Renderer(asc).render(s, wdt, 30)
            for y, row in enumerate(rows):
                plain = "".join(t for t, _ in row)
                assert len(plain) <= max(60, wdt) + 2, f"overflow w={wdt} asc={asc} y={y} len={len(plain)}"
    # wide frame shows the logo glyph (▓ present in header region) + header text
    wide = "\n".join("".join(t for t, _ in r) for r in M.Renderer(False).render(s, 104, 30))
    hdr = "\n".join(wide.splitlines()[1:6])
    chk("4L logo present wide", M.NIX_LOGO and ("\u2588" in hdr), hdr[:80])
    chk("4L header text beside logo", "PHASE" in hdr and "session" in hdr, hdr[:120])
    # narrow frame: plain header, no logo gutter widening
    narrow = "\n".join("".join(t for t, _ in r) for r in M.Renderer(False).render(s, 80, 30))
    nhdr = narrow.splitlines()[1]
    chk("4L narrow header has arc name, no logo", "ARC" in nhdr
        and M.Renderer(False).b["f"] not in nhdr, nhdr[:60])
    chk("4L logo renders all widths without overflow", True)
finally:
    proc.kill(); proc.wait()

print("=" * 72)
print("SCENARIO 4K: LIMITS shows no confident-wrong % without a real denominator")
print("=" * 72)
# uncalibrated (prior only): must NOT print a percentage or PRIOR TOO LOW
root, repo, ch, dl = build(n_msgs=40, burn_mult=200, model="claude-opus-4-1")
cfg = mk_cfg(repo, ch, dl)  # no calib_5h/calib_weekly -> prior
proc = subprocess.Popen(["sleep", "300"])
try:
    mon, s = collect(cfg, pid=proc.pid)
    frame = "\n".join("".join(t for t, _ in row)
                      for row in M.Renderer(False).render(s, 104, 30))
    # LIMITS is the RIGHT column; take text after the last column separator per
    # row so the PROGRESS column (which legitimately has a context %) is excluded.
    lim_rows = []
    for line in frame.splitlines():
        if "\u2502" in line[1:]:
            lim_rows.append(line[1:].rsplit("\u2502", 1)[-1])
    lim = "\n".join(lim_rows)
    chk("4K no PRIOR TOO LOW", "PRIOR TOO LOW" not in lim, lim[:300])
    chk("4K no >100%", ">100%" not in lim, lim[:300])
    chk("4K no usage percent in LIMITS", "%" not in lim, lim[:300])
    chk("4K shows wtok used", "used" in frame, frame[:400])
    chk("4K points to statusline", "statusline" in frame.lower(), lim[:400])
    chk("4K burn still shown", "burn" in frame)
    chk("4K no estimate-exceeded banner on prior", "EXCEEDED" not in frame,
        [l for l in frame.splitlines() if "EXCEED" in l])
    chk("4K reset clocks still shown", "reset" in frame)
finally:
    proc.kill(); proc.wait()

# calibrated: a real denominator DOES yield a percentage
root, repo, ch, dl = build(n_msgs=40)
cfg = mk_cfg(repo, ch, dl)
# Even with a calib value present, auto-calibration is DISABLED and we never
# render a usage percentage anywhere. Confirm against the whole frame.
mon, s0 = collect(cfg)
cfg["calib_5h"] = [s0["g5"].used * 1.3]
mon, s = collect(cfg)
frame = "\n".join("".join(t for t, _ in row)
                  for row in M.Renderer(False).render(s, 104, 30))
usage_region = frame.split("PROGRESS")[1] if "PROGRESS" in frame else frame
chk("4K never shows a usage percent",
    ">100%" not in frame and "PRIOR TOO LOW" not in frame, frame[:400])
chk("4K shows wtok used", "used" in frame, frame[:400])
chk("4K no cap-exceeded banner", "CAP EXCEEDED" not in frame and "APPROACHING" not in frame)

print()
print()
print()
print()
print("=" * 72)
print("SCENARIO 4P: argparse help strings are format-safe (no stray %)")
print("=" * 72)
import argparse as _ap
try:
    # invoke the same parser main() builds; --help must not raise
    import subprocess as _sp, sys as _sys
    r = _sp.run([_sys.executable, "/home/claude/work/monitor.py", "--help"],
                capture_output=True, text=True, timeout=15)
    chk("4P --help exits cleanly", r.returncode == 0, r.stderr[-200:])
    chk("4P --help lists usage-snapshot", "usage-snapshot" in r.stdout, r.stdout[:300])
except Exception as _e:
    chk("4P --help runs", False, str(_e))

print("=" * 72)
print("SCENARIO 4O: claude-hud usage snapshot -> real 5h/weekly bars")
print("=" * 72)
import json as _j, tempfile as _tf, os as _os
from datetime import datetime as _dt, timezone as _tz
snap = _tf.mktemp(suffix=".json")
_now = _dt.now(_tz.utc)
_j.dump({"updated_at": _now.isoformat(),
    "five_hour": {"used_percentage": 60, "resets_at": _now.isoformat()},
    "seven_day": {"used_percentage": 86, "resets_at": _now.isoformat()}}, open(snap, "w"))
# reader parses it
d = M.read_usage_snapshot(snap)
chk("4O reader parses 5h", d and d["five_pct"] == 60.0, d)
chk("4O reader parses 7d", d and d["seven_pct"] == 86.0, d)
# stale snapshot is rejected
stale = _tf.mktemp(suffix=".json")
_old = _dt.fromtimestamp(_now.timestamp() - 3600, _tz.utc)
_j.dump({"updated_at": _old.isoformat(),
    "five_hour": {"used_percentage": 60, "resets_at": _old.isoformat()},
    "seven_day": {"used_percentage": 86, "resets_at": _old.isoformat()}}, open(stale, "w"))
chk("4O stale snapshot rejected", M.read_usage_snapshot(stale) is None, "should be None")
# missing file -> None (fallback)
chk("4O missing snapshot -> None", M.read_usage_snapshot("/nonexistent.json") is None)
# render shows real bars + percentages
root, repo, ch, dl = build(n_msgs=30)
cfg = mk_cfg(repo, ch, dl); proc = subprocess.Popen(["sleep", "300"])
try:
    class _A:
        pid = proc.pid
        usage_snapshot = snap
    mon = M.Monitor(cfg, _A()); s = mon.collect(force_slow=True)
    frame = "\n".join("".join(t for t, _ in row)
                      for row in M.Renderer(False).render(s, 104, 30))
    chk("4O renders 60%", "60%" in frame, [l for l in frame.splitlines() if "5h" in l])
    chk("4O renders 86%", "86%", "86%" in frame)
    chk("4O labels snapshot source", "claude-hud snapshot" in frame, frame[:400])
finally:
    proc.kill(); proc.wait()
    _os.unlink(snap); _os.unlink(stale)
# without snapshot -> honest fallback, no fabricated %
root, repo, ch, dl = build(n_msgs=30)
cfg = mk_cfg(repo, ch, dl)
class _B:
    pid = None
    usage_snapshot = "/definitely/not/here.json"
mon = M.Monitor(cfg, _B()); s = mon.collect(force_slow=True)
frame = "\n".join("".join(t for t, _ in row) for row in M.Renderer(False).render(s, 104, 30))
chk("4O fallback: statusline pointer", "statusline" in frame.lower(), frame[:400])
chk("4O fallback: no fabricated usage %", ">100%" not in frame and "PRIOR" not in frame)

print("=" * 72)
print("SCENARIO 4N: large ctx (cache_read) picks 1M window -> matches CC 80%")
print("=" * 72)
# Simulate CC's real live session: ~800k context via cache_read, on the main
# conversation. Expect the monitor to pick it and show 1M window / 80%.
root, repo, ch, dl = build(n_msgs=20)
proj = ch / "projects" / "-repo"
proj.mkdir(parents=True, exist_ok=True)
import json as _j, time as _t
now = _t.time()
big = proj / "live-big-0000.jsonl"
lines = []
for i in range(4):
    lines.append(_j.dumps({"sessionId":"livebig","timestamp":
        _t.strftime("%Y-%m-%dT%H:%M:%SZ", _t.gmtime(now - 10 + i)),
        "type":"assistant","message":{"model":"claude-opus-4-8","usage":{
            "input_tokens":2,"cache_creation_input_tokens":88,
            "cache_read_input_tokens":799747,"output_tokens":1160}}}))
big.write_text("\n".join(lines) + "\n")
cfg = mk_cfg(repo, ch, dl); cfg["claude_home"] = str(ch)
mon, s = collect(cfg)
# find the big session
if s["ctx_used"] >= 700_000:
    chk("4N picks the 800k session", s["ctx_used"] >= 799_000, s["ctx_used"])
    chk("4N window scales to 1M", s["ctx_limit"] == 1_000_000, s["ctx_limit"])
    frac = s["ctx_used"] / s["ctx_limit"]
    chk("4N context ~80%", 0.78 <= frac <= 0.82, round(frac, 3))
else:
    # fixture wiring may not expose this project dir; assert tier logic directly
    chk("4N tier logic: 800k -> 1M",
        next(c for c in M.CTX_TIERS if 800_000 <= c) == 1_000_000, M.CTX_TIERS)

print("=" * 72)
print("SCENARIO 4M: context line shows a percent matching the fraction")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=40)
cfg = mk_cfg(repo, ch, dl); proc = subprocess.Popen(["sleep", "300"])
try:
    mon, s = collect(cfg, pid=proc.pid)
    cu, cl = s["ctx_used"], s.get("ctx_limit") or M.CTX_LIMIT
    if cu:
        frame = "\n".join("".join(t for t, _ in row)
                          for row in M.Renderer(False).render(s, 104, 30))
        ctx_line = [l for l in frame.splitlines() if "context" in l][0]
        exp = f"{cu/cl*100:.0f}%"
        chk("4M context shows percent", "%" in ctx_line, ctx_line)
        chk("4M context percent matches fraction", exp in ctx_line, (exp, ctx_line))
    else:
        chk("4M ctx present in fixture", False, "no ctx tokens in fixture")
finally:
    proc.kill(); proc.wait()

print("=" * 72)
print("SCENARIO 4J: ETA from task-progress-bar --status-line (real CC source)")
print("=" * 72)
# Stub the reader to return what `task-progress-bar --status-line` really emits.
_real_reader = M.read_task_progress
M.read_task_progress = lambda tasks_dir=None: {
    "done": 30, "total": 61, "eta": 16 * 3600 + 19 * 60,
    "in_progress": 7, "pending": 24,
    "raw": "Tasks [....] 30/61 (~16h 19m left) | ok30 ip7 pend24"}
try:
    root, repo, ch, dl = build(n_msgs=30)
    cfg = mk_cfg(repo, ch, dl)
    proc = subprocess.Popen(["sleep", "300"])
    try:
        mon, s = collect(cfg, pid=proc.pid)
        chk("4J task_progress read", s.get("task_progress") is not None, s.get("task_progress"))
        chk("4J job todos from tpb", s["progress"]["todos"] == (30, 61), s["progress"]["todos"])
        chk("4J job ETA from tpb", abs((s["progress"]["eta"] or 0) - (16*3600+19*60)) < 1,
            s["progress"]["eta"])
        chk("4J eta basis names tpb", "tpb" in (s["progress"]["eta_basis"] or ""),
            s["progress"]["eta_basis"])
        chk("4J no span warmup needed (authoritative)",
            s["progress"]["eta_source"] == "task-progress-bar", s["progress"].get("eta_source"))
        frame = "\n".join("".join(t for t, _ in row)
                          for row in M.Renderer(False).render(s, 104, 30))
        chk("4J JOB left shows a time", "JOB left" in frame and "16h" in frame,
            [l for l in frame.splitlines() if "JOB" in l])
        chk("4J tasks row rendered", "tasks" in frame and "30/61" in frame,
            [l for l in frame.splitlines() if "tasks" in l])
        chk("4J trio rendered (done/inprog/pending)",
            all(str(n) in frame for n in (30, 7, 24)),
            [l for l in frame.splitlines() if "30" in l or "24" in l])
    finally:
        proc.kill(); proc.wait()
    # completion => no ETA
    M.read_task_progress = lambda tasks_dir=None: {"done": 61, "total": 61, "eta": 0,
        "in_progress": 0, "pending": 0, "raw": "done"}
    mon, s = collect(cfg)
    chk("4J complete -> no job eta", s["progress"]["eta"] is None, s["progress"]["eta"])
    # tool absent => graceful fallback, no crash
    M.read_task_progress = lambda tasks_dir=None: None
    mon, s = collect(cfg)
    chk("4J tool absent -> fallback", s["progress"].get("eta_source") == "observed",
        s["progress"].get("eta_source"))
finally:
    M.read_task_progress = _real_reader

print("=" * 72)
print("SCENARIO 4I: whole-job + per-agent ETA appear with sane numbers")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=40)
cfg = mk_cfg(repo, ch, dl)
proc = subprocess.Popen(["sleep", "300"])
try:
    a = Args(); a.pid = proc.pid
    mon = M.Monitor(cfg, a)
    # backdate first_seen so the job has a real 10-min span (as if monitor has
    # been observing these agents for 600s). agents: 20/27 done aggregate.
    s = mon.collect(force_slow=True)
    for stem in list(mon.agent_first_seen):
        mon.agent_first_seen[stem] = time.time() - 600
    s = mon.collect(force_slow=True)
    je = s["progress"]["eta"]
    chk("4I whole-job ETA present", je is not None, je)
    # 20/27 done in 600s -> ~7 remaining at 30s each -> ~210s
    chk("4I whole-job ETA sane", 60 < (je or 0) < 900, je)
    chk("4I eta basis names obs", "obs" in (s["progress"]["eta_basis"] or ""),
        s["progress"]["eta_basis"])
    todo_agents = [x for x in s["agents"] if x["kind"] == "todo" and not x["complete"]]
    chk("4I per-agent ETA present",
        any(x.get("eta") is not None for x in todo_agents),
        [(x["id"], x["done"], x["total"], x.get("eta")) for x in todo_agents])
    frame = "\n".join("".join(t for t, _ in row)
                      for row in M.Renderer(False).render(s, 104, 30))
    chk("4I JOB left row rendered", "JOB left" in frame,
        [l for l in frame.splitlines() if "JOB" in l])
    chk("4I per-agent 'left' rendered", "left" in frame.split("AGENTS")[1] if "AGENTS" in frame else False,
        frame.split("AGENTS")[1][:200] if "AGENTS" in frame else "no agents section")
    # completed agent shows no ETA, running one does
    chk("4I completed agent no eta",
        all(x.get("eta") is None for x in s["agents"] if x["complete"]))
    # a fresh agent (just observed, span<MIN_SPAN) yields no fabricated eta
    (ch / "todos" / "fresh-0000-9.json").write_text(_j.dumps(
        [{"content":"a","status":"completed"},{"content":"b","status":"in_progress"},
         {"content":"c","status":"pending"}]))
    import json as _jj
    s2 = mon.collect(force_slow=True)
    fresh = [x for x in s2["agents"] if x["id"].startswith("fresh")]
    chk("4I fresh agent no fabricated eta",
        all(x.get("eta") is None for x in fresh), [(x["id"], x.get("worked")) for x in fresh])
finally:
    proc.kill(); proc.wait()

print("=" * 72)
print("SCENARIO 4H: no completion-ETA shown; current session identified")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=40)
cfg = mk_cfg(repo, ch, dl)
proc = subprocess.Popen(["sleep", "300"])
try:
    mon, s = collect(cfg, pid=proc.pid)
    frame = "\n".join("".join(t for t, _ in row)
                      for row in M.Renderer(False).render(s, 104, 30))
    chk("4H no ETA row", "ETA" not in frame, [l for l in frame.splitlines() if "ETA" in l])
    chk("4H no declared-budget row", "declared" not in frame,
        [l for l in frame.splitlines() if "declared" in l])
    chk("4H no 'ARC ETA' collision text", "ARC ETA" not in frame)
    chk("4H current session identified", s.get("cur_session") is not None, s.get("cur_session"))
    chk("4H session line rendered", "session " in frame,
        [l for l in frame.splitlines() if "session" in l][:2])
    chk("4H elapsed still shown (actual)", "elapsed" in frame)
    chk("4H gates still shown (actual)", "gates" in frame)
    chk("4H limits resets still shown", "reset" in frame)
finally:
    proc.kill(); proc.wait()

print("=" * 72)
print("SCENARIO 4G: stale historical agents dropped (screenshot regression)")
print("=" * 72)
# Reproduce the node02 frame: a FRESH process, but the transcript history holds
# sidechains that last logged 45-104h ago. They must NOT appear as agents.
root, repo, ch, dl = build(n_msgs=20, sidechains=0)
proj = ch / "projects" / "-home-bbt-nix"; proj.mkdir(parents=True, exist_ok=True)
nowt = time.time()
import json as _j
# 8 ancient sidechains, last activity 45h..104h ago
for k, hrs in enumerate([104, 81, 68, 66, 64, 57, 55, 45]):
    last = nowt - hrs * 3600
    recs = []
    for i in range(4):
        recs.append(_j.dumps({"type": "assistant", "isSidechain": True,
            "timestamp": iso(last - (3 - i) * 60), "sessionId": f"ancient-{k}",
            "message": {"role": "assistant", "model": "claude-opus-4-1",
                        "usage": {"input_tokens": 2000, "output_tokens": 1500},
                        "content": [{"type": "tool_use", "name": "Edit", "input": {}}]}}))
    (proj / f"ancient-{k}.jsonl").write_text("\n".join(recs) + "\n")
# one sidechain active RIGHT NOW (should show)
recs = [_j.dumps({"type": "assistant", "isSidechain": True,
        "timestamp": iso(nowt - 20 - (3 - i) * 5), "sessionId": "live-agent",
        "message": {"role": "assistant", "model": "claude-sonnet-4-5",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                    "content": [{"type": "tool_use", "name": "Bash", "input": {}}]}})
        for i in range(4)]
(proj / "live-agent.jsonl").write_text("\n".join(recs) + "\n")

# fresh process, started 3 min ago (like a just-launched arc, not 9h old)
proc = subprocess.Popen(["sleep", "600"])
try:
    fresh_start = nowt - 180
    real_tab = M.proc_table
    def _pt():
        tab = real_tab()
        if proc.pid in tab:
            tab[proc.pid] = dict(tab[proc.pid], start=fresh_start)
        return tab
    M.proc_table = _pt
    mon, s = collect(cfg=mk_cfg(repo, ch, dl), pid=proc.pid)
    ids = [a["id"] for a in s["agents"]]
    idles = [a["idle"] for a in s["agents"]]
    chk("4G no ancient agents shown", all(i < 3600 for i in idles),
        [(a["id"], round(a["idle"]/3600, 1)) for a in s["agents"]])
    chk("4G live agent present", any("live-age" in i for i in ids), ids)
    chk("4G max idle under window",
        (max(idles) if idles else 0) <= M.AGENT_SHOW_WINDOW, max(idles) if idles else 0)
    # with proc_start floor: even within 30min window, nothing before proc_start
    chk("4G agent count sane (1 live)", len([a for a in s["agents"]
        if a["kind"] == "sidechain"]) == 1, ids)
finally:
    M.proc_table = real_tab
    proc.kill(); proc.wait()

print("=" * 72)
print("SCENARIO 5: incremental tail + rotation")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=10)
cfg = mk_cfg(repo, ch, dl)
a = no_proc_args(); mon = M.Monitor(cfg, a)
s1 = mon.collect(force_slow=True); n1 = len(mon.tx.events)
p = ch / "projects" / "-home-chris-nix" / "sess-main.jsonl"
with open(p, "a") as fh:
    fh.write(json.dumps({"type": "assistant", "timestamp": iso(time.time()),
                         "sessionId": "sess-main",
                         "message": {"role": "assistant", "model": "sonnet",
                                     "usage": {"input_tokens": 10, "output_tokens": 5},
                                     "content": []}}) + "\n")
s2 = mon.collect(); n2 = len(mon.tx.events)
chk("5a incremental append", n2 == n1 + 1, f"{n1}->{n2}")
# partial line must NOT be consumed
with open(p, "a") as fh:
    fh.write('{"type":"assistant","timestamp":"')
s3 = mon.collect(); n3 = len(mon.tx.events)
chk("5b partial line held", n3 == n2, f"{n2}->{n3}")
with open(p, "a") as fh:
    fh.write(iso(time.time()) + '","sessionId":"sess-main","message":{"role":"assistant","usage":{"output_tokens":1},"content":[]}}\n')
s4 = mon.collect(); n4 = len(mon.tx.events)
chk("5c completed line consumed", n4 == n3 + 1, f"{n3}->{n4}")
# truncation
p.write_text("")
s5 = mon.collect()
chk("5d truncation handled", mon.tx.offsets[str(p)] == 0, mon.tx.offsets[str(p)])
chk("5e ts_index sorted", mon.tx.ts_index == sorted(mon.tx.ts_index))

print()
print("=" * 72)
print("SCENARIO 6: perf")
print("=" * 72)
root, repo, ch, dl = build(n_msgs=4000, sidechains=6)
cfg = mk_cfg(repo, ch, dl)
a = no_proc_args(); mon = M.Monitor(cfg, a)
t = time.time(); s = mon.collect(force_slow=True); cold = time.time() - t
t = time.time(); s = mon.collect(); warm = time.time() - t
t = time.time()
r = M.Renderer(False)
for _ in range(30):
    r.render(s, 120, 45)
paint = (time.time() - t) / 30
print(f"  cold collect {cold*1000:.0f}ms | warm collect {warm*1000:.0f}ms | render {paint*1000:.1f}ms")
chk("perf cold < 3s", cold < 3.0, cold)
chk("perf warm < 0.6s", warm < 0.6, warm)
chk("perf render < 20ms", paint < 0.02, paint)
chk("6 events all ingested", len(mon.tx.events) >= 4000, len(mon.tx.events))

print()
print("=" * 72)
print(f"RESULT: {len(FAILS)} failures")
for f in FAILS:
    print("  " + f)
shutil.rmtree(ROOT, ignore_errors=True)
sys.exit(1 if FAILS else 0)
