/* ============================================================
   原项目功能原型 · 共享小工具（2026-11-20 按 modern-web-guidance 收口）
   ------------------------------------------------------------
   · dialog / light-dismiss-a-dialog：原生 <dialog> + showModal() + closedby="any"，
     不再手写遮罩、不再绑 Esc、不做焦点陷阱（浏览器自带 inert / 顶层 / 焦点返回）。
   · tabs：aria-selected 是唯一状态源，面板用 hidden="until-found"，方向键可切换。
   · switch：原生 checkbox，change 时同步 aria-checked（Chrome 暂不支持 switch 属性）。
   ============================================================ */
(function (w, d) {
  function $(s, r) { return (r || d).querySelector(s); }
  function $$(s, r) { return Array.prototype.slice.call((r || d).querySelectorAll(s)); }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var timer = null;
  function toast(msg) {
    var el = $('#toast');
    if (!el) {
      el = d.createElement('div'); el.id = 'toast'; d.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add('on');
    clearTimeout(timer);
    timer = setTimeout(function () { el.classList.remove('on'); }, 2400);
  }

  /* ---------- 原生 dialog ---------- */
  /* html 必须自带 <dialog class="modal" closedby="any" aria-labelledby="…"> */
  function openDialog(html) {
    closeOv();
    d.body.insertAdjacentHTML('beforeend', html);
    var all = $$('dialog.modal');
    var dlg = all[all.length - 1];
    if (!dlg) return null;

    /* close 事件统一清理 DOM；不用 click 事件承载关闭前的关键逻辑 */
    dlg.addEventListener('close', function () { dlg.remove(); });

    /* light-dismiss-a-dialog 的 MANDATORY fallback：Safari 等不支持 closedby 时
       判断点击是否落在 dialog 内容盒之外，再手动 close */
    if (!('closedBy' in HTMLDialogElement.prototype)) {
      dlg.addEventListener('click', function (e) {
        if (e.target !== dlg) return;
        var r = dlg.getBoundingClientRect();
        var inside = r.top <= e.clientY && e.clientY <= r.bottom
          && r.left <= e.clientX && e.clientX <= r.right;
        if (!inside) dlg.close();
      });
    }
    dlg.showModal();
    return dlg;
  }

  function closeOv() {
    $$('dialog.modal[open]').forEach(function (x) { x.close(); });
  }

  /* 只保留「关闭按钮」；Esc 由原生 dialog 处理，遮罩由 closedby / fallback 处理 */
  d.addEventListener('click', function (e) {
    var x = e.target.closest && e.target.closest('[data-close-ov]');
    if (x) closeOv();
  });

  /* ---------- Tabs ---------- */
  function tabScope(box) {
    var s = box.parentNode;
    while (s && s !== d.body && !s.querySelector('[data-pane]')) s = s.parentNode;
    return (s && s !== d.body && s !== d) ? s : d;
  }
  function selectTab(box, tab, moveFocus) {
    var scope = tabScope(box);
    var tabs = $$('[data-tab]', box);
    tabs.forEach(function (t) {
      var on = t === tab;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      /* focusgroup="… nomemory" 时把起点跟着选中项走 */
      if (box.hasAttribute('focusgroup')) t.toggleAttribute('focusgroupstart', on);
    });
    $$('[data-pane]', scope).forEach(function (p) {
      if (p.dataset.pane === tab.dataset.tab) p.removeAttribute('hidden');
      else p.setAttribute('hidden', 'until-found');
    });
    if (moveFocus) tab.focus();
  }
  function bindTabs(root) {
    $$('[data-tabs]', root || d).forEach(function (box) {
      var scope = tabScope(box);
      var tabs = $$('[data-tab]', box);
      /* 初始状态以 HTML 为准，这里只补齐 tabindex / hidden（HTML 已写 aria-selected + hidden） */
      var active = tabs.filter(function (t) { return t.getAttribute('aria-selected') === 'true'; })[0] || tabs[0];
      if (active) selectTab(box, active, false);

      box.addEventListener('click', function (e) {
        var b = e.target.closest('[data-tab]');
        if (b && box.contains(b)) selectTab(box, b, false);
      });

      /* selection-follows-focus：方向键换焦点即换选中项。
         focusgroup 只负责 role 与焦点顺序，aria-selected 仍要脚本同步（指南示例即如此）；
         preventDefault 避免与浏览器默认方向键行为叠加。 */
      box.addEventListener('keydown', function (e) {
        var i = tabs.indexOf(d.activeElement);
        if (i < 0) return;
        var n = -1;
        if (e.key === 'ArrowRight') n = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') n = 0;
        else if (e.key === 'End') n = tabs.length - 1;
        if (n < 0) return;
        e.preventDefault();
        selectTab(box, tabs[n], true);
      });

      /* find-in-page 命中隐藏面板时同步选中态 */
      $$('[data-pane]', scope).forEach(function (p) {
        p.addEventListener('beforematch', function () {
          var t = tabs.filter(function (x) { return x.dataset.tab === p.dataset.pane; })[0];
          if (t) selectTab(box, t, false);
        });
      });
    });
  }

  /* ---------- Switch：原生 checked → aria-checked ---------- */
  function bindSwitches(root) {
    $$('input[switch]', root || d).forEach(function (el) {
      if (el.dataset.swBound) return;
      el.dataset.swBound = '1';
      el.setAttribute('aria-checked', el.checked ? 'true' : 'false');
      el.addEventListener('change', function () {
        el.setAttribute('aria-checked', el.checked ? 'true' : 'false');
      });
    });
  }

  w.FP = { $: $, $$: $$, esc: esc, toast: toast,
           openDialog: openDialog, closeOv: closeOv,
           bindTabs: bindTabs, bindSwitches: bindSwitches };
  d.addEventListener('DOMContentLoaded', function () {
    bindTabs(); bindSwitches();
  });
})(window, document);
