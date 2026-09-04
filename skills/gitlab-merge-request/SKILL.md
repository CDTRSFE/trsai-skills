---
name: gitlab-merge-request
description: 当用户要求提交、创建、发起 MR/merge request/合并请求，尤其是“提交 MR 到 master”时使用；用于推送当前源分支并在 GitLab 创建 MR，默认目标分支 master、默认分配给 puyuchun。
---

# GitLab Merge Request

## 核心目标

把当前项目分支推送到远程，并创建 GitLab Merge Request。默认行为是：源分支为当前 Git 分支，目标分支为 `master`，分配人为 `puyuchun`。创建成功后，把 MR 地址明确告诉用户，并说明推送成功。

这是 TRS 团队的 GitLab MR 流程。除非用户明确说项目使用其他代码托管平台，否则不要提非 GitLab 平台、非 GitLab 合并流程或非 GitLab CLI。

## 触发场景

用户出现以下意图时使用本技能：

- “提交 MR 到 master”
- “提个 MR”
- “创建 merge request”
- “发起合并请求”
- “把当前分支提交到 master”
- “推送并提交 MR”

如果用户只是要求 `commit`、普通 `push`、按 Jira 信息提交或收尾，优先使用 `jira-git-workflow`；只有用户明确要创建 MR 时，才使用本技能。

## 默认参数

按以下优先级确定参数：

- 源分支：用户明确指定的源分支；否则使用当前 Git 分支。
- 目标分支：用户明确指定的目标分支；否则使用 `master`。
- 分配人：用户明确指定的分配人；否则使用 `puyuchun`。
- remote：优先使用当前分支 upstream 对应 remote；没有 upstream 时默认 `origin`。
- MR 标题：优先使用用户明确给出的标题；否则根据最近一次 commit 信息、分支名或 Jira 上下文生成简洁标题。无法判断时先问用户。

注意：用户说“提交 MR 到 master”时，`master` 是目标分支，不是源分支。

## 第一响应与耗时控制

用户要求“提交 MR”后，第一条可见回复必须简短说明将要做的事情和边界，不要先沉默执行大量检查。建议话术：

```text
我先做 GitLab MR 的最小前置检查：当前分支、工作区状态、upstream/remote 和是否已有可推送提交；不会先暂存、提交、推送或创建 MR。
```

前置检查保持轻量，只做能直接判断 MR 是否可创建的 Git/GitLab 信息。不要在创建 MR 前自动触发完整代码审查、build、测试、全仓搜索、依赖安装、浏览器验证或非必要的远程同步。

如果因为 `git fetch`、网络、认证或仓库体积导致等待超过约 30 秒，应先告诉用户当前卡在哪一步、已经看到什么、下一步要等什么；不要等全部命令结束后才汇报。

## 执行前检查

创建 MR 前只检查并向用户说明关键上下文：

1. 当前仓库路径和当前分支。
2. `git status --short` 工作区状态。
3. 当前分支 upstream、remote 和 GitLab 项目地址。
4. 源分支相对目标分支是否有可提交到 MR 的 commit。
5. 将使用的源分支、目标分支、分配人、MR 标题。
6. 将执行的推送和创建 MR 命令。

推荐最小命令集合：

```bash
git branch --show-current
git status --short
git remote -v
git rev-parse --abbrev-ref --symbolic-full-name @{u}
git log --oneline <目标分支>..<源分支>
```

如果本地目标分支或远程引用过旧，可以执行一次 `git fetch <remote> <目标分支>` 后再判断差异。不要因为要创建 MR 就扫描整个仓库或检查无关 CLI。

如果工作区有未提交改动，不要自动提交、暂存、还原或删除。先提示用户当前还有未提交内容，询问是否继续只推送已有 commit，或先进入提交流程。

如果当前分支是 `master`，或源分支与目标分支相同，必须停止并提醒用户切换或指定正确源分支。

## 推送分支

创建 MR 前必须确保源分支已经推送到远程：

- 当前分支已有 upstream：执行 `git push`。
- 当前分支没有 upstream：执行 `git push -u <remote> <源分支>`。
- 用户指定了非当前源分支时，先确认该分支在本地或远程存在；不存在则停止说明。

如果 `git push` 因远程分支有本地没有的新提交而失败，例如 `fetch first`、`non-fast-forward`，不要自动改写历史。说明失败原因，并询问用户是否执行 `git pull --rebase` 或其他同步方式。

## 创建 MR

只使用 GitLab 相关工具链：

1. 如果仓库或环境已配置 `glab`，优先使用 `glab mr create`。
2. 如果没有 `glab`，但项目提供脚本或文档中已有 MR 创建命令，按项目方式执行。
3. 如果只能通过 GitLab API 创建，先确认可用的 GitLab 地址、project id 或远程 URL 解析结果，以及 token 环境变量；不要在对话中要求用户明文粘贴 token。

不要检查或建议安装任何非 GitLab CLI；它们不能作为本技能的 MR 创建路径。

`glab` 命令示例：

```bash
glab mr create --source-branch <源分支> --target-branch <目标分支> --assignee <分配人> --title "<MR标题>"
```

如果需要描述，可以优先使用简洁说明，例如本次分支的最近提交摘要；没有必要编造详细 MR 描述。

## 已有 MR 处理

创建前尽量检查是否已存在相同源分支到目标分支的 open MR：

- 如果已存在，直接给出已有 MR 地址，并说明没有重复创建。
- 如果工具无法可靠检查，创建失败且提示重复 MR 时，转为查询或让用户打开失败信息里的地址。

## 成功反馈

成功后必须告诉用户：

- 分支已推送成功。
- MR 已创建成功。
- MR 地址。
- 源分支、目标分支和分配人。

示例：

```text
推送成功，MR 已创建：

- 源分支：feature/demo
- 目标分支：master
- 分配人：puyuchun
- 地址：https://gitlab.example.com/group/project/-/merge_requests/123
```

## 安全边界

- 不得在用户明确确认前执行会创建 MR 的操作；执行前需要展示将使用的参数。
- 不得在本技能中自动 `git add`、`git commit`、`git reset`、`git checkout --` 或删除文件。
- 不得把未提交改动偷偷带入 MR 流程；只能推送已经存在的 commit。
- 不得默认 force push。除非用户明确要求并理解影响，否则不要执行 `--force` 或 `--force-with-lease`。
- 如果权限、认证、分支保护或 token 缺失导致失败，停止并说明需要用户处理的具体信息。
- 如果无法判断 GitLab 项目地址或 MR 创建工具不可用，先说明缺少的依赖或配置，不要假装已创建。
- 不得把 GitLab MR 说成其他平台的合并流程；最终反馈和中间进度统一使用“GitLab / MR / 合并请求”。

## 常见请求示例

- “提交 MR 到 master。”
- “把当前分支提 MR，分配给 zhangsan。”
- “源分支 feature/a，目标分支 release/1.2，提交一个 MR。”
- “推送当前分支并创建 merge request。”
