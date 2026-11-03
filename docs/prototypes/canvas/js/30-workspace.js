/* 30-workspace.js — 项目工作台：把真项目已有的功能填进原型位置

   边界（原型不是实现）：
   - 工作台只预演项目级流程，不调用任何后端接口
   - 任务队列、角色注入、发布都明确标注「模拟」或「占位」
   - 唯一真实的动作是复用画布已有的导出、本地修图、提示词库
   - 价格优先从 PRICE_BOOK / CAPS 读，读不到的写「未配」，不编数字

   状态有两套，别混：
   - 真项目状态：real / partial / planned
   - 原型状态：live / sim / slot
*/

/* ================= 1. 项目数据 ================= */

const WS_PROJECT = {
  n: '谁让短剧这么降智',
  ep: '第 3 集',
  kind: '短剧',
  logline: '苏晚在片场发现自己的台词被临时改掉。她当着全组把合同拍在桌上，说要么按原稿拍，要么今天停机。',
  novel: { chapters: 12, words: '1.8 万字' },
  canvas: '我的短剧 / 第 3 集'
};

const WS_STAGES = [
  {
    k: 'script', n: '剧本', s: '原著 → 提纲', st: 'real', real: '/story',
    can: ['看这一集的梗概与场次', '把一段故事拆成镜头', '回到画布按镜头改'],
    boundary: '原型只放固定文本。章节编辑、原著导入、提纲生成都未接后端。',
    next: [{ l: '拆成分镜', f: 'wsFromScript()' }, { l: '去镜头墙', f: 'wsGoShots()' }]
  },
  {
    k: 'chars', n: '角色', s: '角色卡 · 一致性', st: 'real', real: '/characters',
    can: ['看角色卡的外观、服装、避免项', '把角色引用到输入框', '按角色重画某一镜'],
    boundary: '角色卡自动注入是预演。原型不会真的把人物设定带进模型请求。',
    next: [{ l: '去生成页', f: "wsOpenStage('gen')" }, { l: '看素材库', f: 'openAssetHub()' }]
  },
  {
    k: 'shots', n: '分镜', s: '镜头表 · 参考', st: 'real', real: '/canvas · /story',
    can: ['看每一镜的状态与参考角色', '去镜头墙改顺序', '把待生成镜头排队'],
    boundary: '状态变化由原型模拟。真实现由任务完成后回写 asset。',
    next: [{ l: '打开镜头墙', f: 'wsGoShots()' }, { l: '把待生成排队', f: 'wsQueueTodo()' }]
  },
  {
    k: 'gen', n: '生成', s: '图片 · 视频 · 3D', st: 'real',
    real: '/image-gen · /motion · /video-gen · /previs · /model-3d',
    can: ['选模型、比例、数量', '引用角色与素材', '提交前看价格并过门禁'],
    boundary: '提交后只进原型任务队列，不调用模型。价格是示例，真实现从配置读。',
    next: [{ l: '打开任务中心', f: 'openTaskCenter()' }, { l: '看模型价格', f: "openModelPicker('gen')" }]
  },
  {
    k: 'edit', n: '剪辑', s: '时间线 · 字幕 · 配乐', st: 'real', real: '/clip · /subtitle · /bgm',
    can: ['看时间线、字幕、配乐的位置', '打开真合成导出', '回到画布做本地修图'],
    boundary: '剪辑与字幕面板在原型里只是入口，没有时间线编辑器。',
    next: [{ l: '打开导出', f: 'openExport()' }, { l: '人像修饰', f: 'wsOpenRetouch()' }]
  },
  {
    k: 'delivery', n: '交付', s: '导出 · 发布 · 检查', st: 'partial', real: '/publish · 导出',
    can: ['看交付清单与阻断项', '打开真合成导出', '做发布前检查'],
    boundary: '发布只做到番茄存草稿。抖音和快手是计划项。原型不会发任何内容。',
    next: [{ l: '发布前检查', f: 'wsPublishCheck()' }, { l: '打开导出', f: 'openExport()' }]
  }
];

/* 18 项真实功能，按「输入 / 制作 / 交付」归组 */
const WS_FEATURES = [
  { id: 'story', g: '输入与设定', n: '创作项目与章节', path: '/story', st: 'real', proto: 'sim', note: '工作台「剧本」页，原型放固定文本' },
  { id: 'characters', g: '输入与设定', n: '角色库与角色卡', path: '/characters', st: 'real', proto: 'sim', note: '角色页 + 输入框 @ 引用' },
  { id: 'world', g: '输入与设定', n: '世界设定与实体关系', path: '/characters（世界）', st: 'real', proto: 'slot', note: '只在功能地图标出，未做界面' },
  { id: 'style', g: '输入与设定', n: '写作风格档案', path: '/story（风格）', st: 'real', proto: 'slot', note: '待补：风格卡与引用' },
  { id: 'storyboard', g: '输入与设定', n: '分镜与镜头表', path: '/canvas', st: 'real', proto: 'live', note: '镜头墙 + 工作台分镜页' },
  { id: 'image', g: '制作', n: '生图与多模型', path: '/image-gen', st: 'real', proto: 'sim', note: '生成页 + 模型价格' },
  { id: 'to3d', g: '制作', n: '图生 3D', path: '/model-3d', st: 'real', proto: 'sim', note: '生成页切到 3D' },
  { id: 'previs', g: '制作', n: '3D 导演台', path: '/previs', st: 'real', proto: 'sim', note: '生成页切到导演台' },
  { id: 'motion', g: '制作', n: '动图与视频', path: '/motion · /video-gen', st: 'real', proto: 'sim', note: '生成页切到视频' },
  { id: 'local', g: '制作', n: '本地修图与 RAW', path: '本地', st: 'real', proto: 'live', note: '磨皮、液化、RAW 已接真像素' },
  { id: 'assets', g: '制作', n: '素材库', path: '/assets', st: 'real', proto: 'sim', note: '素材库面板，导入图用真缩略图' },
  { id: 'prompt', g: '制作', n: '提示词库', path: '画布内', st: 'real', proto: 'live', note: '顶栏「提示词库」已可用' },
  { id: 'agent', g: '制作', n: '智能体工具与 Skill', path: '/agent', st: 'real', proto: 'sim', note: '对话是模拟，工具调用不真实' },
  { id: 'tasks', g: '制作', n: '任务中心', path: '/tasks', st: 'real', proto: 'sim', note: '任务队列与推进为模拟' },
  { id: 'edit', g: '交付', n: '剪辑 / 字幕 / 配乐', path: '/clip · /subtitle · /bgm', st: 'real', proto: 'slot', note: '只保留入口，没有时间线编辑器' },
  { id: 'export', g: '交付', n: '导出合成', path: '本地', st: 'real', proto: 'live', note: '真逐层合成，可下载' },
  { id: 'publish', g: '交付', n: '发布', path: '/publish', st: 'partial', proto: 'slot', note: '真项目只做到番茄存草稿' },
  { id: 'billing', g: '交付', n: '积分与账单', path: '未建页面', st: 'planned', proto: 'sim', note: '只有内存花费与门禁记录' }
];

const WS_CHARACTERS = [
  {
    id: 'suwan', n: '苏晚', role: '女主 · 制片人', av: '晚', color: '#22d3ee',
    look: '利落黑色短发，左眼下有一颗小痣',
    outfit: '深灰双排扣西装，银扣，白衬衫',
    avoid: '避免甜妹妆、避免大波浪、避免圆领',
    prompt: '苏晚，30 岁制片人，利落黑色短发，左眼下一颗小痣，深灰双排扣西装，银扣，冷静克制。 / Su Wan, 30s producer, short black hair, beauty mark under the left eye, charcoal double-breasted suit with silver buttons, restrained.'
  },
  {
    id: 'guyan', n: '顾言', role: '男主 · 导演', av: '言', color: '#a78bfa',
    look: '短寸，眉骨高，右眉尾有一道旧疤',
    outfit: '黑色高领，深蓝工装外套',
    avoid: '避免油头、避免西装领带、避免笑',
    prompt: '顾言，35 岁导演，短寸，眉骨高，右眉尾旧疤，黑色高领，深蓝工装外套。 / Gu Yan, 35, director, buzz cut, high brow, old scar at the right eyebrow tail, black turtleneck, navy work jacket.'
  },
  {
    id: 'linxiaoman', n: '林小满', role: '配角 · 场记', av: '满', color: '#34d399',
    look: '马尾，圆框眼镜，个子小',
    outfit: '卡其色多口袋马甲，挂工作证',
    avoid: '避免浓妆、避免高跟鞋',
    prompt: '林小满，24 岁场记，马尾，圆框眼镜，卡其色多口袋马甲，工作证。 / Lin Xiaoman, 24, script supervisor, ponytail, round glasses, khaki utility vest, crew badge.'
  }
];

const WS_ASSETS = [
  { id: 'a1', n: '苏晚 · 定妆正面', kind: '角色图', cls: 0, src: '角色库', used: 2 },
  { id: 'a2', n: '苏晚 · 侧面', kind: '角色图', cls: 2, src: '角色库', used: 1 },
  { id: 'a3', n: '片场 · 走廊', kind: '场景图', cls: 1, src: '素材库', used: 3 },
  { id: 'a4', n: '合同特写', kind: '道具图', cls: 3, src: '素材库', used: 1 },
  { id: 'a5', n: '第 2 集成片', kind: '视频', cls: 4, src: '剪辑', used: 0 },
  { id: 'a6', n: '第 3 集 BGM', kind: '音频', cls: 5, src: '配乐', used: 0 }
];

const WS_STYLES = [
  { id: 'cinematic', n: '电影感', d: '低饱和，侧逆光，浅景深' },
  { id: 'drama', n: '短剧质感', d: '高对比，面部补光，节奏快' },
  { id: 'docu', n: '纪实', d: '自然光，手持感，少调色' }
];

const WS_MODELS = [
  { id: 'gpt-image-2', n: 'GPT Image 2', kind: 'image', unit: '张', pts: 14, cny: 1.4, note: '复杂服装和手部更稳', src: '已有配置' },
  { id: 'nanobanana', n: 'NanoBanana', kind: 'image', unit: '张', pts: 3, cny: 0.3, note: '便宜，适合草稿', src: '已有配置' },
  { id: 'jimeng-4', n: '即梦 4.0', kind: 'image', unit: '张', pts: 8, cny: null, note: '中文场景理解好，人民币价未配', src: '示例价' },
  { id: 'flux', n: 'Flux.1', kind: 'image', unit: '张', pts: 6, cny: null, note: '出图快，风格偏写实', src: '示例价' },
  { id: 'kling-3', n: '可灵 3.0', kind: 'video', unit: '5s', pts: 60, cny: null, note: '图生视频，按 5 秒计', src: '示例价' },
  { id: 'tripo-sr', n: 'TripoSR', kind: '3d', unit: '次', pts: 0, cny: 0, note: '本地跑，只吃电费', src: '本地' },
  { id: 'previs-local', n: '本地导演台', kind: 'previs', unit: '次', pts: 0, cny: 0, note: '摆机位，不调模型', src: '本地' }
];

/* ================= 2. 状态 ================= */

let WS = {
  stage: 'script',
  gen: {
    kind: 'image',
    model: 'gpt-image-2',
    ratio: '2:3',
    qty: 2,
    prompt: '苏晚站在片场走廊，手里捏着改过的台词页，侧逆光，背景是虚化的灯架。',
    refs: [],
    shotId: null
  }
};

let WS_TASKS = [];
let WS_TASK_SEQ = 0;
let WS_TIMER = null;
let WS_PICKER = null;
let WS_AT_TAB = 'character';
let WS_COMPOSER_REFS = [];
let WS_COMPOSER_MODEL = 'gpt-image-2';

