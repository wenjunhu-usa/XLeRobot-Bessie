'use strict';
// Non-standard pads must be calibrated with actual inputs before motion is allowed.
window.createPadMapping = function(panel, stop) {
  const box = document.createElement('div');
  box.innerHTML = '<button type="button" id="pad-calibrate">校准非标准手柄</button><button type="button" id="pad-calibrate-directions">校准方向键</button><p id="pad-calibration-status"></p><label>手臂纵向关节 <select id="pad-joint-select"><option value="0">肩部抬升</option><option value="1">肘部</option><option value="2">手腕俯仰</option><option value="3">手腕旋转</option><option value="4">夹爪</option></select></label><p>V2 校准会记录 A/B/X/Y、L/R、−/+ 和双摇杆。旧校准需重新执行一次。校准过程中不允许机器人动作。</p>';
  panel.append(box);
  const button = box.querySelector('button'), message = box.querySelector('p');
  const directionButton = box.querySelector('#pad-calibrate-directions');
  const directionStages = [['按十字方向键 ↑', 'direction', 12], ['按十字方向键 ↓', 'direction', 13], ['按十字方向键 ←', 'direction', 14], ['按十字方向键 →', 'direction', 15]];
  const stages = [
    ['按住 A', 'button', 0],
    ['按住 B', 'button', 1],
    ['按住 X', 'button', 2],
    ['按住 Y', 'button', 3],
    ['按住左肩键 L（不是 ZL 扳机）', 'button', 4],
    ['按住右肩键 R（不是 ZR 扳机）', 'button', 5],
    ['按住 − / Back', 'button', 8],
    ['按住 + / Start', 'button', 9],
    ['只把左摇杆推向右', 'axis', 0, 1],
    ['只把左摇杆推向上', 'axis', 1, -1],
    ['只把右摇杆推向右', 'axis', 2, 1],
    ['只把右摇杆推向上', 'axis', 3, -1]
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
    if (calibration) { calibration = null; message.textContent = '校准已取消'; button.textContent = '校准非标准手柄'; return; }
    if (!current) { message.textContent = '先按手柄普通按钮，让浏览器识别设备'; return; }
    calibration = {id:current.id, stage:0, released:false, centers:current.axes.slice(), buttons:{}, axes:{}, axisCount:current.axes.length, buttonCount:current.buttons.length, directions:{}, stages};
    button.textContent = '取消校准';
    message.textContent = '松开所有按钮，让两个摇杆回中，然后按提示操作';
  };
  directionButton.onclick = () => {
    stop();
    if (!current || !valid(saved[current.id], current)) { message.textContent = '请先完成非标准手柄的按键和摇杆校准，再校准方向键'; return; }
    const map = saved[current.id];
    calibration = {...map, id:current.id, stage:0, released:false, centers:current.axes.slice(), directions:{}, stages:directionStages};
    button.textContent = '取消校准';
    message.textContent = '先松开十字方向键，再按提示分别按上、下、左、右';
  };
  function sample(pad) {
    current = pad;
    if (!calibration) {
      if (releaseCenters && pad && !pad.buttons.some(b=>b.pressed) && pad.axes.every((v,i)=>Math.abs(v-releaseCenters[i])<.35)) releaseCenters = null;
      return;
    }
    if (!pad || pad.id !== calibration.id) { calibration = null; button.textContent = '校准非标准手柄'; message.textContent = '手柄断连，校准已取消'; return; }
    const c = calibration;
    const stages = c.stages;
    const held = pad.buttons.map((b,i)=>b.pressed ? i : -1).filter(i=>i>=0);
    const deviations = pad.axes.map((v,i)=>({index:i,delta:v-c.centers[i]}));
    const offCenter = deviations.filter(a=>Math.abs(a.delta)>=.35);
    const neutral = !held.length && !offCenter.length;
    if (!c.released) {
      if (neutral) { c.released = true; message.textContent = `步骤 ${c.stage+1}/${stages.length}：${stages[c.stage][0]}`; }
      else message.textContent = `步骤 ${c.stage+1}/${stages.length}：先松开按钮并回中。${held.length ? '仍按下按钮 '+held.join(', ') : ''} ${offCenter.length ? '未回中的轴 '+offCenter.map(a=>`${a.index} (${a.delta.toFixed(2)})`).join(', ') : ''}`;
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
      } else { message.textContent = `步骤 ${c.stage+1}/${stages.length}：${label}，只按一个方向并保持约半秒`; return; }
    } else if (kind === 'button') {
      const inputs = pad.buttons.map((b,i)=>b.pressed?i:-1).filter(i=>i>=0);
      if (inputs.length !== 1) { message.textContent = `步骤 ${c.stage+1}/${stages.length}：${label}；${inputs.length ? '检测到多个按钮 '+inputs.join(', ')+'，请只按一个' : '尚未检测到按键，请按住约半秒'}；原始轴：${pad.axes.map(v=>v.toFixed(2)).join(', ')}`; return; }
      if (Object.values(c.buttons).includes(inputs[0])) { message.textContent = '此按钮已分配，请松开后按正确按钮：'+label; return; }
      c.buttons[output] = inputs[0];
    } else {
      const inputs = deviations.filter(a=>Math.abs(a.delta)>.45).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
      if (!inputs.length || (inputs[1] && Math.abs(inputs[0].delta)-Math.abs(inputs[1].delta)<.25)) {
        message.textContent = `步骤 ${c.stage+1}/${stages.length}：${label}，推过一半并保持约半秒；${inputs.length ? '两条轴变化接近，请沿提示方向直推' : '摇杆幅度不足'}。实际轴变化：${deviations.map(a=>`${a.index}: ${a.delta.toFixed(2)}`).join(' | ')}`; return;
      }
      if (Object.values(c.axes).some(a=>a.index===inputs[0].index)) { message.textContent = '此轴已分配，请松开后移动正确摇杆：'+label; return; }
      c.axes[output] = {index:inputs[0].index, center:c.centers[inputs[0].index], sign:Math.sign(inputs[0].delta)*sign};
    }
    c.stage++; c.released = false;
    if (c.stage === stages.length) {
      saved[pad.id] = {buttons:c.buttons,axes:c.axes,directions:c.directions,axisCount:c.axisCount,buttonCount:c.buttonCount};
      try { localStorage.setItem('xlerobot-pad-mappings',JSON.stringify(saved)); } catch (_) {}
      releaseCenters = c.centers;
      calibration = null; button.textContent = '重新校准手柄';
      message.textContent = stages === directionStages ? '方向键校准完成：↑↓ 切换关节，←→ 切换模式。' : '校准完成。可继续点击“校准方向键”，或用网页选择模式和关节。';
    } else message.textContent = `已记录步骤 ${c.stage}/${stages.length}。下一步：${stages[c.stage][0]}；请先松开按钮并让摇杆回中`;
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
