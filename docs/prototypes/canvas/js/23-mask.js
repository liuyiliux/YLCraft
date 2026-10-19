/* 23-mask.js — 局部调整（蒙版 / 渐变 / 径向）
   🔴 之前只能整图调 —— 想只调脸、只调背景做不到。
      这是专业后期最核心的能力。

   实现：调整层用 CSS mask-image 控制作用范围，参数只影响蒙版内。
   蒙版类型：矩形 / 圆形（径向）/ 线性渐变，全部可拖、可羽化。
*/

const MASK = {
  mode: 'full',      // full | rect | circle | linear
  x: 0.5, y: 0.42,   // 中心（0-1）
  w: 0.55, h: 0.5,   // 宽高（0-1，相对图片）
  feather: 0.22,     // 羽化
  angle: 90,         // 渐变角度
  params: { exposure: 0, contrast: 1, saturation: 1 }
};
let MASK_DRAG = null;

/* 把蒙版转成 CSS */
function maskImageCSS(){
  const m = MASK;
  const cx = (m.x*100).toFixed(1), cy = (m.y*100).toFixed(1);
  const f = (m.feather*100).toFixed(1);
  if (m.mode === 'circle'){
    const rx = (m.w*50).toFixed(1), ry = (m.h*50).toFixed(1);
    // 用椭圆近似（radial-gradient 支持椭圆）
    const r = Math.max(rx, ry);
    return `radial-gradient(ellipse ${r}% ${r * (ry/rx)}% at ${cx}% ${cy}%, #000 0%, #000 ${Math.max(0,100-f*2).toFixed(0)}%, transparent 100%)`;
  }
  if (m.mode === 'linear'){
    return `linear-gradient(${m.angle}deg, #000 0%, #000 25%, transparent 90%)`;
  }
  if (m.mode === 'rect'){
    const l = ((m.x - m.w/2)*100).toFixed(1);
    const t = ((m.y - m.h/2)*100).toFixed(1);
    const r = ((m.x + m.w/2)*100).toFixed(1);
    const b = ((m.y + m.h/2)*100).toFixed(1);
    const g = `linear-gradient(#000,#000)`;
    // 用 mask-composite 组合太绕，矩形直接用 clip-path + 羽化用 blur 近似
    return null;   // 矩形走 clipPath
  }
  return null;
}

/* ===== 面板 ===== */
function openLocalMask(id){
  const sid = id || selId || (DOC.items[0] && DOC.items[0].id);
  const s = DOC.items.find(x=>x.id===sid);
  if (!s){ toast('先选一张图'); return; }
  if (typeof hideFloatBar === 'function') hideFloatBar();
  MASK_DRAG = null;

  document.getElementById('overlayHost').innerHTML = `
    <div class="lm" onclick="if(event.target.classList.contains('lmw'))closeMask()">
      <div class="lmw">
        <div class="le-hd">
          <div class="le-t">局部调整 · ${esc(s.name)}</div>
          <span class="le-free">免费</span>
          <span class="le-nb">非破坏</span>
          <button class="inp-x" onclick="closeMask()">✕</button>
        </div>

        <div class="le-body">
          <div class="le-stage">
            <div class="lm-imgwrap" id="lmWrap">
              <div class="lm-base"><div class="lm-fig"></div></div>
              <div class="lm-adj" id="lmAdj"></div>
              <div class="lm-handle" id="lmHandle"></div>
            </div>
            <div class="le-tag" id="lmTag">全图调整 · 换成蒙版可以只调一块</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">作用范围</div>
            <div class="lm-modes">
              ${[['full','全图'],['rect','矩形'],['circle','圆形'],['linear','渐变']].map(([k,n])=>
                `<button class="lm-m ${MASK.mode===k?'on':''}" onclick="setMaskMode('${k}')">${n}</button>`
              ).join('')}
            </div>

            <div class="lm-hint" id="lmHint">当前是全图 —— 所有参数影响整张</div>

            <div id="lmShapeCtrl" style="display:none">
              <div class="le-sec">蒙版位置与大小</div>
              ${maskSlider('x','左右',0,1,0.01)}
              ${maskSlider('y','上下',0,1,0.01)}
              ${maskSlider('w','宽',0.05,1,0.01)}
              ${maskSlider('h','高',0.05,1,0.01)}
              ${maskSlider('feather','羽化',0,0.6,0.01)}
              <div id="lmAngleRow" style="display:none">${maskSlider('angle','角度',0,360,1)}</div>
            </div>

            <div class="le-sec" style="margin-top:16px">调整（只影响上面这块）</div>
            <div class="le-row">
              <span class="le-l">曝光</span>
              <input type="range" class="le-r" min="-1.5" max="1.5" step="0.05" value="${MASK.params.exposure}"
                oninput="setMaskParam('exposure',this.value)">
              <span class="le-v" id="lmVexp">${(MASK.params.exposure>=0?'+':'')+MASK.params.exposure.toFixed(2)}EV</span>
            </div>
            <div class="le-row">
              <span class="le-l">对比度</span>
              <input type="range" class="le-r" min="0.5" max="1.6" step="0.01" value="${MASK.params.contrast}"
                oninput="setMaskParam('contrast',this.value)">
              <span class="le-v" id="lmVcon">${MASK.params.contrast.toFixed(2)}</span>
            </div>
            <div class="le-row">
              <span class="le-l">饱和度</span>
              <input type="range" class="le-r" min="0" max="2" step="0.01" value="${MASK.params.saturation}"
                oninput="setMaskParam('saturation',this.value)">
              <span class="le-v" id="lmVsat">${MASK.params.saturation.toFixed(2)}</span>
            </div>

            <div class="lm-tip">
              💡 典型用法：<b>只提亮脸</b>（圆形 + 羽化）·
              <b>只压暗背景</b>（圆形反过来）·
              <b>只调天空</b>（渐变）
            </div>
          </div>
        </div>

        <div class="le-foot">
          <div class="le-cost">
            花费 <b class="le-zero">0</b>
            <span class="le-costn">本地像素运算 · 蒙版只是参数 · 随时能改形状</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="resetMask()">重置</button>
            <button class="insp-b pri" onclick="applyMask()">应用</button>
          </div>
        </div>
      </div>
    </div>`;

  renderMask();
}

