/* 19-aifit.js — AI 适配度星级（来源：深海导演技巧库的量化做法）
   🔴 深海导演那份 skill 里，30 个技法每条都标「AI 适配度星级」：
      ★★★★★ 极易实现（已有大量训练数据）
      ★★★★  较易（需精确描述参数）
      ★★★   可实现（需复杂提示词）
      ★★    需后期处理或特殊技术
   这解决了"提示词写得很美但生成不出来"的问题。

   我们的做法：按关键词推断 + 允许手动覆盖（elements 里的 ai 字段优先）。
*/

const AI_FIT_RULES = [
  // —— 2 星：模型最难的地方 ——
  { re:/文字|logo|品名|规格|标题|字体|落位|对齐/i, ai:2,
    why:'文字和 logo 是模型最弱的一环，字形基本保不住' },
  { re:/比例|遮挡|持握|手指|手势|交叠|接触/i, ai:2,
    why:'比例关系和手部动作最容易崩' },
  { re:/机位|景别|视角|透视|仰视|俯视/i, ai:2,
    why:'精确机位需要很长的参数描述，且经常不听话' },

  // —— 3 星：能实现但需要精确描述 ——
  { re:/脸型|脸宽|下巴|颧骨|身高|体型|肩宽|容量|尺寸/i, ai:3,
    why:'需要精确控制，而且跨镜一致性差' },
  { re:/材质|表面|纹理|反光|磨砂|金属|玻璃|布料/i, ai:3,
    why:'材质描述容易出偏差，需要反复调' },
  { re:/构图|版式|留白|栅格|结构|布局/i, ai:3,
    why:'版式类要求高，模型容易自己发挥' },

  // —— 4 星：较易 ——
  { re:/瞳色|肤色|发色|颜色|主色|辅色|色温/i, ai:4,
    why:'颜色能描述，但容易偏一点' },
  { re:/服装|上装|下装|外套|鞋|配饰|耳饰|饰品|标志物/i, ai:4,
    why:'常见元素，训练数据多，但要描述得具体' },
  { re:/道具|台面|背景|墙面|地面|天气|时段/i, ai:4,
    why:'常见场景元素，基本能出' },

  // —— 5 星：极易 ——
  { re:/发型|发长|光比|光|色调|氛围|风格|调性|质感|景深|虚化/i, ai:5,
    why:'风格/光照类词汇效果最好，模型训练充分' },
  { re:/动作|表情|情绪|姿态/i, ai:4,
    why:'常见动作没问题，复杂交互才难' }
];

/* 取某个要素的 AI 适配度 */
function aiFitOf(elem){
  // 手动标注优先
  if (elem && typeof elem.ai === 'number') return { ai: elem.ai, why: aiWhyOf(elem.ai), manual:true };
  const k = (elem && elem.k) || '';
  for (const r of AI_FIT_RULES){
    if (r.re.test(k)) return { ai: r.ai, why: r.why };
  }
  return { ai: 3, why:'没有对应规则，按"可实现"估' };
}

function aiWhyOf(n){
  return {
    5:'极易实现 · 模型训练数据充足',
    4:'较易 · 需要描述得具体',
    3:'可实现 · 需要精确提示词',
    2:'需后期处理或特殊技术',
    1:'基本靠运气'
  }[n] || '';
}

/* 星级 HTML */
function aiStars(n){
  let s = '';
  for (let i = 1; i <= 5; i++) s += `<span class="aist ${i<=n?'on':''}">★</span>`;
  return `<span class="aifit" title="${aiWhyOf(n)}">${s}</span>`;
}

/* 统计：这组要素里有多少项 AI 不好生成 */
function aiFitSummary(elements){
  const list = elements.filter(e=>e.ok && !String(e.v).startsWith('—'));
  const hard = list.filter(e=>{
    const f = aiFitOf(e);
    return f.ai <= 2;
  });
  const mid = list.filter(e=>{
    const f = aiFitOf(e);
    return f.ai === 3;
  });
  return { total:list.length, hard, mid };
}

/* 给提示词打一条"生成难度说明" */
function aiFitNote(elements){
  const s = aiFitSummary(elements);
  if (!s.hard.length && !s.mid.length) return '';
  const parts = [];
  if (s.hard.length){
    parts.push(`<b>${s.hard.length} 项很难生成</b>（${s.hard.map(e=>e.k).join('、')}）`);
  }
  if (s.mid.length){
    parts.push(`${s.mid.length} 项要精确描述（${s.mid.map(e=>e.k).join('、')}）`);
  }
  const extra = s.hard.length
    ? '<br><span class="aitip-x">难生成的那些建议：多跑几版挑一版 / 或先用「局部重绘」事后修</span>'
    : '';
  return `<div class="aitip">
    <span class="aitip-i">◈</span>
    <span class="aitip-t">生成难度：${parts.join(' · ')}${extra}</span>
  </div>`;
}
