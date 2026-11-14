# SERVOS — Raspberry Pi PCA9685 control panel

Dark BloomCore-style local dashboard for **16 servo channels** and **8 reserved motor bays**.

- Six connected micro servos assumed on PCA9685 channels **0–5**; channels 6–15 are placeholders and cannot be moved.
- Eight motor slots are visible placeholders only; **no DC motor control driver has been implemented**.
- Rename servo tiles, adjust angle 0–180°, center individually, release individually, release all, arm, and stop/disarm.
- Local-only Python server; **simulation mode by default**, explicit `--hardware` to write to I²C.
- On startup **all PWM outputs are released**, nothing is commanded to move. ARM alone does not move servos.
- Default conservative **1000–2000 µs** pulse span; individual servo physical limits must still be verified.
- STOP releases PWM but **does not cut servo power**; use a real hardware power switch / emergency stop.

## Wiring / safety

Pi SDA GPIO2 (pin 3) → PCA9685 SDA; Pi SCL GPIO3 (pin 5) → SCL; Pi GND → PCA9685 GND; Pi 3.3V → PCA9685 VCC. Power **V+** servo rail from a **separate regulated ~5V supply** sized for the combined servo stall current, with **common GND** to the Pi. **Never run six servos from the Pi 5V or 3.3V rail.** Verify your breakout's wiring and the ratings of your specific servos.

Before using, mount horns so your linkage will not collide; 90° is not universally safe mechanically. E-stop hardware should cut servo power.

## Start on Raspberry Pi OS

```bash
git clone https://github.com/Etsimulocto/Servos.git
cd Servos
python3 app.py                         # simulated, no I2C commands
```

Open **http://127.0.0.1:8765** on the Pi in Firefox.

To test actual servos:

```bash
sudo raspi-config                     # Interface Options → I2C → Enable
sudo apt install -y i2c-tools python3-venv
sudo i2cdetect -y 1                   # verify PCA9685 appears at 40
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py --hardware
```

Browser: **http://127.0.0.1:8765**. Ensure wiring and power are safe *before* launching hardware mode.

## Architecture / expansion

`app.py` is the standard-library HTTP server and smbus2 PCA9685 adapter. `index.html` is the responsive, no-build frontend. The server deliberately binds only to localhost; do not expose an unauthenticated motor controller to the public network. Angles and names reset when the process restarts. Future phases: editable per-servo calibrations and connected-channel settings, movement interpolation, saveable poses, motor-driver selection and mappings, speed/forward/reverse/brake per motor, and hardwired E-stop.

## Input mapper (V2)

Each servo card has **negative / positive** input slots. Click a slot and press any keyboard key, gamepad button, or move a gamepad axis. Controller IDs are read from the browser Gamepad API; multiple controllers are supported when they have distinct IDs. Click × to unbind. Mappings and renamed channels are stored locally in `servo-mappings.json` and survive restarts; that file is excluded from git.

Keyboard: the browser window must have focus. Gamepads: press a button so Firefox recognizes the controller. Holding an assigned key or gamepad direction steps the channel by **2° at most every 125 ms**, within its configured range. Button and axis controls require returning to released/neutral after arming before movement; STOP/DISARM releases PWM. Do not use this interface for load-bearing or safety-critical motion.

**External devices:** Browser-recognized USB/Bluetooth gamepads display their device ID automatically and can be assigned. Generic USB serial devices, MIDI, custom HID, and Raspberry Pi `/dev/input/event*` inputs not exposed to Firefox are **not yet implemented**; these require a Linux input adapter. Keyboard ID separation is not available through ordinary browser keyboard events.

**Updating:** close running old app processes before `git pull` and relaunch the new code. Existing running processes continue to serve old HTML until restarted.

## SG90 calibration + live controller diagnostics (V3)

The **Input Devices** panel displays every browser-detected controller's identifier, raw axes in the range -1.00 to +1.00, currently held buttons, and each connected channel's binding activation. It is read-only and functions while DISARMED.

Every servo card now has three saved calibration fields:
- **Min µs**: 1000–1500; default 1000.
- **Max µs**: 1500–2000; default 2000.
- **Measured travel °**: 30–180; default 90, entered by the user. This only changes the on-screen *estimated* physical-angle display: it is not position feedback and does not alter pulse output.
  
The pulse endpoints affect the PCA9685 output and are bounded to the existing conservative range. Calibration edits are only accepted while **DISARMED**, and are persisted alongside mappings in `servo-mappings.json`. No servo is commanded merely by saving calibration or arming. Changes are not auto-applied to an already running process: stop and restart it after pulling Git updates.

**Test procedure:** disconnect any overheated/damaged servo, check 5V and common ground, connect only one known-good unloaded SG90 to the intended output, test the controller axis readings while disarmed, then cautiously test a small servo movement. Stop immediately at abnormal heat, buzzing, or binding.

This is an open-loop driver. PWM release after 0.6 seconds is not a power disconnect; it cannot determine position, stall, temperature, or protect against incorrect wiring. A hardware supply cutoff is recommended. **Do not use automatic movement unattended.**

## Copyable diagnostics (V3.1)

The Input Devices panel includes **COPY DIAGNOSTIC LOG**, a selectable read-only text box, **FREEZE / REFRESH SNAPSHOT**, and **CLEAR EVENTS**. The report contains detected controller IDs, live axis and button values, binding states for all channels, pulse settings, controller arm/mode state, and up to 80 recent browser control actions/errors. Copy captures an up-to-date snapshot. If Firefox disallows clipboard access, select the text and use Ctrl+C. This is a browser-side diagnostic snapshot, **not** a persistent Python traceback log; startup failures remain in `servos-launch.log`.
