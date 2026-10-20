/* 18-panels.js - split from canvas_unified_v14.html (lines 4280-0) */
/* ================= 图层面板 / 撤销历史 / 提示词库（三个位置先占上） =================
   原则：入口 + 数据结构 + 交互占住，具体实现后做。
*/

/* ---------- ① 图层模型（复用 _export 里的 makeLocalLayer / makeAiLayer）---------- */
let LAYER_PANEL_ON = false;
let ACTIVE_LAYER = null;

/* 每个镜头一套图层（演示用，存在内存） */
function layersOf(shotId){
  if (!SHOT_LAYERS[shotId]){
    SHOT_LAYERS[shotId] = [
      { id:'src', type:'source', name:'原图', visible:true, opacity:1,
        params:{ src:'asset_9f2a', w:1024, h:1536 }, cost:0 }
    ];
  }
  return SHOT_LAYERS[shotId];
}
const SHOT_LAYERS = {};

function toggleLayerPanel(){
  LAYER_PANEL_ON = !LAYER_PANEL_ON;
  renderLayerPanel();
}

function renderLayerPanel(){
  const host = document.getElementById('layerPanel');
  if (!host) return;
  if (!LAYER_PANEL_ON){ host.innerHTML = ''; host.classList.remove('on'); return; }
  host.classList.add('on');
  const shotId = selId || (DOC.items[0] && DOC.items[0].id);
  const layers = layersOf(shotId);
  ACTIVE_LAYER = ACTIVE_LAYER || (layers[layers.length-1] && layers[layers.length-1].id);

  host.innerHTML = `
    <div class="lp-hd">
      <span class="lp-t">图层</span>
      <span class="lp-n">${layers.length}</span>
      <button class="lp-x" onclick="toggleLayerPanel()">✕</button>
    </div>
    <div class="lp-body">
      ${layers.slice().reverse().map(l=>`
        <div class="lp-item ${l.type} ${ACTIVE_LAYER===l.id?'on':''}"
             onclick="ACTIVE_LAYER='${l.id}';renderLayerPanel()">
          <span class="lp-eye ${l.visible?'':''}"
            onclick="event.stopPropagation();toggleLayerVis('${l.id}')"
            title="${l.visible?'隐藏':'显示'}">${l.visible?'◉':'○'}</span>
          <span class="lp-name">${l.name}</span>
          <span class="lp-tag ${l.type}">${
            l.type==='source' ? '源' : l.type==='local' ? '本地' : '调模型'
          }</span>
          <span class="lp-cost ${l.type==='local'?'free':''}">${
            l.type==='source' ? '—' : l.cost ? '⚡'+l.cost : '免费'
          }</span>
          ${l.type==='source'?'':`<span class="lp-del" onclick="event.stopPropagation();deleteLayer('${l.id}')">✕</span>`}
        </div>
        ${ACTIVE_LAYER===l.id && l.type!=='source' ? `
          <div class="lp-op">
            <span class="lp-op-l">透明度</span>
            <input type="range" class="le-r" min="0" max="1" step="0.01" value="${l.opacity}"
              oninput="setLayerOpacity('${l.id}', this.value)">
            <span class="lp-op-v" id="lpOpv">${Math.round(l.opacity*100)}%</span>
          </div>
          <div class="lp-blend">
            <span class="lp-op-l">混合</span>
            <select class="lp-blend-sel" onchange="setLayerBlend('${l.id}', this.value)">
              ${BLEND_MODES.map(m=>`<option value="${m.k}" ${(l.blend||'normal')===m.k?'selected':''}>${m.n}</option>`).join('')}
            </select>
          </div>
          <div class="lp-blend-hint">${BLEND_MODES.find(m=>(l.blend||'normal')===m.k).d}</div>` : ''}
      `).join('')}
    </div>
    <div class="lp-add">
      <button class="lp-add-b" onclick="addLayer('local')">＋ 调整层</button>
      <button class="lp-add-b" onclick="addLayer('ai')">＋ AI 编辑</button>
    </div>
    <div class="lp-foot">
      点层看参数 · 关眼睛隐藏 · 拖透明度混 ｜ 全部非破坏
    </div>`;
}

