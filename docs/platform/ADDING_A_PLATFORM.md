# 新增平台登记表（Checklist）

接入任何新平台（小红书、抖音、快手、知乎……）时，**不要凭记忆改代码**——
同一个「平台」概念在本仓库散落在多处，漏一处就会出现
**「后端早就支持了，但 UI 上根本没有入口」**或**「点『浏览器』报暂不支持」**。

这类坑在接入番茄时集中爆发过一次：业务侧 `SUPPORTED_PLATFORMS` 早已支持番茄，
但前端 `PLATFORM_METAS`、后端 `_detector_registry`、`PLATFORM_LOGIN_URLS` 三处都没同步，
于是账号中心完全看不到番茄、点浏览器还报「暂不支持 Patchright」。

## 必改清单

| # | 位置 | 漏了的后果 | 备注 |
| --- | --- | --- | --- |
| 1 | `backend/app/db/models/platform_connection.py` → `PlatformType` | 连 DB 列都建不了 | 成员名用大写，PG 存的是 **name（大写）** |
| 2 | PostgreSQL 原生枚举 `platformtype`（**需 Alembic 迁移**） | 用该平台查库报 `invalid input value for enum platformtype` | 参考迁移 `047_add_fanqie_platform_type`；**必须补大写值** |
| 3 | `backend/app/api/v1/platforms.py` → `SUPPORTED_PLATFORMS` | 平台整体不可用 | |
| 4 | `backend/app/services/cookies/base.py` → `PLATFORM_LOGIN_URLS` | Cookie 退化为登录 google.com | 必须指向该平台的**创作者后台**而非读者站（二者登录上下文不同，指错会「登录成功但没权限」） |
| 5 | 同上 → `PLATFORM_DOMAINS` | 提取不到该站 Cookie | |
| 6 | 同上 → `PLATFORM_TEST_URLS` | Cookie 健康检查无的放矢 | |
| 7 | `backend/app/services/cookies/platforms/<plat>.py` + `__init__.py` 的 `_detector_registry` | 点「浏览器」报**暂不支持 Patchright** | Detector 优先用**接口判定**登录态，比 DOM 探测抗改版 |
| 8 | `frontend/src/pages/accounts/index.tsx` → `PLATFORM_METAS` | **账号中心看不到入口**（最容易被漏、也最容易被用户发现） | |

## 自动校验

改完后必须跑：

```bash
cd backend
python scripts/check_platform_registry.py <platform>     # 只查这一个
python scripts/check_platform_registry.py                # 全量（会报历史缺口）
python scripts/check_platform_registry.py --allow-known  # 全量但放行已知缺口
```

脚本会连真实数据库读取 PG 枚举值，逐项比对上述清单，缺失即退出码 1。

### 校验分两层（2026-09-29 扩展）

| 层 | 查什么 | 漏了的典型症状 |
|----|--------|---------------|
| **登记层** | 枚举 / PG / 三张 cookie 表 / Detector / 前端入口 | 「业务可用但 UI 无入口」 |
| **能力层** | 「我的数据」下拉 / 创作者中心平台守卫 / 搜索结果带 `has_more` | 「功能看着有，但**悄无声息地不对**」 |

**能力层是这次新加的** —— 因为本轮实测的四个 bug 全部属于
「**登记齐全，但功能没接通**」，而**都不报错**：

| # | 症状 | 根因 |
|---|------|------|
| ① | X 的「我的数据」**选不到** | 前端下拉漏加（后端明明支持） |
| ② | 微博下面显示**抖音的创作者数据** | `if (isXhs) {...} else {...抖音...}` —— `else` 无条件兜底 |
| ③ | 搜索**没有「下一页」** | 后端从没设 `has_more`（X/B站/抖音/微博**全中**） |
| ④ | 下载的素材**素材库里找不到** | 建节点时漏了 `owner_user_id`（列表按 owner 过滤） |

> ⚠️ 能力层检查**要扫整个平台目录**（`platforms/<平台>/*.py`），
> 不能只扫 `search_api.py` —— 微博的搜索实现在
> `search_patchright.py`，只扫前几个文件会**误判成"没实现"**。

---

## ⚠️ 教训：**必须跑全量校验，不能只查自己改的那个平台**

2026-09-28 接入推特时，我只跑了 `check_platform_registry.py weibo`
（只校验微博），**漏掉了推特**，于是：

  · 后端做完了搜索（`services/platforms/twitter/`）
  · 但 `_detector_registry` 里**没有 `twitter`**
  · 用户在账号中心点 X → 报
    **「平台 twitter 暂不支持 Patchright 获取」**
  · 结果：功能写了，**但用户根本没法登录**，等于不可用

