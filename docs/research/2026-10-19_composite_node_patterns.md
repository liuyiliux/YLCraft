# 别家的"复杂节点"是怎么设计的（2026-10-19）

> 问题：**别的平台的复杂节点是怎么设计的？**
> 查了七个体系，结论先放：**Houdini 的 Digital Asset（HDA）是最贴我们的范式**。

---

## 一、七种机制对照

| 体系 | 机制 | 本质 | 折叠成节点？ |
| --- | --- | --- | --- |
| 🔴 **Houdini** | **Digital Asset (HDA)** + **promoting parameters** | 把一张节点网络打包成一个节点，**挑几个参数提升到节点界面** | ✅ 且可解锁进入 |
| **Blender** | **Node Group**（Ctrl+G） | 一组节点折叠成一个，用 Group Input/Output 定义接口，Tab 进出 | ✅ |
| **ComfyUI** | **Group Node**（Convert to Group Node） | 选中一组 → 转成一个虚拟节点，可存成自定义节点 | ✅ |
| **n8n** | **Sub-workflow**（Execute Sub-workflow） | 一个节点**引用另一张工作流**，显式映射输入输出 | ✅（引用式） |
| **LibTV** | **打组（整组执行）** | 🔴 **只解决"一起跑"，不折叠** | ❌ |
| **Toonflow** | 节点插件化（`packages/nodes/*`）+ 插件市场 | 一个节点一个包，可安装 | ❌ |
| **Lovart** | **Skill** | 🔴 **点开是表单，根本不是节点** | ❌ |

---

## 二、🔴 Houdini HDA：最贴我们的范式

