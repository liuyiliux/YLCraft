/* 07-agent.js - split from canvas_unified_v14.html (lines 1475-1946) */
/* ================= Agent ================= */
/* ================= 知识库 → 画布：Agent 回答带编号出处 =================
   对照 AI copilot UI patterns：
   - Inline citations：[1][2] 可点，跳到原文片段
   - 区分来源类型：公众号/Git/网页/笔记 各有颜色
   - 🔴 "No source"：模型自己想的 vs 材料里有的，必须分开说
   - Context chips：这次用了哪几条知识，可见
*/

const KB_CITE = {
  'k1': { t:'AI 生图的提示词工程实践（2025 修订版）', k:'wechat', seg:12, src:'卡兹克' },
  'k5': { t:'短剧分镜的 12 个镜头语言',              k:'wechat', seg:8,  src:'影视工业网' },
  'k8': { t:'我做 Cos 图的 7 条经验',                k:'note',   seg:3,  src:'我' },
  'k4': { t:'Anthropic: Building effective agents',  k:'web',    seg:5,  src:'Anthropic' },
  'k2': { t:'ComfyUI-Impact-Pack',                   k:'git',    seg:2,  src:'GitHub' }
};
const CITE_COLOR = { wechat:'#34d399', git:'#a78bfa', web:'#22d3ee', note:'#9c9ca8', doc:'#fbbf24' };

/* 渲染一条引用 chip */
function citeChip(id, n){
  const c = KB_CITE[id] || {};
  const col = CITE_COLOR[c.k] || '#71717a';
  return `<span class="cite" style="color:${col};border-color:${col}44"
    onclick="openCite('${id}')" title="${c.t||''} 第${c.seg||''}段">[${n}]</span>`;
}