function maskSlider(key, label, min, max, step){
  const v = MASK[key];
  return `<div class="le-row">
    <span class="le-l">${label}</span>
    <input type="range" class="le-r lm-r" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${v}"
      oninput="setMaskField('${key}', this.value)">
    <span class="le-v" id="lmV_${key}">${key==='angle'?Math.round(v)+'°':v.toFixed(2)}</span>
  </div>`;
}

function closeMask(){ document.getElementById('overlayHost').innerHTML = ''; }

function setMaskMode(m){
  MASK.mode = m;
  document.querySelectorAll('.lm-m').forEach(b=>{
    b.classList.toggle('on', b.textContent.trim() === {full:'全图',rect:'矩形',circle:'圆形',linear:'渐变'}[m]);
  });
  document.getElementById('lmShapeCtrl').style.display = (m==='full') ? 'none' : '';
  document.getElementById('lmAngleRow').style.display = (m==='linear') ? '' : 'none';
  const hints = {
    full:'当前是全图 —— 所有参数影响整张',
    rect:'矩形蒙版 —— 拖手柄移动，调宽高改大小',
    circle:'圆形蒙版 —— 最适合"只提亮脸"这类操作',
    linear:'线性渐变 —— 适合"只调天空上半部分"'
  };
  document.getElementById('lmHint').textContent = hints[m];
  document.getElementById('lmTag').textContent = m==='full'
    ? '全图调整' : '只有蒙版内会变 · 蒙版外保持原样';
  renderMask();
}

function setMaskField(k, v){
  MASK[k] = Number(v);
  const el = document.getElementById('lmV_' + k);
  if (el) el.textContent = (k==='angle') ? Math.round(Number(v))+'°' : Number(v).toFixed(2);
  renderMask();
}

function setMaskParam(k, v){
  MASK.params[k] = Number(v);
  const map = { exposure:['lmVexp', x=>(x>=0?'+':'')+Number(x).toFixed(2)+'EV'],
                contrast:['lmVcon', x=>Number(x).toFixed(2)],
                saturation:['lmVsat', x=>Number(x).toFixed(2)] };
  const el = document.getElementById(map[k][0]);
  if (el) el.textContent = map[k][1](v);
  renderMask();
}

function resetMask(){
  MASK.mode='full'; MASK.x=0.5; MASK.y=0.42; MASK.w=0.55; MASK.h=0.5;
  MASK.feather=0.22; MASK.angle=90;
  MASK.params = { exposure:0, contrast:1, saturation:1 };
  openLocalMask(selId);
  toast('已重置');
}

