#!/usr/bin/env python3
"""End-to-end test for yaui-tui via a real pty.

Spawns yaui-tui running a fixture script in a pty, sends keypresses, and
collects the screen bytes. Then asserts that expected text appears in output
and that the fixture wrote the expected event log to disk.
"""

import os
import pty
import select
import signal
import subprocess
import sys
import time


def run(cmd, keys, timeout=5.0):
    """Run cmd in a pty, drip keys (each as bytes), return collected output."""
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(cmd[0], cmd)
    out = bytearray()
    deadline = time.time() + timeout
    sent = 0
    last_send = time.time()
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if fd in r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            out += data
        # Send next key after a short delay between keys
        if sent < len(keys) and time.time() - last_send > 0.3:
            os.write(fd, keys[sent])
            sent += 1
            last_send = time.time()
        # Check if child exited
        try:
            wpid, status = os.waitpid(pid, os.WNOHANG)
            if wpid != 0:
                # Drain remaining
                drain_deadline = time.time() + 0.2
                while time.time() < drain_deadline:
                    r, _, _ = select.select([fd], [], [], 0.05)
                    if fd in r:
                        try:
                            data = os.read(fd, 4096)
                        except OSError:
                            break
                        if not data:
                            break
                        out += data
                    else:
                        break
                return bytes(out), os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        except ChildProcessError:
            break
    # Timed out; kill
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.1)
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass
    return bytes(out), -2


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    yaui = os.path.join(here, 'yaui-tui')
    fixture = os.path.join(here, '_fixture.sh')
    log_path = os.path.join(here, '_events.log')

    # Fixture: outputs a dialog with a button, reads one event line, writes
    # that line to a log, then outputs a second UI and reads another line.
    fixture_src = f"""#!/bin/sh
LOG={log_path!s}
: > "$LOG"
cat <<'EOL'
{{"type":"dialog","title":"T1","content":[{{"type":"vbox","children":[
  {{"type":"label","text":"Step 1"}},
  {{"type":"button","id":"ok","text":"OK"}}
]}}]}}
EOL
read e1
printf '%s\\n' "$e1" >> "$LOG"
cat <<'EOL'
{{"type":"dialog","title":"T2","content":[{{"type":"label","text":"Step 2 done"}}]}}
EOL
read e2
printf '%s\\n' "$e2" >> "$LOG"
"""
    with open(fixture, 'w') as f:
        f.write(fixture_src)
    os.chmod(fixture, 0o755)
    if os.path.exists(log_path):
        os.remove(log_path)

    # Keys: Enter (activates focused button), then Esc to dismiss.
    out, exit_code = run([yaui, fixture], keys=[b'\r', b'\x1b'], timeout=4.0)

    # Show last bit of output for debugging
    sys.stdout.write('--- pty bytes (decoded, last 600) ---\n')
    sys.stdout.write(out.decode('utf-8', errors='replace')[-600:])
    sys.stdout.write('\n--- exit ---\n')
    print('exit_code:', exit_code)

    print('\n--- _events.log ---')
    if os.path.exists(log_path):
        with open(log_path) as f:
            print(f.read())
    else:
        print('(missing)')

    text = out.decode('utf-8', errors='replace')
    failures = []
    if 'Step 1' not in text:
        failures.append('first UI Step 1 not seen')
    if 'Step 2 done' not in text:
        failures.append('second UI Step 2 not seen after click')
    if not os.path.exists(log_path):
        failures.append('event log missing')
    else:
        log = open(log_path).read()
        if '"type": "click"' not in log and '"type":"click"' not in log:
            failures.append(f'click event missing in log: {log!r}')
        if '"type": "close"' not in log and '"type":"close"' not in log:
            failures.append(f'close event missing in log: {log!r}')

    if failures:
        print('\nFAIL:')
        for f in failures:
            print(' -', f)
        sys.exit(1)
    print('\nALL CHECKS PASSED')


if __name__ == '__main__':
    main()
