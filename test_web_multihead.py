#!/usr/bin/env python3
"""Multi-head test for yaui-web.

Exercises:
  1. Two concurrent SSE clients receive the same UI tree.
  2. A change event POSTed by client A is delivered as a peer event to
     client B (cross-tab sync without script re-emit).
  3. Disconnecting and reconnecting a client (simulating a reload)
     immediately replays the latest UI tree AND the shadow of any peer
     events recorded since.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request


HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def post_json(url, obj):
    body = json.dumps(obj).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=2.0) as r:
        return r.status


def open_sse(url):
    """Return a Popen running curl -N -s on the SSE endpoint."""
    return subprocess.Popen(
        ['curl', '-s', '-N', url],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )


def read_sse_for(proc, seconds, max_bytes=8192):
    """Drain proc.stdout for `seconds`, return decoded text."""
    import select
    out = b''
    deadline = time.time() + seconds
    while time.time() < deadline and len(out) < max_bytes:
        r, _, _ = select.select([proc.stdout], [], [], 0.05)
        if proc.stdout in r:
            chunk = os.read(proc.stdout.fileno(), 4096)
            if not chunk:
                break
            out += chunk
    return out.decode('utf-8', errors='replace')


def parse_sse(text):
    """Parse SSE blocks → list of (event_type, data_json)."""
    blocks = []
    for raw in text.split('\n\n'):
        lines = raw.splitlines()
        ev = 'message'
        data = []
        for l in lines:
            if l.startswith('event: '):
                ev = l[len('event: '):]
            elif l.startswith('data: '):
                data.append(l[len('data: '):])
        if data:
            try:
                blocks.append((ev, json.loads('\n'.join(data))))
            except json.JSONDecodeError:
                blocks.append((ev, '\n'.join(data)))
    return blocks


def main():
    port = free_port()
    fixture = os.path.join(HERE, '_mh_fixture.sh')
    log_path = os.path.join(HERE, '_mh_events.log')

    # Fixture: emit one UI tree with a textbox + a list, then read events
    # forever (we need it alive across the test).
    fixture_src = f"""#!/bin/sh
LOG={log_path!s}
: > "$LOG"
cat <<'EOL'
{{"type":"dialog","title":"mh","content":[{{"type":"vbox","children":[
  {{"type":"textbox","id":"q","width":20,"value":""}},
  {{"type":"list","id":"items","items":["alpha","beta","gamma"]}}
]}}]}}
EOL
while IFS= read -r line; do
  printf '%s\\n' "$line" >> "$LOG"
  case "$line" in *'"close"'*) exit 0 ;; esac
done
"""
    with open(fixture, 'w') as f:
        f.write(fixture_src)
    os.chmod(fixture, 0o755)
    if os.path.exists(log_path):
        os.remove(log_path)

    yaui = os.path.join(HERE, 'yaui-web')
    proc = subprocess.Popen(
        [yaui, '--no-browser', '--port', str(port), fixture],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    failures = []
    cli_a = None
    cli_b = None
    cli_c = None
    try:
        # Wait for server
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz',
                                       timeout=0.3).read()
                break
            except Exception:
                time.sleep(0.05)
        else:
            failures.append('server never started')
            return _finish(proc, failures)

        base = f'http://127.0.0.1:{port}'

        # Step 1: open client A and B simultaneously, each should get the UI.
        cli_a = open_sse(f'{base}/events')
        cli_b = open_sse(f'{base}/events')
        time.sleep(0.7)
        a1 = parse_sse(read_sse_for(cli_a, 0.3))
        b1 = parse_sse(read_sse_for(cli_b, 0.3))
        a_ui = [d for (e, d) in a1 if e == 'ui']
        b_ui = [d for (e, d) in b1 if e == 'ui']
        if not a_ui or not b_ui:
            failures.append(f'initial UI not received: a={a1!r} b={b1!r}')

        # Step 2: post a change event "from client A" via /event.
        # Server should forward to script AND broadcast to B.
        post_json(f'{base}/event',
                  {'type': 'change', 'id': 'q', 'value': 'hello'})
        time.sleep(0.4)
        b2 = parse_sse(read_sse_for(cli_b, 0.4))
        peers = [d for (e, d) in b2 if e == 'peer']
        if not any(p.get('id') == 'q' and p.get('value') == 'hello'
                   for p in peers):
            failures.append(f'B did not receive peer change for q=hello: {peers!r}')

        # Step 3: disconnect B, reconnect (simulating reload).
        cli_b.terminate()
        cli_b.wait(timeout=1.0)
        cli_b = None
        time.sleep(0.2)
        cli_c = open_sse(f'{base}/events')
        time.sleep(0.7)
        c1 = parse_sse(read_sse_for(cli_c, 0.3))
        c_ui = [d for (e, d) in c1 if e == 'ui']
        c_peer = [d for (e, d) in c1 if e == 'peer']
        if not c_ui:
            failures.append(f'reconnected client did not get UI: {c1!r}')
        if not any(p.get('id') == 'q' and p.get('value') == 'hello'
                   for p in c_peer):
            failures.append(
                f'reconnected client did not receive shadow replay for q: {c_peer!r}')

        # Also send a list selection from C and confirm A sees it.
        post_json(f'{base}/event',
                  {'type': 'change', 'id': 'items',
                   'value': 1, 'item': 'beta'})
        time.sleep(0.3)
        a2 = parse_sse(read_sse_for(cli_a, 0.3))
        a_peer = [d for (e, d) in a2 if e == 'peer']
        if not any(p.get('id') == 'items' and p.get('item') == 'beta'
                   for p in a_peer):
            failures.append(f'A did not receive list change peer: {a_peer!r}')

        return _finish(proc, failures, log_path,
                       cleanup=[cli_a, cli_b, cli_c])
    finally:
        for c in (cli_a, cli_b, cli_c):
            if c is not None:
                try: c.terminate()
                except Exception: pass


def _finish(proc, failures, log_path=None, cleanup=()):
    proc.terminate()
    try: proc.wait(timeout=2.0)
    except subprocess.TimeoutExpired: proc.kill()

    print('--- yaui-web stderr ---')
    err = proc.stderr.read() if proc.stderr else ''
    print(err or '(empty)')
    if log_path and os.path.exists(log_path):
        print('--- script event log ---')
        print(open(log_path).read())

    if failures:
        print('\nFAIL:')
        for f in failures:
            print(' -', f)
        return 1
    print('\nALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
