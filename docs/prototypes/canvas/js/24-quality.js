/* 24-quality.js — 画质与色彩（全部本地运算，免费）
   补齐对照检查里的 P1：
     · 降噪      纯本地（高斯小半径）
     · 锐化      USM（feConvolveMatrix 卷积核）
     · 镜头虚化   景深模拟（径向 mask + blur）
     · 柔化阴影   抬暗部（色阶/曲线能覆盖，但单独给个入口更好懂）
     · HSL       色相 / 饱和 / 明度 分开调

   🔴 这几个都不调模型 —— 花钱的只有"超清放大"和"AI 追色"。
*/

const QUALITY = {
  denoise: 0,       // 0 ~ 1   降噪强度
  sharpen: 0,       // 0 ~ 1   锐化强度
  shadow: 0,        // 0 ~ 1   柔化阴影（抬暗部）
  blur: 0,          // 0 ~ 1   镜头虚化强度
  blurMode: 'edge', // edge | center | linear   虚化作用在哪
  hsl: { hue: 0, sat: 1, light: 0 }
};

/* 生成 SVG 滤镜（降噪 + 锐化 + 柔化阴影） */
function ensureQualityFilter(){
  let svg = document.getElementById('qSvg');
  if (!svg){
    svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.id = 'qSvg';
    svg.setAttribute('width','0'); svg.setAttribute('height','0');
    svg.style.position='absolute'; svg.style.pointerEvents='none';
    document.body.appendChild(svg);
  }
  const d = QUALITY;
  const parts = [];

  // ① 降噪：高斯小半径（sigma 0~1.2）
  const sigma = (d.denoise * 1.2).toFixed(2);
  if (d.denoise > 0.01){
    parts.push(`<feGaussianBlur in="SourceGraphic" stdDeviation="${sigma}" result="denoised"/>`);
  }
  const src = d.denoise > 0.01 ? 'denoised' : 'SourceGraphic';

  // ② 锐化：USM = 原图 + (原图 - 模糊) * 强度
  if (d.sharpen > 0.01){
    const amt = d.sharpen.toFixed(2);
    parts.push(`<feGaussianBlur in="${src}" stdDeviation="1.6" result="blurred"/>`);
    parts.push(`<feComposite in="${src}" in2="blurred" operator="arithmetic"
      k1="0" k2="${(1 + Number(amt)).toFixed(2)}" k3="${(-Number(amt)).toFixed(2)}" k4="0" result="sharpened"/>`);
  }
  const afterSharpen = d.sharpen > 0.01 ? 'sharpened' : src;

  // ③ 柔化阴影：抬暗部（用 table 提亮低端）
  if (d.shadow > 0.01){
    const lift = d.shadow * 0.22;
    const tbl = [0,0.25,0.5,0.75,1].map((x,i)=>{
      const v = i === 0 ? lift : x;
      return Math.min(1, v).toFixed(3);
    }).join(' ');
    parts.push(`<feComponentTransfer in="${afterSharpen}" result="soft"><feFuncR type="table" tableValues="${tbl}"/><feFuncG type="table" tableValues="${tbl}"/><feFuncB type="table" tableValues="${tbl}"/></feComponentTransfer>`);
  }
  const afterShadow = d.shadow > 0.01 ? 'soft' : afterSharpen;

  // ④ HSL：feColorMatrix 做饱和 + 色相旋转（明度用 brightness 在外面）
  const sat = Math.max(0, d.hsl.sat);
  const hueDeg = d.hsl.hue;
  if (Math.abs(sat - 1) > 0.01 || Math.abs(hueDeg) > 0.5){
    // 饱和度矩阵
    const s = sat;
    const sr = 0.213, sg = 0.715, sb = 0.072;
    const m = [
      (sr*(1-s)+s).toFixed(3), (sg*(1-s)).toFixed(3), (sb*(1-s)).toFixed(3), 0, 0,
      (sr*(1-s)).toFixed(3), (sg*(1-s)+s).toFixed(3), (sb*(1-s)).toFixed(3), 0, 0,
      (sr*(1-s)).toFixed(3), (sg*(1-s)).toFixed(3), (sb*(1-s)+s).toFixed(3), 0, 0,
      0, 0, 0, 1, 0
    ].join(' ');
    const rot = hueDeg ? `<feColorMatrix type="hueRotate" values="${hueDeg}" result="hued"/>` : '';
    const srcH = hueDeg ? 'hued' : afterShadow;
    parts.push(`${rot}<feColorMatrix in="${srcH}" type="matrix" values="${m}" result="hsl"/>`);
  }
  const final = (Math.abs(sat-1) > 0.01 || Math.abs(hueDeg) > 0.5) ? 'hsl' : afterShadow;

  svg.innerHTML = `<defs><filter id="qFilter" color-interpolation-filters="sRGB">
    ${parts.join('\n')}
  </filter></defs>`;
  return parts.length > 0;
}

