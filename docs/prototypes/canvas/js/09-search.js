/* 09-search.js - split from canvas_unified_v14.html (lines 2034-2602) */
/* ================= 生成型搜索：画布对话里的一整段 =================
   场景：用户要生成一个"最近出现的角色"，模型知识里没有
   → 承认不认识 → 搜 → 抽外观要素 → 自检缺什么 → 参考图存资产 → 生成
*/
/* ================= 主体类型 → 要素 schema（可切换） =================
   之前的"五官/发型/服装/配饰/风格"只是【人像】的 schema。
   商品图 / 场景图 / 海报，要素完全不同 —— 所以必须按主体类型切。
*/

const SUBJECT_SCHEMAS = {
  /* ---------- 人像 / 角色 ---------- */
  character: {
    n:'人像 / 角色', ic:'◑', d:'角色、Coser、短剧人物',
    lead:'我知识里没有这个角色的最新形象',
    queries:['霜见月 角色 外观 设定','霜见月 官方 发布 图','霜见月 发色 瞳色 服装'],
    /* 组顺序 = 提示词顺序 */
    groups:[
      { k:'face',   t:'五官', order:1,
        fields:['脸型','瞳色','肤色'] },
      { k:'hair',   t:'发型', order:2,
        fields:['发型','发色'] },
      { k:'outfit', t:'服装', order:3,
        fields:['上装','下装','鞋'] },
      { k:'acc',    t:'配饰', order:4,
        fields:['耳饰','标志物'] },
      { k:'body',   t:'体型', order:5,
        fields:['身高','体型'] },
      { k:'style',  t:'风格', order:6,
        fields:['色调','光比'] }
    ],
    elements:{
      '脸型':{ v:'— 搜到的资料没写', ok:0, ai:3 },
      '瞳色':{ v:'红色 竖瞳',        ok:1, src:'2', ai:4 },
      '肤色':{ v:'冷白 无明显血色',   ok:1, src:'1', ai:4 },
      '发型':{ v:'银白色 长直发 过腰', ok:1, src:'1', ai:5 },
      '发色':{ v:'银白 发梢微青',     ok:1, src:'3', ai:5 },
      '上装':{ v:'黑色高领长风衣 银扣', ok:1, src:'3', ai:5 },
      '下装':{ v:'— 只有半身图',      ok:0, ai:4 },
      '鞋':  { v:'— 搜不到',          ok:0, ai:5 },
      '耳饰':{ v:'— 搜不到',          ok:0, ai:4 },
      '标志物':{ v:'左眼下 泪痕状疤痕', ok:1, src:'1', ai:4 },
      '身高':{ v:'约 168cm',          ok:1, src:'3', ai:3 },
      '体型':{ v:'纤细 肩窄',         ok:1, src:'3', ai:4 },
      '色调':{ v:'冷色调 高对比',      ok:1, src:'2', ai:5 },
      '光比':{ v:'逆光 边缘光明显',    ok:1, src:'2', ai:5 }
    },
    promptTail:'银白发丝逆光边缘光, 高清细节',
    /* 缺项影响度不同 */
    critical:['脸型','瞳色','上装'],
    criticalWhy:'脸决定像不像，服装决定对不对得上版本'
  },

  /* ---------- 商品图 ---------- */
  product: {
    n:'商品图', ic:'▤', d:'电商主图、详情页、美妆食品服装',
    lead:'我知识里没有这个产品的最新包装',
    queries:['凝光面霜 官方 产品图','凝光面霜 包装 规格','凝光面霜 成分 卖点'],
    groups:[
      { k:'obj',    t:'产品本体', order:1,
        fields:['品类','形态','容量'] },
      { k:'mat',    t:'材质', order:2,
        fields:['瓶身材质','盖材质','表面处理'] },
      { k:'color',  t:'颜色', order:3,
        fields:['主色','辅色'] },
      { k:'mark',   t:'标识', order:4,
        fields:['logo位置','品名文字','规格文字'] },
      { k:'scene',  t:'场景', order:5,
        fields:['背景','台面'] },
      { k:'light',  t:'光照', order:6,
        fields:['主光','辅助光','反射'] },
      { k:'style',  t:'风格', order:7,
        fields:['调性','色调'] }
    ],
    elements:{
      '品类':{ v:'精华面霜 圆罐装',      ok:1, src:'1' },
      '形态':{ v:'矮圆柱罐 磨砂玻璃',    ok:1, src:'1' },
      '容量':{ v:'50ml',               ok:1, src:'2' },
      '瓶身材质':{ v:'半透明磨砂玻璃',    ok:1, src:'1' },
      '盖材质':{ v:'哑光金属 香槟金',    ok:1, src:'1' },
      '表面处理':{ v:'无高光 磨砂',      ok:1, src:'2' },
      '主色':{ v:'奶白 半透',           ok:1, src:'1' },
      '辅色':{ v:'香槟金 点缀',         ok:1, src:'1' },
      'logo位置':{ v:'— 官方图清晰度不够', ok:0 },
      '品名文字':{ v:'"凝光" 竖排 衬线体', ok:1, src:'2' },
      '规格文字':{ v:'50ml 在罐底',      ok:1, src:'2' },
      '背景':{ v:'— 详情页只有白底',      ok:0 },
      '台面':{ v:'— 搜不到',            ok:0 },
      '主光':{ v:'左上方柔光箱',         ok:1, src:'1' },
      '辅助光':{ v:'右侧弱补光',         ok:1, src:'1' },
      '反射':{ v:'罐底轻微投影',         ok:1, src:'1' },
      '调性':{ v:'干净 高级 不花哨',      ok:1, src:'1' },
      '色调':{ v:'暖白 低饱和',          ok:1, src:'1' }
    },
    promptTail:'商业产品摄影, 柔和阴影, 高清细节',
    critical:['品类','容量','logo位置','品名文字'],
    criticalWhy:'形状错=不是这个产品，文字错=不能上架'
  },

  /* ---------- 场景图 ---------- */
  scene: {
    n:'场景图', ic:'◍', d:'环境、空间、氛围背景',
    lead:'我知识里没有这个地方的实景',
    queries:['雨夜 老街 实景','雨夜 街道 霓虹 摄影','老巷 雨夜 光线'],
    groups:[
      { k:'space',  t:'空间', order:1,
        fields:['场所类型','年代','尺度'] },
      { k:'weather',t:'天候', order:2,
        fields:['天气','时段'] },
      { k:'light',  t:'光照', order:3,
        fields:['主光源','色温'] },
      { k:'mat',    t:'材质', order:4,
        fields:['地面','墙面'] },
      { k:'detail', t:'细节', order:5,
        fields:['标志物'] },
      { k:'view',   t:'视角', order:6,
        fields:['机位','景别'] }
    ],
    elements:{
      '场所类型':{ v:'老城区窄巷',        ok:1, src:'1' },
      '年代':{ v:'当代 但有旧痕迹',       ok:1, src:'2' },
      '尺度':{ v:'巷宽约 3m 可过一人',    ok:1, src:'1' },
      '天气':{ v:'小雨 地面积水',         ok:1, src:'1' },
      '时段':{ v:'深夜 无天光',           ok:1, src:'2' },
      '主光源':{ v:'霓虹招牌 顶光偏右',    ok:1, src:'1' },
      '色温':{ v:'冷蓝 + 品红 对比',      ok:1, src:'3' },
      '地面':{ v:'湿沥青 反光',           ok:1, src:'1' },
      '墙面':{ v:'旧砖 有水渍',           ok:1, src:'2' },
      '标志物':{ v:'— 不确定哪个招牌',     ok:0 },
      '机位':{ v:'齐眼高 平视',           ok:1, src:'3' },
      '景别':{ v:'中景 能看全巷口',       ok:1, src:'3' }
    },
    promptTail:'电影感, 浅景深, 高对比',
    critical:['场所类型','时段','主光源'],
    criticalWhy:'场所和光错了整张氛围就废'
  }
};

