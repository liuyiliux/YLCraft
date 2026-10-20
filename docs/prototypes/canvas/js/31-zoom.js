/* 31-zoom.js — 画布缩放（Ctrl+滚轮）
   🔴 2026-10-20 用户报的问题：
      「ctrl 加滚轮是页面放大不是画布放大」
      查证：全项目**根本没有 wheel 事件**，Ctrl+滚轮走的是浏览器默认的页面缩放。

   现在：
     · Ctrl/⌘ + 滚轮 → 缩放画布（不是页面）
     · 以鼠标位置为中心缩放（不是以左上角）
     · 自由画布 / 连线图都支持
     · 右上角显示当前缩放百分比，点一下复位
*/

let CV_ZOOM = 1;
let CV_PAN = { x: 0, y: 0 };
const CV_ZOOM_MIN = 0.2;
const CV_ZOOM_MAX = 4;

/* 哪些容器要缩放 */
function zoomTargets(){
  const out = [];
  const free = document.getElementById('freecv');
  if (free) out.push({ el: free, kind: 'free' });
  const ginner = document.getElementById('ginner');
  if (ginner) out.push({ el: ginner, kind: 'graph' });
  return out;
}

/* 当前可见的是哪个（用 offsetParent / 尺寸判断） */
function activeZoomTarget(){
  const list = zoomTargets();
  for (const t of list){
    const r = t.el.getBoundingClientRect();
    if (r.width > 40 && r.height > 40 && t.el.offsetParent !== null) return t;
  }
  return null;
}

function applyZoom(){
  const t = activeZoomTarget();
  if (!t) return;
  t.el.style.transformOrigin = '0 0';
  t.el.style.transform = 'translate(' + CV_PAN.x + 'px,' + CV_PAN.y + 'px) scale(' + CV_ZOOM.toFixed(3) + ')';
  updateZoomBadge();
}

function resetZoom(){
  CV_ZOOM = 1;
  CV_PAN = { x: 0, y: 0 };
  applyZoom();
  toast('缩放已复位 100%');
}

function updateZoomBadge(){
  let b = document.getElementById('zoomBadge');
  if (!b){
    b = document.createElement('div');
    b.id = 'zoomBadge';
    b.className = 'zoom-badge';
    b.title = '点一下复位 100%';
    b.onclick = resetZoom;
    document.body.appendChild(b);
  }
  const pct = Math.round(CV_ZOOM * 100);
  b.textContent = pct + '%';
  b.classList.toggle('off', pct === 100);
}

/* ===== Ctrl + 滚轮 ===== */
document.addEventListener('wheel', (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;      // 普通滚轮不拦，留给页面滚动

  const t = activeZoomTarget();
  if (!t) return;
  if (!t.el.contains(e.target) && e.target !== t.el) return;

  /* 🔴 关键：阻止浏览器默认的"页面缩放" */
  e.preventDefault();

  const rect = t.el.parentElement ? t.el.parentElement.getBoundingClientRect() : t.el.getBoundingClientRect();

  /* 鼠标在容器内容坐标里的位置（缩放前） */
  const px = (e.clientX - rect.left - CV_PAN.x) / CV_ZOOM;
  const py = (e.clientY - rect.top - CV_PAN.y) / CV_ZOOM;

  const step = e.deltaY > 0 ? -0.12 : 0.12;
  const next = Math.max(CV_ZOOM_MIN, Math.min(CV_ZOOM_MAX, CV_ZOOM * (1 + step)));
  if (Math.abs(next - CV_ZOOM) < 0.001) return;
  CV_ZOOM = next;

  /* 让鼠标下的那个点保持不动 */
  CV_PAN.x = e.clientX - rect.left - px * CV_ZOOM;
  CV_PAN.y = e.clientY - rect.top - py * CV_ZOOM;

  applyZoom();
}, { passive: false });

/* 双击空白处复位（不影响双击曲线等其他地方） */
document.addEventListener('dblclick', (e) => {
  const t = activeZoomTarget();
  if (!t) return;
  if (e.target === t.el || e.target.classList.contains('grid') || e.target.classList.contains('dotgrid')){
    resetZoom();
  }
});

/* 切换模式后重新挂载（transform 会随 DOM 重建丢失） */
(function zoomBoot(){
  function sync(){
    applyZoom();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync);
  else sync();

  /* 观察容器内容变化，重建后恢复 transform */
  const iv = setInterval(()=>{
    const t = activeZoomTarget();
    if (t && t.el.style.transform.indexOf('scale') < 0){
      applyZoom();
    }
    updateZoomBadge();
  }, 800);
  setTimeout(()=>clearInterval(iv), 60000);   // 60 秒后停，避免一直跑
})();
