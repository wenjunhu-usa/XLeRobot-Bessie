#!/usr/bin/env python3
from local_config import get_port
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

CONFIG = {
    "left": (get_port("XLEROBOT_LEFT_HEAD_PORT"), "calibration/xlerobot_left_arm.json"),
    "right": (get_port("XLEROBOT_RIGHT_WHEELS_PORT"), "calibration/xlerobot_right_arm.json"),
}
buses, targets = {}, {}
lock = threading.Lock()

for side, (port, calibration_path) in CONFIG.items():
    saved = json.load(open(calibration_path))["gripper"]
    bus = FeetechMotorsBus(
        port=port,
        motors={"gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100)},
        calibration={"gripper": MotorCalibration(**saved)},
    )
    bus.connect()
    bus.disable_torque("gripper")
    bus.write("Operating_Mode", "gripper", OperatingMode.POSITION.value)
    bus.write("Acceleration", "gripper", 5)
    bus.write("Goal_Velocity", "gripper", 50, normalize=False)
    targets[side] = bus.read("Present_Position", "gripper")
    bus.write("Goal_Position", "gripper", targets[side])
    bus.enable_torque("gripper")
    buses[side] = bus

PAGE = b"""<!doctype html><meta charset=utf-8><title>XLeRobot Grippers</title>
<style>body{font:20px system-ui;max-width:850px;margin:50px auto;text-align:center;background:#111827;color:#f9fafb}.grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.card{background:#1f2937;border-radius:18px;padding:24px}button{font-size:22px;padding:16px 30px;margin:12px 6px;border:0;border-radius:12px;background:#2563eb;color:white}.s{font-size:22px;margin:20px}.warn{font-size:16px;color:#fbbf24}</style>
<h1>XLeRobot Gripper Control</h1><div class=grid>
<div class=card><h2>Left Gripper (ID 6)</h2><div class=s id=left>Loading...</div><button onclick=step('left',-1)>&minus; 1%</button><button onclick=step('left',1)>+ 1%</button></div>
<div class=card><h2>Right Gripper (ID 6)</h2><div class=s id=right>Loading...</div><button onclick=step('right',-1)>&minus; 1%</button><button onclick=step('right',1)>+ 1%</button></div>
</div><p class=warn>First test: keep fingers and objects outside both grippers.</p>
<script>async function state(){let r=await fetch('/api/state');let x=await r.json();for(let s of ['left','right'])document.getElementById(s).textContent=`Target ${x[s].target.toFixed(1)}% | Actual ${x[s].actual.toFixed(1)}%`}async function step(s,n){await fetch(`/api/step?side=${s}&amount=${n}`,{method:'POST'});setTimeout(state,250)}setInterval(state,1000);state()</script>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_): return
    def send_json(self, value):
        data = json.dumps(value).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if urlparse(self.path).path == "/":
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE); return
        if self.path == "/api/state":
            with lock:
                state = {side: {"target": targets[side], "actual": bus.read("Present_Position", "gripper")} for side, bus in buses.items()}
            self.send_json(state); return
        self.send_error(404)
    def do_POST(self):
        parsed = urlparse(self.path); query = parse_qs(parsed.query); side = query.get("side", [""])[0]
        if parsed.path != "/api/step" or side not in buses: self.send_error(400); return
        amount = max(-1.0, min(1.0, float(query.get("amount", ["0"])[0])))
        with lock:
            targets[side] = max(0.0, min(100.0, targets[side] + amount))
            buses[side].write("Goal_Position", "gripper", targets[side])
            self.send_json({"side": side, "target": targets[side]})

server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
print("Dual gripper controller: http://127.0.0.1:8765", flush=True)
try: server.serve_forever()
finally:
    for bus in buses.values(): bus.disconnect(disable_torque=False)
