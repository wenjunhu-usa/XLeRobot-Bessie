'use strict';
// Non-standard pads must be calibrated with actual inputs before motion is allowed.
window.createPadMapping = function(panel, stop) {
  const box = document.createElement('div');
  box.innerHTML = '<button type="button" id="pad-calibrate">Calibrate non-standard gamepad</button><button type="button" id="pad-calibrate-directions">Calibrate D-pad</button><p id="pad-calibration-status"></p><label>Arm vertical joint <select id="pad-joint-select"><option value="0">Shoulder lift</option><option value="1">Elbow</option><option value="2">Wrist pitch</option><option value="3">Wrist roll</option><option value="4">Gripper</option></select></label><p>V2 calibration records A/B/X/Y, L/R, −/+, and both sticks. Run calibration again for old profiles. Robot motion is disabled during calibration.</p>';
  panel.append(box);
  const button = box.querySelector('button'), message = box.querySelector('p');
  const directionButton = box.querySelector('#pad-calibrate-directions');
  const directionStages = [['Press D-pad ↑', 'direction', 12], ['Press D-pad ↓', 'direction', 13], ['Press D-pad ←', 'direction', 14], ['Press D-pad →', 'direction', 15]];
  const stages = [
    ['Hold A', 'button', 0],
    ['Hold B', 'button', 1],
    ['Hold X', 'button', 2],
    ['Hold Y', 'button', 3],
    ['Hold left shoulder button L (not trigger ZL)', 'button', 4],
    ['Hold right shoulder button R (not trigger ZR)', 'button', 5],
    ['Hold − / Back', 'button', 8],
    ['Hold + / Start', 'button', 9],
    ['Move only the left stick right', 'axis', 0, 1],
    ['Move only the left stick up', 'axis', 1, -1],
    ['Move only the right stick right', 'axis', 2, 1],
    ['Move only the right stick up', 'axis', 3, -1]
  ];
  let calibration = null, saved = {}, current = null, releaseCenters = null;
  try { saved = JSON.parse(localStorage.getItem('xlerobot-pad-mappings') || '{}'); } catch (_) {}
  function valid(map, pad) {
    return map && map.axisCount === pad.axes.length && map.buttonCount === pad.buttons.length &&
      [0,1,2,3,4,5,8,9].every(i => Number.isInteger(map.buttons[i]) && map.buttons[i] >= 0 && map.buttons[i] < pad.buttons.length) &&
      [0,1,2,3].every(i => map.axes[i] && Number.isInteger(map.axes[i].index) && map.axes[i].index >= 0 && map.axes[i].index < pad.axes.length && Number.isFinite(map.axes[i].center) && [1,-1].includes(map.axes[i].sign));
  }
  button.onclick = () => {
    stop();
    if (calibration) { calibration = null; message.textContent = 'Calibration cancelled'; button.textContent = 'Calibrate non-standard gamepad'; return; }
    if (!current) { message.textContent = 'Press a regular gamepad button so the browser detects it'; return; }
    calibration = {id:current.id, stage:0, released:false, centers:current.axes.slice(), buttons:{}, axes:{}, axisCount:current.axes.length, buttonCount:current.buttons.length, directions:{}, stages};
    button.textContent = 'Cancel calibration';
    message.textContent = 'Release all buttons, center both sticks, then follow the prompts';
  };
  directionButton.onclick = () => {
    stop();
    if (!current || !valid(saved[current.id], current)) { message.textContent = 'Complete non-standard button and stick calibration before calibrating the D-pad'; return; }
    const map = saved[current.id];
    calibration = {...map, id:current.id, stage:0, released:false, centers:current.axes.slice(), directions:{}, stages:directionStages};
    button.textContent = 'Cancel calibration';
    message.textContent = 'Release the D-pad, then press up, down, left, and right as prompted';
  };
  function sample(pad) {
    current = pad;
    if (!calibration) {
      if (releaseCenters && pad && !pad.buttons.some(b=>b.pressed) && pad.axes.every((v,i)=>Math.abs(v-releaseCenters[i])<.35)) releaseCenters = null;
      return;
    }
    if (!pad || pad.id !== calibration.id) { calibration = null; button.textContent = 'Calibrate non-standard gamepad'; message.textContent = 'Gamepad disconnected; calibration cancelled'; return; }
    const c = calibration;
    const stages = c.stages;
    const held = pad.buttons.map((b,i)=>b.pressed ? i : -1).filter(i=>i>=0);
    const deviations = pad.axes.map((v,i)=>({index:i,delta:v-c.centers[i]}));
    const offCenter = deviations.filter(a=>Math.abs(a.delta)>=.35);
    const neutral = !held.length && !offCenter.length;
    if (!c.released) {
      if (neutral) { c.released = true; message.textContent = `Step ${c.stage+1}/${stages.length}: ${stages[c.stage][0]}`; }
      else message.textContent = `Step ${c.stage+1}/${stages.length}—release buttons and center sticks first. ${held.length ? 'Buttons still held: '+held.join(', ') : ''} ${offCenter.length ? 'Off-center axes: '+offCenter.map(a=>`${a.index} (${a.delta.toFixed(2)})`).join(', ') : ''}`;
      return;
    }
    const [label, kind, output, sign] = stages[c.stage];
    if (kind === 'direction') {
      const inputs = held;
      const changes = deviations.filter(a=>Math.abs(a.delta)>.45 && !Object.values(c.axes).some(stick=>stick.index===a.index));
      if (inputs.length === 1 && !Object.values(c.buttons).includes(inputs[0])) {
        c.directions[output] = {button:inputs[0]};
      } else if (!inputs.length && changes.length === 1) {
        c.directions[output] = {axis:changes[0].index, center:c.centers[changes[0].index], sign:Math.sign(changes[0].delta)};
      } else { message.textContent = `Step ${c.stage+1}/${stages.length}: ${label}—hold only one direction for about half a second`; return; }
    } else if (kind === 'button') {
      const inputs = pad.buttons.map((b,i)=>b.pressed?i:-1).filter(i=>i>=0);
      if (inputs.length !== 1) { message.textContent = `Step ${c.stage+1}/${stages.length}: ${label}; ${inputs.length ? 'multiple buttons detected: '+inputs.join(', ')+'. Press only one' : 'no button detected; hold it for about half a second'}; raw axes: ${pad.axes.map(v=>v.toFixed(2)).join(', ')}`; return; }
      if (Object.values(c.buttons).includes(inputs[0])) { message.textContent = 'This button is already assigned. Release it and press the requested button: '+label; return; }
      c.buttons[output] = inputs[0];
    } else {
      const inputs = deviations.filter(a=>Math.abs(a.delta)>.45).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
      if (!inputs.length || (inputs[1] && Math.abs(inputs[0].delta)-Math.abs(inputs[1].delta)<.25)) {
        message.textContent = `Step ${c.stage+1}/${stages.length}: ${label}—move beyond halfway and hold for about half a second; ${inputs.length ? 'two axes changed similarly; move straight in the requested direction' : 'stick movement is too small'}. Actual axis changes: ${deviations.map(a=>`${a.index}: ${a.delta.toFixed(2)}`).join(' | ')}`; return;
      }
      if (Object.values(c.axes).some(a=>a.index===inputs[0].index)) { message.textContent = 'This axis is already assigned. Release it and move the requested stick: '+label; return; }
      c.axes[output] = {index:inputs[0].index, center:c.centers[inputs[0].index], sign:Math.sign(inputs[0].delta)*sign};
    }
    c.stage++; c.released = false;
    if (c.stage === stages.length) {
      saved[pad.id] = {buttons:c.buttons,axes:c.axes,directions:c.directions,axisCount:c.axisCount,buttonCount:c.buttonCount};
      try { localStorage.setItem('xlerobot-pad-mappings',JSON.stringify(saved)); } catch (_) {}
      releaseCenters = c.centers;
      calibration = null; button.textContent = 'Recalibrate gamepad';
      message.textContent = stages === directionStages ? 'D-pad calibration complete: ↑↓ changes joints and ←→ changes modes.' : 'Calibration complete. You can calibrate the D-pad or select modes and joints on the page.';
    } else message.textContent = `Recorded step ${c.stage}/${stages.length}. Next: ${stages[c.stage][0]}; release buttons and center the sticks first`;
  }
  return {
    sample,
    get calibrating() { return !!calibration; },
    normalize(pad) {
      if (!pad || calibration || releaseCenters) return null;
      if (pad.mapping === 'standard' && pad.axes.length >= 4 && pad.buttons.length >= 16) return pad;
      const map = saved[pad.id];
      if (!valid(map,pad)) return null;
      return {id:pad.id,index:pad.index,mapping:'standard',
        axes:[0,1,2,3].map(i=>(pad.axes[map.axes[i].index]-map.axes[i].center)*map.axes[i].sign),
        buttons:Array.from({length:16},(_,i)=>{
          const direction = map.directions?.[i];
          if (direction) {
            if (Number.isInteger(direction.button)) return pad.buttons[direction.button] || {pressed:false};
            const delta = (pad.axes[direction.axis]-direction.center)*direction.sign;
            return {pressed:Number.isFinite(delta) && delta>.45};
          }
          return map.buttons[i] === undefined ? {pressed:false} : pad.buttons[map.buttons[i]];
        })};
    }
  };
};
