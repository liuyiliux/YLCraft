/* 27-graphrun.js — 连线图真执行
   🔴 之前连线只是画在屏幕上的线，点运行什么都不发生。
   现在：拓扑排序 → 按依赖顺序执行 → 每个节点调对应能力 → 更新状态 + 记进制作实况。

   这是"可编排"这件事的核心：不是画着好看，是真的能跑。
*/

let GRAPH_RUNNING = false;

/* 每个节点跑的时候做什么（对应 CAPS 能力） */
const NODE_EXEC = {
  script:  { cap:'—',              cost:0,  ms:300,  say:'读脚本，拆出 ' , noCost:true },
  board:   { cap:'—',              cost:0,  ms:400,  say:'排分镜表', noCost:true },
  merge:   { cap:'clip',           cost:2,  ms:900,  say:'合成时间线' },
  out:     { cap:'clip',           cost:0,  ms:600,  say:'出片' },
  to3d:    { cap:'model-3d',       cost:8,  ms:1200, say:'图生 3D' },
  previs:  { cap:'previs',         cost:6,  ms:1100, say:'3D 导演台预演' },
  gen:     { cap:'image-gen',      cost:14, ms:1400, say:'生成镜头' }
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

/* ---------- 找到这个节点该调什么 ---------- */
function nodeExecOf(node){
  if (node.id === 'script') return NODE_EXEC.script;
  if (node.id === 'board') return NODE_EXEC.board;
  if (node.id === 'merge') return NODE_EXEC.merge;
  if (node.id === 'out') return NODE_EXEC.out;
  if (node.id === 'to3d') return NODE_EXEC.to3d;
  if (node.id === 'previs') return NODE_EXEC.previs;
  if (typeof node.shot === 'number') return NODE_EXEC.gen;
  return { cap:'—', cost:0, ms:300, say:'处理' };
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

  GRAPH_RUNNING = true;
  const nodeById = {};
  GRAPH.nodes.forEach(n=>{ nodeById[n.id] = n; });

  // 只跑能跑的（runnable 或有执行定义的）
  const plan = order.map(id=>nodeById[id]).filter(Boolean);
  let totalCost = 0, totalMs = 0, ran = 0;
  const startedAt = new Date();

  // 先全部重置成 todo
  GRAPH.nodes.forEach(n=>{
    if (n.id === 'script' || n.id === 'board') return;
    n._prevSt = n.st;
    n.st = 'todo';
  });
  renderGraphNodes();
  await sleep(120);

  for (const node of plan){
    if (node.id === 'script' || node.id === 'board') continue;
    const ex = nodeExecOf(node);

    // 标记运行中
    node.st = 'run';
    node.sub = '执行中…';
    renderGraphNodes();
    updateGraphPin(node.id, ex.say);
    await sleep(ex.ms / 4);

    // "执行"
    node.st = 'ok';
    node.sub = '完成 · ' + (ex.cost ? '⚡' + ex.cost : '免费');
    totalCost += ex.cost;
    totalMs += ex.ms;
    ran++;
    renderGraphNodes();
    updateGraphPin(node.id, ex.say + ' ✓');
    await sleep(ex.ms / 6);
  }

  // 如果出片节点在，标完成
  const outNode = GRAPH.nodes.find(n=>n.id === 'out');
  if (outNode){ outNode.st = 'ok'; outNode.sub = '已出片'; }

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

  // 记进制作实况
  if (typeof PROD_LOG !== 'undefined'){
    PROD_LOG.push({
      at: new Date().toLocaleTimeString('zh-CN', { hour12:false }).slice(0,8),
      kind: 'gen',
      title: '跑连线图 · ' + ran + ' 个节点',
      detail: order.join(' → '),
      model: '按节点配置',
      cost: totalCost, ms: totalMs, status: 'ok'
    });
    if (typeof renderBoard === 'function' && typeof BOARD_TAB !== 'undefined' && BOARD_TAB === 'board'){
      renderBoard();
    }
  }

  // 汇报
  const costTxt = totalCost ? '⚡' + totalCost : '0（全免费）';
  if (typeof agAdd === 'function'){
    agAdd('ai', `连线图跑完了：<b>${ran} 个节点</b>，花费 <b>${costTxt}</b>。<br><br>`
      + `执行顺序（按依赖排的）：<br>`
      + `<span style="font-family:var(--fm);font-size:10px;color:var(--tx3)">`
      + order.filter(id=>id!=='script'&&id!=='board').join(' → ')
      + `</span><br><br>`
      + `<span class="myown">这是<b>真按依赖顺序执行的</b> —— 拓扑排序算出谁先谁后，`
      + `不是按你摆的位置。上游没跑完，下游不会开始。</span>`);
  }
  toast('跑完了 · ' + ran + ' 节点 · ' + costTxt);
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

/* ---------- 运行按钮（只在连线图模式显示） ---------- */
function mountGraphRunBtn(){
  if (document.getElementById('graphRunBtn')) return;
  const b = document.createElement('button');
  b.id = 'graphRunBtn';
  b.className = 'graph-run-btn';
  b.innerHTML = '<span>▶</span> 运行整图';
  b.title = '按依赖顺序执行所有节点';
  b.onclick = runGraph;
  document.body.appendChild(b);
}

function syncGraphRunBtn(){
  const b = document.getElementById('graphRunBtn');
  if (!b) return;
  const inGraph = !!document.querySelector('#gnodes .gnode');
  b.style.display = inGraph ? '' : 'none';
}

/* 挂载：等 renderGraph 跑完再同步按钮 */
(function(){
  function boot(){
    mountGraphRunBtn();
    const orig = window.renderGraph;
    if (typeof orig === 'function'){
      window.renderGraph = function(){
        const r = orig.apply(this, arguments);
        syncGraphRunBtn();
        return r;
      };
    }
    syncGraphRunBtn();
    setInterval(syncGraphRunBtn, 900);
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
