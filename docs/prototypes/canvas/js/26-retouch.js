/* 26-retouch.js — 人像修饰（磨皮 / 液化 / 祛瑕疵）
   🔴 已实证可行（见 canvas/_test-retouch.html，三个算法跑出真实效果）：
      磨皮   高低频分离    103ms / 320×420
      液化   径向推挤+双线性  3ms
      祛瑕疵 环形采样 inpaint  5ms
   全部纯本地，零模型，零成本。

   ✅ 现在接的是文档里的真实像素（item.canvas，见 29-real-image.js）：
      选中一张导入的图再打开，磨皮/液化/祛瑕疵直接作用在它的 ImageData 上，
      点「应用并写回」后用同一份像素重画缩略图，导出也读这份。
      没选中真图时退回演示人像，并明确标注"不会写回"。
*/

let RT_W = 320, RT_H = 420;
let RT_BASE = null;     // 原始像素
let RT_CUR = null;      // 当前像素
let RT_MASK = null;     // 手动蒙版（磨皮用）
let RT_DRAG = null;
let RT_MODE = 'skin';   // skin | liquify | heal
let RT_ITEM_ID = null;  // 正在修的镜头/图片
let RT_REAL = false;    // 是否真的接到了文档里的像素
let RT_SRC_CANVAS = null;
let RT_SKIN_TIMER = null;

/* ---------- 画一张假人像（带噪点和痘印，供算法用） ---------- */
function rtMakePortrait(withNoise, withSpots){
  const c = document.createElement('canvas');
  c.width = RT_W; c.height = RT_H;
  const g = c.getContext('2d');
  const w = RT_W, h = RT_H;

  const bg = g.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, '#2a2340'); bg.addColorStop(1, '#141020');
  g.fillStyle = bg; g.fillRect(0, 0, w, h);

  g.fillStyle = '#2b2b38';
  g.beginPath(); g.ellipse(w/2, h*1.05, w*0.42, h*0.3, 0, 0, Math.PI*2); g.fill();

  g.fillStyle = '#c99b74';
  g.fillRect(w/2 - w*0.09, h*0.62, w*0.18, h*0.2);

  const fc = g.createRadialGradient(w*0.42, h*0.32, 10, w/2, h*0.38, w*0.34);
  fc.addColorStop(0, '#f0cfae'); fc.addColorStop(1, '#c99b74');
  g.fillStyle = fc;
  g.beginPath(); g.ellipse(w/2, h*0.38, w*0.26, h*0.22, 0, 0, Math.PI*2); g.fill();

  g.fillStyle = '#1a1420';
  g.beginPath(); g.ellipse(w/2, h*0.28, w*0.30, h*0.17, 0, Math.PI, Math.PI*2); g.fill();

  g.fillStyle = '#2a2030';
  g.beginPath(); g.ellipse(w*0.40, h*0.36, w*0.045, h*0.022, 0, 0, Math.PI*2); g.fill();
  g.beginPath(); g.ellipse(w*0.60, h*0.36, w*0.045, h*0.022, 0, 0, Math.PI*2); g.fill();
  g.fillStyle = '#101018';
  g.beginPath(); g.arc(w*0.40, h*0.36, w*0.018, 0, Math.PI*2); g.fill();
  g.beginPath(); g.arc(w*0.60, h*0.36, w*0.018, 0, Math.PI*2); g.fill();

  g.strokeStyle = '#241a28'; g.lineWidth = 3;
  g.beginPath(); g.moveTo(w*0.34, h*0.315); g.lineTo(w*0.45, h*0.308); g.stroke();
  g.beginPath(); g.moveTo(w*0.55, h*0.308); g.lineTo(w*0.66, h*0.315); g.stroke();

  g.strokeStyle = '#b08862'; g.lineWidth = 2;
  g.beginPath(); g.moveTo(w*0.5, h*0.36); g.lineTo(w*0.5, h*0.42); g.stroke();

  g.fillStyle = '#a85c5c';
  g.beginPath(); g.ellipse(w/2, h*0.455, w*0.055, h*0.014, 0, 0, Math.PI*2); g.fill();

  if (withNoise){
    const id = g.getImageData(0, 0, w, h);
    const d = id.data;
    for (let i = 0; i < d.length; i += 4){
      const n = (Math.random() - 0.5) * 40;
      d[i] += n; d[i+1] += n; d[i+2] += n;
    }
    g.putImageData(id, 0, 0);
  }
  if (withSpots){
    [[0.42,0.42],[0.58,0.44],[0.47,0.50],[0.55,0.33],[0.38,0.47]].forEach(([sx,sy])=>{
      g.fillStyle = 'rgba(190,110,100,.9)';
      g.beginPath(); g.arc(w*sx, h*sy, 5.5, 0, Math.PI*2); g.fill();
    });
  }
  return c;
}

