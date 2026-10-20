/* 02-canvas.js - split from canvas_unified_v14.html (lines 37-570) */
/* ================= 模式切换 ================= */
function setMode(m){
  mode = m;
  document.getElementById('mShots').classList.toggle('on', m==='shots');
  document.getElementById('mFree').classList.toggle('on', m==='free');
  document.getElementById('mFlow').classList.toggle('on', m==='flow');
  document.getElementById('vShots').classList.toggle('hidden', m!=='shots');
  document.getElementById('vFree').classList.toggle('hidden', m!=='free');
  document.getElementById('vFlow').classList.toggle('hidden', m!=='flow');
  emptyEl.classList.toggle('hidden', DOC.items.length>0);
  // 空态时藏掉信息条和时间线
  const sbarEl = document.querySelector('#vShots .sbar');
  const tlEl = document.querySelector('#vShots .tl');
  if (sbarEl) sbarEl.classList.toggle('hidden', DOC.items.length===0);
  if (tlEl) tlEl.classList.toggle('hidden', DOC.items.length===0);
  if (m==='shots') renderShots();
  if (m==='free')  renderFree();
  if (m==='flow')  renderFlow();
  const hints = {
    shots: DOC.items.length? '镜头墙：点镜头选中 · 拖动换顺序，镜号自动重排' : '选一条路开始',
    free:  DOC.items.length? '自由画布：拖动图片摆放 · 点图放大编辑 · 右键更多' : '选一条路开始',
    flow:  '高级：这是流程步骤，不是节点连线 · 改完点「整组重跑」'
  };
  showHint(hints[m]);
  closeCtx();
}

/* 提示条自动淡出，不长期占位 */
let hintTimer = null;
function showHint(html, hold){
  const h = document.getElementById('hintBar');
  h.innerHTML = html;
  h.style.transition = 'opacity .3s';
  h.style.opacity = '1';
  clearTimeout(hintTimer);
  hintTimer = setTimeout(()=>{ h.style.opacity = '0'; }, hold || 3800);
}

/* ================= 填充演示数据 ================= */
function demoFill(kind, count){
  // 自由画布模式用紧凑排布（6 列 × 2 行，轻微错落），镜头墙模式不依赖坐标
  const total = Math.min(count || 12, DEMO.length);
  const W = 122, H = 168;
  const base = DEMO.slice(0, total).map((s,i)=>{
    const col = i % 6, row = Math.floor(i / 6);
    return {
      id:'s'+(i+1), order:i, duration:s.d, status:s.st, name:s.n, cls:i%6,
      x: 16 + col*130,
      y: 26 + row*200 + (col%2)*14,
      w: W, h: H
    };
  });
  DOC.items = base;
  selId = null;
  emptyEl.classList.add('hidden');
  buildGraph(false);   // 数据变了，连线图重建（丢掉旧的拖动位置和手连的线）
  closeParams();

  const N = total;   // 实际生成的数量
  const openings = {
    script:`收到。我把这段故事拆成了 <b>${N} 个镜头</b>，先按中景/特写/过场分了类。要调整顺序直接拖卡片。`,
    upload:`收到参考图。我把它放在了 <b>自由画布</b>里，可以点开放大改。要拆成镜头序列也可以。`,
    tpl:`用了「短剧分镜」模板：<b>${N} 个镜头</b>，其中 ${Math.max(0,N-3)} 个已生成、1 个生成中、1 个失败、1 个待生成。`,
    talk:`好，我按你说的做了。总共 <b>${N} 个镜头</b>，先看看镜头墙的节奏对不对。`
  };
  // 搜索流程里由 runSearchDemo 自己汇报，不要这里再插一条
  if (!window.__suppressDemoMsg) agAdd('ai', openings[kind] || '好的。');

  // 参数不同的场景切到合适模式
  setMode(kind==='upload' ? 'free' : 'shots');
  toast(`已生成 ${N} 个${kind==='upload'?'对象':'镜头'}`);
}