let WS_SHOT_REFS = {
  s1: [{ kind: 'character', id: 'suwan', label: '苏晚' }, { kind: 'style', id: 'cinematic', label: '电影感' }],
  s2: [{ kind: 'character', id: 'suwan', label: '苏晚' }, { kind: 'character', id: 'guyan', label: '顾言' }],
  s3: [{ kind: 'character', id: 'suwan', label: '苏晚' }],
  s4: [{ kind: 'character', id: 'guyan', label: '顾言' }],
  s7: [{ kind: 'character', id: 'linxiaoman', label: '林小满' }],
  s10: [{ kind: 'character', id: 'suwan', label: '苏晚' }]
};

const WS_ST = {
  real: { l: '真项目已有', cls: 'real' },
  partial: { l: '部分可用', cls: 'partial' },
  planned: { l: '计划中', cls: 'planned' },
  live: { l: '原型可操作', cls: 'live' },
  sim: { l: '原型模拟', cls: 'sim' },
  slot: { l: '原型占位', cls: 'slot' }
};

/* ================= 3. 基础工具 ================= */

function wsShots() {
  if (typeof DOC === 'undefined' || !DOC.items) return [];
  return DOC.items.slice().sort((a, b) => a.order - b.order);
}
function wsModel(id) {
  return WS_MODELS.find(m => m.id === id) || WS_MODELS[0];
}
function wsChar(id) {
  return WS_CHARACTERS.find(c => c.id === id);
}
function wsStyle(id) {
  return WS_STYLES.find(s => s.id === id);
}
function wsAsset(id) {
  return WS_ASSETS.find(a => a.id === id);
}
function wsShotIndex(id) {
  return wsShots().findIndex(s => s.id === id) + 1;
}
function wsClock() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false });
}
function wsTag(k) {
  const s = WS_ST[k] || { l: k, cls: 'slot' };
  return `<span class="ws-tag ${s.cls}"><span class="ws-tag-dot"></span>${s.l}</span>`;
}
function wsBoundShots() {
  return wsShots().filter(s => (WS_SHOT_REFS[s.id] || []).length).length;
}
function wsRealShots() {
  return wsShots().filter(s => s.status === 'ok' && !s.wsSim && (s.canvas || s.thumbUrl)).length;
}
function wsActiveTasks() {
  return WS_TASKS.filter(t => t.status === 'queued' || t.status === 'run');
}
function wsSlots() {
  return document.getElementById('wsRoot');
}
function wsHostEl() {
  let h = document.getElementById('wsHost');
  if (!h) {
    h = document.createElement('div');
    h.id = 'wsHost';
    h.innerHTML = '<div id="wsRoot"></div><div id="wsPanelHost"></div>';
    document.body.appendChild(h);
  }
  return h;
}

/* ================= 4. 工作台开关 ================= */

function openWorkspace(stage) {
  if (stage) WS.stage = stage;
  if (typeof hideFloatBar === 'function') hideFloatBar();
  wsHostEl();
  wsRender();
  wsStartTicker();
}

function closeWorkspace() {
  const root = document.getElementById('wsRoot');
  if (root) root.innerHTML = '';
  const panel = document.getElementById('wsPanelHost');
  if (panel) panel.innerHTML = '';
  wsAtDone();
}

function wsOpenStage(k) {
  WS.stage = k;
  wsClosePanel();
  if (!wsSlots()) { openWorkspace(k); return; }
  wsRender();
}

function wsClosePanel() {
  const p = document.getElementById('wsPanelHost');
  if (p) p.innerHTML = '';
  WS_PICKER = null;
}

function wsPanel(html) {
  wsHostEl();
  const p = document.getElementById('wsPanelHost');
  if (p) p.innerHTML = html;
}

function wsRender() {
  const root = wsSlots();
  if (!root) return;
  const items = wsShots();
  const active = wsActiveTasks().length;
  root.innerHTML = `
    <div class="ws" onclick="if(event.target.classList.contains('ws'))closeWorkspace()">
      <div class="ws-shell">
        <header class="ws-hd">
          <div class="ws-hd-l">
            <span class="ws-kicker">项目工作台</span>
            <div class="ws-title">${WS_PROJECT.n}<span>${WS_PROJECT.ep}</span></div>
            <div class="ws-sub">${WS_PROJECT.kind} · ${items.length} 镜 · ${WS_PROJECT.canvas}</div>
          </div>
          <div class="ws-hd-r">
            <span class="ws-proto">原型预演 · 不接后端</span>
            <button class="b out" onclick="openTaskCenter()">任务中心<span id="wsTaskBadge">${active ? ' · ' + active + ' 个在跑' : ''}</span></button>
            <button class="b out" onclick="openAssetHub()">素材库</button>
            <button class="b out" onclick="openFeatureMap()">功能地图</button>
            <button class="b out" onclick="closeWorkspace()" title="关闭工作台">✕</button>
          </div>
        </header>
        <nav class="ws-stages">
          ${WS_STAGES.map(s => `
            <button class="ws-stage ${WS.stage === s.k ? 'on' : ''}" onclick="wsOpenStage('${s.k}')">
              <span class="ws-stage-dot ${s.st}" title="${WS_ST[s.st].l}"></span>
              <span class="ws-stage-txt"><b>${s.n}</b><i>${s.s}</i></span>
              ${s.st !== 'real' ? `<span class="ws-stage-flag">${s.st === 'partial' ? '部分' : '计划'}</span>` : ''}
            </button>`).join('')}
        </nav>
        <div class="ws-body">
          <aside class="ws-left">${wsLeftRail()}</aside>
          <main class="ws-main">${wsStageHtml()}</main>
          <aside class="ws-right">${wsRightRail()}</aside>
        </div>
      </div>
    </div>`;
}

function wsStageHtml() {
  switch (WS.stage) {
    case 'chars': return wsStageChars();
    case 'shots': return wsStageShots();
    case 'gen': return wsStageGen();
    case 'edit': return wsStageEdit();
    case 'delivery': return wsStageDelivery();
    default: return wsStageScript();
  }
}

/* ================= 5. 左右栏 ================= */

function wsLeftRail() {
  const items = wsShots();
  const done = items.filter(s => s.status === 'ok').length;
  const tpl = (typeof currentTplRef !== 'undefined' && currentTplRef)
    ? ((typeof TPLS !== 'undefined' ? TPLS.find(t => t.id === currentTplRef.id) : null) || { n: '模板' })
    : null;
  return `
    <div class="ws-card ws-pad">
      <div class="ws-card-h">项目</div>
      <div class="ws-cover"><span>${WS_PROJECT.kind}</span><b>${WS_PROJECT.n}</b><i>${WS_PROJECT.ep}</i></div>
      <div class="ws-kv"><span>原著</span><b>${WS_PROJECT.novel.chapters} 章 · ${WS_PROJECT.novel.words}</b></div>
      <div class="ws-kv"><span>镜头</span><b>${items.length} 镜</b></div>
      <div class="ws-kv"><span>已生成</span><b><span id="wsLeftDone">${done}</span> / ${items.length}</b></div>
      <div class="ws-kv"><span>今日花费</span><b>${money(spendToday())}</b></div>
      <div class="ws-mini-note">原型的扣费只记在内存，刷新就清空。</div>
    </div>

    <div class="ws-card ws-pad">
      <div class="ws-card-h">画布</div>
      <div class="ws-canvasrow"><span class="ws-canvasdot"></span><b>${WS_PROJECT.canvas}</b></div>
      <div class="ws-kv"><span>模式</span><b>${mode === 'shots' ? '镜头墙' : mode === 'free' ? '素材墙' : '高级'}</b></div>
      <div class="ws-kv"><span>模板</span><b>${tpl ? tpl.n + ' v' + currentTplRef.ver : '未使用'}</b></div>
      <button class="b ws-wide-b" onclick="wsGoShots()">回到镜头墙</button>
    </div>

    <div class="ws-card ws-pad">
      <div class="ws-card-h">状态标记</div>
      <div class="ws-legend">
        <div>${wsTag('real')}<span>真项目里能用</span></div>
        <div>${wsTag('partial')}<span>只做了一部分</span></div>
        <div>${wsTag('planned')}<span>还没做</span></div>
        <div>${wsTag('live')}<span>原型里可操作</span></div>
        <div>${wsTag('sim')}<span>原型里只模拟</span></div>
        <div>${wsTag('slot')}<span>原型里只占位</span></div>
      </div>
    </div>`;
}

function wsRightRail() {
  const s = WS_STAGES.find(x => x.k === WS.stage) || WS_STAGES[0];
  const items = wsShots();
  const done = items.filter(x => x.status === 'ok').length;
  const bad = items.filter(x => x.status === 'err').length;
  return `
    <div class="ws-card ws-pad">
      <div class="ws-card-h">这个阶段</div>
      <div class="ws-devt">实现标注（给开发看）</div>
      <div class="ws-path">${s.real}</div>
      <div class="ws-rail-l">原型里能做</div>
      <ul class="ws-ul">${s.can.map(x => `<li>${x}</li>`).join('')}</ul>
      <div class="ws-rail-l">边界</div>
      <div class="ws-bound">${s.boundary}</div>
      <div class="ws-rail-l">下一步</div>
      <div class="ws-rail-actions">${s.next.map(a => `<button class="b" onclick="${a.f}">${a.l}</button>`).join('')}</div>
    </div>

    <div class="ws-card ws-pad">
      <div class="ws-card-h">现在</div>
      <div class="ws-kv"><span>已生成</span><b>${done} / ${items.length}</b></div>
      <div class="ws-kv"><span>失败</span><b class="${bad ? 'ws-bad' : ''}">${bad} 镜</b></div>
      <div class="ws-kv"><span>在跑</span><b>${wsActiveTasks().length} 个任务</b></div>
      <div class="ws-kv"><span>参考绑定</span><b>${wsBoundShots()} 镜</b></div>
      <div class="ws-kv"><span>模拟产出</span><b class="${items.filter(s => s.wsSim).length ? 'ws-warn' : ''}">${items.filter(s => s.wsSim).length} 镜</b></div>
      <div class="ws-mini-note">数字从 DOC 和任务队列推导。模拟完成的镜头也计入「已生成」，但会单独标出来。</div>
    </div>`;
}

function wsRefreshRail() {
  const rail = document.querySelector('.ws-right');
  if (rail) rail.innerHTML = wsRightRail();
  if (WS.stage === 'delivery' && document.querySelector('.ws-main')) {
    const main = document.querySelector('.ws-main');
    if (main) main.innerHTML = wsStageDelivery();
  }
}

/* ================= 6. 剧本 ================= */

function wsStageScript() {
  return `
    <div class="ws-main-h">
      <div><h2>剧本与提纲</h2><div class="ws-main-s">原著怎么变成这一集的镜头</div></div>
      ${wsTag('real')}
    </div>

    <div class="ws-card ws-pad">
      <div class="ws-script-q">${WS_PROJECT.logline}</div>
      <div class="ws-script-meta">第 3 集 · 场 7 · 预计 42 秒 · 12 镜</div>
      <div class="ws-chapters">
        <span class="ws-chapter on">第 1 章 · 改词</span>
        <span class="ws-chapter">第 2 章 · 停机</span>
        <span class="ws-chapter">第 3 章 · 重拍</span>
      </div>
    </div>

    <div class="ws-sec-h">从原著到分镜</div>
    <div class="ws-flowline">
      <div class="ws-fl"><b>原著</b><span>${WS_PROJECT.novel.chapters} 章</span></div>
      <span class="ws-fl-ar">→</span>
      <div class="ws-fl"><b>提纲</b><span>3 场</span></div>
      <span class="ws-fl-ar">→</span>
      <div class="ws-fl"><b>分镜</b><span>12 镜</span></div>
      <span class="ws-fl-ar">→</span>
      <div class="ws-fl"><b>生成</b><span>图片 / 视频</span></div>
    </div>

    <div class="ws-callout">真项目里这段来自 /story 的章节与提纲。原型只放固定文本，用来预演「拆镜头」这一步。拆完会真的落到镜头墙，但不会生成图片。</div>

    <div class="ws-actions">
      <button class="b solid" onclick="wsFromScript()">拆成 12 个镜头</button>
      <button class="b" onclick="wsSlot('编辑提纲','真项目 /story 的章节编辑还没搬进原型。这里只保留入口，避免写了不生效的编辑框。')">编辑提纲</button>
      <button class="b" onclick="wsSlot('导入原著','真项目支持从小说项目导入。原型不接文件上传，也不会解析文本。')">导入原著</button>
    </div>

    <div class="ws-note">拆镜头之后，角色页和分镜页会用同一批镜头数据。改顺序去镜头墙，改参考在分镜页。</div>`;
}

