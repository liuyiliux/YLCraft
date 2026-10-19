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
          </div>` : ''}
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
  const layers = layersOf(selId || DOC.items[0].id);
  const l = layers.find(x=>x.id===id);
  if (l){ l.visible = !l.visible; renderLayerPanel(); }
}
function setLayerOpacity(id, v){
  const layers = layersOf(selId || DOC.items[0].id);
  const l = layers.find(x=>x.id===id);
  if (l){ l.opacity = Number(v); }
  const el = document.getElementById('lpOpv');
  if (el) el.textContent = Math.round(Number(v)*100) + '%';
}
function deleteLayer(id){
  const sid = selId || DOC.items[0].id;
  SHOT_LAYERS[sid] = layersOf(sid).filter(x=>x.id!==id);
  ACTIVE_LAYER = null;
  renderLayerPanel();
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
  renderLayerPanel();
  pushHistory('加了一层：' + l.name);
  toast(kind === 'local' ? '加了调整层 · 免费' : '加了 AI 编辑层 · 要调模型');
}

/* ---------- ② 撤销 / 历史 ---------- */
let HISTORY = [];
let HIST_POS = -1;

function pushHistory(label){
  HISTORY = HISTORY.slice(0, HIST_POS + 1);
  HISTORY.push({
    label, at: new Date().toLocaleTimeString('zh-CN', { hour12:false }),
    snapshot: JSON.stringify({ adj: LOCAL_ADJ, fixed: Array.from(FIXED) })
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
    } catch(_){}
  }
  renderHistory();
  if (document.querySelector('.lew')) leRenderAll();
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