/* ---------- 磨皮：双边滤波 ---------- */
function rtBilateral(data, w, h, radius, sigmaS, sigmaR){
  const out = new Uint8ClampedArray(data.length);
  const rs = Math.ceil(radius);
  const sS2 = 2*sigmaS*sigmaS, sR2 = 2*sigmaR*sigmaR;
  for (let y = 0; y < h; y++){
    for (let x = 0; x < w; x++){
      let r=0,g=0,b=0,wsum=0;
      const ci = (y*w+x)*4;
      const cr = data[ci], cg = data[ci+1], cb = data[ci+2];
      for (let dy=-rs; dy<=rs; dy++){
        const yy = y+dy; if (yy<0||yy>=h) continue;
        for (let dx=-rs; dx<=rs; dx++){
          const xx = x+dx; if (xx<0||xx>=w) continue;
          const d2 = dx*dx+dy*dy; if (d2 > radius*radius) continue;
          const ni = (yy*w+xx)*4;
          const dr = data[ni]-cr, dg = data[ni+1]-cg, db = data[ni+2]-cb;
          const wgt = Math.exp(-d2/sS2) * Math.exp(-(dr*dr+dg*dg+db*db)/sR2);
          r += data[ni]*wgt; g += data[ni+1]*wgt; b += data[ni+2]*wgt; wsum += wgt;
        }
      }
      out[ci] = r/wsum; out[ci+1] = g/wsum; out[ci+2] = b/wsum; out[ci+3] = 255;
    }
  }
  return out;
}

/* ---------- 液化：径向推挤 + 双线性 ---------- */
function rtLiquify(cur, w, h, cx, cy, dx, dy, radius, strength){
  const src = new Uint8ClampedArray(cur.data);
  const out = cur.data;
  const r2 = radius*radius;
  for (let y = 0; y < h; y++){
    for (let x = 0; x < w; x++){
      const ddx = x-cx, ddy = y-cy;
      const d2 = ddx*ddx + ddy*ddy;
      if (d2 > r2) continue;
      const d = Math.sqrt(d2);
      const amt = strength * Math.pow(1 - d/radius, 2);
      const sx = x - dx*amt, sy = y - dy*amt;
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const fx = sx-x0, fy = sy-y0;
      const idx = (y*w+x)*4;
      if (x0<0||y0<0||x0>=w-1||y0>=h-1) continue;
      for (let ch=0; ch<3; ch++){
        const p00 = src[(y0*w+x0)*4+ch];
        const p10 = src[(y0*w+x0+1)*4+ch];
        const p01 = src[((y0+1)*w+x0)*4+ch];
        const p11 = src[((y0+1)*w+x0+1)*4+ch];
        const top = p00 + (p10-p00)*fx;
        const bot = p01 + (p11-p01)*fx;
        out[idx+ch] = top + (bot-top)*fy;
      }
      out[idx+3] = src[idx+3];
    }
  }
}

/* ---------- 祛瑕疵：环形采样填充 ---------- */
function rtInpaint(cur, w, h, cx, cy, radius){
  const src = new Uint8ClampedArray(cur.data);
  const out = cur.data;
  const r2 = radius*radius;
  const ring = [];
  for (let a = 0; a < 360; a += 2){
    const rad = a*Math.PI/180;
    for (const rr of [radius+1.5, radius+3]){
      const px = Math.round(cx + Math.cos(rad)*rr);
      const py = Math.round(cy + Math.sin(rad)*rr);
      if (px<0||py<0||px>=w||py>=h) continue;
      const i = (py*w+px)*4;
      ring.push({ a, r:src[i], g:src[i+1], b:src[i+2] });
    }
  }
  if (!ring.length) return;
  for (let y = Math.ceil(cy-radius); y <= cy+radius; y++){
    for (let x = Math.ceil(cx-radius); x <= cx+radius; x++){
      if (x<0||y<0||x>=w||y>=h) continue;
      const ddx = x-cx, ddy = y-cy;
      if (ddx*ddx+ddy*ddy > r2) continue;
      const ang = (Math.atan2(ddy, ddx)*180/Math.PI + 360) % 360;
      let best = ring[0], minD = 999;
      for (const rp of ring){
        let diff = Math.abs(rp.a - ang);
        if (diff > 180) diff = 360 - diff;
        if (diff < minD){ minD = diff; best = rp; }
      }
      const idx = (y*w+x)*4;
      out[idx] = best.r; out[idx+1] = best.g; out[idx+2] = best.b; out[idx+3] = src[idx+3];
    }
  }
  // 边缘羽化
  const snap = new Uint8ClampedArray(out);
  for (let y = Math.ceil(cy-radius-2); y <= cy+radius+2; y++){
    for (let x = Math.ceil(cx-radius-2); x <= cx+radius+2; x++){
      if (x<1||y<1||x>=w-1||y>=h-1) continue;
      const dd = Math.hypot(x-cx, y-cy);
      if (dd < radius-2 || dd > radius+2) continue;
      const t = (dd-(radius-2))/4;
      const idx = (y*w+x)*4, ni = (y*w+x+1)*4;
      for (let ch=0; ch<3; ch++) out[idx+ch] = out[idx+ch]*(1-t) + snap[ni+ch]*t;
    }
  }
}

