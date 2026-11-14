#!/usr/bin/env python3
"""Servos: local-only PCA9685 servo control panel. Python standard library + smbus2."""
import argparse
import json
import threading
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_VERSION = '3.4.3'
CHANNELS = 16
MOTORS = 8
HTML = Path(__file__).with_name("index.html").read_bytes()
CONFIG = Path(__file__).with_name("servo-mappings.json")

class PCA9685:
    def __init__(self, address=0x40, bus_number=1):
        from smbus2 import SMBus
        import time
        self.bus = SMBus(bus_number)
        self.addr = address
        self.lock = threading.Lock()
        with self.lock:
            self.bus.write_byte_data(address, 0x00, 0x10)  # sleep before prescale
            self.bus.write_byte_data(address, 0xFE, 121)   # ~50 Hz at 25 MHz
            self.bus.write_byte_data(address, 0x01, 0x04)  # output driver
            for ch in range(CHANNELS):
                self._off(ch)  # release every channel at startup
            self.bus.write_byte_data(address, 0x00, 0x20)  # wake; auto-increment
        time.sleep(0.005)

    def _off(self, ch):
        base = 0x06 + 4 * ch
        self.bus.write_i2c_block_data(self.addr, base, [0, 0, 0, 0x10])

    def release(self, ch):
        with self.lock:
            self._off(ch)

    def set_us(self, ch, us):
        # 20 ms cycle / 4096 steps, at configured ~50 Hz.
        ticks = max(1, min(4095, round(us * 4096 / 20000)))
        base = 0x06 + 4 * ch
        with self.lock:
            self.bus.write_i2c_block_data(self.addr, base,
                                           [0, 0, ticks & 255, (ticks >> 8) & 15])

    def close(self):
        try:
            with self.lock:
                for ch in range(CHANNELS):
                    self._off(ch)
        finally:
            self.bus.close()

