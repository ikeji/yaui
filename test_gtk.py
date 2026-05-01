#!/usr/bin/env python3
"""End-to-end test for yaui-gtk under Xvfb.

Strategy: no synthetic input is available (no xdotool / python-xlib / atspi),
so we drive yaui-gtk with a fixture script that emits a sequence of UI
trees and then exits. We assert that yaui-gtk:
  - starts Xvfb cleanly
  - renders a window (verified by xwininfo finding it)
  - applies every UI update without raising on stderr
  - exits with status 0 when the script finishes
A screenshot is captured for visual inspection.
"""

import os
import signal
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
    display = ':99'
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
    fixture_path = os.path.join(HERE, '_gtk_fixture.sh')
    log_path = os.path.join(HERE, '_gtk_events.log')
    shot_path = os.path.join(HERE, '_gtk_shot.png')

    # Fixture: emits a dialog, then 3 progressive updates, then exits.
    # The label "tick:N" lets us see re-renders are working.
    fixture = f"""#!/bin/sh
LOG={log_path!s}
: > "$LOG"
emit() {{
  cat <<EOL
{{"type":"dialog","title":"yaui-gtk smoke",
 "content":[{{"type":"vbox","children":[
   {{"type":"label","text":"$1"}},
   {{"type":"progressbar","value":$2,"max":3,"show_text":true}},
   {{"type":"button","id":"go","text":"Go"}}
 ]}}]}}
EOL
}}
emit "tick:0" 0
sleep 0.4
emit "tick:1" 1
sleep 0.4
emit "tick:2" 2
sleep 0.4
emit "Done." 3
sleep 0.6
"""
    with open(fixture_path, 'w') as f:
        f.write(fixture)
    os.chmod(fixture_path, 0o755)
    if os.path.exists(log_path):
        os.remove(log_path)

    # Launch yaui-gtk
    yaui = os.path.join(HERE, 'yaui-gtk')
    proc = subprocess.Popen(
        [yaui, '--debug', fixture_path],
        env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    # Wait for window to appear
    deadline = time.time() + 5.0
    found = None
    while time.time() < deadline and found is None:
        found = find_window(display, 'yaui-gtk smoke')
        if found is None:
            time.sleep(0.1)
    window_seen = found is not None

    # Wait midway, take screenshot
    time.sleep(0.6)
    screenshot(display, shot_path)

    # Wait for process to finish naturally (script sleeps ~2s)
    try:
        out, err = proc.communicate(timeout=5)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        rc = -1

    failures = []
    if not window_seen:
        failures.append('window with title "yaui-gtk smoke" was never created')
    if rc != 0:
        failures.append(f'yaui-gtk exited with status {rc}')
    # Filter common harmless GLib/GTK warnings if any
    serious = [l for l in err.splitlines()
               if l.strip() and 'WARNING' not in l and 'CRITICAL' not in l
               and 'Traceback' in l]
    if serious:
        failures.append('python traceback on stderr:\n' + '\n'.join(serious))
    if 'CRITICAL' in err or 'Traceback' in err:
        failures.append('stderr contains CRITICAL or Traceback:\n' + err)

    print('--- yaui-gtk stderr ---')
    print(err or '(empty)')
    print('--- exit ---')
    print('rc:', rc)
    print('window_seen:', window_seen)
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
