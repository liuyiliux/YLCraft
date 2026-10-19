/* 12-inspect.js - split from canvas_unified_v14.html (lines 3033-3213) */
/* ================= 巡检（修正版）：按「本地能修」vs「要调模型」分 =================
   修正 2026-10-19：之前按「便宜/贵」分是错的 ——
   同一生图接口，改多改少一个价。真实分界是：
     本地像素运算 = 免费
     任何涉及「内容」的改动 = 调模型，且同价
*/

const INSPECT_FINDINGS = [
  /* ===== 本地能修（免费，纯像素运算） ===== */
  { id:'f1', shot:1, layer:'local',
    title:'色温偏冷',
    evidence:'5200K · 序列均值 6100K · 偏了 900K',
    why:'这是白平衡偏差，纯通道运算能修',
    fix:'白平衡 + 曲线', cost:0,
    note:'本地算，不动内容、不动脸',
    kind:'白平衡' },

  { id:'f2', shot:2, layer:'local',
    title:'曝光偏暗',
    evidence:'平均亮度 0.38 · 序列均值 0.46 · 约 -0.35EV',
    why:'线性域乘个系数就回来了',
    fix:'曝光补偿 + 提亮暗部', cost:0,
    note:'本地算，不动内容',
    kind:'曝光' },

  { id:'f3', shot:6, layer:'local',
    title:'对比度偏平',
    evidence:'直方图标准差 0.14 · 其余 0.19',
    why:'曲线拉一下 S 形就行',
    fix:'S 曲线', cost:0,
    note:'本地算',
    kind:'曲线' },

  /* ===== 要调模型（花钱，改多改少同价） ===== */
  { id:'f4', shot:4, layer:'model',
    title:'光照方向不一致',
    evidence:'第 4 镜光源在左 210° · 其余 5 镜都在右 35°',
    why:'🔴 本地只能调「整体亮暗/色温」，改不了「光从左来还是右来」。要改光的方向 = 重算画面 = 调模型',
    fix:'局部重绘（改光照方向）', cost:14,
    note:'会变脸，改完要重新校脸',
    sameAs:'和整图重画同价 —— 输出尺寸一样，API 就收一样的钱' },

  { id:'f5', shot:3, layer:'model',
    title:'人脸不一致',
    evidence:'与参考图相似度 0.62 · 阈值 0.85',
    why:'要改的是脸本身。局部改脸会越改越歪 —— 模型改脸时会连带改动五官比例',
    fix:'重画这一镜', cost:14,
    note:'会变脸，重画后必须重新校脸',
    forced:1 },

  { id:'f6', shot:5, layer:'model',
    title:'服装细节错',
    evidence:'风衣是单排扣 · 设定是双排扣 + 银扣',
    why:'要改的是主体本身，不是某一小块',
    fix:'重画这一镜', cost:14,
    note:'会变脸',
    forced:1 }
];

