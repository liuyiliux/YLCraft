/* 25-enhance.js — AI 增强（这两项要调模型，花钱）
   补齐对照检查 P1：
     · AI 超清 / 放大     —— 输出分辨率上不去
     · AI 追色（三模式）  —— 像素蛋糕的决策表，按「变化量」选模型

   🔴 AI 追色那张表最值得抄：
      场景一致只调色 → 追色1.0（快、无损、不能改光）
      场景一致光线变 → 追色2.0追光（智能补光、程度可调）
      场景差异大     → 追色2.0追场景（还原度最高、仅4K）
*/

/* ===== ① AI 超清 / 放大 ===== */
const UPSCALE = { factor: 2, engine: 'auto', face: true };

function openUpscale(id){
  const sid = id || selId || (DOC.items[0] && DOC.items[0].id);
  const s = DOC.items.find(x=>x.id===sid);
  if (!s){ toast('先选一张图'); return; }
  if (typeof hideFloatBar === 'function') hideFloatBar();

  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="if(event.target.classList.contains('exw'))closeUpscale()">
      <div class="exw" style="width:min(560px,94vw)">
        <div class="inp-hd">
          <div class="inp-t">超清放大</div>
          <div class="inp-sub">${esc(s.name)} · 1024 × 1536 · 这一项要调模型</div>
          <button class="inp-x" onclick="closeUpscale()">✕</button>
        </div>

        <div class="ex-body">
          <div class="ex-sec"><span class="ex-st">放大倍数</span></div>
          <div class="up-factors">
            ${[2,3,4].map(f=>`
              <button class="up-f ${UPSCALE.factor===f?'on':''}" onclick="setUpFactor(${f})">
                <span class="up-fn">${f}×</span>
                <span class="up-fd">${1024*f} × ${1536*f}</span>
                <span class="up-fc">⚡${f===2?6:f===3?10:16}</span>
              </button>`).join('')}
          </div>

          <div class="ex-sec" style="margin-top:14px"><span class="ex-st">选项</span></div>
          <label class="up-ck">
            <input type="checkbox" ${UPSCALE.face?'checked':''} onchange="UPSCALE.face=this.checked">
            <span>人脸修复（放大后重新生成清晰五官）</span>
          </label>

          <div class="ex-key" style="margin-top:14px">
            🔴 <b>为什么这个要花钱</b> —— 它不是"插值放大"（那样会糊），
            而是<b>用模型重新生成细节</b>。所以按输出像素数计费。
            <br><span class="ex-key2">4K 的 4× 比 2× 贵 2.7 倍，因为像素多 4 倍。</span>
          </div>

          <div class="ex-todo" style="margin-top:9px">
            <span class="ex-td">占位</span>
            真实实现需要：① 分块放大（避免显存爆）② 人脸区域单独处理
            ③ 接缝融合。<b>具体实现后做。</b>
          </div>
        </div>

        <div class="ex-foot">
          <div class="ex-cost">
            花费 <b style="color:var(--ac);font-family:var(--fm);font-size:15px">⚡${UPSCALE.factor===2?6:UPSCALE.factor===3?10:16}</b>
            <span class="ex-costn">调模型 · 按输出像素计费</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="closeUpscale()">取消</button>
            <button class="insp-b pri" onclick="doUpscale()">放大 ${UPSCALE.factor}×</button>
          </div>
        </div>
      </div>
    </div>`;
}

function setUpFactor(f){ UPSCALE.factor = f; openUpscale(selId); }
function closeUpscale(){ document.getElementById('overlayHost').innerHTML = ''; }

function doUpscale(){
  const f = UPSCALE.factor, cost = f===2?6:f===3?10:16;
  closeUpscale();
  if (typeof agAdd === 'function'){
    agAdd('ai', `放大到 <b>${1024*f} × ${1536*f}</b>，花了 <b>⚡${cost}</b>。<br><br>`
      + (UPSCALE.face ? `开了人脸修复 —— 五官是重新生成的，会清晰但不一定和原来完全一样。` : `没开人脸修复，五官会保留原来的模糊感。`)
      + `<br><br><span class="myown">这一个是要花钱的 —— 模型重新生成细节，不是插值。`
      + `所以先做完全部免费的调整（降噪/调色/曲线），再来放大最省钱。</span>`);
  }
  toast(`放大 ${f}× · ⚡${cost}`);
}

/* ===== ② AI 追色（三模式） ===== */
const COLOR_MATCH_MODES = [
  { k:'match1', n:'追色 1.0', sub:'只追色彩影调',
    use:'场景一致、打光基本一样',
    pros:['速度快','画质无损','色彩/影调可分开调'],
    cons:['不能改光线方向'],
    cost:4, out:'原尺寸' },
  { k:'match2light', n:'追色 2.0 · 追光', sub:'追色 + 还原打光',
    use:'场景一致但光线/天气不同（阴天→晴天）',
    pros:['保持原尺寸','背景改动少','智能补光','程度滑杆 0-100'],
    cons:['不支持色彩/影调独立调节'],
    cost:8, out:'原尺寸' },
  { k:'match2scene', n:'追色 2.0 · 追场景', sub:'凭空重塑光影与背景',
    use:'场景差异大、极限换天（夜转昼）',
    pros:['还原度最高','可凭空生成复杂光影'],
    cons:['仅 4K 输出','不支持程度调节'],
    cost:16, out:'仅 4K' }
];

let MATCH_PICK = 'match2light';

function openColorMatch(id){
  const sid = id || selId || (DOC.items[0] && DOC.items[0].id);
  const s = DOC.items.find(x=>x.id===sid);
  if (!s){ toast('先选一张图'); return; }
  if (typeof hideFloatBar === 'function') hideFloatBar();

  const cur = COLOR_MATCH_MODES.find(m=>m.k===MATCH_PICK);

  document.getElementById('overlayHost').innerHTML = `
    <div class="ex" onclick="if(event.target.classList.contains('exw'))closeColorMatch()">
      <div class="exw" style="width:min(660px,94vw)">
        <div class="inp-hd">
          <div class="inp-t">AI 追色</div>
          <div class="inp-sub">给一张样片，让这张跟它一个调 · ${esc(s.name)}</div>
          <button class="inp-x" onclick="closeColorMatch()">✕</button>
        </div>

        <div class="ex-body">
          <div class="ex-sec">
            <span class="ex-st">参考样片</span>
            <span class="ex-s2">系统精选 / 我自己上传的</span>
          </div>
          <div class="cm-refs">
            <div class="cm-ref on"><div class="cm-rh" style="background:linear-gradient(160deg,#243b55,#141e30)"></div><span>冷调夜景</span></div>
            <div class="cm-ref"><div class="cm-rh" style="background:linear-gradient(160deg,#ffd89b,#c86b4a)"></div><span>暖调夕阳</span></div>
            <div class="cm-ref"><div class="cm-rh" style="background:linear-gradient(160deg,#e8e8e8,#a8a8a8)"></div><span>干净白调</span></div>
            <div class="cm-ref upload"><div class="cm-rh">+</div><span>上传</span></div>
          </div>

          <div class="ex-sec" style="margin-top:16px">
            <span class="ex-st">选模式</span>
            <span class="ex-s2">🔴 按「变化量」选，不是随便挑</span>
          </div>
          <div class="cm-modes">
            ${COLOR_MATCH_MODES.map(m=>`
              <button class="cm-m ${MATCH_PICK===m.k?'on':''}" onclick="setMatchMode('${m.k}')">
                <div class="cm-mh">
                  <span class="cm-mn">${m.n}</span>
                  <span class="cm-mc">⚡${m.cost}</span>
                </div>
                <div class="cm-msub">${m.sub}</div>
                <div class="cm-muse">${m.use}</div>
              </button>`).join('')}
          </div>

          <div class="cm-detail">
            <div class="cm-dh">
              <span class="cm-dn">${cur.n}</span>
              <span class="cm-do">输出：${cur.out}</span>
            </div>
            <div class="cm-dl">
              <div class="cm-dp">
                <span class="cm-dk ok">能做</span>
                <span>${cur.pros.join(' · ')}</span>
              </div>
              <div class="cm-dp">
                <span class="cm-dk no">做不到</span>
                <span>${cur.cons.join(' · ')}</span>
              </div>
            </div>
          </div>

          <div class="ex-key" style="margin-top:12px">
            🔴 <b>这张表照抄像素蛋糕</b> —— 同一个需求「跟样片一个调」，
            按你场景的<b>变化量</b>选模型，价格和效果差一个档。
            <br><span class="ex-key2">
              场景一致只调色 → 用 1.0（便宜、无损）·
              光线变了 → 用追光（中档）· 场景完全不同 → 才用追场景（最贵）
            </span>
          </div>
        </div>

        <div class="ex-foot">
          <div class="ex-cost">
            花费 <b style="color:var(--ac);font-family:var(--fm);font-size:15px">⚡${cur.cost}</b>
            <span class="ex-costn">${cur.k==='match1'?'纯色彩运算类':'生成式重绘'}</span>
          </div>
          <div class="le-acts">
            <button class="insp-b ghost" onclick="closeColorMatch()">取消</button>
            <button class="insp-b pri" onclick="doColorMatch()">用 ${cur.n}</button>
          </div>
        </div>
      </div>
    </div>`;
}

function setMatchMode(k){ MATCH_PICK = k; openColorMatch(selId); }
function closeColorMatch(){ document.getElementById('overlayHost').innerHTML = ''; }

function doColorMatch(){
  const m = COLOR_MATCH_MODES.find(x=>x.k===MATCH_PICK);
  closeColorMatch();
  if (typeof agAdd === 'function'){
    agAdd('ai', `用「<b>${m.n}</b>」追了色，花了 <b>⚡${m.cost}</b>。<br><br>`
      + `它做的是：${m.pros.join('、')}。<br>`
      + `<span class="myown">限制是：${m.cons.join('、')} —— 这是模型本身的能力边界，不是我选择不做。</span><br><br>`
      + (m.k === 'match1'
          ? `你选的这个最便宜，因为它只动色彩和影调，画面内容一个像素不改。`
          : m.k === 'match2light'
          ? `这个会重算光照方向 —— 所以能"阴天变晴天"，但色彩和影调就不能单独调了。`
          : `这个能凭空重塑场景，还原度最高，但它不支持程度调节，一次到底。`));
  }
  toast(`追色完成 · ⚡${m.cost}`);
}
