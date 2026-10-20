/* 16-export.js — 导出（真合成，不是占位）
   🔴 2026-10-19 用户纠正的模型，现在真的实现了：
     ① 文档层：存参数，不存像素
     ② 预览层：画布上实时渲染
     ③ 导出层：只在导出时按顺序合成像素

   之前这里是占位（面板里写死两层假数据，点导出弹个提示）。
   现在：从 layersOf() 读真实图层，用 canvas 逐层真合成，能预览、能下载。
*/

/* ---------- 一层调整（本地，免费）---------- */
function makeLocalLayer(){
  return {
    id: 'ly' + Math.random().toString(36).slice(2, 8),
    type: 'local', name: '本地调整', visible: true, opacity: 1,
    blend: 'normal', cost: 0,
    params: { exposure: 0, contrast: 1, saturation: 1, temp: 6100 }
  };
}

/* ---------- 一层 AI 编辑（花钱）---------- */
function makeAiLayer(op, params){
  return {
    id: 'ly' + Math.random().toString(36).slice(2, 8),
    type: 'ai', name: 'AI 编辑', visible: true, opacity: 1,
    blend: 'normal', cost: 14,
    op: op || 'inpaint',
    params: params || {}
  };
}

/* ---------- 镜头文档结构（真实现时落在 CanvasDocument.document_json）---------- */
const SHOT_DOC_DEMO = {
  shotId: null,
  layers: [],       // 层就是参数，不是像素
  history: [],      // 操作记录
  updatedAt: null
};

/* ================= 真合成 ================= */

/* 造一张"原图"（复用 retouch 的人像，没有就用渐变） */
function exportBaseCanvas(w, h, shotId){
  const out = document.createElement('canvas');
  out.width = w; out.height = h;
  const g = out.getContext('2d');
  const item = (typeof DOC !== 'undefined') ? DOC.items.find(x=>x.id===shotId) : null;
  if (item && item.canvas){
    const iw = item.canvas.width, ih = item.canvas.height;
    const s = Math.max(w/iw, h/ih);
    const dw = iw*s, dh = ih*s;
    g.imageSmoothingQuality = 'high';
    g.drawImage(item.canvas, (w-dw)/2, (h-dh)/2, dw, dh);
    return out;
  }
  if (typeof rtMakePortrait === 'function'){
    const src = rtMakePortrait(false, false);
    g.drawImage(src, 0, 0, w, h);
    return out;
  }
  const bg = g.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, '#2a2340'); bg.addColorStop(1, '#141020');
  g.fillStyle = bg; g.fillRect(0, 0, w, h);
  return out;
}

/* 我们的混合模式 → canvas globalCompositeOperation */
const BLEND_TO_CANVAS = {
  normal:'source-over', multiply:'multiply', screen:'screen',
  overlay:'overlay', 'soft-light':'soft-light', color:'color'
};

/* 把 AI 层画成"重画后的样子"（filter + 色相偏移模拟，不是真生成）
   🔧 2026-10-20 修：参数改成「当前合成结果」而不是 base ——
      之前所有 AI 层都画同一张 base，等于把下面的内容抹掉了。 */
function paintAiLayer(ctx, w, h, current, layer){
  ctx.save();
  ctx.globalAlpha = layer.opacity === undefined ? 1 : layer.opacity;
  ctx.globalCompositeOperation = BLEND_TO_CANVAS[layer.blend || 'normal'] || 'source-over';
  const tmp = document.createElement('canvas');
  tmp.width = w; tmp.height = h;
  const tg = tmp.getContext('2d');
  tg.filter = 'hue-rotate(8deg) saturate(1.15) contrast(1.08)';
  tg.drawImage(current, 0, 0);
  ctx.drawImage(tmp, 0, 0);
  ctx.restore();
}

/* 核心：按图层顺序真合成
   🔴 2026-10-20 修（审查报告实现偏离 1）：
      之前 local 层用 source-over 画不透明 base，会把下层的 AI 层抹掉
      （实测 a1+l2 与 l2 only 像素 0% 差异）。
      正确语义（同 PS 调整图层）：调整层作用于「它下方的合成结果」，不是重画原图。 */
