'use strict';
(() => {
  const panel=document.createElement('div'); panel.className='panel base';
  panel.innerHTML=`<h2>训练数据采集</h2>
    <label>任务指令 <input id="record-task" size="48" maxlength="300" value="pick up the green block"></label>
    <p><button id="record-start">开始录制</button> <button id="record-success">成功结束</button>
    <button id="record-failure">失败结束</button> <button id="record-discard">删除本次</button></p>
    <p id="record-status">未录制</p>`;
  document.querySelector('.cams').before(panel);
  const task=panel.querySelector('#record-task'),status=panel.querySelector('#record-status');
  const buttons=['record-success','record-failure','record-discard'].map(id=>panel.querySelector('#'+id));
  async function call(action,data={}) { const r=await fetch('/api/recording/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); if(!r.ok)throw new Error(await r.text()); return r.json(); }
  panel.querySelector('#record-start').onclick=async()=>{try{await call('start',{task:task.value});await refresh()}catch(e){status.textContent='开始失败：'+e.message}};
  panel.querySelector('#record-success').onclick=async()=>{try{await call('finish',{success:true});await refresh()}catch(e){status.textContent='保存失败：'+e.message}};
  panel.querySelector('#record-failure').onclick=async()=>{try{await call('finish',{success:false});await refresh()}catch(e){status.textContent='保存失败：'+e.message}};
  panel.querySelector('#record-discard').onclick=async()=>{try{await call('discard');await refresh()}catch(e){status.textContent='删除失败：'+e.message}};
  async function refresh(){try{const s=await(await fetch('/api/recording/status')).json();status.textContent=s.active?`录制中：episode ${s.episode_index}，${s.frames}帧，${s.duration_s}秒，${s.task}`:(s.error?'录制错误：'+s.error:'未录制');panel.querySelector('#record-start').disabled=s.active;buttons.forEach(b=>b.disabled=!s.active)}catch(e){status.textContent='状态读取失败：'+e.message}}
  setInterval(refresh,500);refresh();
})();
