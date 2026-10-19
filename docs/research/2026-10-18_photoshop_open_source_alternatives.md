# PS 平替开源项目盘点（2026-10-18）

> 场景：给 YLCraft 后期做 **COSER 工具** 和 **摄影工具** 时，能嵌进来的图层/修图底座。
> 数据来源：**GitHub API 实测**（star / 许可），非记忆。

---

## 一、先按用途分成四类

| 类别 | 用途 | 能不能嵌进我们产品 |
| --- | --- | --- |
| **A. 画布底座** | 无限画布 + 图形/图片编辑框架 | ✅ 能（注意许可） |
| **B. 网页内嵌编辑器** | 直接在浏览器里做图层/裁剪/滤镜 | ✅ 能（MIT 的可放心嵌） |
| **C. 桌面级修图** | COSER 人像精修（液化/磨皮/蒙版） | ⚠️ GPL 有传染性，不能随便嵌 |
| **D. 摄影 RAW 工作流** | 调色、镜头校正、批量 | ⚠️ 同上 |

---

## 二、逐个数据（实测）

### A. 画布底座

| 项目 | Star | 许可 | 说明 |
| --- | --- | --- | --- |
| **tldraw** | **50,961** | ⚠️ **自定义（NOASSERTION）** | **Lovart 的画布就是它**（DOM 里 `application "tldraw"`） |
| **excalidraw** | **134,049** | ✅ **MIT** | 手绘风白板，完全免费 |
| **penpot** | **61,280** | MPL-2.0 | 开源 Figma（设计稿，不是修图） |

### B. 网页内嵌编辑器

| 项目 | Star | 许可 | 说明 |
| --- | --- | --- | --- |
| **tui.image-editor** | **7,671** | ✅ **MIT** | NHN 出品，canvas 实现，功能全，长期维护 |
| **miniPaint** | **3,478** | ⚠️ **Other（未识别为标准许可）** | **最像 PS 的网页版**，topics 明确带 `layers` `photoshop` |
| **filerobot-image-editor** | **1,921** | ✅ **MIT** | Scaleflex 出品，易嵌入 |

### C. 桌面级修图

| 项目 | Star | 许可 | 说明 |
| --- | --- | --- | --- |
| **Krita** | **10,572** | ⚠️ GPL-3.0 | 绘画为主，但有修图能力和 AI 插件生态 |
| **GIMP** | 6,521（GitHub 镜像） | ⚠️ GPL/LGPL | 主库在 GitLab |
| **Pinta** | **4,097** | ✅ **MIT** | 轻量 GTK 画图，功能少但许可干净 |

### D. 摄影 RAW

| 项目 | Star | 许可 | 说明 |
| --- | --- | --- | --- |
| **darktable** | **13,289** | ⚠️ GPL-3.0 | 开源 Lightroom，RAW 工作流最全 |
| **RawTherapee** | **4,236** | ⚠️ GPL-3.0 | 老牌 RAW 处理，算法强 |

### 补充（非开源但值得知道）

| 项目 | 许可 | 说明 |
| --- | --- | --- |
| **Photopea** | ❌ 闭源（网页免费） | **最接近 PS 的网页版**，但不能嵌进产品，只能当参考 |

---

## 三、🔴 最关键的一条：许可红线

| 许可 | 能不能嵌进我们的产品 |
| --- | --- |
| ✅ **MIT**（tui / filerobot / Pinta / Excalidraw） | **可以**，只需保留版权声明 |
| ⚠️ **MPL-2.0**（penpot） | 可以，但**改了它的文件要开源那几个文件** |
| 🔴 **GPL-3.0**（Krita / GIMP / darktable / RawTherapee） | **不行** —— 会传染，嵌进闭源产品等于要求我们整体开源 |
| 🔴 **tldraw 自定义许可** | **免费版带水印**，商用去水印要付费 |

> **所以：能安全嵌进我们产品的只有这五个**
> `tui.image-editor`(MIT) / `filerobot-image-editor`(MIT) / `Pinta`(MIT) / `excalidraw`(MIT) / `penpot`(MPL-2.0)
>
> **Krita / GIMP / darktable 只能"推荐用户自己装"，不能打包进我们的产品。**

---

## 四、对我们两个场景的匹配度

### COSER 工具需要什么

| 能力 | 谁有 |
| --- | --- |
| 图层 / 蒙版 | tui.image-editor ✅ / miniPaint ✅ / Krita ✅ |
| 液化（瘦脸推脸） | Krita ✅ / GIMP ✅ / **网页版基本都没有** ❌ |
| 磨皮 / 频率分离 | Krita ✅ / GIMP ✅ / 网页版弱 |
| 素材拼贴 / 模板 | tui.image-editor ✅ / penpot ✅ |
| 批量套模板 | penpot ✅（组件/实例） |
| **AI 局部重绘** | ❌ **开源的都没有** —— 这正是 Lovart 的差异化 |

### 摄影工具需要什么

| 能力 | 谁有 |
| --- | --- |
| RAW 解码 | darktable ✅ / RawTherapee ✅（GPL，不能嵌） |
| 色彩管理（ICC） | darktable ✅ / Krita 部分 |
| 镜头校正 | darktable ✅ / RawTherapee ✅ |
| 批量导出 | darktable ✅ |
| 网页端轻量调色 | tui.image-editor ✅（滤镜级，不是 RAW 级） |

---

## 五、我的建议

### 如果要"像 Lovart 那样在画布上改图"

```
画布底座：  tldraw（Lovart 同款）⚠️ 有水印限制
       或   Excalidraw（MIT，全免费，但偏白板不是设计工具）

图片编辑：  tui.image-editor（MIT，7.6k star，最稳）
      或   miniPaint（最像 PS，但许可要自己确认）
```

### 如果要做 COSER 精修

**开源的网页版做不到液化/频率分离。**
两条路：
1. **推荐用户装 Krita**（GPL，我们不打包），我们做"文件桥接"
2. **自己做**：液化 + 磨皮 + 蒙版，用 `tui.image-editor` 当底子扩展

### 如果要做摄影 RAW

**darktable 是唯一成熟解，但 GPL 不能嵌。**
只能"引导用户用 darktable 处理 RAW，处理完再进我们的产品做 AI 环节"。

---

## 六、一个值得注意的对比

**Lovart 用的 tldraw 是"免费有水印"的商业许可。**
它能把产品做出来，是因为它**买了授权或者接受水印**。

**我们要抄它的画布形态，最省事的是 Excalidraw（MIT）**，
但 Excalidraw 偏"白板/流程图"，**不是设计稿画布**。
要设计稿形态更接近的是 **penpot（MPL-2.0）**。

---

## 七、待核实

| 项 | 状态 |
| --- | --- |
| miniPaint 的确切许可 | `未确认`（GitHub 识别为 Other，LICENSE 文件读不到） |
| PhotoDemon 的确切许可 | `未确认`（同上） |
| tldraw 免费版水印的具体限制 | `只看到"有水印"说法，没实测` |
| tui.image-editor 是否支持液化 | `未读源码确认` |
| penpot 能否当"图片设计"用（不只是 UI 稿） | `未试` |
| Photopea 是否有可嵌入的授权方案 | `未查` |

---

## 八、一句话

**能免费嵌进产品的，都不带液化；带液化的，都不能免费嵌。**

这是 COSER 工具的核心矛盾 —— **要么自己做液化，要么走"外部软件桥接"**。

而 **Lovart 真正的护城河不是画布，是"生成 + 分层 + 局部重绘"这条闭环**，
**开源的各家一个都没有。**
