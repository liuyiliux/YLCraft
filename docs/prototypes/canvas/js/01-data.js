/* 01-data.js - split from canvas_unified_v14.html (lines 1-36) */

/* ================= 数据：一份文档，三种渲染 ================= */
const BG = ['linear-gradient(165deg,#4a3520,#2a1d12 45%,#17110b)',
  'linear-gradient(165deg,#1e2a35,#0d141b)',
  'linear-gradient(165deg,#2b2440,#141020)',
  'linear-gradient(165deg,#243027,#111a15)',
  'linear-gradient(165deg,#33262b,#1a1216)',
  'linear-gradient(165deg,#2a3320,#12180d)'];

const DEMO = [
  {n:'中景推进', d:4.2, st:'ok'},
  {n:'特写',     d:3.1, st:'ok'},
  {n:'侧身回头', d:5.0, st:'ok'},
  {n:'过场',     d:2.8, st:'ok'},
  {n:'中景',     d:4.5, st:'ok'},
  {n:'近景',     d:3.3, st:'ok'},
  {n:'远景',     d:4.0, st:'err'},
  {n:'特写',     d:3.6, st:'ok'},
  {n:'转身',     d:4.8, st:'ok'},
  {n:'过场',     d:2.2, st:'run'},
  {n:'中景',     d:3.9, st:'ok'},
  {n:'收尾',     d:0.0, st:'todo'}
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

