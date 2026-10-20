/* 17-channels.js - split from canvas_unified_v14.html (lines 3967-4279) */
/* ================= 分通道曲线 / 色阶 / 直方图 =================
   全部本地运算，仍然免费。
   实现要点：
     ① 色阶先作用，曲线后作用 → 合成一个 LUT 塞给 feComponentTransfer
     ② 三个通道各一条曲线（默认跟随 RGB 合成）
     ③ 直方图用当前参数模拟分布（真实现要从像素算）
*/

/* 扩展 LOCAL_ADJ */
LOCAL_ADJ.levels = { black: 0, white: 1, gamma: 1 };
LOCAL_ADJ.channel = 'rgb';          // 当前编辑的通道
/* 🔴 2026-10-20 按 PS / Camera Raw 改：曲线初始**只有两个端点**，中间没有预设点。
   依据 PhotoCraft（净室重实现，MIT/Apache）：
     crates/ui-egui/src/point_curve.rs、camera_raw_ui.rs、adjust_dialog.rs 等 7 处
     都是 vec![[0.0, 0.0], [255.0, 255.0]]
   它的 can_delete() 判定：pts.len() > 2 && i > 0 && i < len-1
   —— 至少保留 2 个点，首尾删不掉，中间点都是用户点出来的。
   之前我们固定 5 个点（0/0.25/0.5/0.75/1），这就是"看起来像预设点"的原因。 */
LOCAL_ADJ.curves = {                // 四个通道各一套点（初始都是直线 = 两端点）
  rgb: [[0,0],[1,1]],
  r:   [[0,0],[1,1]],
  g:   [[0,0],[1,1]],
  b:   [[0,0],[1,1]]
};

/* 兼容旧字段：LOCAL_ADJ.curve 指向当前通道 */
Object.defineProperty(LOCAL_ADJ, 'curve', {
  get(){ return LOCAL_ADJ.curves[LOCAL_ADJ.channel]; },
  set(v){ LOCAL_ADJ.curves[LOCAL_ADJ.channel] = v; }
});

/* ---- 色阶 + 曲线 → 最终 LUT ---- */
function applyLevels(x){
  const L = LOCAL_ADJ.levels;
  const span = Math.max(1e-6, L.white - L.black);
  let v = (x - L.black) / span;
  v = Math.max(0, Math.min(1, v));
  if (L.gamma !== 1) v = Math.pow(v, 1 / L.gamma);
  return v;
}

/* 某个通道的最终采样函数 */
function channelSample(ch, x){
  let v = applyLevels(x);
  // rgb 合成曲线先作用，再叠该通道曲线
  v = curveSample(LOCAL_ADJ.curves.rgb, v);
  if (ch !== 'rgb') v = curveSample(LOCAL_ADJ.curves[ch], v);
  return Math.max(0, Math.min(1, v));
}

/* 覆盖：生成 filter 时三通道分别算 */
ensureCurveFilter = function(){
  let svg = document.getElementById('leSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.id = 'leSvg';
    svg.setAttribute('width','0'); svg.setAttribute('height','0');
    svg.style.position = 'absolute'; svg.style.pointerEvents = 'none';
    document.body.appendChild(svg);
  }
  /* 🔧 采样数 16 → 64：16 个 tableValues 做线性插值，曲线会显折线感 */
    const N = 64, mk = ch => {
    const a = [];
    for (let i = 0; i < N; i++) a.push(channelSample(ch, i/(N-1)).toFixed(4));
    return a.join(' ');
  };
  svg.innerHTML = `<defs>
    <filter id="leCurve" color-interpolation-filters="sRGB">
      <feComponentTransfer>
        <feFuncR type="table" tableValues="${mk('r')}"/>
        <feFuncG type="table" tableValues="${mk('g')}"/>
        <feFuncB type="table" tableValues="${mk('b')}"/>
      </feComponentTransfer>
    </filter>
  </defs>`;
};

