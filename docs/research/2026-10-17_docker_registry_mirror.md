# Docker 镜像源问题与解法（2026-10-17）

> 起因：实测 BeefTV 时 `docker compose build` 全部失败，官方镜像一个都拉不下来。
> 本文记录根因、我试过什么、什么不管用、真正的解法。

---

## 一、根因

`docker info` 显示：

```
Registry Mirrors:
  https://zd2qonk0.mirror.aliyuncs.com/
```

这个阿里云个人镜像站**已失效**，对所有镜像返回 403：

```
unexpected status from HEAD request to
https://zd2qonk0.mirror.aliyuncs.com/v2/library/nginx/manifests/1.27-alpine?ns=docker.io: 403 Forbidden
```

配置还包含第二层 —— Docker Desktop 内置代理：

```json
"proxies": {
  "http-proxy": "http.docker.internal:3128",
  "https-proxy": "http.docker.internal:3128",
  "no-proxy": "hubproxy.docker.internal"
},
"insecure-registries": ["hubproxy.docker.internal:5555"]
```

实际运行命令（在 `docker-desktop` WSL 发行版里）：

```
dockerd --config-file /run/config/docker/daemon.json ...
```

**关键**：`/run/config/docker/daemon.json` 是 **Docker Desktop 启动时生成**的，
不是从 `~/.docker/daemon.json` 直接读取的。

---

## 二、我试过、但**不管用**的（别再浪费时间）

| 尝试 | 结果 |
| --- | --- |
| 改 `~/.docker/daemon.json` 清空 mirrors | ❌ 仍显示阿里云 |
| 改 `~/.docker/daemon.json` 换成可用镜像站 | ❌ 仍显示阿里云 |
| 改 `%APPDATA%\Docker\daemon.json`（Roaming） | ❌ 仍显示阿里云 |
| 强制杀进程 + `wsl --shutdown` + 重启 | ❌ 仍显示阿里云 |
| 全盘搜 `zd2qonk0`（ProgramData / AppData / 注册表） | ❌ **配置文件里根本没有这个字符串**，只有日志 |
| `docker desktop` CLI 找设置命令 | ❌ 只有 start/stop/restart/engine/kubernetes，**没有 settings** |

**结论**：Docker Desktop 29 把这份引擎配置存在
**WSL VM 磁盘或内部数据库**里，主机上找不到可编辑的明文文件。

---

## 三、✅ 真正可行的解法

### 方案 A（推荐，30 秒）：在 Docker Desktop GUI 里改

**Settings → Docker Engine**，把 JSON 里的 `registry-mirrors` 换成可用的：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ]
}
```

`Apply & restart` 后 `docker info` 应显示新源。

**可用的镜像站（2026-10-17 实测 `/v2/` 端点存活）**：

| 镜像站 | 探测结果 |
| --- | --- |
| `docker.m.daocloud.io` | ✅ 401（registry 活着） |
| `docker.1ms.run` | ✅ 401 |
| `hub.rat.dev` | ✅ 401 |
| `dockerproxy.com` | ✅ 200 |

### 方案 B（不改配置，已验证可用）：拉取后打本地 tag

```powershell
docker pull docker.1ms.run/library/alpine:3.22
docker tag  docker.1ms.run/library/alpine:3.22 alpine:3.22

docker pull docker.m.daocloud.io/library/nginx:1.27-alpine
docker tag  docker.m.daocloud.io/library/nginx:1.27-alpine nginx:1.27-alpine
```

**这个方案实测成功**：BeefTV 构建所需的
`alpine:3.22` / `nginx:1.27-alpine` / `oven/bun:1.3.13` / `golang:1.25-alpine`
全部靠这招拉下来，构建通过。

### 方案 C：Dockerfile 里的 `# syntax=` 指令也要绕

它同样走 `docker.io/docker/dockerfile:1.7`，会被同一堵墙挡住。
**删掉 Dockerfile 首行 `# syntax=docker/dockerfile:1.7` 即可**（多数项目不需要 heredoc）。

---

## 四、当前状态

| 项 | 状态 |
| --- | --- |
| `~/.docker/daemon.json` | ✅ 已写成可用镜像站（**但 Docker Desktop 不读它**） |
| 运行中的 daemon | ⚠️ **仍是失效的阿里云镜像源** |
| Docker Hub 直连 | ❌ 不通（`auth.docker.io` EOF） |
| 方案 B 拉取 | ✅ 可用 |

> **所以目前拉官方镜像仍需走方案 B。**
> 要彻底修好，请在 Docker Desktop GUI 里按方案 A 改一次。

---

## 五、保留的基础镜像（清理后）

为方便以后构建，这些通用基础镜像**保留**（已去掉镜像站前缀的重复 tag）：

```
alpine:3.22            golang:1.25-alpine     nginx:1.27-alpine
oven/bun:1.3.13        redis:7-alpine         busybox:latest
```

> 其余是用户自己项目原有的镜像（moneyprinterturbo / montage-ai / narratoai /
> compose-* / arcreel / n8n / mysql / pgvector 等），**未做任何改动**。
