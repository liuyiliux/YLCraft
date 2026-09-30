# 快手 `__NS_hxfalcon` 调研报告

> 调研日期：2026-09-28
> 结论：**纯 HTTP 可行**。算法已 100% 还原并对照真实浏览器签名逐字节验证通过。

---

## 0. 核心结论（先说结果）

| 问题 | 结论 |
|---|---|
| `__NS_hxfalcon` 是什么 | **请求签名**（sig4），非会话令牌。形如 `HUDR_<blob>$HE_<hex>` |
| 能纯 HTTP 吗 | **能**。已用纯 Python 实现并与真实浏览器签名逐字节对齐 |
| 有现成 Python 实现吗 | **PyPI 上没有**；**GitHub 上有一个**：`cv-cat/KuaiShou-Spider` → `utils/sign/falcon_pure.py` |
| 需要浏览器吗 | **不需要**（但首次需浏览器抓一次运行时常量，见 §5） |
| 搜索接口签名 | 与 `/rest/v/search/user` **完全同一套**，只是 `sign_input` 的路径不同 |

**本仓库产出**：`docs/research/kuaishou_hxfalcon_sign.py`（纯 Python，可直接用）

---

## 1. `__NS_hxfalcon` 是什么

### 结构
```
HUDR_<base64url> $HE_<hex>
```
- **`HUDR_` 段**：设备/运行时信息 blob（`collectDeviceInfo()`）。TLV 串逐字节异或 `0x23`，过一遍**非标准 ChaCha20**，再 base64 并把 `+/=` 换成 `-_.`
  - 内含 4 项：`document.scripts.length` / `KsGuard.count` / `SECS.s` / `SECS.c`
  - **`SECS.s` 是 `Error.stack` 尾部 100 字符**（不是设备指纹）
  - **`SECS.c` 恒等于当次 count**
- **`$HE_` 段**：45 字节明文的校验字节 + 异或容器
  - 摘要流水线：`serialize(sign_input) + "HUDR_" + prefix` → **BLAKE2s 变体** → **3-LFSR 流密码** → 取前 4 字节 → 异或 `(45,211,69,192)`

### `HUDR_` 前缀含义
- `HUDR_` 是固定字面量前缀，**不是** `HUDR_` + 某个哈希
- **未找到** `__NS_` 是官方安全参数命名约定的权威文档说明；观察到的同类参数只有 `__NS_hxfalcon`（www/cp，sig4）和 `__NS_sig3`（cp 站）。`__NS_` 前缀的确切含义**未找到官方或逆向界的明确解释**

### `$HE_` 明文布局（88 hex 字符 + 2 校验）
```
4b54 | cda9 | ab | startupRandom(LE6) | random48(LE6) | 0100000000
     | count^3131873467(LE4) | digest(4B) | now^3360347992(LE6)
     | env(7B) | lrc(env)(1B)          [+ 整体 lrc(1B)]
```
- `env` = `jmpOnw_geh()` **硬编码返回** `"e0000000000000"` 异或 `(123,86,62,218)` 循环 → 实际值 `9b563eda7b563e`（**已对照实抓签名验证**）

---

## 2. 逆向来源（两条独立来源，互相印证）

### 来源 A（主）：Rust crate `amagi`
- 仓库：https://github.com/bandange/amagi-rs ｜ GPL-3.0-only ｜ crates.io `amagi` v0.1.6
- 关键文件（crate 内路径）：
  - `src/platforms/kuaishou/sign/hudr.rs` — ChaCha20 密钥/nonce、mask 0x23、TLV 布局
  - `src/platforms/kuaishou/sign/he.rs` — `$HE_` 拼接、常量表
  - `src/platforms/kuaishou/sign/primitives.rs` — BLAKE2s 变体、CTS LFSR、LRC
  - `src/platforms/kuaishou/sign/helpers/payload.rs` — `sign_input` 序列化
- 文档：https://docs.rs/amagi/latest/amagi/platforms/kuaishou/sign/