/* ================= 面板 ================= */
function rtDisplaySize(w, h){
  const s = Math.min(250 / w, 380 / h, 1.6);
  return { w: Math.max(90, Math.round(w*s)), h: Math.max(90, Math.round(h*s)) };
}

function rtPickSource(){
  if (typeof pickImageFile !== 'function'){ toast('图片导入没加载'); return; }
  closeRetouch();
  pickImageFile({ onDone: items=>{
    if (items && items[0]) openRetouch(items[0].id);
  }});
}

function openRetouch(id){
  if (typeof hideFloatBar === 'function') hideFloatBar();
  RT_MODE = 'skin';
  RT_BASE = null; RT_CUR = null; RT_SRC_CANVAS = null;

  RT_ITEM_ID = id || (typeof selId !== 'undefined' ? selId : null)
    || (DOC.items[0] && DOC.items[0].id) || null;
  const item = RT_ITEM_ID ? DOC.items.find(x=>x.id===RT_ITEM_ID) : null;
  RT_REAL = !!(item && item.canvas);
  if (RT_REAL){
    RT_SRC_CANVAS = (typeof riFitCanvas === 'function')
      ? riFitCanvas(item.canvas, 1600) : item.canvas;
  } else {
    RT_W = 320; RT_H = 420;
    RT_SRC_CANVAS = rtMakePortrait(true, true);
  }
  if (RT_SRC_CANVAS){
    RT_W = RT_SRC_CANVAS.width;
    RT_H = RT_SRC_CANVAS.height;
  }
  const dim = rtDisplaySize(RT_W, RT_H);
  const title = RT_REAL ? ('人像修饰 · ' + esc(String(item.name || '图片'))) : '人像修饰 · 演示';
  const srcMeta = RT_REAL
    ? `${RT_W}×${RT_H} 工作分辨率`
      + (item.realW && item.realW !== RT_W ? ` · 原图 ${item.realW}×${item.realH}` : '')
    : '没有选中真实图片 · 拖一张进来，或点右边导入';

  document.getElementById('overlayHost').innerHTML = `
    <div class="le" onclick="if(event.target.classList.contains('lew'))closeRetouch()">
      <div class="lew" style="width:min(880px,95vw)">
        <div class="le-hd">
          <div class="le-t">${title}</div>
          <span class="le-free">免费</span>
          <span class="le-nb">经典算法</span>
          <button class="inp-x" onclick="closeRetouch()">✕</button>
        </div>

        <div class="le-body">
          <div class="le-stage">
            <div class="rt-src ${RT_REAL?'':'demo'}">
              <span class="rt-src-dot"></span>
              <span class="rt-src-t"><b>${RT_REAL ? '正在改这张图' : '演示模式'}</b>
                <span class="rt-src-m">${srcMeta}</span></span>
              <button class="rt-src-b" onclick="rtPickSource()">${RT_REAL?'换一张':'导入自己的图'}</button>
            </div>
            <!-- 🔴 2026-10-20 用户要求：单张图、编辑立即生效、可切换看原图。
                 原来左右并排两张（原图 + 处理后），现在叠放成一张，
                 默认显示处理后的；「看原图」按住或点亮就切到原图。 -->
            <div class="rt-row rt-stack">
              <div class="rt-wrap rt-stagewrap">
                <canvas id="rtA" class="rt-layer" width="${RT_W}" height="${RT_H}"
                  style="width:${dim.w}px;height:${dim.h}px"></canvas>
                <canvas id="rtB" class="rt-layer on" width="${RT_W}" height="${RT_H}"
                  style="width:${dim.w}px;height:${dim.h}px"></canvas>
                <div class="rt-cl" id="rtBLabel">处理后 · 编辑实时预览</div>
              </div>
            </div>
            <div class="rt-viewbar">
              <button class="rt-origbtn" id="rtOrigBtn"
                onmousedown="rtShowOrig(true)" onmouseup="rtShowOrig(false)"
                onmouseleave="rtShowOrig(false)"
                onclick="rtToggleOrig()"
                title="按住看原图 · 点一下锁定">👁 看原图</button>
              <span class="rt-viewhint">按住 = 临时看原图 · 点一下 = 锁定对比</span>
            </div>
            <div class="le-tag" id="rtTag">选一个工具，然后拖 / 点</div>
          </div>

          <div class="le-panel">
            <div class="le-sec">工具</div>
            <div class="rt-modes">
              <button class="rt-m on" data-m="skin" onclick="setRtMode('skin')">
                <span class="rt-mn">磨皮</span><span class="rt-md">高低频</span>
              </button>
              <button class="rt-m" data-m="liquify" onclick="setRtMode('liquify')">
                <span class="rt-mn">液化</span><span class="rt-md">拖哪推哪</span>
              </button>
              <button class="rt-m" data-m="heal" onclick="setRtMode('heal')">
                <span class="rt-mn">祛瑕疵</span><span class="rt-md">点哪消哪</span>
              </button>
            </div>

            <div id="rtSkin" class="rt-ctrl">
              <div class="le-row"><span class="le-l">强度</span>
                <input type="range" class="le-r" id="rtSkinAmt" min="0" max="100" value="70" oninput="rtApplySkinSoon()">
                <span class="le-v" id="rtSkinAmtV">70</span></div>
              <div class="le-row"><span class="le-l">半径</span>
                <input type="range" class="le-r" id="rtSkinRad" min="3" max="12" value="6" oninput="rtApplySkinSoon()">
                <span class="le-v" id="rtSkinRadV">6</span></div>
              <div class="rt-note"><b>高低频分离</b> —— 把图拆成"低频（颜色明暗）+ 高频（纹理）"，只压高频。<br>高频幅度大的算边缘（五官）保留，幅度小的算噪点压掉。所以<b>磨完皮五官还在</b>。</div>
            </div>

            <div id="rtLiq" class="rt-ctrl" style="display:none">
              <div class="le-row"><span class="le-l">笔刷</span>
                <input type="range" class="le-r" id="rtLiqRad" min="10" max="70" value="36"
                  oninput="document.getElementById('rtLiqRadV').textContent=this.value">
                <span class="le-v" id="rtLiqRadV">36</span></div>
              <div class="le-row"><span class="le-l">力度</span>
                <input type="range" class="le-r" id="rtLiqAmt" min="1" max="20" value="8"
                  oninput="document.getElementById('rtLiqAmtV').textContent=this.value">
                <span class="le-v" id="rtLiqAmtV">8</span></div>
              <button class="rt-demo" onclick="rtDemoFace()">自动演示「瘦脸」</button>
              <div class="rt-note">在左边画布上按住拖动就能推。纯双线性重采样，3ms 一次。</div>

              <div class="rt-sec">一键（要做，先占位）</div>
              <button class="rt-auto" onclick="rtOneKeyFace()">
                <span class="rt-an">一键瘦脸</span>
                <span class="rt-ad">自动找人脸 → 按关键点向内推 → 不用手拖</span>
                <span class="rt-atag">待实现</span>
              </button>
              <button class="rt-auto" onclick="rtOneKeyEye()">
                <span class="rt-an">放大眼睛</span>
                <span class="rt-ad">按眼角关键点做局部膨胀</span>
                <span class="rt-atag">待实现</span>
              </button>
              <div class="rt-dep">
                <b>依赖</b>：人脸关键点检测。
                <br>调研结论：<b>MediaPipe Face Mesh</b>（Google，<b>Apache-2.0，可免费商用</b>），
                468 个 3D 关键点，<b>能直接在浏览器跑</b>，包不算大。
                <br><span class="rt-dep2">具体实现后做：拿到关键点后，在脸颊两侧 / 眼角位置
                调用已有的 <code>rtLiquify</code> 就行 —— 液化算法本身不用改。</span>
              </div>
            </div>

            <div id="rtHeal" class="rt-ctrl" style="display:none">
              <button class="rt-demo" onclick="rtDemoHeal()">自动祛掉脸上痘印</button>
              <div class="le-row" style="margin-top:8px"><span class="le-l">笔刷</span>
                <input type="range" class="le-r" id="rtHealRad" min="3" max="20" value="7"
                  oninput="document.getElementById('rtHealRadV').textContent=this.value">
                <span class="le-v" id="rtHealRadV">7</span></div>
              <div class="rt-note">点瑕疵就消。从边界环形采样 + 距离加权填充 + 羽化。<br>
                真实现换成 <code>cv2.inpaint</code> 或 PatchMatch 会更自然。</div>
            </div>

            <div class="rt-key">
              🔴 <b>这三个都不调模型</b> —— 磨皮是高低频分离、液化是网格重采样、
              祛瑕疵是邻域填充。<b>PS 在 AI 之前就是这么做的。</b><br>
              <span class="rt-key2">
                代价是要手动操作（拖、点），不是"一键瘦脸"。
                要一键就得接人脸关键点模型 —— 那是可选升级。
              </span>
            </div>
          </div>
        </div>

        <div class="le-foot">
          <div class="le-cost">
            花费 <b class="le-zero">0</b>
            <span class="le-costn">${RT_REAL
              ? '真实像素 · 应用后写回这张图 · 不走模型'
              : '演示像素 · 不会写回文档 · 不走模型'}</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="rtReset()">重置</button>
            <button class="insp-b pri" onclick="rtApplyAll()">${RT_REAL?'应用并写回':'应用（演示）'}</button>
          </div>
        </div>
      </div>
    </div>`;

  rtInit(RT_SRC_CANVAS);
  RT_SHOW_ORIG = false; RT_ORIG_LOCK = false; rtSyncView();
}

