/* 36-nodeworkbench.js — 节点级工作台：点节点后「上工具 + 下对话」（2026-11-08）
 *
 * 对齐即梦选中态（用户 11-08 纠正：第二张截图是画布点中节点之后，不是另一个页面）：
 *   常态   卡片极简：一张图 + 分镜标题 + 图上角标，不常驻参数表 / 运行按钮
 *   选中   工具条浮在节点上方、对话生成框浮在节点下方，节点本体留在中间
 *   二级   原来那张 10 行字段的 gparams 降级成「完整参数」入口，不再默认弹
 *   全局   右侧 420px 智能体栏默认收起，点竖条展开；它是全局对话，和节点级对话框两回事
 *
 * 加载顺序：本文件在 35 之后，运行时才被 02-canvas.js 的 bindGraph 调用，
 * 因此这里引用的 CAPS / capKeyOfNode / runNode / showNodeParams / agAdd 都已就绪。
 */

(function nodeWorkbench(){
  /* ---------- 工具条：按节点类型给一套，不是一张通用表单 ---------- */
  const ICON = {
    edit:'<path d="M4 20h4L20 8l-4-4L4 16z"/>',
    crop:'<path d="M4 9V4h5M20 15v5h-5M15 4h5v5M9 20H4v-5"/>',
    wand:'<path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
    layers:'<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    sun:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/>',
    play:'<path d="M5 3l14 9-14 9z"/>',
    cube:'<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>',
    text:'<path d="M4 6h16M4 12h10M4 18h7"/>',
    compare:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16M7 9l-2 3 2 3M17 9l2 3-2 3"/>',
    more:'<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>'
  };
  const T = (n,i,d)=>({n:n,i:i,d:d});
  const TOOLSETS = {
    image:[T('智能改图','edit','就地改这张图'), T('扩图','crop','把画幅往外扩'),
           T('局部重绘','wand','圈一块重画'), T('多角度','layers','换机位出几张'),
           T('打光','sun','重打光线'), T('超清','more','放大到印刷尺寸')],
    video:[T('图生视频','play','让这一镜动起来'), T('运镜','sun','推 / 拉 / 摇'),
           T('首尾帧','layers','定住起止画面'), T('时长','text','改这一镜几秒'),
           T('配音','wand','配一句台词')],
    model:[T('生成 3D','cube','出 glb'), T('换视角','layers','换观察角度'),
           T('预演','play','进 3D 导演台'), T('精度','sun','标准 / 高')],
    text: [T('拆镜','layers','拆成两镜'), T('改写','text','重写这段'),
           T('补一镜','wand','在中间加一镜'), T('台词','text','补对白')],
    other:[T('重跑','play','只跑这一个节点'), T('参数','edit','看它背后那份能力')]
  };
  const MODELS = ['GPT Image 2','即梦 3.0','Flux Pro','本地 SDXL'];
  const RATIOS = ['2:3','1:1','3:4','16:9'];

  let wbId = null, wbEl = null, wbTools = null, wbChat = null, raf = 0, lastPos = '';
  let modelIdx = 0, ratioIdx = 0;

  function escTxt(s){
    return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }
  function node(){ return (typeof GRAPH!=='undefined' && GRAPH.nodes || []).find(n=>n.id===wbId) || null; }
  function svg(path){ return `<svg class="ic sm" viewBox="0 0 24 24">${path}</svg>`; }
  function clamp(v,a,b){ return b<a ? a : Math.max(a,Math.min(v,b)); }

  function ensure(){
    if (wbEl) return;
    wbEl = document.createElement('div');
    wbEl.id = 'nodeWb';
    wbEl.className = 'nwb';
    wbEl.hidden = true;
    wbEl.innerHTML = '<div class="nwb-tools" id="nwbTools"></div>'
                   + '<div class="nwb-chat" id="nwbChat"></div>';
    document.body.appendChild(wbEl);
    wbTools = document.getElementById('nwbTools');
    wbChat  = document.getElementById('nwbChat');

    /* 事件委托绑容器：定位时只改 style，绝不重建 DOM（中文输入法不能丢 textarea） */
    wbEl.addEventListener('click', e=>{
      const el = e.target.closest('[data-wb]');
      if (!el || !wbEl.contains(el)) return;
      wbAct(el.dataset.wb, el);
    });
    wbChat.addEventListener('keydown', e=>{
      if (e.target.id === 'nwbTa' && e.key === 'Enter' && !e.shiftKey && !e.isComposing){
        e.preventDefault(); wbSend();
      }
    });
  }

  function setKey(n){
    if (n.kind === 'model') return 'model';
    if (n.kind === 'video') return 'video';
    if (n.kind === 'text' || n.data) return 'text';
    if (n.kind === 'image' || n.hasimg) return 'image';
    return 'other';
  }

  function openNodeWb(id){
    if (typeof flowView === 'undefined' || flowView !== 'graph' || mode !== 'flow') return;
    const n = (GRAPH.nodes||[]).find(x=>x.id===id);
    if (!n) return;
    ensure();
    wbId = id;
    const canRun = typeof capKeyOfNode === 'function' && capKeyOfNode(n);
    const tools = TOOLSETS[setKey(n)].map(t=>
      `<button class="nwb-tb" data-wb="tool" data-label="${escTxt(t.n)}" title="${escTxt(t.d)}">`
      + svg(ICON[t.i]||ICON.more) + escTxt(t.n) + '</button>').join('');
    wbTools.innerHTML = tools
      + (setKey(n)==='image'
          ? `<button class="nwb-tb" data-wb="compare" title="原图 / 生成图对比 · 拖动分割或并排">${svg(ICON.compare)}对比</button>`
          : '')
      + '<span class="nwb-sep"></span>'
      + `<button class="nwb-tb" data-wb="params" title="完整参数（二级入口，原来默认弹的那张表）">${svg(ICON.edit)}完整参数</button>`
      + (canRun ? `<button class="nwb-tb run" data-wb="run" title="运行这个节点（会先过门禁）">${svg(ICON.play)}运行</button>` : '')
      + '<button class="nwb-tb close" data-wb="close" title="关闭（点空白 / Esc 同效）">✕</button>';

    const label = escTxt(n.t);
    wbChat.innerHTML =
      `<div class="nwb-hd"><span class="t">对 <b>${label}</b> 说</span><span class="sp"></span>`
      + `<span class="cost">⚡14 / 次</span></div>`
      + `<div class="nwb-chips">
           <button class="nwb-chip" data-wb="chip">相机 <span class="cv">▾</span></button>
           <button class="nwb-chip" data-wb="chip">配色 <span class="cv">▾</span></button>
           <button class="nwb-chip" data-wb="chip">风格 <span class="cv">▾</span></button>
           <button class="nwb-chip" data-wb="chip">景别 <span class="cv">▾</span></button>
           <span class="nwb-sep"></span>
           <button class="nwb-chip" data-wb="ref">@ 引用</button>
         </div>`
      + `<textarea id="nwbTa" rows="2" placeholder="说一句想怎么改这一镜，例如：把光调成逆光，人物居中…"></textarea>`
      + `<div class="nwb-foot">
           <button class="nwb-op" data-wb="model" id="nwbModel">${MODELS[modelIdx]} ▾</button>
           <button class="nwb-op" data-wb="ratio" id="nwbRatio">${RATIOS[ratioIdx]} ▾</button>
           <span class="sp"></span>
           <button class="nwb-send" data-wb="send">发送 ↑</button>
         </div>`
      + `<div class="nwb-log" id="nwbLog"></div>`;

    /* 二级化：选中节点不再默认弹 gparams，只有点「完整参数」才开 */
    if (typeof closeParams === 'function') closeParams();
    wbEl.hidden = false;
    wbEl.style.visibility = 'visible';
    lastPos = '';
    positionNodeWb();
    if (!raf) raf = requestAnimationFrame(tick);
  }

  function closeNodeWb(){
    wbId = null;
    if (wbEl){ wbEl.hidden = true; wbEl.style.visibility = 'hidden'; }
    if (raf){ cancelAnimationFrame(raf); raf = 0; }
    if (typeof closeParams === 'function') closeParams();
  }

  /* 屏幕坐标跟随：节点在 .ginner 里会被 scale + scroll，逐帧量 rect 最省心。
     只在坐标真的变了才写 style，避免每帧触发布局。 */
  function positionNodeWb(){
    if (!wbEl || wbEl.hidden || !wbId) return;
    const el = document.querySelector('#gnodes .gnode[data-id="' + wbId + '"]');
    const canvas = document.querySelector('#flowGraphView .gcanvas');
    if (!el || !canvas) return;
    const r = el.getBoundingClientRect(), c = canvas.getBoundingClientRect();
    if (!r.width || !c.width) return;

    const leftLimit = c.left + 8, rightLimit = c.right - 8;
    const topLimit = c.top + 8, bottomLimit = c.bottom - 8;
    const offscreen = r.bottom < c.top || r.top > c.bottom || r.right < c.left || r.left > c.right;
    wbEl.style.visibility = offscreen ? 'hidden' : 'visible';
    if (offscreen) return;

    const tw = wbTools.offsetWidth, th = wbTools.offsetHeight;
    const cw = wbChat.offsetWidth,  ch = wbChat.offsetHeight;
    const cx = (Math.max(r.left,c.left) + Math.min(r.right,c.right)) / 2;
    const tl = clamp(cx - tw/2, leftLimit, Math.max(leftLimit, rightLimit - tw));
    let   tt = r.top - th - 10;
    if (tt < topLimit) tt = r.top + 6;                 // 顶部不够就贴卡片上沿
    tt = clamp(tt, topLimit, Math.max(topLimit, bottomLimit - th));
    const cl = clamp(cx - cw/2, leftLimit, Math.max(leftLimit, rightLimit - cw));
    let   ct = r.bottom + 10;
    if (ct + ch > bottomLimit) ct = r.bottom - ch - 10;  // 底部不够就贴卡片下沿
    ct = clamp(ct, topLimit, Math.max(topLimit, bottomLimit - ch));

    const key = [tl,tt,cl,ct].map(v=>Math.round(v)).join(',');
    if (key === lastPos) return;
    lastPos = key;
    wbTools.style.left = tl+'px'; wbTools.style.top = tt+'px';
    wbChat.style.left  = cl+'px'; wbChat.style.top  = ct+'px';
  }

  function tick(){
    if (!wbEl || wbEl.hidden){ raf = 0; return; }
    positionNodeWb();
    raf = requestAnimationFrame(tick);
  }

  function wbAct(act, el){
    const n = node();
    if (act === 'close'){ if (typeof clearEdgeFocus === 'function') clearEdgeFocus(); return; }
    if (act === 'params'){
      if (typeof showNodeParams === 'function') showNodeParams(wbId);
      toast('完整参数 · 二级入口，不再默认弹');
      return;
    }
    if (act === 'run'){
      if (typeof runNode === 'function') runNode(wbId);
      return;
    }
    if (act === 'compare'){
      /* 原图 / 生成图对比：从节点工具条进日常路径，不再只藏在精调深层面板 */
      if (typeof openCompare === 'function') openCompare(wbId);
      return;
    }
    if (act === 'tool'){
      wbTools.querySelectorAll('.nwb-tb[data-wb="tool"]').forEach(b=>b.classList.toggle('on', b===el));
      toast('「' + (el.dataset.label||'工具') + '」· 就地作用于「' + (n?n.t:wbId) + '」');
      return;
    }
    if (act === 'chip'){ el.classList.toggle('on'); toast(el.textContent.trim() + ' · 参数 chip'); return; }
    if (act === 'ref'){ toast('@ 引用角色 / 素材 · 原型不接上传'); return; }
    if (act === 'model'){
      modelIdx = (modelIdx+1) % MODELS.length;
      el.innerHTML = MODELS[modelIdx] + ' ▾';
      toast('模型换成 ' + MODELS[modelIdx]);
      return;
    }
    if (act === 'ratio'){
      ratioIdx = (ratioIdx+1) % RATIOS.length;
      el.innerHTML = RATIOS[ratioIdx] + ' ▾';
      toast('画面比例换成 ' + RATIOS[ratioIdx]);
      return;
    }
    if (act === 'send'){ wbSend(); return; }
  }

  function wbSend(){
    const ta = document.getElementById('nwbTa');
    if (!ta) return;
    const t = ta.value.trim();
    if (!t){ toast('先说一句想怎么改'); ta.focus(); return; }
    const n = node();
    const name = n ? n.t : wbId;
    ta.value = '';
    const log = document.getElementById('nwbLog');
    if (log) log.textContent = '已提交给「' + name + '」· 排队中（原型不真跑模型）';
    toast('已提交 · 生成结果会落回这个节点');
    /* 节点级对话也留一份到全局智能体，展开右侧栏能接着看，功能不丢 */
    if (typeof agAdd === 'function'){
      agAdd('me', escTxt(t));
      setTimeout(()=>{
        agAdd('ai', '收到，这句是对「<b>' + escTxt(name) + '</b>」说的：' + escTxt(t)
          + '<br><br><span class="myown">原型只演示「点节点 → 就地对话」这条入口，'
          + '真生成要走节点背后那份 CAPS 能力并先过门禁。</span>');
      }, 420);
    }
  }

  /* ---------- 右侧全局智能体栏：折叠 / 展开 ---------- */
  function toggleAg(open){
    const on = (open === undefined) ? !document.body.classList.contains('ag-open') : !!open;
    document.body.classList.toggle('ag-open', on);
    lastPos = '';
    positionNodeWb();
    if (typeof updateGmap === 'function') updateGmap();
  }

  /* 全局出口：02-canvas.js / 08-events.js / index.html 会调 */
  window.openNodeWb = openNodeWb;
  window.closeNodeWb = closeNodeWb;
  window.positionNodeWb = positionNodeWb;
  window.toggleAg = toggleAg;
  window.wbSend = wbSend;
})();
