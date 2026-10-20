/* 06-imageops.js - split from canvas_unified_v14.html (lines 1278-1474) */
/* ================= 放大编辑（含全部图片能力 + 自定义置顶） ================= */

/* 图片操作全清单
   来源：Lovart 右键12项+浮条7项 / Toonflow imageNode 5个实现 / LibTV Slash 6项
        + 我们自己的 image-editor 9个本地工具 / motion-gif 动图 / 画面批注改图 */
const IMG_OPS = [
  {g:'本地处理 · 免费即时（不用调模型）', items:[
    {k:'裁剪',        d:'改构图', c:'免费', on:1},
    {k:'旋转与翻转',  d:'水平/垂直/任意角度', c:'免费', on:1},
    {k:'滤镜',        d:'亮度 / 对比 / 饱和 / 色相', c:'免费', on:1},
    {k:'压缩 / 改尺寸', d:'改变像素尺寸与体积', c:'免费', on:1},
    {k:'加文字',      d:'图上写字', c:'免费', on:1},
    {k:'水印',        d:'加文字水印（居中/右下/平铺）', c:'免费', on:1},
    {k:'画图 / 涂鸦', d:'手绘几笔', c:'免费', on:1},
    {k:'字符画',      d:'转成字符拼成的图', c:'免费', on:0},
    {k:'Base64',      d:'导出编码，给开发用', c:'免费', on:0}
  ]},
  {g:'AI 修改 · 在这张图上改（便宜）', items:[
    {k:'画面批注改图', d:'圈一块 + 写意见，直接重画（我们已有）', c:'⚡3', on:1},
    {k:'局部重绘',    d:'框选一块，描述要变成什么', c:'⚡3', on:1},
    {k:'重新打光',    d:'光位跟着原图走', c:'⚡3', on:1},
    {k:'AI 调色',     d:'说"冷一点/暖一点"', c:'⚡2', on:1}
  ]},
  {g:'派生 · 生成新图（中等）', items:[
    {k:'扩展画布',     d:'向外扩，补背景（outpaint）', c:'⚡4', on:1},
    {k:'去背景 / 抠主体', d:'输出透明底 PNG', c:'⚡2', on:1},
    {k:'换背景',      d:'描述新背景', c:'⚡4', on:1},
    {k:'画同款',      d:'照这张的风格再出一张', c:'⚡14', on:1},
    {k:'变体 ×4',     d:'同提示词出 4 张备选', c:'⚡28', on:1},
    {k:'生成多角度',  d:'换机位看同一主体', c:'⚡14', on:1},
    {k:'图层拆分',    d:'拆成 人物 / 背景 / 文字 层', c:'⚡6', on:1},
    {k:'编辑文字',    d:'OCR 抽字重绘（会丢原字体效果）', c:'⚡14', on:1},
    {k:'图生 3D',    d:'TripoSR 出 glb，可进 3D 导演台预演', c:'⚡8', on:1}
  ]},
  {g:'动图 · 多格图切帧（合成不花钱）', items:[
    {k:'生成动图',     d:'一次画多格画面（不是视频）', c:'⚡14', on:1},
    {k:'切帧合成 GIF', d:'选格数 → 合成 GIF / WebP / MP4', c:'免费', on:1},
    {k:'帧级滤镜',     d:'亮度/对比/饱和/色相/旋转', c:'免费', on:1},
    {k:'自定义切分网格', d:'格子分割线可以手拖', c:'免费', on:1}
  ]},
  {g:'批量 · 一次出多张（贵）', items:[
    {k:'多机位九宫格', d:'一张 → 9 个机位', c:'⚡126', on:1},
    {k:'角色三视图',   d:'正面 / 侧面 / 背面', c:'⚡42', on:1},
    {k:'剧情推演四宫格', d:'情节往下推 4 格', c:'⚡56', on:1},
    {k:'25 宫格连贯分镜', d:'一次出 25 格（一次别点）', c:'⚡350', on:1}
  ]},
  {g:'输出', items:[
    {k:'存到素材库', d:'合成图 + 分层结构两份', c:'免费', on:1},
    {k:'下载原图',   d:'', c:'免费', on:1},
    {k:'复制一张',   d:'', c:'免费', on:1}
  ]}
];

/* 置顶（自定义工具栏）—— 对应 Lovart「自定义工具栏」 */
const OP_DEFAULT_PINNED = ['画面批注改图','重新打光','扩展画布','去背景 / 抠主体','存到素材库'];
let PINNED = new Set(OP_DEFAULT_PINNED);
let showOpNames = true;

function allOps(){ return IMG_OPS.flatMap(g=>g.items); }
function findOp(k){ return allOps().find(x=>x.k===k); }