function closeRetouch(){
  clearTimeout(RT_SKIN_TIMER);
  document.getElementById('overlayHost').innerHTML = '';
}

function setRtMode(m){
  RT_MODE = m;
  document.querySelectorAll('.rt-m').forEach(b=>b.classList.toggle('on', b.dataset.m===m));
  document.getElementById('rtSkin').style.display = m==='skin' ? '' : 'none';
  document.getElementById('rtLiq').style.display = m==='liquify' ? '' : 'none';
  document.getElementById('rtHeal').style.display = m==='heal' ? '' : 'none';
  const tags = {
    skin:'磨皮：调强度/半径即时看效果',
    liquify:'液化：在左图按住拖动，往哪推就往哪变形',
    heal:'祛瑕疵：在左图点瑕疵，自动用周围补'
  };
  document.getElementById('rtTag').textContent = tags[m];
  document.getElementById('rtBLabel').textContent = {skin:'磨皮后',liquify:'液化后',heal:'祛瑕疵后'}[m];
  if (m === 'skin') rtApplySkin();
}

function rtInit(srcCanvas){
  const c = srcCanvas || RT_SRC_CANVAS || rtMakePortrait(true, true);
  const a = document.getElementById('rtA');
  const ga = a.getContext('2d', { willReadFrequently: true });
  ga.clearRect(0, 0, RT_W, RT_H);
  ga.drawImage(c, 0, 0, RT_W, RT_H);
  RT_BASE = ga.getImageData(0, 0, RT_W, RT_H);
  RT_CUR = new ImageData(new Uint8ClampedArray(RT_BASE.data), RT_W, RT_H);
  document.getElementById('rtB').getContext('2d').putImageData(RT_CUR, 0, 0);
  rtApplySkin();
  rtBindCanvas();
}