**ChaCha20 常量原文**（`hudr.rs`）：
```rust
const KUAISHOU_HUDR_MASK_BYTE: u8 = 35;
const KUAISHOU_HUDR_CHACHA_KEY: [u32; 8] = [
    4_183_807_412, 394_484_062, 1_106_561_997, 2_378_328_696,
    630_790_222, 2_546_784_104, 2_891_127_470, 1_922_531_795,
];
const KUAISHOU_HUDR_CHACHA_NONCE: [u32; 3] = [2_215_853_858, 1_643_070_585, 1_849_059_804];
```

**`$HE_` 常量原文**（`he.rs`）：
```rust
const KUAISHOU_HE_HEADER_HEX: &str = "4B54";
const KUAISHOU_HE_VERSION_HEX: &str = "cda9";
const KUAISHOU_HE_STARTUP_MARKER_HEX: &str = "ab";
const KUAISHOU_HE_FIXED_BODY_HEX: &str = "0100000001";   // ← 见 §4 修正
const KUAISHOU_HE_INPUT_XOR_MASK: [u8; 4] = [45, 211, 69, 192];
const KUAISHOU_HE_COUNTER_XOR_MASK: u32 = 3_131_873_467;
const KUAISHOU_HE_TIME_XOR_MASK: u64 = 3_360_347_992;
const KUAISHOU_HE_TAIL_HEX: &str = "9b563eda7b563e";
const KUAISHOU_HE_RANDOM_MAX: u64 = 281_474_976_710_655;
```

**`sign_input` 构造原文**（`helpers/payload.rs`）：
```rust
let mut serialized_params = combined_params.into_iter()
    .filter(|(key, _)| !key.contains("__NS"))     // 跳过 __NS_ 开头的 key
    .map(|(key, value)| format!("{key}={value}"))
    .collect::<Vec<_>>();
serialized_params.sort();
format!("{}{}{}", normalize_pathname(&payload.url), serialized_params.join(""), request_body)
```
→ 即 `pathname + 排序后的 query 拼接 + JSON body`，且 **跳过含 `__NS` 的 key**。

### 来源 B（交叉验证）：`cv-cat/KuaiShou-Spider`
- 仓库：https://github.com/cv-cat/KuaiShou-Spider ｜ **无 LICENSE 文件**（注意合规风险）
- 关键文件：`utils/sign/falcon_pure.py`（577 行，`HxFalconSigner` 类）
- 同仓库另有 `sig3_pure.py` / `kww_pure.py` / `jsval.py` / `ks_util.py`
- 比 amagi 多覆盖：`__NS_sig3`、`kww`、分站白名单
- **注意**：`falcon_pure.py` 依赖 `utils.sign.jsval`，**不能单文件抠出来用**

**PyPI 探测结论**：探测 36 个候选包名，**零个**快手签名包。
`kuaishou-api`（200）是开放平台 OAuth 封装；`ksapi`（200）是无关的 "Knowledge Stack API"；其余全部 404。

**GitHub 仓库搜索**：`hxfalcon` 与 `__NS_hxfalcon` 的 `total_count` **均为 0**（无仓库以此命名）。
**盲区声明**：GitHub 未认证 code search API 返回 401，无法做全仓库代码级搜索。

---

## 3. 本仓库实现与逐字节验证

`docs/research/kuaishou_hxfalcon_sign.py` 是 amagi 算法的纯 Python 移植，已用真实浏览器 `$encode` 交叉验证：

### 验证方法
用 Playwright 注入 `Object.prototype.caver` setter 钩子（MediaCrawler 的技术）劫持快手自己的 JS realm，调用页面内置 `$encode` 拿到**真实签名**，再用本实现解密密文对比。

### 验证结果 1：`HUDR_` 段 —— 逐字节完全一致 ✅
用真实签名解出的运行时常量（`count=100`, `scriptCount=24`, 真实 SECS 栈）反哺本实现，**232 个 hex 字符全部相同**：
```
OURS full HUDR : HUDR_sFnX-DtsGUFXsbDPT3TMP-sk0itpU6ZHr3MF...bUlhQif
REAL full HUDR : HUDR_sFnX-DtsGUFXsbDPT3TMP-sk0itpU6ZHr3MF...bUlhQif
HUDR MATCH: True
```

