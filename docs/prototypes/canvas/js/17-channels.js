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

/* ==========================================================================
   ⭐ AI 建议 → 图层（2026-10-22 按 AI修图大师 的做法搬进画布编辑面板）
   原则：建议是起点不是结果。采纳了能关、能删、能恢复。
   ========================================================================== */
const LE_SUGG_DEF = [
  { id:'s1', kind:'调色', state:'pending',
    title:'整体提亮，背景压暗，拉开层次',
    why:'画面偏暗，人和背景亮度接近，看着闷',
    src:'v', srcText:'读图推的', region:'全图',
    p:{ exposure:0.20, contrast:1.06, highlights:-0.12, shadows:0.18 } },
  { id:'s2', kind:'调色', state:'pending',
    title:'脸上高光压一点，别过曝',
    why:'额头和鼻梁的高光已经贴边，再亮点就没细节了',
    src:'v', srcText:'读图推的', region:'椭圆',
    p:{ highlights:-0.30, clarity:0.10 } },
  { id:'s3', kind:'影调', state:'pending',
    title:'暗部提一点，让阴影里有东西',
    why:'头发和衣服已经压成一片黑，看不出层次',
    src:'v', srcText:'读图推的', region:'线性渐变',
    p:{ shadows:0.42, clarity:-0.08 } }
];
let LE_SUGG = JSON.parse(JSON.stringify(LE_SUGG_DEF));
let LE_LAYERS = [];   // {id, name, on, region, p}

/* ---- 叠加：标量（曝光/对比/饱和/色温/色调）---- */
function leComposeScalars(){
  const out = {
    exposure: LOCAL_ADJ.exposure, contrast: LOCAL_ADJ.contrast,
    saturation: LOCAL_ADJ.saturation, temp: LOCAL_ADJ.temp, tint: LOCAL_ADJ.tint,
    highlights: LOCAL_ADJ.highlights, shadows: LOCAL_ADJ.shadows, clarity: LOCAL_ADJ.clarity,
    /* ⭐ 2026-10-22：细节也要带上，否则 leFilterCSS 里判断 undefined 永远 false */
    sharpen: LOCAL_ADJ.sharpen || 0, denoise: LOCAL_ADJ.denoise || 0
  };
  LE_LAYERS.forEach(function(L){
    if (!L.on) return;
    /* ⭐ 区域图层走自己的叠加层，不参与全局合成 */
    if (L.region && L.region !== '全图') return;
    const p = L.p || {};
    if (p.exposure   != null) out.exposure   += p.exposure;
    if (p.contrast   != null) out.contrast   *= p.contrast;
    if (p.saturation != null) out.saturation *= p.saturation;
    if (p.temp       != null) out.temp        = p.temp;
    if (p.tint       != null) out.tint       += p.tint;
  });
  return out;
}

/* ---- 叠加：影调（高光/阴影/清晰度）---- */
function leComposeTone(){
  const out = {
    highlights: LOCAL_ADJ.highlights,
    shadows: LOCAL_ADJ.shadows,
    clarity: LOCAL_ADJ.clarity
  };
  LE_LAYERS.forEach(function(L){
    if (!L.on) return;
    /* ⭐ 区域图层不参与全局影调 */
    if (L.region && L.region !== '全图') return;
    const p = L.p || {};
    if (p.highlights != null) out.highlights += p.highlights;
    if (p.shadows    != null) out.shadows    += p.shadows;
    if (p.clarity    != null) out.clarity    += p.clarity;
  });
  // 夹住，别越界
  out.highlights = Math.max(-1, Math.min(1, out.highlights));
  out.shadows    = Math.max(-1, Math.min(1, out.shadows));
  out.clarity    = Math.max(-1, Math.min(1, out.clarity));
  return out;
}