let curSubject = 'character';
let editingElem = null;
let addingElem = null;
let searchStep = 0;

/* 当前 case（从 schema 动态生成，跟旧接口兼容） */
function buildCase(type){
  const s = SUBJECT_SCHEMAS[type];
  const els = [];
  let i = 0;
  s.groups.forEach(g=>{
    g.fields.forEach(f=>{
      const meta = s.elements[f] || { v:'— 没搜到', ok:0 };
      els.push({
        id: 'e' + (i++),
        group: g.k,
        k: f,
        v: meta.v, ok: meta.ok,
        src: meta.src || null,
        edited: false, addedByMe: false
      });
    });
  });
  return {
    type, schema: s,
    q: '生成一个' + s.n + '：' + (type==='character'?'霜见月':type==='product'?'凝光面霜':'雨夜老街'),
    name: type==='character'?'霜见月':type==='product'?'凝光面霜':'雨夜老街',
    queries: s.queries,
    merged: 7,
    sources: [
      { n:1, t:'官方' + ({product:'产品页',character:'角色页',scene:'实景图',poster:'品牌视觉规范',ui:'设计系统',mixed:'商拍样片'}[type]||'资料'), u:'official.example.com/…', d:'2026-10-15', w:'official', type:'官网' },
      { n:2, t:'规格 / 发布信息', u:'x.com/official_/status/…', d:'2026-10-16', w:'official', type:'官方' },
      { n:3, t:'社区整理（含实拍）', u:'wiki.example.com/…', d:'2026-10-17', w:'community', type:'wiki' },
      { n:4, t:'相关视频', u:'bilibili.com/video/BV…', d:'2026-10-16', w:'official', type:'视频' }
    ],
    assets: [
      { id:'asset_9f2a', t:'官方主图', from:'official.example.com', kind:'image' },
      { id:'asset_9f2b', t:'实拍/截图', from:'bilibili.com', kind:'image' }
    ],
    elements: els
  };
}

