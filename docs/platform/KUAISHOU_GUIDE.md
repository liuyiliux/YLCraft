# 快手（Kuaishou）接入指南

> 本文是**快手取数的当前事实来源**。
> 排查"取不到数"时**先读第二节的签名机制**——绝大多数问题都出在那里。
> 历史踩坑与已证伪的结论见「六、已证伪的结论（勿重新启用）」，
> 那几条的代价都很高，别再走回头路。

最后更新：2026-10-11（功能全部打通，含获赞）

---

## 一、能力现状

| 功能 | 状态 | 数据来源 |
| --- | --- | --- |
| 搜索作品 | ✅ | `POST /rest/v/search/feed` |
| 搜索博主 | ✅ | `POST /rest/v/search/user` |
| 博主详情（昵称/头像/简介） | ✅ | `profile/user` |
| 粉丝 / 关注 / 作品数 | ✅ **精确值** | `profile/user` 的 `ownerCount` |
| **获赞** | ✅ | `profile/user` 的 `ownerCount.like` |
| 作品列表 | ✅ 20 条/页 | `POST /rest/v/profile/feed` |
| 评论 | ✅ | （见评论统一入口） |

实测样例（uid=`3xep6p7wbnqcvj6`，「沈阳」）：
粉丝 12544 / 关注 8 / 作品 176 / 获赞 55169，与快手页面显示一致。

---

## 二、签名机制（`__NS_hxfalcon`）—— **最关键**

### 2.1 签名怎么来的

快手的所有 `/rest/v/*` 接口都要带 `__NS_hxfalcon=…` 查询参数。
**它无法用纯 HTTP 伪造**（由前端 JS 按设备指纹实时生成）。

⇒ 唯一办法：**用真实浏览器打开页面，抓它自己发出的带签名请求**。
实现见 `backend/app/services/platforms/kuaishou/client.py` 的
`_ensure_signed_url()`：监听 `page.on("request")`，按路径收集并缓存。

### 2.2 ⚠️ 签名是**会话级**的，不是"绑死某个路径"

早期注释写着"签名绑路径 —— 用 A 的签名调 B 会 `result:2`"。
**这条至少不适用于 `profile/user`**（见下节）。

### 2.3 ⚠️ `profile/user` 必须**借签名**

**`profile/user` 这个路径，快手页面从来不发**（实测四个页面都没有它）：

```
抓到 4 个路径的签名：/rest/v/profile/feed, /rest/v/profile/get,
                    /rest/v/search/feed, /rest/v/search/user
抓到签名但 /rest/v/profile/user 不在其中
```

⇒ 它永远抓不到"自己的"签名。
解法：**拿 `profile/get` 的签名、只换 URL 路径**（保留 `__NS_hxfalcon` 串）。
实现见 `_post_profile_user()`。这是唯一能拿到**精确粉丝数 + 获赞**的路径。

### 2.4 哪些页面会发哪些请求（实测）

| 打开 | 会发出 |
| --- | --- |
| `/search/video?searchKey=…` | `search/feed`、`search/user`、`profile/get` |
| `/profile/{uid}` | `profile/feed`、`profile/get` |

所以 `_pages_for()` 要**返回多个候选页面**，凑齐不同路径的签名。

---

## 三、`profile/user` 的响应结构 —— ⚠️ 层级易错

```json
{"result":1,"userProfile":{
    "profile":   {"user_name":"沈阳","headurl":"…","user_text":"…",
                  "user_id":"3xep6p7wbnqcvj6"},
    "ownerCount":{"fan":12548,"like":55165,"follow":8,"photo_public":176},
    "userDefineId":"1578058299","isFollowing":false,"gender":"M", …}}
```

两个**极易踩错**的点（都实际犯过，线上表现为"全 None"和"数据被丢弃"）：

1. **`ownerCount` 是 `profile` 的兄弟节点，在 `userProfile` 这一层，
   不在 `profile` 里面。** 写成 `up["profile"]["ownerCount"]` 必然取不到。
2. **两个 id 不是一回事**：
   - `userProfile.profile.user_id` = `3xep6p7wbnqcvj6` ← **等于请求的 uid**
   - `userProfile.userDefineId` = `1578058299` ← 「快手号」，**另一个**

   校验必须用 `profile.user_id`。用 `userDefineId` 会导致"数据拿到了却被
   自己的防冒充校验扔掉"。

### 字段对照

| 含义 | 取值 |
| --- | --- |
| 昵称 / 头像 / 简介 | `profile.user_name` / `headurl` / `user_text` |
| 粉丝 | `ownerCount.fan` |
| 关注 | `ownerCount.follow` |
| 作品 | `ownerCount.photo_public` |
| **获赞** | `ownerCount.like` |

⚠️ `ownerCount.photo` 实测返回 `null`，**别用它当作品数**。