/* ---- 建议 / 图层 渲染 ---- */
function leRenderSugg(){
  const host = document.getElementById('leSugg');
  if (!host) return;
  const act = LE_SUGG.filter(function(s){ return s.state === 'pending'; });
  const ign = LE_SUGG.filter(function(s){ return s.state === 'ignored'; });

  let h = act.map(function(s){
    return '<div class="lh-sg">'
      + '<div class="lh-sg-h"><span class="lh-sg-dot"></span>'
      +   '<span class="lh-sg-t">' + s.title + '</span>'
      +   '<span class="lh-sg-k">' + s.kind + '</span></div>'
      + '<div class="lh-sg-w">' + s.why + '</div>'
      + '<div class="lh-sg-s ' + s.src + '">' + s.srcText
      +   (s.region !== '全图' ? ' · 只影响' + s.region : ' · 影响全图') + '</div>'
      + '<div class="lh-sg-a">'
      +   '<button class="lh-b y" onclick="leAdopt(\'' + s.id + '\')">采纳</button>'
      +   '<button class="lh-b" onclick="leIgnore(\'' + s.id + '\')">忽略</button>'
      + '</div></div>';
  }).join('');

  if (ign.length){
    h += '<div class="lh-ign-h">已忽略</div>';
    h += ign.map(function(s){
      return '<div class="lh-sg off">'
        + '<div class="lh-sg-h"><span class="lh-sg-dot"></span>'
        + '<span class="lh-sg-t">' + s.title + '</span></div>'
        + '<div class="lh-sg-a"><button class="lh-b" onclick="leRestore(\'' + s.id + '\')">恢复</button></div>'
        + '</div>';
    }).join('');
  }
  if (!act.length && !ign.length){
    h = '<div class="lh-empty">建议都处理完了。<br>采纳的都变成了下面的图层，随时能关。</div>';
  }
  host.innerHTML = h;
  const n = document.getElementById('leSuggN');
  if (n) n.textContent = act.length + ' 条待确认';
}

function leRenderLayers(){
  const host = document.getElementById('leLayers');
  if (!host) return;
  if (!LE_LAYERS.length){
    host.innerHTML = '<div class="lh-empty">还没有图层。<br>采纳一条建议，它就变成图层 ——<br>能关掉、能删掉，原图不动。</div>';
  } else {
    host.innerHTML = LE_LAYERS.map(function(L, i){
      return '<div class="lh-ly' + (L.on ? '' : ' off') + '">'
        + '<button class="lh-eye' + (L.on ? ' on' : '') + '" onclick="leToggleLayer(' + i + ')">'
        +   (L.on ? '◉' : '○') + '</button>'
        + '<span class="lh-ly-n">' + L.name + '</span>'
        + '<span class="lh-ly-r' + (L.region === '全图' ? '' : ' local') + '">'
        +   (L.region === '全图' ? '全图' : '仅' + L.region) + '</span>'
        + '<button class="lh-x" onclick="leDelLayer(' + i + ')">✕</button>'
        + '</div>';
    }).join('');
  }
  const n = document.getElementById('leLyN');
  if (n) n.textContent = LE_LAYERS.length;
}

/* ---- 采纳 / 忽略 / 恢复 / 开关 / 删除 ---- */
function leAdopt(id){
  const s = LE_SUGG.find(function(x){ return x.id === id; });
  if (!s) return;
  s.state = 'adopted';
  LE_LAYERS.push({ id:s.id, name:s.title, on:true, region:s.region, p:s.p });
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSnap();
  toast('已采纳 · 变成图层了，随时能关');
}
function leIgnore(id){
  const s = LE_SUGG.find(function(x){ return x.id === id; });
  if (!s) return;
  s.state = 'ignored';
  LE_LAYERS = LE_LAYERS.filter(function(L){ return L.id !== id; });
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSnap();
}
function leRestore(id){
  const s = LE_SUGG.find(function(x){ return x.id === id; });
  if (!s) return;
  s.state = 'pending';
  leRenderSugg();
}
function leToggleLayer(i){
  LE_LAYERS[i].on = !LE_LAYERS[i].on;
  leRenderLayers(); leApplyPreview(); leSnap();
}
function leDelLayer(i){
  const L = LE_LAYERS[i];
  const s = LE_SUGG.find(function(x){ return x.id === L.id; });
  if (s) s.state = 'ignored';
  LE_LAYERS.splice(i, 1);
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSnap();
}
function leClearLayers(){
  LE_LAYERS = [];
  LE_SUGG.forEach(function(s){ if (s.state === 'adopted') s.state = 'pending'; });
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSnap();
}


/* ==========================================================================
   ⭐ 区域限定（2026-10-22）
   之前图层上写着「只影响椭圆」，但参数是全图生效 —— 这是假承诺。
   现在：每个区域图层叠一份「带自己滤镜 + 遮罩」的图，遮罩外一点不动。
   ========================================================================== */

/* 把一份参数里的「影调」作用到 0~1 的亮度上 */
function leToneOf(v, p){
  p = p || {};
  if (p.highlights) v += p.highlights * 0.28 * v * v;
  if (p.shadows)    v += p.shadows * 0.28 * (1 - v) * (1 - v);
  if (p.clarity)    v += p.clarity * 0.16 * Math.sin((v - 0.5) * Math.PI)
                          * (1 - Math.abs(v * 2 - 1));
  return Math.max(0, Math.min(1, v));
}

