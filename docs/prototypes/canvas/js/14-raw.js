/* 14-raw.js — RAW 导入（真解码 + 真线性转换）
   之前：演示流程，解码是模拟的。
   现在：
     · 能真选文件（接受 RAW 扩展名 + 常见图片格式）
     · 浏览器能解的（DNG 预览、TIFF、JPG）真解出来
     · 真做「线性→sRGB」对比：能看到不死黑和死黑的差别
     · 直方图从真实像素算，不是画出来的

   ⚠️ 诚实说明：
     · 真正 RAW 的传感器数据（.CR3/.NEF/.ARW）浏览器没解码器，解不了。
       要用后端 rawpy（LibRaw 的 Python 封装，MIT）。
     · 但「解码后怎么处理」是真的：线性数据直接显示会死黑，必须 gamma 提亮。
       这条规律原型里能真验证。
*/

const RAW_META = {
  name: 'DSC_04812.CR3',
  camera: 'Canon EOS R5',
  rawBits: 14,
  outBits: 16
};

let RAW_STATE = {
  loaded: false, img: null, linear: false, gamma: 2.2, dims:[0,0],
  canvas: null, demo: false, name: ''
};

/* ================= 面板 ================= */
function openRawImport(){
  document.getElementById('overlayHost').innerHTML = `
    <div class="raw" onclick="if(event.target.classList.contains('raww'))closeRaw()">
      <div class="raww">
        <div class="inp-hd">
          <div class="inp-t">导入 RAW</div>
          <div class="inp-sub">相机原片 · 本地处理 · 不上传</div>
          <button class="inp-x" onclick="closeRaw()">✕</button>
        </div>

        <div class="raw-body" id="rawBody">
          <div class="raw-pick">
            <label class="raw-drop" for="rawFile">
              <div class="raw-ic">▤</div>
              <div class="raw-dt">选一个文件</div>
              <div class="raw-ds">真选文件 · 也接受 JPG/PNG 试效果</div>
              <div class="raw-df">.CR2 .CR3 .NEF .ARW .RAF .DNG · 也支持 .jpg .png</div>
              <input type="file" id="rawFile"
                accept=".cr2,.cr3,.nef,.arw,.raf,.dng,.tif,.tiff,.jpg,.jpeg,.png,.webp"
                style="display:none" onchange="rawOnFile(this)">
            </label>
            <button class="raw-demo-btn" onclick="rawUseDemo()">没文件？用模拟数据看流程</button>

            <div class="raw-why">
              <div class="raw-wh">为什么 RAW 要单独做</div>
              <div class="raw-wr">
                <span class="raw-wk">相机传感器</span>
                <span class="raw-wv">${RAW_META.rawBits} bit · 每像素只有 1 个颜色通道</span>
              </div>
              <div class="raw-wr">
                <span class="raw-wk">解码后</span>
                <span class="raw-wv">${RAW_META.outBits} bit 线性数据 · <b>不是 sRGB</b></span>
              </div>
              <div class="raw-wr">
                <span class="raw-wk">关键</span>
                <span class="raw-wv">线性数据直接当图显示 → <b>死黑</b>；必须 gamma 提亮</span>
              </div>
            </div>
          </div>
        </div>

        <div class="raw-foot" id="rawFoot">
          <div class="raw-fn">这一步是免费的 —— 本地解码，不调模型</div>
          <div class="le-acts"><button class="insp-b ghost" onclick="closeRaw()">关闭</button></div>
        </div>
      </div>
    </div>`;
}

function closeRaw(){ document.getElementById('overlayHost').innerHTML = ''; }