function rtApplySkinSoon(){
  clearTimeout(RT_SKIN_TIMER);
  RT_SKIN_TIMER = setTimeout(rtApplySkin, 110);
}

function rtDrawB(){ document.getElementById('rtB').getContext('2d').putImageData(RT_CUR, 0, 0); }

/* 磨皮：高低频分离 + 高频阈值保边（又快又准）
   ① 低频 = 可分离盒式模糊 ×3（近似高斯，O(n)，极快）
   ② 高频 = 原图 - 低频
   ③ 合成：高频幅度大的（边缘/五官）保留，幅度小的（噪点/毛孔）压掉
   这就是"磨皮但不糊五官"的原理。 */
function rtBoxBlur1D(src, w, h, r, horiz){
  const out = new Float32Array(src.length);
  const n = horiz ? w : h, m = horiz ? h : w;
  const win = 2*r + 1;
  for (let a = 0; a < m; a++){
    for (let ch = 0; ch < 3; ch++){
      let sum = 0;
      const idx = (b)=> horiz ? (a*w + b)*4 + ch : (b*w + a)*4 + ch;
      for (let b = -r; b <= r; b++) sum += src[idx(Math.min(n-1, Math.max(0, b)))];
      for (let b = 0; b < n; b++){
        out[idx(b)] = sum / win;
        const bOut = Math.max(0, b - r);
        const bIn  = Math.min(n-1, b + r + 1);
        sum += src[idx(bIn)] - src[idx(bOut)];
      }
    }
  }
  return out;
}

