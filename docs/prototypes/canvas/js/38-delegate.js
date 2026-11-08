/* 38-delegate.js — 设计委托（2026-11-08 原型收口第 2 批 ⑩）
 *
 * 开源自用口径（用户 11-08 明确）：这是「让 Agent 自己跑」的排程规则，
 * 定时 + 成本上限是自用也真实的保护，**不是**付费档位 / 卖额度。
 * 原型不真跑、不扣积分、不上传；面板里每一处都写清这点。
 *
 * 语义边界：委托 = 排程规则；任务中心里的 WS_TASKS = 单次生成任务。
 * 两者不是一回事，所以委托记录自包含在本面板，不往 30-workspace.js 里塞。
 */
(function delegate(){
  const JOBS = [
    {id:'j1', n:'把 12 镜按同一色调调完', nodes:12, cost:96,
     d:'批量套预设 + 本地调色，不调模型'},
    {id:'j2', n:'补齐所有待生成镜头', nodes:4, cost:56,
     d:'4 个 todo 镜头走生图，会调模型'},
    {id:'j3', n:'导出成片并做交付检查', nodes:3, cost:0,
     d:'本地合成 + 交付检查，⚡0'}
  ];
  const TIMES = [{k:'now',n:'立即'},{k:'night',n:'今晚 22:00'},{k:'daily',n:'每天 09:00'}];
  let jobSel = 0, timeSel = 0, cap = 120, seq = 0;
  let list = [], host = null, onKey = null;

  function esc(s){
    return String(s==null?'':s).replace(/[&<>"]/g,c=>({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  }
  function closeDelegate(){
    if (onKey){ document.removeEventListener('keydown', onKey); onKey = null; }
    if (host){ host.remove(); host = null; }
  }
  function render(){
    if (!host) return;
    const j = JOBS[jobSel], t = TIMES[timeSel];
    host.innerHTML =
      '<div class="dg-w" role="dialog" aria-label="设计委托">'
      + '<div class="dg-hd"><div>'
      +   '<div class="dg-t">设计委托 · 让 Agent 自己跑</div>'
      +   '<div class="dg-s">定时 + 成本上限 · 开源自用：跑的是你本机的任务，不上传、不卖额度</div>'
      + '</div><button class="dg-x" data-dg="close" title="关闭（Esc 同效）">✕</button></div>'
      + '<div class="dg-body">'
      +   '<div class="dg-sec">委托什么</div><div class="dg-jobs">'
      +   JOBS.map((x,i)=>`<button class="dg-job ${i===jobSel?'on':''}" data-dg="job" data-i="${i}">
            <b>${esc(x.n)}</b><span>${esc(x.d)}</span></button>`).join('')
      +   '</div>'
      +   '<div class="dg-sec">什么时候跑</div><div class="dg-times">'
      +   TIMES.map((x,i)=>`<button class="dg-time ${i===timeSel?'on':''}" data-dg="time" data-i="${i}">${esc(x.n)}</button>`).join('')
      +   '</div>'
      +   '<div class="dg-sec">最多花多少</div>'
      +   '<div class="dg-cap"><input type="number" id="dgCap" min="0" max="9999" step="10" value="' + cap + '">'
      +   '<span class="dg-unit">⚡</span>'
      +   '<span class="dg-cap-tip">到上限自动停，不会继续扣 · 原型不真跑、不扣真实积分</span></div>'
      +   `<div class="dg-sum">预计 ${j.nodes} 个节点 · 预估 ⚡${j.cost} · 触发：${esc(t.n)} · 上限 ⚡${cap}`
      +   (j.cost > cap ? ` <b class="dg-warn">超过上限，到上限就会停</b>` : '') + '</div>'
      +   '<div class="dg-sec">已创建的委托</div><div class="dg-list">'
      +   (list.length ? list.map(d=>`<div class="dg-item">
            <div class="dg-it-n">${esc(d.job)}<span class="dg-st">${esc(d.state)}</span></div>
            <div class="dg-it-m">${esc(d.when)} · 上限 ⚡${d.cap} · 预估 ⚡${d.cost}</div>
            <button class="dg-del" data-dg="cancel" data-id="${d.id}">撤销</button></div>`).join('')
          : '<div class="dg-empty">还没有委托 · 创建后会出现在这里，可随时撤销</div>')
      +   '</div>'
      + '</div>'
      + '<div class="dg-ft">'
      +   '<span>委托是排程规则，跟任务中心里「单次生成任务」不是一回事</span>'
      +   '<span class="dg-sp"></span>'
      +   '<button class="dg-btn" data-dg="close">关闭</button>'
      +   '<button class="dg-btn pri" data-dg="submit">创建委托</button>'
      + '</div></div>';
  }

  function openDelegate(){
    closeDelegate();
    host = document.createElement('div');
    host.className = 'dg-ov';
    host.id = 'dgOv';
    document.body.appendChild(host);
    render();

    /* 事件委托：切任务 / 时间会重建面板，但输入值只从全局变量读，不重建输入框本身 */
    host.addEventListener('click', e=>{
      if (e.target === host){ closeDelegate(); return; }
      const b = e.target.closest('[data-dg]');
      if (!b) return;
      const a = b.dataset.dg;
      if (a === 'close'){ closeDelegate(); return; }
      if (a === 'job'){ jobSel = +b.dataset.i; render(); return; }
      if (a === 'time'){ timeSel = +b.dataset.i; render(); return; }
      if (a === 'cancel'){
        list = list.filter(x=>x.id !== b.dataset.id);
        render();
        toast('已撤销委托');
        return;
      }
      if (a === 'submit') submitDelegate();
    });
    host.addEventListener('input', e=>{
      if (e.target.id !== 'dgCap') return;
      const v = Math.max(0, Math.min(9999, Number(e.target.value) || 0));
      cap = v;
      /* 只更新汇总那一行，不重建面板 —— 数字输入不能被打断 */
      const sum = host.querySelector('.dg-sum');
      if (sum){
        const j = JOBS[jobSel], t = TIMES[timeSel];
        sum.innerHTML = `预计 ${j.nodes} 个节点 · 预估 ⚡${j.cost} · 触发：${esc(t.n)} · 上限 ⚡${cap}`
          + (j.cost > cap ? ` <b class="dg-warn">超过上限，到上限就会停</b>` : '');
      }
    });
    onKey = e=>{ if (e.key === 'Escape') closeDelegate(); };
    document.addEventListener('keydown', onKey);
  }

  function submitDelegate(){
    const j = JOBS[jobSel], t = TIMES[timeSel];
    const d = {id:'d' + (++seq), job:j.n, when:t.n, cap:cap, cost:j.cost,
               nodes:j.nodes, state:'已排程 · 原型不真跑'};
    list.unshift(d);
    closeDelegate();
    if (typeof agAdd === 'function'){
      agAdd('ai', `已创建委托「<b>${esc(j.n)}</b>」。<br><br>`
        + `触发：${esc(t.n)} · 成本上限 <b>⚡${cap}</b>（到顶自动停） · 预计 ${j.nodes} 个节点。<br><br>`
        + `<span class="myown">开源自用：定时与上限是无人值守的保护，不是付费档位。`
        + `原型只演示这条排程规则，<b>不会真的定时执行、不会扣积分</b>；`
        + `真实现要落一张委托表 + 本机调度器，并在每次扣费前先问「还剩多少额度」。</span>`);
    }
    toast(`已创建委托 · ${t.n} · 上限 ⚡${cap}（原型不真跑）`);
  }

  window.openDelegate = openDelegate;
  window.closeDelegate = closeDelegate;
})();