function openInspect(){
  const local = INSPECT_FINDINGS.filter(f=>f.layer==='local');
  const model = INSPECT_FINDINGS.filter(f=>f.layer==='model');
  const modelCost = model.reduce((a,b)=>a+b.cost,0);

  const cardOf = (f)=>{
    const isModel = f.layer==='model';
    return `<div class="insp-item ${isModel?'model':'local'}">
      <div class="insp-hd">
        <span class="insp-shot">第 ${f.shot} 镜</span>
        <span class="insp-title">${f.title}</span>
        ${f.forced?`<span class="insp-badge">必须重画</span>`:''}
        <span class="insp-layer ${isModel?'m':'l'}">${isModel?'调模型':'本地'}</span>
      </div>

      <div class="insp-evi">
        <span class="insp-evi-l">证据</span>
        <span class="insp-evi-v">${f.evidence}</span>
      </div>

      <div class="insp-why">${f.why}</div>

      <div class="insp-fix">
        <div class="insp-fix-row">
          <span class="insp-fix-t">${f.fix}</span>
          <span class="insp-fix-c ${isModel?'':'free'}">${isModel?'⚡'+f.cost:'免费'}</span>
        </div>
        <div class="insp-fix-note">${f.note}</div>
        ${f.sameAs?`<div class="insp-fix-alt">${f.sameAs}</div>`:''}
      </div>
    </div>`;
  };

  document.getElementById('overlayHost').innerHTML = `
    <div class="insp" onclick="if(event.target.classList.contains('inspw'))closeInspect()">
      <div class="inspw">
        <div class="inp-hd">
          <div class="inp-t">巡检结果</div>
          <div class="inp-sub">扫了 6 镜 · 发现 ${INSPECT_FINDINGS.length} 个问题</div>
          <button class="inp-x" onclick="closeInspect()">✕</button>
        </div>

        <div class="inp-cost">
          <div class="inp-cost-l">巡检本身花了多少钱</div>
          <div class="inp-cost-rows">
            <div class="icr"><span class="icr-k">L1 尺寸 / 格式 / 损坏</span><span class="icr-v ok">免费</span></div>
            <div class="icr"><span class="icr-k">L2 本地模型（人脸/CLIP/直方图）</span><span class="icr-v ok">免费</span></div>
            <div class="icr"><span class="icr-k">L3 语义判断</span><span class="icr-v">⚡2</span><span class="icr-d">只查 L1/L2 报警的 2 处</span></div>
          </div>
        </div>

        <div class="insp-body">
          <div class="insp-sec ok">
            <div class="insp-sec-h">
              <span class="insp-sec-t">本地就能修</span>
              <span class="insp-sec-n">${local.length} 个</span>
              <span class="insp-sec-c free">免费</span>
              <span class="insp-sec-w">不动内容</span>
            </div>
            <div class="insp-sec-d">
              这些是<b>色温 / 曝光 / 对比</b>这类纯像素运算 —— 本地算，不调模型，
              <b>脸一个像素都不动</b>，而且随时能调回来。
            </div>
            ${local.map(cardOf).join('')}
          </div>

          <div class="insp-sec danger">
            <div class="insp-sec-h">
              <span class="insp-sec-t">必须调模型</span>
              <span class="insp-sec-n">${model.length} 个</span>
              <span class="insp-sec-c">共 ⚡${modelCost}</span>
              <span class="insp-sec-w red">会变脸</span>
            </div>
            <div class="insp-sec-d">
              这些要改的是<b>画面内容本身</b>（光的方向、脸、衣服细节），
              本地算法改不了。🔴 <b>而且是「改多改少一个价」</b> —— 同一个接口，输出尺寸相同就收同样的钱。
            </div>
            ${model.map(cardOf).join('')}
          </div>
        </div>

        <div class="insp-foot">
          <div class="insp-sum">
            选着修：本地 <b style="color:var(--ok)">免费</b>
            <span class="insp-sum-n">· 调模型 ⚡${modelCost}</span>
          </div>
          <div class="insp-acts">
            <button class="insp-b ghost" onclick="closeInspect()">先不修</button>
            <button class="insp-b mid" onclick="inspDo('model','${modelCost}')">重画那 ${model.length} 镜 · ⚡${modelCost}</button>
            <button class="insp-b pri" onclick="inspDo('local',0)">先修本地那 ${local.length} 个 · 免费</button>
          </div>
        </div>
      </div>
    </div>`;
}

function closeInspect(){ document.getElementById('overlayHost').innerHTML = ''; }

function inspDo(which, cost){
  closeInspect();
  if (which === 'local'){
    agAdd('ai', `修好了 3 处，<b>没花钱</b>。<br><br>`
      + `· 第 1 镜 白平衡 5200K → 6100K<br>`
      + `· 第 2 镜 曝光 -0.35EV → 0<br>`
      + `· 第 6 镜 拉了个 S 曲线<br><br>`
      + `<span class="myown">这三处都是本地像素运算 —— 画面内容没动，脸没动，`
      + `而且随时能调回来（参数还在，不是烘焙进图里的）。</span><br><br>`
      + `还剩 <b>3 个</b>必须调模型：光照方向、人脸不一致、服装细节 —— 共 ⚡42。<br>`
      + `<span class="myown">这三个「改多改少都一个价」，所以要么一起改，要么先放着。</span>`);
    toast('本地修好 3 处 · 免费');
  } else {
    agAdd('ai', `重画了第 3、4、5 镜，花了 <b>⚡${cost}</b>。<br><br>`
      + `· 第 4 镜 光照方向 → 已对齐右 35°<br>`
      + `· 第 3 镜 人脸 → 重新生成<br>`
      + `· 第 5 镜 服装 → 双排扣银扣<br><br>`
      + `<span class="myown">这三镜的脸都是新的 —— 要重新校一次脸，确认和设定一致。`
      + `建议再跑一次巡检。</span>`);
    toast(`重画 3 镜 · ⚡${cost}`);
  }
}


