#!/usr/bin/env python3
"""End-to-end test for yaui-tk under Xvfb.

Same strategy as test_gtk.py: drive yaui-tk with a fixture script that
emits a sequence of UI trees and then exits. Asserts that yaui-tk:
  - starts on the Xvfb display
  - renders a window (verified via xwininfo)
  - applies every UI update without raising
  - exits with status 0 when the script finishes
A screenshot is captured for visual inspection.
"""

import os
import subprocess
import sys
import time


HERE = os.path.dirname(os.path.abspath(__file__))


def wait_for_x(display, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if subprocess.run(
            ['xwininfo', '-root', '-display', display],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0:
            return True
        time.sleep(0.1)
    return False


def find_window(display, title):
    out = subprocess.run(
        ['xwininfo', '-root', '-tree', '-display', display],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        if title in line:
            return line.strip()
    return None


def screenshot(display, path):
    subprocess.run(
        ['import', '-display', display, '-window', 'root', path],
        check=False,
    )


def run_with_xvfb(test_fn):
    display = ':108'
    xvfb = subprocess.Popen(
        ['Xvfb', display, '-screen', '0', '800x600x24', '-nolisten', 'tcp'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_for_x(display):
            print('FAIL: Xvfb did not start')
            return 1
        env = dict(os.environ)
        env['DISPLAY'] = display
        return test_fn(env, display)
    finally:
        xvfb.terminate()
        try:
            xvfb.wait(timeout=2)
        except subprocess.TimeoutExpired:
            xvfb.kill()


def test_main(env, display):
    fixture_path = os.path.join(HERE, '_tk_fixture.sh')
    shot_path = os.path.join(HERE, '_tk_shot.png')

    fixture = """#!/bin/sh
emit() {
  cat <<EOL
{"type":"dialog","title":"yaui-tk smoke",
 "content":[{"type":"vbox","children":[
   {"type":"label","text":"$1"},
   {"type":"progressbar","value":$2,"max":3},
   {"type":"button","id":"go","text":"Go"}
 ]}]}
EOL
}
emit "tick:0" 0
sleep 0.4
emit "tick:1" 1
sleep 0.4
emit "tick:2" 2
sleep 0.4
emit "Done." 3
sleep 0.5
"""
    with open(fixture_path, 'w') as f:
        f.write(fixture)
    os.chmod(fixture_path, 0o755)

    yaui = os.path.join(HERE, 'yaui-tk')
    proc = subprocess.Popen(
        [yaui, '--debug', fixture_path],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    deadline = time.time() + 5.0
    found = None
    while time.time() < deadline and found is None:
        found = find_window(display, 'yaui-tk smoke')
        if found is None:
            time.sleep(0.1)
    window_seen = found is not None

    time.sleep(0.6)
    screenshot(display, shot_path)

    try:
        out, err = proc.communicate(timeout=5)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        rc = -1

    failures = []
    if not window_seen:
        failures.append('window with title "yaui-tk smoke" was never created')
    if rc != 0:
        failures.append(f'yaui-tk exited with status {rc}')
    if 'Traceback' in err:
        failures.append('python traceback on stderr:\n' + err)

    print('--- yaui-tk stderr ---')
    print(err or '(empty)')
    print('--- exit ---')
    print('rc:', rc, 'window_seen:', window_seen)
    print('screenshot:', shot_path, 'exists:', os.path.exists(shot_path))

    if failures:
        print('\nFAIL:')
        for f in failures:
            print(' -', f)
        return 1
    print('\nALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(run_with_xvfb(test_main))
