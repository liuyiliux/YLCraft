# 许可审计：我们的画布代码到底出自哪（2026-10-18）

> **结论先行：我们抄的是 `basketikun/infinite-canvas`（MIT），不是 AGPL 那个。**
> **`NOTICE.md` 写错了许可，把 MIT 写成了 AGPL-3.0。**
> **我们白白背了一个月的 AGPL 包袱。**

---

## 一、审计方法

1. 下载两个同名项目的源码（`codeload`）
2. 逐行对比核心算法
3. 判定我们的代码出自哪一个

---

## 二、两个项目是同源的

| 文件 | `basketikun/infinite-canvas` | `tigerowo/infinite-canvas` |
| --- | --- | --- |
| `infinite-canvas.tsx` | 10.6 KB | 11.5 KB |
| `canvas-mini-map.tsx` | 5.6 KB | 5.8 KB |
| `canvas-node-hover-toolbar.tsx` | 17.6 KB | 18.5 KB |
| **LICENSE** | 🔵 **MIT**（1 KB） | 🔴 **AGPL-3.0**（33.7 KB） |
| Star | 7,748 | 1,210 |

**同名文件、几乎一样的体积 —— 是同一个项目的两个分支。**
两个版本的 `infinite-canvas.tsx` 代码 95% 相同，只差 `"use client"` 和 import 路径。

> 🔴 **这解释了我们为什么会写错**：两个项目**同名**，一个 MIT 一个 AGPL，
> 当初抄的时候很可能查到了 AGPL 那份的许可说明。

---

## 三、逐行证据：我们的代码出自哪个

### 3.1 指针锚定缩放算法

| 代码 | basketikun | tigerowo | **我们** |
| --- | --- | --- | --- |
| `const delta = -event.deltaY` | ✅ L91 | ✅ L93 | ✅ L262 |
| `Math.pow(1.1, delta / 100)` | ✅ | ✅ | ✅ |
| `Math.min(Math.max(..., 0.05), 5)` | ✅ | ✅ | **`MIN_SCALE, MAX_SCALE`** |
| `worldX = (mouseX - x) / k` | ✅ | ✅ | ✅ |
| `x: mouseX - worldX * newScale` | ✅ | ✅ | ✅ |

**核心 5 行逐字相同。**

**但注意常量：**

| | 缩放范围 |
| --- | --- |
| 上游两边 | `0.05 ~ 5` |
| **我们** | **`MIN_SCALE = 0.08` ~ `MAX_SCALE = 4`** |

🔴 **这是关键证据：上游两边都是 `0.05, 5`，我们改成了 `0.08, 4`。**

> 如果是照抄 tigerowo，我们应该也是 `0.05, 5`。
> **说明我们抄的是"算法骨架"，常量自己调过 —— 这是 MIT 允许的派生方式。**

### 3.2 网格渲染

| 代码 | basketikun | tigerowo | **我们** |
| --- | --- | --- | --- |
| `const gridSize = 48 * viewport.k` | ✅ L239 | ✅ L251 | ✅ `GRID_SIZE * viewport.k` |
| `const x = viewport.x % gridSize` | ✅ L240 | ✅ L252 | ✅ |
| `backgroundSize: ${gridSize}px ${gridSize}px` | ✅ L251 | ✅ L263 | ✅ |
| `backgroundPosition: ${x}px ${y}px` | ✅ L252 | ✅ L264 | ✅ |

**四行逐字相同。** 但我们的多了一个 `immersive` 模式（`opacity` 和两套背景色）—— 这是我们自己加的。

### 3.3 交互排除选择器

| | 内容 |
| --- | --- |
| 上游两边 | `"[data-canvas-no-zoom],.ant-modal,.ant-popover,.ant-dropdown,.ant-select-dropdown,.ant-picker-dropdown"` |
| **我们** | **抽成了常量** `CANVAS_INTERACTIVE_SELECTOR`，**并多加了 `data-canvas-no-drag` / `data-canvas-interactive`** |

**同样是"抄骨架 + 自己扩展"。**

### 3.4 我们独有、上游没有的

| 能力 | 上游 | 我们 |
| --- | --- | --- |
| **类型化端口** (`CanvasPort` / `dataType`) | ❌ | ✅ |
| **连线类型校验** (`compatible`) | ❌ | ✅ |
| **workflow 执行轨迹** (`WorkflowTrace`) | ❌ | ✅ |
| `immersive` 网格模式 | ❌ | ✅ |
| 自定义缩放范围 | ❌ | ✅ |
| `data-canvas-no-drag` 等 3 个属性 | ❌ | ✅ |

---

## 四、审计结论

### ✅ 我们抄的是 **MIT** 版本

三条理由：

1. **我们只抄了"算法骨架"**（缩放数学、网格定位、排除选择器思路），
   **没有整文件复制**——我们的 `InfiniteCanvasSurface.tsx` 39.4 KB / 1,062 行，
   上游 `infinite-canvas.tsx` 只有 10.6 KB。
2. **常量都不一样**（`0.08/4` vs `0.05/5`），说明是**改编不是复制**。
3. **两个上游里，只有 basketikun 是 MIT**，而我们是按它改的。

### 🔴 但 `NOTICE.md` 写的是 AGPL-3.0

```markdown
Interaction model adapted from basketikun/infinite-canvas:
https://github.com/basketikun/infinite-canvas
Licensed under AGPL-3.0. See NOTICE.md in this directory.
```

**上游 LICENSE 原文第一行：`MIT License` `Copyright (c) 2026 basketikun`**

### 影响

| | 按现在的 NOTICE（AGPL） | 按实际（MIT） |
| --- | --- | --- |
| 能否闭源 | ❌ 不能，整套服务端要开源 | ✅ **能** |
| 能否商用 | ⚠️ 可以但必须开源 | ✅ **能** |
| 义务 | 提供全部源码 | **只保留版权声明** |

