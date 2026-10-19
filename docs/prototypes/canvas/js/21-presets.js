/* 21-presets.js — 预设：保存/复用本地精调参数
   为什么必须有：调好的曲线/色阶/色温，12 镜要统一 —— 不能每张重调。
   和「批量应用」是一对（预设管"存"，批量管"用"）。
*/

/* 预设库（自用阶段存内存） */
let PRESETS = [
  { id:'ps1', name:'冷调电影感', tags:['人像','冷色'],
    params:{ exposure:0, contrast:1.12, saturation:0.92, temp:5800,
      levels:{black:0.02, white:0.98, gamma:1.05},
      curves:{ rgb:[[0,0],[0.25,0.2],[0.5,0.5],[0.75,0.82],[1,1]],
               r:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],
               g:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],
               b:[[0,0],[0.25,0.28],[0.5,0.54],[0.75,0.8],[1,1]] } },
    used:24 },
  { id:'ps2', name:'暖调夕阳', tags:['人像','暖色'],
    params:{ exposure:0.15, contrast:1.06, saturation:1.08, temp:6900,
      levels:{black:0, white:0.96, gamma:1.02},
      curves:{ rgb:[[0,0],[0.25,0.28],[0.5,0.54],[0.75,0.79],[1,1]],
               r:[[0,0],[0.25,0.27],[0.5,0.54],[0.75,0.8],[1,1]],
               g:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],
               b:[[0,0],[0.25,0.23],[0.5,0.46],[0.75,0.72],[1,1]] } },
    used:17 },
  { id:'ps3', name:'商品白底干净', tags:['商品','白底'],
    params:{ exposure:0.3, contrast:0.95, saturation:0.95, temp:6400,
      levels:{black:0.04, white:0.99, gamma:1.0},
      curves:{ rgb:[[0,0],[0.25,0.26],[0.5,0.52],[0.75,0.78],[1,1]],
               r:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],
               g:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],
               b:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]] } },
    used:41 }
];

/* 从当前 LOCAL_ADJ 抓一份参数 */
function currentAdjParams(){
  const a = (typeof LOCAL_ADJ !== 'undefined') ? LOCAL_ADJ : null;
  if (!a) return null;
  return JSON.parse(JSON.stringify({
    exposure: a.exposure, contrast: a.contrast, saturation: a.saturation,
    temp: a.temp, levels: a.levels, curves: a.curves
  }));
}

/* 面板：预设列表 */
function openPresetLib(){
  if (typeof hideFloatBar === 'function') hideFloatBar();
  document.getElementById('overlayHost').innerHTML = `
    <div class="pl" onclick="if(event.target.classList.contains('plw'))closePresetLib()">
      <div class="plw">
        <div class="inp-hd">
          <div class="inp-t">调色预设</div>
          <div class="inp-sub">调好的参数存下来 · 12 镜一次套</div>
          <button class="inp-x" onclick="closePresetLib()">✕</button>
        </div>
        <div class="pl-search">
          <input class="pl-in" placeholder="搜预设名或标签…" oninput="renderPresetLib(this.value)">
        </div>
        <div class="pl-body" id="psBody"></div>
        <div class="pl-foot">
          <span class="pl-note">从「本地精调」调好的参数可以一键存成预设</span>
          <button class="insp-b pri" onclick="savePresetFromAdj()">存当前参数</button>
        </div>
      </div>
    </div>`;
  renderPresetLib('');
}

function closePresetLib(){ document.getElementById('overlayHost').innerHTML = ''; }

function renderPresetLib(q){
  const host = document.getElementById('psBody');
  if (!host) return;
  const k = (q||'').trim().toLowerCase();
  const list = PRESETS.filter(p=>
    !k || p.name.toLowerCase().includes(k) || p.tags.some(t=>t.toLowerCase().includes(k))
  );
  host.innerHTML = list.length ? list.map(p=>`
    <div class="pl-item">
      <div class="pl-hd">
        <span class="pl-name">${esc(p.name)}</span>
        <span class="pl-used">用过 ${p.used} 次</span>
      </div>
      <div class="pl-tags">${p.tags.map(t=>`<span class="pl-tag">${t}</span>`).join('')}</div>
      <div class="pl-text">${describeParams(p.params)}</div>
      <div class="pl-acts">
        <button class="pl-b" onclick="usePreset('${p.id}')">套到这张</button>
        <button class="pl-b" onclick="batchApplyPreset('${p.id}')">批量套…</button>
        <button class="pl-b" onclick="delPreset('${p.id}')" style="color:var(--tx3)">删</button>
      </div>
    </div>`).join('') : '<div class="pl-empty">没找到</div>';
}

/* 参数说明（人话） */
function describeParams(p){
  const out = [];
  if (Math.abs(p.exposure) > 0.01) out.push('曝光 ' + (p.exposure>=0?'+':'') + p.exposure.toFixed(2) + 'EV');
  if (Math.abs(p.contrast-1) > 0.01) out.push('对比 ' + p.contrast.toFixed(2));
  if (Math.abs(p.saturation-1) > 0.01) out.push('饱和 ' + p.saturation.toFixed(2));
  if (Math.abs(p.temp-6100) > 30) out.push('色温 ' + Math.round(p.temp) + 'K');
  if (p.levels && (p.levels.black>0.005 || p.levels.white<0.995 || Math.abs(p.levels.gamma-1)>0.02))
    out.push('色阶');
  if (p.curves){
    const chNames = {rgb:'RGB', r:'R', g:'G', b:'B'};
    Object.keys(p.curves).forEach(ch=>{
      if (p.curves[ch].some(x=>Math.abs(x[1]-x[0])>0.02)) out.push(chNames[ch] + '曲线');
    });
  }
  return out.length ? out.join(' · ') : '无调整';
}

/* 套到当前编辑中的那张 */
function usePreset(id){
  const p = PRESETS.find(x=>x.id===id);
  if (!p) return;
  if (typeof LOCAL_ADJ === 'undefined'){ toast('先在画布上打开一张图'); return; }
  Object.assign(LOCAL_ADJ, JSON.parse(JSON.stringify(p.params)));
  p.used++;
  closePresetLib();
  if (document.querySelector('.lew') && typeof leRenderAll === 'function'){
    leRenderAll();
    toast('已套用「' + p.name + '」');
  } else {
    // 当前没打开精调面板 → 打开并套用
    if (typeof openLocalEdit === 'function'){
      openLocalEdit(selId || (DOC.items[0] && DOC.items[0].id));
      setTimeout(()=>{
        Object.assign(LOCAL_ADJ, JSON.parse(JSON.stringify(p.params)));
        if (typeof leRenderAll === 'function') leRenderAll();
        toast('已套用「' + p.name + '」');
      }, 120);
    }
  }
}

/* 从当前参数存预设 */
function savePresetFromAdj(){
  const params = currentAdjParams();
  if (!params){ toast('没有可存的参数'); return; }
  const name = prompt('给这个预设起个名字：', '未命名预设');
  if (name === null) return;
  PRESETS.unshift({
    id: 'ps' + Date.now(),
    name: String(name).trim() || '未命名预设',
    tags: ['我存的'],
    params, used: 0
  });
  renderPresetLib('');
  toast('已存成预设');
}

function delPreset(id){
  PRESETS = PRESETS.filter(x=>x.id!==id);
  renderPresetLib('');
  toast('已删除');
}