/* 引用详情（点 [1] 弹出的片段原文） */
function openCite(id){
  const c = KB_CITE[id]; if (!c) return;
  const col = CITE_COLOR[c.k] || '#71717a';
  const texts = {
    'k1':'负向约束要写"避免"，不要写"不要" —— 模型对否定句的理解不稳定，容易把被否定的词画出来。',
    'k5':'情绪转折处先用中景过渡，别直接切特写 —— 观众会跟不上空间关系。',
    'k8':'磨皮别一次推到底，分两次：第一次只去瑕疵，第二次才轻推皮肤纹理，这样不会塑料。',
    'k4':'The most successful implementations use simple, composable patterns rather than complex frameworks.',
    'k2':'Impact Pack 提供检测、修脸、细节增强等节点，适合在生图后做后处理。'
  };
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="citebox">
      <div class="cbh">
        <span class="cbdot" style="background:${col}"></span>
        <div style="flex:1;min-width:0">
          <div class="cbt">${c.t}</div>
          <div class="cbs">${c.src} · 第 ${c.seg} 段</div>
        </div>
        <button class="b" onclick="closeOverlay()">✕</button>
      </div>
      <div class="cbb">${texts[id]||'（片段原文）'}</div>
      <div class="cbf">
        <span class="cbn">这条回答引用了它</span>
        <button class="b solid" onclick="closeOverlay();toast('打开知识库原文')">看原文 →</button>
      </div>
    </div></div>`;
}

/* 知识库问答：命中 → 回答 + 编号引用 */
function kbAnswer(q){
  const hits = [
    { id:'k8', score:0.87 }, { id:'k1', score:0.91 }, { id:'k5', score:0.74 }
  ].filter(h => KB_CITE[h.id]);
  const strong = hits.filter(h=>h.score>=0.8);
  return {
    html: `磨皮分两次推，别一次到底 —— 这样能保留皮肤纹理。<br><br>`
      + `第一次只去瑕疵，第二次才轻推明暗过渡 ${citeChip('k8',1)}。`
      + `另外，负向约束的写法也有讲究：写"避免"比写"不要"稳 ${citeChip('k1',2)}。<br><br>`
      + `<span class="myown">剩下的（推几次、每次多少）是我的经验推断，材料里没写死 —— 按你那张图的肤质调。</span>`
      + `<div class="citefoot">
           <span class="citef1">查了知识库 · 命中 ${hits.length} 段，其中 ${strong.length} 段高相关</span>
           <span class="citef2">${hits.map(h=>citeChip(h.id, hits.indexOf(h)+1)).join('')}</span>
         </div>`,
    chips: hits.map(h=>KB_CITE[h.id])
  };
}

/* 把知识库接进 send()：识别提问意图，走 kbAnswer */
const KB_TRIGGER = /磨皮|打光|光位|提示词|怎么写|镜头|分镜|参考|知识库|之前那篇|材料/;

/* 在消息下方渲染"用了哪些知识"的 context chips */
function agChips(list){
  if (!list || !list.length) return;
  const host = agb.lastElementChild;
  if (!host) return;
  const d = document.createElement('div');
  d.className = 'ctxchips';
  d.innerHTML = `<span class="cc-l">使用了</span>`
    + list.map(c=>`<span class="cc-i" style="border-color:${(CITE_COLOR[c.k]||'#71717a')}44">
        <span class="cc-d" style="background:${CITE_COLOR[c.k]||'#71717a'}"></span>${c.t}</span>`).join('');
  host.appendChild(d);
  agb.scrollTop = agb.scrollHeight;
}

function agAdd(kind, html){
  const d=document.createElement('div');
  d.className='msg '+kind;
  d.innerHTML = kind==='ai'
    ? `<div class="who">智能体</div><div class="bubble">${html}</div>`
    : `<div class="bubble">${html}</div>`;
  agb.appendChild(d); agb.scrollTop=agb.scrollHeight;
}
function send(){
  const ta=document.getElementById('ta');
  const t=ta.value.trim(); if(!t) return;
  ta.value=''; ta.rows=1;
  agAdd('me', esc(t));
  if (typeof wsConsumeComposerRefs === 'function') wsConsumeComposerRefs();
  /* 参考组合由对话触发（2026-11-01）——场景从这句话里读，不另设选择器
     触发词要宽一点：「凑一组参考」「要一组参考」「帮我找参考」都得认 */
  if (/(参考组合|凑.{0,4}参考|找.{0,4}参考|要.{0,2}组?参考|来.{0,2}组?参考)/.test(t)
      && typeof wsOpenRefCombo === 'function'){
    setTimeout(()=>{ wsOpenRefCombo(t); }, 420);
    return;
  }
  if (DOC.items.length===0){
    setTimeout(()=>{ demoFill('talk'); }, 500);
    return;
  }
  setTimeout(()=>{
    // 生成型搜索：要生成模型知识里没有的东西
    if (/最近出现|不认识|搜一下|搜搜|生成|做个|画个/.test(t) && detectSubject(t)){
      runSearchDemo(t);
      return;
    }
    // 知识库问答：带编号出处
    if (KB_TRIGGER.test(t)){
      const r = kbAnswer(t);
      agAdd('ai', r.html);
      agChips(r.chips);
      return;
    }
    const m=t.match(/第\s*(\d+)\s*镜/);
    if (/拆/.test(t) && m){
      const order=+m[1]-1;
      const arr=DOC.items.slice().sort((a,b)=>a.order-b.order);
      const s=arr[order]; if(!s){ agAdd('ai','没找到第 '+m[1]+' 镜。'); return; }
      const a={...s, id:s.id+'a', name:s.name+'A（中景）', duration:Math.round(s.duration*0.6*10)/10, status:'todo'};
      const b={...s, id:s.id+'b', name:s.name+'B（特写）', duration:Math.round(s.duration*0.4*10)/10, status:'todo'};
      arr.splice(order,1,a,b);
      arr.forEach((o,k)=>o.order=k);
      DOC.items=arr; renderShots();
      agAdd('ai', `拆好了。第 ${m[1]} 镜分成两镜，<b>后面镜号自动重排</b>。<br><br>`
        + `原镜头「${s.name}」<br>拆成 2A 中景 / 2B 特写<br>`
        + `镜号 ${arr.length-1} → ${arr.length} 镜<br>`
        + `两个新镜头都是<b>待生成</b>。<br><br>要我接着生成这两镜吗？<b>会花两镜的钱。</b>`);
      document.getElementById('hintBar').innerHTML = `第 ${m[1]} 镜已拆成两镜 · 镜号已重排`;
    } else {
      agAdd('ai', '收到。这版原型只演示了「拆镜头」和「换顺序」，你说"把第 2 镜拆成中景和特写"试试。');
    }
  }, 500);
}
function esc(s){ return s.replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function toast(t){
  const old=document.querySelector('.toast'); if(old) old.remove();
  const d=document.createElement('div'); d.className='toast';
  d.innerHTML='<svg class="ic sm" viewBox="0 0 24 24" style="color:var(--ac)"><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>'+t;
  document.body.appendChild(d);
  setTimeout(()=>{d.style.opacity='0';d.style.transition='opacity .4s';},2100);
  setTimeout(()=>d.remove(),2600);
}

/* ================= Skill 表单入口（Lovart 路线：不看节点也能用） ================= */
/* 和复杂节点共用同一份能力，只是外面套一件"表单"而不是"节点" */

/* ================= P5：Skill 也引用 CAPS（一份能力，三种外壳彻底打通） ================= */

/* 🔴 关键：skill.cap 指向 CAPS 里的能力。
   价格、接口、默认参数、页面 —— 全部从 CAPS 读，不在这里重复定义。
   这样"改一处，三处同变"。 */
const SKILLS = [
  { id:'poster', n:'美妆海报', ic:'▤', d:'给商品图，出成品海报',
    cap:'image-gen', fill:{kind:'upload', n:2},
    fields:[
      {k:'p', t:'image',  l:'商品 / 主体图', req:1, mapTo:'reference'},
      {k:'s', t:'select', l:'风格', opts:['极简','日系','金属质感','复古'], mapTo:'model'},
      {k:'c', t:'text',   l:'文案', ph:'例如：一抹即亮', mapTo:'prompt'},
      {k:'r', t:'select', l:'尺寸', opts:['2:3','1:1','3:4'], mapTo:'ratio'}
    ]},

  { id:'drama', n:'短剧分镜', ic:'▥', d:'一段故事，拆成镜头表',
    cap:'image-gen', fill:{kind:'script', n:12},
    fields:[
      {k:'p', t:'text',   l:'故事', ph:'例如：雨夜，她在巷口回头', rows:3, mapTo:'prompt'},
      {k:'e', t:'select', l:'集数', opts:['1 集','3 集','6 集'], mapTo:'count'},
      {k:'s', t:'select', l:'风格', opts:['电影感','日漫','写实'], mapTo:'model'}
    ]},

  { id:'coser', n:'Cos 精修', ic:'◑', d:'保留皮肤纹理，别磨成塑料',
    cap:'image-editor', fill:{kind:'upload', n:1},
    fields:[
      {k:'p', t:'image',  l:'原图', req:1, mapTo:'image'},
      {k:'d', t:'select', l:'精修程度', opts:['轻','中','重'], mapTo:'op'}
    ]},

  { id:'char3', n:'角色三视图', ic:'◨', d:'正面 / 侧面 / 背面',
    cap:'image-gen', fill:{kind:'upload', n:3},
    fields:[
      {k:'p', t:'text',   l:'角色描述', ph:'例如：银发，黑色风衣', rows:2, mapTo:'prompt'},
      {k:'s', t:'select', l:'风格', opts:['日漫','美漫','写实'], mapTo:'model'}
    ]},

  { id:'motion', n:'图转动图', ic:'▷', d:'多格图 → 切帧 → GIF',
    cap:'motion-gif', fill:{kind:'upload', n:4},
    fields:[
      {k:'p', t:'image',  l:'多格图', req:1, mapTo:'sheet'},
      {k:'a', t:'select', l:'动效', opts:['推近','摇摆','循环'], mapTo:'format'},
      {k:'g', t:'select', l:'格数', opts:['4 格','9 格'], mapTo:'grid'}
    ]},

  { id:'to3d', n:'图生 3D', ic:'◈', d:'一张图出 glb，可进导演台',
    cap:'model-3d', fill:{kind:'upload', n:1},
    fields:[
      {k:'p', t:'image',  l:'图片', req:1, mapTo:'image'},
      {k:'q', t:'select', l:'精度', opts:['标准','高'], mapTo:'quality'}
    ]}
];

let skillId = null;

/* 价格 / 接口 一律从 CAPS 读 —— 不在这儿写死 */
function capOfSkill(s){ return CAPS[s.cap] || null; }
function skillCost(s){ const c = capOfSkill(s); return c ? (c.cost ? '⚡' + c.cost : '免费') : '—'; }

function openSkills(){
  closeCtx();
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="skl">
      <div class="th2"><div class="t">快速开始</div>
        <div class="s">选一个，填两三项就出结果 —— <b>不用懂画布、不用连节点</b></div></div>
      <div class="skgrid">
        ${SKILLS.map(s=>`
          <div class="skcard" onclick="openSkillForm('${s.id}')">
            <div class="skic">${s.ic}</div>
            <div class="skn">${s.n}</div>
            <div class="skd">${s.d}</div>
            <div class="skc">${skillCost(s)}</div>
          </div>`).join('')}
      </div>
      <div class="skfoot">
        <span class="sknote">
          这些技能背后就是画布上的「复杂节点」，<b>能力、价格、接口全部同一份</b>。
        </span>
        <button class="b" onclick="closeOverlay()">关闭</button>
      </div>
    </div></div>`;
  showHint('技能 = 一个按钮 + 一张表单 · 价格和能力都来自同一份配置', 6000);
}

