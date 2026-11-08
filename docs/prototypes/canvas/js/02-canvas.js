/* 02-canvas.js - split from canvas_unified_v14.html (lines 37-570) */
/* ================= 模式切换 ================= */
function setMode(m){
  mode = m;
  /* 离开画布视图就收掉节点浮层，别让工具条飘到镜头墙上 */
  if (m!=='flow' && typeof clearEdgeFocus === 'function') clearEdgeFocus();
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
    shots: DOC.items.length
      ? (DOC.kind === 'character'
          ? '角色图：点一张看大图 · 拖动换角度顺序 · 想做视频再拆分镜'
          : '镜头墙：点镜头选中 · 拖动换顺序，镜号自动重排')
      : '选一条路开始',
    free:  DOC.items.length? '素材墙：拖动图片摆放 · 点图放大编辑 · 右键更多' : '选一条路开始',
    flow:  '画布：节点 + 连线，能拖能连能跑 · 上面可切「步骤」看流程组成'
  };
  showHint(hints[m]);
  closeCtx();
  /* 小地图随视图显隐（33-gmap.js）：切走时 gcanvas 宽度归 0，地图自动藏 */
  if (typeof updateGmap === 'function') updateGmap();
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
function demoFill(kind, count, opts){
  /* opts.quiet = 启动时的默认示例数据（2026-11-05）：只填内容，
     不发消息 / 不弹 toast / 不切模式 / 不自动存版本，免得一进页面弹一堆东西。 */
  const quiet = !!(opts && opts.quiet);
  // 素材墙模式用紧凑排布（6 列 × 2 行，轻微错落），镜头墙模式不依赖坐标
  // character = 角色图（按角度）· promo = 宣传片（建筑/产品，没有角色）· 其余 = 人物分镜
  const src = kind === 'character' && typeof DEMO_CHAR !== 'undefined' ? DEMO_CHAR
            : kind === 'promo' && typeof DEMO_PROMO !== 'undefined' ? DEMO_PROMO
            : DEMO;
  const total = Math.min(count || 12, src.length);
  /* 本地占位片：三组题材各一套纯本地 SVG，不外链、不占版权。
     数量超出时按组循环，绝不出现空 url。生成脚本 tools/gen_thumbs.py。 */
  const thumbSet = kind === 'character' ? 'char' : kind === 'promo' ? 'promo' : 'story';
  const THUMB_N = { char:6, promo:6, story:12 };
  const W = 122, H = 168;
  /* 素材墙的落位：手摆的、大小不一、间距不匀 —— 摆东西的墙就不该是网格。
     （本视图 2026-11-03 由「自由画布」改名素材墙：画布专指节点连线图，
      这里的单位是「一张素材」，不叫画布，免得两种形态混称。）
     坐标是写死的（不用随机），保证每次打开一样，好对比。 */
  const FREE_POS = [
    {x:56,  y:26,  w:134, h:180}, {x:224, y:66,  w:114, h:152},
    {x:372, y:14,  w:152, h:198}, {x:558, y:84,  w:122, h:164},
    {x:716, y:32,  w:138, h:184}, {x:88,  y:238, w:120, h:160},
    {x:242, y:290, w:142, h:190}, {x:420, y:244, w:126, h:168},
    {x:586, y:292, w:118, h:158}, {x:740, y:236, w:134, h:178},
    {x:142, y:452, w:128, h:172}, {x:326, y:470, w:136, h:182}
  ];
  const base = src.slice(0, total).map((s,i)=>{
    const pos = FREE_POS[i] || { x: 40 + (i%6)*140, y: 40 + Math.floor(i/6)*200, w: W, h: H };
    return {
      id:'s'+(i+1), order:i, duration:s.d, status:s.st, name:s.n, sz:s.sz || '',
      cast: s.cast,   // undefined = 不是分镜（如角色图），[] = 空镜
      /* 分镜是**视频片段**，角色图才是**图片** —— 之前全按图片处理，
         连分辨率都显示成 SD 的 1024×1536（2026-11-03） */
      media: kind === 'character' ? 'img' : 'vid',
      thumbUrl: 'assets/thumbs/' + thumbSet + '-'
        + String((i % THUMB_N[thumbSet]) + 1).padStart(2,'0') + '.svg',
      cls:i%6,
      x: pos.x,
      y: pos.y,
      w: pos.w, h: pos.h
    };
  });
  DOC.items = base;
  DOC.kind = kind;   // 记住这批是角色图还是分镜，顶栏统计按它换词
  selId = null;
  emptyEl.classList.add('hidden');
  buildGraph(false);   // 数据变了，连线图重建（丢掉旧的拖动位置和手连的线）
  closeParams();

  const N = total;   // 实际生成的数量
  const openings = {
    script:`收到。我把这段故事拆成了 <b>${N} 个分镜</b>，景别从远景到特写都配上了。标题是这一镜讲什么，景别在卡片左下角。要调整顺序直接拖卡片。`,
    promo:`按宣传片的思路拆了 <b>${N} 个镜头</b>。这类片子<b>没有角色属性</b> —— 卡片上只有景别，不标人，也不留空位。`,
    character:`按你这份设定出了 <b>${N} 张角色图</b>。正面两张先挑一张定妆，其余角度留给后续镜头当参考 —— 哪张不对单独重跑，别整批重来。`,
    upload:`收到参考图。我把它放在了 <b>素材墙</b>里，可以点开放大改。要拆成镜头序列也可以。`,
    tpl:`用了「短剧分镜」模板：<b>${N} 个镜头</b>，其中 ${Math.max(0,N-3)} 个已生成、1 个生成中、1 个失败、1 个待生成。`,
    talk:`好，我按你说的做了。总共 <b>${N} 个镜头</b>，先看看镜头墙的节奏对不对。`
  };
  if (quiet){
    /* 默认示例：把「画布还是空的」换成示例说明，别让右边和左边自相矛盾 */
    const w = document.getElementById('welcome');
    if (w) w.innerHTML = '已载入一份<b>示例分镜</b>：秋天颐和园 · 小林 · 12 镜。'
      + '左边是节点和连线，点节点改参数，拖空白处平移。<br><br>'
      + '想看从零开始的样子：回启动页点<b>空白画布</b>（?empty=1）。';
    return;
  }
  // 搜索流程里由 runSearchDemo 自己汇报，不要这里再插一条
  if (!window.__suppressDemoMsg) agAdd('ai', openings[kind] || '好的。');

  // 参数不同的场景切到合适模式
  setMode(kind==='upload' ? 'free' : 'shots');
  const unit = kind === 'upload' ? '个对象' : (kind === 'character' ? '张角色图' : '个镜头');
  toast(`已生成 ${N} ${unit}`);
  /* 版本记录（34-versions.js）：生成完成自动存一版 */
  if (typeof autoVersion === 'function') autoVersion('生成 ' + N + ' ' + unit);
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
    /* 分镜是视频，角色图是图片 —— 时长/分辨率/播放标识都跟着变（2026-11-03） */
    const isVid = s.media !== 'img';
    const res = s.wsSim ? '模拟'
      : s.canvas ? (s.canvas.width + '×' + s.canvas.height)
      : s.status === 'ok' ? (isVid ? '1080×1920' : '1024×1536')
      : s.status === 'err' ? '403'
      : s.status === 'run' ? '生成中' : '—';
    const durTx = isVid && s.duration > 0
      ? '<svg class="ic sm playtri" viewBox="0 0 24 24"><path d="M7 4l12 8-12 8z"/></svg>'
        + s.duration.toFixed(1) + 's'
      : (isVid ? '—' : '图片');

    el.innerHTML = `<div class="im${s.thumbUrl?' has-img':''}" style="${
        s.thumbUrl
          ? `background-image:url('${s.thumbUrl}');background-size:cover;background-position:center`
          : `background:${BG[s.cls]}`
      }">
        ${s.thumbUrl ? '' : '<div class="glow"></div><div class="fig"></div>'}`
      + (s.status==='err' ? '<div class="errbadge">生成失败 · 403</div>' : '')
      + (s.status==='todo' ? '<div class="todobadge">'
          + '<svg class="ic" viewBox="0 0 24 24" style="color:var(--tx3)"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/></svg>待生成</div>' : '')
      + `<span class="no">${String(i+1).padStart(2,'0')}</span>`
      + `<span class="stt ${s.status}"></span>`
      + (s.sz ? `<span class="sz">${esc(s.sz)}</span>` : '')
      /* 这一镜画面里有谁。空数组显式标「空镜」——
         不标就分不清「确实没人」和「忘了填」（2026-11-03，照 Storyboard 的做法） */
      + (Array.isArray(s.cast)
          ? (s.cast.length
              ? `<span class="cast">${s.cast.map(c => esc(c)).join(' · ')}</span>`
              : `<span class="cast empty">空镜</span>`)
          : '')
      + `</div>`
      + `<div class="info"><div class="nm">${s.name}</div><div class="ln">`
      + `<span class="dur${isVid ? ' vid' : ''}">${durTx}</span>`
      + `<span class="d">${res}</span>`
      /* 参考标记原来 absolute 在缩略图底部，整行盖住景别和角色角标 ——
         角标看不见、点角标还会误开到参考弹层。挪到 info 区（2026-11-03） */
      + (typeof wsRefChipsHtml === 'function' ? wsRefChipsHtml(s.id) : '')
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
    <div style="font-size:var(--fz);color:var(--tx3);margin-top:6px;line-height:1.6">
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
  // 角色图批次没有时长，别硬写「总时长 00:00」，也别留着视频时间轴（2026-11-01 修）
  const isChar = DOC.kind === 'character';
  // 景别分布比总时长有用 —— 摄影师第一眼看的是「景别够不够变化」（2026-11-02）
  const szCount = {};
  items.forEach(s => { if (s.sz) szCount[s.sz] = (szCount[s.sz] || 0) + 1; });
  const szText = Object.keys(szCount).length
    ? ' · 景别 ' + Object.keys(szCount).map(k => k + ' ' + szCount[k]).join(' / ')
    : '';
  document.getElementById('metaBar').textContent =
    (isChar
      ? `${items.length} 张角色图 · 按角度出 · `
      : `${items.length} 个镜头 · 总时长 ${fmt(items.reduce((a,s)=>a+(s.duration||0),0))}${szText} · `)
    + `${c('ok')} 已生成 / ${c('run')} 生成中 / ${c('err')} 失败 / ${c('todo')} 待生成`;

  // 标题与底部时间轴跟着换：角色图不是视频，不该有播放器和轨道
  const ttl = document.querySelector('#vShots .ttl');
  if (ttl) ttl.textContent = isChar ? '角色图' : '镜头墙';
  const tl = document.querySelector('#vShots .tl');
  if (tl) tl.style.display = isChar ? 'none' : '';
}
function fmt(sec){ const m=Math.floor(sec/60), s=Math.round(sec%60);
  return String(m).padStart(2,'0')+':'+String(s).padStart(2,'0'); }
