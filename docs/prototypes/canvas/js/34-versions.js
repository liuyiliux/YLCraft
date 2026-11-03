/* 34-versions.js — 画布版本记录（BeefTV 欠账 #1 的另一半，2026-11-03）
   和 18-panels.js 的「历史」不是一回事：
   - 历史（HISTORY）= 操作级撤销/重做，只在本会话内
   - 版本（这里）= **命名快照**：存一版，之后随时回到那一版

   最小版（够用就停）：
   · 手动「存当前版本」
   · 自动存：生成完成 / 整组重跑 / 跑连线图 之后各存一版（内容没变就不重复存）
   · 每版记录：标签、时间、镜头数、节点数、手自动
   · 回到这版 / 删掉；上限 12 版，超了丢最旧的

   恢复的范围：DOC.items（镜头数据）+ DOC.kind + 节点位置 + 连线。
   不恢复的东西明说：缩放/滚动位置、撤销历史栈 —— 那些是"看的状态"，不是"内容"。 */

let VERSIONS = [];
let VSEQ = 0;
const VER_MAX = 12;

function verNow(){
  return new Date().toLocaleTimeString('zh-CN', { hour12:false }).slice(0,5);
}

function verSnapshot(){
  return {
    kind: DOC.kind || '',
    items: JSON.parse(JSON.stringify(DOC.items || [])),
    nodes: (typeof GRAPH !== 'undefined' ? GRAPH.nodes : []).map(n => ({ id:n.id, x:n.x, y:n.y, w:n.w, h:n.h })),
    edges: (typeof GRAPH !== 'undefined' ? JSON.parse(JSON.stringify(GRAPH.edges)) : [])
  };
}

function verKey(snap){
  return JSON.stringify([snap.items, snap.nodes, snap.edges]);
}

/* 自动存：内容（镜头/节点/连线）和上一版完全一样就不存，免得列表被空版本刷满 */
function autoVersion(label){
  if (!DOC.items.length) return;           // 空画布不存
  const snap = verSnapshot();
  const key = verKey(snap);
  if (VERSIONS.length && VERSIONS[0].key === key) return;
  pushVersion(label || '自动', snap, key, true);
  if (document.getElementById('verBody')) renderVersionList();
}

function pushVersion(label, snap, key, auto){
  VERSIONS.unshift({
    id: 'v' + (++VSEQ), label, at: verNow(), auto, key, snap,
    shots: snap.items.length,
    nodes: snap.nodes.length
  });
  while (VERSIONS.length > VER_MAX) VERSIONS.pop();
}

function saveVersionManual(){
  if (!DOC.items.length){ toast('画布是空的，先做点东西再存'); return; }
  const snap = verSnapshot();
  pushVersion('手动保存', snap, verKey(snap), false);
  renderVersionList();
  toast('已存一个版本');
}

function restoreVersion(id){
  const v = VERSIONS.find(x => x.id === id);
  if (!v) return;
  const s = v.snap;
  DOC.kind = s.kind;
  DOC.items = JSON.parse(JSON.stringify(s.items));

  if (typeof buildGraph === 'function') buildGraph(false);
  /* 位置回填：buildGraph 只重建结构，位置按快照还原 */
  if (typeof GRAPH !== 'undefined'){
    s.nodes.forEach(p => {
      const n = GRAPH.nodes.find(x => x.id === p.id);
      if (n){ n.x = p.x; n.y = p.y; if (p.w) n.w = p.w; if (p.h) n.h = p.h; }
    });
    GRAPH.edges = JSON.parse(JSON.stringify(s.edges));
  }
  if (typeof renderShots === 'function') renderShots();
  if (typeof setMode === 'function') setMode('flow');
  closeVersionPanel();
  toast('已回到「' + v.label + '」· ' + v.at + ' · ' + v.shots + ' 镜');
}

function deleteVersion(id, e){
  if (e) e.stopPropagation();
  VERSIONS = VERSIONS.filter(x => x.id !== id);
  renderVersionList();
  toast('已删掉这个版本');
}

function openVersionPanel(){
  hideFloatBar();
  document.getElementById('overlayHost').innerHTML = `
    <div class="pl" onclick="if(event.target.classList.contains('plw'))closeVersionPanel()">
      <div class="plw">
        <div class="inp-hd">
          <div class="inp-t">版本记录</div>
          <div class="inp-sub">存一版随时能回来 · 自动存，上限 ${VER_MAX} 版</div>
          <button class="inp-x" onclick="closeVersionPanel()">✕</button>
        </div>
        <div class="pl-body" id="verBody"></div>
        <div class="pl-foot">
          <span class="pl-note">恢复的是镜头、节点位置和连线 —— 缩放和撤销历史不跟着回</span>
          <button class="insp-b pri" onclick="saveVersionManual()">存当前版本</button>
        </div>
      </div>
    </div>`;
  renderVersionList();
}

function closeVersionPanel(){
  document.getElementById('overlayHost').innerHTML = '';
}

function renderVersionList(){
  const host = document.getElementById('verBody');
  if (!host) return;
  host.innerHTML = VERSIONS.length ? VERSIONS.map((v, i) => `
    <div class="ver-row ${i === 0 ? 'on' : ''}">
      <span class="ver-i">${VERSIONS.length - i}</span>
      <span class="ver-l">${esc(v.label)}</span>
      <span class="ver-m">${v.shots} 镜 · ${v.nodes} 节点 · ${v.at}</span>
      <span class="ver-tag">${v.auto ? '自动' : '手动'}</span>
      <button class="ver-b" onclick="restoreVersion('${v.id}')">回到这版</button>
      <button class="ver-b del" onclick="deleteVersion('${v.id}', event)" title="删掉">✕</button>
    </div>`).join('')
    : '<div class="lh-empty">还没有版本 —— 生成一次，或点右下角「存当前版本」</div>';
}
