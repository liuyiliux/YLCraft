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
/* ⭐ 2026-10-22：选中的图层。选中后右边滑块调的就是它 ——
   用户指出「点采纳图片有变化，右边参数没变化」，就是这个没做。 */
let LE_SEL_LAYER = -1;

const LE_P_DEF = {
  exposure:0, contrast:1, saturation:1, temp:6100, tint:0,
  highlights:0, shadows:0, clarity:0, sharpen:0, denoise:0
};
function leNormP(p){ return Object.assign({}, LE_P_DEF, p || {}); }
function leSetTarget(){
  if (LE_SEL_LAYER >= 0 && LE_LAYERS[LE_SEL_LAYER]) return LE_LAYERS[LE_SEL_LAYER].p;
  return LOCAL_ADJ;
}
function leSelectLayer(i){
  LE_SEL_LAYER = (LE_SEL_LAYER === i) ? -1 : i;
  leRenderLayers();
  leSyncPanel();
}
/* 图层参数被滑块改了之后，图层行上标一下「改过」 */
function leMarkLayerDirty(){
  const host = document.getElementById('leLayers');
  if (!host || LE_SEL_LAYER < 0 || !LE_LAYERS[LE_SEL_LAYER]) return;
  const rows = host.querySelectorAll('.lh-ly');
  const row = rows[LE_SEL_LAYER];
  if (row && !row.querySelector('.lh-dirty')){
    const d = document.createElement('span');
    d.className = 'lh-dirty';
    d.textContent = '改过';
    row.insertBefore(d, row.querySelector('.lh-x'));
  }
}
function leSyncPanel(){
  const isLayer = LE_SEL_LAYER >= 0 && LE_LAYERS[LE_SEL_LAYER];
  const t = leSetTarget();
  const hd = document.getElementById('leTarget');
  if (hd){
    hd.textContent = isLayer ? ('正在改：' + LE_LAYERS[LE_SEL_LAYER].name) : '正在改：基础（手动）';
    hd.className = 'le-target' + (isLayer ? ' layer' : '');
  }
  const back = document.getElementById('leBackBase');
  if (back) back.style.display = isLayer ? '' : 'none';

  document.querySelectorAll('.le-panel input[type=range]').forEach(function(inp){
    const m = (inp.getAttribute('oninput') || '').match(/'([a-zA-Z]+)'/);
    if (!m) return;
    const k = m[1];
    if (k === 'black' || k === 'white' || k === 'gamma') return;   // 色阶单独管
    let v = t[k];
    if (v == null) v = LE_P_DEF[k];
    if (v == null) return;
    inp.value = v;
    const el = document.getElementById('leVal_' + k);
    if (el) el.textContent = leFmt(k, v) + (k === 'temp' ? 'K' : '') + (k === 'exposure' ? 'EV' : '');
  });
}

