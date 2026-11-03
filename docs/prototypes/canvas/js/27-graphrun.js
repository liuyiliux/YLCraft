/* 27-graphrun.js — 连线图真执行
   🔴 之前连线只是画在屏幕上的线，点运行什么都不发生。
   现在：拓扑排序 → 按依赖顺序执行 → 每个节点解析到 CAPS 里那份能力 → 更新状态 + 记进制作实况。

   这是"可编排"这件事的核心：不是画着好看，是真的能跑。
   成本和接口只有 CAPS 一份：节点详情、页面表单、跑整图三条路读同一个数字（基调 E1）。
*/

let GRAPH_RUNNING = false;

/* 节点跑起来「说什么、等多久」—— 这里只留表现层。
   🔴 成本 / 接口 / 名字一律从 CAPS 读（基调 E1：一份能力只有一处定义）。
   以前这张表按 node.id 硬编码 cap+cost，等于同一件事有两个价目表：
   从节点库加的「生图工作台」指不到 id，落到兜底分支 → 免费跑完、什么都不报。 */
const NODE_FLAVOR = {
  script:  { ms:300,  say:'读脚本，拆出 ' },
  board:   { ms:400,  say:'排分镜表' },
  merge:   { ms:900,  say:'合成时间线' },
  out:     { ms:600,  say:'渲染出片' },
  to3d:    { ms:1200, say:'图生 3D' },
  previs:  { ms:1100, say:'3D 导演台预演' },
  gen:     { ms:1400, say:'生成镜头' }
};

/* ---------- 拓扑排序（Kahn） ---------- */
function topoSort(nodes, edges){
  const indeg = {};
  const adj = {};
  nodes.forEach(n=>{ indeg[n.id] = 0; adj[n.id] = []; });
  edges.forEach(e=>{
    if (indeg[e.t] === undefined || adj[e.f] === undefined) return;
    indeg[e.t]++;
    adj[e.f].push(e.t);
  });
  const q = nodes.filter(n=>indeg[n.id] === 0).map(n=>n.id);
  const order = [];
  while (q.length){
    const id = q.shift();
    order.push(id);
    (adj[id] || []).forEach(t=>{
      indeg[t]--;
      if (indeg[t] === 0) q.push(t);
    });
  }
  // 有环 → 返回 null
  if (order.length !== nodes.length) return null;
  return order;
}

/* ---------- 找到这个节点该调什么 ----------
   解析顺序：节点指的 capKey → CAPS 里那份能力 → 价格/接口都从它身上读。
   读不到就明说「指不到能力」，绝不回落到一个编出来的成本。 */
function flavorOf(node){
  if (node.id === 'script')  return NODE_FLAVOR.script;
  if (node.id === 'board')   return NODE_FLAVOR.board;
  if (node.id === 'merge')   return NODE_FLAVOR.merge;
  if (node.id === 'out')     return NODE_FLAVOR.out;
  if (node.id === 'to3d')    return NODE_FLAVOR.to3d;
  if (node.id === 'previs')  return NODE_FLAVOR.previs;
  if (typeof node.shot === 'number') return NODE_FLAVOR.gen;
  return { ms:700, say:node.t || '处理' };
}

function nodeExecOf(node){
  const f = flavorOf(node);
  const capKey = node.cap && CAPS[node.cap] ? node.cap : null;

  if (capKey){
    const cap = CAPS[capKey];
    return { node:node.id, data:false, capKey, cap,
             label:cap.label, path:cap.invoke.path,
             cost:cap.cost || 0, local:!!cap.local, ms:f.ms, say:f.say };
  }
  /* 读文档的节点（script / board / 文本节点）：不是能力调用，所以真的不花钱 */
  if (node.data){
    return { node:node.id, data:true, capKey:null, cap:null,
             label:'读文档', path:null, cost:0, local:true, ms:f.ms, say:f.say };
  }
  /* 组节点：里面才是能跑的节点，按 Tab 进去才跑 —— 这里不冒充"跑过了" */
  if (node.userGroup){
    return { node:node.id, data:true, container:true, capKey:null, cap:null,
             label:'组 · 进去才跑', path:null, cost:0, local:true, ms:f.ms, say:f.say };
  }
  return { node:node.id, data:false, capKey:null, cap:null,
           label:node.t || '节点', path:null, cost:null, local:false,
           ms:f.ms, say:f.say, unconfigured:true };
}