function openLB(id){
  const s = DOC.items.find(x=>x.id===id); if(!s) return;
  const enabled = allOps().filter(x=>x.on).length;
  document.getElementById('overlayHost').innerHTML =
   `<div class="lb" onclick="if(event.target.classList.contains('lbw')||event.target.classList.contains('lb'))closeLB()">
      <div class="top2">
        <div class="nm">${s.name} · <b>点图编辑</b></div>
        <div class="sp"></div>
        <button class="b out" onclick="closeLB()">关闭 ✕</button>
      </div>
      <div class="lbmain">
        <div class="lbw">
          <div class="lbi" style="aspect-ratio:${s.canvas ? s.canvas.width+'/'+s.canvas.height : s.w+'/'+s.h};height:min(64vh,440px);${
            s.thumbUrl
              ? `background-image:url("${s.thumbUrl}");background-size:contain;background-position:center;background-repeat:no-repeat;background-color:#0b0b0f`
              : `background:${BG[s.cls]}`
          }">
            ${s.thumbUrl ? '' : '<div class="glow"></div><div class="fig"></div>'}
          </div>
        </div>
        <aside class="lbside">
          <div class="lsh">
            <span class="lst">可以对这张图做的（${enabled} 项）</span>
            <button class="px" onclick="closeLB()">✕</button>
          </div>
          <div class="lsb" id="opList"></div>
        </aside>
      </div>
      <div class="lbb" id="opBar"></div>
    </div>`;
  renderOps();
}

function renderOps(){
  // 列表
  document.getElementById('opList').innerHTML = IMG_OPS.map(g=>`
    <div class="opg"><div class="opgt">${g.g}</div>
      ${g.items.map(it=>{
        const pin = PINNED.has(it.k);
        return `<div class="opit ${it.on?'':'dis'}" onclick="doOp('${it.k}','${it.c}',${it.on?1:0})">
          <span class="opk">${it.k}</span>
          <span class="opc">${it.c}</span>
          <button class="opin ${pin?'on':''}" title="${pin?'从工具栏移除':'加到工具栏'}"
            onclick="event.stopPropagation();togglePin('${it.k}')">${pin?'★':'☆'}</button>
          ${it.d?`<span class="opd">${it.d}</span>`:''}
        </div>`;
      }).join('')}
    </div>`).join('')
    + `<div class="opnote">
        价格来自模型配置（每张多少钱），换模型价格会变。<br>
        <b>★ 加到下面工具栏</b> —— 工具栏最多放 6 个，这就是「自定义工具栏」。<br>
        灰掉的：字符画 / Base64 是开发工具，用不上。
      </div>`;

  // 工具栏（置顶）
  const bar = [...PINNED].slice(0,6).map(k=>{
    const o = findOp(k); if(!o) return '';
    return `<div class="tool" onclick="doOp('${o.k}','${o.c}',${o.on?1:0})">
      ${showOpNames?o.k:''} ${o.c!=='免费'?`<span class="pr">${o.c}</span>`:''}</div>`;
  }).join('');
  document.getElementById('opBar').innerHTML = `
    <span class="m2">${s0w()} · 工具栏 ${PINNED.size}/6</span>
    ${bar}
    <div class="tool" style="margin-left:6px;border-color:var(--acl);color:var(--ac)"
      onclick="toggleNames()">${showOpNames?'隐藏名称':'显示名称'}</div>`;
}
function s0w(){ const i=DOC.items.find(x=>x.id===selId)||DOC.items[0]; return i?`${i.w}×${i.h}`:''; }

function togglePin(k){
  if (PINNED.has(k)){
    if (PINNED.size<=1){ toast('至少留一个'); return; }
    PINNED.delete(k);
  } else {
    if (PINNED.size>=6){ toast('工具栏最多 6 个，先去掉一个'); return; }
    const o = findOp(k);
    if (o && !o.on){ toast('这项暂不做，不能加'); return; }
    PINNED.add(k);
  }
  renderOps();
}
function toggleNames(){ showOpNames=!showOpNames; renderOps(); }

function doOp(k, c, on){
  if (!on){ toast(`「${k}」暂不做`); return; }
  toast(c && c!=='免费' ? `「${k}」开始 · 预计 ${c}` : `「${k}」`);
  if (k === '存到素材库'){ setTimeout(()=>{ closeLB(); toast('已存到素材库（合成图 + 分层结构两份）'); }, 600); }
}

function closeLB(){ document.getElementById('overlayHost').innerHTML=''; closeCtx(); }

/* ================= 右键：砍到 6 项 ================= */
let ctxEl = null;
/* ================= 完整能力菜单（右键 / 浮条「⋯」都打开这个） =================
   照 Lovart：浮条 7 项是快捷的，完整 32 项在这里分组展示
*/
function openCtx(x,y,id){
  closeCtx();
  ctxTargetId = id;
  const enabled = allOps().filter(o=>o.on);
  const m = document.createElement('div');
  m.className = 'ctx opsctx';
  m.innerHTML =
    `<div class="ctx-h">全部能力 <span>${enabled.length} 项可用</span></div>
     <div class="ctx-body">`
     + IMG_OPS.map(g=>{
         const items = g.items.filter(o=>o.on);
         if (!items.length) return '';
         return `<div class="ctx-g">
           <div class="ctx-gt">${g.g.replace(/ ·.*$/,'')}</div>
           ${items.map(o=>`<div class="ctx-oi" onclick="ctxDo('${o.k.replace(/'/g,'')}')">
             <span class="ctx-ok">${o.k}</span>
             <span class="ctx-od">${o.d||''}</span>
             <span class="ctx-oc">${o.c}</span>
           </div>`).join('')}
         </div>`;
       }).join('')
     + `</div>`;
  const W = 268, H = 420;
  m.style.left = Math.max(8, Math.min(x, innerWidth - W - 8)) + 'px';
  m.style.top  = Math.max(8, Math.min(y, innerHeight - H - 8)) + 'px';
  document.body.appendChild(m); ctxEl = m;
}
let ctxTargetId = null;

function closeCtx(){ if(ctxEl){ctxEl.remove();ctxEl=null;} }
function ctxAct(t){ closeCtx(); if(t==='更多…'){ openCtx(120,120,selId); } else toast(t); }
function ctxDo(k){
  closeCtx();
  const op = findOp(k);
  toast((op?op.k:k) + (op&&op.c!=='免费' ? ' · ' + op.c : ' · 免费'));
}

/* 浮条「⋯」/「快捷编辑」→ 打开完整能力菜单（不弹大图） */
function fbMore(){
  const fb = document.getElementById('floatBar');
  const r = fb ? fb.getBoundingClientRect() : {left:200, bottom:120};
  openCtx(r.left, r.bottom + 6, floatTarget);
}


