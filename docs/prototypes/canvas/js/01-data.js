/* 01-data.js - split from canvas_unified_v14.html (lines 1-36) */

/* ================= 数据：一份文档，三种渲染 ================= */
const BG = ['linear-gradient(165deg,#4a3520,#2a1d12 45%,#17110b)',
  'linear-gradient(165deg,#1e2a35,#0d141b)',
  'linear-gradient(165deg,#2b2440,#141020)',
  'linear-gradient(165deg,#243027,#111a15)',
  'linear-gradient(165deg,#33262b,#1a1216)',
  'linear-gradient(165deg,#2a3320,#12180d)'];

/* n = 分镜标题（这一镜讲什么，AI 对画面的总结）
   sz = 景别（属性，显示成角标）
   cast = 这一镜画面里有谁（空数组 = 空镜，要显式标出来）
   ⚠️ 别把景别词当标题 —— 「中景推进」是属性不是标题，卡片下面那行要写内容。
   这一组是「秋天颐和园 · 小林 · 斜侧逆光」的分镜，改 2026-11-02。
   2026-11-03 加 cast：照 Storyboard 的做法，只标「这一镜出现的人」，不是全场名单。 */
const DEMO = [
  {n:'她在长廊尽头回头',   sz:'中景', d:4.2, st:'ok',  cast:['小林']},
  {n:'眼圈红了的那一下',   sz:'特写', d:3.1, st:'ok',  cast:['小林']},
  {n:'侧身，肩线转过来',   sz:'中景', d:5.0, st:'ok',  cast:['小林']},
  {n:'从石阶走到廊下',     sz:'全景', d:2.8, st:'ok',  cast:['小林']},
  {n:'停在窗棂前',         sz:'中景', d:4.5, st:'ok',  cast:['小林']},
  {n:'手指划过木栏杆',     sz:'近景', d:3.3, st:'ok',  cast:['小林']},
  {n:'整条长廊的空镜',     sz:'远景', d:4.0, st:'err', cast:[]},
  {n:'抬头，睫毛在抖',     sz:'特写', d:3.6, st:'ok',  cast:['小林']},
  {n:'转身走进光里',       sz:'中景', d:4.8, st:'ok',  cast:['小林']},
  {n:'光影扫过地面',       sz:'全景', d:2.2, st:'run', cast:[]},
  {n:'两人并肩走过长廊',   sz:'中景', d:3.9, st:'ok',  cast:['小林','客户B']},
  {n:'走远，背影变小',     sz:'全景', d:0.0, st:'todo', cast:['小林']}
];

/* 角色图批次（2026-11-01 加）
   ⚠️ 别再把它和 DEMO 混用：DEMO 是**视频分镜**（一镜有景别和时长），
   这里是**角色设定图**（按角度出，没有时长）。搜角色参考那条流程必须走这个。
   角度取自后端 turnaround 的 9 个方位标签（characters.py），是现成能力不是编的。 */
const DEMO_CHAR = [
  {n:'正面 · 半身', d:0, st:'ok'},
  {n:'正面 · 全身', d:0, st:'ok'},
  {n:'3⁄4 侧',      d:0, st:'ok'},
  {n:'侧面',        d:0, st:'ok'},
  {n:'背面',        d:0, st:'ok'},
  {n:'俯视 · 半身', d:0, st:'ok'}
];

let DOC = { items: [] };   // {id,order,duration,status,name,x,y,w,h,cls}
let mode = 'shots';
let selId = null;
let dragOrder = -1;

const stage  = document.getElementById('stage');
const grid   = document.getElementById('grid');
const track  = document.getElementById('track');
const freecv = document.getElementById('freecv');
const agb    = document.getElementById('agb');
const emptyEl= document.getElementById('empty');