function wsFromScript() {
  closeWorkspace();
  window.__suppressDemoMsg = true;
  demoFill('script');
  window.__suppressDemoMsg = false;
  const items = wsShots();
  const total = items.reduce((a, s) => a + (s.duration || 0), 0);
  const done = items.filter(s => s.status === 'ok').length;
  const todo = items.filter(s => s.status === 'todo' || s.status === 'err').length;
  agAdd('ai', `已把第 3 集拆成 <b>${items.length} 个镜头</b>。<br><br>`
    + `做了什么：生成镜头表，镜号 01 到 ${String(items.length).padStart(2, '0')}，绑定 3 个角色的出场参考。<br>`
    + `没做什么：没有生成图片，没有调用模型，没有花钱。<br>`
    + `自检：镜头时长合计 ${total.toFixed(1)} 秒，已生成 ${done} 镜，待处理 ${todo} 镜。<br>`
    + `变更规模：画布 ${items.length} 个镜头（原型模拟）。`);
  toast(`已拆成 ${items.length} 个镜头 · 没有生成图片`);
}

function wsGoShots() {
  closeWorkspace();
  if (!wsShots().length) {
    toast('还没有镜头，先在工作台拆一次');
    return;
  }
  setMode('shots');
}

/* ================= 7. 角色 ================= */

function wsStageChars() {
  return `
    <div class="ws-main-h">
      <div><h2>角色与一致性</h2><div class="ws-main-s">同一张脸，靠角色卡带进每次生成</div></div>
      ${wsTag('real')}
    </div>

    <div class="ws-intro">角色卡是生成时的默认参考。真项目里它应该自动带入，用户不用每次都描述同一个角色。原型只预演「引用」这个动作。</div>

    <div class="ws-chars">
      ${WS_CHARACTERS.map(c => wsCharCard(c)).join('')}
    </div>

    <div class="ws-actions">
      <button class="b" onclick="wsSlot('新增角色','真项目 /characters 已有角色创建。原型没有表单，避免出现填了不生效的输入框。')">新增角色</button>
      <button class="b" onclick="wsSlot('从素材提取角色','真项目里可以从参考图提取外观要素。原型没接视觉模型。')">从素材提取角色</button>
    </div>

    <div class="ws-note">每张角色卡都写了「避免什么」。负向约束和正向描述一样重要，不然模型会漂移。</div>`;
}

function wsCharCard(c) {
  const used = wsShots().filter(s => (WS_SHOT_REFS[s.id] || []).some(r => r.kind === 'character' && r.id === c.id)).length;
  return `
    <div class="ws-charcard">
      <div class="ws-charav" style="background:${c.color};color:#081015">${c.av}</div>
      <div class="ws-charbody">
        <div class="ws-charh"><b>${c.n}</b><span>${c.role}</span><i>${used} 镜在用</i></div>
        <div class="ws-charl"><span>外观</span>${c.look}</div>
        <div class="ws-charl"><span>服装</span>${c.outfit}</div>
        <div class="ws-charl avoid"><span>避免</span>${c.avoid}</div>
        <div class="ws-charactions">
          <button class="b" onclick="wsCharDetail('${c.id}')">看设定</button>
          <button class="b" onclick="wsRefCharacter('${c.id}','composer')">@ 引用到输入框</button>
          <button class="b solid" onclick="wsUseCharInGen('${c.id}')">用它生成</button>
        </div>
      </div>
    </div>`;
}

function wsRefCharacter(id, target) {
  const c = wsChar(id);
  if (!c) return;
  const ref = { kind: 'character', id: c.id, label: c.n };
  if (target === 'gen') {
    wsAddGenRef(ref);
    wsClosePanel();
    wsOpenStage('gen');
    toast('已作为生成参考：' + c.n);
    return;
  }
  wsAddComposerRef(ref);
  wsClosePanel();
  toast('已引用到输入框：' + c.n);
}

function wsUseCharInGen(id) {
  const c = wsChar(id);
  if (!c) return;
  WS.gen.kind = 'image';
  WS.gen.model = 'gpt-image-2';
  WS.gen.refs = [{ kind: 'character', id: c.id, label: c.n }];
  WS.gen.prompt = c.n + '站在片场走廊，手里捏着改过的台词页，侧逆光，背景是虚化的灯架。';
  wsClosePanel();
  if (!wsSlots()) openWorkspace('gen');
  else { WS.stage = 'gen'; wsRender(); }
  toast('已带上角色卡：' + c.n);
}