而且当时 `twitter` 还在脚本的 `KNOWN_GAPS`（"已知缺口，放行"）里，
`--allow-known` 会**继续放行**这个已经能修的问题，进一步掩盖。

**两条规则**：

1. 改完平台后跑**不带参数的**全量校验（不是 `<platform>` 单查）——
   单查只能证明你改的那个没问题，证明不了别的没被带坏。
2. **修好一个平台就从 `KNOWN_GAPS` 移出** ——
   它只是"历史上确实没做"的记录，不是"可以一直不做"。
   （`twitter` 修好后已移出；剩下 `telegram`/`tiktok`/`youtube` 是真的没做。）

对应的回归测试：`backend/tests/test_platform_registry_completeness.py`
（会检查"已实现搜索的平台都在 Patchright 支持列表里"、
"registry 里每个 key 都能真正加载出类"、"KNOWN_GAPS 不含已修平台"）。

已知历史缺口（`telegram`/`tiktok`/`youtube` 缺 Detector 与前端入口，
本就未支持浏览器取 Cookie）在脚本的 `KNOWN_GAPS` 里单列，**新平台不得加入**。

## ✅ `youtube`：VPN 通了之后已实现（2026-10-01 当天闭环）

上面那次探查（网络不通）之后，用户开了 VPN，**当天就把 YouTube 做完了**。
留档这次的完整过程，因为它演示了"先探网络、再动手"的价值。

**网络验证（VPN 开启后重跑同一组探针）**：

```
DNS  www.youtube.com  → 104.244.42.197（不再是 Facebook 的 IP）
HTTP https://www.youtube.com/robots.txt  → 200 OK
HTTP https://t.me/telegram               → 200 OK
127.0.0.1:10090 代理端口               → 有进程监听了
```

**实现方案：yt-dlp**（不自己逆向 innertube —— 签名/API 轮换它内部全处理了，
而且项目下载链路一直在用它）。

实测（全部 firsthand，2026-10-01）：

| 调用 | 结果 |
|------|------|
| `ytsearch5:python tutorial` | 5 条（相关度，首条 Mosh） |
| `...&sp=EgIIAQ%3D%3D` | 54 条（**最新**，首条 92 秒的新视频） |
| `...&sp=CAMSAhAB` | 479 条（**播放量**，首条 freeCodeCamp 4937 万） |
| `...&sp=EgIQAg%3D%3D` | 频道（`UC...` 24 位） |
| `/@freecodecamp/videos` | 1724 条 |
| `/download/parse` | 返回 googlevideo 720p 直链 + 封面 + 时长（下载链路直接可用） |

**三档排序首条互不相同** → 真排序，不是假选项。

**三个实测踩到的坑（都写进代码注释 + 回归测试了）**：

1. **`ytsearchdateN:` 语法不支持** —— 实测 `Unsupported url scheme:
   "ytsearchdate3"`。所以"最新"排序必须用 **`sp=` 参数的完整搜索 URL**。
2. **搜索结果会混入播放列表** —— `PL...` 开头的卡片（id 几十位、
   duration=None）不是视频，点详情打不开（这就是第一轮实测拿到 404
   的原因）。判据：**视频 ID 恰好 11 位**。
3. **频道 ID ≠ handle** —— `UC68KSmHePPePCjW4v57VPQg` 拼成
   `@UC68...` 会 **404**，必须走 `/channel/{id}/videos`。

**已知边界（如实）**：
  · 详情**不给** video 直链 —— YouTube 是分段加密流，直链几分钟失效；
    下载走 `/api/v1/download` 的 yt-dlp 链路（实测可用）。
  · 时长过滤在**客户端**做：YouTube 只认一个 `sp=`，排序与时长互斥。
  · 免登录：公开数据不需要 Cookie，所以 `users.py::SUPPORTED` 里
    youtube 带 `no_login` 标记（不要求先有连接）。

**教训**：`KNOWN_GAPS` 里的 `youtube` 我**保留**了（因为它确实没有
cookie detector）——但注释改成了"**设计如此**：免登录平台没有
'浏览器取 Cookie'这回事"，而不是"待办"。否则后人会以为漏配了。

## ⚠️ `telegram`：仍未实现（网络已通，但缺的是别的东西）

