/* 29-real-image.js — 真实图片接入（导入 / 缩略图 / 写回 / 拖放）
   之前所有"修图"都在演示人像上做，文档里根本没有像素。
   现在：
     · 真选文件 / 真拖进来
     · 解出来的像素存进 item.canvas
     · 缩略图、放大、导出、修图都读同一份像素
     · 工作分辨率长边 1600（原型性能取舍，原图尺寸另存 realW/realH）
*/

const RI_WORK_MAX = 1600;
let RI_IMPORTING = 0;

function riBaseName(name){
  return String(name || '图片').replace(/\.[^.]+$/, '');
}

/* 把任意图片源缩到工作分辨率，返回新 canvas（不共享引用） */
function riFitCanvas(src, maxDim){
  const w = (src && (src.naturalWidth || src.width)) || 0;
  const h = (src && (src.naturalHeight || src.height)) || 0;
  if (!w || !h) return null;
  const max = maxDim || RI_WORK_MAX;
  const s = Math.min(1, max / Math.max(w, h));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w * s));
  c.height = Math.max(1, Math.round(h * s));
  const g = c.getContext('2d');
  g.imageSmoothingEnabled = true;
  g.imageSmoothingQuality = 'high';
  g.drawImage(src, 0, 0, c.width, c.height);
  return c;
}

function riMakeThumb(src, max){
  const t = riFitCanvas(src, max || 640);
  if (!t) return '';
  try { return t.toDataURL('image/webp', 0.85); } catch(_){}
  try { return t.toDataURL('image/png'); } catch(_){ return ''; }
}

/* 图层里的"原图"层跟着像素更新，导出/图层面板才不会还写着演示尺寸 */
function riSyncSourceLayer(item){
  if (!item || typeof layersOf !== 'function') return;
  try {
    const src = layersOf(item.id).find(l=>l.type==='source');
    if (!src) return;
    src.params = Object.assign({}, src.params || {}, {
      src: item.imageName || item.name,
      w: item.canvas ? item.canvas.width : 0,
      h: item.canvas ? item.canvas.height : 0,
      realW: item.realW || 0,
      realH: item.realH || 0
    });
    src.hasPixels = !!item.canvas;
  } catch(_){}
}

function riRerender(){
  try {
    if (mode === 'shots' && typeof renderShots === 'function') renderShots();
    else if (mode === 'free' && typeof renderFree === 'function') renderFree();
    if (typeof renderLayerPanel === 'function') renderLayerPanel();
  } catch(_){}
}

/* 把像素写进某个镜头/图片对象（缩略图 + 图层 + 重新渲染） */
function setItemCanvas(item, canvas, opts){
  const o = opts || {};
  if (!item || !canvas) return null;
  const work = riFitCanvas(canvas, o.maxDim || RI_WORK_MAX);
  if (!work) return null;
  if (!item.realW) item.realW = canvas.width || canvas.naturalWidth || 0;
  if (!item.realH) item.realH = canvas.height || canvas.naturalHeight || 0;
  item.canvas = work;
  item.hasRealPixels = true;
  item.thumbUrl = riMakeThumb(work, 640);
  if (o.name) item.name = o.name;
  if (o.imageName) item.imageName = o.imageName;
  else if (!item.imageName) item.imageName = item.name;
  if (mode === 'free' && o.keepSize !== true && item.w){
    item.h = Math.max(70, Math.round(item.w * work.height / work.width));
  }
  riSyncSourceLayer(item);
  if (!o.silent) riRerender();
  return work;
}

/* 新建一张真图（素材墙 / RAW 解码结果都走这里） */
function addRealImageItem(src, name, opts){
  const o = opts || {};
  const work = riFitCanvas(src, o.maxDim || RI_WORK_MAX);
  if (!work) return null;
  const rawW = src.naturalWidth || src.width || work.width;
  const rawH = src.naturalHeight || src.height || work.height;
  const label = name || ('导入图 ' + (DOC.items.length + 1));
  const maxOrder = DOC.items.reduce((a,s)=>Math.max(a,s.order),-1);

  let w = 176;
  let h = Math.round(w * work.height / work.width);
  if (h > 300){ h = 300; w = Math.round(h * work.width / work.height); }
  if (w > 300){ w = 300; h = Math.round(w * work.height / work.width); }

  const item = {
    id: 'img' + Date.now() + '_' + Math.floor(Math.random()*1000),
    order: maxOrder + 1,
    duration: 0,
    status: 'ok',
    name: label,
    cls: DOC.items.length % 6,
    x: 24 + (DOC.items.length % 6) * 26,
    y: 24 + (DOC.items.length % 4) * 30,
    w, h,
    realW: rawW,
    realH: rawH,
    imageName: o.imageName || label
  };
  DOC.items.push(item);
  setItemCanvas(item, work, {
    silent: true,
    keepSize: true,
    maxDim: o.maxDim || RI_WORK_MAX,
    imageName: item.imageName
  });

  selId = item.id;
  if (typeof emptyEl !== 'undefined' && emptyEl) emptyEl.classList.add('hidden');
  if (o.free !== false && mode !== 'free') setMode('free');
  else riRerender();
  if (typeof buildGraph === 'function'){ try { buildGraph(false); } catch(_){} }
  if (o.pushHistory !== false){
    if (typeof pushHistory === 'function') pushHistory('导入图片：' + label);
  }
  return item;
}