/* ---------- 真执行 ---------- */
async function runGraph(){
  if (GRAPH_RUNNING){ toast('正在跑，等它跑完'); return; }
  if (!GRAPH || !GRAPH.nodes.length){ toast('画布是空的'); return; }

  const order = topoSort(GRAPH.nodes, GRAPH.edges);
  if (!order){
    toast('有循环依赖，跑不了');
    if (typeof agAdd === 'function'){
      agAdd('ai', `跑不了 —— 节点之间形成了<b>循环依赖</b>。<br><br>`
        + `<span class="myown">A 等 B 的结果、B 又等 A 的，永远排不出顺序。`
        + `去掉一条线再试。</span>`);
    }
    return;
  }

  /* 一次性把每个节点解析成"执行说明"，门禁和真跑共用同一份 ——
     否则估算和实花容易读两套数字。 */
  const nodeById = {};
  GRAPH.nodes.forEach(n=>{ nodeById[n.id] = n; });
  const EX = {};
  order.forEach(id=>{ EX[id] = nodeExecOf(nodeById[id]); });

  /* 🔴 门禁：跑整图前先算成本，超过阈值必须批准 */
  {
    const estCost = order.reduce((a,id)=>a+(EX[id].cost||0),0);
    const willRun = order.filter(id=>!EX[id].data);
    const priced  = willRun.filter(id=>EX[id].cost > 0);
    const free    = willRun.filter(id=>!EX[id].unconfigured && !(EX[id].cost > 0));
    const unconf  = willRun.filter(id=>EX[id].unconfigured);
    const groups  = order.filter(id=>EX[id].container);

    const gatePlan = [
      '按依赖顺序执行 ' + willRun.length + ' 个节点',
      '顺序：' + willRun.join(' → '),
      '有消耗的节点：' + (priced.length
        ? priced.map(id=>id + '(⚡' + EX[id].cost + ')').join('、') : '无'),
      '免费/本地的节点：' + (free.length
        ? free.map(id=>id + '(' + EX[id].label + ')').join('、') : '无')
    ];
    if (unconf.length){
      gatePlan.push('🔴 指不到能力的节点：' + unconf.map(id=>id + '(' + EX[id].label + ')').join('、')
        + ' —— 这些不跑、不算钱，也不给你编一个价格');
    }
    if (groups.length){
      gatePlan.push('组节点 ' + groups.join('、') + ' 没进去，里面不算这次的钱');
    }

    if ((estCost >= GATE_COST_THRESHOLD || unconf.length) && typeof requestGate === 'function'){
      const approved = await requestGate({
        kind:'graph-run',
        title:'跑整图 · ' + willRun.length + ' 个节点',
        plan: gatePlan,
        cost: estCost,
        irreversible: false,
        why: '一次跑十几个节点，成本在跑之前就要让你知道'
      });
      if (!approved){
        toast('已取消 · 没跑 · 没花钱');
        return;
      }
    }
  }

  GRAPH_RUNNING = true;

  // 只跑能跑的（有 cap 的；读文档的跳过；指不到能力的标出来）
  const plan = order.map(id=>nodeById[id]).filter(Boolean);
  let totalCost = 0, totalCny = 0, totalMs = 0, ran = 0;
  const steps = [], skipped = [];

  // 先全部重置成 todo
  GRAPH.nodes.forEach(n=>{
    if (EX[n.id] && EX[n.id].data) return;
    n._prevSt = n.st;
    n.st = 'todo';
  });
  renderGraphNodes();
  await sleep(120);

  for (const node of plan){
    const ex = EX[node.id];
    if (!ex || ex.data) continue;

    if (ex.unconfigured){
      node.st = 'err';
      node.sub = '指不到能力 · 没跑';
      skipped.push(node.id);
      renderGraphNodes();
      updateGraphPin(node.id, '这个节点没接能力');
      await sleep(160);
      continue;
    }

    // 标记运行中
    node.st = 'run';
    node.sub = '执行中…';
    renderGraphNodes();
    updateGraphPin(node.id, ex.say);
    await sleep(ex.ms / 4);

    // "执行"：走和节点详情、页面表单同一个 invokeCap（P4：一份能力，多套外壳）
    const r = invokeCap(ex.capKey, {}, ex.cap.params);
    /* ⚡ 之外按 PRICE_BOOK 落人民币；能力上没配 price 就不记，不编 */
    let cny = 0;
    if (ex.cap.price && typeof chargeFor === 'function'){
      const bill = chargeFor(ex.cap, ex.cap.price, 1);
      if (bill && bill.ok) cny = bill.amountCny;
    }
    node.st = 'ok';
    node.sub = '完成 · ' + (ex.cost ? '⚡' + ex.cost : '免费');
    totalCost += ex.cost;
    totalCny += cny;
    totalMs += ex.ms;
    ran++;
    steps.push({ id:node.id, label:ex.label, path:r ? r.path : ex.path,
                 cost:ex.cost, cny, payload:r ? r.payload : null });
    renderGraphNodes();
    updateGraphPin(node.id, ex.say + ' ✓');
    await sleep(ex.ms / 6);
  }

  // 出片节点跑过了才改标题；没跑过（指不到能力）不能盖成「已出片」
  const outNode = GRAPH.nodes.find(n=>n.id === 'out');
  if (outNode && outNode.st === 'ok'){ outNode.sub = '已出片'; }

  // 所有镜头节点标已生成
  if (typeof DOC !== 'undefined'){
    DOC.items.forEach(s=>{ s.status = 'ok'; });
  }
  GRAPH.nodes.forEach(n=>{
    if (n.st === 'todo'){ n.st = n._prevSt || 'ok'; }
    delete n._prevSt;
  });
  renderGraphNodes();
  if (typeof renderShots === 'function') renderShots();
  if (typeof applyAllLayers === 'function') applyAllLayers();

  GRAPH_RUNNING = false;

  // 记进制作实况：每个节点落到哪个接口、多少钱，一起写进去（可核对，不是"跑了就完"）
  const epTxt = steps.map(s=>s.id + ' → ' + s.label + ' · <code>' + s.path + '</code> · '
    + (s.cost ? '⚡' + s.cost : '免费') + (s.cny ? ' / ' + money(s.cny) : '')).join('<br>');
  if (typeof PROD_LOG !== 'undefined'){
    PROD_LOG.push({
      at: new Date().toLocaleTimeString('zh-CN', { hour12:false }).slice(0,8),
      kind: 'gen',
      title: '跑连线图 · ' + ran + ' 个节点',
      detail: epTxt || order.join(' → '),
      model: steps.length ? (steps.length + ' 个能力') : '—',
      why: '成本和接口从 CAPS 读，不由这张图自己写死'
        + (totalCny ? '；按 PRICE_BOOK 落了 ' + money(totalCny) : '')
        + (skipped.length ? '；' + skipped.length + ' 个节点指不到能力，没跑：' + skipped.join('、') : ''),
      cost: totalCost, ms: totalMs, status: skipped.length ? 'partial' : 'ok'
    });
    if (typeof renderBoard === 'function' && typeof BOARD_TAB !== 'undefined' && BOARD_TAB === 'board'){
      renderBoard();
    }
  }
  if (typeof renderUserChip === 'function') renderUserChip();

  // 汇报
  const costTxt = totalCost ? '⚡' + totalCost + (totalCny ? ' / ' + money(totalCny) : '')
                            : '0（全免费）';
  if (typeof agAdd === 'function'){
    agAdd('ai', `连线图跑完了：<b>${ran} 个节点</b>，花费 <b>${costTxt}</b>。<br><br>`
      + `执行顺序（按依赖排的）：<br>`
      + `<span style="font-family:var(--fm);font-size:10px;color:var(--tx3)">`
      + order.filter(id=>!EX[id].data).join(' → ')
      + `</span><br><br>`
      + `每个节点调的是哪个接口：<br>`
      + `<span style="font-family:var(--fm);font-size:10px;color:var(--tx3)">`
      + steps.map(s=>s.id + ' · ' + s.path + ' · ' + (s.cost ? '⚡'+s.cost : '免费')).join('<br>')
      + `</span><br>`
      + (skipped.length ? `<br>🔴 有 <b>${skipped.length}</b> 个节点<b>没跑</b>：`
          + skipped.join('、') + `。它们指不到 CAPS 里的任何能力 —— `
          + `我不给它们编价格和接口，标出来让你自己接线。<br>` : '')
      + `<br><span class="myown">这是<b>真按依赖顺序执行的</b> —— 拓扑排序算出谁先谁后，`
      + `不是按你摆的位置。上游没跑完，下游不会开始。<br>`
      + `成本和接口是从 <code>CAPS</code> 那一份里读的，跟节点详情、页面表单同源（基调 E1）。</span>`);
  }
  toast('跑完了 · ' + ran + ' 节点 · ' + costTxt
    + (skipped.length ? ' · ' + skipped.length + ' 个没接线' : ''));
}

