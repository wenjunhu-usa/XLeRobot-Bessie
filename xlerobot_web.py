#!/usr/bin/env python3
from local_config import get_port
import fcntl, json, math, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import cv2
from pathlib import Path
from arm_gamepad import plan_steps, wheel_speeds
from cartesian_control import arm_pose, plan_cartesian
from data_collection.recorder import EpisodeRecorder

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

CAL = json.load(open("calibration/xlerobot_040.json"))
SAFETY = json.load(open("calibration/safety_limits.json"))["joints"]
controller_lock = open("/tmp/xlerobot-controller.lock", "w")
try:
    fcntl.flock(controller_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Another XLeRobot controller is already running.")
LEFT = ["left_arm_shoulder_pan", "left_arm_shoulder_lift", "left_arm_elbow_flex", "left_arm_wrist_flex", "left_arm_wrist_roll", "left_arm_gripper", "head_motor_1", "head_motor_2"]
RIGHT = ["right_arm_shoulder_pan", "right_arm_shoulder_lift", "right_arm_elbow_flex", "right_arm_wrist_flex", "right_arm_wrist_roll", "right_arm_gripper"]
WHEELS = ["base_left_wheel", "base_right_wheel"]
def calibrated_safe_limits(name):
    return [SAFETY[name]["min"], SAFETY[name]["max"]]

LIMITS = {name: calibrated_safe_limits(name) for name in LEFT + RIGHT}
META = {
    name: {
        "min": LIMITS[name][0], "max": LIMITS[name][1],
        "unit": "%" if name.endswith("gripper") else "deg",
        "raw_min": CAL[name]["range_min"], "raw_max": CAL[name]["range_max"],
    }
    for name in LEFT + RIGHT
}

def motor(name):
    mode = MotorNormMode.RANGE_0_100 if name.endswith("gripper") else MotorNormMode.DEGREES
    if name in WHEELS: mode = MotorNormMode.RANGE_M100_100
    return Motor(CAL[name]["id"], "sts3215", mode)

bus1 = FeetechMotorsBus(port=get_port("XLEROBOT_LEFT_HEAD_PORT"), motors={n:motor(n) for n in LEFT}, calibration={n:MotorCalibration(**CAL[n]) for n in LEFT})
bus2 = FeetechMotorsBus(port=get_port("XLEROBOT_RIGHT_WHEELS_PORT"), motors={n:motor(n) for n in RIGHT+WHEELS}, calibration={n:MotorCalibration(**CAL[n]) for n in RIGHT+WHEELS})
lock = threading.Lock(); buses = {**{n:bus1 for n in LEFT}, **{n:bus2 for n in RIGHT+WHEELS}}
estop = {"active": False, "reason": ""}
last_gamepad_step = 0.0
gamepad = {"mode": "arms", "token": None, "wheel_deadline": 0.0}
keyboard_session = {"token": None, "last_step": 0.0}
cartesian_session = {"token": None, "last_step": 0.0}
bus1.connect(); bus1.disable_torque()
try:
    bus2.connect(); bus2.disable_torque()
except Exception:
    bus1.disconnect(disable_torque=True)
    raise
for name in LEFT+RIGHT:
    b=buses[name]; b.write("Operating_Mode",name,OperatingMode.POSITION.value); b.write("Acceleration",name,5); b.write("Goal_Velocity",name,50,normalize=False)
    # P=16 is intentionally soft, but loaded shoulder/elbow joints can stall
    # against gravity even with the full 6 degree bounded target lead. 24 is
    # below the STS3215 default (32) while restoring usable bidirectional
    # motion for the weight-bearing joints.
    if name.endswith(("shoulder_lift", "elbow_flex")):
        b.write("P_Coefficient",name,24,normalize=False)
for name in WHEELS: bus2.write("Operating_Mode",name,OperatingMode.VELOCITY.value)
targets = {**bus1.sync_read("Present_Position",LEFT), **bus2.sync_read("Present_Position",RIGHT)}
actual_positions = dict(targets)
startup_bad=[
    name for name,value in targets.items()
    if not math.isfinite(value) or value<LIMITS[name][0] or value>LIMITS[name][1]
]
if startup_bad:
    bus2.sync_write("Goal_Velocity",dict.fromkeys(WHEELS,0),normalize=False)
    bus1.disconnect(disable_torque=False);bus2.disconnect(disable_torque=False)
    raise SystemExit("DO NOT MOVE: startup pose is outside safety limits: "+", ".join(startup_bad))
bus1.sync_write("Goal_Position",{n:targets[n] for n in LEFT}); bus2.sync_write("Goal_Position",{n:targets[n] for n in RIGHT})
bus2.sync_write("Goal_Velocity",dict.fromkeys(WHEELS,0),normalize=False); bus1.enable_torque(); bus2.enable_torque()

CAMERA_PATHS={"left":get_port("XLEROBOT_LEFT_CAMERA"),"right":get_port("XLEROBOT_RIGHT_CAMERA")}
def open_camera(path):
    camera=cv2.VideoCapture(path)
    camera.set(cv2.CAP_PROP_FOURCC,cv2.VideoWriter_fourcc(*"MJPG"))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH,640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
    camera.set(cv2.CAP_PROP_FPS,30)
    camera.set(cv2.CAP_PROP_BUFFERSIZE,1)
    return camera

cams={name:open_camera(path) for name,path in CAMERA_PATHS.items()}
cam_locks={name:threading.Lock() for name in cams}
cam_frames={name:None for name in cams}
cam_health={name:{"frames":0,"failures":0,"reconnects":0,"updated":0.0,"error":""} for name in cams}
camera_stop=threading.Event()
for name,c in cams.items():
    if not c.isOpened(): print(f"Warning: camera {name} could not be opened",flush=True)

def camera_reader(name,camera):
    """Continuously drain the device buffer and retain only the newest JPEG."""
    next_encode=0.0
    consecutive_failures=0
    while not camera_stop.is_set():
        ok,frame=camera.read()
        if not ok:
            consecutive_failures+=1
            with cam_locks[name]:
                cam_health[name]["failures"]+=1
                cam_health[name]["error"]="camera read failed"
            if consecutive_failures>=20:
                camera.release()
                camera_stop.wait(0.25)
                camera=open_camera(CAMERA_PATHS[name])
                cams[name]=camera
                consecutive_failures=0
                with cam_locks[name]: cam_health[name]["reconnects"]+=1
            camera_stop.wait(0.05)
            continue
        consecutive_failures=0
        now=time.monotonic()
        if now < next_encode: continue
        next_encode=now+0.05
        ok,jpg=cv2.imencode(".jpg",frame,[cv2.IMWRITE_JPEG_QUALITY,75])
        if ok:
            with cam_locks[name]:
                cam_frames[name]=jpg.tobytes()
                cam_health[name]["frames"]+=1
                cam_health[name]["updated"]=now
                cam_health[name]["error"]=""

camera_threads=[]
for name,camera in cams.items():
    thread=threading.Thread(target=camera_reader,args=(name,camera),daemon=True,name=f"camera-{name}")
    thread.start();camera_threads.append(thread)

RECORDED_JOINTS = [n for n in LEFT if n.startswith("left_arm_")] + RIGHT + ["head_motor_1", "head_motor_2"]
def recording_snapshot():
    with lock:
        state=[float(actual_positions[n]) for n in RECORDED_JOINTS]
        action=[float(targets[n]) for n in RECORDED_JOINTS]
        following=[action[i]-state[i] for i in range(len(state))]
    with cam_locks["left"],cam_locks["right"]:
        images={name:cam_frames[name] for name in ("left","right")}
        camera_age={name:None if not cam_health[name]["updated"] else time.monotonic()-cam_health[name]["updated"] for name in images}
    return {"observation_state":state,"action":action,"following_error":following,"camera_age_s":camera_age,"images":images}

recorder=EpisodeRecorder(Path(__file__).with_name("collected_data")/"raw",RECORDED_JOINTS,recording_snapshot,fps=20)

def stop_motion(reason):
    """Caller must hold lock. Stop wheels and hold every position motor where it is."""
    gamepad["token"] = None
    gamepad["wheel_deadline"] = 0.0
    keyboard_session["token"] = None
    cartesian_session["token"] = None
    estop["active"], estop["reason"] = True, reason
    bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
    actual = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
    actual_positions.update(actual)
    for name, value in actual.items():
        lo, hi = LIMITS[name]
        targets[name] = max(lo, min(hi, value))
    bus1.sync_write("Goal_Position", {n: targets[n] for n in LEFT})
    bus2.sync_write("Goal_Position", {n: targets[n] for n in RIGHT})

def revoke_control_sessions(stop_wheels=True):
    """Caller must hold lock. Make all previously issued control tokens stale."""
    gamepad["token"] = None
    gamepad["wheel_deadline"] = 0.0
    keyboard_session["token"] = None
    cartesian_session["token"] = None
    if stop_wheels:
        bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)