function openSkillForm(id){
  const s = SKILLS.find(x=>x.id===id); if(!s) return;
  const cap = capOfSkill(s);
  skillId = id;
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="skform">
      <div class="th2" style="display:flex;align-items:center;gap:10px">
        <div class="skic sm">${s.ic}</div>
        <div><div class="t">${s.n}</div><div class="s">${s.d}</div></div>
        <span style="margin-left:auto;color:var(--ac);font-family:var(--fm);font-size:12px">${skillCost(s)}</span>
      </div>
      <div class="skfields">
        ${s.fields.map(f=>`
          <div class="sff">
            <label>${f.l}${f.req?'<span class="req">*</span>':''}</label>
            ${f.t==='text'
              ? `<textarea data-f="${f.mapTo||''}" id="skf_${f.mapTo||''}" rows="${f.rows||1}" placeholder="${f.ph||''}"></textarea>`
              : f.t==='image'
              ? `<div class="sfup" data-f="${f.mapTo||''}" id="skf_${f.mapTo||''}"
                     onclick="toast('选图（原型不接上传）')">
                   <svg class="ic sm" viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>
                   点这里选图
                 </div>`
              : `<div class="sfsel" data-f="${f.mapTo||''}" id="skf_${f.mapTo||''}"
                     data-v="${f.opts[0]}"
                     onclick="cycleOpt(this,'${f.opts.join('|')}')">${f.opts[0]} <span class="cv2">▾</span></div>`}
          </div>`).join('')}
      </div>
      <div class="skfoot">
        <span class="sknote">
          能力 <code style="font-family:var(--fm);color:var(--tx2)">${cap ? cap.invoke.method + ' ' + cap.invoke.path : '—'}</code>
        </span>
        <button class="b" onclick="openSkills()">返回</button>
        ${cap ? `<button class="b" onclick="openPage('${s.cap}')">打开完整页面 ↗</button>` : ''}
        <button class="b solid" onclick="runSkill('${s.id}')">开始生成</button>
      </div>
    </div></div>`;
}

function cycleOpt(el, opts){
  const a = opts.split('|');
  const cur = el.textContent.trim().replace(' ▾','');
  const i = (a.indexOf(cur) + 1) % a.length;
  el.innerHTML = a[i] + ' <span class="cv2">▾</span>';
  /* 把当前值同步到 dataset，runSkill 从这里读 */
  if (el.dataset) el.dataset.v = a[i];
}

/* 🔴 跑技能 = 走和节点同一个 invokeCap
   🔧 2026-10-20 修：之前表单字段没有 id/data-f，所以只能写死「（表单值）」。
      现在给字段挂了 data-f，这里真读用户填的值。
   🔧 同时补门禁：之前 runSkill 直接 invokeCap，花钱不批。 */
async function runSkill(id){
  const s = SKILLS.find(x=>x.id===id); if(!s) return;
  const cap = capOfSkill(s);
  if (!cap){ toast('这个技能还没有接上能力'); return; }

  // 把表单字段按 mapTo 映射成 invoke 的 inputs/params（真读 DOM）
  const params = { ...cap.params };
  const inputs = {};
  s.fields.forEach(f=>{
    if (!f.mapTo) return;

    // ① 先从表单里读用户实际填的值
    let val = null;
    const el = document.querySelector('[data-f="' + f.mapTo + '"]');
    if (el){
      if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT'){
        val = el.value;
      } else {
        // 自定义 select 把自己的当前值挂在 dataset.v 上
        val = el.dataset ? el.dataset.v : null;
        if (!val) val = (el.textContent || '').replace(/▾/g, '').trim();
      }
    }

    // ② 没填 → 用默认值（select 取第一项，text 留空）
    if (val === null || val === undefined || String(val).trim() === ''){
      val = (f.t === 'select' && f.opts) ? f.opts[0] : '';
    }

    if (cap.params && Object.prototype.hasOwnProperty.call(cap.params, f.mapTo)){
      params[f.mapTo] = val;
    } else {
      inputs[f.mapTo] = val;
    }
  });

  // ③ 门禁：花钱的必须批（和节点、整图同一条规矩）
  const cost = (typeof skillCost === 'function') ? Number(String(skillCost(s)).replace(/[^\d.]/g, '')) || 0 : 0;
  if (cost >= GATE_COST_THRESHOLD && typeof requestGate === 'function'){
    const approved = await requestGate({
      kind: 'skill-run',
      title: '跑技能 · ' + s.n,
      plan: [
        '能力：' + (cap.invoke ? cap.invoke.method + ' ' + cap.invoke.path : '—'),
        '参数：' + JSON.stringify(inputs),
        '产出：' + (s.fill ? s.fill.n + ' 个' + (s.fill.kind === 'script' ? '镜头' : '图') : '结果')
      ],
      cost: cost,
      irreversible: false,
      why: '技能和节点是同一份能力，花钱的规矩也一样'
    });
    if (!approved) return;
  }

  const r = invokeCap(s.cap, inputs, params);   // 🔴 和节点完全同一条路
  closeOverlay();
  demoFill(s.fill.kind, s.fill.n);

  agAdd('ai', `<b>${s.n}</b> 跑完了。<br><br>`
    + `调用 <code>${r.path}</code><br>`
    + `参数：<code>${escapeHtml(JSON.stringify(r.payload))}</code><br><br>`
    + (r.cost ? `这一单 ⚡${r.cost}。` : '本地处理，不花钱。')
    + `<br>产物已经落在画布上了，可以接着改。`);
  toast(`「${s.n}」完成 · ${r.cost ? '⚡' + r.cost : '免费'}`);
}

function closeOverlay(){ document.getElementById('overlayHost').innerHTML=''; }


/* ================= 模板弹窗 ================= */
/* ================= 模板（含版本：默认快照 + 手动升级） ================= */

/* 版本模型：
   - 用模板创建画布时，记下 {tpl_id, version} —— 存的是那一刻的快照
   - 模板作者更新 → 我的画布不变，只在顶栏挂一个「有新版」
   - 点升级 → 先给 diff（加/删/改哪些），确认才动
*/
const TPLS = [
  {id:'drama',  n:'短剧分镜',   nodes:5, used:210, seq:[0,1,1,1,1], fill:'script', cat:'漫剧', ver:3, latest:4,
   changelog:[
     {t:'add',  s:'增加「角色一致性检查」'},
     {t:'chg',  s:'生成镜头图：默认模型改为 GPT Image 2'},
     {t:'chg',  s:'合成时间线：默认 24fps'}
   ]},
  {id:'coser',  n:'Cos 精修',   nodes:2, used:128, seq:[0,1],       fill:'upload', cat:'修图', ver:2, latest:2, changelog:[]},
  {id:'ecom',   n:'电商主图',   nodes:3, used:96,  seq:[0,1,1],     fill:'upload', cat:'电商', ver:1, latest:1, changelog:[]},
  {id:'char',   n:'角色三视图', nodes:4, used:180, seq:[0,1,1,1],   fill:'script', cat:'漫剧', ver:2, latest:3,
   changelog:[
     {t:'chg',  s:'三视图：比例从 1:1 改为 2:3'},
     {t:'del',  s:'移除「背景统一」步骤'}
   ]},
  {id:'board',  n:'分镜表拆解', nodes:4, used:64,  seq:[0,1,0,1],   fill:'script', cat:'漫剧', ver:1, latest:1, changelog:[]},
  {id:'poster', n:'海报排版',   nodes:3, used:45,  seq:[0,1,1],     fill:'tpl',    cat:'设计', ver:1, latest:2,
   changelog:[
     {t:'add',  s:'增加「安全边距检查」'}
   ]},
];
let tplSel = 0;

/* 当前画布用的模板（用模板创建后记下） */
let currentTplRef = null;   // { id, ver }

function openTpl(){
  closeCtx();
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeTpl()"><div class="tpl">
      <div class="th2"><div class="t">新建画布 · 选一个起点</div>
        <div class="s">模板就是一套连好的流程，选完可以直接用，也能改</div></div>
      <div class="cats">
        <button class="on">全部</button><button>漫剧</button><button>修图</button><button>电商</button><button>我的</button>
      </div>
      <div class="tbody" id="tplBody"></div>
      <div class="tf"><span class="info" id="tplInfo"></span>
        <button class="b" onclick="closeTpl()">取消</button>
        <button class="b solid" onclick="useTpl()">用这个模板</button></div>
    </div></div>`;
  renderTpl();
  showHint('选一个模板 → 点「用这个模板」· 用了以后模板更新不会自动改你的画布', 7000);
}