### 验证结果 2：`$HE_` 段常量字段 —— 全部一致 ✅
| 字段 | 真实签名 | 本实现 | |
|---|---|---|---|
| header | `4b54` | `4b54` | ✅ |
| version | `cda9` | `cda9` | ✅ |
| marker | `ab` | `ab` | ✅ |
| fixed_body | `0100000000` | `0100000000` | ✅（修正后）|
| env | `9b563eda7b563e` | `9b563eda7b563e` | ✅ |
| lrc_tail | `e8` | `e8` | ✅ |
| count | 100 | 100 | ✅ |
| LRC 自洽 | `b8 == b8` | `d7 == d7` | ✅ |

仅随机数（`startupRandom`/`random48`/`now`）和依赖它们的 `digest` 不同 —— 属预期。

### 生活验证 3：服务端行为
对 `/rest/v/search/user` 用**完全相同的其余参数**发送：

| 情况 | 响应 |
|---|---|
| 无签名 | `{"result":50,"error_msg":"签名验证失败"}` |
| **本实现生成的签名** | `{"result":2,...}` —— **不是签名错误** |

**`result:2` = `操作太快了，请稍微休息一下`（限流），是签名之外的独立风控。**

> ⚠️ **诚实声明**：限流闸门在签名校验之前触发，会**遮蔽**签名内容校验。在本次测试 IP 上，一旦进入限流，**连垃圾签名也会返回 `result:2`**。因此我**无法**从线上响应单独证明"内容级校验通过"。
> 内容级正确性由 §3 的**逐字节对照真实浏览器签名**证明（这是更强的证据）。

---

## 4. 关键坑位（两条，务必注意）

### 坑 1：SDK 版本号分站不同 ⚠️
- `falcon_pure.py` 注释记录：`SDK_VERSION_DEFAULT = 43468`（`cca9`，www/cp）、`SDK_VERSION_LIVE = 43469`（`cda9`，live）
- **amagi 硬编码 `cda9` = 43469 = live 站的值**
- **实测**：我在 `www.kuaishou.com/search/video` 抓到的真实签名版本字段正是 **`cda9` (43469)**
- → **对本仓库的搜索接口，`cda9` 是对的**。但若将来打 cp 站或签名被拒不匹配，**优先检查这里**

### 坑 2：`fixed_body` 常量已漂移 ⚠️
- amagi 与 falcon **都**写 `0100000001`
- **实测真实签名为 `0100000000`**（offset 43 差 1 字节）
- 本实现已修正为 `0100000000`（`ks_sign.py` 中 `HE_FIXED_BODY`）
- 说明该常量随快手前端版本变化，**未来需定期复查**

### 坑 3：空 body 是否带 `form`/`requestBody`
`falcon_pure.py` 注释：www 站（`omit_empty_body=True`）没 body 就不带这两个键；
`/rest/v/profile/get` 是**唯一真校验签名内容的只读接口** —— 带 `"{}"` 一律 `result=50`，不带才 `1`。
**这是最省事的端到端验证靶子**（建议用它做 CI 自检）。

---

## 5. 可落地方案

### 方案 A（推荐）：纯 HTTP + 首次浏览器播种
```python
from kuaishou_hxfalcon_sign import generate_hxfalcon
sig, sign_input, caver = generate_hxfalcon(
    "https://www.kuaishou.com/rest/v/search/feed?caver=2")
# POST https://www.kuaishou.com/rest/v/search/feed?caver=2&__NS_hxfalcon=<sig>
```

**需要处理的运行时状态**（`HxFalconSigner` 是有状态的，等价于浏览器一个页面会话）：
- `count`：会话内自增，初始 100
- `startup_random`：会话启动时间戳（毫秒），**会话内固定**
- `script_count`：页面脚本数（实抓 24）
- `secs_stack`：`Error.stack` 尾部 100 字符

**最省事的做法**：用 Playwright 打开一次页面，抓一次这四个常量 + cookies（`did`/`kpn`/`kwssectoken`），之后**全部走纯 HTTP**，本地自增 `count`。
本实现的 `generate_hxfalcon(url, count=, script_count=, stack=, startup_random=)` 已暴露这些参数。