/* 解一个本地文件（浏览器能解的格式；真 RAW 会 reject 并说清原因） */
function riDecodeFile(file){
  return new Promise((resolve, reject)=>{
    if (!file) return reject(new Error('没有文件'));
    const isRaw = /\.(cr2|cr3|nef|arw|raf|dng|orf|rw2|pef|srw)$/i.test(file.name);
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = ()=>{
      const c = document.createElement('canvas');
      c.width = img.naturalWidth || img.width;
      c.height = img.naturalHeight || img.height;
      c.getContext('2d').drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      resolve({ canvas: c, name: file.name, isRaw, size: file.size });
    };
    img.onerror = ()=>{
      URL.revokeObjectURL(url);
      reject(new Error(isRaw
        ? '浏览器解不了这个 RAW —— 真 RAW 需要后端 rawpy（LibRaw）解码'
        : '这个文件浏览器打不开'));
    };
    img.src = url;
  });
}

/* 批量导入：一张一张解，最后只记一步历史 */
function riImportFiles(files, opts){
  const o = opts || {};
  const list = Array.from(files || []);
  if (!list.length) return;
  if (RI_IMPORTING){ toast('上一批还在导入，稍等'); return; }
  RI_IMPORTING = list.length;

  const added = [];
  const failed = [];
  let done = 0;

  const finishOne = ()=>{
    done++;
    if (done < list.length) return;
    RI_IMPORTING = 0;

    if (added.length){
      if (o.pushHistory !== false && typeof pushHistory === 'function'){
        pushHistory(added.length > 1 ? `导入 ${added.length} 张图` : '导入图片');
      }
      if (typeof agAdd === 'function' && o.announce !== false){
        const first = added[0];
        agAdd('ai', `已导入 <b>${added.length} 张真图</b>。`
          + `像素现在存在文档里了 —— 缩略图、放大、修图、导出读的是<b>同一份像素</b>。`
          + `<br><br><span class="myown">工作分辨率长边 ${RI_WORK_MAX}px`
          + (first.realW && first.realW !== first.canvas.width
              ? `（原图 ${first.realW}×${first.realH}，原型为性能缩到 ${first.canvas.width}×${first.canvas.height}）`
              : '')
          + `。<br>全部本地处理，没上传、没调模型、没花钱。</span>`);
      }
      toast(`已导入 ${added.length} 张 · 本地 · 免费`);
    }
    if (failed.length){
      if (typeof agAdd === 'function'){
        agAdd('ai', `有 <b>${failed.length} 个文件</b>没导进来：<br>`
          + failed.map(x=>'· ' + esc(x)).join('<br>')
          + `<br><br><span class="myown">JPG/PNG/WebP 浏览器能直接解；`
          + `真 RAW（CR3/NEF/ARW…）里的传感器数据浏览器没有解码器，`
          + `要接后端 <b>rawpy</b>（LibRaw 的 Python 封装，MIT）才行。`
          + `现在可以在「RAW」里试模拟流程。</span>`);
      } else {
        toast('有文件没导进来');
      }
    }
    if (typeof o.onDone === 'function') o.onDone(added, failed);
  };

  list.forEach((f)=>{
    riDecodeFile(f).then(res=>{
      const item = addRealImageItem(res.canvas, riBaseName(res.name), {
        free: o.free !== false,
        pushHistory: false,
        imageName: res.name
      });
      if (item) added.push(item);
    }).catch(err=>{
      failed.push((f.name || '文件') + '：' + err.message);
    }).finally(finishOne);
  });
}

/* 打开系统选图框；opts 可以是回调，也可以是 {multiple, free, onDone} */
function pickImageFile(opts){
  const o = (typeof opts === 'function') ? { onDone: opts } : (opts || {});
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*,.cr2,.cr3,.nef,.arw,.raf,.dng,.orf,.rw2,.pef,.srw,.tif,.tiff';
  input.multiple = !!o.multiple;
  input.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0';
  document.body.appendChild(input);
  input.onchange = ()=>{
    const files = Array.from(input.files || []);
    input.remove();
    if (!files.length) return;
    riImportFiles(files, o);
  };
  input.click();
}

/* 拖文件进画布（拖内部卡片排序不会误触：只看 Files） */
(function riBindDrop(){
  const host = document.getElementById('stage');
  if (!host) return;
  host.addEventListener('dragover', e=>{
    const types = e.dataTransfer ? Array.from(e.dataTransfer.types || []) : [];
    if (!types.includes('Files')) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
    host.classList.add('ri-drop');
  });
  host.addEventListener('dragleave', e=>{
    if (!host.contains(e.relatedTarget)) host.classList.remove('ri-drop');
  });
  host.addEventListener('drop', e=>{
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    host.classList.remove('ri-drop');
    riImportFiles(e.dataTransfer.files, { free: true });
  });
  window.addEventListener('dragover', e=>{
    const types = e.dataTransfer ? Array.from(e.dataTransfer.types || []) : [];
    if (types.includes('Files')) e.preventDefault();
  });
  window.addEventListener('drop', e=>{
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) e.preventDefault();
  });
})();