/* ---- 重画曲线（按当前通道）---- */
leRenderCurve = function(){
  const pts = LOCAL_ADJ.curve;
  const toPx = p => [p[0]*200, (1-p[1])*200];
  let d = '';
  for (let i = 0; i <= 120; i++){
    const x = i/120;
    const y = curveSample(pts, x);
    d += (i===0?'M':'L') + (x*200).toFixed(1) + ',' + ((1-y)*200).toFixed(1) + ' ';
  }

  /* 🔴 2026-10-20 按 Camera Raw 加：直方图当曲线图背景。
     用和 leRenderHist 同一套模拟分布，映射到 200×200 的坐标里画一条填充路径。 */
  const histEl = document.getElementById('leHistBg');
  if (histEl){
    const N = 48;
    const bins = [];
    for (let i = 0; i < N; i++){
      const x = i / (N - 1);
      bins.push(Math.exp(-Math.pow((x - 0.42) / 0.22, 2)) * 0.85
              + Math.exp(-Math.pow((x - 0.75) / 0.14, 2)) * 0.35);
    }
    const mx = Math.max.apply(null, bins.concat([0.01]));
    let hd = 'M0,200';
    bins.forEach((v, i)=>{
      const x = i / (N - 1) * 200;
      const y = 200 - (v / mx) * 190;   // 最高柱到顶留 10
      hd += ' L' + x.toFixed(1) + ',' + y.toFixed(1);
    });
    hd += ' L200,200 Z';
    histEl.setAttribute('d', hd);
  }

  const pathEl = document.getElementById('lePath');
  if (pathEl){
    pathEl.setAttribute('d', d);
    const chColor = { rgb:'var(--ac)', r:'#f87171', g:'#34d399', b:'#60a5fa' }[LOCAL_ADJ.channel];
    pathEl.style.stroke = chColor;
  }

  /* 选中点的输入/输出值（0-255，和 PS 一样） */
  const ioEl = document.getElementById('leCurveIO');
  if (ioEl){
    if (LE_DRAG >= 0 && pts[LE_DRAG]){
      const p = pts[LE_DRAG];
      ioEl.textContent = '输入：' + Math.round(p[0] * 255) + '　输出：' + Math.round(p[1] * 255)
        + '　（第 ' + (LE_DRAG + 1) + '/' + pts.length + ' 点）';
    } else {
      ioEl.textContent = pts.length + ' 个控制点 · 点图上任意位置加点';
    }
  }

  const g = document.getElementById('lePts');
  if (g) g.innerHTML = pts.map((p,i)=>{
    const [px,py] = toPx(p);
    const isEnd = (i === 0 || i === pts.length - 1);
    const chColor = { rgb:'var(--ac)', r:'#f87171', g:'#34d399', b:'#60a5fa' }[LOCAL_ADJ.channel];
    /* 🔧 2026-10-20：首尾点原本就存在（5 个），但贴在角落看不清，
       用户以为只有 3 个点、也以为不能加点。
       现在：首尾稍大 + 白描边，每个点带 title，右上显示总点数。 */
    return `<circle cx="${px}" cy="${py}" r="${isEnd ? 6 : 5}"
      class="le-dot ${i===LE_DRAG?'on':''} ${isEnd?'end':''}"
      data-idx="${i}" style="fill:${chColor}"><title>第 ${i+1}/${pts.length} 点 · 拖动改曲线</title></circle>`;
  }).join('');

  /* 点数提示：让用户知道能加点、还能加几个 */
  const cntEl = document.getElementById('leCurveCount');
  if (cntEl) cntEl.textContent = pts.length + ' 点' + ((pts.length < 16) ? ' · 点空白处加点' : '（已满 16 点 · PS 上限）');

  // 通道 tab 高亮
  document.querySelectorAll('.le-ch').forEach(b=>{
    b.classList.toggle('on', b.dataset.ch === LOCAL_ADJ.channel);
  });
  leRenderHist();
};

/* ---- 切换通道 ---- */
function leSetChannel(ch){
  LOCAL_ADJ.channel = ch;
  leRenderCurve();
}