/* 渲染：调整层 + 蒙版手柄 */
function renderMask(){
  const adj = document.getElementById('lmAdj');
  const hd = document.getElementById('lmHandle');
  if (!adj || !hd) return;

  const p = MASK.params;
  const f = ['brightness(' + (1 + p.exposure*0.35).toFixed(3) + ')',
             'contrast(' + p.contrast.toFixed(3) + ')',
             'saturate(' + p.saturation.toFixed(3) + ')'].join(' ');

  if (MASK.mode === 'full'){
    adj.style.filter = f;
    adj.style.maskImage = 'none';
    adj.style.webkitMaskImage = 'none';
    adj.style.clipPath = 'none';
    hd.style.display = 'none';
    // 全图模式：直接把基底也套上滤镜，避免叠加层半透明
    adj.style.opacity = '1';
    return;
  }

  adj.style.opacity = '1';
  hd.style.display = '';

  if (MASK.mode === 'rect'){
    const l = (MASK.x - MASK.w/2)*100, t = (MASK.y - MASK.h/2)*100;
    const r = (MASK.x + MASK.w/2)*100, b = (MASK.y + MASK.h/2)*100;
    adj.style.filter = f;
    adj.style.maskImage = 'none';
    adj.style.webkitMaskImage = 'none';
    adj.style.clipPath = `inset(${t.toFixed(1)}% ${(100-r).toFixed(1)}% ${(100-b).toFixed(1)}% ${l.toFixed(1)}%)`;
    // 羽化：用 blur 近似（滤镜链里加）
    if (MASK.feather > 0.01){
      adj.style.clipPath = 'none';
      const g = `linear-gradient(#000,#000)`;
      adj.style.maskImage = 'none';
      adj.style.webkitMaskImage = 'radial-gradient(ellipse '+((MASK.w*55)).toFixed(0)+'% '+((MASK.h*55)).toFixed(0)+'% at '+(MASK.x*100).toFixed(0)+'% '+(MASK.y*100).toFixed(0)+'%, #000 0%, #000 '+Math.max(0,100-MASK.feather*180).toFixed(0)+'%, transparent 100%)';
    }
    hd.style.clipPath = 'none';
    hd.style.maskImage = 'none';
    hd.style.left = l + '%'; hd.style.top = t + '%';
    hd.style.width = (MASK.w*100) + '%'; hd.style.height = (MASK.h*100) + '%';
    hd.style.borderRadius = '3px';
  } else {
    const mi = maskImageCSS();
    adj.style.filter = f;
    adj.style.clipPath = 'none';
    adj.style.maskImage = mi;
    adj.style.webkitMaskImage = mi;
    hd.style.maskImage = 'none';
    hd.style.width = (MASK.w*100) + '%';
    hd.style.height = (MASK.h*100) + '%';
    hd.style.left = ((MASK.x - MASK.w/2)*100) + '%';
    hd.style.top = ((MASK.y - MASK.h/2)*100) + '%';
    hd.style.borderRadius = (MASK.mode === 'circle') ? '50%' : '3px';
  }
}

/* 拖动蒙版手柄 */
document.addEventListener('mousedown', e=>{
  if (!e.target.closest('#lmHandle')) return;
  MASK_DRAG = { sx:e.clientX, sy:e.clientY, ox:MASK.x, oy:MASK.y };
  e.preventDefault();
});
document.addEventListener('mousemove', e=>{
  if (!MASK_DRAG) return;
  const wrap = document.getElementById('lmWrap');
  if (!wrap) { MASK_DRAG = null; return; }
  const r = wrap.getBoundingClientRect();
  MASK.x = Math.max(0, Math.min(1, MASK_DRAG.ox + (e.clientX - MASK_DRAG.sx)/r.width));
  MASK.y = Math.max(0, Math.min(1, MASK_DRAG.oy + (e.clientY - MASK_DRAG.sy)/r.height));
  // 同步滑块
  ['x','y'].forEach(k=>{
    const inp = document.querySelector('.lm-r[data-k="'+k+'"]');
    if (inp) inp.value = MASK[k];
    const el = document.getElementById('lmV_' + k);
    if (el) el.textContent = MASK[k].toFixed(2);
  });
  renderMask();
});
document.addEventListener('mouseup', ()=>{ MASK_DRAG = null; });

function applyMask(){
  const m = MASK;
  const p = m.params;
  const hasAdj = Math.abs(p.exposure) > 0.01 || Math.abs(p.contrast-1) > 0.01 || Math.abs(p.saturation-1) > 0.01;
  if (!hasAdj && m.mode === 'full'){ toast('没做任何调整'); closeMask(); return; }
  const modeName = { full:'全图', rect:'矩形蒙版', circle:'圆形蒙版', linear:'渐变蒙版' }[m.mode];
  const adjTxt = [];
  if (Math.abs(p.exposure) > 0.01) adjTxt.push('曝光 ' + (p.exposure>=0?'+':'') + p.exposure.toFixed(2) + 'EV');
  if (Math.abs(p.contrast-1) > 0.01) adjTxt.push('对比 ' + p.contrast.toFixed(2));
  if (Math.abs(p.saturation-1) > 0.01) adjTxt.push('饱和 ' + p.saturation.toFixed(2));
  closeMask();
  if (typeof agAdd === 'function'){
    agAdd('ai', `局部调整已应用：<b>${modeName}</b> · ${adjTxt.join(' · ') || '无参数'}<br><br>`
      + (m.mode==='full'
          ? `全图调整。`
          : `<span class="myown">只有蒙版内那块变了，蒙版外保持原样 —— 这是局部调整的意义。`
            + `形状和羽化都是参数，随时能改。</span>`)
      + `<br><br><b>没花钱</b> —— 本地像素运算。`);
  }
  toast('已应用 · 免费');
}