---

## 四、三个资料接口的对比（都实测过）

| 接口 | 能抓到签名 | 返回谁 | 备注 |
| --- | --- | --- | --- |
| `profile/get` | ✅ | **登录账号自己** | 即使带 `?userId=<目标>` 也一样（实测确认） |
| `profile/user` | ❌ 页面不发 | **目标用户** ✅ | 需**借** `profile/get` 的签名 |
| GraphQL `visionProfile` | 免签名 | 目标用户 | 数字**四舍五入**（`"1.3万"`），且**无获赞** |

⇒ **主路径是"借签名调 `profile/user`"**，GraphQL 只作兜底。

### GraphQL 兜底的两个已知缺陷

- `ownerCount` 给的是**展示字符串** `{"fan":"1.3万"}` → 解析成 13000，
  真实 12544（差约 450）。**不是精确值。**
- **没有 `like` 字段** ⇒ 获赞取不到。
- 作品数要用 `photo_public`（`photo` 恒为 `null`）。

---

## 五、并发坑：`Execution context was destroyed`

抓签名会 `page.goto()`，而**另一次导航会把正在执行的 `evaluate` 上下文销毁**：

```
Page.evaluate: Execution context was destroyed, most likely because of a navigation.
```

⇒ `_post()` 里加了**重试**（识别该错误 → 等 `domcontentloaded` → 退避重发，共 3 次）。
线上验证：重试后 `作品 -> 20 条` 正常返回。

---

## 六、已证伪的结论（勿重新启用）

这几条都被写进过代码注释，**代价是绕了几天**：

| 结论 | 为什么错 |
| --- | --- |
| "未登录时页面不发带签名请求" | 实测未登录照发，`search/user` 返回 `result:1`。**用户从未登录的浏览器也能搜人。** |
| "数字来自加密接口 `/s/w/c`，取不到" | 走 `profile/user` 就能拿到 |
| "`INIT_STATE` 里有明文数据" | 那是**搜索页缓存残留**：SSR HTML 里 8 个关键词全 0 命中，该页从未发出资料请求；且数值会漂移 |
| "快手把无头浏览器挡了" | **未复现**（先测出失败、后测出成功，自相矛盾）。默认值已改回无头，不要据此弹窗 |
| "`profile/get` 带 `?userId=` 能查别人" | 实测仍返回登录账号自己（2695872552） |
| "响应有嵌套/扁平两种形状" | 误判。真实原因只是**取错层级**，只有单一结构 |

### ⚠️ 方法论教训（比上面任何一条都重要）

**"接口能返回数据" ≠ "我们能调它"** —— 前提是**拿得到它的签名**。
`profile/user` 就是典型：它确实能返回目标用户的完整资料，
但页面不发这个路径，所以我们一度以为"快手不提供这些数字"。

另一条：**遇到"取不到"，做对照实验（一次只改一个变量），不要猜**。
上面 6 条里有 4 条是"听起来合理"的推断，一次对照都没做。

---

## 七、登录态

- `kwscode` / `kwssectoken` TTL 约 **6 分钟**（服务端控制，无法延长）
- 失效后**签名抓不到**，功能不可用 ⇒ 需到「账号中心」重新扫码
- ⚠️ 这**不代表快手要求登录**（资料/搜索数据对游客开放），
  是我们取签名的方式依赖登录态

---

## 八、相关文件

| 文件 | 作用 |
| --- | --- |
| `backend/app/services/platforms/kuaishou/client.py` | 客户端主体（签名抓取 / 借签名 / GraphQL 兜底） |
| `backend/app/services/platforms/kuaishou/apis.py` | 端点常量与响应解析 |
| `backend/tests/test_kuaishou_graphql_contract.py` | 契约测试（钉住接口与字段） |
| `backend/tests/test_kuaishou_profile_user_shape.py` | 响应层级与 id 校验（防上面两个坑复发） |
| `backend/tests/test_kuaishou_cn_count.py` | 中文数量解析（`"1.3万"`） |

### 排查顺序（建议）

1. 看日志里 `抓到 N 个路径的签名：[…]` —— 若为空，先查浏览器/登录态
2. 若 `profile/user` 不在列表里 → 正常，走借签名
3. 若四个值仍是 `None` → 查第三节的两个层级/id 陷阱
4. 若报 `Execution context was destroyed` → 并发，已有重试

---

## 九、外部参考

另一工作区的独立调查报告（含完整抓包与原始响应）：
`F:\workspace\简单脚本\调查报告2.md`、`ks_profile_user.json`、
`e_profileuser.js`（借签名的做法就出自这里）。

⚠️ 该报告有**两处已被本项目证伪**：它说"资料接口是 `/profile/get`"
（错，那只能查自己）、"只有游客态有 `INIT_STATE`"（实测登录态也有）。
以本文为准。