/* ================= 镜头墙渲染 ================= */
function renderShots(){
  const items = DOC.items.slice().sort((a,b)=>a.order-b.order);
  grid.innerHTML='';
  items.forEach((s,i)=>{
    const el = document.createElement('div');
    el.className = 'shot' + (s.id===selId?' sel':'') + (s.status==='err'?' err':'') + (s.status==='todo'?' todo':'') + (s.wsSim?' sim':'');
    el.draggable = true;
    el.dataset.id = s.id;
    el.dataset.i = i;
    el.innerHTML = `<div class="im${s.thumbUrl?' has-img':''}" style="${
        s.thumbUrl
          ? `background-image:url("${s.thumbUrl}");background-size:cover;background-position:center`
          : `background:${BG[s.cls]}`
      }">
        ${s.thumbUrl ? '' : '<div class="glow"></div><div class="fig"></div>'}`
      + (s.status==='err' ? '<div class="errbadge">生成失败 · 403</div>' : '')
      + (s.status==='todo' ? '<div class="todobadge">'
          + '<svg class="ic" viewBox="0 0 24 24" style="color:var(--tx3)"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></svg>待生成</div>' : '')
      + `<span class="no">${String(i+1).padStart(2,'0')}</span>`
      + `<span class="stt ${s.status}"></span>`
      + (typeof wsRefChipsHtml === 'function' ? wsRefChipsHtml(s.id) : '')
      + `</div>`
      + `<div class="info"><div class="nm">${s.name}</div><div class="ln">`
      + `<span>${s.duration>0?s.duration.toFixed(1)+'s':'—'}</span>`
      + `<span class="d">${s.wsSim ? '模拟' : s.canvas ? s.canvas.width+'×'+s.canvas.height : s.status==='ok'?'1024×1536':s.status==='err'?'403':s.status==='run'?'生成中':'—'}</span>`
      + `</div></div>`;
    el.addEventListener('click', ()=>{
      if(s.status==='todo') return;
      selId=s.id; renderShots();
      const n=document.querySelector('.shot[data-id="' + s.id + '"]');
      if (n) showFloatBar(n, s);
    });
    el.addEventListener('dblclick', ()=> openLB(s.id));
    el.addEventListener('contextmenu', e=>{ e.preventDefault(); selId=s.id; renderShots(); openCtx(e.clientX,e.clientY,s.id); });
    el.addEventListener('dragstart', e=>{ dragOrder=i; el.classList.add('dragging');
      e.dataTransfer.effectAllowed='move'; try{e.dataTransfer.setData('text/plain',String(i))}catch(_){} });
    el.addEventListener('dragend', ()=>{ el.classList.remove('dragging'); dragOrder=-1; });
    el.addEventListener('dragover', e=>{ e.preventDefault(); if(dragOrder!==-1&&dragOrder!==i) el.classList.add('over'); });
    el.addEventListener('dragleave', ()=> el.classList.remove('over'));
    el.addEventListener('drop', e=>{
      e.preventDefault(); el.classList.remove('over');
      if(dragOrder===-1||dragOrder===i) return;
      const arr = DOC.items.slice().sort((a,b)=>a.order-b.order);
      const moved = arr.splice(dragOrder,1)[0];
      arr.splice(i,0,moved);
      arr.forEach((o,k)=>o.order=k);
      DOC.items = arr;
      renderShots();
      const from=Math.min(dragOrder,i)+1;
      document.getElementById('hintBar').innerHTML = `镜头 <b>${from}</b> 移到第 <b>${i+1}</b> 位 · 镜号已重排`;
      setTimeout(()=>{ if(mode==='shots') setMode('shots');
bindFloatBarHide();

/* 原型演示工具条：搜索失败 / 注入（真实现里不该有） */
(function mountFailTools(){
  const host = document.getElementById('agb');
  if (!host) return;
  const d = document.createElement('div');
  d.className = 'msg ai'; d.id = 'failToolsMsg';
  d.innerHTML = `<div class="who">演示</div><div class="bubble" style="padding:9px 11px">${failToolbar()}
    <div style="font-size:9.5px;color:var(--tx3);margin-top:6px;line-height:1.6">
      真搜索一定会失败。这三种要分开说 —— 别把"查不到"说成"没有"。
    </div></div>`;
  host.appendChild(d);
})(); }, 1600);
    });
    grid.appendChild(el);
  });
  renderTimeline();
  renderMeta();
}

