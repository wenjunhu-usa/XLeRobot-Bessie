'use strict';
(() => {
  const panel = document.createElement('div');
  panel.className = 'panel base';
  panel.innerHTML = `<h2>Gamepad Control</h2><label>Mode <select id="pad-mode"><option value="arms">Joint</option><option value="cartesian">Cartesian grasp (kinematics)</option><option value="head">Head</option><option value="wheels">Wheels</option></select></label> <label><input id="arm-pad-enabled" type="checkbox">Enable gamepad</label><p id="arm-pad-status">Press a gamepad button to detect it</p><p>D-pad ← / → changes modes; re-enable after switching. Cartesian mode controls reach, height, and grippers for manual pickup and placement. − / + triggers emergency stop.</p><p id="pad-error" role="alert" style="color:#fbbf24"></p><details><summary>Gamepad diagnostics (no motion)</summary><pre id="pad-diagnostics" style="white-space:pre-wrap;text-align:left"></pre></details><div id="pad-guide"></div>`;
  document.querySelector('.cams').before(panel);
  const enabled = document.getElementById('arm-pad-enabled');
  const status = document.getElementById('arm-pad-status');
  const mode = document.getElementById('pad-mode');
  const raised = document.getElementById('raised');
  const guide = document.getElementById('pad-guide');
  const errorDisplay = document.getElementById('pad-error');
  const diagnostics = document.getElementById('pad-diagnostics');
  const modes = ['arms', 'cartesian', 'head', 'wheels'];
  const joints = ['shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper'];
  const names = ['Shoulder lift', 'Elbow', 'Wrist pitch', 'Wrist roll', 'Gripper'];
  let selected = 0, previous = [], ready = false, busy = false, token = null, revision = 0, activeIndex = null;
  function renderGuide() {
    const armJoint = names[selected];
    let rows;
    if (mode.value === 'arms') {
      rows = [
        ['Hold L + left stick ← / →', 'Left arm shoulder pan'],
        ['Hold L + left stick ↑ / ↓', `Left arm ${armJoint} (${joints[selected]})`],
        ['Hold R + right stick ← / →', 'Right arm shoulder pan'],
        ['Hold R + right stick ↑ / ↓', `Right arm ${armJoint} (${joints[selected]})`],
        ['D-pad ↑ / ↓', 'Change vertical-stick joint: shoulder lift → elbow → wrist pitch → wrist roll → gripper'],
        ['Hold L + R together', 'Both sticks can control both arms simultaneously'],
        ['Release the corresponding shoulder button', 'Stop adding motion; hold the last joint target']
      ];
    } else if (mode.value === 'cartesian') {
      rows = [
        ['Hold L + left stick ← / →', 'Left tool retract / extend'],
        ['Hold L + left stick ↑ / ↓', 'Left tool raise / lower'],
        ['Hold R + right stick ← / →', 'Right tool retract / extend'],
        ['Hold R + right stick ↑ / ↓', 'Right tool raise / lower'],
        ['Hold L or R + A / B', 'Close / open the corresponding gripper'],
        ['Hold L or R + X / Y', 'Pitch the corresponding gripper down / up'],
        ['Hold L + R together', 'Control both arms simultaneously']
      ];
    } else if (mode.value === 'head') {
      rows = [
        ['Hold L + left stick ← / →', 'Head pan (head_motor_1)'],
        ['Hold L + left stick ↑ / ↓', 'Head tilt (head_motor_2)'],
        ['Release L', 'Stop adding motion; head holds the last target'],
        ['Right stick / R', 'No action is mapped in this mode']
      ];
    } else {
      rows = [
        ['Check “Wheels are raised”', 'Allow wheel mode; keep wheels raised during initial testing'],
        ['Hold L + left stick ↑ / ↓', 'Forward / reverse (coordinated wheels)'],
        ['Hold L + left stick ← / →', 'Turn left / right (can combine with forward/reverse)'],
        ['Release L / center left stick', 'Stop wheels'],
        ['Right stick / R', 'No action is mapped in this mode']
      ];
    }
    rows.push(['D-pad ← / → or page mode selector', 'Switch joint / Cartesian / head / wheel modes; release sticks and shoulder buttons, then re-enable'],
      ['− / + (Back / Start)', 'Emergency stop; reset it on the page before re-enabling'],
      ['Window switch / gamepad disconnect', 'Disable and request a stop; wheels also have a server communication timeout']);
    guide.innerHTML = `<h3>${mode.options[mode.selectedIndex].text}: controls</h3>${mode.value === 'arms' ? `<p style="color:#fbbf24">Current vertical-stick joint: <strong>${armJoint}</strong> (shared by both arms)</p>` : ''}<table style="width:100%;text-align:left;border-collapse:collapse"><thead><tr><th scope="col">Gamepad input</th><th scope="col">Joint / action</th></tr></thead><tbody>${rows.map(([key, action]) => `<tr><td style="padding:8px;border-top:1px solid #475569">${key}</td><td style="padding:8px;border-top:1px solid #475569">${action}</td></tr>`).join('')}</tbody></table><p>L / R are shoulder buttons (LB / RB), not ZL / ZR triggers. Right or up increases joint values and the opposite direction decreases them. Confirm physical direction with small motions first. Gripper up increases opening percentage and down decreases it.</p>`;
  }
  renderGuide();
  let queue = Promise.resolve();
  const pressed = (pad, i) => !!pad.buttons[i]?.pressed;
  const axis = v => Number.isFinite(v) && Math.abs(v) > 0.2 ? Math.max(-1, Math.min(1, v)) : 0;
  async function request(path, data) {
    const response = await fetch('/api/gamepad/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data), signal:AbortSignal.timeout(1000)});
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(response.status === 404 || response.status === 501 ? 'The server has not loaded the gamepad API. Stop it with Ctrl+C, run ./start_web_controller.sh, and refresh the page.' : `HTTP ${response.status}: ${detail}`);
    }
    return response.json();
  }
  function enqueue(task) { queue = queue.catch(() => {}).then(task); return queue; }
  function disable() {
    const oldToken = token;
    enabled.checked = false; ready = false; token = null; activeIndex = null; revision++;
    if (oldToken) enqueue(() => request('stop', {token:oldToken})).catch(() => {});
  }
  const mapping = window.createPadMapping(panel, disable);
  const jointSelect = document.getElementById('pad-joint-select');
  jointSelect.addEventListener('change', () => { selected = Number(jointSelect.value); renderGuide(); });
  enabled.addEventListener('change', () => {
    if (!enabled.checked) disable();
    else { errorDisplay.textContent = ''; ready = false; token = null; revision++; }
  });
  mode.addEventListener('change', () => { disable(); renderGuide(); });
  raised.addEventListener('change', () => { if (!raised.checked && mode.value === 'wheels') disable(); });
  window.addEventListener('blur', disable);
  document.addEventListener('visibilitychange', () => { if (document.hidden) disable(); });
  window.addEventListener('gamepaddisconnected', disable);
  async function tick() {
    if (busy) return;
    const pads = [...(navigator.getGamepads?.() || [])].filter(Boolean);
    const rawPad = activeIndex === null ? pads[0] : pads.find(p => p.index === activeIndex);
    mapping.sample(rawPad);
    const pad = mapping.normalize(rawPad);
    if (mapping.calibrating) { if (enabled.checked) disable(); status.textContent = 'Gamepad calibration in progress; robot motion is disabled'; return; }
    diagnostics.textContent = rawPad ? `${rawPad.id}\nMapping: ${rawPad.mapping || 'non-standard'}; axes: ${rawPad.axes.length}; buttons: ${rawPad.buttons.length}\nAxis values: ${rawPad.axes.map((v,i) => `${i}: ${v.toFixed(3)}`).join(' | ')}\nPressed buttons: ${rawPad.buttons.map((b,i) => b.pressed ? i : null).filter(i => i !== null).join(', ') || 'none'}\nPage focus: ${document.hasFocus() ? 'yes' : 'no'}` : 'Browser did not detect a gamepad';
    if (!pad || pad.mapping !== 'standard' || pad.axes.length < 4 || pad.buttons.length < 16) {
      if (enabled.checked || token) {
        errorDisplay.textContent = rawPad ? 'Enable failed: this gamepad lacks a complete standard mapping. Calibrate its buttons and sticks first.' : 'Enable failed: the browser did not detect a gamepad. Press a regular gamepad button on this page.';
        disable();
      }
      status.textContent = rawPad ? `${rawPad.id}: complete non-standard gamepad calibration first` : 'No gamepad detected; press a button'; return;
    }
    const buttons = pad.buttons.map(b => b.pressed);
    const edge = i => buttons[i] && !previous[i];
    if (edge(14) || edge(15)) {
      mode.value = modes[(modes.indexOf(mode.value) + (edge(15) ? 1 : 2)) % 3]; disable();
    }
    if (mode.value === 'arms') {
      if (edge(12)) selected = (selected + joints.length - 1) % joints.length;
      if (edge(13)) selected = (selected + 1) % joints.length;
    }
    jointSelect.value = String(selected);
    if ([12, 13, 14, 15].some(edge)) renderGuide();
    const emergencyPressed = edge(8) || edge(9);
    previous = buttons;
    status.textContent = `${pad.id} | ${mode.options[mode.selectedIndex].text} ${mode.value === 'arms' ? ' / ' + names[selected] : ''} | ${ready ? 'enabled' : 'stopped; release sticks and shoulder buttons after enabling'}`;
    if (emergencyPressed) { disable(); busy = true; try { await emergency(); } catch (e) { status.textContent = e.message; } finally { busy = false; } return; }
    if (!enabled.checked) return;
    if (document.hidden || !document.hasFocus()) { disable(); return; }
    if (mode.value === 'wheels' && !raised.checked) { disable(); errorDisplay.textContent = 'Wheel mode: check “Wheels are raised” first'; return; }
    const rev = revision;
    busy = true;
    try {
      if (!ready) {
        if (pad.axes.slice(0, 4).every(v => Number.isFinite(v) && Math.abs(v) <= 0.2) && !pressed(pad, 4) && !pressed(pad, 5)) {
          const result = await enqueue(() => request('mode', {mode:mode.value}));
          if (revision === rev) { token = result.token; ready = true; activeIndex = pad.index; errorDisplay.textContent = ''; }
        } else {
          errorDisplay.textContent = 'Waiting to enable: release both shoulder buttons and center both sticks. See diagnostics for actual input.';
        }
        return;
      }
      const data = {token};
      if (mode.value === 'wheels') {
        data.forward = pressed(pad, 4) ? -axis(pad.axes[1]) : 0;
        data.turn = pressed(pad, 4) ? axis(pad.axes[0]) : 0;
        data.raised = raised.checked;
      } else if (mode.value === 'cartesian') {
        data.cartesian = {};
        for (const [side, button, offset] of [['left',4,0],['right',5,2]]) {
          if (!pressed(pad,button)) continue;
          const command={reach:axis(pad.axes[offset])*.003,height:-axis(pad.axes[offset+1])*.003,pitch:0,pan:0,roll:0,gripper:0};
          if (pressed(pad,0)) command.gripper=-2;
          if (pressed(pad,1)) command.gripper=2;
          if (pressed(pad,2)) command.pitch=-1;
          if (pressed(pad,3)) command.pitch=1;
          if (Object.values(command).some(Boolean)) data.cartesian[side]=command;
        }
        if (!Object.keys(data.cartesian).length) return;
      } else {
        data.steps = {};
        if (mode.value === 'head' && pressed(pad, 4)) {
          const x = axis(pad.axes[0]) * 0.4, y = -axis(pad.axes[1]) * 0.4;
          if (x) data.steps.head_motor_1 = x;
          if (y) data.steps.head_motor_2 = y;
        } else if (mode.value === 'arms') {
          for (const [side, button, offset] of [['left',4,0],['right',5,2]]) {
            if (!pressed(pad, button)) continue;
            const x = axis(pad.axes[offset]) * 0.4, y = -axis(pad.axes[offset+1]) * 0.4;
            if (x) data.steps[`${side}_arm_shoulder_pan`] = x;
            if (y) data.steps[`${side}_arm_${joints[selected]}`] = y;
          }
        }
        if (!Object.keys(data.steps).length) return;
      }
      await enqueue(() => revision === rev ? request('move', data) : undefined);
    } catch (error) {
      if (revision === rev) { disable(); errorDisplay.textContent = `Gamepad stopped: ${error.message}`; }
    } finally { busy = false; }
  }
  setInterval(tick, 200);
})();
