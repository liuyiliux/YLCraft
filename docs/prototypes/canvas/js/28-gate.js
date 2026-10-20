/* 28-gate.js — 门禁强制（不批准就不许过）
   🔴 来源：OpenMontage

     原话：「Human approval gates are **enforced, not suggested**」
           checkpoint writer **拒绝**没有批准记录的完成态
           「在浪费 GPU 前抓出坏计划」

   我们之前的问题：
     · 花费大的操作直接就跑了，没有"先给你看计划、你点头才花"这一步
     · 即使有确认按钮，点了也只是弹个提示，没有真正拦住流程

   这个文件做三件事：
     ① 花钱前必须先过门禁（不批准 → 不执行）
     ② 门禁有记录，能查到"谁批的、什么时候、批了什么"
     ③ 被拒绝的操作有明确说明，不是静默失败
*/

/* ================= 门禁定义 ================= */

/* 哪些操作需要门禁 */
const GATE_RULES = [
  { k:'batch-gen',  n:'批量生成',   min:2,  why:'一次出多张，跑起来就收不住' },
  { k:'regen',      n:'重画镜头',   min:1,  why:'重画会换掉已有的脸，不可逆' },
  { k:'upscale',    n:'超清放大',   min:1,  why:'按输出像素计费，4K 很贵' },
  { k:'colormatch', n:'AI 追色',    min:1,  why:'追场景模式一次到底，不能调' },
  { k:'3d',         n:'图生 3D',    min:1,  why:'耗时且要占 GPU' },
  { k:'previs',     n:'3D 导演台',  min:1,  why:'预演会回填分镜，改了就麻烦' },
  { k:'graph-run',  n:'跑整图',     min:1,  why:'一次跑十几个节点，成本不可预估' },
  { k:'export',     n:'导出',       min:1,  why:'导出不改内容，但会落文件' }
];

/* 门禁阈值：花费超过多少必须确认 */
const GATE_COST_THRESHOLD = 1;

/* 批准记录（真实现时要落库，带用户和时间） */
let GATE_LOG = [];

/* ================= 核心：请求批准 =================
   返回 Promise<boolean>：
     true  → 已批准，调用方可以继续
     false → 被拒绝，调用方必须中止
*/
function requestGate(opts){
  const {
    kind,          // 'batch-gen' | 'regen' | ...
    title,         // 给用户看的标题
    plan,          // 计划做什么（数组，一条一句）
    cost,          // 预计花费
    irreversible,  // 不可逆？
    why            // 为什么要花这个钱
  } = opts;

  const rule = GATE_RULES.find(r=>r.k===kind) || { n:'操作' };

  return new Promise(resolve => {
    const gateId = 'g' + Date.now();

    document.getElementById('overlayHost').innerHTML = `
      <div class="gate" onclick="if(event.target.classList.contains('gate'))__gateReject('${gateId}','${kind}')">
        <div class="gatew">
          <div class="gathd">
            <span class="gatic">⊘</span>
            <div class="gath">
              <div class="gatt">需要你确认：${esc(title || rule.n)}</div>
              <div class="gats">${esc(rule.why || '这一步会花钱')}</div>
            </div>
            <button class="gatx" onclick="__gateReject('${gateId}','${kind}')">✕</button>
          </div>

          <div class="gatbody">
            <div class="gatsec">要做什么</div>
            <div class="gatplan">
              ${(plan||[]).map(p=>`<div class="gatpi"><span class="gatpd">·</span><span>${esc(p)}</span></div>`).join('')}
            </div>

            <div class="gatcost">
              <span class="gatck">预计花费</span>
              <span class="gatcv">${cost ? '⚡' + cost : '免费'}</span>
              ${irreversible ? '<span class="gatirr">不可逆</span>' : ''}
            </div>

            ${why ? `<div class="gatwhy">${esc(why)}</div>` : ''}

            <div class="gatrule">
              🔴 <b>这一关是真的拦人的</b> ——
              点「不」就不会执行，不花钱；点「确认」才真正跑。
              <br><span class="gatr2">
                （之前我们的确认按钮点了只是弹提示，流程照样往下走 —— 这次改了）
              </span>
            </div>
          </div>

          <div class="gatfoot">
            <button class="insp-b ghost" onclick="__gateReject('${gateId}','${kind}')">不，先别跑</button>
            <button class="insp-b pri" onclick="__gateApprove('${gateId}','${kind}',${cost||0})">
              确认${cost ? ' · ⚡' + cost : ''}
            </button>
          </div>
        </div>
      </div>`;

    window.__GATE_PENDING = window.__GATE_PENDING || {};
    window.__GATE_PENDING[gateId] = {
      resolve, kind, cost, title: title || rule.n, plan
    };
  });
}

