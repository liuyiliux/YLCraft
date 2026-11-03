/* 11-floatbar.js - split from canvas_unified_v14.html (lines 2937-3032) */
/* ================= 选中图片 → 上方浮出工具条（照 Lovart 改） =================
   Lovart 3.1：图片上方浮出的快捷工具条（7 项）
   [⇥ 快捷编辑] [⛶ 放大] [◑ 去背景] [✎ 橡皮工具] [⋯]  |  [◫ 画同款] [↓ 下载]
   注意：点了不弹大图，就地操作；「放大」才是主动看大图。
*/

let floatBarEl = null;
let floatTarget = null;

function showFloatBar(anchorEl, item){
  hideFloatBar();
  if (!anchorEl || !item) return;
  floatTarget = item.id;
  const r = anchorEl.getBoundingClientRect();
  if (r.width === 0){ return; }

  const bar = document.createElement('div');
  bar.className = 'floatbar';
  bar.id = 'floatBar';
  bar.innerHTML = `
    <button class="fb-b" title="快捷编辑" onclick="fbAct('edit')">
      <svg class="ic sm" viewBox="0 0 24 24"><path d="M4 20h4L20 8l-4-4L4 16z"/></svg>
      <span>快捷编辑</span>
    </button>
    <button class="fb-b" title="放大查看" onclick="fbAct('zoom')">
      <svg class="ic sm" viewBox="0 0 24 24"><path d="M4 9V4h5M20 15v5h-5M15 4h5v5M9 20H4v-5"/></svg>
    </button>
    <button class="fb-b" title="去背景" onclick="fbAct('cutout')">
      <svg class="ic sm" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M8 12h8"/></svg>
    </button>
    <button class="fb-b" title="橡皮擦" onclick="fbAct('eraser')">
      <svg class="ic sm" viewBox="0 0 24 24"><path d="M4 16l8-8 6 6-6 6H6z"/><path d="M9 21h11"/></svg>
    </button>
    <button class="fb-b" title="更多能力" onclick="fbAct('more')">
      <span style="letter-spacing:1px">⋯</span>
    </button>
    <span class="fb-sep"></span>
    <button class="fb-b" title="画同款" onclick="fbAct('same')">
      <svg class="ic sm" viewBox="0 0 24 24"><rect x="4" y="4" width="12" height="12" rx="2"/><path d="M8 20h10a2 2 0 0 0 2-2V8"/></svg>
      <span>画同款</span>
    </button>
    <button class="fb-b" title="导出（合成所有层）" onclick="fbAct('export')">
      <svg class="ic sm" viewBox="0 0 24 24"><path d="M4 16v3h16v-3"/><path d="M12 4v10M8 10l4 4 4-4"/></svg>
    </button>
    <button class="fb-b" title="下载" onclick="fbAct('download')">
      <svg class="ic sm" viewBox="0 0 24 24"><path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/></svg>
    </button>
  `;
  // 先挂上去量宽度，再定位（避免超出屏幕）
  bar.style.left = '0px';
  bar.style.top = '-9999px';
  document.body.appendChild(bar);
  floatBarEl = bar;
  const bw = bar.offsetWidth;
  const bh = bar.offsetHeight;
  let left = r.left + r.width / 2 - bw / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - bw - 8));
  let top = r.top - bh - 8;
  /* 原来写死 top < 56 才避让，但顶栏 52 + 统计条 34 = 86 —— 算出来 58 刚好卡在
     统计条上（临界值漏掉了）。改成量统计条的实际底边（2026-11-03） */
  const sbarEl = document.querySelector('#vShots .sbar');
  const limit = sbarEl ? sbarEl.getBoundingClientRect().bottom + 6 : 56;
  if (top < limit) top = r.bottom + 8;
  bar.style.left = left + 'px';
  bar.style.top = top + 'px';
}

function hideFloatBar(){
  if (floatBarEl){ floatBarEl.remove(); floatBarEl = null; }
  floatTarget = null;
}

function fbAct(act){
  const id = floatTarget;
  const item = id ? DOC.items.find(x=>x.id===id) : null;
  if (!item){ hideFloatBar(); return; }
  if (act === 'zoom'){ openLB(id); return; }
  if (act === 'more'){ fbMore(); return; }
  if (act === 'edit'){ openLocalEdit(id); return; }
  if (act === 'export'){ openExport(); return; }
  if (act === 'cutout'){ toast('去背景 · 输出透明底 PNG'); return; }
  if (act === 'eraser'){ toast('橡皮擦 · 擦掉不要的部分'); return; }
  if (act === 'same'){ toast('画同款 · 照这张的风格再出一张'); return; }
  if (act === 'download'){ toast('下载原图'); return; }
}

/* 滚动 / 缩放时收起来（跟着算太抖，不如直接藏） */
function bindFloatBarHide(){
  ['grid','freecv'].forEach(id=>{
    const el = document.getElementById(id);
    if (el) el.addEventListener('scroll', hideFloatBar, { passive:true });
  });
  window.addEventListener('resize', hideFloatBar);
  document.addEventListener('click', e=>{
    if (e.target.closest('.floatbar')) return;
    if (e.target.closest('.shot') || e.target.closest('.item')) return;
    hideFloatBar();
  });
}


