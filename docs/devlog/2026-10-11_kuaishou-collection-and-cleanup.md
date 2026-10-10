# 2026-10-11 快手采集打通 + 仓库清理

## 项目目标

修复快手（Kuaishou）"看着实现了、实际取不到数"的问题：
搜索博主 / 搜索作品 / 博主详情 / 作品列表，以及**精确粉丝数与获赞**。

## 已改文件

**后端**
- `backend/app/services/platforms/kuaishou/client.py`
  - 新增 `_post_profile_user()`：`profile/user` + **借用 `profile/get` 的签名**（只换 URL 路径，保留 `__NS_hxfalcon`）
  - `_pages_for(uid)` 改为返回**多个候选页面**（主页 + 搜索页），凑齐不同路径的签名
  - `_post()` 支持 `extra_query`；新增**重试**（修复 `Execution context was destroyed`）
  - `headless` 改为可配置（默认无头，`YLCRAFT_KS_HEADLESS=0` 可切有头）
- `backend/app/services/platforms/kuaishou/apis.py`：新增 `PROFILE_USER`、`build_profile_user_body()`、`_parse_cn_count()`（解析 `"1.3万"`）

**前端**
- `frontend/src/pages/platform-users/index.tsx`：统计卡改为**逐项显示**（0 与"取不到"区分）；删掉硬编码的快手获赞 `null`
- `frontend/src/pages/crawler/index.tsx`：内容搜索**去掉快手「用户」tab**（用户搜索归「博主中心」，避免重复入口）

**文档**
- 新增 `docs/platform/KUAISHOU_GUIDE.md`（当前事实来源）
- `docs/README.md`：平台清单 + 「当前主线状态」更新

**测试**
- `test_kuaishou_graphql_contract.py`（重写）、`test_kuaishou_profile_user_shape.py`（新增）、`test_kuaishou_cn_count.py`（新增）

## 当前进度

**已完成**。界面实测确认：粉丝 1.3万（12544）、关注 8、作品 176、**获赞 5.5万**（55169）、作品列表 20 条。

## 验证结果

后端 `pytest -k "kuaishou or users or frontend_platform"` → **138 passed**；
`tsc` exit=0，`vite build` 成功。功能由用户在浏览器确认。

## 三个最贵的坑（都实际犯过）

1. **`ownerCount` 取错层级** —— 它是 `profile` 的**兄弟**，挂在 `userProfile` 下，不在 `profile` 里。写成 `up["profile"]["ownerCount"]` 必然全 `None`。
2. **两个 id 搞混** —— `profile.user_id`（=`3xep…`，等于请求的 uid）vs `userDefineId`（=`1578058299`，快手号）。校验用错会导致**数据拿到了却被防冒充逻辑扔掉**。
3. **硬编码 null** —— 前一轮以为"快手无获赞"，写了 `platform === 'kuaishou' ? null : …`，把后来拿到的真值藏了。

## 关键决策

- **`profile/user` 靠借签名**：该路径页面从不请求 ⇒ 永远抓不到自己的签名。借 `profile/get` 的签名、只换路径，实测可行。
  ⚠️ 这推翻了原注释"签名绑路径（跨路径必 `result:2`）"——该规则**至少不适用于 `profile/user`**。
- **GraphQL 只作兜底**：它的数字是四舍五入的展示值（`"1.3万"` → 13000，真实 12544），且**无 `like` 字段**。
- **不追求无头**：曾据一次未复现的实验判定"快手挡无头"并改默认值，随后自测推翻 ⇒ 改回无头默认，不凭未证实结论弹用户窗口。

## 方法论（建议下一位 AI 先读）

> **"接口能返回数据" ≠ "我们能调它"** —— 前提是**拿得到它的签名**。
> 遇到"取不到"：**做对照实验（一次只改一个变量），不要猜**。
>
> 本轮 6 条错误结论里有 4 条是"听起来合理"的推断，一次对照都没做：
> 未登录不发签名 / 数字在加密接口 / INIT_STATE 是明文 / 无头被挡。
>
> 另：**子智能体调查比自己带着历史结论查更有效** —— 它没有先验包袱。

## 待办任务

无阻塞项。可选后续：用同样思路审计其他平台的"取不到"问题。

## 报错细节

- `Page.evaluate: Execution context was destroyed…` → 抓签名 `goto` 与并发 `evaluate` 冲突，已加重试（3 次，退避）
- `'KuaishouClient' object has no attribute '_fix_bili_url'` → 误用 B站客户端方法，已改为直接用 `headurl`
- `抓到签名但 /rest/v/profile/user 不在其中` → 该路径页面不发，属**预期**，走借签名

## 下一步建议

1. 如需继续，优先审计其他平台是否也有"看着取不到、实为取数方式问题"的情况
2. 4 个活动 OpenSpec 任务（见下）均与我这轮无关，且都被外部条件阻塞

## 顺带的仓库清理

- 删除 4 个 `git commit -F` 遗留的提交信息文件（`_cm_*.txt`，内容已在 git log）
- 删除 `esbuild_story.err`、`tmp/`（未跟踪的本地产物）
- `check_mobile.py` → `tools/check_mobile.py`，补"怎么跑"说明（需 `_mob_cred.txt` + 前后端在跑）
- `.gitignore` 补 `_m*.txt` / `_mob_cred.txt` / `_mobile_shots/`
- 删除误提交的 `_m47.txt`（我上次用 `git add -A` 带进去的）
- ⚠️ 保留 `_mobile_shots/`（未跟踪截图）与 `check_mobile.py`（唯一移动端回归工具）
