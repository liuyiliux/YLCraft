/* 05-account.js - split from canvas_unified_v14.html (lines 853-1277) */
/* ================= 用户维度 · 画布隔离 · 积分按配置算 =================
   三条规则（来自实测代码 + 用户要求）：
   ① 画布必须带 owner。现在 `CanvasDocument` 只有 project_id，没有 owner —— 缺口。
   ② 画布隔离：别人看不到我的画布；同一份 JSON 不能被两个用户共享指针。
   ③ 积分 = 配置模型的实际花费。自用阶段没有"套餐额度"，只有"这次花了多少"。
*/

/* --------- 用户 --------- */
const USERS = [
  { id:'u-mei',  n:'我（梅）',  av:'梅', color:'#22d3ee' },
  { id:'u-lin',  n:'林设计',    av:'林', color:'#a78bfa' },
  { id:'u-zhao', n:'赵剪辑',    av:'赵', color:'#fbbf24' }
];
let currentUser = 'u-mei';

function me(){ return USERS.find(u=>u.id===currentUser); }

/* --------- 画布（带 owner） --------- */
const CANVASES = {
  'cv-001': { id:'cv-001', owner:'u-mei',  project:'我的短剧 / 第 3 集', title:'短剧 · 第 3 集',
              updated:'2 分钟前', nodes:12, tplRef:{id:'drama', ver:3},   visibility:'private' },
  'cv-002': { id:'cv-002', owner:'u-mei',  project:'Cos 精修',          title:'Cos 图 · 蕾姆',
              updated:'昨天',     nodes:3,  tplRef:{id:'coser', ver:2},   visibility:'private' },
  'cv-003': { id:'cv-003', owner:'u-lin',  project:'电商主图',           title:'618 主图',
              updated:'1 小时前', nodes:3,  tplRef:{id:'ecom', ver:1},    visibility:'private' },
  'cv-004': { id:'cv-004', owner:'u-lin',  project:'团队共享',           title:'品牌视觉统一',
              updated:'3 天前',   nodes:8,  tplRef:null,                   visibility:'team' },
  'cv-005': { id:'cv-005', owner:'u-zhao', project:'短剧 · 第 2 集',      title:'短剧 · 第 2 集',
              updated:'5 小时前', nodes:14, tplRef:{id:'drama', ver:4},    visibility:'private' }
};
let currentCanvas = 'cv-001';

/* 隔离规则：只看得到自己的 + 团队可见的 */
function visibleCanvases(){
  return Object.values(CANVASES).filter(c =>
    c.owner === currentUser || c.visibility === 'team'
  );
}
function mine(){ return Object.values(CANVASES).filter(c=>c.owner===currentUser); }
function canOpen(cv){
  if (!cv) return false;
  return cv.owner === currentUser || cv.visibility === 'team';
}
function canEdit(cv){
  if (!cv) return false;
  return cv.owner === currentUser;   // 团队可见但别人不能改
}

/* --------- 积分：只和配置模型的费用有关（自用阶段） --------- */
const PRICE_BOOK = {
  'gpt-image-2':  { n:'GPT Image 2',     per:'张', cny:1.40 },
  'nanobanana':   { n:'NanoBanana',      per:'张', cny:0.30 },
  'tripo-sr':     { n:'TripoSR',         per:'次', cny:0.00, note:'本地跑，只吃电费' },
  'local-op':     { n:'本地处理',         per:'次', cny:0.00, note:'不调模型' }
};
let spendLog = [];   // { at, item, model, amountCny }

function cnyOf(item){
  const p = PRICE_BOOK[item.model];
  return p ? p.cny * (item.qty || 1) : 0;
}
function spendToday(){
  return spendLog.reduce((a,x)=>a+x.amountCny, 0);
}

/* 扣费 = 按配置算；没配置就 0，不瞎写 */
function chargeFor(cap, model, qty){
  const p = PRICE_BOOK[model];
  if (!p) return { ok:false, reason:'模型没有配价格', amountCny:0 };
  const amount = p.cny * (qty||1);
  spendLog.push({ at:Date.now(), item:cap.label, model:p.n, amountCny:amount, qty:qty||1 });
  return { ok:true, amountCny:amount, model:p.n, unit:p.per };
}

