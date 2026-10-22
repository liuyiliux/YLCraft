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
  /* ⭐ 2026-10-22 加：课程里讲「直方图看高光溢出和欠曝」，
     所以高光/阴影必须能单独压和提 —— 只靠曝光是把整张一起动。 */
  highlights: 0,    // -1 ~ +1   负=压高光，正=提高光
  shadows: 0,       // -1 ~ +1   正=提阴影，负=压阴影
  clarity: 0,       // -1 ~ +1   中间调对比（让画面「透」或「柔」）
  tint: 0,          // -1 ~ +1   色调：负=偏绿，正=偏品红
  /* ⭐ 2026-10-22 加：细节（锐化 / 降噪）和裁剪 */
  sharpen: 0,       // 0 ~ 1   锐化（USM 的反卷积近似）
  denoise: 0,       // 0 ~ 1   降噪（高斯，小半径）
  crop: '原图',     // 原图 | 1:1 | 4:3 | 3:4 | 16:9
  curve: [[0,0],[1,1]],   // 直线（PS 只有两个端点，中间的点是用户点出来的）
  curveMode: 'rgb'  // rgb | r | g | b
};

let LE_ID = null;   // 正在编辑的镜头 id
let LE_DRAG = -1;   // 正在拖的曲线点

/* ---- 曲线采样：分段线性 ---- */
/* ===== 曲线插值：单调三次 Hermite（PCHIP / Fritsch–Carlson）=====
   🔴 2026-10-20 用户指出「拉取的不够圆润」。
   之前是**分段线性**（点与点直连），所以曲线是折线、转折处是尖角。
   PS / Camera Raw 用的是「单调三次样条」：
     · 平滑（C1 连续，切线自然过渡）
     · 但保证不过冲 —— 单调区间内仍单调，不会甩出去
   这正是 PCHIP 的数学性质，所以用它。
*/
function curveTangents(pts){
  const n = pts.length;
  if (n < 2) return [0];
  const d = [];                       // 各段割线斜率
  for (let i = 0; i < n - 1; i++){
    const dx = pts[i+1][0] - pts[i][0];
    d.push(dx > 1e-9 ? (pts[i+1][1] - pts[i][1]) / dx : 0);
  }
  const m = new Array(n);
  m[0] = d[0];
  m[n-1] = d[n-2];
  for (let i = 1; i < n - 1; i++){
    if (d[i-1] * d[i] <= 0){
      m[i] = 0;                       // 极值点：切线归零，保证单调不过冲
    } else {
      const h0 = pts[i][0] - pts[i-1][0];
      const h1 = pts[i+1][0] - pts[i][0];
      const w1 = 2 * h1 + h0;
      const w2 = h1 + 2 * h0;
      m[i] = (w1 + w2) / (w1 / d[i-1] + w2 / d[i]);
    }
  }
  return m;
}

function curveSample(pts, x){
  if (!pts || !pts.length) return x;
  if (x <= pts[0][0]) return pts[0][1];
  const last = pts[pts.length-1];
  if (x >= last[0]) return last[1];

  /* 找所在区间 */
  let k = 0;
  while (k < pts.length - 2 && x > pts[k+1][0]) k++;

  const x0 = pts[k][0], x1 = pts[k+1][0];
  const y0 = pts[k][1], y1 = pts[k+1][1];
  const h = x1 - x0;
  if (h <= 1e-9) return Math.max(0, Math.min(1, y0));

  const m = curveTangents(pts);
  const t = (x - x0) / h;
  const t2 = t * t, t3 = t2 * t;

  /* Hermite 基函数 */
  const h00 = 2*t3 - 3*t2 + 1;
  const h10 = t3 - 2*t2 + t;
  const h01 = -2*t3 + 3*t2;
  const h11 = t3 - t2;

  const y = h00*y0 + h10*(m[k] * h) + h01*y1 + h11*(m[k+1] * h);
  return Math.max(0, Math.min(1, y));
}

