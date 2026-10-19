# BeefTV 深挖：Agent 工具契约 + 技能库（2026-10-17）

> 承接 `2026-10-17_beeftv_installed_verified.md`。
> 本文是**源码级**发现：Agent 的 21 个操作契约、33 个技能的实际清单与使用数据。

---

## 一、🔴 先结案：403 的真正原因（三层）

之前 UI 报 `Request failed with status code 403`，我一开始怀疑是模型端点问题。
**查完源码 + 日志，是三层叠加，而且这是设计如此，不是 bug。**

### 第 1 层：`/assistant/status` 要求 loopback

`backend/internal/handler/agent_proxy.go:141`：

```go
guardedStatus := func(c *gin.Context) {
    // 状态查询不含任何凭据，只做本机同源校验
    if !isLoopbackRequest(c.Request) {
        c.JSON(http.StatusForbidden, gin.H{"code": 403, "reason": "forbidden"})
        return
    }
```

`isLoopbackRequest`（`agent_ops.go:261`）要求 **Host / RemoteAddr / Origin 三者都是本机**。

**Docker 下不成立**：nginx 从 `172.25.0.1` 转发，后端看到的不是 loopback。
日志实证：

```
172.25.0.1 - [GET /api/assistant/status] 403 75.552µs
127.0.0.1 - [GET /api/assistant/status] 200 3.316ms   ← 我从容器内直连，通了
```

### 第 2 层：镜像里根本没有 agent-host

从容器内直连虽然过了 loopback 校验，但拿到的是：

```json
{"available": false,
 "model": {"channelName": "mytesters", "id": "deepseek-v4.1-flash"},
 "reason": "host_start_failed"}
```

**原因**：`backend/Dockerfile` 只构建了 `./cmd/server`：

```dockerfile
go build ... -o /out/infinite-canvas-backend ./cmd/server
```

而 `agent-host/` 是**独立的 Node/Bun 项目**（`.mjs` + `bun.lock`），
后端镜像只装了 `ca-certificates tzdata wget`，**没有 Node**。

### 第 3 层：官方注释说这是有意的

`docker-compose.yml` 里那句注释是答案：

> 「Do not publish 8080 on all host interfaces:
> **the server profile has no launch token.**」

**→ 结论：BeefTV 的 Agent 是桌面版（Wails）专属功能。**
**Docker / 服务端形态下 Agent 不可用，且是设计如此。**

> 这也说明：**BeefTV 面向"本地桌面创作"，不是"可自建的 Web 服务"**
> （对比 OhMyGame 也是桌面优先）。
> **这是"本地优先 vs 服务化"的一条清晰分界。**

---

## 二、🔴🔴 Agent 的 21 个操作契约（源码实读）

BeefTV 的 Agent **没有硬编码工具列表** —— 它从后端 `/ops` 注册表动态生成工具：
每个 op 变成 LLM 的一个 tool（`canvas.get` → `canvas_get`）。

### 2.1 完整清单

| # | op ID | 摘要（原文） | 关键属性 |
| --- | --- | --- | --- |
| 1 | `canvas.get` | 读取指定画布的完整内容（节点与连线） | **ReadOnly** |
| 2 | `canvas.search` | 按关键字分页搜索工作区内的画布 | ReadOnly |
| 3 | `canvas.nodes.create` | 批量创建节点（**整批校验**，带 revision CAS） | ReplaySafe |
| 4 | `canvas.node.update` | **局部**修改一个节点（只提交目标字段，其余保持原样，**带 revision CAS**） | ReplaySafe |
| 5 | `canvas.edge.create` | 连接两个节点（**重复连接幂等返回**） | ReplaySafe |
| 6 | `canvas.node.configure` | 设置媒体节点的生成草稿参数；**不生成、不扣费** | ReplaySafe |
| 7 | `canvas.node.bind_asset` | 把已上传素材绑定到参考节点；**写入真实资源与素材身份，不生成不付费** | — |
| 8 | `canvas.generation.propose` | **提议**对选中节点做付费生成（**只登记提议，不生成、不扣费**） | **ReadOnly** + AssistantProposal |
| 9 | `canvas.task.bind` | 把已交付的任务产物绑定回节点（校验归属与就绪资源，CAS，**幂等回执**） | ReplaySafe |
| 10 | `canvas.timeline.update` | 修改时间线（裁剪/顺序/音量/字幕；**仅用已关联素材**，revision CAS） | ReplaySafe |
| 11 | `canvas.timeline.render` | **免费本地渲染**已保存时间线（**不调用付费生成**） | ReplaySafe |
| 12 | `canvas.script.rows.append` | 向分镜脚本节点**批量追加**分镜行（**行 ID 与镜号由服务端分配**） | ReplaySafe |
| 13 | `canvas.script.row.update` | 按行 ID 批量局部更新（只覆盖给出的字段，**未知行整批拒绝**） | ReplaySafe |
| 14 | `canvas.script.row.remove` | 按行 ID 批量删除并**重排镜号**（未知行整批拒绝） | ReplaySafe |
| 15 | `canvas.document.commit` | 按已知 revision 提交整份文档（保留未触及字段，CAS） | ReplaySafe |
| 16 | `asset.list` / `asset.get` | 素材列表 / 详情 | — |
| 17 | `task.get` | 任务查询 | — |
| 18 | `model.catalog` | 模型目录 | — |
| 19 | `skill.catalog` | **技能目录** | — |
| 20 | `conversation.message.attach` | 把产物附加到对话消息 | — |
| 21 | `opus`/其他辅助 | — | — |

