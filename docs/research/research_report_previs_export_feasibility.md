# 3D 预演台导出能力评估：逐帧导出与视频编码

> **落地状态（2026-09-15）**：本报告的**阶段 A（批量参考帧 ZIP）与阶段 B（服务端 ffmpeg 合成）已实现**，实现与验证记录见 `openspec/changes/3d-director-previs/tasks.md` #26/#27、架构文档 §4.4.5；**阶段 C（剪辑时间线导出）未做**。本报告保留为那条路线选择的**决策依据与实测数据**，不再改动其结论。
> 触发问题：`3d-director-previs` #16「Evaluate frame capture and MP4/WebM export only after static capture is stable; document browser and cost constraints」。
> 评估范围：浏览器编码能力（MediaRecorder / WebCodecs / captureStream）、编码成本、真实负载下的视口帧率、仓内已有的导出与 ffmpeg 基础设施。
> 数据来源：本机实测（Windows / Chromium 148 / Intel UHD Graphics；另取 SwiftShader 软件渲染作为最坏情况）。测量脚本为一次性探针，结论与测量条件一并记录在下方。

---

## 一、结论先行

**1）视频导出的真正瓶颈不是"浏览器支持不支持"，而是"视口跑不跑得到 24fps"。**
能力层面全部就绪（`captureStream`、`MediaRecorder`、`VideoEncoder` 都可用，连 `video/mp4;codecs=avc1` 都支持）。但在**有真实负载**的场景上，播放时 **17% 的帧超出 24fps 预算**（p95 66.5ms，预算 41.7ms）；一旦并行编码，**35% 的帧超预算**、平均只剩 25.7fps。

**2）因此 `MediaRecorder` 实时录制不应作为主路径。**
它按**墙上时钟**打时间戳。视口既然稳定不了 24fps，录出来的就是一条时长漂移、节奏不匀的视频——而不是我们时间轴上那条确定的 24fps。**我们花了很大力气让"同一帧永远是同一姿态"（#14/#15），实时录制会把这个性质扔掉。**

**3）应走「确定性离线导出」：逐帧渲染 → 逐帧取图 → 服务端按固定帧率合成。**
离线导出可以慢，但每一帧都来自我们指定的帧号，因此输出必然是准确的 24fps。实测成本完全可接受：**96 帧（4 秒 @24fps）≈ 3.6 秒渲染+编码、约 9.4 MB**。

**4）格式要分开看：单帧截图保持 PNG，批量导出才用 JPEG。**
当前截图链路用 `toDataURL('image/png')`（`SceneViewport.tsx:501`）。实测 PNG 比 JPEG(q0.92) **慢 4.2 倍、大 14 倍**：96 帧 PNG 是 **132 MB / 6.8 秒**，JPEG 只有 **9.4 MB / 1.6 秒**。

但**这不意味着现有截图该改**：它是**单张**、要当生图/图生视频的**结构参考**（`role=storyboard_reference`），无损在这里有实际价值，而 71ms 与 1.4MB 对单张来说完全不是问题；JPEG 的有损压缩反而可能给下游 AI 引入它自己会放大的伪影。

**要改的只有批量导出**——那里是几十上百帧，体积与耗时才是决定性的。

**5）一个意外的坑：WebP 编码比 JPEG 慢 9 倍。**
WebP 体积只有 JPEG 的 44%（44KB vs 100KB），但编码耗时是 **154ms vs 17ms**。批量导出场景下"省一半体积、多花九倍时间"并不划算，**批量帧导出应选 JPEG**。（WebP 更适合"只导一张、想更小"的场合。）

**6）成本结论：这条链路零 API 额度。**
客户端编码是本地算力；服务端合成用的是仓内已有的本地 ffmpeg（`core/ffmpeg.py`）。**不产生任何模型/生图费用。** 唯一的成本是导出耗时与磁盘/带宽，而按 JPEG 计都在可接受范围内。

---

## 二、浏览器能力矩阵（真机探测）

环境：`HeadlessChrome/148.0.7778.96`。

| 能力 | 结果 |
|---|---|
| `canvas.captureStream` | **可用** |
| `MediaRecorder` | **可用** |
| `video/webm;codecs=vp9` / `vp8` / `webm` | 支持 |
| `video/mp4;codecs=avc1.42E01E` | 支持 |
| `video/mp4;codecs=avc1` / `video/mp4` | 支持 |
| `video/webm;codecs=av01` | 支持 |
| `video/x-matroska;codecs=avc1` | 支持 |
| WebCodecs `VideoEncoder` / `VideoDecoder` | **均可用** |

WebCodecs 具体配置：

| 编码 | 结果 |
|---|---|
| H.264 **baseline**（`avc1.42001f`） | **不支持** |
| H.264 main（`avc1.4d0028`） | 支持 |
| VP9（`vp09.00.10.08`） | 支持 |
| VP8（`vp8`） | 支持 |
| AV1（`av01.0.04M.08`） | 支持 |

