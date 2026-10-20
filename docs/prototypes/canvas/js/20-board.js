/* 20-board.js — 制作实况看板（对话 vs 实况分开）
   来源：OpenMontage 的 Backlot
   🔴 原话：「Chat tells you what the agent SAID.
            Backlot shows you what the production is actually DOING.」

   我们的问题：Agent 面板只有对话，把"实际做了什么"压成一句文字摘要
   （"生成了 6 镜"）。看不到：每镜花了多少钱、用了哪个模型、为什么选它、耗时多久。

   这个看板 = 事实层。全部从 DOC.items + 生产日志推导，
   不要求 Agent 额外汇报（OpenMontage: derive everything from project files）。
*/

/* 生产日志：真实现里这些应该来自后端事件流 */
const PROD_LOG = [
  { at:'22:41:00', kind:'decide', title:'选模型',
    detail:'选了 gpt-image-2 而不是 nanobanana',
    why:'要保服装细节（银扣/高领），nanobanana 在复杂服装上细节保真差',
    alt:'nanobanana ⚡0.30/张（便宜 4.7 倍，但细节会糊）',
    cost:0 },
  { at:'22:41:03', kind:'gen', shot:1, title:'第 1 镜 中景推进',
    model:'gpt-image-2', cost:14, ms:8200, status:'ok' },
  { at:'22:41:12', kind:'gen', shot:2, title:'第 2 镜 特写',
    model:'gpt-image-2', cost:14, ms:7100, status:'ok' },
  { at:'22:41:21', kind:'gen', shot:3, title:'第 3 镜 侧身回头',
    model:'gpt-image-2', cost:14, ms:9400, status:'ok' },
  { at:'22:41:32', kind:'inspect', title:'巡检 6 镜',
    detail:'L1/L2 全过 · L3 语义查了 2 处', cost:2, ms:3200, status:'ok' },
  { at:'22:41:36', kind:'fix', shot:1, title:'第 1 镜 白平衡',
    detail:'5200K → 6100K', model:'本地', cost:0, ms:120, status:'ok' },
  { at:'22:41:37', kind:'fix', shot:2, title:'第 2 镜 曝光',
    detail:'-0.35EV → 0', model:'本地', cost:0, ms:90, status:'ok' },
  { at:'22:41:38', kind:'fix', shot:6, title:'第 6 镜 对比度',
    detail:'拉 S 曲线', model:'本地', cost:0, ms:110, status:'ok' },
  { at:'22:41:45', kind:'gen', shot:4, title:'第 4 镜 过场（重画）',
    model:'gpt-image-2', cost:14, ms:8800, status:'ok',
    why:'原图光照方向在左 210°，其余都在右 35° —— 本地改不了光的方向' },
  { at:'22:41:56', kind:'gen', shot:5, title:'第 5 镜 中景（重画）',
    model:'gpt-image-2', cost:14, ms:9100, status:'ok',
    why:'风衣画成单排扣，设定是双排扣银扣' },
  { at:'22:42:10', kind:'export', title:'导出 PNG 1024×1536',
    detail:'合成 11 层（本地调整 + AI 结果）', cost:0, ms:640, status:'ok' }
];

const KIND_META = {
  decide:{ ic:'◈', l:'决策', c:'var(--ac)' },
  gen:   { ic:'▣', l:'生成', c:'var(--tx2)' },
  inspect:{ ic:'⊙', l:'巡检', c:'var(--wn)' },
  fix:   { ic:'✎', l:'本地修', c:'var(--ok)' },
  export:{ ic:'⇥', l:'导出', c:'var(--tx3)' }
};

let BOARD_TAB = 'chat';   // 'chat' | 'board'

/* 切换面板 tab */
function setAgentTab(t){
  BOARD_TAB = t;
  const chat = document.getElementById('agb');
  const cmp  = document.querySelector('.cmp');
  const board = document.getElementById('boardPane');
  const tabs = document.querySelectorAll('.atab');

  tabs.forEach(b=>b.classList.toggle('on', b.dataset.tab === t));
  if (t === 'board'){
    if (chat) chat.style.display = 'none';
    if (cmp) cmp.style.display = 'none';
    if (board){ board.style.display = 'flex'; renderBoard(); }
  } else {
    if (chat) chat.style.display = '';
    if (cmp) cmp.style.display = '';
    if (board) board.style.display = 'none';
  }
}

/* 安装 tab 栏（挂到 Agent 面板标题下） */
function mountAgentTabs(){
  const ag = document.querySelector('.ag');
  if (!ag || document.getElementById('agentTabs')) return;

  const tabs = document.createElement('div');
  tabs.className = 'atabs';
  tabs.id = 'agentTabs';
  tabs.innerHTML = `
    <button class="atab on" data-tab="chat" onclick="setAgentTab('chat')">
      对话<span class="atab-n">Agent 说了什么</span>
    </button>
    <button class="atab" data-tab="board" onclick="setAgentTab('board')">
      制作实况<span class="atab-n">实际做了什么</span>
    </button>`;
  const hd = ag.querySelector('.agh') || ag.firstElementChild;
  if (hd && hd.nextSibling) ag.insertBefore(tabs, hd.nextSibling);
  else ag.appendChild(tabs);

  const pane = document.createElement('div');
  pane.className = 'boardpane';
  pane.id = 'boardPane';
  pane.style.display = 'none';
  ag.appendChild(pane);
}