/* 组装最终 filter 字符串 */
function qualityFilterCSS(){
  const ok = ensureQualityFilter();
  const out = [];
  if (ok) out.push('url(#qFilter)');
  // 明度（HSL 的 L）
  if (Math.abs(QUALITY.hsl.light) > 0.01){
    out.push('brightness(' + (1 + QUALITY.hsl.light * 0.5).toFixed(3) + ')');
  }
  // 镜头虚化：CSS blur（作用范围用 mask 控制）
  if (QUALITY.blur > 0.01){
    out.push('blur(' + (QUALITY.blur * 4).toFixed(2) + 'px)');
  }
  return out.length ? out.join(' ') : 'none';
}

/* 虚化的蒙版（让边缘虚化、中心清晰，模拟景深） */
function blurMaskCSS(){
  if (QUALITY.blur < 0.01) return null;
  if (QUALITY.blurMode === 'edge'){
    // 中心清晰，边缘虚 —— 用径向渐变反向
    return `radial-gradient(ellipse 40% 32% at 50% 42%, transparent 0%, transparent 55%, #000 100%)`;
  }
  if (QUALITY.blurMode === 'center'){
    return `radial-gradient(ellipse 40% 32% at 50% 42%, #000 0%, transparent 70%)`;
  }
  return `linear-gradient(180deg, #000 0%, transparent 60%)`;
}

/* ===== 面板 ===== */
function openQuality(id){
  const sid = id || selId || (DOC.items[0] && DOC.items[0].id);
  const s = DOC.items.find(x=>x.id===sid);
  if (!s){ toast('先选一张图'); return; }
  if (typeof hideFloatBar === 'function') hideFloatBar();

  document.getElementById('overlayHost').innerHTML = `
    <div class="le" onclick="if(event.target.classList.contains('lew'))closeQuality()">
      <div class="lew">
        <div class="le-hd">
          <div class="le-t">画质与色彩 · ${esc(s.name)}</div>
          <span class="le-free">免费</span>
          <span class="le-nb">本地运算</span>
          <button class="inp-x" onclick="closeQuality()">✕</button>
        </div>

        <div class="le-body">
          <div class="le-stage">
            <div class="le-img" id="qImg"><div class="le-fig"></div></div>
            <div class="le-tag">全部本地运算 · 不走模型 · 参数不烘焙</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">画质 <span class="le-sec2">（这几个最容易做，也最常忘）</span></div>
            ${qSlider('denoise','降噪',0,1,0.01,'柔化噪点，但会糊一点细节')}
            ${qSlider('sharpen','锐化',0,1,0.01,'USM 锐化，让边缘更清楚')}
            ${qSlider('shadow','柔化阴影',0,1,0.01,'抬起暗部，不死黑')}
            ${qSlider('blur','镜头虚化',0,1,0.01,'模拟景深，突出主体')}

            <div class="q-row-inline" id="qBlurMode" style="display:none">
              <span class="le-l">虚化范围</span>
              <span class="q-modes">
                <button class="q-m on" data-m="edge" onclick="setBlurMode('edge')">边缘</button>
                <button class="q-m" data-m="center" onclick="setBlurMode('center')">中心</button>
                <button class="q-m" data-m="linear" onclick="setBlurMode('linear')">上到下</button>
              </span>
            </div>

            <div class="le-sec" style="margin-top:16px">HSL <span class="le-sec2">（分开调，比整体调准）</span></div>
            ${qSlider('hslHue','色相',-180,180,1,'整体偏色，±180°')}
            ${qSlider('hslSat','饱和度',0,2,0.01,'1.00 = 原样')}
            ${qSlider('hslLight','明度',-1,1,0.01,'0 = 原样')}

            <div class="lm-tip" style="margin-top:14px">
              🔴 <b>这五个全是本地运算</b> —— 降噪、锐化、柔化阴影、虚化、HSL，
              都不调模型，<b>免费且随时能改回去</b>。<br>
              <span style="opacity:.75">真正要花钱的是「超清放大」和「AI 追色」，在另一个面板。</span>
            </div>
          </div>
        </div>

        <div class="le-foot">
          <div class="le-cost">
            花费 <b class="le-zero">0</b>
            <span class="le-costn">本地像素运算 · 不走模型</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="resetQuality()">全部重置</button>
            <button class="insp-b pri" onclick="applyQuality()">应用</button>
          </div>
        </div>
      </div>
    </div>`;
  renderQuality();
}

