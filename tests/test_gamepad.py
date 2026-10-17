"""Hardware-free tests for the web gamepad routes and wheel timeout."""
import ast
import io
import json
import math
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from arm_gamepad import ARM_JOINTS, plan_steps, wheel_speeds
from cartesian_control import arm_pose, plan_cartesian


class GamepadTests(unittest.TestCase):
    def setUp(self):
        self.clock = Mock()
        self.clock.monotonic.return_value = 10.0
        self.bus = Mock()
        names = ARM_JOINTS | {'head_motor_1', 'head_motor_2'}
        self.bus.sync_read.return_value = dict.fromkeys(names, 5.0)
        self.env = dict(lock=threading.Lock(), gamepad={'mode':'arms', 'token':None, 'wheel_deadline':0},
                        keyboard_session={'token':None, 'last_step':0},
                        cartesian_session={'token':None, 'last_step':0},
                        estop={'active':False, 'reason':''}, bus2=self.bus, bus1=self.bus,
                        WHEELS=['left', 'right'], LEFT=list(names), RIGHT=[],
                        targets=dict.fromkeys(names, 5.0), LIMITS=dict.fromkeys(names, (0,10)),
                        actual_positions=dict.fromkeys(names, 5.0),
                        buses=dict.fromkeys(names, self.bus), last_gamepad_step=0.0,
                        time=self.clock, math=math, uuid=types.SimpleNamespace(uuid4=lambda:types.SimpleNamespace(hex='new-token')),
                        json=json, plan_steps=plan_steps, wheel_speeds=wheel_speeds,
                        arm_pose=arm_pose, plan_cartesian=plan_cartesian,
                        BaseHTTPRequestHandler=object)
        from urllib.parse import parse_qs, urlparse
        self.env.update(parse_qs=parse_qs, urlparse=urlparse)
        tree = ast.parse((ROOT/'xlerobot_web.py').read_text())
        nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in ('H','watchdog','apply_position_plan','revoke_control_sessions','stop_wheels_at')]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT/'xlerobot_web.py'), 'exec'), self.env)

    def post(self, path, data):
        return self.post_path('/api/gamepad/' + path, data)

    def post_keyboard(self, path, data):
        return self.post_path('/api/keyboard/' + path, data)

    def post_path(self, path, data):
        handler = self.env['H']()
        body = json.dumps(data).encode()
        handler.path = path
        handler.headers = {'Content-Length':str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.out = Mock()
        handler.do_POST()
        return handler.out.call_args.args

    def test_modes_and_stale_commands(self):
        self.env['targets']['left_arm_elbow_flex'] = 8.0
        self.env['actual_positions']['left_arm_elbow_flex'] = 5.0
        self.assertEqual(self.post('mode', {'mode':'head'})[0], 200)
        self.assertEqual(self.env['targets']['left_arm_elbow_flex'], 5.0)
        self.assertEqual(self.post('move', {'token':'new-token','steps':{'head_motor_1':.4}})[0], 200)
        self.assertEqual(self.post('move', {'token':'new-token','steps':{'left_arm_elbow_flex':.4}})[0], 400)
        self.post('stop', {'token':'new-token'})
        self.assertEqual(self.post('move', {'token':'new-token','steps':{'head_motor_1':.4}})[0], 409)
        self.env['estop']['active'] = True
        self.assertEqual(self.post('mode', {'mode':'arms'})[0], 409)
        self.assertEqual(self.post('stop', {})[0], 200)

    def test_stale_or_unowned_stop_cannot_revoke_active_session(self):
        self.assertEqual(self.post('mode', {'mode':'arms'})[0], 200)
        self.assertEqual(self.env['gamepad']['token'], 'new-token')
        self.assertEqual(self.post('stop', {})[0], 200)
        self.assertEqual(self.env['gamepad']['token'], 'new-token')
        self.assertEqual(self.post('stop', {'token':'older-token'})[0], 200)
        self.assertEqual(self.env['gamepad']['token'], 'new-token')
        self.assertEqual(self.post('stop', {'token':'new-token'})[0], 200)
        self.assertIsNone(self.env['gamepad']['token'])

    def test_keyboard_has_independent_owned_session(self):
        self.env['targets']['right_arm_shoulder_lift']=8.0
        self.env['actual_positions']['right_arm_shoulder_lift']=5.0
        self.assertEqual(self.post_keyboard('session',{})[0],200)
        self.assertEqual(self.env['targets']['right_arm_shoulder_lift'],5.0)
        self.assertEqual(self.env['keyboard_session']['token'],'new-token')
        self.assertEqual(self.post('stop',{})[0],200)
        self.assertEqual(self.env['keyboard_session']['token'],'new-token')
        self.assertEqual(self.post_keyboard('stop',{'token':'stale'})[0],200)
        self.assertEqual(self.env['keyboard_session']['token'],'new-token')
        self.assertEqual(self.post_keyboard('move',{'token':'new-token','steps':{'right_arm_shoulder_lift':2}})[0],200)
        self.clock.monotonic.return_value=10.2
        self.assertEqual(self.post_keyboard('move',{'token':'new-token','steps':{'right_arm_shoulder_lift':2}})[0],200)
        self.assertEqual(self.env['keyboard_session']['token'],'new-token')
        self.env['actual_positions']['right_arm_shoulder_lift']=7.0
        self.clock.monotonic.return_value=10.4
        self.assertEqual(self.post_keyboard('move',{'token':'new-token','steps':{'right_arm_shoulder_lift':2}})[0],200)
        self.assertEqual(self.post_keyboard('stop',{'token':'new-token'})[0],200)
        self.assertIsNone(self.env['keyboard_session']['token'])

    def test_keyboard_following_wait_is_not_reported_as_an_error(self):
        name='right_arm_shoulder_lift'
        self.env['actual_positions'][name]=0.0
        self.assertEqual(self.post_keyboard('session',{})[0],200)
        # Recreate a full bounded lead after session synchronization.
        self.env['targets'][name]=6.0
        response=self.post_keyboard('move',{'token':'new-token','steps':{name:2}})
        self.assertEqual(response[0],200)
        self.assertIn(b'"waiting":true',response[1])

    def test_starting_gamepad_revokes_keyboard_session(self):
        self.assertEqual(self.post_keyboard('session',{})[0],200)
        self.assertEqual(self.post('mode',{'mode':'arms'})[0],200)
        self.assertIsNone(self.env['keyboard_session']['token'])
        self.assertEqual(self.post_keyboard('move',{'token':'new-token','steps':{'right_arm_shoulder_lift':2}})[0],409)

    def test_wheels_and_timeout(self):
        self.post('mode', {'mode':'wheels'})
        data = {'token':'new-token', 'forward':1, 'turn':0, 'raised':False}
        self.assertEqual(self.post('move', data)[0], 400)
        data['raised'] = True
        self.assertEqual(self.post('move', data)[0], 200)
        self.bus.sync_write.assert_called_with('Goal_Velocity', {'left':-100, 'right':100}, normalize=False)
        self.clock.monotonic.return_value = 10.5
        self.clock.sleep.side_effect = [None, KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt): self.env['watchdog']()
        self.bus.sync_write.assert_called_with('Goal_Velocity', {'left':0, 'right':0}, normalize=False)
        self.assertIsNone(self.env['gamepad']['token'])
        self.assertEqual(self.post('move', data)[0], 409)

    def test_manual_wheel_pulse_stops_without_holding_http_lock(self):
        self.env['gamepad']['wheel_deadline']=10.25
        self.env['stop_wheels_at'](10.25)
        self.clock.sleep.assert_called_with(.25)
        self.bus.sync_write.assert_called_with('Goal_Velocity',{'left':0,'right':0},normalize=False)
        self.assertEqual(self.env['gamepad']['wheel_deadline'],0)

    def test_cartesian_gamepad_and_keyboard_routes(self):
        self.assertEqual(self.post('mode', {'mode':'cartesian'})[0], 200)
        move={'token':'new-token','cartesian':{'left':{'pan':.5}}}
        self.assertEqual(self.post('move',move)[0],200)
        self.assertTrue(any(call.args[0]=='Goal_Position' for call in self.bus.sync_write.call_args_list))

        self.assertEqual(self.post_path('/api/cartesian/session',{'action':'start'})[0],200)
        self.assertIsNone(self.env['gamepad']['token'])
        keyboard={'token':'new-token','commands':{'right':{'roll':.5}}}
        self.assertEqual(self.post_path('/api/cartesian/move',keyboard)[0],200)
        self.post_path('/api/cartesian/session',{'action':'stop'})
        self.assertEqual(self.post_path('/api/cartesian/move',keyboard)[0],409)

    def test_control_sources_are_exclusive(self):
        self.assertEqual(self.post_path('/api/cartesian/session',{'action':'start'})[0],200)
        keyboard_token=self.env['cartesian_session']['token']
        self.assertEqual(self.post('mode',{'mode':'arms'})[0],200)
        self.assertIsNone(self.env['cartesian_session']['token'])
        stale={'token':keyboard_token,'commands':{'left':{'height':.001}}}
        self.assertEqual(self.post_path('/api/cartesian/move',stale)[0],409)

    def test_cartesian_following_error_rejects_a_runaway_goal(self):
        name='left_arm_shoulder_pan'
        self.env['actual_positions'][name]=0
        with self.assertRaisesRegex(ValueError,'has not caught up'):
            self.env['apply_position_plan']({name:6.1},enforce_following=True)
        self.bus.sync_write.assert_not_called()

    def test_gripper_following_error_is_limited(self):
        name='left_arm_gripper'
        self.env['actual_positions'][name]=0
        with self.assertRaisesRegex(ValueError,'has not caught up'):
            self.env['apply_position_plan']({name:10.1},enforce_following=True)

    def test_cartesian_can_use_tighter_coordinated_following_limit(self):
        name='right_arm_shoulder_lift'
        self.env['actual_positions'][name]=5
        with self.assertRaisesRegex(ValueError,'has not caught up'):
            self.env['apply_position_plan']({name:6.01},enforce_following=True,following_deg=1.0)

    def test_watchdog_communication_error_revokes_control_and_stops_wheels(self):
        self.env['gamepad'].update(token='live',wheel_deadline=20)
        self.env['cartesian_session']['token']='keyboard'
        self.bus.sync_read.side_effect=RuntimeError('serial lost')
        self.clock.sleep.side_effect=[None,KeyboardInterrupt]
        with self.assertRaises(KeyboardInterrupt): self.env['watchdog']()
        self.assertTrue(self.env['estop']['active'])
        self.assertIsNone(self.env['gamepad']['token'])
        self.assertIsNone(self.env['cartesian_session']['token'])
        self.bus.sync_write.assert_called_with('Goal_Velocity',{'left':0,'right':0},normalize=False)

    def test_limits_and_invalid_input(self):
        n = 'left_arm_elbow_flex'
        targets = {n:9.9}
        self.assertEqual(plan_steps({n:.4}, targets, {n:(0,10)})[n],10)
        self.assertEqual(plan_steps({n:2}, targets, {n:(0,20)})[n],11.9)
        for amount in (float('nan'), float('inf'), True, 2.1, '1'):
            with self.assertRaises(ValueError): plan_steps({n:amount}, targets, {n:(0,10)})
        for value in (float('nan'), True, 2, None):
            with self.assertRaises(ValueError): wheel_speeds(value,0,True)
        self.assertEqual(wheel_speeds(1,1,True), (0,100))


if __name__ == '__main__': unittest.main()
