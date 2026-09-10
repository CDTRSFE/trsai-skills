---
name: trs-apollo-bootstrap-project
description: Use when onboarding a new frontend project to TRS Apollo, especially when the request involves a new pipeline, first image build, topology application, Kubernetes Deployment or Service, or a shared PUBLIC Nginx development entry.
---

# TRS Apollo 新工程部署

## 概览

把一个已有代码仓库从“尚未接入 Apollo”推进到“开发环境可访问”，覆盖流水线、首个镜像、拓扑资源、项目 Nginx 和共享入口。每个写操作都必须先发现、再确认、再回读验证。

**REQUIRED SUB-SKILL:** 使用 `trs-apollo` 完成 Apollo 认证、系统发现、流水线、镜像、拓扑和 Pod API 操作。本 Skill 只补充“新工程端到端接入”流程，不复制基础 API 文档。

本 Skill 仅使用命令行和已确认的 Apollo API，不依赖额外的 Git Skill。不调用浏览器 Skill、浏览器 MCP 或浏览器 CLI，不打开 Apollo 页面，不执行页面登录、抓包或切换浏览器；认证、接口发现、创建、部署和验收均遵守此边界。凭据或接口资料不足时，报告缺口并暂停相关步骤，补齐并验证后再继续。

## 按需读取

- 执行流水线创建、首次构建和拓扑创建前，完整读取 [references/apollo-workflow.md](references/apollo-workflow.md)。
- 添加项目 Nginx 或共享 PUBLIC Nginx 路由前，完整读取 [references/nginx-routing.md](references/nginx-routing.md)。
- 需要参考一套已验证参数或核对交付记录格式时，读取 [references/meishan-fx-map-example.md](references/meishan-fx-map-example.md)。实例中的 ID、Pod 名和镜像只能作为历史记录，不能直接复用。

## 不可跳过的安全门

1. **先只读发现。** 确认仓库、Apollo 系统、命名空间、同名流水线、同名拓扑、镜像仓库、共享 Nginx 应用和当前配置。
2. **确认目标后再写。** 至少向用户汇报系统、项目名、分支或 tag、构建命令、Node 版本、镜像名、拓扑名、访问路径及所有歧义。
3. **分阶段授权。** 创建/修改流水线、触发构建、部署镜像、进入容器 shell、修改共享 Nginx 分别遵守 `trs-apollo` 的确认规则；前一步授权不自动覆盖后一步。
4. **不存凭据。** Skill、项目文件、日志和最终回复中不得写入完整 Token、Cookie、登录密文或其他凭据。
5. **先确认接口契约。** 创建前，从 API 参考、已验证的请求记录或用户提供的接口资料核对请求方法、路径、必填字段和回读方式。信息不足时报告已确认内容与缺失信息，暂停依赖该接口的步骤；不猜接口，不转向浏览器或页面表单。
6. **每次写后回读。** 创建后读详情，构建后读日志和镜像，部署后读 Pod，上传 Nginx 后重新下载并比较内容。
7. **共享 Nginx 必须可回滚。** 写入前备份；`nginx -t` 失败立即恢复且禁止 reload；成功时只做平滑 reload，不停止共享服务。
8. **保护现有入口。** 新入口验证时同时抽查至少一个修改前已存在的路由。

## 必要输入

| 输入 | 获取方式 |
| --- | --- |
| Git 仓库与远端 | `git rev-parse --show-toplevel`、`git remote get-url origin` |
| Apollo 系统/命名空间 | 用户指定；未指定时按 `trs-apollo` 默认系统发现 |
| 项目标识 | 用户确认的流水线名、镜像名、拓扑 `appName` |
| 展示名 | 用户确认的拓扑 `projectName`，不要默认等于 `appName` |
| 构建 ref | 明确分支或裸 tag，并配套正确 `gitPullMethod` |
| 构建环境 | 包管理器、锁文件、Node 版本、构建命令、输出目录 |
| 访问基路径 | 例如 `/project-name/`，需和构建产物、项目 Nginx、共享路由一致 |
| 参考项目 | 仅用于复制经验证的字段结构；所有 ID 和名称重新发现 |

## 端到端流程

### 1. 仓库预检

- 检查远端、当前分支、工作区状态、最新提交、锁文件、构建脚本、Vite `base`、现有 Dockerfile/Nginx。
- 判断流水线构建是否要求远端已包含部署文件。若需要新增 `nginx.conf`，先完成项目内配置并按用户授权提交、推送。
- 不覆盖用户未提交改动，不为了接入流水线做无关重构。

### 2. 形成并确认部署摘要

在任何写操作前，向用户提供：

- 系统名/系统 code/命名空间
- 流水线名、Git 地址、分支或 tag、Jenkins/GitLab 连接、Node 版本、打包命令
- 镜像仓库、镜像名、Dockerfile 来源
- 拓扑 `appName`、`projectName`、Deployment、Service、端口和副本数
- 开发环境访问 host、路径和共享 Nginx 目标应用

