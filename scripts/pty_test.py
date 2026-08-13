#!/usr/bin/env python3
"""Drive monitor.py's real curses loop under a pty: keys, resize, teardown."""
import fcntl, os, pty, signal, struct, subprocess, sys, termios, time, importlib.util, shutil

from pathlib import Path

HERE = Path(__file__).resolve().parent
MON, HARNESS = HERE / "monitor.py", HERE / "harness.py"
for _f in (MON, HARNESS):
    if not _f.exists():
        sys.exit(f"{_f.name} not found beside {__file__}")
spec = importlib.util.spec_from_file_location("mon", str(MON))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
src = HARNESS.read_text().split('print("=" * 72)')[0]
g = {"__name__": "hb", "__file__": str(HARNESS)}; exec(src, g)
root, repo, ch, dl = g["build"](n_msgs=80)

FAILS = []
def chk(n, c, d=""):
    (FAILS.append(f"{n} :: {d}") if not c else None)
    print(("  FAIL " if not c else "  ok   ") + n + (f" :: {d}" if not c else ""))

def winsz(fd, rows, cols):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

env = dict(os.environ, TERM="xterm-256color", HOME=str(root))
pid, fd = pty.fork()
if pid == 0:
    os.execve(sys.executable,
              [sys.executable, str(MON),
               "--repo", str(repo), "--arc-dir", str(dl),
               "--claude-home", str(ch), "--rate", "0.5"], env)

out = b""
try:
    winsz(fd, 40, 110)
    time.sleep(2.0)
    os.set_blocking(fd, False)
    def drain(t=0.8):
        global out
        end = time.time() + t
        buf = b""
        while time.time() < end:
            try:
                b = os.read(fd, 65536)
                if b: buf += b
            except (BlockingIOError, OSError):
                time.sleep(0.05)
        out += buf
        return buf

    first = drain(1.5)
    chk("pty: alt screen entered", b"\x1b[?1049h" in first or b"\x1b[?47h" in first,
        first[:60])
    chk("pty: painted a frame", b"NIX MONITOR" in first, first[-200:])
    chk("pty: no python traceback", b"Traceback" not in out)

    os.write(fd, b"+"); time.sleep(0.8); drain(0.6)
    os.write(fd, b"a"); time.sleep(0.8)          # ascii toggle
    asc = drain(1.2)
    chk("pty: ascii toggle renders", b"+--" in asc or b"|" in asc, asc[-120:])
    os.write(fd, b"a"); time.sleep(0.6); drain(0.6)

    os.write(fd, b"p"); time.sleep(0.6)
    pz = drain(1.0)
    chk("pty: pause flag shown", b"PAUSED" in pz or b"PAUSE" in pz, pz[-160:])
    os.write(fd, b"p"); time.sleep(0.5); drain(0.5)

    # resize storm, including hostile narrow/short
    for r, c in ((24, 80), (12, 60), (60, 200), (8, 40), (5, 30), (45, 120)):
        winsz(fd, r, c)
        os.kill(pid, signal.SIGWINCH)
        time.sleep(0.35)
    rs = drain(1.5)
    chk("pty: survives resize storm", b"Traceback" not in out and b"NIX MONITOR" in rs,
        out[-300:])

    os.write(fd, b"r"); time.sleep(0.8); drain(0.6)
    chk("pty: still alive after force probe", os.waitpid(pid, os.WNOHANG)[0] == 0)

    os.write(fd, b"q"); time.sleep(1.2)
    tail = drain(1.0)
    wpid, status = os.waitpid(pid, 0)
    chk("pty: clean exit 0", os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
        status)
    chk("pty: alt screen restored", b"\x1b[?1049l" in (tail or out) or
        b"\x1b[?47l" in (tail or out), (tail or out)[-80:])
    chk("pty: no traceback overall", b"Traceback" not in out, out[-400:])
finally:
    try: os.kill(pid, signal.SIGKILL)
    except OSError: pass
    os.close(fd)

# --once / non-tty path
r = subprocess.run([sys.executable, str(MON), "--once",
                    "--repo", str(repo), "--arc-dir", str(dl),
                    "--claude-home", str(ch), "--width", "100"],
                   capture_output=True, text=True, env=env, timeout=60)
chk("--once exit 0", r.returncode == 0, r.stderr[-300:])
chk("--once frame", "NIX MONITOR" in r.stdout, r.stdout[:120])
chk("--once no stderr", not r.stderr.strip(), r.stderr[-300:])
maxlen = max(len(l) for l in r.stdout.splitlines())
chk("--once width honoured", maxlen == 100, maxlen)

# piped stdout must auto-fall back to --once, never hang
r2 = subprocess.run(f"{sys.executable} {MON} "
                    f"--repo {repo} --arc-dir {dl} --claude-home {ch} | head -3",
                    shell=True, capture_output=True, text=True, env=env, timeout=60)
chk("piped stdout falls back", "NIX MONITOR" in r2.stdout, r2.stdout[:120])

# bad args
r3 = subprocess.run([sys.executable, str(MON),
                     "--weekly", "Blursday 99:99", "--once"],
                    capture_output=True, text=True, env=env, timeout=60)
chk("bad --weekly rejected", r3.returncode == 2, r3.returncode)

print(f"\nPTY RESULT: {len(FAILS)} failures")
for f in FAILS: print("  " + f)
shutil.rmtree(root, ignore_errors=True)
sys.exit(1 if FAILS else 0)
