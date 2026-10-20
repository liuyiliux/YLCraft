/* 13-localedit.js - split from canvas_unified_v14.html (lines 3214-3508) */
/* ================= 本地精调（曲线 / 色阶 / 曝光 / 白平衡）=================
   🔴 这一层是真的免费：纯像素运算，不调任何模型。
   而且非破坏性 —— 参数留着，随时能改回去。

   技术上：SVG feComponentTransfer type="table" 就是 LUT，
   拖曲线点 → 重算 tableValues → 浏览器实时重绘。
*/

const LOCAL_ADJ = {
  exposure: 0,      // -2 ~ +2 EV
  contrast: 1,      // 0.5 ~ 1.5
  saturation: 1,    // 0 ~ 2
  temp: 6100,       // 色温 K（目标值）
  gamma: 1,
  curve: [[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]],   // 直线
  curveMode: 'rgb'  // rgb | r | g | b
};

let LE_ID = null;   // 正在编辑的镜头 id
let LE_DRAG = -1;   // 正在拖的曲线点

/* ---- 曲线采样：分段线性 ---- */
function curveSample(pts, x){
  if (x <= pts[0][0]) return pts[0][1];
  const last = pts[pts.length-1];
  if (x >= last[0]) return last[1];
  let k = 0;
  while (k < pts.length - 2 && x > pts[k+1][0]) k++;
  const x0=pts[k][0], x1=pts[k+1][0], y0=pts[k][1], y1=pts[k+1][1];
  const t = x1 === x0 ? 0 : (x - x0) / (x1 - x0);
  return Math.max(0, Math.min(1, y0 + (y1 - y0) * t));
}

/* ---- 曲线 → tableValues（这就是 LUT 的采样） ---- */
function curveToTable(pts, n = 16){
  const out = [];
  for (let i = 0; i < n; i++) out.push(curveSample(pts, i / (n - 1)));
  return out;
}

/* ---- 生成 / 更新 SVG filter ---- */
function ensureCurveFilter(){
  let svg = document.getElementById('leSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.id = 'leSvg';
    svg.setAttribute('width','0'); svg.setAttribute('height','0');
    svg.style.position = 'absolute'; svg.style.pointerEvents = 'none';
    document.body.appendChild(svg);
  }
  const tbl = curveToTable(LOCAL_ADJ.curve).map(v=>v.toFixed(4)).join(' ');
  svg.innerHTML = `<defs>
    <filter id="leCurve" color-interpolation-filters="sRGB">
      <feComponentTransfer>
        <feFuncR type="table" tableValues="${tbl}"/>
        <feFuncG type="table" tableValues="${tbl}"/>
        <feFuncB type="table" tableValues="${tbl}"/>
      </feComponentTransfer>
    </filter>
  </defs>`;
}

/* ---- 汇总成 CSS filter 串 ---- */
function leFilterCSS(){
  ensureCurveFilter();
  const a = LOCAL_ADJ;
  const parts = [
    'url(#leCurve)',
    `brightness(${(1 + a.exposure * 0.35).toFixed(3)})`,
    `contrast(${a.contrast.toFixed(3)})`,
    `saturate(${a.saturation.toFixed(3)})`
  ];
  // 色温：低于 6100 偏暖（sepia 微调），高于偏冷
  const t = (a.temp - 6100) / 2000;   // -1 ~ +1 左右
  if (Math.abs(t) > 0.02){
    parts.push(`sepia(${Math.max(0,t*0.28).toFixed(3)})`);
    parts.push(`hue-rotate(${(-t*14).toFixed(1)}deg)`);
  }
  return parts.join(' ');
}