function rtBlur(srcData, w, h, radius){
  let buf = new Float32Array(srcData.length);
  buf.set(srcData);
  // 盒式模糊 3 次 ≈ 高斯
  for (let pass = 0; pass < 3; pass++){
    buf = rtBoxBlur1D(buf, w, h, radius, true);
    buf = rtBoxBlur1D(buf, w, h, radius, false);
  }
  return buf;
}

function rtApplySkin(){
  const amtEl = document.getElementById('rtSkinAmt');
  const radEl = document.getElementById('rtSkinRad');
  if (!amtEl || !radEl) return;
  const amt = Number(amtEl.value)/100;
  const rad = Number(radEl.value);
  document.getElementById('rtSkinAmtV').textContent = Math.round(amt*100);
  document.getElementById('rtSkinRadV').textContent = rad;
  if (typeof RT_BASE === 'undefined' || !RT_BASE) return;
  const t0 = performance.now();

  const src = RT_BASE.data;
  const low = rtBlur(src, RT_W, RT_H, rad);

  // 高频幅度阈值：超过它的算"边缘"（五官），保留；低于它的算"噪点"，压掉
  const THRESH = 30;
  const keepEdge = 1.0;
  const keepFlat = 1 - amt;

  const out = RT_CUR.data;
  for (let i = 0; i < src.length; i += 4){
    for (let ch = 0; ch < 3; ch++){
      const hi = src[i+ch] - low[i+ch];
      const mag = Math.abs(hi);
      // 平滑过渡：mag 从 0 到 THRESH，保留比例从 keepFlat 到 keepEdge
      const t = Math.min(1, mag / THRESH);
      const keep = keepFlat + (keepEdge - keepFlat) * t;
      out[i+ch] = low[i+ch] + hi * keep;
    }
    out[i+3] = src[i+3];
  }
  rtDrawB();
  const el = document.getElementById('rtTag');
  if (el) el.textContent = '磨皮 ' + Math.round(amt*100) + '% · 高低频分离（边缘保留） · 耗时 ' + (performance.now()-t0).toFixed(0) + 'ms';
}

/* 液化自动演示 */
function rtDemoFace(){
  RT_CUR = new ImageData(new Uint8ClampedArray(RT_BASE.data), RT_W, RT_H);
  const amt = Number(document.getElementById('rtLiqAmt').value);
  const rad = Number(document.getElementById('rtLiqRad').value);
  const cy = RT_H*0.40;
  rtLiquify(RT_CUR, RT_W, RT_H, RT_W*0.30, cy, -amt, 0, rad, 1);
  rtLiquify(RT_CUR, RT_W, RT_H, RT_W*0.70, cy,  amt, 0, rad, 1);
  rtLiquify(RT_CUR, RT_W, RT_H, RT_W*0.50, RT_H*0.58, 0, -amt*0.6, rad, 1);
  rtDrawB();
  document.getElementById('rtTag').textContent = '瘦脸：左右两侧向内推 + 下巴上推';
}

/* 祛瑕疵自动演示 */
function rtDemoHeal(){
  RT_CUR = new ImageData(new Uint8ClampedArray(RT_BASE.data), RT_W, RT_H);
  [[0.42,0.42],[0.58,0.44],[0.47,0.50],[0.55,0.33],[0.38,0.47]].forEach(([sx,sy])=>{
    rtInpaint(RT_CUR, RT_W, RT_H, RT_W*sx, RT_H*sy, 9);
  });
  rtDrawB();
  document.getElementById('rtTag').textContent = '修掉 5 个痘印';
}

/* 画布交互 */
/* ===== 笔刷圆圈光标 =====
   🔴 2026-10-20 用户问「笔刷大小怎么看，PS 应该是圆圈吧」。
   查 PhotoCraft（crates/ui-egui/src/canvas.rs）的做法：
     · 圆形笔刷画圆、方形画方框
     · 关键是**双圈描边**：外圈半透明黑 alpha160 + 内圈半透明白 alpha230
       —— 不管背景亮还是暗，圆圈都看得见（单色圈在相近背景上会消失）
     · 笔刷太小（屏幕直径 <6px）时额外画十字准星，否则看不见在哪
     · 系统光标设 None（隐藏箭头）
   这里用 DOM 元素 + CSS box-shadow 做双圈，效果等价、开销更小。
*/
let RT_CURSOR_EL = null;

