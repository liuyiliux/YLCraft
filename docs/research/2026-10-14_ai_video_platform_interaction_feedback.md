# AI 视频/生图平台交互口碑调研（2026-10-14）

> 目的：为 YLCraft 界面重设计提供「真实用户反馈」依据，不采用媒体商单。
> 方法：浏览器实抓技术论坛一手帖（V2EX / LINUX DO / GitHub issue / Reddit）。
> **一手已核实**的条目直接引用原文；未能抓取正文的标 `[UNVERIFIED]`。

## 一、一手已核实的用户原声

### 1. V2EX《调用即梦或者 liblib 生图接口的问题》

来源：https://global.v2ex.co/t/1222675 （1129 次点击，3 条回复，已实抓全文）

- 提问者（ok168168）：「已经修复过无数次提示词，为啥还是出现各种人物角色不一致的问题？
  有时候是头发，有时候是衣服，有时候是男变女或者女变男。还有时候是对眼」
- 回复 1（oouz）：「先用 image2 或其他图片生成模型，先把人物角色的全身图片生成出来定义好。
  然后再让视频模型使用这个人物图片素材生成视频」
- 回复 2（sesshomaru0）：**「解决不了，你不能保证模型不出错」**
- 回复 3（mrsongopen1）：「我们后面做视频就打算用这种方案，先把角色模型以图片的形式做出来，
  再去生成视频，稳定性应该会大幅提高」

**结论**：跨镜一致性的行业标准解法是「先把角色固化成参考图，再喂给视频模型」，
而不是反复调提示词。V2EX 用户在**独立于任何平台之外**的情况下自发得出同一结论。

### 2. ComfyUI 官方仓库 Issue #6635
《When GUI Becomes More Complex Than Command Line》（已实抓全文）

作者 yzx-870726 的三条主论点：

1. **Unnecessary Model Splitting** —— ComfyUI 强迫用户手动分开 Text Encoder / VAE /
   Diffusion Model，而 HuggingFace 上这些是打包好的，官方示例代码也是一起加载的。
2. **No Real Use Case for Modular Approach**
3. **GUI Should Simplify, Not Complicate**

评论区最有价值的两条（真实用户反驳与补充）：

- 「ComfyUI isn't particularly meant for the average AI user. Alternate frontends are much
  better for that purpose. However ComfyUI's modularity makes it great for the
  intermediate-advanced user.」
- 「If you want to hide the modular structure and use a simplified UI, you can use **SwarmUI**.
  SwarmUI uses ComfyUI as the backend but provides a UI that **hides the node control system**,
  making it easier to use.」
- 「However, if you start wanting to go even slightly beyond simple usage, you will
  inevitably find yourself turning to ComfyUI's modular approach.」
- 另一用户：「我只想在 mac 上跑 flux.dev，和huggingface 一样，结果搜出来的结果都让我用 ComfyUI，
  只有少数提到 mflux。我花了大量时间安装……」

**结论**：这是本轮**最强的一条证据**——用户不要「模块化」，要的是「简单默认 + 可下钻」。
同时社区自己给出了答案：**用预设遮住复杂性（SwarmUI 模式），需要时再展开**。

### 3. LINUX DO《目前的 image2 生图》

来源：https://linux.do/t/topic/2438006 （19 楼，已实抓）

楼主 wanzui 的实测结论：

- 「用户的 size 以及质量要求**并非硬性指令**，codex 在收到 prompt，会**内部自行决定**
  生出的图是 high 还是 medium、low」
- 「生成的 size 也由其内部判断，不走严格的 12 倍数的比例……测试中我让其生成 16:9，
  但最终得到的比例是 1672×941」
- 结论：「size、quality 参数由模型内部判断，**无法保证严格按照指令执行**」

回复区关键分歧：

- sfm：「没有吧，今天刚出一个 4k 的图，你传参感觉不对，**去 response 了就会自动路由**」
- Triceratops2017：「佬，你咋出 4k 的？我测试过 cpa，**不理会输入的参数**」

**结论**：两个高价值信号 ——
① **「参数写了但系统不照做」是技术用户最敏感的失控感来源**；
② 「去 response 了就会自动路由」揭示了**用户看不见的内部路由**，用户只能靠试错发现它。

## 二、未能抓取的一手材料 `[UNVERIFIED]`

以下来自搜索结果标题/摘要，**未读到正文与评论区**，只能作为方向参考：

- 黑猫投诉一批积分投诉：LibTV「Agent 黑盒未明码标价扣费」、LibTV「私自把我积分清零」、
  liblib 星流「欺骗消费者」、即梦会员「付费后卡死拒不退款」。
  标题列表见 https://tousu.sina.cn/complaint/view/17400664069 等。
- App Store 即梦AI 用户评分与评论（https://apps.apple.com/cn/app/id6503676563）
- Reddit r/Runway 的 credits 讨论（实测被登录墙拦截，未读到）
- r/StableDiffusion 搜「comfyui confusing」返回的标题多为**教程/模板分享**，
  说明社区自发用「minimalistic workflows」「cheat sheet for beginners」
  来**对冲**复杂度的痛点 —— 这本身是间接证据，但非吐槽原声。

## 三、从一手材料提炼的交互原则

| # | 原则 | 证据来源 | 对 YLCraft 的含义 |
| --- | --- | --- | --- |
| 1 | **把复杂度藏起来，而不是暴露给用户** | ComfyUI #6635 + SwarmUI 提及 | 我们已有的角色库/世界地图/资产中枢，应作为**默认自动带入**的输入，而非让用户逐个挑 |
| 2 | **一致性由系统继承，不由用户手工维持** | V2EX 三条回复一致 | 角色卡 / 种子 / 参考图应自动注入每个生成请求，用户不用重复提醒 |
| 3 | **参数必须真的生效，否则就是失控** | LINUX DO 楼主 + 回复 | 任何「写了下但不起作用」的参数都要删掉或明示为建议值 |
| 4 | **内部路由要可见** | LINUX DO「去 response 了就会自动路由」 | 我们若有多供应商自动路由，需显示实际用了谁 |
| 5 | **简单默认 + 可下钻** | ComfyUI 评论区共识 | 保持现有双栏/收敛方向，但给进阶用户留展开层 |

## 四、关键提醒

- 本轮**没有**读到任何国内平台的一手界面操作体验描述（LINUX DO 那条偏生图参数，
  不是界面吐槽）。「用户夸/骂界面」这类反馈在本轮**基本没抓到**。
- Reddit 部分页面需要登录/验证码，未能完整覆盖海外平台。
- 若要补齐，最有价值的下一步是实抓 **App Store 即梦AI 差评** 和
  **黑猫投诉正文**（投诉正文通常有详细的使用过程描述）。