**一处值得记下的细节**：若将来真要用 WebCodecs 编 H.264，**不能想当然选 baseline**——本次探测里它不被支持，main 才可以。这种差异只能实测得到，查文档通常会写成"H.264 支持"。

---

## 三、编码成本实测（5 次取均值）

绘制内容为渐变 + 400 个随机矩形（避免纯色让压缩率虚高）。

| 分辨率 | PNG | JPEG q0.92 | WebP q0.92 |
|---|---|---|---|
| 1440×900 | **71.1 ms / 1409 KB** | **16.9 ms / 100 KB** | 154.4 ms / 44 KB |
| 1920×1080 | **93.1 ms / 2247 KB** | **25.2 ms / 119 KB** | 248.0 ms / 48 KB |

按 96 帧（4 秒 @24fps）推算：

| 分辨率 | PNG | JPEG |
|---|---|---|
| 1440×900 | **6.8 s / 132.1 MB** | **1.6 s / 9.4 MB** |
| 1920×1080 | 8.9 s / 210.7 MB | 2.4 s / 11.2 MB |

**读法**：PNG 的 132 MB 对"一段 4 秒的预演"是不可用的——它既超过浏览器单次下载的舒适区，也会让服务端合成前先花掉几十秒在网络与磁盘上。JPEG 的 9.4 MB 则是一次普通上传的量级。

---

## 四、真实负载下的视口帧率（本条最关键）

场景构成：**Vanguard 骨骼模型（2.1 MB，156 通道动画）+ 2 个几何体 + 1 盏聚光（投影）+ 位移动画关键帧**，分辨率 1440×900，`shadows="soft"`。

| 运行环境 | 静止 | 播放（骨骼动画+插值） | 播放 + 并行 JPEG 编码 |
|---|---|---|---|
| **SwiftShader**（headless，无 GPU） | 19.0 fps | 17.2 fps | 15.4 fps |
| **Intel UHD Graphics**（真实 GPU） | **50.2 fps** | **41.0 fps** | **25.7 fps** |
| 超出 24fps 预算(41.7ms)的帧（有 GPU） | 5 / 150 | **25 / 150（17%）** | **42 / 120（35%）** |

**必须先说明测量方法上的一个坑**：首轮我在 headless 下量到 19fps 并差点据此下结论。核查渲染器后发现 headless 走的是 **SwiftShader 软件渲染**（`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device...))`），而带界面模式用真实 GPU（`ANGLE (Intel, Intel(R) UHD Graphics, D3D11)`）。**两者差 2.6 倍**，用软件渲染的数字代表用户体验是错的——所以上表把两种情况都列出，并把结论建立在真实 GPU 那一栏。

**读法**：即使有 GPU，播放时的平均值（41fps）看起来够，但 **p95 是 66.5ms、17% 的帧超过预算**——这意味着画面会周期性地"顿一下"。并行编码时更差（35% 超预算）。实时录制会把这种顿挫**固化进产出的视频**。

---

## 五、三条路线对比

| | A. 批量参考帧导出 | B. 服务端 ffmpeg 合成 | C. 浏览器实时录制（MediaRecorder） |
|---|---|---|---|
| 产出 | JPEG/PNG 序列（ZIP） | MP4 / WebM | WebM（或 Chromium 下的 MP4） |
| 帧率正确性 | 不涉及（单帧） | **由帧号决定，必然正确** | **取决于实时性能，会漂移** |
| 依赖视口帧率 | 否（离线逐帧） | 否（离线逐帧） | **是（这是致命点）** |
| 浏览器差异 | 无 | 无（服务端） | MIME/编解码跨浏览器不一致 |
| 实现成本 | 低（复用现有截图） | 中（需新增序列合成） | 低（API 简单） |
| 4 秒 @24fps 耗时 | ~1.6 s 编码 | ~1.6 s 取图 + 合成 | 录制 4 s 实时（+丢帧） |
| 体积 | 9.4 MB | 与码率相关 | 与码率相关 |
| 对用户的价值 | 可进任意剪辑软件、可做参考帧 | 可直接播放/交付 | 同 B，但质量不保证 |

**为什么 C 即使实现最简单也不选**：它的输出质量直接绑定在"渲染有多快"上，而 §4 已经说明渲染稳定不了 24fps。改成 `captureStream(0)` + `track.requestFrame()` 手动喂帧确实能控制"抓哪一帧"，但 **MediaRecorder 的时间戳仍按墙上时钟**，快速批量喂帧会得到一条时长/节奏错误的视频。要拿到正确时间轴，最终还是得回到"按帧号 + 固定帧率合成"，也就是 B。

---

## 六、推荐方案与分期

