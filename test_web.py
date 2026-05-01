#!/usr/bin/env python3
"""End-to-end test for yaui-web using curl/HTTP only (no browser needed).

Spawns yaui-web in --no-browser mode against a fixture script, then exercises
the HTTP surface:
  GET /          -> HTML page contains the renderer
  GET /events    -> SSE stream pushes the UI JSON
  POST /event    -> event JSON is forwarded to the script's stdin
                    (the fixture writes received events to a log file)
"""

import json
import os
import re
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


def http_get(url, timeout=2.0):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8', errors='replace')


def http_post_json(url, obj, timeout=2.0):
    body = json.dumps(obj).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read().decode('utf-8', errors='replace')


def read_sse(url, max_seconds=1.5, max_bytes=8192):
    """Read raw bytes from an SSE endpoint for a short window."""
    proc = subprocess.Popen(
        ['curl', '-s', '-N', '--max-time', str(max_seconds), url],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        out, _ = proc.communicate(timeout=max_seconds + 1.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, _ = proc.communicate()
    return out.decode('utf-8', errors='replace')[:max_bytes]


def parse_sse_data(text):
    """Extract data: <json> entries from SSE text."""
    out = []
    for block in text.split('\n\n'):
        data_lines = [l[len('data: '):] for l in block.splitlines()
                      if l.startswith('data: ')]
        if not data_lines:
            continue
        joined = '\n'.join(data_lines)
        try:
            out.append(json.loads(joined))
        except json.JSONDecodeError:
            pass
    return out


def main():
    port = free_port()
    log_path = os.path.join(HERE, '_web_events.log')
    fixture_path = os.path.join(HERE, '_web_fixture.sh')

    fixture_src = f"""#!/bin/sh
LOG={log_path!s}
: > "$LOG"
cat <<'EOL'
{{"type":"dialog","title":"web smoke","content":[{{"type":"vbox","children":[
  {{"type":"label","text":"hi from web"}},
  {{"type":"button","id":"go","text":"Go"}}
]}}]}}
EOL
# Wait for one event line, log it, then exit.
read line
printf '%s\\n' "$line" >> "$LOG"
"""
    with open(fixture_path, 'w') as f:
        f.write(fixture_src)
    os.chmod(fixture_path, 0o755)
    if os.path.exists(log_path):
        os.remove(log_path)

    yaui = os.path.join(HERE, 'yaui-web')
    proc = subprocess.Popen(
        [yaui, '--no-browser', '--port', str(port), fixture_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    failures = []
    try:
        # Wait for server to listen
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                http_get(f'http://127.0.0.1:{port}/healthz', timeout=0.3)
                break
            except Exception:
                time.sleep(0.05)
        else:
            failures.append('server never accepted connections')

        # 1. GET /
        try:
            status, body = http_get(f'http://127.0.0.1:{port}/', timeout=2)
            if status != 200:
                failures.append(f'GET / status={status}')
            for needle in ['yaui-web', 'EventSource', '/events', '/event']:
                if needle not in body:
                    failures.append(f'GET / missing token: {needle}')
        except Exception as e:
            failures.append(f'GET / raised: {e}')

        # 2. GET /events
        sse_text = read_sse(f'http://127.0.0.1:{port}/events', max_seconds=1.2)
        ui_objects = parse_sse_data(sse_text)
        if not ui_objects:
            failures.append('SSE returned no UI JSON. Raw=\n' + sse_text[:500])
        else:
            first = ui_objects[0]
            if first.get('type') != 'dialog':
                failures.append(f'first SSE UI not a dialog: {first!r}')
            if first.get('title') != 'web smoke':
                failures.append(f'first SSE UI wrong title: {first!r}')

        # 3. POST /event
        try:
            status, _ = http_post_json(
                f'http://127.0.0.1:{port}/event',
                {'type': 'click', 'id': 'go'},
            )
            if status != 204:
                failures.append(f'POST /event status={status}')
        except Exception as e:
            failures.append(f'POST /event raised: {e}')

        # Give the script a moment to read the line and exit
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.terminate()

        if not os.path.exists(log_path):
            failures.append('event log missing — script never received POST?')
        else:
            log = open(log_path).read()
            if '"type": "click"' not in log and '"type":"click"' not in log:
                failures.append(f'click event not seen in log: {log!r}')
            if '"id": "go"' not in log and '"id":"go"' not in log:
                failures.append(f'event id "go" not in log: {log!r}')
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                proc.kill()

    print('--- yaui-web stderr ---')
    err = proc.stderr.read() if proc.stderr else ''
    print(err or '(empty)')
    print('--- exit ---')
    print('rc:', proc.returncode)

    print('--- _web_events.log ---')
    if os.path.exists(log_path):
        print(open(log_path).read())
    else:
        print('(missing)')

    if failures:
        print('\nFAIL:')
        for f in failures:
            print(' -', f)
        return 1
    print('\nALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