/* 批准 */
function __gateApprove(gateId, kind, cost){
  const p = (window.__GATE_PENDING || {})[gateId];
  if (!p) return;
  GATE_LOG.push({
    id: gateId, kind, cost,
    title: p.title,
    at: new Date().toLocaleTimeString('zh-CN', { hour12:false }),
    result: 'approved'
  });
  delete window.__GATE_PENDING[gateId];
  document.getElementById('overlayHost').innerHTML = '';
  toast(cost ? `已批准 · ⚡${cost}` : '已批准');
  p.resolve(true);
}

/* 拒绝 */
function __gateReject(gateId, kind){
  const p = (window.__GATE_PENDING || {})[gateId];
  if (!p) return;
  GATE_LOG.push({
    id: gateId, kind, cost: 0,
    title: p.title,
    at: new Date().toLocaleTimeString('zh-CN', { hour12:false }),
    result: 'rejected'
  });
  delete window.__GATE_PENDING[gateId];
  document.getElementById('overlayHost').innerHTML = '';

  // 🔴 被拒绝要有明确说明，不能静默失败
  if (typeof agAdd === 'function'){
    agAdd('ai', `好的，<b>没有执行</b> —— 也没花钱。<br><br>`
      + `<span class="myown">你可以随时再来一次，或者先把别的调好再跑。`
      + `被拒绝的操作我记下来了，如果想看"为什么当时要花这个钱"，问我就行。</span>`);
  }
  toast('已取消 · 没花钱');
  p.resolve(false);
}

/* ================= 便捷包装 =================
   用法：
     const ok = await gateThen('regen', {...}, () => doRegen());
   —— 批准才执行，拒绝就返回 undefined
*/
async function gateThen(kind, opts, fn){
  const approved = await requestGate({
    kind,
    cost: opts.cost || 0,
    title: opts.title,
    plan: opts.plan || [],
    irreversible: opts.irreversible,
    why: opts.why
  });
  if (!approved) return { ok:false, rejected:true };
  const r = await fn();
  return { ok:true, result:r };
}

/* ================= 门禁记录面板 ================= */
function openGateLog(){
  if (typeof hideFloatBar === 'function') hideFloatBar();
  const ok = GATE_LOG.filter(g=>g.result==='approved');
  const no = GATE_LOG.filter(g=>g.result==='rejected');
  const spent = ok.reduce((a,b)=>a+(b.cost||0),0);

  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="if(event.target.classList.contains('exw'))closeGateLog()">
      <div class="exw" style="width:min(560px,94vw)">
        <div class="inp-hd">
          <div class="inp-t">门禁记录</div>
          <div class="inp-sub">每次花钱前的批准 / 拒绝都在这</div>
          <button class="inp-x" onclick="closeGateLog()">✕</button>
        </div>
        <div class="ex-body">
          <div class="gatl-sum">
            <div class="gatl-si"><span>批准</span><b>${ok.length}</b></div>
            <div class="gatl-si"><span>拒绝</span><b class="no">${no.length}</b></div>
            <div class="gatl-si"><span>因此花掉</span><b class="co">⚡${spent}</b></div>
            <div class="gatl-si"><span>因此省下</span><b class="ok">⚡${no.reduce((a,b)=>a+(b.cost||0),0)}</b></div>
          </div>
          <div class="gatl-list">
            ${GATE_LOG.length ? GATE_LOG.slice().reverse().map(g=>`
              <div class="gatl-item ${g.result}">
                <span class="gatl-t">${g.at}</span>
                <span class="gatl-n">${esc(g.title)}</span>
                <span class="gatl-r ${g.result}">${g.result==='approved'?'批准':'拒绝'}</span>
                <span class="gatl-c">${g.cost?'⚡'+g.cost:'—'}</span>
              </div>`).join('') : '<div class="gatl-empty">还没有记录</div>'}
          </div>
        </div>
        <div class="ex-foot">
          <div class="ex-cost" style="font-size:9.5px;color:var(--tx3)">
            门禁是强制的：不批准，流程不会往下走
          </div>
          <div class="le-acts"><button class="insp-b ghost" onclick="closeGateLog()">关闭</button></div>
        </div>
      </div>
    </div>`;
}

function closeGateLog(){ document.getElementById('overlayHost').innerHTML = ''; }