function compositeShot(shotId, w, h){
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext('2d');
  const base = exportBaseCanvas(w, h, shotId);
  const layers = layersOf(shotId);

  /* 抓当前画布快照 */
  function snapshot(){
    const s = document.createElement('canvas');
    s.width = w; s.height = h;
    s.getContext('2d').drawImage(canvas, 0, 0);
    return s;
  }

  layers.forEach(l => {
    if (l.visible === false) return;
    const alpha = (l.opacity === undefined) ? 1 : l.opacity;

    if (l.type === 'source'){
      ctx.globalAlpha = alpha;
      ctx.globalCompositeOperation = 'source-over';
      ctx.filter = 'none';
      ctx.drawImage(base, 0, 0);

    } else if (l.type === 'local'){
      const f = (typeof layerFilterOf === 'function') ? layerFilterOf(l) : 'none';
      if (!f || f === 'none') return;

      const below = snapshot();                 // 下方已合成的结果
      const adj = document.createElement('canvas');
      adj.width = w; adj.height = h;
      const ag = adj.getContext('2d');
      ag.filter = f;                            // 对"下方内容"整体套滤镜
      ag.drawImage(below, 0, 0);

      ctx.save();
      ctx.clearRect(0, 0, w, h);
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';
      ctx.filter = 'none';
      ctx.drawImage(below, 0, 0);               // 先还原下方内容
      ctx.globalAlpha = alpha;                  // 再按透明度叠调整后
      ctx.globalCompositeOperation = BLEND_TO_CANVAS[l.blend || 'normal'] || 'source-over';
      ctx.drawImage(adj, 0, 0);
      ctx.restore();

    } else if (l.type === 'ai'){
      paintAiLayer(ctx, w, h, snapshot(), l);
    }
  });
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';
  return canvas;
}

/* ================= 面板 ================= */
let EX_FMT = 'png';