/* 全局入口：切换主体类型 */
function setSubject(t){
  curSubject = t;
  SEARCH_CASE = buildCase(t);
  editingElem = null; addingElem = null;
  if (document.querySelector('.srch')) refreshSearchCard();
  else if (document.querySelector('.fail-bar')) { /* 演示工具条上，只更新类型标记 */ }
  toast('切到「' + SUBJECT_SCHEMAS[t].n + '」schema · ' + SUBJECT_SCHEMAS[t].groups.length + ' 组');
}

/* 兼容：其它地方用 SEARCH_CASE 变量 */
let SEARCH_CASE = buildCase('character');

/* ---------- 分组的提示词（按 group order 排） ---------- */
function buildPrompt(){
  const c = SEARCH_CASE;
  const s = c.schema;
  const lines = [];
  s.groups.slice().sort((a,b)=>a.order-b.order).forEach(g=>{
    const vals = c.elements
      .filter(e=>e.group===g.k && e.ok && e.v.trim() && !e.v.startsWith('—'))
      .map(e=> e.edited||e.addedByMe ? `<b>${e.v.trim()}</b>` : e.v.trim());
    if (vals.length) lines.push(vals.join(', '));
  });
  if (!lines.length) return '<span style="color:var(--tx3)">（还没要素）</span>';
  const okCount = c.elements.filter(e=>e.ok && !e.v.startsWith('—')).length;
  const edCount = c.elements.filter(e=>e.edited||e.addedByMe).length;
  return lines.join(' | ')
    + `<div class="srch-live2">按 ${s.groups.length} 个组的顺序拼 · ${okCount} 项要素 · ${edCount} 项是你动过的</div>`;
}

function runSearchDemo(){
  if (searchStep > 0){ toast('已经在跑了'); return; }
  searchStep = 1;
  agAdd('me', esc(SEARCH_CASE.q));
  setTimeout(()=>{
    agAdd('ai', renderSearchThinking());
    agb.scrollTop = agb.scrollHeight;
    setTimeout(()=>{
      searchStep = 2;
      const last = agb.lastElementChild;
      if (last) last.innerHTML = `<div class="who">智能体</div><div class="bubble">${renderSearchResult()}</div>`;
      agb.scrollTop = agb.scrollHeight;
    }, 1600);
  }, 400);
}

