/* 32-localhub.js — 本地调整统一面板（画质 / 人像 / 局部 / 精调）
   🔴 2026-10-20 用户选定方案 B。

   之前的问题：四个本地像素面板散成四个入口
     本地精调（曝光/对比/色温/色阶/曲线）
     画质与色彩（降噪/锐化/柔和阴影/镜头虚化/HSL）
     人像修饰（磨皮/液化/祛瑕疵，带笔刷）
     局部调整（蒙版）
   它们都是"免费、本地、参数不烘焙"，但工具栏上四个按钮名字看不出区别，
   用户想磨皮会先去画质找、想调 HSL 会去人像找 —— 找不着。

   现在：顶部一条 Tab 栏，四个面板在同一层壳里切换。
   实现取巧但风险低：**不改三个面板内部实现**，只做两件事
     ① 任何入口调用 → 转到 openLocalHub(tab)
     ② 面板渲染完 → 在页面顶部浮一条 Tab 栏
   好处：面板内部逻辑（笔刷、曲线、蒙版）一行不动，不会引入回归。
*/

const LOCAL_HUB_TABS = [
  { k:'quality', n:'画质与色彩', d:'降噪 / 锐化 / 柔和阴影 / 镜头虚化 / HSL' },
  { k:'retouch', n:'人像修饰',   d:'磨皮 / 液化 / 祛瑕疵（带笔刷）' },
  { k:'mask',    n:'局部调整',   d:'蒙版 + 曝光 / 对比 / 饱和' },
  { k:'edit',    n:'本地精调',   d:'曝光 / 对比 / 饱和 / 色温 / 色阶 / 曲线' }
];

let LOCAL_HUB_TAB = 'quality';
let LOCAL_HUB_ID = null;

/* 原始实现（在自己被改写之前抓住） */
const LOCAL_HUB_FN = {
  quality: (typeof openQuality === 'function') ? openQuality : null,
  retouch: (typeof openRetouch === 'function') ? openRetouch : null,
  mask:    (typeof openLocalMask === 'function') ? openLocalMask : null,
  edit:    (typeof openLocalEdit === 'function') ? openLocalEdit : null
};

function localHubBar(){
  let bar = document.getElementById('localHubTabs');
  if (bar) return bar;
  bar = document.createElement('div');
  bar.id = 'localHubTabs';
  bar.className = 'lh-tabs';
  document.body.appendChild(bar);
  return bar;
}

function renderLocalHubTabs(){
  const bar = localHubBar();
  bar.innerHTML =
    '<span class="lh-lead">本地调整</span>'
    + LOCAL_HUB_TABS.map(t =>
        '<button class="lh-tab' + (t.k === LOCAL_HUB_TAB ? ' on' : '') + '"'
        + ' data-tab="' + t.k + '"'
        + ' onclick="openLocalHub(\'' + t.k + '\')"'
        + ' title="' + t.d + '">' + t.n + '</button>'
      ).join('')
    + '<span class="lh-hint">都是本地像素运算 · 免费 · 参数不烘焙</span>';
  bar.style.display = 'flex';
}

function hideLocalHubTabs(){
  const bar = document.getElementById('localHubTabs');
  if (bar) bar.style.display = 'none';
}

/* 唯一入口 —— 四个面板都从这儿进 */
function openLocalHub(tab, id){
  const keys = LOCAL_HUB_TABS.map(function(t){ return t.k; });
  const k = (tab && keys.indexOf(tab) >= 0) ? tab : 'quality';
  LOCAL_HUB_TAB = k;

  /* 记住当前图，切 Tab 不丢 */
  const useId = id
    || LOCAL_HUB_ID
    || (typeof selId !== 'undefined' ? selId : null)
    || (typeof DOC !== 'undefined' && DOC.items && DOC.items[0] ? DOC.items[0].id : null);
  LOCAL_HUB_ID = useId;

  const fn = LOCAL_HUB_FN[k];
  if (typeof fn !== 'function'){
    toast('这个面板还没加载');
    return;
  }
  fn(useId);
  renderLocalHubTabs();
}

/* ---- 把四个直接入口全部路由到 hub，保证入口一致 ---- */
(function routeAllEntries(){
  if (typeof LOCAL_HUB_FN.quality === 'function'){
    window.openQuality = function(id){ return openLocalHub('quality', id); };
  }
  if (typeof LOCAL_HUB_FN.retouch === 'function'){
    window.openRetouch = function(id){ return openLocalHub('retouch', id); };
  }
  if (typeof LOCAL_HUB_FN.mask === 'function'){
    window.openLocalMask = function(id){ return openLocalHub('mask', id); };
  }
  if (typeof LOCAL_HUB_FN.edit === 'function'){
    window.openLocalEdit = function(id){ return openLocalHub('edit', id); };
  }
})();

/* ---- 面板关掉时把 Tab 栏一起收掉 ---- */
(function wrapClosers(){
  ['closeQuality','closeRetouch','closeMask','closeLocalEdit','closeOverlay'].forEach(function(n){
    const orig = window[n];
    if (typeof orig !== 'function') return;
    window[n] = function(){
      hideLocalHubTabs();
      return orig.apply(this, arguments);
    };
  });
})();

/* ---- 键盘：Ctrl/Cmd + 1..4 切 Tab（面板开着时才生效） ---- */
document.addEventListener('keydown', function(e){
  if (!(e.ctrlKey || e.metaKey)) return;
  if (!/^[1-4]$/.test(e.key)) return;
  const bar = document.getElementById('localHubTabs');
  if (!bar || bar.style.display === 'none') return;
  const t = LOCAL_HUB_TABS[Number(e.key) - 1];
  if (!t) return;
  e.preventDefault();
  openLocalHub(t.k);
});