function toggleLayerVis(id){
  const sid = selId || DOC.items[0].id;
  const layers = layersOf(sid);
  const l = layers.find(x=>x.id===id);
  if (l){
    l.visible = !l.visible;
    refreshLayers(sid);
    /* 🔧 2026-10-20 修：之前关眼睛不进历史，撤销退不回来 */
    pushHistory((l.visible ? '显示' : '隐藏') + '一层：' + l.name);
  }
}
function setLayerOpacity(id, v){
  const sid = selId || DOC.items[0].id;
  const layers = layersOf(sid);
  const l = layers.find(x=>x.id===id);
  if (l){ l.opacity = Number(v); applyLayers(sid); }
  const el = document.getElementById('lpOpv');
  if (el) el.textContent = Math.round(Number(v)*100) + '%';
  /* 拖动时不刷历史（太密），松手才记 —— 用节流 */
  if (typeof __opacityHistTimer !== 'undefined' && __opacityHistTimer) clearTimeout(__opacityHistTimer);
  window.__opacityHistTimer = setTimeout(()=>{
    if (l) pushHistory('透明度 ' + l.name + ' → ' + Math.round(Number(v)*100) + '%');
  }, 420);
}
function deleteLayer(id){
  const sid = selId || DOC.items[0].id;
  SHOT_LAYERS[sid] = layersOf(sid).filter(x=>x.id!==id);
  ACTIVE_LAYER = null;
  refreshLayers(sid);
  pushHistory('删掉一层');
  toast('已删除该层（原图不受影响）');
}
function addLayer(kind){
  const sid = selId || DOC.items[0].id;
  const layers = layersOf(sid);
  const l = kind === 'local' ? makeLocalLayer() : makeAiLayer('inpaint', {});
  l.name = kind === 'local' ? '调整层 ' + (layers.length) : '局部重绘';
  layers.push(l);
  ACTIVE_LAYER = l.id;
  refreshLayers(sid);
  pushHistory('加了一层：' + l.name);
  toast(kind === 'local' ? '加了调整层 · 免费' : '加了 AI 编辑层 · 要调模型');
}

/* ---------- ② 撤销 / 历史 ---------- */
let HISTORY = [];
let HIST_POS = -1;

function pushHistory(label){
  HISTORY = HISTORY.slice(0, HIST_POS + 1);
  /* 镜头整份进快照（不含像素对象），像素单独用引用存 —— 撤销导入/修饰才回得去 */
  const items = (typeof DOC !== 'undefined' ? DOC.items : []).map(x=>{
    const o = {};
    Object.keys(x).forEach(k=>{
      if (k === 'canvas' || k === 'thumbUrl') return;
      o[k] = x[k];
    });
    o._hasCanvas = !!x.canvas;
    return o;
  });
  const images = {};
  if (typeof DOC !== 'undefined'){
    DOC.items.forEach(x=>{ if (x.canvas) images[x.id] = x.canvas; });
  }
  HISTORY.push({
    label, at: new Date().toLocaleTimeString('zh-CN', { hour12:false }),
    snapshot: JSON.stringify({
      adj: LOCAL_ADJ,
      fixed: Array.from(FIXED),
      /* 🔴 图层也进快照 —— 之前漏了，所以撤销图层操作没效果 */
      layers: JSON.parse(JSON.stringify(SHOT_LAYERS)),
      /* 镜头整份进快照 */
      items
    }),
    /* canvas 不能被 JSON 序列化，用引用平行保存 */
    images
  });
  HIST_POS = HISTORY.length - 1;
  renderHistory();
}

