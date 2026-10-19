/* 03-groups.js - split from canvas_unified_v14.html (lines 571-696) */
/* ============ 用户打组（Blender 路线：Tab 进出） ============ */
let gMulti = new Set();     // Shift 多选
let GROUPS  = {};           // id -> { id, t, members, innerEdges, boundary, groupNode }
let insideGroup = null;     // 当前在哪个组内部

function makeGroup(){
  const ids = [...gMulti];
  if (ids.length < 2){ toast('至少选 2 个节点'); return; }
  const inSet = id => ids.includes(id);
  const members = GRAPH.nodes.filter(n=>inSet(n.id)).map(n=>({...n}));
  if (members.length < 2){ toast('选中的节点已经不在了'); return; }
  if (members.some(n=>n.group)){ toast('组里不能再套组'); return; }

  const gid = 'grp' + Date.now();
  // 内部边（成员之间）
  const innerEdges = GRAPH.edges.filter(e=>inSet(e.f) && inSet(e.t)).map(e=>({...e}));
  // 跨边界边：改接到组节点
  const boundary = GRAPH.edges.filter(e=>inSet(e.f) !== inSet(e.t))
    .map(e=>({ ...e, f: inSet(e.f) ? gid : e.f, t: inSet(e.t) ? gid : e.t }));

  const minX = Math.min(...members.map(n=>n.x));
  const minY = Math.min(...members.map(n=>n.y));
  const groupNode = {
    id: gid, x: minX, y: minY, w: 156,
    t: '我的流程', sub: members.length + ' 个节点 · Tab 进入',
    kind: 'any', st: 'ok', runnable: false,
    ins: ['text','image'], outs: ['image','video'],
    group: gid, userGroup: 1
  };
  GROUPS[gid] = { id: gid, t: '我的流程', members, innerEdges, boundary, groupNode };

  GRAPH.nodes = GRAPH.nodes.filter(n=>!inSet(n.id)).concat([{...groupNode, ins:[...groupNode.ins], outs:[...groupNode.outs]}]);
  GRAPH.edges = GRAPH.edges.filter(e=>!inSet(e.f) && !inSet(e.t)).concat(boundary.map(e=>({...e})));

  gMulti.clear();
  insideGroup = null;
  renderGraph(); renderGroupBar();
  toast('已打组「我的流程」· ' + members.length + ' 个节点 · 按 Tab 进入');
}

function enterGroup(gid){
  const g = GROUPS[gid];
  if (!g){ toast('这个组不存在'); return; }
  // 回写组节点位置不算，成员位置保持不变
  GRAPH.nodes = GRAPH.nodes.filter(n=>n.id!==gid);
  GRAPH.nodes = GRAPH.nodes.concat(g.members.map(m=>({...m, ins:[...(m.ins||[])], outs:[...(m.outs||[])]})));
  // 去掉指向组节点的边（boundary 已另存），加回内部边
  GRAPH.edges = GRAPH.edges.filter(e=>e.f!==gid && e.t!==gid)
    .concat(g.innerEdges.map(e=>({...e})));
  insideGroup = gid;
  gMulti.clear();
  renderGraph(); renderGroupBar();
  showHint('已进入组「' + g.t + '」· 按 <b>Tab</b> 退出', 6000);
}

function exitGroup(){
  const gid = insideGroup;
  if (!gid) return;
  const g = GROUPS[gid];
  if (!g){ insideGroup = null; return; }
  const memberIds = new Set(g.members.map(m=>m.id));
  // 回写位置/状态
  GRAPH.nodes.filter(n=>memberIds.has(n.id)).forEach(n=>{
    const m = g.members.find(x=>x.id===n.id);
    if (m){ m.x = n.x; m.y = n.y; m.st = n.st; m.sub = n.sub; }
  });
  // 存内部边（可能新增过）
  g.innerEdges = GRAPH.edges.filter(e=>memberIds.has(e.f) && memberIds.has(e.t)).map(e=>({...e}));
  // 收起来
  GRAPH.nodes = GRAPH.nodes.filter(n=>!memberIds.has(n.id))
    .concat([{...g.groupNode, sub: g.members.length + ' 个节点 · Tab 进入'}]);
  GRAPH.edges = GRAPH.edges.filter(e=>!memberIds.has(e.f) && !memberIds.has(e.t))
    .concat(g.boundary.map(e=>({...e})));
  insideGroup = null;
  renderGraph(); renderGroupBar();
  toast('已退出组「' + g.t + '」');
}

function toggleGroup(){
  if (insideGroup) exitGroup();
  else if (gSel && GROUPS[gSel]) enterGroup(gSel);
  else toast('先选中一个组节点，再按 Tab');
}

/* 顶栏：多选提示 + 打组按钮 */
function renderGroupBar(){
  const bar = document.getElementById('groupBar');
  if (!bar) return;
  if (gMulti.size >= 2 && !insideGroup){
    bar.classList.remove('hidden');
    bar.innerHTML = `<span class="gb-t">已选 <b>${gMulti.size}</b> 个节点</span>
      <button class="b solid" style="font-size:11px;padding:3px 10px" onclick="makeGroup()">打组</button>
      <button class="b" style="font-size:11px;padding:3px 8px" onclick="gMulti.clear();renderGraph();renderGroupBar()">取消</button>`;
  } else if (insideGroup){
    bar.classList.remove('hidden');
    bar.innerHTML = `<span class="gb-t">在组「${(GROUPS[insideGroup]||{}).t||''}」内部</span>
      <button class="b solid" style="font-size:11px;padding:3px 10px" onclick="exitGroup()">Tab 退出</button>`;
  } else if (gSel && GROUPS[gSel]){
    bar.classList.remove('hidden');
    bar.innerHTML = `<span class="gb-t">组「${GROUPS[gSel].t}」· Tab 进入</span>
      <button class="b" style="font-size:11px;padding:3px 10px" onclick="renameGroup('${gSel}')">重命名</button>
      <button class="b" style="font-size:11px;padding:3px 10px" onclick="saveGroupAsFlow('${gSel}')">存为流程</button>
      <button class="b solid" style="font-size:11px;padding:3px 10px" onclick="enterGroup('${gSel}')">进入</button>`;
  } else {
    bar.classList.add('hidden');
  }
}

function addNodeFromLib(k){
  const d = LIB_DEFS[k]; if(!d) return;
  const c = document.querySelector('.gcanvas');
  const g = document.getElementById('ginner');
  const sx = c ? c.scrollLeft : 0, sy = c ? c.scrollTop : 0;
  const id = 'n' + Date.now();
  GRAPH.nodes.push({
    id, x: sx + 200 + Math.random()*120, y: sy + 120 + Math.random()*100, w:140,
    t:d.t, sub: d.comp ? '点开是页面表单' : '新加的基础节点',
    kind:d.kind, st: d.comp ? 'todo' : 'ok',
    runnable: !!d.runnable, ins:d.ins, outs:d.outs,
    comp: d.comp ? 1 : 0, atomic: d.atomic ? 1 : 0, cap: d.cap || null
  });
  renderGraph();
  closeParams();
  toast(d.comp ? ('已加复杂节点「@' + d.t + '」· 点开是页面表单') : ('已加基础节点「' + d.t + '」'));
}