function openExport(){
  const shotId = selId || (DOC.items[0] && DOC.items[0].id);
  const shot = DOC.items.find(x=>x.id===shotId) || DOC.items[0];
  if (!shot){ toast('先选一张图'); return; }
  if (typeof hideFloatBar === 'function') hideFloatBar();

  const layers = layersOf(shotId);
  const vis = layers.filter(l=>l.visible !== false);
  const W = 320, H = 480;

  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="if(event.target.classList.contains('exw'))closeExport()">
      <div class="exw" style="width:min(800px,95vw)">
        <div class="inp-hd">
          <div class="inp-t">导出</div>
          <div class="inp-sub">${esc(shot.name)} · 这些层按顺序真合成一张图</div>
          <button class="inp-x" onclick="closeExport()">✕</button>
        </div>

        <div class="ex-body">
          <div class="ex-cols">
            <div class="ex-left">
              <div class="ex-preview"><canvas id="exCanvas" width="${W}" height="${H}"></canvas></div>
              <div class="ex-pv">合成结果 · 实时</div>
            </div>

            <div class="ex-right">
              <div class="ex-sec">
                <span class="ex-st">合成顺序</span>
                <span class="ex-s2">从下往上叠 · ${vis.length}/${layers.length} 层可见</span>
              </div>

              <div class="ex-stack">
                ${layers.slice().reverse().map((l,i)=>{
                  const idx = layers.length - i;
                  const hidden = l.visible === false;
                  return `
                    <div class="ex-layer ${l.type} ${hidden?'off':''}">
                      <span class="ex-n">${idx}</span>
                      <span class="ex-ln">${esc(l.name)}</span>
                      <span class="ex-lt ${l.type}">${
                        l.type==='source' ? '原图' : l.type==='local' ? '本地' : '调模型'
                      }</span>
                      <span class="ex-lc ${l.type==='local'||l.type==='source'?'free':''}">${
                        l.type==='source' ? '—' : l.cost ? '⚡'+l.cost : '免费'
                      }</span>
                      ${hidden?'<span class="ex-off">已隐藏</span>':''}
                    </div>
                    <div class="ex-ld">${
                      l.type==='source' ? '原始像素'
                      : l.type==='local' ? ((typeof layerFilterOf==='function') ? layerFilterOf(l) : '无参数')
                      : 'AI 重画 · 混合 ' + (l.blend || 'normal')
                    }</div>`;
                }).join('')}
              </div>

              <div class="ex-sec" style="margin-top:14px"><span class="ex-st">格式</span></div>
              <div class="ex-fmts">
                <button class="ex-f on" data-f="png" onclick="setExFmt('png')">PNG</button>
                <button class="ex-f" data-f="jpeg" onclick="setExFmt('jpeg')">JPEG</button>
              </div>

              <div class="ex-key">
                🔴 <b>这是真合成</b> —— 按图层顺序用 canvas 逐层画，
                filter 和混合模式都真的作用在像素上。<br>
                <span class="ex-key2">参数不烘焙：导出的是一张新图，图层还在文档里，随时能改。</span>
              </div>
            </div>
          </div>
        </div>

        <div class="ex-foot">
          <div class="ex-cost">
            花费 <b class="le-zero">0</b>
            <span class="ex-costn">本地合成 · 不走模型 · 导出 1024×1536</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="closeExport()">取消</button>
            <button class="insp-b" onclick="exPreviewLarger()">看大图</button>
            <button class="insp-b pri" onclick="exDo()">导出</button>
          </div>
        </div>
      </div>
    </div>`;

  const c = compositeShot(shotId, W, H);
  const dst = document.getElementById('exCanvas');
  if (dst) dst.getContext('2d').drawImage(c, 0, 0);
}

function setExFmt(f){
  EX_FMT = f;
  document.querySelectorAll('.ex-f').forEach(b=>b.classList.toggle('on', b.dataset.f===f));
}

function closeExport(){ document.getElementById('overlayHost').innerHTML = ''; }

/* 看大图：真合一张大的 */
function exPreviewLarger(){
  const shotId = selId || (DOC.items[0] && DOC.items[0].id);
  const c = compositeShot(shotId, 640, 960);
  const url = c.toDataURL('image/png');
  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="closeExport()">
      <div style="max-width:90vw;max-height:92vh;cursor:zoom-out">
        <img src="${url}" style="max-width:90vw;max-height:88vh;border-radius:8px;
          box-shadow:0 24px 70px -20px rgba(0,0,0,.95);display:block">
        <div style="text-align:center;font-size:10px;color:var(--tx3);margin-top:8px">
          640×960 真合成 · 点任意处关闭
        </div>
      </div>
    </div>`;
}

/* 真导出：下载 */
function exDo(){
  const shotId = selId || (DOC.items[0] && DOC.items[0].id);
  const shot = DOC.items.find(x=>x.id===shotId);
  const W = 1024, H = 1536;
  const c = compositeShot(shotId, W, H);
  const mime = EX_FMT === 'jpeg' ? 'image/jpeg' : 'image/png';
  const ext = EX_FMT === 'jpeg' ? 'jpg' : 'png';
  const url = c.toDataURL(mime, 0.92);

  const a = document.createElement('a');
  a.href = url;
  a.download = (shot ? shot.name : 'export') + '.' + ext;
  document.body.appendChild(a);
  a.click();
  a.remove();

  closeExport();

  const layers = layersOf(shotId);
  const vis = layers.filter(l=>l.visible !== false);
  if (typeof agAdd === 'function'){
    agAdd('ai', `导出好了：<b>${W}×${H} ${EX_FMT.toUpperCase()}</b>，`
      + `合成 <b>${vis.length} 层</b>。<br><br>`
      + `<span class="myown">这是真合出来的像素 —— 按图层顺序逐层画的，`
      + `filter 和混合模式都作用在像素上了。<br>`
      + `但<b>参数没被吃掉</b>：图导出了，图层还在文档里，随时能改再导一次。</span><br><br>`
      + `<b>没花钱</b> —— 本地合成。`);
  }
  toast('已导出 · ' + W + '×' + H + ' · 免费');
}