function undo(){
  if (HIST_POS <= 0){ toast('已经到最早一步了'); return; }
  HIST_POS--;
  restoreHistory();
  toast('退回：' + HISTORY[HIST_POS].label);
}
function redo(){
  if (HIST_POS >= HISTORY.length - 1){ toast('已经是最新一步了'); return; }
  HIST_POS++;
  restoreHistory();
  toast('前进：' + HISTORY[HIST_POS].label);
}
function jumpHistory(i){
  HIST_POS = i;
  restoreHistory();
}
function restoreHistory(){
  const h = HISTORY[HIST_POS];
  if (h){
    try {
      const s = JSON.parse(h.snapshot);
      if (s.adj){
        Object.keys(s.adj).forEach(k=>{ LOCAL_ADJ[k] = s.adj[k]; });
      }
      FIXED = new Set(s.fixed || []);
      /* 🔴 恢复图层 —— 之前快照里没存图层，所以撤销图层操作没效果 */
      if (s.layers){
        Object.keys(SHOT_LAYERS).forEach(k=>{ delete SHOT_LAYERS[k]; });
        Object.keys(s.layers).forEach(k=>{
          SHOT_LAYERS[k] = JSON.parse(JSON.stringify(s.layers[k]));
        });
      }
      /* 恢复镜头：新快照是整份的，老快照只有 id/status */
      if (s.items && typeof DOC !== 'undefined'){
        const full = s.items.some(it=>it && Object.prototype.hasOwnProperty.call(it, 'name'));
        if (full){
          DOC.items = s.items.map(it=>{
            const o = Object.assign({}, it);
            delete o._hasCanvas;
            return o;
          });
          /* 像素用快照里的引用接回去；缩略图从像素重新生成 */
          Object.keys(h.images || {}).forEach(id=>{
            const item = DOC.items.find(x=>x.id===id);
            if (!item) return;
            item.canvas = h.images[id];
            item.hasRealPixels = true;
            if (typeof riMakeThumb === 'function') item.thumbUrl = riMakeThumb(item.canvas, 640);
            if (typeof riSyncSourceLayer === 'function') riSyncSourceLayer(item);
          });
          if (!DOC.items.some(x=>x.id===selId)) selId = DOC.items[0] ? DOC.items[0].id : null;
          if (typeof emptyEl !== 'undefined' && emptyEl) emptyEl.classList.toggle('hidden', DOC.items.length>0);
          if (typeof buildGraph === 'function'){ try { buildGraph(false); } catch(_){} }
          if (typeof setMode === 'function') setMode(mode);
        } else {
          s.items.forEach(it=>{
            const shot = DOC.items.find(x=>x.id===it.id);
            if (shot) shot.status = it.status;
          });
        }
      }
    } catch(_){}
  }
  renderHistory();
  if (document.querySelector('.lew')) leRenderAll();
  /* 🔴 撤销后要把图层效果重新画到缩略图上 */
  if (typeof applyAllLayers === 'function') applyAllLayers();
  if (typeof renderLayerPanel === 'function') renderLayerPanel();
}

function renderHistory(){
  const host = document.getElementById('histPanel');
  if (!host) return;
  host.innerHTML = `
    <div class="lh-hd">
      <span class="lh-t">历史</span>
      <span class="lh-n">${HIST_POS+1}/${HISTORY.length}</span>
      <span class="lh-btns">
        <button class="lh-b" onclick="undo()" title="撤销 Ctrl+Z">↶</button>
        <button class="lh-b" onclick="redo()" title="重做 Ctrl+Y">↷</button>
      </span>
    </div>
    <div class="lh-body">
      ${HISTORY.length ? HISTORY.map((h,i)=>`
        <div class="lh-item ${i===HIST_POS?'on':''} ${i>HIST_POS?'future':''}"
          onclick="jumpHistory(${i})">
          <span class="lh-i">${i+1}</span>
          <span class="lh-l">${h.label}</span>
          <span class="lh-t2">${h.at}</span>
        </div>`).join('') : '<div class="lh-empty">还没有操作</div>'}
    </div>
    <div class="lh-foot">点任意一步可以回到那里 · Ctrl+Z 撤销</div>`;
}

/* ---------- ③ 提示词库 ---------- */
let PROMPT_LIB = [
  { id:'p1', name:'霜见月 · 冷色逆光', tags:['人像','冷色调','逆光'],
    text:'银白长发过腰 · 红色竖瞳 · 黑色高领长风衣银扣 · 左眼下泪痕状疤痕 · 冷色调高对比逆光 · 银白发丝逆光边缘光',
    used:12 },
  { id:'p2', name:'面霜 · 商业白底', tags:['商品','白底','极简'],
    text:'精华面霜圆罐 · 磨砂玻璃瓶身 · 香槟金哑光盖 · 左上前柔光箱 · 右侧弱补光 · 罐底轻微投影 · 暖白低饱和 · 商业产品摄影',
    used:38 },
  { id:'p3', name:'雨夜老街 · 赛博', tags:['场景','霓虹','夜景'],
    text:'老城区窄巷 · 雨夜地面积水反光 · 霓虹招牌顶光偏右 · 冷蓝品红对比 · 旧砖墙面水渍 · 齐眼高平视中景 · 电影感浅景深',
    used:7 }
];