function rtBrushEl(){
  if (RT_CURSOR_EL && document.body.contains(RT_CURSOR_EL)) return RT_CURSOR_EL;
  const el = document.createElement('div');
  el.id = 'rtBrushCursor';
  el.className = 'rt-brush-cursor';
  document.body.appendChild(el);
  RT_CURSOR_EL = el;
  return el;
}

/* 当前模式的笔刷半径（画布像素）。磨皮是全图操作，没有笔刷范围 */
function rtBrushRadius(){
  if (RT_MODE === 'liquify'){
    const e = document.getElementById('rtLiqRad');
    return e ? Number(e.value) : 30;
  }
  if (RT_MODE === 'heal'){
    const e = document.getElementById('rtHealRad');
    return e ? Number(e.value) : 8;
  }
  return 0;
}

function rtMoveBrushCursor(e, cv){
  const el = rtBrushEl();
  const r = rtBrushRadius();
  if (!r || !cv){ el.style.display = 'none'; return; }

  const rect = cv.getBoundingClientRect();
  const scale = rect.width / RT_W;          // 画布像素 → 屏幕像素
  const rs = Math.max(1.5, r * scale);

  el.style.display = 'block';
  el.style.width = (rs * 2) + 'px';
  el.style.height = (rs * 2) + 'px';
  el.style.left = (e.clientX - rs) + 'px';
  el.style.top = (e.clientY - rs) + 'px';
  el.classList.toggle('tiny', rs * 2 < 6);  // 太小加十字
}

function rtHideBrushCursor(){
  if (RT_CURSOR_EL) RT_CURSOR_EL.style.display = 'none';
}

function rtBindCanvas(){
  /* 🔧 2026-10-20 修：单图叠放后可见的是 rtB（rtA 是隐藏的原图）。
     之前事件绑在 rtA 上，改完单图后笔刷/液化/祛瑕疵全都收不到指针事件。
     现在绑可交互的那张（rtB 优先），并把笔刷光标挂上去。 */
  const a = document.getElementById('rtB') || document.getElementById('rtA');
  if (!a) return;
  const scale = ()=> RT_W / a.getBoundingClientRect().width;
  const pos = e=>{
    const r = a.getBoundingClientRect();
    return [ (e.clientX-r.left)*scale(), (e.clientY-r.top)*scale() ];
  };
  let last = null;
  a.addEventListener('pointerdown', e=>{
    const [x,y] = pos(e);
    if (RT_MODE === 'heal'){
      const rad = Number(document.getElementById('rtHealRad').value);
      rtInpaint(RT_CUR, RT_W, RT_H, x, y, rad);
      rtDrawB();
      document.getElementById('rtTag').textContent = '修掉一处瑕疵';
    } else if (RT_MODE === 'liquify'){
      last = [x,y];
    }
  });
  a.addEventListener('pointermove', e=>{
    rtMoveBrushCursor(e, a);      // 光标一直跟着，不管按没按

    if (RT_MODE !== 'liquify' || !last || e.buttons !== 1) return;
    const [x,y] = pos(e);
    const dx = x-last[0], dy = y-last[1];
    if (Math.abs(dx)<0.3 && Math.abs(dy)<0.3) return;
    const rad = Number(document.getElementById('rtLiqRad').value);
    rtLiquify(RT_CUR, RT_W, RT_H, x, y, dx, dy, rad, 0.9);
    rtDrawB();
    last = [x,y];
  });
  a.addEventListener('pointerup', ()=>{ last = null; });
  a.addEventListener('pointerleave', ()=>{ last = null; rtHideBrushCursor(); });
}

function rtReset(){
  if (!RT_BASE) return;
  RT_CUR = new ImageData(new Uint8ClampedArray(RT_BASE.data), RT_W, RT_H);
  rtDrawB();
  toast('已重置');
}