def stop_wheels_at(deadline):
    """Stop a manual wheel pulse without holding the controller lock asleep."""
    delay = max(0.0, deadline-time.monotonic())
    if delay: time.sleep(delay)
    with lock:
        if gamepad["wheel_deadline"] == deadline:
            bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
            gamepad["wheel_deadline"] = 0.0

def apply_position_plan(planned,enforce_following=False,following_deg=6.0):
    """Caller must hold lock. Write coordinated targets once per motor bus."""
    if enforce_following:
        lagging=[
            name for name,value in planned.items()
            if (name.endswith("gripper") and abs(value-actual_positions[name])>10.0)
            or (not name.endswith("gripper") and abs(value-actual_positions[name])>following_deg)
        ]
        if lagging: raise ValueError("Arm has not caught up; rejected target: "+", ".join(lagging))
    left={name:value for name,value in planned.items() if name in LEFT}
    right={name:value for name,value in planned.items() if name in RIGHT}
    if left: bus1.sync_write("Goal_Position",left)
    if right: bus2.sync_write("Goal_Position",right)
    targets.update(planned)

def watchdog():
    while True:
        time.sleep(0.2)
        try:
            with lock:
                if gamepad["wheel_deadline"] and time.monotonic() >= gamepad["wheel_deadline"]:
                    bus2.sync_write("Goal_Velocity", dict.fromkeys(WHEELS, 0), normalize=False)
                    gamepad["wheel_deadline"] = 0.0
                    gamepad["token"] = None
                actual = {**bus1.sync_read("Present_Position", LEFT), **bus2.sync_read("Present_Position", RIGHT)}
                actual_positions.update(actual)
                if not estop["active"]:
                    for name, value in actual.items():
                        lo, hi = LIMITS[name]
                        if not math.isfinite(value) or value < lo or value > hi:
                            stop_motion(f"{name} actual {value:.1f} exceeded safe range {lo:.1f}…{hi:.1f}")
                            break
        except Exception as exc:
            with lock:
                gamepad["token"]=None
                gamepad["wheel_deadline"]=0.0
                keyboard_session["token"]=None
                cartesian_session["token"]=None
                estop["active"], estop["reason"] = True, f"Safety monitor communication error: {exc}"
                try: bus2.sync_write("Goal_Velocity",dict.fromkeys(WHEELS,0),normalize=False)
                except Exception: pass