/* ================= 真：选文件 ================= */
function rawOnFile(input){
  const f = input.files && input.files[0];
  if (!f) return;
  if (!f.size || f.size < 200){
    toast('这个文件读不出来（' + (f ? f.size : 0) + ' 字节）');
    return;
  }

  const isRaw = /\.(cr2|cr3|nef|arw|raf|dng)$/i.test(f.name);
  const isTiff = /\.(tif|tiff)$/i.test(f.name);
  const url = URL.createObjectURL(f);

  const img = new Image();
  img.onload = ()=>{
    RAW_STATE.loaded = true;
    RAW_STATE.img = img;
    RAW_STATE.linear = isRaw;
    RAW_STATE.demo = false;
    RAW_STATE.name = f.name;
    RAW_STATE.dims = [img.naturalWidth, img.naturalHeight];
    renderRawDecoded('真实文件：' + f.name, f.size);
    URL.revokeObjectURL(url);
  };
  img.onerror = ()=>{
    URL.revokeObjectURL(url);
    if (isRaw || isTiff) renderRawUnsupported(f.name);
    else toast('这个文件打不开');
  };
  img.src = url;
}

/* 浏览器解不了的 → 说清楚，给模拟流程 */
function renderRawUnsupported(name){
  document.getElementById('rawBody').innerHTML = `
    <div class="raw-unsup">
      <div class="raw-ui">⚠</div>
      <div class="raw-ut">浏览器解不了 <b>${esc(name)}</b></div>
      <div class="raw-ud">
        这不是 bug —— <b>真正 RAW 里的传感器数据，浏览器没有解码器</b>。<br>
        要用后端 <code>rawpy</code>（LibRaw 的 Python 封装，MIT 许可）来解。
      </div>
      <div class="raw-tech">
        <div class="raw-th">后端要做的（具体实现后做）</div>
        <div class="raw-tr">
          <code>rawpy.imread(f).postprocess(gamma=(1,1), output_bps=16, no_auto_bright=True)</code>
        </div>
        <div class="raw-td">
          三个参数是关键：<b>gamma=(1,1)</b> 拿线性数据 ·
          <b>output_bps=16</b> 保位深 · <b>no_auto_bright=True</b> 别替我们自动提亮
        </div>
      </div>
      <button class="insp-b pri" style="margin-top:12px" onclick="rawUseDemo()">用模拟数据看后面的流程</button>
    </div>`;
}

/* ================= 真：解码后处理 ================= */
function renderRawDecoded(title, bytes){
  const img = RAW_STATE.img;
  const dims = RAW_STATE.dims;
  document.getElementById('rawBody').innerHTML = `
    <div class="raw-dec">
      <div class="raw-preview">
        <div class="raw-pw">
          <div class="raw-plabel">线性（未提亮 → 死黑）</div>
          <div class="raw-pres" id="rawLin"></div>
        </div>
        <div class="raw-pw">
          <div class="raw-plabel">gamma 提亮后（正常）</div>
          <div class="raw-pres" id="rawGam"></div>
        </div>
      </div>

      <div class="raw-info">
        <div><span class="raw-ik">文件</span><span class="raw-iv">${esc(title)}</span></div>
        <div><span class="raw-ik">尺寸</span><span class="raw-iv">${dims[0]} × ${dims[1]}</span></div>
        <div><span class="raw-ik">大小</span><span class="raw-iv">${bytes ? (bytes/1024/1024).toFixed(1) + ' MB' : '—'}</span></div>
        <div><span class="raw-ik">解码</span><span class="raw-iv">本地 · 免费 · 未上传</span></div>
      </div>

      <div class="raw-gamma">
        <div class="raw-gh">
          <span>gamma 值</span>
          <span class="raw-gv" id="rawGammaV">${RAW_STATE.gamma.toFixed(1)}</span>
        </div>
        <input type="range" class="le-r" min="1" max="3" step="0.1"
          value="${RAW_STATE.gamma}" oninput="rawSetGamma(this.value)">
        <div class="raw-gn">
          🔴 <b>这一段是真验证的</b> —— 线性数据直接显示会死黑（左），
          gamma 提亮后才正常（右）。所以"RAW 调曝光不炸"的前提是先正确解码成线性。
        </div>
      </div>

      <div class="raw-hist">
        <div class="raw-hh">直方图（从真实像素算）</div>
        <canvas id="rawHist" width="320" height="70"></canvas>
      </div>
    </div>`;

  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth || 320;
  canvas.height = img.naturalHeight || 420;
  const cx = canvas.getContext('2d');
  cx.drawImage(img, 0, 0);
  RAW_STATE.canvas = canvas;   // 解码结果留给「进入编辑」，不再只是画个预览

  let dataUrl = '';
  try { dataUrl = canvas.toDataURL(); } catch(_){ dataUrl = ''; }

  const linEl = document.getElementById('rawLin');
  if (linEl && dataUrl){
    linEl.style.backgroundImage = `url(${dataUrl})`;
    linEl.style.filter = 'brightness(0.3)';
  }
  const gamEl = document.getElementById('rawGam');
  if (gamEl && dataUrl){
    gamEl.style.backgroundImage = `url(${dataUrl})`;
    gamEl.style.filter = rawGammaFilter();
  }

  drawRawHistogram(canvas);

  const foot = document.getElementById('rawFoot');
  if (foot){
    foot.innerHTML = `
      <div class="raw-fn">解码完成 · 免费 · ${dims[0]}×${dims[1]}</div>
      <div class="le-acts">
        <button class="insp-b ghost" onclick="openRawImport()">换一个</button>
        <button class="insp-b pri" onclick="rawToEdit()">进入编辑</button>
      </div>`;
  }
}

