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

## Adjustable gamepad travel (V3.2)

Each servo has independent **Gamepad min °** and **Gamepad max °** fields. Defaults stay 60–120 for caution, but the user may widen the commanded angle range (minimum 0–89; maximum 91–180) while DISARMED. Click **SAVE GAMEPAD LIMITS**; values persist in `servo-mappings.json` and are enforced by both the browser and server. Increase the range in small increments and observe the physical servo: 0–180 dashboard degrees do **not** necessarily correspond to 180 physical degrees. Nothing in the interface measures stalls, voltage, current, or temperature. Never use a servo that has overheated or is unresponsive.

## V3.3 — Per-channel ARM / DISARM

Each of 16 servo cards shows a channel-specific **ARM CH** or **DISARM CH** button. Reserved channels cannot be armed. A channel starts disarmed, as do all channels when the server starts. Arming does **not** move the servo. Movement from slider, center, keyboard, or gamepad is allowed only for individually armed channels. **DISARM CH** releases that channel's PCA9685 PWM output, leaving other channels alone. Global **ARM ALL** arms only configured connected channels; global **STOP / DISARM** disarms all channels and releases all PWM outputs. **RELEASE ALL** releases PWM without changing which channels are armed. Per-channel arm state is intentionally not persisted; reboot always starts safe. Changes to calibration and mapped travel limits require the relevant channel to be disarmed. The diagnostic log includes arm state per channel.

PWM release does **not** physically disconnect servo power. Power off before rewiring; do not use a damaged/overheated servo. To upgrade, stop all existing Servos processes, run `git pull origin main`, and launch the desktop icon again.

## V3.4 — Adjustable input movement speed

Each servo has a **GAMEPAD MOVEMENT SPEED** slider, saved per channel to `servo-mappings.json`. Step size is 1–8 dashboard degrees per 125ms, defaulting to 4 (previously fixed at 2). The speed applies to mapped gamepad and keyboard input, not manual slider jumps. The default corresponds to at most 32 commanded degrees/second; physical rotation depends on servo calibration, load, and the browser/network round-trip. Settings can only be edited when that channel is disarmed. Travel limits and idle PWM release remain in effect. Increase cautiously and stop at buzzing, heat or binding.

## V3.5 — Extended pulse calibration for physical travel

The min/max pulse width calibration is now 500–1500 µs for minimum and 1500–2500 µs for maximum, with the **existing 1000–2000 µs default unchanged**. The server validates and saves both settings only when that servo channel is DISARMED. When either endpoint extends beyond the default range, the UI requires explicit confirmation. The pulse mapping remains linear between the selected endpoints; editing `Measured travel °` changes only a displayed estimate.

**Do not assume an SG90 can travel 180°**: variants differ, and mechanical stops can be closer than the commanded range. Start at 900–2100 µs if the servo moves freely over 1000–2000 µs, and only increase farther in small increments while watching for buzzing, heating, binding or current spikes. Unload the servo arm for calibration and disconnect external servo power immediately if it stalls. Never set 500–2500 µs blindly. PWM watchdog releases the signal after 0.6s inactivity but cannot cut supply power or detect stalls. If you need continuous 360° spinning rather than positional travel, a continuous-rotation servo is a different hardware class.

## V3.6 — Manual shaft-movement video recorder

A **Manual rotation recorder** section includes opt-in camera preview, **RECORD**, **STOP RECORDING**, and **DOWNLOAD VIDEO** controls. The webcam captures what the user does with the servo shaft by hand; SG90 three-wire servos do not provide electrical position feedback. Record with servo supply **disconnected**, using a visible pointer on the horn and preferably a protractor behind it. During a recording, click **LEFT STOP**, **CENTER**, and **RIGHT STOP** to add relative time markers. **DOWNLOAD MARKERS (.JSON)** saves a separate note file with timestamps and a snapshot of the app's displayed channel parameters. Firefox's standard camera permission is required; video is recorded in the browser using MediaRecorder (WebM where supported) and is **not uploaded** or transferred to the Python server. Download the recording before navigating away or refreshing; video is held in page memory. Avoid forcing mechanical stops, even with power disconnected.

### V3.6.1 diagnostic extension

The maximum calibration pulse accepts up to 2800 µs for a sacrificial SG90 test only, explicitly confirmed above 2500 µs in the UI and required by the backend API (`extended_confirmed: true`). Existing settings stay unchanged. Increase by at most 50 µs between tests, with the servo unloaded and a quick external power disconnect available; stop if motion stops increasing, there is buzzing, mechanical binding or heat. This extension is outside normal SG90 specifications and may permanently damage a servo. Do not mistake 180° hand rotation for guaranteed powered travel.

### V3.6.2 — Experimental ceiling 3500 µs