/* ---- 曲线 → tableValues（这就是 LUT 的采样） ---- */
function curveToTable(pts, n = 64){
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
  const tbl = leLut(64).map(v=>v.toFixed(4)).join(' ');
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

/* ============ ⭐ 影调映射：高光 / 阴影 / 清晰度 ============
   为什么要在「曲线」之前单独做一层：
   高光和阴影不是同一个东西 —— 曝光拉整张，高光只动亮部，阴影只动暗部。
   课程里讲直方图看「高光溢出」，就是靠这一层单独压。
*/
function clamp01(v){ return v < 0 ? 0 : v > 1 ? 1 : v; }

function leToneMap(v){
  /* 图层采纳后，影调是「手动 + 各图层」叠加的。
     leComposeTone 由 17-channels.js 提供（那里管图层）。 */
  const a = (typeof leComposeTone === 'function') ? leComposeTone() : LOCAL_ADJ;
  // 高光：权重随亮度平方增长（只动亮部）
  if (a.highlights !== 0){
    const w = v * v;
    v = clamp01(v + a.highlights * 0.28 * w);
  }
  // 阴影：权重随暗度平方增长（只动暗部）
  if (a.shadows !== 0){
    const w = (1 - v) * (1 - v);
    v = clamp01(v + a.shadows * 0.28 * w);
  }
  // 清晰度：中间调加 S 形（不碰两端，所以不会吃掉高光阴影细节）
  if (a.clarity !== 0){
    const mid = 1 - Math.abs(v * 2 - 1);       // 中间调权重
    const s = Math.sin((v - 0.5) * Math.PI);   // -1~1 的 S 推动
    v = clamp01(v + a.clarity * 0.16 * s * mid);
  }
  return v;
}

/* 完整 LUT：影调 → 用户曲线 */
function leLut(n = 64){
  const out = [];
  for (let i = 0; i < n; i++){
    let v = i / (n - 1);
    v = leToneMap(v);
    v = curveSample(LOCAL_ADJ.curve, v);
    out.push(clamp01(v));
  }
  return out;
}

/* ============ ⭐ 直方图 ============
   从真实像素算，不是画个假图形。
   参数一变它就跟着变 —— 压高光看到右边那块降下来，就是真的。
*/
let LE_SRC_PIX = null;   // 缓存的源像素亮度数组（0~1）

function leBuildSourcePixels(){
  if (LE_SRC_PIX) return LE_SRC_PIX;
  const W = 180, H = 240;
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d', { willReadFrequently: true });

  // 背景（和演示图一样的渐变）
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, '#2b2440'); g.addColorStop(1, '#141020');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

  // 人物（暖肤渐变）
  const fg = ctx.createLinearGradient(0, H * 0.18, 0, H * 0.82);
  fg.addColorStop(0, '#e8d5bd'); fg.addColorStop(1, '#a8825c');
  ctx.fillStyle = fg;
  ctx.beginPath();
  ctx.ellipse(W * 0.5, H * 0.5, W * 0.10, H * 0.34, 0, 0, Math.PI * 2);
  ctx.fill();

  const d = ctx.getImageData(0, 0, W, H).data;
  const out = new Float32Array(W * H);
  for (let i = 0, j = 0; i < d.length; i += 4, j++){
    // 感知亮度
    out[j] = (d[i] * 0.299 + d[i+1] * 0.587 + d[i+2] * 0.114) / 255;
  }
  LE_SRC_PIX = out;
  return out;
}

function leDrawHistogram(){
  const cv = document.getElementById('leHistCv');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);

  const pix = leBuildSourcePixels();
  const lut = leLut(64);
  const BINS = 64;
  const hist = new Array(BINS).fill(0);

  let over = 0, under = 0;
  for (let i = 0; i < pix.length; i++){
    let v = pix[i];
    // 曝光（和 CSS brightness 一致）
    v = clamp01(v * (1 + LOCAL_ADJ.exposure * 0.35));
    // LUT（影调 + 曲线）
    const fi = v * (BINS - 1);
    const lo = Math.floor(fi), hi = Math.min(BINS - 1, lo + 1);
    v = lut[lo] + (lut[hi] - lut[lo]) * (fi - lo);
    v = clamp01(v);
    hist[Math.min(BINS - 1, Math.floor(v * (BINS - 1)))]++;
    if (v > 0.995) over++;
    if (v < 0.005) under++;
  }

  const max = Math.max(...hist) || 1;
  const bw = W / BINS;
  for (let b = 0; b < BINS; b++){
    const h = (hist[b] / max) * (H - 6);
    // 颜色：暗部偏蓝、中间灰、亮部偏暖
    const t = b / (BINS - 1);
    const r = Math.round(110 + t * 130);
    const gg = Math.round(120 + t * 90);
    const bb = Math.round(190 - t * 110);
    ctx.fillStyle = 'rgba(' + r + ',' + gg + ',' + bb + ',0.85)';
    ctx.fillRect(b * bw, H - h, Math.max(1, bw - 0.6), h);
  }

  // 底部基线
  ctx.fillStyle = 'rgba(255,255,255,.12)';
  ctx.fillRect(0, H - 1, W, 1);

  // 溢出提示
  const total = pix.length;
  const op = (over / total * 100).toFixed(1);
  const up = (under / total * 100).toFixed(1);
  const info = document.getElementById('leHistInfo');
  if (info){
    info.textContent = '过曝 ' + op + '% · 欠曝 ' + up + '%';
    info.style.color = (over / total > 0.02 || under / total > 0.05)
      ? 'var(--wn)' : 'var(--tx3)';
  }
}