/* 一个图层的 LUT（只含影调，颜色参数走 CSS filter）*/
function leLayerLut(p, n){
  n = n || 64;
  const out = [];
  for (let i = 0; i < n; i++) out.push(leToneOf(i / (n - 1), p));
  return out;
}

/* 为每个区域图层建一个 SVG filter */
function leEnsureLayerFilters(){
  let svg = document.getElementById('leLayerSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = 'leLayerSvg';
    svg.setAttribute('width', '0'); svg.setAttribute('height', '0');
    svg.style.position = 'absolute'; svg.style.pointerEvents = 'none';
    document.body.appendChild(svg);
  }
  let html = '<defs>';
  LE_LAYERS.forEach(function(L){
    const p = L.p || {};
    const needsTone = (p.highlights || p.shadows || p.clarity);
    if (!needsTone) return;
    const tbl = leLayerLut(p).map(function(v){ return v.toFixed(4); }).join(' ');
    html += '<filter id="lf_' + L.id + '" color-interpolation-filters="sRGB">'
      + '<feComponentTransfer>'
      + '<feFuncR type="table" tableValues="' + tbl + '"/>'
      + '<feFuncG type="table" tableValues="' + tbl + '"/>'
      + '<feFuncB type="table" tableValues="' + tbl + '"/>'
      + '</feComponentTransfer></filter>';
  });
  html += '</defs>';
  svg.innerHTML = html;
}

/* 图层的颜色类滤镜（曝光/对比/饱和/色温/色调）*/
function leLayerColorFilter(L){
  const p = L.p || {};
  const parts = [];
  if (p.exposure)   parts.push('brightness(' + (1 + p.exposure * 0.35).toFixed(3) + ')');
  if (p.contrast)   parts.push('contrast(' + p.contrast.toFixed(3) + ')');
  if (p.saturation) parts.push('saturate(' + p.saturation.toFixed(3) + ')');
  if (p.temp){
    const t = (p.temp - 6100) / 2000;
    if (Math.abs(t) > 0.02){
      parts.push('sepia(' + Math.max(0, t * 0.28).toFixed(3) + ')');
      parts.push('hue-rotate(' + (-t * 14).toFixed(1) + 'deg)');
    }
  }
  if (p.tint){
    const g = p.tint < 0;
    parts.push('hue-rotate(' + (p.tint * (g ? -12 : 12)).toFixed(1) + 'deg)');
  }
  return parts.join(' ');
}

/* 区域 → CSS 遮罩（椭圆/渐变带羽化，矩形硬边）*/
function leMaskCSS(region){
  if (region === '椭圆')
    return { mask: 'radial-gradient(ellipse 46% 34% at 50% 33%, #000 52%, transparent 78%)' };
  if (region === '线性渐变')
    return { mask: 'linear-gradient(180deg, #000 0%, #000 32%, transparent 72%)' };
  if (region === '矩形')
    return { clip: 'inset(14% 22% 34% 22% round 10px)' };
  return {};   // 全图 或 画笔（暂不支持）
}

/* 重画所有区域叠加层 */
function leRenderFx(){
  const img = document.getElementById('leImg');
  if (!img) return;
  img.querySelectorAll('.le-fx').forEach(function(e){ e.remove(); });
  if (LE_CMP) return;            // 对比原图时不加
  leEnsureLayerFilters();

  const cs = getComputedStyle(img);
  let skipped = 0;

  LE_LAYERS.forEach(function(L){
    if (!L.on) return;
    if (!L.region || L.region === '全图') return;
    if (L.region === '画笔'){ skipped++; return; }   // 画笔还没做

    const m = leMaskCSS(L.region);
    if (!m.mask && !m.clip){ skipped++; return; }

    const fx = document.createElement('div');
    fx.className = 'le-fx';
    // 复制底图（背景图 / 渐变 / 演示小人）
    fx.style.backgroundImage = cs.backgroundImage;
    fx.style.backgroundSize = cs.backgroundSize;
    fx.style.backgroundPosition = cs.backgroundPosition;
    fx.style.backgroundRepeat = cs.backgroundRepeat;
    fx.style.backgroundColor = cs.backgroundColor;
    if (img.querySelector('.le-fig')) fx.innerHTML = '<div class="le-fig"></div>';

    // 这一层自己的滤镜：影调 LUT + 颜色
    const parts = [];
    const p = L.p || {};
    if (p.highlights || p.shadows || p.clarity) parts.push('url(#lf_' + L.id + ')');
    const col = leLayerColorFilter(L);
    if (col) parts.push(col);
    fx.style.filter = parts.join(' ') || 'none';

    if (m.mask){ fx.style.webkitMaskImage = m.mask; fx.style.maskImage = m.mask; }
    if (m.clip) fx.style.clipPath = m.clip;

    img.appendChild(fx);
  });

  // 有没生效的，老实说出来
  const warn = document.getElementById('leFxWarn');
  if (warn){
    if (skipped){
      warn.style.display = '';
      warn.textContent = '⚠️ 有 ' + skipped + ' 个图层选的区域还做不了（画笔），这条参数暂时按全图算';
    } else {
      warn.style.display = 'none';
    }
  }
}