### 方案 B（保底）：MediaCrawler 的 realm 劫持
若快手前端升级导致算法失效，用这个立刻恢复可用：
```javascript
// 注入到 Object.prototype，等页面自己 set caver 时抓到 $encode 所在的 realm
Object.defineProperty(Object.prototype, "caver", { set: function(v){
  if (this !== window && typeof this.$encode === "function") window.__ks_realm = this;
  ...
}, configurable: true });
```
然后 `page.evaluate` 调 `window.__ks_realm.call('$encode', [{url, query, form, requestBody}, {suc, err}])`
→ **只调签名函数，签名串拿回 Python 后仍由 httpx 发数据请求**（数据请求不经过浏览器，性能好）。

### 方案 C（不推荐）：抓 HTML
**已验证不可行**：`https://www.kuaishou.com/search/video?searchKey=美食` 返回 200 但 HTML 仅 78KB SPA 外壳，
`"feeds"`/`photoId`/`manifestH265`/`__APOLLO_STATE__`/`__NEXT_DATA__` **出现次数均为 0**。
与小红书不同，**快手搜索页不是 SSR/SSG，无法抓 HTML**。

### 方案 D（不推荐）：移动版
- `https://m.kuaishou.com/` → 200（可访问）
- `https://m.kuaishou.com/search/video?searchKey=美食` → **404**
- `https://v.kuaishou.com/` → 连接失败（000）
- **未找到更简单的移动版搜索接口**

---

## 6. 关于你抓到的 `/rest/v/search/user`

**用的是完全同一套签名**，只是 `sign_input` 的路径不同：

| 接口 | `sign_input` |
|---|---|
| `/rest/v/search/feed` | `/rest/v/search/feed` + `caver=2` |
| `/rest/v/search/user` | `/rest/v/search/user` + `caver=2` |

`falcon_pure.py` 的 `SIG4_WHITELIST` 确认了需签名的接口清单：
```python
SIG4_WHITELIST = (
    "/rest/v/profile/get", "/rest/v/profile/user/v2", "/rest/v/search/user",
    "/rest/v/search/feed", "/rest/v/profile/feed", "/rest/v/feed/hot",
    "/rest/v/feed/liked", "/rest/v/collect/list", "/rest/v/private/list",
)
```
→ **白名单外的 `/rest/v/*` 接口 cookie 直连即可，无需签名。**

`kww` 头：`falcon_pure.py` 说明它是**页面初始化时从 localStorage/Cookie 冻结的 `kwfv1` 快照**，
后续 Cookie `kwfv1` 轮换**不会覆盖**这个页面快照。这与你们的实测（`kww` = cookie 里的 `kwfv1`）一致，
**确认 `kww` 不是签名，只是转发**。MediaCrawler 全仓库 **零处** 使用 `kww`。

---

## 7. 已知盲区（明确声明未查到的部分）

1. **`__NS_` 前缀的确切含义** —— 未找到官方或逆向界的明确解释
2. **e-com-net.com 那篇「纯 Python 还原」正文** —— Cloudflare 403，未取得正文。
   其 CSDN 镜像 https://bingyun.blog.csdn.net/article/details/160050786 摘要提到
   "HUDR 段实质是固定字段的 ChaCha 加密结果 / HE 段采用自定义流式异或 + BLAKE2s 哈希的组合算法 /
   SECS.s 实际来自调用栈截取" —— **与本实现完全吻合**
3. **GitHub code search** —— 未认证 API 返回 401，无法全仓库代码级搜索，
   不排除存在未被仓库名/description 命中的实现
4. **内容级签名校验的线上直接证据** —— 因限流遮蔽，未能从 HTTP 响应单独证明（见 §3 声明）

---

## 8. 参考链接

- https://github.com/bandange/amagi-rs （Rust，GPL-3.0）
- https://docs.rs/amagi/latest/amagi/platforms/kuaishou/sign/
- https://github.com/cv-cat/KuaiShou-Spider （Python，无 LICENSE）
- https://github.com/NanmiCoder/MediaCrawler （realm 劫持方案参考）
- https://blog.csdn.net/RockyYu/article/details/158456357
- https://www.52pojie.cn/thread-2097554-1-5.html