/* ---- 汇总成 CSS filter 串 ---- */
function leFilterCSS(){
  ensureCurveFilter();
  /* 同上：标量参数也走叠加版 */
  const a = (typeof leComposeScalars === 'function') ? leComposeScalars() : LOCAL_ADJ;
  if (a.vignette == null) a.vignette = LOCAL_ADJ.vignette || 0;
  if (a.grain == null) a.grain = LOCAL_ADJ.grain || 0;
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
  // 色调：负=偏绿，正=偏品红
  if (Math.abs(a.tint) > 0.02){
    const g = a.tint < 0;
    parts.push(`hue-rotate(${(a.tint * (g ? -12 : 12)).toFixed(1)}deg)`);
  }
  /* ⭐ 细节：降噪先做（去噪点），锐化后做（找回边缘）—— 顺序不能反 */
  if (typeof leEnsureDetailFilters === 'function'){
    leEnsureDetailFilters(a.denoise, a.sharpen);
    if (a.denoise > 0.01) parts.push('url(#leDenoise)');
    if (a.sharpen > 0.01) parts.push('url(#leSharpen)');
  }
  /* 暗角（CSS filter 没这个原语，用对比微调 + 容器阴影补）*/
  if (a.vignette > 0.01){
    parts.push('contrast(' + (1 + a.vignette * 0.06).toFixed(3) + ')');
  }
  /* 颗粒：SVG 噪点 */
  if (a.grain > 0.01 && typeof leEnsureGrain === 'function'){
    leEnsureGrain();
    parts.push('url(#leGrainF)');
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
            <div class="le-sec">直方图 <span class="le-sec2">参数一变它就跟着变</span></div>
            <div class="le-histo">
              <canvas id="leHistCv" width="256" height="64"></canvas>
              <div class="le-histo-l"><span>暗</span>
                <span id="leHistInfo">—</span><span>亮</span></div>
            </div>

            <div class="le-sec">基础</div>
            ${leSlider('exposure','曝光','EV',-2,2,0.05)}
            ${leSlider('contrast','对比度','',0.5,1.5,0.01)}
            ${leSlider('saturation','饱和度','',0,2,0.01)}
            ${leSlider('temp','色温','K',4000,8000,50)}
            ${leSlider('tint','色调','',-1,1,0.02)}

            <div class="le-sec">影调 <span class="le-sec2">只动亮部 / 只动暗部</span></div>
            ${leSlider('highlights','高光','',-1,1,0.02)}
            ${leSlider('shadows','阴影','',-1,1,0.02)}
            ${leSlider('clarity','清晰度','',-1,1,0.02)}

            <div class="le-sec">曲线 <span class="le-sec2">RGB 合成</span>
              <button class="le-reset" onclick="leResetCurve()">拉直</button><span class="le-curvecnt" id="leCurveCount"></span>
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
            <div class="le-hint">点空白处加点（最多 8 点）· 拖点改曲线 · 双击拉直 · 双击恢复</div>
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
  // 高光/阴影/清晰度/色调是双向的，带符号更清楚
  if (['highlights','shadows','clarity','tint'].includes(key))
    return (v >= 0 ? '+' : '') + v.toFixed(2);
  if (key === 'sharpen' || key === 'denoise') return (v * 100).toFixed(0) + '%';
  return v.toFixed(2);
}

function leSet(key, v){
  /* ⭐ 2026-10-22：选中了图层就改那个图层，否则改基础参数。
     用户指出「点采纳图片有变化，右边参数没变化」，这里就是根因。 */
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  t[key] = Number(v);
  const el = document.getElementById('leVal_' + key);
  if (el) el.textContent = leFmt(key, Number(v)) + (key==='temp'?'K':'') + (key==='exposure'?'EV':'');
  leApplyPreview();
  if (typeof leMarkLayerDirty === 'function') leMarkLayerDirty();
  if (typeof leSnap === 'function') leSnap();
}

/* ---- 曲线交互 ---- */
function leCurveXYtoPct(e){
  const svg = document.getElementById('leCurveSvg');
  const r = svg.getBoundingClientRect();
  const x = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  const y = Math.max(0, Math.min(1, 1 - (e.clientY - r.top) / r.height));
  return [x, y];
}

/* ===== PS / Camera Raw 曲线交互规范 =====
   依据 PhotoCraft（净室重实现，MIT/Apache-2.0）crates/ui-egui/src/point_curve.rs：
     MAX_POINTS = 16        点数上限（PS 是 16，我们之前只给 8）
     MIN_GAP    = 2/255     输入差小于这个就视为同一个点
     can_delete: pts.len()>2 && i>0 && i<len-1   首尾删不掉、至少留 2 点
   交互：
     左键点空白 → 加点并开始拖
     左键点已有点 → 选中拖动
     右键 / Ctrl+左键 点已有点 → 删掉（首尾和最少 2 点时删不掉）
*/
const LE_CURVE_MAX = 16;
const LE_CURVE_GAP = 2 / 255;
const LE_HIT_RADIUS = 0.05;

function leCurveHit(pts, x, y){
  let best = -1, bd = 1e9;
  pts.forEach((p, i)=>{
    const d = Math.hypot(p[0] - x, p[1] - y);
    if (d < bd && d <= LE_HIT_RADIUS){ bd = d; best = i; }
  });
  return best;
}

function leCurveInsert(pts, x, y){
  /* 附近已有 → 直接选它，不重复加点 */
  const near = pts.findIndex(p => Math.abs(p[0] - x) < LE_CURVE_GAP);
  if (near >= 0) return near;
  if (pts.length >= LE_CURVE_MAX) return -1;
  pts.push([x, y]);
  pts.sort((a, b) => a[0] - b[0]);
  return pts.findIndex(p => p[0] === x && p[1] === y);
}

function leCurveDel(i){
  const pts = LOCAL_ADJ.curve;
  /* PS 规则：至少留 2 点，首尾不能删 */
  if (pts.length <= 2 || i <= 0 || i >= pts.length - 1){
    toast('首尾两点删不掉（曲线至少留 2 个点）');
    return false;
  }
  pts.splice(i, 1);
  leRenderCurve();
  leApplyPreview();
  toast('删掉一个控制点 · 还剩 ' + pts.length + ' 点');
  return true;
}

function leCurveDown(e){
  const [x, y] = leCurveXYtoPct(e);
  const pts = LOCAL_ADJ.curve;
  const hit = leCurveHit(pts, x, y);

  /* 右键 / Ctrl+左键：删点 */
  const wantDel = (e.button === 2) || (e.ctrlKey || e.metaKey);
  if (wantDel){
    if (hit >= 0) leCurveDel(hit);
    LE_DRAG = -1;
    return;
  }

  if (hit >= 0){
    LE_DRAG = hit;
  } else {
    const idx = leCurveInsert(pts, x, y);
    if (idx < 0){
      LE_DRAG = -1;
      toast('已经 ' + LE_CURVE_MAX + ' 个点了（PS 上限就是 16）');
      return;
    }
    LE_DRAG = idx;
  }
  leCurveMove(e);
}

function leCurveMove(e){
  if (LE_DRAG < 0) return;
  const pts = LOCAL_ADJ.curve;
  let [x, y] = leCurveXYtoPct(e);
  /* 首尾固定 x，中间点不能越过邻居 */
  if (LE_DRAG === 0) x = 0;
  else if (LE_DRAG === pts.length - 1) x = 1;
  else {
    const lo = pts[LE_DRAG-1][0] + 0.008;
    const hi = pts[LE_DRAG+1][0] - 0.008;
    x = Math.max(lo, Math.min(hi, x));
  }
  y = Math.max(0, Math.min(1, y));
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
    const isEnd = (i === 0 || i === pts.length - 1);
    /* 🔧 2026-10-20：首尾点原本就存在，但贴在角落看不清，用户以为只有 3 个点。
       给首尾单独样式（稍大 + 亮描边），并给每个点加 title 提示。 */
    return `<circle cx="${px}" cy="${py}" r="${isEnd ? 6 : 5}"
      class="le-dot ${i===LE_DRAG?'on':''} ${isEnd?'end':''}"
      data-idx="${i}"><title>第 ${i+1}/${pts.length} 点 · 拖动改曲线</title></circle>`;
  }).join('');

  /* 点数提示，让用户知道还能加点 */
  const cnt = document.getElementById('leCurveCount');
  if (cnt) cnt.textContent = pts.length + ' 点' + (pts.length < 16 ? ' · 点空白处加点' : '（已满 16 点）');
}