/* ---- 打开面板 ---- */
function openLocalEdit(id){
  LE_ID = id || selId || (DOC.items[0] && DOC.items[0].id);
  const s = DOC.items.find(x=>x.id===LE_ID);
  if (!s){ toast('先选一张图'); return; }
  hideFloatBar();
  const pic = s.thumbUrl || '';
  const dims = s.canvas ? (s.canvas.width + '×' + s.canvas.height) : (s.w + '×' + s.h);

  document.getElementById('overlayHost').innerHTML = `
    <div class="le" onclick="if(event.target.classList.contains('lew'))closeLocalEdit()">
      <div class="lew">
        <div class="le-hd">
          <div class="le-t">本地精调 · ${esc(s.name)}</div>
          <span class="le-free">免费</span>
          <span class="le-nb">非破坏</span>
          <button class="inp-x" onclick="closeLocalEdit()">✕</button>
        </div>

        <div class="le-body">
          <div class="le-stage">
            <div class="le-img${pic?' has-pic':''}" id="leImg"${pic?` style="width:100%;height:min(58vh,440px);aspect-ratio:auto;background-image:url('${pic}');background-size:contain;background-position:center;background-repeat:no-repeat;background-color:#0b0b0f"`:''}>
              ${pic?'':'<div class="le-fig"></div>'}
            </div>
            <div class="le-tag">${pic ? '真实图片预览 · ' + dims : '演示图预览 · 导入图片后这里显示你自己的图'} · 拖动左边参数看效果</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">基础</div>
            ${leSlider('exposure','曝光','EV',-2,2,0.05)}
            ${leSlider('contrast','对比度','',0.5,1.5,0.01)}
            ${leSlider('saturation','饱和度','',0,2,0.01)}
            ${leSlider('temp','色温','K',4000,8000,50)}

            <div class="le-sec">曲线 <span class="le-sec2">RGB 合成</span>
              <button class="le-reset" onclick="leResetCurve()">拉直</button>
            </div>
            <div class="le-curvewrap">
              <svg class="le-curve" id="leCurveSvg" viewBox="0 0 200 200"
                   onmousedown="leCurveDown(event)" onmousemove="leCurveMove(event)"
                   onmouseup="leCurveUp(event)" onmouseleave="leCurveUp(event)" ondblclick="leResetCurve()">
                <line x1="0" y1="200" x2="200" y2="0" class="le-diag"/>
                <g id="leGrid">
                  <line x1="50" y1="0" x2="50" y2="200" class="le-grid"/>
                  <line x1="100" y1="0" x2="100" y2="200" class="le-grid"/>
                  <line x1="150" y1="0" x2="150" y2="200" class="le-grid"/>
                  <line x1="0" y1="50" x2="200" y2="50" class="le-grid"/>
                  <line x1="0" y1="100" x2="200" y2="100" class="le-grid"/>
                  <line x1="0" y1="150" x2="200" y2="150" class="le-grid"/>
                </g>
                <path id="lePath" class="le-path" d=""/>
                <g id="lePts"></g>
              </svg>
            </div>
            <div class="le-hint">拖中间的点做 S 曲线 · 双击恢复</div>
          </div>
        </div>

        <div class="le-foot">
          <div class="le-cost">
            花费 <b class="le-zero">0</b>
            <span class="le-costn">本地像素运算 · 不走模型 · 参数留着随时能改</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="leResetAll()">全部重置</button>
            <button class="insp-b pri" onclick="leApply()">应用</button>
          </div>
        </div>
      </div>
    </div>`;

  leRenderAll();
}

function leSlider(key, label, unit, min, max, step){
  const v = LOCAL_ADJ[key];
  return `<div class="le-row">
    <span class="le-l">${label}</span>
    <input type="range" class="le-r" min="${min}" max="${max}" step="${step}" value="${v}"
      oninput="leSet('${key}', this.value)">
    <span class="le-v" id="leVal_${key}">${leFmt(key,v)}${unit}</span>
  </div>`;
}

function leFmt(key, v){
  v = Number(v);
  if (key === 'exposure') return (v >= 0 ? '+' : '') + v.toFixed(2);
  if (key === 'temp') return String(Math.round(v));
  return v.toFixed(2);
}

function leSet(key, v){
  LOCAL_ADJ[key] = Number(v);
  const el = document.getElementById('leVal_' + key);
  if (el) el.textContent = leFmt(key, Number(v)) + (key==='temp'?'K':'') + (key==='exposure'?'EV':'');
  leApplyPreview();
}

/* ---- 曲线交互 ---- */
function leCurveXYtoPct(e){
  const svg = document.getElementById('leCurveSvg');
  const r = svg.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const y = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height));
  return [x, y];
}

function leCurveDown(e){
  const [x, y] = leCurveXYtoPct(e);
  const pts = LOCAL_ADJ.curve;
  // 找最近的点
  let best = -1, bd = 1e9;
  pts.forEach((p, i)=>{
    const d = Math.hypot(p[0]-x, p[1]-y);
    if (d < bd){ bd = d; best = i; }
  });
  // 太远就在旁边插一个
  if (bd > 0.12 && pts.length < 8){
    pts.push([x, y]);
    pts.sort((a,b)=>a[0]-b[0]);
    best = pts.findIndex(p=>p[0]===x && p[1]===y);
  }
  LE_DRAG = best;
  leCurveMove(e);
}

