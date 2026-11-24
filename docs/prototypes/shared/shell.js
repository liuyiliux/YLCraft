/* ============================================================
   YLCraft 原型 · 统一外壳（2026-11-24）
   ------------------------------------------------------------
   各页在 </body> 前引一行即可，不用改页面结构：

     <script src="../shared/shell.js?v=202611242100"></script>

   做三件事：
     1) 把 shared/shell.css 插到 head 末尾（保证压过页面自带样式）；
     2) 插左侧导航（工作台 / 功能页 / 原型），按当前路径高亮；
     3) 页面没有 .topbar 的（原型首页）补一条，只放面包屑与说明。

   画布 / 摄影参考库 / 3D 导演台 是整屏应用，不要引本脚本，只被侧栏链过去。
   导航项改这里一处，全站同步。
   ============================================================ */
(function () {
  var script = document.currentScript;
  if (!script || document.querySelector('.yl-side')) return;

  var ROOT = script.src.replace(/\/shared\/shell\.js.*$/i, '/');
  var VER = '202611242100';

  /* ---------- 导航结构：改这里一处，全站生效 ---------- */
  var GROUPS = [
    {
      name: '工作台', note: '整屏应用', items: [
        ['画布', 'canvas/index.html', '连线图 / 镜头墙 / 素材墙'],
        ['摄影参考库', 'photo-ref/index.html', '参考库 + 策划 + 现场'],
        ['Agent 页', 'photo-ref/agent-page.html', '对话协作三栏'],
        ['3D 导演台', 'previs/director-agent.html', '场景 / 机位 / 关键帧']
      ]
    },
    {
      name: '功能页', note: '按真实前端补', items: [
        ['提示词库', 'features/prompts.html', '13,309 条案例 · 多维筛选', 1],
        ['角色工作台', 'features/characters.html', '完善度 9 项 + 关系图'],
        ['创作项目', 'features/story-desk.html', '阶段轨 + Writer Room'],
        ['素材工作台', 'features/assets-home.html', '库状态 + 导入趋势'],
        ['素材库', 'features/assets.html', '筛选网格 + 版本血缘'],
        ['任务中心', 'features/tasks.html', '诊断 + 事件 + 日志'],
        ['账号中心', 'features/accounts.html', '连接体检 + 扫码登录'],
        ['AI 生成结果墙', 'features/gen-wall.html', '生图 / 视频 / 3D 三形态']
      ]
    },
    {
      name: '原型', note: '', items: [
        ['总览', 'index.html', '全部入口与登记规则'],
        ['功能地图', 'features/index.html', '真实功能 ↔ 覆盖对照']
      ]
    }
  ];

  /* ---------- 样式：插到 head 末尾 ---------- */
  var link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = ROOT + 'shared/shell.css?v=' + VER;
  document.head.appendChild(link);

  /* 原型首页自带一套精简变量，缺的补在 body 作用域，不动 html 上的主题变量 */
  var probe = getComputedStyle(document.documentElement).getPropertyValue('--acbg').trim();
  if (!probe) {
    var fb = document.createElement('style');
    fb.textContent = 'body.sh{--s4:#25252c;--acbg:rgba(34,211,238,.10);--onac:#04191e;--r:10px}';
    document.head.appendChild(fb);
  }

  /* ---------- 当前页 ---------- */
  var here = location.pathname;
  var cur = null;
  GROUPS.forEach(function (g) {
    g.items.forEach(function (it) { if (here.indexOf(it[1]) > -1) cur = { g: g, it: it }; });
  });

  /* ---------- 顶栏：没有就补一条 ---------- */
  var bar = document.querySelector('.topbar');
  if (!bar) {
    bar = document.createElement('header');
    bar.className = 'topbar';
    bar.innerHTML = '<span class="crumb"></span><span class="spacer"></span>' +
      '<span class="hintbar">原型不是实现事实 · 落地前看真代码</span>';
    document.body.insertBefore(bar, document.body.firstChild);
  }
  var crumb = bar.querySelector('.crumb');
  if (crumb && cur) {
    crumb.innerHTML = '<span class="g">' + cur.g.name + '</span><span class="sep">/</span>' + cur.it[0];
  }

  /* ---------- 侧栏 ---------- */
  var side = document.createElement('aside');
  side.className = 'yl-side';
  side.setAttribute('aria-label', '原型导航');

  var html = '<div class="yl-side-hd"><span class="mk">Y</span><span class="nm">YLCraft 原型</span>' +
    '<span class="tag">v0.9</span></div><nav class="yl-side-nav">';

  GROUPS.forEach(function (g) {
    html += '<div class="yl-grp">' + g.name +
      (g.note ? '<span class="n">' + g.note + '</span>' : '') + '</div>';
    g.items.forEach(function (it) {
      var on = cur && cur.it === it;
      html += '<a class="yl-link' + (on ? ' on' : '') + '" href="' + ROOT + it[1] + '"' +
        (on ? ' aria-current="page"' : '') + ' title="' + it[2] + '">' +
        '<span class="dot"></span><span>' + it[0] + '</span>' +
        (it[3] ? '<span class="new">新</span>' : '') + '</a>';
    });
  });

  html += '</nav><div class="yl-side-ft">' +
    '本地预览 · <b>127.0.0.1:8901</b><br>' +
    '历史版本别当规格 · <a href="' + ROOT + 'README.md">登记规则</a></div>';

  side.innerHTML = html;
  document.body.insertBefore(side, document.body.firstChild);
  document.body.classList.add('sh');

  /* ---------- 窄屏菜单按钮 ---------- */
  var toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'yl-side-toggle';
  toggle.setAttribute('aria-label', '展开导航');
  toggle.textContent = '≡';
  toggle.addEventListener('click', function () {
    document.body.classList.toggle('nav-open');
  });
  bar.insertBefore(toggle, bar.firstChild);
  side.addEventListener('click', function (e) {
    if (e.target.closest('a')) document.body.classList.remove('nav-open');
  });
})();