VPN 通了之后 `t.me` 也能访问了（HTTP 200），但 Telegram 有**两条**
与网络无关的约束：

  · `https://t.me/s/<channel>` 只能看**公开频道的消息列表**，
    没有关键词搜索能力。
  · **关键词搜索需要 MTProto 登录**（`telethon` + `api_id`/`api_hash`
    + 手机号验证码），是另一套东西，不是"给个 cookie 就能搜"。

**接入前必须先和用户确认走哪条路**（只能按频道采集 vs 上 MTProto），
不要自作主张。所以 `telegram` 保持未实现 + 501。

## 搜索类平台的三个额外约束

1. **登录检测必须问站点自己的接口，不能看 URL、也不能只看 CSS 类名。**
   实测教训（2026-09-26）：抖音原判据是 `if "/recommend" in page.url: return True`，
   小红书是 `if "/explore" in page.url ...`——而这两个页面**未登录也能打开**，
   会把游客误判成已登录，存下一个没有登录凭证的废连接，之后所有搜索都失败
   且极难定位。可靠判据：抖音 `/aweme/v1/web/user/profile/self/` 未登录返回
   `status_code=8`；小红书未登录会被**重定向到 `/login`**。
   **判不出来一律按"未登录"处理**，不要乐观假设。

2. **前端 `PLATFORM_SEARCH_CONFIG` 只列出后端真正实现的类型。**
   抖音搜索只实现了内容搜索（`note`），用户/直播未抓包确认，
   就不该出现在 UI 里——否则用户点了没反应，还会以为是网络问题。

3. **未抓包确认的能力要显式抛 `NotImplementedError`，不要静默返回空列表。**
   "返回空"会被上层理解成"没搜到"，属于假阴性，排查时最费时间。

4. **解析器要用真实抓包样本回归，不要只测自己编的假数据。**
   假数据只能证明代码不自相矛盾，证明不了它对**真实字段**有效。
   做法：从浏览器抓一份真实响应，剥掉 URL 里的签名参数后存到 `.local/`，
   测试读它跑解析器（`.local/` 已 gitignore）。
   范例：`backend/tests/test_douyin_real_sample.py`、`test_xhs_real_sample.py`。
   抖音那个样本立刻暴露了两个真实差异：`data` 既可能是数组也可能是
   `{"0":...}` 索引对象；时长字段是**毫秒**。

5. **搜索的 mode 要按平台选，不能一律 `api`。**
   小红书搜索端点迁移+需要签名后，`api` 模式已不可用（旧地址返回 code:300011），
   必须走 `patchright`；抖音/B站则正常走 `api`。见
   `crawler/service.py::_search_via_platforms` 里的 mode 选择。

## 数据/内容层的坑（2026-09-29 集中踩了一轮）

登记层修好只保证"能跑起来"。**内容层还有一类坑：数据本身不对，但不报错。**

### ① 类型判断要用平台给的**权威字段**，不要猜

| 平台 | 权威字段 |
|------|---------|
| 抖音 | **`aweme_type`**（`0`=视频 / `68`=图集） |
| 小红书 | **`note_card.type`**（`normal` / `video`） |
| 微博 / X | 无（看有没有视频地址） |

实测两次踩坑：

  · 抖音用 `bool(image_infos)` 猜 → 图集的图片其实在 **`images`**（`image_infos` 是空的）
    → 图集**一张图都拿不到**、还被标成 `video`
  · **`video_url` 拿"原文链接"兜底** → 所有图集都有 `video_url`
    → 前端把**图集判成视频**（渲染出 0:00 空播放器）

> **推论**：`video_url` / `images` 这类字段**宁可留空也不要兜底**。
> 兜底会让下游的"有没有值"判断全部失真。

### ② 防盗链：**每个平台方向可能相反**，要按域名判断

| 平台 | 图片 | 视频 |
|------|------|------|
| **X** | **不能带** Referer（带 403） | **不能带** |
| **抖音** | 必须带**对的**（兜底成别家 → 403） | 必须带对的 |
| **微博** | 必须带 weibo 的 | 无所谓 |
| **小红书** | 无所谓 | 无所谓 |

统一走 `proxy.py::_guess_referer` + `_NO_REFERER_HOSTS`（**按域名**），
**不要**在前端或下载器里按 `platform` 字符串写死一张表 —— 实测漏平台后
兜底成抖音，微博图片**全 403**。

### ③ 素材要带 `owner_user_id`