function renderTpl(){
  let html = TPLS.map((t,i)=>{
    const mini = t.seq.map((c,k)=>`<i class="${c?'c':''}"></i>${k<t.seq.length-1?'<span class="ar"></span>':''}`).join('');
    const newer = t.latest > t.ver;
    return `<div class="tcard ${i===tplSel?'on':''}" onclick="tplSel=${i};renderTpl()">
      <div class="mini">${mini}</div>
      <div class="ti"><div class="tn">${t.n}
          <span class="tver">v${t.latest}</span>
          ${newer?`<span class="tnew" title="这个模板有新版本">NEW</span>`:''}
        </div>
        <div class="tm">${t.nodes} 步 · 用过 ${t.used} 次</div></div></div>`;
  }).join('');
  html += `<div class="tcard blank ${tplSel===-1?'on':''}" onclick="tplSel=-1;renderTpl()">
      <div class="mini" style="font-size:18px;color:var(--tx3)">+</div>
      <div class="ti"><div class="tn">空白画布</div><div class="tm">从零搭</div></div></div>`;
  document.getElementById('tplBody').innerHTML = html;

  if (tplSel >= 0){
    const t = TPLS[tplSel];
    const newer = t.latest > t.ver;
    document.getElementById('tplInfo').innerHTML =
      `选中「${t.n}」v${t.latest} · ${t.nodes} 步 · 其中 ${Math.max(1,t.nodes-2)} 步会花钱`
      + (newer ? ` · <b style="color:var(--wn)">这个模板刚更新过</b>` : '');
  } else {
    document.getElementById('tplInfo').textContent = '空白画布 · 自己开始';
  }
}

