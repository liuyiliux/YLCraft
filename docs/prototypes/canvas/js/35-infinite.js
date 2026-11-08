/* 35-infinite.js — 连线图做成真·无限画布（2026-11-03）
   之前：内容是固定尺寸的滚动区，往右下拖到头就没了，往左上顶死在原点。
   文档里写的是「无限画布」（LibTV 拆解原文：「无限画布是我们创作的主战场」）。

   现在：
   · 拖空白处平移（光标变抓手）—— 不用去够滚动条
   · 往左上拖：世界坐标重锚（02-canvas.js 的节点拖拽里做），画布永远"还有地方"
   · 往右下拖：拖拽时实时撑大内容区
   · Ctrl+滚轮缩放、双击空白复位 沿用 31-zoom.js

   不做的事：不改缩放实现、不做框选（没有这个需求，别塞）。 */

(function infiniteCanvasBoot(){
  function boot(){
    const c = document.querySelector('#flowGraphView .gcanvas');
    if (!c || c.dataset.infWired) return;
    c.dataset.infWired = '1';

    let pan = null;

    function isBackground(t){
      /* 节点 / 端口 / 连线 / 参数浮层 / 小地图 / 提示条 —— 都不是背景 */
      if (!t) return false;
      /* 节点工作台浮层 / 右侧折叠竖条也是前景，点它们不该触发平移或取消选中 */
      if (t.closest('.gnode, .gmap, .gparams, #groupBar, .ghint, .nodelib, .nwb, #agPeek, .cmp-ov, .dg-ov')) return false;
      if (t.tagName === 'path' || t.closest('svg.gedges')) return false;
      return true;
    }

    c.addEventListener('pointerdown', e => {
      if (e.button !== 0) return;                 // 只左键
      if (!isBackground(e.target)) return;
      /* 点空白 = 取消节点选中，连线恢复默认亮度（Esc 同效，见 08-events.js） */
      if (typeof clearEdgeFocus === 'function') clearEdgeFocus();
      /* 空白处双击要留给「缩放复位」，所以不抢 dblclick */
      pan = { x: e.clientX, y: e.clientY, sl: c.scrollLeft, st: c.scrollTop };
      c.classList.add('panning');
      c.setPointerCapture(e.pointerId);
    });

    c.addEventListener('pointermove', e => {
      if (!pan) return;
      c.scrollLeft = pan.sl - (e.clientX - pan.x);
      c.scrollTop  = pan.st - (e.clientY - pan.y);
    });

    function endPan(e){
      if (!pan) return;
      pan = null;
      c.classList.remove('panning');
      try { c.releasePointerCapture(e.pointerId); } catch(_){}
    }
    c.addEventListener('pointerup', endPan);
    c.addEventListener('pointercancel', endPan);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