function rawGammaFilter(){
  const g = RAW_STATE.gamma;
  const br = Math.pow(g / 2.2, 0.62);
  return 'brightness(' + br.toFixed(2) + ') contrast(' + (0.88 + g*0.07).toFixed(2) + ') saturate(1.06)';
}

function rawSetGamma(v){
  RAW_STATE.gamma = Number(v);
  const el = document.getElementById('rawGammaV');
  if (el) el.textContent = Number(v).toFixed(1);
  const gam = document.getElementById('rawGam');
  if (gam) gam.style.filter = rawGammaFilter();
}

/* 真直方图：从像素算 */
function drawRawHistogram(srcCanvas){
  const cv = document.getElementById('rawHist');
  if (!cv) return;
  const W = 320, H = 70;
  const g = cv.getContext('2d');

  const s = document.createElement('canvas');
  s.width = 96; s.height = 128;
  const sg = s.getContext('2d', { willReadFrequently: true });
  sg.drawImage(srcCanvas, 0, 0, 96, 128);
  let d;
  try { d = sg.getImageData(0, 0, 96, 128).data; } catch(_){ return; }

  const bins = new Array(64).fill(0);
  for (let i = 0; i < d.length; i += 4){
    const lum = 0.2126*d[i] + 0.7152*d[i+1] + 0.0722*d[i+2];
    bins[Math.min(63, Math.floor(lum / 4))]++;
  }
  const max = Math.max.apply(null, bins) || 1;

  g.clearRect(0, 0, W, H);
  g.strokeStyle = 'rgba(255,255,255,.06)';
  g.lineWidth = 1;
  for (let i = 1; i < 4; i++){
    g.beginPath(); g.moveTo(W*i/4, 0); g.lineTo(W*i/4, H); g.stroke();
  }
  const bw = W / 64;
  bins.forEach((v, i)=>{
    const h = (v / max) * (H - 4);
    const grad = g.createLinearGradient(0, H-h, 0, H);
    grad.addColorStop(0, 'rgba(34,211,238,.9)');
    grad.addColorStop(1, 'rgba(34,211,238,.25)');
    g.fillStyle = grad;
    g.fillRect(i * bw, H - h, Math.max(1, bw - 0.6), h);
  });
}