function openPromptLib(){
  hideFloatBar();
  document.getElementById('overlayHost').innerHTML = `
    <div class="pl" onclick="if(event.target.classList.contains('plw'))closePromptLib()">
      <div class="plw">
        <div class="inp-hd">
          <div class="inp-t">提示词库</div>
          <div class="inp-sub">调好的组合存起来，下次直接用</div>
          <button class="inp-x" onclick="closePromptLib()">✕</button>
        </div>
        <div class="pl-search">
          <input class="pl-in" placeholder="搜名字或标签…" oninput="renderPromptLib(this.value)">
        </div>
        <div class="pl-body" id="plBody"></div>
        <div class="pl-foot">
          <span class="pl-note">从「搜索抽要素」里调好的结果，可以一键存进来</span>
          <button class="insp-b pri" onclick="savePromptToLib()">存当前要素</button>
        </div>
      </div>
    </div>`;
  renderPromptLib('');
}

function renderPromptLib(q){
  const host = document.getElementById('plBody');
  if (!host) return;
  const k = (q||'').trim().toLowerCase();
  const list = PROMPT_LIB.filter(p=>
    !k || p.name.toLowerCase().includes(k) || p.tags.some(t=>t.toLowerCase().includes(k))
  );
  host.innerHTML = list.length ? list.map(p=>`
    <div class="pl-item">
      <div class="pl-hd">
        <span class="pl-name">${esc(p.name)}</span>
        <span class="pl-used">用过 ${p.used} 次</span>
      </div>
      <div class="pl-tags">${p.tags.map(t=>`<span class="pl-tag">${t}</span>`).join('')}</div>
      <div class="pl-text">${esc(p.text)}</div>
      <div class="pl-acts">
        <button class="pl-b" onclick="insertPrompt('${p.id}')">插入到输入框</button>
        <button class="pl-b" onclick="copyPrompt('${p.id}')">复制</button>
      </div>
    </div>`).join('') : '<div class="pl-empty">没找到</div>';
}

function closePromptLib(){ document.getElementById('overlayHost').innerHTML = ''; }

function insertPrompt(id){
  const p = PROMPT_LIB.find(x=>x.id===id);
  if (!p) return;
  const ta = document.getElementById('ta');
  if (ta){ ta.value = p.text; ta.focus(); }
  closePromptLib();
  toast('已插入到输入框');
}

function copyPrompt(id){
  const p = PROMPT_LIB.find(x=>x.id===id);
  if (!p) return;
  if (navigator.clipboard) navigator.clipboard.writeText(p.text).catch(()=>{});
  toast('已复制');
}

function savePromptToLib(){
  // 从当前搜索要素里取
  let text = '';
  try { text = buildPrompt().replace(/<div class="srch-live2">[\s\S]*$/, '').replace(/<[^>]+>/g,''); } catch(_){}
  if (!text){ toast('还没有可以存的要素'); return; }
  PROMPT_LIB.unshift({
    id: 'p' + Date.now(),
    name: '未命名 · 刚才调的',
    tags: [SUBJECT_SCHEMAS[curSubject] ? SUBJECT_SCHEMAS[curSubject].n : '自定义'],
    text, used: 0
  });
  renderPromptLib('');
  toast('已存进提示词库');
}

/* ---------- 快捷键 & 挂载 ---------- */
document.addEventListener('keydown', e=>{
  if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey){
    e.preventDefault(); undo();
  }
  if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))){
    e.preventDefault(); redo();
  }
});

/* 首次打开时初始化历史 */
setTimeout(()=>{ if (!HISTORY.length) pushHistory('打开画布'); }, 1200);


/* 把图层面板挂进 #stage，这样它相对画布定位，不会盖住智能体 */
(function mountLayerPanel(){
  const st = document.getElementById('stage');
  const lp = document.getElementById('layerPanel');
  if (!st || !lp) return;
  st.style.position = st.style.position || 'relative';
  st.appendChild(lp);
})();