class Controller:
    def __init__(self, hardware=False, address=0x40, bus=1):
        self.lock = threading.RLock()
        self.driver = PCA9685(address, bus) if hardware else None
        self.armed = False
        self.last_command = [0.0] * CHANNELS
        self.shutdown = threading.Event()
        self.channels = [
            dict(id=i, name=f"Servo {i+1:02d}", connected=(i < 6),
                 angle=90, min_angle=0, max_angle=180,
                 min_us=1000, max_us=2000, physical_span=90, map_min=60, map_max=120, speed=4, armed=False, output=False)
            for i in range(CHANNELS)
        ]
        self.bindings = {str(i): {"negative": None, "positive": None} for i in range(CHANNELS)}
        self._load_config()

    def _load_config(self):
        if not CONFIG.exists():
            return
        try:
            data = json.loads(CONFIG.read_text())
            for i, servo in enumerate(self.channels):
                name = data.get("names", {}).get(str(i))
                if isinstance(name, str) and 1 <= len(name) <= 32:
                    servo["name"] = name
                cal = data.get("calibration", {}).get(str(i), {})
                if isinstance(cal, dict):
                    lo, hi, span = cal.get("min_us"), cal.get("max_us"), cal.get("physical_span")
                    if (type(lo) is int and type(hi) is int and
                        1000 <= lo <= 1500 and 1500 <= hi <= 2000 and
                        lo < hi and type(span) is int and 30 <= span <= 180):
                        servo["min_us"], servo["max_us"] = lo, hi
                        servo["physical_span"] = span
                mapped = data.get("mapped_limits", {}).get(str(i), {})
                if isinstance(mapped, dict):
                    mn, mx = mapped.get("min"), mapped.get("max")
                    if type(mn) is int and type(mx) is int and 0 <= mn < 90 < mx <= 180:
                        servo["map_min"], servo["map_max"] = mn, mx
                saved_speed = data.get("speeds", {}).get(str(i))
                if type(saved_speed) is int and 1 <= saved_speed <= 8:
                    servo["speed"] = saved_speed
                for direction in ("negative", "positive"):
                    binding = data.get("bindings", {}).get(str(i), {}).get(direction)
                    if self._valid_binding(binding):
                        self.bindings[str(i)][direction] = binding
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @staticmethod
    def _valid_binding(b):
        if b is None:
            return True
        if not isinstance(b, dict) or b.get("type") not in ("keyboard", "gamepad_button", "gamepad_axis"):
            return False
        if b["type"] == "keyboard":
            return isinstance(b.get("code"), str) and 1 <= len(b["code"]) <= 40
        return (isinstance(b.get("device_id"), str) and len(b["device_id"]) <= 256
                and type(b.get("index")) is int and 0 <= b["index"] <= 127
                and (b["type"] != "gamepad_axis" or b.get("direction") in (-1, 1)))

    def _save_config(self):
        data = {"names": {str(s["id"]): s["name"] for s in self.channels},
                "bindings": self.bindings,
                "speeds": {str(s["id"]): s["speed"] for s in self.channels},
                "mapped_limits": {str(s["id"]): {"min": s["map_min"], "max": s["map_max"]} for s in self.channels},
                "calibration": {str(s["id"]): {
                    "min_us": s["min_us"], "max_us": s["max_us"],
                    "physical_span": s["physical_span"]} for s in self.channels}}
        temp = CONFIG.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2) + "\n")
        os.replace(temp, CONFIG)

    def state(self):
        with self.lock:
            return dict(version=APP_VERSION, mode="HARDWARE" if self.driver else "SIMULATION",
                        armed=self.armed, bindings=self.bindings, servos=[dict(x) for x in self.channels],
                        motors=[dict(id=i, name=f"Motor {i+1:02d}", status="RESERVED")
                                for i in range(MOTORS)])

    def handle(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Expected an object")
        op = payload.get("action")
        with self.lock:
            if op == "arm":
                # No movement on arming. A subsequent intentional servo command is required.
                for servo in self.channels:
                    servo["armed"] = bool(servo["connected"])
                self.armed = any(s["armed"] for s in self.channels)
            elif op in ("disarm", "stop"):
                for servo in self.channels:
                    servo["armed"] = False
                self.armed = False
                self.release_all()
            elif op == "release_all":
                self.release_all()
            elif op in ("angle", "release", "rename", "binding", "calibration", "mapped_limits", "arm_channel", "disarm_channel", "speed"):
                idx = payload.get("channel")
                if type(idx) is not int or not (0 <= idx < CHANNELS):
                    raise ValueError("Invalid servo channel")
                servo = self.channels[idx]
                if op == "arm_channel":
                    if not servo["connected"]:
                        raise ValueError("Cannot arm a reserved channel")
                    # Arming only grants permission; it never commands a position.
                    servo["armed"] = True
                    self.armed = True
                elif op == "disarm_channel":
                    # Release only this channel; others remain unchanged.
                    if self.driver:
                        self.driver.release(idx)
                    servo["output"] = False
                    servo["armed"] = False
                    self.armed = any(s["armed"] for s in self.channels)
                elif op == "rename":
                    name = payload.get("name")
                    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 32):
                        raise ValueError("Name must be 1 to 32 characters")
                    servo["name"] = name.strip()
                    self._save_config()
                elif op == "binding":
                    direction = payload.get("direction")
                    binding = payload.get("binding")
                    if direction not in ("negative", "positive") or not self._valid_binding(binding):
                        raise ValueError("Invalid input binding")
                    self.bindings[str(idx)][direction] = binding
                    self._save_config()
                elif op == "calibration":
                    # Calibration changes are only permitted while disarmed.
                    if servo["armed"]:
                        raise ValueError("Disarm this channel before changing calibration")
                    lo = payload.get("min_us")
                    hi = payload.get("max_us")
                    span = payload.get("physical_span")
                    if not (type(lo) is int and type(hi) is int and type(span) is int
                            and 1000 <= lo <= 1500 and 1500 <= hi <= 2000
                            and lo < hi and 30 <= span <= 180):
                        raise ValueError("Safe range: min 1000–1500 µs, max 1500–2000 µs, estimated travel 30–180°")
                    servo["min_us"], servo["max_us"], servo["physical_span"] = lo, hi, span
                    self._save_config()
                elif op == "mapped_limits":
                    if servo["armed"]:
                        raise ValueError("Disarm this channel before editing gamepad limits")
                    minimum, maximum = payload.get("minimum"), payload.get("maximum")
                    if not (type(minimum) is int and type(maximum) is int and
                            0 <= minimum < 90 < maximum <= 180):
                        raise ValueError("Limits must satisfy 0 <= minimum < 90 < maximum <= 180")
                    servo["map_min"], servo["map_max"] = minimum, maximum
                    self._save_config()
                elif op == "speed":
                    if servo["armed"]:
                        raise ValueError("Disarm channel before setting movement speed")
                    speed = payload.get("speed")
                    if type(speed) is not int or not 1 <= speed <= 8:
                        raise ValueError("Speed must be between 1 and 8 degrees per step")
                    servo["speed"] = speed
                    self._save_config()
                elif op == "release":
                    if self.driver:
                        self.driver.release(idx)
                    servo["output"] = False
                else:
                    if not servo["armed"]:
                        raise ValueError("Arm this servo channel first")
                    if not servo["connected"]:
                        raise ValueError("Channel is reserved; not connected")
                    angle = payload.get("angle")
                    if type(angle) not in (int, float) or not (0 <= angle <= 180):
                        raise ValueError("Angle must be 0 to 180")
                    if payload.get("source") == "mapped" and not servo["map_min"] <= angle <= servo["map_max"]:
                        raise ValueError("Mapped input exceeds this channel\u0027s configured limits")
                    if not servo["min_angle"] <= angle <= servo["max_angle"]:
                        raise ValueError("Outside configured limits")
                    us = round(servo["min_us"] + (angle / 180) *
                               (servo["max_us"] - servo["min_us"]))
                    if self.driver:
                        self.driver.set_us(idx, us)
                    servo["angle"] = round(angle)
                    servo["output"] = True
                    self.last_command[idx] = time.monotonic()
            else:
                raise ValueError("Unknown action")
            return self.state()

    def watchdog(self):
        # Releasing PWM does not disconnect power or detect stalls.
        while not self.shutdown.wait(0.1):
            with self.lock:
                now = time.monotonic()
                for servo in self.channels:
                    idx = servo["id"]
                    if servo["output"] and now - self.last_command[idx] > 0.6:
                        try:
                            if self.driver:
                                self.driver.release(idx)
                            servo["output"] = False
                        except OSError:
                            servo["armed"] = False
                            self.armed = any(s["armed"] for s in self.channels)

    def release_all(self):
        for servo in self.channels:
            if self.driver:
                self.driver.release(servo["id"])
            servo["output"] = False

