/* ============================================================
   YLCraft 原型互通导航（2026-11-07 ⑥）
   ------------------------------------------------------------
   三个活原型之前互不跳转，只有启动页是枢纽。各页在 </body> 前引一行：

     <script src="../shared/proto-nav.js?v=<版本>"></script>

   脚本自动找顶栏插入「原型 ▾」；找不到顶栏就退化成右下角小按钮。
   路径从本脚本的 src 反推站点根，所以 canvas/ photo-ref/ previs/
   各层子目录都能用同一个文件。面板自带固定深色，不依赖页面主题变量
   ——摄影参考库有亮色 dawn 主题，用 rgba(白,x) 会看不见。
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
    ['多角度',       'canvas/multi-angle.html']
  ];

  /* 面板自带固定深色，不读页面的 --bg/--tx，亮色主题下也能读 */
  var css = [
    '.yl-pnav{position:relative;display:inline-flex;align-items:center;flex:0 0 auto;',
    '  font-family:var(--fs),system-ui,sans-serif;z-index:9000}',
    '.yl-pnav>button{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;',
    '  border:1px solid rgba(255,255,255,.20);border-radius:999px;background:#17171d;',
    '  color:#e4e4e7;font-family:inherit;font-size:12px;line-height:1;cursor:pointer;white-space:nowrap}',
    '.yl-pnav>button:hover{border-color:#22d3ee;color:#67e8f9}',
    '.yl-pnav>button i{font-style:normal;font-size:var(--fz);color:#8b8c9e;line-height:1}',
    '.yl-pmenu{position:fixed;min-width:186px;padding:5px;display:none;z-index:9999;',
    '  background:#121216;border:1px solid rgba(255,255,255,.18);border-radius:10px;',
    '  box-shadow:0 18px 46px -12px rgba(0,0,0,.9);font-family:var(--fs),system-ui,sans-serif}',
    '.yl-pmenu a{display:block;padding:7px 11px;border-radius:6px;color:#c9c9d2;',
    '  text-decoration:none;font-size:12px;line-height:1.4;white-space:nowrap}',
    '.yl-pmenu a:hover{background:#22222b;color:#67e8f9}',
    '.yl-pmenu a.cur{color:#22d3ee;font-weight:600}',
    '.yl-pmenu hr{border:0;border-top:1px solid rgba(255,255,255,.12);margin:4px 6px}',
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