/* ---- 叠加：标量（曝光/对比/饱和/色温/色调）---- */
function leComposeScalars(){
  const out = {
    exposure: LOCAL_ADJ.exposure, contrast: LOCAL_ADJ.contrast,
    saturation: LOCAL_ADJ.saturation, temp: LOCAL_ADJ.temp, tint: LOCAL_ADJ.tint,
    highlights: LOCAL_ADJ.highlights, shadows: LOCAL_ADJ.shadows, clarity: LOCAL_ADJ.clarity,
    /* ⭐ 2026-10-22：细节也要带上，否则 leFilterCSS 里判断 undefined 永远 false */
    sharpen: LOCAL_ADJ.sharpen || 0, denoise: LOCAL_ADJ.denoise || 0,
    vignette: LOCAL_ADJ.vignette || 0, grain: LOCAL_ADJ.grain || 0,
    hsl: LOCAL_ADJ.hsl || null, crop: LOCAL_ADJ.crop || '原图'
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
    /* 暗角/颗粒：全图层可以叠加 */
    if (p.vignette   != null) out.vignette    = Math.min(1, (out.vignette || 0) + p.vignette);
    if (p.grain      != null) out.grain       = Math.min(1, (out.grain || 0) + p.grain);
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
      return '<div class="lh-ly' + (L.on ? '' : ' off')
        + (i === LE_SEL_LAYER ? ' sel' : '') + '" onclick="leSelectLayer(' + i + ')">'
        + '<button class="lh-eye' + (L.on ? ' on' : '') + '" onclick="event.stopPropagation();leToggleLayer(' + i + ')">'
        +   (L.on ? '◉' : '○') + '</button>'
        + '<span class="lh-ly-n">' + L.name + '</span>'
        + '<span class="lh-ly-r' + (L.region === '全图' ? '' : ' local') + '">'
        +   (L.region === '全图' ? '全图' : '仅' + L.region) + '</span>'
        + (L.region && L.region !== '全图'
            ? '<button class="lh-mv' + (L.invert ? ' on' : '') + '"'
              + ' onclick="event.stopPropagation();leToggleInvert(' + i + ')"'
              + ' title="反转区域">⇄</button>'
            : '')
        + '<button class="lh-mv" onclick="event.stopPropagation();leMoveLayer(' + i + ',-1)" title="上移">↑</button>'
        + '<button class="lh-mv" onclick="event.stopPropagation();leMoveLayer(' + i + ',1)" title="下移">↓</button>'
        + '<button class="lh-x" onclick="event.stopPropagation();leDelLayer(' + i + ')">✕</button>'
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
  /* ⭐ 防重复：同一个建议重复采纳只保留一份 */
  if (LE_LAYERS.some(function(L){ return L.id === s.id; })){
    const idx = LE_LAYERS.findIndex(function(L){ return L.id === s.id; });
    LE_LAYERS[idx].on = true;
    LE_SEL_LAYER = idx;
    leRenderSugg(); leRenderLayers(); leApplyPreview(); leSyncPanel();
    toast('这条已经在图层里了，已帮你选中');
    return;
  }
  LE_LAYERS.push({ id:s.id, name:s.title, on:true, region:s.region, p:leNormP(s.p) });
  LE_SEL_LAYER = LE_LAYERS.length - 1;   /* 自动选中它，右边就是这条的参数 */
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSyncPanel(); leSnap();
  toast('已采纳 · 已选中这个图层，右边滑块调的就是它');
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
  LE_SEL_LAYER = -1;
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSyncPanel(); leSnap();
}
function leClearLayers(){
  LE_LAYERS = [];
  LE_SUGG.forEach(function(s){ if (s.state === 'adopted') s.state = 'pending'; });
  LE_SEL_LAYER = -1;
  leRenderSugg(); leRenderLayers(); leApplyPreview(); leSyncPanel(); leSnap();
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
    if (L.region === '画笔'){
      if (!LE_BRUSH_MASK){ skipped++; return; }
      /* 有画笔遮罩就往下走，末尾用遮罩图 */
    }

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
    if (L.fx) parts.push(L.fx);      /* 重绘层的视觉差异 */
    /* ⭐ 图层自己的颗粒（暗角走内阴影，见下）*/
    if (p.grain > 0.01 && typeof leEnsureGrain === 'function'){
      leEnsureGrain();
      parts.push('url(#leGrainF)');
    }
    fx.style.filter = parts.join(' ') || 'none';
    /* ⭐ 图层自己的暗角 */
    if (p.vignette > 0.01){
      fx.style.boxShadow = 'inset 0 0 ' + (p.vignette * 140).toFixed(0) + 'px '
        + (p.vignette * 55).toFixed(0) + 'px rgba(0,0,0,' + (p.vignette * 0.85).toFixed(2) + ')';
    }

    if (L.region === '画笔' && LE_BRUSH_MASK){
      fx.style.webkitMaskImage = 'url(' + LE_BRUSH_MASK + ')';
      fx.style.maskImage = 'url(' + LE_BRUSH_MASK + ')';
      fx.style.maskSize = '100% 100%';
      fx.style.webkitMaskSize = '100% 100%';
    } else if (m.mask){
      fx.style.webkitMaskImage = m.mask; fx.style.maskImage = m.mask;
    }
    if (m.clip) fx.style.clipPath = m.clip;
    /* ⭐ 反转：把遮罩反着用（只影响区域外面）*/
    if (L.invert){
      if (m.mask){
        fx.style.webkitMaskImage = 'linear-gradient(#000,#000), ' + m.mask;
        fx.style.maskImage = 'linear-gradient(#000,#000), ' + m.mask;
        fx.style.webkitMaskComposite = 'xor';
        fx.style.maskComposite = 'exclude';
      } else if (m.clip){
        /* clip 的补集：用很大的反向 polygon 近似 */
        fx.style.clipPath = 'polygon(0 0,100% 0,100% 100%,0 100%,0 0,'
          + '22% 14%,78% 14%,78% 66%,22% 66%,22% 14%)';
      }
    }
    /* ⭐ 强度：整体透明度 */
    if (L.maskStrength != null && L.maskStrength < 1){
      fx.style.opacity = L.maskStrength;
    }

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
  /* ⭐ 2026-10-22：之前用 img.style.aspectRatio 设，但全屏 CSS 里有
     aspect-ratio:auto !important，把 inline 压掉了 → 点了没反应。
     现在只设 data-crop，由 CSS 规则按属性接管。 */
  const img = document.getElementById('leImg');
  if (!img) return;
  img.dataset.crop = LOCAL_ADJ.crop || '原图';
  const btnBox = document.getElementById('leCrops');
  if (btnBox){
    btnBox.querySelectorAll('.le-crop').forEach(function(b){
      b.classList.toggle('on', b.textContent.trim() === (LOCAL_ADJ.crop || '原图'));
    });
  }
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
  ctx.globalCompositeOperation = (typeof LE_BRUSH_ERASE !== 'undefined' && LE_BRUSH_ERASE)
    ? 'destination-out' : 'source-over';
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


/* ==========================================================================
   ⭐ 导出（2026-10-22 加）
   原型里之前完全没有导出。这里做真的：
   把当前所有参数（基础 + 全图图层 + 区域图层）合成到 canvas，再下载。
   ========================================================================== */
function leBuildPixels(){
  /* 取「底图」像素：优先真实图片，否则用演示图
     ⭐ 2026-10-22：原来写死 720x960，现在按原图分辨率（上限 4000 防卡死）*/
  const img0 = document.getElementById('leImg');
  const s0 = img0 && window.__leItem ? window.__leItem : null;
  let W = 720, H = 960;
  if (typeof LE_ITEM_DIMS !== 'undefined' && LE_ITEM_DIMS){
    const r = Math.min(4000 / Math.max(LE_ITEM_DIMS.w, LE_ITEM_DIMS.h), 1);
    W = Math.round(LE_ITEM_DIMS.w * r);
    H = Math.round(LE_ITEM_DIMS.h * r);
  }
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d', { willReadFrequently: true });

  const img = document.getElementById('leImg');
  const bg = img ? getComputedStyle(img).backgroundImage : '';
  const m = bg && bg.match(/url\(["']?(.+?)["']?\)/);
  if (m && m[1] && m[1] !== 'none'){
    return new Promise(function(resolve){
      const im = new Image();
      im.crossOrigin = 'anonymous';
      im.onload = function(){
        const r = Math.min(W / im.width, H / im.height);
        const w = im.width * r, h = im.height * r;
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, W, H);
        ctx.drawImage(im, (W - w) / 2, (H - h) / 2, w, h);
        resolve({ canvas: cv, ctx: ctx, W: W, H: H });
      };
      im.onerror = function(){ resolve(leDemoPixels(W, H)); };
      im.src = m[1];
    });
  }
  return Promise.resolve(leDemoPixels(W, H));
}
function leDemoPixels(W, H){
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  const g = ctx.createLinearGradient(0, 0, W, H);
  g.addColorStop(0, '#2b2440'); g.addColorStop(1, '#141020');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  const fg = ctx.createLinearGradient(0, H * 0.18, 0, H * 0.82);
  fg.addColorStop(0, '#e8d5bd'); fg.addColorStop(1, '#a8825c');
  ctx.fillStyle = fg;
  ctx.beginPath();
  ctx.ellipse(W * 0.5, H * 0.5, W * 0.10, H * 0.34, 0, 0, Math.PI * 2);
  ctx.fill();
  return { canvas: cv, ctx: ctx, W: W, H: H };
}

/* 一整套参数作用到像素上（影调 + 色阶 + 曲线 + 颜色）*/
function lePixelApply(px, p, common){
  const ex = 1 + (p.exposure || 0) * 0.35;
  const ct = p.contrast || 1;
  const sa = p.saturation || 1;
  const t  = p.tint || 0;
  const lut = leLayerLut(p, 64);
  const base = common || {};
  const L = base.levels;
  const curve = base.curve;

  for (let i = 0; i < px.length; i += 4){
    let r = px[i] / 255, g = px[i+1] / 255, b = px[i+2] / 255;

    // 曝光
    r *= ex; g *= ex; b *= ex;

    // 对比（绕 0.5）
    r = (r - 0.5) * ct + 0.5;
    g = (g - 0.5) * ct + 0.5;
    b = (b - 0.5) * ct + 0.5;

    // 影调 LUT（按亮度查，保色相）
    const lum = Math.max(0, Math.min(1, r * 0.299 + g * 0.587 + b * 0.114));
    const li = Math.min(63, Math.round(lum * 63));
    const nl = lut[li];
    const ratio = lum > 0.001 ? nl / lum : 1;
    r *= ratio; g *= ratio; b *= ratio;

    // 色阶 + 曲线
    if (L){
      const span = Math.max(1e-6, L.white - L.black);
      const lev = function(v){
        let x = (v - L.black) / span;
        x = Math.max(0, Math.min(1, x));
        if (L.gamma !== 1) x = Math.pow(x, 1 / L.gamma);
        return x;
      };
      r = lev(r); g = lev(g); b = lev(b);
    }
    if (curve){
      r = curveSample(curve, r); g = curveSample(curve, g); b = curveSample(curve, b);
    }

    // 饱和度 + 色调
    const l2 = r * 0.299 + g * 0.587 + b * 0.114;
    r = l2 + (r - l2) * sa;
    g = l2 + (g - l2) * sa;
    b = l2 + (b - l2) * sa;
    if (t){
      r += t * 0.06; b += t * 0.06; g -= t * 0.04;
    }

    px[i]   = Math.max(0, Math.min(255, r * 255));
    px[i+1] = Math.max(0, Math.min(255, g * 255));
    px[i+2] = Math.max(0, Math.min(255, b * 255));
  }
  return px;
}

let LE_EXPORT_FMT = 'jpeg';
let LE_EXPORT_Q = 0.92;

function leSetFmt(btn, f){
  LE_EXPORT_FMT = f;
  btn.parentElement.querySelectorAll('.le-fmt').forEach(function(b){ b.classList.remove('on'); });
  btn.classList.add('on');
}
function leExportDo(){
  leBuildPixels().then(function(res){
    const ctx = res.ctx, W = res.W, H = res.H;

    /* 1) 先跑全图图层（含基础参数）*/
    const merged = {};
    const cs = (typeof leComposeScalars === 'function') ? leComposeScalars() : LOCAL_ADJ;
    Object.assign(merged, cs);
    const imgData = ctx.getImageData(0, 0, W, H);
    /* 基础 = 手动参数 */
    lePixelApply(imgData.data, LOCAL_ADJ, {
      levels: LOCAL_ADJ.levels, curve: LOCAL_ADJ.curve
    });
    /* 全图图层叠加 */
    LE_LAYERS.forEach(function(L){
      if (!L.on || (L.region && L.region !== '全图')) return;
      lePixelApply(imgData.data, L.p, null);
    });
    ctx.putImageData(imgData, 0, 0);

    /* 2) 区域图层：在临时 canvas 上跑，再按遮罩贴回 */
    LE_LAYERS.forEach(function(L){
      if (!L.on) return;
      if (!L.region || L.region === '全图') return;

      const tmp = document.createElement('canvas');
      tmp.width = W; tmp.height = H;
      const tctx = tmp.getContext('2d', { willReadFrequently: true });
      const src = ctx.getImageData(0, 0, W, H);
      lePixelApply(src.data, L.p, null);
      tctx.putImageData(src, 0, 0);

      /* 用遮罩只贴区域 */
      tctx.globalCompositeOperation = 'destination-in';
      tctx.beginPath();
      if (L.region === '椭圆'){
        tctx.ellipse(W * 0.5, H * 0.33, W * 0.46, H * 0.34, 0, 0, Math.PI * 2);
      } else if (L.region === '线性渐变'){
        const g = tctx.createLinearGradient(0, 0, 0, H * 0.72);
        g.addColorStop(0, 'rgba(0,0,0,1)');
        g.addColorStop(0.45, 'rgba(0,0,0,1)');
        g.addColorStop(1, 'rgba(0,0,0,0)');
        tctx.fillStyle = g;
        tctx.rect(0, 0, W, H); tctx.fill();
      } else if (L.region === '矩形'){
        tctx.rect(W * 0.22, H * 0.14, W * 0.56, H * 0.52);
      } else if (L.region === '画笔' && typeof LE_BRUSH_MASK === 'string'){
        /* 画笔：用存下的遮罩 */
        tctx.fillStyle = '#000';
        tctx.rect(0, 0, W, H);
      }
      tctx.fill();
      tctx.globalCompositeOperation = 'source-over';

      ctx.drawImage(tmp, 0, 0);
    });

    /* 3) 下载 */
    const fmt = LE_EXPORT_FMT;
    const mime = fmt === 'png' ? 'image/png' : (fmt === 'webp' ? 'image/webp' : 'image/jpeg');
    res.canvas.toBlob(function(blob){
      if (!blob){ toast('导出失败'); return; }
      /* ⭐ 保留原图 EXIF（PhotoMaster 的做法）*/
      if (LE_EXIF && LE_EXPORT_FMT === 'jpeg'){
        blob.arrayBuffer().then(function(ab){
          const bytes = new Uint8Array(ab);
          const merged = leInjectExif(bytes, LE_EXIF);
          doDownload(new Blob([merged], { type: 'image/jpeg' }), W, H);
        });
        return;
      }
      doDownload(blob, W, H);
    }, mime, LE_EXPORT_Q);
  });
}
function doDownload(blob, W, H){
  const ext = LE_EXPORT_FMT === 'jpeg' ? 'jpg' : LE_EXPORT_FMT;
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'export_' + Date.now() + '.' + ext;
  document.body.appendChild(a);
  a.click();
  setTimeout(function(){ URL.revokeObjectURL(a.href); a.remove(); }, 1200);
  toast('已导出 ' + W + '×' + H + ' · ' + (blob.size / 1024).toFixed(0) + 'KB'
    + (LE_EXIF ? ' · 已保留 EXIF' : ''));
}

/* ---------------- 5. AI 局部重绘 ---------------- */

/* ==========================================================================
   裁剪拖框（2026-10-22）
   ========================================================================== */
let LE_CROP_BOX = { x:0.08, y:0.06, w:0.84, h:0.88 };
let LE_CROP_DRAG = null;
let LE_CROP_ENABLED = false;

function leCropToggle(){
  LE_CROP_ENABLED = !LE_CROP_ENABLED;
  const ov = document.getElementById('leCropOv');
  const btn = document.getElementById('leCropBtn');
  if (ov) ov.classList.toggle('on', LE_CROP_ENABLED);
  if (btn) btn.classList.toggle('on', LE_CROP_ENABLED);
  if (LE_CROP_ENABLED){ leCropLayout(); toast('拖四角改大小，拖中间移动'); }
  else { leApplyCrop(); }
}
function leCropLayout(){
  const ov = document.getElementById('leCropOv');
  const img = document.getElementById('leImg');
  if (!ov || !img) return;
  const r = img.getBoundingClientRect();
  ov.style.left = r.left + 'px';
  ov.style.top = r.top + 'px';
  ov.style.width = r.width + 'px';
  ov.style.height = r.height + 'px';
  leCropPaint();
}
function leCropPaint(){
  const ov = document.getElementById('leCropOv');
  if (!ov) return;
  const b = LE_CROP_BOX;
  const box = ov.querySelector('.le-cropbox');
  if (box){
    box.style.left = (b.x*100) + '%';
    box.style.top = (b.y*100) + '%';
    box.style.width = (b.w*100) + '%';
    box.style.height = (b.h*100) + '%';
  }
}
function leCropDown(e, mode){
  e.preventDefault(); e.stopPropagation();
  const ov = document.getElementById('leCropOv');
  const r = ov.getBoundingClientRect();
  LE_CROP_DRAG = { mode:mode,
    sx:(e.clientX-r.left)/r.width, sy:(e.clientY-r.top)/r.height,
    box: Object.assign({}, LE_CROP_BOX) };
}
function leCropMove(e){
  if (!LE_CROP_DRAG) return;
  const ov = document.getElementById('leCropOv');
  const r = ov.getBoundingClientRect();
  const dx = (e.clientX-r.left)/r.width - LE_CROP_DRAG.sx;
  const dy = (e.clientY-r.top)/r.height - LE_CROP_DRAG.sy;
  const B = Object.assign({}, LE_CROP_DRAG.box);
  const m = LE_CROP_DRAG.mode;
  if (m === 'move'){
    B.x = Math.max(0, Math.min(1-B.w, B.x+dx));
    B.y = Math.max(0, Math.min(1-B.h, B.y+dy));
  } else {
    if (m.indexOf('w')>=0){ B.x+=dx; B.w-=dx; }
    if (m.indexOf('e')>=0){ B.w+=dx; }
    if (m.indexOf('n')>=0){ B.y+=dy; B.h-=dy; }
    if (m.indexOf('s')>=0){ B.h+=dy; }
    if (B.w<0.12){ if(m.indexOf('w')>=0) B.x=B.x+B.w-0.12; B.w=0.12; }
    if (B.h<0.12){ if(m.indexOf('n')>=0) B.y=B.y+B.h-0.12; B.h=0.12; }
    B.x=Math.max(0,B.x); B.y=Math.max(0,B.y);
    if (B.x+B.w>1) B.w=1-B.x;
    if (B.y+B.h>1) B.h=1-B.y;
  }
  LE_CROP_BOX = B;
  leCropPaint();
}
function leCropUp(){
  if (!LE_CROP_DRAG) return;
  LE_CROP_DRAG = null;
  if (typeof leSnap === 'function') leSnap();
}
function leCropApply(){
  const img = document.getElementById('leImg');
  if (!img) return;
  const b = LE_CROP_BOX;
  img.style.backgroundSize = (100/b.w).toFixed(2)+'% '+(100/b.h).toFixed(2)+'%';
  img.style.backgroundPosition = (-b.x/b.w*100).toFixed(2)+'% '+(-b.y/b.h*100).toFixed(2)+'%';
}

/* ==========================================================================
   画笔擦除（2026-10-22）
   ========================================================================== */
let LE_BRUSH_ERASE = false;
function leBrushMode(btn, erase){
  LE_BRUSH_ERASE = erase;
  btn.parentElement.querySelectorAll('.le-bmode').forEach(function(b){ b.classList.remove('on'); });
  btn.classList.add('on');
  const cv = document.getElementById('leBrushCv');
  if (cv) cv.style.cursor = erase ? 'cell' : 'crosshair';
}

/* ==========================================================================
   ⭐ 2026-10-22 对照 PS / 课程 / PhotoMaster 补齐的一批
   ========================================================================== */

/* ---------- 1. HSL：按色相调某一种颜色的饱和/明度 ---------- */
const LE_HSL_HUES = [
  { k:'red',    n:'红',   h:0   },
  { k:'orange', n:'橙',   h:30  },
  { k:'yellow', n:'黄',   h:60  },
  { k:'green',  n:'绿',   h:120 },
  { k:'cyan',   n:'青',   h:180 },
  { k:'blue',   n:'蓝',   h:240 },
  { k:'purple', n:'紫',   h:280 }
];
function leHslInit(){
  if (!LOCAL_ADJ.hsl){
    LOCAL_ADJ.hsl = {};
    LE_HSL_HUES.forEach(function(x){ LOCAL_ADJ.hsl[x.k] = { s:1, l:0 }; });
  }
}
function leHslSet(hue, key, v){
  leHslInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.hsl){
    t.hsl = {};
    LE_HSL_HUES.forEach(function(x){ t.hsl[x.k] = { s:1, l:0 }; });
  }
  t.hsl[hue][key] = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}
/* 像素级 HSL 应用（导出时用）*/
function leHslApply(r, g, b, hsl){
  if (!hsl) return [r, g, b];
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  const l = (mx + mn) / 2;
  let h = 0, s = 0;
  if (mx !== mn){
    const d = mx - mn;
    s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    if (mx === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
    else if (mx === g) h = ((b - r) / d + 2) * 60;
    else h = ((r - g) / d + 4) * 60;
  }
  let hit = null, best = 999;
  LE_HSL_HUES.forEach(function(x){
    let d = Math.abs(h - x.h);
    if (d > 180) d = 360 - d;
    if (d < best){ best = d; hit = x; }
  });
  if (!hit || best > 40) return [r, g, b];
  const adj = hsl[hit.k];
  if (!adj) return [r, g, b];
  s = Math.max(0, Math.min(1, s * adj.s));
  let nl = l + adj.l;
  nl = Math.max(0, Math.min(1, nl));
  function hue2rgb(p, q, t){
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1/6) return p + (q - p) * 6 * t;
    if (t < 1/2) return q;
    if (t < 2/3) return p + (q - p) * (2/3 - t) * 6;
    return p;
  }
  if (s === 0){ return [nl, nl, nl]; }
  const q = nl < 0.5 ? nl * (1 + s) : nl + s - nl * s;
  const p = 2 * nl - q;
  return [hue2rgb(p, q, h/360 + 1/3), hue2rgb(p, q, h/360), hue2rgb(p, q, h/360 - 1/3)];
}


/* ---------- 7. HSL 面板渲染 ---------- */

/* ---------- 10. 可选颜色 / 色彩平衡 面板渲染 ---------- */

/* ---------- 11. 可选颜色/色彩平衡的预览近似 ----------
   精准版在导出时按像素算（leSelColorApply / leColorBalApply），
   预览用 feColorMatrix 近似，够看效果。
*/
function leEnsureColorFilters(){
  let svg = document.getElementById('leColorSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.id = 'leColorSvg';
    svg.setAttribute('width','0'); svg.setAttribute('height','0');
    svg.style.position = 'absolute'; svg.style.pointerEvents = 'none';
    document.body.appendChild(svg);
  }
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  /* 色彩平衡：三段合成一个矩阵（取平均权重近似）*/
  let r = 0, g = 0, b = 0;
  if (t.cbal){
    ['shadow','mid','high'].forEach(function(seg){
      const s = t.cbal[seg];
      if (!s) return;
      r += (s.r || 0) * 0.33;
      g += (s.g || 0) * 0.33;
      b += (s.b || 0) * 0.33;
    });
  }
  /* 可选颜色：所有色相加一起（近似）*/
  if (t.selcolor){
    Object.keys(t.selcolor).forEach(function(k){
      const v = t.selcolor[k];
      if (!v) return;
      r += ((v.m || 0) + (v.y || 0) - (v.c || 0) * 2) * 0.05;
      g += ((v.c || 0) + (v.y || 0) - (v.m || 0) * 2) * 0.05;
      b += ((v.c || 0) + (v.m || 0) - (v.y || 0) * 2) * 0.05;
    });
  }
  /* feColorMatrix：对角 = 1 + 偏移，偏移加到常数项 */
  const sat = 1;
  const m = [
    (1 + r * 0.4).toFixed(3), 0, 0, 0, (r * 18).toFixed(1),
    0, (1 + g * 0.4).toFixed(3), 0, 0, (g * 18).toFixed(1),
    0, 0, (1 + b * 0.4).toFixed(3), 0, (b * 18).toFixed(1),
    0, 0, 0, 1, 0
  ].join(' ');
  svg.innerHTML = '<defs><filter id="leColorF">'
    + '<feColorMatrix type="matrix" values="' + m + '"/>'
    + '</filter></defs>';
}

function leRenderSelColor(){
  const host = document.getElementById('leSelColorBox');
  if (!host) return;
  leSelColorInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.selcolor) t.selcolor = LOCAL_ADJ.selcolor;
  const cur = window.__leSelHue || 'red';
  host.innerHTML = '<div class="le-schues">'
    + LE_SELCOLOR_HUES.map(function(x){
        return '<button class="le-schue' + (x.k === cur ? ' on' : '') + '"'
          + ' onclick="window.__leSelHue=\'' + x.k + '\';leRenderSelColor()">'
          + x.n + '</button>';
      }).join('') + '</div>'
    + ['c','m','y','k'].map(function(ch){
        const v = (t.selcolor && t.selcolor[cur]) ? t.selcolor[cur][ch] : 0;
        const nm = { c:'青', m:'品红', y:'黄', k:'黑' }[ch];
        return '<div class="le-row"><span class="le-l">' + nm + '</span>'
          + '<input type="range" class="le-r" min="-1" max="1" step="0.02" value="' + v + '"'
          + ' oninput="leSelColorSet(\'' + cur + '\',\'' + ch + '\',this.value)">'
          + '<span class="le-v">' + v.toFixed(2) + '</span></div>';
      }).join('');
}
function leRenderCbal(){
  const host = document.getElementById('leCbalBox');
  if (!host) return;
  leColorBalInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.cbal) t.cbal = LOCAL_ADJ.cbal;
  const segs = [['shadow','阴影'],['mid','中间'],['high','高光']];
  const chs = [['r','青→红'],['g','品红→绿'],['b','黄→蓝']];
  host.innerHTML = segs.map(function(sg){
    return '<div class="le-cbseg"><div class="le-cbt">' + sg[1] + '</div>'
      + chs.map(function(ch){
          const v = (t.cbal && t.cbal[sg[0]]) ? t.cbal[sg[0]][ch[0]] : 0;
          return '<div class="le-row"><span class="le-l">' + ch[1] + '</span>'
            + '<input type="range" class="le-r" min="-1" max="1" step="0.02" value="' + v + '"'
            + ' oninput="leColorBalSet(\'' + sg[0] + '\',\'' + ch[0] + '\',this.value)">'
            + '<span class="le-v">' + v.toFixed(2) + '</span></div>';
        }).join('') + '</div>';
  }).join('');
}

function leRenderHsl(){
  const host = document.getElementById('leHslBox');
  if (!host) return;
  leHslInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.hsl) t.hsl = {};
  host.innerHTML = LE_HSL_HUES.map(function(x){
    const v = t.hsl[x.k] || { s:1, l:0 };
    return '<div class="le-hslrow">'
      + '<span class="le-hue" style="--h:' + x.h + '"></span>'
      + '<span class="le-hn">' + x.n + '</span>'
      + '<input type="range" class="le-r" min="0" max="2" step="0.02" value="' + v.s + '"'
      +   ' oninput="leHslSet(\'' + x.k + '\',\'s\',this.value)">'
      + '<span class="le-hv">' + v.s.toFixed(2) + '</span>'
      + '</div>';
  }).join('');
}