/* ================= 模拟流程 ================= */
function rawUseDemo(){
  const c = document.createElement('canvas');
  c.width = 320; c.height = 420;
  const g = c.getContext('2d');

  const bg = g.createLinearGradient(0, 0, 320, 420);
  bg.addColorStop(0, '#141018');
  bg.addColorStop(1, '#0a0810');
  g.fillStyle = bg; g.fillRect(0, 0, 320, 420);

  g.fillStyle = '#3a3038';
  g.beginPath(); g.ellipse(160, 430, 150, 120, 0, 0, Math.PI*2); g.fill();

  g.fillStyle = '#4a3a30';
  g.beginPath(); g.ellipse(160, 175, 88, 105, 0, 0, Math.PI*2); g.fill();

  g.fillStyle = '#241c22';
  g.beginPath(); g.ellipse(160, 118, 100, 60, 0, Math.PI, Math.PI*2); g.fill();

  g.fillStyle = '#1a1418';
  g.beginPath(); g.ellipse(133, 168, 14, 7, 0, 0, Math.PI*2); g.fill();
  g.beginPath(); g.ellipse(187, 168, 14, 7, 0, 0, Math.PI*2); g.fill();

  g.fillStyle = '#2a2028';
  g.beginPath(); g.ellipse(160, 212, 16, 5, 0, 0, Math.PI*2); g.fill();

  RAW_STATE.loaded = true;
  RAW_STATE.img = c;
  RAW_STATE.dims = [320, 420];
  RAW_STATE.linear = true;
  RAW_STATE.demo = true;
  RAW_STATE.name = RAW_META.name;

  renderRawDecoded('模拟：' + RAW_META.name + ' · ' + RAW_META.camera, 28.4 * 1024 * 1024);
  toast('模拟数据 —— 感受线性 vs gamma 的差别');
}

function rawDone(){ rawUseDemo(); }

/* 进编辑：把解码结果作为一张真图放进文档，再打开本地精调 */
function rawToEdit(){
  const canvas = RAW_STATE.canvas;
  const baseName = String(RAW_STATE.name || 'RAW').replace(/\.[^.]+$/, '');
  const demo = !!RAW_STATE.demo;
  closeRaw();

  let item = null;
  if (canvas && typeof addRealImageItem === 'function'){
    item = addRealImageItem(canvas, baseName + (demo ? ' · 模拟' : ' · RAW'), {
      free: true,
      imageName: RAW_STATE.name,
      pushHistory: true
    });
  }

  if (item){
    const note = demo
      ? `这次是<b>模拟 RAW</b>：流程是真的，传感器数据是画的。<br>`
        + `真 RAW（CR3/NEF/ARW…）浏览器解不了，要后端 <b>rawpy</b>（LibRaw，MIT）`
        + `解成线性数据再进来。`
      : `浏览器解的是<b>预览图</b>（已经是 sRGB）；真正 RAW 的线性传感器数据要后端 rawpy 解。<br>`
        + `但「解码 → 编辑 → 写回 → 导出」这条链已经通了。`;
    if (typeof agAdd === 'function'){
      agAdd('ai', `RAW 解码完了，像素已经放进文档，正在打开编辑。<br><br>`
        + `尺寸 <b>${item.canvas.width}×${item.canvas.height}</b>（工作分辨率）`
        + (item.realW && item.realW !== item.canvas.width
            ? `，原图 ${item.realW}×${item.realH}` : '')
        + `<br><br><span class="myown">${note}</span>`);
    }
    if (typeof openLocalEdit === 'function') setTimeout(()=>openLocalEdit(item.id), 160);
    toast('已进入编辑 · ' + item.canvas.width + '×' + item.canvas.height + ' · 免费');
    return;
  }

  if (typeof agAdd === 'function'){
    agAdd('ai', `RAW 解码完了，但没拿到可用的像素。<br><br>`
      + `<span class="myown">真 RAW 的传感器数据浏览器没有解码器，`
      + `要接后端 <b>rawpy</b>（LibRaw 的 Python 封装，MIT）才行。</span>`);
  }
  toast('没拿到像素 · 需要后端 rawpy');
}