function useTpl(){
  const t = tplSel>=0 ? TPLS[tplSel] : null;
  closeTpl();
  if (!t){
    currentTplRef = null;
    demoFill('talk', 3);
    toast('已创建空白画布');
    renderTplRefBar();
    return;
  }
  // 🔴 记下快照版本
  currentTplRef = { id:t.id, ver:t.ver };
  const counts = { drama:12, char:3, board:12, coser:3, ecom:3, poster:2 };
  demoFill(t.fill, counts[t.id] || 6);
  toast(`已用「${t.n}」v${t.ver} 创建 · ${counts[t.id]||6} 个对象`);
  // 有新版的模板，一创建就提示
  if (t.latest > t.ver) setTimeout(showTplUpgrade, 900);
  renderTplRefBar();
}
function closeTpl(){ document.getElementById('overlayHost').innerHTML=''; }

/* --------- 顶栏：当前模板 + 有新版提示 --------- */
function renderTplRefBar(){
  const el = document.getElementById('tplRefBar');
  if (!el) return;
  if (!currentTplRef){ el.classList.add('hidden'); el.innerHTML=''; return; }
  const t = TPLS.find(x=>x.id===currentTplRef.id);
  if (!t){ el.classList.add('hidden'); return; }
  const newer = t.latest > currentTplRef.ver;
  el.classList.remove('hidden');
  el.innerHTML = `<span class="trb">来自 <b>${t.n}</b> v${currentTplRef.ver}</span>`
    + (newer
      ? `<button class="b" style="font-size:10.5px;padding:3px 9px;border-color:var(--wn);color:var(--wn)"
           onclick="showTplUpgrade()">有新版 v${t.latest}</button>`
      : `<span class="trb ok">已是最新</span>`);
}