/* --- 阶段 1：搜索中 --- */
function renderSearchThinking(){
  return `
    <div class="srch">
      <div class="srch-h">
        <span class="srch-spin"></span>
        <span>先查一下 —— <b>我知识里没有「霜见月」这个角色</b></span>
      </div>
      <div class="srch-q">
        ${SEARCH_CASE.queries.map((q,i)=>`
          <div class="srch-qi" style="animation-delay:${i*0.15}s">
            <span class="srch-qn">${i+1}</span>
            <span class="srch-qt">${q}</span>
            <span class="srch-qs">搜索中…</span>
          </div>`).join('')}
      </div>
      <div class="srch-note">同时搜 3 个方向 —— 外观 / 官方图 / 具体特征</div>
    </div>`;
}

/* --- 阶段 2：结果 --- */
/* ================= 要素可编辑 =================
   用户能:
   ① 改已有要素的值
   ② 手动填缺项（自己知道就填）
   ③ 删掉不对的项
   ④ 看到不同来源的标记（来自哪条 / 我填的 / 我改的）
   ⑤ 底部实时预览"当前会用的提示词"
*/

/* 给要素补来源和编辑状态 */
function initElemMeta(){
  const c = SEARCH_CASE;
  if (c.__metaDone) return;
  c.elements.forEach((e,i)=>{
    e.id = 'e' + i;
    e.src = e.ok ? String(1 + (i % 3)) : null;   // 依次来自 [1][2][3]
    e.edited = false;
  });
  c.__metaDone = true;
}

/* 编辑中的字段 id */