素材库列表**按 owner 过滤**。建节点时不写 owner → 用户
「下载了但在素材库里找不到」（记录其实在库里，只是 `owner=None`）。

⚠️ **后台任务**（`DownloadTask`）也要带 —— 请求结束后 `principal` 就没了。

### ④ 「搜索能搜到」**不等于**「登录态有效」

微博的搜索靠 **Service Worker 上下文**，**未登录也能搜**；
而「我的数据」需要登录。实测被这个误导过一整轮：
用户说"我搜索能搜到啊"，我据此以为 cookie 有效，其实
m 站 `/api/config` 返回 `login=False`。

**正确做法**：判断登录态要**问站点自己的接口**（见上文"三个额外约束"第 1 条），
不要用"别的功能能用"来推断。

---

## 两个曾经踩过的陷阱

> 实际已不止两个，下面每条都是真金白银换来的。**做小红书 / 抖音 / 任何新平台前先读一遍。**

**⓪ 判断「平台不支持某操作」前，必须穷举该操作的所有入口**

这是我踩过代价最大的一个坑（2026-09-26 更正）。

番茄：我抓了「新建章节」入口，观察到**零** author API 调用，于是记下
「番茄没有创建章节的接口，用户必须手动建章」——还围绕这个错误结论设计了妥协方案。
**事实是错误的**：「新建草稿」入口（`?enter_from=newdraft`）会真实调用
`POST /api/author/article/new_article/v0/` 并返回新分配的 `item_id`。

同一操作常常有多个入口（新建/另存/导入/草稿/模板…），它们**未必走同一条路**。
下否定结论前必须穷举；**否定结论比肯定结论更容易错**，因为它会让后续设计全部绕路。

判定标准：只有把该操作**所有**可见入口都抓过包、且都无 author API 调用时，
才能说"没有接口"。记录时写明**抓了哪些入口**，方便后来者复查。

**① 不要相信文档里的「已完成」**

`openspec/changes/fanqie-publisher` 曾白纸黑字写着
「`PlatformType.FANQIE` 已加（`platform_connection.py` + `database.py` 的 `_PG_ENUM_VALUES`）」——
**而全仓库根本没有 `_PG_ENUM_VALUES` 这个东西**，同步从未做过。
凡是涉及平台登记的勾选，都要用上面的脚本或 `rg` 验证，不要只看文档。

**② 「接口返回成功」不等于「事情做成了」**

`start_session` 曾把异常吞掉：出错时只写 `status=FAILED`，却照常 `return session_id`，
接口因此永远返回 `success: true`，浏览器压根没起来也显示成功。
验证请以**实际结果**为准（终端 `status` / `page_url` / 日志有没有报错），而不是返回值。

**③ 日志不要把异常类型丢掉**

`AcquisitionMethod.PATCHRIGHT` 根本不存在（Python 枚举只有 MANUAL/PLAYWRIGHT/QRCODE），
但日志写成 `logger.error(f"... failed: {e}")` —— 只打 `str(e)`，
输出就剩下一个孤零零的 `PATCHRIGHT`，看着极像数据库枚举问题，实际是 `AttributeError`。
排查方向被带偏了一整轮。**异常日志必须包含 `type(e).__name__`**：

```python
logger.error("... failed: %s: %s", type(e).__name__, e, exc_info=True)
```

**④ 枚举改动要 Python 与 PG 两侧一起改**

同一枚举值存在两处：Python `class XxxEnum` 和 PostgreSQL 原生枚举类型（需 Alembic 迁移）。
已发生两次：

| 枚举 | 现象 | 修 |
| --- | --- | --- |
| `PlatformType.FANQIE` | `invalid input value for enum platformtype` | 迁移 `047` |
| `AcquisitionMethod.PATCHRIGHT` | `AttributeError: PATCHRIGHT` + PG 侧缺值 | 迁移 `048` |

SQLAlchemy 对 `enum.Enum` 字段默认存 **name（大写）**，所以 PG 侧要补**大写**值。
库里那批小写值（`fanqie`/`patchright`/`manual`…）是历史遗留、未被使用——
查库时看到"小写值已存在"**不代表**对齐了。

## 相关文档

- 番茄实现范例：`docs/platform/FANQIE_GUIDE.md`
- 多平台对照：`docs/platform/MULTI_PLATFORM_REFERENCE.md`
- 浏览器获取 Cookie 的 Windows 约束（`--loop` 必填）：`docs/architecture/YLCRAFT_SYSTEM_ARCHITECTURE.md` §2