/* ===== 图层混合模式（PS 的 mix-blend-mode 对应实现） =====
   🔴 为什么要这个：之前有图层但只能"正常"叠加，
      等于半个图层系统 —— 分层的价值一半在混合方式。
*/
const BLEND_MODES = [
  { k:'normal',    n:'正常',   d:'直接盖上去（默认）' },
  { k:'multiply',  n:'正片叠底', d:'变暗：两个颜色相乘，适合压暗、上色' },
  { k:'screen',    n:'滤色',   d:'变亮：反过来相乘，适合加光、去黑底' },
  { k:'overlay',   n:'叠加',   d:'暗的更暗、亮的更亮 —— 增强对比' },
  { k:'soft-light',n:'柔光',   d:'温和版的叠加，适合调氛围不伤细节' },
  { k:'color',     n:'颜色',   d:'只取色相饱和度，保留下面的明暗' }
];

function setLayerBlend(id, mode){
  const layers = layersOf(selId || DOC.items[0].id);
  const l = layers.find(x=>x.id===id);
  if (!l) return;
  l.blend = mode;
  refreshLayers(selId);
  // 把混合模式挂到画布上对应缩略图（如果该镜头是当前选中）
  applyBlendPreview();
  const m = BLEND_MODES.find(x=>x.k===mode);
  /* 🔧 2026-10-20 修：混合模式改变也要进历史 */
  pushHistory('混合：' + l.name + ' → ' + (m ? m.n : mode));
  toast('混合：' + (m?m.n:mode) + (m&&mode!=='normal' ? ' —— ' + m.d : ''));
}

