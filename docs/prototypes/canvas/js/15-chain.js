/* 15-chain.js - split from canvas_unified_v14.html (lines 3662-3799) */
/* ================= 主链路串联：让这几块不是孤立面板 =================
   一句话 → 生成 → 本地调 → 巡检 → 修 → 再审
   关键：状态要流动。
      本地精调改了色温 → 巡检里"色温偏冷"变成已修
      巡检修了本地 3 项   → 面板里打勾，只剩调模型的
*/

/* 已修的巡检问题 */
let FIXED = new Set();
/* 本会话累计花费 */
let SPENT = 0;

/* ---- 包装：本地精调应用后，把相关巡检项标记已修 ---- */
const _leApply = leApply;
leApply = function(){
  const a = LOCAL_ADJ;
  const fixedNow = [];
  // 判断哪些巡检项被这次调整覆盖了
  INSPECT_FINDINGS.forEach(f=>{
    if (f.layer !== 'local' || FIXED.has(f.id)) return;
    if (f.kind === '白平衡' && Math.abs(a.temp - 6100) > 30){ FIXED.add(f.id); fixedNow.push(f); }
    if (f.kind === '曝光' && Math.abs(a.exposure) > 0.05){ FIXED.add(f.id); fixedNow.push(f); }
    if (f.kind === '曲线' && a.curve.some(p=>Math.abs(p[1]-p[0]) > 0.02)){ FIXED.add(f.id); fixedNow.push(f); }
  });
  _leApply();
  if (fixedNow.length){
    setTimeout(()=>{
      agAdd('ai', `顺带说：这次调整<b>把巡检里的 ${fixedNow.length} 个问题也修掉了</b> ——
        ${fixedNow.map(f=>`第 ${f.shot} 镜 ${f.title}`).join('、')}。<br><br>`
        + `<span class="myown">不用再单独点一次"修"，同一个参数解决了两件事。</span>`);
    }, 400);
  }
};

/* ---- 包装：巡检修本地后，标记已修并更新累计花费 ---- */
const _inspDo = inspDo;
inspDo = function(which, cost){
  if (which === 'local'){
    INSPECT_FINDINGS.filter(f=>f.layer==='local').forEach(f=>FIXED.add(f.id));
  } else {
    INSPECT_FINDINGS.filter(f=>f.layer==='model').forEach(f=>FIXED.add(f.id));
    SPENT += Number(cost) || 0;
  }
  _inspDo(which, cost);
  setTimeout(()=>renderSpend(), 100);
};

/* ---- 巡检面板：已修的打勾置灰 ---- */
const _openInspect = openInspect;
openInspect = function(){
  _openInspect();
  const items = document.querySelectorAll('.insp-item');
  const all = INSPECT_FINDINGS;
  items.forEach((el, i)=>{
    const f = all[i];
    if (f && FIXED.has(f.id)){
      el.classList.add('fixed');
      const hd = el.querySelector('.insp-hd');
      if (hd && !hd.querySelector('.insp-fixedbadge')){
        hd.insertAdjacentHTML('beforeend', '<span class="insp-fixedbadge">✓ 已修</span>');
      }
    }
  });
  // 全修完了就换成完成态
  const allLocalFixed = all.filter(f=>f.layer==='local').every(f=>FIXED.has(f.id));
  const allModelFixed = all.filter(f=>f.layer==='model').every(f=>FIXED.has(f.id));
  const foot = document.querySelector('.insp-foot');
  if (foot){
    if (allLocalFixed && allModelFixed){
      foot.innerHTML = `<div class="insp-sum okall">✅ 全部修完了 · 累计花费 <b>⚡${SPENT}</b>
        <span class="insp-sum-n">（本地 3 项免费 + 调模型 ⚡${SPENT}）</span></div>
        <div class="insp-acts"><button class="insp-b pri" onclick="closeInspect()">好</button></div>`;
    } else if (allLocalFixed){
      const m = all.filter(f=>f.layer==='model');
      foot.querySelector('.insp-acts').innerHTML =
        `<button class="insp-b ghost" onclick="closeInspect()">先不修</button>
         <button class="insp-b mid" onclick="inspDo('model','${m.reduce((a,b)=>a+b.cost,0)}')">重画那 ${m.length} 镜 · ⚡${m.reduce((a,b)=>a+b.cost,0)}</button>`;
      const sm = foot.querySelector('.insp-sum');
      if (sm) sm.innerHTML = `本地 <b style="color:var(--ok)">已全部修完</b>
        <span class="insp-sum-n">· 只剩调模型的 ${m.length} 个</span>`;
    }
  }
};

/* ---- 花费显示（顶栏） ---- */
function renderSpend(){
  let el = document.getElementById('spendChip');
  if (!el){
    const host = document.querySelector('.tools') || document.querySelector('.tr');
    if (!host) return;
    el = document.createElement('span');
    el.id = 'spendChip';
    el.className = 'spendchip';
    host.insertBefore(el, host.firstChild);
  }
  el.innerHTML = `<span class="sp-l">本次花费</span><span class="sp-v">⚡${SPENT}</span>
    <span class="sp-n">本地操作免费</span>`;
}

/* ---- 完整链路演示：一次点完 ---- */
function demoFullChain(){
  document.getElementById('agb').innerHTML = '';
  FIXED = new Set(); SPENT = 0; renderSpend();

  agAdd('ai', `<div class="chain-hero">
    <div class="chain-h">完整链路演示</div>
    <div class="chain-s">一句话 → 生成 → 本地调 → 巡检 → 修。<br>每一步都会告诉你「花不花钱」。</div>
    <div class="chain-steps">
      <span class="chain-st on">① 说一句话</span>
      <span class="chain-st">② 生成 6 镜</span>
      <span class="chain-st">③ 本地精调</span>
      <span class="chain-st">④ 巡检</span>
      <span class="chain-st">⑤ 修</span>
    </div>
  </div>`);

  setTimeout(()=>{
    runSearchDemo('生成一个最近出现的角色，叫霜见月');
  }, 700);
}

/* ---- 本地精调里显示"这一项在巡检里被标记了" ---- */
const _openLE = openLocalEdit;
openLocalEdit = function(id){
  _openLE(id);
  const pend = INSPECT_FINDINGS.filter(f=>f.layer==='local' && !FIXED.has(f.id));
  if (!pend.length) return;
  const panel = document.querySelector('.le-panel');
  if (!panel) return;
  panel.insertAdjacentHTML('afterbegin',
    `<div class="le-tip">
      💡 巡检发现 <b>${pend.length} 个</b>本地能修的问题：
      ${pend.map(f=>`第${f.shot}镜 ${f.title}`).join('、')}<br>
      <span class="le-tip2">调下面这些参数就能修，不用花钱。</span>
    </div>`);
};


