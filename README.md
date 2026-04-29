# trsai-skills

TRS 前端团队 AI 规则与技能集。脚手架项目已内置 ESLint、stylelint、Prettier 和 commit 阶段校验，本仓库只保留 AI 每次都应遵守的短规则，以及需要上下文判断或工具执行的条件技能。

## 文件分工

| 位置 | 用途 |
|------|------|
| `AGENTS.md` | Codex 常驻项目规范，放短规则 |
| `CLAUDE.md` | Claude Code 项目记忆入口，通过 `@AGENTS.md` 复用同一套规则 |
| `skills/*/SKILL.md` | 条件触发技能，处理需求澄清、接口、表单、Store、组件、样式、发版和 Review |
| `docs/conventions/*` | 团队规范参考，基础格式和风格优先交给脚手架校验 |
| `.codex-plugin/plugin.json` | Codex 插件声明，技能目录指向 `./skills/` |
| `.claude-plugin/marketplace.json` | Claude skills 安装声明 |

## Claude Code 使用

Claude Code 读取当前项目的 `CLAUDE.md`，不会直接读取 `AGENTS.md`。推荐做法：

1. 在当前要开发的业务项目中打开 Claude Code，不要把 `trsai-skills` 当作业务项目打开。
2. 安装本仓库 skills：

```bash
npx skills add CDTRSFE/trsai-skills --global
```

3. 业务项目如已有 `AGENTS.md`，在项目根目录放一个很薄的 `CLAUDE.md`：

```md
@AGENTS.md

## Claude Code 补充

- 通用规则维护在 `AGENTS.md`，Claude Code 通过本文件导入。
```

4. Claude 专属补充才写在 `CLAUDE.md`；通用团队规则优先维护在 `AGENTS.md`。

## Codex 使用

Codex CLI / App 默认读取 `AGENTS.md`。推荐做法：

1. 如你的 Codex 环境支持 `skills` 安装器，优先直接用：

```bash
npx skills add CDTRSFE/trsai-skills --global --yes
```

更新时直接执行：

```bash
npx skills update trsai-skills --global --yes
```

说明：

- 通过 `npx skills add/update` 安装到 Codex 时，skills 安装器实际通常会把 skill 落到 `~/.agents/skills/`，Codex 会从这里识别，而不一定写入 `~/.codex/skills/`。
- `update` 负责覆盖当前仓库里仍然存在的 skill；如果仓库后来删除了某个 skill，安装器不会自动帮你清理本机上旧的目录。
- 如果某个旧 skill 已经从 `trsai-skills` 仓库移除，但你在 Codex 里还能看到，优先检查并删除 `~/.agents/skills/<skill-name>` 里的旧目录，然后重启 Codex。

2. 把团队通用规则放到 Codex 全局配置，一台电脑做一次即可：

```bash
mkdir -p ~/.codex
cp /path/to/trsai-skills/AGENTS.md ~/.codex/AGENTS.md
```

3. 在当前要开发的业务项目中打开 Codex CLI 或 Codex App。
4. 业务项目特殊规则写在该项目根目录的 `AGENTS.md`；子目录强约束可用 `AGENTS.override.md`。

### Codex 进阶：从 GitHub 镜像安装

如果当前 Codex 环境不支持 `npx skills add/update`，或者你想明确控制安装到 `~/.codex/skills` 的目录结构，再使用下面的底层方式。

如果这个仓库已经推到 GitHub，而你希望其他同事或另一台机器直接从远端同步到 Codex，本仓库建议分两部分处理：

1. 同步全局规则 `AGENTS.md`

```bash
mkdir -p ~/.codex
curl -L https://raw.githubusercontent.com/CDTRSFE/trsai-skills/main/AGENTS.md -o ~/.codex/AGENTS.md
```

2. 把仓库里的 skills 安装到 `~/.codex/skills`

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo CDTRSFE/trsai-skills \
  --path skills/ai-collaboration \
  --path skills/api-integration \
  --path skills/css-patterns \
  --path skills/form-validation \
  --path skills/git-tag-release \
  --path skills/pinia-store-design \
  --path skills/trs-code-review \
  --path skills/vue-component-design
```

说明：

- 上面命令会把每个 skill 安装到 `~/.codex/skills/<skill-name>`。
- 这条“底层安装”路径和 `npx skills add/update` 不同：前者直接写 `~/.codex/skills/`，后者在 Codex 下通常写 `~/.agents/skills/`。
- 本仓库的 Codex 插件入口是 `.codex-plugin/plugin.json`，其中 `skills` 指向 `./skills/`，见 [plugin.json](.codex-plugin/plugin.json)。
- 安装完成后重启 Codex，新的 skills 才会被识别。

### Codex 进阶：从 GitHub 镜像更新已安装 skills

`install-skill-from-github.py` 在目标目录已存在时会中止，所以更新最稳妥的方式是先删旧目录，再重新安装：

```bash
rm -rf \
  ~/.codex/skills/ai-collaboration \
  ~/.codex/skills/api-integration \
  ~/.codex/skills/css-patterns \
  ~/.codex/skills/form-validation \
  ~/.codex/skills/git-tag-release \
  ~/.codex/skills/pinia-store-design \
  ~/.codex/skills/trs-code-review \
  ~/.codex/skills/vue-component-design
