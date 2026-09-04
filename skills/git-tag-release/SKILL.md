---
name: git-tag-release
description: 在规划或执行 TRS 部署 tag、打 tag、发版、推 RC tag、生成下一个版本号，或需要回写 package.json tag 字段并推送到远端时使用；writing-plans 阶段涉及发版任务时必须使用。
---

# Git Tag Release

## writing-plans 阶段要求

当本技能用于实施计划阶段时，计划必须写清：

- 本技能约束适用于哪些任务。
- 计划的 `Required TRS skills` 中必须列出 `git-tag-release`。
- 目标仓库、remote、目标环境 `target`、tag prefix、versionType 或部署流水号规则、suffix、是否回写 `package.json.tag`、是否推送当前分支。
- 预览、用户确认、执行脚本和推送 tag 的步骤边界。
- 验证方式：预览结果、git status、tag 是否存在、push 结果；发版前需要 `pnpm build` 时，必须先获得用户明确确认。

## 适用场景

- 用户想在当前仓库里按既有规则生成下一个 tag。
- TRS Jenkins 部署需要按开发/生产环境生成 `<缩写>-dev-v<a>.<b>.<c>` 或 `<缩写>-prod-v<a>.<b>.<c>` tag。
- 仓库根目录有 `package.json`；部署流水号模式优先从 `package.json#tag` 或 `package.json#tagPrefix` 读取项目缩写；都没有时才从工程/仓库目录名推导项目缩写，不从 `package.json#name` 推导，因为脚手架项目的 `name` 可能相同。
- 用户希望从已有 git tags 推导下一个 `major`、`minor`、`patch` 或 `RC` 版本。
- 用户希望可选地把结果写回 `package.json.tag`，提交 `package.json`，再创建并推送 tag。

## 核心原则

- 始终先预览，再执行。
- 预览阶段把“将要打的 tag”明确展示给用户。
- 如果用户改参数，就重新预览。
- 一旦用户确认，用预览产出的最终 tag 原样传给执行脚本，避免 `RC` 时间戳漂移。
- TRS 部署默认使用目标环境流水号规则，不要求把 tag 规则写入 `deploy.json`。

## 参考文档

- 需要判断提交粒度、提交信息或 GitLab MR 说明时，读取 `references/git.md`。

## Bundled Script

使用 skill 自身目录里的 `scripts/git-tag-release.cjs`，不要手写一整串 git 命令。

不要在 bash 里写相对路径 `node scripts/git-tag-release.cjs ...`。

原因：命令通常会在目标仓库目录执行，相对路径会指向当前仓库的 `scripts/`，而不是 skill 目录本身。无论 skill 安装在项目本地还是全局目录，都必须先从当前已加载的 skill 元信息里拿到 `Base directory for this skill`，将其中的 `file://` 路径转换为本地绝对路径，再执行脚本。

示意：

```text
Base directory for this skill: file:///Users/name/.agents/skills/git-tag-release
=> 本地脚本绝对路径: /Users/name/.agents/skills/git-tag-release/scripts/git-tag-release.cjs
```

它有两个子命令：

- `preview`
  读取仓库配置、拉取 tags、计算候选 tag、输出风险和将执行的动作。
- `execute`
  再次校验并正式执行：可选回写 `package.json.tag`、提交 `package.json`、可选推送当前分支、创建 tag、推送 tag。

## AI 工作流

### 1. 收集参数

至少确认：

- `cwd`
- `remote`
- `target`
  TRS 部署传 `dev` 或 `prod`；非部署语义版本场景可为空
- `prefix`
  可为空；TRS 部署会优先从 `package.json#tag` 或 `package.json#tagPrefix` 提取业务缩写，再拼接本次目标环境；非部署场景沿用 `package.json#tagPrefix[0]`
- `versionType`
  非 TRS 部署场景允许 `major`、`minor`、`patch`、`RC`
- `suffix`
- `editPkg`
- `pushBranch`
  部署流程中如果会生成 `package.json.tag` 提交，建议为 `true`

默认值建议：