### 2.2 🔴 六条设计原则（每条都能直接抄）

| # | 原则 | 证据 |
| --- | --- | --- |
| 1 | 🔴 **成本边界写进工具描述** | 反复出现「**不生成、不扣费**」「**只登记提议**」—— Agent 从工具签名就知道"这一步不花钱" |
| 2 | 🔴 **读写分离** | `canvas.generation.propose` 是 **ReadOnly**：提议不产生副作用，真正生成要另走流程 |
| 3 | 🔴 **乐观锁（revision CAS）** | 几乎所有写操作都带 revision CAS —— 防并发覆盖 |
| 4 | 🔴 **幂等（ReplaySafe）** | 「重复连接幂等返回」「幂等回执」—— 重放安全 |
| 5 | 🔴 **批量要么全成要么全败** | 「整批校验」「**未知行整批拒绝**」—— 不留下半成品 |
| 6 | 🔴 **服务端分配 ID** | 「行 ID 与镜号**由服务端分配**」—— 避免 Agent 自己编 |

### 2.3 agent-host 的并发保护（`operation-bridge.mjs`）

```js
const REBASABLE_WRITES = new Set(['canvas.nodes.create', ...]);
// 模型在同一份旧版本上并行发出的几次写入，可以接到本轮自己的最新版本上
```

还有两个硬约束：

| 机制 | 作用 |
| --- | --- |
| `rebaseOntoWriteChain` | 并发写**重基到最新版本** |
| `turn_intent_changed` | 用户**中途改需求** → 阻止写入，要求先重读 |
| `operation_id_reused_with_different_payload` | 同一 operationId 换了载荷 → 报错 |
| `request-budget.mjs` (`spendToolStep` / `budgetError`) | **每轮工具有预算上限** |

> 💡 **「turn_intent_changed」这条最值得学**：
> 用户改主意时，Agent **不应该继续按旧意图写**，而是停下来重读。

---

## 三、🔴🔴 33 个技能库（含真实使用数据）

`backend/internal/skills/seed/skills.json`（602 KB，33 条）。

**按「使用次数」排序：**

| # | 技能名 | tag | 赞 | 使用 | 作者 |
| --- | --- | --- | --- | --- | --- |
| 1 | **叙事短片导演分镜** | drama | **469** | **2372** | 森海荧光 |
| 2 | 一图成片-电影广告全能导演 | drama | 300 | 1961 | 渊静-中意 |
| 3 | 剧本资产视频一条龙创作 | drama | 252 | 1427 | 娜乌斯嘉 |
| 4 | AI演员微表情导演 | drama | 189 | 1008 | **即梦AI** |
| 5 | 世界观美术设定 | drama | 120 | 812 | 慕影-中意 |
| 6 | 系列套图生成 | creative | 117 | 808 | 渊静-中意 |
| 7 | 角色设计 | drama | 102 | 784 | 慕影-中意 |
| 8 | 故事开发 | drama | 89 | 674 | 慕影-中意 |
| 9 | 剧本撰写 | drama | 76 | 647 | 慕影-中意 |
| 10 | 顶级波普视觉广告导演 | ecommerce | 123 | 483 | 即梦AI |
| 11 | 穿搭上身试穿视频生成 | ecommerce | 78 | 425 | 即梦AI |
| 12 | 15秒视觉特效 | creative | 58 | 346 | 猫叔 |
| 13 | TikTok网红带货视频 | ecommerce | 55 | 317 | 即梦AI |
| 14 | 珠宝电商图文视频一站式 | ecommerce | 80 | 311 | 地质大学博士说AI |
| 15 | 高能未来电子产品广告视频 | ecommerce | 72 | 300 | 即梦AI |
| 16 | 数字人搞笑采访视频生成 | social | 64 | 299 | 小文 |
| 17 | 治愈系原创IP孵化助手 | social | 61 | 290 | 即梦AI |
| 18 | 名导十五秒视频风格资产引擎 | creative | 58 | 285 | 即梦AI |
| 19 | 人像捏脸导演 | social | 39 | 269 | 即梦AI |
| 20 | 小红书素人穿搭配方 | social | 68 | 261 | 即梦AI |
| 21 | AI造型师高转化模特图 | ecommerce | 23 | 191 | 即梦AI |
| 22 | 二维动画线稿批量上色 | others | 34 | 164 | 小弹簧晓丹 |
| 23 | 角色精灵图动画产线 | creative | 45 | 162 | AIGC炼丹师 |
| 24 | OC魅力诊断师 | others | 24 | 148 | 即梦AI |
| 25 | 15秒极致夸张反转提示词 | creative | 25 | 143 | 猫叔 |
| 26 | 先锋服装商拍视觉指导 | social | 17 | 135 | 即梦AI |
| 27 | 3D国漫风转身变身特效 | creative | 38 | 133 | 即梦AI |
| 28 | 社媒素人App宣传 | ecommerce | 10 | 129 | 即梦AI |
| 29 | 三幕式短剧工厂 | drama | 10 | 123 | BOB 二黑 |
| 30 | 珠宝设计出款 | creative | 31 | 122 | 地质大学博士说AI |
| 31 | ASMR沉浸式潮玩开箱导演 | social | 47 | 120 | 即梦AI |
| 32 | 珠宝设计进化 | creative | 24 | 90 | 地质大学博士说AI |
| 33 | 绿幕猫咪跳舞素材生成 | social | 18 | 72 | 即梦AI |

