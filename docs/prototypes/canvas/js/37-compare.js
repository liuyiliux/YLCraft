/* 37-compare.js — 原图 / 生成图对比（2026-11-08 原型收口第 1 批 ②）
 *
 * 画面核销结论：以前只有人像修饰深层的「👁 看原图」和精调的「按住对比原图」，
 * 日常路径没有入口。这里把它接到节点选中态的工具条上，并提供两种形态：
 *   · 拖动分割：同一位置上下两层，拖中间线看「改了多少」（修图软件常态）
 *   · 并排：左右各一张，看整体差异
 *
 * 边界：原型不生成像素，「生成图」用同一张占位片加 CSS 滤镜示意差异，
 *       浮层里明说这一点，不假装是真模型输出。
 * 挂 body + fixed，不挂 .ginner（那块会被整体 scale）；定位只改 style，不重建 DOM。
 */
(function compare(){
  let host = null, mode = 'split', pct = 50, onKey = null, dragging = false;
  const FALLBACK = "url('assets/thumbs/story-01.svg')";

  function escTxt(s){
    return String(s==null?'':s).replace(/[&<>"]/g,c=>({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }

  /* 直接读选中节点画面上那张图，保证对比的就是用户刚点的那张 */
  function pickBg(id){
    const el = id ? document.querySelector('#gnodes .gnode[data-id="' + id + '"] .gimg') : null;
    const bg = el ? getComputedStyle(el).backgroundImage : '';
    return (bg && bg !== 'none') ? bg : FALLBACK;
  }
  function pickTitle(id){
    const n = (typeof GRAPH !== 'undefined' && GRAPH.nodes || []).find(x=>x.id===id);
    return n ? n.t : '当前镜头';
  }

  function setSplit(v){
    pct = Math.max(2, Math.min(98, Number(v)));
    const line = document.getElementById('cmpLine');
    const old  = document.getElementById('cmpOld');
    if (line) line.style.left = pct + '%';
    if (old)  old.style.clipPath = 'inset(0 ' + (100 - pct) + '% 0 0)';
  }

  function setMode(m){
    mode = m === 'side' ? 'side' : 'split';
    const stage = document.getElementById('cmpStage');
    if (stage) stage.classList.toggle('side', mode === 'side');
    host.querySelectorAll('[data-cmp="mode"]').forEach(b=>{
      b.classList.toggle('on', b.dataset.mode === mode);
    });
    if (mode === 'split') setSplit(pct);
  }

  function onPointer(e){
    const stage = document.getElementById('cmpStage');
    if (!stage || mode !== 'split') return;
    const r = stage.getBoundingClientRect();
    if (!r.width) return;
    if (e.type === 'pointerdown'){
      dragging = true;
      stage.setPointerCapture && stage.setPointerCapture(e.pointerId);
    }
    if (!dragging) return;
    e.preventDefault();
    setSplit(((e.clientX - r.left) / r.width) * 100);
  }

  function onUp(e){
    dragging = false;
    const stage = document.getElementById('cmpStage');
    if (stage && stage.releasePointerCapture && e.pointerId != null){
      try { stage.releasePointerCapture(e.pointerId); } catch(_){}
    }
  }

  function closeCompare(){
    if (onKey){ document.removeEventListener('keydown', onKey); onKey = null; }
    if (host){ host.remove(); host = null; }
    dragging = false;
  }

  function openCompare(id){
    closeCompare();
    const bg = pickBg(id), title = pickTitle(id);
    host = document.createElement('div');
    host.className = 'cmp-ov';
    host.id = 'cmpOv';
    host.innerHTML =
      '<div class="cmp-w" role="dialog" aria-label="原图与生成图对比">'
      + '<div class="cmp-hd"><div>'
      +   '<div class="cmp-t">原图 / 生成图对比</div>'
      +   '<div class="cmp-s">' + escTxt(title) + ' · 拖动中间分割线看改了多少</div>'
      + '</div><div class="cmp-hd-r">'
      +   '<button class="cmp-btn on" data-cmp="mode" data-mode="split">拖动分割</button>'
      +   '<button class="cmp-btn" data-cmp="mode" data-mode="side">并排</button>'
      +   '<button class="cmp-btn" data-cmp="close" title="关闭（Esc 同效）">✕</button>'
      + '</div></div>'
      + '<div class="cmp-body"><div class="cmp-stage" id="cmpStage">'
      +   '<div class="cmp-img cmp-old" id="cmpOld"></div>'
      +   '<div class="cmp-img cmp-new" id="cmpNew"></div>'
      +   '<div class="cmp-line" id="cmpLine"><span class="cmp-handle">⇔</span></div>'
      +   '<span class="cmp-tag l">原图</span><span class="cmp-tag r">生成图</span>'
      + '</div></div>'
      + '<div class="cmp-ft"><span>示意：右侧「生成图」用同一张占位片加 CSS 滤镜表达差异，'
      + '原型不生成像素；真实实现这里放原图 URL 与生成结果 URL。</span>'
      + '<button class="cmp-btn" data-cmp="close">关闭</button></div>'
      + '</div>';
    document.body.appendChild(host);
    document.getElementById('cmpOld').style.backgroundImage = bg;
    document.getElementById('cmpNew').style.backgroundImage = bg;

    const stage = document.getElementById('cmpStage');
    stage.addEventListener('pointerdown', onPointer);
    stage.addEventListener('pointermove', onPointer);
    stage.addEventListener('pointerup', onUp);
    stage.addEventListener('pointercancel', onUp);

    host.addEventListener('click', e=>{
      if (e.target === host){ closeCompare(); return; }
      const b = e.target.closest('[data-cmp]');
      if (!b) return;
      if (b.dataset.cmp === 'close') closeCompare();
      else if (b.dataset.cmp === 'mode') setMode(b.dataset.mode);
    });
    onKey = e=>{ if (e.key === 'Escape') closeCompare(); };
    document.addEventListener('keydown', onKey);
    setMode(mode);
  }

  window.openCompare = openCompare;
  window.closeCompare = closeCompare;
})();