/* ---- 直方图（按当前参数模拟）---- */
function leRenderHist(){
  const host = document.getElementById('leHist');
  if (!host) return;
  const W = 200, H = 52;
  // 模拟：一个中间偏暗的分布，套上当前 LUT 后形变
  const bars = [];
  const N = 40;
  for (let i = 0; i < N; i++){
    const x = i / (N - 1);
    // 基础分布（模拟一张中间调偏暗的图）
    let base = Math.exp(-Math.pow((x - 0.42) / 0.22, 2)) * 0.85
             + Math.exp(-Math.pow((x - 0.75) / 0.14, 2)) * 0.35;
    bars.push(base);
  }
  // 应用 LUT：把 base 分布按最终映射搬位置（色阶 + 合成曲线 + 该通道曲线）
  const mapped = new Array(N).fill(0);
  for (let i = 0; i < N; i++){
    const out = channelSample(LOCAL_ADJ.channel, i/(N-1));
    const idx = Math.round(out * (N-1));
    mapped[Math.max(0, Math.min(N-1, idx))] += bars[i];
  }
  const mx = Math.max(...mapped, 0.01);
  const ch = LOCAL_ADJ.channel;
  const color = { rgb:'var(--ac)', r:'#f87171', g:'#34d399', b:'#60a5fa' }[ch];
  host.innerHTML = mapped.map((v,i)=>{
    const h = (v/mx) * H;
    const w = W/N;
    return `<rect x="${(i*w).toFixed(1)}" y="${(H-h).toFixed(1)}" width="${(w*0.82).toFixed(1)}"
      height="${h.toFixed(1)}" fill="${color}" opacity="0.55"/>`;
  }).join('') + (ch === 'rgb'
    ? `<rect x="0" y="0" width="${W}" height="${H}" fill="none"/>` : '');
}

/* ---- 色阶滑块 ---- */
function leLevel(key, val){
  LOCAL_ADJ.levels[key] = Number(val);
  const el = document.getElementById('leLv_' + key);
  if (el) el.textContent = key === 'gamma'
    ? Number(val).toFixed(2)
    : Math.round(Number(val) * 255);
  // 黑场不能超过白场
  if (LOCAL_ADJ.levels.black >= LOCAL_ADJ.levels.white){
    if (key === 'black') LOCAL_ADJ.levels.black = LOCAL_ADJ.levels.white - 0.02;
    else LOCAL_ADJ.levels.white = LOCAL_ADJ.levels.black + 0.02;
    leRenderAll();
    return;
  }
  leApplyPreview();
  leRenderHist();
}

/* ---- 重写面板（加通道 tab + 色阶 + 直方图）---- */
openLocalEdit = function(id){
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
            <div class="le-tag">${pic ? '真实图片预览 · ' + dims : '演示图预览 · 导入图片后这里显示你自己的图'} · 参数渲染，不是烘焙进图里</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">基础</div>
            ${leSlider('exposure','曝光','EV',-2,2,0.05)}
            ${leSlider('contrast','对比度','',0.5,1.5,0.01)}
            ${leSlider('saturation','饱和度','',0,2,0.01)}
            ${leSlider('temp','色温','K',4000,8000,50)}

            <div class="le-sec">直方图 <span class="le-sec2">按当前参数模拟</span></div>
            <div class="le-hwrap"><svg class="le-hist" id="leHist" viewBox="0 0 200 52"
              preserveAspectRatio="none"></svg></div>

            <div class="le-sec">色阶
              <button class="le-reset" onclick="leResetLevels()">复位</button>
            </div>
            <div class="le-row">
              <span class="le-l">黑场</span>
              <input type="range" class="le-r" min="0" max="1" step="0.005" value="${LOCAL_ADJ.levels.black}"
                oninput="leLevel('black', this.value)">
              <span class="le-v" id="leLv_black">${Math.round(LOCAL_ADJ.levels.black*255)}</span>
            </div>
            <div class="le-row">
              <span class="le-l">白场</span>
              <input type="range" class="le-r" min="0" max="1" step="0.005" value="${LOCAL_ADJ.levels.white}"
                oninput="leLevel('white', this.value)">
              <span class="le-v" id="leLv_white">${Math.round(LOCAL_ADJ.levels.white*255)}</span>
            </div>
            <div class="le-row">
              <span class="le-l">Gamma</span>
              <input type="range" class="le-r" min="0.3" max="3" step="0.02" value="${LOCAL_ADJ.levels.gamma}"
                oninput="leLevel('gamma', this.value)">
              <span class="le-v" id="leLv_gamma">${LOCAL_ADJ.levels.gamma.toFixed(2)}</span>
            </div>

            <div class="le-sec">曲线
              <span class="le-chs">
                <button class="le-ch on" data-ch="rgb" onclick="leSetChannel('rgb')">RGB</button>
                <button class="le-ch r" data-ch="r" onclick="leSetChannel('r')">R</button>
                <button class="le-ch g" data-ch="g" onclick="leSetChannel('g')">G</button>
                <button class="le-ch b" data-ch="b" onclick="leSetChannel('b')">B</button>
              </span>
              <button class="le-reset" onclick="leResetCurve()">拉直</button>
              <span class="le-curvecnt" id="leCurveCount"></span>
            </div>
            <div class="le-curvewrap">
              <svg class="le-curve" id="leCurveSvg" viewBox="0 0 200 200"
                   onmousedown="leCurveDown(event)" onmousemove="leCurveMove(event)"
                   onmouseup="leCurveUp(event)" onmouseleave="leCurveUp(event)"
                   oncontextmenu="event.preventDefault();leCurveDown(event)"
                   ondblclick="leResetCurve()">
                <!-- 🔴 2026-10-20 按 Camera Raw 加：直方图作为曲线图背景 -->
                <path id="leHistBg" class="le-histbg" d=""/>
                <line x1="0" y1="200" x2="200" y2="0" class="le-diag"/>
                <g>
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
            <!-- 选中点的输入/输出值（Camera Raw 也是这么显示的） -->
            <div class="le-curveio" id="leCurveIO">输入：— 输出：—</div>
            <div class="le-hint">点空白处加点（PS 上限 16）· 右键/Ctrl 点删点 · 双击拉直</div>
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
};

