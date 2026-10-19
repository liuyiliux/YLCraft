/* 16-export.js - split from canvas_unified_v14.html (lines 3800-3966) */
/* ================= 非破坏性编辑：文档层 / 预览层 / 导出层 =================
   🔴 2026-10-19 用户纠正：
   「曲线导出成真图」这个说法是错的。
   正确模型和 PS 一样：
     ① 文档层：存参数，不存像素
     ② 预览层：画布上实时渲染（看到的就是最终的）
     ③ 导出层：只在导出时按顺序合成

   原型阶段「先把位置占上」—— 这里把三层的数据结构和入口占住，
   具体合成实现后做。
*/

/* ---------- 一层调整（本地，免费）---------- */
function makeLocalLayer(){
  return {
    id: 'adj_' + Date.now(),
    type: 'local',            // local | ai
    name: '本地精调',
    visible: true,
    opacity: 1,
    params: {
      exposure: 0,
      contrast: 1,
      saturation: 1,
      temp: 6100,
      curve: [[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]]
    },
    cost: 0                     // 🔴 本地层永远 0
  };
}

/* ---------- 一层 AI 编辑（花钱）---------- */
function makeAiLayer(kind, params){
  return {
    id: 'ai_' + Date.now(),
    type: 'ai',
    kind,                       // 'inpaint' | 'outpaint' | 'regenerate' | 'lighting'
    name: { inpaint:'局部重绘', outpaint:'扩展画布',
            regenerate:'重画这一镜', lighting:'改光照方向' }[kind] || kind,
    visible: true,
    opacity: 1,
    mask: null,                 // 蒙版（白=要改的区域）
    params: params || {},
    cost: 14,
    resultAsset: null           // 结果图，合成时用
  };
}

/* ---------- 镜头文档结构（占位）---------- */
/* 真实实现时应该落在 CanvasDocument.document_json 里 */
const SHOT_DOC_DEMO = {
  id: 'shot_3',
  source: { assetId: 'asset_9f2a', w: 1024, h: 1536, bitDepth: 8, colorSpace: 'sRGB' },
  layers: [
    makeLocalLayer(),
    makeAiLayer('lighting', { direction: 35 })
  ],
  export: { format: 'png', quality: 95, scale: 1 },
  history: []                   // 撤销栈
};

/* ---------- 导出面板（占住位置）---------- */
function openExport(){
  const shot = DOC.items.find(x=>x.id===selId) || DOC.items[0];
  if (!shot){ toast('先选一张图'); return; }
  hideFloatBar();

  const layers = [
    { n:'本地精调', t:'local', c:'免费', d:'曝光 +0.80EV · 色温 7200K · S 曲线' },
    { n:'改光照方向', t:'ai', c:'⚡14', d:'蒙版重绘 · 结果已缓存' }
  ];

  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="if(event.target.classList.contains('exw'))closeExport()">
      <div class="exw">
        <div class="inp-hd">
          <div class="inp-t">导出</div>
          <div class="inp-sub">${esc(shot.name)} · 把下面这些层按顺序合成</div>
          <button class="inp-x" onclick="closeExport()">✕</button>
        </div>

        <div class="ex-body">
          <div class="ex-sec">
            <span class="ex-st">合成顺序</span>
            <span class="ex-s2">从上到下依次应用 · 参数不烘焙，随时能改</span>
          </div>

          <div class="ex-stack">
            ${layers.map((l,i)=>`
              <div class="ex-layer ${l.t}">
                <span class="ex-n">${i+1}</span>
                <span class="ex-ln">${l.n}</span>
                <span class="ex-lt ${l.t}">${l.t==='local'?'本地':'调模型'}</span>
                <span class="ex-lc ${l.t==='local'?'free':''}">${l.c}</span>
              </div>
              <div class="ex-ld">${l.d}</div>
            `).join('')}
            <div class="ex-layer src">
              <span class="ex-n">0</span>
              <span class="ex-ln">原图</span>
              <span class="ex-lt src">源</span>
              <span class="ex-lc">—</span>
            </div>
          </div>

          <div class="ex-sec"><span class="ex-st">导出设置</span></div>
          <div class="ex-grid">
            <div class="ex-gi"><span class="ex-gk">格式</span>
              <select class="ex-sel" onchange="toast('格式：'+this.value)">
                <option>PNG（无损）</option><option>JPEG 95</option>
                <option>WebP 90</option><option>TIFF 16bit</option>
              </select>
            </div>
            <div class="ex-gi"><span class="ex-gk">尺寸</span>
              <select class="ex-sel" onchange="toast('尺寸：'+this.value)">
                <option>原尺寸 1024×1536</option><option>2 倍 2048×3072</option>
                <option>Web 1200 宽</option>
              </select>
            </div>
          </div>

          <div class="ex-key">
            🔴 <b>导出才合成</b> —— 画布上你看到的一直是实时预览（参数渲染），
            只有点这里才会真正把像素算出来。<br>
            <span class="ex-key2">所以导出之前，任何一步都还能改回去。</span>
          </div>

          <div class="ex-todo">
            <span class="ex-td">占位</span>
            真实合成需要：① 把 local 层的参数应用到像素 ② 把 AI 层的结果按蒙版贴回去
            ③ 按 opacity 混合 ④ 按格式编码。<b>具体实现后做。</b>
          </div>
        </div>

        <div class="ex-foot">
          <div class="ex-cost">
            导出花费 <b class="le-zero">0</b>
            <span class="ex-costn">合成是本地处理 · 除非选 2 倍放大要调模型</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="closeExport()">取消</button>
            <button class="insp-b pri" onclick="exDo()">导出 PNG</button>
          </div>
        </div>
      </div>
    </div>`;
}

function closeExport(){ document.getElementById('overlayHost').innerHTML = ''; }

function exDo(){
  closeExport();
  agAdd('ai', `导出好了 —— <b>PNG · 1024×1536 · 花了 0</b>。<br><br>`
    + `合成了 2 层：本地精调（曝光/色温/曲线）+ 改光照方向。<br><br>`
    + `<span class="myown">原图和各层参数都还在，随时能改完再导一次。`
    + `这次导出不会把参数烘焙掉。</span>`);
  toast('已导出 · 免费');
}

/* ---------- 在浮条加「导出」入口 ---------- */
const _fbAct = fbAct;
fbAct = function(act){
  if (act === 'export'){ openExport(); return; }
  _fbAct(act);
};


