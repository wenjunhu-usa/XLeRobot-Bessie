'use strict';
(() => {
  const panel = document.createElement('div');
  panel.className = 'panel base';
  panel.innerHTML = `<h2>手柄控制</h2><label>模式 <select id="pad-mode"><option value="arms">逐关节</option><option value="cartesian">末端抓取（运动学）</option><option value="head">头部</option><option value="wheels">轮子</option></select></label> <label><input id="arm-pad-enabled" type="checkbox">启用手柄</label><p id="arm-pad-status">按一下手柄按钮以识别设备</p><p>方向键 ← / → 切换模式，切换后需重新启用。末端抓取模式可连续伸缩、升降和开合夹爪，适合手动 Pickup / Place。− / + 急停。</p><p id="pad-error" role="alert" style="color:#fbbf24"></p><details><summary>手柄识别诊断（无动作）</summary><pre id="pad-diagnostics" style="white-space:pre-wrap;text-align:left"></pre></details><div id="pad-guide"></div>`;
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
  const names = ['肩部抬升', '肘部', '手腕俯仰', '手腕旋转', '夹爪'];
  let selected = 0, previous = [], ready = false, busy = false, token = null, revision = 0, activeIndex = null;
  function renderGuide() {
    const armJoint = names[selected];
    let rows;
    if (mode.value === 'arms') {
      rows = [
        ['按住 L + 左摇杆 ← / →', '左臂肩部旋转（shoulder_pan）'],
        ['按住 L + 左摇杆 ↑ / ↓', `左臂${armJoint}（${joints[selected]}）`],
        ['按住 R + 右摇杆 ← / →', '右臂肩部旋转（shoulder_pan）'],
        ['按住 R + 右摇杆 ↑ / ↓', `右臂${armJoint}（${joints[selected]}）`],
        ['方向键 ↑ / ↓', '切换纵向摇杆关节：肩部抬升 → 肘部 → 手腕俯仰 → 手腕旋转 → 夹爪'],
        ['同时按住 L + R', '两个摇杆可同时控制双臂'],
        ['松开对应肩键', '停止新增动作，关节保持最后目标']
      ];
    } else if (mode.value === 'cartesian') {
      rows = [
        ['按住 L + 左摇杆 ← / →', '左臂末端收回 / 伸出'],
        ['按住 L + 左摇杆 ↑ / ↓', '左臂末端升高 / 降低'],
        ['按住 R + 右摇杆 ← / →', '右臂末端收回 / 伸出'],
        ['按住 R + 右摇杆 ↑ / ↓', '右臂末端升高 / 降低'],
        ['按住 L 或 R + A / B', '对应夹爪闭合 / 打开'],
        ['按住 L 或 R + X / Y', '对应夹爪俯仰向下 / 向上'],
        ['同时按住 L + R', '可同时控制双臂']
      ];
    } else if (mode.value === 'head') {
      rows = [
        ['按住 L + 左摇杆 ← / →', '头部左右转动（head_motor_1）'],
        ['按住 L + 左摇杆 ↑ / ↓', '头部上下俯仰（head_motor_2）'],
        ['松开 L', '停止新增动作，头部保持最后目标'],
        ['右摇杆 / R', '此模式没有动作映射']
      ];
    } else {
      rows = [
        ['勾选“车轮已架空”', '允许启用轮子模式；首次测试保持车轮架空'],
        ['按住 L + 左摇杆 ↑ / ↓', '前进 / 后退（左右车轮配合）'],
        ['按住 L + 左摇杆 ← / →', '左转 / 右转（可与前后组合）'],
        ['松开 L / 左摇杆回中', '停车'],
        ['右摇杆 / R', '此模式没有动作映射']
      ];
    }
    rows.push(['方向键 ← / → 或网页模式下拉框', '切换逐关节 / 末端抓取 / 头部 / 轮子；取消启用，松开摇杆和肩键后重新勾选'],
      ['− / +（Back / Start）', '急停；在网页解除急停后重新启用'],
      ['切换窗口 / 手柄断连', '取消启用并请求停车；轮子另有服务端通信超时停车保护']);
    guide.innerHTML = `<h3>${mode.options[mode.selectedIndex].text}：按键与关节对照</h3>${mode.value === 'arms' ? `<p style="color:#fbbf24">当前纵向摇杆关节：<strong>${armJoint}</strong>（左右臂共用选择）</p>` : ''}<table style="width:100%;text-align:left;border-collapse:collapse"><thead><tr><th scope="col">手柄按键 / 操作</th><th scope="col">关节 / 动作</th></tr></thead><tbody>${rows.map(([key, action]) => `<tr><td style="padding:8px;border-top:1px solid #475569">${key}</td><td style="padding:8px;border-top:1px solid #475569">${action}</td></tr>`).join('')}</tbody></table><p>肩键 L / R 是顶部肩键（LB / RB），不是扳机 ZL / ZR。摇杆向右或向上增加关节数值，反向减少；实际机械运动方向首次小幅确认。夹爪向上增加开合百分比、向下减少。</p>`;
  }
  renderGuide();
  let queue = Promise.resolve();
  const pressed = (pad, i) => !!pad.buttons[i]?.pressed;
  const axis = v => Number.isFinite(v) && Math.abs(v) > 0.2 ? Math.max(-1, Math.min(1, v)) : 0;
  async function request(path, data) {
    const response = await fetch('/api/gamepad/' + path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data), signal:AbortSignal.timeout(1000)});
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(response.status === 404 || response.status === 501 ? '服务端尚未加载手柄接口：请先 Ctrl+C 停止控制器，再运行 ./start_web_controller.sh 并刷新页面' : `HTTP ${response.status}: ${detail}`);
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
    if (mapping.calibrating) { if (enabled.checked) disable(); status.textContent = '正在校准手柄，机器人动作已禁用'; return; }
    diagnostics.textContent = rawPad ? `${rawPad.id}\n映射：${rawPad.mapping || '非标准'}；轴数：${rawPad.axes.length}；按钮数：${rawPad.buttons.length}\n轴值：${rawPad.axes.map((v,i) => `${i}: ${v.toFixed(3)}`).join(' | ')}\n按下的按钮：${rawPad.buttons.map((b,i) => b.pressed ? i : null).filter(i => i !== null).join(', ') || '无'}\n页面焦点：${document.hasFocus() ? '有' : '无'}` : '浏览器没有检测到手柄';
    if (!pad || pad.mapping !== 'standard' || pad.axes.length < 4 || pad.buttons.length < 16) {
      if (enabled.checked || token) {
        errorDisplay.textContent = rawPad ? '启用失败：此手柄没有完整标准映射，请点击“校准非标准手柄”，按提示完成按键和摇杆校准。' : '启用失败：浏览器未检测到手柄，请在此页面按一下手柄普通按钮。';
        disable();
      }
      status.textContent = rawPad ? `${rawPad.id}：请先完成非标准手柄校准` : '未检测到手柄，请按一下按钮'; return;
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
    status.textContent = `${pad.id} | ${mode.options[mode.selectedIndex].text} ${mode.value === 'arms' ? ' / ' + names[selected] : ''} | ${ready ? '已启用' : '停止：启用后松开摇杆和肩键'}`;
    if (emergencyPressed) { disable(); busy = true; try { await emergency(); } catch (e) { status.textContent = e.message; } finally { busy = false; } return; }
    if (!enabled.checked) return;
    if (document.hidden || !document.hasFocus()) { disable(); return; }
    if (mode.value === 'wheels' && !raised.checked) { disable(); errorDisplay.textContent = '轮子模式：先勾选“车轮已架空”'; return; }
    const rev = revision;
    busy = true;
    try {
      if (!ready) {
        if (pad.axes.slice(0, 4).every(v => Number.isFinite(v) && Math.abs(v) <= 0.2) && !pressed(pad, 4) && !pressed(pad, 5)) {
          const result = await enqueue(() => request('mode', {mode:mode.value}));
          if (revision === rev) { token = result.token; ready = true; activeIndex = pad.index; errorDisplay.textContent = ''; }
        } else {
          errorDisplay.textContent = '等待启用：请松开两侧肩键并让两个摇杆回中。实际输入可在手柄识别诊断中查看。';
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
      if (revision === rev) { disable(); errorDisplay.textContent = `手柄已停止：${error.message}`; }
    } finally { busy = false; }
  }
  setInterval(tick, 200);
})();