- TRS 部署：传 `--target dev|prod`，使用部署流水号规则
- 非部署语义版本：`versionType=patch`
- `suffix=""`
- `editPkg=true`
- `pushBranch=false`；部署流程需要远端分支可追溯时传 `true`
- `remote` 默认取第一个 remote
- `prefix` 在 TRS 部署中优先由包内记录的业务缩写加目标环境生成：先读 `package.json#tag`，再读 `package.json#tagPrefix`，再看对应环境已有唯一历史前缀，最后才按工程/仓库目录名生成

### 2. 运行预览

TRS 部署默认预览：

```bash
node "/absolute/path/to/git-tag-release/scripts/git-tag-release.cjs" preview --cwd /path/to/repo --remote origin --target dev --edit-pkg true --push-branch true --json
```

非部署语义版本预览：

```bash
node "/absolute/path/to/git-tag-release/scripts/git-tag-release.cjs" preview --cwd /path/to/repo --remote origin --prefix v- --version-type RC --suffix "" --edit-pkg true --json
```

预览结果里重点看：

- `finalTag`
- `prefix`
- `target`
- `prefixSource`
- `targetPrefixes`
- `tagPrefixes`
- `actions`
  仅用于内部核对脚本将执行的动作，不要把 `actions` 原样作为代码块打印给用户。
- `warnings`
- `ready`
- `problems`

### 3. 给用户确认

明确告诉用户：

- 将要打的 tag 是什么
- 当前目标环境是什么；TRS 部署必须展示 `dev` 或 `prod`
- 当前使用的前缀是什么
- 前缀来源是什么：用户显式指定、`package.json#tag`、`package.json#tagPrefix`、已有历史 tag，还是工程目录名推导
- 是否会改 `package.json.tag`
- 是否会提交 `package.json`
- 是否会推送当前分支
- 将推送到哪个 remote

用户确认文案保持简洁，只展示上述摘要字段；不要额外打印“脚本预览到的动作是”或原始命令动作列表。需要说明风险时，用中文短句概括，不贴整段 `actions`。

如果 TRS 部署能从 `package.json#tag` 解析出业务缩写，例如 `cq-dev-v0.1.8` 解析为 `cq`，则本次目标环境由用户请求决定：开发部署使用 `cq-dev-v`，生产部署使用 `cq-prod-v`。同一环境下已有多个历史前缀时，如果包内记录已经明确业务缩写，继续使用包内记录；只有包内没有可用记录时，才停止并让用户选择。用户选择后用 `--prefix <prefix>` 重新预览。

如果非部署语义版本里用户没有明确指定 `prefix`，还必须补充：

- 当前是按默认前缀预览的
- `tagPrefixes` 里还有哪些可选前缀
- 用户如果想切换前缀，可以直接说“改成 `<prefix>` 再预览/执行”

如果 `ready=false` 或 `problems` 非空，先解决问题，不要执行。

### 4. 用户修改参数时

- 修改 `remote`、`prefix`、`versionType`、`suffix` 或 `editPkg` 后，重新跑一次 `preview`
- 不要沿用旧的 `finalTag`

### 5. 用户确认后执行

将预览产出的 `finalTag` 作为 `--tag` 传给执行脚本。TRS 部署示例：

```bash
node "/absolute/path/to/git-tag-release/scripts/git-tag-release.cjs" execute --cwd /path/to/repo --remote origin --target dev --tag "cq-dev-v0.1.0" --edit-pkg true --push-branch true --json
```

非部署语义版本示例：

```bash
node "/absolute/path/to/git-tag-release/scripts/git-tag-release.cjs" execute --cwd /path/to/repo --remote origin --tag "v-1.2.3-RC-20260417153045" --edit-pkg true --json
```

这样执行时不会重新生成另一个 RC 时间戳。

## 规则说明

### 1. TRS 部署 tag 规范

TRS Jenkins 部署默认使用：

```text
<项目缩写>-dev-v<a>.<b>.<c>
<项目缩写>-prod-v<a>.<b>.<c>
```

