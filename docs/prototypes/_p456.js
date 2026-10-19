/* ================= P4/P5/P6 补丁 =================
   P4 chips 可移除 + 引用留痕打通
   P5 间隔重复（错题按遗忘曲线排复习）
   P6 划词标注
   以函数重定义的方式追加（后定义覆盖前定义）
*/

/* ---------------- P4：chips 可移除 ---------------- */
let disabledCites = new Set();   // 用户停用的引用来源

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
    + `<span class="myown">需要的话在知识库里重新启用它。本次回答里已经用到的那段保留，不回滚。</span>`);
  toast('已停用：《' + title + '》');
}

/* ---------------- P5：间隔重复 ---------------- */
const SR_STEPS = [1, 3, 7, 16, 35];   // 天：1→3→7→16→35
let wrongBox = [];   // [{qid, stage, due, wrongCount}]
const DAY = 86400000;

function srAdd(qid){
  const now = Date.now();
  let it = wrongBox.find(w=>w.qid===qid);
  if (!it){ it = { qid, stage:0, due: now + SR_STEPS[0]*DAY, wrongCount:1 }; wrongBox.push(it); }
  else {
    it.wrongCount++;
    it.stage = Math.max(0, it.stage - 1);      // 又错了，退回上一档
    it.due = now + SR_STEPS[it.stage]*DAY;
  }
}
function srPass(qid){
  const it = wrongBox.find(w=>w.qid===qid);
  if (!it) return;
  it.stage++;
  if (it.stage >= SR_STEPS.length){ wrongBox = wrongBox.filter(w=>w.qid!==qid); return; }
  it.due = Date.now() + SR_STEPS[it.stage]*DAY;
}
function srDue(){ return wrongBox.filter(w=>w.due <= Date.now()); }
function srWhen(ts){
  const days = Math.round((ts - Date.now())/DAY);
  if (days <= 0) return '现在该复习';
  if (days === 1) return '明天';
  return days + ' 天后';
}

/* 覆盖 submitQuiz：答错自动进遗忘曲线 */
const _submitQuiz = submitQuiz;
submitQuiz = function(){
  if (quiz.pick === null) return;
  const q = KB_QUIZ[quiz.i];
  quiz.answers[quiz.i] = quiz.pick;
  if (quiz.pick === q.a) srPass(q.id);
  else srAdd(q.id);
  renderKBInto();
};

/* 覆盖错题本：带复习时间 */
wrongCardHTML = function(){
  if (!wrongBox.length && !quiz.answers.length) return `
    <div class="qzwrongempty">
      <div class="qzwe-t">错题本</div>
      <div class="qzwe-s">还没有错题。<b>做一次测验，答错的会自动收进来。</b></div>
    </div>`;

  const due = srDue();
  const items = wrongBox.map(w=>({ w, q: KB_QUIZ.find(x=>x.id===w.qid) })).filter(x=>x.q);

  return `
    <div class="qzwrong">
      <div class="qzwh">
        <span class="qzwh-t">错题本</span>
        <span class="qzwh-c">${items.length} 题</span>
        ${due.length?`<span class="qzwh-due">${due.length} 题该复习了</span>`:''}
        <button class="b" style="margin-left:auto;font-size:10.5px;padding:3px 9px"
          onclick="startQuiz()">再测一次</button>
      </div>

      ${items.length ? items.map(({w,q})=>{
        const isDue = w.due <= Date.now();
        return `<div class="qzwitem ${isDue?'due':''}">
          <div class="qzwq">${q.q}</div>
          <div class="qzwl">
            <span class="bad">错 ${w.wrongCount} 次</span>
            <span class="${isDue?'good':'dim'}">${isDue?'该复习了':'下次 '+srWhen(w.due)}</span>
          </div>
          <div class="qzwr">
            来自《${q.ref.t}》第 ${q.ref.seg} 段
            <span class="qzwlink" onclick="openCite('${q.ref.id}')">看原文 →</span>
          </div>
        </div>`;
      }).join('')
      : '<div class="qzwe-s" style="padding:12px">全对！错题本是空的。</div>'}

      ${items.length?`<div class="qzsr">
        <b>为什么排时间：</b>答错后 1 天复习 → 对了排 3 天 → 7 天 → 16 天 → 35 天。
        再错就退回前一档。<span class="qzsr-n">（间隔重复 · 按遗忘曲线）</span>
      </div>`:''}
    </div>`;
};

/* ---------------- P6：划词标注 ---------------- */
let selText = '';
let annForItem = null;

