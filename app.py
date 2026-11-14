#!/usr/bin/env python3
"""Servos: local-only PCA9685 servo control panel. Python standard library + smbus2."""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CHANNELS = 16
MOTORS = 8
HTML = Path(__file__).with_name("index.html").read_bytes()

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
        self.channels = [
            dict(id=i, name=f"Servo {i+1:02d}", connected=(i < 6),
                 angle=90, min_angle=0, max_angle=180,
                 min_us=1000, max_us=2000, output=False)
            for i in range(CHANNELS)
        ]

    def state(self):
        with self.lock:
            return dict(mode="HARDWARE" if self.driver else "SIMULATION",
                        armed=self.armed, servos=[dict(x) for x in self.channels],
                        motors=[dict(id=i, name=f"Motor {i+1:02d}", status="RESERVED")
                                for i in range(MOTORS)])

    def handle(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Expected an object")
        op = payload.get("action")
        with self.lock:
            if op == "arm":
                # No movement on arming. A subsequent intentional servo command is required.
                self.armed = True
            elif op in ("disarm", "stop"):
                self.armed = False
                self.release_all()
            elif op == "release_all":
                self.release_all()
            elif op in ("angle", "release", "rename"):
                idx = payload.get("channel")
                if type(idx) is not int or not (0 <= idx < CHANNELS):
                    raise ValueError("Invalid servo channel")
                servo = self.channels[idx]
                if op == "rename":
                    name = payload.get("name")
                    if not isinstance(name, str) or not (1 <= len(name.strip()) <= 32):
                        raise ValueError("Name must be 1 to 32 characters")
                    servo["name"] = name.strip()
                elif op == "release":
                    if self.driver:
                        self.driver.release(idx)
                    servo["output"] = False
                else:
                    if not self.armed:
                        raise ValueError("Arm the controller first")
                    if not servo["connected"]:
                        raise ValueError("Channel is reserved; not connected")
                    angle = payload.get("angle")
                    if type(angle) not in (int, float) or not (0 <= angle <= 180):
                        raise ValueError("Angle must be 0 to 180")
                    if not servo["min_angle"] <= angle <= servo["max_angle"]:
                        raise ValueError("Outside configured limits")
                    us = round(servo["min_us"] + (angle / 180) *
                               (servo["max_us"] - servo["min_us"]))
                    if self.driver:
                        self.driver.set_us(idx, us)
                    servo["angle"] = round(angle)
                    servo["output"] = True
            else:
                raise ValueError("Unknown action")
            return self.state()

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
        if self.path == "/":
            self._reply(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._reply(200, controller.state())
        else:
            self._reply(404, {"error": "Not found"})

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
    print(f"Servos {controller.state()['mode']} at http://{args.bind}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        with controller.lock:
            controller.armed = False
            controller.release_all()
            if controller.driver:
                controller.driver.close()

if __name__ == "__main__":
    main()