function money(v){
  if (v === 0) return '¥0';
  if (v < 0.01) return '¥' + v.toFixed(4);
  return '¥' + v.toFixed(2);
}

/* 节点/技能 → 能力 的映射（这就是"加新用途=加配置"） */
function capKeyOfNode(n){
  if (!n) return null;
  if (n.cap && CAPS[n.cap]) return n.cap;
  if (n.pageKey && CAPS[n.pageKey]) return n.pageKey;
  return null;
}
function capOfNode(n){
  const k = capKeyOfNode(n);
  return k ? CAPS[k] : null;
}

/* 模拟一次 invoke：返回可验证的产物 */
function invokeCap(capKey, inputs, params){
  const cap = CAPS[capKey];
  if (!cap) return null;
  return {
    ok:true,
    cap: capKey,
    path: cap.invoke.path,
    payload: cap.map(inputs||{}, params||cap.params),
    assets: [{ id:'asset_' + Date.now(), kind: capKey.startsWith('model')?'model':'image' }],
    cost: cap.cost,
    evidence: cap.local ? '本地处理 · 0 成本' : ('调用 ' + cap.invoke.path)
  };
}

/* --------- 用户 / 画布隔离：UI --------- */

function openUserMenu(){
  const u = me();
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="umenu">
      <div class="umh">当前登录</div>
      <div class="umcur">
        <span class="avt" style="background:${u.color}">${u.av}</span>
        <div><div class="umn">${u.n}</div>
          <div class="ums">${mine().length} 块画布 · 今天花了 ${money(spendToday())}</div></div>
      </div>
      <div class="umh" style="margin-top:12px">切换用户（演示隔离）</div>
      ${USERS.map(x=>`
        <div class="umitem ${x.id===currentUser?'on':''}" onclick="switchUser('${x.id}')">
          <span class="avt sm" style="background:${x.color}">${x.av}</span>
          <span>${x.n}</span>
          <span class="umc">${Object.values(CANVASES).filter(c=>c.owner===x.id).length} 块</span>
        </div>`).join('')}
      <div class="umnote">切换后画布列表会变 —— <b>别人的私有画布你看不到</b>。</div>
      <div class="umfoot"><button class="b" onclick="closeOverlay()">关闭</button></div>
    </div></div>`;
}

function switchUser(uid){
  currentUser = uid;
  // 🔴 切了用户，当前画布必须重选（不能留着一个不属于你的）
  const vis = visibleCanvases();
  currentCanvas = vis.length ? vis[0].id : null;
  GROUPS = {}; gMulti.clear(); insideGroup = null; gSel = null;
  DOC.items = []; buildGraph(false);
  closeOverlay();
  renderUserChip(); renderTplRefBar();
  openCanvasList();
  toast('已切换为「' + me().n + '」· 现在只剩你的画布');
}

function renderUserChip(){
  const el = document.getElementById('userChip');
  if (!el) return;
  const u = me();
  el.innerHTML = `<span class="avt xs" style="background:${u.color}">${u.av}</span>
    <span class="uname">${u.n}</span>
    <span class="ucost" title="今天花了多少">${money(spendToday())}</span>`;
}

/* --------- 画布列表（隔离后的） --------- */
function openCanvasList(){
  const rows = visibleCanvases();
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="cvl">
      <div class="th2"><div class="t">我的画布</div>
        <div class="s">只显示 <b>${me().n}</b> 的和团队共享的，别人的私有画布看不到</div></div>
      <div class="cvbody">
        ${rows.map(c=>{
          const owner = USERS.find(u=>u.id===c.owner);
          const isMine = c.owner === currentUser;
          return `<div class="cvrow ${c.id===currentCanvas?'on':''}" onclick="openCanvas('${c.id}')">
            <span class="avt sm" style="background:${owner.color}">${owner.av}</span>
            <div class="cvi">
              <div class="cvn">${c.title}
                ${isMine?'':'<span class="cvtag">团队共享 · 只读</span>'}</div>
              <div class="cvs">${c.project} · ${c.nodes} 个节点 · ${c.updated}</div>
            </div>
            ${c.tplRef?`<span class="cvt">模板 v${c.tplRef.ver}</span>`:''}
          </div>`;
        }).join('')}
      </div>
      <div class="cvfoot">
        <button class="b" onclick="closeOverlay()">关闭</button>
      </div>
    </div></div>`;
}

