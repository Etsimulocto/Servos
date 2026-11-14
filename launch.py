#!/usr/bin/env python3
"""Start the local Servos UI, choosing a free port instead of opening a stale 404."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
LOG = ROOT / "servos-launch.log"

def notify(message):
    print(message, file=sys.stderr)
    try:
        subprocess.run(["zenity", "--error", "--title=Servos", "--text="+message],
                       timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass

def state_at(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/state", timeout=0.3) as result:
            data = json.load(result)
        if isinstance(data, dict) and len(data.get("servos", [])) == 16:
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None

def port_free(port):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulation", action="store_true", help="Do not connect I2C hardware")
    args = parser.parse_args()
    wanted = "SIMULATION" if args.simulation else "HARDWARE"
    # Reuse an existing matching controller; never mistake a stale/foreign 404 for the app.
    for port in range(8765, 8786):
        existing = state_at(port)
        if existing and existing.get("mode") == wanted:
            webbrowser.open(f"http://127.0.0.1:{port}/")
            return
    port = next((p for p in range(8765, 8786) if port_free(p)), None)
    if port is None:
        return notify("No free local port in 8765–8785. Close older Servos instances.")
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        return notify("Python environment not installed. Run: cd ~/Servos && python3 install_desktop.py")
    cmd = [str(python), str(ROOT / "app.py"), "--port", str(port)]
    if not args.simulation:
        cmd.append("--hardware")
    with LOG.open("ab") as output:
        proc = subprocess.Popen(cmd, cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT,
                                start_new_session=True)
    for _ in range(50):
        if proc.poll() is not None:
            return notify(f"Servos exited at startup. See log: {LOG}")
        if state_at(port):
            webbrowser.open(f"http://127.0.0.1:{port}/")
            return
        time.sleep(0.1)
    proc.terminate()
    return notify(f"Servos did not start. See log: {LOG}")

if __name__ == "__main__":
    main()