官方原话（[Introduction to digital assets](http://www.sidefx.com/docs/houdini/assets/intro.html)）：

> "You can turn your own networks into **reusable custom nodes** with their own user interfaces."
> —— 把自己的网络变成**可复用的自定义节点**，带自己的界面。

> "You can create a user interface for your asset by **promoting parameters** on the contained nodes up onto the asset node."
> —— 通过**把内部节点的参数"提升"到资产节点上**，来做界面。

> "The animators can interact with the character node exclusively **without being exposed to the implementation details**."
> —— 动画师只用这个角色节点，**完全不用碰实现细节**。

> "has defaults tweaked the way you want them, and **only exposes the controls you want lighters to use**."
> —— 只暴露**你想让打光师用**的那几个控件。

### 这套机制解决了我们三个问题

| Houdini 的机制 | 对应我们的问题 |
| --- | --- |
| **promoting parameters**（参数提升） | 🔴 **"复杂节点只露 3 个参数"** —— 不是新发明，是 HDA 的标准做法 |
| 用户**不接触实现细节** | 🔴 三层模型（L2 页面内部有 10 个参数，L3 只露 3 个） |
| **资产库 + 版本 + 市场（Orbolt）** | 我们的模板 / 技能体系 |

### HDA 的完整生命周期（值得照抄）

```
① 搭一张网络
      ↓
② 转成资产（subnetwork → HDA）
      ↓
③ 提升参数（挑 N 个到节点界面）
      ↓
④ 定义资产界面（分组/标签页/条件显示）
      ↓
⑤ 存进资产库（.hda），带版本
      ↓
⑥ 别人安装 → 像内置节点一样用
      ↓
⑦ 需要时"解锁"进入内部改
```

**这就是我们"复杂节点"该有的完整链路。**

---

## 三、Blender Node Group：Tab 进出这个设计值得抄

[Blender 手册](https://docs.blender.org/manual/zh-hant/3.6/interface/controls/nodes/groups.html)：

> "Conceptually, node groups allow you to **treat a set of nodes as though it were just one node**.
> They're similar to **functions in programming**: they can be reused (even in different node trees) and can be customized by changing their 'parameters'."

**关键操作：**
| 操作 | 行为 |
| --- | --- |
| `Ctrl+G` | 选中节点 → 打组 |
| **`Tab`** | **进入 / 退出组**（不是双击！） |
| Group Input / Group Output | 定义这个组的输入输出接口 |
| `Ctrl+Alt+G` | 取消群组 |
| **Group Insert** | 把某个节点插进已有的组（不改连线） |

🔴 **Tab 进出比双击更明确** —— 用户知道自己在"组内外"哪一层。
双击容易跟"打开属性"冲突。

---

## 四、ComfyUI Group Node：有坑，值得看

做法：选中多个节点 → 右键 「Convert to Group Node」→ 变成一个虚拟节点，有 primitive 输入输出，可存成自定义节点。

**但有个真实的坑**：[Issue #8887 "Convert to Group Nodes is not working"](https://github.com/Comfy-Org/ComfyUI/issues/8887)
—— 说明这套机制**端口映射和内部引用很容易出错**。

**给我们的警示：**
- 折叠节点最难的部分是**接口（端口）映射**，不是折叠本身
- 必须**先定义好接口再允许折叠**
- 内部节点被删/改时，要能报错而不是静默失效

---

## 五、n8n Sub-workflow：显式输入输出映射

n8n 的做法：一个「Execute Sub-workflow」节点，**引用另一张已存在的工作流**。

| 特点 | 说明 |
| --- | --- |
| **显式映射** | 子工作流有明确的 Input/Output 定义，父级填写对应关系 |
| 一个子流程多处复用 | 改了子流程，所有引用处都变 |
| 有执行历史穿透 | 能看到子流程里的执行详情 |

🔴 **"改了子流程，引用处全变"这个特性我们要不要？**
- 要 → 模板升级能自动生效（方便，但危险）
- 不要 → 每个引用是快照（安全，但要手动升）

**我建议：默认快照，允许手动"升级到最新"。**（HDA 的版本机制也是这个思路）

---

## 六、LibTV / Toonflow / Lovart：三种"不折叠"的做法

| 平台 | 做法 | 评价 |
| --- | --- | --- |
| **LibTV** | **打组只为"一起跑"**（整组执行） | 🔴 组还是散的，视觉没减少；但**解决了"改了一处要重跑一片"** |
| **Toonflow** | 节点插件化，一个节点一个包 | 节点本身不复杂，不需要折叠 |
| **Lovart** | **Skill = 表单** | 用户只看到"按钮 → 表单 → 产物"，**连节点概念都没有** |

**Lovart 这条路值得单独说**：它压根没有"复杂节点"这个问题，因为它没有节点。
用户看到的是「美妆海报」这个**按钮**，点开是表单（当前模板/商品图/商品资料/开始生成）。

🔴 **这提示我们：如果某类用户永远不想看节点，就该给他 Skill 表单，而不是复杂节点。**

---

## 七、汇总：我们该抄什么

| 来源 | 抄什么 | 落到我们哪 |
| --- | --- | --- |
| 🔴 **Houdini** | **参数提升（promoting parameters）** | 复杂节点只露 3 个参数 |
| 🔴 **Houdini** | 用户不接触实现细节 | 页面内部参数不露 |
| **Houdini** | 资产库 + 版本 + 市场（Orbolt） | 模板 / 技能市场 |
| **Houdini** | 锁定 / 解锁 | 复杂节点默认锁定，可解锁进页面 |
| 🔴 **Blender** | **Tab 进出组** | 用户自己打的组 |
| **Blender** | Group Input / Output 定义接口 | 用户组的接口由他定义 |
| **ComfyUI** | ⚠️ 端口映射是最大的坑 | 先定接口再允许折叠 |
| **n8n** | 显式输入输出映射 | 复杂节点的端口要显式 |
| **n8n** | 子流程改了就全变 → **我们改快照** | 模板默认快照，手动升级 |
| **LibTV** | 打组执行（不是折叠） | 复杂节点内的"整组重跑" |
| **Lovart** | Skill = 表单（无节点） | 给不想看节点的用户 |

---

## 八、更新后的复杂节点规格

基于 HDA，补三条之前没有的：

```ts
interface CompositeNodeSpec {
  id: string;
  label: string;              // '@生图工作台'（名词）

  // ① HDA 的参数提升：从页面 N 个参数里挑 ≤3 个
  promotedParams: [
    { key:'model', label:'模型', widget:'select', source:'page.model' },
    { key:'ratio', label:'比例', widget:'select', source:'page.ratio' },
  ];
  hiddenParamCount: 4;        // 折叠起来的数量，显示成「⚙ 还有 4 项」

  // ② n8n 的显式映射
  inputs:  [{ id:'prompt', type:'text', required:true }],
  outputs: [{ id:'images', type:'image', multiple:true }],

  // ③ 调用后端（不是调页面）
  invoke: { method:'POST', path:'/api/v1/images/generate', map: fn },

  // ④ Houdini 的"解锁"：进入页面改全部参数
  unlock: { action:'open-page', url:'/image-gen' },

  // ⑤ 版本（Houdini 的 asset versioning）
  version: 3,
  upgradePolicy: 'snapshot',   // 默认快照；允许手动"升到最新"
}
```

**新增的三个字段：`promotedParams` / `hiddenParamCount` / `upgradePolicy`**

---

## 九、还没定的

| # | 问题 | 我的倾向 |
| --- | --- | --- |
| 1 | 复杂节点要不要允许"解锁进入页面" | **要**（Houdini 这么做） |
| 2 | 用户打的组用 Tab 还是双击进出 | **Tab**（Blender 更明确） |
| 3 | 模板升级：快照 vs 全变 | **默认快照，手动升级** |
| 4 | 要不要做模板/技能市场 | 以后（Toonflow、Houdini 都有） |
| 5 | 给不想看节点的用户，要不要单独做 Skill 表单入口 | **要**（Lovart 路线） |