threading.Thread(target=watchdog, daemon=True, name="xlerobot-safety-watchdog").start()

PAGE="""<!doctype html><meta charset=utf-8><title>XLeRobot Web Controller v2</title><style>body{font:16px system-ui;margin:20px;background:#0f172a;color:#e2e8f0}h1{text-align:center}.cams,.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}.cam,.panel{background:#1e293b;padding:14px;border-radius:14px}.cam img{width:100%;border-radius:8px}.joint{display:grid;grid-template-columns:1fr 90px;gap:7px;align-items:center;margin:9px 0}.joint small{display:block;color:#94a3b8;font-size:11px}.value{font-variant-numeric:tabular-nums;text-align:right}button{padding:9px;border:0;border-radius:8px;background:#2563eb;color:white;font-size:16px}button:disabled{background:#475569;color:#94a3b8}.base{text-align:center;margin:18px}.warn{color:#fbbf24}.safety{position:sticky;top:0;z-index:3;text-align:center;padding:12px;border-radius:10px;background:#166534}.safety.stop{background:#991b1b}</style><h1>XLeRobot Web Controller v2</h1><div id=safety class=safety>Safety monitor starting…</div><div class=base><button onclick=emergency()>EMERGENCY STOP</button> <button onclick=resetSafety()>Reset safety latch</button></div><div class=cams><div class=cam><b id=clabel>Camera Left</b><img id=cl></div><div class=cam><b id=crlabel>Camera Right</b><img id=cr></div></div><div class=cols><div class=panel><h2>Left arm + head</h2><div id=left></div></div><div class=panel><h2>Right arm</h2><div id=right></div></div></div><div class="panel base"><h2>Base wheels</h2><label class=warn><input id=raised type=checkbox> I confirm the wheels are raised off the floor</label><br><button class=motion onclick=base('left')>Rotate left</button> <button class=motion onclick=base('forward')>Forward</button> <button class=motion onclick=base('back')>Back</button> <button class=motion onclick=base('right')>Rotate right</button><p>Each click: low speed for 0.25 seconds, then automatic stop.</p></div><script>
const L=%LEFT%,R=%RIGHT%,M=%META%; function label(n){return n.replaceAll('_',' ')} function build(id,a){document.getElementById(id).innerHTML=a.map(n=>`<div class=joint><span>${label(n)}<small>safe ${M[n].min}…${M[n].max} ${M[n].unit} | raw ${M[n].raw_min}…${M[n].raw_max}</small></span><span class=value id="v-${n}">--</span></div>`).join('')} build('left',L);build('right',R);
async function state(){let x=await(await fetch('/api/state')).json();window.dispatchEvent(new CustomEvent('xlerobot-state',{detail:x}));for(let n of [...L,...R])document.getElementById('v-'+n).textContent=x.positions[n].toFixed(1)+(n.endsWith('gripper')?'%':'°');for(let side of ['left','right']){let c=x.cameras?.[side],el=document.getElementById(side==='left'?'clabel':'crlabel');if(c)el.textContent=`Camera ${side==='left'?'Left':'Right'} — ${c.age!==null&&c.age<=1?'LIVE':'STALE'} | frames ${c.frames} | reconnects ${c.reconnects}`}safety.textContent=x.estop.active?'STOPPED: '+x.estop.reason:'Safety monitor active — motion permitted';safety.className=x.estop.active?'safety stop':'safety';document.querySelectorAll('.base .motion').forEach(b=>b.disabled=x.estop.active)} async function base(c){if(!raised.checked){alert('Confirm wheels are raised first.');return}let r=await fetch(`/api/base?cmd=${c}`,{method:'POST'});if(!r.ok)alert(await r.text())}async function emergency(){await fetch('/api/estop',{method:'POST'});state()}async function resetSafety(){let r=await fetch('/api/reset',{method:'POST'});if(!r.ok)alert(await r.text());state()} function camera(img,url){const next=()=>setTimeout(()=>{img.src=url+'?t='+Date.now()},50);img.onload=next;img.onerror=next;img.src=url+'?t='+Date.now()}setInterval(state,500);state();camera(cl,'/camera/left.jpg');camera(cr,'/camera/right.jpg');</script>""".replace("%LEFT%",json.dumps(LEFT)).replace("%RIGHT%",json.dumps(RIGHT)).replace("%META%",json.dumps(META))