function wsCharDetail(id) {
  const c = wsChar(id);
  if (!c) return;
  const shots = wsShots().filter(s => (WS_SHOT_REFS[s.id] || []).some(r => r.kind === 'character' && r.id === c.id));
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">${c.n} · ${c.role}</div>
          <div class="inp-sub">角色卡 · 真项目对应 /characters</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          <div class="ws-chardetail-top">
            <div class="ws-charav lg" style="background:${c.color};color:#081015">${c.av}</div>
            <div>
              <div class="ws-kv"><span>外观</span><b>${c.look}</b></div>
              <div class="ws-kv"><span>服装</span><b>${c.outfit}</b></div>
              <div class="ws-kv"><span>避免</span><b class="ws-bad">${c.avoid}</b></div>
              <div class="ws-kv"><span>出场</span><b>${shots.length} 镜</b></div>
            </div>
          </div>
          <div class="ws-field-l">喂给模型的提示词</div>
          <div class="ws-promptbox">${c.prompt}</div>
          <div class="ws-field-l">出场镜头</div>
          <div class="ws-shotlinks">
            ${shots.length ? shots.map(s => `<button class="b" onclick="wsClosePanel();wsOpenStage('shots')">第 ${wsShotIndex(s.id)} 镜 · ${s.name}</button>`).join('') : '<span class="ws-empty-inline">还没有绑定镜头。</span>'}
          </div>
          <div class="ws-note">真实现里这张卡应该在生成请求里自动带上，不靠用户重复描述。原型只做引用预演。</div>
        </div>
        <div class="wsx-foot">
          <button class="b" onclick="wsCopyChar('${c.id}')">复制提示词</button>
          <span class="ws-sp"></span>
          <button class="b" onclick="wsRefCharacter('${c.id}','composer')">引用到输入框</button>
          <button class="b solid" onclick="wsUseCharInGen('${c.id}')">用它生成</button>
        </div>
      </div>
    </div>`);
}

function wsCopyChar(id) {
  const c = wsChar(id);
  if (c) wsCopy(c.prompt);
}

function wsCopy(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => toast('已复制')).catch(() => toast('复制失败，请手动选中'));
      return;
    }
  } catch (_) {}
  toast('当前浏览器不给剪贴板权限，请手动选中');
}

/* ================= 8. 分镜 ================= */

function wsStageShots() {
  const items = wsShots();
  if (!items.length) {
    return `
      <div class="ws-main-h"><div><h2>分镜</h2><div class="ws-main-s">还没有镜头</div></div>${wsTag('real')}</div>
      <div class="ws-empty">
        <div class="ws-empty-t">画布还是空的</div>
        <div class="ws-empty-d">先从剧本拆一次，或者回镜头墙手动加一镜。</div>
        <div class="ws-empty-a">
          <button class="b solid" onclick="wsFromScript()">从剧本拆镜头</button>
          <button class="b" onclick="wsGoShots()">去镜头墙</button>
        </div>
      </div>`;
  }
  const ok = items.filter(s => s.status === 'ok').length;
  const todo = items.filter(s => s.status === 'todo' || s.status === 'err').length;
  return `
    <div class="ws-main-h">
      <div><h2>分镜</h2><div class="ws-main-s">每一镜的参考，决定生成时带谁的脸</div></div>
      ${wsTag('real')}
    </div>
    <div class="ws-shotsum" id="wsShotsSummary">${items.length} 镜 · ${ok} 已生成 · ${todo} 待处理 · 参考绑定 ${wsBoundShots()} 镜</div>
    <div class="ws-actions">
      <button class="b" onclick="wsGoShots()">去镜头墙改顺序</button>
      <button class="b" onclick="wsQueueTodo()">把待处理镜头排队</button>
      <button class="b" onclick="wsSlot('按角色统一重画','真项目里可以按角色筛选镜头后批量重画。原型没有做筛选和批量参数。')">按角色重画</button>
    </div>
    <div class="ws-shotlist">
      ${items.map((s, i) => wsShotRow(s, i)).join('')}
    </div>
    <div class="ws-note">参考列是占位数据。真实现里由角色卡和素材库自动注入，不需要每镜手选。</div>`;
}

function wsShotRow(s, i) {
  const refs = WS_SHOT_REFS[s.id] || [];
  return `
    <div class="ws-shotrow ${s.status}" data-wsshot="${s.id}">
      <span class="ws-shotno">${String(i + 1).padStart(2, '0')}</span>
      <span class="stt ${s.status}"></span>
      <span class="ws-shotnm">${esc(s.name)}</span>
      <span class="ws-shotd">${s.duration > 0 ? s.duration.toFixed(1) + 's' : '—'}</span>
      <span class="ws-shotrefs">${refs.length ? refs.slice(0, 3).map(r => `<span class="ws-ref sm">${esc(r.label)}</span>`).join('') + (refs.length > 3 ? `<span class="ws-ref sm">+${refs.length - 3}</span>` : '') : '<span class="ws-empty-inline">没有参考</span>'}</span>
      <span class="ws-shotstatus">${s.wsSim ? '已生成（模拟）' : wsShotStatusLabel(s.status)}</span>
      <span class="ws-shota">
        <button class="b" onclick="wsOpenShotRefs('${s.id}')">参考</button>
        <button class="b" onclick="wsRegenShot('${s.id}')">重画</button>
      </span>
    </div>`;
}

function wsShotStatusLabel(st) {
  return st === 'ok' ? '已生成' : st === 'run' ? '生成中' : st === 'err' ? '失败' : '待生成';
}

function wsRegenShot(id) {
  const s = wsShots().find(x => x.id === id);
  if (!s) return;
  WS.gen.kind = 'image';
  WS.gen.model = 'gpt-image-2';
  WS.gen.qty = 1;
  WS.gen.shotId = id;
  WS.gen.prompt = `${s.name}，${(WS_SHOT_REFS[id] || []).map(r => r.label).join('、') || '保持原设定'}，画面连贯，光线一致。`;
  WS.gen.refs = (WS_SHOT_REFS[id] || []).slice();
  wsOpenStage('gen');
  toast('已带出第 ' + wsShotIndex(id) + ' 镜的参考');
}

function wsClearGenTarget() {
  WS.gen.shotId = null;
  wsRender();
}

function wsOpenShotRefs(shotId) {
  WS_PICKER = { type: 'shot', shotId };
  wsPanel(wsRefPickerHtml());
}

/* ================= 9. 生成 ================= */

function wsStageGen() {
  const g = WS.gen;
  const m = wsModel(g.model);
  const cost = wsGenCost();
  const shot = g.shotId ? wsShots().find(s => s.id === g.shotId) : null;
  const kinds = [['image', '图片'], ['video', '视频'], ['3d', '3D'], ['previs', '导演台']];
  return `
    <div class="ws-main-h">
      <div><h2>生成</h2><div class="ws-main-s">选模型，带参考，先看价再过门禁</div></div>
      ${wsTag('real')}
    </div>

    ${shot ? `<div class="ws-target">正在重画 <b>第 ${wsShotIndex(shot.id)} 镜 · ${esc(shot.name)}</b><button class="b" onclick="wsClearGenTarget()">取消指定</button></div>` : ''}

    <div class="ws-kinds">
      ${kinds.map(([k, n]) => `<button class="ws-kind ${g.kind === k ? 'on' : ''}" onclick="wsGenKind('${k}')">${n}</button>`).join('')}
    </div>

    <div class="ws-gen-grid">
      <div class="ws-card ws-pad">
        <div class="ws-field-l">模型</div>
        <div class="ws-models">
          ${WS_MODELS.filter(x => x.kind === g.kind).map(x => `
            <button class="ws-model ${x.id === g.model ? 'on' : ''}" onclick="wsGenModel('${x.id}')">
              <span class="ws-model-n">${x.n}</span>
              <span class="ws-model-p">${x.pts ? '⚡' + x.pts + '/' + x.unit : '免费'}</span>
              <span class="ws-model-d">${x.note}</span>
              <span class="ws-model-s">${x.src}</span>
            </button>`).join('')}
        </div>

        <div class="ws-field-l" style="margin-top:14px">提示词</div>
        <textarea id="wsGenPrompt" class="ws-ta" rows="5" placeholder="写清楚要生成什么，带上角色和场景" oninput="WS.gen.prompt=this.value">${esc(g.prompt)}</textarea>

        <div class="ws-fieldrow">
          <button class="ws-chip" onclick="wsGenCycle('ratio')">比例 ${g.ratio} <span class="ws-caret">▾</span></button>
          ${g.kind === 'image' ? `<button class="ws-chip" onclick="wsGenCycle('qty')">数量 ${g.qty} <span class="ws-caret">▾</span></button>` : ''}
          <button class="ws-chip" onclick="wsPickGenRefs()">@ 参考${g.refs.length ? ' ' + g.refs.length : ''}</button>
        </div>
        <div id="wsGenRefs" class="ws-genrefs">${wsGenRefsInline()}</div>
      </div>

      <div class="ws-card ws-pad ws-costbox">
        <div class="ws-field-l">这次要花</div>
        <div class="ws-bigcost">${cost ? '⚡' + cost : '免费'}</div>
        <div class="ws-costsub">${wsCostSub(m, g)}</div>
        <div class="ws-div"></div>
        <div class="ws-kv"><span>模型</span><b>${m.n}</b></div>
        <div class="ws-kv"><span>用途</span><b>${shot ? '重画镜头' : '新生成'}</b></div>
        <div class="ws-kv"><span>参考</span><b>${g.refs.length ? g.refs.length + ' 项' : '无'}</b></div>
        <div class="ws-kv"><span>预估耗时</span><b>${wsEtaText(g)}</b></div>
        <div class="ws-div"></div>
        <button class="b solid ws-submit" onclick="wsGenSubmit()">${cost ? '过门禁并提交' : '直接提交'}</button>
        <div class="ws-costnote">原型模拟：只进任务队列，不调用模型，不产生像素。</div>
      </div>
    </div>

    <div class="ws-sec-h">排队中 <span id="wsGenTasks" class="ws-sec-r">${wsTaskMini()}</span></div>`;
}

function wsGenKind(k) {
  WS.gen.kind = k;
  const first = WS_MODELS.find(m => m.kind === k);
  WS.gen.model = first ? first.id : WS_MODELS[0].id;
  WS.gen.qty = 1;
  wsRender();
}

function wsGenModel(id) {
  const m = wsModel(id);
  WS.gen.model = m.id;
  WS.gen.kind = m.kind;
  wsRender();
}

function wsGenCycle(field) {
  if (field === 'ratio') {
    const arr = ['2:3', '1:1', '3:4', '16:9'];
    WS.gen.ratio = arr[(arr.indexOf(WS.gen.ratio) + 1) % arr.length];
  } else if (field === 'qty') {
    const arr = [1, 2, 4];
    WS.gen.qty = arr[(arr.indexOf(WS.gen.qty) + 1) % arr.length];
  }
  wsRender();
}

function wsGenCost() {
  const m = wsModel(WS.gen.model);
  return m.pts * (WS.gen.qty || 1);
}

function wsCostSub(m, g) {
  const parts = [];
  if (m.pts) parts.push(`⚡${m.pts} × ${g.qty} ${m.unit}`);
  else parts.push('本地处理，不扣积分');
  if (m.cny != null) parts.push(`约 ¥${(m.cny * g.qty).toFixed(2)}`);
  else parts.push('人民币价未配');
  if (m.src === '示例价') parts.push('示例价，真实现从配置读');
  return parts.join(' · ');
}

function wsEtaText(g) {
  if (g.kind === 'video') return '约 45 秒（示例）';
  if (g.kind === '3d') return '约 12 秒（本地）';
  if (g.kind === 'previs') return '约 3 秒（本地）';
  return '约 ' + (g.qty * 2) + ' 秒（模拟）';
}

function wsTaskMini() {
  const active = wsActiveTasks();
  return active.length
    ? `${active.length} 个任务在跑 · <button class="ws-link" onclick="openTaskCenter()">去任务中心</button>`
    : `没有排队任务 · <button class="ws-link" onclick="openTaskCenter()">打开任务中心</button>`;
}

function wsGenRefsInline() {
  const refs = WS.gen.refs || [];
  if (!refs.length) return '<span class="ws-empty-inline">还没有参考。点「@ 参考」加角色、素材或风格。</span>';
  return refs.map(r => `<span class="ws-ref">${esc(r.label)}<button class="ws-ref-x" onclick="wsGenRemoveRef('${r.kind}','${r.id}')">✕</button></span>`).join('');
}

function wsAddGenRef(ref) {
  if (!WS.gen.refs.some(r => r.kind === ref.kind && r.id === ref.id)) {
    WS.gen.refs.push(ref);
  }
  const el = document.getElementById('wsGenRefs');
  if (el) el.innerHTML = wsGenRefsInline();
}

function wsGenRemoveRef(kind, id) {
  WS.gen.refs = WS.gen.refs.filter(r => !(r.kind === kind && r.id === id));
  const el = document.getElementById('wsGenRefs');
  if (el) el.innerHTML = wsGenRefsInline();
}

function wsPickGenRefs() {
  WS_PICKER = { type: 'gen' };
  wsPanel(wsRefPickerHtml());
}

async function wsGenSubmit() {
  const g = WS.gen;
  const promptEl = document.getElementById('wsGenPrompt');
  const prompt = (promptEl ? promptEl.value : g.prompt || '').trim();
  if (!prompt) {
    toast('先写一句要生成什么');
    if (promptEl) promptEl.focus();
    return;
  }
  g.prompt = prompt;
  const m = wsModel(g.model);
  const cost = wsGenCost();
  const shot = g.shotId ? wsShots().find(s => s.id === g.shotId) : null;
  const kindName = g.kind === 'image' ? '图片' : g.kind === 'video' ? '视频' : g.kind === '3d' ? '3D' : '导演台预演';
  const title = shot
    ? `重画第 ${wsShotIndex(shot.id)} 镜 · ${shot.name}`
    : g.kind === 'image' ? `生成 ${g.qty} 张图片` : `生成${kindName}`;
  const plan = [
    `类型：${kindName} · 模型：${m.n}`,
    `参考：${g.refs.length ? g.refs.map(r => r.label).join('、') : '无'}`,
    shot ? `用途：重画第 ${wsShotIndex(shot.id)} 镜` : '用途：新增内容',
    '结果：进入原型任务队列，由模拟任务推进'
  ];
  if (cost > GATE_COST_THRESHOLD) {
    const ok = await requestGate({
      kind: g.kind === '3d' ? '3d' : g.kind === 'previs' ? 'previs' : shot ? 'regen' : 'batch-gen',
      cost,
      title,
      plan,
      irreversible: !!shot,
      why: shot ? '重画会换掉这一镜现有的脸和构图，不可撤销' : '一次生成多份，跑起来就收不住'
    });
    if (!ok) {
      toast('已取消 · 没花钱');
      return;
    }
  }
  wsQueueTask({
    title, kind: g.kind, model: m.id, cost, qty: g.qty,
    refs: g.refs.slice(), shotId: shot ? shot.id : null, gated: cost > GATE_COST_THRESHOLD
  });
  wsRender();
  toast(`已进入任务中心 · ${title}`);
}

/* ================= 10. 参考选择器 ================= */

function wsRefPickerHtml() {
  const t = WS_PICKER || { type: 'gen' };
  let title = '添加参考';
  let sub = '角色、素材、风格会被带进这次生成。真实现里角色卡自动带入，不需要每次手选。';
  if (t.type === 'shot') {
    const s = wsShots().find(x => x.id === t.shotId);
    title = s ? `第 ${wsShotIndex(t.shotId)} 镜 · 参考` : '镜头参考';
    sub = '这些参考会跟着这一镜走。真实现由角色卡和素材库自动注入。';
  }
  return `
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">${title}</div>
          <div class="inp-sub">${sub}</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body" id="wsPickerBody">${wsRefPickerBody()}</div>
        <div class="wsx-foot">
          <span class="ws-footnote">原型引用只改界面，不会发给模型。</span>
          <button class="b solid" onclick="wsClosePanel()">完成</button>
        </div>
      </div>
    </div>`;
}

function wsRefPickerBody() {
  const t = WS_PICKER || { type: 'gen' };
  const sel = t.type === 'shot' ? (WS_SHOT_REFS[t.shotId] || []) : WS.gen.refs;
  const isOn = (k, id) => sel.some(r => r.kind === k && r.id === id);
  const row = (k, id, label, sub, color) => `
    <button class="ws-pickrow ${isOn(k, id) ? 'on' : ''}" onclick="wsPickerToggle('${k}','${id}')">
      <span class="ws-pickav" style="background:${color || 'var(--s3)'};color:${color ? '#081015' : 'var(--tx2)'}">${label.slice(0, 1)}</span>
      <span class="ws-pickb"><b>${esc(label)}</b><i>${esc(sub)}</i></span>
      <span class="ws-pickc">${isOn(k, id) ? '已引用' : '+'}</span>
    </button>`;
  return `
    <div class="ws-picksec">角色</div>
    ${WS_CHARACTERS.map(c => row('character', c.id, c.n, c.role, c.color)).join('')}
    <div class="ws-picksec">素材</div>
    ${WS_ASSETS.map(a => row('asset', a.id, a.n, a.kind + ' · ' + a.src)).join('')}
    <div class="ws-picksec">风格</div>
    ${WS_STYLES.map(s => row('style', s.id, s.n, s.d)).join('')}`;
}

function wsPickerToggle(kind, id) {
  const t = WS_PICKER || { type: 'gen' };
  const arr = t.type === 'shot'
    ? (WS_SHOT_REFS[t.shotId] || (WS_SHOT_REFS[t.shotId] = []))
    : WS.gen.refs;
  const idx = arr.findIndex(r => r.kind === kind && r.id === id);
  if (idx >= 0) {
    arr.splice(idx, 1);
  } else {
    const label = kind === 'character' ? (wsChar(id) || {}).n
      : kind === 'asset' ? (wsAsset(id) || {}).n
      : (wsStyle(id) || {}).n;
    if (label) arr.push({ kind, id, label });
  }
  const body = document.getElementById('wsPickerBody');
  if (body) body.innerHTML = wsRefPickerBody();
  if (t.type === 'shot') {
    if (typeof renderShots === 'function' && mode === 'shots') renderShots();
    if (wsSlots() && WS.stage === 'shots') wsRender();
  } else {
    const el = document.getElementById('wsGenRefs');
    if (el) el.innerHTML = wsGenRefsInline();
  }
}

/* ================= 11. 素材库 ================= */

function openAssetHub() {
  const docItems = wsShots().filter(s => s.thumbUrl);
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w wsx-wide">
        <div class="inp-hd">
          <div class="inp-t">素材库</div>
          <div class="inp-sub">本画布的导入图在上，占位素材在下。真项目对应 /assets。</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          ${docItems.length ? `<div class="ws-picksec">本画布的真图</div>
            <div class="ws-assets">
              ${docItems.map(s => `
                <button class="ws-asset" onclick="wsAssetDetail('${s.id}')">
                  <span class="ws-asset-th" style="background-image:url(&quot;${s.thumbUrl}&quot;);background-size:cover;background-position:center"></span>
                  <span class="ws-asset-n">${esc(s.name)}</span>
                  <span class="ws-asset-m">${s.realW || (s.canvas ? s.canvas.width : '?')}×${s.realH || (s.canvas ? s.canvas.height : '?')} · 真图</span>
                </button>`).join('')}
            </div>` : `<div class="ws-empty-inline">本画布还没有导入真图。顶栏的导入按钮可以把 JPG / PNG / RAW 带进来。</div>`}
          <div class="ws-picksec">占位素材</div>
          <div class="ws-assets">
            ${WS_ASSETS.map(a => wsAssetCard(a)).join('')}
          </div>
          <div class="ws-note">占位素材不是真实产出，只用来预演「引用某张参考图」的交互。真项目里它们来自素材库。</div>
        </div>
        <div class="wsx-foot">
          <span class="ws-footnote">导入图可以引用到输入框，但原型不会把它发给模型。</span>
          <button class="b" onclick="wsSlot('上传素材','真项目 /assets 有上传与素材管理。原型不接文件上传。')">上传素材</button>
          <button class="b solid" onclick="wsClosePanel()">完成</button>
        </div>
      </div>
    </div>`);
}