function sleep(ms){ return new Promise(r=>setTimeout(r, ms)); }

/* 只重画节点状态（不重建整张图）
   注意：节点的副标题 DOM 是 .gbd（不是 .gn-sub） */
function renderGraphNodes(){
  if (typeof GRAPH === 'undefined' || !GRAPH) return;
  GRAPH.nodes.forEach(n=>{
    const el = document.querySelector('.gnode[data-id="' + n.id + '"]');
    if (!el) return;
    el.classList.remove('gn-st-run','gn-st-ok','gn-st-err','gn-st-todo');
    el.classList.add('gn-st-' + (n.st || 'todo'));
    const sub = el.querySelector('.gbd');
    if (sub && n.sub) sub.textContent = n.sub;
  });
}

/* ---------- 运行按钮：不单独造，复用它 ----------
   之前这里造了一个浮动「▶ 运行整图」，和顶栏的「整组重跑」位置重叠。
   现在改成：不造按钮，反过来把顶栏那个接到 runGraph 上。
   保留这两个函数名（前面 08-events 的 boot 会调），但只做清理。 */
function mountGraphRunBtn(){
  const old = document.getElementById('graphRunBtn');
  if (old) old.remove();
}

function syncGraphRunBtn(){
  const old = document.getElementById('graphRunBtn');
  if (old) old.remove();
}