function openCanvas(id){
  const cv = CANVASES[id];
  if (!cv){ toast('画布不存在'); return; }
  if (!canOpen(cv)){ toast('这是别人的私有画布'); return; }
  currentCanvas = id;
  GROUPS = {}; gMulti.clear(); insideGroup = null; gSel = null;
  if (cv.tplRef){ currentTplRef = { id:cv.tplRef.id, ver:cv.tplRef.ver }; }
  else currentTplRef = null;
  // 演示：按节点数造一份内容
  demoFill(cv.project.includes('短剧') ? 'script' : 'upload',
           Math.min(cv.nodes, 12));
  closeOverlay();
  renderTplRefBar(); renderUserChip(); renderCanvasName();
  toast((canEdit(cv) ? '打开：' : '以只读打开：') + cv.title);
}

function renderCanvasName(){
  const el = document.getElementById('canvasName');
  if (!el) return;
  const cv = CANVASES[currentCanvas];
  el.textContent = cv ? cv.project : '未命名';
}

/* --------- P6：我的流程要存参数值 --------- */
/* 之前只存了节点结构，复用出来全是空壳。现在把节点上的参数一起存。 */
function nodeParamsOf(n){
  // 节点上的可存参数：内联参数 + 状态
  return {
    inline: n.inlineParams ? JSON.parse(JSON.stringify(n.inlineParams)) : null,
    cap: n.cap || null,
    kind: n.kind, ins: [...(n.ins||[])], outs: [...(n.outs||[])],
    st: n.st, sub: n.sub
  };
}

function restoreNodeParams(m, saved){
  const p = (saved && saved[m.id]) || null;
  if (!p) return m;
  const out = { ...m };
  if (p.inline) out.inlineParams = p.inline;
  if (p.cap) out.cap = p.cap;
  if (p.st) out.st = p.st;
  return out;
}