function wsAssetCard(a) {
  return `
    <button class="ws-asset" onclick="wsAssetDetail('${a.id}')">
      <span class="ws-asset-th" style="background:${BG[a.cls]}">
        <span class="ws-asset-k">${a.kind}</span>
      </span>
      <span class="ws-asset-n">${a.n}</span>
      <span class="ws-asset-m">${a.src} · 用过 ${a.used} 次</span>
    </button>`;
}

function wsAssetDetail(id) {
  const doc = typeof DOC !== 'undefined' ? DOC.items.find(x => x.id === id) : null;
  const a = doc ? null : wsAsset(id);
  if (!doc && !a) return;
  const name = doc ? doc.name : a.n;
  const kind = doc ? '画布图片' : a.kind;
  const src = doc ? '本画布' : a.src;
  const dims = doc ? `${doc.realW || (doc.canvas ? doc.canvas.width : '?')}×${doc.realH || (doc.canvas ? doc.canvas.height : '?')}` : '占位素材';
  const used = doc ? wsShots().filter(s => s === doc).length : a.used;
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">${esc(name)}</div>
          <div class="inp-sub">${kind} · ${src}</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          <div class="ws-asset-big">
            ${doc
              ? `<img src="${doc.thumbUrl}" alt="${esc(name)}">`
              : `<div class="ws-asset-big-ph" style="background:${BG[a.cls]}"><span>${kind}</span></div>`}
          </div>
          <div class="ws-kv"><span>尺寸</span><b>${dims}</b></div>
          <div class="ws-kv"><span>来源</span><b>${src}</b></div>
          <div class="ws-kv"><span>使用</span><b>${used} 次</b></div>
          ${doc ? '<div class="ws-note">这张图有真实像素，可以进本地修图、图层和导出。</div>' : '<div class="ws-note">这张是占位素材，没有真实像素。真项目里才来自素材库。</div>'}
        </div>
        <div class="wsx-foot">
          <button class="b" onclick="wsAssetToComposer('${doc ? doc.id : a.id}')">引用到输入框</button>
          <button class="b solid" onclick="wsAssetToGen('${doc ? doc.id : a.id}')">作为生成参考</button>
        </div>
      </div>
    </div>`);
}

function wsAssetLabel(id) {
  if (typeof DOC !== 'undefined') {
    const d = DOC.items.find(x => x.id === id);
    if (d) return d.name;
  }
  const a = wsAsset(id);
  return a ? a.n : '';
}

function wsAssetToComposer(id) {
  const label = wsAssetLabel(id);
  if (!label) return;
  wsAddComposerRef({ kind: 'asset', id, label });
  wsClosePanel();
}

function wsAssetToGen(id) {
  const label = wsAssetLabel(id);
  if (!label) return;
  wsUseAssetInGen(id, label);
}

function wsUseAssetInGen(id, name) {
  WS.gen.kind = 'image';
  if (wsModel(WS.gen.model).kind !== 'image') WS.gen.model = 'gpt-image-2';
  WS.gen.refs = [{ kind: 'asset', id, label: name }];
  wsClosePanel();
  if (!wsSlots()) openWorkspace('gen');
  else { WS.stage = 'gen'; wsRender(); }
  toast('已作为生成参考：' + name);
}

/* ================= 12. 模型选择 ================= */

function openModelPicker(scope) {
  const cur = scope === 'composer' ? WS_COMPOSER_MODEL : WS.gen.model;
  const groups = [['image', '图片'], ['video', '视频'], ['3d', '3D'], ['previs', '导演台']];
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">模型与价格</div>
          <div class="inp-sub">积分按能力配置读，人民币价读 PRICE_BOOK。读不到的写「未配」。</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          ${groups.map(([k, n]) => `
            <div class="ws-picksec">${n}</div>
            ${WS_MODELS.filter(m => m.kind === k).map(m => `
              <button class="ws-modelrow ${m.id === cur ? 'on' : ''}" onclick="wsPickModel('${m.id}','${scope || 'gen'}')">
                <span class="ws-mr-n">${m.n}</span>
                <span class="ws-mr-p">${m.pts ? '⚡' + m.pts + '/' + m.unit : '免费'}</span>
                <span class="ws-mr-cny">${m.cny == null ? '人民币价未配' : money(m.cny) + '/' + m.unit}</span>
                <span class="ws-mr-note">${m.note}</span>
                <span class="ws-mr-src">${m.src}</span>
              </button>`).join('')}`).join('')}
          <div class="ws-note">NanoBanana 和 GPT Image 2 的价格来自已有配置。即梦、Flux、可灵的积分是示例，真实现要写进配置，不能写死在界面。</div>
        </div>
        <div class="wsx-foot">
          <span class="ws-footnote">换模型会立刻改价格，不存在「显示一个价、扣另一个价」。</span>
          <button class="b solid" onclick="wsClosePanel()">完成</button>
        </div>
      </div>
    </div>`);
}

function wsPickModel(id, scope) {
  const m = wsModel(id);
  if (scope === 'composer') {
    WS_COMPOSER_MODEL = m.id;
    WS.gen.kind = m.kind;
    WS.gen.model = m.id;
    wsUpdateComposerChips();
    wsClosePanel();
    toast('输入框模型改为 ' + m.n);
    return;
  }
  WS.gen.kind = m.kind;
  WS.gen.model = m.id;
  WS.gen.qty = 1;
  wsClosePanel();
  if (wsSlots()) wsRender();
  toast('生成模型改为 ' + m.n);
}

/* ================= 13. 任务队列 ================= */

function wsQueueTask(o) {
  const t = {
    id: 't' + (++WS_TASK_SEQ),
    title: o.title,
    kind: o.kind || 'image',
    model: o.model || 'gpt-image-2',
    cost: o.cost || 0,
    qty: o.qty || 1,
    refs: (o.refs || []).slice(),
    shotId: o.shotId || null,
    gated: !!o.gated,
    status: 'queued',
    progress: 0,
    createdAt: Date.now(),
    doneAt: null
  };
  WS_TASKS.unshift(t);
  if (t.shotId) {
    const s = DOC.items.find(x => x.id === t.shotId);
    if (s) s.status = 'run';
    if (mode === 'shots') renderShots();
  }
  wsStartTicker();
  wsRefreshRail();
  return t;
}

function wsStartTicker() {
  if (WS_TIMER) return;
  WS_TIMER = setInterval(wsTick, 900);
}

function wsTick() {
  const active = wsActiveTasks();
  if (!active.length) {
    clearInterval(WS_TIMER);
    WS_TIMER = null;
    return;
  }
  active.forEach(t => {
    if (t.status === 'queued') {
      t.status = 'run';
    } else {
      t.progress = Math.min(100, t.progress + (t.kind === 'video' ? 12 : 25));
      if (t.progress >= 100) wsTaskDone(t);
    }
  });
  wsRefreshTasks();
}

function wsTaskDone(t) {
  if (t.status === 'done') return;
  t.status = 'done';
  t.progress = 100;
  t.doneAt = Date.now();
  const m = wsModel(t.model);
  const idx = t.shotId ? wsShotIndex(t.shotId) : 0;
  if (t.shotId) {
    const s = DOC.items.find(x => x.id === t.shotId);
    if (s) {
      s.status = 'ok';
      s.wsSim = true;
    }
    if (mode === 'shots') renderShots();
    const row = document.querySelector(`[data-wsshot="${t.shotId}"]`);
    if (row) {
      row.classList.remove('run', 'todo', 'err');
      row.classList.add('ok', 'sim');
      const dot = row.querySelector('.stt');
      if (dot) dot.className = 'stt ok';
      const st = row.querySelector('.ws-shotstatus');
      if (st) st.textContent = '已生成（模拟）';
    }
    const leftDone = document.getElementById('wsLeftDone');
    if (leftDone) leftDone.textContent = String(wsShots().filter(s => s.status === 'ok').length);
    const summary = document.getElementById('wsShotsSummary');
    if (summary) {
      const items = wsShots();
      const ok = items.filter(s => s.status === 'ok').length;
      const todo = items.filter(s => s.status === 'todo' || s.status === 'err').length;
      const sim = items.filter(s => s.wsSim).length;
      summary.textContent = `${items.length} 镜 · ${ok} 已生成 · ${todo} 待处理 · ${sim} 模拟 · 参考绑定 ${wsBoundShots()} 镜`;
    }
  }
  if (typeof PROD_LOG !== 'undefined') {
    PROD_LOG.push({
      at: wsClock(),
      kind: 'gen',
      shot: idx || undefined,
      title: t.title,
      model: m.n,
      cost: t.cost,
      ms: Date.now() - t.createdAt,
      status: 'ok',
      detail: '原型模拟完成，没有调用真实模型'
    });
  }
  if (document.getElementById('boardPane') && typeof renderBoard === 'function') renderBoard();
  wsRefreshTasks();
  wsRefreshRail();
  toast(`任务完成 · ${t.title}（模拟）`);
  if (typeof agAdd === 'function') {
    agAdd('ai', `<b>${esc(t.title)}</b> 完成（原型模拟）。<br><br>`
      + `做了什么：任务 ${t.id} 走完队列${idx ? '，第 ' + idx + ' 镜标成已生成' : ''}，制作实况新增 1 条。<br>`
      + `没做什么：没有调用真实模型，没有生成像素，也没有扣真实积分。第 ${idx || '—'} 镜现在标的是「模拟」，不是真产出。<br>`
      + `自检：${t.gated ? '门禁已批准' : '未触发门禁'}，成本 ⚡${t.cost}，状态 done。<br>`
      + `变更规模：${idx ? '1 个镜头状态' : '0 个镜头'}，制作实况 +1 条。`);
  }
}

function wsRefreshTasks() {
  const list = document.getElementById('wsTaskList');
  if (list) list.innerHTML = wsTaskListHtml();
  const sum = document.getElementById('wsTaskSum');
  if (sum) sum.innerHTML = wsTaskSumHtml();
  const badge = document.getElementById('wsTaskBadge');
  if (badge) {
    const n = wsActiveTasks().length;
    badge.textContent = n ? ' · ' + n + ' 个在跑' : '';
  }
  const mini = document.getElementById('wsGenTasks');
  if (mini) mini.innerHTML = wsTaskMini();
}

function wsTaskStatus(st) {
  const map = {
    queued: '排队中', run: '生成中', done: '已完成（模拟）',
    failed: '失败', canceled: '已取消', retried: '已重试'
  };
  return map[st] || st;
}

function wsTaskSumHtml() {
  const done = WS_TASKS.filter(t => t.status === 'done');
  const active = wsActiveTasks();
  const canceled = WS_TASKS.filter(t => t.status === 'canceled');
  const spent = done.reduce((a, t) => a + t.cost, 0);
  return `
    <div class="ws-sumcell"><span>在跑</span><b>${active.length}</b></div>
    <div class="ws-sumcell"><span>已完成（模拟）</span><b>${done.length}</b></div>
    <div class="ws-sumcell"><span>已取消</span><b>${canceled.length}</b></div>
    <div class="ws-sumcell"><span>预估花费</span><b class="ws-ac">⚡${spent}</b></div>`;
}