/* 把当前镜头各层的混合模式套到缩略图上（视觉预览） */
function applyBlendPreview(){
  const sid = selId || (DOC.items[0] && DOC.items[0].id);
  const layers = layersOf(sid);
  const el = document.querySelector('.shot[data-id="' + sid + '"] .im');
  if (!el) return;
  const adj = layers.filter(l=>l.type!=='source' && l.visible && l.blend && l.blend!=='normal');
  // 用一个叠加层表现混合效果
  let ov = el.querySelector('.blendlayer');
  if (!adj.length){
    if (ov) ov.remove();
    return;
  }
  if (!ov){
    ov = document.createElement('div');
    ov.className = 'blendlayer';
    ov.style.cssText = 'position:absolute;inset:0;pointer-events:none;border-radius:inherit';
    el.appendChild(ov);
  }
  // 取最上面那个非常规混合
  const l = adj[adj.length-1];
  ov.style.mixBlendMode = l.blend;
  ov.style.background = 'linear-gradient(160deg, rgba(34,211,238,.45), rgba(120,40,200,.4))';
  ov.style.opacity = String(l.opacity);
}
/* ================= 图层做真：把图层状态真正画到缩略图上 =================
   之前图层只是数据，改了看不见效果。现在：
   · 原图层隐藏 → 缩略图变灰 + 标"原图隐藏"
   · 本地调整层 → 缩略图应用对应 filter（曝光/对比/饱和/色温）
   · AI 编辑层 → 叠一层色块表示"内容被改过"
   · 透明度 → 影响强度
   · 混合模式 → 影响叠加方式
*/
function layerFilterOf(l){
  const p = l.params || {};
  const parts = [];

  /* 只推「非中性」的项 —— 否则会输出 contrast(1.000) 这种等于没变的冗余 */
  if (typeof p.exposure === 'number' && Math.abs(p.exposure) > 0.005)
    parts.push('brightness(' + (1 + p.exposure*0.35).toFixed(3) + ')');
  if (typeof p.contrast === 'number' && Math.abs(p.contrast - 1) > 0.005)
    parts.push('contrast(' + p.contrast.toFixed(3) + ')');
  if (typeof p.saturation === 'number' && Math.abs(p.saturation - 1) > 0.005)
    parts.push('saturate(' + p.saturation.toFixed(3) + ')');

  /* 🔧 2026-10-20 修：之前只读 exposure/contrast/saturation，
     导致 temp / levels / curves 全链路白存（预设和批量应用的参数到下游全失效）。
     现在把这三类也翻译成 CSS filter。 */

  // ① 色温：偏暖加 sepia，偏冷减饱和再偏蓝
  let tempOn = false;
  if (typeof p.temp === 'number' && Math.abs(p.temp - 6100) > 30){
    const t = (p.temp - 6100) / 2000;   // -1 ~ +0.95
    if (t > 0){
      parts.push('sepia(' + (t * 0.30).toFixed(3) + ')');
      parts.push('hue-rotate(' + (-t * 10).toFixed(1) + 'deg)');
    } else {
      const k = -t;
      parts.push('saturate(' + (1 - k * 0.12).toFixed(3) + ')');
      parts.push('hue-rotate(' + (k * 16).toFixed(1) + 'deg)');
    }
    tempOn = true;
  }

  // ② 色阶 gamma：gamma>1 提亮中间调
  let lvOn = false;
  if (p.levels){
    const g = typeof p.levels.gamma === 'number' ? p.levels.gamma : 1;
    if (Math.abs(g - 1) > 0.02){
      parts.push('brightness(' + Math.pow(1 / g, 0.45).toFixed(3) + ')');
      lvOn = true;
    }
    const blk = typeof p.levels.black === 'number' ? p.levels.black : 0;
    const wht = typeof p.levels.white === 'number' ? p.levels.white : 1;
    if (blk > 0.005 || wht < 0.995){
      const span = Math.max(0.05, wht - blk);
      parts.push('contrast(' + (1 / span).toFixed(3) + ')');
      lvOn = true;
    }
  }

  // ③ 曲线：CSS 做不了任意曲线，用中点偏移估一个对比度（并标注是近似）
  let cvOn = false;
  if (p.curves && Array.isArray(p.curves.rgb) && p.curves.rgb.length >= 3){
    const pts = p.curves.rgb;
    let midY = 0.5;
    let bestD = 9;
    pts.forEach(function(pt){
      const d = Math.abs(pt[0] - 0.5);
      if (d < bestD){ bestD = d; midY = pt[1]; }
    });
    if (Math.abs(midY - 0.5) > 0.02){
      parts.push('contrast(' + (1 + (midY - 0.5) * 0.9).toFixed(3) + ')');
      cvOn = true;
    }
  }

  /* ④ 画质参数（24-quality.js 落盘进来的）——
     CSS 没有降噪/锐化，用近似表达：降噪→轻微模糊，锐化→加对比 */
  let qOn = false;
  if (typeof p.denoise === 'number' && p.denoise > 0.01){
    parts.push('blur(' + (p.denoise * 0.8).toFixed(2) + 'px)');
    qOn = true;
  }
  if (typeof p.sharpen === 'number' && p.sharpen > 0.01){
    parts.push('contrast(' + (1 + p.sharpen * 0.22).toFixed(3) + ')');
    qOn = true;
  }
  if (typeof p.shadow === 'number' && p.shadow > 0.01){
    parts.push('brightness(' + (1 + p.shadow * 0.18).toFixed(3) + ')');
    qOn = true;
  }
  if (typeof p.blur === 'number' && p.blur > 0.01){
    parts.push('blur(' + (p.blur * 4).toFixed(2) + 'px)');
    qOn = true;
  }
  if (p.hsl){
    if (Math.abs(p.hsl.hue || 0) > 0.5){
      parts.push('hue-rotate(' + Number(p.hsl.hue).toFixed(1) + 'deg)');
      qOn = true;
    }
    if (typeof p.hsl.sat === 'number' && Math.abs(p.hsl.sat - 1) > 0.01){
      parts.push('saturate(' + p.hsl.sat.toFixed(3) + ')');
      qOn = true;
    }
    if (typeof p.hsl.light === 'number' && Math.abs(p.hsl.light) > 0.01){
      parts.push('brightness(' + (1 + p.hsl.light * 0.5).toFixed(3) + ')');
      qOn = true;
    }
  }

  /* 参数全是中性（1/0）时给一点默认效果 —— 否则用户加了层却看不出变化。
     🔧 修：中性判断要包含 temp/levels/curves，否则设了色温还说"中性"就被覆盖。 */
  const neutral =
    (parts.length === 0) ||
    (!tempOn && !lvOn && !cvOn && !qOn &&
     Math.abs(p.exposure || 0) < 0.01 &&
     Math.abs((p.contrast === undefined ? 1 : p.contrast) - 1) < 0.01 &&
     Math.abs((p.saturation === undefined ? 1 : p.saturation) - 1) < 0.01);

  if (neutral) return 'contrast(1.14) saturate(1.12) brightness(1.07)';
  return parts.join(' ');
}

