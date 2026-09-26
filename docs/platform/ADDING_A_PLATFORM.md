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
已知历史缺口（`telegram`/`tiktok`/`twitter`/`youtube` 缺 Detector 与前端入口，
本就未支持浏览器取 Cookie）在脚本的 `KNOWN_GAPS` 里单列，**新平台不得加入**。

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