function renderSearchResult(){
  const c = SEARCH_CASE;
  const s = c.schema;
  const miss = c.elements.filter(e=>!e.ok);
  const editedCount = c.elements.filter(e=>e.edited).length;
  const addedCount  = c.elements.filter(e=>e.addedByMe).length;
  const isCrit = (k)=> (s.critical||[]).includes(k);

  /* 单个要素行 */
  const rowOf = (e)=>{
    if (e.adding){
      return `<div class="srch-ei adding">
        <input class="srch-input key" id="key_${e.id}" value="${esc(e.k||'')}"
          placeholder="项名"
          onkeydown="if(event.key==='Escape')cancelAdd()">
        <input class="srch-input" id="inp_${e.id}" value=""
          placeholder="值"
          onkeydown="if(event.key==='Enter')saveAdd('${e.id}');if(event.key==='Escape')cancelAdd()">
        <button class="srch-mini ok" onclick="saveAdd('${e.id}')">✓</button>
        <button class="srch-mini" onclick="cancelAdd()">✕</button>
      </div>`;
    }
    if (editingElem === e.id){
      return `<div class="srch-ei editing">
        <span class="srch-ek">${e.k}</span>
        <input class="srch-input" id="inp_${e.id}" value="${esc(e.v.replace(/^—\s*/, ''))}"
          placeholder="填一个值…"
          onkeydown="if(event.key==='Enter')saveElem('${e.id}');if(event.key==='Escape')cancelElem()">
        <button class="srch-mini ok" onclick="saveElem('${e.id}')">✓</button>
        <button class="srch-mini" onclick="cancelElem()">✕</button>
      </div>`;
    }
    const fit = (typeof aiFitOf === 'function') ? aiFitOf(e) : null;
    const hardCls = (fit && e.ok && fit.ai <= 2) ? 'hardgen' : '';
    return `<div class="srch-ei ${e.ok?'':'miss'} ${e.edited?'edited':''} ${e.addedByMe?'added':''} ${hardCls}"
        onclick="startEditElem('${e.id}')" title="点一下改${fit?' · AI 适配度 '+fit.ai+'/5：'+fit.why:''}">
      <span class="srch-ek">${e.k}</span>
      <span class="srch-ev">${e.v}</span>
      ${fit ? (typeof aiStars === 'function' ? aiStars(fit.ai) : '') : ''}
      <span class="srch-esrc ${e.addedByMe?'add':(e.edited?'me':(e.src?'':'none'))}">
        ${e.addedByMe ? '我加的' : (e.edited ? '我改的' : (e.src ? `[${e.src}]` : '缺 · 点我填'))}
      </span>
      ${e.addedByMe
        ? `<span class="srch-revert" onclick="event.stopPropagation();removeElem('${e.id}')" title="删掉">✕</span>`
        : (e.edited?`<span class="srch-revert" onclick="event.stopPropagation();revertElem('${e.id}')" title="恢复">↺</span>`:'')}
    </div>`;
  };

  /* 按组渲染 */
  const groupsHtml = s.groups.slice().sort((a,b)=>a.order-b.order).map(g=>{
    const rows = c.elements.filter(e=>e.group===g.k);
    const okN = rows.filter(e=>e.ok && !e.v.startsWith('—')).length;
    const total = rows.length;
    const grpMiss = total - okN;
    const collapsed = collapsedGroups.has(g.k);
    return `<div class="grp ${grpMiss?'hasmiss':''}">
      <div class="grp-h" onclick="toggleGrp('${g.k}')">
        <span class="grp-chev">${collapsed?'▸':'▾'}</span>
        <span class="grp-t">${g.t}</span>
        <span class="grp-n">${g.order}</span>
        <span class="grp-c ${grpMiss?'miss':'ok'}">${grpMiss?('缺 '+grpMiss):(okN+'/'+total)}</span>
      </div>
      ${collapsed?'':`<div class="grp-b">${rows.map(rowOf).join('')}</div>`}
    </div>`;
  }).join('');

  const critMiss = miss.filter(e=>isCrit(e.k));

  return `
    <div class="srch">
      <div class="subj-bar">
        <span class="subj-l">主体类型</span>
        ${Object.entries(SUBJECT_SCHEMAS).map(([k,v])=>`
          <button class="subj-b ${curSubject===k?'on':''}" onclick="setSubject('${k}')"
            title="${v.d}">${v.ic} ${v.n}</button>`).join('')}
        ${SEARCH_CASE.__autoWhy?`<span class="subj-auto">自动判断：${SEARCH_CASE.__autoWhy}</span>`:''}
      </div>

      <div class="srch-done">
        搜了 <b>${c.queries.length}</b> 个方向 · 合并去重后剩下 <b>${c.merged}</b> 条
        <span class="srch-why">（各取 3 条交错合并，重复的只留一条）</span>
      </div>

      <div class="srch-src">
        ${c.sources.map(x=>`
          <div class="srch-si">
            <span class="srch-sn">[${x.n}]</span>
            <a class="srch-st" onclick="toast('打开 ${esc(x.u)}')">${x.t}</a>
            <span class="srch-sw ${x.w}">${x.type}</span>
            <span class="srch-sd">${x.d}</span>
          </div>`).join('')}
        <div class="srch-more">还有 3 条被截断（已到上限，想更多要细化查询）</div>
      </div>

      <div class="srch-sec">
        ${s.groups.length} 组要素
        <span class="srch-sec2">（组顺序 = 提示词顺序 · 点行可改）</span>
        ${editedCount?`<span class="srch-edn">改过 ${editedCount}</span>`:''}
        ${addedCount?`<span class="srch-edn added">加了 ${addedCount}</span>`:''}
      </div>

      <div class="srch-groups">${groupsHtml}</div>

      <button class="srch-add" onclick="startAdd()">＋ 加一项（资料里没写，但我知道要什么）</button>

      <div class="srch-sec">参考图已存进素材库 <span class="srch-sec2">（可直接当参考图）</span></div>
      <div class="srch-assets">
        ${c.assets.map(a=>`
          <div class="srch-as" onclick="toast('用这张当参考图')">
            <div class="srch-aim"><div class="srch-fig"></div></div>
            <div class="srch-ai2">${a.t}</div>
            <div class="srch-ac">${a.from}</div>
          </div>`).join('')}
      </div>

      <div class="srch-sec">当前会用的提示词 <span class="srch-sec2">（按组顺序拼 · 改完实时更新）</span></div>
      <div class="srch-live" id="livePrompt">${buildPrompt()}</div>
      ${(typeof aiFitNote === 'function') ? aiFitNote(c.elements) : ''}

      <div class="srch-warn ${miss.length?'':'ok'}">
        ${miss.length
          ? `${critMiss.length
              ? `⚠️ 缺 <b>${miss.length}</b> 项，其中 <b>${critMiss.length} 项影响最大</b>（${critMiss.map(m=>m.k).join('、')}）<br><span class="srch-why2">${s.criticalWhy || ''}</span>`
              : `⚠️ 缺 <b>${miss.length}</b> 项（${miss.map(m=>m.k).join('、')}）—— 不影响主体辨识`}
             <br><span class="srch-link" onclick="searchMore()">让我再搜一轮</span> 或点上面的行自己填。`
          : `✅ <b>${s.groups.length} 组要素全齐（${c.elements.length} 项）</b> —— 可以放心生成。`}
      </div>

      <div class="srch-acts">
        ${miss.length
          ? `<button class="srch-b" onclick="searchMore()">再搜一轮补缺</button>` : ''}
        <button class="srch-b pri" onclick="searchGenerate()">${miss.length?'先这样生成':'开始生成'}</button>
      </div>
    </div>`;
}

