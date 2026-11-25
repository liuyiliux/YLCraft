## ADDED Requirements

### Requirement: 画布内 Agent 面板（双运行时）

画布 SHALL 提供可收起的 360px 右侧 Agent 面板，含对话/技能/历史/日志 tabs；面板 SHALL 同时支持**内置运行时**（默认，永远在线）与**外置运行时**（本地编码智能体桥接，可连接/断开），消息与审批卡 SHALL 带运行时来源标识。

#### Scenario: 打开面板
- **WHEN** 用户在画布工具带点击「Agent」
- **THEN** 右侧滑出 360px 面板，默认使用内置运行时
- **AND** 收起后画布恢复全宽

#### Scenario: 运行时来源可辨识
- **WHEN** 面板中存在来自不同运行时的消息或审批卡
- **THEN** 每条消息/审批卡标注来源（内置 / Codex 等外置智能体名）
- **AND** 顶栏显示当前连接状态

### Requirement: 内置运行时复用现有 Agent 后端

内置运行时 SHALL 复用本体 Agent 运行时（chat / runs / steps confirm / skill-candidate+skill-draft / delegate），不新建对话后端。

#### Scenario: 门禁确认
- **WHEN** 内置运行时的某个工具步骤进入 pending
- **THEN** 面板出现审批卡（执行 / 拒绝），确认走 `steps/{id}/confirm`
- **AND** 等待确认时输入框保持可用

#### Scenario: 门禁拒绝
- **WHEN** 用户拒绝一个 pending 步骤
- **THEN** 面板给出明确拒绝回执，不静默失败
- **AND** 展示因此省下的预估成本

#### Scenario: 运行痕迹
- **WHEN** 一次 run 完成
- **THEN** 过程痕迹（计划/工具/委派）折叠进最终答案，失败与待确认痕迹保持可见

#### Scenario: 委托
- **WHEN** 用户让 Agent「自己跑 / 委托」
- **THEN** 走现有 delegate 端点，支持触发时间与成本上限输入，超上限前明确提示且可撤销

### Requirement: 外置运行时（本地智能体桥接）

系统 SHALL 支持通过本地代理服务连接外置编码智能体（蓝本：canvas-oss Codex 桥）；桥接能力 SHALL 默认关闭、显式开启、token 鉴权。

#### Scenario: 连接外置智能体
- **WHEN** 用户在连接视图配置本地代理 endpoint + token 并连接
- **THEN** 面板显示连接状态，消息走外置运行时
- **AND** 断开/超时给出明确状态，可重连

#### Scenario: 外置智能体读写画布
- **WHEN** 外置智能体需要画布上下文或提交画布修改
- **THEN** 系统把画布快照（CanvasAgentSnapshot）推给代理，修改经工具结果回传进入同一 CanvasAgentOps 层
- **AND** 对画布的写操作一律先出审批卡（accept / acceptForSession / decline），未经审批不生效

#### Scenario: 打断与历史
- **WHEN** 外置智能体回合进行中用户点击打断
- **THEN** 调用 interrupt 终止当前回合
- **AND** 历史回合可确认后同步，避免重复显示

### Requirement: 画布上下文引用

面板对话 SHALL 支持把选中节点/连线作为画布引用（canvasReferences）注入消息上下文，并以引用预览卡展示。

#### Scenario: 引用画布节点
- **WHEN** 用户选中节点后在面板发起对话
- **THEN** 消息携带所选节点/连线摘要，面板显示引用预览卡
- **AND** 智能体回复可基于这些引用内容

### Requirement: 技能管理 tab

技能 tab SHALL 列出当前运行时的技能（内置走技能运行时；外置走代理 skills 接口），并支持「从当前对话/从当前画布生成技能草稿」。

#### Scenario: 生成技能草稿
- **WHEN** 用户触发技能草稿生成（来源 conversation 或 canvas）
- **THEN** 系统生成草稿并以预览呈现，**经用户确认后才落库**，绝不静默写入

#### Scenario: 草稿确认后生效
- **WHEN** 用户确认草稿
- **THEN** 内置运行时走待审批技能流程入库；外置运行时调代理 skills 创建接口
- **AND** 面板展示新技能并可查看详情

### Requirement: 对话历史按项目组织

对话历史 SHALL 按**项目**分组展示（不暴露 Session 概念），每条对话显示运行状态点与后台任务数，面板底部显示全局任务汇总。

#### Scenario: 找回某项目的对话
- **WHEN** 用户打开历史 tab
- **THEN** 对话按所属项目分组，● 表示在跑、○ 表示空闲
- **AND** 底部汇总「你在 N 个对话里有 M 个任务在跑」

### Requirement: 全双工后台任务

面板 SHALL 支持全双工：后台任务执行时前台对话与输入框保持可用，对话底部常驻后台任务条显示进行中任务及进度。

#### Scenario: 后台任务运行时继续对话
- **WHEN** 存在后台生成任务且用户继续输入
- **THEN** 输入框可用，后台任务条显示「后台 N 个任务在跑」与逐任务进度
- **AND** 任务完成在对话流中给出回执

### Requirement: Watchdog 主动提示

运行时具备任务进度事件时，面板 SHALL 主动提示疑似卡住的任务并提供处置动作，而非依赖用户翻日志。

#### Scenario: 任务长时间无进展
- **WHEN** 某后台任务超过阈值无新进展
- **THEN** 面板出现提示条（如「已 4 分钟没新进展，看起来卡住了」）
- **AND** 提供「让它去查」与「先不管」两个动作

### Requirement: 交付即接管画布

Agent 交付画布成果 SHALL 以可接管的卡片呈现（打开画布 ↗、节点/连线摘要、只读态标识），点击直接进入对应画布视图并收敛面板；不提供「复制链接自行粘贴」路径。

#### Scenario: Agent 交付一张画布
- **WHEN** 会话中 Agent 完成画布类交付
- **THEN** 消息区出现画布卡（摘要 + 「打开画布 ↗」）
- **AND** 点击后进入画布连线视图、面板收起、顶栏变为已打开态

### Requirement: 知识引用诚实呈现

Agent 回答涉及知识库/素材来源时 SHALL 带编号出处（可点开原文片段），按来源类型分色，并 SHALL 区分「材料中的内容」与「模型自述（No source）」；每次回答可查看使用了哪些来源（context chips）。

#### Scenario: 回答带出处
- **WHEN** Agent 基于知识库回答
- **THEN** 关键论断带 [n] 编号引用，点击展示来源标题、类型与片段
- **AND** 无出处的论断明确标识为模型自述，不与材料内容混淆

### Requirement: 节点级与全局级 Agent 联通

画布 SHALL 同时提供两级 Agent 入口：节点级（选中节点时工具条浮于节点上方、对话生成框浮于节点下方）与全局级（可收起的右侧智能体栏）；节点级对话 SHALL 同步到全局栏，展开可继续查看，功能不丢失。

#### Scenario: 节点级对话进全局流
- **WHEN** 用户在节点级对话框发起生成或追问
- **THEN** 该对话同时出现在全局栏消息流中
- **AND** 展开右侧栏可接着聊，节点本体不被面板遮挡