function leCurveMove(e){
  if (LE_DRAG < 0) return;
  const pts = LOCAL_ADJ.curve;
  let [x, y] = leCurveXYtoPct(e);
  // 首尾固定 x
  if (LE_DRAG === 0) x = 0;
  else if (LE_DRAG === pts.length - 1) x = 1;
  else {
    x = Math.max(pts[LE_DRAG-1][0] + 0.03, Math.min(pts[LE_DRAG+1][0] - 0.03, x));
  }
  pts[LE_DRAG] = [x, y];
  leRenderCurve();
  leApplyPreview();
}

function leCurveUp(){ LE_DRAG = -1; }

function leRenderCurve(){
  const pts = LOCAL_ADJ.curve;
  const toPx = p => [p[0]*200, (1-p[1])*200];
  // path：直接用控制点连线（和实际 LUT 采样一致）
  let d = '';
  const N = 60;
  for (let i = 0; i <= N; i++){
    const x = i/N;
    const y = curveSample(pts, x);
    d += (i===0?'M':'L') + (x*200).toFixed(1) + ',' + ((1-y)*200).toFixed(1) + ' ';
  }
  const pathEl = document.getElementById('lePath');
  if (pathEl) pathEl.setAttribute('d', d);
  const g = document.getElementById('lePts');
  if (g) g.innerHTML = pts.map((p,i)=>{
    const [px,py] = toPx(p);
    return `<circle cx="${px}" cy="${py}" r="5" class="le-dot ${i===LE_DRAG?'on':''}"/>`;
  }).join('');
}

function leResetCurve(){
  LOCAL_ADJ.curve = [[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]];
  leRenderCurve(); leApplyPreview();
}

function leResetAll(){
  Object.assign(LOCAL_ADJ, {
    exposure:0, contrast:1, saturation:1, temp:6100, gamma:1,
    curve:[[0,0],[0.25,0.25],[0.5,0.5],[0.75,0.75],[1,1]]
  });
  leRenderAll();
  toast('已重置 · 回到原图');
}

function leRenderAll(){
  // 滑块值
  ['exposure','contrast','saturation','temp'].forEach(k=>{
    const input = document.querySelector(`.le-r[oninput*="${k}"]`);
    if (input) input.value = LOCAL_ADJ[k];
    const el = document.getElementById('leVal_' + k);
    if (el) el.textContent = leFmt(k, LOCAL_ADJ[k]) + (k==='temp'?'K':'') + (k==='exposure'?'EV':'');
  });
  leRenderCurve();
  leApplyPreview();
}

function leApplyPreview(){
  const img = document.getElementById('leImg');
  if (img) img.style.filter = leFilterCSS();
}

function closeLocalEdit(){
  document.getElementById('overlayHost').innerHTML = '';
  LE_ID = null;
}

function leApply(){
  closeLocalEdit();
  const a = LOCAL_ADJ;
  const changes = [];
  if (Math.abs(a.exposure) > 0.01) changes.push(`曝光 ${(a.exposure>=0?'+':'')}${a.exposure.toFixed(2)}EV`);
  if (Math.abs(a.contrast-1) > 0.01) changes.push(`对比度 ${a.contrast.toFixed(2)}`);
  if (Math.abs(a.saturation-1) > 0.01) changes.push(`饱和度 ${a.saturation.toFixed(2)}`);
  if (Math.abs(a.temp-6100) > 30) changes.push(`色温 ${Math.round(a.temp)}K`);
  const curveChanged = a.curve.some(p=>Math.abs(p[1]-p[0]) > 0.02);
  if (curveChanged) changes.push('曲线');

  agAdd('ai', changes.length
    ? `调好了：${changes.join(' · ')}<br><br><b>没花钱</b> —— 这是本地像素运算。<br><br>`
      + `<span class="myown">参数我留着了，不是烘焙进图里的。你哪天想改回去，点开还能调。</span>`
    : `没改任何参数，图还是原样。`);
  toast(changes.length ? '已应用 · 免费' : '没改动');
}