function renderTimeline(){
  const items = DOC.items.slice().sort((a,b)=>a.order-b.order);
  track.innerHTML='';
  const total = items.reduce((a,s)=>a+(s.duration||0),0) || 1;
  items.forEach((s,i)=>{
    const el=document.createElement('div');
    el.className='seg2 '+s.status+(s.id===selId?' sel':'');
    el.style.flex=String(Math.max(s.duration,0.4)/total);
    el.textContent=s.duration>0?s.duration.toFixed(1):'';
    el.title=`镜头 ${i+1} · ${s.name} · ${s.duration>0?s.duration.toFixed(1)+'s':'待生成'}`;
    el.addEventListener('click',()=>{ if(s.status!=='todo'){ selId=s.id; renderShots(); } });
    track.appendChild(el);
  });
  document.getElementById('totalTime').textContent = fmt(total);
  const sel = items.find(x=>x.id===selId);
  document.getElementById('curTime').textContent = sel
    ? fmt(items.slice(0, items.findIndex(x=>x.id===selId)).reduce((a,s)=>a+(s.duration||0),0)) : '00:00';
}
function renderMeta(){
  const items = DOC.items;
  const c = k => items.filter(s=>s.status===k).length;
  document.getElementById('metaBar').textContent =
    `${items.length} 个镜头 · 总时长 ${fmt(items.reduce((a,s)=>a+(s.duration||0),0))} · `
    + `${c('ok')} 已生成 / ${c('run')} 生成中 / ${c('err')} 失败 / ${c('todo')} 待生成`;
}
function fmt(sec){ const m=Math.floor(sec/60), s=Math.round(sec%60);
  return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0'); }
function addShot(){
  const maxOrder = DOC.items.reduce((a,s)=>Math.max(a,s.order),-1);
  DOC.items.push({id:'n'+Date.now(), order:maxOrder+1, duration:0, status:'todo',
    name:'新镜头', cls:DOC.items.length%6, x:30, y:30, w:176, h:244});
  emptyEl.classList.add('hidden');
  renderShots();
  toast('已加一镜 · 待生成');
  grid.scrollTop = grid.scrollHeight;
}

/* ================= 自由画布渲染 ================= */
function renderFree(){
  freecv.querySelectorAll('.item').forEach(e=>e.remove());
  DOC.items.forEach(s=>{
    const el=document.createElement('div');
    el.className='item'+(s.id===selId?' sel':'');
    el.dataset.id=s.id;
    el.style.cssText=`left:${s.x}px;top:${s.y}px;width:${s.w}px;height:${s.h}px`;
    el.innerHTML=`<div class="im${s.thumbUrl?' has-img':''}" style="${
        s.thumbUrl
          ? `background-image:url("${s.thumbUrl}");background-size:cover;background-position:center`
          : `background:${BG[s.cls]}`
      }">${s.thumbUrl ? '' : '<div class="glow"></div><div class="fig"></div>'}</div>
        <div class="lbl2">${s.name}</div>`;
    bindFree(el,s);
    freecv.appendChild(el);
  });
}
function bindFree(el,s){
  let drag=false,moved=false,sx=0,sy=0,ox=0,oy=0;
  el.addEventListener('pointerdown',e=>{
    if(e.button!==0) return;
    e.stopPropagation(); el.setPointerCapture(e.pointerId);
    drag=true;moved=false;sx=e.clientX;sy=e.clientY;ox=s.x;oy=s.y;
    // 注意：这里绝不能 renderFree()，否则正在拖的元素会被重建，拖不动
    selId=s.id;
    freecv.querySelectorAll('.item').forEach(x=>x.classList.toggle('sel', x.dataset.id===s.id));
  });
  el.addEventListener('pointermove',e=>{
    if(!drag) return;
    const dx=e.clientX-sx, dy=e.clientY-sy;
    if(Math.abs(dx)>3||Math.abs(dy)>3) moved=true;
    s.x=Math.max(-20,Math.min(freecv.clientWidth-s.w+20,ox+dx));
    s.y=Math.max(-20,Math.min(freecv.clientHeight-s.h+30,oy+dy));
    el.style.left=s.x+'px'; el.style.top=s.y+'px';
  });
  el.addEventListener('pointerup',e=>{
    if(!drag) return; drag=false; el.releasePointerCapture(e.pointerId);
    if(!moved){
      selId=s.id; renderFree();
      const el2 = freecv.querySelector('.item[data-id="' + s.id + '"]');
      if (el2) showFloatBar(el2, s);
    }
  });
  el.addEventListener('contextmenu',e=>{
    e.preventDefault(); e.stopPropagation(); selId=s.id; renderFree(); openCtx(e.clientX,e.clientY,s.id);
  });
}

/* ================= 高级：打组执行 ================= */
function renderFlow(){
  const items = DOC.items.slice().sort((a,b)=>a.order-b.order);
  const ok = items.filter(s=>s.status==='ok').length;
  document.getElementById('flowCount').textContent =
    `${items.length} 个镜头 · ${ok} 个已生成`;
  const steps = [
    ['1','读取分镜脚本','12 镜','ok','0.3s'],
    ['2','角色/场景一致性检查','参考库匹配','ok','0.4s'],
    ['3','生成镜头图 ×'+items.length, ok+'/'+items.length+' 完成',
      items.some(s=>s.status==='err')?'err':'ok',
      items.some(s=>s.status==='run')?'运行中':'—'],
    ['4','合成时间线','总时长 '+fmt(items.reduce((a,s)=>a+(s.duration||0),0)),'ok','0.2s'],
    ['5','出片（未开始）','—','todo','—']
  ];
  document.getElementById('steps').innerHTML = steps.map(x=>
    `<div class="step"><span class="n">${x[0]}</span>
     <span class="tx">${x[1]}</span>
     <span class="st2 ${x[3]}">${x[2]}</span></div>`).join('');
  if (flowView==='graph') renderGraph();
}

/* 高级子视图切换 */
let flowView = 'steps';
function setFlowView(v){
  flowView = v;
  document.getElementById('ftbSteps').classList.toggle('on', v==='steps');
  document.getElementById('ftbGraph').classList.toggle('on', v==='graph');
  document.getElementById('flowStepsView').classList.toggle('hidden', v!=='steps');
  document.getElementById('flowGraphView').classList.toggle('hidden', v!=='graph');
  if (v==='graph') renderGraph();
}

/* ============ 连线图：可编辑 · 可连线 · 可运行 ============ */
let GRAPH = { nodes: [], edges: [] };
let gSel = null;        // 选中节点 id
let gLink = null;       // { from, kind, x1, y1 } 正在连线
let gDrag = null;       // { id, sx, sy, ox, oy, moved }

const KIND_COLOR = { text:'#60a5fa', image:'#22d3ee', video:'#a78bfa', model:'#fbbf24', any:'#71717a' };
const NODE_DEFS = [
  {k:'text',   n:'文本',     ins:[],              outs:['text'],  run:false},
  {k:'prompt', n:'提示词',   ins:['text'],        outs:['text'],  run:true},
  {k:'image',  n:'生图',     ins:['text','image'],outs:['image'], run:true},
  {k:'video',  n:'生视频',   ins:['image','text'],outs:['video'], run:true},
  {k:'merge',  n:'合成',     ins:['image'],       outs:['video'], run:false},
];

function canConnect(aKind, bKind){
  if (!aKind || !bKind) return false;
  if (aKind === 'any' || bKind === 'any') return true;
  return aKind === bKind;
}

function buildGraph(keepPos){
  const items = DOC.items.slice().sort((a,b)=>a.order-b.order);
  // 空画布：不造节点，直接给空图（切换用户/新建画布时会走到这里）
  if (!items.length){
    GRAPH = { nodes: [], edges: [] };
    return;
  }
  const N = items.length || 12;
  /* 每个节点都要指到一个 capKey（CAPS 里那份能力）—— 指不到的就是假壳。
     script / board 是例外：它们读文档、不调能力，用 data:true 明说。 */
  const nodes = [
    {id:'script', x:20,  y:170, w:136, t:'分镜脚本', sub:N+' 镜',                     kind:'text',  st:'ok', data:true, ins:[],           outs:['text']},
    {id:'board',  x:186, y:170, w:136, t:'分镜表',   sub:'镜号 01-'+String(N).padStart(2,'0'), kind:'text', st:'ok', data:true, ins:['text'], outs:['text']}
  ];
  for (let i=0;i<N;i++){
    const col=i%3, row=Math.floor(i/3);
    nodes.push({
      id:'g'+i, x:372+col*152, y:16+row*78, w:140,
      t:String(i+1).padStart(2,'0')+' '+items[i].name,
      sub: items[i].status==='ok'?'已生成':(items[i].status==='err'?'失败 403':(items[i].status==='run'?'生成中':'待生成')),
      kind:'image', st:items[i].status, ins:['text','image'], outs:['image'], shot:i,
      cap:'image-gen'
    });
  }
  const rows=Math.ceil(N/3), yb=16+rows*78+18;
  nodes.push({id:'merge', x:372, y:yb, w:140, t:'合成时间线', kind:'video',
    sub:'总时长 '+fmt(items.reduce((a,s)=>a+(s.duration||0),0)), st:'ok', ins:['image'], outs:['video'],
    cap:'clip'});
  nodes.push({id:'out',   x:548, y:yb, w:140, t:'出片', kind:'video',
    sub:'未开始', st:'todo', ins:['video'], outs:[],
    cap:'clip-render'});
  // 🔴 3D 分支：图生3D（原子）→ 3D 导演台（复合）
  nodes.push({id:'to3d',   x:372, y:yb+78, w:140, t:'图生 3D', kind:'model',
    sub:'TripoSR → glb', st:'ok', ins:['image'], outs:['model'], atomic:true,
    cap:'model-3d'});
  nodes.push({id:'previs', x:548, y:yb+78, w:140, t:'3D 导演台', kind:'video', comp:1,
    sub:'预演运镜 → 回填分镜', st:'todo', ins:['model','text'], outs:['video'],
    cap:'previs'});

  const edges=[{f:'script',fp:'text',t:'board',tp:'text'}];
  for(let i=0;i<N;i++) edges.push({f:'board', fp:'text',  t:'g'+i,   tp:'text'});
  for(let i=0;i<N;i++) edges.push({f:'g'+i,   fp:'image', t:'merge', tp:'image'});
  edges.push({f:'merge', fp:'video', t:'out', tp:'video'});
  // 3D 分支连线
  edges.push({f:'g0',    fp:'image', t:'to3d',   tp:'image'});
  edges.push({f:'board', fp:'text',  t:'previs', tp:'text'});
  edges.push({f:'to3d',  fp:'model', t:'previs', tp:'model'});

  const oldPos = {};
  if (keepPos) (GRAPH.nodes||[]).forEach(n=>oldPos[n.id]={x:n.x,y:n.y});
  nodes.forEach(n=>{ if(oldPos[n.id]){ n.x=oldPos[n.id].x; n.y=oldPos[n.id].y; } });

  GRAPH = { nodes, edges };
}

/* --------- 渲染 --------- */
function renderGraph(){
  if (!GRAPH.nodes.length) buildGraph(false);
  const ginner = document.getElementById('ginner');
  const svg    = document.getElementById('gedges');
  const nbox   = document.getElementById('gnodes');

  const maxY = Math.max(...GRAPH.nodes.map(n=>n.y)) + 90;
  const maxX = Math.max(...GRAPH.nodes.map(n=>n.x+n.w)) + 60;
  ginner.style.height = Math.max(maxY, 420)+'px';
  ginner.style.width  = Math.max(maxX, 700)+'px';
  svg.setAttribute('viewBox', `0 0 ${Math.max(maxX,700)} ${Math.max(maxY,420)}`);

  const pos = {};
  GRAPH.nodes.forEach(n=> pos[n.id]={x:n.x,y:n.y,w:n.w});
  const portY = (n, idx, total) => n.y + 24 + (idx - (total-1)/2) * 15;

  // 连线
  svg.innerHTML = GRAPH.edges.map((e,i)=>{
    const a = pos[e.f], b = pos[e.t];
    if (!a || !b) return '';
    const na = GRAPH.nodes.find(n=>n.id===e.f), nb = GRAPH.nodes.find(n=>n.id===e.t);
    const yi = na.outs.indexOf(e.fp), yo = nb.ins.indexOf(e.tp);
    const y1 = portY(a, yi<0?0:yi, Math.max(na.outs.length,1)) - 8;
    const y2 = portY(b, yo<0?0:yo, Math.max(nb.ins.length,1)) - 8;
    const x1 = a.x + a.w, x2 = b.x;
    const dx = Math.max(28, (x2-x1)/2);
    const st = nb.st || 'ok';
    const cls = st==='run'?'run':st==='err'?'err':st==='todo'?'todo':'ok';
    return `<path class="gedge ${cls}" data-ei="${i}" style="pointer-events:stroke;cursor:pointer"
      d="M ${x1} ${y1} C ${x1+dx} ${y1}, ${x2-dx} ${y2}, ${x2} ${y2}"/>`;
  }).join('');

  // 节点
  nbox.innerHTML = GRAPH.nodes.map(n=>{
    const dot = n.st==='ok'?'var(--ok)':n.st==='run'?'var(--ac)':n.st==='err'?'var(--dg)':'var(--tx3)';
    const ins = (n.ins||[]).map((k,i)=>`<span class="gport i" data-node="${n.id}" data-kind="${k}" data-dir="in"
        style="border-color:${KIND_COLOR[k]||KIND_COLOR.any};top:${24+(i-(n.ins.length-1)/2)*15}px"></span>`).join('');
    const outs = (n.outs||[]).map((k,i)=>`<span class="gport o" data-node="${n.id}" data-kind="${k}" data-dir="out"
        style="border-color:${KIND_COLOR[k]||KIND_COLOR.any};top:${24+(i-(n.outs.length-1)/2)*15}px"></span>`).join('');
    return `<div class="gnode${gSel===n.id?' sel':''}${n.comp?' comp':''}${n.userGroup?' usergrp':''}${gMulti.has(n.id)?' multi':''}" data-id="${n.id}"
        style="left:${n.x}px;top:${n.y}px;width:${n.w}px">
      ${ins}
      <div class="ghd"><span class="gt">${n.t}</span><span class="gd" style="background:${dot}"></span></div>
      <div class="gbd">${n.sub}</div>
      ${outs}
      ${capKeyOfNode(n)?`<button class="grun" data-run="${n.id}" title="运行这个节点（会先过门禁）">▶</button>`:''}
    </div>`;
  }).join('');

  // 临时连线
  const ghost = document.getElementById('gghost');
  if (gLink && ghost){
    const a = pos[gLink.from];
    const x1 = a.x + a.w, y1 = a.y + 8;
    ghost.innerHTML = `<path class="gedge ghost" d="M ${x1} ${y1} L ${gLink.x1} ${gLink.y1}"/>`;
  } else if (ghost) ghost.innerHTML='';

  bindGraph();
}

/* --------- 交互绑定 --------- */
function bindGraph(){
  // 节点拖动 / 选中
  document.querySelectorAll('.gnode').forEach(el=>{
    el.addEventListener('pointerdown', e=>{
      if (e.target.classList.contains('gport')) return;
      if (e.target.classList.contains('grun')) return;
      const id = el.dataset.id;
      const n = GRAPH.nodes.find(x=>x.id===id);
      if (e.shiftKey){
        if (gMulti.has(id)) gMulti.delete(id); else gMulti.add(id);
        el.classList.toggle('multi', gMulti.has(id));
        renderGroupBar();
        return;
      }
      gSel = id;
      gDrag = { id, sx:e.clientX, sy:e.clientY, ox:n.x, oy:n.y, moved:false };
      el.setPointerCapture(e.pointerId);
      // 只改选中态，绝不 renderGraph（否则正在拖的节点被重建，拖不动）
      document.querySelectorAll('.gnode').forEach(x=>x.classList.toggle('sel', x.dataset.id===id));
      showNodeParams(id);
    });
    el.addEventListener('pointermove', e=>{
      if (!gDrag || gDrag.id !== el.dataset.id) return;
      const dx=e.clientX-gDrag.sx, dy=e.clientY-gDrag.sy;
      if (Math.abs(dx)>3||Math.abs(dy)>3) gDrag.moved=true;
      const n = GRAPH.nodes.find(x=>x.id===gDrag.id);
      n.x = Math.max(0, gDrag.ox+dx); n.y = Math.max(0, gDrag.oy+dy);
      el.style.left = n.x+'px'; el.style.top = n.y+'px';
      redrawEdges();
    });
    el.addEventListener('pointerup', e=>{
      if (gDrag && gDrag.id===el.dataset.id){
        const moved = gDrag.moved;
        gDrag=null;
        if (moved){ renderGraph(); }   // 拖完才重建，位置已存进 GRAPH
      }
    });
  });

  // 端口：拖出连线
  document.querySelectorAll('.gport').forEach(p=>{
    p.addEventListener('pointerdown', e=>{
      e.stopPropagation();
      if (p.dataset.dir !== 'out') return;
      const n = GRAPH.nodes.find(x=>x.id===p.dataset.node);
      gLink = { from:p.dataset.node, kind:p.dataset.kind, x1:n.x+n.w+60, y1:n.y+24 };
      document.addEventListener('pointermove', onLinkMove);
      document.addEventListener('pointerup', onLinkUp);
      renderGraph();
    });
    p.addEventListener('pointerup', e=>{
      e.stopPropagation();
      if (!gLink) return;
      // 落在某个输入端口上？
      if (p.dataset.dir === 'in' && p.dataset.node !== gLink.from){
        const ok = canConnect(gLink.kind, p.dataset.kind);
        if (ok){
          GRAPH.edges.push({f:gLink.from, fp:gLink.kind, t:p.dataset.node, tp:p.dataset.kind});
          toast(`已连线：${gLink.kind} → ${p.dataset.kind}`);
        } else {
          toast(`类型不匹配：${gLink.kind} ✕ ${p.dataset.kind}`);
        }
      }
      endLink();
    });
  });

  // 点连线删除
  document.querySelectorAll('.gedge[data-ei]').forEach(p=>{
    p.addEventListener('click', e=>{
      e.stopPropagation();
      const i = +p.dataset.ei;
      const ed = GRAPH.edges[i];
      GRAPH.edges.splice(i,1);
      renderGraph();
      toast(`已断开连线 ${ed?ed.f+'→'+ed.t:''}`);
    });
  });

  // 运行单节点
  document.querySelectorAll('.grun').forEach(b=>{
    b.addEventListener('click', e=>{
      e.stopPropagation();
      runNode(b.dataset.run);
    });
  });
}

function onLinkMove(e){
  if (!gLink) return;
  const r = document.getElementById('ginner').getBoundingClientRect();
  const sc = r.width / document.getElementById('ginner').offsetWidth || 1;
  gLink.x1 = (e.clientX - r.left) / (r.width/parseFloat(document.getElementById('ginner').style.width||r.width));
  gLink.y1 = (e.clientY - r.top)  / (r.height/parseFloat(document.getElementById('ginner').style.height||r.height));
  const ghost = document.getElementById('gghost');
  const a = GRAPH.nodes.find(n=>n.id===gLink.from);
  if (ghost && a){
    ghost.innerHTML = `<path class="gedge ghost"
      d="M ${a.x+a.w} ${a.y+8} L ${gLink.x1} ${gLink.y1}"/>`;
  }
}
function onLinkUp(e){
  if (!gLink) return;
  // 落在节点上但没落在端口 → 取消
  setTimeout(endLink, 10);
}
function endLink(){
  gLink = null;
  document.removeEventListener('pointermove', onLinkMove);
  document.removeEventListener('pointerup', onLinkUp);
  const ghost = document.getElementById('gghost');
  if (ghost) ghost.innerHTML='';
  renderGraph();
}
function redrawEdges(){
  const svg = document.getElementById('gedges');
  const pos = {};
  GRAPH.nodes.forEach(n=> pos[n.id]={x:n.x,y:n.y,w:n.w});
  const portY = (n, idx, total) => n.y + 24 + (idx - (total-1)/2) * 15;
  svg.innerHTML = GRAPH.edges.map((e,i)=>{
    const a=pos[e.f], b=pos[e.t]; if(!a||!b) return '';
    const na=GRAPH.nodes.find(n=>n.id===e.f), nb=GRAPH.nodes.find(n=>n.id===e.t);
    const yi=na.outs.indexOf(e.fp), yo=nb.ins.indexOf(e.tp);
    const y1=portY(a,yi<0?0:yi,Math.max(na.outs.length,1))-8;
    const y2=portY(b,yo<0?0:yo,Math.max(nb.ins.length,1))-8;
    const x1=a.x+a.w, x2=b.x, dx=Math.max(28,(x2-x1)/2);
    const st=nb.st||'ok';
    const cls=st==='run'?'run':st==='err'?'err':st==='todo'?'todo':'ok';
    return `<path class="gedge ${cls}" data-ei="${i}" style="pointer-events:stroke;cursor:pointer"
      d="M ${x1} ${y1} C ${x1+dx} ${y1}, ${x2-dx} ${y2}, ${x2} ${y2}"/>`;
  }).join('');
}

/* --------- 从节点库加节点（P4：加新用途=加配置） --------- */
const LIB_DEFS = {
  'text':      {t:'文本',            kind:'text',  ins:[],                outs:['text'],  atomic:1, data:1},
  'prompt':    {t:'提示词',          kind:'text',  ins:['text'],          outs:['text'],  atomic:1, data:1},
  'image':     {t:'AI 生图',         kind:'image', ins:['text','image'],  outs:['image'], atomic:1, cap:'image-gen'},
  'to3d':      {t:'图生 3D',         kind:'model', ins:['image'],         outs:['model'], atomic:1, cap:'model-3d'},
  'crop':      {t:'裁剪（本地）',     kind:'image', ins:['image'],         outs:['image'], atomic:1, cap:'crop'},
  'filter':    {t:'滤镜（本地）',     kind:'image', ins:['image'],         outs:['image'], atomic:1, cap:'filter'},
  'gen-page':  {t:'生图工作台',       kind:'image', ins:['text','image'],  outs:['image'], comp:1, cap:'image-gen'},
  'motion-page':{t:'动图工作台',      kind:'video', ins:['image'],         outs:['video'], comp:1, cap:'motion-gif'},
  'm3d-page':  {t:'3D 工作台',        kind:'model', ins:['image','model'], outs:['model'], comp:1, cap:'model-3d'},
  'previs-page':{t:'3D 导演台',       kind:'video', ins:['model','text'],  outs:['video'], comp:1, cap:'previs'},
  /* 🔴 剪辑出片调的是 clip（/api/v1/clip/compose）。
     之前写成 cap:'image-editor' —— 而 image-editor 在 CAPS 里明确标 node:false
     （它只是 L2 页面容器，内部调 crop/filter/image-adjust），等于一个节点指着
     「不是能力的能力」。 */
  'clip-page': {t:'剪辑出片',         kind:'video', ins:['video','audio'], outs:['video'], comp:1, cap:'clip'}
};