/* --------- P2：打开完整页面（Houdini "解锁"） --------- */
function openPage(capKey){
  const cap = CAPS[capKey];
  if (!cap){ toast('这个节点没有对应页面'); return; }
  if (!cap.page){
    toast(cap.label + ' 是本地处理，没有独立页面（走 ' + cap.invoke.path + '）');
    return;
  }
  // 原型的"页面"用一张示意卡片代替，真实现是 navigate(cap.page + query)
  const q = encodeURIComponent(JSON.stringify(cap.params));
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="pgv">
      <div class="pgv-top">
        <span class="pgv-dot" style="background:#f87171"></span>
        <span class="pgv-dot" style="background:#fbbf24"></span>
        <span class="pgv-dot" style="background:#34d399"></span>
        <span class="pgv-url">${cap.page}?params=${cap.params ? '…' : ''}</span>
        <button class="b" style="margin-left:auto;font-size:11px;padding:3px 9px" onclick="closeOverlay()">返回画布 ←</button>
      </div>
      <div class="pgv-body">
        <div class="pgv-h">这里是完整页面</div>
        <div class="pgv-sub">${cap.label} 的全部参数都在这儿。<b>画布那边只露 3 个常用参数</b>，其余的来这改。</div>
        <div class="pgv-kv"><span>接口</span><code>${cap.invoke.method} ${cap.invoke.path}</code></div>
        <div class="pgv-kv"><span>当前参数</span><code>${escapeHtml(JSON.stringify(cap.params))}</code></div>
        <div class="pgv-kv"><span>回传</span><code>改完点「返回画布」→ 参数与产物回填到节点</code></div>
        <div class="pgv-note">
          🔴 真实实现是 <code>navigate('${cap.page}')</code>，
          页面走自己的 UI，<b>画布不知道它内部怎么做的</b>（这是基调 E1：页面与节点是兄弟）。
        </div>
      </div>
    </div></div>`;
}
function escapeHtml(s){ return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

/* --------- P3：组重命名 + 保存复用 --------- */
function renameGroup(gid){
  const g = GROUPS[gid];
  if (!g){ toast('没有选中组'); return; }
  const cur = g.t;
  const name = prompt('给这个组起个名字', cur);
  if (name === null) return;
  const v = String(name).trim();
  if (!v){ toast('名字不能为空'); return; }
  g.t = v;
  g.groupNode.t = v;
  const live = GRAPH.nodes.find(n=>n.id===gid);
  if (live){ live.t = v; }
  renderGraph(); renderGroupBar();
  toast('已重命名为「' + v + '」');
}

/* 把组存成「我的流程」模板，之后能从节点库拖出来复用 */
const MY_FLOWS = [];
function saveGroupAsFlow(gid){
  const g = GROUPS[gid];
  if (!g){ toast('没有选中组'); return; }
  const name = g.t === '我的流程' ? prompt('给这个流程起个名字', '我的流程 ' + (MY_FLOWS.length+1)) : g.t;
  if (name === null) return;
  const v = String(name).trim();
  if (!v){ toast('名字不能为空'); return; }
  const exist = MY_FLOWS.findIndex(f=>f.n === v);
  const item = { id:'flow'+Date.now(), n:v, nodes:g.members.length, edges:g.innerEdges.length,
                 members: g.members.map(m=>({...m})), innerEdges: g.innerEdges.map(e=>({...e})),
                 params: Object.fromEntries(g.members.map(m=>[m.id, nodeParamsOf(m)])),  // 🔴 P6：连参数一起存
                 owner: currentUser };
  if (exist >= 0) MY_FLOWS[exist] = item; else MY_FLOWS.push(item);
  renderMyFlows();
  toast('已存为流程「' + v + '」· 可在节点库拖出来复用');
}

function renderMyFlows(){
  const host = document.getElementById('myFlows');
  if (!host) return;
  if (!MY_FLOWS.length){ host.innerHTML = ''; host.classList.add('hidden'); return; }
  host.classList.remove('hidden');
  host.innerHTML = `<div class="nlg">我的流程 <span class="nlc">${MY_FLOWS.length}</span></div>`
    + MY_FLOWS.map(f=>`<div class="nli comp" onclick="useMyFlow('${f.id}')">
        <span class="nldot" style="background:#fbbf24"></span>${escapeHtml(f.n)}
        <span class="nlcnt">${f.nodes}</span></div>`).join('');
}

/* 从「我的流程」加回画布：整组作为一个可展开的组节点 */
function useMyFlow(fid){
  const f = MY_FLOWS.find(x=>x.id===fid);
  if (!f){ toast('流程已不存在'); return; }
  const c = document.querySelector('.gcanvas');
  const sx = c ? c.scrollLeft : 0, sy = c ? c.scrollTop : 0;
  const gid = 'grp' + Date.now();
  const groupNode = {
    id: gid, x: sx + 180, y: sy + 140, w: 156,
    t: f.n, sub: f.nodes + ' 个节点 · Tab 进入',
    kind:'any', st:'ok',
    ins:['text','image'], outs:['image','video'],
    group: gid, userGroup: 1
  };
  // 成员偏移放到组节点附近
  const minX = Math.min(...f.members.map(m=>m.x));
  const minY = Math.min(...f.members.map(m=>m.y));
  GROUPS[gid] = {
    id:gid, t:f.n,
    members: f.members.map(m=>restoreNodeParams({...m, x: groupNode.x + (m.x-minX), y: groupNode.y + (m.y-minY)}, f.params)),
    innerEdges: f.innerEdges.map(e=>({...e})),
    boundary: [],
    groupNode
  };
  GRAPH.nodes.push({ ...groupNode, ins:[...groupNode.ins], outs:[...groupNode.outs] });
  renderGraph(); closeParams();
  toast('已加入流程「' + f.n + '」· 按 Tab 展开');
}

/* --------- 参数面板 --------- */
let paramsFor = null;
function showNodeParams(id){
  const n = GRAPH.nodes.find(x=>x.id===id);
  if (!n) return;
  paramsFor = id;
  const host = document.getElementById('gparams');
  if (!host) return;
  const isShot = typeof n.shot === 'number';
  const it = isShot ? DOC.items.slice().sort((a,b)=>a.order-b.order)[n.shot] : null;
  const capKey = capKeyOfNode(n);
  const cap = capKey ? CAPS[capKey] : null;
  /* 这一栏就是"节点背后那份能力"：能指到就报接口和价，指不到就明说，不编 */
  const capBlock = cap ? `
      <div class="psep"></div>
      <div class="prow"><span class="pk">能力</span><span class="pv">${cap.label} <code style="font-size:10px">${capKey}</code></span></div>
      <div class="prow"><span class="pk">接口</span><span class="pv"><code style="font-size:10px">${cap.invoke.method==='LOCAL'?'本地 '+cap.invoke.path:cap.invoke.path}</code></span></div>
      <div class="prow"><span class="pk">成本</span><span class="pv">${cap.cost?'⚡'+cap.cost:'免费'}</span></div>
      ${it?`<div class="prow"><span class="pk">参数</span><span class="pv">${escapeHtml(Object.values(cap.params).join(' · '))}</span></div>`:''}
      ` : (n.cap ? `
      <div class="psep"></div>
      <div class="pnote">🔴 节点写了 <code>${escapeHtml(String(n.cap))}</code>，但 CAPS 里没这份能力 —— 跑不了，也不给价格。</div>
      ` : `
      <div class="psep"></div>
      <div class="prow"><span class="pk">能力</span><span class="pv">${n.data?'读文档 · 不调能力':(n.userGroup?'组 · 进去才是真节点':'🔴 指不到能力')}</span></div>
      `);
  host.classList.remove('hidden');
  host.innerHTML = `
    <div class="ph2"><span class="pt">${n.t}</span>
      <button class="px" onclick="closeParams()">✕</button></div>
    <div class="pb">
      <div class="prow"><span class="pk">类型</span><span class="pv">${n.kind}</span></div>
      <div class="prow"><span class="pk">输入</span><span class="pv">${(n.ins||[]).join(' / ')||'—'}</span></div>
      <div class="prow"><span class="pk">输出</span><span class="pv">${(n.outs||[]).join(' / ')||'—'}</span></div>
      ${capBlock}
      ${it?`
      <div class="psep"></div>
      <div class="prow"><span class="pk">镜头</span><span class="pv">${String(n.shot+1).padStart(2,'0')} ${it.name}</span></div>
      <div class="prow"><span class="pk">时长</span><span class="pv">${it.duration>0?it.duration.toFixed(1)+'s':'—'}</span></div>
      <div class="prow"><span class="pk">状态</span><span class="pv">${n.sub}</span></div>
      <div class="psep"></div>
      <div class="pnote">改参数会标脏，点「运行」只跑这一镜。</div>
      `:''}
    </div>
    <div class="pf">
      ${capKey?`<button class="b solid" style="flex:1;justify-content:center;font-size:11.5px"
        onclick="runNode('${id}')">▶ 运行这个节点</button>`:
        `<span style="font-size:11px;color:var(--tx3)">${n.userGroup?'组节点 · 按 Tab 进去跑里面的':(n.data?'读文档 · 不调能力':'指不到能力 · 跑不了')}</span>`}
      ${capKey ? `<button class="b out" style="font-size:11.5px" onclick="openPage('${capKey}')">打开完整页面 ↗</button>` : ''}
    </div>`;
}
function closeParams(){
  paramsFor=null;
  const h=document.getElementById('gparams');
  if (h) h.classList.add('hidden');
}

/* --------- 运行 ---------
   🔴 两条以前漏掉的路：
     · ▶ 单节点直接跑，⚡14 花出去没人问（跑整图反而有门禁）
     · chargeFor 定义了却没人调，顶栏「今天花了」永远是 ¥0
   现在：解析能力 → 过门禁 → 执行 → 按 PRICE_BOOK 落账 → 刷顶栏。 */
async function runNode(id){
  const n = GRAPH.nodes.find(x=>x.id===id);
  if (!n) return;

  const isShot = typeof n.shot === 'number';
  const capKey = capKeyOfNode(n);
  if (!capKey){
    if (n.data){ toast('「' + n.t + '」读文档，不调能力 —— 没有要跑的东西'); return; }
    toast('这个节点指不到 CAPS 里的能力 · 没跑');
    return;
  }
  const cap = CAPS[capKey];
  const cost = cap.cost || 0;

  if (cost >= GATE_COST_THRESHOLD && typeof requestGate === 'function'){
    const approved = await requestGate({
      kind:'node-run',
      title:'运行「' + n.t + '」',
      plan:[
        '能力：' + cap.label + '（' + capKey + '）',
        '接口：' + (cap.local ? '本地 ' + cap.invoke.path : cap.invoke.method + ' ' + cap.invoke.path),
        '参数：' + Object.entries(cap.params).map(([k,v])=>k+'='+(Array.isArray(v)?v.join('|'):v)).join(' · '),
        isShot ? ('只重画第 ' + String(n.shot+1).padStart(2,'0') + ' 镜') : '只跑这一个节点，不动上游'
      ],
      cost,
      irreversible:false,
      why:'一次点击就是一次真生成，价格要在你点头之前看见'
    });
    if (!approved){
      toast('已取消 · 没跑 · 没花钱');
      return;
    }
  }

  n.st='run'; n.sub='运行中…'; renderGraph();
  toast('运行中：' + n.t);
  const r = invokeCap(capKey, {}, cap.params);
  /* ⚡ 之外还要落人民币：能力上没配 price 就不记，不编 */
  const bill = (cap.price && typeof chargeFor === 'function') ? chargeFor(cap, cap.price, 1) : null;
  const ms = isShot ? 1200 : 900;

  setTimeout(()=>{
    if (isShot){
      const items = DOC.items.slice().sort((a,b)=>a.order-b.order);
      const it = items[n.shot];
      if (it){ it.status='ok'; it.duration = it.duration || 3.5; }
    }
    n.st='ok';
    n.sub = cost ? ('完成 · ⚡' + cost) : '完成 · 免费';
    renderGraph();
    if (isShot){ renderShots(); renderTimeline(); renderMeta(); }
    showNodeParams(id);
    if (typeof renderUserChip === 'function') renderUserChip();

    const moneyTxt = bill
      ? (bill.ok ? ' ⚡' + cost + ' / ' + money(bill.amountCny) : ' ⚡' + cost + '（' + bill.reason + '）')
      : (cost ? ' ⚡' + cost + '（PRICE_BOOK 没配这个模型的价，只记积分）' : ' 免费');

    if (typeof PROD_LOG !== 'undefined'){
      PROD_LOG.push({
        at: new Date().toLocaleTimeString('zh-CN', { hour12:false }).slice(0,8),
        kind:'gen',
        title:'跑单节点 · ' + n.t,
        detail: capKey + ' · <code>' + r.path + '</code> · ' + r.evidence,
        model: cap.price || '未配价',
        why:'跑之前过了门禁：⚡' + cost,
        cost, ms, status:'ok'
      });
      if (typeof renderBoard === 'function' && typeof BOARD_TAB !== 'undefined' && BOARD_TAB === 'board') renderBoard();
    }

    agAdd('ai', '<b>' + cap.label + '</b> 跑完了。<br><br>'
      + r.evidence + '<br>'
      + '参数：<code>' + escapeHtml(JSON.stringify(r.payload)) + '</code><br><br>'
      + '花费：<b>' + moneyTxt + '</b><br>'
      + '产物已经接到下游节点了。');
    toast('完成：' + cap.label + (cost ? ' · ⚡' + cost : ''));
  }, ms);
}

function rerunAll(){
  const items = DOC.items;
  const todo = items.filter(s=>s.status==='todo'||s.status==='err');
  toast(`整组重跑：只重跑 ${todo.length} 个待生成/失败镜头`);
  todo.forEach((s,i)=>setTimeout(()=>{
    s.status='ok'; s.duration=s.duration||3.5;
    buildGraph(true);          // 保留你拖过的节点位置
    renderFlow();
  }, 400+i*300));
  setTimeout(()=>{ buildGraph(true); if(mode==='flow') renderFlow(); }, 400+todo.length*300+120);
}