/* 渲染看板 */
function renderBoard(){
  const host = document.getElementById('boardPane');
  if (!host) return;

  const gens = PROD_LOG.filter(x=>x.kind==='gen');
  const totalCost = PROD_LOG.reduce((a,b)=>a+(b.cost||0),0);
  const totalMs = PROD_LOG.reduce((a,b)=>a+(b.ms||0),0);
  const localFixes = PROD_LOG.filter(x=>x.kind==='fix');
  const localCost = localFixes.reduce((a,b)=>a+(b.cost||0),0);

  const shots = (typeof DOC !== 'undefined' ? DOC.items : []);

  host.innerHTML = `
    <div class="bp-hd">
      <span class="bp-t">制作实况</span>
      <span class="bp-used">演示数据 · 编号 1-11 是预置样例，第 12 条起才是真实操作</span>
    </div>

    <div class="bp-sum">
      <div class="bp-si"><span class="bp-sk">总花费</span><span class="bp-sv">⚡${totalCost}</span></div>
      <div class="bp-si"><span class="bp-sk">总耗时</span><span class="bp-sv">${(totalMs/1000).toFixed(1)}s</span></div>
      <div class="bp-si"><span class="bp-sk">生成调用</span><span class="bp-sv">${gens.length} 次</span></div>
      <div class="bp-si"><span class="bp-sk">本地修</span><span class="bp-sv ok">${localFixes.length} 次 · ⚡${localCost}</span></div>
    </div>

    <div class="bp-sec">
      <span>镜头实况</span>
      <span class="bp-sec2">${shots.length} 镜 · 每镜的状态/模型/成本</span>
    </div>
    <div class="bp-shots">
      ${shots.map((s,i)=>{
        const g = PROD_LOG.filter(x=>x.kind==='gen' && x.shot===i+1);
        const f = PROD_LOG.filter(x=>x.kind==='fix' && x.shot===i+1);
        const cost = g.reduce((a,b)=>a+(b.cost||0),0);
        const st = s.status || 'ok';
        return `<div class="bp-shot ${st}">
          <span class="bp-no">${String(i+1).padStart(2,'0')}</span>
          <span class="bp-nm">${s.name||'—'}</span>
          <span class="bp-st ${st}">${st==='ok'?'已生成':st==='run'?'生成中':st==='err'?'失败':'待生成'}</span>
          <span class="bp-md">${g.length?'gpt-image-2':'—'}</span>
          <span class="bp-ct">${cost?'⚡'+cost:(f.length?'<b class="ok">免费修</b>':'—')}</span>
        </div>`;
      }).join('')}
    </div>

    <div class="bp-sec">
      <span>完整过程</span>
      <span class="bp-sec2">带决策理由 · 可回放</span>
    </div>
    <div class="bp-log">
      ${PROD_LOG.map((l,i)=>{
        const m = KIND_META[l.kind] || { ic:'·', l:l.kind, c:'var(--tx3)' };
        return `<div class="bp-li ${l.kind}">
          <span class="bp-lt">${l.at}</span>
          <span class="bp-ic" style="color:${m.c}">${m.ic}</span>
          <div class="bp-lb">
            <div class="bp-lh">
              <span class="bp-lk">${m.l}</span>
              <span class="bp-lti">${l.title}</span>
              ${l.model?`<span class="bp-lmo">${l.model}</span>`:''}
              <span class="bp-lrt">${l.cost?'⚡'+l.cost:'免费'}${l.ms?' · '+(l.ms/1000).toFixed(1)+'s':''}</span>
            </div>
            ${l.detail?`<div class="bp-ld">${l.detail}</div>`:''}
            ${l.why?`<div class="bp-lw"><span class="bp-lwk">为什么</span>${l.why}</div>`:''}
            ${l.alt?`<div class="bp-lw alt"><span class="bp-lwk">备选</span>${l.alt}</div>`:''}
          </div>
        </div>`;
      }).join('')}
    </div>

    <div class="bp-foot">
      <span class="bp-fn">🔴 跑了 ${gens.length} 次生成、${localFixes.length} 次免费本地修 · 合计 ⚡${totalCost}</span>
      <button class="bp-replay" onclick="replayProduction()">▶ 回放</button>
    </div>`;
}

/* 回放：一条一条点亮 */
let REPLAY_TIMER = null;
function replayProduction(){
  const items = document.querySelectorAll('.bp-li');
  if (!items.length) return;
  if (REPLAY_TIMER){ clearInterval(REPLAY_TIMER); REPLAY_TIMER = null; }
  items.forEach(el=>el.classList.add('dim'));
  let i = 0;
  REPLAY_TIMER = setInterval(()=>{
    if (i >= items.length){ clearInterval(REPLAY_TIMER); REPLAY_TIMER = null; return; }
    items[i].classList.remove('dim');
    items[i].classList.add('lit');
    items[i].scrollIntoView({ block:'nearest', behavior:'smooth' });
    i++;
  }, 260);
}