function addShot(){
  const maxOrder = DOC.items.reduce((a,s)=>Math.max(a,s.order),-1);
  DOC.items.push({id:'n'+Date.now(), order:maxOrder+1, duration:0, status:'todo',
    name:'未命名的分镜', sz:'中景', cast:[], media:'vid',
    cls:DOC.items.length%6, x:30, y:30, w:176, h:244});
  emptyEl.classList.add('hidden');
  renderShots();
  toast('已加一镜 · 先填标题和景别');
  grid.scrollTop = grid.scrollHeight;
}

/* ================= 素材墙渲染 ================= */
function renderFree(){
  freecv.querySelectorAll('.item').forEach(e=>e.remove());
  DOC.items.forEach(s=>{
    const el=document.createElement('div');
    el.className='item'+(s.id===selId?' sel':'');
    el.dataset.id=s.id;
    el.style.cssText=`left:${s.x}px;top:${s.y}px;width:${s.w}px;height:${s.h}px`;
    el.innerHTML=`<div class="im${s.thumbUrl?' has-img':''}" style="${
        s.thumbUrl
          ? `background-image:url('${s.thumbUrl}');background-size:cover;background-position:center`
          : `background:${BG[s.cls]}`
      }">${s.thumbUrl ? '' : '<div class="glow"></div><div class="fig"></div>'}`
      /* 素材墙的卡片也要带属性，不能只有一张图 + 名字（2026-11-03） */
      + (s.sz ? `<span class="sz">${esc(s.sz)}</span>` : '')
      + (Array.isArray(s.cast)
          ? (s.cast.length
              ? `<span class="cast">${s.cast.map(c => esc(c)).join(' · ')}</span>`
              : `<span class="cast empty">空镜</span>`)
          : '')
      + `</div>`
      + `<div class="lbl2">${s.name}</div>`;
    bindFree(el,s);
    freecv.appendChild(el);
  });
  /* 🔧 2026-10-20：重建后要把图层效果重新套上，否则一渲染就丢
     （之前 applyLayers 只认 .shot，素材墙这边压根没套过） */
  if (typeof applyAllLayers === 'function') { try { applyAllLayers(); } catch(_){} }
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
    /* 🔧 2026-10-20：有缩放时，屏幕位移要除以 zoom 才是画布坐标位移 */
    const z = (typeof CV_ZOOM === 'number' && CV_ZOOM > 0) ? CV_ZOOM : 1;
    const dx=(e.clientX-sx)/z, dy=(e.clientY-sy)/z;
    if(Math.abs(dx)>3||Math.abs(dy)>3) moved=true;
    s.x=Math.round(Math.max(-20,Math.min(freecv.clientWidth-s.w+20,ox+dx)));
    s.y=Math.round(Math.max(-20,Math.min(freecv.clientHeight-s.h+30,oy+dy)));
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

/* 画布（原「高级」）子视图切换 · 默认连线图 —— 节点图才是画布本体（2026-11-03） */
let flowView = 'graph';
function setFlowView(v){
  flowView = v;
  /* 切到「步骤」时节点已隐藏，浮层不能留在屏幕上（2026-11-08） */
  if (v!=='graph' && typeof clearEdgeFocus === 'function') clearEdgeFocus();
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

const KIND_COLOR = { text:'#60a5fa', image:'#22d3ee', video:'#a78bfa', audio:'#f472b6', model:'#fbbf24', any:'#71717a' };
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
    /* 列距 176（原来 164）：列间留白，卡片不贴脸。
       这个间距是 11-07 为避障通道调的；避障已撤，布局沿用不改（不动数据）。*/
    const col=i%3, row=Math.floor(i/3);
    nodes.push({
      id:'g'+i, x:372+col*176, y:16+row*224, w:150,
      t:String(i+1).padStart(2,'0')+' '+items[i].name,
      /* 底部信息行放真数据（时长 · 分辨率），不放「已生成」——
         状态已经由标题行的点和连线颜色表达，这行字要给尺寸这种数，
         参考图的节点底部就是 1024×576（2026-11-03）。分镜是视频 → 1080×1920 */
      sub: items[i].status==='err' ? '失败 · 403'
        : (items[i].duration>0 ? items[i].duration.toFixed(1)+'s' : '—') + ' · 1080×1920',
      kind:'image', st:items[i].status, ins:['text','image'], outs:['image'], shot:i,
      /* 节点带缩略图 —— 参考图和即梦都是大图卡片，图占主体（2026-11-03 放大）。
         高度固定 208（竖版 9:16），和 CSS .gnode.hasimg 一致，否则连线端口会错位。
         缩略图信息直接存进节点数据：渲染节点的函数拿不到 items。 */
      hasimg:true, h:208,
      thumb: items[i].thumbUrl || '', shotCls: items[i].cls, shotSz: items[i].sz || '',
      cap:'image-gen'
    });
  }
  /* 收尾节点错落成两列四行（原来 2×2 挤在同一行）：
     往下错开后汇流线不会全挤在同一行端口上。同为 11-07 避障方案调的布局，
     避障已撤但布局沿用不改。*/
  const rows=Math.ceil(N/3), yb=16+rows*224+18;
  nodes.push({id:'merge', x:372, y:yb, w:140, t:'合成时间线', kind:'video',
    sub:'总时长 '+fmt(items.reduce((a,s)=>a+(s.duration||0),0)), st:'ok', ins:['image'], outs:['video'],
    cap:'clip'});
  nodes.push({id:'out',   x:548, y:yb+78, w:140, t:'出片', kind:'video',
    sub:'未开始', st:'todo', ins:['video'], outs:[],
    cap:'clip-render'});
  // 🔴 3D 分支：图生3D（原子）→ 3D 导演台（复合）
  nodes.push({id:'to3d',   x:372, y:yb+156, w:140, t:'图生 3D', kind:'model',
    sub:'TripoSR → glb', st:'ok', ins:['image'], outs:['model'], atomic:true,
    cap:'model-3d'});
  nodes.push({id:'previs', x:548, y:yb+234, w:140, t:'3D 导演台', kind:'video', comp:1,
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

/* --------- 连线：单段平滑贝塞尔（2026-11-07 对齐即梦） ---------
   即梦 / React Flow / ComfyUI 都是「端口水平出入的一根 S 曲线」：不绕路、不避障，
   穿过别的卡片时线在节点下层，被卡片自然盖住就够了。
   上一版为了把「穿卡数」压到 0 枚举走廊候选，线绕到图底反而难看 ——
   用户 11-07 拿即梦截图明确否掉，整套采样避障（bezPt / arcSeg / sampleSegs /
   pathHits / pathLen / segsToPath / 走廊策略）一并删除，别再捡回来。 */
function routeEdge(e,pos,y1,y2){
  const a=pos[e.f], b=pos[e.t];
  if(!a||!b) return '';
  const x1=a.x+a.w, x2=b.x;
  const span=Math.abs(x2-x1);
  /* 控制点只沿 x 偏 → 端口水平出入；跨度越大弯得越开，短边不回勾。
     回环边（x2<x1）自然形成 U 形，跟主流节点编辑器一致。 */
  const s=Math.min(170,Math.max(20,span*.5),Math.max(16,span*.48));
  const f=n=>Math.round(n*10)/10;
  return `M ${f(x1)} ${f(y1)} C ${f(x1+s)} ${f(y1)}, ${f(x2-s)} ${f(y2)}, ${f(x2)} ${f(y2)}`;
}
function buildEdgesSvg(){
  const svg=document.getElementById('gedges');
  if(!svg) return;
  const pos={}; GRAPH.nodes.forEach(n=>pos[n.id]=n);
  /* 端口基准统一用节点真实高度（大图卡 208、普通 54），
     renderGraph 和 redrawEdges 以前各算各的，拖动时会跳 3px。 */
  const portY=(n,idx,total)=>n.y+(n.h||54)/2+(idx-(total-1)/2)*15;
  /* 平时所有线统一灰色、不分状态色（对齐即梦）：状态由节点标题的小圆点和
     卡片上的「失败 · 403」表达；点节点才由 focusEdges 点亮直连的线。 */
  svg.innerHTML=GRAPH.edges.map((e,i)=>{
    const a=pos[e.f], b=pos[e.t]; if(!a||!b) return '';
    const yi=(a.outs||[]).indexOf(e.fp), yo=(b.ins||[]).indexOf(e.tp);
    const y1=portY(a,yi<0?0:yi,Math.max((a.outs||[]).length,1))-8;
    const y2=portY(b,yo<0?0:yo,Math.max((b.ins||[]).length,1))-8;
    return `<path class="gedge" data-ei="${i}" style="pointer-events:stroke;cursor:pointer" d="${routeEdge(e,pos,y1,y2)}"/>`;
  }).join('');
  /* 重画后把选中聚焦补回来（拖动 / 切视图 / 断线都会走这里），
     否则高亮会在第一次 redrawEdges 时消失。 */
  focusEdges(gSel);
}

/* --------- 选中节点 → 点亮相连连线（2026-11-07 对齐即梦） ---------
   即梦是「平时全灰，点了卡片才把与它直连的线点亮」，其余线仍是灰的、
   不额外压暗。这里只切 .hi，不重建路径 —— 拖节点时每帧调用也不会卡。 */
let GHINT_BASE = '';
function setFocusHint(html){
  const h = document.querySelector('#flowGraphView .ghint');
  if (!h) return;
  if (!GHINT_BASE) GHINT_BASE = h.innerHTML;
  const out = html || GHINT_BASE;
  if (h.innerHTML !== out) h.innerHTML = out;
  h.classList.toggle('focused', !!html);
}
function focusEdges(sel){
  const svg = document.getElementById('gedges');
  if (!svg) return 0;
  const ids = sel instanceof Set ? sel
            : Array.isArray(sel) ? new Set(sel)
            : new Set(sel ? [sel] : []);
  const edges = (typeof GRAPH !== 'undefined' && GRAPH.edges) || [];
  const nodes = (typeof GRAPH !== 'undefined' && GRAPH.nodes) || [];
  const near = new Set();
  let hit = 0;
  svg.querySelectorAll('.gedge[data-ei]').forEach(p=>{
    const e = edges[+p.dataset.ei];
    const rel = ids.size > 0 && !!e && (ids.has(e.f) || ids.has(e.t));
    p.classList.toggle('hi', rel);
    if (rel){ hit++; near.add(e.f); near.add(e.t); }
  });
  svg.classList.toggle('focused', ids.size > 0 && hit > 0);
  const nbox = document.getElementById('gnodes');
  if (nbox) nbox.querySelectorAll('.gnode').forEach(el=>{
    el.classList.toggle('rel', ids.size > 0 && near.has(el.dataset.id) && !ids.has(el.dataset.id));
  });
  if (hit){
    const one = ids.size === 1 ? [...ids][0] : '';
    const node = nodes.find(n=>n.id===one);
    const label = ids.size === 1 ? (node ? node.t : one) : ids.size+' 个节点';
    const safe = typeof esc === 'function' ? esc(String(label))
      : String(label).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
    setFocusHint(`已点亮与「${safe}」相连的 <b>${hit}</b> 条连线 · 点空白 / Esc 取消`);
  } else if (ids.size){
    setFocusHint(`选中的节点还没有连线 · 拖右侧圆点连一条`);
  } else {
    setFocusHint('');
  }
  return hit;
}
function clearEdgeFocus(){
  gSel = null;
  focusEdges(null);
  document.querySelectorAll('#gnodes .gnode').forEach(el=>el.classList.remove('sel','multi','rel'));
  if (typeof gMulti !== 'undefined' && gMulti.size) gMulti.clear();
  if (typeof renderGroupBar === 'function') renderGroupBar();
  if (typeof closeNodeWb === 'function') closeNodeWb();
  else if (typeof closeParams === 'function') closeParams();
  setFocusHint('');
}

/* --------- 渲染 --------- */
function renderGraph(){
  if (!GRAPH.nodes.length) buildGraph(false);
  const ginner = document.getElementById('ginner');
  const svg    = document.getElementById('gedges');
  const nbox   = document.getElementById('gnodes');

  /* 无限画布（2026-11-03）：右下留足余量，别让节点一摆就贴边；
     真实拖拽时 02-canvas 的节点拖拽还会实时撑大。 */
  const maxY = Math.max(...GRAPH.nodes.map(n=>n.y + (n.h||54))) + 260;
  const maxX = Math.max(...GRAPH.nodes.map(n=>n.x+n.w)) + 260;
  ginner.style.height = Math.max(maxY, 420)+'px';
  ginner.style.width  = Math.max(maxX, 700)+'px';
  svg.setAttribute('viewBox', `0 0 ${Math.max(maxX,700)} ${Math.max(maxY,420)}`);

  /* 连线统一交给 buildEdgesSvg（单段平滑贝塞尔），两处绘制不再各写一份 */
  buildEdgesSvg();

  // 节点
  nbox.innerHTML = GRAPH.nodes.map(n=>{
    const dot = n.st==='ok'?'var(--ok)':n.st==='run'?'var(--ac)':n.st==='err'?'var(--dg)':'var(--tx3)';
    const ins = (n.ins||[]).map((k,i)=>`<span class="gport i" data-node="${n.id}" data-kind="${k}" data-dir="in"
        style="border-color:${KIND_COLOR[k]||KIND_COLOR.any};top:${(n.h||54)/2+(i-(n.ins.length-1)/2)*15}px"></span>`).join('');
    const outs = (n.outs||[]).map((k,i)=>`<span class="gport o" data-node="${n.id}" data-kind="${k}" data-dir="out"
        style="border-color:${KIND_COLOR[k]||KIND_COLOR.any};top:${(n.h||54)/2+(i-(n.outs.length-1)/2)*15}px"></span>`).join('');
    const shot = n.hasimg ? n : null;
    const imgStyle = shot
      ? (shot.thumb
          ? `background-image:url('${shot.thumb}');background-size:cover;background-position:center`
          : `background:${BG[shot.shotCls] || BG[0]}`)
      : '';
    return `<div class="gnode${gSel===n.id?' sel':''}${n.comp?' comp':''}${n.userGroup?' usergrp':''}${gMulti.has(n.id)?' multi':''}${n.hasimg?' hasimg':''}" data-id="${n.id}"
        style="left:${n.x}px;top:${n.y}px;width:${n.w}px">
      ${ins}
      <div class="ghd"><span class="gt">${n.t}</span><span class="gd" style="background:${dot}"></span></div>
      ${shot ? `<div class="gimg" style="${imgStyle}">`
        + (shot.shotSz ? `<span class="sz">${esc(shot.shotSz)}</span>` : '')
        /* 卡片瘦身（2026-11-08 两级结构）：时长 / 分辨率收进图内角标，
           不再占卡片底部一整行；运行按钮移到点节点后的上方工具条。 */
        + `<span class="gmeta${n.st==='err'?' err':''}">${esc(n.sub)}</span>`
        + `</div>` : `<div class="gbd">${n.sub}</div>`}
      ${outs}
    </div>`;
  }).join('');

  // 临时连线
  const ghost = document.getElementById('gghost');
  if (gLink && ghost){
    const a = GRAPH.nodes.find(n=>n.id===gLink.from);
    if (a){
      const x1 = a.x + a.w, y1 = a.y + 8;
      ghost.innerHTML = `<path class="gedge ghost" d="M ${x1} ${y1} L ${gLink.x1} ${gLink.y1}"/>`;
    }
  } else if (ghost) ghost.innerHTML='';

  /* 上面 buildEdgesSvg 已给「连线」补过高亮，但它跑在 nbox.innerHTML 之前，
     节点 DOM 重建会把 .rel（相连节点的浅色边框）冲掉 —— 这里补一次。 */
  focusEdges(gSel);
  bindGraph();
  /* 小地图跟着节点增删/拖动重画（33-gmap.js， BeefTV 欠账 #1） */
  if (typeof updateGmap === 'function') updateGmap();
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
        /* 多选是「一组节点」的操作，不该留着单节点的工作台浮层 */
        if (typeof closeNodeWb === 'function') closeNodeWb();
        focusEdges(gMulti);            // 多选：所有选中节点的相连线一起亮
        return;
      }
      gSel = id;
      gDrag = { id, sx:e.clientX, sy:e.clientY, ox:n.x, oy:n.y, moved:false };
      el.setPointerCapture(e.pointerId);
      // 只改选中态，绝不 renderGraph（否则正在拖的节点被重建，拖不动）
      document.querySelectorAll('.gnode').forEach(x=>x.classList.toggle('sel', x.dataset.id===id));
      focusEdges(id);                // 相连的连线亮起来（只切 class，不重画路径）
      /* 两级信息结构（2026-11-08）：选中不再默认弹右侧 10 行参数表，
         改为在节点上方浮工具条、下方浮对话框；完整参数降为二级入口。 */
      if (typeof openNodeWb === 'function') openNodeWb(id);
    });
    el.addEventListener('pointermove', e=>{
      if (!gDrag || gDrag.id !== el.dataset.id) return;
      const dx=e.clientX-gDrag.sx, dy=e.clientY-gDrag.sy;
      if (Math.abs(dx)>3||Math.abs(dy)>3) gDrag.moved=true;
      const n = GRAPH.nodes.find(x=>x.id===gDrag.id);
      /* 无限画布（2026-11-03）：不再钉在原点。
         往左上拖出界时把整张图整体平移（世界坐标重锚），同时补滚动量保持视觉不动；
         往右下拖时实时把内容区撑大 —— 拖多远画布就有多远。 */
      n.x = gDrag.ox+dx; n.y = gDrag.oy+dy;
      const c = document.querySelector('#flowGraphView .gcanvas');
      const g = document.getElementById('ginner');
      if (c && g && (n.x < 0 || n.y < 0)){
        const ox2 = n.x < 0 ? (-n.x + 80) : 0;
        const oy2 = n.y < 0 ? (-n.y + 80) : 0;
        GRAPH.nodes.forEach(m => { m.x += ox2; m.y += oy2; });
        c.scrollLeft += ox2 * CV_ZOOM;
        c.scrollTop  += oy2 * CV_ZOOM;
        gDrag.ox += ox2; gDrag.oy += oy2;
      }
      if (c && g){
        if (n.x + n.w + 160 > g.offsetWidth)  g.style.width  = (n.x + n.w + 160) + 'px';
        if (n.y + (n.h||54) + 160 > g.offsetHeight) g.style.height = (n.y + (n.h||54) + 160) + 'px';
      }
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

  /* 运行单节点（2026-11-08 两级结构）：卡片上不再常驻 .grun 按钮，
     入口迁到 36-nodeworkbench.js 上方工具条的「运行」；runNode() 与门禁链路不变。 */
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
  /* 拖动节点时实时重算正交路由（原来这里用的是另一套 portY 基准，会跳 3px） */
  buildEdgesSvg();
}

/* --------- 从节点库加节点（P4：加新用途=加配置） --------- */
const LIB_DEFS = {
  'text':      {t:'文本',            kind:'text',  ins:[],                outs:['text'],  atomic:1, data:1},
  'prompt':    {t:'提示词',          kind:'text',  ins:['text'],          outs:['text'],  atomic:1, data:1},
  'image':     {t:'AI 生图',         kind:'image', ins:['text','image'],  outs:['image'], atomic:1, cap:'image-gen'},
  'video':     {t:'图生视频',         kind:'video', ins:['image','text'],  outs:['video'], atomic:1, cap:'video-gen'},
  'bgm':       {t:'配乐混音',         kind:'audio', ins:['video'],         outs:['video'], atomic:1, cap:'bgm-mix'},
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