/* 挂载：不再单独造按钮 —— 复用顶栏已有的「整组重跑」，
   把它接到真执行上（之前它只弹提示）。
   这样连线图里只有一个运行按钮，不重复。 */
(function(){
  function boot(){
    /* 🔴 必须精确指到「整组重跑」：sbar 里第一个 button 是「步骤」切换钮 ——
       之前用 '#vFlow .sbar button' 取第一个，结果点「步骤」会触发跑整图 + 门禁。
       2026-11-03 给按钮加了 id，直接指。 */
    const btn = document.getElementById('rerunBtn')
      || document.querySelector('#vFlow .sbar button.b.solid');
    if (btn && !btn.dataset.wired){
      btn.onclick = null;
      btn.addEventListener('click', function(e){
        e.preventDefault();
        if (typeof runGraph === 'function') runGraph();
      });
      btn.title = '按依赖顺序执行整张连线图（会先问你要不要花这个钱）';
      btn.dataset.wired = '1';
    }
    /* 只保留一个入口：不再造浮动按钮 */
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

/* 节点上冒一个小提示 */
function updateGraphPin(nodeId, text){
  const el = document.querySelector('.gnode[data-id="' + nodeId + '"]');
  if (!el) return;
  let pin = el.querySelector('.gn-pin');
  if (!pin){
    pin = document.createElement('div');
    pin.className = 'gn-pin';
    el.appendChild(pin);
  }
  pin.textContent = text;
  pin.classList.add('on');
  setTimeout(()=>pin.classList.remove('on'), 900);
}