/* --------- 升级确认：先给 diff --------- */
function showTplUpgrade(){
  if (!currentTplRef){ toast('当前画布不是从模板创建的'); return; }
  const t = TPLS.find(x=>x.id===currentTplRef.id);
  if (!t || t.latest <= currentTplRef.ver){ toast('已经是最新版'); return; }
  const icon = {add:'+', chg:'~', del:'−'};
  const color = {add:'var(--ok)', chg:'var(--wn)', del:'var(--dg)'};
  document.getElementById('overlayHost').innerHTML =
   `<div class="ov" onclick="if(event.target===this)closeOverlay()"><div class="upd">
      <div class="th2"><div class="t">「${t.n}」有新版本</div>
        <div class="s">v${currentTplRef.ver} → v${t.latest} · 你的画布<b>不会自动变</b>，确认后才升级</div></div>
      <div class="updbody">
        <div class="updl">会改这些：</div>
        ${(t.changelog||[]).map(c=>`
          <div class="updi">
            <span class="updicon" style="color:${color[c.t]};border-color:${color[c.t]}">${icon[c.t]}</span>
            <span>${c.s}</span>
          </div>`).join('') || '<div class="updi" style="color:var(--tx3)">这个版本没有会改动你现有内容的地方</div>'}
        <div class="updwarn">
          ⚠️ 升级会<b>替换掉你对这些节点的自定义</b>（改过的参数、换过的模型）。
          <br>不想丢的话，先「另存为我的模板」。
        </div>
      </div>
      <div class="updfoot">
        <button class="b" onclick="closeOverlay()">暂不升级</button>
        <button class="b" onclick="toast('已另存为我的模板（原型不落库）');closeOverlay()">另存为我的模板</button>
        <button class="b solid" onclick="doTplUpgrade()">确认升级</button>
      </div>
    </div></div>`;
}

function doTplUpgrade(){
  const t = TPLS.find(x=>x.id===currentTplRef.id);
  if (!t) return;
  currentTplRef.ver = t.latest;
  closeOverlay();
  renderTplRefBar();
  const adds = (t.changelog||[]).filter(c=>c.t==='add').length;
  toast(`已升级到 v${t.latest}` + (adds ? ` · 新增 ${adds} 个步骤` : ''));
  agAdd('ai', `模板「${t.n}」已升级到 <b>v${t.latest}</b>。`
    + (adds ? `<br>新增了 ${adds} 个步骤，已经在流程里了。` : '')
    + `<br><br>你之前改过的参数<b>保留了</b>（升级只补结构，不覆盖你的设置）。`);
}

