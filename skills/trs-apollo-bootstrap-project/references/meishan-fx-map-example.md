# meishan-fx-map 已验证接入实例

本文件记录 2026-07-17 完成的一次真实接入，供下一次部署核对字段和验证顺序。ID、Pod 名、镜像 tag、时间和备份路径均为历史值，使用时必须重新发现。

## 来源与目标

| 项目 | 值 |
| --- | --- |
| 教程依据 | 《成都开发环境流水线部署新工程》 |
| 仓库 | `https://git.trscd.com.cn/cdtrs/dev/03_super_star/bigscreen/fx-map.git` |
| 本地仓库 | `/Users/zhaoqing/trs/fx-map` |
| 项目标识 | `meishan-fx-map` |
| Apollo 系统 | 云哨开发环境（`trs-police-yunshao`） |
| 构建 ref | `master`，commit `0b50064` |
| 已创建源码 tag | `dev-v0.1.0`（本次流水线仍构建 `master`） |
| 开发地址 | `https://ys.dev.trs/meishan-fx-map/` |

## 项目代码准备

项目根目录新增 `nginx.conf`：

- `/meishan-fx-map` 301 跳转到 `/meishan-fx-map/`
- `/meishan-fx-map/` 使用 `alias /meishan-fx-map/`
- history fallback 到 `/meishan-fx-map/index.html`

提交并推送：

```text
0b50064 build: 新增眉山风险地图 Nginx 部署配置
```

最终确认本地与远端 `master` 均为 `0b50064`，工作区无未提交改动。

## 流水线

| 字段 | 实际值 |
| --- | --- |
| 流水线 ID | `72` |
| `pipelineName` / `jobName` | `meishan-fx-map` |
| Jenkins | `3` |
| GitLab | `6` |
| `projectType` | `2` |
| Node | `20.15.0` |
| `gitPullMethod` | `1` |
| `gitBranch` | `master` |
| 打包命令 | `npm i -g pnpm@10.30.3 && pnpm i --frozen-lockfile && pnpm build` |
| 镜像目录 | `trs-police-yunshao` |
| 镜像名 | `meishan-fx-map` |
| `imageTagType` | `1` |
| `imagePlatformCode` | `4` |
| `dockerfileBuildMode` | `2`（内联 Dockerfile） |
| 首次构建号 | `1` |

内联 Dockerfile：

```dockerfile
FROM harbor.trscd.com.cn/baseapp/nginx:1.26.2-alpine-slim-root
ENV LANG C.UTF-8
ENV TZ Asia/Shanghai
WORKDIR /meishan-fx-map
COPY dist /meishan-fx-map
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
```

首次构建在 2026-07-17 14:42 左右完成，Jenkins 日志结果为 SUCCESS。产物：

```text
harbor.trscd.com.cn/trs-police-yunshao/meishan-fx-map:0b50064-20260717_0640
```

## 拓扑

| 字段 | 实际值 |
| --- | --- |
| `appId` | `310` |
| `appName` | `meishan-fx-map` |
| `projectName` | `meishan-fx-map` |
| `mark` | `meishan-fx-map` |
| 副本数 | `1` |
| Service | `meishan-fx-map-svc` |
| Service port | `80` |
| container port | `80` |
| Service 类型 | ClusterIP（无 NodePort） |
| Deployment YAML 记录 | `30637`，类型 `2`，版本 `1` |
| Service YAML 记录 | `30638`，类型 `3`，版本 `1` |

最终业务 Pod：

```text
meishan-fx-map-85688f5ff9-gn27f  Running  1/1
```

该 Pod 名是当时的运行实例，不可在后续操作中硬编码。实际容器镜像与首次构建产物完全一致。

## PUBLIC 共享 Nginx

历史发现结果：

| 字段 | 实际值 |
| --- | --- |
| 系统 | PUBLIC（`public`） |
| Nginx `appId` | `1` |
| 当时 Pod | `nginx-deploy-6bb4999665-95qs8` |
| 容器 | `nginx` |
| 镜像 | `harbor.trscd.com.cn/baseapp/nginx:1.26.2-alpine-slim-root` |
| 配置文件 | `/etc/nginx/conf.d/ys-dev.trs.conf` |
| 备份 | `/etc/nginx/conf.d/ys-dev.trs.conf.bak-20260717-161323` |

新增路由：

```nginx
    # 眉山风险地图
    location /meishan-fx-map {
        proxy_pass http://meishan-fx-map-svc.trs-police-yunshao/meishan-fx-map/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
```

操作证据：

- 修改前配置大小 `28503` 字节，SHA-256 前缀 `fd5acf95726a11d2`
- 修改后配置大小 `28854` 字节，SHA-256 前缀 `2ecb1e6547928c02`
- 回读后目标 `location` 数量为 `1`
- `nginx -t` 成功
- `nginx -s reload` 成功

## 最终验收

| 检查 | 结果 |
| --- | --- |
| `https://ys.dev.trs/meishan-fx-map/` | HTTP 200，HTML，标题“风险地图” |
| 原有 `/gzbigscreen/` | HTTP 200，未受影响 |
| PUBLIC Nginx Pod | Running，`1/1` |
| `meishan-fx-map` Pod | Running，`1/1` |
| 业务镜像 | 与流水线产物一致 |
| Git `master` | 本地/远端均为 `0b50064` |

`trs-apollo/state/repository-map.json` 已记录流水线 ID `72`、拓扑 `appId` `310`、构建 ref 和当前镜像。PUBLIC Nginx 是共享基础设施，没有作为业务仓库拓扑写入该映射。

## 本实例验证出的关键顺序

1. 先完成项目 Nginx 并推送代码。
2. 创建流水线，回读参数，再触发首次构建。
3. 从日志和镜像列表确认精确镜像。
4. 用户确认后创建拓扑、Deployment、Service 并部署。
5. Pod 与 Service 正常后，再单独确认修改 PUBLIC Nginx。
6. 共享配置先备份、上传后回读、`nginx -t`、平滑 reload。
7. 同时验证新地址、旧路由、两个 Pod 和 Git 状态。