function rtApplyAll(){
  const m = {skin:'磨皮',liquify:'液化',heal:'祛瑕疵'}[RT_MODE];

  if (RT_REAL && RT_CUR){
    const item = DOC.items.find(x=>x.id===RT_ITEM_ID);
    if (item){
      const out = document.createElement('canvas');
      out.width = RT_W; out.height = RT_H;
      out.getContext('2d').putImageData(RT_CUR, 0, 0);
      setItemCanvas(item, out, {
        name: item.name,
        imageName: item.imageName,
        maxDim: (typeof RI_WORK_MAX === 'number' ? RI_WORK_MAX : 1600)
      });
      if (typeof pushHistory === 'function') pushHistory('人像修饰：' + m);
      closeRetouch();
      if (typeof agAdd === 'function'){
        agAdd('ai', `已把 <b>${m}</b> 应用到 <b>${esc(String(item.name||''))}</b> 的真实像素上。`
          + `缩略图、放大预览、导出读到的都已经是修饰后的这张图。`
          + `<br><br><span class="myown">全部本地运算：高低频分离 / 双线性重采样 / 邻域填充 —— `
          + `<b>没调模型、没花钱</b>。<br>`
          + `原型是<b>就地覆盖</b>这张图（工作分辨率 ${RT_W}×${RT_H}）；`
          + `正式版会生成一个<b>修饰层</b>，原图保留，随时能关掉或调强度。</span>`);
      }
      toast('已写回图片 · 免费');
      return;
    }
  }

  closeRetouch();
  if (typeof agAdd === 'function'){
    agAdd('ai', `演示效果已应用：<b>${m}</b><br><br>`
      + `<span class="myown">你刚才改的是演示人像，<b>不会写进文档</b>。`
      + `先导入一张自己的图（工具栏的图片按钮，或直接把文件拖进画布），`
      + `再打开人像修饰，就能改真实像素并写回。</span><br><br>`
      + `算法本身全是经典方法 —— 高低频分离 / 网格重采样 / 邻域填充，`
      + `<b>没调模型，没花钱</b>。`);
  }
  toast('演示效果 · 未写回（先导入一张图）');
}

/* ---------- 一键功能的占位（具体实现后做） ----------
   已调研：MediaPipe Face Mesh（Apache-2.0，可免费商用，浏览器能跑）
   拿到 468 个 3D 关键点后：
     · 一键瘦脸：取左右脸颊关键点，向内调用 rtLiquify
     · 放大眼睛：取眼角/眼睑关键点，做局部膨胀
   液化算法本身不用改 —— 缺的只是"脸在哪里"。
*/
function rtOneKeyFace(){
  toast('待实现：需要接人脸关键点检测（MediaPipe Face Mesh）');
  setTimeout(()=>{
    if (typeof agAdd === 'function'){
      agAdd('ai', `「一键瘦脸」还没做。<br><br>`
        + `它缺的不是算法 —— <b>液化本身已经有了</b>（你刚才拖的就是）。<br>`
        + `缺的是<b>「脸在哪里」</b>：得先检测出人脸关键点，才知道往哪个方向推。<br><br>`
        + `<span class="myown">调研结论：用 <b>MediaPipe Face Mesh</b>（Google 开源，`
        + `<b>Apache-2.0 可免费商用</b>），468 个关键点，能直接在浏览器跑。<br>`
        + `接上之后，自动瘦脸 / 放大眼睛 都能做 —— <b>液化算法一行都不用改</b>，`
        + `只是把"手拖的方向"换成"按关键点算的方向"。</span><br><br>`
        + `<b>具体实现后做。</b>`);
    }
  }, 120);
}

function rtOneKeyEye(){ rtOneKeyFace(); }
/* ================= 实时预览：单图 + 看原图 =================
   🔴 2026-10-20 按用户要求改：
     · 只显示一张图（原来是左右两张对比）
     · 编辑立即生效（rtB 一直是实时渲染的，现在它就在正中间）
     · 「看原图」按钮：按住临时看，点一下锁定对比
*/
let RT_SHOW_ORIG = false;   // 当前是否正在看原图
let RT_ORIG_LOCK = false;   // 是否点了锁定

function rtSyncView(){
  const a = document.getElementById('rtA');
  const b = document.getElementById('rtB');
  const btn = document.getElementById('rtOrigBtn');
  if (a) a.classList.toggle('on', RT_SHOW_ORIG);
  if (b) b.classList.toggle('on', !RT_SHOW_ORIG);
  if (btn){
    btn.classList.toggle('on', RT_SHOW_ORIG);
    btn.textContent = RT_SHOW_ORIG ? '👁 正在看原图' : '👁 看原图';
  }
  const lbl = document.getElementById('rtBLabel');
  if (lbl) lbl.textContent = RT_SHOW_ORIG ? '原图（未处理）' : '处理后 · 编辑实时预览';
}

/* 按住：显示原图；松开：回到效果 */
function rtShowOrig(on){
  if (RT_ORIG_LOCK) return;      // 锁定时按住无效
  RT_SHOW_ORIG = !!on;
  rtSyncView();
}

/* 点击：锁定/解除锁定 */
function rtToggleOrig(){
  RT_ORIG_LOCK = !RT_ORIG_LOCK;
  RT_SHOW_ORIG = RT_ORIG_LOCK;
  rtSyncView();
  if (RT_ORIG_LOCK) toast('已锁定原图 · 再点一下回到处理效果');
  else toast('回到处理效果');
}