function wsTaskListHtml() {
  if (!WS_TASKS.length) {
    return `
      <div class="ws-empty">
        <div class="ws-empty-t">还没有任务</div>
        <div class="ws-empty-d">生成页提交后会排到这里。原型不会真的生成，只预演排队、门禁、完成回写。</div>
        <div class="ws-empty-a">
          <button class="b solid" onclick="wsClosePanel();wsOpenStage('gen')">去生成页</button>
          <button class="b" onclick="wsClosePanel();wsQueueTodo()">把待处理镜头排队</button>
        </div>
      </div>`;
  }
  return WS_TASKS.map(t => {
    const m = wsModel(t.model);
    const idx = t.shotId ? wsShotIndex(t.shotId) : 0;
    const canCancel = t.status === 'queued' || t.status === 'run';
    const canRetry = t.status === 'done' || t.status === 'failed' || t.status === 'canceled';
    return `
      <div class="ws-task ${t.status}">
        <span class="ws-task-ic">▣</span>
        <div class="ws-task-body">
          <div class="ws-task-h"><b>${esc(t.title)}</b><span class="ws-task-st">${wsTaskStatus(t.status)}</span></div>
          <div class="ws-task-m">${m.n} · 预估 ⚡${t.cost} · ${t.refs.length} 个参考${idx ? ' · 第 ' + idx + ' 镜' : ''}${t.gated ? ' · 已过门禁' : ''}</div>
          <div class="ws-prog"><i style="width:${t.progress}%"></i></div>
        </div>
        <div class="ws-task-a">
          ${canCancel ? `<button class="b" onclick="wsCancelTask('${t.id}')">取消</button>` : ''}
          ${canRetry ? `<button class="b" onclick="wsRetryTask('${t.id}')">重试</button>` : ''}
        </div>
      </div>`;
  }).join('');
}

function openTaskCenter() {
  wsHostEl();
  const active = wsActiveTasks().length;
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w wsx-wide">
        <div class="inp-hd">
          <div class="inp-t">任务中心 <span class="ws-proto sm">原型模拟</span></div>
          <div class="inp-sub">${active ? active + ' 个在跑 · ' : ''}任务在后台推进，关掉面板也不会停。</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="ws-task-sum" id="wsTaskSum">${wsTaskSumHtml()}</div>
        <div class="wsx-body" id="wsTaskList">${wsTaskListHtml()}</div>
        <div class="wsx-foot">
          <span class="ws-footnote">任务都是原型模拟，不调用模型、不扣真实积分。「预估花费」只是按模型价 × 数量算出来的。取消的任务不计入。</span>
          <button class="b solid" onclick="wsClosePanel()">关闭</button>
        </div>
      </div>
    </div>`);
}

function wsCancelTask(id) {
  const t = WS_TASKS.find(x => x.id === id);
  if (!t || (t.status !== 'queued' && t.status !== 'run')) return;
  t.status = 'canceled';
  if (t.shotId) {
    const s = DOC.items.find(x => x.id === t.shotId);
    if (s && s.status === 'run') s.status = 'todo';
    if (mode === 'shots') renderShots();
  }
  wsRefreshTasks();
  toast('任务已取消 · 这一单不算完成花费');
}

async function wsRetryTask(id) {
  const t = WS_TASKS.find(x => x.id === id);
  if (!t) return;
  if (t.cost > GATE_COST_THRESHOLD) {
    const ok = await requestGate({
      kind: 'regen',
      cost: t.cost,
      title: '重试 · ' + t.title,
      plan: ['重新排队同一个任务', `模型：${wsModel(t.model).n}`, `参考：${t.refs.length} 项`],
      irreversible: false,
      why: '重试会再跑一次模型，按同样的价格再花一次'
    });
    if (!ok) {
      toast('已取消 · 没花钱');
      return;
    }
  }
  t.status = 'retried';
  wsQueueTask({
    title: t.title, kind: t.kind, model: t.model, cost: t.cost, qty: t.qty,
    refs: t.refs, shotId: t.shotId, gated: t.cost > GATE_COST_THRESHOLD
  });
  wsRefreshTasks();
  toast('已重新排队 · ' + t.title);
}

async function wsQueueTodo() {
  const items = wsShots().filter(s => s.status === 'todo' || s.status === 'err');
  if (!items.length) {
    toast('没有待处理或失败的镜头');
    return;
  }
  const m = wsModel('gpt-image-2');
  const cost = m.pts * items.length;
  if (cost > GATE_COST_THRESHOLD) {
    const ok = await requestGate({
      kind: 'batch-gen',
      cost,
      title: `把 ${items.length} 个镜头排队生成`,
      plan: items.map(s => `第 ${wsShotIndex(s.id)} 镜 ${s.name}`).concat(`模型：${m.n}`),
      irreversible: false,
      why: '一次批量重画，花的是真钱'
    });
    if (!ok) {
      toast('已取消 · 没花钱');
      return;
    }
  }
  items.forEach(s => {
    wsQueueTask({
      title: `第 ${wsShotIndex(s.id)} 镜 ${s.name}`,
      kind: 'image',
      model: m.id,
      cost: m.pts,
      qty: 1,
      refs: (WS_SHOT_REFS[s.id] || []).slice(),
      shotId: s.id,
      gated: cost > GATE_COST_THRESHOLD
    });
  });
  if (wsSlots()) wsRender();
  openTaskCenter();
  toast(`已排队 ${items.length} 个镜头`);
}

/* ================= 14. 剪辑 ================= */

function wsStageEdit() {
  return `
    <div class="ws-main-h">
      <div><h2>剪辑与声音</h2><div class="ws-main-s">镜头之后还有时间线、字幕和配乐</div></div>
      ${wsTag('real')}
    </div>

    <div class="ws-editlist">
      ${wsEditRow('时间线', '按镜头顺序拼，拖边界改时长', 'real', 'slot', '真项目的剪辑页还没搬进原型。这里不画假时间线。', 'wsSlot(\'剪辑时间线\',\'真项目 /clip 有时间线与合成。原型没有时间线编辑器，避免做成假的可拖拽控件。\')')}
      ${wsEditRow('字幕', '识别台词，逐句校对', 'real', 'slot', '字幕需要真实音频和识别结果，原型不造假字幕。', 'wsSlot(\'字幕\',\'真项目 /subtitle 有字幕编辑。原型没有音频，也没有识别结果，所以不展示假字幕。\')')}
      ${wsEditRow('配乐', '选曲、调音量、对节奏', 'real', 'slot', 'AI 听不到声音，选曲必须人试听。原型只留入口。', 'wsSlot(\'配乐\',\'真项目 /bgm 有配乐选择。好不好听必须人来判断，原型不会替你选。\')')}
      ${wsEditRow('本地修图', '磨皮、液化、RAW、画质', 'real', 'live', '这条已经接了真像素，可以真的改图。', 'wsOpenRetouch()')}
    </div>

    <div class="ws-actions">
      <button class="b solid" onclick="openExport()">打开导出</button>
      <button class="b" onclick="wsGoShots()">回镜头墙</button>
    </div>

    <div class="ws-note">剪辑、字幕、配乐在真项目里是分开的页面。原型把它们放在同一阶段展示，只用来预演「做完镜头之后还要干什么」。</div>`;
}

function wsEditRow(n, d, st, proto, note, action) {
  return `
    <div class="ws-editrow">
      <span class="ws-edit-ic"></span>
      <div class="ws-edit-b"><b>${n}</b><span>${d}</span><i>${note}</i></div>
      <div class="ws-edit-tags">${wsTag(st)}${wsTag(proto)}</div>
      <button class="b" onclick="${action}">打开</button>
    </div>`;
}

function wsOpenRetouch() {
  const items = wsShots();
  if (!items.length) {
    toast('先导入一张图或生成镜头');
    return;
  }
  const id = selId || items[0].id;
  if (typeof openRetouch === 'function') openRetouch(id);
}

/* ================= 15. 交付 ================= */

function wsStageDelivery() {
  const items = wsShots();
  const ok = items.filter(s => s.status === 'ok').length;
  const err = items.filter(s => s.status === 'err').length;
  const todo = items.filter(s => s.status === 'todo' || s.status === 'run').length;
  const bound = wsBoundShots();
  const sim = items.filter(s => s.wsSim).length;
  const real = wsRealShots();
  const ph = Math.max(0, ok - sim - real);
  const genSt = !items.length ? 'unknown' : (ok === items.length ? 'pass' : 'fail');
  const realSt = (!items.length || !ok) ? 'unknown' : (sim || ph) ? 'fail' : 'pass';
  const realNote = (!items.length || !ok) ? '还没有已生成的镜头'
    : sim ? `${sim} 镜是原型模拟，没有真像素`
    : ph ? `${ph} 镜是演示占位，没有真像素`
    : `${real} 镜都有真实像素`;
  return `
    <div class="ws-main-h">
      <div><h2>交付</h2><div class="ws-main-s">先检查，再导出，最后才是发布</div></div>
      ${wsTag('partial')}
    </div>

    <div class="ws-checks">
      ${wsCheckRow('镜头生成', genSt, items.length ? `${ok} / ${items.length} 已生成${err ? ' · ' + err + ' 失败' : ''}${todo ? ' · ' + todo + ' 待处理' : ''}` : '还没有镜头，先去分镜页')}
      ${wsCheckRow('真实产出', realSt, realNote)}
      ${wsCheckRow('角色引用', bound ? 'pass' : 'unknown', `${bound} 镜绑定了角色卡`)}
      ${wsCheckRow('字幕轨', 'unknown', '原型没有接字幕检查')}
      ${wsCheckRow('发布授权', 'manual', '发布前需要你本人确认')}
    </div>

    <div class="ws-sec-h">去哪里交付</div>
    <div class="ws-deliver">
      <div class="ws-deliver-row">
        <span class="ws-deliver-ic">⇥</span>
        <div class="ws-deliver-b"><b>导出成片</b><span>真逐层合成，可下载 PNG / JPG</span></div>
        <div class="ws-edit-tags">${wsTag('real')}${wsTag('live')}</div>
        <button class="b" onclick="openExport()">打开导出</button>
      </div>
      <div class="ws-deliver-row">
        <span class="ws-deliver-ic">▤</span>
        <div class="ws-deliver-b"><b>发布 · 番茄小说</b><span>真项目只做到登录、选书、存草稿</span></div>
        <div class="ws-edit-tags">${wsTag('partial')}${wsTag('slot')}</div>
        <button class="b" onclick="wsSlot('发布到番茄','真项目 /publish 目前只做到番茄存草稿：登录、选书、存草稿。\\n\\n原型没有接账号，不会发任何内容。')">看说明</button>
      </div>
      <div class="ws-deliver-row">
        <span class="ws-deliver-ic">▤</span>
        <div class="ws-deliver-b"><b>发布 · 抖音 / 快手</b><span>真项目还没有这两个平台的发布链路</span></div>
        <div class="ws-edit-tags">${wsTag('planned')}${wsTag('slot')}</div>
        <button class="b" onclick="wsSlot('抖音 / 快手发布','真项目还没有这两个平台的发布链路。这里只是占位，别当成能用。')">看说明</button>
      </div>
    </div>

    <div class="ws-callout">交付检查里「未验证」和「阻断」分开写。字幕没接检查就写未验证，不能写成「没问题」。</div>

    <div class="ws-actions">
      <button class="b solid" onclick="wsPublishCheck()">发布前检查</button>
      <button class="b" onclick="openExport()">打开导出</button>
    </div>`;
}

function wsCheckRow(n, st, ev) {
  const label = st === 'pass' ? '通过' : st === 'fail' ? '阻断' : st === 'manual' ? '需人工' : '未验证';
  return `<div class="ws-check ${st}"><span class="ws-check-dot"></span><b>${n}</b><span>${ev}</span><i>${label}</i></div>`;
}

function wsPublishCheck() {
  const items = wsShots();
  const ok = items.filter(s => s.status === 'ok').length;
  const err = items.filter(s => s.status === 'err').length;
  const todo = items.filter(s => s.status === 'todo' || s.status === 'run').length;
  const bound = wsBoundShots();
  const total = items.reduce((a, s) => a + (s.duration || 0), 0);
  const sim = items.filter(s => s.wsSim).length;
  const real = wsRealShots();
  const ph = Math.max(0, ok - sim - real);
  const blocked = (err || todo || sim || ph) ? 1 : 0;
  const realNote = (!items.length || !ok) ? '还没有已生成的镜头'
    : sim ? `${sim} 镜是原型模拟，没有真像素`
    : ph ? `${ph} 镜是演示占位，没有真像素`
    : `${real} 镜都有真实像素`;
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">发布前检查</div>
          <div class="inp-sub">检查的是这一集，不是某一张图</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          <div class="ws-check-list">
            ${wsCheckRow('镜头全部生成', !items.length ? 'unknown' : (err || todo) ? 'fail' : 'pass', items.length ? `${ok} / ${items.length} 已生成 · ${err} 失败 · ${todo} 待处理` : '还没有镜头')}
            ${wsCheckRow('真实产出', (!items.length || !ok) ? 'unknown' : (sim || ph) ? 'fail' : 'pass', realNote)}
            ${wsCheckRow('角色引用已绑定', bound ? 'pass' : 'unknown', `${bound} 镜有角色卡参考`)}
            ${wsCheckRow('总时长', items.length ? 'pass' : 'unknown', `${total.toFixed(1)} 秒 · 目标约 42 秒`)}
            ${wsCheckRow('字幕轨', 'unknown', '原型未接字幕检查，真项目 /subtitle 已有')}
            ${wsCheckRow('发布授权', 'manual', '发布前需要你本人确认目标账号')}
          </div>
          <div class="ws-callout">${blocked ? '有阻断项。失败、待生成、模拟出来的、或者只是演示占位的镜头，都不能当成可交付。' : '没有阻断项。字幕和授权仍然是未验证或需人工，不能当成通过。'}</div>
          <div class="ws-note">原型不会发布任何内容。这里只预演「发布前要检查什么」。</div>
        </div>
        <div class="wsx-foot">
          <button class="b" onclick="wsClosePanel();openExport()">打开导出</button>
          <span class="ws-sp"></span>
          ${blocked ? '<button class="b solid" onclick="wsClosePanel();wsOpenStage(\'shots\')">去分镜页处理</button>' : '<button class="b solid" onclick="wsClosePanel()">知道了</button>'}
        </div>
      </div>
    </div>`);
}

