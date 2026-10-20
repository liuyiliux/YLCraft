/* 22-batch.js — 批量应用：选 N 镜 × 选预设 → 一次套
   🔴 我们原来只有"批量出图"（往外出），没有"批量改图"（往里收）。
      12 镜要统一色调，得一张一张手动改 —— 这是最不对称的地方。
*/

let BATCH_SEL = new Set();
let BATCH_PRESET = null;

/* 打开批量应用面板 */
function openBatchApply(presetId){
  BATCH_PRESET = presetId || (PRESETS[0] && PRESETS[0].id);
  BATCH_SEL = new Set();
  // 默认全选有问题的/已生成的
  const items = (typeof DOC !== 'undefined') ? DOC.items : [];
  items.forEach(s=>{ if (s.status === 'ok') BATCH_SEL.add(s.id); });
  renderBatchPane();
}

function closeBatchApply(){ document.getElementById('overlayHost').innerHTML = ''; }

function renderBatchPane(){
  const items = (typeof DOC !== 'undefined') ? DOC.items : [];
  const pre = PRESETS.find(p=>p.id===BATCH_PRESET);
  const selCount = BATCH_SEL.size;
  // 每张图套预设 = 本地运算 = 0 成本
  const cost = 0;

  document.getElementById('overlayHost').innerHTML = `
    <div class="ba" onclick="if(event.target.classList.contains('baw'))closeBatchApply()">
      <div class="baw">
        <div class="inp-hd">
          <div class="inp-t">批量应用</div>
          <div class="inp-sub">选一个预设 · 勾要套的镜头 · 一次改完</div>
          <button class="inp-x" onclick="closeBatchApply()">✕</button>
        </div>

        <div class="ba-body">
          <div class="ba-sec">选预设</div>
          <div class="ba-presets">
            ${PRESETS.map(p=>`
              <button class="ba-p ${p.id===BATCH_PRESET?'on':''}"
                onclick="BATCH_PRESET='${p.id}';renderBatchPane()">
                <span class="ba-pn">${esc(p.name)}</span>
                <span class="ba-pu">用过 ${p.used} 次</span>
              </button>`).join('')}
          </div>

          ${pre?`<div class="ba-desc">${describeParams(pre.params)}</div>`:''}

          <div class="ba-sec" style="margin-top:14px">
            选镜头
            <span class="ba-cnt">${selCount}/${items.length}</span>
            <span class="ba-selall">
              <button class="ba-mini" onclick="batchAll(true)">全选</button>
              <button class="ba-mini" onclick="batchAll(false)">全不选</button>
            </span>
          </div>
          <div class="ba-shots">
            ${items.map((s,i)=>{
              const on = BATCH_SEL.has(s.id);
              return `<div class="ba-shot ${on?'on':''} ${s.status!=='ok'?'dis':''}"
                onclick="${s.status==='ok'?`batchToggle('${s.id}')`:''}">
                <span class="ba-ck">${on?'✓':''}</span>
                <span class="ba-no">${String(i+1).padStart(2,'0')}</span>
                <span class="ba-nm">${esc(s.name||'—')}</span>
                <span class="ba-st">${s.status==='ok'?'可套':s.status==='err'?'失败':'待生成'}</span>
              </div>`;
            }).join('')}
          </div>

          <div class="ba-key">
            🔴 <b>批量套预设是本地运算</b> —— 不改画面内容、不动脸，
            只是给每张图挂上同一组调整参数。<b>免费，而且随时能单独改回去。</b>
          </div>
        </div>

        <div class="ba-foot">
          <div class="ba-cost">
            花费 <b class="le-zero">${cost}</b>
            <span class="ba-costn">本地参数应用 · 不走模型 · ${selCount} 张</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="closeBatchApply()">取消</button>
            <button class="insp-b pri" onclick="doBatchApply()" ${selCount?'':'disabled style="opacity:.4"'}>
              套到 ${selCount} 张
            </button>
          </div>
        </div>
      </div>
    </div>`;
}

function batchToggle(id){
  if (BATCH_SEL.has(id)) BATCH_SEL.delete(id);
  else BATCH_SEL.add(id);
  renderBatchPane();
}
function batchAll(on){
  const items = (typeof DOC !== 'undefined') ? DOC.items : [];
  BATCH_SEL = new Set();
  if (on) items.forEach(s=>{ if (s.status==='ok') BATCH_SEL.add(s.id); });
  renderBatchPane();
}

/* 执行批量应用
   🔴 批量套预设是本地运算（⚡0），不走门禁 —— 门禁只拦花钱的。
      免费操作还让人确认就是烦人。
*/
function doBatchApply(){
  const pre = PRESETS.find(p=>p.id===BATCH_PRESET);
  if (!pre){ toast('先选一个预设'); return; }
  const n = BATCH_SEL.size;
  if (!n){ toast('先勾要套的镜头'); return; }

  // 把预设挂到每张图的图层里（非破坏）
  if (typeof layersOf === 'function'){
    BATCH_SEL.forEach(sid=>{
      const layers = layersOf(sid);
      // 已经有调整层就覆盖参数，否则加一层
      const exist = layers.find(l=>l.type==='local' && l.fromPreset);
      if (exist){
        exist.params = JSON.parse(JSON.stringify(pre.params));
        exist.name = pre.name;
      } else {
        const l = makeLocalLayer();
        l.name = pre.name;
        l.fromPreset = pre.id;
        l.params = JSON.parse(JSON.stringify(pre.params));
        layers.push(l);
      }
    });
  }
  pre.used += n;
  closeBatchApply();
  if (typeof renderLayerPanel === 'function') renderLayerPanel();

  if (typeof agAdd === 'function'){
    agAdd('ai', `把「<b>${esc(pre.name)}</b>」套到了 <b>${n} 张</b>上，<b>没花钱</b>。<br><br>`
      + `${describeParams(pre.params)}<br><br>`
      + `<span class="myown">这只是给每张图挂了同一组参数 —— 画面内容没动、脸没动。`
      + `哪张觉得不合适，点开单独调就行，其他张不受影响。</span>`);
  }
  toast(`已套到 ${n} 张 · 免费`);
}