function leResetCurve(){
  /* PS 的「拉直」= 回到只有两端点的直线 */
  LOCAL_ADJ.curve = [[0,0],[1,1]];
  leRenderCurve(); leApplyPreview();
}

function leResetAll(){
  Object.assign(LOCAL_ADJ, {
    exposure:0, contrast:1, saturation:1, temp:6100, gamma:1,
    highlights:0, shadows:0, clarity:0, tint:0,
    curve:[[0,0],[1,1]]
  });
  leRenderAll();
  toast('已重置 · 回到原图');
}

function leRenderAll(){
  // 滑块值
  ['exposure','contrast','saturation','temp','tint','highlights','shadows','clarity'].forEach(k=>{
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
  /* 暗角：容器内阴影，比 filter 更像真的暗角 */
  if (img){
    const a = (typeof leComposeScalars === 'function') ? leComposeScalars() : LOCAL_ADJ;
    const v = (a.vignette != null ? a.vignette : (LOCAL_ADJ.vignette || 0));
    img.style.boxShadow = v > 0.01
      ? 'inset 0 0 ' + (v * 140).toFixed(0) + 'px ' + (v * 55).toFixed(0)
        + 'px rgba(0,0,0,' + (v * 0.85).toFixed(2) + ')'
      : '';
  }
  if (typeof leDrawHistogram === 'function') leDrawHistogram();
  /* ⭐ 2026-10-22：17-channels.js 覆盖了面板（带色阶/通道/真直方图），
     它的重绘函数要在这里触发，否则拖滑块直方图不动。 */
  if (typeof leRenderHist === 'function') leRenderHist();
  if (typeof leRenderCurve === 'function') leRenderCurve();
  /* 区域图层的叠加层 */
  if (typeof leRenderFx === 'function') leRenderFx();
  /* 课程：下手别太狠 */
  if (typeof leCheckHarsh === 'function') leCheckHarsh();
  if (typeof leSkinApplyPreview === 'function') leSkinApplyPreview();
  if (typeof leAutoSave === 'function') leAutoSave();
}

function closeLocalEdit(){
  document.getElementById('overlayHost').innerHTML = '';
  LE_ID = null;
}

function leApply(){
  const a = LOCAL_ADJ;
  const changes = [];
  if (Math.abs(a.exposure) > 0.01) changes.push(`曝光 ${(a.exposure>=0?'+':'')}${a.exposure.toFixed(2)}EV`);
  if (Math.abs(a.contrast-1) > 0.01) changes.push(`对比度 ${a.contrast.toFixed(2)}`);
  if (Math.abs(a.saturation-1) > 0.01) changes.push(`饱和度 ${a.saturation.toFixed(2)}`);
  if (Math.abs(a.temp-6100) > 30) changes.push(`色温 ${Math.round(a.temp)}K`);
  if (Math.abs(a.tint) > 0.02) changes.push(`色调 ${a.tint.toFixed(2)}`);
  if (Math.abs(a.highlights) > 0.02) changes.push(`高光 ${a.highlights.toFixed(2)}`);
  if (Math.abs(a.shadows) > 0.02) changes.push(`阴影 ${a.shadows.toFixed(2)}`);
  if (Math.abs(a.clarity) > 0.02) changes.push(`清晰度 ${a.clarity.toFixed(2)}`);
  const curveChanged = a.curve.some(p=>Math.abs(p[1]-p[0]) > 0.02);
  if (curveChanged) changes.push('曲线');

  closeLocalEdit();

  /* 🔧 2026-10-20 修（审查报告阻断问题 4）：之前只往对话发一条，
     画布参数一个字节没变。现在真写进图层，画面/导出/撤销都带上。 */
  let committed = null;
  if (changes.length && typeof commitLocalLayer === 'function'){
    committed = commitLocalLayer(
      '精调：' + changes.slice(0, 2).join(' '),
      {
        exposure: a.exposure, contrast: a.contrast, saturation: a.saturation,
        temp: a.temp,
        levels: JSON.parse(JSON.stringify(a.levels || {})),
        curves: JSON.parse(JSON.stringify(a.curves || null))
      },
      '应用精调：' + changes.join(' · ')
    );
  }

  agAdd('ai', changes.length
    ? `调好了：${changes.join(' · ')}<br><br><b>没花钱</b> —— 这是本地像素运算。<br><br>`
      + `<span class="myown">${committed ? '参数已经挂成一层了：画面能看出来、导出会带上、撤销能退。' : ''}`
      + `参数我留着了，不是烘焙进图里的。你哪天想改回去，点开还能调。</span>`
    : `没改任何参数，图还是原样。`);
  toast(changes.length ? '已应用 · 免费' : '没改动');
}