Maximum pulse width can now be entered up to **3500 µs** while a channel is disarmed. Above 2500 µs the UI presents an explicit high-risk confirmation and the Python backend requires `extended_confirmed: true`. The default remains unchanged. This extension is for troubleshooting an expendable unit only: 3500 µs is outside typical SG90 specifications. At nearly 90° to one side already by 2500 µs, further pulses may push the servo into its mechanical stop. Use an unloaded horn, controlled incremental tests, and a physical external power disconnect; do not continue through buzzing, binding or heating. A full 180° travel does not require exceeding endpoints.

## V3.7 — PWM Diagnostics & Timing panel

Every hidden timing value is now visible on the Servos dashboard. **Editable global settings** (require DISARM ALL and explicit confirmation): target PWM frequency 40–100 Hz (default 50), assumed PCA9685 oscillator 23–27 MHz (default 25 MHz), angle mapping divisor 90–360 (default 180), and idle PWM release watchdog 200–3000 ms (default 600). These are persisted under `timing` in `servo-mappings.json`; the rest of the saved per-servo configuration remains intact. A reset button restores these four global timing defaults.

**Read-only derived values**: PCA9685 hardware resolution (4096 ticks), prescaler register computed from selected clock and target frequency, nominal output frequency, and calculated PWM period. The device is programmed using that derived prescaler, and the microsecond-to-tick conversion now uses the same derived nominal frequency (rather than a fixed 20,000 µs constant). The frequency may slightly differ from the requested target because prescaler is an integer. Clock is an **assumption**, not a hardware measurement; an oscilloscope or logic analyzer is required to determine actual PWM timing.

Each channel's diagnostic output now includes requested pulse width, computed PWM ticks and nominal quantized pulse width. **These are predictions from configuration, NOT sensed servo position or measured wire voltage/timing.** PWM output can be released by the idle watchdog even though the last commanded angle remains in state.

Safety: global timing changes are rejected unless ALL channels are disarmed, and the PCA9685 is configured with every output disabled. The angle divisor is a software mapping denominator: changing it alters the pulse target at a given commanded dashboard degree; it does not magically increase a servo's safe travel. The watchdog releases the *signal* only and cannot remove external power. Keep servo power disconnected for initial configuration checks. A servo already approaching its mechanical stops at extreme pulse widths may be damaged if retimed.

## V3.8 three-point calibration

Each servo independently saves MIN/CENTER/MAX microsecond pulse values. Dashboard 0°, 90°, 180° map exactly to MIN, CENTER, MAX, with two independent linear segments between them. CENTER is a user-set electrical reference and need not be 1500 µs or the arithmetic midpoint. Existing two-point settings migrate with CENTER=(MIN+MAX)/2 rounded, preserving their previous mapping. Values persist in servo-mappings.json. Calibration requires disarming the channel; prior extended pulse confirmations remain. Global legacy angle divisor remains visible but no longer affects the three-point mapping. The diagnostics now print MIN/CENTER/MAX. These settings cannot measure physical angle or override mechanical servo stops.

## V3.9 — smooth mapped movement

Mapped keyboard/gamepad control now uses a nominal **25 ms** update loop with fractional angle accumulation. Speed 1–8 sets **8–64 commanded degrees per second**, rather than 1–8° jumps every 125 ms. The per-channel optional acceleration/deceleration checkbox is enabled by default and saved as `ramps` with the speed; when the input is released the controller immediately stops sending new position commands (no coast). As a mapped limit is approached, ramp mode reduces the commanded rate. Full 16-channel UI rendering is throttled during motion, while displayed angles update on every acknowledged response. Browser-to-Pi HTTP round-trip can reduce actual update frequency. STOP, DISARM, and RELEASE are no longer rejected by the busy guard during an in-flight mapped command. Existing three-point MIN/CENTER/MAX PWM values and 50 Hz frequency are unchanged.

This improves the *commands*, not the servo's inherent motor speed or precision. Start unloaded and avoid pushing an extended-range endpoint into a mechanical stop.

## V3.10 — independent manual range and guarded copy calibration

Manual angle sliders continue to command 0–180° independently of mapped gamepad/keyboard min/max limits. The UI now labels that distinction. While a manual slider is being dragged, the mapped motion loop skips that channel to prevent a held gamepad input from fighting the drag; moving the slider sends its final angle when released, not a continuous stream of browser requests.

Every connected channel except CH 00 has a **COPY CH 00 PULSE CALIBRATION** button. It copies only MIN/CENTER/MAX/physical-span settings; it never copies input bindings, gamepad travel limits, motion speed, acceleration, or arm state. Both source and target must be DISARMED. The backend validates the source and target and requires explicit confirmation, plus a second extended-pulse confirmation if the copied calibration exceeds 1000–2000 µs. Copying does not move a servo. Calibration of individual servo endpoints is still necessary: a pulse range that works on CH 00 could mechanically stall or damage a different servo.