### 3.1 五条洞察

| # | 洞察 | 数据 |
| --- | --- | --- |
| 1 | 🔴 **最热的是短剧/叙事类** | 前 5 名**全是 drama**，第 1 名 2372 次使用 |
| 2 | 🔴 **「即梦AI」官方在自家竞品里放了 14 个技能** | 33 个里占 14 个 —— 平台方在投内容 |
| 3 | 🔴 **技能名都是"职称"** | 导演 / 造型师 / 诊断师 / 规划师 / 引擎 —— **不是功能名** |
| 4 | 🔴 **有完整社交指标** | 赞 + 使用次数 + 作者名 + 头像 |
| 5 | **分类只有 5 个 tag** | `drama` / `creative` / `ecommerce` / `social` / `others` |

### 3.2 技能的数据结构

```jsonc
{
  "skill_id": "14811816982028",
  "skill_name": "系列套图生成",
  "description": "本技能用于将用户提供的母版提示词、参考图、产品图……",
  "instruction": "## 0. 角色定位\n我是「系列图像项目生成导演」，不是单条提示词润色器……",
  "status": 1,
  "tag": "creative",
  "sort_weight": 1000,
  "is_private": false,
  "like_count": 117,
  "added_count": 808,
  "owner_uid": "3848725071922103",
  "effective_user": { "name": "渊静-中意", "avatar_url": "…" },
  "showcase_media": "…"
}
```

> ⚠️ **`instruction` 字段是完整的 Markdown 角色设定**
> （「我是『系列图像项目生成导演』，不是单条提示词润色器」）——
> **和我们的 SKILL.md 是同一形态。**

---

## 四、对我们的意义

### 4.1 三条最该抄的

| # | 抄什么 | 为什么 |
| --- | --- | --- |
| 1 | 🔴 **工具描述里写死成本边界**（"不生成、不扣费"） | Agent 从签名就知道哪步花钱，**不用赌** |
| 2 | 🔴 **`turn_intent_changed`**：用户改主意就停写重读 | 防"按旧意图继续改" |
| 3 | 🔴 **技能带使用次数/点赞** | 我们的 13 个 skill **没有任何"哪个真有用"的信号** |

### 4.2 一个刺痛的数据

**BeefTV 最热的第 1 名技能是「叙事短片导演分镜」，2372 次使用。**
**我们主战场就是短剧。**

这说明：
- ✅ **方向对了**（短剧/叙事是刚需）
- ⚠️ **但这个赛道已经很拥挤** —— 竞品有 33 个技能在覆盖它
- 🔴 **我们的差异化必须靠"别人没有的"**：世界地图、剧情时间线、小说→世界提取

### 4.3 一个失败教训

**Docker 部署试了 1 小时，最后发现 Agent 在设计上就不支持服务端模式。**
教训：**先读部署形态说明，再决定怎么验证** —— `docker-compose.yml` 里那句
"the server profile has no launch token" 早就写了答案，我是踩完坑才看到。

---

## 五、待核实

| 项 | 状态 |
| --- | --- |
| Agent 真跑一次（搭草案） | ❌ **不可能** —— 需桌面版（Go 1.25 + Bun + GCC） |
| 33 个技能的 `instruction` 全文 | `只看了 1 条` |
| `skill_packages.go`（33.7 KB）的打包机制 | `未读` |
| 导演台节点的实际界面 | `未进` |
| 本地构建桌面版 | `未尝试`（缺 Go/Bun/GCC） |
| 我们 13 个 skill 是否有使用统计 | `待查` |