controller = None

class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, data, mime="application/json"):
        raw = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        route = urlsplit(self.path).path
        if route == "/api/state":
            self._reply(200, controller.state())
        elif route == "/favicon.ico":
            self._reply(204, b"", "image/x-icon")
        elif route in ("/", "/index.html", "/servos", "/servos/"):
            self._reply(200, HTML, "text/html; charset=utf-8")
        elif route.startswith("/api/"):
            self._reply(404, {"error": "API endpoint not found"})
        else:
            # Friendly redirect for bookmarked paths: the UI is always at '/'.
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):
        if self.path != "/api/control":
            return self._reply(404, {"error": "Not found"})
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return self._reply(415, {"error": "Expected application/json"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size))
            self._reply(200, controller.handle(payload))
        except (ValueError, KeyError, json.JSONDecodeError) as ex:
            self._reply(400, {"error": str(ex)})
        except OSError as ex:
            controller.armed = False
            for servo in controller.channels:
                servo["armed"] = False
            self._reply(503, {"error": f"I2C hardware error: {ex}"})

def main():
    global controller
    parser = argparse.ArgumentParser()
    parser.add_argument("--hardware", action="store_true", help="Enable PCA9685 writes")
    parser.add_argument("--bind", default="127.0.0.1", help="Default: loopback only")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--address", type=lambda s: int(s, 0), default=0x40)
    parser.add_argument("--bus", type=int, default=1)
    args = parser.parse_args()
    controller = Controller(args.hardware, args.address, args.bus)
    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    watcher = threading.Thread(target=controller.watchdog, daemon=True)
    watcher.start()
    print(f"Servos {controller.state()['mode']} at http://{args.bind}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        controller.shutdown.set()
        watcher.join(timeout=2)
        with controller.lock:
            controller.armed = False
            for servo in controller.channels:
                servo["armed"] = False
            controller.release_all()
            if controller.driver:
                controller.driver.close()

if __name__ == "__main__":
    main()