/* ================= 16. 功能地图 ================= */

function openFeatureMap() {
  const groups = [...new Set(WS_FEATURES.map(f => f.g))];
  const real = WS_FEATURES.filter(f => f.st === 'real').length;
  const partial = WS_FEATURES.filter(f => f.st === 'partial').length;
  const planned = WS_FEATURES.filter(f => f.st === 'planned').length;
  const live = WS_FEATURES.filter(f => f.proto === 'live').length;
  const sim = WS_FEATURES.filter(f => f.proto === 'sim').length;
  const slot = WS_FEATURES.filter(f => f.proto === 'slot').length;
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w wsx-wide">
        <div class="inp-hd">
          <div class="inp-t">项目功能地图</div>
          <div class="inp-sub">真项目有的功能和原型位置的对照。路径是实现标注，不是给用户看的入口。</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          ${groups.map(g => `
            <div class="ws-picksec">${g}</div>
            <div class="ws-featlist">
              ${WS_FEATURES.filter(f => f.g === g).map(f => `
                <div class="ws-feat">
                  <div class="ws-feat-n"><b>${f.n}</b><span class="ws-feat-path">${f.path}</span></div>
                  <div class="ws-feat-tags">${wsTag(f.st)}${wsTag(f.proto)}</div>
                  <div class="ws-feat-note">${f.note}</div>
                </div>`).join('')}
            </div>`).join('')}
        </div>
        <div class="wsx-foot">
          <span class="ws-footnote">真项目：${real} 项已有 · ${partial} 项部分 · ${planned} 项计划中。原型：${live} 项可操作 · ${sim} 项模拟 · ${slot} 项占位。</span>
          <button class="b solid" onclick="wsClosePanel()">关闭</button>
        </div>
      </div>
    </div>`);
}

function wsSlot(title, msg) {
  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w wsx-narrow">
        <div class="inp-hd">
          <div class="inp-t">${title}</div>
          <div class="inp-sub">这个位置先留出来，功能没有接</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          <div class="ws-slotmsg">${esc(msg).replace(/\n/g, '<br>')}</div>
          <div class="ws-note">写清边界，比放一个点了没反应的按钮好。</div>
        </div>
        <div class="wsx-foot"><button class="b solid" onclick="wsClosePanel()">知道了</button></div>
      </div>
    </div>`);
}

/* ================= 17. 输入框 @ 引用 ================= */

function wsUpdateComposerChips() {
  const m = wsModel(WS_COMPOSER_MODEL);
  const modelEl = document.getElementById('cmpModel');
  if (modelEl) modelEl.innerHTML = `${m.n} <span class="cv2">▾</span>`;
  const costEl = document.getElementById('cmpCost');
  if (costEl) costEl.textContent = m.pts ? '⚡' + m.pts : '免费';
  const ratioEl = document.getElementById('cmpRatio');
  if (ratioEl) ratioEl.innerHTML = `${WS.gen.ratio} <span class="cv2">▾</span>`;
}

function wsCycleComposerRatio() {
  const arr = ['2:3', '1:1', '3:4', '16:9'];
  WS.gen.ratio = arr[(arr.indexOf(WS.gen.ratio) + 1) % arr.length];
  wsUpdateComposerChips();
}

function wsAddComposerRef(ref) {
  if (WS_COMPOSER_REFS.some(r => r.kind === ref.kind && r.id === ref.id)) {
    toast('已经在引用里了');
    return;
  }
  WS_COMPOSER_REFS.push(ref);
  wsRenderComposerRefs();
  toast('已引用：' + ref.label);
}

function wsRemoveComposerRef(kind, id) {
  WS_COMPOSER_REFS = WS_COMPOSER_REFS.filter(r => !(r.kind === kind && r.id === id));
  wsRenderComposerRefs();
}

function wsRenderComposerRefs() {
  const bar = document.getElementById('wsRefBar');
  if (!bar) return;
  if (!WS_COMPOSER_REFS.length) {
    bar.classList.remove('has');
    bar.innerHTML = '';
    return;
  }
  bar.classList.add('has');
  bar.innerHTML = WS_COMPOSER_REFS.map(r => `
    <span class="ws-ref">${esc(r.label)}<button class="ws-ref-x" onclick="wsRemoveComposerRef('${r.kind}','${r.id}')">✕</button></span>`).join('')
    + '<span class="ws-ref-hint">会随这条消息带上</span>';
}

function openAtPicker() {
  if (document.getElementById('atPop')) {
    wsAtDone();
    return;
  }
  const cmp = document.querySelector('.cmp');
  if (!cmp) return;
  const d = document.createElement('div');
  d.id = 'atPop';
  d.className = 'atpop';
  cmp.appendChild(d);
  wsAtRender();
  setTimeout(() => document.addEventListener('click', wsAtOutside), 0);
}

function wsAtDone() {
  const p = document.getElementById('atPop');
  if (p) p.remove();
  document.removeEventListener('click', wsAtOutside);
}

function wsAtOutside(e) {
  if (!(e.target instanceof Element)) return;
  if (e.target.closest('#atPop') || e.target.closest('#atBtn')) return;
  wsAtDone();
}

function wsAtTab(k) {
  WS_AT_TAB = k;
  wsAtRender();
}

function wsAtRender() {
  const p = document.getElementById('atPop');
  if (!p) return;
  const tabs = [['character', '角色'], ['asset', '素材'], ['style', '风格']];
  let items;
  if (WS_AT_TAB === 'character') {
    items = WS_CHARACTERS.map(c => ({ kind: 'character', id: c.id, label: c.n, sub: c.role, color: c.color }));
  } else if (WS_AT_TAB === 'asset') {
    items = WS_ASSETS.map(a => ({ kind: 'asset', id: a.id, label: a.n, sub: a.kind + ' · ' + a.src }));
  } else {
    items = WS_STYLES.map(s => ({ kind: 'style', id: s.id, label: s.n, sub: s.d }));
  }
  p.innerHTML = `
    <div class="atpop-h">
      <b>@ 引用素材</b>
      <button class="atpop-x" onclick="wsAtDone()">✕</button>
    </div>
    <div class="atpop-tabs">
      ${tabs.map(([k, n]) => `<button class="${WS_AT_TAB === k ? 'on' : ''}" onclick="wsAtTab('${k}')">${n}</button>`).join('')}
    </div>
    <div class="atpop-list">
      ${items.map(it => {
        const on = WS_COMPOSER_REFS.some(r => r.kind === it.kind && r.id === it.id);
        return `<button class="atpop-i ${on ? 'on' : ''}" onclick="wsAtToggle('${it.kind}','${it.id}')">
          <span class="atpop-av" style="background:${it.color || 'var(--s3)'};color:${it.color ? '#081015' : 'var(--tx2)'}">${it.label.slice(0, 1)}</span>
          <span class="atpop-t"><b>${esc(it.label)}</b><i>${esc(it.sub)}</i></span>
          <span class="atpop-c">${on ? '已引用' : '+'}</span>
        </button>`;
      }).join('')}
    </div>
    <div class="atpop-f">
      <span>${WS_COMPOSER_REFS.length} 项已引用</span>
      <button class="b solid" onclick="wsAtDone()">完成</button>
    </div>`;
}

function wsAtToggle(kind, id) {
  const idx = WS_COMPOSER_REFS.findIndex(r => r.kind === kind && r.id === id);
  if (idx >= 0) {
    WS_COMPOSER_REFS.splice(idx, 1);
  } else {
    const label = kind === 'character' ? (wsChar(id) || {}).n
      : kind === 'asset' ? (wsAsset(id) || {}).n
      : (wsStyle(id) || {}).n;
    if (label) WS_COMPOSER_REFS.push({ kind, id, label });
  }
  wsRenderComposerRefs();
  wsAtRender();
}

function wsConsumeComposerRefs() {
  if (!WS_COMPOSER_REFS.length) return;
  const refs = WS_COMPOSER_REFS.slice();
  WS_COMPOSER_REFS = [];
  wsRenderComposerRefs();
  wsAtDone();
  const last = agb ? agb.lastElementChild : null;
  const bubble = last ? last.querySelector('.bubble') : null;
  if (!bubble) return;
  const d = document.createElement('div');
  d.className = 'ws-used';
  d.innerHTML = '<span>带上了</span>' + refs.map(r => `<span class="ws-used-i">${esc(r.label)}</span>`).join('');
  bubble.appendChild(d);
}

/* ================= 18. 镜头墙上的参考标记 ================= */

function wsShotRefs(shotId) {
  return WS_SHOT_REFS[shotId] || [];
}

function wsRefChipsHtml(shotId) {
  const refs = wsShotRefs(shotId);
  if (!refs.length) return '';
  const show = refs.slice(0, 2);
  const more = refs.length - show.length;
  return `<div class="shot-refs" onclick="event.stopPropagation()">`
    + show.map(r => `<span class="shot-ref" title="参考：${esc(r.label)}" onclick="event.stopPropagation();wsOpenShotRefs('${shotId}')">${esc(r.label)}</span>`).join('')
    + (more ? `<span class="shot-ref more" onclick="event.stopPropagation();wsOpenShotRefs('${shotId}')">+${more}</span>` : '')
    + '</div>';
}

/* ================= 19. 键盘与初始化 ================= */

