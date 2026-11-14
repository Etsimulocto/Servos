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
