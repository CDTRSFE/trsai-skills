# Apollo 流水线与拓扑工作流

本流程仅通过命令行和已确认的 Apollo API 执行，不调用浏览器或操作页面。认证失败按 `trs-apollo` 的 API 登录与失败处理规则执行；接口契约缺失时报告缺口并暂停相关步骤，不使用页面登录、抓包或表单兜底。

## 目录

1. 仓库与系统发现
2. 流水线创建
3. 首次构建
4. 拓扑应用与资源
5. 部署和验证
6. 仓库映射
7. 常见错误

## 1. 仓库与系统发现

先执行只读检查：

```bash
git rev-parse --show-toplevel
git remote get-url origin
git status --short --branch
git log -1 --oneline
```

检查 `package.json`、锁文件、构建配置、`nginx.conf`、Dockerfile 和构建产物目录。用 `rg` 定位 Vite `base`、部署路径和现有项目名，避免复制参考项目的旧名称。

随后按 `trs-apollo` 完成：

1. 验证登录缓存。
2. 查询系统列表并选择用户确认的系统。
3. 读取 `state/repository-map.json`；仅使用当前系统节点。
4. 搜索同名流水线、同名拓扑和镜像仓库。
5. 若用户给出参考项目，读取其完整流水线配置，但重新发现连接 ID、命名空间和目标名称。

形成部署摘要前，核对本次需要的流水线、拓扑、Deployment 和 Service 创建接口：请求方法、路径、必填字段及回读方式。API 参考未覆盖时，只从已验证的请求记录或用户提供的接口资料补充；仍无法确认时，报告缺失信息并暂停依赖步骤。

写操作前输出部署摘要并等待确认。创建新工程时不能仅凭仓库目录名推断最终项目名。

## 2. 流水线创建

### 2.1 确认 Git ref

使用 `/devops/platform/gitlab/getBranchOrTag` 确认 ref 存在：

- 分支：`gitPullMethod=1`，`gitBranch=<branch>`
- 已有 tag：`gitPullMethod=2`，`gitBranch=<bare-tag>`
- 新 tag 触发：`gitPullMethod=3`，另配 trigger 字段

不要把 `refs/tags/<tag>` 保存为分支。

### 2.2 确认构建字段

从仓库和参考流水线确认以下字段：

| 字段 | 规则 |
| --- | --- |
| `pipelineName` / `jobName` | 使用用户确认的项目标识 |
| `jenkinsId` / `gitlabId` | 从当前 Apollo 环境发现，不跨系统照抄 |
| `projectType` | 前端项目通常为 `2`，以参考流水线为准 |
| `nodejs` | 使用 Apollo 已安装且符合项目约束的版本 |
| `gitUrl` | 当前仓库规范化远端地址 |
| `gitPullMethod` / `gitBranch` | 作为原子配置 |
| `packCommand` | 固定包管理器版本，优先 frozen lockfile |
| `imageDir` | 当前系统镜像命名空间 |
| `imageName` | 用户确认的镜像名 |
| `imageTagType` | 以参考流水线策略为准 |
| `dockerfileBuildMode` | 本地 Dockerfile 或内联内容必须明确 |
| `dockerfileLocal` / `dockerfileContent` | 与构建模式配套，不同时填写猜测值 |

前端 Nginx 镜像的内联 Dockerfile 可采用以下结构，所有路径替换为当前项目：

```dockerfile
FROM harbor.trscd.com.cn/baseapp/nginx:1.26.2-alpine-slim-root
ENV LANG C.UTF-8
ENV TZ Asia/Shanghai
WORKDIR /<project-name>
COPY dist /<project-name>
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
```

### 2.3 保存和回读

使用 `POST /devops/pipeline/save`：

- 新建流水线时不带旧项目 `id`。
- 基于参考流水线构造完整表单 payload，只替换必要字段。
- 不提交只包含几个字段的部分 payload。

保存后重新查询流水线列表和 `getOne`，核对：

- 新 ID、`pipelineName`、`jobName`
- Git URL、ref 类型和值
- Node、打包命令
- 镜像目录、镜像名、tag 策略
- Dockerfile 模式和内容

如果无法确认当前 Apollo 的新建接口契约或完整 payload，暂停保存，报告已确认字段与缺失信息；取得可验证的接口资料后，再通过 API 保存和回读，不切换到页面填写。

## 3. 首次构建

触发构建属于写操作。用户确认后调用：

```text
GET /devops/pipeline/start?jobName=<job>&namespace=<namespace>&jenkinsId=<jenkinsId>
```

