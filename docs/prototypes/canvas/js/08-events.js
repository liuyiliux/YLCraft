/* 08-events.js - split from canvas_unified_v14.html (lines 1947-2033) */
/* ================= 事件 ================= */
document.addEventListener('click', e=>{
  if (ctxEl && !e.target.closest('.ctx')) closeCtx();
  if (!e.target.closest('.item') && !e.target.closest('.shot') && mode==='free'){
    selId=null; renderFree();
  }
});
document.addEventListener('keydown', e=>{
  if(e.key==='Tab' && mode==='flow' && flowView==='graph'){
    e.preventDefault(); toggleGroup(); return;
  }
  if(e.key==='Escape'){
    if(ctxEl) closeCtx();
    else if(document.querySelector('.lb')) closeLB();
  }
});
const ta = document.getElementById('ta');
ta.addEventListener('input', ()=>{ ta.rows=Math.min(3,Math.max(1,Math.ceil(ta.value.length/34)||1)); });
ta.addEventListener('keydown', e=>{ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); send(); } });

renderUserChip(); renderCanvasName(); renderTplRefBar();
setMode('shots');
/* 🔴 bindFloatBarHide 定义在 11-floatbar.js（后面才加载）——
   直接调用会 ReferenceError 并中断后面所有脚本。
   用 typeof 守卫，等 DOM ready 再绑。 */
if (typeof bindFloatBarHide === 'function') bindFloatBarHide();
else document.addEventListener('DOMContentLoaded', ()=>{
  if (typeof bindFloatBarHide === 'function') bindFloatBarHide();
});

/* 原型演示工具条：搜索失败 / 注入（真实现里不该有） */
(function mountFailTools(){
  const host = document.getElementById('agb');
  if (!host) return;
  const d = document.createElement('div');
  d.className = 'msg ai'; d.id = 'failToolsMsg';
  d.innerHTML = `<div class="who">演示</div><div class="bubble" style="padding:9px 11px">${failToolbar()}
    <div style="font-size:9.5px;color:var(--tx3);margin-top:6px;line-height:1.6">
      真搜索一定会失败。这三种要分开说 —— 别把"查不到"说成"没有"。
    </div></div>`;
  host.appendChild(d);
})();

/* 被平台壳嵌入时（?embed=1），隐藏壳已经提供的元素，避免重复 */
if (new URLSearchParams(location.search).get('embed') === '1'){
  const st = document.createElement('style');
  st.textContent = '.brand,#userChip{display:none!important}.top{gap:7px}';
  document.head.appendChild(st);
}

/* ================= P4：context chips 可移除（画布侧） ================= */
let disabledCites = new Set();

agChips = function(list){
  if (!list || !list.length) return;
  const host = agb.lastElementChild;
  if (!host) return;
  const d = document.createElement('div');
  d.className = 'ctxchips';
  d.innerHTML = `<span class="cc-l">使用了</span>`
    + list.map(c=>{
        const off = disabledCites.has(c.t);
        return `<span class="cc-i ${off?'off':''}" style="border-color:${(CITE_COLOR[c.k]||'#71717a')}44">
          <span class="cc-d" style="background:${CITE_COLOR[c.k]||'#71717a'}"></span>
          <span class="cc-t">${c.t}</span>
          <span class="cc-x" onclick="disableCite('${c.t}',this)" title="这条别用了">✕</span>
        </span>`;
      }).join('');
  host.appendChild(d);
  agb.scrollTop = agb.scrollHeight;
};

function disableCite(title, el){
  disabledCites.add(title);
  const chip = el.closest('.cc-i');
  if (chip) chip.classList.add('off');
  agAdd('ai', `好，以后<b>不再引用</b>《${esc(title)}》。<br><br>`
    + `<span class="myown">需要的话可以在知识库里重新启用它。本次回答里已经用到的那段保留，不回滚。</span>`);
  toast('已停用：《' + title + '》');
}

(function chipCSS(){
  const st = document.createElement('style');
  st.textContent = `
    .cc-i .cc-t{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .cc-i.off{opacity:.42;text-decoration:line-through}
    .cc-x{margin-left:3px;opacity:.5;cursor:pointer;font-size:8px;padding:0 1px;line-height:1}
    .cc-x:hover{opacity:1;color:var(--dg)}
  `;
  document.head.appendChild(st);
})();