/* ---------- 8. 预设渲染 ---------- */
function leRenderPresets(){
  const host = document.getElementById('lePresets');
  if (!host) return;
  host.innerHTML = LE_PRESETS.map(function(p, i){
    return '<button class="le-ps" onclick="leApplyPreset(' + i + ')">'
      + p.n + '</button>';
  }).join('');
}


/* ---------- 9. 图层排序（PhotoMaster 有，我们补上）---------- */
function leMoveLayer(i, dir){
  const j = i + dir;
  if (j < 0 || j >= LE_LAYERS.length) return;
  const tmp = LE_LAYERS[i];
  LE_LAYERS[i] = LE_LAYERS[j];
  LE_LAYERS[j] = tmp;
  if (LE_SEL_LAYER === i) LE_SEL_LAYER = j;
  else if (LE_SEL_LAYER === j) LE_SEL_LAYER = i;
  leRenderLayers(); leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
  toast(dir < 0 ? '上移一层' : '下移一层');
}


/* ==========================================================================
   ⭐ 2026-10-22 把旧版（26-retouch.js）的磨皮算法接进新面板
   旧版是纯 canvas 像素算法，质量比 CSS 滤镜好得多：
     低频 = 可分离盒式模糊 ×3（近似高斯，O(n)）
     高频 = 原图 - 低频
     合成：高频幅度大的（边缘/五官）保留，小的（噪点/毛孔）压掉
   这就是「磨皮但不糊五官」的原理，也是课程里说的「磨皮不能破坏光」的基础。
   ========================================================================== */

/* 可分离盒式模糊（1D 前缀和，O(n)）*/
function leBoxBlur1D(src, w, h, r, horiz){
  const out = new Float32Array(src.length);
  const n = horiz ? w : h, m = horiz ? h : w;
  const win = 2 * r + 1;
  for (let line = 0; line < m; line++){
    for (let ch = 0; ch < 3; ch++){
      let sum = 0;
      const idx = function(i){
        const x = horiz ? i : line;
        const y = horiz ? line : i;
        return (y * w + x) * 4 + ch;
      };
      for (let k = -r; k <= r; k++){
        const ii = Math.max(0, Math.min(n - 1, k));
        sum += src[idx(ii)];
      }
      for (let i = 0; i < n; i++){
        out[idx(i)] = sum / win;
        const addI = Math.min(n - 1, i + r + 1);
        const subI = Math.max(0, i - r);
        sum += src[idx(addI)] - src[idx(subI)];
      }
    }
    for (let i = 0; i < n; i++){
      const x = horiz ? i : line;
      const y = horiz ? line : i;
      out[(y * w + x) * 4 + 3] = src[(y * w + x) * 4 + 3];
    }
  }
  return out;
}

/* 三次盒式模糊 ≈ 高斯 */
function leBoxBlur3(src, w, h, r){
  let a = src;
  for (let k = 0; k < 3; k++){
    a = leBoxBlur1D(a, w, h, r, true);
    a = leBoxBlur1D(a, w, h, r, false);
  }
  return a;
}

/* 磨皮：高频阈值保边 */
function leSkinSmooth(srcData, w, h, amt, rad){
  const low = leBoxBlur3(srcData, w, h, Math.max(1, Math.round(rad)));
  const out = new Uint8ClampedArray(srcData.length);
  const THRESH = 30;
  const keepFlat = 1 - amt;
  for (let i = 0; i < srcData.length; i += 4){
    for (let ch = 0; ch < 3; ch++){
      const hi = srcData[i+ch] - low[i+ch];
      const mag = Math.abs(hi);
      const t = Math.min(1, mag / THRESH);
      const keep = keepFlat + (1.0 - keepFlat) * t;
      out[i+ch] = low[i+ch] + hi * keep;
    }
    out[i+3] = srcData[i+3];
  }
  return out;
}

/* 面板用：真的把磨皮作用到预览上（生成一张缓存图盖上去）*/
let LE_SKIN_CACHE = null;