**阶段 A：批量参考帧导出（先做，风险最低）**
按帧号逐帧渲染并导出 **JPEG q0.92**，打包 ZIP。复用现有截图渲染路径（`gl.render()` + `toDataURL`），**不需要任何编码器**。仓内 `services/export/service.py` 已有 ZIP 批量导出（含分卷逻辑）可复用。产出可直接拖进剪辑软件当参考层，或喂给生图做 img2img 的结构参考。

**阶段 B：服务端 ffmpeg 合成 MP4（帧率正确性的唯一可靠解）**
客户端离线逐帧取图（JPEG）→ 上传 → 服务端 `ffmpeg -framerate 24` 合成。走**既有任务中心**做异步（4 秒预演约需数秒，不该阻塞请求）。
**需要新增**：`core/ffmpeg.py` 的 `FFmpegService` 目前有 9 个方法（`get_video_info` / `concat_videos` / `trim_video` / `add_subtitles` / `add_audio` / `add_watermark` / `resize_video` / `extract_audio` / `create_thumbnail`），**独缺"图片序列 → 视频"**；全仓也没有按 `-framerate` 读序列的先例。这是本路线唯一的新增点。

**阶段 C：导出剪辑时间线（零编码，可最后做）**
按参考项目的做法（Previs Pro 支持 FCP7 XML 直进 Premiere/Resolve），导出**镜头清单 + 时间线**而不是视频：镜头变 clip、时长来自帧数与 fps。**没有任何编码成本**，且专业用户往往更想要这个（他们要在自己的工程里继续调）。

**明确不做**：不做浏览器实时录制作为主路径（依据见 §四、§五）。若仍想提供一个"快速预览录制"，必须**同时标注它不保证帧率**，且不能与阶段 A/B 的产出混为一谈。

---

## 七、成本结论（钱与额度）

| 项 | 成本 |
|---|---|
| 客户端编码（PNG/JPEG/WebP） | **零**，本地算力 |
| 服务端合成（ffmpeg） | **零 API 额度**，本地 CPU；4 秒预演数秒量级 |
| 模型/生图费用 | **不涉及**——纯本地渲染，不调用任何收费接口 |
| 磁盘/带宽 | JPEG 方案约 9.4 MB / 4 秒（PNG 为 132 MB，不可接受） |
| 时间 | 取图 96×~20ms + 编码 96×~17ms ≈ **3.6 s**（有 GPU 时） |

**结论：这条链路不花钱。** 唯一的实际约束是导出耗时与体积，而这在 JPEG 方案下都可接受。

---

## 八、局限性（如实标注）

1. **单机单浏览器**：数据来自 Windows + Chromium 148 + Intel UHD。Safari / Firefox **未测**——保守应假设它们只保证 WebM（`video/mp4` 在 MediaRecorder 里是 Chromium 近年才支持的）。
2. **未真实录制**：只测了能力与并发编码成本，**没有实际跑一遍 MediaRecorder 产出并检查其时间戳**。"时间戳按墙上时钟"是依据 API 语义的判断，未用产出文件验证。
3. **场景规模有限**：负载测试用了 1 个骨骼模型 + 2 个几何体 + 1 盏投影灯。多角色（如 3～5 个骨骼模型）或大面积透明材质的场景会更慢，**帧率结论可能偏乐观**。
4. **帧率受硬件影响极大**：同一场景在软件渲染下只有 17fps，在集成 GPU 下 41fps。若目标用户使用无独显的设备，阶段 A/B 的"耗时 3.6 秒"会显著变长（按 SwiftShader 推算约 8～10 秒），但**离线导出变慢仍不影响正确性**——这恰恰是它比实时录制更稳的地方。
5. **96 帧推算假设成本均匀**：实际首帧含模型加载与着色器编译，会更慢；未单独测量首帧成本。

---

## 参考（代码位置）

| 位置 | 说明 |
|---|---|
| `frontend/src/pages/previs/SceneViewport.tsx:501` | 现有单帧截图：`gl.render()` 后 `toDataURL('image/png')`。**保持 PNG**——单张且要当生图结构参考，无损有价值；批量导出另走 JPEG |
| `frontend/src/pages/previs/SceneViewport.tsx` | `useFrame` 逐帧求值，是"离线逐帧导出"的天然挂点 |
| `frontend/src/pages/previs/timeline.ts` | 帧↔秒换算、`sampleFromKeys`；导出按帧号推进时会用到 |
| `backend/app/core/ffmpeg.py` | `FFmpegService`（9 个方法，**缺图片序列→视频**） |
| `backend/app/services/export/service.py` | 既有 ZIP 批量导出（含分卷），阶段 A 可复用 |
| `backend/app/api/v1/previs.py` | 现有 capture 端点（单文件 → Asset Hub → 关联分镜），阶段 A/B 需另设端点 |
| `openspec/changes/3d-director-previs/design.md` §118-124 | Phase 4 分期原文：参考帧批量导出 → MediaRecorder/WebCodecs 或 FFmpeg 评估 |