function qSlider(key, label, min, max, step, tip){
  let v;
  if (key === 'hslHue') v = QUALITY.hsl.hue;
  else if (key === 'hslSat') v = QUALITY.hsl.sat;
  else if (key === 'hslLight') v = QUALITY.hsl.light;
  else v = QUALITY[key];
  return `<div class="le-row">
    <span class="le-l">${label}</span>
    <input type="range" class="le-r" min="${min}" max="${max}" step="${step}" value="${v}"
      oninput="setQuality('${key}', this.value)">
    <span class="le-v" id="qV_${key}">${qFmt(key, v)}</span>
  </div>
  <div class="q-tip">${tip}</div>`;
}

function qFmt(key, v){
  v = Number(v);
  if (key === 'hslHue') return Math.round(v) + '°';
  if (key === 'hslLight') return (v >= 0 ? '+' : '') + v.toFixed(2);
  if (key === 'sharpen' || key === 'denoise' || key === 'shadow' || key === 'blur')
    return (v*100).toFixed(0) + '%';
  return v.toFixed(2);
}

function setQuality(key, val){
  const v = Number(val);
  if (key === 'hslHue') QUALITY.hsl.hue = v;
  else if (key === 'hslSat') QUALITY.hsl.sat = v;
  else if (key === 'hslLight') QUALITY.hsl.light = v;
  else QUALITY[key] = v;
  const el = document.getElementById('qV_' + key);
  if (el) el.textContent = qFmt(key, v);
  if (key === 'blur'){
    const row = document.getElementById('qBlurMode');
    if (row) row.style.display = v > 0.01 ? '' : 'none';
  }
  renderQuality();
}

function setBlurMode(m){
  QUALITY.blurMode = m;
  document.querySelectorAll('.q-m').forEach(b=>b.classList.toggle('on', b.dataset.m === m));
  renderQuality();
}

function renderQuality(){
  const img = document.getElementById('qImg');
  if (!img) return;
  img.style.filter = qualityFilterCSS();
  const mask = blurMaskCSS();
  if (mask){
    img.style.maskImage = mask;
    img.style.webkitMaskImage = mask;
  } else {
    img.style.maskImage = 'none';
    img.style.webkitMaskImage = 'none';
  }
}

function closeQuality(){ document.getElementById('overlayHost').innerHTML = ''; }

function resetQuality(){
  Object.assign(QUALITY, {
    denoise:0, sharpen:0, shadow:0, blur:0, blurMode:'edge',
    hsl:{ hue:0, sat:1, light:0 }
  });
  openQuality(selId);
  toast('已重置');
}

function applyQuality(){
  const q = QUALITY;
  const out = [];
  if (q.denoise > 0.01) out.push('降噪 ' + (q.denoise*100).toFixed(0) + '%');
  if (q.sharpen > 0.01) out.push('锐化 ' + (q.sharpen*100).toFixed(0) + '%');
  if (q.shadow > 0.01) out.push('柔化阴影 ' + (q.shadow*100).toFixed(0) + '%');
  if (q.blur > 0.01) out.push('虚化 ' + (q.blur*100).toFixed(0) + '%（' + {edge:'边缘',center:'中心',linear:'上到下'}[q.blurMode] + '）');
  if (Math.abs(q.hsl.hue) > 0.5) out.push('色相 ' + Math.round(q.hsl.hue) + '°');
  if (Math.abs(q.hsl.sat - 1) > 0.01) out.push('饱和 ' + q.hsl.sat.toFixed(2));
  if (Math.abs(q.hsl.light) > 0.01) out.push('明度 ' + q.hsl.light.toFixed(2));
  closeQuality();

  /* 🔧 2026-10-20 修（审查报告阻断问题 4）：之前只发消息不落盘。现在真写进图层。 */
  let committed = null;
  if (out.length && typeof commitLocalLayer === 'function'){
    committed = commitLocalLayer(
      '画质：' + out.slice(0, 2).join(' '),
      {
        denoise: q.denoise, sharpen: q.sharpen, shadow: q.shadow,
        blur: q.blur, blurMode: q.blurMode,
        hsl: JSON.parse(JSON.stringify(q.hsl || {}))
      },
      '应用画质：' + out.join(' · ')
    );
  }

  if (typeof agAdd === 'function'){
    agAdd('ai', out.length
      ? `画质调整已应用：<b>${out.join(' · ')}</b><br><br><b>没花钱</b> —— 全是本地运算。<br><br>`
        + `<span class="myown">${committed ? '参数已经挂成一层了：导出会带上、撤销能退。' : ''}`
        + `降噪会轻微损细节，锐化过头会有白边 —— 觉得过了随时能调低。</span>`
      : '没做任何调整。');
  }
  toast(out.length ? '已应用 · 免费' : '没改动');
}