```

然后重新执行上面的安装命令，并重启 Codex。

如果只更新某一个 skill，就只删除并重装对应目录即可。

### Codex 进阶：清理已从仓库移除的旧 skills

如果你之前通过 `npx skills add/update` 安装过本仓库，而仓库后续删掉了某个 skill，`update` 不会自动清掉本机旧目录。此时应手动删除 `~/.agents/skills/<skill-name>` 对应目录，再重启 Codex。

例如，先查看本机当前有哪些 TRS skills：

```bash
find ~/.agents/skills -mindepth 1 -maxdepth 1 -type d | sort
```

确认后删除已经不再由 `trsai-skills` 提供的目录即可。

验证是否读取规则，可直接问：

```text
请总结当前加载的 AGENTS.md 项目规范，并说明你会如何处理验证。
```

## Agent 与 Skill 分工

- `AGENTS.md` / `CLAUDE.md`：常驻短规则，每次都应遵守。
- `skills/*/SKILL.md`：特定场景才触发，避免把基础格式、命名、模板细节都做成 skill。
- Superpowers：负责规划、TDD、系统调试、验证、请求代码审查等流程纪律。
- TRS skills：负责团队领域规范、前端实现判断、发版工具和收尾审查。

## 推荐工作流

复杂需求、新页面、新组件体系或跨接口/表单/Store/权限的改动，默认按下面流程：

```text
brainstorming -> writing-plans -> 执行 -> review
```

- `brainstorming`：产出设计文档，明确目标、范围、交互、数据流、组件边界和验收标准。
- `writing-plans`：产出实施计划，并按任务类型结合 TRS skills，例如接口用 `api-integration`，表单用 `form-validation`，样式用 `css-patterns`，Store 用 `pinia-store-design`，组件拆分用 `vue-component-design`。
- 执行：按计划修改代码；如果遇到计划外的新领域问题，再补充调用对应 TRS skill。
- `review`：完成验证后用 `trs-code-review` 做 TRS 前端收尾审查。

小型 bug、文案、类型、配置、样式微调或低风险重构不强制产出完整 spec/plan。处理时应先确认范围或根因，按需调用领域 skill，直接修改并说明验证结果。

## 技能列表

| 技能 | 触发场景 |
|------|---------|
| `ai-collaboration` | 模糊前端需求的信息清单，补齐页面、接口、交互、权限和验收上下文 |
| `api-integration` | 封装 HTTP 请求、设计 API 层、处理错误和加载状态 |
| `css-patterns` | 任意页面或组件样式编写/调整、样式覆盖、局部布局、响应式、z-index、UnoCSS 与 CSS/Less 取舍 |
| `form-validation` | 新增/编辑表单、表单提交、校验规则（Ant Design Vue / Vant） |
| `git-tag-release` | 打 tag、发版、推 RC tag、管理 package.json tag 前缀 |
| `pinia-store-design` | 决定是否建 store、设计 store 结构、跨组件状态共享 |
| `vue-component-design` | 设计新组件、重构组件、组件拆分策略 |
| `trs-code-review` | TRS 前端代码审查、提交前检查、MR/PR 前检查、完成验收 |

Superpowers 结合方式见 `docs/superpowers-codex.md`。

## 更新规范

- 每次都要遵守的短规则：改 `AGENTS.md`。
- Claude Code 入口或专属补充：改 `CLAUDE.md`。
- 特定场景技能：改 `skills/<skill-name>/SKILL.md`。
- 可被 lint/stylelint/commit 校验覆盖的规范：改 `docs/conventions/*` 或脚手架规则。
- Codex 插件元信息：改 `.codex-plugin/plugin.json`。
- Claude skills 安装声明：改 `.claude-plugin/marketplace.json`。

## 目录结构

```text
AGENTS.md                 ← Codex 常驻项目规范
CLAUDE.md                 ← Claude Code 项目记忆入口，导入 AGENTS.md
skills/
  <skill-name>/
    SKILL.md              ← 条件触发技能
docs/
  conventions/            ← 团队规范参考文档
.codex-plugin/
  plugin.json             ← Codex 插件声明
.claude-plugin/
  marketplace.json        ← Claude 插件声明
```
