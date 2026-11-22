/* 39-jimeng-shell.js — 11-22 照 basketikun/infinite-canvas 抄的画布外壳。
   只加外壳，不改 01..38 的节点 / 连线 / 浮层逻辑：
     · 左侧节点栏改成窄图标栏（资产 / 节点两页 + 搜索）
     · 画布空白右键弹「选择节点」
     · 选中节点上方浅色胶囊条、节点下方紧凑输入框
     · 底部居中工具条 + 左下缩放条
   所有动作能落到原函数的就落原函数，其余明确 toast「原型占位」。 */
(function jimengShell(){
  var $  = function(s,r){ return (r||document).querySelector(s); };
  var $$ = function(s,r){ return Array.prototype.slice.call((r||document).querySelectorAll(s)); };
  var INJ = false, curWbId = null, origNlb = '';

  var SVG = {
    undo:'<path d="M9 7L4 12l5 5"/><path d="M4 12h9a6 6 0 0 1 0 12"/>',
    redo:'<path d="M15 7l5 5-5 5"/><path d="M20 12h-9a6 6 0 0 0 0 12"/>',
    text:'<path d="M4 6h16M4 12h10M4 18h7"/>',
    image:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/>',
    video:'<rect x="3" y="5" width="14" height="14" rx="2"/><path d="M17 10l4-3v10l-4-3z"/>',
    audio:'<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
    link:'<circle cx="6" cy="18" r="2.4"/><circle cx="18" cy="6" r="2.4"/><path d="M8 16L16 8"/>',
    del:'<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13"/>',
    reset:'<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>',
    settings:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1"/>',
    plus:'<path d="M12 5v14M5 12h14"/>'
  };
  function svg(p){ return '<svg class="ic sm" viewBox="0 0 24 24">'+p+'</svg>'; }
  function ico(p){ return '<svg class="ico" viewBox="0 0 24 24">'+p+'</svg>'; }

  function toast(t){ if (typeof window.toast === 'function') window.toast(t); }

  function inject(){
    if (INJ) return;
    var lib = $('.nodelib'), cv = $('.gcanvas');
    if (!lib || !cv) return;

    var head = document.createElement('div');
    head.innerHTML = '<div class="jm-tabs" role="tablist" aria-label="左侧面板">'
      + '<button type="button" data-jtab="assets" aria-pressed="false">资产</button>'
      + '<button type="button" data-jtab="nodes" aria-pressed="true" class="on">节点</button></div>'
      + '<div class="jm-tools"><span class="tip">右键画布 · 选择节点　全部 ▾</span>'
      + '<input type="search" aria-label="搜索节点" placeholder="搜索节点"></div>';
    lib.insertBefore(head, lib.firstChild);

    var nlb = $('.nlb', lib);
    if (nlb) origNlb = nlb.innerHTML;

    var dock = document.createElement('div');
    dock.className = 'jm-dock';
    dock.setAttribute('role','toolbar');
    dock.setAttribute('aria-label','画布工具');
    dock.innerHTML =
      '<button type="button" data-jm="undo" title="撤销">'+svg(SVG.undo)+'</button>'
      + '<button type="button" data-jm="redo" title="重做">'+svg(SVG.redo)+'</button>'
      + '<span class="sep"></span>'
      + '<button type="button" data-jm="text" title="加文本节点">'+svg(SVG.text)+'</button>'
      + '<button type="button" data-jm="image" title="加图片节点">'+svg(SVG.image)+'</button>'
      + '<button type="button" data-jm="video" title="加视频节点">'+svg(SVG.video)+'</button>'
      + '<button type="button" data-jm="bgm" title="加音频节点">'+svg(SVG.audio)+'</button>'
      + '<button type="button" data-jm="link" title="连线：拖节点边缘圆点">'+svg(SVG.link)+'</button>'
      + '<span class="sep"></span>'
      + '<button type="button" data-jm="del" class="danger" title="删除选中节点">'+svg(SVG.del)+'</button>';
    cv.appendChild(dock);

    var zm = document.createElement('div');
    zm.className = 'jm-zoom';
    zm.innerHTML = '<button type="button" data-jm="reset" title="复位 100%">'+svg(SVG.reset)+'</button>'
      + '<button type="button" data-jm="settings" title="画布设置（原型占位）">'+svg(SVG.settings)+'</button>'
      + '<input type="range" min="30" max="300" value="100" aria-label="画布缩放">'
      + '<span class="pct">100%</span>'
      + '<button type="button" data-jm="zi" title="放大">'+svg(SVG.plus)+'</button>';
    cv.appendChild(zm);

    var ctx = document.createElement('div');
    ctx.className = 'jm-ctx'; ctx.id = 'jmCtx';
    var items = [
      ['text','文本',SVG.text],['image','图片',SVG.image],['video','视频',SVG.video],
      ['audio','音频',SVG.audio],['group','组',SVG.link]
    ];
    ctx.innerHTML = '<div class="h">选择节点 <button type="button" data-jm-close aria-label="关闭">✕</button></div>'
      + items.map(function(x){
          return '<button class="it" type="button" data-jm-add="'+x[0]+'">'+ico(x[2])+'<span>'+x[1]+'</span></button>';
        }).join('');
    document.body.appendChild(ctx);

    INJ = true;
  }

  /* ---------- 左侧两页 + 搜索 ---------- */
  function initPanel(){
    var tabs = $$('.jm-tabs button');
    tabs.forEach(function(b){
      b.addEventListener('click', function(){
        tabs.forEach(function(x){
          var on = x === b;
          x.setAttribute('aria-pressed', on?'true':'false');
          x.classList.toggle('on', on);
        });
        var nlb = $('.nodelib .nlb');
        if (!nlb) return;
        if (b.dataset.jtab === 'assets'){
          var imgs = ['story-01','story-05','char-02','promo-02','story-08','char-04'];
          nlb.innerHTML = '<div class="jm-assets">' + imgs.map(function(f,i){
            return '<button type="button" data-jmasset="'+f+'" title="素材 '+(i+1)+'">'
              + '<img src="../canvas/assets/thumbs/'+f+'.svg" alt="">'
              + '<span>素材 '+(i+1)+'</span></button>';
          }).join('') + '</div>';
        } else {
          nlb.innerHTML = origNlb;
        }
      });
    });
    var inp = $('.jm-tools input');
    if (inp) inp.addEventListener('input', function(){
      var q = this.value.trim();
      $$('.nodelib .nli').forEach(function(el){
        el.style.display = (!q || el.textContent.indexOf(q) >= 0) ? '' : 'none';
      });
    });
  }

  /* ---------- 底部工具条 / 左下缩放 ---------- */
  function initDock(){
    var map = {text:'text', image:'image', video:'video', audio:'bgm', group:'gen-page'};
    $('.gcanvas').addEventListener('click', function(e){
      var b = e.target.closest('[data-jm]'); if (!b) return;
      var a = b.dataset.jm;
      if (a === 'undo'){ undo(); return; }
      if (a === 'redo'){ redo(); return; }
      if (a === 'del'){ delNode(); return; }
      if (a === 'reset'){ resetZoom(); return; }
      if (a === 'settings'){ toast('画布设置：网格 / 吸附 / 自动保存（原型占位）'); return; }
      if (a === 'link'){ toast('连线：拖节点边缘的圆点接到另一个节点'); return; }
      if (map[a]){ addNodeFromLib(map[a]); return; }
    });
    var rg = $('.jm-zoom input');
    if (rg) rg.addEventListener('input', function(){
      var v = +this.value;
      CV_ZOOM = v/100;
      applyZoom();
      $('.jm-zoom .pct').textContent = v+'%';
    });
  }

  /* ---------- 右键轻点 / 双击空白弹「选择节点」，右键按住拖拽平移 ----------
     参考项目：右键按下拖动 = 平移画布，右键单击 = 弹菜单；双击空白也弹菜单。
     35-infinite.js 只接管左键平移，这里补右键那半边，不碰它的实现。
     31-zoom.js 的「双击复位」被本文件的双击菜单取代；复位入口仍留在左下缩放条。 */
  function isBg(t){
    if (!t) return false;
    if (t.closest('.gnode, .gmap, .gparams, #groupBar, .ghint, .nodelib, .nwb, #agPeek, .cmp-ov, .dg-ov, .jm-dock, .jm-zoom, #jmCtx')) return false;
    if (t.tagName === 'path' || t.closest('svg.gedges')) return false;
    return true;
  }
  function openCtxAt(x, y){
    var ctx = $('#jmCtx'); if (!ctx) return;
    /* 上游 NodeCreateMenu 宽 240px（w-[240px]），定位按它算，别用旧 178 */
    ctx.style.left = Math.max(8, Math.min(x, window.innerWidth - 250))+'px';
    ctx.style.top  = Math.max(8, Math.min(y, window.innerHeight - 268))+'px';
    ctx.classList.add('on');
  }
  function initCtx(){
    var cv = $('.gcanvas'), ctx = $('#jmCtx');
    if (!cv || !ctx) return;
    var rp = null;   // right-button pan
    cv.addEventListener('contextmenu', function(e){
      if (!isBg(e.target)) return;
      e.preventDefault(); e.stopPropagation();   // 菜单改在 pointerup 里判断：拖过就不弹
    });
    cv.addEventListener('pointerdown', function(e){
      if (e.button !== 2 || !isBg(e.target)) return;
      rp = { x:e.clientX, y:e.clientY, sl:cv.scrollLeft, st:cv.scrollTop, moved:false };
      try { cv.setPointerCapture(e.pointerId); } catch(_){}
    });
    cv.addEventListener('pointermove', function(e){
      if (!rp) return;
      var dx = e.clientX - rp.x, dy = e.clientY - rp.y;
      if (!rp.moved && Math.abs(dx)+Math.abs(dy) < 5) return;
      rp.moved = true;
      cv.classList.add('panning');
      cv.scrollLeft = rp.sl - dx;
      cv.scrollTop  = rp.st - dy;
    });
    function endRight(e){
      if (!rp) return;
      var moved = rp.moved; rp = null;
      cv.classList.remove('panning');
      try { cv.releasePointerCapture(e.pointerId); } catch(_){}
      if (!moved && e.button === 2) openCtxAt(e.clientX, e.clientY);
    }
    cv.addEventListener('pointerup', endRight);
    cv.addEventListener('pointercancel', endRight);
    /* 双击空白弹同一份菜单（用 capture 抢在 31-zoom 的 document 监听之前） */
    cv.addEventListener('dblclick', function(e){
      if (!isBg(e.target)) return;
      e.preventDefault(); e.stopPropagation();
      openCtxAt(e.clientX, e.clientY);
    }, true);

    document.addEventListener('click', function(e){
      var it = e.target.closest('[data-jm-add]');
      if (it){ addNodeFromLib(it.dataset.jmAdd); ctx.classList.remove('on'); return; }
      var a = e.target.closest('[data-jmasset]');
      if (a){ toast('素材「'+a.dataset.jmasset+'」· 原型不真上传'); ctx.classList.remove('on'); return; }
      if (e.target.closest('[data-jm-close]')){ ctx.classList.remove('on'); return; }
      if (!e.target.closest('#jmCtx')) ctx.classList.remove('on');
    });
    document.addEventListener('keydown', function(e){
      if (e.key === 'Escape'){ ctx.classList.remove('on'); return; }
      /* Delete / Backspace 删选中节点：上游 infinite-canvas 也没这套，是用户要的原型手感。
         ① 只在画布图视图生效 ② 不碰输入框 ③ 从 .gnode.sel 取 id，多选全删。 */
      if (e.key !== 'Delete' && e.key !== 'Backspace') return;
      if (typeof mode !== 'undefined' && mode !== 'flow') return;
      if (typeof flowView !== 'undefined' && flowView !== 'graph') return;
      var t = e.target;
      if (t && (t.closest('input, textarea, select, [contenteditable="true"]'))) return;
      var sels = $$('#gnodes .gnode.sel');
      if (!sels.length) return;
      e.preventDefault(); e.stopImmediatePropagation();
      sels.forEach(function(el){
        var id = el.dataset.id;
        GRAPH.nodes = GRAPH.nodes.filter(function(n){ return n.id !== id; });
        if (GRAPH.edges) GRAPH.edges = GRAPH.edges.filter(function(ed){
          return ed.from !== id && ed.to !== id;
        });
      });
      if (typeof closeNodeWb === 'function') closeNodeWb();
      if (typeof clearEdgeFocus === 'function') clearEdgeFocus();
      if (typeof renderGraph === 'function') renderGraph();
      if (typeof updateGmap === 'function') updateGmap();
      curWbId = null;
      toast('已删除 ' + sels.length + ' 个节点');
    });
  }

  /* ---------- 删除节点：复用 GRAPH，不动别的模块 ---------- */
  function delNode(){
    if (!curWbId){ toast('先点一个节点'); return; }
    GRAPH.nodes = GRAPH.nodes.filter(function(n){ return n.id !== curWbId; });
    if (GRAPH.edges) GRAPH.edges = GRAPH.edges.filter(function(ed){
      return ed.from !== curWbId && ed.to !== curWbId;
    });
    if (typeof closeNodeWb === 'function') closeNodeWb();
    if (typeof renderGraph === 'function') renderGraph();
    if (typeof updateGmap === 'function') updateGmap();
    curWbId = null;
    toast('节点已删除');
  }

  function stepZoom(d){
    CV_ZOOM = Math.max(0.3, Math.min(3, Math.round((CV_ZOOM + d*0.12)*100)/100));
    applyZoom();
    var pct = Math.round(CV_ZOOM*100);
    var p = $('.jm-zoom .pct'), r = $('.jm-zoom input');
    if (p) p.textContent = pct+'%';
    if (r) r.value = pct;
  }

  /* ---------- 把选中浮条换成参考的浅色胶囊 + 紧凑输入框 ---------- */
  function restyleWb(){
    var t = $('#nwbTools'); if (!t) return;
    var hasRun = !!t.querySelector('[data-wb="run"]');
    t.innerHTML = '<button class="nwb-tb" data-wb="params" title="完整参数">ⓘ 信息</button>'
      + '<button class="nwb-tb" data-wb="delnode" title="删除这个节点">✕ 删除</button>'
      + '<button class="nwb-tb" data-wb="asset" title="存进素材库（原型占位）">▣ 存资产</button>'
      + '<button class="nwb-tb" data-wb="'+(hasRun?'run':'gen')+'" title="按这个节点的设定生成">✦ 生图</button>'
      + '<button class="nwb-tb" data-wb="zo" title="缩小画布">－ 缩小</button>'
      + '<button class="nwb-tb" data-wb="zi" title="放大画布">＋ 放大</button>'
      + '<button class="nwb-tb close" data-wb="close" title="关闭浮层">✕</button>';
    var hd = $('.nwb-hd .t'); if (hd) hd.textContent = '参考内容';
    var ta = $('#nwbTa'); if (ta) ta.placeholder = '请输入你想要生成的文本内容';
    var md = $('#nwbModel'); if (md) md.textContent = 'gpt-5.5 ▾';
    var rt = $('#nwbRatio'); if (rt) rt.textContent = '模型 · 自动 · 1 次';
    var sd = $('.nwb-send'); if (sd) sd.textContent = '↑';
  }

  function patchWb(){
    var orig = window.openNodeWb;
    if (typeof orig === 'function'){
      window.openNodeWb = function(id){
        curWbId = id;
        orig(id);
        requestAnimationFrame(restyleWb);
      };
    }
    /* capture 阶段拦新动作，别让 36 的 wbAct 再把它们当未知动作吞掉。
       #nodeWb 是点节点时才由 36 创建的，这里不能取元素绑事件，绑 document 才接得住。 */
    document.addEventListener('click', function(e){
      var b = e.target.closest('#nodeWb [data-wb]'); if (!b) return;
      var a = b.dataset.wb;
      if (a === 'delnode'){ e.stopImmediatePropagation(); delNode(); }
      else if (a === 'asset'){ e.stopImmediatePropagation(); toast('已存进素材库（原型占位）'); }
      else if (a === 'gen'){ e.stopImmediatePropagation(); toast('生图：走节点背后能力，原型不真调模型'); }
      else if (a === 'zo'){ e.stopImmediatePropagation(); stepZoom(-1); }
      else if (a === 'zi'){ e.stopImmediatePropagation(); stepZoom(1); }
    }, true);
  }

  /* ---------- 模式同步：只连线图视图挂外壳 ---------- */
  function sync(){
    inject();
    if (INJ && !$('.jm-tabs button').dataset.bound){ initPanel(); initDock(); initCtx(); patchWb();
      $('.jm-tabs button').dataset.bound = '1'; }
    var on = (typeof mode === 'undefined' || mode === 'flow')
      && (typeof flowView === 'undefined' || flowView === 'graph');
    document.body.classList.toggle('jm-on', !!on);
    var p = $('.jm-zoom .pct');
    if (p && typeof CV_ZOOM !== 'undefined') p.textContent = Math.round(CV_ZOOM*100)+'%';
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync);
  else sync();
  setInterval(sync, 300);
})();