- `dev` 和 `prod` 是两条独立版本线，互不影响。
- 项目缩写优先来自包内记录：`package.json#tag` 可使用完整历史 tag，例如 `cq-dev-v0.1.8`；`package.json#tagPrefix` 在 TRS 部署中推荐记录业务缩写，例如 `["cq"]`，也兼容从完整环境前缀如 `["cq-dev-v"]` 提取 `cq`。本次环境仍由用户请求决定，不从旧 tag 固定继承。
- 先拉取远端 tags，再查找对应环境历史 tag。
- 如果包内记录能提取项目缩写，使用 `<项目缩写>-<目标环境>-v` 作为前缀；历史 tag 只用于计算这个前缀下的下一个版本号。
- 如果对应环境已有唯一历史前缀，例如 `cq-dev-v`，继续沿用它递增，不要重新按工程/仓库目录名生成缩写。
- 如果对应环境已有多个历史前缀，但包内记录已经明确项目缩写，例如 `package.json#tag` 是 `cq-dev-v0.1.8`，开发部署继续用 `cq-dev-v`，生产部署继续用 `cq-prod-v`。
- 如果包内没有可用记录且对应环境已有多个历史前缀，停止并让用户选择。
- 如果包内没有可用记录且对应环境没有历史 tag，才根据工程/仓库目录名生成新前缀，首个 tag 为 `<缩写>-<环境>-v0.0.0`。

### 2. TRS 部署递增规则

部署流水号只自动递增，不让日常部署选择 `major/minor/patch`：

```text
0.0.0 -> 0.0.1
0.0.99 -> 0.0.100
0.0.100 -> 0.1.0
0.100.100 -> 1.0.0
```

规则：

- `c < 100` 时，`c + 1`。
- `c = 100` 且 `b < 100` 时，`b + 1`，`c` 归 `0`。
- `b = 100` 且 `c = 100` 时，`a + 1`，`b` 和 `c` 归 `0`。

### 3. 非部署语义版本解析已有 tags

- 对每个 tag，从中提取首个匹配 `(\d+\.\d+\.\d+)` 的版本号参与基线计算。
- 只要 tag 在对应前缀下能解析出版本号，就会纳入该前缀的版本序列；后缀如 `-RC-*`、`-beta`、自定义说明不会阻止版本号被提取。
- 按前缀分组维护版本序列；不同前缀互不影响。
- 某个前缀下没有任何可解析版本号的历史 tag 时，基线视为 `0.0.0`。

### 4. 非部署语义版本递增规则

- `major`：`X+1.0.0`
- `minor`：`X.Y+1.0`
- `patch`：`X.Y.Z+1`
- `RC`：基于该前缀当前解析出的最新版本号，生成
  `<latest-version>-RC-<yyyyMMddHHmmss>`

### 5. 拼接规则

最终 tag 结构：

```text
<prefix><version><suffix>
```

## 安全边界

- 在执行前，一定要给用户看 `finalTag`。
- 只处理本次发版相关文件；不要还原用户已有改动或无关文件。
- 如果 tag 已存在，不要执行。
- 如果 `editPkg=true`，要提示会修改 `package.json` 并尝试提交。
- 如果部署流程使用 `editPkg=true` 生成了 `package.json.tag` 提交，应使用 `--push-branch true` 或由部署 skill 负责把当前分支推送到远端，保证远端分支也能查到这个版本提交。
- 如果工作区有未提交修改，尤其是 `package.json` 有改动，要把 warning 明确转述给用户。
- 不要为了同步远端 tags 而删除本地全部 tags；脚本只做 `git fetch <remote> --tags`。
- 不得默认执行 `pnpm build`；如果判断发版前必须构建验证，先说明原因并等待用户确认。

## 常见失败

- `package.json` 不是合法 JSON
- 非部署语义版本里 `tagPrefix` 不是数组或为空
- 没有任何 remote
- `git fetch` 失败
- tag 已存在
- 包内没有可用项目缩写，且同一环境存在多个历史 tag 前缀，需要用户选择
- `git push <remote> <tag>` 被权限或保护策略拒绝
- `--push-branch true` 但当前处于 detached HEAD 或分支推送失败

## 示例请求

- “部署开发环境，按 TRS tag 规则生成下一个 tag”
- “推一个 rc 的 tag”
- “按这个仓库的 `tagPrefix` 规则生成下一个 patch tag，并推到 `origin`”
- “用 `web-` 前缀发一个 minor 版本，不要改 `package.json`”
- “把下一个 tag 算出来，我确认后再推”
