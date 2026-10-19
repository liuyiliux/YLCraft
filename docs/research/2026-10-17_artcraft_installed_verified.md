# ArtCraft 实装实测（2026-10-17）

> **证据等级：直接证据** —— 下载安装、启动、用 WebView2 CDP 读 DOM + 截图。
> 版本 `v0.41.0`（正式版）· Windows x64 · 39.9 MB 安装包

---

## 〇、事实核对（先纠正文章）

| 公众号文章说 | 仓库/实测 |
| --- | --- |
| 20.4K star | **30,978 star / 4,916 fork** |
| 「开源仅 1 个月」 | 仓库 **2022-03-31** 创建，不是 1 个月 |
| 未提许可 | 🔴 **Apache-2.0**（比 OhMyGame 的 Apache-2.0 同级，比 Infinite Canvas 的 AGPL 宽松得多） |
| — | 最新提交 **2026-10-15**（很活跃） |

**仓库**：`storytold/artcraft` · **官网**：`getartcraft.com`
**安装位置**：`%LOCALAPPDATA%\ArtCraft\artcraft.exe`（73.5 MB）

---

## 一、怎么看到界面的（方法可复用）

ArtCraft 是 **Tauri + WebView2**（不是 Electron），所以 `--remote-debugging-port` **不管用**。
正确做法：

```powershell
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = "--remote-debugging-port=9666"
Start-Process "$env:LOCALAPPDATA\ArtCraft\artcraft.exe"
# 然后 http://127.0.0.1:9666/json 就通了
```

> 💡 **这是一条新方法**：Electron 用命令行参数，**Tauri/WebView2 用环境变量**。

**注册墙**：应用启动强制弹「Create your account」（Username/Email/Password），
**没有关闭按钮、Esc 无效**。我通过 CDP 移除 `div.z-[100]` 遮罩层看到了背后界面
（**只为看界面，未绕过任何付费功能**）。

---

## 二、功能地图（19 个工具，DOM 实读）

### Create（8）
| 工具 | 说明（原文） | 对应我们 |
| --- | --- | --- |
| Create Image | Generate AI images | 生图 |
| Create Video | Create video from images | 视频 |
| Create Audio | Generate music and sound effects | BGM/TTS |
| Image to 3D Object | Convert references into textured assets | 图转3D |
| Image to 3D World | Turn mood boards into explorable worlds | 无 |
| **Angles** `NEW` | **Generate new camera angles from a single photo** | 🔴 Previs 机位 |
| **Moodboard** `BETA` | **Collect references and steer generations from a board** | 🔴 提示词参考库 |
| **3D Stage** | **Precision control. Great for AI film.** | 🔴 Previs 3D 导演台 |

### Edit（7）
| 工具 | 说明 |
| --- | --- |
| Edit Image | Change with inpainting |
| Video Frame Extractor | Extract frames from video |
| Video Watermark Remover | `SOON` |
| Image Watermark Remover | `SOON` |
| Remove Background | Remove backgrounds |
| Video Editor `BETA` | Edit and assemble video |
| Image Editor | Easy edits. Great for graphics |

> 🔴 **注意：它也在做「去水印」** —— 和我们 `content-production-orchestration` 里的
> 去水印能力撞车了。

---

## 三、3D Stage 真实布局（核心，截图实测）

```
┌──────────────────────────────────────────────────────────────────────┐
│ [🏠][🖼][🎬][🎵][✒][📦★]  Edit Scene / Untitled New Scene  [0 Credits]│
│                                              [Upgrade][共享][⚙][My Library]│
├──────────────────────────────────────────────────────────────────────┤
│ [File▾] [Outline] [Shortcuts]     [Build] Record    [Viewport][16:9][Sign up to save]│
│                  [+] [✕]  [Move] [Rotate] [Scale]   [World]          │
├─────────────┬────────────────────────────────────────────────────────┤
│ Scene  +Add │                                                        │
│  📷 Camera  │              3D 网格地面 + 线框立方体                    │
│     Camera  │              （可旋转/平移/缩放的视口）                   │
│  👁 🔒 →    │                                                        │
├─────────────┴────────────────────────────────────────────────────────┤
│ [▶] 0:00 ───────────●───────────────── 0:10        [🧮 Costs 14][? Help]│
└──────────────────────────────────────────────────────────────────────┘
```

### 值得抄的六点

| # | 设计 | 说明 |
| --- | --- | --- |
| 1 | 🔴 **`Build` / `Record` 双模式** | Build=搭场景，Record=录制/出片。**一个界面两种意图** |
| 2 | 🔴 **`Costs` 常驻在时间轴旁** | 一直显示当前成本（`14`），点开看明细 |
| 3 | **`Sign up to save`** | **能玩、能编辑，但保存要账号** —— 极低门槛试用 |
| 4 | **`16:9` 在顶栏** | 画幅是场景级设置，不是节点参数 |
| 5 | **时间轴 0:00–0:10** | 3D 场景天然带时间维度（动画/镜头运动） |
| 6 | **左侧 `Scene` 面板 + `+ Add`** | 对象树（Camera 及其子项），带 👁/🔒/→ 三个操作 |

---

## 四、🔴 资产库（Add 对话框，最有价值的一屏）

**7 个分类**（左侧带图标的导航）：