/* 覆盖原文 tab：文本可选，选中后浮出「标注」 */
kbTabText = function(it){
  const ann = KB_ANNOT[it.id] || [];
  if (it.state === 'parsing'){
    return `<div class="kbd3pend">正在处理：${it.progress||'转写中'}<br>
      <span style="font-size:10px;color:var(--tx3)">原因是「处理设置」里没绑 OCR / 转写模型</span></div>`;
  }
  const body = it.k === 'git'
    ? '# ' + it.t + '\n\n## 这是什么\n（README 正文会被完整保留，代码文件按函数切片。）\n\n## 怎么用\n（目录结构、关键文件都保留路径信息，检索时能定位到具体文件。）'
    : '（这里显示正文。真实内容是全文可读。）\n\n'
      + '第 1 段：' + (it.k==='note'?'这是我自己的记录：':'') + '先看整体再抠细节，别一上来就调参数。\n\n'
      + '第 ' + (ann[0] ? ann[0].seg : 3) + ' 段：' + (ann[0] ? ann[0].quote : '……') + '\n\n'
      + '第 9 段：参数是给别人看的，效果是给自己看的 —— 先看效果。';

  return `
    <div class="kbsim" id="annotHost" onmouseup="kbSelCheck('${it.id}')">
      <div class="kbsimt">全文 · <b>划一下可以标注</b></div>
      <div class="kbsimp" style="-webkit-user-select:text;user-select:text">${body.replace(/</g,'&lt;')}</div>
    </div>
    ${ann.length?`<div class="kbd3tip">这条材料上已有 <b>${ann.length}</b> 条标注 · 切到「标注」看</div>`:''}`;
};

function kbSelCheck(itemId){
  setTimeout(()=>{
    const sel = window.getSelection();
    const t = sel ? String(sel).trim() : '';
    const old = document.getElementById('selPop');
    if (old) old.remove();
    if (!t || t.length < 4) return;
    selText = t.slice(0, 120);
    annForItem = itemId;
    const r = sel.getRangeAt(0).getBoundingClientRect();
    const d = document.createElement('div');
    d.className = 'selpop'; d.id = 'selPop';
    d.style.left = Math.min(r.left + r.width/2, window.innerWidth - 120) + 'px';
    d.style.top = (r.top - 34) + 'px';
    d.innerHTML = `<span onclick="kbDoAnnot()">＋ 标注这句</span>`;
    document.body.appendChild(d);
  }, 10);
}

function kbDoAnnot(){
  const pop = document.getElementById('selPop'); if (pop) pop.remove();
  const note = prompt('给这句写个标注：', '');
  if (note === null) return;
  const v = String(note).trim();
  if (!v){ toast('标注不能为空'); return; }
  const arr = KB_ANNOT[annForItem] || (KB_ANNOT[annForItem] = []);
  arr.unshift({ seg: 3, quote: selText, note: v, at: '刚刚' });
  renderKbDetail();
  toast('已标注 · 会跟着这段一起进检索');
}

/* ---------------- 顺手：让 context chips 的 × 有点样式 ---------------- */
(function injectChipCSS(){
  const st = document.createElement('style');
  st.textContent = `
    .cc-i .cc-t{max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .cc-i.off{opacity:.4;text-decoration:line-through}
    .cc-x{margin-left:2px;opacity:.5;cursor:pointer;font-size:8px;padding:0 1px}
    .cc-x:hover{opacity:1;color:var(--dg)}
    .selpop{position:fixed;z-index:600;transform:translateX(-50%);
      background:rgba(20,20,24,.98);border:1px solid var(--acl);border-radius:6px;
      box-shadow:0 8px 24px -8px rgba(0,0,0,.9);padding:3px 4px;animation:pop .14s var(--ez)}
    .selpop span{font-size:11px;color:var(--ac);cursor:pointer;padding:3px 7px;display:block;
      border-radius:4px;white-space:nowrap}
    .selpop span:hover{background:var(--acs)}
    .qzwh-due{font-size:9px;color:var(--wn);background:rgba(251,191,36,.12);
      border:-radius:3px;border-radius:3px;padding:1px 5px}
    .qzwitem.due{background:rgba(251,191,36,.05);border-radius:6px;padding:10px;margin:0 -10px}
    .qzwl .dim{color:var(--tx3)}
    .qzsr{margin-top:11px;padding:9px 11px;border-radius:var(--r2);font-size:10px;
      line-height:1.7;color:var(--tx3);background:var(--bg2);border:1px solid var(--ln)}
    .qzsr b{color:var(--tx2)}
    .qzsr-n{opacity:.7}
  `;
  document.head.appendChild(st);
})();