/* ---- 重置色阶 ---- */
function leResetLevels(){
  LOCAL_ADJ.levels = { black:0, white:1, gamma:1 };
  leRenderAll();
}

/* ---- leRenderAll 要带上色阶值 ---- */
const _leRenderAll = leRenderAll;
leRenderAll = function(){
  _leRenderAll();
  ['black','white','gamma'].forEach(k=>{
    const inp = document.querySelector('.le-r[oninput*="' + k + '"]');
    if (inp) inp.value = LOCAL_ADJ.levels[k];
    const el = document.getElementById('leLv_' + k);
    if (el) el.textContent = k === 'gamma'
      ? LOCAL_ADJ.levels[k].toFixed(2) : Math.round(LOCAL_ADJ.levels[k]*255);
  });
  leRenderHist();
};

/* ---- 重置要连色阶和分通道一起 ---- */
const _leResetAll = leResetAll;
leResetAll = function(){
  LOCAL_ADJ.levels = { black:0, white:1, gamma:1 };
  /* PS 的直线 = 只有两端点 */
  const lin = () => [[0,0],[1,1]];
  LOCAL_ADJ.curves = { rgb: lin(), r: lin(), g: lin(), b: lin() };
  LOCAL_ADJ.channel = 'rgb';
  Object.assign(LOCAL_ADJ, { exposure:0, contrast:1, saturation:1, temp:6100, gamma:1 });
  leRenderAll();
  toast('已重置 · 回到原图');
};

/* ---- 应用汇报要带上色阶/分通道 ---- */
const _leApply2 = leApply;
leApply = function(){
  const L = LOCAL_ADJ.levels;
  const extra = [];
  if (L.black > 0.005) extra.push(`黑场 ${Math.round(L.black*255)}`);
  if (L.white < 0.995) extra.push(`白场 ${Math.round(L.white*255)}`);
  if (Math.abs(L.gamma - 1) > 0.02) extra.push(`Gamma ${L.gamma.toFixed(2)}`);
  ['r','g','b'].forEach(ch=>{
    const c = LOCAL_ADJ.curves[ch];
    if (c.some(p=>Math.abs(p[1]-p[0]) > 0.02)) extra.push(ch.toUpperCase() + ' 通道曲线');
  });
  const before = { n: 'before' };
  _leApply2();
  if (extra.length){
    setTimeout(()=>{
      agAdd('ai', `另外还调了：<b>${extra.join(' · ')}</b>。`);
    }, 500);
  }
};