> 🔴 **如果 YLCraft 将来要闭源或商业化，这个错误是致命的。**
> 好消息是：**它是写错了，不是真的侵权。**

---

## 五、要改什么

### 1. `NOTICE.md` 改成 MIT（必须）

```markdown
# YLCraft Infinite Canvas Notice

The viewport, world-layer, grid, pointer-anchored zoom and pan interaction
model are adapted from:

- Project: basketikun/infinite-canvas
- Source: https://github.com/basketikun/infinite-canvas
- License: MIT
- Copyright (c) 2026 basketikun

This project's canvas module is an independent adaptation: the interaction
model and math are derived, but node types, port typing, connection
validation and execution tracing are YLCraft's own work.
```

### 2. `InfiniteCanvasSurface.tsx` 头部注释也要改

现在是：
```
* Licensed under AGPL-3.0. See NOTICE.md in this directory.
```
改成：
```
* Licensed under MIT. See NOTICE.md in this directory.
```

### 3. 搜全仓库还有没有其他 AGPL 误标

---

## 六、还有一个隐患要查

**我们的调研里记录过 `tigerowo/infinite-canvas` 是 AGPL-3.0（1,210★）。**

**如果当初参考过它的代码**（哪怕只参考了一部分），那部分仍是 AGPL。
本次审计只对比了 `infinite-canvas.tsx` 这一个文件的缩放/网格逻辑，**没有做全文件比对**。

**建议**：如果要彻底放心，做一次全文件相似度比对
（比如用 `diff` 或 `jscpd` 跑我们 `canvas/` 目录 vs 上游）。

---

## 七、一句话

**我们抄的是 MIT 项目，NOTICE 却写成了 AGPL。**
**这是笔误，不是侵权 —— 但会误导团队和用户，必须改。**

---

## 八、全量相似度比对（2026-10-18 补充执行）

### 方法

对 `InfiniteCanvasSurface.tsx`（729 条有效行，已剔除空行/纯括号/import）与两个上游做
**逐行精确匹配**（空白归一化后完全相等才算命中），并设计对照实验排除通用样板噪声。

### 结果

| 对比对象 | 重合行数 | 占我们有效行 |
| --- | --- | --- |
| 上游 `canvas-mini-map.tsx`（**不同功能，对照组**） | 8 | 1.1% |
| 上游 `canvas-node-hover-toolbar.tsx`（不同功能，对照组） | 5 | 0.7% |
| 上游 `canvas-node-split-dialog.tsx`（不同功能，对照组） | 5 | 0.7% |
| **上游 `infinite-canvas.tsx`（功能对应）** | **19** | **2.6%** |
| 上游 tigerowo 版 `infinite-canvas.tsx` | 16 | 2.2% |

### 解读

**对照组给出噪声基线：0.7% ~ 1.1%。**
（这些是 `useEffect(() => {`、`return () => {`、`ref={containerRef}` 这类谁写都一样的样板）

**真正对应文件的 2.6% 比基线高出 1.5~1.9 个百分点** —— 超出的这十几行，正是我们已在
NOTICE 里声明的派生范围：

```
const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
onWheel={handleWheel}
transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.k})`,
backgroundPosition: `${x}px ${y}px`,
onViewportChange({
frameRef.current = requestAnimationFrame(() => {
```

**即：指针锚定缩放 + 网格偏移 + 视口 transform 的交互骨架。**

### 与 tigerowo（AGPL）的 16 行重合说明什么

**不能证明抄了 tigerowo。** 两个上游本就 95% 相同，那 16 行是**两边都有的通用样板**，
是"两份上游互相同"的自然结果，不是"我们抄了 AGPL 那份"的证据。

**判定依据仍是**：① 我们的 NOTICE 当时写明来源是 basketikun；② 派生范围只在交互模型；
③ 超出基线的部分不含 tigerowo 独有代码（tigerowo 独有的 ctrlKey 缩放分支等我们都没有）。

### 量化结论

| 指标 | 值 |
| --- | --- |
| 文件规模 | 我们 729 有效行 / 上游 149 有效行 |
| 逐字重合 | 19 行（2.6%），其中约 8~11 行是通用样板 |
| **实际派生** | **约 1.5%~1.9% 的交互骨架** |
| 自有实现 | 端口类型化、连线校验、WorkflowTrace、节点渲染、文档模型、持久化、immersive 网格、自定义缩放边界 |

**这是一个范围明确、可声明的 MIT 派生，不是复制。**

---

## 附：审计证据文件位置

```
%TEMP%\ic-audit\
  basketikun__infinite-canvas.zip    (4.0 MB)
  tigerowo__infinite-canvas.zip      (2.4 MB)
```
审计完可删。

---

## 九、已执行的修正

| 文件 | 改动 |
| --- | --- |
| `frontend/src/components/canvas/NOTICE.md` | AGPL-3.0 → **MIT**，补 `Copyright (c) 2026 basketikun`，新增「派生范围 / 自有部分」两节，记录本次误标原因 |
| `frontend/src/components/canvas/InfiniteCanvasSurface.tsx` | 头部注释 `Licensed under AGPL-3.0` → **MIT**，明确派生范围 |
| `docs/reference/REF_PROJECTS.md` | 🔴 **误标源头**：把 `basketikun`（MIT）的 URL 与 AGPL-3.0 错误配对 → 改为 MIT 并加同名项目警示 |

全仓库复查：除上述三处，其余 `AGPL` 提及均指向**其他项目**（OpenMontage / immich / pooml /
YILING0013 / MediaCMS / FreeMoCap），事实无误，不需改。
