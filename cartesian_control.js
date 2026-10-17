'use strict';
(() => {
  const panel = document.createElement('div');
  panel.className = 'panel base';
  panel.innerHTML = `<h2>双臂逐关节控制（键盘连续）</h2>
    <label>手臂 <select id="joint-arm"><option value="left">左臂</option><option value="right">右臂</option></select></label>
    <label><input id="joint-keyboard-enabled" type="checkbox">启用键盘逐关节控制</label>
    <p id="joint-keyboard-status">停止</p>
    <table style="margin:auto;text-align:left;border-collapse:collapse"><tbody>
      <tr><td>Q / A</td><td>肩部水平转：负 / 正</td><td>W / S</td><td>上臂肩关节：负 / 正</td></tr>
      <tr><td>E / D</td><td>前臂肘关节：负 / 正</td><td>R / F</td><td>手腕俯仰：负 / 正</td></tr>
      <tr><td>T / G</td><td>手腕旋转：负 / 正</td><td>Y / H</td><td>夹爪：闭合 / 张开</td></tr>
      <tr><td>空格</td><td colspan="3">立即取消键盘控制</td></tr>
    </tbody></table>
    <p>先选择左臂或右臂。勾选启用后，直接持续按住动作键即可连续移动；松开立即停止新增目标。关节每周期 2°，夹爪每周期 2%。首次操作请用短按确认实机方向。</p>`;
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
    shoulder_pan:'肩部水平转', shoulder_lift:'上臂肩关节', elbow_flex:'前臂肘关节',
    wrist_flex:'手腕俯仰', wrist_roll:'手腕旋转', gripper:'夹爪'
  };
  const opposites = {q:'a',a:'q',w:'s',s:'w',e:'d',d:'e',r:'f',f:'r',t:'g',g:'t',y:'h',h:'y'};
  const readyText = () => `已启用：${arm.options[arm.selectedIndex].text}，等待按键`;

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
  function stop(message='停止') {
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
    } catch (error) { stop('启用失败：' + error.message); }
  });
  arm.addEventListener('change', () => {
    held.clear();
    if (enabled.checked) status.textContent = readyText();
  });
  window.addEventListener('blur', () => pause('窗口失去焦点，已暂停；返回后直接按键继续'));
  window.addEventListener('focus', () => {
    if (enabled.checked && token) status.textContent = readyText();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) pause('页面不可见，已暂停；返回后直接按键继续');
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
        status.textContent = `移动中：${arm.options[arm.selectedIndex].text}；${actions.join('，')}；松开即停止`;
      }
    } catch (error) {
      if (rev === revision && (error.status === 400 || error.status === 429)) {
        status.textContent = error.status === 400
          ? '机械臂正在跟随目标，自动等待后继续'
          : '连续控制中：等待下一控制周期';
      } else if (rev === revision) {
        stop('已停止：' + error.message);
      }
    } finally { busy = false; }
  }
  setInterval(tick,200);
})();