轮询 `/devops/pipeline/log`，检查完整构建阶段：

1. checkout 到正确 commit/ref
2. 安装依赖
3. 构建产物成功
4. Docker 构建成功
5. 镜像 push 成功
6. 日志结束于 `Finished: SUCCESS`

流水线 `getOne` 的 `jobState`、`buildNumber`、`lastBuildTime` 可能滞后。构建结束后查询：

```text
GET /devops/basicEnvConf/1.0/application/queryAppImages?appId=<appId>
```

若拓扑尚未创建，可从构建日志的 push 结果得到完整镜像，再在拓扑创建后用应用镜像列表交叉确认。不要用字符串猜 tag。

构建成功后向用户汇报完整镜像并单独询问是否部署。

## 4. 拓扑应用与资源

### 4.1 发现和创建应用

先查询 `/devops/app/list`，排除同名应用。确认：

- `appName`：稳定部署标识
- `projectName`：拓扑展示名
- `mark`：项目标识
- 镜像仓库/应用类型
- 所属系统和命名空间

创建拓扑属于写操作，必须通过已确认的 API 和完整 payload 执行。若 API 参考、已验证的请求记录或用户提供的接口资料仍不足以确认创建契约，报告已确认字段及缺失的方法、路径、字段或回读方式，暂停创建和依赖它的部署步骤。取得可验证的契约后再创建，并通过 API 回读；不猜接口名、不提交不完整 payload，也不使用浏览器或页面抓包补齐契约。

### 4.2 Deployment

创建或配置 Deployment 时至少确认：

- 名称：通常 `<app-name>`
- 镜像：首次构建产物的完整 URL
- 副本：按需求，未说明时参考同类项目并向用户确认
- 容器端口：前端 Nginx 通常为 `80`
- requests/limits：遵循当前环境规范，不复制无意义的空值
- 健康检查：只有项目和平台配置一致时开启

保存后读取 YAML 记录或资源状态，确认 Deployment 已部署。

### 4.3 Service

创建稳定的 ClusterIP Service：

| 字段 | 建议 |
| --- | --- |
| 名称 | `<app-name>-svc` |
| Service port | `80` |
| target/container port | `80` 或项目实际监听端口 |
| NodePort | 共享 Nginx 通过集群 DNS 访问时不需要 |

共享 Nginx 的上游通常使用：

```text
http://<service-name>.<namespace>/<base-path>/
```

配置公共入口前必须确认 Service 已部署、存在 Endpoint、Pod Ready。

## 5. 部署和验证

拓扑应用存在后，部署精确镜像：

```http
POST /devops/cicd/v1.0/job/deployByImage
Content-Type: application/json;charset=UTF-8

{
  "appId": <app-id>,
  "image": "<full-image-url>"
}
```

依次验证：

1. `/devops/cicd/v1.0/job/getStatus?appId=<id>&resourceType=2`
2. `/devops/app/getResourceStatus?appId=<id>` 中 Deployment 和 Service 均已部署
3. `/devops/k8s/pod/getAppPods?appId=<id>` 中 Pod 为 `Running`
4. Ready 数达到预期，例如 `1/1`
5. 容器镜像与构建产物完全一致
6. Service 名和端口与共享 Nginx 上游一致

Pod 名属于短期状态，记录时注明时间，不把它当下一次操作目标。

## 6. 仓库映射

全部验证后，按 `trs-apollo` 的层级更新：

```text
repositories[repoKey].systems[systemCode]
```

记录：

- 系统名、code、ID
- 流水线 ID、名称、Jenkins/GitLab、ref 类型和值
- 拓扑 `appId`、`appName`、`projectName`
- 当前完整镜像
- `updatedAt`

不要把 PUBLIC Nginx 应用写成业务仓库的拓扑映射；它是共享基础设施，只在操作记录中引用。

## 7. 常见错误

- **复制参考项目 ID**：名称相似不表示同一资源，所有 ID 都要在当前系统重新发现。
- **先建入口再建 Service**：容易直接产生 502；顺序必须是 Pod/Service 正常后再配入口。
- **只看 `jobState`**：Apollo 字段可能滞后，必须读 Jenkins 日志和镜像列表。
- **构建分支和 tag 混用**：同时修改 `gitPullMethod` 与 `gitBranch`。
- **Dockerfile 路径不一致**：`WORKDIR`、`COPY dist`、项目 Nginx `alias`、共享入口基路径必须一致。
- **接口缺失时转向页面或猜请求**：从已确认的接口资料核对契约；仍有缺口时报告并暂停相关步骤，不打开浏览器、不抓包、不猜接口。
