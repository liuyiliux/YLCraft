/* ============================================================
   YLCraft 原型互通导航（2026-11-07 ⑥）
   ------------------------------------------------------------
   三个活原型之前互不跳转，只有启动页是枢纽。各页在 </body> 前引一行：

     <script src="../shared/proto-nav.js?v=<版本>"></script>

   脚本自动找顶栏插入「原型 ▾」；找不到顶栏就退化成右下角小按钮。
   路径从本脚本的 src 反推站点根，所以 canvas/ photo-ref/ previs/
   各层子目录都能用同一个文件。按钮/菜单用自带的 --yl-* 变量按
   data-theme / data-t 切换深/亮配色，亮色 dawn 下不再顶着深色胶囊。
   启动页本身是枢纽，不引入本脚本。
   ============================================================ */
(function () {
  var script = document.currentScript;
  if (!script || document.querySelector('.yl-pnav')) return;

  var ROOT = script.src.replace(/\/shared\/proto-nav\.js.*$/i, '/');
  var here = location.pathname.replace(/^\//, '').toLowerCase();
  if (here === '' || here === 'index.html') return;

  var LINKS = [
    ['总览',         'index.html'],
    ['画布',         'canvas/index.html'],
    ['摄影参考库',   'photo-ref/index.html'],
    ['Agent 页',     'photo-ref/agent-page.html'],
    null,
    ['3D 导演台',    'previs/director-agent.html'],
    ['修图器 v2',    'canvas/image-editor-v2.html'],
    ['多角度',       'canvas/multi-angle.html'],
    null,
    ['功能地图',     'features/index.html'],
    ['AI 生成结果墙', 'features/gen-wall.html'],
    ['角色工作台',   'features/characters.html'],
    ['创作项目',     'features/story-desk.html'],
    ['素材工作台',   'features/assets-home.html'],
    ['素材库',       'features/assets.html'],
    ['任务中心',     'features/tasks.html'],
    ['账号中心',     'features/accounts.html']
  ];

  /* 2026-11-21：注入自定义 --yl-* 变量，按页面主题切换深/亮两套配色。
     不用页面自己的变量名 —— 画布/摄影库/features 三套命名不同；
     无 data-theme/data-t 的画布页保持原深色；features 和摄影库都支持 dawn 亮色。 */
  var css = [
    ':root{--yl-bg:#17171d;--yl-fg:#e4e4e7;--yl-bd:rgba(255,255,255,.20);',
    '  --yl-ac:#22d3ee;--yl-ach:#67e8f9;--yl-dim:#8b8c9e;',
    '  --yl-menu:#121216;--yl-menufg:#c9c9d2;--yl-menubd:rgba(255,255,255,.18);',
    '  --yl-menuho:#22222b;--yl-hr:rgba(255,255,255,.12);--yl-sh:0 18px 46px -12px rgba(0,0,0,.9)}',
    /* 摄影库的 data-t 挂在 body 上，features 的 data-theme 挂在 html 上，两边都要覆盖 */
    ':root[data-theme="moonlight"],:root[data-t="moonlight"],body[data-t="moonlight"]{',
    '  --yl-bg:#1d1a24;--yl-fg:#e4e4ec;--yl-ac:#a78bfa;--yl-ach:#c4b5fd;--yl-dim:#8884a4;',
    '  --yl-menu:#1d1a24;--yl-menufg:#ded8ea;--yl-menuho:#262130;--yl-hr:rgba(167,139,250,.16)}',
    ':root[data-theme="dawn"],:root[data-t="dawn"],body[data-t="dawn"]{',
    '  --yl-bg:#ffffff;--yl-fg:#27272a;--yl-bd:#d6d3d1;--yl-ac:#0d9488;--yl-ach:#0f766e;',
    '  --yl-dim:#8b8b93;--yl-menu:#ffffff;--yl-menufg:#52525b;--yl-menubd:#d6d3d1;',
    '  --yl-menuho:#f2f1ee;--yl-hr:#e7e5e4;--yl-sh:0 18px 46px -12px rgba(0,0,0,.22)}',
    '.yl-pnav{position:relative;display:inline-flex;align-items:center;flex:0 0 auto;',
    '  font-family:var(--fs),system-ui,sans-serif;z-index:9000}',
    '.yl-pnav>button{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;',
    '  border:1px solid var(--yl-bd);border-radius:999px;background:var(--yl-bg);',
    '  color:var(--yl-fg);font-family:inherit;font-size:var(--fz);line-height:1;cursor:pointer;white-space:nowrap}',
    '.yl-pnav>button:hover{border-color:var(--yl-ac);color:var(--yl-ach)}',
    '.yl-pnav>button i{font-style:normal;font-size:var(--fz);color:var(--yl-dim);line-height:1}',
    '.yl-pmenu{position:fixed;min-width:186px;padding:5px;display:none;z-index:9999;',
    '  background:var(--yl-menu);border:1px solid var(--yl-menubd);border-radius:10px;',
    '  box-shadow:var(--yl-sh);font-family:var(--fs),system-ui,sans-serif}',
    '.yl-pmenu a{display:block;padding:7px 11px;border-radius:6px;color:var(--yl-menufg);',
    '  text-decoration:none;font-size:var(--fz);line-height:1.4;white-space:nowrap}',
    '.yl-pmenu a:hover{background:var(--yl-menuho);color:var(--yl-ach)}',
    '.yl-pmenu a.cur{color:var(--yl-ac);font-weight:600}',
    '.yl-pmenu hr{border:0;border-top:1px solid var(--yl-hr);margin:4px 6px}',
    '.yl-pnav.fixed{position:fixed;right:12px;bottom:12px;margin:0;z-index:9000}'
  ].join('\n');

  var st = document.createElement('style');
  st.id = 'yl-pnav-css';
  st.textContent = css;
  document.head.appendChild(st);

  var nav = document.createElement('div');
  nav.className = 'yl-pnav';
  var btn = document.createElement('button');
  btn.type = 'button';
  btn.setAttribute('aria-label', '切换原型');
  btn.innerHTML = '原型 <i>▾</i>';
  nav.appendChild(btn);

  var menu = document.createElement('div');
  menu.className = 'yl-pmenu';
  LINKS.forEach(function (item) {
    if (!item) { menu.appendChild(document.createElement('hr')); return; }
    var a = document.createElement('a');
    a.href = ROOT + item[1];
    a.textContent = item[0];
    if (item[1].toLowerCase() === here) a.className = 'cur';
    menu.appendChild(a);
  });
  document.body.appendChild(menu);

  /* 有顶栏就塞进顶栏，没有就退到右下角固定按钮 */
  var bar = document.querySelector('.topbar, .appbar, .top');
  if (bar) bar.appendChild(nav);
  else { nav.className = 'yl-pnav fixed'; document.body.appendChild(nav); }

  function place() {
    if (menu.style.display !== 'block') return;
    var r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 6) + 'px';
    menu.style.right = Math.max(8, Math.round(window.innerWidth - r.right)) + 'px';
  }
  function toggle(e) {
    e.stopPropagation();
    var open = menu.style.display === 'block';
    menu.style.display = open ? 'none' : 'block';
    nav.classList.toggle('open', !open);
    place();
  }
  btn.addEventListener('click', toggle);
  document.addEventListener('click', function (e) {
    if (menu.style.display === 'block' && !menu.contains(e.target) && !nav.contains(e.target)) {
      menu.style.display = 'none';
      nav.classList.remove('open');
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { menu.style.display = 'none'; nav.classList.remove('open'); }
  });
  window.addEventListener('resize', place);
})();
