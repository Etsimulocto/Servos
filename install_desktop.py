#!/usr/bin/env python3
"""Install an application-menu launcher and desktop shortcut for the current Pi user."""
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
venv = root / ".venv"
if not venv.exists():
    subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)], check=True)
subprocess.run([str(venv / "bin" / "python"), "-m", "pip", "install", "-r",
                str(root / "requirements.txt")], check=True)
app_dir = Path.home() / ".local" / "share" / "applications"
app_dir.mkdir(parents=True, exist_ok=True)
icon_dir = Path.home() / ".local" / "share" / "icons"
icon_dir.mkdir(parents=True, exist_ok=True)
icon = icon_dir / "bloomcore-servos.svg"
icon.write_bytes((root / "servos-icon.svg").read_bytes())
desktop = ("[Desktop Entry]\nType=Application\nName=Servos\n"
           "Comment=BloomCore 16-servo and 8-motor controller\n"
           f"Exec=/usr/bin/python3 {root / 'launch.py'}\n"
           f"Icon={icon}\n"
           f"Path={root}\n"
           "Terminal=false\nCategories=Utility;Electronics;\nStartupNotify=true\n")
menu_entry = app_dir / "bloomcore-servos.desktop"
menu_entry.write_text(desktop)
menu_entry.chmod(0o755)
# XDG_DESKTOP_DIR may differ from ~/Desktop; resolve it without evaluating shell.
desktop_dir = Path.home() / "Desktop"
try:
    result = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, check=True)
    if result.stdout.strip():
        desktop_dir = Path(result.stdout.strip())
except (OSError, subprocess.CalledProcessError):
    pass
desktop_dir.mkdir(parents=True, exist_ok=True)
shortcut = desktop_dir / "Servos.desktop"
shortcut.write_text(desktop)
shortcut.chmod(0o755)
print(f"Installed application menu: {menu_entry}")
print(f"Installed desktop icon:    {shortcut}")
print("Double-click Servos. If asked, choose 'Allow Launching' / 'Trust and Launch'.")
print("Hardware mode is armed only by a button in the UI. Servo rail requires external power.")