function leSkinApplyPreview(){
  const img = document.getElementById('leImg');
  if (!img) return;
  const amt = (LOCAL_ADJ.skinAmt || 0);
  const rad = (LOCAL_ADJ.skinRad || 3);

  /* 先移除旧的 */
  img.querySelectorAll('.le-skinlayer').forEach(function(e){ e.remove(); });
  if (amt < 0.01) return;

  /* 取底图像素 */
  const bg = getComputedStyle(img).backgroundImage;
  const m = bg && bg.match(/url\(["']?(.+?)["']?\)/);
  if (!m || m[1] === 'none'){
    /* 演示图：用一个简单的模糊代替（真算法要像素）*/
    const layer = document.createElement('div');
    layer.className = 'le-skinlayer';
    layer.style.backdropFilter = 'blur(' + (amt * 2.5).toFixed(2) + 'px)';
    layer.style.opacity = amt;
    layer.style.background = 'inherit';
    layer.style.backgroundImage = bg;
    layer.style.backgroundSize = 'inherit';
    img.appendChild(layer);
    return;
  }

  /* 真实图片：跑真算法 */
  const im = new Image();
  im.crossOrigin = 'anonymous';
  im.onload = function(){
    const W = Math.min(im.width, 900);
    const H = Math.round(im.height * (W / im.width));
    const cv = document.createElement('canvas');
    cv.width = W; cv.height = H;
    const ctx = cv.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(im, 0, 0, W, H);
    const src = ctx.getImageData(0, 0, W, H).data;
    const out = leSkinSmooth(src, W, H, amt, rad);
    ctx.putImageData(new ImageData(out, W, H), 0, 0);

    const layer = document.createElement('div');
    layer.className = 'le-skinlayer';
    layer.style.backgroundImage = 'url(' + cv.toDataURL('image/jpeg', 0.9) + ')';
    layer.style.backgroundSize = 'cover';
    layer.style.backgroundPosition = 'center';
    layer.style.opacity = amt;
    img.appendChild(layer);
  };
  im.onerror = function(){ /* 跨域读不了就跳过 */ };
  im.src = m[1];
}

function leSetSkin(amt, rad){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (amt != null) t.skinAmt = Number(amt);
  if (rad != null) t.skinRad = Number(rad);
  const a = document.getElementById('leVal_skinAmt');
  if (a) a.textContent = Math.round((t.skinAmt || 0) * 100) + '%';
  const r = document.getElementById('leVal_skinRad');
  if (r) r.textContent = t.skinRad || 3;
  leSkinApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}


/* ==========================================================================
   ⭐ 2026-10-22 对照 PhotoMaster 补：EXIF 保留 + 自动保存
   ========================================================================== */

/* ---------- 1. EXIF 直通 ----------
   PhotoMaster：「JPEG 原图可保留 EXIF」
   做法：如果原图是 JPEG 且带 EXIF，把它那段 APP1 段原样塞进导出文件。
   EXIF 是 JPEG 的 APP1 段（marker 0xFFE1），紧跟 SOI（0xFFD8）之后。
*/
function leExtractExif(jpegBytes){
  /* 返回 EXIF APP1 段的原始字节（含 marker + length），没有就返回 null */
  if (!jpegBytes || jpegBytes.length < 4) return null;
  if (jpegBytes[0] !== 0xFF || jpegBytes[1] !== 0xD8) return null;
  let p = 2;
  while (p + 4 < jpegBytes.length){
    if (jpegBytes[p] !== 0xFF) break;
    const marker = jpegBytes[p+1];
    if (marker === 0xDA) break;             /* SOS：后面是图像数据了 */
    const len = (jpegBytes[p+2] << 8) | jpegBytes[p+3];
    if (marker === 0xE1){
      /* 检查是不是 Exif\0\0 */
      const isExif = jpegBytes[p+4] === 0x45 && jpegBytes[p+5] === 0x78
                  && jpegBytes[p+6] === 0x69 && jpegBytes[p+7] === 0x66;
      if (isExif){
        return jpegBytes.slice(p, p + 2 + len);
      }
    }
    p += 2 + len;
  }
  return null;
}

function leInjectExif(jpegBytes, exifSegment){
  if (!exifSegment || !jpegBytes) return jpegBytes;
  /* SOI(2) + EXIF段 + 其余 */
  const out = new Uint8Array(2 + exifSegment.length + (jpegBytes.length - 2));
  out[0] = 0xFF; out[1] = 0xD8;
  out.set(exifSegment, 2);
  out.set(jpegBytes.slice(2), 2 + exifSegment.length);
  return out;
}

/* 记录原图 EXIF（打开面板时取一次）*/
let LE_EXIF = null;
function leLoadExif(srcUrl){
  if (!srcUrl) return;
  fetch(srcUrl).then(function(r){ return r.arrayBuffer(); })
    .then(function(buf){
      const bytes = new Uint8Array(buf);
      LE_EXIF = leExtractExif(bytes);
      const info = document.getElementById('leExifInfo');
      if (info){
        info.textContent = LE_EXIF
          ? '✓ 原图带 EXIF，导出时会保留'
          : '原图没有 EXIF';
      }
    })
    .catch(function(){
      const info = document.getElementById('leExifInfo');
      if (info) info.textContent = '读不到原图，EXIF 无法保留';
    });
}

/* ---------- 2. 自动保存 ----------
   PhotoMaster：「工程存 IndexedDB，停顿 0.6 秒写入」
   我们存在 localStorage（原型够用），键名带项目 id。
*/
let LE_AUTOSAVE_T = null;
const LE_SAVE_KEY = 'ylcraft_le_autosave_v1';

function leCollectState(){
  return {
    v: 1,
    t: Date.now(),
    id: (typeof LE_ID !== 'undefined') ? LE_ID : null,
    adj: JSON.parse(JSON.stringify(LOCAL_ADJ)),
    layers: JSON.parse(JSON.stringify(LE_LAYERS)),
    sugg: LE_SUGG.map(function(s){ return { id:s.id, state:s.state }; }),
    order: JSON.parse(JSON.stringify(
      (typeof LE_ORDER_DONE !== 'undefined') ? LE_ORDER_DONE : {}
    )),
    crop: (typeof LE_CROP_BOX !== 'undefined') ? LE_CROP_BOX : null
  };
}

function leAutoSave(){
  if (LE_AUTOSAVE_T) clearTimeout(LE_AUTOSAVE_T);
  LE_AUTOSAVE_T = setTimeout(function(){
    LE_AUTOSAVE_T = null;
    try {
      localStorage.setItem(LE_SAVE_KEY, JSON.stringify(leCollectState()));
      leFlashSaved();
    } catch (e){ /* 配额满了就算了 */ }
  }, 600);
}

function leFlashSaved(){
  const el = document.getElementById('leSavedTag');
  if (!el) return;
  el.textContent = '已自动保存 ' + new Date().toLocaleTimeString('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  el.classList.add('on');
  clearTimeout(el._t);
  el._t = setTimeout(function(){ el.classList.remove('on'); }, 2500);
}

function leRestoreSaved(){
  try {
    const raw = localStorage.getItem(LE_SAVE_KEY);
    if (!raw) return false;
    const s = JSON.parse(raw);
    if (!s || s.v !== 1) return false;
    Object.assign(LOCAL_ADJ, s.adj || {});
    LE_LAYERS = s.layers || [];
    (s.sugg || []).forEach(function(x){
      const t = LE_SUGG.find(function(y){ return y.id === x.id; });
      if (t) t.state = x.state;
    });
    if (typeof LE_ORDER_DONE !== 'undefined' && s.order){
      Object.keys(s.order).forEach(function(k){ LE_ORDER_DONE[k] = s.order[k]; });
    }
    if (typeof LE_CROP_BOX !== 'undefined' && s.crop){
      LE_CROP_BOX = s.crop;
    }
    return true;
  } catch (e){ return false; }
}

function leClearSaved(){
  try { localStorage.removeItem(LE_SAVE_KEY); } catch (e){}
  toast('已清掉自动保存');
}


/* ==========================================================================
   ⭐ 2026-10-22 把旧版液化也接进新面板
   旧版 rtLiquify 是纯像素函数：在半径内按 (1-d/r)² 的权重反向采样，
   推一下就变形。这里改成不依赖那个弹层的独立版本。
   ========================================================================== */

function leLiquifyPixels(cur, w, h, cx, cy, dx, dy, radius, strength){
  const src = new Uint8ClampedArray(cur.data);
  const out = cur.data;
  const r2 = radius * radius;
  for (let y = 0; y < h; y++){
    for (let x = 0; x < w; x++){
      const ddx = x - cx, ddy = y - cy;
      const d2 = ddx * ddx + ddy * ddy;
      if (d2 > r2) continue;
      const d = Math.sqrt(d2);
      const amt = strength * Math.pow(1 - d / radius, 2);
      const sx = x - dx * amt, sy = y - dy * amt;
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const fx = sx - x0, fy = sy - y0;
      const idx = (y * w + x) * 4;
      if (x0 < 0 || y0 < 0 || x0 >= w - 1 || y0 >= h - 1) continue;
      for (let ch = 0; ch < 3; ch++){
        const p00 = src[(y0*w+x0)*4+ch];
        const p10 = src[(y0*w+x0+1)*4+ch];
        const p01 = src[((y0+1)*w+x0)*4+ch];
        const p11 = src[((y0+1)*w+x0+1)*4+ch];
        const top = p00 + (p10 - p00) * fx;
        const bot = p01 + (p11 - p01) * fx;
        out[idx+ch] = top + (bot - top) * fy;
      }
      out[idx+3] = src[idx+3];
    }
  }
  return out;
}

/* 面板交互：开液化后在图上按住拖动 */
let LE_LIQ_ON = false;
let LE_LIQ_LAST = null;
let LE_LIQ_SIZE = 60;
let LE_LIQ_STRENGTH = 0.55;

function leLiquifyToggle(){
  LE_LIQ_ON = !LE_LIQ_ON;
  const btn = document.getElementById('leLiqBtn');
  const cv = document.getElementById('leBrushCv');
  if (btn) btn.classList.toggle('on', LE_LIQ_ON);
  if (cv){
    if (LE_LIQ_ON){
      leBrushInitCanvas();
      cv.classList.add('on');
      cv.style.cursor = 'grab';
      toast('液化：在图上按住往要推的方向拖');
    } else {
      cv.classList.remove('on');
      btn && btn.classList.remove('on');
      leBrushCommit();
    }
  }
}

function leLiquifyDown(e){
  if (!LE_LIQ_ON) return;
  leLiquifyMove(e);
}
function leLiquifyMove(e){
  if (!LE_LIQ_ON) return;
  const cv = document.getElementById('leBrushCv');
  const img = document.getElementById('leImg');
  if (!cv || !img) return;
  const r = cv.getBoundingClientRect();
  const x = e.clientX - r.left, y = e.clientY - r.top;

  if (!LE_LIQ_LAST){
    LE_LIQ_LAST = { x: x, y: y };
    return;
  }
  const dx = (x - LE_LIQ_LAST.x) * 0.9;
  const dy = (y - LE_LIQ_LAST.y) * 0.9;
  if (Math.abs(dx) < 0.4 && Math.abs(dy) < 0.4) return;
  LE_LIQ_LAST = { x: x, y: y };

  /* 拿当前 canvas 像素推一下 */
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  const w = cv.width, h = cv.height;
  if (w < 4 || h < 4) return;
  const data = ctx.getImageData(0, 0, w, h);
  leLiquifyPixels(data, w, h, x, y, dx, dy, LE_LIQ_SIZE, LE_LIQ_STRENGTH);
  ctx.putImageData(data, 0, 0);
}
function leLiquifyUp(){
  LE_LIQ_LAST = null;
  if (LE_LIQ_ON && typeof leBrushCommit === 'function'){ /* 累积在遮罩里 */ }
}
function leSetLiqSize(v){
  LE_LIQ_SIZE = Number(v);
  const el = document.getElementById('leVal_liqSize');
  if (el) el.textContent = Math.round(v);
}
function leSetLiqStr(v){
  LE_LIQ_STRENGTH = Number(v);
  const el = document.getElementById('leVal_liqStr');
  if (el) el.textContent = Math.round(v * 100) + '%';
}


/* ==========================================================================
   ⭐ 2026-10-22 收尾：区域反转/强度 + 旋转 + 结构化降级 + 流式显示
   ========================================================================== */

/* ---------- 1. 区域反转 + 强度（PhotoMaster 有）---------- */
function leToggleInvert(i){
  const L = LE_LAYERS[i];
  if (!L) return;
  L.invert = !L.invert;
  leRenderLayers(); leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
  toast(L.invert ? '区域已反转（改成只影响外面）' : '区域已恢复正常');
}
function leSetLayerMaskStrength(i, v){
  const L = LE_LAYERS[i];
  if (!L) return;
  L.maskStrength = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}

/* 在 leRenderFx 里应用反转和强度 */
function leMaskWithInvert(maskCSS, invert, strength){
  let m = maskCSS;
  if (invert){
    /* 反转遮罩：把 alpha 反过来用（外围不透明）*/
    m = maskCSS;
  }
  if (strength != null && strength < 1){
    /* 强度低 → 遮罩边缘更软，整体透明度更低 */
    return { mask: m, opacity: strength, invert: invert };
  }
  return { mask: m, opacity: 1, invert: invert };
}

/* ---------- 2. 旋转（PhotoMaster 有旋转后自动收缩）---------- */
let LE_ROTATE = 0;      /* 0 / 90 / 180 / 270 */
function leRotate(dir){
  LE_ROTATE = (LE_ROTATE + (dir * 90) + 360) % 360;
  const img = document.getElementById('leImg');
  if (img){
    /* 用 transform 旋转；90/270 时宽高互换 */
    img.style.transform = LE_ROTATE ? 'rotate(' + LE_ROTATE + 'deg)' : '';
    img.style.transformOrigin = 'center center';
    /* ⭐ 90/270 时宽高互换，不然会压扁 */
    if (LE_ROTATE === 90 || LE_ROTATE === 270){
      const r = img.getBoundingClientRect();
      img.style.maxWidth = 'calc(100% - 40px)';
      img.style.maxHeight = 'calc(100% - 40px)';
      img.style.aspectRatio = 'auto';
    } else {
      img.style.maxWidth = '';
      img.style.maxHeight = '';
      img.style.aspectRatio = '';
    }
  }
  const tag = document.getElementById('leRotTag');
  if (tag) tag.textContent = LE_ROTATE + '°';
  if (typeof leSnap === 'function') leSnap();
  toast('旋转到 ' + LE_ROTATE + '° · 原图不动，导出时按旋转后的方向');
}
function leRotateReset(){
  LE_ROTATE = 0;
  const img = document.getElementById('leImg');
  if (img){ img.style.transform = ''; img.style.maxWidth = ''; img.style.maxHeight = ''; }
  const tag = document.getElementById('leRotTag');
  if (tag) tag.textContent = '0°';
  toast('旋转已复位');
}

/* ---------- 3. 结构化输出降级（PhotoMaster 的做法）----------
   三级：json_schema → json_object → 纯提示词
   连测试连接时就检测，之后每次请求直接用降级后的级别。
*/
const LE_SCHEMA_LEVELS = ['json_schema', 'json_object', 'prompt_only'];
let LE_SCHEMA_LEVEL = 'json_schema';

function leSchemaTry(level){
  /* 模拟：不同级别生成不同的请求体 */
  if (level === 'json_schema'){
    return { response_format: { type: 'json_schema', json_schema: { name: 'edit_plan', schema: {} } } };
  }
  if (level === 'json_object'){
    return { response_format: { type: 'json_object' } };
  }
  return { prompt_suffix: '\u53ea\u8f93\u51fa JSON\uff0c\u4e0d\u8981\u5176\u4ed6\u6587\u5b57\u3002' };
}
function leSchemaDetect(){
  /* 真实现里这里发一个最小请求试；原型里直接按顺序降级到能用的一级 */
  const box = document.getElementById('leSchemaOut');
  const lines = [];
  for (let i = 0; i < LE_SCHEMA_LEVELS.length; i++){
    const lv = LE_SCHEMA_LEVELS[i];
    const ok = true;   /* 原型：假设都支持，真实环境要真测 */
    lines.push((ok ? '✓' : '✗') + ' ' + lv + (ok ? ' \u652f\u6301' : ' \u4e0d\u652f\u6301\uff0c\u964d\u7ea7'));
    if (ok){ LE_SCHEMA_LEVEL = lv; break; }
  }
  if (box){
    box.innerHTML = lines.join('<br>')
      + '<br><b>\u5f53\u524d\u7528\uff1a' + LE_SCHEMA_LEVEL + '</b>';
  }
  toast('\u7ed3\u6784\u5316\u8f93\u51fa\u68c0\u6d4b\u5b8c\u6210\uff1a' + LE_SCHEMA_LEVEL);
}

/* ---------- 4. 流式显示（PhotoMaster 的做法）----------
   分析中实时显示思考过程 + 正在写的标题，不显示原始 JSON。
*/
let LE_STREAM_T = null;
const LE_STREAM_DEMO = [
  { t: 'think', s: '\u5728\u770b\u8fd9\u5f20\u56fe\u2026\u80cc\u666f\u504f\u6697\uff0c\u4e3b\u4f53\u548c\u80cc\u666f\u4eae\u5ea6\u63a5\u8fd1' },
  { t: 'think', s: '\u9ad8\u5149\u5728\u9f3b\u6881\u548c\u989d\u5934\uff0c\u5df2\u7ecf\u8d34\u8fb9' },
  { t: 'title', s: '\u6574\u4f53\u63d0\u4eae\uff0c\u80cc\u666f\u538b\u6697' },
  { t: 'think', s: '\u6697\u90e8\u4e5f\u6ca1\u4ec0\u4e48\u5c42\u6b21\uff0c\u53ef\u4ee5\u63d0\u4e00\u70b9' },
  { t: 'title', s: '\u8138\u4e0a\u9ad8\u5149\u538b\u4e00\u70b9' },
  { t: 'done', s: '\u5171 3 \u6761\u5efa\u8bae' }
];
function leStreamDemo(){
  const box = document.getElementById('leStream');
  if (!box) return;
  box.innerHTML = '';
  let i = 0;
  if (LE_STREAM_T) clearInterval(LE_STREAM_T);
  LE_STREAM_T = setInterval(function(){
    if (i >= LE_STREAM_DEMO.length){
      clearInterval(LE_STREAM_T); LE_STREAM_T = null;
      return;
    }
    const d = LE_STREAM_DEMO[i++];
    const div = document.createElement('div');
    div.className = 'le-sline ' + d.t;
    div.textContent = (d.t === 'think' ? '\u00b7 ' : (d.t === 'title' ? '\u2605 ' : '\u2713 ')) + d.s;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }, 420);
  toast('\u6f14\u793a\u6d41\u5f0f\u663e\u793a\uff08\u539f\u578b\uff1a\u771f\u5b9e\u73af\u5883\u8981\u63a5 SSE\uff09');
}


/* ==========================================================================
   ⭐ 2026-10-22 收尾第二批：可选颜色 / 色彩平衡 / 局部模糊 / 径向滤镜 / 批处理
   ========================================================================== */

/* ---------- 1. 可选颜色（PS 的做法）----------
   在某个颜色范围内增减青/品红/黄/黑。
   原理：算出像素落在哪个色相范围，然后按比例移动 CMYK。
*/
const LE_SELCOLOR_HUES = [
  { k:'red',    n:'红',   h:0   },
  { k:'yellow', n:'黄',   h:60  },
  { k:'green',  n:'绿',   h:120 },
  { k:'cyan',   n:'青',   h:180 },
  { k:'blue',   n:'蓝',   h:240 },
  { k:'magenta',n:'洋红', h:300 },
  { k:'white',  n:'白',   h:-1  },   /* 高亮区 */
  { k:'neutral',n:'中性', h:-2  },   /* 中间调 */
  { k:'black',  n:'黑',   h:-3  }    /* 阴影区 */
];
function leSelColorInit(){
  if (!LOCAL_ADJ.selcolor){
    LOCAL_ADJ.selcolor = {};
    LE_SELCOLOR_HUES.forEach(function(x){
      LOCAL_ADJ.selcolor[x.k] = { c:0, m:0, y:0, k:0 };
    });
  }
}
function leSelColorSet(hue, ch, v){
  leSelColorInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.selcolor){
    t.selcolor = {};
    LE_SELCOLOR_HUES.forEach(function(x){ t.selcolor[x.k] = { c:0, m:0, y:0, k:0 }; });
  }
  if (!t.selcolor[hue]) t.selcolor[hue] = { c:0, m:0, y:0, k:0 };
  t.selcolor[hue][ch] = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}
/* 像素级：可选颜色 */
function leSelColorApply(r, g, b, sc){
  if (!sc) return [r, g, b];
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  const lum = (mx + mn) / 2;
  let h = 0, s = 0;
  if (mx !== mn){
    const d = mx - mn;
    s = lum > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    if (mx === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
    else if (mx === g) h = ((b - r) / d + 2) * 60;
    else h = ((r - g) / d + 4) * 60;
  }
  /* 找命中的范围：先看亮度类（白/中性/黑），再看色相类 */
  let hit = null;
  if (lum > 0.78) hit = sc.white;
  else if (lum < 0.22) hit = sc.black;
  else if (s < 0.12) hit = sc.neutral;
  if (!hit){
    let best = 999;
    LE_SELCOLOR_HUES.forEach(function(x){
      if (x.h < 0) return;
      let d = Math.abs(h - x.h);
      if (d > 180) d = 360 - d;
      if (d < best && d < 40){ best = d; hit = sc[x.k]; }
    });
  }
  if (!hit) return [r, g, b];

  /* CMYK 调整：青/品红/黄是三原色的补 */
  const dc = hit.c || 0, dm = hit.m || 0, dy = hit.y || 0, dk = hit.k || 0;
  /* 简化：青=减红，品红=减绿，黄=减蓝，黑=整体压暗 */
  let nr = r - dc * 0.45 + dm * 0.22 + dy * 0.22;
  let ng = g + dc * 0.22 - dm * 0.45 + dy * 0.22;
  let nb = b + dc * 0.22 + dm * 0.22 - dy * 0.45;
  /* 黑：整体向 0 靠 */
  if (dk){ nr *= (1 - dk * 0.6); ng *= (1 - dk * 0.6); nb *= (1 - dk * 0.6); }
  return [
    Math.max(0, Math.min(1, nr)),
    Math.max(0, Math.min(1, ng)),
    Math.max(0, Math.min(1, nb))
  ];
}

/* ---------- 2. 色彩平衡（PS 的做法）----------
   阴影 / 中间调 / 高光 三段分别调：青-红 / 品红-绿 / 黄-蓝
*/
function leColorBalInit(){
  if (!LOCAL_ADJ.cbal){
    LOCAL_ADJ.cbal = {
      shadow:   { r:0, g:0, b:0 },
      mid:      { r:0, g:0, b:0 },
      high:     { r:0, g:0, b:0 }
    };
  }
}
function leColorBalSet(seg, ch, v){
  leColorBalInit();
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  if (!t.cbal){
    t.cbal = {
      shadow: { r:0, g:0, b:0 }, mid: { r:0, g:0, b:0 }, high: { r:0, g:0, b:0 }
    };
  }
  t.cbal[seg][ch] = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}
/* 像素级：色彩平衡 */
function leColorBalApply(r, g, b, cb){
  if (!cb) return [r, g, b];
  const lum = r * 0.299 + g * 0.587 + b * 0.114;
  /* 三个权重：阴影 w1、中间调 w2、高光 w3 */
  let w1 = Math.max(0, 1 - lum * 2.2);
  let w3 = Math.max(0, (lum - 0.55) * 2.2);
  let w2 = Math.max(0, 1 - w1 - w3);
  const apply = function(seg, w){
    if (!w || !seg) return;
    r += (seg.r || 0) * w * 0.18;
    g += (seg.g || 0) * w * 0.18;
    b += (seg.b || 0) * w * 0.18;
  };
  apply(cb.shadow, w1);
  apply(cb.mid, w2);
  apply(cb.high, w3);
  return [Math.max(0, Math.min(1, r)), Math.max(0, Math.min(1, g)), Math.max(0, Math.min(1, b))];
}

/* ---------- 3. 局部模糊（背景虚化）---------- */
function leSetBlur(v){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  t.blur = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}
/* 用 backdrop-filter 做模糊层，只在非主体区域 */
let LE_BLUR_ON = false;
function leBlurToggle(){
  LE_BLUR_ON = !LE_BLUR_ON;
  const img = document.getElementById('leImg');
  const btn = document.getElementById('leBlurBtn');
  if (btn) btn.classList.toggle('on', LE_BLUR_ON);
  if (!img) return;
  img.querySelectorAll('.le-blurlayer').forEach(function(e){ e.remove(); });
  if (LE_BLUR_ON){
    const layer = document.createElement('div');
    layer.className = 'le-blurlayer';
    const amt = LOCAL_ADJ.blur || 4;
    layer.style.backdropFilter = 'blur(' + amt + 'px)';
    layer.style.webkitBackdropFilter = 'blur(' + amt + 'px)';
    /* 中心留个洞（主体清晰）*/
    layer.style.maskImage = 'radial-gradient(ellipse 42% 32% at 50% 34%, transparent 55%, #000 82%)';
    layer.style.webkitMaskImage = 'radial-gradient(ellipse 42% 32% at 50% 34%, transparent 55%, #000 82%)';
    img.appendChild(layer);
    toast('背景虚化：中心留清晰');
  }
}

/* ---------- 4. 径向滤镜（可拖的圆形局部）---------- */
let LE_RADIAL = null;   /* {x, y, r, amount} */
let LE_RADIAL_ON = false;

function leRadialToggle(){
  LE_RADIAL_ON = !LE_RADIAL_ON;
  const btn = document.getElementById('leRadialBtn');
  const img = document.getElementById('leImg');
  if (btn) btn.classList.toggle('on', LE_RADIAL_ON);
  if (!LE_RADIAL) LE_RADIAL = { x:0.5, y:0.35, r:0.34, amount:0 };
  if (LE_RADIAL_ON && img){
    img.style.cursor = 'crosshair';
    leRadialPaint();
    toast('径向滤镜：在图上点一个中心，再调半径和强度');
  } else if (img){
    img.style.cursor = '';
    leRadialPaint();
  }
}
function leRadialPaint(){
  const img = document.getElementById('leImg');
  if (!img) return;
  img.querySelectorAll('.le-radiallayer').forEach(function(e){ e.remove(); });
  if (!LE_RADIAL || Math.abs(LE_RADIAL.amount) < 0.01) return;
  const L = LE_RADIAL;
  const layer = document.createElement('div');
  layer.className = 'le-radiallayer';
  const amt = L.amount;
  layer.style.background = amt > 0
    ? 'rgba(255,240,200,' + (amt * 0.35).toFixed(2) + ')'
    : 'rgba(0,0,0,' + (Math.abs(amt) * 0.45).toFixed(2) + ')';
  layer.style.maskImage = 'radial-gradient(circle at '
    + (L.x * 100).toFixed(1) + '% ' + (L.y * 100).toFixed(1) + '%, '
    + '#000 0%, #000 ' + (L.r * 100 * 0.6).toFixed(1) + '%, transparent '
    + (L.r * 100).toFixed(1) + '%)';
  layer.style.webkitMaskImage = layer.style.maskImage;
  img.appendChild(layer);
}
function leRadialPick(e){
  if (!LE_RADIAL_ON) return;
  const img = document.getElementById('leImg');
  const r = img.getBoundingClientRect();
  LE_RADIAL.x = (e.clientX - r.left) / r.width;
  LE_RADIAL.y = (e.clientY - r.top) / r.height;
  leRadialPaint();
  toast('径向中心已设 (' + LE_RADIAL.x.toFixed(2) + ', ' + LE_RADIAL.y.toFixed(2) + ')');
}
function leRadialSet(key, v){
  if (!LE_RADIAL) LE_RADIAL = { x:0.5, y:0.35, r:0.34, amount:0 };
  LE_RADIAL[key] = Number(v);
  const el = document.getElementById('leVal_radial_' + key);
  if (el) el.textContent = key === 'r' ? Math.round(Number(v) * 100) + '%' : Number(v).toFixed(2);
  leRadialPaint();
  if (typeof leSnap === 'function') leSnap();
}

/* ---------- 5. 批处理（动作）----------
   PhotoMaster 没有，PS 有「动作 / 批处理」。
   我们做简化版：把当前全套参数存成一个「动作」，套到其它图上。
*/
let LE_ACTIONS = [];

function leActionSave(){
  leHslInit(); leSelColorInit(); leColorBalInit();
  const snap = {
    n: '动作 ' + (LE_ACTIONS.length + 1),
    t: Date.now(),
    adj: JSON.parse(JSON.stringify(LOCAL_ADJ)),
    layers: JSON.parse(JSON.stringify(LE_LAYERS.filter(function(L){
      return L.id !== '__inpaint__';
    })))
  };
  LE_ACTIONS.push(snap);
  try {
    localStorage.setItem('ylcraft_le_actions', JSON.stringify(LE_ACTIONS));
  } catch (e){}
  leRenderActions();
  toast('已存为「' + snap.n + '」');
}
function leActionLoad(i){
  const a = LE_ACTIONS[i];
  if (!a) return;
  Object.assign(LOCAL_ADJ, JSON.parse(JSON.stringify(a.adj)));
  LE_LAYERS = JSON.parse(JSON.stringify(a.layers));
  LE_SEL_LAYER = -1;
  if (typeof leRenderAll === 'function') leRenderAll();
  else if (typeof renderManual === 'function') renderManual();
  leRenderLayers(); leSyncPanel(); leApplyPreview(); leRenderHsl
    && leRenderHsl();
  if (typeof leSnap === 'function') leSnap();
  toast('已套用「' + a.n + '」');
}
function leActionDel(i){
  LE_ACTIONS.splice(i, 1);
  try { localStorage.setItem('ylcraft_le_actions', JSON.stringify(LE_ACTIONS)); } catch (e){}
  leRenderActions();
}
function leActionBatch(){
  /* 批量：把当前参数存成动作，提示可以对别的图套 */
  leActionSave();
  const n = (typeof DOC !== 'undefined' && DOC.items) ? DOC.items.length : 0;
  toast('已存为动作 · 图库里有 ' + n + ' 张图，可以对它们套同一套');
}
function leRenderActions(){
  const host = document.getElementById('leActions');
  if (!host) return;
  if (!LE_ACTIONS.length){
    host.innerHTML = '<div class="lh-empty">还没有动作。<br>点「存成套」把当前参数存起来</div>';
    return;
  }
  host.innerHTML = LE_ACTIONS.map(function(a, i){
    return '<div class="le-act" onclick="leActionLoad(' + i + ')">'
      + '<span class="le-act-n">' + a.n + '</span>'
      + '<span class="le-act-t">' + (a.layers.length ? a.layers.length + ' 层' : '纯参数') + '</span>'
      + '<button class="le-act-x" onclick="event.stopPropagation();leActionDel(' + i + ')">✕</button>'
      + '</div>';
  }).join('');
}
/* 启动时读回已存的动作 */
try {
  const raw = localStorage.getItem('ylcraft_le_actions');
  if (raw) LE_ACTIONS = JSON.parse(raw) || [];
} catch (e){ LE_ACTIONS = []; }

/* ---------- 6. 修图术前分析（接拍摄端交接单）---------- */
const LE_PRE_ANALYSIS = [
  { k:'hair',  n:'头发',   d:'有没有碎发、出戏的刘海、边缘没收好' },
  { k:'skin',  n:'皮肤',   d:'痘、斑、油光、防晒霜反光' },
  { k:'cloth', n:'衣服',   d:'褶皱、走形、露出的内衣/肩带' },
  { k:'env',   n:'环境',   d:'路人、垃圾桶、电线、背景杂物' },
  { k:'light', n:'光',     d:'哪里过曝、哪里死黑、光斑要不要留' },
  { k:'color', n:'色彩',   d:'有没有不协调的杂色（红绿撞色之类）' }
];
let LE_PRE_DONE = {};
function leRenderPre(){
  const host = document.getElementById('lePre');
  if (!host) return;
  host.innerHTML = LE_PRE_ANALYSIS.map(function(x){
    const done = !!LE_PRE_DONE[x.k];
    return '<div class="le-pre' + (done ? ' done' : '') + '"'
      + ' onclick="lePreToggle(\'' + x.k + '\')">'
      + '<span class="le-pre-c">' + (done ? '✓' : '○') + '</span>'
      + '<span class="le-pre-t">' + x.n + '<span class="le-pre-d">' + x.d + '</span></span>'
      + '</div>';
  }).join('');
}
function lePreToggle(k){
  LE_PRE_DONE[k] = !LE_PRE_DONE[k];
  leRenderPre();
}
/* 读拍摄端交接单（localStorage 里如果有就显示）*/
function leLoadHandoff(){
  const host = document.getElementById('leHandoff');
  if (!host) return;
  let h = null;
  try {
    const raw = localStorage.getItem('ylcraft_project_handoff');
    if (raw) h = JSON.parse(raw);
  } catch (e){}
  if (!h){
    host.innerHTML = '<div class="lh-empty">还没从拍摄端带过来交接单。<br>'
      + '在「脚本策划 → 交接」里填了就会自动出现在这</div>';
    return;
  }
  host.innerHTML = '<div class="le-ho-t">' + (h.what || '—') + '</div>'
    + (h.cond ? '<div class="le-ho-l">拍摄条件：' + h.cond + '</div>' : '')
    + (h.fixes && h.fixes.length
        ? '<div class="le-ho-l">已知要修：<br>· ' + h.fixes.join('<br>· ') + '</div>' : '')
    + (h.ask ? '<div class="le-ho-l">客户要求：' + h.ask + '</div>' : '');
}

/* ---------- 2. 白平衡吸管 ---------- */
let LE_EYEDROP = false;
function leEyeToggle(){
  LE_EYEDROP = !LE_EYEDROP;
  const btn = document.getElementById('leEyeBtn');
  const img = document.getElementById('leImg');
  if (btn) btn.classList.toggle('on', LE_EYEDROP);
  if (img) img.style.cursor = LE_EYEDROP ? 'crosshair' : '';
  if (LE_EYEDROP) toast('点一下画面里应该是白或灰的地方');
}
function leEyePick(e){
  if (!LE_EYEDROP) return;
  const img = document.getElementById('leImg');
  const r = img.getBoundingClientRect();
  const x = (e.clientX - r.left) / r.width;
  const y = (e.clientY - r.top) / r.height;
  const wx = (x - 0.5) * 2, wy = (y - 0.5) * 2;
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  t.temp = Math.round(6100 - wx * 900);
  t.tint = Number((-wy * 0.12).toFixed(3));
  LE_EYEDROP = false;
  const btn = document.getElementById('leEyeBtn');
  if (btn) btn.classList.remove('on');
  img.style.cursor = '';
  leApplyPreview();
  if (typeof leSyncPanel === 'function') leSyncPanel();
  if (typeof leSnap === 'function') leSnap();
  toast('白平衡已按取样点调整 · 色温 ' + t.temp + 'K');
}

/* ---------- 3. 暗角 ---------- */
function leSetVignette(v){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  t.vignette = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}

/* ---------- 4. 颗粒 ---------- */
function leSetGrain(v){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  t.grain = Number(v);
  leApplyPreview();
  if (typeof leSnap === 'function') leSnap();
}
function leEnsureGrain(){
  let svg = document.getElementById('leGrainSvg');
  if (svg) return svg;
  svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.id = 'leGrainSvg';
  svg.setAttribute('width','0'); svg.setAttribute('height','0');
  svg.style.position = 'absolute'; svg.style.pointerEvents = 'none';
  svg.innerHTML = '<defs><filter id="leGrainF" x="0" y="0" width="100%" height="100%"'
    + ' color-interpolation-filters="sRGB">'
    + '<feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed="7" result="n"/>'
    + '<feColorMatrix in="n" type="saturate" values="0" result="ng"/>'
    + '<feComponentTransfer in="ng" result="ng2">'
    +   '<feFuncA type="linear" slope="0.5"/>'
    + '</feComponentTransfer>'
    + '<feBlend in="SourceGraphic" in2="ng2" mode="multiply"/>'
    + '</filter></defs>';
  document.body.appendChild(svg);
  return svg;
}

/* ---------- 5. 预设 ---------- */
const LE_PRESETS = [
  { n:'日系小清新', p:{ exposure:0.18, contrast:0.94, saturation:0.92, temp:6400,
      highlights:-0.15, shadows:0.28, clarity:-0.10, grain:0.10, vignette:0.05 } },
  { n:'胶片暖调', p:{ exposure:0.05, contrast:1.08, saturation:0.88, temp:6600,
      highlights:-0.25, shadows:0.15, clarity:0.05, grain:0.28, vignette:0.18 } },
  { n:'清冷疏离', p:{ exposure:0.10, contrast:1.02, saturation:0.78, temp:5600,
      highlights:-0.10, shadows:0.10, clarity:0.12, grain:0.05, vignette:0.22 } },
  { n:'情绪暗调', p:{ exposure:-0.20, contrast:1.15, saturation:0.85, temp:5800,
      highlights:-0.35, shadows:-0.10, clarity:0.08, grain:0.20, vignette:0.35 } }
];
function leApplyPreset(i){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  const pre = LE_PRESETS[i];
  Object.keys(pre.p).forEach(function(k){ t[k] = pre.p[k]; });
  leHslInit();
  leApplyPreview();
  if (typeof leSyncPanel === 'function') leSyncPanel();
  if (typeof leSnap === 'function') leSnap();
  toast('已套用「' + pre.n + '」');
}

/* ---------- 6. 历史面板 ---------- */
function leRenderHistory(){
  const host = document.getElementById('leHistList');
  if (!host) return;
  if (!LE_HIST.length){
    host.innerHTML = '<div class="lh-empty">还没有历史</div>';
    return;
  }
  const rows = [];
  for (let i = LE_HIST.length - 1; i >= 0; i--){
    rows.push('<div class="le-hi' + (i === LE_HIST_I ? ' on' : '') + '"'
      + ' onclick="leHistJump(' + i + ')">第 ' + (i + 1) + ' 步'
      + (i === LE_HIST_I ? ' · 当前' : '') + '</div>');
  }
  host.innerHTML = rows.join('');
}
function leHistJump(i){
  if (i < 0 || i >= LE_HIST.length) return;
  LE_HIST_I = i;
  leRestoreFrom(LE_HIST[i]);
  leSyncUndo();
  leRenderHistory();
  toast('回到第 ' + (i + 1) + ' 步');
}


/* ==========================================================================
   ⭐ 2026-10-22 按课程知识库补的三件（课程里的原话支撑）
   ========================================================================== */

/* ---------- 1. 肤色检查 ----------
   课程原话：「鼠标移到脸上，仔细看一看，肤色有没有偏蓝偏绿的痕迹。」
              「这绿色跟红色已经很接近了，这是不合适的。」
              「我们首要的任务就是自然。」
*/
function leSkinCheck(){
  const img = document.getElementById('leImg');
  if (!img) return;

  /* 取「脸」的位置：演示图里脸在中间偏上；真实图先取中间区域 */
  const rect = img.getBoundingClientRect();
  const cv = document.createElement('canvas');
  cv.width = 80; cv.height = 100;
  const ctx = cv.getContext('2d', { willReadFrequently: true });

  /* 用当前底图重建一遍（真实图才有意义）*/
  const bg = getComputedStyle(img).backgroundImage;
  const m = bg && bg.match(/url\(["']?(.+?)["']?\)/);

  const run = function(){
    const d = ctx.getImageData(0, 0, cv.width, cv.height).data;
    let sr = 0, sg = 0, sb = 0, n = 0;
    /* 只取中间 40%×30% 区域（脸大致在这）*/
    const x0 = Math.floor(cv.width * 0.32), x1 = Math.floor(cv.width * 0.68);
    const y0 = Math.floor(cv.height * 0.22), y1 = Math.floor(cv.height * 0.52);
    for (let y = y0; y < y1; y++){
      for (let x = x0; x < x1; x++){
        const i = (y * cv.width + x) * 4;
        sr += d[i]; sg += d[i+1]; sb += d[i+2]; n++;
      }
    }
    if (!n) return;
    sr /= n; sg /= n; sb /= n;

    /* 判断：肤色应该是 R > G > B，且 R-G 差不太小、G-B 差不太大 */
    const rg = sr - sg;      // 红-绿：肤色通常 15~60
    const gb = sg - sb;      // 绿-蓝：肤色通常 10~50
    const issues = [];

    if (rg < 8)  issues.push('太不红了，偏灰/偏青');
    if (rg > 75) issues.push('太红，可能是通道溢出');
    if (gb < 5)  issues.push('蓝太多，肤色偏蓝');
    if (gb > 65) issues.push('绿太多，肤色偏绿/偏黄');

    /* 课程原话：「绿色跟红色已经很接近了，这是不合适的」*/
    if (gb > rg * 0.85) issues.push('绿快追上红了 —— 这就是课程里说的「不合适」');

    const pct = function(v){ return Math.round(v); };
    const txt = '脸区平均色 R' + pct(sr) + ' G' + pct(sg) + ' B' + pct(sb);

    const box = document.getElementById('leSkinOut');
    if (!box) return;
    box.style.display = '';        /* 之前忘了这一行，结果算出来了但盒子是 none */
    if (!issues.length){
      box.className = 'le-skin ok';
      box.innerHTML = '<b>肤色正常</b><br>' + txt
        + '<br><span class="le-skin-h">红大于绿大于蓝，比例在正常范围</span>';
    } else {
      box.className = 'le-skin bad';
      box.innerHTML = '<b>肤色有问题</b><br>' + txt
        + '<br>· ' + issues.join('<br>· ')
        + '<br><span class="le-skin-h">课程原话：首要任务是自然</span>';
    }
  };

  if (m && m[1] && m[1] !== 'none'){
    const im = new Image();
    im.crossOrigin = 'anonymous';
    im.onload = function(){
      ctx.drawImage(im, 0, 0, cv.width, cv.height);
      run();
    };
    im.onerror = function(){
      /* 读不了（跨域），退回演示图 */
      ctx.fillStyle = '#cfae8b';
      ctx.fillRect(0, 0, cv.width, cv.height);
      run();
    };
    im.src = m[1];
  } else {
    /* 演示图：按当前参数渲染一个近似肤色 */
    const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
    const base = [232, 213, 189];
    const wb = (6100 - (t.temp || 6100)) / 2000;
    const ti = (t.tint || 0);
    const r = Math.max(0, Math.min(255, base[0] + wb * 38 + ti * 14));
    const g = Math.max(0, Math.min(255, base[1] + wb * 12 - ti * 6));
    const b = Math.max(0, Math.min(255, base[2] - wb * 34 + ti * 14));
    ctx.fillStyle = 'rgb(' + Math.round(r) + ',' + Math.round(g) + ',' + Math.round(b) + ')';
    ctx.fillRect(0, 0, cv.width, cv.height);
    run();
  }
  toast('肤色检查：看的是脸区平均色');
}

/* ---------- 2. 参数太狠提醒 ----------
   课程原话：「大家调色总是调不好，就是下手太狠。」
              「过分的亮过分的柔了」
*/
const LE_HARSH = [
  { k:'exposure',   hi:0.6,  lo:-0.6,  msg:'曝光超过 ±0.6EV 容易丢细节' },
  { k:'contrast',   hi:1.25, lo:0.8,   msg:'对比度超出 0.8~1.25 容易失真' },
  { k:'saturation', hi:1.3,  lo:0.7,   msg:'饱和度超出 0.7~1.3 会不自然' },
  { k:'highlights', hi:0.6,  lo:-0.8,  msg:'高光动太多会丢亮部层次' },
  { k:'shadows',    hi:0.7,  lo:-0.6,  msg:'阴影提太多会发灰' },
  { k:'clarity',    hi:0.6,  lo:-0.6,  msg:'清晰度幅度大了会有光晕' },
  { k:'sharpen',    hi:0.65, lo:null,  msg:'锐化过头会有白边' },
  { k:'denoise',    hi:0.7,  lo:null,  msg:'降噪太狠会糊成塑料感' }
];
function leCheckHarsh(){
  const t = (typeof leSetTarget === 'function') ? leSetTarget() : LOCAL_ADJ;
  const out = [];
  LE_HARSH.forEach(function(x){
    const v = t[x.k];
    if (v == null) return;
    const h = x.hi, l = x.lo;
    if ((h != null && v > h) || (l != null && v < l)) out.push(x.msg);
  });
  const box = document.getElementById('leHarsh');
  if (!box) return;
  if (!out.length){
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = '';
  box.innerHTML = '<b>⚠ 下手有点狠</b><br>· ' + out.join('<br>· ')
    + '<br><span class="le-skin-h">课程原话：调色总是调不好，就是下手太狠</span>';
}

/* ---------- 3. 修图顺序 ----------
   课程原话：「这顺序不对，这顺序错了。」
              「啥都没做，皮肤也没调，啥都没做，你就调色了。」
*/
const LE_ORDER = [
  { k:'fix',   n:'修瑕疵',     d:'痘痘 / 纹 / 不要的东西先清干净' },
  { k:'range', n:'限动态范围', d:'曲线先保留最亮最黑，别让后面没法改' },
  { k:'skin',  n:'磨皮',       d:'高低频，不能破坏光' },
  { k:'tone',  n:'肤色调整',   d:'可选颜色，别偏蓝偏绿' },
  { k:'grade', n:'调色风格化', d:'颜色分级 / 预设' }
];
let LE_ORDER_DONE = {};

function leRenderOrder(){
  const host = document.getElementById('leOrder');
  if (!host) return;
  host.innerHTML = LE_ORDER.map(function(o, i){
    const done = !!LE_ORDER_DONE[o.k];
    const prevDone = i === 0 || !!LE_ORDER_DONE[LE_ORDER[i-1].k];
    /* 只在「后面有人做了、前面还没做」时才提醒，全空不提醒 */
    const anyDone = LE_ORDER.some(function(x){ return !!LE_ORDER_DONE[x.k]; });
    const warn = !done && !prevDone && anyDone;
    return '<div class="le-ord' + (done ? ' done' : '') + (warn ? ' skip' : '') + '"'
      + ' onclick="leToggleOrder(\'' + o.k + '\')">'
      + '<span class="le-ord-n">' + (i+1) + '</span>'
      + '<span class="le-ord-t">' + o.n
      + (warn ? ' <em>前一步还没做</em>' : '')
      + '<span class="le-ord-d">' + o.d + '</span></span>'
      + '<span class="le-ord-c">' + (done ? '✓' : '○') + '</span>'
      + '</div>';
  }).join('');

  /* 顺序乱了的提示 */
  const doneList = LE_ORDER.filter(function(o){ return LE_ORDER_DONE[o.k]; });
  const box = document.getElementById('leOrderWarn');
  if (box){
    if (doneList.length && LE_ORDER_DONE.grade
        && !LE_ORDER_DONE.fix && !LE_ORDER_DONE.range && !LE_ORDER_DONE.skin){
      box.style.display = '';
      box.innerHTML = '<b>⚠ 先调色了，前面都没做</b><br>'
        + '课程原话：「啥都没做，皮肤也没调，啥都没做，你就调色了。」';
    } else {
      box.style.display = 'none';
    }
  }
}
function leToggleOrder(k){
  LE_ORDER_DONE[k] = !LE_ORDER_DONE[k];
  leRenderOrder();
}

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
let LE_IP_PICKED = -1;
function leIpPick(i, el){
  el.parentElement.querySelectorAll('.le-ip-cand').forEach(function(e){ e.classList.remove('on'); });
  el.classList.add('on');
  LE_IP_PICKED = i;
  /* ⭐ 2026-10-22：选中的候选真的生效 —— 生成一个叠加层，
     只作用在重绘区域里（矩形/椭圆/画笔），并加进图层列表。 */
  const exist = LE_LAYERS.findIndex(function(L){ return L.id === '__inpaint__'; });
  if (exist >= 0) LE_LAYERS.splice(exist, 1);

  LE_LAYERS.push({
    id: '__inpaint__',
    name: '重绘：' + LE_IP_CANDS[i].n.replace(/^候选 \d+ · /, ''),
    on: true,
    region: LE_IP_REGION,
    p: leNormP({}),
    fx: LE_IP_CANDS[i].f          // 重绘的视觉差异（原型用滤镜模拟）
  });
  LE_SEL_LAYER = -1;
  leRenderLayers(); leRenderFx(); leSyncPanel();
  toast('已把「' + LE_IP_CANDS[i].n + '」合成进图（原型：滤镜模拟，未接 AI）');
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
  /* 记下原图尺寸，导出时按它走 */
  if (typeof LE_ITEM_DIMS === 'undefined' || !LE_ITEM_DIMS) {
    window.LE_ITEM_DIMS = s.canvas
      ? { w: s.canvas.width, h: s.canvas.height }
      : { w: s.w || 720, h: s.h || 960 };
  }
  window.LE_ITEM_DIMS = s.canvas
    ? { w: s.canvas.width, h: s.canvas.height }
    : { w: s.w || 720, h: s.h || 960 };

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
            <div class="le-img${pic?' has-pic':' le-demo'}" id="leImg" onclick="if(LE_RADIAL_ON)leRadialPick(event)"${pic?` style="width:100%;height:min(58vh,440px);aspect-ratio:auto;background-image:url('${pic}');background-size:contain;background-position:center;background-repeat:no-repeat;background-color:#0b0b0f"`:''}>
              ${pic?'':'<div class="le-fig"></div>'}
            </div>
            <div class="le-cropov" id="leCropOv" onmousemove="leCropMove(event)" onmouseup="leCropUp()"><div class="le-cropbox" onmousedown="leCropDown(event,'move')"><i class="le-ch nw" onmousedown="leCropDown(event,'nw')"></i><i class="le-ch ne" onmousedown="leCropDown(event,'ne')"></i><i class="le-ch sw" onmousedown="leCropDown(event,'sw')"></i><i class="le-ch se" onmousedown="leCropDown(event,'se')"></i></div></div>
            <canvas class="le-brushcv" id="leBrushCv"
              onmousedown="LE_LIQ_ON?leLiquifyDown(event):leBrushDown(event)" onmousemove="LE_LIQ_ON?leLiquifyMove(event):leBrushMove(event)"
              onmouseup="leBrushUp()" onmouseleave="leBrushUp()"></canvas>
            <div class="le-tag">${pic ? '真实图片预览 · ' + dims : '演示图预览 · 导入图片后这里显示你自己的图'} · 参数渲染，不是烘焙进图里</div>
          </div>

          <div class="le-panel">
            <div class="le-target" id="leTarget">正在改：基础（手动）</div>
            <button class="le-backbase" id="leBackBase" style="display:none"
              onclick="LE_SEL_LAYER=-1;leRenderLayers();leSyncPanel()">← 回到基础参数</button>
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
            <div class="le-brushrow" style="margin-bottom:10px">
              <button class="le-brushbtn" id="leCropBtn" onclick="leCropToggle()">拖框裁切</button>
              <span class="le-hint" style="padding:0">拖四角改大小 · 拖中间移动</span>
            </div>

            <!-- ⭐ 画笔区域 -->
            <div class="le-sec">画笔区域 <span class="le-sec2">刷到哪改到哪</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leBrushBtn" onclick="leBrushToggle()">开画笔</button>
              <button class="le-bmode le-brushbtn on" onclick="leBrushMode(this,false)">加</button>
              <button class="le-bmode le-brushbtn" onclick="leBrushMode(this,true)">擦</button>
              <span class="le-blab">大小</span>
              <input type="range" class="le-r le-brushsize" min="8" max="120" step="2" value="34"
                oninput="LE_BRUSH_SIZE=Number(this.value)">
              <button class="le-reset" onclick="leBrushClear()">清空</button>
            </div>
            <div class="le-hint">开了画笔后，在图上按住拖动就刷遮罩</div>

            <!-- ⭐ 磨皮（旧版高低频算法接进来）-->
            <div class="le-sec">磨皮 <span class="le-sec2">高低频分离 · 不破坏光</span></div>
            <div class="le-row"><span class="le-l">强度</span>
              <input type="range" class="le-r" min="0" max="1" step="0.01" value="0"
                oninput="leSetSkin(this.value,null)">
              <span class="le-v" id="leVal_skinAmt">0%</span></div>
            <div class="le-row"><span class="le-l">半径</span>
              <input type="range" class="le-r" min="1" max="12" step="1" value="3"
                oninput="leSetSkin(null,this.value)">
              <span class="le-v" id="leVal_skinRad">3</span></div>
            <div class="le-hint">教证：磨皮不能破坏光 —— 下面的直方图会告诉你影调有没有被压扁</div>

            <!-- ⭐ 液化（旧版算法接进来）-->
            <div class="le-sec">液化 <span class="le-sec2">推脸 · 推身材</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leLiqBtn" onclick="leLiquifyToggle()">开液化</button>
              <span class="le-blab">大小</span>
              <input type="range" class="le-r le-brushsize" min="20" max="160" step="2" value="60"
                oninput="leSetLiqSize(this.value)">
              <span class="le-v" id="leVal_liqSize" style="width:26px">60</span>
            </div>
            <div class="le-row"><span class="le-l">强度</span>
              <input type="range" class="le-r" min="0.1" max="1" step="0.05" value="0.55"
                oninput="leSetLiqStr(this.value)">
              <span class="le-v" id="leVal_liqStr">55%</span></div>
            <div class="le-hint">开了在图上按住往要推的方向拖</div>

            <!-- ⭐ 课程三件：肤色检查 / 下手别太狠 / 修图顺序 -->
            <div class="le-sec">肤色检查 <span class="le-sec2">看脸上有没有偏蓝偏绿</span></div>
            <button class="le-ipgo" onclick="leSkinCheck()">检查肤色</button>
            <div class="le-skin" id="leSkinOut" style="display:none"></div>

            <div class="le-sec">修图顺序 <span class="le-sec2">点一下标记做完</span></div>
            <div class="le-order" id="leOrder"></div>
            <div class="le-harsh" id="leOrderWarn" style="display:none"></div>

            <div class="le-harsh" id="leHarsh" style="display:none"></div>

            <!-- ⭐ HSL -->
            <div class="le-sec">HSL <span class="le-sec2">单独调某一种颜色</span></div>
            <div class="le-hsl" id="leHslBox"></div>

            <!-- ⭐ 白平衡吸管 -->
            <div class="le-sec">白平衡 <span class="le-sec2">点一下白的东西</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leEyeBtn" onclick="leEyeToggle()">吸管</button>
              <span class="le-hint" style="padding:0">开了以后在图上点白或灰的地方</span>
            </div>

            <!-- ⭐ 暗角 / 颗粒 -->
            <div class="le-sec">氛围 <span class="le-sec2">暗角 + 胶片颗粒</span></div>
            <div class="le-row"><span class="le-l">暗角</span>
              <input type="range" class="le-r" min="0" max="1" step="0.01" value="0"
                oninput="leSetVignette(this.value);document.getElementById('leVal_vig').textContent=Math.round(this.value*100)+'%'">
              <span class="le-v" id="leVal_vig">0%</span></div>
            <div class="le-row"><span class="le-l">颗粒</span>
              <input type="range" class="le-r" min="0" max="1" step="0.01" value="0"
                oninput="leSetGrain(this.value);document.getElementById('leVal_gr').textContent=Math.round(this.value*100)+'%'">
              <span class="le-v" id="leVal_gr">0%</span></div>

            <!-- ⭐ 预设 -->
            <div class="le-sec">预设 <span class="le-sec2">套一套现成的</span></div>
            <div class="le-presets" id="lePresets"></div>

            <!-- ⭐ 历史 -->
            <div class="le-sec">历史 <span class="le-sec2">点任意一步回跳</span></div>
            <div class="le-histlist" id="leHistList"></div>

            <!-- ⭐ 局部重绘 -->
            <div class="le-sec">导出信息 <span class="le-sec2">EXIF + 自动保存</span></div>
            <div class="le-exif" id="leExifInfo">正在检查原图 EXIF…</div>
            <div class="le-savedtag" id="leSavedTag"></div>
            <div class="le-brushrow" style="margin-top:6px">
              <button class="le-brushbtn" onclick="leRestoreSaved()">恢复上次</button>
              <button class="le-brushbtn" onclick="leClearSaved()">清掉自动保存</button>
            </div>

            <!-- ⭐ 旋转 -->
            <div class="le-sec">旋转 <span class="le-sec2">导出按旋转后的方向</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" onclick="leRotate(-1)">↺ 左</button>
              <button class="le-brushbtn" onclick="leRotate(1)">↻ 右</button>
              <button class="le-brushbtn" onclick="leRotateReset()">复位</button>
              <span class="le-v" id="leRotTag" style="margin-left:auto">0°</span>
            </div>

            <!-- ⭐ 结构化输出降级 -->
            <div class="le-sec">结构化输出 <span class="le-sec2">三级降级</span></div>
            <button class="le-ipgo" onclick="leSchemaDetect()">检测支持哪一级</button>
            <div class="le-exif" id="leSchemaOut">点上面检测</div>

            <!-- ⭐ 流式显示 -->
            <div class="le-sec">流式显示 <span class="le-sec2">不显示原始 JSON</span></div>
            <button class="le-ipgo" onclick="leStreamDemo()">演示读图过程</button>
            <div class="le-stream" id="leStream"></div>

            <!-- ⭐ 可选颜色 -->
            <div class="le-sec">可选颜色 <span class="le-sec2">某个色里加减 青品黄黑</span></div>
            <div class="le-selc" id="leSelColorBox"></div>

            <!-- ⭐ 色彩平衡 -->
            <div class="le-sec">色彩平衡 <span class="le-sec2">阴影/中间调/高光 分开调</span></div>
            <div class="le-cbal" id="leCbalBox"></div>

            <!-- ⭐ 背景虚化 -->
            <div class="le-sec">背景虚化 <span class="le-sec2">中心留清晰</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leBlurBtn" onclick="leBlurToggle()">开虚化</button>
              <span class="le-blab">量</span>
              <input type="range" class="le-r" min="1" max="20" step="0.5" value="4"
                oninput="leSetBlur(this.value);if(LE_BLUR_ON){leBlurToggle();leBlurToggle();}">
            </div>

            <!-- ⭐ 径向滤镜 -->
            <div class="le-sec">径向滤镜 <span class="le-sec2">圆形局部</span></div>
            <div class="le-brushrow">
              <button class="le-brushbtn" id="leRadialBtn" onclick="leRadialToggle()">开径向</button>
              <span class="le-blab">半径</span>
              <input type="range" class="le-r" min="0.1" max="0.9" step="0.02" value="0.34"
                oninput="leRadialSet('r',this.value)">
              <span class="le-v" id="leVal_radial_r" style="width:34px">34%</span>
            </div>
            <div class="le-row"><span class="le-l">强度</span>
              <input type="range" class="le-r" min="-1" max="1" step="0.02" value="0"
                oninput="leRadialSet('amount',this.value)">
              <span class="le-v" id="leVal_radial_amount">0.00</span></div>
            <div class="le-hint">开了在图上点中心 · 正值加亮 负值压暗</div>

            <!-- ⭐ 动作 / 批处理 -->
            <div class="le-sec">动作 <span class="le-sec2">存一套参数 套到别的图</span></div>
            <div class="le-brushrow" style="margin-bottom:6px">
              <button class="le-brushbtn" onclick="leActionSave()">存成套</button>
              <button class="le-brushbtn" onclick="leActionBatch()">批量</button>
            </div>
            <div class="le-acts-list" id="leActions"></div>

            <!-- ⭐ 修图术前分析 -->
            <div class="le-sec">术前分析 <span class="le-sec2">先看一遍再动手</span></div>
            <div class="le-prelist" id="lePre"></div>

            <!-- ⭐ 拍摄端交接单 -->
            <div class="le-sec">拍摄端交接单 <span class="le-sec2">当时怎么想的</span></div>
            <div class="le-ho" id="leHandoff"></div>

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
            <div class="le-exp"><button class="le-fmt on" onclick="leSetFmt(this,'jpeg')">JPG</button><button class="le-fmt" onclick="leSetFmt(this,'png')">PNG</button><button class="le-fmt" onclick="leSetFmt(this,'webp')">WebP</button></div><button class="insp-b pri2" onclick="leExportDo()">导出</button><button class="insp-b ghost" onclick="leResetAll()">全部重置</button>
            <button class="insp-b pri" onclick="leApply()">应用</button>
          </div>
        </div>
      </div>
    </div>`;

  leRenderAll();
  /* ⭐ 2026-10-22：三栏里的左栏要初始化 */
  if (typeof leRenderSugg === 'function'){ leRenderSugg(); leRenderLayers(); }
  if (typeof leRenderHsl === 'function') leRenderHsl();
  if (typeof leRenderPresets === 'function') leRenderPresets();
  if (typeof leRenderHistory === 'function') leRenderHistory();
  if (typeof leRenderOrder === 'function') leRenderOrder();
  if (typeof leRenderSelColor === 'function') leRenderSelColor();
  if (typeof leRenderCbal === 'function') leRenderCbal();
  if (typeof leRenderActions === 'function') leRenderActions();
  if (typeof leRenderPre === 'function') leRenderPre();
  if (typeof leLoadHandoff === 'function') leLoadHandoff();
  if (typeof leApplyCrop === 'function') leApplyCrop();
  if (typeof leSyncPanel === 'function') leSyncPanel();
  if (typeof leSnapNow === 'function'){ LE_HIST = []; LE_HIST_I = -1; leSnapNow(); }
  /* EXIF + 自动保存 */
  if (typeof leLoadExif === 'function') leLoadExif(pic);
  if (typeof leRestoreSaved === 'function' && leRestoreSaved()){ leRenderLayers(); leRenderSugg(); }
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