PAGE = PAGE.replace('</script>', '</script><script src="/cartesian_control.js"></script><script src="/gamepad_mapping.js"></script><script src="/arm_gamepad.js"></script><script src="/data_collection/recording_ui.js"></script>')

class H(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def out(self,code,data,ctype):
        try:
            self.send_response(code);self.send_header("Cache-Control","no-store");self.send_header("Content-Type",ctype);self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def do_GET(self):
        p=urlparse(self.path)
        if p.path=="/": return self.out(200,PAGE.encode(),"text/html; charset=utf-8")
        if p.path in ("/arm_gamepad.js", "/gamepad_mapping.js", "/cartesian_control.js"):
            return self.out(200,Path(__file__).with_name(p.path[1:]).read_bytes(),"application/javascript; charset=utf-8")
        if p.path=="/data_collection/recording_ui.js":
            return self.out(200,(Path(__file__).with_name("data_collection")/"recording_ui.js").read_bytes(),"application/javascript; charset=utf-8")
        if p.path=="/api/recording/status":
            return self.out(200,json.dumps(recorder.status()).encode(),"application/json")
        if p.path=="/api/state":
            with lock:
                s={**bus1.sync_read("Present_Position",LEFT),**bus2.sync_read("Present_Position",RIGHT)}
                target_snapshot=dict(targets)
            now=time.monotonic()
            with cam_locks["left"],cam_locks["right"]:
                camera_status={name:{**health,"age":None if not health["updated"] else now-health["updated"]} for name,health in cam_health.items()}
            poses={side:arm_pose(side,s) for side in ("left","right")}
            following={name:target_snapshot[name]-s[name] for name in LEFT+RIGHT}
            return self.out(200,json.dumps({"positions":s,"targets":target_snapshot,"following_error":following,"cartesian":poses,"cameras":camera_status,"estop":estop}).encode(),"application/json")
        if p.path=="/api/motor/diagnostics":
            names=["right_arm_shoulder_lift","right_arm_elbow_flex","right_arm_wrist_flex"]
            registers=["Present_Position","Goal_Position","Present_Load","Present_Current","Present_Temperature","Present_Voltage","P_Coefficient","Torque_Limit","Goal_Velocity"]
            diagnostics={}
            with lock:
                for name in names:
                    diagnostics[name]={}
                    for register in registers:
                        try: diagnostics[name][register]=bus2.read(register,name,normalize=False)
                        except Exception as exc: diagnostics[name][register]={"error":str(exc)}
            return self.out(200,json.dumps(diagnostics).encode(),"application/json")
        if p.path.startswith("/camera/"):
            side=p.path.split("/")[-1].split(".")[0]
            if side not in cams:return self.send_error(404)
            with cam_locks[side]:
                jpg=cam_frames[side]
                age=None if not cam_health[side]["updated"] else time.monotonic()-cam_health[side]["updated"]
            if jpg is None:return self.out(503,b"Camera frame not ready","text/plain")
            if age is None or age>1.0:return self.out(503,f"Camera {side} frame is stale ({age:.1f}s)".encode(),"text/plain")
            return self.out(200,jpg,"image/jpeg")
        self.send_error(404)
    def do_POST(self):
        global last_gamepad_step
        p=urlparse(self.path); q=parse_qs(p.query)
        if p.path in ("/api/recording/start","/api/recording/finish","/api/recording/discard"):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 1024: raise ValueError("Invalid request size")
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError("Expected object")
                if p.path.endswith("/start"): result=recorder.start(data.get("task",""))
                elif p.path.endswith("/finish"):
                    if not isinstance(data.get("success"),bool): raise ValueError("success must be boolean")
                    result=recorder.finish(data["success"])
                else: result=recorder.discard()
                return self.out(200,json.dumps(result).encode(),"application/json")
            except (ValueError,RuntimeError) as exc:
                return self.out(400,str(exc).encode(),"text/plain")
        if p.path in ("/api/keyboard/session", "/api/keyboard/move", "/api/keyboard/stop"):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 1024: raise ValueError("Invalid request size")
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError("Expected object")
                with lock:
                    if p.path=="/api/keyboard/stop":
                        supplied=data.get("token")
                        if supplied and supplied==keyboard_session["token"]:
                            keyboard_session["token"]=None
                        return self.out(200,b"{}","application/json")
                    if estop["active"]: return self.out(409,estop["reason"].encode(),"text/plain")
                    if p.path=="/api/keyboard/session":
                        revoke_control_sessions()
                        targets.update(actual_positions)
                        keyboard_session.update(token=uuid.uuid4().hex,last_step=0.0)
                        return self.out(200,json.dumps({"token":keyboard_session["token"]}).encode(),"application/json")
                    if not keyboard_session["token"] or data.get("token")!=keyboard_session["token"]:
                        return self.out(409,b"Keyboard control expired; re-enable keyboard","text/plain")
                    now=time.monotonic()
                    if now-keyboard_session["last_step"]<0.15:
                        return self.out(429,b"Keyboard rate limit","text/plain")
                    planned=plan_steps(data.get("steps"),targets,LIMITS,"arms")
                    # A 2 degree error is too small for a loaded shoulder/elbow
                    # to overcome gravity with the robot's intentionally soft
                    # P gain (16).  Permit a bounded 6 degree accumulated lead
                    # while a key is held.  This is large enough to start the
                    # joint, but still prevents the old ~20 degree target jump.
                    try:
                        apply_position_plan(planned,enforce_following=True,following_deg=6.0)
                    except ValueError as exc:
                        # Reaching the bounded lead while a key remains held is
                        # normal flow control: keep the session alive and let
                        # the next tick retry after the physical joint moves.
                        if str(exc).startswith("Arm has not caught up;"):
                            return self.out(200,b'{"waiting":true}',"application/json")
                        raise
                    keyboard_session["last_step"]=now
                return self.out(200,b"{}","application/json")
            except (ValueError,TypeError) as exc:
                return self.out(400,str(exc).encode(),"text/plain")
        if p.path in ("/api/cartesian/session", "/api/cartesian/move"):
            try:
                length=int(self.headers.get("Content-Length","0"))
                if not 0 < length <= 2048: raise ValueError("Invalid request size")
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict): raise ValueError("Expected object")
                with lock:
                    if p.path=="/api/cartesian/session":
                        if data.get("action")=="stop":
                            cartesian_session["token"]=None
                            return self.out(200,b"{}","application/json")
                        if data.get("action")!="start": raise ValueError("Invalid session action")
                        if estop["active"]: return self.out(409,estop["reason"].encode(),"text/plain")
                        revoke_control_sessions()
                        targets.update(actual_positions)
                        cartesian_session.update(token=uuid.uuid4().hex,last_step=0.0)
                        return self.out(200,json.dumps({"token":cartesian_session["token"]}).encode(),"application/json")
                    if estop["active"]: return self.out(409,estop["reason"].encode(),"text/plain")
                    if not cartesian_session["token"] or data.get("token")!=cartesian_session["token"]:
                        return self.out(409,b"Cartesian control expired; re-enable keyboard","text/plain")
                    now=time.monotonic()
                    if now-cartesian_session["last_step"]<0.08:
                        return self.out(429,b"Cartesian rate limit","text/plain")
                    # Integrate from the last accepted target so sub-degree
                    # shoulder steps can build past servo deadband. The
                    # following-error guard in apply_position_plan limits how
                    # far this target may lead the monitored physical pose.
                    planned=plan_cartesian(data.get("commands"),targets,LIMITS)
                    apply_position_plan(planned,enforce_following=True,following_deg=1.0)
                    cartesian_session["last_step"]=now
                return self.out(200,b"{}","application/json")
            except (ValueError,TypeError) as exc:
                return self.out(400,str(exc).encode(),"text/plain")
        if p.path in ("/api/gamepad/mode", "/api/gamepad/move", "/api/gamepad/stop"):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024: raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict): raise ValueError('Expected object')
                with lock:
                    if p.path == "/api/gamepad/stop":
                        # A disabled/stale UI must not revoke a newer gamepad
                        # session. Keyboard sessions use a separate endpoint.
                        supplied_token = data.get('token')
                        if supplied_token and supplied_token == gamepad['token']:
                            gamepad['token'] = None
                            gamepad['wheel_deadline'] = 0.0
                            bus2.sync_write('Goal_Velocity', dict.fromkeys(WHEELS, 0), normalize=False)
                        return self.out(200,b'{}','application/json')
                    if estop['active']: return self.out(409,estop['reason'].encode(),'text/plain')
                    if p.path == "/api/gamepad/mode":
                        mode = data.get('mode')
                        if mode not in ('arms', 'cartesian', 'head', 'wheels'): raise ValueError('Invalid mode')
                        revoke_control_sessions()
                        # Every newly enabled position-control session starts
                        # from the monitored physical pose. Reusing an older
                        # target can make the first small keyboard/gamepad step
                        # move in the wrong direction.
                        if mode in ('arms', 'cartesian', 'head'):
                            targets.update(actual_positions)
                        gamepad.update(mode=mode, token=uuid.uuid4().hex, wheel_deadline=0.0)
                        last_gamepad_step = 0.0
                        return self.out(200,json.dumps({'token':gamepad['token']}).encode(),'application/json')
                    if not gamepad['token'] or data.get('token') != gamepad['token']:
                        return self.out(409,b'Control expired; re-enable gamepad','text/plain')
                    mode = gamepad['mode']
                    if mode == 'wheels':
                        values = wheel_speeds(data.get('forward'), data.get('turn'), data.get('raised'))
                        bus2.sync_write('Goal_Velocity', dict(zip(WHEELS, values)), normalize=False)
                        gamepad['wheel_deadline'] = time.monotonic() + 0.4 if any(values) else 0.0
                    elif mode == 'cartesian':
                        planned=plan_cartesian(data.get('cartesian'),targets,LIMITS)
                        now=time.monotonic()
                        if now-last_gamepad_step<0.15:
                            return self.out(429,b'Gamepad rate limit','text/plain')
                        last_gamepad_step=now
                        apply_position_plan(planned,enforce_following=True,following_deg=3.0)
                    else:
                        planned = plan_steps(data.get('steps'), targets, LIMITS, mode)
                        now = time.monotonic()
                        if now - last_gamepad_step < 0.15:
                            return self.out(429,b'Gamepad rate limit','text/plain')
                        last_gamepad_step = now
                        apply_position_plan(planned,enforce_following=True,following_deg=1.0)
                return self.out(200,b'{}','application/json')
            except (ValueError, TypeError) as exc:
                return self.out(400,str(exc).encode(),'text/plain')
        if p.path=="/api/step":
            n=q.get("name",[""])[0]
            try:
                a=float(q.get("amount",[0])[0])
                if not math.isfinite(a): raise ValueError
                a=max(-1,min(1,a))
            except (TypeError,ValueError): return self.send_error(400)
            if n not in targets: return self.send_error(400)
            with lock:
                if estop["active"]: return self.out(409,estop["reason"].encode(),"text/plain")
                revoke_control_sessions()
                proposed = targets[n] + a
                if proposed < LIMITS[n][0] or proposed > LIMITS[n][1]:
                    stop_motion(f"Rejected unsafe target for {n}: {proposed:.1f}")
                    return self.out(409,estop["reason"].encode(),"text/plain")
                apply_position_plan({n:proposed},enforce_following=True)
            return self.out(200,b"{}","application/json")
        if p.path=="/api/base":
            cmd=q.get("cmd",[""])[0]; values={"forward":(-100,100),"back":(100,-100),"left":(100,100),"right":(-100,-100)}.get(cmd)
            if not values:return self.send_error(400)
            with lock:
                if estop["active"]: return self.out(409,estop["reason"].encode(),"text/plain")
                revoke_control_sessions()
                deadline=time.monotonic()+.25
                gamepad["wheel_deadline"]=deadline
                bus2.sync_write("Goal_Velocity",dict(zip(WHEELS,values)),normalize=False)
                threading.Thread(target=stop_wheels_at,args=(deadline,),daemon=True,name="manual-wheel-stop").start()
            return self.out(200,b"{}","application/json")
        if p.path=="/api/estop":
            with lock: stop_motion("Manual emergency stop")
            return self.out(200,b"{}","application/json")
        if p.path=="/api/reset":
            with lock:
                actual={**bus1.sync_read("Present_Position",LEFT),**bus2.sync_read("Present_Position",RIGHT)}
                bad=[n for n,v in actual.items() if not math.isfinite(v) or v<LIMITS[n][0] or v>LIMITS[n][1]]
                if bad:return self.out(409,("Cannot reset; out of range: "+", ".join(bad)).encode(),"text/plain")
                targets.update(actual);actual_positions.update(actual);bus1.sync_write("Goal_Position",{n:targets[n] for n in LEFT});bus2.sync_write("Goal_Position",{n:targets[n] for n in RIGHT});estop["active"],estop["reason"]=False,""
            return self.out(200,b"{}","application/json")
        if p.path=="/api/shutdown":
            with lock: stop_motion("Safe shutdown requested")
            self.out(200,b"{}","application/json")
            threading.Thread(target=server.shutdown, daemon=True).start()
            return
        self.send_error(404)

server=ThreadingHTTPServer(("127.0.0.1",8765),H);print("http://127.0.0.1:8765",flush=True)
try:server.serve_forever()
finally:
    if recorder.status()["active"]:
        try: recorder.finish(False)
        except Exception as exc: print(f"Warning: could not finalize active recording: {exc}",flush=True)
    bus2.sync_write("Goal_Velocity",dict.fromkeys(WHEELS,0),normalize=False)
    camera_stop.set()
    for c in cams.values():c.release()
    for thread in camera_threads:thread.join(timeout=1)
    bus1.disconnect(disable_torque=False);bus2.disconnect(disable_torque=False)