存在多个候选项时停止并询问，不按相似名称选择。

### 3. 准备项目部署文件

- 为前端单页应用准备根目录 `nginx.conf`，同时处理无尾斜杠跳转、静态资源和 history fallback。
- 确认镜像内工作目录、`COPY dist` 目标和 Nginx `alias` 完全一致。
- 使用仓库既有验证规则检查构建；不要新增无需求的测试文件。

### 4. 创建流水线并首次构建

- 查同名流水线；存在时读取并让用户决定复用还是修改，禁止重复创建。
- 读取参考流水线完整详情，只替换目标项目相关字段。新建时提交完整 payload，不提交猜测的局部字段。
- 创建后重新读取流水线，核对 ref 类型、ref 值、Node、打包命令、镜像目录、Dockerfile 模式。
- 触发构建后以 Jenkins 日志中的 `Finished:` 为准，并交叉查询镜像列表得到精确镜像 URL。
- 构建成功后先汇报镜像，再询问是否部署到拓扑。

### 5. 创建拓扑并部署

- 查同名拓扑；存在时核对真实应用，不重复创建。
- 新建应用后创建 Deployment 和 Service：镜像使用本次构建的完整 URL，Service 名保持稳定，端口映射与容器监听一致。
- 通过 `deployByImage` API 部署精确镜像；轮询部署状态和 Pod，必须达到 `Running`、期望 Ready 数和正确镜像。
- 记录 `appId`、资源状态、Service DNS、镜像和 Pod；写入 `trs-apollo/state/repository-map.json` 前先完成实际验证。

### 6. 配置共享 PUBLIC Nginx

- 这是独立的高风险阶段，必须再次获得用户明确授权。
- 动态发现 PUBLIC 系统、Nginx 应用、当前 Pod、容器和配置文件；不要复用历史 Pod 名。
- 下载当前配置并计算哈希，确认目标 `location` 不存在或与期望一致。
- 备份原文件，插入最小路由，上传后回读比对；执行 `nginx -t`，通过后执行 `nginx -s reload`。
- 如果配置在读取和写入之间发生变化，停止写入并重新开始，不覆盖他人变更。

### 7. 最终验收

- 通过 HTTP 请求检查新 URL 的状态码、HTML 中的 `<title>` 或稳定文本标识。
- 至少一个旧路由仍正常。
- 共享 Nginx 与业务 Pod 均为 `Running` 且 Ready。
- Apollo 流水线、拓扑、镜像和远端 Git ref 与记录一致。
- 项目仓库无本次流程遗留的临时文件。

## 决策与异常处理

| 情况 | 处理 |
| --- | --- |
| 会话缓存缺失或 API 明确返回会话失效 | 按 `trs-apollo` 读取钥匙链凭据并调用登录 API，重新验证后继续 |
| 登录凭据缺失、无法读取或 API 登录失败 | 报告脱敏错误并暂停依赖认证的步骤，不转向浏览器 |
| 创建或资源接口契约缺失 | 报告缺失的方法、路径、字段或回读方式，暂停相关步骤，不使用页面兜底 |
| 同名流水线/拓扑有多个 | 停止，向用户展示候选并确认 |
| 分支/tag 不存在 | 不保存流水线，不触发构建 |
| 构建日志成功但详情状态滞后 | 以日志和新镜像交叉验证，不只看 `jobState` |
| 构建成功但用户未授权部署 | 只汇报镜像并等待 |
| Service 无 Endpoint 或 Pod 未 Ready | 不配置公共入口，先修复拓扑 |
| 共享路由已存在且内容不同 | 展示差异并重新确认，禁止追加重复 `location` |
| 上传后哈希不一致 | 禁止 `nginx -t`/reload，恢复或重新读取 |
| `nginx -t` 失败 | 恢复备份，再验证旧配置；禁止 reload |
| reload 失败 | 保留备份，汇报实际状态；不使用 stop/start 猜修 |
| 新 URL 502 | 检查 Service DNS、命名空间、Endpoint、Pod 和目标端口 |
| HTML 200 但资源 404 | 检查构建 `base`、项目 Nginx alias、代理 URI 和尾斜杠 |

## 最终汇报

只汇报可验证事实：

- 系统和命名空间
- 流水线 ID、名称、ref、构建号/时间和结果
- 完整镜像 URL
- 拓扑 `appId`、Deployment、Service、Pod Ready 状态
- 公共访问 URL、HTTP 状态和页面标识
- 共享 Nginx 配置路径、备份路径、`nginx -t` 与 reload 结果
- 旧路由抽查结果
- 本地/远端 Git 状态

不要在最终回复中输出完整 Token、Cookie、固定登录 payload 或整份共享 Nginx 配置。