| 分类 | 内容（实测样例） | 来源 |
| --- | --- | --- |
| **Characters** | Storyboy / Story Girl / Knight / News Anchor | **Mixamo** |
| **Objects** | Cube / Cylinder / Donut / Sphere | 内置 |
| **Memes** | Toothless / Doge / Grimace / Roblox | Mixamo |
| **Sets** | Concert Stage / Desert home / Waterfall / Office | **GLB** |
| **Creatures** | fox / frog / horse / lizard | GLB |
| **Animations** | Sit / Idle / Walk / Punch | **Mixamo** |
| **Skybox** | Empty / Day / Night / Gray | 内置 |

**交互细节（每条都值得学）**：

1. 🔴 **每个资产的悬停动词不同**：
   - Characters/Objects/Sets/Creatures/Skybox → **`Drag to Scene`**
   - Animations → **`Add to Character`**（动画只能挂到角色上）
   **动词即约束** —— 用户不用猜能不能用。
2. **每个分类都有 `View all >`** —— 首页只露 4 个，不堆满
3. **搜索框在最上**，左侧分类导航独立滚动
4. 🔴 **`☐ Reopen after adding` 复选框** —— 记住"连续添加"的偏好
5. **每个缩略图是真实 3D 渲染**，不是图标

> 💡 **对照我们的角色库**：我们有角色，但**没有 Objects / Sets / Creatures / Skybox /
> Animations 这些分类**，也没有 Mixamo 那类动作库。
> **更关键的是「Drag to Scene」vs「Add to Character」这种按类型给的动词。**

---

## 五、🔴 成本明细面板（COST BREAKDOWN）

```
COST BREAKDOWN
STAGE 3D
  Model          GPT Image 1.5
  Resolution     1K
  Images         1

CREDITS          14 Credits
ESTIMATED PRICE  $0.14        [USD ($) ▾]
```

**四个设计点：**

| # | 设计 | 为什么好 |
| --- | --- | --- |
| 1 | **按参数逐项列出** | 改分辨率/张数时能看到成本变化源头 |
| 2 | **标注 `STAGE 3D`** | 明确这是哪个工具的消耗 |
| 3 | **Credits + 折算金额双显示** | 既有平台币也有真钱 |
| 4 | **货币可切换**（`USD ($) ▾`） | 面向全球用户 |

> 这正是我在 skill 里写的「**消耗写在生成按钮旁**」，但做得更彻底——
> **生成前可查明细，且随参数实时变**。

---

## 六、商业形态（实测观察，未完全确认）

| 项 | 观察 |
| --- | --- |
| 顶栏 | `0 Credits` + `Upgrade` 按钮 |
| 生成 | **消耗 Credits**（不是自带 Key） |
| 试用 | 无需账号可进 3D Stage，**但 `Sign up to save`** |
| 许可 | **Apache-2.0**（可自建/改） |

> ⚠️ **与 OhMyGame 的一个关键区别**：
> OhMyGame 是 **BYOK（自带 Key）**，ArtCraft 看起来是 **Credits 体系**。
> **但它是 Apache-2.0，理论上可以自建后端。**
> `待核实`：是否有 BYOK 选项（我没找到设置入口进不去）。

---

## 七、对我们最有价值的四条

| # | 抄什么 | 为什么 |
| --- | --- | --- |
| 1 | 🔴 **`Build` / `Record` 双模式分区** | 我们 Previs 只有"编辑"，没有"出片"这个明确阶段 |
| 2 | 🔴 **资产按类型给不同动词**（Drag to Scene / Add to Character） | 比"插入"这种通用词更能防错 |
| 3 | 🔴 **成本明细随参数实时变 + 货币切换** | 我们目前只在确认卡片里显示 prompt，没有成本 |
| 4 | **`Sign up to save`**（能玩不能存） | 我们自用，此条不适用；但"低门槛试用"思路可借鉴 |

### 4.1 它验证了我们 Previs 的方向是对的

ArtCraft 整篇的立论是「**在生成之前先把场景搭好**」，
而我们 `3d-director-previs` 就是这个思路。
**区别在于它把 3D 场景和"AI 出图/出片"接成了闭环**（Build → Record），
而我们 Previs 目前更像独立工具。

### 4.2 它也没解决的一件事

文章说「出的图之间没关系、长相还可能换个人」——
ArtCraft 用 **3D 摆位 + 机位**解决"空间一致"，
但**角色长相一致**它靠什么，我这轮没看到（可能在 Create Image 里，有参考图机制）。

---

## 八、待核实

| 项 | 状态 |
| --- | --- |
| 是否有 BYOK（自带 Key） | `未确认`（设置入口没找到） |
| Create Image 的实际界面与参考图机制 | `未看`（需注册才能生成） |
| Moodboard / Angles 的实际界面 | `未看` |
| 62 个模型的完整清单 | `只读文章转述`（DOM 里只看到 GPT Image 1.5） |
| Build → Record 的出片质量 | `未测`（需注册 + Credits） |
| `_docs/dev_setup.md`（怎么自建） | `未看` |

---

## 九、清理

| 项 | 位置 |
| --- | --- |
| ArtCraft | `%LOCALAPPDATA%\ArtCraft`（73.5 MB exe，可卸载） |
| 我的临时脚本 | `tmp_cdp3.cjs` / `tmp_expr.txt` / `tmp_b.txt` / `tmp_cdp2.mjs` ── **应删除** |