/* ==========================================================================
   ⭐ 2026-10-22 一次补齐五件：撤销重做 / 锐化降噪 / 裁剪 / 画笔区域 / 局部重绘
   ========================================================================== */

/* ---------------- 1. 细节滤镜：降噪 + 锐化 ---------------- */
function leEnsureDetailFilters(denoise, sharpen){
  let svg = document.getElementById('leDetailSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.id = 'leDetailSvg';
    svg.setAttribute('width','0'); svg.setAttribute('height','0');
    svg.style.position='absolute'; svg.style.pointerEvents='none';
    document.body.appendChild(svg);
  }
  const parts = ['<defs>'];
  if (denoise > 0.01){
    const r = (denoise * 1.6).toFixed(2);
    parts.push('<filter id="leDenoise" x="0" y="0" width="100%" height="100%">'
      + '<feGaussianBlur stdDeviation="' + r + '"/></filter>');
  }
  if (sharpen > 0.01){
    /* USM 的矩阵近似：中间 1+4a，四邻 -a */
    const a = (sharpen * 1.1);
    const ctr = (1 + 4 * a).toFixed(3);
    const na = (-a).toFixed(3);
    const k = '0 ' + na + ' 0  ' + na + ' ' + ctr + ' ' + na + '  0 ' + na + ' 0';
    parts.push('<filter id="leSharpen" x="0" y="0" width="100%" height="100%">'
      + '<feConvolveMatrix order="3" preserveAlpha="true" kernelMatrix="'
      + k + '"/></filter>');
  }
  parts.push('</defs>');
  svg.innerHTML = parts.join('');
}

/* ---------------- 2. 撤销 / 重做 ---------------- */
let LE_HIST = [];
let LE_HIST_I = -1;
let LE_SNAP_T = null;

function leSnapNow(){
  const s = {
    adj: JSON.parse(JSON.stringify(LOCAL_ADJ)),
    layers: JSON.parse(JSON.stringify(LE_LAYERS)),
    sugg: LE_SUGG.map(function(x){ return { id:x.id, state:x.state }; }),
    brush: LE_BRUSH_MASK
  };
  /* 干掉 redo 分支 */
  LE_HIST = LE_HIST.slice(0, LE_HIST_I + 1);
  LE_HIST.push(s);
  if (LE_HIST.length > 60) LE_HIST.shift();
  LE_HIST_I = LE_HIST.length - 1;
  leSyncUndo();
}
/* 改动停下 400ms 再记一笔，拖滑块不会记成几十步 */
function leSnap(){
  if (LE_SNAP_T) clearTimeout(LE_SNAP_T);
  LE_SNAP_T = setTimeout(function(){ LE_SNAP_T = null; leSnapNow(); }, 400);
}
function leRestoreFrom(s){
  Object.assign(LOCAL_ADJ, JSON.parse(JSON.stringify(s.adj)));
  LE_LAYERS = JSON.parse(JSON.stringify(s.layers));
  s.sugg.forEach(function(x){
    const t = LE_SUGG.find(function(y){ return y.id === x.id; });
    if (t) t.state = x.state;
  });
  LE_BRUSH_MASK = s.brush || null;
  if (typeof renderManual === 'function') renderManual();
  else if (typeof leRenderAll === 'function') leRenderAll();
  leRenderSugg(); leRenderLayers(); leApplyPreview();
}
function leUndo(){
  if (LE_HIST_I <= 0){ toast('已经到头了'); return; }
  LE_HIST_I--; leRestoreFrom(LE_HIST[LE_HIST_I]); leSyncUndo();
  toast('撤销 · 第 ' + (LE_HIST_I + 1) + ' 步');
}
function leRedo(){
  if (LE_HIST_I >= LE_HIST.length - 1){ toast('没有可重做的了'); return; }
  LE_HIST_I++; leRestoreFrom(LE_HIST[LE_HIST_I]); leSyncUndo();
  toast('重做 · 第 ' + (LE_HIST_I + 1) + ' 步');
}
function leSyncUndo(){
  const u = document.getElementById('leUndoBtn');
  const r = document.getElementById('leRedoBtn');
  if (u) u.disabled = (LE_HIST_I <= 0);
  if (r) r.disabled = (LE_HIST_I >= LE_HIST.length - 1);
}
document.addEventListener('keydown', function(e){
  if (!(e.ctrlKey || e.metaKey)) return;
  if (e.key === 'z' || e.key === 'Z'){
    e.preventDefault();
    if (e.shiftKey) leRedo(); else leUndo();
  }
});