function applyLayers(shotId){
  const el = document.querySelector('.shot[data-id="' + shotId + '"] .im');
  if (!el) return;
  const layers = layersOf(shotId);

  // 清掉之前叠的
  el.querySelectorAll('.lyr-ov').forEach(n=>n.remove());
  el.style.filter = '';
  el.style.opacity = '';
  el.classList.remove('src-hidden');

  const src = layers.find(l=>l.type==='source');
  const srcVisible = !src || src.visible !== false;
  if (!srcVisible) el.classList.add('src-hidden');

  const locals = layers.filter(l=>l.type==='local' && l.visible);
  const ais    = layers.filter(l=>l.type==='ai' && l.visible);

  // 本地调整层：合成一个 filter（按可见 + 透明度加权）
  let filterStr = '';
  if (locals.length){
    // 取最上面那层的参数（简化：多层就取最后一层，避免滤镜重复叠加失真）
    const top = locals[locals.length-1];
    const base = layerFilterOf(top);
    // 透明度 <1 时减弱效果
    if (top.opacity < 0.99){
      const t = top.opacity;
      filterStr = base.replace(/([\d.]+)\)/g, (m,n)=> {
        const num = Number(n);
        const weakened = 1 + (num - 1) * t;
        return weakened.toFixed(3) + ')';
      });
    } else {
      filterStr = base;
    }
  }
  // AI 层也会让画面"变了"
  if (ais.length && !filterStr){
    filterStr = 'contrast(1.1) saturate(1.15) brightness(1.05)';
  }
  if (filterStr) el.style.filter = filterStr;

  // AI 编辑层：叠一个可见的标记层（因为没法真生成）
  ais.forEach(a=>{
    const ov = document.createElement('div');
    ov.className = 'lyr-ov';
    ov.style.cssText = 'position:absolute;inset:0;pointer-events:none;border-radius:inherit;'
      + 'background:linear-gradient(160deg,rgba(34,211,238,.28),rgba(140,60,220,.22));'
      + 'opacity:' + a.opacity + ';'
      + 'mix-blend-mode:' + (a.blend || 'normal') + ';';
    el.appendChild(ov);
  });

  // 隐藏的原图 → 加个遮罩感
  if (!srcVisible){
    const ov = document.createElement('div');
    ov.className = 'lyr-ov';
    ov.style.cssText = 'position:absolute;inset:0;pointer-events:none;border-radius:inherit;'
      + 'background:repeating-linear-gradient(45deg,rgba(0,0,0,.55) 0 6px,rgba(0,0,0,.35) 6px 12px);';
    el.appendChild(ov);
  }
}

/* 全局重画所有镜头的图层效果 */
function applyAllLayers(){
  if (typeof DOC === 'undefined' || !DOC.items) return;
  DOC.items.forEach(s=>{
    if (SHOT_LAYERS[s.id]) applyLayers(s.id);
  });
}

/* 图层操作后统一刷新 */
function refreshLayers(shotId){
  renderLayerPanel();
  const sid = shotId || selId || (DOC.items[0] && DOC.items[0].id);
  applyLayers(sid);
}
/* ================= 统一落盘：把一组参数变成一个图层 =================
   🔴 2026-10-20 修（审查报告阻断问题 4）：
      之前 leApply / applyQuality / applyMask 点「应用」只往对话里发一条
      "做完了"，画布参数一个字节没变 —— 看着像做了，其实没落盘。

      现在统一走这里：参数 → 新图层 → applyLayers 重画 → pushHistory 可撤销。
*/
function commitLocalLayer(name, params, historyLabel){
  const sid = selId || (DOC.items[0] && DOC.items[0].id);
  if (!sid){ toast('先选一张图'); return null; }

  const layers = layersOf(sid);
  const l = makeLocalLayer();
  l.name = name || '调整层';
  l.params = Object.assign({}, params || {});
  layers.push(l);
  ACTIVE_LAYER = l.id;

  if (typeof refreshLayers === 'function') refreshLayers(sid);
  else if (typeof renderLayerPanel === 'function') renderLayerPanel();

  if (typeof pushHistory === 'function') pushHistory(historyLabel || ('应用：' + l.name));

  return l;
}