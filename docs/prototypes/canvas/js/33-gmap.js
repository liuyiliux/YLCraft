/* 33-gmap.js — 连线图小地图（BeefTV 欠账 #1，2026-11-03）
   背景：节点放大成大图卡片（208 高）后，12 个节点铺 4 行，
   画布又长又宽，找节点要滚半天 —— 台账里 BeefTV 的「小地图」欠账正好还上。

   · 右下角常驻：节点缩成色块（按类型着色）+ 视口框（青色）
   · 点 / 拖地图 → 视口中心跳到那个位置
   · 跟滚动、缩放、节点增删联动（滚动/缩放事件里重画）

   坐标系说明（这个容易错）：
   - .gcanvas 是滚动容器，#ginner 是内容；缩放走 CSS transform（CV_ZOOM / CV_PAN）
   - transform 不影响布局，所以 scrollLeft/scrollTop 是「未缩放的布局像素」
   - 内容点 L 的屏幕位置 = canvasRect.left - scrollLeft + CV_PAN.x + L * CV_ZOOM
     —— 视口框和跳转都从这一个式子推，别各自瞎算 */

const GMAP_W = 168, GMAP_H = 108;

function gmapEls(){
  return {
    map:    document.getElementById('gmap'),
    canvas: document.querySelector('#flowGraphView .gcanvas'),
    inner:  document.getElementById('ginner')
  };
}

function gmapScale(inner){
  return Math.min(GMAP_W / inner.offsetWidth, GMAP_H / inner.offsetHeight);
}

function updateGmap(){
  const { map, canvas, inner } = gmapEls();
  if (!map || !canvas || !inner) return;
  /* 🔴 不能用 map.offsetParent 判可见 —— 地图初始就带 hidden（display:none），
     offsetParent 永远是 null，会把自己锁死。用滚动容器的宽度判：视图切走时它归 0。 */
  if (canvas.clientWidth < 80 || inner.offsetWidth < 120){
    map.classList.add('hidden');
    return;
  }
  map.classList.remove('hidden');

  const s = gmapScale(inner);
  const gr = inner.getBoundingClientRect();
  const cr = canvas.getBoundingClientRect();
  /* 视口在内容（未缩放）坐标里的框 —— 含缩放与平移，getBoundingClientRect 自带 */
  const vx = (cr.left - gr.left) / CV_ZOOM;
  const vy = (cr.top  - gr.top)  / CV_ZOOM;
  const vw = cr.width  / CV_ZOOM;
  const vh = cr.height / CV_ZOOM;

  let dots = '';
  GRAPH.nodes.forEach(n => {
    const h = n.h || 54;
    const c = KIND_COLOR[n.kind] || KIND_COLOR.any;
    dots += `<i style="left:${(n.x*s).toFixed(1)}px;top:${(n.y*s).toFixed(1)}px;`
      + `width:${Math.max(2.5, n.w*s).toFixed(1)}px;height:${Math.max(2.5, h*s).toFixed(1)}px;`
      + `background:${c}"></i>`;
  });

  map.innerHTML = dots
    + `<b style="left:${Math.max(0,vx*s).toFixed(1)}px;top:${Math.max(0,vy*s).toFixed(1)}px;`
    + `width:${Math.min(GMAP_W, vw*s).toFixed(1)}px;height:${Math.min(GMAP_H, vh*s).toFixed(1)}px"></b>`;
}

/* 点 / 拖地图：把那个内容点放到视口中央 */
function gmapJump(e){
  const { map, canvas, inner } = gmapEls();
  if (!map || !canvas || !inner) return;
  const r = map.getBoundingClientRect();
  const s = gmapScale(inner);
  const L = (e.clientX - r.left) / s;   /* 内容布局坐标 */
  const T = (e.clientY - r.top)  / s;
  /* 从屏幕位置式反解：scrollLeft = CV_PAN.x + L*CV_ZOOM - 视口宽/2 */
  canvas.scrollLeft = Math.max(0, CV_PAN.x + L * CV_ZOOM - canvas.clientWidth  / 2);
  canvas.scrollTop  = Math.max(0, CV_PAN.y + T * CV_ZOOM - canvas.clientHeight / 2);
  updateGmap();
}

(function gmapBoot(){
  function boot(){
    const { map, canvas } = gmapEls();
    if (!map || !canvas) return;

    let dragging = false;
    map.addEventListener('pointerdown', e => {
      e.preventDefault();
      dragging = true;
      map.setPointerCapture(e.pointerId);
      gmapJump(e);
    });
    map.addEventListener('pointermove', e => { if (dragging) gmapJump(e); });
    map.addEventListener('pointerup',   () => { dragging = false; });
    map.addEventListener('pointercancel', () => { dragging = false; });

    canvas.addEventListener('scroll', () => updateGmap(), { passive: true });
    window.addEventListener('resize', () => updateGmap());

    updateGmap();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