/* 组的折叠状态 */
let collapsedGroups = new Set();
function toggleGrp(k){
  if (collapsedGroups.has(k)) collapsedGroups.delete(k);
  else collapsedGroups.add(k);
  refreshSearchCard();
}

/* --- 要素编辑动作 --- */
function startEditElem(id){
  editingElem = id;
  refreshSearchCard();
}
function cancelElem(){
  editingElem = null;
  refreshSearchCard();
}
function saveElem(id){
  const inp = document.getElementById('inp_' + id);
  if (!inp) return;
  const v = inp.value.trim();
  const e = SEARCH_CASE.elements.find(x=>x.id===id);
  if (!e) return;
  if (!v){
    // 清空 = 变成缺项
    e.v = '— 我清空了'; e.ok = 0; e.edited = true;
  } else {
    if (!e.origV) e.origV = e.v;
    e.v = v; e.ok = 1; e.edited = true;
  }
  editingElem = null;
  refreshSearchCard();
  toast(v ? `已改成「${v}」· 提示词已更新` : '已清空 · 会提示还缺这项');
}
function revertElem(id){
  const e = SEARCH_CASE.elements.find(x=>x.id===id);
  if (!e) return;
  e.v = e.origV || '— 搜到的资料没写';
  e.ok = e.origV ? 1 : 0;
  e.edited = false;
  refreshSearchCard();
  toast('已恢复原值');
}

/* --- 新增 / 删除要素 --- */

function startAdd(){
  if (addingElem){ cancelAdd(); return; }
  const id = 'new' + Date.now();
  addingElem = id;
  SEARCH_CASE.elements.push({ id, k:'', v:'', ok:0, src:null, edited:false, adding:true });
  refreshSearchCard();
}
function cancelAdd(){
  if (!addingElem) return;
  SEARCH_CASE.elements = SEARCH_CASE.elements.filter(e=>e.id!==addingElem);
  addingElem = null;
  refreshSearchCard();
}
function saveAdd(id){
  const keyInp = document.getElementById('key_' + id);
  const valInp = document.getElementById('inp_' + id);
  const k = keyInp ? keyInp.value.trim() : '';
  const v = valInp ? valInp.value.trim() : '';
  if (!k && !v){ cancelAdd(); return; }
  if (!k){ toast('给这项起个名字（比如 饰品）'); return; }
  if (!v){ toast('填个值（比如 银色耳环）'); return; }
  const e = SEARCH_CASE.elements.find(x=>x.id===id);
  if (!e) return;
  e.k = k; e.v = v; e.ok = 1; e.addedByMe = true; e.edited = true; e.adding = false;
  addingElem = null;
  refreshSearchCard();
  toast('加了「' + k + '：' + v + '」· 提示词已更新');
}
function removeElem(id){
  const e = SEARCH_CASE.elements.find(x=>x.id===id);
  if (!e) return;
  SEARCH_CASE.elements = SEARCH_CASE.elements.filter(x=>x.id!==id);
  refreshSearchCard();
  toast('已删掉「' + e.k + '」');
}