document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (document.querySelector('.gate, .lb, .ex, .pl, .insp, .le, .raw, .lm')) return;
  if (document.getElementById('atPop')) { wsAtDone(); return; }
  const panel = document.getElementById('wsPanelHost');
  if (panel && panel.innerHTML.trim()) { wsClosePanel(); return; }
  if (wsSlots() && wsSlots().innerHTML.trim()) closeWorkspace();
});

(function wsInit() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wsUpdateComposerChips, { once: true });
  } else {
    wsUpdateComposerChips();
  }
})();

/* ============================================================
   / 技能弹层（2026-11-01 加）
   基线来自即梦：打字时打 / 直接弹技能列表，每个带一句话说明 + 官方标记，
   顶部有搜索框。截图见 docs/research/jimeng/02_skills.png。
   · 壳复用 @ 引用的 .atpop（同一套视觉，不再画第三套）
   · 方向也跟 @ 一致往上开 —— 输入框贴着视口底，往下开会出屏。
     即梦在下是因为它输入框下面还有 chips 行，我们不是，别照抄。
   ============================================================ */
const WS_SKILLS = [
  { n:'创作分镜',   d:'一句话拆成分镜，标好景别和运镜' },
  { n:'角色三视图', d:'按 9 个方位出一套立绘，跨镜头不变脸' },
  { n:'参考组合',   d:'按你说的场景凑服装和姿势，不碰脸' },
  { n:'视频反解',   d:'拆解参考视频的镜头语言、光影和节奏' },
  { n:'电商套图',   d:'按商品信息出一套风格统一的主图' },
  { n:'海报设计',   d:'给标题和卖点，出一版可直接用的海报' },
  { n:'剧情短片',   d:'从大纲到分镜再到成片的完整流程' }
];

let wsSkillIdx = 0;
let wsSkillQ = '';
let wsSkillAt = 0;   // 打开时的光标位置，选中后往这儿插

function openSkillPicker(){
  if (document.getElementById('skillPop')) return;
  const cmp = document.querySelector('.cmp');
  if (!cmp) return;
  const taEl = document.getElementById('ta');
  wsSkillAt = taEl ? taEl.selectionStart : 0;
  wsSkillQ = '';
  wsSkillIdx = 0;

  const d = document.createElement('div');
  d.id = 'skillPop';
  d.className = 'atpop skillpop';
  cmp.appendChild(d);

  // 壳只建一次：搜索框不能被重建，否则每打一个字光标就跳回开头
  d.innerHTML = `
    <div class="atpop-h"><b>/ 技能</b>
      <button class="atpop-x" onclick="wsSkillDone()">✕</button></div>
    <div class="skillpop-s">
      <input id="skSearch" placeholder="搜索技能"
             oninput="wsSkillFilter(this.value)" onkeydown="wsSkillKey(event)">
    </div>
    <div class="atpop-list" id="skillList"></div>
    <div class="atpop-f"><span>↑↓ 选 · Enter 用 · Esc 关</span></div>`;

  wsSkillRender();
  setTimeout(()=>document.addEventListener('click', wsSkillOutside), 0);
  const s = document.getElementById('skSearch');
  if (s) s.focus();
}

function wsSkillDone(){
  const p = document.getElementById('skillPop');
  if (p) p.remove();
  document.removeEventListener('click', wsSkillOutside);
  wsSkillQ = '';
}

function wsSkillOutside(e){
  if (!(e.target instanceof Element)) return;
  if (e.target.closest('#skillPop')) return;
  wsSkillDone();
}

function wsSkillFilter(v){
  wsSkillQ = v || '';
  wsSkillIdx = 0;
  wsSkillRender();
}

function wsSkillItems(){
  const q = wsSkillQ.trim().toLowerCase();
  if (!q) return WS_SKILLS;
  return WS_SKILLS.filter(s =>
    s.n.toLowerCase().includes(q) || s.d.toLowerCase().includes(q));
}

function wsSkillRender(){
  const box = document.getElementById('skillList');
  if (!box) return;
  const items = wsSkillItems();
  box.innerHTML = items.length
    ? items.map((s, i) => `
        <button class="atpop-i ${i === wsSkillIdx ? 'sel' : ''}" onclick="wsSkillPick('${s.n}')">
          <span class="sk-k">/</span>
          <span class="atpop-t"><b>${esc(s.n)}</b><i>${esc(s.d)}</i></span>
          <span class="sk-tag">官方</span>
        </button>`).join('')
    : `<div style="padding:14px 10px;font-size:10px;color:var(--tx3);text-align:center">
         没有匹配「${esc(wsSkillQ)}」的技能</div>`;
}

function wsSkillKey(e){
  const items = wsSkillItems();
  if (e.key === 'ArrowDown'){
    e.preventDefault();
    wsSkillIdx = Math.min(items.length - 1, wsSkillIdx + 1);
    wsSkillRender();
  } else if (e.key === 'ArrowUp'){
    e.preventDefault();
    wsSkillIdx = Math.max(0, wsSkillIdx - 1);
    wsSkillRender();
  } else if (e.key === 'Enter'){
    e.preventDefault();
    if (items[wsSkillIdx]) wsSkillPick(items[wsSkillIdx].n);
  } else if (e.key === 'Escape'){
    e.preventDefault();
    wsSkillDone();
    const taEl = document.getElementById('ta');
    if (taEl) taEl.focus();
  }
}

function wsSkillPick(name){
  const taEl = document.getElementById('ta');
  if (taEl){
    const v = taEl.value;
    const at = Math.max(0, Math.min(wsSkillAt, v.length));
    const ins = '/' + name + ' ';
    taEl.value = v.slice(0, at) + ins + v.slice(at);
    const pos = at + ins.length;
    taEl.focus();
    taEl.setSelectionRange(pos, pos);
    taEl.rows = Math.min(3, Math.max(1, Math.ceil(taEl.value.length / 34) || 1));
  }
  wsSkillDone();
}

/* ============================================================
   参考组合（2026-11-01）：由对话触发，不做独立页面
   · 场景**从这句话里解析**，不是让用户在下拉里选
   · 只推荐服装 + 姿势 —— 脸由角色决定，不参与推荐
   ============================================================ */
const REF_SCENES = {
  yiheyuan: { n:'秋天颐和园', place:'长廊尽头的石阶', light:'下午四点的斜侧逆光，银杏叶透光', tone:'暖调，高对比' },
  marriage: { n:'民政局门口', place:'红墙前的台阶', light:'阴天散射光，柔和无硬影', tone:'低饱和，冷调' },
  studio:   { n:'棚拍 · 灰背景', place:'灰色无缝背景纸', light:'一盏柔光箱 45° 侧上，补光打底', tone:'中性，干净' }
};

const REF_RECS = {
  yiheyuan: [
    { o:'羊绒大衣', p:'靠墙站', why:'斜侧逆光里站定比走动更容易吃到边缘光；十月风大，大衣压得住；靠墙不抢长廊纵深。' },
    { o:'齐胸襦裙', p:'走姿回头', why:'古建配古装；纱质裙摆走动才飘得起来，逆光才看得见轮廓。' },
    { o:'针织开衫', p:'侧身站', why:'长廊有窗棂，侧身能把窗格光影投在脸上；米白在暖调里不抢银杏。' }
  ],
  marriage: [
    { o:'白衬衫牛仔', p:'侧身站', why:'阴天散射光没有硬影，正适合平淡真实；红墙配白衬衫对比最强。' },
    { o:'丝质长裙', p:'走姿回头', why:'正式场合裙子比裤子对；柔光对丝绸反光最友好，不会爆高光。' },
    { o:'针织开衫', p:'抱膝坐', why:'领完证放松的状态，坐台阶比站着自然；低饱和下燕麦色不显脏。' }
  ],
  studio: [
    { o:'白衬衫牛仔', p:'侧身站', why:'灰底配白最干净；45° 侧光能切出肩线。' },
    { o:'丝质长裙', p:'扶栏杆', why:'侧光专切侧脸轮廓；身体微后仰把下颌线拉开。' },
    { o:'宽松针织', p:'抱膝坐', why:'俯拍压缩空间，灰背景正好当留白。' }
  ]
};

/* 从一句话里读场景 —— 真实现交给模型抽，原型用关键词兜底 */
function wsParseScene(text){
  const t = text || '';
  if (/颐和园|长廊|银杏/.test(t)) return { key:'yiheyuan', ...REF_SCENES.yiheyuan, hit:'颐和园' };
  if (/民政局|领证|红墙/.test(t))  return { key:'marriage', ...REF_SCENES.marriage, hit:'民政局' };
  if (/棚|灰背景|背景纸/.test(t))  return { key:'studio',   ...REF_SCENES.studio,   hit:'棚拍' };
  return { key:'yiheyuan', ...REF_SCENES.yiheyuan, hit:'没读出来，先按颐和园' };
}

function wsOpenRefCombo(need){
  const pj = wsParseScene(need);
  const list = REF_RECS[pj.key] || REF_RECS.yiheyuan;

  const rows = list.map((r, i) => `
    <button class="refrec" onclick="wsUseRefRec('${pj.key}',${i})">
      <span class="refrec-no">${i + 1}</span>
      <span class="refrec-bd">
        <span class="refrec-t">${esc(r.o)} + ${esc(r.p)}</span>
        <span class="refrec-w">${esc(r.why)}</span>
      </span>
      <span class="refrec-go">用这组</span>
    </button>`).join('');

  wsPanel(`
    <div class="wsx" onclick="if(event.target.classList.contains('wsx'))wsClosePanel()">
      <div class="wsx-w">
        <div class="inp-hd">
          <div class="inp-t">凑一组参考</div>
          <div class="inp-sub">场景从你这句话里读，不用另外选</div>
          <button class="inp-x" onclick="wsClosePanel()">✕</button>
        </div>
        <div class="wsx-body">
          <div class="refscene">
            <span class="refscene-lb">读到的场景</span>
            <b>${esc(pj.n)}</b>
            <span>${esc(pj.place)}</span>
            <span>${esc(pj.light)}</span>
            <span class="refscene-hit">${esc(pj.hit)}</span>
          </div>
          <div class="refscene-note">
            来源：你刚说的那句「${esc((need || '').slice(0, 40))}」。
            脸按角色档案，不在这里推荐 —— 只推荐服装和姿势。
          </div>
          ${rows}
        </div>
        <div class="wsx-foot">
          <span class="ws-note">选一组会写进输入框，你可以再改</span>
          <button class="b" onclick="wsClosePanel()">取消</button>
        </div>
      </div>
    </div>`);
}

function wsUseRefRec(key, i){
  const r = (REF_RECS[key] || [])[i];
  if (!r) return;
  const pj = REF_SCENES[key];
  const taEl = document.getElementById('ta');
  if (taEl){
    taEl.value = '按这组出：穿' + r.o + '，' + r.p + '；' + pj.place + '，' + pj.light;
    taEl.rows = Math.min(3, Math.max(1, Math.ceil(taEl.value.length / 34) || 1));
    taEl.focus();
    taEl.setSelectionRange(taEl.value.length, taEl.value.length);
  }
  wsClosePanel();
  toast('参考已写进输入框 · 还能改');
}

/* ============================================================
   顶栏「更多」菜单（2026-11-02）
   原来顶栏塞了 14 个按钮，1440 宽就撑爆、模式切换被压成竖排。
   低频工具收进这个菜单，顶栏只留：logo · 剧集名 · 模式切换 · 用户 · 出片 · ⋯
   ============================================================ */
function toggleMore(e){
  if (e) e.stopPropagation();
  const m = document.getElementById('moreMenu');
  if (!m) return;
  const opening = m.classList.contains('hidden');
  m.classList.toggle('hidden', !opening);
  if (opening) setTimeout(()=>document.addEventListener('click', moreOutside), 0);
  else document.removeEventListener('click', moreOutside);
}

function closeMore(){
  const m = document.getElementById('moreMenu');
  if (m) m.classList.add('hidden');
  document.removeEventListener('click', moreOutside);
}

function moreOutside(e){
  if (!(e.target instanceof Element)) return;
  if (e.target.closest('[onclick*="toggleMore"]')) return;   // 交给 toggleMore 自己翻
  closeMore();                                               // 点菜单里或外面都关
}
