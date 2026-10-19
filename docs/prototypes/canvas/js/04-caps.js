/* 04-caps.js - split from canvas_unified_v14.html (lines 697-852) */
/* ================= P4：统一 invoke（Skill / 复杂节点 / 基础节点共用一份） ================= */

/* 一个能力 = 一份 invoke。外面套节点还是套表单，是渲染层的事。 */
const CAPS = {
  'image-gen': {
    label:'生图', page:'/image-gen',
    invoke:{ method:'POST', path:'/api/v1/images/generate' },
    map:(i,p)=>({ prompt:i.prompt, refs:i.reference, model:p.model, ratio:p.ratio, n:p.count||1 }),
    params:{ model:'GPT Image 2', ratio:'2:3', count:1 },
    cost:14
  },
  'motion-gif': {
    label:'动图', page:'/motion',
    invoke:{ method:'POST', path:'/api/v1/images/motion-gif/compose' },
    map:(i,p)=>({ sheet:i.sheet, layout:p.grid, format:p.format }),
    params:{ grid:'3×3', format:'GIF' },
    cost:14
  },
  'model-3d': {
    label:'图生 3D', page:'/model-3d',
    invoke:{ method:'POST', path:'/api/v1/3d/generate-from-image' },
    map:(i,p)=>({ image:i.image, quality:p.quality }),
    params:{ quality:'标准' },
    cost:8
  },
  'previs': {
    label:'3D 导演台', page:'/previs',
    invoke:{ method:'POST', path:'/api/v1/previs/preview' },
    map:(i,p)=>({ board:i.text, model:i.model, shot:p.shot }),
    params:{ shot:'推近' },
    cost:6
  },
  'image-editor': {
    label:'图片编辑', page:'/image-editor',
    invoke:{ method:'POST', path:'/api/v1/images/edit' },
    map:(i,p)=>({ image:i.image, op:p.op }),
    params:{ op:'裁剪' },
    cost:0
  },
  'clip': {
    label:'剪辑出片', page:'/clip',
    invoke:{ method:'POST', path:'/api/v1/clip/compose' },
    map:(i,p)=>({ shots:i.video, tempo:p.tempo }),
    params:{ tempo:'标准' },
    cost:2
  },
  'crop': {
    label:'裁剪', page:null, local:true,
    invoke:{ method:'LOCAL', path:'shared/image-ops#crop' },
    map:(i,p)=>({ image:i.image, box:p.box }),
    params:{ box:'居中' },
    cost:0
  },
  'filter': {
    label:'滤镜', page:null, local:true,
    invoke:{ method:'LOCAL', path:'shared/image-ops#filter' },
    map:(i,p)=>({ image:i.image, preset:p.preset }),
    params:{ preset:'中' },
    cost:0
  }
};

/* ================= 补全 L1 能力清单（对应 FEATURE_LAYER_MATRIX） =================
   原则：一个能力一份定义，L2 页面和 L3 节点都调它。
   layer: 'local' 免费 / 'model' 调模型
   node:  能不能在画布上做成节点
*/
Object.assign(CAPS, {
  'search-web': {
    label:'联网搜索', layer:'model', node:true,
    invoke:{ method:'POST', path:'/api/v1/search/web' },
    map:(i,p)=>({ queries:p.queries, intent:p.intent }),
    params:{ queries:['','',''], intent:'appearance' },
    cost:0,
    note:'queries 数组 1-4 个 · intent 三种：fact / appearance / reference-image'
  },
  'search-asset': {
    label:'搜参考图', layer:'local', node:true,
    invoke:{ method:'POST', path:'/api/v1/search/asset' },
    map:(i,p)=>({ queries:p.queries, count:p.count }),
    params:{ queries:[''], count:3 },
    cost:0,
    note:'搜到的图直接存成 asset，能当参考图'
  },
  'extract-elements': {
    label:'抽要素', layer:'model', node:true,
    invoke:{ method:'POST', path:'/api/v1/extract/elements' },
    map:(i,p)=>({ sources:p.sources, subject:p.subject }),
    params:{ subject:'character' },
    cost:2,
    note:'输出结构化要素（不是总结）· 按 subject schema 分组 · 带 critical 判断'
  },
  'image-adjust': {
    label:'本地精调', layer:'local', node:true,
    invoke:{ method:'POST', path:'/api/v1/images/adjust' },
    map:(i,p)=>({ asset:i.image, exposure:p.exposure, levels:p.levels, curves:p.curves }),
    params:{ exposure:0, levels:{black:0,white:1,gamma:1}, curves:null },
    cost:0,
    note:'曲线/色阶/曝光/白平衡 · 纯像素运算 · 参数不烘焙'
  },
  'image-raw': {
    label:'RAW 解码', layer:'local', node:true,
    invoke:{ method:'POST', path:'/api/v1/images/raw-decode' },
    map:(i,p)=>({ file:i.file, bps:p.bps }),
    params:{ bps:16 },
    cost:0,
    note:'rawpy · gamma=(1,1) · output_bps=16 → 线性数据 · 调曝光才不炸'
  },
  'image-export': {
    label:'导出合成', layer:'local', node:true,
    invoke:{ method:'POST', path:'/api/v1/images/export' },
    map:(i,p)=>({ asset:i.image, layers:p.layers, format:p.format }),
    params:{ format:'PNG', scale:1 },
    cost:0,
    note:'按层顺序合成 · 只在导出时算像素 · 导出后参数还在'
  },
  'image-inspect': {
    label:'巡检', layer:'local', node:true,
    invoke:{ method:'POST', path:'/api/v1/images/inspect' },
    map:(i,p)=>({ assets:p.assets, level:p.level }),
    params:{ level:'L1+L2' },
    cost:2,
    note:'三层成本：L1代码免费 / L2本地模型免费 / L3语义才花钱'
  },
  'prompt-lib': {
    label:'提示词库', layer:'local', node:false,
    invoke:{ method:'GET', path:'/api/v1/prompts' },
    map:(i,p)=>({ q:p.q }),
    params:{},
    cost:0,
    note:'资产（和素材库同级）· 不是节点，是 @ 引用的来源'
  }
});

/* 给原有 8 项补上 layer / node 标记 */
Object.assign(CAPS['image-gen'],   { layer:'model', node:true });
Object.assign(CAPS['motion-gif'],  { layer:'model', node:true });
Object.assign(CAPS['model-3d'],    { layer:'model', node:true });
Object.assign(CAPS['previs'],      { layer:'model', node:true });
Object.assign(CAPS['image-editor'],{ layer:'model', node:false,
  note:'L2 页面容器，不是独立能力 —— 它内部调 crop/filter/image-adjust' });
Object.assign(CAPS['clip'],        { layer:'model', node:true });
Object.assign(CAPS['crop'],        { layer:'local', node:true });
Object.assign(CAPS['filter'],      { layer:'local', node:true });

/* 能力清单统计（原型里能看到） */
function capsStats(){
  const all = Object.entries(CAPS);
  return {
    total: all.length,
    local: all.filter(([k,v])=>v.layer==='local').length,
    model: all.filter(([k,v])=>v.layer==='model').length,
    nodes: all.filter(([k,v])=>v.node).length
  };
}