/* 只刷新这张卡（不重绘整条消息，避免丢失滚动和动画） */
function refreshSearchCard(){
  const card = agb.querySelector('.srch');
  const host = card ? card.closest('.msg') : null;
  if (!host) return;
  const scroller = agb;
  const st = scroller.scrollTop;
  host.innerHTML = `<div class="who">智能体</div><div class="bubble">${renderSearchResult()}</div>`;
  scroller.scrollTop = st;
  // 编辑态自动聚焦
  if (editingElem){
    const inp = document.getElementById('inp_' + editingElem);
    if (inp){ inp.focus(); inp.select(); }
  }
}



/* --- 补搜 --- */
function searchMore(){
  const last = agb.lastElementChild;
  if (!last) return;
  const actHost = last.querySelector('.srch-acts') || last.querySelector('.srch-warn');
  if (actHost) actHost.innerHTML =
    `<span class="srch-loading"><span class="srch-spin"></span>补搜中：脸型 / 体型…</span>`;
  setTimeout(()=>{
    const miss = SEARCH_CASE.elements.filter(e=>!e.ok);
    SEARCH_CASE.elements.forEach((e,i)=>{
      if (!e.ok){
        // 按缺的项补上
        if (e.k === '脸型'){ e.v = '窄脸 尖下巴 高鼻梁'; e.ok = 1; e.src = '3'; }
        if (e.k === '体型'){ e.v = '纤细 身高约 168cm';  e.ok = 1; e.src = '3'; }
      }
    });
    searchStep = 3;
    refreshSearchCard();
    agb.scrollTop = agb.scrollHeight;
    toast(`补到 ${miss.length} 项 · 要素齐了`);
  }, 1400);
}

/* --- 生成 --- */
function searchGenerate(){
  const c = SEARCH_CASE;
  const miss = c.elements.filter(e=>!e.ok);
  const edited = c.elements.filter(e=>e.edited && !e.addedByMe);
  const added  = c.elements.filter(e=>e.addedByMe);
  const filled = c.elements.filter(e=>e.ok).length;

  agAdd('ai', `好，开始生成。<br><br>`
    + `<span class="srch-prompt">${buildPrompt().replace(/<div class="srch-live2">[\s\S]*$/,'')}</span><br><br>`
    + (miss.length
        ? `要素 <b>${filled} 项</b>，其中 <b>${miss.length} 项缺</b>`
          + `（${miss.map(m=>m.k).join('、')}）—— <b>这几项我会猜，不一定准</b>。<br><br>`
        : `要素 <b>${filled} 项全齐</b>。`)
    + (edited.length
        ? `其中 <b>${edited.length} 项是你改的</b>（${edited.map(m=>m.k).join('、')}），按你那份来。<br><br>`
        : ``
      )
    + (added.length
        ? `另外<b>你加了 ${added.length} 项</b>（${added.map(m=>m.k+'：'+m.v).join('、')}），资料里没有，我按你给的用。<br><br>`
        : ``)
    + `参考图用了素材库里的 2 张（asset_9f2a / asset_9f2b）。`
    + `引用来源 ${citeChip('k4',1)}`);

  setTimeout(()=>{
    window.__suppressDemoMsg = true;
    demoFill('script', 6);
    window.__suppressDemoMsg = false;
    agb.insertAdjacentHTML('beforeend',
      `<div class="msg ai"><div class="who">智能体</div><div class="bubble">`
      + `生成了 <b>6 镜</b>。<br><br>`
      + (edited.length
          ? `你改的那 <b>${edited.length} 项</b>（${edited.map(m=>m.k).join('、')}）都进去了。`
          : (miss.length
              ? `先说清楚：<b>${miss.map(m=>m.k).join('、')}是我猜的</b>，不对说一声我按你那版重出。`
              : `要素都是从搜到的资料里来的，没靠猜。看完哪镜不对直接说。`))
      + `</div></div>`);
    agb.scrollTop = agb.scrollHeight;
    toast('已生成 6 镜');
  }, 900);
}


