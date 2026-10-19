/* 14-raw.js - split from canvas_unified_v14.html (lines 3509-3661) */
/* ================= RAW 导入（本地解码，零成本）=================
   为什么 RAW 值得做：相机原片是 12-14bit 传感器数据，
   转成 JPEG 只剩 8bit —— 调曝光就炸。
   我们要的是：rawpy 解码成 16bit 线性，再进本地精调（曲线/曝光才真的有效）。
*/

const RAW_DEMO = {
  name: 'IMG_4821.CR3',
  camera: 'Canon EOS R6 Mark II',
  rawBits: 14,
  sizeMB: 28.4,
  dim: '6000 × 4000',
  stages: [
    { t:'读 RAW 头', d:'识别相机型号与传感器配置', ms:400 },
    { t:'抽内嵌缩略图', d:'相机里存的 JPEG 预览 · 先让你看见', ms:600 },
    { t:'解码拜耳阵列', d:'6000×4000 · 每像素只有一个颜色', ms:1600 },
    { t:'去马赛克', d:'还原每像素 RGB', ms:1400 },
    { t:'转线性 16bit', d:'gamma=(1,1) · output_bps=16', ms:900 }
  ]
};

function openRawImport(){
  document.getElementById('overlayHost').innerHTML = `
    <div class="raw" onclick="if(event.target.classList.contains('raww'))closeRaw()">
      <div class="raww">
        <div class="inp-hd">
          <div class="inp-t">导入 RAW</div>
          <div class="inp-sub">相机原片 · 本地解码 · 不花钱也不上传原始文件</div>
          <button class="inp-x" onclick="closeRaw()">✕</button>
        </div>

        <div class="raw-body" id="rawBody">
          <div class="raw-pick">
            <div class="raw-drop" onclick="rawUseDemo()">
              <div class="raw-ic">▤</div>
              <div class="raw-dt">点这里模拟导入一个 RAW</div>
              <div class="raw-ds">${RAW_DEMO.name} · ${RAW_DEMO.camera}</div>
              <div class="raw-df">支持 .CR2 .CR3 .NEF .ARW .RAF .DNG</div>
            </div>

            <div class="raw-why">
              <div class="raw-wh">为什么 RAW 值得单独做</div>
              <div class="raw-wr">
                <span class="raw-wk">相机传感器</span>
                <span class="raw-wv">${RAW_DEMO.rawBits} bit · 每像素只有 1 个颜色</span>
              </div>
              <div class="raw-wr">
                <span class="raw-wk">直出 JPEG</span>
                <span class="raw-wv">8 bit · 已经压掉了高光暗部</span>
              </div>
              <div class="raw-wr hl">
                <span class="raw-wk">我们要的</span>
                <span class="raw-wv">16 bit <b>线性</b> · 调曝光才不炸</span>
              </div>
              <div class="raw-wn">
                🔴 拿 8bit JPEG 调曝光，就是在已经压扁的数据上二次损失 ——
                高光一抹白就回不来了。RAW 里那些数据还在。
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>`;
}

function closeRaw(){ document.getElementById('overlayHost').innerHTML = ''; }

/* 演示：走一遍解码流程 */
function rawUseDemo(){
  const body = document.getElementById('rawBody');
  body.innerHTML = `
    <div class="raw-run">
      <div class="raw-thumb" id="rawThumb">
        <div class="raw-tph">缩略图</div>
        <div class="raw-tfig"></div>
      </div>
      <div class="raw-steps">
        <div class="raw-src">
          <span class="raw-sn">${RAW_DEMO.name}</span>
          <span class="raw-sc">${RAW_DEMO.camera} · ${RAW_DEMO.dim} · ${RAW_DEMO.sizeMB}MB</span>
        </div>
        <div id="rawSteps"></div>
        <div class="raw-bar"><div class="raw-fill" id="rawFill"></div></div>
        <div class="raw-note" id="rawNote">准备中…</div>
      </div>
    </div>`;

  const host = document.getElementById('rawSteps');
  const fill = document.getElementById('rawFill');
  const note = document.getElementById('rawNote');
  const thumb = document.getElementById('rawThumb');
  const total = RAW_DEMO.stages.reduce((a,b)=>a+b.ms,0);
  let done = 0;

  host.innerHTML = RAW_DEMO.stages.map((s,i)=>
    `<div class="raw-st" id="rawSt_${i}">
       <span class="raw-si" id="rawSi_${i}">○</span>
       <span class="raw-stt">${s.t}</span>
       <span class="raw-sd">${s.d}</span>
     </div>`).join('');

  RAW_DEMO.stages.forEach((s, i)=>{
    setTimeout(()=>{
      const el = document.getElementById('rawSi_' + i);
      if (el){ el.textContent = '✓'; el.classList.add('ok'); }
      // 第 2 步完成就能显示缩略图
      if (i === 1 && thumb){ thumb.classList.add('show'); }
      done += s.ms;
      fill.style.width = Math.round(done / total * 100) + '%';
      note.textContent = i === 1 ? '缩略图已出，你可以边看边等全质量' :
        (i === RAW_DEMO.stages.length-1 ? '完成' : '处理中…');
      if (i === RAW_DEMO.stages.length-1) rawDone();
    }, s.ms + (i > 0 ? RAW_DEMO.stages.slice(0,i).reduce((a,b)=>a+b.ms,0) : 0));
  });
}

function rawDone(){
  const body = document.getElementById('rawBody');
  body.insertAdjacentHTML('beforeend', `
    <div class="raw-done">
      <div class="raw-dh">解码完成</div>
      <div class="raw-grid">
        <div class="raw-gi"><span class="raw-gk">位深</span><span class="raw-gv ok">16 bit 线性</span></div>
        <div class="raw-gi"><span class="raw-gk">色彩空间</span><span class="raw-gv ok">Linear → sRGB 可切</span></div>
        <div class="raw-gi"><span class="raw-gk">尺寸</span><span class="raw-gv">${RAW_DEMO.dim}</span></div>
        <div class="raw-gi"><span class="raw-gk">花费</span><span class="raw-gv ok">0</span></div>
      </div>
      <div class="raw-dnote">
        🔴 <b>拿到 16bit 线性数据之后，曲线和曝光才是真的有效</b> ——
        这些调整都在没被压缩的数据上做，不是二次损失。
      </div>
      <div class="raw-dacts">
        <button class="insp-b ghost" onclick="closeRaw()">只要图，先放着</button>
        <button class="insp-b pri" onclick="rawToEdit()">直接进本地精调</button>
      </div>
    </div>`);
}

function rawToEdit(){
  closeRaw();
  // 造一条素材进画布
  const id = 'raw' + Date.now();
  DOC.items.unshift({
    id, name: RAW_DEMO.name.replace(/\.\w+$/,''),
    cls: 'warm', x: 60, y: 40, w: 150, h: 225,
    duration: 0, status: 'ok', raw: true
  });
  renderShots(); if (typeof renderFree === 'function') renderFree();
  setTimeout(()=>openLocalEdit(id), 200);
  toast('已导入 · 16bit 线性 · 花费 0');
}