/* ---------------- 3. 裁剪（比例预设）---------------- */
const LE_RATIOS = { '原图':null, '1:1':1, '4:3':4/3, '3:4':3/4, '16:9':16/9, '9:16':9/16 };
function leSetCrop(btn, ratio){
  LOCAL_ADJ.crop = ratio;
  const box = document.getElementById('leCrops');
  if (box) box.querySelectorAll('.le-crop').forEach(function(b){ b.classList.remove('on'); });
  if (btn) btn.classList.add('on');
  leApplyCrop();
  leApplyPreview();
  leSnap();
}
function leApplyCrop(){
  const img = document.getElementById('leImg');
  if (!img) return;
  const r = LE_RATIOS[LOCAL_ADJ.crop];
  if (!r){
    img.style.aspectRatio = '';
    img.style.removeProperty('--crop-h');
    img.dataset.crop = '原图';
    return;
  }
  img.style.aspectRatio = String(r);
  img.dataset.crop = LOCAL_ADJ.crop;
}

/* ---------------- 4. 画笔区域 ---------------- */
let LE_BRUSH_MASK = null;    // dataURL
let LE_BRUSH_ON = false;
let LE_BRUSH_SIZE = 34;
let LE_BRUSH_DRAWING = false;

function leBrushToggle(){
  LE_BRUSH_ON = !LE_BRUSH_ON;
  const cv = document.getElementById('leBrushCv');
  const btn = document.getElementById('leBrushBtn');
  if (cv) cv.classList.toggle('on', LE_BRUSH_ON);
  if (btn) btn.classList.toggle('on', LE_BRUSH_ON);
  if (LE_BRUSH_ON){
    leBrushInitCanvas();
    toast('画笔：直接在图上刷，刷到的地方才生效');
  } else {
    leBrushCommit();
  }
}
function leBrushInitCanvas(){
  const cv = document.getElementById('leBrushCv');
  const img = document.getElementById('leImg');
  if (!cv || !img) return;
  const r = img.getBoundingClientRect();
  cv.width = Math.max(2, Math.round(r.width));
  cv.height = Math.max(2, Math.round(r.height));
  cv.style.width = r.width + 'px';
  cv.style.height = r.height + 'px';
  /* fixed 定位盖到图片上（模板里 canvas 是 stage 的兄弟，不是图片的子元素） */
  cv.style.position = 'fixed';
  cv.style.left = r.left + 'px';
  cv.style.top = r.top + 'px';
  cv.style.zIndex = '580';
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  /* 之前画过的接着显示 */
  if (LE_BRUSH_MASK){
    const im = new Image();
    im.onload = function(){ ctx.drawImage(im, 0, 0, cv.width, cv.height); };
    im.src = LE_BRUSH_MASK;
  }
}
function leBrushPos(e){
  const cv = document.getElementById('leBrushCv');
  const r = cv.getBoundingClientRect();
  return [e.clientX - r.left, e.clientY - r.top];
}
function leBrushDown(e){
  if (!LE_BRUSH_ON) return;
  LE_BRUSH_DRAWING = true;
  leBrushDot(e);
}
function leBrushMove(e){
  if (!LE_BRUSH_ON || !LE_BRUSH_DRAWING) return;
  leBrushDot(e);
}
function leBrushUp(){
  if (!LE_BRUSH_DRAWING) return;
  LE_BRUSH_DRAWING = false;
  leBrushCommit();
}
function leBrushDot(e){
  const cv = document.getElementById('leBrushCv');
  if (!cv) return;
  const ctx = cv.getContext('2d');
  const [x, y] = leBrushPos(e);
  const rad = LE_BRUSH_SIZE / 2;
  const g = ctx.createRadialGradient(x, y, rad * 0.35, x, y, rad);
  g.addColorStop(0, 'rgba(0,0,0,1)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, rad, 0, Math.PI * 2);
  ctx.fill();
}
function leBrushCommit(){
  const cv = document.getElementById('leBrushCv');
  if (!cv) return;
  LE_BRUSH_MASK = cv.toDataURL('image/png');
  leRenderFx();
  leSnap();
}
function leBrushClear(){
  const cv = document.getElementById('leBrushCv');
  if (cv){
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
  }
  LE_BRUSH_MASK = null;
  leRenderFx();
  toast('画笔已清空');
}

/* ---------------- 5. AI 局部重绘 ---------------- */
let LE_IP_REGION = '矩形';
/* 原型：不同候选 = 不同处理，用 CSS 滤镜模拟，标注清楚没接 AI */
const LE_IP_CANDS = [
  { n:'候选 1 · 补背景', f:'blur(0.6px) brightness(1.04) saturate(0.95)' },
  { n:'候选 2 · 换色调', f:'hue-rotate(-16deg) saturate(1.15) brightness(1.02)' },
  { n:'候选 3 · 更干净', f:'brightness(1.07) contrast(0.97) saturate(1.05)' }
];
function leIpRegion(btn, r){
  LE_IP_REGION = r;
  const box = btn.parentElement;
  box.querySelectorAll('.le-ip-r').forEach(function(b){ b.classList.remove('on'); });
  btn.classList.add('on');
}
function leIpGo(){
  const ta = document.getElementById('leIpText');
  const txt = (ta.value || '').trim();
  if (!txt){ ta.focus(); toast('先说一句要换成什么'); return; }
  const host = document.getElementById('leIpCands');
  if (!host) return;
  host.innerHTML = '<div class="le-ip-loading">正在生成 3 张…</div>';
  setTimeout(function(){
    host.innerHTML = LE_IP_CANDS.map(function(c, i){
      return '<div class="le-ip-cand" onclick="leIpPick(' + i + ',this)">'
        + '<div class="le-ip-img" style="filter:' + c.f + '">'
        +   '<div class="le-ip-inner">' + txt.substring(0, 14) + '</div></div>'
        + '<div class="le-ip-n">' + c.n + '</div>'
        + '</div>';
    }).join('') + '<div class="le-ip-warn">⚠️ 原型占位：还没接 AI，'
      + '上面三张是本地滤镜模拟，不是真的重绘</div>';
  }, 700);
}
function leIpPick(i, el){
  el.parentElement.querySelectorAll('.le-ip-cand').forEach(function(e){ e.classList.remove('on'); });
  el.classList.add('on');
  toast('选了「' + LE_IP_CANDS[i].n + '」· 原型里只做选中态，不会真改图');
}

/* ---- 对比原图 ---- */
let LE_CMP = false;
function leSetCompare(on){
  LE_CMP = !!on;
  const img = document.getElementById('leImg');
  if (img) img.style.filter = LE_CMP ? 'none' : leFilterCSS();
  const bar = document.getElementById('leCmpBar');
  if (bar) bar.classList.toggle('on', LE_CMP);
  if (typeof leRenderFx === 'function') leRenderFx();
}
document.addEventListener('keydown', function(e){
  if (e.key === '\\' && !e.repeat){ e.preventDefault(); leSetCompare(true); }
});
document.addEventListener('keyup', function(e){
  if (e.key === '\\'){ e.preventDefault(); leSetCompare(false); }
});

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
  /* ⭐ 2026-10-22：高光/阴影/清晰度先过一遍，再进色阶和曲线。
     顺序有讲究 —— 影调是「哪一段亮」的问题，曲线是「怎么改」的问题。 */
  let v = (typeof leToneMap === 'function') ? leToneMap(x) : x;
  v = applyLevels(v);
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

  /* 直方图当曲线图背景（Camera Raw 的做法）。
     ⭐ 2026-10-22：原来是模拟高斯分布，现在和上面那块用同一个真像素函数。 */
  const histEl = document.getElementById('leHistBg');
  if (histEl){
    const N = 128;   /* 从 48 提到 128，剪影更顺 */
    const R2 = leRealHistBins(N);
    const bins = R2 ? R2.hist.slice() : new Array(N).fill(0);
    const mx = Math.sqrt(Math.max.apply(null, bins.concat([1])));
    let hd = 'M0,200';
    bins.forEach((v, i)=>{
      const x = i / (N - 1) * 200;
      const y = 200 - (Math.sqrt(v) / mx) * 190;   // 最高柱到顶留 10（平方根归一化）
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

/* ============ ⭐ 真直方图分箱（从像素算）============
   2026-10-22：之前「直方图块」和「曲线背景」各写了一套高斯模拟，
   两处都是假的。现在统一走这一个函数，都是真像素。
*/
function leRealHistBins(N){
  const pix = (typeof leBuildSourcePixels === 'function') ? leBuildSourcePixels() : null;
  if (!pix) return null;
  const ch = LOCAL_ADJ.channel;
  const expMul = 1 + LOCAL_ADJ.exposure * 0.35;
  const hist = new Array(N).fill(0);
  let over = 0, under = 0;
  for (let i = 0; i < pix.length; i++){
    let v = Math.max(0, Math.min(1, pix[i] * expMul));
    v = channelSample(ch, v);
    hist[Math.min(N - 1, Math.floor(v * (N - 1)))]++;
    if (v > 0.995) over++;
    if (v < 0.005) under++;
  }
  return { hist, over, under, total: pix.length };
}

/* ---- 直方图块 ---- */
function leRenderHist(){
  const host = document.getElementById('leHist');
  if (!host) return;
  const W = 200, H = 52;

  const BINS = 256;   /* ⭐ PS 是 256 级（每个色阶一根），之前 48 太粗 */
  const R = leRealHistBins(BINS);
  if (!R){ host.innerHTML = ''; return; }
  const hist = R.hist, over = R.over, under = R.under, pix = { length: R.total };
  const ch = LOCAL_ADJ.channel;

  /* 用平方根归一化 —— 线性归一化时暗部一大簇会把亮部小簇压没，
     照片软件里也都是这么画的（不然深色衣服的图看不到别的东西）。 */
  const mx = Math.sqrt(Math.max(...hist) || 1);
  const bw = W / BINS;
  const color = { rgb:'#22d3ee', r:'#f87171', g:'#34d399', b:'#60a5fa' }[ch] || '#22d3ee';

  host.innerHTML = hist.map((v, i) => {
    const h = (Math.sqrt(v) / mx) * H;
    return '<rect x="' + (i*bw).toFixed(1) + '" y="' + (H-h).toFixed(1) + '"'
      + ' width="' + (bw*1.02).toFixed(2) + '" height="' + h.toFixed(1) + '"'
      + ' fill="' + color + '" opacity="0.62"/>';
  }).join('');

  // 溢出数字：课程里说「看直方图判断过曝欠曝」
  const info = document.getElementById('leHistInfo');
  if (info){
    const op = (over / pix.length * 100).toFixed(1);
    const up = (under / pix.length * 100).toFixed(1);
    info.textContent = '过曝 ' + op + '% · 欠曝 ' + up + '%';
    info.style.color = (over/pix.length > 0.02 || under/pix.length > 0.05)
      ? 'var(--wn)' : 'var(--tx3)';
  }
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

        <div class="le-body le-body3">

          <!-- ⭐ 左栏：AI 建议 + 图层（照 AI修图大师 的三栏） -->
          <div class="le-left">
            <div class="le-sec">AI 读完这张图的建议 <em id="leSuggN">3 条待确认</em></div>
            <div id="leSugg"></div>
            <div class="le-sec">图层 <em id="leLyN">0</em>
              <button class="le-reset" onclick="leClearLayers()">清空</button></div>
            <div id="leLayers"></div>
            <div class="le-fxwarn" id="leFxWarn" style="display:none"></div>
            <div class="le-cmp">
              <button class="lh-b le-cmpb" onmousedown="leSetCompare(true)"
                onmouseup="leSetCompare(false)" onmouseleave="leSetCompare(false)">
                按住对比原图</button>
              <div class="le-cmp-t">松开回到你改过的版本 · 或按 \ 键</div>
            </div>
          </div>

          <div class="le-stage">
            <div class="le-img${pic?' has-pic':' le-demo'}" id="leImg"${pic?` style="width:100%;height:min(58vh,440px);aspect-ratio:auto;background-image:url('${pic}');background-size:contain;background-position:center;background-repeat:no-repeat;background-color:#0b0b0f"`:''}>
              ${pic?'':'<div class="le-fig"></div>'}
            </div>
            <canvas class="le-brushcv" id="leBrushCv"
              onmousedown="leBrushDown(event)" onmousemove="leBrushMove(event)"
              onmouseup="leBrushUp()" onmouseleave="leBrushUp()"></canvas>
            <div class="le-tag">${pic ? '真实图片预览 · ' + dims : '演示图预览 · 导入图片后这里显示你自己的图'} · 参数渲染，不是烘焙进图里</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">基础</div>
            ${leSlider('exposure','曝光','EV',-2,2,0.05)}
            ${leSlider('contrast','对比度','',0.5,1.5,0.01)}
            ${leSlider('saturation','饱和度','',0,2,0.01)}
            ${leSlider('temp','色温','K',4000,8000,50)}
            ${leSlider('tint','色调','',-1,1,0.02)}

            <div class="le-sec">影调 <span class="le-sec2">只动亮部 · 只动暗部</span></div>
            ${leSlider('highlights','高光','',-1,1,0.02)}
            ${leSlider('shadows','阴影','',-1,1,0.02)}
            ${leSlider('clarity','清晰度','',-1,1,0.02)}

            <div class="le-sec">直方图 <span class="le-sec2">从像素算的 · 参数一变就跟着变</span></div>
            <div class="le-hwrap"><svg class="le-hist" id="leHist" viewBox="0 0 200 52"
              preserveAspectRatio="none"></svg></div>
            <div class="le-histinfo" id="leHistInfo">—</div>

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

            <!-- ⭐ 细节 -->
            <div class="le-sec">细节 <span class="le-sec2">降噪先，锐化后</span></div>
            ${leSlider('denoise','降噪','',0,1,0.01)}
            ${leSlider('sharpen','锐化','',0,1,0.01)}

            <!-- ⭐ 裁剪 -->
            <div class="le-sec">裁剪
              <span class="le-sec2">只改显示和导出</span>
              <button class="le-reset" onclick="leSetCrop(null,'原图')">还原</button>
            </div>
            <div class="le-crops" id="leCrops">
              <button class="le-crop on" onclick="leSetCrop(this,'原图')">原图</button>
              <button class="le-crop" onclick="leSetCrop(this,'1:1')">1:1</button>
              <button class="le-crop" onclick="leSetCrop(this,'4:3')">4:3</button>
              <button class="le-crop" onclick="leSetCrop(this,'3:4')">3:4</button>
              <button class="le-crop" onclick="leSetCrop(this,'16:9')">16:9</button>
              <button class="le-crop" onclick="leSetCrop(this,'9:16')">9:16</button>
            </div>

            <!-- ⭐ 画笔区域 -->
            <div class="le-sec">画笔区域 <span class="le-sec2">刷到哪改到哪</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leBrushBtn" onclick="leBrushToggle()">开画笔</button>
              <span class="le-blab">大小</span>
              <input type="range" class="le-r le-brushsize" min="8" max="120" step="2" value="34"
                oninput="LE_BRUSH_SIZE=Number(this.value)">
              <button class="le-reset" onclick="leBrushClear()">清空</button>
            </div>
            <div class="le-hint">开了画笔后，在图上按住拖动就刷遮罩</div>

            <!-- ⭐ 局部重绘 -->
            <div class="le-sec">局部重绘 <span class="le-sec2">圈一块 · 说一句</span></div>
            <div class="le-ipregions">
              <button class="le-ip-r on" onclick="leIpRegion(this,'矩形')">矩形</button>
              <button class="le-ip-r" onclick="leIpRegion(this,'椭圆')">椭圆</button>
              <button class="le-ip-r" onclick="leIpRegion(this,'画笔')">画笔</button>
            </div>
            <textarea class="le-ipta" id="leIpText"
              placeholder="把这里换成什么？&#10;例如：去掉后面那个人 / 换成一片天空"></textarea>
            <button class="le-ipgo" onclick="leIpGo()">生成 3 张</button>
            <div class="le-ipcands" id="leIpCands"></div>
          </div>
        </div>

        <div class="le-foot">
          <div class="le-cost">
            花费 <b class="le-zero">0</b>
            <span class="le-costn">本地像素运算 · 不走模型 · 参数留着随时能改</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" id="leUndoBtn" onclick="leUndo()" title="撤销 Ctrl+Z">↶ 撤销</button>
            <button class="insp-b ghost" id="leRedoBtn" onclick="leRedo()" title="重做 Ctrl+Shift+Z">↷ 重做</button>
            <button class="insp-b ghost" onclick="leResetAll()">全部重置</button>
            <button class="insp-b pri" onclick="leApply()">应用</button>
          </div>
        </div>
      </div>
    </div>`;

  leRenderAll();
  /* ⭐ 2026-10-22：三栏里的左栏要初始化 */
  if (typeof leRenderSugg === 'function'){ leRenderSugg(); leRenderLayers(); }
  if (typeof leApplyCrop === 'function') leApplyCrop();
  if (typeof leSnapNow === 'function'){ LE_HIST = []; LE_HIST_I = -1; leSnapNow(); }
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


