/* ============================================================
   features 原型主题开关（2026-11-20）
   ------------------------------------------------------------
   三套主题对齐摄影参考库：deep 深海 / moonlight 月光 / dawn 晨曦。
   只作用于 features/ 页（画布页不引入本脚本，它有大量白色半透明
   文字，亮底会看不见）。选择记 localStorage，刷新保持。

   按钮/菜单直接读页面主题变量（--s2 / --ln2 / --tx / --ac / --modal），
   dawn 亮色下跟着变浅色；shared/proto-nav.js 跨三套命名不同的页面，
   用自带的 --yl-* 变量做同样的深/亮切换。

   modern-web-guidance：menu 语义 + aria-checked + 方向键 / Esc；
   Esc 不自己关模态（这里不是 dialog，是普通弹出层，需要自己关）。
   ============================================================ */
(function () {
  var KEY = 'ylcraft-features-theme';
  var THEMES = [
    ['deep', '深海', '#22d3ee'],
    ['moonlight', '月光', '#a78bfa'],
    ['dawn', '晨曦', '#0d9488']
  ];
  var names = { deep: '深海', moonlight: '月光', dawn: '晨曦' };
  var cur = 'deep';
  try { cur = localStorage.getItem(KEY) || 'deep'; } catch (e) {}
  if (!names[cur]) cur = 'deep';

  function apply(t, save) {
    if (!names[t]) return;
    cur = t;
    document.documentElement.setAttribute('data-theme', t);
    var meta = document.querySelector('meta[name="color-scheme"]');
    if (meta) meta.setAttribute('content', t === 'dawn' ? 'light' : 'dark');
    if (save) { try { localStorage.setItem(KEY, t); } catch (e) {} }
    if (btn) {
      btn.innerHTML = '<i style="background:' + (names[t] === '晨曦' ? '#0d9488' : names[t] === '月光' ? '#a78bfa' : '#22d3ee') + '"></i>'
        + names[t] + ' <span aria-hidden="true">▾</span>';
      btn.setAttribute('aria-label', '当前主题：' + names[t] + '，点击切换');
    }
    if (menu) {
      Array.prototype.forEach.call(menu.querySelectorAll('[role="menuitemradio"]'), function (m) {
        m.setAttribute('aria-checked', m.dataset.theme === t ? 'true' : 'false');
      });
    }
  }
  apply(cur, false);

  var bar = document.querySelector('.topbar, .appbar, .top');
  if (!bar) return;

  /* 2026-11-21：按钮/菜单全部走 features/app.css 的主题变量，dawn 亮底下不再是深色胶囊。
     这个脚本只在 features/ 页引入，页面一定有 --s1/--ln2/--tx/--ac 这套变量。 */
  var css = [
    '.yl-theme{position:relative;display:inline-flex;align-items:center;flex:0 0 auto;z-index:9000;',
    '  font-family:var(--fs),system-ui,sans-serif}',
    '.yl-theme>button{display:inline-flex;align-items:center;gap:6px;height:26px;padding:0 10px;',
    '  border:1px solid var(--ln2);border-radius:999px;background:var(--s2);',
    '  color:var(--tx);font-family:inherit;font-size:var(--fz);line-height:1;cursor:pointer;white-space:nowrap}',
    '.yl-theme>button:hover{border-color:var(--ac);color:var(--ac)}',
    '.yl-theme>button i{width:7px;height:7px;border-radius:50%;flex:0 0 auto;display:inline-block}',
    '.yl-tmenu{position:fixed;min-width:150px;padding:5px;display:none;z-index:9999;',
    '  background:var(--modal);border:1px solid var(--ln2);border-radius:10px;',
    '  box-shadow:0 18px 46px -12px var(--shade);font-family:var(--fs),system-ui,sans-serif}',
    '.yl-tmenu [role="menuitemradio"]{display:flex;align-items:center;gap:9px;width:100%;',
    '  padding:8px 11px;border-radius:6px;color:var(--tx2);font-size:var(--fz);line-height:1.3;',
    '  text-align:left;cursor:pointer}',
    '.yl-tmenu [role="menuitemradio"]:hover,.yl-tmenu [role="menuitemradio"]:focus-visible{background:var(--s3);color:var(--ac)}',
    '.yl-tmenu [role="menuitemradio"] i{width:9px;height:9px;border-radius:50%;flex:0 0 auto}',
    '.yl-tmenu [role="menuitemradio"] .ck{margin-left:auto;color:var(--ac);font-size:var(--fz)}',
    '.yl-tmenu .hd{padding:5px 11px 7px;color:var(--tx3);font-size:var(--fz);border-bottom:1px solid var(--ln2);margin-bottom:4px}'
  ].join('\n');
  var st = document.createElement('style');
  st.id = 'yl-theme-css';
  st.textContent = css;
  document.head.appendChild(st);

  var nav = document.createElement('div');
  nav.className = 'yl-theme';
  var btn = document.createElement('button');
  btn.type = 'button';
  bar.appendChild(nav);
  nav.appendChild(btn);

  var menu = document.createElement('div');
  menu.className = 'yl-tmenu';
  menu.setAttribute('role', 'menu');
  menu.setAttribute('aria-label', '选择原型主题');
  var hd = document.createElement('div');
  hd.className = 'hd';
  hd.textContent = '主题 · 记在本机';
  menu.appendChild(hd);
  THEMES.forEach(function (t) {
    var m = document.createElement('button');
    m.type = 'button';
    m.setAttribute('role', 'menuitemradio');
    m.dataset.theme = t[0];
    m.innerHTML = '<i style="background:' + t[2] + '"></i><span>' + t[1] + '</span>'
      + '<span class="ck" aria-hidden="true"></span>';
    menu.appendChild(m);
  });
  document.body.appendChild(menu);
  apply(cur, false);

  function place() {
    if (menu.style.display !== 'block') return;
    var r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 6) + 'px';
    menu.style.right = Math.max(8, Math.round(window.innerWidth - r.right)) + 'px';
  }
  function open() {
    menu.style.display = 'block';
    place();
    var on = menu.querySelector('[aria-checked="true"]') || menu.querySelector('[role="menuitemradio"]');
    if (on) on.focus();
  }
  function close(returnFocus) {
    menu.style.display = 'none';
    if (returnFocus) btn.focus();
  }
  btn.addEventListener('click', function (e) {
    e.stopPropagation();
    if (menu.style.display === 'block') close(true); else open();
  });
  menu.addEventListener('click', function (e) {
    var m = e.target.closest('[role="menuitemradio"]');
    if (!m) return;
    apply(m.dataset.theme, true);
    close(true);
  });
  menu.addEventListener('keydown', function (e) {
    var items = Array.prototype.slice.call(menu.querySelectorAll('[role="menuitemradio"]'));
    var i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (i < 0) i = 0;
      else i = (e.key === 'ArrowDown') ? (i + 1) % items.length : (i - 1 + items.length) % items.length;
      items[i].focus();
    } else if (e.key === 'Home' || e.key === 'End') {
      e.preventDefault();
      items[e.key === 'Home' ? 0 : items.length - 1].focus();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (i >= 0) { apply(items[i].dataset.theme, true); close(true); }
    }
  });
  document.addEventListener('click', function (e) {
    if (menu.style.display === 'block' && !menu.contains(e.target) && !nav.contains(e.target)) close(false);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && menu.style.display === 'block') { e.stopPropagation(); close(true); }
  });
  window.addEventListener('resize', place);
})();
