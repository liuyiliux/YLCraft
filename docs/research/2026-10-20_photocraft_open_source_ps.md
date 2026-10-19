# PhotoCraft：开源的 PS 重实现（2026-10-20 核实）

> 你问：**「最近 PS 是不是被逆向开源了 photocraft」**
>
> **有这个东西，但「逆向」这个说法不准确。**
> 它是 **clean-room reimplementation（净室重实现）**，不是逆向工程。
> 这个区别在**法律上**很重要，我下面说清楚。

---

# 一、它是什么（GitHub API 实测）

| 项 | 数据 |
| --- | --- |
| 仓库 | [`storytold/photocraft`](https://github.com/storytold/photocraft) |
| 自述 | **「an open-source, clean-room reimplementation of Adobe Photoshop, rebuilt in pure Rust」** |
| Stars | **68,327** |
| Forks | **12,040** |
| Open issues | **2,851** |
| 语言 | **100% Rust** |
| 许可证 | **MIT / Apache-2.0 双许可** ✅ |
| 创建 | **2026-09-30**（20 天前） |
| 最后 push | 2026-10-19（一直在更新） |
| 主页 | https://getartcraft.com/apps/photocraft |
| 平台 | macOS / Windows / Linux / FreeBSD / **Web-native** |

## 1.1 🔴 「逆向」vs「净室重实现」—— 这个区别必须说清

媒体标题用的是「AI 逆向的 Adobe 全家桶」（[DoNews](https://www.donews.com/news/detail/1/6738371.html)、[知乎](https://zhuanlan.zhihu.com/p/2094482470439855952)），
**但这个说法在法律上是错的，而且会误导我们对它能不能用的判断。**

| | 逆向工程（Reverse Engineering） | 净室重实现（Clean-room Reimplementation） |
| --- | --- | --- |
| **做什么** | 反编译/破解原软件二进制 | 看功能描述，从零写代码 |
| **碰原代码吗** | 碰 | **完全不碰** |
| **合法性** | 侵犯著作权 | **合法** |
| **PhotoCraft 属于** | | ✅ **这个** |

README 原话：**「clean-room reimplementation」**、**「written entirely in Rust」**。

**所以：它是合法的开源软件，MIT/Apache-2.0 双许可，我们可以自由学习甚至移植它的代码。**

媒体用「逆向」纯是标题党。

## 1.2 它是 AI 写的（这点媒体说对了）

从仓库能看出明显的 AI 开发痕迹：

| 证据 | 说明 |
| --- | --- |
| `AGENTS.md`（18.5KB） | AI agent 协作规范 |
| ROADMAP 里用 **「Opus 5.5 agent hours」** 做工时单位 | 直接按 AI 工作时间估算 |
| **1,004 个 merged PR** 在 20 天内 | 人类做不到这个速度 |
| ROADMAP 说「features 从 224→532 菜单，一天内」 | 同上 |

**这印证了一件事：AI 能把"重写一个 PS"的成本压到 20 天出 alpha。**
（但离"能用"还有距离，见下）

---

# 二、它现在到底做到什么程度（ROADMAP 实读）

## 2.1 关键数字（v0.6.0，2026-10-13 数据）

| 指标 | 值 |
| --- | --- |
| **阶段** | **early alpha**（不是完成品） |
| **功能广度** | **~76%**（菜单 628/628 · 工具 56/68 · 面板 30/35 · 格式 13+4 of 31） |
| **真正能干活** | **~45%**（40–50%） |
| Open issues | **953**（2026-10-13） |
| 性能预算 | **25 个里只达标 3 个** |
| **PSD 兼容** | 🔴 **写出来的 PSD，Photoshop 还不能可靠打开**（#1281、#2469） |
| 距 beta | **~1,100–1,800 小时** |
| 距完全对齐 PS 2026 | **~2,300–4,100 小时** |
| 首个 commit | 2026-09-30 |

**所以：「PS 被开源了」这个说法过头了 —— 它是「PS 的 76% 广度、45% 可用度的早期 alpha」。**

## 2.2 分维度就绪度（🔴 这张表对我们最有价值）

| 维度 | 就绪度 | 我们还差多少 |
| --- | --- | --- |
| **Layers, masks, blend modes, smart objects, styles** | **65%** | 我们刚做完图层+6种混合模式 ✅ 方向对 |
| **Adjustments and filters** | **70%** | 我们做了曲线/色阶/HSL/降噪锐化 ✅ |
| **Transform, warp, puppet, liquify** | **55%** | 🟢 **我们刚做完液化** ✅ |
| **Retouching (healing, clone, patch, content-aware)** | **50%** | 🟢 我们刚做完祛瑕疵 ✅ |
| Selections, Select and Mask, channels | 55% | 我们只有蒙版，没有选区工具 |
| Painting and brush engine | 55% | 我们没做画笔（不适用） |
| Colour management and modes | 70% | 我们只有色温/色相 |
| Camera Raw | 45% | 我们有 RAW 占位 |
| File I/O | 60% | 我们的导出是占位 |
| Type | 40% | 我们只有"加文字" |
| Vector shapes and paths | 55% | 不适用 |
| **AI / generative** | 🔴 **10%** | **这是我们的强项** |
| Ecosystem / plug-ins / scripting | 15% | 我们没做 |
| Video / timeline | 30% | 我们有动图 |

## 2.3 🔴 最重要的一条：它的 AI 只有 10%

```
AI features        10%    300–600 小时
```

**PhotoCraft 强在"传统修图"（图层70% / 调整70% / 液化55%），弱在 AI（10%）。**

**而这正好和我们互补：**
- 我们强在 AI 生成（搜索→要素→生成→巡检）
- 它强在传统修图底座

`docs/gaps.md` 里还有个 **`G15 AI and generative features`** 章节专门列 AI 的缺口。

**换句话说：它把「PS 的传统部分」做了，我们把「AI 生成部分」做了。两者不冲突。**

---

# 三、对我们有没有用？有用，但不是"直接拿来用"

## 3.1 不能直接嵌（技术栈不同）

| | PhotoCraft | 我们 |
| --- | --- | --- |
| 语言 | Rust | Python（后端）+ JS（前端） |
| 形态 | 原生桌面应用 | Web |
| 许可 | MIT/Apache-2.0 | — |

**Rust 桌面应用不能嵌进我们的 Python + Web 产品。**

## 3.2 但有三件实实在在的用处

### ✅ 用处 1：验证我们刚才的判断（液化/磨皮/祛瑕疵）

我们昨天刚实证的：
- 液化 = 网格变形（3ms）
- 磨皮 = 高低频分离（103ms）
- 祛瑕疵 = 环形采样 inpaint（5ms）

**PhotoCraft 的 `Transform, warp, puppet, liquify = 55%`、`Retouching = 50%`，
说明这条路是通的，而且他们走的也是经典算法（不是模型）。**

**我们的方向被一个 68k stars 的项目印证了。**

### ✅ 用处 2：可以看它的算法实现（MIT/Apache-2.0 允许）

许可证允许我们：
- **读它的代码学实现**（`crates/` 目录下应该有图像处理 crate）
- **移植核心算法**（要保留版权声明）
- 甚至**直接引用**某些 crate（如果许可兼容）

**这解决了我们"蒙版/选区/内容识别填充具体怎么实现"的问题。**

### ✅ 用处 3：它"为 agent 设计"（`#built-for-agents`）

README 里有专门的 **「Built for agents」** 章节。
它不是只给人类用的 GUI，还考虑了 AI agent 怎么调用。

**这和我们的架构（Agent + 画布 + 能力）方向一致，值得看它怎么暴露能力给 agent。**

## 3.3 不该做的事

| 不做 | 为什么 |
| --- | --- |
| ❌ 试图把它嵌进我们产品 | Rust 桌面应用，技术栈不通 |
| ❌ 指望它替代我们的修图链路 | 它是桌面软件，我们是 Web 平台 |
| ❌ 现在就接它 | 它自己还是 alpha，PSD 都写不对 |

---

# 四、诚实的结论

## 4.1 「PS 被逆向开源」= 半真半假

| 说法 | 真假 |
| --- | --- |
| 「有个开源的 PS 重实现叫 PhotoCraft」 | ✅ **真的** |
| 「68k stars、20 天做出来、AI 写的」 | ✅ **真的** |
| 「被**逆向**了」 | ❌ **假的** —— 是净室重实现，合法的 |
| 「PS 被开源了（等于能用了）」 | ❌ **假的** —— 它是早期 alpha，45% 可用，PSD 都写不对 |

## 4.2 对我们的实际价值

| 价值 | 程度 |
| --- | --- |
| **验证我们的算法方向** | ⭐⭐⭐ 高（液化/磨皮/祛瑕疵都被印证） |
| **学它的实现细节** | ⭐⭐⭐ 高（MIT/Apache-2.0 可读可移植） |
| **直接拿来用** | ⭐ 低（Rust 桌面，技术栈不通） |
| **它的 AI 部分帮我们** | ⭐ 零（它 AI 只有 10%，我们比它强） |

## 4.3 一句话

> **它是「AI 用 20 天重写出来的 PS 早期 alpha」，不是「PS 被逆向」。
> 68k stars 说明这个方向对；但它强在传统修图，弱在 AI —— 那正是我们的地盘。
> 我们要的是它的算法细节（可读，MIT/Apache-2.0），不是它的产品形态。**

---

# 五、待核实

| 项 | 状态 | 怎么核 |
| --- | --- | --- |
| `crates/` 里图像处理模块的具体结构 | 未读 | 看 `crates/` 目录和 `docs/architecture.md` |
| 液化/修复的具体算法实现 | 未读 | 找对应 crate 的源码 |
| 「Built for agents」具体怎么做的 | 未读 | 读 README 那一节 |
| Web-native 版能不能真的在浏览器跑 | 未见 | 看 `apps/` 或它的在线版 |
| 它的 AI 那 10% 做了什么 | 未读 | 读 `docs/gaps.md#g15` |

**这些都可以后续读，不急 —— 因为我们现在不需要"用"它，只需要"印证"和"参考"。**
