'use strict';
(() => {
  const panel = document.createElement('div');
  panel.className = 'panel base';
  panel.innerHTML = `<h2>Dual-arm joint control (continuous keyboard)</h2>
    <label>Arm <select id="joint-arm"><option value="left">Left arm</option><option value="right">Right arm</option></select></label>
    <label><input id="joint-keyboard-enabled" type="checkbox">Enable keyboard joint control</label>
    <p id="joint-keyboard-status">Stopped</p>
    <table style="margin:auto;text-align:left;border-collapse:collapse"><tbody>
      <tr><td>Q / A</td><td>Shoulder pan: negative / positive</td><td>W / S</td><td>Shoulder lift: negative / positive</td></tr>
      <tr><td>E / D</td><td>Elbow: negative / positive</td><td>R / F</td><td>Wrist pitch: negative / positive</td></tr>
      <tr><td>T / G</td><td>Wrist roll: negative / positive</td><td>Y / H</td><td>Gripper: close / open</td></tr>
      <tr><td>Space</td><td colspan="3">Immediately disable keyboard control</td></tr>
    </tbody></table>
    <p>Select an arm, enable keyboard control, and hold an action key for continuous motion. Release it to stop adding targets. Joints move 2° per cycle and grippers 2% per cycle. Use short taps first to confirm physical direction.</p>`;
  document.querySelector('.cams').before(panel);

  const enabled = panel.querySelector('#joint-keyboard-enabled');
  const arm = panel.querySelector('#joint-arm');
  const status = panel.querySelector('#joint-keyboard-status');
  const held = new Set();
  let token = null, busy = false, revision = 0;
  const keyMap = {
    q:['shoulder_pan',-2], a:['shoulder_pan',2],
    w:['shoulder_lift',-2], s:['shoulder_lift',2],
    e:['elbow_flex',-2], d:['elbow_flex',2],
    r:['wrist_flex',-2], f:['wrist_flex',2],
    t:['wrist_roll',-2], g:['wrist_roll',2],
    y:['gripper',-2], h:['gripper',2]
  };
  const jointNames = {
    shoulder_pan:'Shoulder pan', shoulder_lift:'Shoulder lift', elbow_flex:'Elbow',
    wrist_flex:'Wrist pitch', wrist_roll:'Wrist roll', gripper:'Gripper'
  };
  const opposites = {q:'a',a:'q',w:'s',s:'w',e:'d',d:'e',r:'f',f:'r',t:'g',g:'t',y:'h',h:'y'};
  const readyText = () => `Enabled: ${arm.options[arm.selectedIndex].text}; waiting for input`;

  async function request(path, data) {
    const response = await fetch('/api/keyboard/' + path, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify(data), signal:AbortSignal.timeout(1000)
    });
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}: ${await response.text()}`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  function stop(message='Stopped') {
    const oldToken = token;
    token = null; held.clear(); enabled.checked = false; revision++;
    status.textContent = message;
    if (oldToken) request('stop',{token:oldToken}).catch(()=>{});
  }
  function pause(message) {
    held.clear();
    if (enabled.checked && token) status.textContent = message;
  }
  enabled.addEventListener('change', async () => {
    held.clear(); revision++;
    if (!enabled.checked) { stop(); return; }
    const rev = revision;
    try {
      const result = await request('session',{});
      if (rev === revision && enabled.checked) {
        token = result.token;
        status.textContent = readyText();
      }
    } catch (error) { stop('Enable failed: ' + error.message); }
  });
  arm.addEventListener('change', () => {
    held.clear();
    if (enabled.checked) status.textContent = readyText();
  });
  window.addEventListener('blur', () => pause('Window lost focus; paused. Press a key after returning to continue.'));
  window.addEventListener('focus', () => {
    if (enabled.checked && token) status.textContent = readyText();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) pause('Page hidden; paused. Press a key after returning to continue.');
  });
  document.addEventListener('keydown', event => {
    if (event.code === 'Space' && enabled.checked) { event.preventDefault(); stop(); return; }
    if (!enabled.checked || event.ctrlKey || event.altKey || event.metaKey) return;
    const key = event.key.toLowerCase();
    if (!keyMap[key]) return;
    event.preventDefault(); held.delete(opposites[key]); held.add(key);
  });
  document.addEventListener('keyup', event => {
    held.delete(event.key.toLowerCase());
    if (!held.size && enabled.checked && token) status.textContent = readyText();
  });

  async function tick() {
    if (!enabled.checked || !token || busy || !held.size || document.hidden || !document.hasFocus()) return;
    const steps = {};
    for (const key of held) {
      const [joint, amount] = keyMap[key];
      steps[`${arm.value}_arm_${joint}`] = amount;
    }
    busy = true; const rev = revision;
    try {
      await request('move',{token,steps});
      if (rev === revision) {
        const actions=[...held].map(key=>{
          const [joint,amount]=keyMap[key];
          return `${key.toUpperCase()} ${jointNames[joint]} ${amount>0?'+':'−'}2${joint==='gripper'?'%':'°'}`;
        });
        status.textContent = `Moving: ${arm.options[arm.selectedIndex].text}; ${actions.join(', ')}; release to stop`;
      }
    } catch (error) {
      if (rev === revision && (error.status === 400 || error.status === 429)) {
        status.textContent = error.status === 400
          ? 'Arm is following the target; waiting automatically'
          : 'Continuous control: waiting for the next cycle';
      } else if (rev === revision) {
        stop('Stopped: ' + error.message);
      }
    } finally { busy = false; }
  }
  setInterval(tick,200);
})();
