'use strict';
(() => {
  const panel=document.createElement('div'); panel.className='panel base';
  panel.innerHTML=`<h2>Training Data Collection</h2>
    <label>Task instruction <input id="record-task" size="48" maxlength="300" value="pick up the green block"></label>
    <p><button id="record-start">Start recording</button> <button id="record-success">Finish: success</button>
    <button id="record-failure">Finish: failure</button> <button id="record-discard">Discard attempt</button></p>
    <p id="record-status">Not recording</p>`;
  document.querySelector('.cams').before(panel);
  const task=panel.querySelector('#record-task'),status=panel.querySelector('#record-status');
  const buttons=['record-success','record-failure','record-discard'].map(id=>panel.querySelector('#'+id));
  async function call(action,data={}) { const r=await fetch('/api/recording/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); if(!r.ok)throw new Error(await r.text()); return r.json(); }
  panel.querySelector('#record-start').onclick=async()=>{try{await call('start',{task:task.value});await refresh()}catch(e){status.textContent='Start failed: '+e.message}};
  panel.querySelector('#record-success').onclick=async()=>{try{await call('finish',{success:true});await refresh()}catch(e){status.textContent='Save failed: '+e.message}};
  panel.querySelector('#record-failure').onclick=async()=>{try{await call('finish',{success:false});await refresh()}catch(e){status.textContent='Save failed: '+e.message}};
  panel.querySelector('#record-discard').onclick=async()=>{try{await call('discard');await refresh()}catch(e){status.textContent='Discard failed: '+e.message}};
  async function refresh(){try{const s=await(await fetch('/api/recording/status')).json();status.textContent=s.active?`Recording: episode ${s.episode_index}, ${s.frames} frames, ${s.duration_s} seconds, ${s.task}`:(s.error?'Recording error: '+s.error:'Not recording');panel.querySelector('#record-start').disabled=s.active;buttons.forEach(b=>b.disabled=!s.active)}catch(e){status.textContent='Status read failed: '+e.message}}
  setInterval(refresh,500);refresh();
})();
